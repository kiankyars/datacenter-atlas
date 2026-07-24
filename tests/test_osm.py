from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.osm import (
    OpenStreetMapAdapter,
    extract_center,
    extract_geometry,
    infer_lifecycle,
    is_explicit_data_center,
)
from datacenter_atlas.models import LifecycleStatus
from datacenter_atlas.service import export_geojson, summarize, validate_database


FIXTURE = Path(__file__).parent / "fixtures" / "osm_minimal.json"
RETRIEVED_AT = "2026-07-17T19:00:00Z"


class OSMImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(Path(self.temporary_directory.name) / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_name_alone_is_not_a_data_center_signal(self) -> None:
        self.assertFalse(is_explicit_data_center({"name": "Big Data Center", "amenity": "cafe"}))
        self.assertTrue(is_explicit_data_center({"man_made": "data_center"}))

    def test_lifecycle_inference_is_conservative(self) -> None:
        self.assertEqual(
            infer_lifecycle({"building": "data_center"})[0], LifecycleStatus.UNKNOWN
        )
        self.assertEqual(
            infer_lifecycle({"building": "construction", "construction": "data_center"})[0],
            LifecycleStatus.UNDER_CONSTRUCTION,
        )
        self.assertEqual(
            infer_lifecycle({"site": "data_center", "proposed": "data_center"})[0],
            LifecycleStatus.PROPOSED,
        )

    def test_node_way_relation_geometry_and_center(self) -> None:
        elements = json.loads(FIXTURE.read_text())["elements"]
        node_geometry = extract_geometry(elements[0])
        way_geometry = extract_geometry(elements[1])
        relation_geometry = extract_geometry(elements[2])
        self.assertEqual(node_geometry["type"], "Point")
        self.assertEqual(way_geometry["type"], "Polygon")
        self.assertEqual(relation_geometry["type"], "Polygon")
        self.assertEqual(extract_center(elements[1], way_geometry), (32.4505, -99.7305))
        self.assertEqual(extract_center(elements[2], relation_geometry), (32.4555, -99.7255))

    def test_fixture_imports_all_explicit_elements(self) -> None:
        result = OpenStreetMapAdapter().import_file(
            self.connection, FIXTURE, retrieved_at=RETRIEVED_AT
        )
        self.assertEqual(result.examined_elements, 4)
        self.assertEqual(result.imported_elements, 3)
        self.assertEqual(result.skipped_elements, 1)
        self.assertEqual(result.entities_created, 6)
        self.assertEqual(result.evidence_created, 3)
        summary = summarize(
            self.connection,
            as_of="2026-07-17",
            recorded_at="2026-07-18T00:00:00Z",
        )
        self.assertEqual(
            summary["entities_by_kind"],
            {"building": 1, "campus": 1, "facility": 2, "project": 2},
        )
        self.assertEqual(
            summary["entities_by_status"],
            {"proposed": 2, "under_construction": 2, "unknown": 1},
        )

    def test_verified_input_provenance_is_retained_and_hash_bound(self) -> None:
        input_sha256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        OpenStreetMapAdapter().import_file(
            self.connection,
            FIXTURE,
            retrieved_at=RETRIEVED_AT,
            provenance={
                "input_sha256": input_sha256,
                "materialization_manifest_sha256": "a" * 64,
            },
        )
        rows = self.connection.execute(
            "SELECT metadata_json FROM evidence ORDER BY id"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            self.assertEqual(metadata["input_sha256"], input_sha256)
            self.assertEqual(metadata["provenance"]["input_sha256"], input_sha256)
            self.assertEqual(
                metadata["provenance"]["materialization_manifest_sha256"],
                "a" * 64,
            )

    def test_verified_input_provenance_rejects_wrong_input_hash(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            OpenStreetMapAdapter().import_file(
                self.connection,
                FIXTURE,
                retrieved_at=RETRIEVED_AT,
                provenance={"input_sha256": "0" * 64},
            )

    def test_import_records_odbl_url_attribution_and_separate_classifications(self) -> None:
        OpenStreetMapAdapter().import_file(self.connection, FIXTURE, retrieved_at=RETRIEVED_AT)
        rows = self.connection.execute(
            "SELECT source_url, license, attribution, retrieved_at FROM evidence ORDER BY source_url"
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["source_url"].startswith("https://www.openstreetmap.org/") for row in rows))
        self.assertTrue(all(row["license"] == "ODbL-1.0" for row in rows))
        self.assertTrue(all(row["attribution"] == "© OpenStreetMap contributors" for row in rows))
        self.assertTrue(all(row["retrieved_at"] == RETRIEVED_AT for row in rows))
        self.assertEqual(
            self.connection.execute("SELECT operating_model FROM operating_model_observations").fetchone()[0],
            "colocation",
        )
        workloads = {
            row[0] for row in self.connection.execute("SELECT workload FROM workload_observations")
        }
        self.assertEqual(workloads, {"general_cloud", "enterprise_it"})

    def test_import_is_idempotent_for_same_retrieval(self) -> None:
        adapter = OpenStreetMapAdapter()
        first = adapter.import_file(self.connection, FIXTURE, retrieved_at=RETRIEVED_AT)
        second = adapter.import_file(self.connection, FIXTURE, retrieved_at=RETRIEVED_AT)
        self.assertEqual(first.entities_created, 6)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 6)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3)

    def test_later_retrieval_supersedes_transaction_time_without_overlap(self) -> None:
        adapter = OpenStreetMapAdapter()
        adapter.import_file(self.connection, FIXTURE, retrieved_at=RETRIEVED_AT)
        adapter.import_file(
            self.connection, FIXTURE, retrieved_at="2026-07-18T19:00:00Z"
        )
        self.assertEqual(validate_database(self.connection), [])
        open_snapshots = self.connection.execute(
            "SELECT COUNT(*) FROM entity_snapshots WHERE superseded_at IS NULL"
        ).fetchone()[0]
        self.assertEqual(open_snapshots, 6)

    def test_geojson_retains_osm_attribution_and_geometry(self) -> None:
        OpenStreetMapAdapter().import_file(self.connection, FIXTURE, retrieved_at=RETRIEVED_AT)
        document = export_geojson(
            self.connection,
            as_of="2026-07-17",
            recorded_at="2026-07-18T00:00:00Z",
        )
        self.assertEqual(document["type"], "FeatureCollection")
        self.assertEqual(document["attribution"], ["© OpenStreetMap contributors"])
        self.assertEqual(len(document["features"]), 6)
        self.assertTrue(all(feature["geometry"] is not None for feature in document["features"]))
        self.assertTrue(
            all(
                feature["properties"]["latitude"] is not None
                and feature["properties"]["longitude"] is not None
                for feature in document["features"]
            )
        )
        self.assertTrue(
            all(
                feature["properties"]["source_license"] == "ODbL-1.0"
                for feature in document["features"]
            )
        )


if __name__ == "__main__":
    unittest.main()
