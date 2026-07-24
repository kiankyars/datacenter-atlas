from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map_v9 import (
    ConstructionMapV9Error,
    validate_construction_map_v9,
    write_construction_map_v9,
)
from datacenter_atlas.construction_master_v9 import (
    ConstructionMasterV9Error,
    validate_construction_master_v9,
    write_construction_master_v9,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-20-public-open-v25.json"
)
MASTER = ROOT / "construction_master/2026-07-20-public-open-v25"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v25.json"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v25"
V59_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
V24_MASTER = ROOT / "construction_master/2026-07-20-public-open-v24"
V24_MAP = ROOT / "construction_maps/2026-07-20-public-open-v24"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionMasterMapV25Tests(unittest.TestCase):
    maxDiff = None

    def test_frozen_pins_and_legacy_v24_preservation(self) -> None:
        pins = {
            ROOT / "datacenter_atlas/construction_master_v8.py": (
                2_664,
                "c5e6d1573ca8af855a35f57e57e1579f6588370458a3cac5cddf1fde92157946",
            ),
            ROOT / "datacenter_atlas/construction_map_v8.py": (
                3_039,
                "7b91d74faf58eac1e1ab5c9717ab4fea79a099283389fe0650aae15aebe4642a",
            ),
            V24_MASTER / "manifest.json": (
                9_719,
                "61f8c11ce3c782d63d02539b58ebfc2dd4f3e1c9f0957fe5ccda2bc5a5216705",
            ),
            V24_MAP / "manifest.json": (
                2_192,
                "2b2c2298a550c07a507c7083326f6e062c884a81f6e32da553d1f35c0a7b314b",
            ),
            ROOT / "datacenter_atlas/construction_master_v9.py": (
                2_550,
                "63ce982579d7d052729a5844954442da868f3126565910e2f5fc5b9f37f9b22d",
            ),
            ROOT / "datacenter_atlas/construction_map_v9.py": (
                2_611,
                "cdb2cf235fc053b00d093874d1ca024dffdb4ba09fe5c89ad3c97168c483249b",
            ),
            MASTER_DEFINITION: (
                5_658,
                "4f87fb1e2e8966b1bbdf5d6e4adc13e383fa83c5452899f504bc671bdef3bcd8",
            ),
            MAP_DEFINITION: (
                2_441,
                "00b7dc30961cbe09cbdb826c9181dddf4d4e8235ca50eaf1d8b97701eb4b5a88",
            ),
            MASTER / "manifest.json": (
                9_720,
                "d717f3ca4eb7f876ce175d42d7c09a338a182e727aeec151f9df555fccd261fd",
            ),
            MAP / "manifest.json": (
                2_192,
                "20e46d30fcde26b4e8fa1ede55e24235b4a9a7d808e85411d3174d374c50d001",
            ),
        }
        for path, (size, digest) in pins.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(_sha256(path), digest)
        for directory in (MASTER, MAP):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)
            for path in directory.iterdir():
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_master_exact_v59_replacement_and_guardrails(self) -> None:
        definition = json.loads(MASTER_DEFINITION.read_text(encoding="utf-8"))
        expected = definition["expected"]
        self.assertEqual(definition["master_id"], "2026-07-20-public-open-v25")
        self.assertEqual(definition["generated_at"], "2026-07-21T03:50:00Z")
        replacement = definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v59")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(replacement["manifest"]["sha256"], _sha256(V59_RELEASE / "manifest.json"))
        self.assertEqual(replacement["definition"]["sha256"], _sha256(V59_DEFINITION))
        self.assertEqual(expected["replacement_rows"], 362)
        self.assertEqual(expected["added_replacement_rows"], 163)
        self.assertEqual(expected["base_replaced_rows"], 199)
        self.assertEqual(expected["total_rows"], 109_274)
        self.assertEqual(expected["tier_a_rows"], 482)
        self.assertEqual(expected["tier_b_rows"], 6_298)
        self.assertEqual(expected["tier_c_rows"], 102_494)
        self.assertEqual(expected["satellite_recovery_rows"], 0)

        coverage = json.loads((MASTER / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["replacement_invariants"], expected)
        counts = coverage["row_counts"]
        self.assertEqual(counts["total"], 109_274)
        self.assertEqual(counts["by_source_artifact"]["epoch-official-open-seed-v59"], 362)
        self.assertIsNone(counts["unique_physical_site_count"])
        scope = coverage["scope"]
        self.assertFalse(scope["benchmark_parity_claimed"])
        self.assertFalse(scope["global_completeness_claimed"])
        self.assertFalse(scope["structural_or_cv_rows_in_construction_arithmetic"])
        self.assertTrue(scope["historical_status_is_not_current_status_claim"])

        release_manifest = json.loads(
            (V59_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(release_manifest["current_status_inferred"])
        self.assertEqual(release_manifest["lifecycle_status_semantics"], "last_observed")
        self.assertEqual(release_manifest["lifecycle_freshness_records"], 399)

    def test_map_is_exact_projection_not_site_count(self) -> None:
        definition = json.loads(MAP_DEFINITION.read_text(encoding="utf-8"))
        expected = definition["expected_projection"]
        self.assertEqual(
            expected,
            {
                "added_replacement_rows_unmapped": 157,
                "added_replacement_unmapped_source_record_ids_sha256": "717a09ba603bf352cf334c75752a31de68fa3901d54b89f06beb3c61dcf61e91",
                "default_visible_rows": 6_492,
                "default_visible_tiers": ["A", "B"],
                "mapped_by_tier": {"A": 212, "B": 6_280, "C": 102_494},
                "mapped_replacement_rows": 93,
                "mapped_rows": 108_986,
                "mapped_rows_with_any_role": 68,
                "master_rows": 109_274,
                "unmapped_rows": 288,
                "unmapped_source_record_ids_sha256": "8dc255e3025a155056151cd82813925d3e75048c2d1a6d1cdc647c78d112113a",
            },
        )
        coverage = json.loads((MAP / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["projection"], expected)
        self.assertEqual(coverage["counts"]["mapped_observation_rows"], 108_986)
        self.assertEqual(coverage["mapped_counts"]["by_source_artifact"]["epoch-official-open-seed-v59"], 93)
        self.assertIsNone(coverage["counts"]["unique_physical_site_count"])
        self.assertTrue(coverage["scope"]["map_rows_are_observations_not_unique_sites"])
        self.assertTrue(coverage["scope"]["historical_status_is_not_current_status_claim"])

    def test_offline_exact_validation_is_repeatable(self) -> None:
        with patch.object(socket, "socket", side_effect=AssertionError("network used")):
            master_manifest = validate_construction_master_v9(
                MASTER, definition_path=MASTER_DEFINITION
            )
            map_manifest = validate_construction_map_v9(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
            )
            self.assertEqual(
                validate_construction_master_v9(
                    MASTER, definition_path=MASTER_DEFINITION
                ),
                master_manifest,
            )
            self.assertEqual(
                validate_construction_map_v9(
                    MAP,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                ),
                map_manifest,
            )

    def test_existing_invalid_targets_are_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_master = root / "master"
            bad_master.mkdir()
            sentinel = bad_master / "sentinel"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(ConstructionMasterV9Error):
                write_construction_master_v9(
                    MASTER_DEFINITION, bad_master, freeze=False
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

            bad_map = root / "map"
            bad_map.mkdir()
            map_sentinel = bad_map / "sentinel"
            map_sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(ConstructionMapV9Error):
                write_construction_map_v9(
                    MASTER,
                    bad_map,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                    freeze=False,
                )
            self.assertEqual(map_sentinel.read_text(encoding="utf-8"), "keep")

    def test_workspace_and_installable_import_layouts(self) -> None:
        program = (
            "from datacenter_atlas.construction_master_v9 import "
            "ConstructionMasterV9Error; "
            "from datacenter_atlas.construction_map_v9 import "
            "ConstructionMapV9Error; "
            "print(ConstructionMasterV9Error.__name__, ConstructionMapV9Error.__name__)"
        )
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for cwd in (WORKSPACE, ROOT):
            result = subprocess.run(
                [sys.executable, "-c", program],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.strip(),
                "ConstructionMasterV9Error ConstructionMapV9Error",
            )


if __name__ == "__main__":
    unittest.main()
