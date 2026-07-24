from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import export_geojson, validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T02:20:07Z"
AS_OF_DATE = "2025-12-31"
PRIMARY_URL = (
    "https://www.sec.gov/Archives/edgar/data/1101239/"
    "000110123926000075/EQIXAnnualRpt2025PRINT.pdf"
)
BODY_SHA256 = "2fdbe45af04ff1513a1dba3851cf3ed4d181edbf2561e193176e728a3437760c"
BODY_BYTES = 12_696_866
HEADERS_SHA256 = (
    "4d8e5dc4b2123868027f592e72a52631bb49d601c8e430e64439008de1a1b205"
)
HEADERS_BYTES = 686
WRITEOUT_SHA256 = (
    "61af1bfe6e2b2b9a8dfa71f869e7b90c85ccd10154b1bfe1081297a9e09ae3ae"
)
WRITEOUT_BYTES = 15_157
USER_AGENT = "Judgment Labs Data Center Atlas research kian@judgmentlabs.ai"
EVIDENCE_KEY = (
    "equinix-2025-annual-report-emea-twelve-ars-pdf-sec-captured-2026-07-20"
)
AMERICAS_EVIDENCE_KEY = (
    "equinix-2025-form-10-k-americas-eight-complete-submission-sec-"
    "captured-2026-07-20"
)
AMERICAS_BODY_SHA256 = (
    "08404c4984e2dc86e78f64580e14277c727d8d49a2de87a303267ed6661497d4"
)
INLINE_XBRL_HTML_BODY_SHA256 = (
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
)
RAW_EVIDENCE_BYTES = 11_846
RAW_EVIDENCE_SHA256 = (
    "eb44784068674ec7bc04293e8ca6ab52594e3f60e8bdcdda370f385fee40ed72"
)
REMAINING14_EVIDENCE_KEY = (
    "equinix-2025-annual-report-fourteen-remaining-table-rows-ars-pdf-sec-"
    "captured-2026-07-20"
)
CORROBORATION_GROUP_ID = (
    "equinix-sec-0001101239-26-000032-construction-table-2025-12-31"
)
REMAINING14_SOURCES = frozenset(
    {
        "curated-official-2026-07-20-equinix-ny11-new-york-phase-5.json",
        "curated-official-2026-07-20-equinix-bg2-bogota-phase-2.json",
        "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-1.json",
        "curated-official-2026-07-20-equinix-lg3-lagos-phase-1.json",
        "curated-official-2026-07-20-equinix-dx3-dubai-phase-2.json",
        "curated-official-2026-07-20-equinix-md5-madrid-phase-1.json",
        "curated-official-2026-07-20-equinix-hk6-hong-kong-phase-1.json",
        "curated-official-2026-07-20-equinix-os3-osaka-phase-4.json",
        "curated-official-2026-07-20-equinix-jk1-jakarta-phase-2.json",
        "curated-official-2026-07-20-equinix-sy5-sydney-phase-4.json",
        "curated-official-2026-07-20-equinix-kl2-kuala-lumpur-phases-1-2.json",
        "curated-official-2026-07-20-equinix-mb3-mumbai-phase-2.json",
        "curated-official-2026-07-20-equinix-cn1-chennai-phase-2.json",
        "curated-official-2026-07-20-equinix-os6-osaka-phase-1.json",
    }
)

SOURCE_SPECS: dict[str, dict[str, str]] = {
    "curated-official-2026-07-20-equinix-il3-istanbul-phase-1.json": {
        "sha256": "280437e92dedd7337d6470ce6f6fdea6c8e41db44abea51e85ec0d98cfc59ac9",
        "country": "Türkiye",
        "address": "Istanbul, Türkiye",
        "campus_key": "curated:equinix-il3-istanbul-data-center",
        "campus_name": "Equinix IL3 Istanbul Data Center",
        "project_key": "curated:equinix-il3-istanbul-data-center:phase-1",
        "project_name": "Equinix IL3 Phase 1",
    },
    "curated-official-2026-07-20-equinix-fr8-frankfurt-phase-3.json": {
        "sha256": "bafbaf95eda8734be62fa461bbe7de16ccf5d5b42740f9a39962253fb6049101",
        "country": "Germany",
        "address": "Frankfurt, Germany",
        "campus_key": "curated:equinix-fr8-frankfurt-data-center",
        "campus_name": "Equinix FR8 Frankfurt Data Center",
        "project_key": "curated:equinix-fr8-frankfurt-data-center:phase-3",
        "project_name": "Equinix FR8 Phase 3",
    },
    "curated-official-2026-07-20-equinix-ld14-london-phase-1.json": {
        "sha256": "7efc590aaf649df2a5ea583a00a80444a545dea7459f42322937575dfad56c7e",
        "country": "United Kingdom",
        "address": "London, United Kingdom",
        "campus_key": "curated:equinix-ld14-london-data-center",
        "campus_name": "Equinix LD14 London Data Center",
        "project_key": "curated:equinix-ld14-london-data-center:phase-1",
        "project_name": "Equinix LD14 Phase 1",
    },
    "curated-official-2026-07-20-equinix-pa14-paris-phase-1.json": {
        "sha256": "3eb12e0bf27c9a864918edba309ba9c6a7221d7a9529d3f7e3ef70c0178b5b40",
        "country": "France",
        "address": "Paris, France",
        "campus_key": "curated:equinix-pa14-paris-data-center",
        "campus_name": "Equinix PA14 Paris Data Center",
        "project_key": "curated:equinix-pa14-paris-data-center:phase-1",
        "project_name": "Equinix PA14 Phase 1",
    },
    "curated-official-2026-07-20-equinix-ls2-lisbon-phase-2.json": {
        "sha256": "b94b174c09d7f027e5035d46d9ba0df0a6d9ea234bb40f787b1e3bffc330c898",
        "country": "Portugal",
        "address": "Lisbon, Portugal",
        "campus_key": "curated:equinix-ls2-lisbon-data-center",
        "campus_name": "Equinix LS2 Lisbon Data Center",
        "project_key": "curated:equinix-ls2-lisbon-data-center:phase-2",
        "project_name": "Equinix LS2 Phase 2",
    },
    "curated-official-2026-07-20-equinix-zh4-zurich-phase-6.json": {
        "sha256": "e7c0ee0403a66e4cda73045b4f0d3aa29f2bfa0ebb7661593d3ae34fe7f94b89",
        "country": "Switzerland",
        "address": "Zurich, Switzerland",
        "campus_key": "curated:equinix-zh4-zurich-data-center",
        "campus_name": "Equinix ZH4 Zurich Data Center",
        "project_key": "curated:equinix-zh4-zurich-data-center:phase-6",
        "project_name": "Equinix ZH4 Phase 6",
    },
    "curated-official-2026-07-20-equinix-db10-dublin-phase-1.json": {
        "sha256": "7502b721023c981cc8e6ee92e8a12d8545bb769b539d7f8bbc51fa84bad026b9",
        "country": "Ireland",
        "address": "Dublin, Ireland",
        "campus_key": "curated:equinix-db10-dublin-data-center",
        "campus_name": "Equinix DB10 Dublin Data Center",
        "project_key": "curated:equinix-db10-dublin-data-center:phase-1",
        "project_name": "Equinix DB10 Phase 1",
    },
    "curated-official-2026-07-20-equinix-ld14-london-phase-2.json": {
        "sha256": "1fc10cc8b1ab18e293815854f0265d6e74342537246f17e7f2b8b39d864226ff",
        "country": "United Kingdom",
        "address": "London, United Kingdom",
        "campus_key": "curated:equinix-ld14-london-data-center",
        "campus_name": "Equinix LD14 London Data Center",
        "project_key": "curated:equinix-ld14-london-data-center:phase-2",
        "project_name": "Equinix LD14 Phase 2",
    },
    "curated-official-2026-07-20-equinix-fr12-frankfurt-phase-1.json": {
        "sha256": "3aa3ad9100adc25c0ab54064c6395763da29162f9200899e5fc7e735f9f0f4ba",
        "country": "Germany",
        "address": "Frankfurt, Germany",
        "campus_key": "curated:equinix-fr12-frankfurt-data-center",
        "campus_name": "Equinix FR12 Frankfurt Data Center",
        "project_key": "curated:equinix-fr12-frankfurt-data-center:phase-1",
        "project_name": "Equinix FR12 Phase 1",
    },
    "curated-official-2026-07-20-equinix-mu4-munich-phase-3.json": {
        "sha256": "bdd5a3b404a5a628694db043735cdafb4bf72604b20887bd49ce0de751623c6f",
        "country": "Germany",
        "address": "Munich, Germany",
        "campus_key": "curated:equinix-mu4-munich-data-center",
        "campus_name": "Equinix MU4 Munich Data Center",
        "project_key": "curated:equinix-mu4-munich-data-center:phase-3",
        "project_name": "Equinix MU4 Phase 3",
    },
    "curated-official-2026-07-20-equinix-pa14-paris-phase-2.json": {
        "sha256": "d5ae344b2980c9ae803e9466ab5317faae97e010dbab9978ccd165b9872d9f7d",
        "country": "France",
        "address": "Paris, France",
        "campus_key": "curated:equinix-pa14-paris-data-center",
        "campus_name": "Equinix PA14 Paris Data Center",
        "project_key": "curated:equinix-pa14-paris-data-center:phase-2",
        "project_name": "Equinix PA14 Phase 2",
    },
    "curated-official-2026-07-20-equinix-fr15-frankfurt-phase-1.json": {
        "sha256": "6d098ebd0a18fb5ceb6c5c98781be2c4c40f2f617f4989e0841cdacfc81631db",
        "country": "Germany",
        "address": "Frankfurt, Germany",
        "campus_key": "curated:equinix-fr15-frankfurt-data-center",
        "campus_name": "Equinix FR15 Frankfurt Data Center",
        "project_key": "curated:equinix-fr15-frankfurt-data-center:phase-1",
        "project_name": "Equinix FR15 Phase 1",
    },
}
SOURCES = tuple(SOURCE_SPECS)
AMERICAS_SOURCES = (
    "curated-official-2026-07-20-equinix-mi1-miami-redevelopment.json",
    "curated-official-2026-07-20-equinix-mt1-montreal-phase-3.json",
    "curated-official-2026-07-20-equinix-dc17-washington-dc-phases-1-2.json",
    "curated-official-2026-07-20-equinix-dc22-washington-dc-phase-2.json",
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json",
    "curated-official-2026-07-20-equinix-tr6-toronto-phase-3.json",
    "curated-official-2026-07-20-equinix-ch5-chicago-phase-2.json",
    "curated-official-2026-07-20-equinix-da12-dallas-phase-1.json",
)
NEW_CAMPUS_KEYS = {spec["campus_key"] for spec in SOURCE_SPECS.values()}
NEW_PROJECT_KEYS = {spec["project_key"] for spec in SOURCE_SPECS.values()}
NEW_ENTITY_KEYS = NEW_CAMPUS_KEYS | NEW_PROJECT_KEYS
MU4_TEMPORAL_SUCCESSOR = (
    "curated-official-2026-07-20-equinix-mu4-munich-phase-3-topout.json"
)
MU4_TEMPORAL_REUSE = {
    "curated:equinix-mu4-munich-data-center": {MU4_TEMPORAL_SUCCESSOR},
    "curated:equinix-mu4-munich-data-center:phase-3": {MU4_TEMPORAL_SUCCESSOR},
}
EXPECTED_TABLE_ROWS = [
    {
        "property": "IL3 phase 1",
        "location": "Istanbul",
        "target_open_quarter": "Q3 2026",
        "sellable_cabinets": 1325,
        "approximate_total_capex_usd_millions": 116,
    },
    {
        "property": "FR8 phase 3",
        "location": "Frankfurt",
        "target_open_quarter": "Q4 2026",
        "sellable_cabinets": 1400,
        "approximate_total_capex_usd_millions": 107,
    },
    {
        "property": "LD14 phase 1",
        "location": "London",
        "target_open_quarter": "Q1 2027",
        "sellable_cabinets": 1425,
        "approximate_total_capex_usd_millions": 242,
    },
    {
        "property": "PA14 phase 1",
        "location": "Paris",
        "target_open_quarter": "Q2 2027",
        "sellable_cabinets": 675,
        "approximate_total_capex_usd_millions": 104,
    },
    {
        "property": "LS2 phase 2",
        "location": "Lisbon",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 325,
        "approximate_total_capex_usd_millions": 31,
    },
    {
        "property": "ZH4 phase 6",
        "location": "Zurich",
        "target_open_quarter": "Q3 2027",
        "sellable_cabinets": 200,
        "approximate_total_capex_usd_millions": 47,
    },
    {
        "property": "DB10 phase 1",
        "location": "Dublin",
        "target_open_quarter": "Q1 2028",
        "sellable_cabinets": 475,
        "approximate_total_capex_usd_millions": 14,
    },
    {
        "property": "LD14 phase 2",
        "location": "London",
        "target_open_quarter": "Q1 2028",
        "sellable_cabinets": 1425,
        "approximate_total_capex_usd_millions": 122,
    },
    {
        "property": "FR12 phase 1",
        "location": "Frankfurt",
        "target_open_quarter": "Q2 2028",
        "sellable_cabinets": 1750,
        "approximate_total_capex_usd_millions": 381,
    },
    {
        "property": "MU4 phase 3",
        "location": "Munich",
        "target_open_quarter": "Q2 2028",
        "sellable_cabinets": 1375,
        "approximate_total_capex_usd_millions": 342,
    },
    {
        "property": "PA14 phase 2",
        "location": "Paris",
        "target_open_quarter": "Q2 2028",
        "sellable_cabinets": 600,
        "approximate_total_capex_usd_millions": 49,
    },
    {
        "property": "FR15 phase 1",
        "location": "Frankfurt",
        "target_open_quarter": "Q3 2028",
        "sellable_cabinets": 1550,
        "approximate_total_capex_usd_millions": 487,
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
    "ars_filing_accession",
    "ars_primary_document_filename",
    "ars_filing_date",
    "ars_accepted_at_as_reported",
    "ars_period_of_report",
    "pdf_file_page_count",
    "target_table_pdf_file_page",
    "target_table_printed_page",
    "target_table_capture_scope",
    "underlying_source_identity",
    "americas_complete_submission_evidence_key",
    "americas_complete_submission_body_sha256",
    "inline_xbrl_html_body_sha256",
    "source_artifact_distinction",
    "regional_observation_scope",
    "embedded_form_10_k_original_filing_date",
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


class EquinixEmea10KTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _raw_evidence(self, name: str) -> bytes:
        raw = (ROOT / "sources" / name).read_bytes()
        start_marker = b'  "evidence": [\n'
        end_marker = b'\n  ],\n  "campus": {'
        start = raw.index(start_marker) + len(start_marker)
        end = raw.index(end_marker, start)
        return raw[start:end]

    def _retrieved_at(self, name: str) -> str:
        values = {row["retrieved_at"] for row in self._load(name)["evidence"]}
        self.assertEqual(len(values), 1)
        return next(iter(values))

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
        self.assertEqual(
            evidence["title"], "Equinix 2025 Annual Report to Security Holders"
        )
        self.assertEqual(evidence["source_url"], PRIMARY_URL)
        self.assertEqual(evidence["publisher"], "Equinix, Inc.")
        self.assertEqual(evidence["source_family"], "equinix_sec_filings")
        self.assertEqual(evidence["published_at"], "2026-04-02")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(evidence["attribution"], "Equinix, Inc.")
        self.assertEqual(evidence["content_hash"], BODY_SHA256)

        metadata = evidence["metadata"]
        self.assertEqual(set(metadata), EXPECTED_METADATA_KEYS)
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(BODY_BYTES), metadata["content_hash_scope"])
        self.assertIn(str(HEADERS_BYTES), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertIn(str(WRITEOUT_BYTES), metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)
        self.assertEqual(metadata["request_user_agent"], USER_AGENT)
        for forbidden in ("Authorization", "Proxy-Authorization", "Cookie"):
            self.assertIn(forbidden, metadata["request_credentials_guardrail"])
        self.assertIn(
            "no authentication option", metadata["request_credentials_guardrail"]
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertIsNone(metadata["content_encoding_as_received"])
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"], BODY_BYTES
        )
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], BODY_BYTES)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], "2026-04-02T20:42:53Z")
        self.assertEqual(metadata["response_set_cookie_header_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], PRIMARY_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["http_version"], "2")
        self.assertEqual(metadata["form_type"], "ARS")
        self.assertEqual(metadata["ars_filing_accession"], "0001101239-26-000075")
        self.assertEqual(
            metadata["ars_primary_document_filename"], "EQIXAnnualRpt2025PRINT.pdf"
        )
        self.assertEqual(metadata["ars_filing_date"], "2026-04-02")
        self.assertEqual(
            metadata["ars_accepted_at_as_reported"], "2026-04-02 16:42:14"
        )
        self.assertEqual(metadata["ars_period_of_report"], AS_OF_DATE)
        self.assertEqual(metadata["pdf_file_page_count"], 162)
        self.assertEqual(metadata["target_table_pdf_file_page"], 61)
        self.assertEqual(metadata["target_table_printed_page"], 44)
        self.assertIn("Direct visual inspection", metadata["target_table_capture_scope"])
        self.assertIn("file page 61", metadata["target_table_capture_scope"])
        self.assertEqual(
            metadata["embedded_form_10_k_original_filing_date"], "2026-02-11"
        )
        self.assertEqual(metadata["fiscal_year_end"], AS_OF_DATE)
        self.assertEqual(metadata["construction_table_as_of_date"], AS_OF_DATE)
        self.assertEqual(
            metadata["construction_table_heading_as_reported"],
            "significant IBX data center projects under construction as of "
            "December 31, 2025",
        )
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)
        self.assertEqual(
            metadata["americas_complete_submission_evidence_key"],
            AMERICAS_EVIDENCE_KEY,
        )
        self.assertEqual(
            metadata["americas_complete_submission_body_sha256"],
            AMERICAS_BODY_SHA256,
        )
        self.assertEqual(
            metadata["inline_xbrl_html_body_sha256"],
            INLINE_XBRL_HTML_BODY_SHA256,
        )
        self.assertNotIn(
            BODY_SHA256,
            {AMERICAS_BODY_SHA256, INLINE_XBRL_HTML_BODY_SHA256},
        )
        self.assertIn("distinct official artifact", metadata["source_artifact_distinction"])
        self.assertIn(
            "not counted as independent factual corroboration",
            metadata["source_artifact_distinction"],
        )
        self.assertIn(
            "no Americas", metadata["regional_observation_scope"]
        )

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
        self.assertTrue(
            {
                "target_open_quarter",
                "sellable_cabinets",
                "approximate_total_capex_usd_millions",
                "target_date",
                "unique_site_count",
            }.isdisjoint(self._nested_keys(non_evidence))
        )

    def _offline(self) -> ExitStack:
        offline = AssertionError("curated source import attempted network access")
        stack = ExitStack()
        for target in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, target, side_effect=offline))
        return stack

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
                                retrieved_at=self._retrieved_at(name),
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
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json FROM entity_snapshots JOIN entities "
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

    def test_exact_hashes_canonical_json_and_byte_identical_evidence(self) -> None:
        self.assertEqual(len(SOURCES), 12)
        self.assertEqual(len(NEW_CAMPUS_KEYS), 10)
        self.assertEqual(len(NEW_PROJECT_KEYS), 12)
        self.assertEqual(len(NEW_ENTITY_KEYS), 22)

        raw_evidence: list[bytes] = []
        documents: list[dict[str, Any]] = []
        for name, expected in SOURCE_SPECS.items():
            source = ROOT / "sources" / name
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), expected["sha256"]
            )
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
        self.assertEqual(hashlib.sha256(raw_evidence[0]).hexdigest(), RAW_EVIDENCE_SHA256)

    def test_exact_rows_historical_scope_and_phase_topology(self) -> None:
        metadata = self._load(SOURCES[0])["evidence"][0]["metadata"]
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_TABLE_ROWS)
        self.assertTrue(
            {row["property"] for row in EXPECTED_TABLE_ROWS}.isdisjoint(
                {"LG3 phase 1", "DX3 phase 2", "MD5 phase 1", "LG4 phase 1"}
            )
        )
        self.assertEqual(
            [row["target_open_quarter"] for row in EXPECTED_TABLE_ROWS],
            [
                "Q3 2026",
                "Q4 2026",
                "Q1 2027",
                "Q2 2027",
                "Q3 2027",
                "Q3 2027",
                "Q1 2028",
                "Q1 2028",
                "Q2 2028",
                "Q2 2028",
                "Q2 2028",
                "Q3 2028",
            ],
        )
        self.assertTrue(all("Q" in row["target_open_quarter"] for row in EXPECTED_TABLE_ROWS))
        self.assertIn("historical status", metadata["historical_status_guardrail"])
        self.assertIn("does not prove", metadata["historical_status_guardrail"])
        self.assertIn("not an exact date", metadata["target_date_guardrail"])
        self.assertIn("not MW", metadata["cabinet_guardrail"])
        self.assertIn("not power", metadata["capex_guardrail"])
        self.assertIn("no capacity row", metadata["capacity_guardrail"])
        self.assertIn("no project-specific PUE", metadata["energy_guardrail"])
        self.assertIn("not normalized", metadata["role_guardrail"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

        campus_counts = Counter(spec["campus_key"] for spec in SOURCE_SPECS.values())
        self.assertEqual(campus_counts["curated:equinix-ld14-london-data-center"], 2)
        self.assertEqual(campus_counts["curated:equinix-pa14-paris-data-center"], 2)
        self.assertTrue(
            all(
                count == 1
                for key, count in campus_counts.items()
                if key
                not in {
                    "curated:equinix-ld14-london-data-center",
                    "curated:equinix-pa14-paris-data-center",
                }
            )
        )
        self.assertEqual(
            {
                spec["project_key"]
                for spec in SOURCE_SPECS.values()
                if ":equinix-ld14-" in spec["project_key"]
            },
            {
                "curated:equinix-ld14-london-data-center:phase-1",
                "curated:equinix-ld14-london-data-center:phase-2",
            },
        )
        self.assertEqual(
            {
                spec["project_key"]
                for spec in SOURCE_SPECS.values()
                if ":equinix-pa14-" in spec["project_key"]
            },
            {
                "curated:equinix-pa14-paris-data-center:phase-1",
                "curated:equinix-pa14-paris-data-center:phase-2",
            },
        )
        self.assertIn("share one campus entity", metadata["location_guardrail"])
        self.assertIn("distinct project entities", metadata["location_guardrail"])
        self.assertIn("unique-site counts", metadata["location_guardrail"])

    def test_il3_uses_source_canonical_turkiye_and_emits_iso_codes(self) -> None:
        name = "curated-official-2026-07-20-equinix-il3-istanbul-phase-1.json"
        document = self._load(name)
        for entity_name in ("campus", "project"):
            self.assertEqual(document[entity_name]["country"], "Türkiye")
            self.assertEqual(document[entity_name]["address"], "Istanbul, Türkiye")

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=RETRIEVED_AT,
                    )
                features = export_geojson(
                    connection,
                    as_of=AS_OF_DATE,
                    recorded_at=RETRIEVED_AT,
                )["features"]
                self.assertEqual(len(features), 2)
                for feature in features:
                    properties = feature["properties"]
                    self.assertEqual(properties["source_country_tag"], "Türkiye")
                    self.assertEqual(properties["country"], "Türkiye")
                    self.assertEqual(properties["country_iso_a2"], "TR")
                    self.assertEqual(properties["country_iso_a3"], "TUR")
            finally:
                connection.close()

    def test_no_entity_or_evidence_key_collision_and_pdf_artifact_is_distinct(self) -> None:
        selected = {(ROOT / "sources" / name).resolve() for name in SOURCES}
        other_entity_keys: dict[str, list[str]] = {}
        other_evidence_keys: dict[str, list[str]] = {}
        body_hash_sources: set[str] = set()
        americas_body_hash_sources: set[str] = set()
        americas_key_sources: set[str] = set()
        for source in sorted((ROOT / "sources").glob("curated-official*.json")):
            if source.resolve() in selected:
                continue
            document = json.loads(source.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None:
                    other_entity_keys.setdefault(entity["stable_key"], []).append(source.name)
            for evidence in document.get("evidence", []):
                other_evidence_keys.setdefault(evidence["key"], []).append(source.name)
                if evidence["content_hash"] == BODY_SHA256:
                    body_hash_sources.add(source.name)
                if evidence["content_hash"] == AMERICAS_BODY_SHA256:
                    americas_body_hash_sources.add(source.name)
                if evidence["key"] == AMERICAS_EVIDENCE_KEY:
                    americas_key_sources.add(source.name)

        collisions = {
            key: set(other_entity_keys[key])
            for key in NEW_ENTITY_KEYS
            if key in other_entity_keys
        }
        self.assertEqual(collisions, MU4_TEMPORAL_REUSE)
        self.assertNotIn(EVIDENCE_KEY, other_evidence_keys)
        self.assertEqual(body_hash_sources, set(REMAINING14_SOURCES))
        self.assertEqual(
            set(other_evidence_keys[REMAINING14_EVIDENCE_KEY]),
            set(REMAINING14_SOURCES),
        )
        for source_name in REMAINING14_SOURCES:
            successor = self._load(source_name)["evidence"][0]
            self.assertEqual(successor["key"], REMAINING14_EVIDENCE_KEY)
            self.assertEqual(successor["content_hash"], BODY_SHA256)
            self.assertEqual(
                successor["metadata"]["corroboration_group_id"],
                CORROBORATION_GROUP_ID,
            )
            self.assertIs(
                successor["metadata"]["independent_factual_corroboration"],
                False,
            )
            self.assertEqual(
                len(successor["metadata"]["target_projects_as_reported"]),
                14,
            )
            self.assertIn(
                "same underlying Equinix 2025 Form 10-K construction table",
                successor["metadata"]["source_artifact_distinction"],
            )
            self.assertIn(
                "not independent factual corroboration",
                successor["metadata"]["source_artifact_distinction"],
            )
        self.assertEqual(americas_body_hash_sources, set(AMERICAS_SOURCES))
        self.assertEqual(americas_key_sources, set(AMERICAS_SOURCES))
        self.assertNotEqual(EVIDENCE_KEY, AMERICAS_EVIDENCE_KEY)
        self.assertNotEqual(BODY_SHA256, AMERICAS_BODY_SHA256)
        self.assertNotEqual(BODY_SHA256, INLINE_XBRL_HTML_BODY_SHA256)

        metadata = self._load(SOURCES[0])["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["americas_complete_submission_evidence_key"],
            AMERICAS_EVIDENCE_KEY,
        )
        self.assertIn("distinct official artifact", metadata["source_artifact_distinction"])
        self.assertIn(
            "not counted as independent factual corroboration",
            metadata["source_artifact_distinction"],
        )

    def test_forward_reverse_repeated_and_cross_artifact_imports_are_invariant(self) -> None:
        forward = self._database_state(SOURCES)
        reverse = self._database_state(tuple(reversed(SOURCES)))
        repeated = self._database_state(SOURCES, repeat=2)
        combined = AMERICAS_SOURCES + SOURCES
        combined_reverse = tuple(reversed(combined))
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)
        self.assertEqual(
            self._database_state(combined), self._database_state(combined_reverse)
        )

        entities, evidence, lifecycle, snapshots, models, workloads, capacities = forward
        self.assertEqual(len(entities), 22)
        self.assertEqual(Counter(row[0] for row in entities), {"campus": 10, "project": 12})
        self.assertEqual({row[1] for row in entities}, NEW_ENTITY_KEYS)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0][2], BODY_SHA256)
        self.assertEqual(len(lifecycle), 12)
        self.assertTrue(all(row[1:] == ("under_construction", AS_OF_DATE, "authoritative_physical_status_update") for row in lifecycle))
        self.assertEqual(len(snapshots), 22)
        self.assertTrue(all(row[1] is None and row[2] is None for row in snapshots))
        self.assertTrue(all(row[3] is None for row in snapshots))
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(capacities, ())

        combined_evidence = self._database_state(combined)[1]
        self.assertEqual(len(combined_evidence), 2)
        self.assertEqual(
            {row[2] for row in combined_evidence},
            {BODY_SHA256, AMERICAS_BODY_SHA256},
        )
        metadata_rows = [json.loads(row[3]) for row in combined_evidence]
        self.assertEqual(
            {
                row["record"].get("americas_complete_submission_evidence_key")
                for row in metadata_rows
            },
            {None, AMERICAS_EVIDENCE_KEY},
        )

    def test_exact_delta_after_completed_americas_tranche(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for name in AMERICAS_SOURCES:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=self._retrieved_at(name),
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
                        "entities": 22,
                        "evidence": 1,
                        "entity_snapshots": 22,
                        "lifecycle_observations": 12,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    },
                )
                self.assertEqual(sum(result.entities_created for result in results), 22)
                self.assertEqual(sum(result.evidence_created for result in results), 1)
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE content_hash = ?",
                        (BODY_SHA256,),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE content_hash = ?",
                        (AMERICAS_BODY_SHA256,),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entities WHERE kind = 'campus' AND "
                        "stable_key IN (?, ?)",
                        (
                            "curated:equinix-ld14-london-data-center",
                            "curated:equinix-pa14-paris-data-center",
                        ),
                    ).fetchone()[0],
                    2,
                )
            finally:
                connection.close()

    def test_individual_imports_and_semantic_mutations_fail_closed(self) -> None:
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
                        {row[0] for row in connection.execute("SELECT stable_key FROM entities")},
                        {expected["campus_key"], expected["project_key"]},
                    )
                finally:
                    connection.close()

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
            self._invalid_capacity("critical_it_mw", 1325, "Cabinets miscast as MW.")
        ]
        mutations.append(("cabinet_as_mw", mutated))

        mutated = copy.deepcopy(original)
        mutated["capacities"] = [
            self._invalid_capacity("gross_facility_mw", 116, "Capex miscast as power.")
        ]
        mutations.append(("capex_as_power", mutated))

        mutated = copy.deepcopy(original)
        mutated["project"]["coordinates"] = {"latitude": 41.0082, "longitude": 28.9784}
        mutations.append(("coordinates", mutated))

        mutated = copy.deepcopy(original)
        mutated["campus"]["roles"] = {"operator": ["Equinix"]}
        mutations.append(("roles", mutated))

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
        mutations.append(("operating_model", mutated))

        mutated = copy.deepcopy(original)
        mutated["evidence"][0]["metadata"][
            "americas_complete_submission_body_sha256"
        ] = BODY_SHA256
        mutations.append(("fake_distinct_capture", mutated))

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
            return {nested for child in value for nested in self._nested_keys(child)}
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


if __name__ == "__main__":
    unittest.main()
