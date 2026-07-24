from __future__ import annotations

import copy
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
V35_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v35.json"
V35_DEFINITION_SHA256 = (
    "ade1722f44a8a97f848d94579a4cfc45bc96f7f706df80f38ad6c46cabc5735d"
)
RETRIEVED_AT = "2026-07-20T01:49:02Z"
AS_OF_DATE = "2025-12-31"
PRIMARY_URL = (
    "https://www.sec.gov/Archives/edgar/data/1101239/"
    "000110123926000032/0001101239-26-000032.txt"
)
USER_AGENT = "Judgment Labs Data Center Atlas research kian@judgmentlabs.ai"
BODY_SHA256 = "08404c4984e2dc86e78f64580e14277c727d8d49a2de87a303267ed6661497d4"
BODY_BYTES = 31_202_332
HEADERS_SHA256 = (
    "68c3a8ae02fe2f3609dc06e6e25cf5d935ae6f3142e4dae5e25fb794e0843a86"
)
HEADERS_BYTES = 732
WRITEOUT_SHA256 = (
    "b6a5ab1bc887520f8cf14d94f66a0fd7d53ac20196e86d4e1e0194d20e2d2825"
)
WRITEOUT_BYTES = 15_161
EVIDENCE_KEY = (
    "equinix-2025-form-10-k-americas-eight-complete-submission-sec-"
    "captured-2026-07-20"
)
RAW_EVIDENCE_BYTES = 10_275
RAW_EVIDENCE_SHA256 = (
    "15768463c64126f04dbf90587404d334b188c8b40f2234192145c8ce8272916d"
)
OLD_HTML_BODY_SHA256 = (
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
)
PRIOR_INLINE_XBRL_HTML_EVIDENCE_KEYS = [
    "equinix-2025-form-10-k-construction-table-captured-2026-07-19",
    "equinix-2025-form-10-k-lg4-bk1-jh2-sg6-construction-table-captured-2026-07-19",
]
CORROBORATION_GROUP_ID = (
    "equinix-sec-0001101239-26-000032-construction-table-2025-12-31"
)
SV18_PHASE_1_SUCCESSOR_SOURCE = (
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-1.json"
)
SV18_SHARED_CAMPUS_KEY = "curated:equinix-sv18-silicon-valley-data-center"
REMAINING14_EVIDENCE_KEY = (
    "equinix-2025-annual-report-fourteen-remaining-table-rows-ars-pdf-sec-"
    "captured-2026-07-20"
)

SOURCE_SPECS: dict[str, dict[str, str]] = {
    "curated-official-2026-07-20-equinix-mi1-miami-redevelopment.json": {
        "sha256": "55e40fce1b15eed4b306826f9d888a49e25b58567f285077c57c93b516d367dc",
        "country": "United States",
        "address": "Miami, United States",
        "campus_key": "curated:equinix-mi1-miami-data-center",
        "campus_name": "Equinix MI1 Miami Data Center",
        "project_key": "curated:equinix-mi1-miami-data-center:redevelopment",
        "project_name": "Equinix MI1 Redevelopment",
    },
    "curated-official-2026-07-20-equinix-mt1-montreal-phase-3.json": {
        "sha256": "aac8525c5b3d7b8bc23bdebe8128e7bafca65d388f68376fa5ffd24ae470100d",
        "country": "Canada",
        "address": "Montreal, Canada",
        "campus_key": "curated:equinix-mt1-montreal-data-center",
        "campus_name": "Equinix MT1 Montreal Data Center",
        "project_key": "curated:equinix-mt1-montreal-data-center:phase-3",
        "project_name": "Equinix MT1 Phase 3",
    },
    "curated-official-2026-07-20-equinix-dc17-washington-dc-phases-1-2.json": {
        "sha256": "ab49ff27607c854bfb5f40e44807d1a6d82e9b476d55319c247d61b244ab2398",
        "country": "United States",
        "address": "Washington, D.C. metro, United States",
        "campus_key": "curated:equinix-dc17-washington-dc-data-center",
        "campus_name": "Equinix DC17 Washington DC Data Center",
        "project_key": (
            "curated:equinix-dc17-washington-dc-data-center:phases-1-and-2"
        ),
        "project_name": "Equinix DC17 Phases 1 and 2",
    },
    "curated-official-2026-07-20-equinix-dc22-washington-dc-phase-2.json": {
        "sha256": "b4da29ceda8c3b1a37afebad9b79619633881fc5ab2bc8ea1c63d2535b81b3e7",
        "country": "United States",
        "address": "Washington, D.C. metro, United States",
        "campus_key": "curated:equinix-dc22-washington-dc-data-center",
        "campus_name": "Equinix DC22 Washington DC Data Center",
        "project_key": "curated:equinix-dc22-washington-dc-data-center:phase-2",
        "project_name": "Equinix DC22 Phase 2",
    },
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json": {
        "sha256": "f738ffea436ed192e6daaab61a083ccf6c187acd6697e6aedcd5a7f3f1794c1b",
        "country": "United States",
        "address": "Silicon Valley, United States",
        "campus_key": "curated:equinix-sv18-silicon-valley-data-center",
        "campus_name": "Equinix SV18 Silicon Valley Data Center",
        "project_key": "curated:equinix-sv18-silicon-valley-data-center:phase-2",
        "project_name": "Equinix SV18 Phase 2",
    },
    "curated-official-2026-07-20-equinix-tr6-toronto-phase-3.json": {
        "sha256": "3946e649d8ff0fa1c090eb390dbb0196350d3cc64a0001b9461516c67f2c5bca",
        "country": "Canada",
        "address": "Toronto, Canada",
        "campus_key": "curated:equinix-tr6-toronto-data-center",
        "campus_name": "Equinix TR6 Toronto Data Center",
        "project_key": "curated:equinix-tr6-toronto-data-center:phase-3",
        "project_name": "Equinix TR6 Phase 3",
    },
    "curated-official-2026-07-20-equinix-ch5-chicago-phase-2.json": {
        "sha256": "adb0539295241508fdcb46f2b10bc1962b52db7062b78631f825abff8978065e",
        "country": "United States",
        "address": "Chicago, United States",
        "campus_key": "curated:equinix-ch5-chicago-data-center",
        "campus_name": "Equinix CH5 Chicago Data Center",
        "project_key": "curated:equinix-ch5-chicago-data-center:phase-2",
        "project_name": "Equinix CH5 Phase 2",
    },
    "curated-official-2026-07-20-equinix-da12-dallas-phase-1.json": {
        "sha256": "d062e18f3ed965209d88da719faa8d2274ebd973d6a897dd7a44b9feca8fa5cc",
        "country": "United States",
        "address": "Dallas, United States",
        "campus_key": "curated:equinix-da12-dallas-data-center",
        "campus_name": "Equinix DA12 Dallas Data Center",
        "project_key": "curated:equinix-da12-dallas-data-center:phase-1",
        "project_name": "Equinix DA12 Phase 1",
    },
}
SOURCES = tuple(SOURCE_SPECS)
NEW_ENTITY_KEYS = {
    spec[field]
    for spec in SOURCE_SPECS.values()
    for field in ("campus_key", "project_key")
}
EXPECTED_TABLE_ROWS = [
    {
        "property": "MI1 redevelopment",
        "location": "Miami",
        "target_open_quarter": "Q3 2026",
        "sellable_cabinets": 475,
        "approximate_total_capex_usd_millions": 59,
    },
    {
        "property": "MT1 phase 3",
        "location": "Montreal",
        "target_open_quarter": "Q4 2026",
        "sellable_cabinets": 300,
        "approximate_total_capex_usd_millions": 37,
    },
    {
        "property": "DC17 phases 1 and 2",
        "location": "Washington, D.C.",
        "target_open_quarter": "Q2 2027",
        "sellable_cabinets": 4700,
        "approximate_total_capex_usd_millions": 622,
    },
    {
        "property": "DC22 phase 2",
        "location": "Washington, D.C.",
        "target_open_quarter": "Q2 2027",
        "sellable_cabinets": 2125,
        "approximate_total_capex_usd_millions": 144,
    },
    {
        "property": "SV18 phase 2",
        "location": "Silicon Valley",
        "target_open_quarter": "Q2 2027",
        "sellable_cabinets": 850,
        "approximate_total_capex_usd_millions": 180,
    },
    {
        "property": "TR6 phase 3",
        "location": "Toronto",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 1075,
        "approximate_total_capex_usd_millions": 123,
    },
    {
        "property": "CH5 phase 2",
        "location": "Chicago",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 1625,
        "approximate_total_capex_usd_millions": 165,
    },
    {
        "property": "DA12 phase 1",
        "location": "Dallas",
        "target_open_quarter": "Q2 2028",
        "sellable_cabinets": 3700,
        "approximate_total_capex_usd_millions": 837,
    },
]
EXPECTED_METADATA_KEYS = {
    "content_hash_scope",
    "content_hash_verification",
    "capture_headers_scope",
    "capture_headers_sha256",
    "capture_curl_writeout_scope",
    "capture_curl_writeout_sha256",
    "capture_artifact_guardrail",
    "request_user_agent",
    "request_credentials_guardrail",
    "http_status",
    "content_type",
    "content_encoding_as_received",
    "http_transfer_encoding_as_received",
    "http_content_length_bytes_as_received",
    "curl_size_download_bytes_as_received",
    "response_http_date",
    "http_last_modified_at",
    "response_set_cookie_header_count",
    "requested_url",
    "effective_url",
    "canonical_url",
    "canonical_url_basis",
    "response_header_blocks",
    "redirect_count",
    "http_version",
    "retrieval_method",
    "retrieved_at_semantics",
    "form_type",
    "complete_submission_filing_accession",
    "complete_submission_embedded_primary_document_type",
    "complete_submission_embedded_primary_document_filename",
    "embedded_primary_document_content_decoded_bytes",
    "corroboration_group_id",
    "inline_xbrl_html_body_sha256",
    "prior_inline_xbrl_html_evidence_keys",
    "independent_factual_corroboration",
    "source_artifact_distinction",
    "target_table_capture_scope",
    "filing_date",
    "fiscal_year_end",
    "construction_table_as_of_date",
    "construction_table_heading_as_reported",
    "target_projects_as_reported",
    "status_scope",
    "historical_status_guardrail",
    "target_date_guardrail",
    "cabinet_guardrail",
    "capex_guardrail",
    "capacity_guardrail",
    "classification_guardrail",
    "location_guardrail",
    "role_guardrail",
    "energy_guardrail",
    "rights_scope",
    "imagery_guardrail",
}


class EquinixAmericas10KTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _raw_evidence(self, name: str) -> bytes:
        raw = (ROOT / "sources" / name).read_bytes()
        start_marker = b'  "evidence": [\n'
        end_marker = b'\n  ],\n  "campus": {'
        start = raw.index(start_marker) + len(start_marker)
        end = raw.index(end_marker, start)
        return raw[start:end]

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        self.assertEqual(
            set(evidence),
            {
                "key",
                "kind",
                "title",
                "source_url",
                "publisher",
                "source_family",
                "published_at",
                "retrieved_at",
                "license",
                "attribution",
                "excerpt",
                "content_hash",
                "metadata",
            },
        )
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["title"], "Equinix 2025 Annual Report (Form 10-K)")
        self.assertEqual(evidence["source_url"], PRIMARY_URL)
        self.assertEqual(evidence["publisher"], "Equinix, Inc.")
        self.assertEqual(evidence["source_family"], "equinix_sec_filings")
        self.assertEqual(evidence["published_at"], "2026-02-11")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], BODY_SHA256)
        self.assertNotEqual(evidence["content_hash"], OLD_HTML_BODY_SHA256)

        metadata = evidence["metadata"]
        self.assertEqual(set(metadata), EXPECTED_METADATA_KEYS)
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(BODY_BYTES), metadata["content_hash_scope"])
        self.assertIn("complete-submission text", metadata["content_hash_scope"])
        self.assertIn(str(HEADERS_BYTES), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertIn(str(WRITEOUT_BYTES), metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)
        self.assertEqual(metadata["request_user_agent"], USER_AGENT)
        for forbidden in ("Authorization", "Proxy-Authorization", "Cookie"):
            self.assertIn(forbidden, metadata["request_credentials_guardrail"])
        self.assertIn("no authentication option", metadata["request_credentials_guardrail"])
        self.assertIn("no request-start artifact", metadata["retrieval_method"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/plain")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 8_071_339)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 8_071_339)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], "2026-02-11T21:16:05Z")
        self.assertEqual(metadata["response_set_cookie_header_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], PRIMARY_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["http_version"], "2")
        self.assertEqual(metadata["form_type"], "10-K")
        self.assertEqual(
            metadata["complete_submission_filing_accession"],
            "0001101239-26-000032",
        )
        self.assertEqual(metadata["complete_submission_embedded_primary_document_type"], "10-K")
        self.assertEqual(
            metadata["complete_submission_embedded_primary_document_filename"],
            "eqix-20251231.htm",
        )
        self.assertEqual(
            metadata["embedded_primary_document_content_decoded_bytes"],
            4_071_886,
        )
        self.assertEqual(metadata["corroboration_group_id"], CORROBORATION_GROUP_ID)
        self.assertEqual(metadata["inline_xbrl_html_body_sha256"], OLD_HTML_BODY_SHA256)
        self.assertEqual(
            metadata["prior_inline_xbrl_html_evidence_keys"],
            PRIOR_INLINE_XBRL_HTML_EVIDENCE_KEYS,
        )
        self.assertIs(metadata["independent_factual_corroboration"], False)
        self.assertIn(
            "distinct wrapper and retrieval", metadata["source_artifact_distinction"]
        )
        self.assertIn(
            "same underlying Equinix 2025 Form 10-K and construction table",
            metadata["source_artifact_distinction"],
        )
        self.assertIn(
            "not counted as independent factual corroboration",
            metadata["source_artifact_distinction"],
        )
        self.assertIn("exactly once", metadata["target_table_capture_scope"])
        self.assertEqual(metadata["filing_date"], "2026-02-11")
        self.assertEqual(metadata["fiscal_year_end"], AS_OF_DATE)
        self.assertEqual(metadata["construction_table_as_of_date"], AS_OF_DATE)
        self.assertEqual(
            metadata["construction_table_heading_as_reported"],
            "significant IBX data center projects under construction as of "
            "December 31, 2025",
        )
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)

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

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(
                set(entity),
                {
                    "stable_key",
                    "name",
                    "country",
                    "address",
                    "roles",
                    "coordinates",
                    "geometry",
                    "evidence_key",
                    "as_of_date",
                    "method",
                    "confidence",
                },
            )
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
        self.assertTrue(
            document["project"]["stable_key"].startswith(
                document["campus"]["stable_key"] + ":"
            )
        )
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

        non_evidence = {key: value for key, value in document.items() if key != "evidence"}
        forbidden_metadata_fields = {
            "target_open_quarter",
            "sellable_cabinets",
            "approximate_total_capex_usd_millions",
            "target_date",
        }
        self.assertTrue(
            forbidden_metadata_fields.isdisjoint(self._nested_keys(non_evidence))
        )

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

    def test_exact_hashes_canonical_json_and_byte_identical_evidence(self) -> None:
        self.assertEqual(
            hashlib.sha256(V35_DEFINITION.read_bytes()).hexdigest(),
            V35_DEFINITION_SHA256,
        )
        definition_text = V35_DEFINITION.read_text(encoding="utf-8")
        self.assertEqual(len(SOURCES), 8)
        self.assertEqual(len(NEW_ENTITY_KEYS), 16)

        raw_evidence: list[bytes] = []
        documents: list[dict[str, Any]] = []
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
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                json.dumps(document, indent=2) + "\n",
            )
            self._assert_document(name, document)
            documents.append(document)
            raw_evidence.append(self._raw_evidence(name))

        self.assertTrue(
            all(document["evidence"] == documents[0]["evidence"] for document in documents)
        )
        self.assertTrue(all(raw == raw_evidence[0] for raw in raw_evidence))
        self.assertEqual(len(raw_evidence[0]), RAW_EVIDENCE_BYTES)
        self.assertEqual(
            hashlib.sha256(raw_evidence[0]).hexdigest(), RAW_EVIDENCE_SHA256
        )
        self.assertIn(OLD_HTML_BODY_SHA256.encode(), raw_evidence[0])

    def test_table_rows_exclusions_and_scope_guardrails_are_exact(self) -> None:
        metadata = self._load(SOURCES[0])["evidence"][0]["metadata"]
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)
        properties = {row["property"] for row in EXPECTED_TABLE_ROWS}
        self.assertTrue(
            properties.isdisjoint(
                {"SV18 phase 1", "RJ3 phase 2", "SP4 phase 5", "SP7 phase 1"}
            )
        )
        self.assertFalse(
            any(
                row["target_open_quarter"] in {"Q1 2026", "Q2 2026"}
                for row in EXPECTED_TABLE_ROWS
            )
        )
        self.assertEqual(
            SOURCE_SPECS[
                "curated-official-2026-07-20-equinix-dc17-washington-dc-phases-1-2.json"
            ]["project_key"],
            "curated:equinix-dc17-washington-dc-data-center:phases-1-and-2",
        )
        self.assertNotIn(
            "curated:equinix-sv18-silicon-valley-data-center:phase-1",
            NEW_ENTITY_KEYS,
        )
        self.assertIn("historical status", metadata["historical_status_guardrail"])
        self.assertIn("does not prove", metadata["historical_status_guardrail"])
        self.assertIn("not an exact date", metadata["target_date_guardrail"])
        self.assertIn("not MW", metadata["cabinet_guardrail"])
        self.assertIn("not power", metadata["capex_guardrail"])
        self.assertIn("no capacity row", metadata["capacity_guardrail"])
        self.assertIn(
            "does not establish a normalized workload",
            metadata["classification_guardrail"],
        )
        self.assertIn("authoritative metro localities", metadata["location_guardrail"])
        self.assertIn("not normalized", metadata["role_guardrail"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])
        self.assertIn("identity inference", metadata["imagery_guardrail"])

    def test_no_collision_with_v35_or_any_other_curated_source(self) -> None:
        selected = {(ROOT / "sources" / name).resolve() for name in SOURCES}
        other_entity_keys: dict[str, list[str]] = {}
        other_evidence_keys: dict[str, list[str]] = {}
        other_evidence_hashes: dict[str, set[str]] = {}
        other_content_hashes: dict[str, list[str]] = {}
        other_sources = 0
        for source in sorted((ROOT / "sources").glob("curated-official*.json")):
            if source.resolve() in selected:
                continue
            other_sources += 1
            document = json.loads(source.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None:
                    other_entity_keys.setdefault(entity["stable_key"], []).append(
                        source.name
                    )
            for evidence in document.get("evidence", []):
                other_evidence_keys.setdefault(evidence["key"], []).append(source.name)
                other_evidence_hashes.setdefault(evidence["key"], set()).add(
                    evidence["content_hash"]
                )
                other_content_hashes.setdefault(evidence["content_hash"], []).append(
                    source.name
                )
        self.assertGreater(other_sources, 0)
        self.assertEqual(
            NEW_ENTITY_KEYS & set(other_entity_keys),
            {SV18_SHARED_CAMPUS_KEY},
        )
        self.assertEqual(
            other_entity_keys[SV18_SHARED_CAMPUS_KEY],
            [SV18_PHASE_1_SUCCESSOR_SOURCE],
        )
        self.assertNotIn(EVIDENCE_KEY, other_evidence_keys)
        self.assertNotIn(BODY_SHA256, other_content_hashes)
        self.assertIn(OLD_HTML_BODY_SHA256, other_content_hashes)
        self.assertEqual(
            {
                key: other_evidence_hashes.get(key)
                for key in PRIOR_INLINE_XBRL_HTML_EVIDENCE_KEYS
            },
            {
                key: {OLD_HTML_BODY_SHA256}
                for key in PRIOR_INLINE_XBRL_HTML_EVIDENCE_KEYS
            },
        )

        phase_2 = self._load(
            "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json"
        )
        phase_1 = self._load(SV18_PHASE_1_SUCCESSOR_SOURCE)
        for field in (
            "stable_key",
            "name",
            "country",
            "address",
            "roles",
            "coordinates",
            "geometry",
            "as_of_date",
            "method",
            "confidence",
        ):
            self.assertEqual(phase_1["campus"][field], phase_2["campus"][field])
        self.assertNotEqual(
            phase_1["project"]["stable_key"],
            phase_2["project"]["stable_key"],
        )
        successor_evidence = phase_1["evidence"][0]
        self.assertEqual(successor_evidence["key"], REMAINING14_EVIDENCE_KEY)
        self.assertEqual(
            successor_evidence["metadata"]["corroboration_group_id"],
            CORROBORATION_GROUP_ID,
        )
        self.assertIs(
            successor_evidence["metadata"]["independent_factual_corroboration"],
            False,
        )

        definition = json.loads(V35_DEFINITION.read_text(encoding="utf-8"))
        v35_paths = {record["path"] for record in definition["curated_inputs"]}
        self.assertTrue(
            {f"sources/{name}" for name in SOURCES}.isdisjoint(v35_paths)
        )
        v35_keys: set[str] = set()
        for record in definition["curated_inputs"]:
            document = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None:
                    v35_keys.add(entity["stable_key"])
        self.assertTrue(NEW_ENTITY_KEYS.isdisjoint(v35_keys))

    def test_forward_reverse_and_repeated_offline_imports_are_invariant(self) -> None:
        forward = self._database_state(SOURCES)
        reverse = self._database_state(tuple(reversed(SOURCES)))
        repeated_forward = self._database_state(SOURCES, repeat=2)
        repeated_reverse = self._database_state(tuple(reversed(SOURCES)), repeat=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated_forward)
        self.assertEqual(forward, repeated_reverse)
        entities, evidence, lifecycle, snapshots, models, workloads, capacities = forward
        self.assertEqual(len(entities), 16)
        self.assertEqual(
            {
                kind: sum(row[0] == kind for row in entities)
                for kind in ("campus", "project")
            },
            {"campus": 8, "project": 8},
        )
        self.assertEqual({row[1] for row in entities}, NEW_ENTITY_KEYS)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(lifecycle), 8)
        self.assertEqual(len(snapshots), 16)
        self.assertTrue(all(row[2] is None and row[3] is None for row in snapshots))
        self.assertTrue(all(row[4] is None for row in snapshots))
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(capacities, ())

    def test_individual_imports_are_paired_and_idempotent(self) -> None:
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
                        [
                            tuple(row)
                            for row in connection.execute(
                                "SELECT status, as_of_date, method "
                                "FROM lifecycle_observations"
                            )
                        ],
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

    def test_exact_delta_after_v35_curated_inputs(self) -> None:
        definition = json.loads(V35_DEFINITION.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for record in definition["curated_inputs"]:
                        source = ROOT / record["path"]
                        self.assertEqual(
                            hashlib.sha256(source.read_bytes()).hexdigest(),
                            record["sha256"],
                        )
                        document = json.loads(source.read_text(encoding="utf-8"))
                        retrieved = {row["retrieved_at"] for row in document["evidence"]}
                        self.assertEqual(len(retrieved), 1)
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source,
                            retrieved_at=next(iter(retrieved)),
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
                        "entities": 16,
                        "evidence": 1,
                        "entity_snapshots": 16,
                        "lifecycle_observations": 8,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    },
                )
                self.assertEqual(sum(result.entities_created for result in results), 16)
                self.assertEqual(sum(result.evidence_created for result in results), 1)
                self.assertTrue(
                    NEW_ENTITY_KEYS
                    <= {
                        row[0]
                        for row in connection.execute("SELECT stable_key FROM entities")
                    }
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "JOIN entities ON entities.id = entity_snapshots.entity_id "
                        f"WHERE entities.stable_key IN ({','.join('?' for _ in NEW_ENTITY_KEYS)}) "
                        "AND (latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL)",
                        tuple(sorted(NEW_ENTITY_KEYS)),
                    ).fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_semantic_source_mutations_fail_closed(self) -> None:
        name = SOURCES[0]
        original = self._load(name)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(original)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(("status", mutated))

        mutated = copy.deepcopy(original)
        mutated["lifecycle"][0]["as_of_date"] = "2026-07-20"
        mutations.append(("as_of", mutated))

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["metadata"]["target_projects_as_reported"][0][
            "target_open_quarter"
        ] = "2026-09-30"
        mutations.append(("target_exactification", mutated))

        mutated = copy.deepcopy(original)
        mutated["capacities"] = [
            self._invalid_capacity("critical_it_mw", 475, "Cabinets miscast as MW.")
        ]
        mutations.append(("cabinet_as_mw", mutated))

        mutated = copy.deepcopy(original)
        mutated["capacities"] = [
            self._invalid_capacity("gross_facility_mw", 59, "Capex miscast as power.")
        ]
        mutations.append(("capex_as_power", mutated))

        mutated = copy.deepcopy(original)
        mutated["project"]["coordinates"] = {
            "latitude": 25.7617,
            "longitude": -80.1918,
        }
        mutations.append(("coordinates", mutated))

        mutated = copy.deepcopy(original)
        mutated["campus"]["roles"] = {"operator": ["Equinix"]}
        mutations.append(("roles", mutated))

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["content_hash"] = "0" * 64
        mutations.append(("content_hash", mutated))

        for label, mutation in mutations:
            with self.subTest(label=label), self.assertRaises(AssertionError):
                self._assert_document(name, mutation)

    def _invalid_capacity(
        self, metric: str, value: float, notes: str
    ) -> dict[str, Any]:
        return {
            "entity": "project",
            "metric": metric,
            "stage": "planned",
            "unit": "MW",
            "low": value,
            "base": value,
            "high": value,
            "method": "reported",
            "confidence": 0.99,
            "evidence_key": EVIDENCE_KEY,
            "as_of_date": AS_OF_DATE,
            "target_date": None,
            "notes": notes,
        }

    def _nested_keys(self, value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                nested
                for child in value.values()
                for nested in self._nested_keys(child)
            }
        if isinstance(value, list):
            return {
                nested for child in value for nested in self._nested_keys(child)
            }
        return set()

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
