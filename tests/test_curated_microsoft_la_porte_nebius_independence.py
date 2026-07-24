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


ROOT = Path(__file__).parents[1]
BASE_DEFINITION = "open-seed-2026-07-19-v20.json"
BASE_DEFINITION_SHA256 = (
    "099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd"
)

MICROSOFT_SOURCE = (
    "curated-official-2026-07-19-microsoft-la-porte-indiana-first-phase.json"
)
MICROSOFT_SOURCE_SHA256 = (
    "557eaac082951d41037343a668d796c6eb1e31e5c895d10597efdaac9a8c9c1d"
)
NEBIUS_SOURCE = (
    "curated-official-2026-07-19-nebius-independence-missouri-phase-1.json"
)
NEBIUS_SOURCE_SHA256 = (
    "366ed041e837c8d28398e8e1868175e979af2297a7bdfe55a914cfbfe6db6ccf"
)

MICROSOFT_RETRIEVED_AT = "2026-07-19T20:46:28Z"
NEBIUS_RETRIEVED_AT = "2026-07-19T20:47:50Z"

MICROSOFT_CAMPUS = "curated:microsoft-la-porte-indiana-campus"
MICROSOFT_PROJECT = (
    "curated:microsoft-la-porte-indiana-campus:first-phase-current-build"
)
NEBIUS_CAMPUS = "curated:nebius-independence-missouri-ai-factory-campus"
NEBIUS_PROJECT = (
    "curated:nebius-independence-missouri-ai-factory-campus:"
    "phase-1-current-build"
)

MICROSOFT_GROUNDBREAKING = (
    "microsoft-la-porte-groundbreaking-2026-06-18-captured-2026-07-19"
)
MICROSOFT_UPDATE = (
    "microsoft-la-porte-current-update-modified-2026-07-10-"
    "captured-2026-07-19"
)
NEBIUS_GROUNDBREAKING = (
    "nebius-independence-groundbreaking-2026-05-12-captured-2026-07-19"
)
NEBIUS_APPROVAL = (
    "nebius-independence-chapter-100-approval-2026-03-03-"
    "captured-2026-07-19"
)
NEBIUS_CITY_REPORT = (
    "independence-mo-may-2026-building-report-nebius-phase-1-"
    "captured-2026-07-19"
)

CAPTURES: dict[str, dict[str, Any]] = {
    MICROSOFT_GROUNDBREAKING: {
        "kind": "company_disclosure",
        "publisher": "Microsoft",
        "source_family": "microsoft_local_project_updates",
        "published_at": "2026-06-23T16:23:15+00:00",
        "retrieved_at": MICROSOFT_RETRIEVED_AT,
        "content_hash": (
            "e3a19166806b1c92bcb2fe4097cf590ea69657268c2d7e07454eb3a74560d67b"
        ),
        "body_bytes": 192757,
        "headers_bytes": 1056,
        "headers_hash": (
            "286edffe7ef86fa13480cdcc361f7295f9ee50df885e19aa6462758857f2c94b"
        ),
        "writeout_bytes": 216,
        "writeout_hash": (
            "1b94d23b4c667f89a02b726c126ce46b6219ca0f741feed0a00296732ed9c6cb"
        ),
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 27434,
        "response_date": "2026-07-19T20:46:28Z",
        "last_modified": None,
        "url": (
            "https://local.microsoft.com/blog/"
            "microsoft-breaks-ground-on-la-porte-datacenter-project/"
        ),
    },
    MICROSOFT_UPDATE: {
        "kind": "company_disclosure",
        "publisher": "Microsoft",
        "source_family": "microsoft_local_project_updates",
        "published_at": "2026-04-22T21:16:49+00:00",
        "retrieved_at": MICROSOFT_RETRIEVED_AT,
        "content_hash": (
            "6b62b800778e0899da39eabd0347112a2f4729f3eb4db09ba53532085350c57e"
        ),
        "body_bytes": 195405,
        "headers_bytes": 1057,
        "headers_hash": (
            "90a39eb8677d0917736b80c95fd438df909fbcacc7fd928a77ebd5d2274d583d"
        ),
        "writeout_bytes": 191,
        "writeout_hash": (
            "b7fb51239e831a722953f5614e5fb69c79152e1cf7ca47e136a06722bb8d5da1"
        ),
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 28144,
        "response_date": "2026-07-19T20:46:28Z",
        "last_modified": None,
        "url": "https://local.microsoft.com/blog/la-porte-public-meeting-recap/",
    },
    NEBIUS_GROUNDBREAKING: {
        "kind": "company_disclosure",
        "publisher": "Nebius",
        "source_family": "nebius_newsroom",
        "published_at": "2026-05-12",
        "retrieved_at": NEBIUS_RETRIEVED_AT,
        "content_hash": (
            "e48852f997daeb2f79ced15cf7c3bd31f4ef5e25e8a6880dbedbea84393739f7"
        ),
        "body_bytes": 280457,
        "headers_bytes": 7493,
        "headers_hash": (
            "862d0bdfa41d6330eba48e68791e38baf5c44ab0e9e60234a4ae2b6876266f42"
        ),
        "writeout_bytes": 231,
        "writeout_hash": (
            "36b850d24c81b2471b10c22e0da9a0a22aa12f18dd5d1721b14dbd71d9356e01"
        ),
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 57573,
        "response_date": "2026-07-19T20:47:21Z",
        "last_modified": None,
        "url": (
            "https://nebius.com/newsroom/nebius-breaks-ground-on-"
            "gigawatt-scale-ai-factory-in-independence-missouri"
        ),
    },
    NEBIUS_APPROVAL: {
        "kind": "company_disclosure",
        "publisher": "Nebius",
        "source_family": "nebius_newsroom",
        "published_at": "2026-03-03",
        "retrieved_at": NEBIUS_RETRIEVED_AT,
        "content_hash": (
            "b73ae86bfb3e35f8017364034694d7c370111bc9ea4892bc327c019d571bf0c8"
        ),
        "body_bytes": 271506,
        "headers_bytes": 7493,
        "headers_hash": (
            "de16277d3117a1eb93d0d190ce71c1fa87038a92ad03325dc325e0a4faae1f77"
        ),
        "writeout_bytes": 220,
        "writeout_hash": (
            "83b0383af96005b80651e551693c6b8f9f1d69813dd8b947e0d02e0f0d046bcd"
        ),
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 54727,
        "response_date": "2026-07-19T20:47:50Z",
        "last_modified": None,
        "url": (
            "https://nebius.com/newsroom/nebius-secures-approval-for-"
            "its-first-gigawatt-scale-ai-factory"
        ),
    },
    NEBIUS_CITY_REPORT: {
        "kind": "government_record",
        "publisher": "City of Independence, Missouri",
        "source_family": "independence_mo_monthly_building_permit_reports",
        "published_at": None,
        "retrieved_at": NEBIUS_RETRIEVED_AT,
        "content_hash": (
            "27eaeb89b231fc1a6bf77567dc299c2110f128047ccb1deeebff7f0cdc23a1f1"
        ),
        "body_bytes": 142902,
        "headers_bytes": 562,
        "headers_hash": (
            "450cdbdcb1103135ab1c58b157ad0b6e4710d7670d5e4d8b8cff61386fb5a65c"
        ),
        "writeout_bytes": 235,
        "writeout_hash": (
            "4180d9ba1e1b94bab99bc0cb250dd5675885daaca3412e7e65158ced5545fc97"
        ),
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 142902,
        "download_bytes": 142902,
        "response_date": "2026-07-19T20:47:20Z",
        "last_modified": "2026-06-01T20:53:22Z",
        "url": (
            "https://www.independencemo.gov/sites/default/files/2026-06/"
            "May%202026%20Monthly%20Building%20Permits%20Reports.pdf"
        ),
    },
}


class MicrosoftLaPorteNebiusIndependenceTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(
        self,
        evidence: dict[str, Any],
        expected: dict[str, Any],
    ) -> None:
        self.assertEqual(evidence["kind"], expected["kind"])
        self.assertEqual(evidence["publisher"], expected["publisher"])
        self.assertEqual(evidence["source_family"], expected["source_family"])
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], expected["retrieved_at"])
        self.assertEqual(evidence["content_hash"], expected["content_hash"])
        self.assertEqual(evidence["source_url"], expected["url"])

        metadata = evidence["metadata"]
        self.assertEqual(
            metadata["content_hash_verification"],
            "fetched_bytes_sha256",
        )
        self.assertIn(str(expected["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(
            str(expected["headers_bytes"]),
            metadata["capture_headers_scope"],
        )
        self.assertEqual(
            metadata["capture_headers_sha256"], expected["headers_hash"]
        )
        self.assertIn(
            str(expected["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            expected["writeout_hash"],
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertIn(
            "sensitive response-header value",
            metadata["capture_artifact_guardrail"],
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], expected["content_type"])
        self.assertEqual(
            metadata["content_encoding_as_received"],
            expected["content_encoding"],
        )
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            expected["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            expected["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], expected["response_date"])
        self.assertEqual(
            metadata["http_last_modified_at"], expected["last_modified"]
        )
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for key in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[key], expected["url"])
        self.assertIn(
            "no request-start artifact was supplied",
            metadata["retrieval_method"],
        )
        self.assertIn("HTTP Date", metadata["retrieved_at_semantics"])
        self.assertNotIn("remote_ip", metadata)
        self.assertFalse(
            any(
                "cookie" in key.lower()
                or "authorization" in key.lower()
                or "credential" in key.lower()
                or "token" in key.lower()
                for key in metadata
            )
        )

    def _assert_entities(
        self,
        document: dict[str, Any],
        *,
        campus_key: str,
        project_key: str,
        address: str,
        evidence_key: str,
        as_of_date: str,
    ) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        for ref, stable_key in (
            ("campus", campus_key),
            ("project", project_key),
        ):
            entity = document[ref]
            self.assertEqual(entity["stable_key"], stable_key)
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], address)
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], evidence_key)
            self.assertEqual(entity["as_of_date"], as_of_date)
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

    def _assert_microsoft(self, document: dict[str, Any]) -> None:
        self.assertEqual(len(document["evidence"]), 2)
        evidence = {row["key"]: row for row in document["evidence"]}
        self.assertEqual(set(evidence), {MICROSOFT_GROUNDBREAKING, MICROSOFT_UPDATE})
        for key, row in evidence.items():
            self._assert_capture(row, CAPTURES[key])

        self._assert_entities(
            document,
            campus_key=MICROSOFT_CAMPUS,
            project_key=MICROSOFT_PROJECT,
            address="La Porte, Indiana, United States",
            evidence_key=MICROSOFT_UPDATE,
            as_of_date="2026-07-10",
        )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": MICROSOFT_GROUNDBREAKING,
                    "as_of_date": "2026-06-18",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                },
                {
                    "entity": "project",
                    "value": "site_preparation",
                    "evidence_key": MICROSOFT_UPDATE,
                    "as_of_date": "2026-07-10",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                },
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        groundbreaking = evidence[MICROSOFT_GROUNDBREAKING]["metadata"]
        update = evidence[MICROSOFT_UPDATE]["metadata"]
        self.assertEqual(
            groundbreaking["event_date_as_reported"],
            "Thursday, June 18, 2026",
        )
        self.assertIn("generic under_construction", groundbreaking["status_scope"])
        self.assertIn(
            "no workload",
            groundbreaking["classification_guardrail"].lower(),
        )
        self.assertEqual(update["page_modified_at"], "2026-07-10T09:06:58+00:00")
        self.assertIn("future vertical", update["construction_wording_as_reported"])
        self.assertIn("site_preparation", update["status_scope"])
        self.assertIn("vertical building construction in the future", update["status_scope"])
        self.assertIn("narrative metadata", update["contractor_guardrail"])

    def _assert_nebius(self, document: dict[str, Any]) -> None:
        self.assertEqual(len(document["evidence"]), 3)
        evidence = {row["key"]: row for row in document["evidence"]}
        self.assertEqual(
            set(evidence),
            {NEBIUS_GROUNDBREAKING, NEBIUS_APPROVAL, NEBIUS_CITY_REPORT},
        )
        for key, row in evidence.items():
            self._assert_capture(row, CAPTURES[key])

        self._assert_entities(
            document,
            campus_key=NEBIUS_CAMPUS,
            project_key=NEBIUS_PROJECT,
            address="251 N Bly Rd, Independence, Missouri, United States",
            evidence_key=NEBIUS_CITY_REPORT,
            as_of_date="2026-05-01",
        )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": NEBIUS_GROUNDBREAKING,
                    "as_of_date": "2026-05-12",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": NEBIUS_GROUNDBREAKING,
                    "as_of_date": "2026-05-12",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["capacities"], [])

        groundbreaking = evidence[NEBIUS_GROUNDBREAKING]["metadata"]
        approval = evidence[NEBIUS_APPROVAL]["metadata"]
        city = evidence[NEBIUS_CITY_REPORT]["metadata"]
        self.assertIn("first phase", groundbreaking["phase_status_wording_as_reported"])
        self.assertIn("generic Phase 1 under_construction", groundbreaking["status_scope"])
        self.assertIn("ai_specialized_unspecified", groundbreaking["workload_scope"])
        self.assertEqual(approval["reported_potential_capacity_upper_bound_gw"], 1.2)
        self.assertIn("strict upper-bound", approval["capacity_guardrail"])
        self.assertIn("no normalized capacity row", approval["capacity_guardrail"])
        self.assertIn("not a building-permit issuance", approval["approval_guardrail"])
        self.assertEqual(city["pdf_page_count"], 2)
        self.assertEqual(city["project_name_as_reported"], "Nebius Data Center - Phase 1")
        self.assertEqual(city["address_as_reported"], "251 N BLY RD")
        self.assertEqual(city["valuation_usd_as_reported"], 106320497)
        self.assertIn("Submitted This Month", city["report_table_as_reported"])
        self.assertIn("not its Issued or Finaled tables", city["submission_guardrail"])
        self.assertIn("creates no lifecycle observation", city["submission_guardrail"])

    def _base_paths(self) -> list[Path]:
        definition_path = ROOT / "sources" / BASE_DEFINITION
        self.assertEqual(
            hashlib.sha256(definition_path.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            source_path = ROOT / record["path"]
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                record["sha256"],
            )
            paths.append(source_path)
        self.assertEqual(len(paths), 113)
        self.assertEqual(len(paths), len(set(paths)))
        return paths

    def _import(self, connection: Any, source_path: Path) -> Any:
        document = json.loads(source_path.read_text(encoding="utf-8"))
        retrieved = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(retrieved), 1)
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            source_path,
            retrieved_at=next(iter(retrieved)),
        )

    def _semantic_state(
        self, connection: Any
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        queries = (
            "SELECT kind, stable_key, created_at FROM entities",
            "SELECT kind, title, source_url, publisher, source_family, license, "
            "attribution, published_at, retrieved_at, excerpt, content_hash, "
            "metadata_json FROM evidence",
            "SELECT project_entity.stable_key, target_entity.stable_key "
            "FROM projects JOIN entities AS project_entity "
            "ON project_entity.id = projects.entity_id "
            "JOIN entities AS target_entity "
            "ON target_entity.id = projects.target_entity_id",
            "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
            "tags_json, evidence.content_hash, as_of_date, valid_to_date, "
            "recorded_at, superseded_at, method, confidence "
            "FROM entity_snapshots JOIN entities "
            "ON entities.id = entity_snapshots.entity_id JOIN evidence "
            "ON evidence.id = entity_snapshots.evidence_id",
            "SELECT entities.stable_key, status, evidence.content_hash, as_of_date, "
            "valid_to_date, recorded_at, superseded_at, method, confidence, notes "
            "FROM lifecycle_observations JOIN entities "
            "ON entities.id = lifecycle_observations.entity_id JOIN evidence "
            "ON evidence.id = lifecycle_observations.evidence_id",
            "SELECT entities.stable_key, operating_model, evidence.content_hash, "
            "as_of_date, valid_to_date, recorded_at, superseded_at, method, "
            "confidence, notes FROM operating_model_observations JOIN entities "
            "ON entities.id = operating_model_observations.entity_id JOIN evidence "
            "ON evidence.id = operating_model_observations.evidence_id",
            "SELECT entities.stable_key, workload, evidence.content_hash, "
            "as_of_date, valid_to_date, recorded_at, superseded_at, method, "
            "confidence, notes FROM workload_observations JOIN entities "
            "ON entities.id = workload_observations.entity_id JOIN evidence "
            "ON evidence.id = workload_observations.evidence_id",
            "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
            "method, confidence, evidence.content_hash, as_of_date, target_date, "
            "valid_to_date, recorded_at, superseded_at, notes "
            "FROM capacity_estimates JOIN entities "
            "ON entities.id = capacity_estimates.entity_id JOIN evidence "
            "ON evidence.id = capacity_estimates.evidence_id",
        )
        return tuple(
            tuple(
                sorted(
                    (tuple(row) for row in connection.execute(query)),
                    key=lambda row: json.dumps(row, ensure_ascii=False),
                )
            )
            for query in queries
        )

    def _counts(self, connection: Any) -> dict[str, int]:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "campuses",
                "projects",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            )
        }

    def _scenario(
        self,
        *,
        base_first: bool,
        new_order: tuple[str, ...],
    ) -> tuple[tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                base_paths = self._base_paths()
                new_paths = [ROOT / "sources" / name for name in new_order]
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ), patch.object(
                    socket,
                    "getaddrinfo",
                    side_effect=AssertionError("DNS used"),
                ):
                    if base_first:
                        for source_path in base_paths:
                            self._import(connection, source_path)
                    for source_path in new_paths:
                        self._import(connection, source_path)
                    before_repeat = self._semantic_state(connection)
                    for source_path in new_paths:
                        result = self._import(connection, source_path)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._semantic_state(connection), before_repeat)
                    if not base_first:
                        for source_path in base_paths:
                            self._import(connection, source_path)
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection), self._counts(connection)
            finally:
                connection.close()

    def _base_state(
        self,
    ) -> tuple[tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ), patch.object(
                    socket,
                    "getaddrinfo",
                    side_effect=AssertionError("DNS used"),
                ):
                    for source_path in self._base_paths():
                        self._import(connection, source_path)
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection), self._counts(connection)
            finally:
                connection.close()

    def test_exact_capture_lineage_and_source_semantics(self) -> None:
        microsoft_path = ROOT / "sources" / MICROSOFT_SOURCE
        nebius_path = ROOT / "sources" / NEBIUS_SOURCE
        self.assertEqual(
            hashlib.sha256(microsoft_path.read_bytes()).hexdigest(),
            MICROSOFT_SOURCE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(nebius_path.read_bytes()).hexdigest(),
            NEBIUS_SOURCE_SHA256,
        )
        self._assert_microsoft(self._load(MICROSOFT_SOURCE))
        self._assert_nebius(self._load(NEBIUS_SOURCE))

        for source_path, expected_evidence in (
            (microsoft_path, 2),
            (nebius_path, 3),
        ):
            with self.subTest(source=source_path.name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with patch.object(
                        socket, "socket", side_effect=AssertionError("network used")
                    ), patch.object(
                        socket,
                        "create_connection",
                        side_effect=AssertionError("network used"),
                    ), patch.object(
                        socket,
                        "getaddrinfo",
                        side_effect=AssertionError("DNS used"),
                    ):
                        result = self._import(connection, source_path)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, expected_evidence)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_v20_both_source_orders_and_base_positions_are_invariant(self) -> None:
        base_state, base_counts = self._base_state()
        reference_state = None
        reference_counts = None
        for new_order in (
            (MICROSOFT_SOURCE, NEBIUS_SOURCE),
            (NEBIUS_SOURCE, MICROSOFT_SOURCE),
        ):
            for base_first in (True, False):
                state, counts = self._scenario(
                    base_first=base_first,
                    new_order=new_order,
                )
                if reference_state is None:
                    reference_state = state
                    reference_counts = counts
                self.assertEqual(state, reference_state)
                self.assertEqual(counts, reference_counts)

        assert reference_state is not None and reference_counts is not None
        expected_deltas = {
            "entities": 4,
            "campuses": 2,
            "projects": 2,
            "evidence": 5,
            "entity_snapshots": 4,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 0,
        }
        self.assertEqual(
            {
                table: reference_counts[table] - base_counts[table]
                for table in expected_deltas
            },
            expected_deltas,
        )

        for before, combined in zip(base_state, reference_state):
            self.assertTrue(set(before).issubset(set(combined)))

        new_entity_keys = {
            MICROSOFT_CAMPUS,
            MICROSOFT_PROJECT,
            NEBIUS_CAMPUS,
            NEBIUS_PROJECT,
        }
        base_entity_keys = {row[1] for row in base_state[0]}
        combined_entity_keys = {row[1] for row in reference_state[0]}
        self.assertTrue(base_entity_keys.isdisjoint(new_entity_keys))
        self.assertEqual(combined_entity_keys - base_entity_keys, new_entity_keys)

        new_content_hashes = {row["content_hash"] for row in CAPTURES.values()}
        base_content_hashes = {row[10] for row in base_state[1]}
        combined_content_hashes = {row[10] for row in reference_state[1]}
        self.assertTrue(base_content_hashes.isdisjoint(new_content_hashes))
        self.assertEqual(
            combined_content_hashes - base_content_hashes,
            new_content_hashes,
        )

        new_snapshots = [
            row for row in reference_state[3] if row[0] in new_entity_keys
        ]
        self.assertEqual(len(new_snapshots), 4)
        for row in new_snapshots:
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertFalse(
                any(key.startswith("role:") for key in json.loads(row[5]))
            )

        lifecycle = [
            (row[0], row[1], row[3], row[7])
            for row in reference_state[4]
            if row[0] in new_entity_keys
        ]
        self.assertEqual(
            set(lifecycle),
            {
                (
                    MICROSOFT_PROJECT,
                    "under_construction",
                    "2026-06-18",
                    "authoritative_construction_start",
                ),
                (
                    MICROSOFT_PROJECT,
                    "site_preparation",
                    "2026-07-10",
                    "authoritative_physical_status_update",
                ),
                (
                    NEBIUS_PROJECT,
                    "under_construction",
                    "2026-05-12",
                    "authoritative_construction_start",
                ),
            },
        )
        workloads = [
            (row[0], row[1], row[3], row[7])
            for row in reference_state[6]
            if row[0] in new_entity_keys
        ]
        self.assertEqual(
            workloads,
            [
                (
                    NEBIUS_PROJECT,
                    "ai_specialized_unspecified",
                    "2026-05-12",
                    "company_disclosure",
                )
            ],
        )
        capacities = [
            row for row in reference_state[7] if row[0] in new_entity_keys
        ]
        self.assertEqual(capacities, [])

    def test_semantic_mutations_fail_source_guardrails(self) -> None:
        microsoft = self._load(MICROSOFT_SOURCE)
        nebius = self._load(NEBIUS_SOURCE)

        microsoft_mutations: list[dict[str, Any]] = []
        mutated = copy.deepcopy(microsoft)
        mutated["lifecycle"][1]["value"] = "foundations"
        microsoft_mutations.append(mutated)
        mutated = copy.deepcopy(microsoft)
        mutated["workloads"] = [{"forbidden": "AI quote is not a site workload"}]
        microsoft_mutations.append(mutated)
        mutated = copy.deepcopy(microsoft)
        mutated["capacities"] = [{"forbidden": "no source-typed MW"}]
        microsoft_mutations.append(mutated)
        mutated = copy.deepcopy(microsoft)
        mutated["project"]["roles"] = {"contractor": ["Ryan Central"]}
        microsoft_mutations.append(mutated)
        mutated = copy.deepcopy(microsoft)
        mutated["project"]["coordinates"] = {
            "latitude": 41.6,
            "longitude": -86.7,
        }
        microsoft_mutations.append(mutated)

        for index, document in enumerate(microsoft_mutations):
            with self.subTest(source="microsoft", mutation=index):
                with self.assertRaises(AssertionError):
                    self._assert_microsoft(document)

        nebius_mutations: list[dict[str, Any]] = []
        mutated = copy.deepcopy(nebius)
        mutated["capacities"] = [
            {"forbidden": "up-to 1.2 GW is untyped campus metadata"}
        ]
        nebius_mutations.append(mutated)
        mutated = copy.deepcopy(nebius)
        mutated["lifecycle"].append(
            {"forbidden": "city submission report is not permit issuance"}
        )
        nebius_mutations.append(mutated)
        mutated = copy.deepcopy(nebius)
        mutated["workloads"][0]["value"] = "ai_training"
        nebius_mutations.append(mutated)
        mutated = copy.deepcopy(nebius)
        mutated["project"]["roles"] = {"contractor": ["ARCO"]}
        nebius_mutations.append(mutated)
        mutated = copy.deepcopy(nebius)
        mutated["campus"]["geometry"] = {
            "type": "Point",
            "coordinates": [-94.4, 39.1],
        }
        nebius_mutations.append(mutated)

        for index, document in enumerate(nebius_mutations):
            with self.subTest(source="nebius", mutation=index):
                with self.assertRaises(AssertionError):
                    self._assert_nebius(document)


if __name__ == "__main__":
    unittest.main()
