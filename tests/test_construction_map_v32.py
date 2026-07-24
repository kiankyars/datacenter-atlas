from __future__ import annotations

import gzip
import hashlib
import json
import stat
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

try:
    from datacenter_atlas import construction_map_v32 as shim
    from datacenter_atlas.datacenter_atlas import construction_map_v32 as map_v32
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    import construction_map_v32 as shim
    from datacenter_atlas import construction_map_v32 as map_v32
    from datacenter_atlas.open_seed_v56 import tree_digest


DEFINITION_PIN = (
    2_509,
    "50248a1fafc5ce96693592b990be6fc9352233091e4c4210817db5d6936cef3f",
)
BUNDLE_TREE_PIN = "78d444c9b289ccc23acdbc7a7a2ff5fbedf0df16ece8100da328cb7fde05572e"
BUNDLE_PINS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "24b0e3143fc9f9a130869c7b546e34ed369228e7772f69669835ac9368cbb96d",
    ),
    "construction-map-index.json.gz": (
        6_683_675,
        "b52ece43b13e7d626115f3f8b3f1393e5e82d4e4821e09b4a383ee96d03f6712",
    ),
    "construction-map.html": (
        8_929_176,
        "c8a1119dc545168612f89ffd048451c6c0b56917744d6e84890e4961cb26acc3",
    ),
    "coverage.json": (
        7_524,
        "98e7b1c7841c2480d69f87fe63416247703b3e28f3f4220f1b0899227198967b",
    ),
    "manifest.json": (
        2_172,
        "8b321d67ef80a6af0fbc0d39d60b5a10387777a1ab97d3a1a0f45a5b9bfa952d",
    ),
    "manifest.sha256": (
        80,
        "765a7137eb4f4c78a33f31c929e527719ee26e55c1519283acd44c553d810d80",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV32Tests(unittest.TestCase):
    def test_exact_structured_projection(self) -> None:
        projection = map_v32.derive_candidate_projection(
            map_v32.CANDIDATE_MASTER,
            map_v32.CANDIDATE_MASTER_DEFINITION,
        )
        self.assertEqual(projection, map_v32.EXPECTED_PROJECTION)

    def test_private_candidate_definition_pins_and_static_validation(self) -> None:
        with map_v32._runtime_timestamps(
            map_v32.MAP_GENERATED_AT,
            map_v32.CANDIDATE_MASTER_GENERATED_AT,
        ):
            manifest = map_v32._core_validate_static(
                map_v32.CANDIDATE_BUNDLE_STAGE,
                frozen=True,
            )
        self.assertEqual(checkpoint(map_v32.CANDIDATE_DEFINITION_STAGE), DEFINITION_PIN)
        self.assertEqual(
            {
                path.name: checkpoint(path)
                for path in map_v32.CANDIDATE_BUNDLE_STAGE.iterdir()
            },
            BUNDLE_PINS,
        )
        self.assertEqual(tree_digest(map_v32.CANDIDATE_BUNDLE_STAGE), BUNDLE_TREE_PIN)
        self.assertEqual(manifest["master"]["rows"], 109_443)
        coverage = json.loads(
            (map_v32.CANDIDATE_BUNDLE_STAGE / "coverage.json").read_bytes()
        )
        self.assertEqual(coverage["projection"], map_v32.EXPECTED_PROJECTION)
        self.assertEqual(
            stat.S_IMODE(map_v32.CANDIDATE_DEFINITION_STAGE.stat().st_mode),
            0o444,
        )
        self.assertEqual(
            stat.S_IMODE(map_v32.CANDIDATE_BUNDLE_STAGE.stat().st_mode),
            0o555,
        )

        predecessor = json.loads(map_v32.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v32.CANDIDATE_DEFINITION_STAGE.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v32.MAP_ID
        expected["generated_at"] = map_v32.MAP_GENERATED_AT
        expected["expected_projection"] = map_v32.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)

    def test_four_bare_collisions_are_distinct_rows_and_not_map_collapses(
        self,
    ) -> None:
        bare_counts: Counter[str] = Counter()
        row_ids: set[str] = set()
        source_identities: set[tuple[str, str]] = set()
        collision_rows: dict[str, list[dict[str, object]]] = {
            record_id: []
            for record_id in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
        }
        master_path = map_v32.CANDIDATE_MASTER / "construction-master.jsonl"
        with master_path.open("rb") as source:
            for raw in source:
                row = json.loads(raw)
                artifact_id = row["source"]["artifact_id"]
                record_id = row["source"]["record_id"]
                row_id = row["row_id"]
                self.assertNotIn(row_id, row_ids)
                self.assertNotIn((artifact_id, record_id), source_identities)
                row_ids.add(row_id)
                source_identities.add((artifact_id, record_id))
                bare_counts[record_id] += 1
                if record_id in collision_rows:
                    collision_rows[record_id].append(row)
        self.assertEqual(len(row_ids), 109_443)
        self.assertEqual(len(source_identities), 109_443)
        self.assertEqual(len(bare_counts), 109_439)
        self.assertEqual(
            {record_id for record_id, count in bare_counts.items() if count > 1},
            map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS,
        )
        for rows in collision_rows.values():
            self.assertEqual(len(rows), 2)
            by_artifact = {row["source"]["artifact_id"]: row for row in rows}
            self.assertEqual(
                set(by_artifact),
                {"epoch-official-open-seed-v97", "global-open-v3"},
            )
            self.assertIsNone(
                by_artifact["epoch-official-open-seed-v97"]["entity"]["latitude"]
            )
            self.assertIsNotNone(by_artifact["global-open-v3"]["entity"]["latitude"])

        index = json.loads(
            gzip.decompress(
                (map_v32.CANDIDATE_BUNDLE_STAGE / map_v32.INDEX_FILENAME).read_bytes()
            )
        )
        rows = [
            dict(zip(index["fields"], values, strict=True)) for values in index["rows"]
        ]
        mapped_collisions = {
            row["source_record_id"]: row["source_artifact_id"]
            for row in rows
            if row["source_record_id"] in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
        }
        self.assertEqual(
            mapped_collisions,
            {
                record_id: "global-open-v3"
                for record_id in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
            },
        )
        northc = next(
            row
            for row in rows
            if row["source_record_id"] == "ab9bf6d5-73d7-5d84-9b66-b80d2da64866"
        )
        self.assertEqual(
            (northc["longitude"], northc["latitude"]),
            (4.77335841, 52.25979593),
        )
        self.assertEqual(northc["source_artifact_id"], "epoch-official-open-seed-v97")

    def test_shim_and_final_paths_remain_unpublished(self) -> None:
        self.assertIs(
            shim.publish_construction_map_v32,
            map_v32.publish_construction_map_v32,
        )
        self.assertFalse(map_v32.PUBLICATION_LOCK.exists())
        self.assertFalse(map_v32.DEFINITION.exists())
        self.assertFalse(map_v32.BUNDLE.exists())

    def test_public_defaults_bind_dated_v32_paths(self) -> None:
        definition_defaults = map_v32.definition_document.__kwdefaults__
        validation_defaults = map_v32.validate_construction_map_v32.__kwdefaults__
        write_defaults = map_v32.write_construction_map_v32.__kwdefaults__
        self.assertIsNotNone(definition_defaults)
        self.assertIsNotNone(validation_defaults)
        self.assertIsNotNone(write_defaults)
        self.assertEqual(definition_defaults["master_directory"], map_v32.MASTER)
        self.assertEqual(
            definition_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(
            map_v32.validate_construction_map_v32.__defaults__,
            (map_v32.BUNDLE,),
        )
        self.assertEqual(validation_defaults["master_directory"], map_v32.MASTER)
        self.assertEqual(
            validation_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(validation_defaults["map_definition_path"], map_v32.DEFINITION)
        self.assertEqual(
            map_v32.write_construction_map_v32.__defaults__,
            (map_v32.MASTER, map_v32.BUNDLE),
        )
        self.assertEqual(
            write_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(write_defaults["map_definition_path"], map_v32.DEFINITION)
        self.assertIs(
            map_v32.build_construction_map_v32,
            map_v32.write_construction_map_v32,
        )


if __name__ == "__main__":
    unittest.main()
