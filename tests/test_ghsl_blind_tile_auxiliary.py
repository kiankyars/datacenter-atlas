from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_ghsl_blind_tile_auxiliary.py"
CACHE = ROOT / "source_cache" / "ghsl-r2023a-2020-1km"
DEFINITION = ROOT / "sources" / "ghsl-blind-tile-auxiliary-2026-07-19-v1.json"


def _load_script():
    spec = importlib.util.spec_from_file_location("fetch_ghsl_blind_tile_auxiliary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GhslBlindTileAuxiliaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fetch = _load_script()
        cls.definition = json.loads(DEFINITION.read_bytes())

    def test_verify_only_pins_exact_archives_and_request_accounting(self) -> None:
        manifest = self.fetch.validate_cache(CACHE)
        self.assertEqual(manifest["http_request_count"], 4)
        self.assertEqual(manifest["downloaded_archive_count"], 2)
        self.assertEqual(sum(row["redirect_count"] for row in manifest["requests"]), 0)
        expected = {artifact.artifact_id: artifact for artifact in self.fetch.ARTIFACTS}
        self.assertEqual(set(expected), {row["artifact_id"] for row in manifest["artifacts"]})
        for row in manifest["artifacts"]:
            artifact = expected[row["artifact_id"]]
            self.assertEqual(row["archive"]["bytes"], artifact.expected_bytes)
            self.assertEqual(row["archive"]["sha256"], artifact.expected_sha256)

    def test_archives_pass_complete_zip_crc_validation(self) -> None:
        for artifact in self.fetch.ARTIFACTS:
            with self.subTest(artifact=artifact.artifact_id):
                with zipfile.ZipFile(CACHE / artifact.filename) as archive:
                    self.assertIsNone(archive.testzip())

    def test_definition_is_canonical_and_fail_closed_about_checksum_provenance(self) -> None:
        canonical = (
            json.dumps(self.definition, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode()
        self.assertEqual(DEFINITION.read_bytes(), canonical)
        self.assertFalse(
            self.definition["acquisition"]["publisher_archive_checksums_advertised"]
        )
        self.assertFalse(self.definition["integration_contract"]["production_frame_built"])
        self.assertTrue(self.definition["integration_contract"]["screen_not_site_detector"])
        self.assertEqual(
            self.definition["integration_contract"]["smod_l2_urban_codes"],
            [21, 22, 23, 30],
        )
        self.assertEqual(
            self.definition["integration_contract"]["crs_authority"], "ESRI:54009"
        )

    def test_metadata_is_bound_to_the_archive_hashes(self) -> None:
        metadata_path = CACHE / "raster-metadata.json"
        metadata = json.loads(metadata_path.read_bytes())
        self.assertEqual(
            metadata_path.read_bytes(),
            (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode(),
        )
        artifacts = {row["artifact_id"]: row for row in metadata["artifacts"]}
        self.assertEqual(
            artifacts["ghs-built-s-2020-1km-v1-0"]["raster"]["nodata"],
            4_294_967_295,
        )
        self.assertEqual(
            artifacts["ghs-smod-2020-1km-v2-0"]["raster"]["observed_values"],
            [-200, 10, 11, 12, 13, 21, 22, 23, 30],
        )
        definition_hash = self.definition["cache"]["fetch_manifest_sha256"]
        self.assertEqual(
            hashlib.sha256((CACHE / "fetch-manifest.json").read_bytes()).hexdigest(),
            definition_hash,
        )
        cache_contract = self.definition["cache"]
        self.assertEqual(metadata_path.stat().st_size, cache_contract["raster_metadata_bytes"])
        self.assertEqual(
            hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
            cache_contract["raster_metadata_sha256"],
        )
        readme_path = CACHE / "README.md"
        self.assertEqual(readme_path.stat().st_size, cache_contract["readme_bytes"])
        self.assertEqual(
            hashlib.sha256(readme_path.read_bytes()).hexdigest(),
            cache_contract["readme_sha256"],
        )

    def test_frozen_inventory_and_modes_are_exact(self) -> None:
        contract = self.definition["cache"]
        self.assertEqual(
            sorted(path.name for path in CACHE.iterdir()),
            contract["frozen_file_inventory"],
        )
        self.assertEqual(stat.S_IMODE(CACHE.stat().st_mode), int("0555", 8))
        for path in CACHE.iterdir():
            with self.subTest(path=path.name):
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), int("0444", 8))


if __name__ == "__main__":
    unittest.main()
