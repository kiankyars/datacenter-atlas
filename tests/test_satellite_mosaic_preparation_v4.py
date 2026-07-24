from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.satellite_mosaic_preparation_v4 as v4
from datacenter_atlas.satellite_mosaic_preparation_v4 import (
    RELEASE_FILES,
    SatelliteMosaicPreparationError,
    validate_satellite_mosaic_preparation_v4,
    write_satellite_mosaic_preparation_v4,
)


ROOT = Path(__file__).resolve().parents[1]
V1_DEFINITION = ROOT / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v1.json"
V2_DEFINITION = ROOT / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v2.json"
V3_DEFINITION = ROOT / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v3.json"
DEFINITION = ROOT / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v4.json"
V1_RELEASE = ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v1"
V2_RELEASE = ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v2"
V3_RELEASE = ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v3"
RELEASE = ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v4"
CLI = ROOT / "scripts/build_satellite_mosaic_preparation_v4.py"


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for node in sorted([path, *path.rglob("*")]):
        relative = "." if node == path else node.relative_to(path).as_posix()
        digest.update(relative.encode())
        digest.update(f"{node.stat().st_mode & 0o777:04o}".encode())
        if node.is_file():
            digest.update(hashlib.sha256(node.read_bytes()).digest())
    return digest.hexdigest()


def _force_remove(path: Path) -> None:
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


def _recovery_paths(parent: Path) -> list[Path]:
    return sorted(
        path for path in parent.iterdir() if path.name.startswith(".release.recovery-")
    )


class SatelliteMosaicPreparationV4Tests(unittest.TestCase):
    def _parent(self) -> Path:
        return Path(tempfile.mkdtemp(prefix=".mosaic-v4-test-", dir=ROOT))

    def test_v1_through_v3_rejected_evidence_is_byte_preserved(self) -> None:
        expected_definitions = {
            V1_DEFINITION: "24b18962bea7f45d06f84a0a93d9c1eba8ba332b94077eb3d2d4e9afe8003ba8",
            V2_DEFINITION: "92c45ec8d6f4058a182411282dfc5314d4e6208f9f9dfd77e804b99265237cae",
            V3_DEFINITION: "6da293ff7d53fe044f76e2b253723d7f56719f30a67c94ba3155762146670967",
        }
        for path, expected in expected_definitions.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
        self.assertEqual(
            _tree_digest(V1_RELEASE),
            "8b714f86265eb106d74d26ac98c966d71aa7f41f7f504a1cd160a465813eab22",
        )
        self.assertEqual(
            _tree_digest(V2_RELEASE),
            "8d6536fe05728a74387cb60ec87b2c1ae2095b9229d850ba2d2f5be79bc646b6",
        )
        self.assertEqual(
            _tree_digest(V3_RELEASE),
            "4fd67858fb75662cc9273cedfd60d047048683f233248da109d13fdc5ae57caa",
        )

    def test_definition_pins_scientific_basis_and_rejected_predecessor(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["schema_version"], 4)
        self.assertFalse(
            definition["publication_contract"]["destructive_failure_cleanup"]
        )
        self.assertTrue(
            definition["publication_contract"][
                "all_possible_leftover_exact_paths_reported"
            ]
        )
        self.assertTrue(
            definition["publication_contract"][
                "generated_quarantine_path_reported_if_unverified"
            ]
        )
        self.assertEqual(
            definition["base_definition"],
            {
                "bytes": 21036,
                "mode": "0444",
                "path": "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v2.json",
                "sha256": "92c45ec8d6f4058a182411282dfc5314d4e6208f9f9dfd77e804b99265237cae",
            },
        )
        self.assertEqual(
            definition["rejected_predecessor"],
            {
                "bytes": 1868,
                "mode": "0444",
                "path": "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v3.json",
                "sha256": "6da293ff7d53fe044f76e2b253723d7f56719f30a67c94ba3155762146670967",
            },
        )

    def test_v4_release_validates_and_preserves_scientific_bytes(self) -> None:
        manifest = validate_satellite_mosaic_preparation_v4(
            RELEASE, definition_path=DEFINITION
        )
        self.assertEqual(manifest["summary"]["metadata_ready"], 6)
        self.assertEqual(manifest["summary"]["blocked"], 1)
        self.assertEqual(manifest["summary"]["source_file_pins"], 40)
        self.assertEqual(RELEASE.stat().st_mode & 0o777, 0o555)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, RELEASE_FILES)
        for name in ("blocked.jsonl", "mosaic-specs.jsonl", "source-inventory.json"):
            self.assertEqual(
                (RELEASE / name).read_bytes(), (V2_RELEASE / name).read_bytes()
            )
            self.assertEqual(
                (RELEASE / name).read_bytes(), (V3_RELEASE / name).read_bytes()
            )
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o444 for path in RELEASE.iterdir())
        )

    def test_cli_validates_v4_release(self) -> None:
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
            '"format": "datacenter-atlas-satellite-mosaic-v3-preparation-v4"',
            completed.stdout,
        )

    def test_two_fresh_builds_are_byte_identical(self) -> None:
        first_parent = self._parent()
        second_parent = self._parent()
        first = first_parent / "release"
        second = second_parent / "release"
        try:
            write_satellite_mosaic_preparation_v4(first, definition_path=DEFINITION)
            write_satellite_mosaic_preparation_v4(second, definition_path=DEFINITION)
            for name in RELEASE_FILES:
                self.assertEqual(
                    (first / name).read_bytes(), (second / name).read_bytes()
                )
        finally:
            _force_remove(first_parent)
            _force_remove(second_parent)

    def test_prepublication_failure_quarantines_owned_tree_without_delete(self) -> None:
        parent = self._parent()
        output = parent / "release"
        try:
            with patch.object(
                v4,
                "validate_satellite_mosaic_preparation_v4",
                side_effect=SatelliteMosaicPreparationError(
                    "injected primary failure"
                ),
            ), patch.object(
                v4.os, "unlink", side_effect=AssertionError("unlink forbidden")
            ), patch.object(
                v4.os, "rmdir", side_effect=AssertionError("rmdir forbidden")
            ):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )
            message = str(raised.exception)
            recoveries = _recovery_paths(parent)
            self.assertEqual(len(recoveries), 1)
            self.assertIn("injected primary failure", message)
            self.assertIn("identity verified and preserved without deletion", message)
            self.assertIn(os.fspath(recoveries[0]), message)
            self.assertFalse(output.exists())
            self.assertEqual({path.name for path in recoveries[0].iterdir()}, RELEASE_FILES)
        finally:
            _force_remove(parent)

    def test_mkdir_side_effect_then_error_reports_exact_staging_path(self) -> None:
        parent = self._parent()
        output = parent / "release"
        real_mkdir = v4.os.mkdir
        created_name: str | None = None

        def create_then_fail(name: str, mode: int = 0o777, *, dir_fd=None) -> None:
            nonlocal created_name
            if name.startswith(".release.staging-") and created_name is None:
                real_mkdir(name, mode, dir_fd=dir_fd)
                created_name = name
                raise OSError(errno.EIO, "injected post-mkdir EIO")
            real_mkdir(name, mode, dir_fd=dir_fd)

        try:
            with patch.object(
                v4.os, "mkdir", side_effect=create_then_fail
            ), patch.object(
                v4.os, "unlink", side_effect=AssertionError("unlink forbidden")
            ), patch.object(
                v4.os, "rmdir", side_effect=AssertionError("rmdir forbidden")
            ):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )

            self.assertIsNotNone(created_name)
            exact_path = parent / str(created_name)
            self.assertTrue(exact_path.is_dir())
            message = str(raised.exception)
            self.assertIn("primary failure: OSError: [Errno 5] injected post-mkdir EIO", message)
            self.assertIn(os.fspath(exact_path), message)
            self.assertIn("observed entry; not verified as writer-created", message)
            self.assertIsInstance(raised.exception.__cause__, OSError)
        finally:
            _force_remove(parent)

    def test_post_quarantine_rename_stat_eio_reports_exact_possible_path(self) -> None:
        parent = self._parent()
        output = parent / "release"
        real_rename = v4._rename_noreplace
        real_stat = v4._stat_at
        quarantine_name: str | None = None

        def capture_quarantine_rename(
            parent_fd: int, source_name: str, target_name: str
        ) -> None:
            nonlocal quarantine_name
            real_rename(parent_fd, source_name, target_name)
            if target_name.startswith(".release.recovery-"):
                quarantine_name = target_name

        def fail_quarantine_stat(parent_fd: int, name: str):
            if name == quarantine_name:
                raise OSError(errno.EIO, "injected quarantine stat EIO")
            return real_stat(parent_fd, name)

        try:
            with patch.object(
                v4,
                "validate_satellite_mosaic_preparation_v4",
                side_effect=SatelliteMosaicPreparationError(
                    "injected primary failure"
                ),
            ), patch.object(
                v4, "_rename_noreplace", side_effect=capture_quarantine_rename
            ), patch.object(
                v4, "_stat_at", side_effect=fail_quarantine_stat
            ), patch.object(
                v4.os, "unlink", side_effect=AssertionError("unlink forbidden")
            ), patch.object(
                v4.os, "rmdir", side_effect=AssertionError("rmdir forbidden")
            ):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )

            self.assertIsNotNone(quarantine_name)
            exact_path = parent / str(quarantine_name)
            self.assertTrue(exact_path.is_dir())
            self.assertFalse(output.exists())
            message = str(raised.exception)
            self.assertIn(
                "primary failure: SatelliteMosaicPreparationError: injected primary failure",
                message,
            )
            self.assertGreaterEqual(message.count("injected quarantine stat EIO"), 3)
            self.assertIn(
                "possible leftover path (unverified ownership; descriptor-relative state unavailable",
                message,
            )
            self.assertIn(os.fspath(exact_path), message)
            self.assertNotIn(
                f"writer-created tree identity verified and preserved without deletion at {exact_path}",
                message,
            )
            self.assertIsInstance(
                raised.exception.__cause__, SatelliteMosaicPreparationError
            )
        finally:
            _force_remove(parent)

    def test_tree_swap_during_quarantine_preserves_and_restores_substitute(self) -> None:
        parent = self._parent()
        output = parent / "release"
        real_rename = v4._rename_noreplace
        owned_names: list[str] = []
        swapped = False

        def swap_at_quarantine(parent_fd: int, source: str, target: str) -> None:
            nonlocal swapped
            if target.startswith(".release.recovery-") and not swapped:
                swapped = True
                owned = f"{source}.owned"
                real_rename(parent_fd, source, owned)
                owned_names.append(owned)
                os.mkdir(source, 0o700, dir_fd=parent_fd)
                source_fd = os.open(
                    source,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                    dir_fd=parent_fd,
                )
                try:
                    descriptor = os.open(
                        "marker",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=source_fd,
                    )
                    try:
                        os.write(descriptor, b"unrelated substitute\n")
                    finally:
                        os.close(descriptor)
                finally:
                    os.close(source_fd)
                real_rename(parent_fd, source, target)
                return
            real_rename(parent_fd, source, target)

        try:
            with patch.object(
                v4,
                "validate_satellite_mosaic_preparation_v4",
                side_effect=SatelliteMosaicPreparationError(
                    "injected primary failure"
                ),
            ), patch.object(v4, "_rename_noreplace", side_effect=swap_at_quarantine):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )
            self.assertIn("entry with unexpected identity", str(raised.exception))
            self.assertTrue(swapped)
            self.assertEqual(len(owned_names), 1)
            self.assertTrue((parent / owned_names[0]).is_dir())
            substitutes = [
                path
                for path in parent.iterdir()
                if path.is_dir() and (path / "marker").exists()
            ]
            self.assertEqual(len(substitutes), 1)
            self.assertEqual(
                (substitutes[0] / "marker").read_text(), "unrelated substitute\n"
            )
        finally:
            _force_remove(parent)

    def test_recovery_stat_eio_reports_every_unknown_generated_path(self) -> None:
        parent = self._parent()
        output = parent / "release"
        recovery_started = False
        real_stat = v4._stat_at

        def primary(*args, **kwargs):
            nonlocal recovery_started
            recovery_started = True
            raise SatelliteMosaicPreparationError("injected primary failure")

        def eio_after_primary(parent_fd: int, name: str):
            if recovery_started:
                raise OSError(errno.EIO, "injected recovery stat EIO")
            return real_stat(parent_fd, name)

        try:
            with patch.object(
                v4, "validate_satellite_mosaic_preparation_v4", side_effect=primary
            ), patch.object(v4, "_stat_at", side_effect=eio_after_primary):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )
            message = str(raised.exception)
            self.assertIn(
                "primary failure: SatelliteMosaicPreparationError: injected primary failure",
                message,
            )
            self.assertIn("recovery stat EIO", message)
            self.assertIn("recovery mutation refused", message)
            self.assertIn(os.fspath(output), message)
            self.assertIn("possible leftover path (unverified ownership", message)
            self.assertIsInstance(
                raised.exception.__cause__, SatelliteMosaicPreparationError
            )
        finally:
            _force_remove(parent)

    def test_publication_and_recovery_fsync_failures_never_return_success(self) -> None:
        parent = self._parent()
        output = parent / "release"
        real_sync = v4._sync_parent

        def failing_sync(parent_fd: int, phase: str) -> None:
            if phase in {
                "publication parent fsync",
                "rollback parent fsync",
                "recovery quarantine parent fsync",
            }:
                raise OSError(errno.EIO, f"injected {phase} failure")
            real_sync(parent_fd, phase)

        try:
            with patch.object(v4, "_sync_parent", side_effect=failing_sync):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )
            message = str(raised.exception)
            self.assertIn("injected publication parent fsync failure", message)
            self.assertIn("rollback parent fsync failed", message)
            self.assertIn("recovery quarantine parent fsync failed", message)
            self.assertFalse(output.exists())
            self.assertEqual(len(_recovery_paths(parent)), 1)
        finally:
            _force_remove(parent)

    def test_atomic_no_clobber_preserves_racing_target(self) -> None:
        parent = self._parent()
        output = parent / "release"
        real_rename = v4._rename_noreplace
        first = True

        def occupy_target(parent_fd: int, source: str, target: str) -> None:
            nonlocal first
            if first and target == "release":
                first = False
                os.mkdir(target, 0o700, dir_fd=parent_fd)
                target_fd = os.open(
                    target,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                    dir_fd=parent_fd,
                )
                try:
                    marker_fd = os.open(
                        "marker",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=target_fd,
                    )
                    try:
                        os.write(marker_fd, b"racing target\n")
                    finally:
                        os.close(marker_fd)
                finally:
                    os.close(target_fd)
            real_rename(parent_fd, source, target)

        try:
            with patch.object(v4, "_rename_noreplace", side_effect=occupy_target):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v4(
                        output, definition_path=DEFINITION
                    )
            message = str(raised.exception)
            self.assertIn("observed entry; not verified as writer-created", message)
            self.assertIn(os.fspath(output), message)
            self.assertEqual((output / "marker").read_text(), "racing target\n")
            self.assertEqual(len(_recovery_paths(parent)), 1)
        finally:
            _force_remove(parent)


if __name__ == "__main__":
    unittest.main()
