from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v31 as map_v31
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v31 as map_v31


GENERATED_AT = "2026-07-22T00:20:00Z"


class ConstructionMapV31PrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection, cls.projected, cls.all_ids = map_v31._projection_from_master(
            map_v31.MASTER, map_v31.MASTER_DEFINITION
        )

    def test_accepted_master_and_predecessor_are_exact(self) -> None:
        self.assertEqual(
            map_v31._require_accepted_master(),
            {
                "definition": map_v31.MASTER_DEFINITION_SHA256,
                "jsonl": map_v31.MASTER_JSONL_SHA256,
                "manifest": map_v31.MASTER_MANIFEST_SHA256,
                "tree": map_v31.MASTER_TREE_SHA256,
            },
        )
        map_v31._require_predecessor()
        self.assertEqual(map_v31.DEFINITION.exists(), map_v31.BUNDLE.exists())
        self.assertEqual(
            map_v31.DEFINITION.is_symlink(), map_v31.BUNDLE.is_symlink()
        )

    def test_projection_and_exact_v30_delta_are_recomputed(self) -> None:
        self.assertEqual(self.projection, map_v31.EXPECTED_PROJECTION)
        map_v31._assert_exact_v30_delta(self.projected, self.all_ids)
        predecessor = map_v31._map_rows(
            map_v31.PREDECESSOR_BUNDLE / map_v31.INDEX_FILENAME
        )
        self.assertEqual(
            set(self.projected) - set(predecessor),
            map_v31.NEW_COORDINATE_MAPPING_IDS,
        )
        old_master_ids = map_v31._master_record_ids(
            map_v31.ROOT
            / "construction_master/2026-07-21-public-open-v30/"
            "construction-master.jsonl"
        )
        self.assertEqual(
            self.all_ids - old_master_ids,
            map_v31.NEW_MASTER_RECORD_IDS,
        )
        self.assertFalse(map_v31.NEW_MASTER_RECORD_IDS & set(self.projected))
        self.assertTrue(map_v31.NEW_COORDINATE_MAPPING_IDS.issubset(old_master_ids))

    def test_direct_v86_coordinates_and_lineage_rewrite_are_exact(self) -> None:
        for record_id, coordinates in map_v31.EXPECTED_NEW_COORDINATES.items():
            row = self.projected[record_id]
            self.assertEqual((row["longitude"], row["latitude"]), coordinates)
            self.assertEqual(
                row["source_artifact_id"], "epoch-official-open-seed-v86"
            )
            self.assertEqual(
                row["source_release_id"], "epoch-official-open-seed-v86"
            )
        predecessor = map_v31._map_rows(
            map_v31.PREDECESSOR_BUNDLE / map_v31.INDEX_FILENAME
        )
        rewritten = {
            record_id
            for record_id, row in predecessor.items()
            if row["source_artifact_id"] == "epoch-official-open-seed-v83"
        }
        self.assertEqual(len(rewritten), 109)
        self.assertEqual(
            map_v31._id_set_digest(rewritten),
            map_v31.REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256,
        )

    def test_definition_is_only_the_v30_successor(self) -> None:
        predecessor = json.loads(map_v31.PREDECESSOR_DEFINITION.read_bytes())
        current = map_v31.definition_document(GENERATED_AT)
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v31.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v31.EXPECTED_PROJECTION
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
        raw = map_v31._canonical_json(current)
        for token in map_v31.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, raw)

    def test_collision_symlink_future_and_reserved_path_guards(self) -> None:
        with tempfile.TemporaryDirectory(prefix="map-v31-guards-") as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            bundle = root / "bundle"
            definition.write_text("occupied", encoding="utf-8")
            with (
                patch.object(map_v31, "DEFINITION", definition),
                patch.object(map_v31, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v31.ConstructionMapV31Error, "refusing replacement"
                ),
            ):
                map_v31._require_unpublished()

            definition.unlink()
            definition.symlink_to(root / "missing")
            with (
                patch.object(map_v31, "DEFINITION", definition),
                patch.object(map_v31, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v31.ConstructionMapV31Error, "refusing replacement"
                ),
            ):
                map_v31._require_unpublished()

            regular = root / "regular"
            regular.write_bytes(b"x")
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
            with self.assertRaisesRegex(
                map_v31.ConstructionMapV31Error, "post-dates"
            ):
                map_v31._path_timestamp_bounds(regular, cutoff, "test artifact")

            stage = root / "stage"
            stage.mkdir()
            (stage / "bad").symlink_to(root / "missing")
            with self.assertRaisesRegex(
                map_v31.ConstructionMapV31Error, "contaminated"
            ):
                map_v31._discard_bundle_stage(stage)

        with self.assertRaisesRegex(
            map_v31.ConstructionMapV31Error,
            "paths and frozen mode are reserved",
        ):
            map_v31.write_construction_map_v31(
                output_directory=Path("elsewhere"),
                generated_at=GENERATED_AT,
            )


if __name__ == "__main__":
    unittest.main()
