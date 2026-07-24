from __future__ import annotations

from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.satellite_mosaic_preparation as preparation_module
from datacenter_atlas.satellite_change import REQUIRED_ASSETS
from datacenter_atlas.satellite_mosaic_preparation import (
    BLOCKED_QUEUE_ID,
    BLOCKED_STATE,
    EXPECTED_QUEUE_IDS,
    READY_STATE,
    RELEASE_FILES,
    SatelliteMosaicPreparationError,
    _pin,
    _source_inventory,
    _validate_expected_cases,
    _validate_source_group,
    validate_satellite_mosaic_preparation,
    write_satellite_mosaic_preparation,
)


ROOT = Path(__file__).resolve().parents[1]
V1_DEFINITION = (
    ROOT
    / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v1.json"
)
V1_RELEASE = (
    ROOT
    / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v1"
)
DEFINITION = (
    ROOT
    / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v2.json"
)
RELEASE = (
    ROOT
    / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v2"
)
CLI = ROOT / "scripts/build_satellite_mosaic_preparation.py"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for node in sorted([path, *path.rglob("*")]):
        relative = "." if node == path else node.relative_to(path).as_posix()
        digest.update(relative.encode())
        digest.update(f"{node.stat().st_mode & 0o777:04o}".encode())
        if node.is_file():
            digest.update(hashlib.sha256(node.read_bytes()).digest())
    return digest.hexdigest()


def _force_remove_fixture(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    for node in path.rglob("*"):
        if not node.is_symlink():
            os.chmod(node, 0o700 if node.is_dir() else 0o600)
    os.chmod(path, 0o700)
    shutil.rmtree(path)


class SatelliteMosaicPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = _read_json(DEFINITION)

    def test_v1_release_and_definition_are_preserved_byte_for_byte(self) -> None:
        self.assertEqual(
            hashlib.sha256(V1_DEFINITION.read_bytes()).hexdigest(),
            "24b18962bea7f45d06f84a0a93d9c1eba8ba332b94077eb3d2d4e9afe8003ba8",
        )
        self.assertEqual(V1_DEFINITION.stat().st_mode & 0o777, 0o444)
        self.assertEqual(
            _tree_digest(V1_RELEASE),
            "8b714f86265eb106d74d26ac98c966d71aa7f41f7f504a1cd160a465813eab22",
        )
        self.assertEqual(V1_RELEASE.stat().st_mode & 0o777, 0o555)
        expected = {
            "ATTRIBUTION.txt": "f5d9bde8c220faf0bae76b6dacae0e1798f4de879708f3815c903eefbd53621b",
            "README.md": "ac2d743f77ffe3927b6302447f2cef660469416bc860ab28ddb4bccfef67a9e3",
            "blocked.jsonl": "0933d1ea50a2afda80505b03290621a5955729243e9f19d7c89f8e6989c9d6a6",
            "manifest.json": "8d18820f75be42534ad0f26f893f7830787c1b4d42c9e6700d331985a1b67b5f",
            "manifest.sha256": "7c1e04de9bd83ceeb96f9eb46604edd3180acca87fed5c757ec1b858736a4a88",
            "mosaic-specs.jsonl": "fe2c4a3417bcb6929c6f4465124756bbc1b38d65c54a5231999f9348da9e7f3b",
            "source-inventory.json": "81954d190f296774adac39401a502b123dfd5d614868fee746c176a7e48ddd78",
            "summary.json": "947508cfa74e8d6eeab129156949570c598b29f4fe146fba7814e0ad6b71e252",
        }
        self.assertEqual({path.name for path in V1_RELEASE.iterdir()}, set(expected))
        for name, digest in expected.items():
            path = V1_RELEASE / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_definition_pins_exact_seven_case_partition(self) -> None:
        cases = _validate_expected_cases(self.definition["cases"])
        self.assertEqual(
            [case["historical_queue_id"] for case in cases],
            list(EXPECTED_QUEUE_IDS),
        )
        self.assertEqual(
            [case["expected_state"] for case in cases].count(READY_STATE), 6
        )
        self.assertEqual(
            [case["expected_state"] for case in cases].count(BLOCKED_STATE), 1
        )

    def test_definition_rejects_bbox_or_epoch_drift(self) -> None:
        cases = deepcopy(self.definition["cases"])
        cases[0]["aoi_bbox_wgs84"][2] = cases[0]["aoi_bbox_wgs84"][0]
        with self.assertRaisesRegex(SatelliteMosaicPreparationError, "AOI"):
            _validate_expected_cases(cases)
        cases = deepcopy(self.definition["cases"])
        cases[0]["epochs"]["baseline"]["epoch"] = "current"
        with self.assertRaisesRegex(SatelliteMosaicPreparationError, "epoch label"):
            _validate_expected_cases(cases)

    def test_definition_pins_accepted_v3_module_and_cli(self) -> None:
        expected = {
            "module": (
                "datacenter_atlas/satellite_change_mosaic.py",
                "68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071",
            ),
            "cli": (
                "scripts/sentinel_change_mosaic.py",
                "6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183",
            ),
        }
        for name, (relative, digest) in expected.items():
            pin = self.definition["processor"]["files"][name]
            self.assertEqual(pin["path"], relative)
            self.assertEqual(pin["sha256"], digest)
            self.assertEqual(_pin(ROOT / relative), {key: pin[key] for key in ("bytes", "mode", "sha256")})

    def test_source_inventory_is_closed_and_hash_bound(self) -> None:
        inventory = _source_inventory(self.definition)
        self.assertEqual(inventory["source_file_count"], 40)
        paths = [row["path"] for row in inventory["files"]]
        self.assertEqual(len(paths), len(set(paths)))
        for row in inventory["files"]:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(row["bytes"], 0)
            self.assertIn(row["mode"], {"0400", "0444", "0644"})

    def test_source_group_rejects_extra_file_and_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary) / "source"
            directory.mkdir()
            source = directory / "one.json"
            source.write_text("{}\n", encoding="utf-8")
            relative = directory.relative_to(ROOT).as_posix()
            group = {
                "directories": {},
                "directory": relative,
                "directory_mode": "0755",
                "files": {"one.json": _pin(source)},
            }
            self.assertEqual(
                _validate_source_group(ROOT, "fixture", group), directory
            )
            (directory / "extra.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SatelliteMosaicPreparationError, "not closed"):
                _validate_source_group(ROOT, "fixture", group)
            (directory / "extra.json").unlink()
            source.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(SatelliteMosaicPreparationError, "pin mismatch"):
                _validate_source_group(ROOT, "fixture", group)

    def test_source_group_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary) / "source"
            directory.mkdir()
            source = directory / "one.json"
            source.write_text("{}\n", encoding="utf-8")
            (directory / "alias.json").symlink_to(source)
            group = {
                "directories": {},
                "directory": directory.relative_to(ROOT).as_posix(),
                "directory_mode": "0755",
                "files": {"one.json": _pin(source)},
            }
            with self.assertRaisesRegex(SatelliteMosaicPreparationError, "symlink"):
                _validate_source_group(ROOT, "fixture", group)

    def test_release_validates_and_has_exact_frozen_tree(self) -> None:
        manifest = validate_satellite_mosaic_preparation(
            RELEASE, definition_path=DEFINITION
        )
        self.assertEqual(manifest["summary"]["metadata_ready"], 6)
        self.assertEqual(manifest["summary"]["blocked"], 1)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, RELEASE_FILES)
        self.assertEqual(RELEASE.stat().st_mode & 0o777, 0o555)
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o444 for path in RELEASE.iterdir())
        )

    def test_cli_validates_v2_release(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                os.fspath(CLI),
                "--validate-only",
                "--definition",
                os.fspath(DEFINITION),
                "--output-dir",
                os.fspath(RELEASE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            '"format": "datacenter-atlas-satellite-mosaic-v3-preparation-v2"',
            completed.stdout,
        )

    def test_release_manifest_sidecar_and_source_inventory(self) -> None:
        manifest_raw = (RELEASE / "manifest.json").read_bytes()
        self.assertEqual(
            (RELEASE / "manifest.sha256").read_text(encoding="ascii"),
            f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n",
        )
        self.assertEqual(
            _read_json(RELEASE / "source-inventory.json"),
            _source_inventory(self.definition),
        )

    def test_v2_preserves_v1_preparation_rows_and_source_closure(self) -> None:
        for name in ("blocked.jsonl", "mosaic-specs.jsonl", "source-inventory.json"):
            self.assertEqual((RELEASE / name).read_bytes(), (V1_RELEASE / name).read_bytes())

    def test_six_specs_pin_every_epoch_binding_bbox_and_argument(self) -> None:
        cases = {
            case["historical_queue_id"]: case for case in self.definition["cases"]
        }
        rows = _read_jsonl(RELEASE / "mosaic-specs.jsonl")
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            [row["historical_queue_id"] for row in rows],
            sorted(set(EXPECTED_QUEUE_IDS) - {BLOCKED_QUEUE_ID}),
        )
        for row in rows:
            case = cases[row["historical_queue_id"]]
            self.assertEqual(row["state"], READY_STATE)
            self.assertEqual(row["aoi_bbox_wgs84"], case["aoi_bbox_wgs84"])
            self.assertFalse(row["execution_performed"])
            self.assertFalse(row["imagery_downloaded"])
            self.assertFalse(row["imagery_opened"])
            self.assertEqual(row["network_requests"], 0)
            arguments = row["execution"]["arguments"]
            for epoch in ("baseline", "current"):
                expected = case["epochs"][epoch]
                actual = row["epochs"][epoch]
                self.assertEqual(actual["epoch"], epoch)
                self.assertEqual(actual["primary"], expected["primary"])
                self.assertEqual(actual["companions"], expected["companions"])
                self.assertTrue(actual["metadata_solvable"])
                self.assertTrue(
                    all(
                        actual["coverage"]["assets"][asset]["complete"]
                        for asset in REQUIRED_ASSETS
                    )
                )
                self.assertIn(
                    f"{expected['primary']['id']}={expected['primary']['stac_item_sha256']}",
                    arguments,
                )
                for companion in expected["companions"]:
                    self.assertIn(
                        f"{companion['id']}={companion['stac_item_sha256']}",
                        arguments,
                    )

    def test_mrs5_blocker_is_explicit_and_never_substituted(self) -> None:
        rows = _read_jsonl(RELEASE / "blocked.jsonl")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["historical_queue_id"], BLOCKED_QUEUE_ID)
        self.assertEqual(row["state"], BLOCKED_STATE)
        self.assertEqual(
            row["missing_binding"],
            {
                "epoch": "current",
                "item_id": None,
                "mgrs_tile": "31TFJ",
                "stac_item_sha256": None,
            },
        )
        self.assertTrue(row["epochs"]["baseline"]["metadata_solvable"])
        self.assertFalse(row["epochs"]["current"]["metadata_solvable"])
        self.assertEqual(row["epochs"]["current"]["companions"], [])
        self.assertTrue(
            all(
                not row["epochs"]["current"]["coverage"]["assets"][asset][
                    "complete"
                ]
                for asset in REQUIRED_ASSETS
            )
        )
        self.assertNotIn("execution", row)

    def test_rejected_overlapping_output_does_not_mutate_source(self) -> None:
        source = (
            ROOT
            / "satellite_calibration_rereview/2026-07-19-algorithm-v2-numerical-aggregate-v1"
        )
        output = source / "must-not-be-created"
        before = _tree_digest(source)
        with self.assertRaisesRegex(SatelliteMosaicPreparationError, "overlaps"):
            write_satellite_mosaic_preparation(output, definition_path=DEFINITION)
        self.assertFalse(output.exists())
        self.assertEqual(_tree_digest(source), before)

    def test_failed_private_staging_validation_leaves_no_target(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            output = parent / "release"
            with patch(
                "datacenter_atlas.satellite_mosaic_preparation.validate_satellite_mosaic_preparation",
                side_effect=SatelliteMosaicPreparationError("injected staging failure"),
            ):
                with self.assertRaisesRegex(
                    SatelliteMosaicPreparationError, "injected staging failure"
                ):
                    write_satellite_mosaic_preparation(
                        output, definition_path=DEFINITION
                    )
            self.assertFalse(output.exists())
            self.assertEqual(list(parent.iterdir()), [])

    def test_existing_regular_parent_is_required_through_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            missing_parent = Path(temporary) / "missing"
            output = missing_parent / "release"
            with self.assertRaisesRegex(
                SatelliteMosaicPreparationError, "output parent is unavailable"
            ):
                write_satellite_mosaic_preparation(output, definition_path=DEFINITION)
            self.assertFalse(missing_parent.exists())
            completed = subprocess.run(
                [
                    sys.executable,
                    os.fspath(CLI),
                    "--definition",
                    os.fspath(DEFINITION),
                    "--output-dir",
                    os.fspath(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("output parent is unavailable", completed.stderr)
            self.assertFalse(missing_parent.exists())

    def test_validator_rejects_lexical_symlink_before_resolution_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            alias = Path(temporary) / "release-alias"
            alias.symlink_to(RELEASE, target_is_directory=True)
            with self.assertRaisesRegex(
                SatelliteMosaicPreparationError, "traverses a symlink"
            ):
                validate_satellite_mosaic_preparation(
                    alias, definition_path=DEFINITION
                )
            completed = subprocess.run(
                [
                    sys.executable,
                    os.fspath(CLI),
                    "--validate-only",
                    "--definition",
                    os.fspath(DEFINITION),
                    "--output-dir",
                    os.fspath(alias),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("traverses a symlink", completed.stderr)

    def test_frozen_file_inodes_are_fsynced_after_chmod(self) -> None:
        observed_regular_modes: list[int] = []
        real_fsync = preparation_module.os.fsync

        def recording_fsync(descriptor: int) -> None:
            value = os.fstat(descriptor)
            if stat.S_ISREG(value.st_mode):
                observed_regular_modes.append(value.st_mode & 0o777)
            real_fsync(descriptor)

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "release"
            with patch.object(
                preparation_module.os, "fsync", side_effect=recording_fsync
            ), patch(
                "datacenter_atlas.satellite_mosaic_preparation.validate_satellite_mosaic_preparation",
                side_effect=SatelliteMosaicPreparationError("stop after freeze"),
            ):
                with self.assertRaises(SatelliteMosaicPreparationError):
                    write_satellite_mosaic_preparation(
                        output, definition_path=DEFINITION
                    )
            self.assertEqual(observed_regular_modes.count(0o444), len(RELEASE_FILES))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_parent_fsync_and_rollback_rename_failure_never_return_success(self) -> None:
        real_sync = preparation_module._sync_parent
        real_rename = preparation_module._rename_noreplace
        rename_calls = 0

        def failing_sync(parent_fd: int, phase: str) -> None:
            if phase == "publication parent fsync":
                raise OSError(errno.EIO, "injected publication fsync failure")
            real_sync(parent_fd, phase)

        def failing_rollback(parent_fd: int, source: str, target: str) -> None:
            nonlocal rename_calls
            rename_calls += 1
            if rename_calls == 2:
                raise OSError(errno.EIO, "injected rollback rename failure")
            real_rename(parent_fd, source, target)

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "release"
            with patch.object(
                preparation_module, "_sync_parent", side_effect=failing_sync
            ), patch.object(
                preparation_module,
                "_rename_noreplace",
                side_effect=failing_rollback,
            ):
                with self.assertRaisesRegex(
                    SatelliteMosaicPreparationError,
                    "rollback rename failed",
                ) as raised:
                    write_satellite_mosaic_preparation(
                        output, definition_path=DEFINITION
                    )
            self.assertIn("injected publication fsync failure", str(raised.exception))
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_rollback_and_cleanup_sync_failures_are_both_reported(self) -> None:
        real_sync = preparation_module._sync_parent

        def failing_sync(parent_fd: int, phase: str) -> None:
            if phase in {
                "publication parent fsync",
                "rollback parent fsync",
                "cleanup parent fsync",
            }:
                raise OSError(errno.EIO, f"injected {phase} failure")
            real_sync(parent_fd, phase)

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "release"
            with patch.object(
                preparation_module, "_sync_parent", side_effect=failing_sync
            ):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation(
                        output, definition_path=DEFINITION
                    )
            message = str(raised.exception)
            self.assertIn("rollback parent fsync failed", message)
            self.assertIn("cleanup parent fsync", message)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_atomic_no_clobber_preserves_racing_target(self) -> None:
        real_rename = preparation_module._rename_noreplace

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            output = parent / "release"

            def occupy_target(parent_fd: int, source: str, target: str) -> None:
                os.mkdir(target, 0o700, dir_fd=parent_fd)
                (parent / target / "marker").write_text("substitute", encoding="utf-8")
                real_rename(parent_fd, source, target)

            try:
                with patch.object(
                    preparation_module,
                    "_rename_noreplace",
                    side_effect=occupy_target,
                ):
                    with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                        write_satellite_mosaic_preparation(
                            output, definition_path=DEFINITION
                        )
                self.assertIn("substituted tree", str(raised.exception))
                self.assertEqual(
                    (output / "marker").read_text(encoding="utf-8"), "substitute"
                )
                self.assertFalse(
                    any(path.name.startswith(".release.staging-") for path in parent.iterdir())
                )
            finally:
                _force_remove_fixture(output)

    def test_staging_path_replacement_is_detected_without_deleting_substitute(self) -> None:
        real_rename = preparation_module._rename_noreplace

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            output = parent / "release"
            owned_paths: list[Path] = []

            def replace_staging(parent_fd: int, source: str, target: str) -> None:
                moved = f"{source}.owned"
                real_rename(parent_fd, source, moved)
                owned_paths.append(parent / moved)
                os.mkdir(source, 0o700, dir_fd=parent_fd)
                (parent / source / "marker").write_text("substitute", encoding="utf-8")
                real_rename(parent_fd, source, target)

            try:
                with patch.object(
                    preparation_module,
                    "_rename_noreplace",
                    side_effect=replace_staging,
                ):
                    with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                        write_satellite_mosaic_preparation(
                            output, definition_path=DEFINITION
                        )
                self.assertIn("substituted tree", str(raised.exception))
                self.assertEqual(
                    (output / "marker").read_text(encoding="utf-8"), "substitute"
                )
                self.assertEqual(len(owned_paths), 1)
                self.assertTrue(owned_paths[0].is_dir())
            finally:
                _force_remove_fixture(output)
                for path in owned_paths:
                    _force_remove_fixture(path)

    def test_target_replacement_before_rollback_is_preserved_and_reported(self) -> None:
        real_sync = preparation_module._sync_parent
        real_rename = preparation_module._rename_noreplace

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            output = parent / "release"
            owned = parent / "release.owned"

            def replace_target_then_fail(parent_fd: int, phase: str) -> None:
                if phase == "publication parent fsync":
                    real_rename(parent_fd, "release", "release.owned")
                    os.mkdir("release", 0o700, dir_fd=parent_fd)
                    (output / "marker").write_text("substitute", encoding="utf-8")
                    raise OSError(errno.EIO, "injected publication fsync failure")
                real_sync(parent_fd, phase)

            try:
                with patch.object(
                    preparation_module,
                    "_sync_parent",
                    side_effect=replace_target_then_fail,
                ):
                    with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                        write_satellite_mosaic_preparation(
                            output, definition_path=DEFINITION
                        )
                self.assertIn("substituted tree", str(raised.exception))
                self.assertEqual(
                    (output / "marker").read_text(encoding="utf-8"), "substitute"
                )
                self.assertTrue(owned.is_dir())
            finally:
                _force_remove_fixture(output)
                _force_remove_fixture(owned)

    def test_validator_detects_output_replacement_and_preserves_substitute(self) -> None:
        real_payloads = preparation_module._payloads
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            parent = Path(temporary)
            output = parent / "release"
            owned = parent / "release.owned"
            write_satellite_mosaic_preparation(output, definition_path=DEFINITION)

            def replace_after_read(definition_path: Path, output_dir: Path | None = None):
                result = real_payloads(definition_path, output_dir)
                os.rename(output, owned)
                output.mkdir(mode=0o700)
                (output / "marker").write_text("substitute", encoding="utf-8")
                return result

            try:
                with patch.object(
                    preparation_module, "_payloads", side_effect=replace_after_read
                ):
                    with self.assertRaisesRegex(
                        SatelliteMosaicPreparationError, "path identity mismatch"
                    ):
                        validate_satellite_mosaic_preparation(
                            output, definition_path=DEFINITION
                        )
                self.assertEqual(
                    (output / "marker").read_text(encoding="utf-8"), "substitute"
                )
                self.assertTrue(owned.is_dir())
            finally:
                _force_remove_fixture(output)
                _force_remove_fixture(owned)

    def test_parent_path_replacement_is_descriptor_bound_and_reported(self) -> None:
        real_sync = preparation_module._sync_parent
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            container = Path(temporary)
            parent = container / "parent"
            parent.mkdir()
            owned_parent = container / "parent.owned"
            output = parent / "release"
            replaced = False

            def replace_parent(parent_fd: int, phase: str) -> None:
                nonlocal replaced
                real_sync(parent_fd, phase)
                if phase == "frozen staging parent fsync" and not replaced:
                    os.rename(parent, owned_parent)
                    parent.mkdir()
                    (parent / "marker").write_text("substitute", encoding="utf-8")
                    replaced = True

            try:
                with patch.object(
                    preparation_module, "_sync_parent", side_effect=replace_parent
                ):
                    with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                        write_satellite_mosaic_preparation(
                            output, definition_path=DEFINITION
                        )
                self.assertIn("parent identity", str(raised.exception))
                self.assertEqual(
                    (parent / "marker").read_text(encoding="utf-8"), "substitute"
                )
                self.assertFalse(output.exists())
                self.assertTrue(owned_parent.is_dir())
                self.assertEqual(list(owned_parent.iterdir()), [])
            finally:
                _force_remove_fixture(parent)
                _force_remove_fixture(owned_parent)


if __name__ == "__main__":
    unittest.main()
