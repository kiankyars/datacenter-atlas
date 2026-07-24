from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v29 as map_v29
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v29 as map_v29


GENERATED_AT = "2026-07-21T13:47:30Z"


class ConstructionMapV29PrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection, cls.projected, cls.all_ids = map_v29._projection_from_master(
            map_v29.MASTER, map_v29.MASTER_DEFINITION
        )

    def test_accepted_master_and_predecessor_are_exact(self) -> None:
        self.assertEqual(
            map_v29._require_accepted_master(),
            {
                "definition": map_v29.MASTER_DEFINITION_SHA256,
                "jsonl": map_v29.MASTER_JSONL_SHA256,
                "manifest": map_v29.MASTER_MANIFEST_SHA256,
                "tree": map_v29.MASTER_TREE_SHA256,
            },
        )
        map_v29._require_predecessor()
        self.assertEqual(map_v29.DEFINITION.exists(), map_v29.BUNDLE.exists())
        self.assertEqual(
            map_v29.DEFINITION.is_symlink(), map_v29.BUNDLE.is_symlink()
        )

    def test_projection_and_exact_v28_delta_are_recomputed(self) -> None:
        self.assertEqual(self.projection, map_v29.EXPECTED_PROJECTION)
        map_v29._assert_exact_v28_delta(self.projected, self.all_ids)
        self.assertEqual(
            set(self.projected) - set(
                map_v29._map_rows(
                    map_v29.PREDECESSOR_BUNDLE / map_v29.INDEX_FILENAME
                )
            ),
            map_v29.NEW_COORDINATE_MAPPING_IDS,
        )
        self.assertTrue(map_v29.NEW_MASTER_RECORD_IDS.isdisjoint(self.projected))

    def test_definition_is_only_the_v28_successor(self) -> None:
        predecessor = json.loads(map_v29.PREDECESSOR_DEFINITION.read_bytes())
        current = map_v29.definition_document(GENERATED_AT)
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v29.MAP_ID
        expected["generated_at"] = GENERATED_AT
        expected["expected_projection"] = map_v29.EXPECTED_PROJECTION
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
        with tempfile.TemporaryDirectory(prefix="map-v29-guards-") as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            bundle = root / "bundle"
            definition.write_text("occupied", encoding="utf-8")
            with (
                patch.object(map_v29, "DEFINITION", definition),
                patch.object(map_v29, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v29.ConstructionMapV29Error, "refusing replacement"
                ),
            ):
                map_v29._require_unpublished()

            definition.unlink()
            definition.symlink_to(root / "missing")
            with (
                patch.object(map_v29, "DEFINITION", definition),
                patch.object(map_v29, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v29.ConstructionMapV29Error, "refusing replacement"
                ),
            ):
                map_v29._require_unpublished()

            regular = root / "regular"
            regular.write_bytes(b"x")
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
            with self.assertRaisesRegex(
                map_v29.ConstructionMapV29Error, "post-dates"
            ):
                map_v29._path_timestamp_bounds(regular, cutoff, "test artifact")

            stage = root / "stage"
            stage.mkdir()
            (stage / "bad").symlink_to(root / "missing")
            with self.assertRaisesRegex(
                map_v29.ConstructionMapV29Error, "contaminated"
            ):
                map_v29._discard_bundle_stage(stage)

        with self.assertRaisesRegex(
            map_v29.ConstructionMapV29Error,
            "paths and frozen mode are reserved",
        ):
            map_v29.write_construction_map_v29(
                output_directory=Path("elsewhere"),
                generated_at=GENERATED_AT,
            )


if __name__ == "__main__":
    unittest.main()
