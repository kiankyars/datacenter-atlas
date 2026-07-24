from __future__ import annotations

import hashlib
import json
import stat
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

try:
    from datacenter_atlas import construction_master_v32 as shim
    from datacenter_atlas.datacenter_atlas import construction_master_v32 as master
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    import construction_master_v32 as shim
    from datacenter_atlas import construction_master_v32 as master
    from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
TRANSACTION = ROOT / ".construction-master-v32.transaction-8gsvvbir"
PRIVATE_DEFINITION = TRANSACTION / "construction-master-2026-07-22-public-open-v32.json"
PRIVATE_BUNDLE = TRANSACTION / "bundle"
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v31.json"
)
PREDECESSOR_JSONL = (
    ROOT / "construction_master/2026-07-21-public-open-v31/construction-master.jsonl"
)

DEFINITION_PIN = (
    5_661,
    "05ed7f1eb48a54efb9e21224356d85108c897e977e2d458d52d10d2c0e14dbdb",
)
BUNDLE_TREE_PIN = "9a651415dbf66c99bcf07bc6aa268a05fc43aa03afaca1eea94cf8b31fed4084"
BUNDLE_PINS = {
    "ATTRIBUTION.txt": (
        5_814,
        "90035aa24b2b68cc54bdc54741cfd36c446975ae517094b8c33256812386b78a",
    ),
    "README.md": (
        1_349,
        "97b9208e80c84cfb20cee9ca53a5ad314b1d3267a28ac976756d24cf67d676bd",
    ),
    "construction-master.csv": (
        190_114_922,
        "50b192c91d3f31c0e281b4a806c735aa654fbc5639e78698c2ebeb1efb8b223f",
    ),
    "construction-master.jsonl": (
        326_143_453,
        "60388e1a111a880ab04ab4ec6aa95bd3cf2a04eaa77b16a1bcd0b85533a32eae",
    ),
    "coverage.json": (
        8_552,
        "a8eb504d91f762bc0a2cfc02fc336cc2cd6559960286c17f0ac2b5e7f7405074",
    ),
    "manifest.json": (
        9_721,
        "aee4310084012a0adc77b0833df6325c6a2da57d4379fe6b57b49b133876294a",
    ),
    "manifest.sha256": (
        80,
        "7c8e499f614cdd9a5c90211f7e04538d3cf6b3375fad9eca2f46d2c790d095dd",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def replacement_ids(path: Path, count: int) -> set[str]:
    result: set[str] = set()
    with path.open("rb") as source:
        for _ in range(count):
            row = json.loads(source.readline())
            result.add(row["source"]["record_id"])
    return result


class ConstructionMasterV32Tests(unittest.TestCase):
    def test_definition_is_exact_v31_to_v97_successor(self) -> None:
        current = master.construction_master_v32_definition()
        with patch.object(
            master, "_identity_final_state", return_value=(False, False, False)
        ):
            prospective = master.construction_master_v32_definition(
                allow_prospective_identity=True
            )
            with self.assertRaisesRegex(
                master.ConstructionMasterV32Error,
                "accepted identity v14 final is absent",
            ):
                master.construction_master_v32_definition()
        self.assertEqual(prospective, current)
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["expected"] = {
            **master.EXPECTED_FIXED,
            **master.EXPECTED_DIGESTS,
        }
        expected["generated_at"] = master.GENERATED_AT
        expected["inputs"]["replacement_release"] = deepcopy(master.REPLACEMENT_INPUTS)
        expected["master_id"] = master.MASTER_ID
        self.assertEqual(current, expected)
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(
            current["inputs"]["base_master"], predecessor["inputs"]["base_master"]
        )
        self.assertEqual(
            current["inputs"]["satellite_recovery_acceptance"],
            predecessor["inputs"]["satellite_recovery_acceptance"],
        )

    def test_private_candidate_exact_pins_counts_and_freeze(self) -> None:
        manifest = master.validate_construction_master_v32(
            PRIVATE_BUNDLE,
            definition_path=PRIVATE_DEFINITION,
            reproduce=False,
            allow_prospective_identity=False,
        )
        self.assertEqual(checkpoint(PRIVATE_DEFINITION), DEFINITION_PIN)
        self.assertEqual(
            {path.name: checkpoint(path) for path in PRIVATE_BUNDLE.iterdir()},
            BUNDLE_PINS,
        )
        self.assertEqual(tree_digest(PRIVATE_BUNDLE), BUNDLE_TREE_PIN)
        self.assertEqual(manifest["row_counts"]["total"], 109_443)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 651, "B": 6_298, "C": 102_494},
        )
        coverage = json.loads((PRIVATE_BUNDLE / "coverage.json").read_bytes())
        self.assertEqual(
            coverage["role_counts"]["rows_with_any_role"],
            205,
        )
        self.assertEqual(stat.S_IMODE(PRIVATE_DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(PRIVATE_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PRIVATE_BUNDLE.iterdir()
            )
        )
        self.assertFalse(master.DEFINITION_PATH.exists())
        self.assertFalse(master.BUNDLE_PATH.exists())

    def test_exact_62_row_replacement_delta_and_unchanged_inherited_bytes(
        self,
    ) -> None:
        old_ids = replacement_ids(PREDECESSOR_JSONL, 469)
        new_jsonl = PRIVATE_BUNDLE / "construction-master.jsonl"
        new_ids = replacement_ids(new_jsonl, 531)
        self.assertFalse(old_ids - new_ids)
        self.assertEqual(len(new_ids - old_ids), 62)
        with PREDECESSOR_JSONL.open("rb") as old, new_jsonl.open("rb") as new:
            for _ in range(469):
                self.assertTrue(old.readline())
            for _ in range(531):
                self.assertTrue(new.readline())
            while chunk := old.read(1024 * 1024):
                self.assertEqual(new.read(len(chunk)), chunk)
            self.assertEqual(new.read(1), b"")

    def test_shim_and_publication_surfaces_remain_unpublished(self) -> None:
        self.assertIs(
            shim.publish_construction_master_v32,
            master.publish_construction_master_v32,
        )
        self.assertIs(
            shim.validate_construction_master_v32,
            master.validate_construction_master_v32,
        )
        self.assertFalse(master.PUBLICATION_LOCK.exists())
        self.assertFalse(master.DEFINITION_PATH.exists())
        self.assertFalse(master.BUNDLE_PATH.exists())


if __name__ == "__main__":
    unittest.main()
