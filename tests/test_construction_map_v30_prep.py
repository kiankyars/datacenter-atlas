from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v30 as map_v30
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v30 as map_v30


GENERATED_AT = "2026-07-21T18:11:00Z"


class ConstructionMapV30PrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection, cls.projected, cls.all_ids = map_v30._projection_from_master(
            map_v30.MASTER, map_v30.MASTER_DEFINITION
        )

    def test_accepted_master_and_predecessor_are_exact(self) -> None:
        self.assertEqual(
            map_v30._require_accepted_master(),
            {
                "definition": map_v30.MASTER_DEFINITION_SHA256,
                "jsonl": map_v30.MASTER_JSONL_SHA256,
                "manifest": map_v30.MASTER_MANIFEST_SHA256,
                "tree": map_v30.MASTER_TREE_SHA256,
            },
        )
        map_v30._require_predecessor()
        self.assertEqual(map_v30.DEFINITION.exists(), map_v30.BUNDLE.exists())
        self.assertEqual(
            map_v30.DEFINITION.is_symlink(), map_v30.BUNDLE.is_symlink()
        )

    def test_projection_and_exact_v29_delta_are_recomputed(self) -> None:
        self.assertEqual(self.projection, map_v30.EXPECTED_PROJECTION)
        map_v30._assert_exact_v29_delta(self.projected, self.all_ids)
        predecessor = map_v30._map_rows(
            map_v30.PREDECESSOR_BUNDLE / map_v30.INDEX_FILENAME
        )
        self.assertEqual(
            set(self.projected) - set(predecessor),
            map_v30.NEW_COORDINATE_MAPPING_IDS,
        )
        self.assertEqual(
            (set(self.all_ids) - map_v30._master_record_ids(
                map_v30.ROOT
                / "construction_master/2026-07-21-public-open-v29/"
                "construction-master.jsonl"
            )),
            map_v30.NEW_MASTER_RECORD_IDS,
        )
        self.assertEqual(
            map_v30.NEW_MASTER_RECORD_IDS & set(self.projected),
            map_v30.NEWLY_ADDED_MAPPED_IDS,
        )

    def test_direct_v83_coordinates_and_lineage_rewrite_are_exact(self) -> None:
        for record_id, coordinates in map_v30.EXPECTED_NEW_COORDINATES.items():
            row = self.projected[record_id]
            self.assertEqual((row["longitude"], row["latitude"]), coordinates)
            self.assertEqual(
                row["source_artifact_id"], "epoch-official-open-seed-v83"
            )
            self.assertEqual(
                row["source_release_id"], "epoch-official-open-seed-v83"
            )
        predecessor = map_v30._map_rows(
            map_v30.PREDECESSOR_BUNDLE / map_v30.INDEX_FILENAME
        )
        rewritten = {
            record_id
            for record_id, row in predecessor.items()
            if row["source_artifact_id"] == "epoch-official-open-seed-v73"
        }
        self.assertEqual(len(rewritten), 105)
        self.assertEqual(
            map_v30._id_set_digest(rewritten),
            map_v30.REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256,
        )

    def test_definition_is_only_the_v29_successor(self) -> None:
        predecessor = json.loads(map_v30.PREDECESSOR_DEFINITION.read_bytes())
        current = map_v30.definition_document(GENERATED_AT)
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v30.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v30.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(current["template"], predecessor["template"])
        self.assertIsNone(current["scope"]["unique_physical_site_count"])
        self.assertTrue(
            current["scope"]["historical_status_is_not_current_status_claim"]
        )
        self.assertTrue(current["scope"]["map_rows_are_observations_not_unique_sites"])
        self.assertFalse(current["scope"]["global_completeness_claimed"])

    def test_collision_symlink_future_and_reserved_path_guards(self) -> None:
        with tempfile.TemporaryDirectory(prefix="map-v30-guards-") as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            bundle = root / "bundle"
            definition.write_text("occupied", encoding="utf-8")
            with (
                patch.object(map_v30, "DEFINITION", definition),
                patch.object(map_v30, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v30.ConstructionMapV30Error, "refusing replacement"
                ),
            ):
                map_v30._require_unpublished()

            definition.unlink()
            definition.symlink_to(root / "missing")
            with (
                patch.object(map_v30, "DEFINITION", definition),
                patch.object(map_v30, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v30.ConstructionMapV30Error, "refusing replacement"
                ),
            ):
                map_v30._require_unpublished()

            regular = root / "regular"
            regular.write_bytes(b"x")
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
            with self.assertRaisesRegex(
                map_v30.ConstructionMapV30Error, "post-dates"
            ):
                map_v30._path_timestamp_bounds(regular, cutoff, "test artifact")

            stage = root / "stage"
            stage.mkdir()
            (stage / "bad").symlink_to(root / "missing")
            with self.assertRaisesRegex(
                map_v30.ConstructionMapV30Error, "contaminated"
            ):
                map_v30._discard_bundle_stage(stage)

        with self.assertRaisesRegex(
            map_v30.ConstructionMapV30Error,
            "paths and frozen mode are reserved",
        ):
            map_v30.write_construction_map_v30(
                output_directory=Path("elsewhere"),
                generated_at=GENERATED_AT,
            )


if __name__ == "__main__":
    unittest.main()
