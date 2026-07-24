from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from datacenter_atlas.epoch_source_capture import (
    EpochSourceCaptureError,
    validate_epoch_source_capture,
)


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "source_cache" / "epoch-ai-data-centers-2026-07-19"


class EpochSourceCaptureTests(unittest.TestCase):
    def mutable_copy(self, temporary: Path) -> Path:
        target = temporary / "capture"
        shutil.copytree(CAPTURE, target)
        target.chmod(0o755)
        for path in target.iterdir():
            path.chmod(0o644)
        return target

    def test_frozen_capture_validates_exact_accounting(self) -> None:
        manifest = validate_epoch_source_capture(CAPTURE)
        self.assertEqual(manifest["request_count"], 4)
        self.assertEqual(len(manifest["archive_inventory"]), 6)
        self.assertEqual(manifest["archive_uncompressed_bytes"], 384_385)
        self.assertEqual(
            manifest["dataset_inventory"],
            {
                "data_center_rows": 74,
                "timeline_names_missing_from_data_centers": ["EdgeCore Mesa PH03"],
                "timeline_rows": 419,
            },
        )
        self.assertEqual(
            hashlib.sha256((CAPTURE / "data_centers.zip").read_bytes()).hexdigest(),
            "d3025a1ffd19deb988031a9816234abf924bd8e11d01a34f724ef99362e466de",
        )

    def test_mutable_capture_requires_explicit_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            validate_epoch_source_capture(copy, require_frozen=False)
            with self.assertRaisesRegex(EpochSourceCaptureError, "mode 0555"):
                validate_epoch_source_capture(copy)

    def test_changed_fetched_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            (copy / "landing.html").write_bytes(b"changed")
            with self.assertRaisesRegex(EpochSourceCaptureError, "landing.html"):
                validate_epoch_source_capture(copy, require_frozen=False)

    def test_unexpected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            (copy / "extra").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(EpochSourceCaptureError, "file set differs"):
                validate_epoch_source_capture(copy, require_frozen=False)

    def test_archive_traversal_member_is_rejected_even_if_redeclared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            archive_path = copy / "data_centers.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../data_centers.csv", "Name\nUnsafe\n")
                archive.writestr(
                    "data_center_timelines.csv", "Data center,Date\nUnsafe,2026-01-01\n"
                )
            manifest_path = copy / "fetch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw = archive_path.read_bytes()
            source = next(
                item for item in manifest["sources"] if item["filename"] == "data_centers.zip"
            )
            source["bytes"] = len(raw)
            source["sha256"] = hashlib.sha256(raw).hexdigest()
            with zipfile.ZipFile(archive_path) as archive:
                manifest["archive_inventory"] = [
                    {
                        "bytes": item.file_size,
                        "crc32": f"{item.CRC:08x}",
                        "name": item.filename,
                    }
                    for item in archive.infolist()
                ]
                manifest["archive_uncompressed_bytes"] = sum(
                    item.file_size for item in archive.infolist()
                )
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(EpochSourceCaptureError, "unsafe"):
                validate_epoch_source_capture(copy, require_frozen=False)

    def test_symlinked_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            copy = self.mutable_copy(temporary)
            alias = temporary / "alias"
            alias.symlink_to(copy, target_is_directory=True)
            with self.assertRaisesRegex(EpochSourceCaptureError, "regular directory"):
                validate_epoch_source_capture(alias, require_frozen=False)


if __name__ == "__main__":
    unittest.main()
