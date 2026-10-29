from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import historical_sources


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = "current_coverage_v19.py"
WRAPPER_SHA256 = "5d66572dc18aa43dd6ebe68c20d7316032059100b449916353c7f27c2bf91e8e"


class HistoricalSourceTests(unittest.TestCase):
    def test_removed_wrapper_keeps_its_historical_fingerprint(self) -> None:
        self.assertFalse((ROOT / WRAPPER).exists())
        raw = historical_sources.read_source_bytes(WRAPPER)
        self.assertEqual(len(raw), 150)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), WRAPPER_SHA256)
        self.assertEqual(
            historical_sources.source_fingerprint(WRAPPER, include_mode=True),
            {"bytes": 150, "sha256": WRAPPER_SHA256, "mode": "0644"},
        )

    def test_historical_provenance_is_independent_of_live_source_edits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / WRAPPER
            path.write_text("# Changed executable code\n")
            historical = historical_sources.read_source_bytes(path, root=root)
            self.assertNotEqual(historical, path.read_bytes())
            self.assertEqual(hashlib.sha256(historical).hexdigest(), WRAPPER_SHA256)

    def test_unarchived_source_uses_the_actual_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "example_builder.py"
            path.write_bytes(b"first version\n")
            self.assertFalse(historical_sources.is_archived_source(path, root=root))
            self.assertEqual(historical_sources.read_source_bytes(path, root=root), b"first version\n")
            path.write_bytes(b"second version\n")
            self.assertEqual(historical_sources.read_source_bytes(path, root=root), b"second version\n")

    def test_corrupt_archive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.zip"
            corrupt.write_bytes(historical_sources.ARCHIVE_PATH.read_bytes() + b"changed")
            with patch.object(historical_sources, "ARCHIVE_PATH", corrupt):
                with self.assertRaisesRegex(historical_sources.HistoricalSourceError, "SHA-256 mismatch"):
                    historical_sources.read_source_bytes(WRAPPER)

    def test_archive_must_be_a_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "archive.zip"
            link.symlink_to(historical_sources.ARCHIVE_PATH)
            with patch.object(historical_sources, "ARCHIVE_PATH", link):
                with self.assertRaisesRegex(historical_sources.HistoricalSourceError, "regular file"):
                    historical_sources.read_source_bytes(WRAPPER)


if __name__ == "__main__":
    unittest.main()
