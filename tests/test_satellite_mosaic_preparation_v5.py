from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.satellite_mosaic_preparation_v5 as v5
from datacenter_atlas.satellite_mosaic_preparation_v5 import (
    RELEASE_FILES,
    SatelliteMosaicPreparationError,
    validate_satellite_mosaic_preparation_v5,
    write_satellite_mosaic_preparation_v5,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    ROOT
    / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v5.json"
)
RELEASE = (
    ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v5"
)
V2_RELEASE = (
    ROOT / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v2"
)
CLI = ROOT / "scripts/build_satellite_mosaic_preparation_v5.py"


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


def _fd_count() -> int:
    return len(os.listdir("/dev/fd"))


class SatelliteMosaicPreparationV5Tests(unittest.TestCase):
    def _parent(self) -> Path:
        return Path(tempfile.mkdtemp(prefix=".mosaic-v5-test-", dir=ROOT))

    def test_v1_through_v4_rejected_evidence_is_byte_preserved(self) -> None:
        definition_hashes = {
            1: "24b18962bea7f45d06f84a0a93d9c1eba8ba332b94077eb3d2d4e9afe8003ba8",
            2: "92c45ec8d6f4058a182411282dfc5314d4e6208f9f9dfd77e804b99265237cae",
            3: "6da293ff7d53fe044f76e2b253723d7f56719f30a67c94ba3155762146670967",
            4: "f054706117ca698cf0871da24efab31c71aed7c6d0bae48ec093c82db4d9e019",
        }
        tree_hashes = {
            1: "8b714f86265eb106d74d26ac98c966d71aa7f41f7f504a1cd160a465813eab22",
            2: "8d6536fe05728a74387cb60ec87b2c1ae2095b9229d850ba2d2f5be79bc646b6",
            3: "4fd67858fb75662cc9273cedfd60d047048683f233248da109d13fdc5ae57caa",
            4: "771897b7f86982ef0150505cc9e02ee74177c2aeda1fbcdbd7021f26debee9fe",
        }
        for version in range(1, 5):
            definition = ROOT / (
                "sources/satellite-mosaic-preparation-2026-07-19-"
                f"algorithm-v2-blocked-v{version}.json"
            )
            release = ROOT / (
                "satellite_mosaic_preparation/2026-07-19-"
                f"algorithm-v2-blocked-v{version}"
            )
            self.assertEqual(
                hashlib.sha256(definition.read_bytes()).hexdigest(),
                definition_hashes[version],
            )
            self.assertEqual(_tree_digest(release), tree_hashes[version])

    def test_definition_marks_v4_rejected_and_declares_close_contract(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["schema_version"], 5)
        self.assertEqual(
            definition["rejected_predecessor"],
            {
                "bytes": 2289,
                "mode": "0444",
                "path": "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v4.json",
                "sha256": "f054706117ca698cf0871da24efab31c71aed7c6d0bae48ec093c82db4d9e019",
            },
        )
        contract = definition["publication_contract"]
        self.assertEqual(
            contract["ambiguous_mkdir_failure_policy"],
            "fail_closed_and_report_exact_candidate",
        )
        self.assertTrue(contract["all_descriptor_closes_attempted"])
        self.assertTrue(contract["descriptor_close_errors_aggregated"])
        self.assertTrue(contract["descriptor_close_failure_paths_reported"])

    def test_v5_release_validates_and_preserves_scientific_bytes(self) -> None:
        manifest = validate_satellite_mosaic_preparation_v5(
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
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o444 for path in RELEASE.iterdir())
        )

    def test_cli_validates_v5_release(self) -> None:
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
            '"format": "datacenter-atlas-satellite-mosaic-v3-preparation-v5"',
            completed.stdout,
        )

    def test_socket_blocked_fresh_build_is_exact(self) -> None:
        parent = self._parent()
        output = parent / "release"
        try:
            with patch.object(
                socket, "socket", side_effect=AssertionError("socket forbidden")
            ), patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("socket forbidden"),
            ):
                write_satellite_mosaic_preparation_v5(
                    output, definition_path=DEFINITION
                )
            for name in RELEASE_FILES:
                self.assertEqual(
                    (output / name).read_bytes(), (RELEASE / name).read_bytes()
                )
        finally:
            _force_remove(parent)

    def test_create_then_fileexists_fails_closed_reports_path_and_keeps_fds_stable(
        self,
    ) -> None:
        parent = self._parent()
        output = parent / "release"
        real_mkdir = v5.os.mkdir
        created_name: str | None = None
        # Rasterio lazily initializes process-global resources on first use; do that
        # before taking the descriptor baseline so the assertion isolates the writer.
        v5._payloads(DEFINITION, output)
        before = _fd_count()

        def create_then_fileexists(
            name: str, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> None:
            nonlocal created_name
            if name.startswith(".release.staging-") and created_name is None:
                real_mkdir(name, mode, dir_fd=dir_fd)
                created_name = name
                raise FileExistsError(
                    errno.EEXIST, "injected create-then-FileExistsError", name
                )
            real_mkdir(name, mode, dir_fd=dir_fd)

        try:
            with patch.object(v5.os, "mkdir", side_effect=create_then_fileexists):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v5(
                        output, definition_path=DEFINITION
                    )
            self.assertEqual(_fd_count(), before)
            self.assertIsNotNone(created_name)
            exact_path = parent / str(created_name)
            self.assertTrue(exact_path.is_dir())
            message = str(raised.exception)
            self.assertIn("ambiguous staging mkdir FileExistsError", message)
            self.assertIn(os.fspath(exact_path), message)
            self.assertIn("observed entry; not verified as writer-created", message)
            self.assertFalse(output.exists())
        finally:
            _force_remove(parent)

    def test_real_close_then_raise_aggregates_both_closes_paths_and_has_no_fd_leak(
        self,
    ) -> None:
        parent = self._parent()
        output = parent / "release"
        v5._payloads(DEFINITION, output)
        before = _fd_count()
        real_open_parent = v5.v2._open_output_parent
        real_freeze = v5.v2._freeze_staging
        real_close = v5.os.close
        parent_fd: int | None = None
        tree_fd: int | None = None
        staging_name = ".release.staging-0123456789abcdef"
        close_calls: list[int] = []

        def capture_parent(*args, **kwargs):
            nonlocal parent_fd
            opened = real_open_parent(*args, **kwargs)
            parent_fd = opened[2]
            return opened

        def capture_tree(
            opened_parent_fd: int,
            opened_staging_name: str,
            opened_tree_fd: int,
            tree_identity: tuple[int, int],
        ) -> None:
            nonlocal tree_fd
            tree_fd = opened_tree_fd
            real_freeze(
                opened_parent_fd,
                opened_staging_name,
                opened_tree_fd,
                tree_identity,
            )

        def real_close_then_raise(descriptor: int) -> None:
            close_calls.append(descriptor)
            if descriptor == tree_fd:
                real_close(descriptor)
                raise OSError(errno.EIO, "injected post-tree-close EIO")
            if descriptor == parent_fd:
                real_close(descriptor)
                raise OSError(errno.EIO, "injected post-parent-close EIO")
            real_close(descriptor)

        try:
            with patch.object(
                v5.v2, "_open_output_parent", side_effect=capture_parent
            ), patch.object(
                v5.v2, "_freeze_staging", side_effect=capture_tree
            ), patch.object(
                v5.secrets, "token_hex", return_value="0123456789abcdef"
            ), patch.object(v5.os, "close", side_effect=real_close_then_raise):
                with self.assertRaises(SatelliteMosaicPreparationError) as raised:
                    write_satellite_mosaic_preparation_v5(
                        output, definition_path=DEFINITION
                    )

            self.assertIsNotNone(tree_fd)
            self.assertIsNotNone(parent_fd)
            self.assertIn(tree_fd, close_calls)
            self.assertIn(parent_fd, close_calls)
            self.assertLess(close_calls.index(tree_fd), close_calls.index(parent_fd))
            self.assertEqual(_fd_count(), before)
            message = str(raised.exception)
            self.assertIn("staged tree descriptor close failed", message)
            self.assertIn("output parent descriptor close failed", message)
            self.assertIn("injected post-tree-close EIO", message)
            self.assertIn("injected post-parent-close EIO", message)
            self.assertIn(os.fspath(output), message)
            self.assertIn(os.fspath(parent / staging_name), message)
            self.assertTrue(output.is_dir())
            validate_satellite_mosaic_preparation_v5(
                output, definition_path=DEFINITION
            )
        finally:
            _force_remove(parent)


if __name__ == "__main__":
    unittest.main()
