from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

import datacenter_atlas.satellite_calibration_blind_rereview as rereview_module
from datacenter_atlas.satellite_calibration_blind_rereview import (
    SatelliteCalibrationBlindRereviewError,
    _cleanup,
    _freeze,
    _fsync_directory,
    _fsync_frozen_files,
    _pin,
    _validate_source_group,
    resolve_panel,
    validate_satellite_calibration_blind_rereview,
    write_satellite_calibration_blind_rereview,
)


R = "retain_site_scale_physical_change"
J = "reject_non_site_or_unusable"
U = "uncertain"


def _without_schema_version(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_schema_version(item)
            for key, item in value.items()
            if key != "schema_version"
        }
    if isinstance(value, list):
        return [_without_schema_version(item) for item in value]
    return value


class BlindRereviewDecisionTests(unittest.TestCase):
    def test_agreement_majority_and_three_way_rules(self) -> None:
        finals, bases = resolve_panel(
            {"v2rr-000000000000000000000001":R,"v2rr-000000000000000000000002":R,"v2rr-000000000000000000000003":R},
            {"v2rr-000000000000000000000001":R,"v2rr-000000000000000000000002":J,"v2rr-000000000000000000000003":J},
            {"v2rr-000000000000000000000002":J,"v2rr-000000000000000000000003":U},
        )
        self.assertEqual(finals, {"v2rr-000000000000000000000001":R,"v2rr-000000000000000000000002":J,"v2rr-000000000000000000000003":U})
        self.assertEqual(bases["v2rr-000000000000000000000001"], "ab_agreement")
        self.assertEqual(bases["v2rr-000000000000000000000002"], "two_of_three_majority")
        self.assertEqual(bases["v2rr-000000000000000000000003"], "three_way_uncertain")

    def test_c_must_cover_exact_disagreement_set(self) -> None:
        with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "C IDs"):
            resolve_panel({"v2rr-000000000000000000000001":R},{"v2rr-000000000000000000000001":J},{})

    def test_ab_id_mismatch_and_invalid_label_fail_closed(self) -> None:
        with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "A/B ID"):
            resolve_panel({"v2rr-000000000000000000000001":R},{},{})
        with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "invalid label"):
            resolve_panel({"v2rr-000000000000000000000001":"retain"},{"v2rr-000000000000000000000001":"retain"},{})


class BlindRereviewFrozenReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.definition = cls.root / "sources/satellite-calibration-2026-07-19-algorithm-v2-blind-rereview-v5.json"
        cls.release = cls.root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v5"

    def test_frozen_release_reproduces_offline(self) -> None:
        manifest = validate_satellite_calibration_blind_rereview(
            self.release,
            definition_path=self.definition,
        )
        self.assertEqual(manifest["summary"]["rows"], {"aggregate": 43, "blocked_multitile_required": 7, "reviewed": 36})
        self.assertEqual(manifest["summary"]["agreement_measure"]["numerator"], 30)

    def test_v5_semantic_payloads_equal_v4_except_schema_version(self) -> None:
        previous = self.root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v4"
        for name in (
            "blind-decisions.jsonl",
            "blocked-multitile.jsonl",
            "calibration-records.jsonl",
        ):
            with self.subTest(name=name):
                previous_rows = [
                    _without_schema_version(json.loads(line))
                    for line in previous.joinpath(name).read_text().splitlines()
                ]
                current_rows = [
                    _without_schema_version(json.loads(line))
                    for line in self.release.joinpath(name).read_text().splitlines()
                ]
                self.assertEqual(current_rows, previous_rows)
        for name in ("protocol-deviations.json", "summary.json"):
            with self.subTest(name=name):
                previous_payload = _without_schema_version(
                    json.loads(previous.joinpath(name).read_text())
                )
                current_payload = _without_schema_version(
                    json.loads(self.release.joinpath(name).read_text())
                )
                self.assertEqual(current_payload, previous_payload)

        previous_definition = json.loads(
            self.root.joinpath(
                "sources/satellite-calibration-2026-07-19-algorithm-v2-blind-rereview-v4.json"
            ).read_text()
        )
        current_definition = json.loads(self.definition.read_text())
        for payload in (previous_definition, current_definition):
            for key in ("format", "release_id", "schema_version"):
                payload.pop(key)
        self.assertEqual(current_definition, previous_definition)

    def test_extra_file_and_mode_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(self.release, copied)
            os.chmod(copied, 0o755)
            extra = copied / "extra.json"
            extra.write_text("{}\n")
            os.chmod(extra, 0o444)
            os.chmod(copied, 0o555)
            with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "file set"):
                validate_satellite_calibration_blind_rereview(copied, definition_path=self.definition)
            os.chmod(copied, 0o755)
            extra.unlink()
            os.chmod(copied / "summary.json", 0o644)
            os.chmod(copied, 0o555)
            with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "file mode"):
                validate_satellite_calibration_blind_rereview(copied, definition_path=self.definition)
            os.chmod(copied, 0o755)

    def test_canonical_content_tamper_fails_reproduction(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(self.release, copied)
            os.chmod(copied, 0o755)
            summary = copied / "summary.json"
            os.chmod(summary, 0o644)
            summary.write_text(summary.read_text().replace('"numerator": 30', '"numerator": 29'))
            os.chmod(summary, 0o444)
            os.chmod(copied, 0o555)
            with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "summary.json differs"):
                validate_satellite_calibration_blind_rereview(copied, definition_path=self.definition)
            os.chmod(copied, 0o755)


class BlindRereviewPublicationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.definition = cls.root / "sources/satellite-calibration-2026-07-19-algorithm-v2-blind-rereview-v5.json"
        cls.cli = cls.root / "scripts/build_satellite_calibration_blind_rereview.py"

    def _run_cli(self, output: Path) -> tuple[int, str, str]:
        spec = importlib.util.spec_from_file_location(
            "blind_rereview_publication_safety_cli", self.cli
        )
        if spec is None or spec.loader is None:
            self.fail("could not load blind rereview CLI")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            str(self.cli),
            "--definition",
            str(self.definition),
            "--output-dir",
            str(output),
        ]
        with patch.object(sys, "argv", arguments), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            return_code = module.main()
        return return_code, stdout.getvalue(), stderr.getvalue()

    def _assert_failure(
        self,
        output: Path,
        message: str,
        *,
        cli: bool,
    ) -> None:
        if cli:
            return_code, stdout, stderr = self._run_cli(output)
            self.assertEqual(return_code, 2, stdout)
            self.assertEqual(stdout, "")
            self.assertIn(message, stderr)
            return
        with self.assertRaisesRegex(
            SatelliteCalibrationBlindRereviewError, message
        ):
            write_satellite_calibration_blind_rereview(
                output,
                definition_path=self.definition,
            )

    def _remove_test_tree(self, path: Path) -> None:
        if path.exists() or path.is_symlink():
            _cleanup(path)

    def _owned_failure_artifacts(self, parent: Path, output: Path) -> list[Path]:
        return sorted(
            [
                *parent.glob(f".{output.name}.staging-*"),
                *parent.glob(f".{output.name}.failed-owned-*"),
            ]
        )

    def _remove_owned_failure_artifacts(self, parent: Path, output: Path) -> None:
        for path in self._owned_failure_artifacts(parent, output):
            self._remove_test_tree(path)
        _fsync_directory(parent)

    def test_overlapping_output_is_rejected_with_zero_filesystem_mutation(self) -> None:
        source = self.root / "satellite_calibration_reviews/2026-07-19-v2-identity-blind-reviewer-a-draft"
        forbidden_parent = source / ".overlap-output-test-v4"
        self.assertFalse(forbidden_parent.exists())
        before = sorted((path.relative_to(source).as_posix(), path.stat().st_mode) for path in source.rglob("*"))
        with self.assertRaisesRegex(SatelliteCalibrationBlindRereviewError, "overlaps"):
            write_satellite_calibration_blind_rereview(
                forbidden_parent / "release",
                definition_path=self.definition,
            )
        after = sorted((path.relative_to(source).as_posix(), path.stat().st_mode) for path in source.rglob("*"))
        self.assertEqual(after, before)
        self.assertFalse(forbidden_parent.exists())

    def test_injected_staging_validation_failure_publishes_nothing(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-prepublication-failure-v5"
        self.assertFalse(output.exists())
        try:
            with patch(
                "datacenter_atlas.satellite_calibration_blind_rereview.validate_satellite_calibration_blind_rereview",
                side_effect=SatelliteCalibrationBlindRereviewError(
                    "injected prepublication failure"
                ),
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError,
                    "primary failure: .*injected prepublication failure",
                ):
                    write_satellite_calibration_blind_rereview(
                        output,
                        definition_path=self.definition,
                    )
            self.assertFalse(output.exists())
            retained = self._owned_failure_artifacts(parent, output)
            self.assertEqual(len(retained), 1)
            validate_satellite_calibration_blind_rereview(
                retained[0], definition_path=self.definition
            )
        finally:
            self._remove_owned_failure_artifacts(parent, output)

    def test_staging_path_replacement_after_validation_is_never_published_or_deleted(self) -> None:
        parent = self.root / "satellite_calibration"
        real_validate = validate_satellite_calibration_blind_rereview
        for cli in (False, True):
            with self.subTest(interface="cli" if cli else "api"):
                suffix = "cli" if cli else "api"
                output = parent / f".injected-staging-replacement-v5-{suffix}"
                self.assertFalse(output.exists())
                staging_path: Path | None = None
                displaced_path: Path | None = None

                def replace_after_validation(
                    path: Path, *, definition_path: Path
                ) -> dict[str, object]:
                    nonlocal staging_path, displaced_path
                    result = real_validate(path, definition_path=definition_path)
                    staging_path = Path(path)
                    displaced_path = parent / f".{staging_path.name}.writer-displaced"
                    os.rename(staging_path, displaced_path)
                    staging_path.mkdir()
                    (staging_path / "unrelated-marker.txt").write_text(
                        "must survive\n"
                    )
                    return result

                try:
                    with patch(
                        "datacenter_atlas.satellite_calibration_blind_rereview.validate_satellite_calibration_blind_rereview",
                        side_effect=replace_after_validation,
                    ):
                        self._assert_failure(
                            output,
                            "no pathname deletion was attempted",
                            cli=cli,
                        )
                    self.assertFalse(output.exists())
                    self.assertIsNotNone(staging_path)
                    self.assertIsNotNone(displaced_path)
                    assert staging_path is not None
                    assert displaced_path is not None
                    self.assertEqual(
                        (staging_path / "unrelated-marker.txt").read_text(),
                        "must survive\n",
                    )
                    real_validate(displaced_path, definition_path=self.definition)
                finally:
                    if staging_path is not None:
                        self._remove_test_tree(staging_path)
                    if displaced_path is not None:
                        self._remove_test_tree(displaced_path)
                    _fsync_directory(parent)

    def test_successful_publication_fsync_swap_cannot_return_success(self) -> None:
        parent = self.root / "satellite_calibration"
        real_validate = validate_satellite_calibration_blind_rereview
        real_sync = rereview_module._sync_parent
        for cli in (False, True):
            with self.subTest(interface="cli" if cli else "api"):
                suffix = "cli" if cli else "api"
                output = parent / f".injected-fsync-success-swap-v5-{suffix}"
                displaced = parent / f".{output.name}.writer-displaced"
                self.assertFalse(output.exists())
                self.assertFalse(displaced.exists())
                replaced = False

                def replace_during_successful_fsync(
                    parent_fd: int, phase: str
                ) -> None:
                    nonlocal replaced
                    real_sync(parent_fd, phase)
                    if (
                        phase == "publication parent fsync"
                        and output.exists()
                        and not replaced
                    ):
                        replaced = True
                        os.rename(output, displaced)
                        output.mkdir()
                        (output / "unrelated-marker.txt").write_text(
                            "must survive\n"
                        )

                try:
                    with patch.object(
                        rereview_module,
                        "_sync_parent",
                        side_effect=replace_during_successful_fsync,
                    ):
                        self._assert_failure(
                            output,
                            "post-fsync target identity mismatch",
                            cli=cli,
                        )
                    self.assertTrue(replaced)
                    self.assertEqual(
                        (output / "unrelated-marker.txt").read_text(),
                        "must survive\n",
                    )
                    real_validate(displaced, definition_path=self.definition)
                finally:
                    self._remove_test_tree(output)
                    self._remove_test_tree(displaced)
                    self._remove_owned_failure_artifacts(parent, output)
                    _fsync_directory(parent)

    def test_quarantine_check_use_swap_never_deletes_unrelated_tree(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-quarantine-swap-v5"
        displaced = parent / f".{output.name}.writer-displaced"
        real_sync = rereview_module._sync_parent
        real_rename = rereview_module._rename_noreplace
        rename_calls = 0

        def fail_publication_sync(parent_fd: int, phase: str) -> None:
            if phase == "publication parent fsync":
                raise OSError("injected publication fsync failure before recovery")
            real_sync(parent_fd, phase)

        def swap_before_quarantine_rename(
            parent_fd: int, source: str, target: str
        ) -> None:
            nonlocal rename_calls
            rename_calls += 1
            if rename_calls == 2:
                os.rename(output, displaced)
                output.mkdir()
                (output / "unrelated-marker.txt").write_text("must survive\n")
            real_rename(parent_fd, source, target)

        try:
            with patch.object(
                rereview_module, "_sync_parent", side_effect=fail_publication_sync
            ), patch.object(
                rereview_module,
                "_rename_noreplace",
                side_effect=swap_before_quarantine_rename,
            ):
                with self.assertRaises(
                    SatelliteCalibrationBlindRereviewError
                ) as raised:
                    write_satellite_calibration_blind_rereview(
                        output, definition_path=self.definition
                    )
            message = str(raised.exception)
            self.assertIn(
                "a racing unrelated replacement was moved to recovery quarantine",
                message,
            )
            self.assertIn(
                "unrelated replacement restored to its original target name",
                message,
            )
            self.assertEqual(rename_calls, 3)
            self.assertEqual(
                (output / "unrelated-marker.txt").read_text(), "must survive\n"
            )
            validate_satellite_calibration_blind_rereview(
                displaced, definition_path=self.definition
            )
        finally:
            self._remove_test_tree(output)
            self._remove_test_tree(displaced)
            self._remove_owned_failure_artifacts(parent, output)

    def test_prepublication_failure_retains_owned_tree_and_fsyncs_creation(self) -> None:
        parent = self.root / "satellite_calibration"
        parent_identity = (parent.stat().st_dev, parent.stat().st_ino)
        real_fsync = os.fsync
        for cli in (False, True):
            with self.subTest(interface="cli" if cli else "api"):
                suffix = "cli" if cli else "api"
                output = parent / f".injected-retained-staging-v5-{suffix}"
                parent_syncs = 0

                def recording_fsync(descriptor: int) -> None:
                    nonlocal parent_syncs
                    value = os.fstat(descriptor)
                    if (value.st_dev, value.st_ino) == parent_identity:
                        parent_syncs += 1
                    real_fsync(descriptor)

                try:
                    with patch(
                        "datacenter_atlas.satellite_calibration_blind_rereview.validate_satellite_calibration_blind_rereview",
                        side_effect=SatelliteCalibrationBlindRereviewError(
                            "injected prepublication failure"
                        ),
                    ), patch(
                        "datacenter_atlas.satellite_calibration_blind_rereview.os.fsync",
                        side_effect=recording_fsync,
                    ):
                        self._assert_failure(
                            output,
                            "injected prepublication failure",
                            cli=cli,
                        )
                    self.assertEqual(parent_syncs, 2)
                    self.assertFalse(output.exists())
                    self.assertEqual(
                        len(self._owned_failure_artifacts(parent, output)), 1
                    )
                finally:
                    self._remove_owned_failure_artifacts(parent, output)

    def test_primary_and_recovery_fsync_failures_are_reported_together(self) -> None:
        parent = self.root / "satellite_calibration"
        real_sync = rereview_module._sync_parent
        for cli in (False, True):
            with self.subTest(interface="cli" if cli else "api"):
                suffix = "cli" if cli else "api"
                output = parent / f".injected-compound-fsync-v5-{suffix}"

                def rejecting_sync(parent_fd: int, phase: str) -> None:
                    if phase == "publication parent fsync":
                        raise OSError("injected primary publication fsync failure")
                    if phase == "target quarantine parent fsync":
                        raise OSError("injected recovery quarantine fsync failure")
                    real_sync(parent_fd, phase)

                try:
                    with patch.object(
                        rereview_module, "_sync_parent", side_effect=rejecting_sync
                    ):
                        if cli:
                            return_code, stdout, stderr = self._run_cli(output)
                            self.assertEqual(return_code, 2, stdout)
                            self.assertEqual(stdout, "")
                            message = stderr
                        else:
                            with self.assertRaises(
                                SatelliteCalibrationBlindRereviewError
                            ) as raised:
                                write_satellite_calibration_blind_rereview(
                                    output, definition_path=self.definition
                                )
                            message = str(raised.exception)
                    self.assertIn(
                        "injected primary publication fsync failure", message
                    )
                    self.assertIn(
                        "injected recovery quarantine fsync failure", message
                    )
                    self.assertFalse(output.exists())
                    retained = self._owned_failure_artifacts(parent, output)
                    self.assertEqual(len(retained), 1)
                    validate_satellite_calibration_blind_rereview(
                        retained[0], definition_path=self.definition
                    )
                finally:
                    self._remove_test_tree(output)
                    self._remove_owned_failure_artifacts(parent, output)

    def test_postrename_sync_failure_quarantines_owned_tree(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-durability-failure-v5"
        self.assertFalse(output.exists())
        real_sync = rereview_module._sync_parent

        def injected(parent_fd: int, phase: str) -> None:
            if phase == "publication parent fsync":
                raise OSError("injected publication parent fsync failure")
            real_sync(parent_fd, phase)

        try:
            with patch.object(
                rereview_module, "_sync_parent", side_effect=injected
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError,
                    "injected publication parent fsync failure",
                ):
                    write_satellite_calibration_blind_rereview(
                        output,
                        definition_path=self.definition,
                    )
            self.assertFalse(output.exists())
            retained = self._owned_failure_artifacts(parent, output)
            self.assertEqual(len(retained), 1)
            validate_satellite_calibration_blind_rereview(
                retained[0], definition_path=self.definition
            )
        finally:
            self._remove_test_tree(output)
            self._remove_owned_failure_artifacts(parent, output)

    def test_quarantine_rename_failure_preserves_validated_target(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-quarantine-rename-failure-v5"
        self.assertFalse(output.exists())
        real_sync = rereview_module._sync_parent
        real_rename = rereview_module._rename_noreplace
        rename_calls = 0

        def injected_sync(parent_fd: int, phase: str) -> None:
            if phase == "publication parent fsync":
                raise OSError("injected publication parent fsync failure")
            real_sync(parent_fd, phase)

        def injected_rename(parent_fd: int, source: str, target: str) -> None:
            nonlocal rename_calls
            rename_calls += 1
            if rename_calls == 2:
                raise OSError("injected quarantine rename failure")
            real_rename(parent_fd, source, target)

        try:
            with patch.object(
                rereview_module, "_sync_parent", side_effect=injected_sync
            ), patch.object(
                rereview_module, "_rename_noreplace", side_effect=injected_rename
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError,
                    "target quarantine rename failed: .*injected quarantine rename failure",
                ):
                    write_satellite_calibration_blind_rereview(
                        output,
                        definition_path=self.definition,
                    )
            self.assertEqual(rename_calls, 2)
            self.assertTrue(output.is_dir())
            validate_satellite_calibration_blind_rereview(
                output, definition_path=self.definition
            )
        finally:
            self._remove_test_tree(output)
            self._remove_owned_failure_artifacts(parent, output)

    def test_swap_after_postfsync_frozen_walk_is_caught_by_final_binding_check(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-postfsync-walk-swap-v5"
        displaced = parent / f".{output.name}.writer-displaced"
        self.assertFalse(output.exists())
        self.assertFalse(displaced.exists())
        real_require = rereview_module._require_frozen_release
        swapped = False

        def swap_after_walk(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            real_require(*args, **kwargs)
            label = args[4] if len(args) >= 5 else kwargs.get("label")
            if label == "post-fsync published release" and not swapped:
                os.rename(output, displaced)
                output.mkdir()
                (output / "unrelated-marker.txt").write_text("must survive\n")
                swapped = True

        try:
            with patch.object(
                rereview_module,
                "_require_frozen_release",
                side_effect=swap_after_walk,
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError,
                    "final published target identity mismatch",
                ):
                    write_satellite_calibration_blind_rereview(
                        output,
                        definition_path=self.definition,
                    )
            self.assertTrue(swapped)
            self.assertEqual(
                (output / "unrelated-marker.txt").read_text(), "must survive\n"
            )
            validate_satellite_calibration_blind_rereview(
                displaced, definition_path=self.definition
            )
        finally:
            self._remove_test_tree(output)
            self._remove_test_tree(displaced)
            self._remove_owned_failure_artifacts(parent, output)

    def test_swap_during_final_parent_check_is_caught_before_return(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-final-parent-check-swap-v5"
        displaced = parent / f".{output.name}.writer-displaced"
        real_require_parent = rereview_module._require_directory_path_identity
        swapped = False

        def swap_after_parent_check(
            path: Path, expected: tuple[int, int], label: str
        ) -> os.stat_result:
            nonlocal swapped
            result = real_require_parent(path, expected, label)
            if label == "final output parent" and not swapped:
                os.rename(output, displaced)
                output.mkdir()
                (output / "unrelated-marker.txt").write_text("must survive\n")
                swapped = True
            return result

        try:
            with patch.object(
                rereview_module,
                "_require_directory_path_identity",
                side_effect=swap_after_parent_check,
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError,
                    "return-bound published target identity mismatch",
                ):
                    write_satellite_calibration_blind_rereview(
                        output, definition_path=self.definition
                    )
            self.assertTrue(swapped)
            self.assertEqual(
                (output / "unrelated-marker.txt").read_text(), "must survive\n"
            )
            validate_satellite_calibration_blind_rereview(
                displaced, definition_path=self.definition
            )
        finally:
            self._remove_test_tree(output)
            self._remove_test_tree(displaced)
            self._remove_owned_failure_artifacts(parent, output)

    def test_postchmod_file_fsync_precedes_staging_validation(self) -> None:
        parent = self.root / "satellite_calibration"
        output = parent / ".injected-postchmod-order-v5"
        self.assertFalse(output.exists())
        observed_regular_modes: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(descriptor: int) -> None:
            value = os.fstat(descriptor)
            if stat.S_ISREG(value.st_mode):
                observed_regular_modes.append(value.st_mode & 0o777)
            real_fsync(descriptor)

        def rejecting(*args: object, **kwargs: object) -> None:
            raise SatelliteCalibrationBlindRereviewError("injected ordered stop")

        try:
            with patch.object(
                rereview_module.os, "fsync", side_effect=recording_fsync
            ), patch(
                "datacenter_atlas.satellite_calibration_blind_rereview.validate_satellite_calibration_blind_rereview",
                side_effect=rejecting,
            ):
                with self.assertRaisesRegex(
                    SatelliteCalibrationBlindRereviewError, "injected ordered stop"
                ):
                    write_satellite_calibration_blind_rereview(
                        output, definition_path=self.definition
                    )
            self.assertEqual(
                observed_regular_modes.count(0o444), len(rereview_module.RELEASE_FILES)
            )
            self.assertFalse(output.exists())
            self.assertEqual(len(self._owned_failure_artifacts(parent, output)), 1)
        finally:
            self._remove_owned_failure_artifacts(parent, output)

    def test_missing_output_parent_is_rejected_without_creation(self) -> None:
        parent = self.root / "satellite_calibration/.missing-parent-v5"
        self.assertFalse(parent.exists())
        with self.assertRaisesRegex(
            SatelliteCalibrationBlindRereviewError,
            "output parent is unavailable",
        ):
            write_satellite_calibration_blind_rereview(
                parent / "release", definition_path=self.definition
            )
        self.assertFalse(parent.exists())

    def test_source_closure_rejects_empty_extra_directory_and_mode_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            sealed = source / "sealed"
            sealed.mkdir(parents=True)
            artifact = sealed / "artifact.jsonl"
            artifact.write_text("{}\n")
            os.chmod(artifact, 0o400)
            os.chmod(sealed, 0o500)
            group = {
                "directories": {"sealed": "0500"},
                "directory": "source",
                "directory_mode": "0755",
                "files": {"sealed/artifact.jsonl": _pin(artifact)},
            }
            _validate_source_group(root, "fixture", group)
            extra = source / "empty-extra"
            extra.mkdir()
            with self.assertRaisesRegex(
                SatelliteCalibrationBlindRereviewError,
                "nested directory set drift",
            ):
                _validate_source_group(root, "fixture", group)
            extra.rmdir()
            os.chmod(sealed, 0o555)
            with self.assertRaisesRegex(
                SatelliteCalibrationBlindRereviewError,
                "directory mode drift",
            ):
                _validate_source_group(root, "fixture", group)

    def test_parent_directory_import_loads_root_compatibility_shim(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.root.parent)
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import datacenter_atlas.satellite_calibration_blind_rereview as m; assert callable(m.resolve_panel)",
                ],
                cwd=temporary,
                env=environment,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class BlindRereviewLexicalAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.definition = cls.root / "sources/satellite-calibration-2026-07-19-algorithm-v2-blind-rereview-v5.json"
        cls.release = cls.root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v5"
        cls.cli = cls.root / "scripts/build_satellite_calibration_blind_rereview.py"

    def _assert_api_and_cli_reject(self, alias: Path) -> None:
        with self.assertRaisesRegex(
            SatelliteCalibrationBlindRereviewError, "symlink alias"
        ):
            validate_satellite_calibration_blind_rereview(
                alias, definition_path=self.definition
            )
        completed = subprocess.run(
            [
                sys.executable,
                str(self.cli),
                "--definition",
                str(self.definition),
                "--output-dir",
                str(alias),
                "--validate-only",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("symlink alias", completed.stderr)

    def test_final_component_symlink_alias_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            alias = Path(temporary) / "release-alias"
            alias.symlink_to(self.release, target_is_directory=True)
            self._assert_api_and_cli_reject(alias)

    def test_parent_component_symlink_alias_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            parent_alias = Path(temporary) / "release-parent-alias"
            parent_alias.symlink_to(self.release.parent, target_is_directory=True)
            self._assert_api_and_cli_reject(parent_alias / self.release.name)

    def test_repository_root_symlink_alias_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root.parent) as temporary:
            root_alias = Path(temporary) / "repository-root-alias"
            root_alias.symlink_to(self.root, target_is_directory=True)
            self._assert_api_and_cli_reject(
                root_alias / "satellite_calibration" / self.release.name
            )


class BlindRereviewV1PreservationTests(unittest.TestCase):
    def test_frozen_v1_release_is_byte_for_byte_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        release = root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v1"
        expected = {
            "ATTRIBUTION.txt": "4d4a5f449a7022fc6dc4e0addf53f494de6a0d2eaaeb90a598361310614d97b2",
            "README.md": "72f7479771bdd5f5ab4863940af678846c1bf60a57ff3d8d8b09528e285de8c9",
            "blind-decisions.jsonl": "8b3bdcb56f5875467525a394be3d95d54fa30ed39d9ba68bb32e98342784b5a1",
            "blocked-multitile.jsonl": "edb444afe2d0656c8319386a07dddcb8a177dd7b5d47c7c2cdd263abc906bbcc",
            "calibration-records.jsonl": "15a4e966f5ca6ea7e7d7dacc0a961b71e046c7aac4fe324dd7c854a7496cd79f",
            "manifest.json": "e152c257d621924bd44ec6c9015a1825612d7b5c6893417b91a06ace976cb1e5",
            "manifest.sha256": "f7520034259cd554f89876564c49567154242f035f59ec8797fbcc7c507c96ba",
            "protocol-deviations.json": "0e2feeb2b86d63677a97695566aa27c48a97c58d82ceedb910fa6c8a42e57ec6",
            "summary.json": "67838d066f0afc9435f12fd06fa2f9d2d6970968f1840e1e07f4d974994e95ff",
        }
        self.assertEqual({path.name for path in release.iterdir()}, set(expected))
        self.assertEqual(release.stat().st_mode & 0o777, 0o555)
        for name, sha256 in expected.items():
            path = release / name
            self.assertEqual(_pin(path)["sha256"], sha256)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_frozen_v2_release_is_byte_for_byte_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        release = root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v2"
        expected = {
            "ATTRIBUTION.txt": "4d4a5f449a7022fc6dc4e0addf53f494de6a0d2eaaeb90a598361310614d97b2",
            "README.md": "859f968c29060f8420c048ea2380fa0012b45318cf8cb0302fb687e3d628db9d",
            "blind-decisions.jsonl": "f67e52bbcf1492d1188158c001ccb56785256c78bf9c9c7806669fc5660bd6a0",
            "blocked-multitile.jsonl": "27aa772f7af6a6e4ef8df02916b0869427e37ba3d001c4044a0ea4b3570c7ea6",
            "calibration-records.jsonl": "872c79866f3938f69cabaedb359007055c58839d0b7167176d0116d4aa7364f0",
            "manifest.json": "4918382ec278576bd89e1af844863a110ebdea2422c731d76c725a1eeadce4bd",
            "manifest.sha256": "ccfe93e65590d3c855e02edc9b3f36de2a3313e96dd6269dc9f23fd327eb40bb",
            "protocol-deviations.json": "67ae25c644d88ec73b7eb505e35db3f3a6bb91504c376a00f22fbe5dfa6c62da",
            "summary.json": "e7ac6551996268a1da0f15da6efc4567bc031fde02a8f852c7434c8e9c8f3815",
        }
        self.assertEqual({path.name for path in release.iterdir()}, set(expected))
        self.assertEqual(release.stat().st_mode & 0o777, 0o555)
        for name, sha256 in expected.items():
            path = release / name
            self.assertEqual(_pin(path)["sha256"], sha256)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_frozen_v3_release_is_byte_for_byte_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        release = root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v3"
        expected = {
            "ATTRIBUTION.txt": "4d4a5f449a7022fc6dc4e0addf53f494de6a0d2eaaeb90a598361310614d97b2",
            "README.md": "6239b89501d2bc4089f93f6ef4d20faa5726a80cafae58533c96e4eb493ee366",
            "blind-decisions.jsonl": "62785f654bc24989648ddaa94b94a4a1191dc93d9ae9490f764210f85d5c8675",
            "blocked-multitile.jsonl": "1b7b9b471c4bf68985479856e7a3cf38ce3da620a66aed5e5656fed885a3202f",
            "calibration-records.jsonl": "2ed943fcd756e1534db89a14817113490a36a7c143726a13cca7f8f60d730c45",
            "manifest.json": "4844565d90e332f8e459e6f4ca1b4db207703bfc7960f9d85840a1e1d8f6c16a",
            "manifest.sha256": "3342160ecb1bf9e7dc740297ce16221b0589fc7a5045bb989bb7ad693792ff50",
            "protocol-deviations.json": "1e9cedb313133f0f86e0d8ccdcbe2c84fd71320456363138d5dec047d33f9769",
            "summary.json": "d1d30f024636f94aa3e4af93d34ea0190914987e056ea8898ca13cafe3621195",
        }
        self.assertEqual({path.name for path in release.iterdir()}, set(expected))
        self.assertEqual(release.stat().st_mode & 0o777, 0o555)
        for name, sha256 in expected.items():
            path = release / name
            self.assertEqual(_pin(path)["sha256"], sha256)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_rejected_frozen_v4_release_is_byte_for_byte_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        release = root / "satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v4"
        expected = {
            "ATTRIBUTION.txt": "4d4a5f449a7022fc6dc4e0addf53f494de6a0d2eaaeb90a598361310614d97b2",
            "README.md": "c173ca7fa4090d7b0d605976b9b46e5df073533411ec96b0aa4f96ec20f0e151",
            "blind-decisions.jsonl": "68f075cefd4bb188d37e13ff1bc79cde328b40e383f702e4cab0bb8dabf85ae7",
            "blocked-multitile.jsonl": "e720ae9ce05f616c12cc61861254034ed96709ab7400e4ab838ce21bfc565957",
            "calibration-records.jsonl": "225e0c48f3261b998893fd60b10d8e8cfd00743fcb85260df674eaef4514741b",
            "manifest.json": "be0e7042eac7a54697ff526400537fe66211dbbdf7d5a505c541a3a6fc4b590d",
            "manifest.sha256": "9975e1c9efd720c02f93d3335667c7d302265ba454603d2c19152135d12aa13b",
            "protocol-deviations.json": "8beed257c21b0fcaeeccd70b7b2c1621c9f6234efd20b4282c3aa95874c84c05",
            "summary.json": "ff5fcba5487e2dd8ca099dffc801c7563e723d3074cf69da6b25e799d54c4eeb",
        }
        self.assertEqual({path.name for path in release.iterdir()}, set(expected))
        self.assertEqual(release.stat().st_mode & 0o777, 0o555)
        for name, sha256 in expected.items():
            path = release / name
            self.assertEqual(_pin(path)["sha256"], sha256)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_v1_through_v4_definitions_are_byte_for_byte_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected = {
            1: "44c0deb0fd84a650492bb41e5151214158c511e25007c8cc37d824d24e1a0d94",
            2: "d8d58ca034bddb6b6c0ddc2fe12642b84c561e507b31878d853208e72e69e3fc",
            3: "74441b552aa8eaff7967c2bf149dcb49e7f8379862b1985c2e3b2c80af9ec452",
            4: "735cb6cee78ff0a7e40513fbfc9535c068b43bedf52391094454c0904c1f95da",
        }
        for version, sha256 in expected.items():
            path = root / (
                "sources/satellite-calibration-2026-07-19-"
                f"algorithm-v2-blind-rereview-v{version}.json"
            )
            self.assertEqual(_pin(path)["sha256"], sha256)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)


if __name__ == "__main__":
    unittest.main()
