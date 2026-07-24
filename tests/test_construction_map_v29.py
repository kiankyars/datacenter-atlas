from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v29 as map_v29
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v29 as map_v29
    from datacenter_atlas.open_seed_v56 import tree_digest


GENERATED_AT = "2026-07-21T13:47:30Z"
GENERATED_EPOCH = datetime.fromisoformat(
    GENERATED_AT.replace("Z", "+00:00")
).timestamp()

FILE_PINS = {
    map_v29.DEFINITION: (
        2_442,
        "9668c1ee0eadfb755745407a2b140e414044a9c97dfeecaf95b131afbf8446bc",
    ),
    map_v29.BUNDLE / "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    map_v29.BUNDLE / "README.md": (
        518,
        "dc374cf972756c00615fe6fc6ffc8e6bb231c307a08589af142c772f09a234ac",
    ),
    map_v29.BUNDLE / map_v29.INDEX_FILENAME: (
        6_681_116,
        "059c2b7a7f2cef562bc9548492ff363036f680829df0de8bf382a2e5368d11fc",
    ),
    map_v29.BUNDLE / "construction-map.html": (
        8_925_764,
        "188ec90273adaa3e33a2a51066d252440ae9ebbfd6e0b41fbd5ac17564c76e91",
    ),
    map_v29.BUNDLE / "coverage.json": (
        7_465,
        "7af745a8c3ec6d2cfd76047dd544febb79cef207c5b75d2be540644dde917398",
    ),
    map_v29.BUNDLE / map_v29.MANIFEST_FILENAME: (
        2_192,
        "5cfaeba6d854df6aabb4b4c500701d1a3d1d9f7c1e4d1481a986a2602374b889",
    ),
    map_v29.BUNDLE / "manifest.sha256": (
        80,
        "6ae78ee6763a7b92975f53167f7f97c9a834776a3b0e8c1296b3a09ae4949c0c",
    ),
}
BUNDLE_TREE_SHA256 = (
    "b551f672a6ce6e82815a0633cc5c7cbd45ce358b9d8f1db1bd8257c4c36fe4b8"
)


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV29Tests(unittest.TestCase):
    def test_exact_pins_closed_inventory_freeze_and_temporal_commit(self) -> None:
        self.assertFalse(map_v29.DEFINITION.is_symlink())
        self.assertFalse(map_v29.BUNDLE.is_symlink())
        self.assertEqual(
            {path.name for path in map_v29.BUNDLE.iterdir()},
            map_v29.BUNDLE_FILES,
        )
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(tree_digest(map_v29.BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(map_v29.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(map_v29.BUNDLE.stat().st_mode), 0o555)
        for path in map_v29.BUNDLE.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)

        staged_paths = (
            map_v29.DEFINITION,
            map_v29.BUNDLE,
            *map_v29.BUNDLE.iterdir(),
        )
        for path in staged_paths:
            metadata = path.stat()
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            self.assertLessEqual(max(birth, metadata.st_mtime), GENERATED_EPOCH)
        self.assertGreaterEqual(map_v29.DEFINITION.stat().st_ctime, GENERATED_EPOCH)
        self.assertGreaterEqual(map_v29.BUNDLE.stat().st_ctime, GENERATED_EPOCH)

    def test_definition_is_exact_v28_successor_and_binds_accepted_master(self) -> None:
        predecessor = json.loads(map_v29.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v29.DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v29.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v29.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)
        self.assertEqual(map_v29.DEFINITION.read_bytes(), map_v29._canonical_json(current))
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(current["template"], predecessor["template"])
        self.assertEqual(current["master"]["master_id"], map_v29.MASTER_ID)
        self.assertEqual(
            current["master"]["definition"]["sha256"],
            map_v29.MASTER_DEFINITION_SHA256,
        )
        self.assertEqual(
            current["master"]["jsonl"]["sha256"], map_v29.MASTER_JSONL_SHA256
        )
        self.assertEqual(
            current["master"]["manifest"]["sha256"],
            map_v29.MASTER_MANIFEST_SHA256,
        )

    def test_full_validator_replays_twice_and_preserves_conservative_scope(self) -> None:
        manifest = map_v29.validate_construction_map_v29(
            validation_wall_clock=datetime.now(timezone.utc)
        )
        self.assertEqual(manifest["map_id"], map_v29.MAP_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["master"]["rows"], 109_332)
        self.assertIsNone(manifest["scope"]["unique_physical_site_count"])
        self.assertFalse(manifest["scope"]["entity_merges_created"])
        self.assertFalse(manifest["scope"]["global_completeness_claimed"])
        self.assertTrue(
            manifest["scope"]["historical_status_is_not_current_status_claim"]
        )
        payload = map_v29.DEFINITION.read_bytes() + b"".join(
            path.read_bytes() for path in sorted(map_v29.BUNDLE.iterdir())
        )
        for token in map_v29.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, payload)

    def test_future_wall_and_republication_are_rejected_without_mutation(self) -> None:
        before = {
            "definition": checkpoint(map_v29.DEFINITION),
            "tree": tree_digest(map_v29.BUNDLE),
        }
        with self.assertRaisesRegex(
            map_v29.ConstructionMapV29Error, "generated_at exceeds wall clock"
        ):
            map_v29._validate_temporal_closure(
                map_v29.DEFINITION,
                map_v29.BUNDLE,
                map_v29.MASTER_DEFINITION,
                map_v29.MASTER,
                validation_wall_clock=(
                    datetime.fromtimestamp(GENERATED_EPOCH, timezone.utc)
                    - timedelta(microseconds=1)
                ),
            )
        with self.assertRaisesRegex(
            map_v29.ConstructionMapV29Error, "refusing replacement"
        ):
            map_v29.publish_construction_map_v29("2026-07-21T13:55:00Z")
        self.assertEqual(
            {
                "definition": checkpoint(map_v29.DEFINITION),
                "tree": tree_digest(map_v29.BUNDLE),
            },
            before,
        )


if __name__ == "__main__":
    unittest.main()
