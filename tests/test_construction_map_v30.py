from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v30 as map_v30
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v30 as map_v30
    from datacenter_atlas.open_seed_v56 import tree_digest


GENERATED_AT = "2026-07-21T18:11:00Z"
GENERATED_EPOCH = datetime.fromisoformat(
    GENERATED_AT.replace("Z", "+00:00")
).timestamp()

FILE_PINS = {
    map_v30.DEFINITION: (
        2_442,
        "47f2322edd2983bc8ed881edf8e0071d806df304cf773be2e215bcc1806d0847",
    ),
    map_v30.BUNDLE / "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    map_v30.BUNDLE / "README.md": (
        518,
        "becb754c1bc0113602f5f28f15b9003e4c4fa4eef07462373ecc568934caafda",
    ),
    map_v30.BUNDLE / map_v30.INDEX_FILENAME: (
        6_682_084,
        "dc5fcccf70fbd7232062134831bfdd68172013ae5d53a35ee5de8ac1fffaa718",
    ),
    map_v30.BUNDLE / "construction-map.html": (
        8_927_056,
        "e46c46e436fd085121d32d21d5dea280f0a0829063fe79fcd7d4d345be8746e6",
    ),
    map_v30.BUNDLE / "coverage.json": (
        7_524,
        "bb4eeb2cfafdc50e0b1fedf21feee4fdef399b7ddc460306b7cb0f128b48b61f",
    ),
    map_v30.BUNDLE / map_v30.MANIFEST_FILENAME: (
        2_192,
        "73108a00068912f83233114fc2ab7ae79087e610d54226762512fe3cc8ef4360",
    ),
    map_v30.BUNDLE / "manifest.sha256": (
        80,
        "36f0aca1ae93f1cb8184967881984ceadbd590531ebfe3fc9cbf9632f8652429",
    ),
}
BUNDLE_TREE_SHA256 = (
    "67bc3870ddc2c34308ab0de5defe19ece9d9cea85f6f1ac5c1d4082b18714149"
)


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV30Tests(unittest.TestCase):
    def test_exact_pins_closed_inventory_freeze_and_temporal_commit(self) -> None:
        self.assertFalse(map_v30.DEFINITION.is_symlink())
        self.assertFalse(map_v30.BUNDLE.is_symlink())
        self.assertEqual(
            {path.name for path in map_v30.BUNDLE.iterdir()},
            map_v30.BUNDLE_FILES,
        )
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(tree_digest(map_v30.BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(map_v30.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(map_v30.BUNDLE.stat().st_mode), 0o555)
        for path in map_v30.BUNDLE.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)

        staged_paths = (
            map_v30.DEFINITION,
            map_v30.BUNDLE,
            *map_v30.BUNDLE.iterdir(),
        )
        for path in staged_paths:
            metadata = path.stat()
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            self.assertLessEqual(max(birth, metadata.st_mtime), GENERATED_EPOCH)
        self.assertGreaterEqual(map_v30.DEFINITION.stat().st_ctime, GENERATED_EPOCH)
        self.assertGreaterEqual(map_v30.BUNDLE.stat().st_ctime, GENERATED_EPOCH)

    def test_definition_is_exact_v29_successor_and_binds_accepted_master(self) -> None:
        predecessor = json.loads(map_v30.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v30.DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v30.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v30.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)
        self.assertEqual(
            map_v30.DEFINITION.read_bytes(), map_v30._canonical_json(current)
        )
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(current["template"], predecessor["template"])
        self.assertEqual(current["master"]["master_id"], map_v30.MASTER_ID)
        self.assertEqual(
            current["master"]["definition"]["sha256"],
            map_v30.MASTER_DEFINITION_SHA256,
        )
        self.assertEqual(
            current["master"]["jsonl"]["sha256"],
            map_v30.MASTER_JSONL_SHA256,
        )
        self.assertEqual(
            current["master"]["manifest"]["sha256"],
            map_v30.MASTER_MANIFEST_SHA256,
        )

    def test_full_validator_replays_twice_and_preserves_conservative_scope(self) -> None:
        manifest = map_v30.validate_construction_map_v30(
            validation_wall_clock=datetime.now(timezone.utc)
        )
        self.assertEqual(manifest["map_id"], map_v30.MAP_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["master"]["rows"], 109_374)
        self.assertIsNone(manifest["scope"]["unique_physical_site_count"])
        self.assertFalse(manifest["scope"]["entity_merges_created"])
        self.assertFalse(manifest["scope"]["global_completeness_claimed"])
        self.assertTrue(
            manifest["scope"]["historical_status_is_not_current_status_claim"]
        )
        payload = map_v30.DEFINITION.read_bytes() + b"".join(
            path.read_bytes() for path in sorted(map_v30.BUNDLE.iterdir())
        )
        for token in map_v30.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, payload)

    def test_future_wall_and_republication_are_rejected_without_mutation(self) -> None:
        before = {
            "definition": checkpoint(map_v30.DEFINITION),
            "tree": tree_digest(map_v30.BUNDLE),
        }
        with self.assertRaisesRegex(
            map_v30.ConstructionMapV30Error, "generated_at exceeds wall clock"
        ):
            map_v30._validate_temporal_closure(
                map_v30.DEFINITION,
                map_v30.BUNDLE,
                map_v30.MASTER_DEFINITION,
                map_v30.MASTER,
                validation_wall_clock=(
                    datetime.fromtimestamp(GENERATED_EPOCH, timezone.utc)
                    - timedelta(microseconds=1)
                ),
            )
        with self.assertRaisesRegex(
            map_v30.ConstructionMapV30Error, "refusing replacement"
        ):
            map_v30.publish_construction_map_v30("2026-07-21T18:15:00Z")
        self.assertEqual(
            {
                "definition": checkpoint(map_v30.DEFINITION),
                "tree": tree_digest(map_v30.BUNDLE),
            },
            before,
        )


if __name__ == "__main__":
    unittest.main()
