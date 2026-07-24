from __future__ import annotations

from dataclasses import replace
import sqlite3
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize, schema_version
from datacenter_atlas.models import (
    AdministrativeAssignment,
    AdministrativeResolutionStatus,
    Building,
    Campus,
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
    OperatingModel,
    Project,
    Workload,
)
from datacenter_atlas.repository import (
    add_administrative_assignment,
    add_building,
    add_campus,
    add_capacity,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_operating_model,
    add_project,
    add_snapshot,
    add_workload,
)
from datacenter_atlas.service import (
    default_recorded_at,
    export_geojson,
    summarize,
    validate_database,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "atlas.sqlite"
        self.connection, self.installed = initialize(self.db_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def evidence(self, evidence_id: str, retrieved_at: str) -> Evidence:
        return Evidence(
            id=evidence_id,
            kind=EvidenceKind.GOVERNMENT_RECORD,
            title=f"Permit {evidence_id}",
            source_url=f"https://example.gov/permits/{evidence_id}",
            retrieved_at=retrieved_at,
            publisher="Example Planning Authority",
        )

    def create_facility(self) -> str:
        retrieved_at = "2026-07-02T00:00:00Z"
        add_evidence(self.connection, self.evidence("evidence-1", retrieved_at))
        facility = Facility("facility-1", "example:facility-1", "evidence-1")
        add_facility(self.connection, facility, created_at=retrieved_at)
        add_snapshot(
            self.connection,
            snapshot_id="snapshot-1",
            entity_id=facility.id,
            name="Example Facility",
            latitude=10.0,
            longitude=20.0,
            geometry={"type": "Point", "coordinates": [20.0, 10.0]},
            tags={},
            evidence_id="evidence-1",
            as_of_date="2026-07-01",
            recorded_at=retrieved_at,
            method="permit",
            confidence=0.9,
        )
        self.connection.commit()
        return facility.id

    def test_migration_is_versioned_and_idempotent(self) -> None:
        self.assertEqual(self.installed, [1, 2])
        self.assertEqual(schema_version(self.connection), 2)
        second_connection, installed = initialize(self.db_path)
        try:
            self.assertEqual(installed, [])
            self.assertEqual(schema_version(second_connection), 2)
        finally:
            second_connection.close()

    def test_existing_version_one_database_migrates_without_rebuilding(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy-v1.sqlite"
        legacy = sqlite3.connect(legacy_path)
        legacy.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
            + (
                Path(__file__).parents[1]
                / "datacenter_atlas"
                / "migrations"
                / "0001_initial.sql"
            ).read_text(encoding="utf-8")
        )
        legacy.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (1, 'initial')"
        )
        legacy.commit()
        legacy.close()

        migrated, installed = initialize(legacy_path)
        try:
            self.assertEqual(installed, [2])
            self.assertEqual(schema_version(migrated), 2)
            self.assertIsNotNone(
                migrated.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'administrative_assignments'"
                ).fetchone()
            )
        finally:
            migrated.close()

    def test_entity_cannot_reference_missing_evidence(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            add_facility(
                self.connection,
                Facility("facility-x", "example:x", "missing"),
                created_at="2026-07-01T00:00:00Z",
            )

    def test_evidence_replay_is_exact_and_conflicts_fail_closed(self) -> None:
        evidence = Evidence(
            id="exact-evidence",
            kind=EvidenceKind.GOVERNMENT_RECORD,
            title="Exact evidence",
            source_url="https://example.gov/exact",
            retrieved_at="2026-07-02T00:00:00Z",
            publisher="Example Authority",
            source_family="example",
            license="CC0-1.0",
            attribution="Example Authority",
            published_at="2026-07-01",
            excerpt="Exact excerpt",
        )
        self.assertTrue(
            add_evidence(
                self.connection,
                evidence,
                content_hash="a" * 64,
                metadata={"b": 2, "a": 1},
            )
        )
        equivalent_offset = replace(
            evidence,
            retrieved_at="2026-07-02T02:00:00+02:00",
        )
        self.assertFalse(
            add_evidence(
                self.connection,
                equivalent_offset,
                content_hash="a" * 64,
                metadata={"a": 1, "b": 2},
            )
        )
        before = tuple(
            self.connection.execute(
                "SELECT * FROM evidence WHERE id = 'exact-evidence'"
            ).fetchone()
        )
        conflicts = (
            (
                replace(evidence, source_url="https://example.gov/changed"),
                "a" * 64,
                {"a": 1, "b": 2},
                "source_url",
            ),
            (evidence, "b" * 64, {"a": 1, "b": 2}, "content_hash"),
            (evidence, "a" * 64, {"a": 2}, "metadata_json"),
        )
        for conflicting, content_hash, metadata, field in conflicts:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    add_evidence(
                        self.connection,
                        conflicting,
                        content_hash=content_hash,
                        metadata=metadata,
                    )
                self.assertEqual(
                    tuple(
                        self.connection.execute(
                            "SELECT * FROM evidence WHERE id = 'exact-evidence'"
                        ).fetchone()
                    ),
                    before,
                )

    def test_sql_rejects_claim_without_evidence(self) -> None:
        entity_id = self.create_facility()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO lifecycle_observations(
                    id, entity_id, status, evidence_id, as_of_date,
                    recorded_at, method, confidence
                ) VALUES ('bad-claim', ?, 'proposed', 'missing', '2026-07-01',
                          '2026-07-02T00:00:00Z', 'test', 0.5)
                """,
                (entity_id,),
            )

    def test_capacity_model_preserves_metric_unit_and_range(self) -> None:
        entity_id = self.create_facility()
        estimate = CapacityEstimate(
            id="capacity-1",
            entity_id=entity_id,
            metric=CapacityMetric.GENERATION_NAMEPLATE_MW,
            low=180.0,
            base=200.0,
            high=220.0,
            method=EstimateMethod.PERMIT_INFERENCE,
            confidence=0.75,
            evidence_id="evidence-1",
            as_of_date="2026-07-01",
            recorded_at="2026-07-02T00:00:00Z",
            stage=CapacityStage.INSTALLED,
            target_date="2026-08-01",
            notes="permit generator schedule",
        )
        add_capacity(self.connection, estimate)
        row = self.connection.execute("SELECT * FROM capacity_estimates").fetchone()
        self.assertEqual(row["metric"], "generation_nameplate_mw")
        self.assertEqual(row["stage"], "installed")
        self.assertEqual(row["unit"], "MW")
        self.assertEqual(row["notes"], "permit generator schedule")
        self.assertEqual(row["target_date"], "2026-08-01")
        summary = summarize(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-03T00:00:00Z",
        )
        installed = summary["capacity_base_totals"]["generation_nameplate_mw"][
            "installed"
        ]
        self.assertEqual(installed, {"base": 200.0, "count": 1, "unit": "MW"})
        self.assertEqual((row["low"], row["base"], row["high"]), (180.0, 200.0, 220.0))

    def test_sql_rejects_wrong_capacity_unit(self) -> None:
        entity_id = self.create_facility()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO capacity_estimates(
                    id, entity_id, metric, unit, low, base, high, method, confidence,
                    evidence_id, as_of_date, recorded_at
                ) VALUES ('bad-unit', ?, 'annual_energy_mwh', 'MW', 1, 2, 3,
                          'reported', 0.5, 'evidence-1', '2026-07-01',
                          '2026-07-02T00:00:00Z')
                """,
                (entity_id,),
            )

    def test_bitemporal_history_is_reproducible(self) -> None:
        entity_id = self.create_facility()
        old = LifecycleObservation(
            "status-old",
            entity_id,
            LifecycleStatus.PROPOSED,
            "evidence-1",
            "2026-07-01",
            "2026-07-02T00:00:00Z",
            "permit",
            0.8,
        )
        add_lifecycle(self.connection, old)
        add_evidence(
            self.connection,
            self.evidence("evidence-2", "2026-07-11T00:00:00Z"),
        )
        new = LifecycleObservation(
            "status-new",
            entity_id,
            LifecycleStatus.UNDER_CONSTRUCTION,
            "evidence-2",
            "2026-07-10",
            "2026-07-11T00:00:00Z",
            "site_inspection",
            0.95,
        )
        add_lifecycle(self.connection, new)
        self.connection.commit()

        historical = export_geojson(
            self.connection,
            as_of="2026-07-05",
            recorded_at="2026-07-05T00:00:00Z",
        )
        retrospective = export_geojson(
            self.connection,
            as_of="2026-07-05",
            recorded_at="2026-07-12T00:00:00Z",
        )
        current = export_geojson(
            self.connection,
            as_of="2026-07-12",
            recorded_at="2026-07-12T00:00:00Z",
        )
        self.assertEqual(historical["features"][0]["properties"]["status"], "proposed")
        self.assertEqual(retrospective["features"][0]["properties"]["status"], "proposed")
        self.assertEqual(current["features"][0]["properties"]["status"], "under_construction")
        self.assertEqual(validate_database(self.connection), [])

    def test_same_as_of_correction_preserves_transaction_history(self) -> None:
        entity_id = self.create_facility()
        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "status-original",
                entity_id,
                LifecycleStatus.PROPOSED,
                "evidence-1",
                "2026-07-01",
                "2026-07-02T00:00:00Z",
                "permit",
                0.8,
            ),
        )
        add_evidence(
            self.connection,
            self.evidence("evidence-correction", "2026-07-03T00:00:00Z"),
        )
        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "status-correction",
                entity_id,
                LifecycleStatus.PERMITTING,
                "evidence-correction",
                "2026-07-01",
                "2026-07-03T00:00:00Z",
                "corrected_permit_reading",
                0.9,
            ),
        )
        self.connection.commit()

        before_correction = export_geojson(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T12:00:00Z",
        )
        after_correction = export_geojson(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-04T00:00:00Z",
        )
        self.assertEqual(
            before_correction["features"][0]["properties"]["status"], "proposed"
        )
        self.assertEqual(
            after_correction["features"][0]["properties"]["status"], "permitting"
        )
        self.assertEqual(validate_database(self.connection), [])

    def test_read_cutoffs_are_canonical_utc_whole_seconds(self) -> None:
        entity_id = self.create_facility()
        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "cutoff-status-old",
                entity_id,
                LifecycleStatus.PROPOSED,
                "evidence-1",
                "2026-07-01",
                "2026-07-02T00:00:00Z",
                "permit",
                0.8,
            ),
        )
        add_evidence(
            self.connection,
            self.evidence("cutoff-evidence-new", "2026-07-02T01:00:00Z"),
        )
        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "cutoff-status-new",
                entity_id,
                LifecycleStatus.PERMITTING,
                "cutoff-evidence-new",
                "2026-07-01",
                "2026-07-02T01:00:00Z",
                "permit_update",
                0.9,
            ),
        )

        before_snapshot = export_geojson(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T01:00:00+02:00",
        )
        self.assertEqual(before_snapshot["atlas_recorded_at"], "2026-07-01T23:00:00Z")
        self.assertEqual(before_snapshot["features"], [])

        at_first_second = export_geojson(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T01:00:00.000+01:00",
        )
        self.assertEqual(
            at_first_second["atlas_recorded_at"], "2026-07-02T00:00:00Z"
        )
        self.assertEqual(
            at_first_second["features"][0]["properties"]["status"], "proposed"
        )

        after_supersession = export_geojson(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T02:00:00+01:00",
        )
        self.assertEqual(
            after_supersession["features"][0]["properties"]["status"],
            "permitting",
        )
        canonical_summary = summarize(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T01:00:00Z",
        )
        offset_summary = summarize(
            self.connection,
            as_of="2026-07-01",
            recorded_at="2026-07-02T02:00:00.000+01:00",
        )
        self.assertEqual(offset_summary, canonical_summary)
        self.assertRegex(
            default_recorded_at(),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

        for label, cutoff in (
            ("fraction", "2026-07-02T01:00:00.500000Z"),
            ("submicrosecond", "2026-07-02T01:00:00.0000001Z"),
            ("naive", "2026-07-02T01:00:00"),
            ("invalid", "not-a-timestamp"),
        ):
            with self.subTest(rejected_cutoff=label):
                with self.assertRaises(ValueError):
                    export_geojson(
                        self.connection,
                        as_of="2026-07-01",
                        recorded_at=cutoff,
                    )
                with self.assertRaises(ValueError):
                    summarize(
                        self.connection,
                        as_of="2026-07-01",
                        recorded_at=cutoff,
                    )

    def test_legacy_noncanonical_timestamps_fail_before_reads_and_writes(self) -> None:
        entity_id = self.create_facility()
        writers = (
            add_evidence,
            add_campus,
            add_facility,
            add_building,
            add_project,
            add_snapshot,
            add_lifecycle,
            add_operating_model,
            add_workload,
            add_capacity,
            add_administrative_assignment,
        )
        self.assertTrue(
            all(
                getattr(writer, "canonical_persistence_preflight", False)
                for writer in writers
            )
        )

        self.connection.execute(
            "UPDATE entity_snapshots SET recorded_at = ? WHERE id = ?",
            ("2026-07-02T00:00:00.500000Z", "snapshot-1"),
        )
        before = "\n".join(self.connection.iterdump())
        validation = validate_database(self.connection)
        self.assertTrue(
            any(
                "entity_snapshots.snapshot-1.recorded_at" in error
                and "explicit timestamp migration required" in error
                for error in validation
            )
        )
        for label, operation in (
            (
                "export",
                lambda: export_geojson(
                    self.connection,
                    as_of="2026-07-01",
                    recorded_at="2026-07-02T00:00:00Z",
                ),
            ),
            (
                "summary",
                lambda: summarize(
                    self.connection,
                    as_of="2026-07-01",
                    recorded_at="2026-07-02T00:00:00Z",
                ),
            ),
            (
                "evidence-write",
                lambda: add_evidence(
                    self.connection,
                    self.evidence("blocked-evidence", "2026-07-03T00:00:00Z"),
                ),
            ),
            (
                "provenance-write",
                lambda: add_facility(
                    self.connection,
                    Facility(entity_id, "example:facility-1", "evidence-1"),
                    created_at="2026-07-02T00:00:00Z",
                ),
            ),
            (
                "supersession-write",
                lambda: add_lifecycle(
                    self.connection,
                    LifecycleObservation(
                        "blocked-lifecycle",
                        entity_id,
                        LifecycleStatus.PROPOSED,
                        "evidence-1",
                        "2026-07-01",
                        "2026-07-02T00:00:00Z",
                        "test",
                        0.9,
                    ),
                ),
            ),
        ):
            with self.subTest(blocked_operation=label):
                with self.assertRaisesRegex(ValueError, "timestamp migration required"):
                    operation()
                self.assertEqual("\n".join(self.connection.iterdump()), before)

        self.connection.rollback()
        add_evidence(
            self.connection,
            self.evidence("supersession-evidence", "2026-07-03T00:00:00Z"),
        )
        add_snapshot(
            self.connection,
            snapshot_id="snapshot-2",
            entity_id=entity_id,
            name="Example Facility Updated",
            latitude=10.0,
            longitude=20.0,
            geometry={"type": "Point", "coordinates": [20.0, 10.0]},
            tags={},
            evidence_id="supersession-evidence",
            as_of_date="2026-07-01",
            recorded_at="2026-07-03T00:00:00Z",
            method="permit_update",
            confidence=0.9,
        )
        self.connection.execute(
            "UPDATE entity_snapshots SET superseded_at = ? WHERE id = ?",
            ("2026-07-03T01:00:00+01:00", "snapshot-1"),
        )
        with self.assertRaisesRegex(ValueError, "snapshot-1.superseded_at"):
            export_geojson(
                self.connection,
                as_of="2026-07-01",
                recorded_at="2026-07-03T00:00:00Z",
            )

    def test_canonical_but_broken_supersession_chain_fails_closed(self) -> None:
        entity_id = self.create_facility()
        add_evidence(
            self.connection,
            self.evidence("mischain-evidence", "2026-07-03T00:00:00Z"),
        )
        add_snapshot(
            self.connection,
            snapshot_id="mischain-snapshot",
            entity_id=entity_id,
            name="Example Facility Updated",
            latitude=10.0,
            longitude=20.0,
            geometry={"type": "Point", "coordinates": [20.0, 10.0]},
            tags={},
            evidence_id="mischain-evidence",
            as_of_date="2026-07-01",
            recorded_at="2026-07-03T00:00:00Z",
            method="permit_update",
            confidence=0.9,
        )
        self.connection.execute(
            "UPDATE entity_snapshots SET superseded_at = ? WHERE id = ?",
            ("2026-07-04T00:00:00Z", "snapshot-1"),
        )
        before = "\n".join(self.connection.iterdump())
        validation = validate_database(self.connection)
        self.assertTrue(
            any(
                "snapshot-1.superseded_at" in error
                and "expected exact next recorded_at '2026-07-03T00:00:00Z'" in error
                for error in validation
            )
        )
        for label, operation in (
            (
                "read",
                lambda: export_geojson(
                    self.connection,
                    as_of="2026-07-01",
                    recorded_at="2026-07-03T00:00:00Z",
                ),
            ),
            (
                "write",
                lambda: add_evidence(
                    self.connection,
                    self.evidence("blocked-by-mischain", "2026-07-04T00:00:00Z"),
                ),
            ),
        ):
            with self.subTest(blocked_operation=label):
                with self.assertRaisesRegex(ValueError, "chronology is unsafe"):
                    operation()
                self.assertEqual("\n".join(self.connection.iterdump()), before)

    def test_entity_creation_provenance_is_import_order_independent(self) -> None:
        provenances = (
            ("creation-evidence-z", "2026-07-03T00:00:00Z"),
            ("creation-evidence-y", "2026-07-02T00:00:00Z"),
            ("creation-evidence-b", "2026-07-01T00:00:00Z"),
            ("creation-evidence-a", "2026-07-01T00:00:00Z"),
        )

        for order in ((0, 1, 2, 3), (3, 2, 1, 0), (1, 3, 0, 2)):
            with self.subTest(order=order):
                connection, _ = initialize(":memory:")
                try:
                    for evidence_id, created_at in provenances:
                        add_evidence(
                            connection,
                            self.evidence(evidence_id, created_at),
                        )
                    creation_results = []
                    for index in order:
                        evidence_id, created_at = provenances[index]
                        creation_results.append(
                            add_facility(
                                connection,
                                Facility(
                                    "shared-facility",
                                    "example:shared-facility",
                                    evidence_id,
                                ),
                                created_at=created_at,
                            )
                        )
                    row = connection.execute(
                        "SELECT kind, stable_key, created_from_evidence_id, created_at "
                        "FROM entities WHERE id = 'shared-facility'"
                    ).fetchone()
                    self.assertEqual(sum(creation_results), 1)
                    self.assertEqual(
                        tuple(row),
                        (
                            "facility",
                            "example:shared-facility",
                            "creation-evidence-a",
                            "2026-07-01T00:00:00Z",
                        ),
                    )
                finally:
                    connection.close()

    def test_entity_identity_collisions_fail_closed(self) -> None:
        add_evidence(
            self.connection,
            self.evidence("identity-evidence", "2026-07-01T00:00:00Z"),
        )
        add_facility(
            self.connection,
            Facility("identity-facility", "example:identity", "identity-evidence"),
            created_at="2026-07-01T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "entity identity conflicts"):
            add_facility(
                self.connection,
                Facility(
                    "identity-facility",
                    "example:different-key",
                    "identity-evidence",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "stable key is already assigned"):
            add_facility(
                self.connection,
                Facility(
                    "different-entity-id",
                    "example:identity",
                    "identity-evidence",
                ),
                created_at="2026-07-01T00:00:00Z",
            )

    def test_entity_relation_conflicts_precede_provenance_updates(self) -> None:
        for evidence_id, timestamp in (
            ("relation-evidence-later", "2026-07-03T00:00:00Z"),
            ("relation-evidence-earlier", "2026-07-01T00:00:00Z"),
        ):
            add_evidence(self.connection, self.evidence(evidence_id, timestamp))
        for campus_id in ("relation-campus-1", "relation-campus-2"):
            add_campus(
                self.connection,
                Campus(
                    campus_id,
                    f"example:{campus_id}",
                    "relation-evidence-later",
                ),
                created_at="2026-07-03T00:00:00Z",
            )

        add_facility(
            self.connection,
            Facility(
                "relation-facility",
                "example:relation-facility",
                "relation-evidence-later",
                "relation-campus-1",
            ),
            created_at="2026-07-03T00:00:00Z",
        )
        original_provenance = (
            "relation-evidence-later",
            "2026-07-03T00:00:00Z",
        )

        def provenance(entity_id: str) -> tuple[str, str]:
            return tuple(
                self.connection.execute(
                    "SELECT created_from_evidence_id, created_at "
                    "FROM entities WHERE id = ?",
                    (entity_id,),
                ).fetchone()
            )

        with self.assertRaisesRegex(ValueError, "facilities relation conflicts"):
            add_facility(
                self.connection,
                Facility(
                    "relation-facility",
                    "example:relation-facility",
                    "relation-evidence-earlier",
                    "relation-campus-2",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        self.assertEqual(provenance("relation-facility"), original_provenance)
        self.assertEqual(
            self.connection.execute(
                "SELECT campus_id FROM facilities "
                "WHERE entity_id = 'relation-facility'"
            ).fetchone()[0],
            "relation-campus-1",
        )
        self.assertFalse(
            add_facility(
                self.connection,
                Facility(
                    "relation-facility",
                    "example:relation-facility",
                    "relation-evidence-earlier",
                    "relation-campus-1",
                ),
                created_at="2026-07-01T01:00:00+01:00",
            )
        )
        self.assertEqual(
            provenance("relation-facility"),
            ("relation-evidence-earlier", "2026-07-01T00:00:00Z"),
        )

        add_facility(
            self.connection,
            Facility(
                "relation-facility-2",
                "example:relation-facility-2",
                "relation-evidence-later",
                "relation-campus-2",
            ),
            created_at="2026-07-03T00:00:00Z",
        )
        add_building(
            self.connection,
            Building(
                "relation-building",
                "example:relation-building",
                "relation-evidence-later",
                "relation-facility",
            ),
            created_at="2026-07-03T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "buildings relation conflicts"):
            add_building(
                self.connection,
                Building(
                    "relation-building",
                    "example:relation-building",
                    "relation-evidence-earlier",
                    "relation-facility-2",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        self.assertEqual(provenance("relation-building"), original_provenance)
        self.assertFalse(
            add_building(
                self.connection,
                Building(
                    "relation-building",
                    "example:relation-building",
                    "relation-evidence-earlier",
                    "relation-facility",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        )

        add_project(
            self.connection,
            Project(
                "relation-project",
                "example:relation-project",
                "relation-evidence-later",
                "relation-campus-1",
            ),
            created_at="2026-07-03T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "projects relation conflicts"):
            add_project(
                self.connection,
                Project(
                    "relation-project",
                    "example:relation-project",
                    "relation-evidence-earlier",
                    "relation-campus-2",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        self.assertEqual(provenance("relation-project"), original_provenance)
        self.assertFalse(
            add_project(
                self.connection,
                Project(
                    "relation-project",
                    "example:relation-project",
                    "relation-evidence-earlier",
                    "relation-campus-1",
                ),
                created_at="2026-07-01T00:00:00Z",
            )
        )

        with self.assertRaisesRegex(ValueError, "lacks a campuses detail row"):
            add_campus(
                self.connection,
                Campus(
                    "relation-facility",
                    "example:relation-facility",
                    "relation-evidence-earlier",
                ),
                created_at="2025-01-01T00:00:00Z",
            )
        self.assertEqual(
            provenance("relation-facility"),
            ("relation-evidence-earlier", "2026-07-01T00:00:00Z"),
        )
    def test_temporal_supersession_is_import_order_independent(self) -> None:
        recorded_at = (
            "2026-07-02T00:00:00Z",
            "2026-07-03T00:00:00Z",
            "2026-07-04T00:00:00Z",
        )

        def import_order(order: tuple[int, ...]) -> tuple[dict[str, list[tuple]], list[str]]:
            connection, _ = initialize(":memory:")
            try:
                for index, timestamp in enumerate(recorded_at):
                    add_evidence(
                        connection,
                        self.evidence(f"temporal-evidence-{index}", timestamp),
                    )
                add_facility(
                    connection,
                    Facility(
                        "temporal-facility",
                        "example:temporal-facility",
                        "temporal-evidence-0",
                    ),
                    created_at=recorded_at[0],
                )

                for index in order:
                    add_snapshot(
                        connection,
                        snapshot_id=f"temporal-snapshot-{index}",
                        entity_id="temporal-facility",
                        name=f"Temporal Facility {index}",
                        latitude=10.0 + index,
                        longitude=20.0 + index,
                        geometry=None,
                        tags={"version": str(index)},
                        evidence_id=f"temporal-evidence-{index}",
                        as_of_date="2026-07-01",
                        recorded_at=recorded_at[index],
                        method="test",
                        confidence=0.9,
                    )
                statuses = (
                    LifecycleStatus.PROPOSED,
                    LifecycleStatus.PERMITTING,
                    LifecycleStatus.UNDER_CONSTRUCTION,
                )
                for index in order:
                    add_lifecycle(
                        connection,
                        LifecycleObservation(
                            f"temporal-lifecycle-{index}",
                            "temporal-facility",
                            statuses[index],
                            f"temporal-evidence-{index}",
                            "2026-07-01",
                            recorded_at[index],
                            "test",
                            0.9,
                        ),
                    )
                operating_models = (
                    OperatingModel.UNKNOWN,
                    OperatingModel.COLOCATION,
                    OperatingModel.HYPERSCALER,
                )
                for index in order:
                    add_operating_model(
                        connection,
                        observation_id=f"temporal-operating-model-{index}",
                        entity_id="temporal-facility",
                        operating_model=operating_models[index],
                        evidence_id=f"temporal-evidence-{index}",
                        as_of_date="2026-07-01",
                        recorded_at=recorded_at[index],
                        method="test",
                        confidence=0.9,
                    )
                for index in order:
                    add_workload(
                        connection,
                        observation_id=f"temporal-workload-{index}",
                        entity_id="temporal-facility",
                        workload=Workload.HPC,
                        evidence_id=f"temporal-evidence-{index}",
                        as_of_date="2026-07-01",
                        recorded_at=recorded_at[index],
                        method=f"test-{index}",
                        confidence=0.9,
                    )
                add_workload(
                    connection,
                    observation_id="isolated-workload-dimension",
                    entity_id="temporal-facility",
                    workload=Workload.GENERAL_CLOUD,
                    evidence_id="temporal-evidence-1",
                    as_of_date="2026-07-01",
                    recorded_at=recorded_at[1],
                    method="test",
                    confidence=0.9,
                )
                for index in order:
                    add_capacity(
                        connection,
                        CapacityEstimate(
                            id=f"temporal-capacity-{index}",
                            entity_id="temporal-facility",
                            metric=CapacityMetric.CRITICAL_IT_MW,
                            low=10.0 + index,
                            base=10.0 + index,
                            high=10.0 + index,
                            method=EstimateMethod.REPORTED,
                            confidence=0.9,
                            evidence_id=f"temporal-evidence-{index}",
                            as_of_date="2026-07-01",
                            recorded_at=recorded_at[index],
                            stage=CapacityStage.PLANNED,
                        ),
                    )
                for estimate_id, metric, stage in (
                    (
                        "isolated-capacity-stage",
                        CapacityMetric.CRITICAL_IT_MW,
                        CapacityStage.OPERATIONAL,
                    ),
                    (
                        "isolated-capacity-metric",
                        CapacityMetric.GRID_CONNECTION_MW,
                        CapacityStage.PLANNED,
                    ),
                ):
                    add_capacity(
                        connection,
                        CapacityEstimate(
                            id=estimate_id,
                            entity_id="temporal-facility",
                            metric=metric,
                            low=20.0,
                            base=20.0,
                            high=20.0,
                            method=EstimateMethod.REPORTED,
                            confidence=0.9,
                            evidence_id="temporal-evidence-1",
                            as_of_date="2026-07-01",
                            recorded_at=recorded_at[1],
                            stage=stage,
                        ),
                    )
                for index in order:
                    add_administrative_assignment(
                        connection,
                        AdministrativeAssignment(
                            id=f"temporal-assignment-{index}",
                            entity_id="temporal-facility",
                            resolution_status=AdministrativeResolutionStatus.UNMATCHED,
                            country_name=None,
                            iso_a2=None,
                            iso_a3=None,
                            source_admin=None,
                            source_sovereignt=None,
                            source_type=None,
                            source_note_adm0=None,
                            source_note_brk=None,
                            source_feature_id=None,
                            match_feature_ids_json="[]",
                            source_country_tag=None,
                            coordinate_snapshot_id=f"temporal-snapshot-{index}",
                            boundary_evidence_id=f"temporal-evidence-{index}",
                            as_of_date="2026-07-01",
                            recorded_at=recorded_at[index],
                            method="test",
                            confidence=0.9,
                        ),
                    )
                connection.commit()
                tables = (
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                    "administrative_assignments",
                )
                rows = {
                    table: [
                        tuple(row)
                        for row in connection.execute(
                            f"SELECT * FROM {table} ORDER BY id"
                        )
                    ]
                    for table in tables
                }
                return rows, validate_database(connection)
            finally:
                connection.close()

        oldest_first, errors = import_order((0, 1, 2))
        self.assertEqual(errors, [])
        for order in ((2, 1, 0), (1, 2, 0)):
            with self.subTest(order=order):
                rows, errors = import_order(order)
                self.assertEqual(rows, oldest_first)
                self.assertEqual(errors, [])

        for table, id_prefix in (
            ("entity_snapshots", "temporal-snapshot"),
            ("lifecycle_observations", "temporal-lifecycle"),
            ("operating_model_observations", "temporal-operating-model"),
            ("workload_observations", "temporal-workload"),
            ("capacity_estimates", "temporal-capacity"),
            ("administrative_assignments", "temporal-assignment"),
        ):
            id_index = 0
            recorded_at_index = {
                "entity_snapshots": 10,
                "lifecycle_observations": 6,
                "operating_model_observations": 6,
                "workload_observations": 6,
                "capacity_estimates": 14,
                "administrative_assignments": 18,
            }[table]
            superseded_at_index = recorded_at_index + 1
            chain = [
                (
                    row[id_index],
                    row[recorded_at_index],
                    row[superseded_at_index],
                )
                for row in oldest_first[table]
                if row[id_index].startswith(id_prefix)
            ]
            self.assertEqual(
                chain,
                [
                    (f"{id_prefix}-0", recorded_at[0], recorded_at[1]),
                    (f"{id_prefix}-1", recorded_at[1], recorded_at[2]),
                    (f"{id_prefix}-2", recorded_at[2], None),
                ],
            )

    def test_temporal_primary_key_replays_require_exact_persisted_content(self) -> None:
        entity_id = self.create_facility()
        add_evidence(
            self.connection,
            self.evidence("exact-claim-evidence", "2026-07-03T00:00:00Z"),
        )

        snapshot = {
            "snapshot_id": "snapshot-1",
            "entity_id": entity_id,
            "name": "Example Facility",
            "latitude": 10.0,
            "longitude": 20.0,
            "geometry": {"coordinates": [20.0, 10.0], "type": "Point"},
            "tags": {},
            "evidence_id": "evidence-1",
            "as_of_date": "2026-07-01",
            "recorded_at": "2026-07-02T00:00:00Z",
            "method": "permit",
            "confidence": 0.9,
        }
        self.assertFalse(add_snapshot(self.connection, **snapshot))
        for field, value, persisted_field in (
            (
                "geometry",
                {"type": "Point", "coordinates": [21.0, 11.0]},
                "geometry_json",
            ),
            ("tags", {"changed": "yes"}, "tags_json"),
        ):
            with self.subTest(table="entity_snapshots", field=field):
                conflicting = dict(snapshot)
                conflicting[field] = value
                with self.assertRaisesRegex(ValueError, persisted_field):
                    add_snapshot(self.connection, **conflicting)

        lifecycle = LifecycleObservation(
            "exact-lifecycle",
            entity_id,
            LifecycleStatus.PROPOSED,
            "evidence-1",
            "2026-07-01",
            "2026-07-02T00:00:00Z",
            "permit",
            0.8,
        )
        self.assertTrue(add_lifecycle(self.connection, lifecycle))
        later_lifecycle = LifecycleObservation(
            "later-lifecycle",
            entity_id,
            LifecycleStatus.PERMITTING,
            "exact-claim-evidence",
            "2026-07-01",
            "2026-07-03T00:00:00Z",
            "permit_update",
            0.9,
        )
        self.assertTrue(add_lifecycle(self.connection, later_lifecycle))
        self.assertFalse(add_lifecycle(self.connection, lifecycle))
        with self.assertRaisesRegex(ValueError, "status"):
            add_lifecycle(
                self.connection,
                replace(lifecycle, status=LifecycleStatus.ANNOUNCED),
            )

        operating_model = {
            "observation_id": "exact-operating-model",
            "entity_id": entity_id,
            "operating_model": OperatingModel.COLOCATION,
            "evidence_id": "evidence-1",
            "as_of_date": "2026-07-01",
            "recorded_at": "2026-07-02T00:00:00Z",
            "method": "reported",
            "confidence": 0.8,
        }
        self.assertTrue(add_operating_model(self.connection, **operating_model))
        self.assertFalse(add_operating_model(self.connection, **operating_model))
        conflicting_model = dict(operating_model)
        conflicting_model["operating_model"] = OperatingModel.HYPERSCALER
        with self.assertRaisesRegex(ValueError, "operating_model"):
            add_operating_model(self.connection, **conflicting_model)

        workload = {
            "observation_id": "exact-workload",
            "entity_id": entity_id,
            "workload": Workload.HPC,
            "evidence_id": "evidence-1",
            "as_of_date": "2026-07-01",
            "recorded_at": "2026-07-02T00:00:00Z",
            "method": "reported",
            "confidence": 0.8,
        }
        self.assertTrue(add_workload(self.connection, **workload))
        self.assertFalse(add_workload(self.connection, **workload))
        conflicting_workload = dict(workload)
        conflicting_workload["workload"] = Workload.GENERAL_CLOUD
        with self.assertRaisesRegex(ValueError, "workload"):
            add_workload(self.connection, **conflicting_workload)

        capacity = CapacityEstimate(
            id="exact-capacity",
            entity_id=entity_id,
            metric=CapacityMetric.CRITICAL_IT_MW,
            low=10.0,
            base=11.0,
            high=12.0,
            method=EstimateMethod.REPORTED,
            confidence=0.8,
            evidence_id="evidence-1",
            as_of_date="2026-07-01",
            recorded_at="2026-07-02T00:00:00Z",
            stage=CapacityStage.PLANNED,
            notes="exact notes",
        )
        self.assertTrue(add_capacity(self.connection, capacity))
        self.assertFalse(add_capacity(self.connection, capacity))
        for field, value in (
            ("stage", CapacityStage.OPERATIONAL),
            ("metric", CapacityMetric.GRID_CONNECTION_MW),
            ("notes", "changed notes"),
        ):
            with self.subTest(table="capacity_estimates", field=field):
                with self.assertRaisesRegex(ValueError, field):
                    add_capacity(self.connection, replace(capacity, **{field: value}))

        assignment = AdministrativeAssignment(
            id="exact-assignment",
            entity_id=entity_id,
            resolution_status=AdministrativeResolutionStatus.UNMATCHED,
            country_name=None,
            iso_a2=None,
            iso_a3=None,
            source_admin=None,
            source_sovereignt=None,
            source_type=None,
            source_note_adm0=None,
            source_note_brk=None,
            source_feature_id=None,
            match_feature_ids_json="[]",
            source_country_tag="Example",
            coordinate_snapshot_id="snapshot-1",
            boundary_evidence_id="evidence-1",
            as_of_date="2026-07-01",
            recorded_at="2026-07-02T00:00:00Z",
            method="test",
            confidence=0.8,
            notes="exact assignment notes",
        )
        self.assertTrue(
            add_administrative_assignment(self.connection, assignment)
        )
        self.assertFalse(
            add_administrative_assignment(self.connection, assignment)
        )
        with self.assertRaisesRegex(ValueError, "notes"):
            add_administrative_assignment(
                self.connection,
                replace(assignment, notes="changed assignment notes"),
            )

        self.assertEqual(validate_database(self.connection), [])

    def test_timestamps_normalize_to_utc_seconds_or_fail_before_mutation(self) -> None:
        earlier = self.evidence(
            "timezone-evidence-earlier",
            "2026-07-02T01:00:00+02:00",
        )
        later = self.evidence(
            "timezone-evidence-later",
            "2026-07-02T00:30:00Z",
        )
        add_evidence(self.connection, earlier)
        add_evidence(self.connection, later)
        add_evidence(
            self.connection,
            self.evidence(
                "timezone-zero-fraction",
                "2026-07-02T00:00:00.000+00:00",
            ),
        )
        self.assertEqual(
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT id, retrieved_at FROM evidence "
                    "WHERE id LIKE 'timezone-%' ORDER BY id"
                )
            ],
            [
                ("timezone-evidence-earlier", "2026-07-01T23:00:00Z"),
                ("timezone-evidence-later", "2026-07-02T00:30:00Z"),
                ("timezone-zero-fraction", "2026-07-02T00:00:00Z"),
            ],
        )

        facility = Facility(
            "timezone-facility",
            "example:timezone-facility",
            "timezone-evidence-later",
        )
        add_facility(
            self.connection,
            facility,
            created_at="2026-07-02T00:30:00Z",
        )
        add_snapshot(
            self.connection,
            snapshot_id="timezone-snapshot-later",
            entity_id=facility.id,
            name="Timezone Facility",
            latitude=None,
            longitude=None,
            geometry=None,
            tags={},
            evidence_id="timezone-evidence-later",
            as_of_date="2026-07-01",
            recorded_at="2026-07-02T00:30:00Z",
            method="test",
            confidence=0.9,
        )
        add_snapshot(
            self.connection,
            snapshot_id="timezone-snapshot-earlier",
            entity_id=facility.id,
            name="Timezone Facility",
            latitude=None,
            longitude=None,
            geometry=None,
            tags={},
            evidence_id="timezone-evidence-earlier",
            as_of_date="2026-07-01",
            recorded_at="2026-07-02T01:00:00+02:00",
            method="test",
            confidence=0.9,
        )
        self.assertEqual(
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT id, recorded_at, superseded_at FROM entity_snapshots "
                    "WHERE entity_id = ? ORDER BY recorded_at",
                    (facility.id,),
                )
            ],
            [
                (
                    "timezone-snapshot-earlier",
                    "2026-07-01T23:00:00Z",
                    "2026-07-02T00:30:00Z",
                ),
                ("timezone-snapshot-later", "2026-07-02T00:30:00Z", None),
            ],
        )
        self.assertFalse(
            add_facility(
                self.connection,
                replace(
                    facility,
                    created_from_evidence_id="timezone-evidence-earlier",
                ),
                created_at="2026-07-02T01:00:00+02:00",
            )
        )
        self.assertEqual(
            tuple(
                self.connection.execute(
                    "SELECT created_from_evidence_id, created_at FROM entities "
                    "WHERE id = ?",
                    (facility.id,),
                ).fetchone()
            ),
            ("timezone-evidence-earlier", "2026-07-01T23:00:00Z"),
        )

        for label, timestamp in (
            ("naive", "2026-07-02T00:00:00"),
            ("invalid", "not-a-timestamp"),
            ("fraction", "2026-07-02T00:00:00.1Z"),
            ("submicrosecond", "2026-07-02T00:00:00.0000001Z"),
        ):
            with self.subTest(evidence_timestamp=label):
                with self.assertRaises(ValueError):
                    add_evidence(
                        self.connection,
                        self.evidence(f"rejected-evidence-{label}", timestamp),
                    )
                self.assertIsNone(
                    self.connection.execute(
                        "SELECT id FROM evidence WHERE id = ?",
                        (f"rejected-evidence-{label}",),
                    ).fetchone()
                )

        provenance_before = tuple(
            self.connection.execute(
                "SELECT created_from_evidence_id, created_at FROM entities WHERE id = ?",
                (facility.id,),
            ).fetchone()
        )
        with self.assertRaisesRegex(ValueError, "whole-second precision"):
            add_facility(
                self.connection,
                facility,
                created_at="2026-06-01T00:00:00.1Z",
            )
        self.assertEqual(
            tuple(
                self.connection.execute(
                    "SELECT created_from_evidence_id, created_at FROM entities WHERE id = ?",
                    (facility.id,),
                ).fetchone()
            ),
            provenance_before,
        )

        fractional_recorded_at = "2026-07-03T00:00:00.1Z"
        fractional_calls = (
            lambda: add_snapshot(
                self.connection,
                snapshot_id="fraction-snapshot",
                entity_id=facility.id,
                name="Rejected",
                latitude=None,
                longitude=None,
                geometry=None,
                tags={},
                evidence_id="timezone-evidence-later",
                as_of_date="2026-07-01",
                recorded_at=fractional_recorded_at,
                method="test",
                confidence=0.9,
            ),
            lambda: add_lifecycle(
                self.connection,
                LifecycleObservation(
                    "fraction-lifecycle",
                    facility.id,
                    LifecycleStatus.PROPOSED,
                    "timezone-evidence-later",
                    "2026-07-01",
                    fractional_recorded_at,
                    "test",
                    0.9,
                ),
            ),
            lambda: add_operating_model(
                self.connection,
                observation_id="fraction-operating-model",
                entity_id=facility.id,
                operating_model=OperatingModel.UNKNOWN,
                evidence_id="timezone-evidence-later",
                as_of_date="2026-07-01",
                recorded_at=fractional_recorded_at,
                method="test",
                confidence=0.9,
            ),
            lambda: add_workload(
                self.connection,
                observation_id="fraction-workload",
                entity_id=facility.id,
                workload=Workload.HPC,
                evidence_id="timezone-evidence-later",
                as_of_date="2026-07-01",
                recorded_at=fractional_recorded_at,
                method="test",
                confidence=0.9,
            ),
            lambda: add_capacity(
                self.connection,
                CapacityEstimate(
                    id="fraction-capacity",
                    entity_id=facility.id,
                    metric=CapacityMetric.CRITICAL_IT_MW,
                    low=1.0,
                    base=1.0,
                    high=1.0,
                    method=EstimateMethod.REPORTED,
                    confidence=0.9,
                    evidence_id="timezone-evidence-later",
                    as_of_date="2026-07-01",
                    recorded_at=fractional_recorded_at,
                    stage=CapacityStage.PLANNED,
                ),
            ),
            lambda: add_administrative_assignment(
                self.connection,
                AdministrativeAssignment(
                    id="fraction-assignment",
                    entity_id=facility.id,
                    resolution_status=AdministrativeResolutionStatus.UNMATCHED,
                    country_name=None,
                    iso_a2=None,
                    iso_a3=None,
                    source_admin=None,
                    source_sovereignt=None,
                    source_type=None,
                    source_note_adm0=None,
                    source_note_brk=None,
                    source_feature_id=None,
                    match_feature_ids_json="[]",
                    source_country_tag=None,
                    coordinate_snapshot_id="timezone-snapshot-earlier",
                    boundary_evidence_id="timezone-evidence-later",
                    as_of_date="2026-07-01",
                    recorded_at=fractional_recorded_at,
                    method="test",
                    confidence=0.9,
                ),
            ),
        )
        for index, call in enumerate(fractional_calls):
            with self.subTest(fractional_temporal_table=index):
                with self.assertRaisesRegex(ValueError, "whole-second precision"):
                    call()
        for table in (
            "entity_snapshots",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
            "administrative_assignments",
        ):
            self.assertEqual(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE id LIKE 'fraction-%'"
                ).fetchone()[0],
                0,
            )
        self.assertEqual(validate_database(self.connection), [])

    def test_same_transaction_time_conflicts_fail_closed_for_snapshots_and_history(
        self,
    ) -> None:
        entity_id = self.create_facility()
        with self.assertRaisesRegex(
            ValueError,
            "entity_snapshots already has a claim for the same logical key",
        ):
            add_snapshot(
                self.connection,
                snapshot_id="snapshot-conflict",
                entity_id=entity_id,
                name="Conflicting Facility Name",
                latitude=11.0,
                longitude=21.0,
                geometry=None,
                tags={},
                evidence_id="evidence-1",
                as_of_date="2026-07-01",
                recorded_at="2026-07-02T00:00:00Z",
                method="conflicting_source",
                confidence=0.8,
            )
        self.assertIsNone(
            self.connection.execute(
                "SELECT id FROM entity_snapshots WHERE id = 'snapshot-conflict'"
            ).fetchone()
        )

        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "status-original",
                entity_id,
                LifecycleStatus.PROPOSED,
                "evidence-1",
                "2026-07-01",
                "2026-07-02T00:00:00Z",
                "permit",
                0.8,
            ),
        )
        add_evidence(
            self.connection,
            self.evidence("evidence-later", "2026-07-04T00:00:00Z"),
        )
        add_lifecycle(
            self.connection,
            LifecycleObservation(
                "status-later",
                entity_id,
                LifecycleStatus.PERMITTING,
                "evidence-later",
                "2026-07-01",
                "2026-07-04T00:00:00Z",
                "permit_update",
                0.9,
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "lifecycle_observations already has a claim for the same logical key",
        ):
            add_lifecycle(
                self.connection,
                LifecycleObservation(
                    "status-conflict",
                    entity_id,
                    LifecycleStatus.ANNOUNCED,
                    "evidence-1",
                    "2026-07-01",
                    "2026-07-02T00:00:00Z",
                    "conflicting_source",
                    0.8,
                ),
            )
        self.assertEqual(
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT id, recorded_at, superseded_at "
                    "FROM lifecycle_observations ORDER BY recorded_at"
                )
            ],
            [
                (
                    "status-original",
                    "2026-07-02T00:00:00Z",
                    "2026-07-04T00:00:00Z",
                ),
                ("status-later", "2026-07-04T00:00:00Z", None),
            ],
        )
        self.assertEqual(validate_database(self.connection), [])


if __name__ == "__main__":
    unittest.main()
