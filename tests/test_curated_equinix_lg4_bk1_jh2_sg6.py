from __future__ import annotations

import copy
import csv
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
V31_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v31.json"
V31_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v31"
V31_DEFINITION_SHA256 = (
    "15d5d8a29b2a1cef0a8cbfa1f24276ea5619f9811aab53959bf83cfb3b5050dd"
)
RETRIEVED_AT = "2026-07-19T19:55:41Z"
AS_OF_DATE = "2025-12-31"
PRIMARY_URL = (
    "https://investor.equinix.com/sec-filings/all-sec-filings/content/"
    "0001101239-26-000032/eqix-20251231.htm"
)
BODY_SHA256 = "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
BODY_BYTES = 4_071_886
HEADERS_SHA256 = (
    "226fb23df1efbdadb6d55352d6c908a3c9c478c1aed00062225dc4539a43f397"
)
HEADERS_BYTES = 2_615
EVIDENCE_KEY = (
    "equinix-2025-form-10-k-lg4-bk1-jh2-sg6-construction-table-"
    "captured-2026-07-19"
)
EXISTING_CAPTURE_SOURCE = (
    "curated-official-2026-07-19-equinix-sp7-sao-paulo-phase-1.json"
)

SOURCE_SPECS: dict[str, dict[str, str]] = {
    "curated-official-2026-07-19-equinix-lg4-lagos-phase-1.json": {
        "sha256": "febd36ed1e50cec8d35f81b610072931d9ed39992c54fc2bdfc695a2ee615ca9",
        "country": "Nigeria",
        "address": "Lagos, Nigeria",
        "campus_key": "curated:equinix-lg4-lagos-data-center",
        "campus_name": "Equinix LG4 Lagos Data Center",
        "project_key": "curated:equinix-lg4-lagos-data-center:phase-1",
        "project_name": "Equinix LG4 Phase 1",
    },
    "curated-official-2026-07-19-equinix-bk1-bangkok-phase-1.json": {
        "sha256": "a7484b6bede27e681203268a9cd2a3d43366d231816f367cd42005bd03433747",
        "country": "Thailand",
        "address": "Bangkok, Thailand",
        "campus_key": "curated:equinix-bk1-bangkok-data-center",
        "campus_name": "Equinix BK1 Bangkok Data Center",
        "project_key": "curated:equinix-bk1-bangkok-data-center:phase-1",
        "project_name": "Equinix BK1 Phase 1",
    },
    "curated-official-2026-07-19-equinix-jh2-johor-phases-1-2.json": {
        "sha256": "e1bcddf890dc2cd01c3d2313e251494cf73501569b8763722c4d9fd15b802505",
        "country": "Malaysia",
        "address": "Johor, Malaysia",
        "campus_key": "curated:equinix-jh2-johor-data-center",
        "campus_name": "Equinix JH2 Johor Data Center",
        "project_key": "curated:equinix-jh2-johor-data-center:phases-1-and-2",
        "project_name": "Equinix JH2 Phases 1 and 2",
    },
    "curated-official-2026-07-19-equinix-sg6-singapore-phase-1.json": {
        "sha256": "9624e173b67e49323c30bd25954fb0d8e1bc77eeee60a57de8707354a9766707",
        "country": "Singapore",
        "address": "Singapore",
        "campus_key": "curated:equinix-sg6-singapore-data-center",
        "campus_name": "Equinix SG6 Singapore Data Center",
        "project_key": "curated:equinix-sg6-singapore-data-center:phase-1",
        "project_name": "Equinix SG6 Phase 1",
    },
}
SOURCES = tuple(SOURCE_SPECS)
NEW_ENTITY_KEYS = {
    spec[key]
    for spec in SOURCE_SPECS.values()
    for key in ("campus_key", "project_key")
}
EXPECTED_TABLE_ROWS = [
    {
        "property": "LG4 phase 1",
        "location": "Lagos",
        "target_open_quarter": "Q4 2027",
        "sellable_cabinets": 975,
        "approximate_total_capex_usd_millions": 78,
    },
    {
        "property": "BK1 phase 1",
        "location": "Bangkok",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 1175,
        "approximate_total_capex_usd_millions": 110,
    },
    {
        "property": "JH2 phases 1 and 2",
        "location": "Johor",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 2225,
        "approximate_total_capex_usd_millions": 201,
    },
    {
        "property": "SG6 phase 1",
        "location": "Singapore",
        "target_open_quarter": "Q1 2027",
        "sellable_cabinets": 1550,
        "approximate_total_capex_usd_millions": 290,
    },
]
SUPPLEMENTARY_URLS = {
    "https://newsroom.equinix.com/2024-10-27-Equinix-Intends-to-Invest-"
    "Approximately-500-Million-to-Bring-Future-Proof-Digital-Infrastructure-"
    "to-Thailand",
    "https://newsroom.equinix.com/2025-11-10-Equinix-Tops-Out-Its-Second-"
    "Data-Center-in-Johor",
    "https://newsroom.equinix.com/2024-11-19-Equinix-Fosters-AI-Development-"
    "by-Building-a-High-Performance-and-Sustainable-Data-Center-in-Singapore",
}


class EquinixLg4Bk1Jh2Sg6Tests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["source_url"], PRIMARY_URL)
        self.assertEqual(evidence["content_hash"], BODY_SHA256)
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["published_at"], "2026-02-11")
        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(BODY_BYTES), metadata["content_hash_scope"])
        self.assertIn(str(HEADERS_BYTES), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], PRIMARY_URL)
        self.assertNotIn("request_started_at", metadata)
        self.assertNotIn("request_start_utc", metadata)
        self.assertIn(
            "no request-start artifact was supplied", metadata["retrieval_method"]
        )
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCE_SPECS[name]
        self.assertEqual(
            set(document),
            {
                "schema_version",
                "evidence",
                "campus",
                "project",
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            },
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        self._assert_capture(document["evidence"][0])
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["construction_table_as_of_date"], AS_OF_DATE)
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], AS_OF_DATE)
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

    def _database_state(
        self, order: tuple[str, ...] | list[str], *, repeat: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repeat):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                ROOT / "sources" / name,
                                retrieved_at=RETRIEVED_AT,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT title, source_url, content_hash, metadata_json "
                    "FROM evidence ORDER BY id",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, name, latitude, longitude, "
                    "geometry_json, tags_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entity_id, operating_model FROM operating_model_observations",
                    "SELECT entity_id, workload FROM workload_observations",
                    "SELECT entity_id, metric, stage, base FROM capacity_estimates",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _offline(self) -> Any:
        offline = AssertionError("curated source import attempted network access")
        return _MultipleContextManagers(
            patch.object(socket, "socket", side_effect=offline),
            patch.object(socket, "create_connection", side_effect=offline),
            patch.object(socket, "getaddrinfo", side_effect=offline),
            patch.object(socket, "gethostbyname", side_effect=offline),
            patch.object(socket, "gethostbyname_ex", side_effect=offline),
        )

    def test_exact_source_hashes_shared_capture_closure_and_v31_exclusion(self) -> None:
        self.assertEqual(
            hashlib.sha256(V31_DEFINITION.read_bytes()).hexdigest(),
            V31_DEFINITION_SHA256,
        )
        definition_text = V31_DEFINITION.read_text(encoding="utf-8")
        release_keys: set[str] = set()
        with (V31_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            release_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        self.assertTrue(NEW_ENTITY_KEYS.isdisjoint(release_keys))

        documents = []
        for name, expected in SOURCE_SPECS.items():
            source = ROOT / "sources" / name
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), expected["sha256"]
            )
            self.assertNotIn(name, definition_text)
            self.assertNotIn(expected["campus_key"], definition_text)
            self.assertNotIn(expected["project_key"], definition_text)
            document = self._load(name)
            self._assert_document(name, document)
            documents.append(document)

        first_evidence = documents[0]["evidence"]
        self.assertTrue(all(document["evidence"] == first_evidence for document in documents))
        prior = self._load(EXISTING_CAPTURE_SOURCE)["evidence"][0]
        current = first_evidence[0]
        self.assertNotEqual(prior["key"], current["key"])
        self.assertEqual(prior["content_hash"], current["content_hash"])
        closure_fields = (
            "content_hash_scope",
            "content_hash_verification",
            "capture_headers_scope",
            "capture_headers_sha256",
            "http_status",
            "content_type",
            "content_encoding_as_received",
            "http_content_length_bytes_as_received",
            "response_http_date",
            "http_last_modified_at",
            "requested_url",
            "effective_url",
            "canonical_url",
            "response_header_blocks",
            "retrieval_method",
            "retrieved_at_semantics",
            "form_type",
            "filing_date",
            "fiscal_year_end",
            "construction_table_as_of_date",
            "construction_table_heading_as_reported",
            "rights_scope",
            "imagery_guardrail",
        )
        for field in closure_fields:
            self.assertEqual(prior["metadata"][field], current["metadata"][field], field)
        self.assertEqual(
            {row["source_url"] for row in first_evidence},
            {PRIMARY_URL},
        )
        self.assertTrue(SUPPLEMENTARY_URLS.isdisjoint({row["source_url"] for row in first_evidence}))

    def test_table_rows_and_scope_guardrails_are_exact(self) -> None:
        metadata = self._load(SOURCES[0])["evidence"][0]["metadata"]
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)
        self.assertIn("forward-looking", metadata["target_date_guardrail"])
        self.assertIn("not MW", metadata["cabinet_guardrail"])
        self.assertIn("approximate", metadata["capex_guardrail"])
        self.assertIn("exactly one combined project", metadata["jh2_combined_row_guardrail"])
        self.assertIn("does not support separate phase 1 and phase 2", metadata["jh2_combined_row_guardrail"])
        self.assertIn("more than 3,375", metadata["bk1_program_scope_guardrail"])
        self.assertIn("not BK1 phase 1 attributes", metadata["bk1_program_scope_guardrail"])
        self.assertEqual(metadata["sg6_full_build_capacity_as_reported_mw_untyped_context"], 20)
        self.assertIn("not a phase 1 allocation", metadata["sg6_capacity_guardrail"])
        self.assertIn("creates no capacity row", metadata["sg6_capacity_guardrail"])
        self.assertIn("not an actual installed", metadata["sg6_ai_ready_guardrail"])
        self.assertIn("no workload", metadata["sg6_ai_ready_guardrail"])
        self.assertIn("not evidence objects", metadata["supplementary_pages_guardrail"])

        jh2 = self._load(
            "curated-official-2026-07-19-equinix-jh2-johor-phases-1-2.json"
        )
        combined_key = jh2["project"]["stable_key"]
        self.assertEqual(
            combined_key,
            "curated:equinix-jh2-johor-data-center:phases-1-and-2",
        )
        self.assertNotEqual(combined_key, "curated:equinix-jh2-johor-data-center:phase-1")
        self.assertNotEqual(combined_key, "curated:equinix-jh2-johor-data-center:phase-2")

    def test_forward_reverse_and_repeated_imports_are_byte_invariant(self) -> None:
        forward = self._database_state(SOURCES)
        reverse = self._database_state(tuple(reversed(SOURCES)))
        repeated_forward = self._database_state(SOURCES, repeat=2)
        repeated_reverse = self._database_state(tuple(reversed(SOURCES)), repeat=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated_forward)
        self.assertEqual(forward, repeated_reverse)
        entities, evidence, lifecycle, snapshots, models, workloads, capacities = forward
        self.assertEqual(len(entities), 8)
        self.assertEqual(
            {kind: sum(row[0] == kind for row in entities) for kind in ("campus", "project")},
            {"campus": 4, "project": 4},
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(lifecycle), 4)
        self.assertEqual(len(snapshots), 8)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(capacities, ())

    def test_individual_imports_and_idempotent_results_are_exact(self) -> None:
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        first = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=RETRIEVED_AT,
                        )
                        second = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=RETRIEVED_AT,
                        )
                    self.assertEqual(first.entities_created, 2)
                    self.assertEqual(first.evidence_created, 1)
                    self.assertEqual(second.entities_created, 0)
                    self.assertEqual(second.evidence_created, 0)
                    self.assertEqual(validate_database(connection), [])
                    self.assertEqual(
                        [
                            tuple(row)
                            for row in connection.execute(
                                "SELECT kind, stable_key FROM entities "
                                "ORDER BY kind, stable_key"
                            )
                        ],
                        [
                            ("campus", expected["campus_key"]),
                            ("project", expected["project_key"]),
                        ],
                    )
                    self.assertEqual(
                        [tuple(row) for row in connection.execute(
                            "SELECT status, as_of_date, method FROM lifecycle_observations"
                        )],
                        [
                            (
                                "under_construction",
                                AS_OF_DATE,
                                "authoritative_physical_status_update",
                            )
                        ],
                    )
                finally:
                    connection.close()

    def test_exact_delta_after_accepted_v31_curated_inputs_has_no_collision(self) -> None:
        definition = json.loads(V31_DEFINITION.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for record in definition["curated_inputs"]:
                        source = ROOT / record["path"]
                        document = json.loads(source.read_text(encoding="utf-8"))
                        retrieved = {row["retrieved_at"] for row in document["evidence"]}
                        self.assertEqual(len(retrieved), 1)
                        CuratedOfficialSourceAdapter().import_file(
                            connection, source, retrieved_at=next(iter(retrieved))
                        )
                    before = self._table_counts(connection)
                    results = [
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=RETRIEVED_AT,
                        )
                        for name in SOURCES
                    ]
                after = self._table_counts(connection)
                self.assertEqual(validate_database(connection), [])
                self.assertEqual(
                    {table: after[table] - before[table] for table in after},
                    {
                        "entities": 8,
                        "evidence": 1,
                        "entity_snapshots": 8,
                        "lifecycle_observations": 4,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    },
                )
                self.assertEqual(sum(result.entities_created for result in results), 8)
                self.assertEqual(sum(result.evidence_created for result in results), 1)
                self.assertTrue(
                    NEW_ENTITY_KEYS
                    <= {
                        row[0]
                        for row in connection.execute(
                            "SELECT stable_key FROM entities"
                        )
                    }
                )
            finally:
                connection.close()

    def _table_counts(self, connection: Any) -> dict[str, int]:
        tables = (
            "entities",
            "evidence",
            "entity_snapshots",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }

    def test_semantic_leakage_mutations_fail_the_focused_contract(self) -> None:
        name = SOURCES[0]
        original = self._load(name)
        mutations: list[dict[str, Any]] = []

        for entity_name in ("campus", "project"):
            mutated = copy.deepcopy(original)
            mutated[entity_name]["roles"] = {"operator": ["Equinix"]}
            mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["project"]["coordinates"] = {"latitude": 6.45, "longitude": 3.39}
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
                "evidence_key": EVIDENCE_KEY,
                "as_of_date": AS_OF_DATE,
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["operating_models"] = [
            {
                "entity": "project",
                "value": "retail_colocation",
                "evidence_key": EVIDENCE_KEY,
                "as_of_date": AS_OF_DATE,
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["capacities"] = [
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 20,
                "base": 20,
                "high": 20,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": EVIDENCE_KEY,
                "as_of_date": AS_OF_DATE,
                "target_date": None,
                "notes": "Invalid normalization of SG6 full-build context.",
            }
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["metadata"]["target_projects_as_reported"][1][
            "sellable_cabinets"
        ] = 3375
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["metadata"]["target_projects_as_reported"].append(
            {
                "property": "JH2 phase 2",
                "location": "Johor",
                "target_open_quarter": "Q3 2027",
                "sellable_cabinets": 2225,
                "approximate_total_capex_usd_millions": 201,
            }
        )
        mutations.append(mutated)

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["content_hash"] = "0" * 64
        mutations.append(mutated)

        for mutated in mutations:
            with self.assertRaises(AssertionError):
                self._assert_document(name, mutated)


class _MultipleContextManagers:
    def __init__(self, *managers: Any) -> None:
        self._managers = managers

    def __enter__(self) -> None:
        for manager in self._managers:
            manager.__enter__()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        for manager in reversed(self._managers):
            manager.__exit__(exc_type, exc_value, traceback)


if __name__ == "__main__":
    unittest.main()
