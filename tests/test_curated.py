from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


FIXTURE = Path(__file__).parent / "fixtures" / "curated_official.json"
RETRIEVED_AT = "2026-07-17T18:30:00Z"
META_RETRIEVED_AT = "2026-07-19T11:41:40Z"
GOOGLE_MEITNER_RETRIEVED_AT = "2026-07-19T05:25:12Z"
GOOGLE_MEITNER_SOURCE = "curated-official-2026-07-19-google-meitner.json"
GOOGLE_MEITNER_SOURCE_SHA256 = (
    "8af7320a5611c6d8289759e1caaaf10d7dceba88f62b533fbd9869cf6f556009"
)
GOOGLE_WILBARGER_RETRIEVED_AT = "2026-07-19T12:48:53Z"
GOOGLE_WILBARGER_SOURCE = "curated-official-2026-07-19-google-wilbarger.json"
GOOGLE_WILBARGER_SOURCE_SHA256 = (
    "4a9be29a7423d250c4e6df3f22c1dd3d4f1f7080ab9660fe54cd85d546989636"
)
GOOGLE_EXPANDED_SOURCES = {
    "curated-official-2026-07-19-google-horndal.json": (
        "9236651e77cc81ccf01231f48785a45242540fed0257b5b83e836de650caf527"
    ),
    "curated-official-2026-07-19-google-muskogee.json": (
        "a3ad4b8f5d6673e0966043e9ae9e540ffdf5730ffe027648e37152022bb61ada"
    ),
    "curated-official-2026-07-19-google-stillwater.json": (
        "7f4d2df1675f0c61f54804772e607ade3bcef2a16c471af4f3888dbe5fe17cbc"
    ),
    "curated-official-2026-07-19-google-vizag-ai-hub.json": (
        "2f47d46c02eaf5aeab70fb59cde3a3c0fd1a1317532a9ed509fe93ddaf8ab7bb"
    ),
}
META_SOURCES = {
    "curated-official-2026-07-19-meta-el-paso.json":
        "51c9222867d8a71e1c5bcff9f0987cbd18c709a41dfbf0771bbd2f1fccb29827",
    "curated-official-2026-07-19-meta-lebanon.json":
        "0515151f38cb071a3e5261dc237914f3c5955f7e3bd3b0bec0a6d5b28119c873",
    "curated-official-2026-07-19-meta-richland-parish.json":
        "90aabf84d4f1e3afca3f39e5c48e5058091cd50489eb521fecdba40b724c3a80",
    "curated-official-2026-07-19-meta-tulsa.json":
        "24ad9add9dc2c64591beae2cff6b36e6c36a4664e1bbae9f58258ae1ccaa4987",
}
MICROSOFT_SOURCES = {
    "curated-official-2026-07-19-microsoft-mount-pleasant-second.json": (
        "9ad3498bc28f1e00993922af38f4010c2ac81756c8cc9c5da70838d5b04c649d"
    ),
    "curated-official-2026-07-19-microsoft-pecos.json": (
        "388465ec039da418a1af3d7ac8011b83fd53a0142734003494dc29cc31de328d"
    ),
}
RELATED_SALINE_SOURCE = "curated-official-2026-07-19-related-saline-stargate.json"
RELATED_SALINE_SOURCE_SHA256 = (
    "3acea1d9dd42d17d75deb54e03a3f9e2af65d10eb990dbb5eaaa929d4a85b24f"
)
AWS_CURRENT_CONSTRUCTION_SOURCES = {
    "curated-official-2026-07-19-amazon-falls-township-pa.json": (
        "a81741c20cb4bca13ad47258ad325698d1323e2b5bda8e40ae5a56d98a2a559d"
    ),
    "curated-official-2026-07-19-amazon-salem-township-pa.json": (
        "e498e3974341d98659bc81ce86e4c685217b3cfe62c6a39c3c05f4d161fc16d1"
    ),
    "curated-official-2026-07-19-aws-walqa-spain.json": (
        "31048bd15869c30f78292a709f2d18e1b8423eacdbfda2faff9a9e04c0983698"
    ),
}
AWS_NEWLY_VERIFIED_PHYSICAL_SOURCES = {
    "curated-official-2026-07-19-amazon-energy-way-hamlet-01-county-scope.json": (
        "9edb7641f2fab0427e2ad9856ee4e65903407bdaf4a1dab0788ea008043a0743"
    ),
    "curated-official-2026-07-19-amazon-energy-way-hamlet-02-groundbreaking.json": (
        "cfe0ee5386d0a241eeccde2cfa0852e191bf187569392e041c3b532d01d91871"
    ),
    "curated-official-2026-07-19-amazon-energy-way-hamlet-03-ncdeq-address.json": (
        "6d2c2ac034a5cea1d59cfda97de5692815e3e9056059d406e2cc89dd50c07d73"
    ),
    "curated-official-2026-07-19-amazon-sbn100-new-carlisle.json": (
        "ef9bbce02e6a4b09fe198303a8a8b98082f0f1a8f88e8ea1476f32d65c056d67"
    ),
}
NEXTDC_SC2_SOURCE = "curated-official-2026-07-19-nextdc-sc2-maroochydore.json"
NEXTDC_SC2_SOURCE_SHA256 = (
    "499d309ef23814cab06c6a83e4bfc92e26004a699863351b4bc6ae3df8a3b4bf"
)
KAO_KLON03_SOURCE = "curated-official-2026-07-19-kao-klon03-harlow.json"
KAO_KLON03_SOURCE_SHA256 = (
    "ad85adb478a332e968a131535b4448f9ddab6eb130de9176912b7a42b5a3db3b"
)


class CuratedOfficialSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary_directory.name)
        self.connection, _ = initialize(self.temp_path / "atlas.sqlite")
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def write_document(self, document: dict, name: str = "record.json") -> Path:
        path = self.temp_path / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def import_fixture(self):
        return CuratedOfficialSourceAdapter().import_file(
            self.connection,
            FIXTURE,
            retrieved_at=RETRIEVED_AT,
        )

    def test_valid_campus_and_project_preserve_provenance_and_roles(self) -> None:
        result = self.import_fixture()
        self.assertEqual(result.entities_created, 2)
        self.assertEqual(result.evidence_created, 2)
        self.assertEqual(
            [tuple(row) for row in self.connection.execute(
                "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
            )],
            [("campus", 1), ("project", 1)],
        )
        project_target = self.connection.execute(
            """
            SELECT target.kind
            FROM projects
            JOIN entities AS target ON target.id = projects.target_entity_id
            """
        ).fetchone()[0]
        self.assertEqual(project_target, "campus")

        evidence = self.connection.execute(
            """
            SELECT kind, source_url, publisher, source_family, published_at,
                   retrieved_at, license, excerpt, content_hash, metadata_json
            FROM evidence WHERE kind = 'utility_record'
            """
        ).fetchone()
        self.assertEqual(evidence["publisher"], "Example Electric Utility")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(len(evidence["content_hash"]), 64)
        metadata = json.loads(evidence["metadata_json"])
        self.assertEqual(metadata["curated_record_key"], "utility-energy-filing")
        self.assertEqual(
            metadata["content_hash_scope"],
            "Fixture placeholder digest; not derived from source bytes",
        )
        self.assertEqual(metadata["content_hash_verification"], "unverified_assertion")
        self.assertEqual(metadata["record"]["reporting_year"], 2025)

        campus_tags = json.loads(
            self.connection.execute(
                "SELECT tags_json FROM entity_snapshots WHERE name = 'Example AI Campus'"
            ).fetchone()[0]
        )
        self.assertEqual(campus_tags["country"], "United States")
        self.assertEqual(campus_tags["role:owner"], "Example Operator")
        self.assertEqual(campus_tags["role:utility"], "Example Electric Utility")
        self.assertEqual(validate_database(self.connection), [])

    def test_authoritative_locality_can_preserve_an_unmapped_entity(self) -> None:
        document = copy.deepcopy(self.document)
        for entity_ref in ("campus", "project"):
            document[entity_ref]["coordinates"] = None
            document[entity_ref]["geometry"] = None
            document[entity_ref]["method"] = "authoritative_locality"

        result = CuratedOfficialSourceAdapter().import_file(
            self.connection,
            self.write_document(document),
            retrieved_at=RETRIEVED_AT,
        )

        self.assertEqual(result.entities_created, 2)
        snapshots = self.connection.execute(
            """
            SELECT latitude, longitude, geometry_json, method
            FROM entity_snapshots
            ORDER BY name
            """
        ).fetchall()
        self.assertEqual(len(snapshots), 2)
        self.assertTrue(
            all(
                row["latitude"] is None
                and row["longitude"] is None
                and row["geometry_json"] is None
                and row["method"] == "authoritative_locality"
                for row in snapshots
            )
        )
        self.assertEqual(validate_database(self.connection), [])

    def test_snapshot_method_and_coordinate_presence_are_coupled(self) -> None:
        malformed_documents = []
        for method in (
            "authoritative_address_geocode",
            "authoritative_site_plan",
            "physical_observation",
            "analyst_geolocation",
        ):
            document = copy.deepcopy(self.document)
            document["campus"]["coordinates"] = None
            document["campus"]["geometry"] = None
            document["campus"]["method"] = method
            malformed_documents.append(("must be authoritative_locality", document))

        coordinate_bearing_locality = copy.deepcopy(self.document)
        coordinate_bearing_locality["campus"]["method"] = "authoritative_locality"
        malformed_documents.append(
            ("authoritative_locality requires null coordinates and geometry", coordinate_bearing_locality)
        )

        for index, (message, document) in enumerate(malformed_documents):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, message):
                    CuratedOfficialSourceAdapter().import_file(
                        self.connection,
                        self.write_document(document, f"malformed-locality-{index}.json"),
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(
                    self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )

    def test_power_and_energy_dimensions_remain_distinct(self) -> None:
        self.import_fixture()
        rows = self.connection.execute(
            """
            SELECT metric, stage, unit, low, base, high, method, target_date, notes
            FROM capacity_estimates ORDER BY metric
            """
        ).fetchall()
        indexed = {(row["metric"], row["stage"]): row for row in rows}
        self.assertEqual(len(rows), 5)
        self.assertEqual(indexed[("grid_connection_mw", "contracted")]["base"], 1000)
        self.assertEqual(indexed[("gross_facility_mw", "design")]["base"], 750)
        self.assertEqual(indexed[("critical_it_mw", "design")]["base"], 600)
        self.assertEqual(indexed[("generation_nameplate_mw", "planned")]["base"], 250)
        measured = indexed[("annual_energy_mwh", "measured")]
        self.assertEqual(measured["unit"], "MWh/year")
        self.assertEqual(measured["base"], 3_000_000)
        evidence_kind = self.connection.execute(
            """
            SELECT evidence.kind FROM evidence
            JOIN capacity_estimates ON capacity_estimates.evidence_id = evidence.id
            WHERE capacity_estimates.metric = 'annual_energy_mwh'
            """
        ).fetchone()[0]
        self.assertEqual(evidence_kind, "utility_record")

    def test_unknown_fields_enums_dates_units_and_references_fail_closed(self) -> None:
        mutations = []

        unknown_field = copy.deepcopy(self.document)
        unknown_field["campus"]["operator_guess"] = "Example"
        mutations.append(("unknown fields", unknown_field))

        unknown_enum = copy.deepcopy(self.document)
        unknown_enum["capacities"][0]["metric"] = "campus_power"
        mutations.append(("must be one of", unknown_enum))

        naive_timestamp = copy.deepcopy(self.document)
        naive_timestamp["evidence"][0]["retrieved_at"] = "2026-07-17T18:30:00"
        mutations.append(("timezone", naive_timestamp))

        bad_date = copy.deepcopy(self.document)
        bad_date["lifecycle"][0]["as_of_date"] = "2026-7-15"
        mutations.append(("ISO 8601 date", bad_date))

        bad_unit = copy.deepcopy(self.document)
        bad_unit["capacities"][4]["unit"] = "MWh"
        mutations.append(("must be 'MWh/year'", bad_unit))

        missing_evidence = copy.deepcopy(self.document)
        missing_evidence["workloads"][0]["evidence_key"] = "missing"
        mutations.append(("references missing evidence", missing_evidence))

        missing_hash_scope = copy.deepcopy(self.document)
        del missing_hash_scope["evidence"][0]["metadata"]["content_hash_scope"]
        mutations.append(("content_hash_scope", missing_hash_scope))

        unknown_hash_verification = copy.deepcopy(self.document)
        unknown_hash_verification["evidence"][0]["metadata"][
            "content_hash_verification"
        ] = "probably_verified"
        mutations.append(("content_hash_verification must be one of", unknown_hash_verification))

        for index, (message, document) in enumerate(mutations):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    CuratedOfficialSourceAdapter().import_file(
                        self.connection,
                        self.write_document(document, f"invalid-{index}.json"),
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(
                    self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )

    def test_construction_and_measured_energy_safeguards(self) -> None:
        weak_construction = copy.deepcopy(self.document)
        weak_construction["lifecycle"][1]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            CuratedOfficialSourceAdapter().import_file(
                self.connection,
                self.write_document(weak_construction, "weak-construction.json"),
                retrieved_at=RETRIEVED_AT,
            )

        unsupported_energy = copy.deepcopy(self.document)
        unsupported_energy["capacities"][4]["evidence_key"] = "company-construction-update"
        with self.assertRaisesRegex(ValueError, "measured annual energy requires"):
            CuratedOfficialSourceAdapter().import_file(
                self.connection,
                self.write_document(unsupported_energy, "unsupported-energy.json"),
                retrieved_at=RETRIEVED_AT,
            )
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0)

    def test_authoritative_physical_status_update_supports_a_typed_stage(self) -> None:
        document = copy.deepcopy(self.document)
        document["lifecycle"][1]["method"] = "authoritative_physical_status_update"

        CuratedOfficialSourceAdapter().import_file(
            self.connection,
            self.write_document(document, "physical-status-update.json"),
            retrieved_at=RETRIEVED_AT,
        )

        row = self.connection.execute(
            """
            SELECT status, method
            FROM lifecycle_observations
            WHERE status = 'under_construction'
            """
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ("under_construction", "authoritative_physical_status_update"),
        )

    def test_unknown_evidence_publication_date_is_preserved_as_null(self) -> None:
        document = copy.deepcopy(self.document)
        document["evidence"][0]["published_at"] = None
        CuratedOfficialSourceAdapter().import_file(
            self.connection,
            self.write_document(document, "unknown-publication-date.json"),
            retrieved_at=RETRIEVED_AT,
        )
        published_at = self.connection.execute(
            "SELECT published_at FROM evidence WHERE title LIKE 'Example operator%'"
        ).fetchone()[0]
        self.assertIsNone(published_at)

    def test_duplicate_logical_claim_keys_within_document_fail_closed(self) -> None:
        lifecycle = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(lifecycle["lifecycle"][0])
        duplicate["value"] = "expansion"
        lifecycle["lifecycle"].append(duplicate)

        operating_model = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(operating_model["operating_models"][0])
        duplicate["value"] = "hyperscaler"
        operating_model["operating_models"].append(duplicate)

        workload = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(workload["workloads"][0])
        duplicate["method"] = "analyst_synthesis"
        workload["workloads"].append(duplicate)

        capacity = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(capacity["capacities"][0])
        duplicate["method"] = "calculated"
        capacity["capacities"].append(duplicate)

        for index, document in enumerate(
            (lifecycle, operating_model, workload, capacity)
        ):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "duplicates the logical claim key"):
                    CuratedOfficialSourceAdapter().import_file(
                        self.connection,
                        self.write_document(document, f"duplicate-claim-{index}.json"),
                        retrieved_at=RETRIEVED_AT,
                    )
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 0)

    def test_conflicting_existing_claim_at_same_transaction_time_fails_closed(self) -> None:
        self.import_fixture()
        baseline_counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            )
        }

        lifecycle = copy.deepcopy(self.document)
        lifecycle["lifecycle"][0]["value"] = "expansion"
        lifecycle["lifecycle"][0]["method"] = "authoritative_status_update"

        operating_model = copy.deepcopy(self.document)
        operating_model["operating_models"][0]["value"] = "hyperscaler"

        workload = copy.deepcopy(self.document)
        workload["workloads"][0]["method"] = "analyst_synthesis"

        capacity = copy.deepcopy(self.document)
        capacity["capacities"][0]["method"] = "calculated"

        expected_tables = (
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        for index, (document, table) in enumerate(
            zip((lifecycle, operating_model, workload, capacity), expected_tables)
        ):
            with self.subTest(table=table):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"{table} already has an active claim",
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        self.connection,
                        self.write_document(document, f"existing-conflict-{index}.json"),
                        retrieved_at=RETRIEVED_AT,
                    )
                current_count = self.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                self.assertEqual(current_count, baseline_counts[table])

    def test_different_as_of_date_is_legitimate_history(self) -> None:
        self.import_fixture()
        later = copy.deepcopy(self.document)
        later["lifecycle"][0]["as_of_date"] = "2026-07-16"
        CuratedOfficialSourceAdapter().import_file(
            self.connection,
            self.write_document(later, "later-observation.json"),
            retrieved_at=RETRIEVED_AT,
        )
        rows = self.connection.execute(
            """
            SELECT as_of_date, superseded_at
            FROM lifecycle_observations
            WHERE status = 'operational'
            ORDER BY as_of_date
            """
        ).fetchall()
        self.assertEqual(
            [(row["as_of_date"], row["superseded_at"]) for row in rows],
            [("2026-07-15", None), ("2026-07-16", None)],
        )

    def test_import_is_offline_and_idempotent(self) -> None:
        adapter = CuratedOfficialSourceAdapter()
        with patch("socket.create_connection", side_effect=AssertionError("network used")):
            first = adapter.import_file(
                self.connection, FIXTURE, retrieved_at=RETRIEVED_AT
            )
            second = adapter.import_file(
                self.connection, FIXTURE, retrieved_at=RETRIEVED_AT
            )
        self.assertEqual(first.entities_created, 2)
        self.assertEqual(first.evidence_created, 2)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0], 5)


class MetaFleetDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(
            Path(self.temporary_directory.name) / "atlas.sqlite"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_one_fleet_disclosure_supports_four_bounded_project_rows(self) -> None:
        source_root = Path(__file__).parents[1] / "sources"
        adapter = CuratedOfficialSourceAdapter()
        evidence_created = 0
        entities_created = 0
        with patch("socket.create_connection", side_effect=AssertionError("network used")):
            for name, expected_sha256 in sorted(META_SOURCES.items()):
                path = source_root / name
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), expected_sha256
                )
                result = adapter.import_file(
                    self.connection, path, retrieved_at=META_RETRIEVED_AT
                )
                evidence_created += result.evidence_created
                entities_created += result.entities_created

        self.assertEqual(evidence_created, 1)
        self.assertEqual(entities_created, 8)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 1
        )
        evidence = self.connection.execute(
            "SELECT source_url, content_hash FROM evidence"
        ).fetchone()
        self.assertEqual(
            evidence["source_url"],
            "https://about.fb.com/news/2026/04/infrastructure-explained-meta-data-centers/",
        )
        self.assertEqual(
            evidence["content_hash"],
            "03276a9c604df1c1adb01179830a4a0a8cabe3552dc9151acfcd70e7d2ff996f",
        )
        lifecycle = self.connection.execute(
            """
            SELECT entities.kind, lifecycle_observations.status,
                   lifecycle_observations.evidence_id
            FROM lifecycle_observations
            JOIN entities ON entities.id = lifecycle_observations.entity_id
            ORDER BY entities.stable_key
            """
        ).fetchall()
        self.assertEqual(len(lifecycle), 4)
        self.assertEqual({row["kind"] for row in lifecycle}, {"project"})
        self.assertEqual(
            {row["status"] for row in lifecycle}, {"under_construction"}
        )
        self.assertEqual(len({row["evidence_id"] for row in lifecycle}), 1)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM operating_model_observations"
            ).fetchone()[0],
            4,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM workload_observations"
            ).fetchone()[0],
            4,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            0,
        )
        self.assertEqual(validate_database(self.connection), [])


class GoogleMeitnerDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(
            Path(self.temporary_directory.name) / "atlas.sqlite"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_construction_and_air_cooling_import_without_power_inference(self) -> None:
        path = Path(__file__).parents[1] / "sources" / GOOGLE_MEITNER_SOURCE
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            GOOGLE_MEITNER_SOURCE_SHA256,
        )
        with patch("socket.create_connection", side_effect=AssertionError("network used")):
            result = CuratedOfficialSourceAdapter().import_file(
                self.connection,
                path,
                retrieved_at=GOOGLE_MEITNER_RETRIEVED_AT,
            )
        self.assertEqual(result.entities_created, 2)
        self.assertEqual(result.evidence_created, 1)
        lifecycle = self.connection.execute(
            """
            SELECT entities.kind, lifecycle_observations.status,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id = lifecycle_observations.entity_id
            """
        ).fetchone()
        self.assertEqual(
            tuple(lifecycle),
            ("project", "under_construction", "authoritative_construction_start"),
        )
        evidence = self.connection.execute(
            "SELECT source_family, content_hash, metadata_json FROM evidence"
        ).fetchone()
        self.assertEqual(evidence["source_family"], "google_infrastructure_blog")
        self.assertEqual(
            evidence["content_hash"],
            "ba34ebf8fa9031339a63ddb670baba0e4f84f82b0ba3d2384e31b3e3aef42ea9",
        )
        metadata = json.loads(evidence["metadata_json"])["record"]
        self.assertIn("air cooling", metadata["cooling_statement"])
        self.assertIn("no typed data-center power", metadata["capacity_guardrail"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            0,
        )
        self.assertEqual(validate_database(self.connection), [])


class GoogleWilbargerDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(
            Path(self.temporary_directory.name) / "atlas.sqlite"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_under_construction_and_air_cooling_do_not_import_statewide_mw(self) -> None:
        path = Path(__file__).parents[1] / "sources" / GOOGLE_WILBARGER_SOURCE
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            GOOGLE_WILBARGER_SOURCE_SHA256,
        )
        with patch("socket.create_connection", side_effect=AssertionError("network used")):
            result = CuratedOfficialSourceAdapter().import_file(
                self.connection,
                path,
                retrieved_at=GOOGLE_WILBARGER_RETRIEVED_AT,
            )
        self.assertEqual(result.entities_created, 2)
        lifecycle = self.connection.execute(
            """
            SELECT entities.kind, lifecycle_observations.status
            FROM lifecycle_observations
            JOIN entities ON entities.id = lifecycle_observations.entity_id
            """
        ).fetchone()
        self.assertEqual(tuple(lifecycle), ("project", "under_construction"))
        evidence = self.connection.execute(
            "SELECT content_hash, metadata_json FROM evidence"
        ).fetchone()
        self.assertEqual(
            evidence["content_hash"],
            "a17a49128feabdd4eb0b2fbffe92e5a08c6e4ea98a470a57b0e3cc90837ebf8a",
        )
        metadata = json.loads(evidence["metadata_json"])["record"]
        self.assertIn("advanced air-cooling", metadata["cooling_statement"])
        self.assertIn("not this data center's load", metadata["capacity_guardrail"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
            0,
        )
        self.assertEqual(validate_database(self.connection), [])


class GoogleExpandedConstructionDisclosureTests(unittest.TestCase):
    def test_four_rows_share_bounded_evidence_and_import_no_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            source_root = Path(__file__).parents[1] / "sources"
            evidence_created = 0
            try:
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    for name, expected_sha256 in sorted(GOOGLE_EXPANDED_SOURCES.items()):
                        path = source_root / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamps = {
                            evidence["retrieved_at"] for evidence in document["evidence"]
                        }
                        self.assertEqual(len(timestamps), 1)
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=timestamps.pop()
                        )
                        evidence_created += result.evidence_created
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    8,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations WHERE status='under_construction'"
                    ).fetchone()[0],
                    4,
                )
                self.assertEqual(evidence_created, 3)
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, COUNT(*) FROM workload_observations "
                        "GROUP BY workload ORDER BY workload"
                    )],
                    [("ai_specialized_unspecified", 1), ("mixed", 1)],
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class MicrosoftCurrentProjectDisclosureTests(unittest.TestCase):
    def test_physical_construction_and_announcement_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            source_root = Path(__file__).parents[1] / "sources"
            try:
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    for name, expected_sha256 in sorted(MICROSOFT_SOURCES.items()):
                        path = source_root / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )

                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    4,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT lifecycle_observations.status,
                               lifecycle_observations.method,
                               entity_snapshots.name
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        JOIN entity_snapshots ON entity_snapshots.entity_id = entities.id
                        ORDER BY lifecycle_observations.status
                        """
                    )],
                    [
                        (
                            "announced",
                            "authoritative_announcement",
                            "Microsoft Pecos Datacenter Campus Development",
                        ),
                        (
                            "under_construction",
                            "authoritative_construction_start",
                            "Microsoft Mount Pleasant Second Datacenter Facility",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT source_family, content_hash FROM evidence "
                        "ORDER BY content_hash"
                    )],
                    [
                        (
                            "microsoft_official_news",
                            "7234fda5abd4dd9da1776fd89bdc85e090636fe908311b480d793aa8a3c05fa0",
                        ),
                        (
                            "microsoft_official_news",
                            "77fac6f3a791838dbedef730cfa66188023339a8f67752ed07e16438a508db29",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations "
                        "WHERE operating_model='hyperscaler'"
                    ).fetchone()[0],
                    2,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations WHERE workload='mixed'"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class RelatedSalineStargateDisclosureTests(unittest.TestCase):
    def test_construction_and_contracted_grid_load_keep_energy_modeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            path = Path(__file__).parents[1] / "sources" / RELATED_SALINE_SOURCE
            try:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    RELATED_SALINE_SOURCE_SHA256,
                )
                document = json.loads(path.read_text(encoding="utf-8"))
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        path,
                        retrieved_at=document["evidence"][0]["retrieved_at"],
                    )

                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 2)
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT status, method FROM lifecycle_observations"
                    )],
                    [("under_construction", "authoritative_construction_start")],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT metric, stage, unit, low, base, high, method
                        FROM capacity_estimates ORDER BY metric
                        """
                    )],
                    [
                        (
                            "annual_energy_mwh",
                            "forecast",
                            "MWh/year",
                            0.0,
                            9_811_200.0,
                            12_264_000.0,
                            "modeled",
                        ),
                        (
                            "grid_connection_mw",
                            "contracted",
                            "MW",
                            1_400.0,
                            1_400.0,
                            1_400.0,
                            "reported",
                        ),
                    ],
                )
                capacity_evidence = [tuple(row) for row in connection.execute(
                    """
                    SELECT capacity_estimates.metric, evidence.kind, evidence.publisher
                    FROM capacity_estimates
                    JOIN evidence ON evidence.id = capacity_estimates.evidence_id
                    ORDER BY capacity_estimates.metric
                    """
                )]
                self.assertEqual(
                    capacity_evidence,
                    [
                        ("annual_energy_mwh", "utility_record", "DTE Energy"),
                        ("grid_connection_mw", "utility_record", "DTE Energy"),
                    ],
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class AWSCurrentConstructionDisclosureTests(unittest.TestCase):
    def test_three_active_builds_preserve_status_scope_and_import_no_power(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            source_root = Path(__file__).parents[1] / "sources"
            try:
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    for name, expected_sha256 in sorted(
                        AWS_CURRENT_CONSTRUCTION_SOURCES.items()
                    ):
                        path = source_root / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )

                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    6,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT lifecycle_observations.status,
                               lifecycle_observations.method,
                               entity_snapshots.name
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        JOIN entity_snapshots ON entity_snapshots.entity_id = entities.id
                        ORDER BY entity_snapshots.name
                        """
                    )],
                    [
                        (
                            "under_construction",
                            "authoritative_construction_start",
                            "AWS Walqa Current Data Center Build",
                        ),
                        (
                            "under_construction",
                            "authoritative_construction_start",
                            "Amazon Falls Township Active Campus Buildout",
                        ),
                        (
                            "under_construction",
                            "authoritative_construction_start",
                            "Amazon Salem Township Active Campus Buildout",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, COUNT(*) FROM workload_observations "
                        "GROUP BY workload ORDER BY workload"
                    )],
                    [("mixed", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT source_family, COUNT(*) FROM evidence "
                        "GROUP BY source_family ORDER BY source_family"
                    )],
                    [
                        ("amazon_pennsylvania_innovation_campus_site", 2),
                        ("aragon_government_news", 1),
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class AWSNewlyVerifiedPhysicalConstructionTests(unittest.TestCase):
    def test_sbn100_and_energy_way_keep_identity_status_and_power_scopes_separate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            source_root = Path(__file__).parents[1] / "sources"
            evidence_created = 0
            entities_created = 0
            try:
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    for name, expected_sha256 in sorted(
                        AWS_NEWLY_VERIFIED_PHYSICAL_SOURCES.items()
                    ):
                        path = source_root / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )
                        evidence_created += result.evidence_created
                        entities_created += result.entities_created

                self.assertEqual(entities_created, 4)
                self.assertEqual(evidence_created, 4)
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities "
                        "GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.method,
                               lifecycle_observations.as_of_date
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:amazon-energy-way-tech-campus-hamlet:physical-build",
                            "under_construction",
                            "authoritative_construction_start",
                            "2025-10-30",
                        ),
                        (
                            "curated:amazon-sbn100-new-carlisle:physical-build",
                            "under_construction",
                            "authoritative_construction_start",
                            "2025-07-14",
                        ),
                    ],
                )
                latest_hamlet = connection.execute(
                    """
                    SELECT entity_snapshots.name, entity_snapshots.tags_json
                    FROM entity_snapshots
                    JOIN entities ON entities.id = entity_snapshots.entity_id
                    WHERE entities.stable_key = ?
                    ORDER BY entity_snapshots.as_of_date DESC
                    LIMIT 1
                    """,
                    ("curated:amazon-energy-way-tech-campus-hamlet",),
                ).fetchone()
                self.assertEqual(latest_hamlet["name"], "Amazon Energy Way Tech Campus")
                hamlet_tags = json.loads(latest_hamlet["tags_json"])
                self.assertEqual(
                    hamlet_tags["address"],
                    "198 Energy Way, Hamlet, Richmond County, North Carolina 28345, "
                    "United States",
                )
                self.assertNotIn("role:operator", hamlet_tags)

                sbn100_tags = json.loads(connection.execute(
                    """
                    SELECT entity_snapshots.tags_json
                    FROM entity_snapshots
                    JOIN entities ON entities.id = entity_snapshots.entity_id
                    WHERE entities.stable_key = ?
                    ORDER BY entity_snapshots.as_of_date DESC
                    LIMIT 1
                    """,
                    ("curated:amazon-sbn100-new-carlisle",),
                ).fetchone()[0])
                self.assertEqual(
                    sbn100_tags["address"],
                    "31100 Edison Road, New Carlisle, St. Joseph County, Indiana 46552, "
                    "United States",
                )
                self.assertEqual(
                    sbn100_tags["role:operator"], "Amazon Data Services, Inc."
                )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT source_family, content_hash FROM evidence "
                        "ORDER BY source_family"
                    )],
                    [
                        (
                            "amazon_data_center_communities",
                            "d8cf69f374b6f4c378afe423a8bfe3da73411b3eb091079c8dc38256b6c03be9",
                        ),
                        (
                            "indiana_idem_air_permit",
                            "022b74f1eac162f47558f6f704b97fe7ec1e82fa2159a96dc1ac791352b832b7",
                        ),
                        (
                            "north_carolina_deq_air_permit_public_notice",
                            "3ca81fa88f66e79cc0e65af8013b6174ded7e0ec8c5536605ddb286d3fbe7196",
                        ),
                        (
                            "richmond_county_economic_development",
                            "bc5db5cd0634754b0ce2b11b4681981d96932d6ce2d1c756a7ea43a0753a9293",
                        ),
                    ],
                )
                ncdeq_metadata = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence "
                    "WHERE source_family='north_carolina_deq_air_permit_public_notice'"
                ).fetchone()[0])["record"]
                self.assertIn("preliminary determinations", ncdeq_metadata["permit_guardrail"])
                self.assertIn("Duke generation", ncdeq_metadata["power_guardrail"])
                idem_metadata = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence "
                    "WHERE source_family='indiana_idem_air_permit'"
                ).fetchone()[0])["record"]
                self.assertIn("SBN201, SBN104", idem_metadata["identity_guardrail"])
                self.assertIn("design release alone", idem_metadata["other_facility_guardrail"])
                self.assertIn("PDF CreationDate", idem_metadata["observation_date_basis"])
                self.assertIsNone(connection.execute(
                    "SELECT published_at FROM evidence "
                    "WHERE source_family='indiana_idem_air_permit'"
                ).fetchone()[0])

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, method FROM workload_observations"
                    )],
                    [("mixed", "government_record")],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class NextdcSc2ConstructionDisclosureTests(unittest.TestCase):
    def test_government_construction_and_ai_factory_import_no_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            path = Path(__file__).parents[1] / "sources" / NEXTDC_SC2_SOURCE
            try:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    NEXTDC_SC2_SOURCE_SHA256,
                )
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        path,
                        retrieved_at="2026-07-19T14:08:52Z",
                    )

                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 1)
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT status, method FROM lifecycle_observations"
                    )],
                    [("under_construction", "authoritative_construction_start")],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, method FROM workload_observations"
                    )],
                    [("ai_specialized_unspecified", "government_record")],
                )
                evidence = connection.execute(
                    "SELECT source_family, content_hash, metadata_json FROM evidence"
                ).fetchone()
                self.assertEqual(
                    evidence["source_family"],
                    "sunshine_coast_council_investment_news",
                )
                self.assertEqual(
                    evidence["content_hash"],
                    "cbd54dda58683be18dc5765acdf7a34d203b99bb9cf6559b4bf363756fa7f95e",
                )
                metadata = json.loads(evidence["metadata_json"])["record"]
                self.assertIn("not power", metadata["investment_guardrail"])
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


class KaoKlon03ConstructionDisclosureTests(unittest.TestCase):
    def test_walkover_and_fresh_filing_preserve_project_and_metric_boundaries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            path = Path(__file__).parents[1] / "sources" / KAO_KLON03_SOURCE
            try:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    KAO_KLON03_SOURCE_SHA256,
                )
                document = json.loads(path.read_text(encoding="utf-8"))
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        path,
                        retrieved_at="2026-07-19T14:23:16Z",
                    )

                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 2)
                self.assertEqual(
                    {item["retrieved_at"] for item in document["evidence"]},
                    {"2026-07-19T14:23:16Z"},
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.kind,
                               lifecycle_observations.status,
                               lifecycle_observations.method,
                               lifecycle_observations.as_of_date,
                               evidence.source_family
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        JOIN evidence ON evidence.id = lifecycle_observations.evidence_id
                        ORDER BY lifecycle_observations.as_of_date
                        """
                    )],
                    [
                        (
                            "project",
                            "under_construction",
                            "physical_observation",
                            "2025-02-10",
                            "environment_agency_permit_application_supporting_document",
                        ),
                        (
                            "project",
                            "under_construction",
                            "authoritative_construction_start",
                            "2026-05-26",
                            "nzx_company_announcement",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT source_family, content_hash FROM evidence "
                        "ORDER BY source_family"
                    )],
                    [
                        (
                            "environment_agency_permit_application_supporting_document",
                            "beed9e6e1cc4413078fd0a46c72e273f5d9adf36bbd4fcf2ef736142d635e5d9",
                        ),
                        (
                            "nzx_company_announcement",
                            "253b86ebd57dcd24f6807269653a1cb15c923c5259014b697d0c0ea255b6c789",
                        ),
                    ],
                )

                project = connection.execute(
                    """
                    SELECT entity_snapshots.name,
                           entity_snapshots.latitude,
                           entity_snapshots.longitude,
                           entity_snapshots.tags_json
                    FROM entity_snapshots
                    JOIN entities ON entities.id = entity_snapshots.entity_id
                    WHERE entities.stable_key = ?
                    """,
                    ("curated:kao-data-harlow-campus:klon-03-building",),
                ).fetchone()
                self.assertEqual(project["name"], "KAO Data KLON-03 Data Centre Building")
                self.assertAlmostEqual(project["latitude"], 51.770073603)
                self.assertAlmostEqual(project["longitude"], 0.130495857)
                project_tags = json.loads(project["tags_json"])
                self.assertEqual(
                    project_tags["address"],
                    "London Road, Harlow, Essex, CM17 9NA, United Kingdom",
                )
                self.assertFalse(
                    any(key.startswith("role:") for key in project_tags)
                )

                ea_metadata = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence WHERE source_family = ?",
                    ("environment_agency_permit_application_supporting_document",),
                ).fetchone()[0])["record"]
                self.assertEqual(ea_metadata["physical_observation_date"], "2025-02-10")
                self.assertIn("not treated", ea_metadata["permit_guardrail"])
                self.assertIn("not a KLON-03 building centroid", ea_metadata["coordinate_basis"])

                nzx_metadata = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence WHERE source_family = ?",
                    ("nzx_company_announcement",),
                ).fetchone()[0])["record"]
                self.assertEqual(nzx_metadata["nzx_attachment_id"], 469320)
                self.assertIn("does not type", nzx_metadata["capacity_guardrail"])
                self.assertIn("forward-looking", nzx_metadata["completion_guardrail"])

                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
