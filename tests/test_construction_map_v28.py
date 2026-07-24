from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v12 as map_v12
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v12 as map_v12
    from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-07-21T11:02:30Z"
GENERATED_EPOCH = datetime.fromisoformat(
    GENERATED_AT.replace("Z", "+00:00")
).timestamp()

FILE_PINS = {
    map_v12.DEFINITION: (
        2442,
        "52aa5b4443f60efb6ff2b983566bc194f707345e5eeaca613512c1791b6bbd85",
    ),
    map_v12.BUNDLE / "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    map_v12.BUNDLE / "README.md": (
        518,
        "e20e1ea9cceeeed3cea09b4fb33558c21c5fdacf9b5be305eef27ff9f97a1ae0",
    ),
    map_v12.BUNDLE / map_v12.INDEX_FILENAME: (
        6_680_645,
        "17a6fe1c50546c5c1e08c0afcde78cb1c1490bae499d66fe427d345e0e45dde5",
    ),
    map_v12.BUNDLE / "construction-map.html": (
        8_925_136,
        "d273dacec927596224ed53a83bfeae837d02775877893ec25e9fb22ff64c0f0e",
    ),
    map_v12.BUNDLE / "coverage.json": (
        7_465,
        "2c46219d54acf600b902b9650d5fb2077bdcd75cf5ceff1385c67a88d9282ac4",
    ),
    map_v12.BUNDLE / map_v12.MANIFEST_FILENAME: (
        2_192,
        "199d2c73cd73871ebe183d10531e44c1c8a0f4387973730523d9c78e65f70e6f",
    ),
    map_v12.BUNDLE / "manifest.sha256": (
        80,
        "0c1d4dc8cfea28ffab46f45c6c914c48f619c4c6ba6c9390392170f2c4fb5448",
    ),
}
BUNDLE_TREE_SHA256 = (
    "57b705610c92e7414666ceff0051b973417a587037730a2e687a3809d3bbab9a"
)


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV28Tests(unittest.TestCase):
    def test_exact_pins_closed_inventory_freeze_and_temporal_commit(self) -> None:
        self.assertFalse(map_v12.DEFINITION.is_symlink())
        self.assertFalse(map_v12.BUNDLE.is_symlink())
        self.assertEqual(
            {path.name for path in map_v12.BUNDLE.iterdir()}, map_v12.BUNDLE_FILES
        )
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(tree_digest(map_v12.BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(map_v12.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(map_v12.BUNDLE.stat().st_mode), 0o555)
        for path in map_v12.BUNDLE.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)

        staged_paths = (
            map_v12.DEFINITION,
            map_v12.BUNDLE,
            *map_v12.BUNDLE.iterdir(),
        )
        for path in staged_paths:
            metadata = path.stat()
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            self.assertLessEqual(max(birth, metadata.st_mtime), GENERATED_EPOCH)
        self.assertGreaterEqual(map_v12.DEFINITION.stat().st_ctime, GENERATED_EPOCH)
        self.assertGreaterEqual(map_v12.BUNDLE.stat().st_ctime, GENERATED_EPOCH)

    def test_definition_is_exact_v27_successor_and_binds_accepted_master(self) -> None:
        predecessor = json.loads(map_v12.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v12.DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v12.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v12.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)
        self.assertEqual(map_v12.DEFINITION.read_bytes(), map_v12._canonical_json(current))
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(current["template"], predecessor["template"])
        self.assertEqual(current["master"]["master_id"], map_v12.MASTER_ID)
        self.assertEqual(
            current["master"]["definition"]["sha256"],
            map_v12.MASTER_DEFINITION_SHA256,
        )
        self.assertEqual(
            current["master"]["jsonl"]["sha256"], map_v12.MASTER_JSONL_SHA256
        )
        self.assertEqual(
            current["master"]["manifest"]["sha256"],
            map_v12.MASTER_MANIFEST_SHA256,
        )

    def test_full_validator_replays_twice_and_preserves_conservative_scope(self) -> None:
        manifest = map_v12.validate_construction_map_v12(
            validation_wall_clock=datetime.now(timezone.utc)
        )
        self.assertEqual(manifest["map_id"], map_v12.MAP_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["master"]["rows"], 109_328)
        self.assertIsNone(manifest["scope"]["unique_physical_site_count"])
        self.assertFalse(manifest["scope"]["entity_merges_created"])
        self.assertFalse(manifest["scope"]["global_completeness_claimed"])
        payload = map_v12.DEFINITION.read_bytes() + b"".join(
            path.read_bytes() for path in sorted(map_v12.BUNDLE.iterdir())
        )
        for token in map_v12.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, payload)

    def test_future_wall_and_republication_are_rejected_without_mutation(self) -> None:
        before = {
            "definition": checkpoint(map_v12.DEFINITION),
            "tree": tree_digest(map_v12.BUNDLE),
        }
        with self.assertRaisesRegex(
            map_v12.ConstructionMapV12Error, "generated_at exceeds wall clock"
        ):
            map_v12._validate_temporal_closure(
                map_v12.DEFINITION,
                map_v12.BUNDLE,
                map_v12.MASTER_DEFINITION,
                map_v12.MASTER,
                validation_wall_clock=(
                    datetime.fromtimestamp(GENERATED_EPOCH, timezone.utc)
                    - timedelta(microseconds=1)
                ),
            )
        with self.assertRaisesRegex(
            map_v12.ConstructionMapV12Error, "refusing replacement"
        ):
            map_v12.publish_construction_map_v12("2026-07-21T11:10:00Z")
        self.assertEqual(
            {
                "definition": checkpoint(map_v12.DEFINITION),
                "tree": tree_digest(map_v12.BUNDLE),
            },
            before,
        )


if __name__ == "__main__":
    unittest.main()
