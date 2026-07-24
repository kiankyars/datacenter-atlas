from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v31 as map_v31
    from datacenter_atlas import construction_map_v31 as shim
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v31 as map_v31
    import construction_map_v31 as shim
    from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-07-22T00:20:00Z"
GENERATED_EPOCH = datetime.fromisoformat(
    GENERATED_AT.replace("Z", "+00:00")
).timestamp()

FILE_PINS = {
    map_v31.DEFINITION: (
        2_442,
        "a8c15cc5f78e3b0c2b7a40b46b496b7c3561662aefda237424dc1c4b6d138f97",
    ),
    map_v31.BUNDLE / "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    map_v31.BUNDLE / "README.md": (
        518,
        "73dc61757fa25232a65bfb26c86ffb1707c986d4700fbd9a69fa449ab0a8256f",
    ),
    map_v31.BUNDLE / map_v31.INDEX_FILENAME: (
        6_683_391,
        "a854c2cce01273484277795d4feae80784cce67dde2f8e6c9beeb065dd8af1d7",
    ),
    map_v31.BUNDLE / "construction-map.html": (
        8_928_796,
        "40636e19c34340fe940d6ac4e8174abad4a3065e74c9970ea05bd8d6b81c2726",
    ),
    map_v31.BUNDLE / "coverage.json": (
        7_524,
        "64d4413ec97faf3dedd8ef463dbde3efdf8b51d054585afaaca819e01e0f59d1",
    ),
    map_v31.BUNDLE / map_v31.MANIFEST_FILENAME: (
        2_192,
        "5305dd9c637a74dbd2a3b355e19185e1fd9f49b815b8a9a51786ce8428b33631",
    ),
    map_v31.BUNDLE / "manifest.sha256": (
        80,
        "5f73a27234b6d71fafa9b3ecd80f7fd220c1d36479aaa5532b767f92380b953b",
    ),
}
BUNDLE_TREE_SHA256 = (
    "73e913f53287a2474274b6ff16daf10dcb8cd2ceceadc766e9aedd9ba3852973"
)
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_map_v31.py": (
        9_900,
        "846746ae0a290600f1779ab706a90611a3adb05f470e1f656759afed0634bd3d",
    ),
    ROOT / "construction_map_v31.py": (
        143,
        "c02ad337f0258b05a720f2575a562b3e29c83a0ba6ac78bde54ca751be43bdbe",
    ),
    ROOT / "scripts/build_construction_map_v31.py": (
        1_607,
        "915fff767852b099fbff30f102cf1036c453e506120dcb4035e975e562b6341b",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV31Tests(unittest.TestCase):
    def test_exact_pins_closed_inventory_freeze_and_temporal_commit(self) -> None:
        self.assertFalse(map_v31.DEFINITION.is_symlink())
        self.assertFalse(map_v31.BUNDLE.is_symlink())
        self.assertEqual(
            {path.name for path in map_v31.BUNDLE.iterdir()},
            map_v31.BUNDLE_FILES,
        )
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(tree_digest(map_v31.BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(map_v31.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(map_v31.BUNDLE.stat().st_mode), 0o555)
        for path in map_v31.BUNDLE.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)

        staged_paths = (
            map_v31.DEFINITION,
            map_v31.BUNDLE,
            *map_v31.BUNDLE.iterdir(),
        )
        for path in staged_paths:
            metadata = path.stat()
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            self.assertLessEqual(max(birth, metadata.st_mtime), GENERATED_EPOCH)
        self.assertGreaterEqual(map_v31.DEFINITION.stat().st_ctime, GENERATED_EPOCH)
        self.assertGreaterEqual(map_v31.BUNDLE.stat().st_ctime, GENERATED_EPOCH)

    def test_definition_is_exact_v30_successor_and_binds_accepted_master(self) -> None:
        predecessor = json.loads(map_v31.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v31.DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v31.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v31.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)
        self.assertEqual(
            map_v31.DEFINITION.read_bytes(), map_v31._canonical_json(current)
        )
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(current["template"], predecessor["template"])
        self.assertEqual(current["master"]["master_id"], map_v31.MASTER_ID)
        self.assertEqual(
            current["master"]["definition"]["sha256"],
            map_v31.MASTER_DEFINITION_SHA256,
        )
        self.assertEqual(
            current["master"]["jsonl"]["sha256"],
            map_v31.MASTER_JSONL_SHA256,
        )
        self.assertEqual(
            current["master"]["manifest"]["sha256"],
            map_v31.MASTER_MANIFEST_SHA256,
        )

    def test_full_validator_replays_twice_and_preserves_conservative_scope(
        self,
    ) -> None:
        manifest = map_v31.validate_construction_map_v31(
            validation_wall_clock=datetime.now(timezone.utc)
        )
        self.assertEqual(manifest["map_id"], map_v31.MAP_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["master"]["rows"], 109_381)
        self.assertIsNone(manifest["scope"]["unique_physical_site_count"])
        self.assertFalse(manifest["scope"]["entity_merges_created"])
        self.assertFalse(manifest["scope"]["global_completeness_claimed"])
        self.assertTrue(
            manifest["scope"]["historical_status_is_not_current_status_claim"]
        )
        payload = map_v31.DEFINITION.read_bytes() + b"".join(
            path.read_bytes() for path in sorted(map_v31.BUNDLE.iterdir())
        )
        for token in map_v31.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, payload)

    def test_future_republication_code_pins_shim_and_residue(self) -> None:
        before = {
            "definition": checkpoint(map_v31.DEFINITION),
            "tree": tree_digest(map_v31.BUNDLE),
        }
        with self.assertRaisesRegex(
            map_v31.ConstructionMapV31Error, "generated_at exceeds wall clock"
        ):
            map_v31._validate_temporal_closure(
                map_v31.DEFINITION,
                map_v31.BUNDLE,
                map_v31.MASTER_DEFINITION,
                map_v31.MASTER,
                validation_wall_clock=(
                    datetime.fromtimestamp(GENERATED_EPOCH, timezone.utc)
                    - timedelta(microseconds=1)
                ),
            )
        with self.assertRaisesRegex(
            map_v31.ConstructionMapV31Error, "refusing replacement"
        ):
            map_v31.publish_construction_map_v31("2026-07-22T00:25:00Z")
        self.assertEqual(
            {
                "definition": checkpoint(map_v31.DEFINITION),
                "tree": tree_digest(map_v31.BUNDLE),
            },
            before,
        )
        self.assertIs(
            shim.publish_construction_map_v31,
            map_v31.publish_construction_map_v31,
        )
        for path, expected in CODE_PINS.items():
            self.assertEqual(checkpoint(path), expected)
        self.assertFalse(map_v31.PUBLICATION_LOCK.exists())
        self.assertFalse(
            list(map_v31.DEFINITION.parent.glob(f".{map_v31.DEFINITION.name}.stage-*"))
        )
        self.assertFalse(
            list(map_v31.BUNDLE.parent.glob(f".{map_v31.BUNDLE.name}.stage-*"))
        )


if __name__ == "__main__":
    unittest.main()
