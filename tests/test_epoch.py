from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import datacenter_atlas.epoch as epoch_module
from datacenter_atlas.database import connect, initialize
from datacenter_atlas.epoch import (
    CAPACITY_INTERVAL_FACTOR,
    EpochAIAdapter,
    parse_epoch_map_html,
)
from datacenter_atlas.service import validate_database


FIXTURES = Path(__file__).parent / "fixtures"
EPOCH_FIXTURE = FIXTURES / "epoch"
MAP_FIXTURE = FIXTURES / "epoch_map.html"
RETRIEVED_AT = "2026-07-17T20:00:00Z"
AS_OF_DATE = "2026-07-17"


class EpochImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary_directory.name)
        self.connection, _ = initialize(self.temp_path / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def import_fixture(self, *, map_html: Path | None = MAP_FIXTURE):
        return EpochAIAdapter().import_file(
            self.connection,
            EPOCH_FIXTURE,
            retrieved_at=RETRIEVED_AT,
            as_of_date=AS_OF_DATE,
            map_html=map_html,
        )

    def test_saved_astro_map_recovers_only_coordinates_and_bounds(self) -> None:
        locations = parse_epoch_map_html(MAP_FIXTURE)
        self.assertEqual(len(locations), 3)
        expansion = locations["expansion campus"]
        self.assertEqual((expansion.longitude, expansion.latitude), (-97.1, 32.1))
        self.assertEqual(expansion.bounds, (-97.2, 32.0, -97.0, 32.2))

    def test_import_creates_one_attributed_campus_per_epoch_record(self) -> None:
        result = self.import_fixture()
        self.assertEqual(result.examined_elements, 3)
        self.assertEqual(result.imported_elements, 3)
        self.assertEqual(result.skipped_elements, 0)
        self.assertEqual(result.entities_created, 3)
        self.assertEqual(result.evidence_created, 3)

        entity_count = self.connection.execute(
            "SELECT kind, COUNT(*) FROM entities GROUP BY kind"
        ).fetchall()[0]
        self.assertEqual(tuple(entity_count), ("campus", 3))
        evidence_rows = self.connection.execute(
            """
            SELECT kind, source_url, publisher, source_family, license, attribution,
                   content_hash, metadata_json
            FROM evidence
            ORDER BY title
            """
        ).fetchall()
        self.assertEqual(len(evidence_rows), 3)
        for row in evidence_rows:
            self.assertEqual(row["kind"], "third_party_dataset")
            self.assertEqual(row["source_url"], "https://epoch.ai/data/ai-data-centers")
            self.assertEqual(row["publisher"], "Epoch AI")
            self.assertEqual(row["source_family"], "epoch_ai_data_centers")
            self.assertEqual(row["license"], "CC-BY-4.0")
            self.assertIn("Epoch AI", row["attribution"])
            self.assertEqual(len(row["content_hash"]), 64)
            metadata = json.loads(row["metadata_json"])
            self.assertTrue(metadata["source_record_id"])
            self.assertEqual(len(metadata["provenance"]["data_centers_sha256"]), 64)
            self.assertIn("selected_sources", metadata["record"])

        tags = [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT tags_json FROM entity_snapshots ORDER BY name"
            )
        ]
        self.assertTrue(all(tag["source_record_id"] for tag in tags))
        self.assertEqual(
            {tag["country"] for tag in tags},
            {"Canada", "United Kingdom", "United States"},
        )
        self.assertEqual(validate_database(self.connection), [])

    def test_lifecycle_uses_current_power_and_only_future_growth(self) -> None:
        self.import_fixture()
        rows = self.connection.execute(
            """
            SELECT snapshots.name, lifecycle.status, lifecycle.confidence,
                   lifecycle.as_of_date
            FROM lifecycle_observations AS lifecycle
            JOIN entity_snapshots AS snapshots ON snapshots.entity_id = lifecycle.entity_id
            ORDER BY snapshots.name
            """
        ).fetchall()
        observed = {
            row["name"]: (row["status"], row["confidence"], row["as_of_date"])
            for row in rows
        }
        self.assertEqual(observed["Expansion Campus"], ("expansion", 0.70, AS_OF_DATE))
        self.assertEqual(observed["Operating Campus"], ("operational", 0.75, AS_OF_DATE))
        self.assertEqual(
            observed["Construction Campus"],
            ("under_construction", 0.55, AS_OF_DATE),
        )
        self.assertLess(
            observed["Construction Campus"][1], observed["Operating Campus"][1]
        )

    def test_capacities_use_latest_nonfuture_row_and_factor_interval(self) -> None:
        self.import_fixture()
        rows = self.connection.execute(
            """
            SELECT snapshots.name, capacity.metric, capacity.stage, capacity.low,
                   capacity.base, capacity.high, capacity.method, capacity.as_of_date,
                   capacity.notes
            FROM capacity_estimates AS capacity
            JOIN entity_snapshots AS snapshots ON snapshots.entity_id = capacity.entity_id
            ORDER BY snapshots.name, capacity.metric
            """
        ).fetchall()
        self.assertEqual(len(rows), 14)
        indexed = {(row["name"], row["metric"], row["stage"]): row for row in rows}

        critical = indexed[("Expansion Campus", "critical_it_mw", "operational")]
        self.assertEqual(critical["base"], 90)
        self.assertAlmostEqual(critical["low"], 90 / CAPACITY_INTERVAL_FACTOR)
        self.assertAlmostEqual(critical["high"], 90 * CAPACITY_INTERVAL_FACTOR)
        self.assertEqual(critical["stage"], "operational")
        self.assertEqual(critical["method"], "modeled")
        self.assertEqual(critical["as_of_date"], "2026-06-01")
        self.assertIn("80%", critical["notes"])

        gross = indexed[("Expansion Campus", "gross_facility_mw", "operational")]
        self.assertEqual(gross["base"], 120)
        self.assertEqual(gross["stage"], "operational")
        self.assertEqual(
            indexed[("Construction Campus", "critical_it_mw", "unknown")]["stage"],
            "unknown",
        )
        expansion_forecast = indexed[("Expansion Campus", "critical_it_mw", "forecast")]
        self.assertEqual(expansion_forecast["base"], 180)
        self.assertEqual(expansion_forecast["low"], 0)
        construction_forecast = indexed[
            ("Construction Campus", "gross_facility_mw", "forecast")
        ]
        self.assertEqual(construction_forecast["base"], 70)
        annual_current = indexed[
            ("Expansion Campus", "annual_energy_mwh", "operational")
        ]
        self.assertEqual(annual_current["base"], 120 * 0.8 * 8760)
        self.assertIn("not metered", annual_current["notes"].casefold())
        annual_forecast = indexed[
            ("Construction Campus", "annual_energy_mwh", "forecast")
        ]
        self.assertEqual(annual_forecast["base"], 70 * 0.8 * 8760)
        self.assertEqual(annual_forecast["low"], 0)

        expansion_evidence = self.connection.execute(
            "SELECT metadata_json FROM evidence WHERE title LIKE '%Expansion Campus'"
        ).fetchone()
        metadata = json.loads(expansion_evidence[0])
        self.assertEqual(metadata["selected_timeline"]["gross_facility_mw"], 120)
        self.assertEqual(metadata["future_timeline_rows"][0]["gross_facility_mw"], 240)
        self.assertNotIn("construction_status", metadata["future_timeline_rows"][0])
        self.assertEqual(metadata["capacity_interval"]["factor"], 1.4)
        self.assertEqual(metadata["capacity_interval"]["coverage"], 0.8)

    def test_epoch_scope_adds_only_conservative_unspecified_ai_workload(self) -> None:
        self.import_fixture()
        rows = self.connection.execute(
            "SELECT workload, method, confidence FROM workload_observations"
        ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            {row["workload"] for row in rows}, {"ai_specialized_unspecified"}
        )
        self.assertTrue(
            all("without_training_inference_subtype" in row["method"] for row in rows)
        )

    def test_map_imagery_equipment_and_access_details_are_not_persisted(self) -> None:
        self.import_fixture()
        persisted = "\n".join(
            str(value or "")
            for row in self.connection.execute(
                """
                SELECT snapshots.tags_json, snapshots.geometry_json,
                       evidence.metadata_json, evidence.excerpt
                FROM entity_snapshots AS snapshots
                JOIN evidence ON evidence.id = snapshots.evidence_id
                """
            )
            for value in row
        ).casefold()
        for forbidden in (
            "imagery.invalid",
            "backup generators",
            "do-not-retain",
            "equipment.geojson",
        ):
            self.assertNotIn(forbidden, persisted)

        geometry = json.loads(
            self.connection.execute(
                "SELECT geometry_json FROM entity_snapshots WHERE name = 'Expansion Campus'"
            ).fetchone()[0]
        )
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(geometry["coordinates"][0][0], [-97.2, 32.0])

    def test_directory_and_zip_imports_are_idempotent_without_network(self) -> None:
        adapter = EpochAIAdapter()
        with patch("socket.create_connection", side_effect=AssertionError("network used")):
            first = adapter.import_file(
                self.connection,
                EPOCH_FIXTURE,
                retrieved_at=RETRIEVED_AT,
                as_of_date=AS_OF_DATE,
                map_html=MAP_FIXTURE,
            )
            second = adapter.import_file(
                self.connection,
                EPOCH_FIXTURE,
                retrieved_at=RETRIEVED_AT,
                as_of_date=AS_OF_DATE,
                map_html=MAP_FIXTURE,
            )
        self.assertEqual(first.entities_created, 3)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)

        archive_path = self.temp_path / "data_centers.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(EPOCH_FIXTURE / "data_centers.csv", "saved/data_centers.csv")
            archive.write(
                EPOCH_FIXTURE / "data_center_timelines.csv",
                "saved/data_center_timelines.csv",
            )
        zipped = adapter.import_file(
            self.connection,
            archive_path,
            retrieved_at=RETRIEVED_AT,
            as_of_date=AS_OF_DATE,
            map_html=MAP_FIXTURE,
        )
        self.assertEqual(zipped.imported_elements, 3)
        self.assertEqual(zipped.entities_created, 0)
        self.assertEqual(zipped.evidence_created, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 3)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3)
        for row in self.connection.execute("SELECT metadata_json FROM evidence"):
            provenance = json.loads(row[0])["provenance"]
            self.assertEqual(provenance["input_type"], "directory")
            self.assertNotIn("input_sha256", provenance)

    def test_zip_capture_provenance_survives_directory_and_repacked_zip_imports(self) -> None:
        first_archive = self.temp_path / "first.zip"
        with zipfile.ZipFile(first_archive, "w") as archive:
            archive.write(EPOCH_FIXTURE / "data_centers.csv", "data_centers.csv")
            archive.write(
                EPOCH_FIXTURE / "data_center_timelines.csv",
                "data_center_timelines.csv",
            )
        first_archive_sha256 = hashlib.sha256(first_archive.read_bytes()).hexdigest()

        adapter = EpochAIAdapter()
        adapter.import_file(
            self.connection,
            first_archive,
            retrieved_at=RETRIEVED_AT,
            as_of_date=AS_OF_DATE,
            map_html=MAP_FIXTURE,
        )
        directory_result = adapter.import_file(
            self.connection,
            EPOCH_FIXTURE,
            retrieved_at=RETRIEVED_AT,
            as_of_date=AS_OF_DATE,
            map_html=MAP_FIXTURE,
        )

        repacked_archive = self.temp_path / "repacked.zip"
        with zipfile.ZipFile(
            repacked_archive, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.write(
                EPOCH_FIXTURE / "data_center_timelines.csv",
                "nested/data_center_timelines.csv",
            )
            archive.write(
                EPOCH_FIXTURE / "data_centers.csv", "nested/data_centers.csv"
            )
        repacked_result = adapter.import_file(
            self.connection,
            repacked_archive,
            retrieved_at=RETRIEVED_AT,
            as_of_date=AS_OF_DATE,
            map_html=MAP_FIXTURE,
        )

        self.assertEqual(directory_result.evidence_created, 0)
        self.assertEqual(repacked_result.evidence_created, 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
        )
        for row in self.connection.execute("SELECT metadata_json FROM evidence"):
            provenance = json.loads(row[0])["provenance"]
            self.assertEqual(provenance["input_type"], "zip")
            self.assertEqual(provenance["input_sha256"], first_archive_sha256)

    def test_non_container_provenance_drift_still_fails_closed(self) -> None:
        self.import_fixture()
        changed_map = self.temp_path / "same-map-different-bytes.html"
        changed_map.write_bytes(MAP_FIXTURE.read_bytes() + b"\n")

        with self.assertRaisesRegex(ValueError, "metadata_json"):
            EpochAIAdapter().import_file(
                self.connection,
                EPOCH_FIXTURE,
                retrieved_at=RETRIEVED_AT,
                as_of_date=AS_OF_DATE,
                map_html=changed_map,
            )

    def test_json_distinct_metadata_types_still_fail_closed(self) -> None:
        self.import_fixture()
        row = self.connection.execute(
            "SELECT id, metadata_json FROM evidence WHERE title LIKE '%Expansion Campus'"
        ).fetchone()
        original = row["metadata_json"]
        original_metadata = json.loads(original)
        self.assertEqual(
            original_metadata["selected_timeline"]["buildings_operational"], 1.0
        )

        for replacement in (True, 1):
            with self.subTest(replacement=repr(replacement)):
                changed = json.loads(original)
                changed["selected_timeline"]["buildings_operational"] = replacement
                with self.connection:
                    self.connection.execute(
                        "UPDATE evidence SET metadata_json = ? WHERE id = ?",
                        (
                            json.dumps(
                                changed, sort_keys=True, separators=(",", ":")
                            ),
                            row["id"],
                        ),
                    )
                with self.assertRaisesRegex(ValueError, "metadata_json"):
                    self.import_fixture()
                with self.connection:
                    self.connection.execute(
                        "UPDATE evidence SET metadata_json = ? WHERE id = ?",
                        (original, row["id"]),
                    )

    def test_invalid_container_provenance_shape_still_fails_closed(self) -> None:
        self.import_fixture()
        row = self.connection.execute(
            "SELECT id, metadata_json FROM evidence WHERE title LIKE '%Expansion Campus'"
        ).fetchone()
        changed = json.loads(row["metadata_json"])
        changed["provenance"]["input_sha256"] = "0" * 64
        with self.connection:
            self.connection.execute(
                "UPDATE evidence SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(changed, sort_keys=True, separators=(",", ":")),
                    row["id"],
                ),
            )

        with self.assertRaisesRegex(ValueError, "metadata_json"):
            self.import_fixture()

    def test_concurrent_directory_and_zip_imports_reconcile_after_insert_race(self) -> None:
        database = self.temp_path / "concurrent.sqlite"
        setup_connection, _ = initialize(database)
        setup_connection.close()
        archive_path = self.temp_path / "concurrent.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(EPOCH_FIXTURE / "data_centers.csv", "data_centers.csv")
            archive.write(
                EPOCH_FIXTURE / "data_center_timelines.csv",
                "data_center_timelines.csv",
            )

        barrier = threading.Barrier(2)
        thread_state = threading.local()
        original_reconcile = epoch_module._reconcile_existing_evidence_metadata

        def synchronized_reconcile(connection, evidence_id, metadata):
            reconciled = original_reconcile(connection, evidence_id, metadata)
            if not getattr(thread_state, "waited", False):
                thread_state.waited = True
                barrier.wait(timeout=10)
            return reconciled

        def run_import(path: Path):
            connection = connect(database)
            try:
                return EpochAIAdapter().import_file(
                    connection,
                    path,
                    retrieved_at=RETRIEVED_AT,
                    as_of_date=AS_OF_DATE,
                    map_html=MAP_FIXTURE,
                )
            finally:
                connection.close()

        with patch.object(
            epoch_module,
            "_reconcile_existing_evidence_metadata",
            side_effect=synchronized_reconcile,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(run_import, EPOCH_FIXTURE),
                    executor.submit(run_import, archive_path),
                ]
                results = [future.result(timeout=20) for future in futures]

        verification = connect(database)
        try:
            self.assertEqual(sum(result.entities_created for result in results), 3)
            self.assertEqual(sum(result.evidence_created for result in results), 3)
            self.assertEqual(
                verification.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 3
            )
            self.assertEqual(
                verification.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
            )
        finally:
            verification.close()

    def test_map_is_optional_and_future_only_rows_are_not_current(self) -> None:
        result = self.import_fixture(map_html=None)
        self.assertEqual(result.imported_elements, 3)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL"
            ).fetchone()[0],
            0,
        )

        second_connection, _ = initialize(self.temp_path / "early.sqlite")
        try:
            EpochAIAdapter().import_file(
                second_connection,
                EPOCH_FIXTURE,
                retrieved_at=RETRIEVED_AT,
                as_of_date="2024-01-01",
            )
            self.assertEqual(
                second_connection.execute(
                    "SELECT DISTINCT status FROM lifecycle_observations"
                ).fetchone()[0],
                "unknown",
            )
            self.assertEqual(
                second_connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                0,
            )
        finally:
            second_connection.close()

    def test_invalid_saved_map_is_rejected(self) -> None:
        invalid_map = self.temp_path / "map.html"
        invalid_map.write_text("<html>no map props</html>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SearchFilterMap"):
            parse_epoch_map_html(invalid_map)


if __name__ == "__main__":
    unittest.main()
