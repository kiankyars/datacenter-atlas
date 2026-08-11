from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.external_captures import (
    DEFAULT_PACKAGE_ROOT,
    ExternalCaptureError,
    PACKAGE_ROOT_ENV,
    external_capture_package_root,
    resolve_external_capture,
)


REGIONAL_GAP_ORIGIN = Path(
    "/Users/kian/.Trash/dc-regional-gap-20260721.pz8R6c"
)


class ExternalCaptureTests(unittest.TestCase):
    def test_all_manifest_roots_resolve_without_mutating_provenance(self) -> None:
        document = json.loads(
            (DEFAULT_PACKAGE_ROOT / "MANIFEST.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(document["items"]), 60)
        for item in document["items"]:
            original = Path(item["original_absolute_path"])
            resolved = resolve_external_capture(original)
            self.assertEqual(
                resolved,
                DEFAULT_PACKAGE_ROOT / item["payload_relative_path"],
            )
            self.assertTrue(resolved.exists() or resolved.is_symlink())
            self.assertEqual(str(original), item["original_absolute_path"])

    def test_manifest_root_resolves_descendant(self) -> None:
        resolved = resolve_external_capture(
            REGIONAL_GAP_ORIGIN / "niger_gov.body"
        )
        self.assertEqual(
            resolved,
            DEFAULT_PACKAGE_ROOT
            / (
                "payload/Users/kian/.Trash/"
                "dc-regional-gap-20260721.pz8R6c/niger_gov.body"
            ),
        )
        self.assertTrue(resolved.is_file())

    def test_existing_historical_path_wins_without_manifest_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "live-capture"
            existing.mkdir()
            self.assertEqual(resolve_external_capture(existing), existing)

    def test_environment_override_is_a_package_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "portable-package"
            payload = package / "payload/private/tmp/example"
            payload.mkdir(parents=True)
            (package / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "original_absolute_path": "/private/tmp/example",
                                "payload_relative_path": "payload/private/tmp/example",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {PACKAGE_ROOT_ENV: str(package)}):
                self.assertEqual(external_capture_package_root(), package)
                self.assertEqual(
                    resolve_external_capture("/private/tmp/example"), payload
                )

    def test_unknown_or_unsafe_paths_fail_closed(self) -> None:
        with self.assertRaisesRegex(ExternalCaptureError, "not declared"):
            resolve_external_capture("/private/tmp/not-exported")

        traversal = REGIONAL_GAP_ORIGIN / ".." / "dc-global-official-next-20260721.umOnmx"
        with self.assertRaisesRegex(ExternalCaptureError, "traversal"):
            resolve_external_capture(traversal)

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "unsafe-package"
            package.mkdir()
            (package / "MANIFEST.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "original_absolute_path": "/private/tmp/example",
                                "payload_relative_path": "../escape",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ExternalCaptureError, "unsafe"):
                resolve_external_capture(
                    "/private/tmp/example", package_root=package
                )


if __name__ == "__main__":
    unittest.main()
