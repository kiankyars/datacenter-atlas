from __future__ import annotations

import csv
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXPECTATIONS = {
    "curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json": {
        "bytes": 24_099,
        "sha256": "2dfcc8c092e81150910adc00e3122c383cc21067a521def2a10c65ad08846e1d",
        "project_key": (
            "curated:ecodatacenter-2-borlange-data-center-campus:"
            "data-center-b1-current-build"
        ),
        "project_name": "EcoDataCenter Borlänge Data Center B1",
    },
    "curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json": {
        "bytes": 24_099,
        "sha256": "e3d5cee16c35d708847b084f3993e60f41ae12281c7aca5a411792110e7ff41f",
        "project_key": (
            "curated:ecodatacenter-2-borlange-data-center-campus:"
            "data-center-b2-current-build"
        ),
        "project_name": "EcoDataCenter Borlänge Data Center B2",
    },
}
SOURCES = tuple(ROOT / "sources" / name for name in SOURCE_EXPECTATIONS)
RECORDED_AT = "2026-07-21T05:10:14Z"

ANNUAL_KEY = "ecodc-2025-annual-report-borlange-b1-b2-captured-2026-07-20"
Q1_KEY = "ecodc-q1-2026-borlange-platform-context-captured-2026-07-20"
SITE_KEY = "ecodc-official-ecodatacenter-2-site-page-captured-2026-07-20"
CAMPUS_KEY = "curated:ecodatacenter-2-borlange-data-center-campus"
PROJECT_B1_KEY = SOURCE_EXPECTATIONS[SOURCES[0].name]["project_key"]
PROJECT_B2_KEY = SOURCE_EXPECTATIONS[SOURCES[1].name]["project_key"]
ADDRESS = "Kvarnsvedsvägen 420, 784 66 Borlänge, Sweden"

FALUN_SOURCES = (
    ROOT / "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
    ROOT / "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
)
FALUN_CAMPUS_KEY = "curated:ecodatacenter-falun-data-center-campus"
FALUN_PROJECT_KEYS = {
    "curated:ecodatacenter-falun-data-center-campus:data-center-e-current-build",
    "curated:ecodatacenter-falun-data-center-campus:data-center-f-current-build",
}
FALUN_ANNUAL_KEY = "ecodc-2025-annual-report-falun-e-f-captured-2026-07-20"
FALUN_Q1_KEY = "ecodc-q1-2026-platform-construction-captured-2026-07-20"

RELEASES = (
    ROOT / "releases/2026-07-20-open-seed-v61",
    ROOT / "releases/2026-07-20-open-seed-v62",
)
CAPTURES: dict[str, dict[str, Any]] = {
    ANNUAL_KEY: {
        "url": (
            "https://ecodatacenter.tech/hubfs/"
            "Annual%20Report%202025_EcoDC%20Holding%20AB_ENG.pdf"
        ),
        "published_at": None,
        "retrieved_at": "2026-07-21T04:51:37Z",
        "last_modified_at": "2026-04-15T15:40:00Z",
        "body_bytes": 1_598_143,
        "body_sha256": (
            "3f2a1140583ff741dc67cd6b17f9b7c9fbebb347b0ca6bc67622d2a1f3caaacd"
        ),
        "header_bytes": 1_357,
        "header_sha256": (
            "3f156d0ae0f878a988a1554e0506e09e3777385ba61e60fc671142465538d2be"
        ),
        "writeout_bytes": 9_681,
        "writeout_sha256": (
            "15761b67d354ee34cfdfe565c94a4c6699a5c62545f1428494e74bb9a0f89039"
        ),
        "page_count": 81,
        "pdf_version": "1.7",
        "pdf_creator": None,
        "pdf_producer": "Microsoft: Print To PDF",
        "publisher": "EcoDC Holding AB (publ)",
        "source_family": "ecodatacenter_financial_reports",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 1_598_143,
        "download_bytes": 1_598_143,
        "num_headers": 28,
    },
    Q1_KEY: {
        "url": (
            "https://ecodatacenter.tech/hubfs/"
            "EcoDC%20Holding%20AB%20Q1%20report%202026_ENG.pdf"
        ),
        "published_at": "2026-05-13",
        "retrieved_at": "2026-07-21T04:51:39Z",
        "last_modified_at": "2026-05-13T06:18:40Z",
        "body_bytes": 1_557_535,
        "body_sha256": (
            "379d3da4a567ee1be8c406a1c632a2ee40abe11d1221334f9a91384dd2573487"
        ),
        "header_bytes": 1_357,
        "header_sha256": (
            "168fdf15102aed4e9f4f43ff6cffed91d859f9c061b6010afa57aedda42567aa"
        ),
        "writeout_bytes": 9_669,
        "writeout_sha256": (
            "fc36617a82b4037e00250cf8e5a9b5d6074f172dcba3e7f8915551cbe04d3d77"
        ),
        "page_count": 21,
        "pdf_version": "1.6",
        "pdf_creator": "Acrobat PDFMaker 26 för PowerPoint",
        "pdf_producer": "Adobe PDF Library 26.1.183",
        "publisher": "EcoDC Holding AB (publ)",
        "source_family": "ecodatacenter_financial_reports",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 1_557_535,
        "download_bytes": 1_557_535,
        "num_headers": 28,
    },
    SITE_KEY: {
        "url": "https://ecodatacenter.tech/data-center/ecodatacenter2",
        "published_at": None,
        "retrieved_at": "2026-07-21T05:10:14Z",
        "last_modified_at": "2026-07-07T06:03:29Z",
        "body_bytes": 48_321,
        "body_sha256": (
            "3ad7711981dcdae93eeaee47ff1b5a143c01c57d658b307883316062883abe1b"
        ),
        "header_bytes": 3_436,
        "header_sha256": (
            "e91de46372298f2b34857efcfe23a9d1db1c06e05cbd46fbe82e89830ac9c8fd"
        ),
        "writeout_bytes": 9_567,
        "writeout_sha256": (
            "e7ad99e2d69e42189ef4d22fdf1a7e496275b93e812f8da037cbbe3feb7361f8"
        ),
        "publisher": "EcoDataCenter",
        "source_family": "ecodatacenter_site_pages",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 10_894,
        "num_headers": 24,
    },
}


class EcoDataCenterBorlangeB1B2CuratedTests(unittest.TestCase):
    def _load(self, source: Path) -> dict[str, Any]:
        return json.loads(source.read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "EcoDataCenter B1/B2 curated import attempted network access"
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _import_sequence(self, source_sequence: tuple[Path, ...]):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = tuple(
            CuratedOfficialSourceAdapterV11().import_file(
                connection,
                source,
                recorded_at=RECORDED_AT,
            )
            for source in source_sequence
        )
        return temporary, connection, results

    def _database_state(self, connection) -> dict[str, tuple[tuple[Any, ...], ...]]:
        order_columns = {
            "evidence": "id",
            "entities": "id",
            "campuses": "entity_id",
            "projects": "entity_id",
            "entity_snapshots": "id",
            "lifecycle_observations": "id",
            "operating_model_observations": "id",
            "workload_observations": "id",
            "capacity_estimates": "id",
        }
        return {
            table: tuple(
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY {order_column}"
                )
            )
            for table, order_column in order_columns.items()
        }

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        documents: list[dict[str, Any]] = []
        for source in SOURCES:
            with self.subTest(source=source.name):
                expected = SOURCE_EXPECTATIONS[source.name]
                self.assertTrue(source.is_file())
                self.assertFalse(source.is_symlink())
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                source_bytes = source.read_bytes()
                self.assertEqual(len(source_bytes), expected["bytes"])
                self.assertEqual(
                    hashlib.sha256(source_bytes).hexdigest(), expected["sha256"]
                )
                source_text = source_bytes.decode("utf-8")
                document = json.loads(source_text)
                documents.append(document)
                self.assertEqual(
                    source_text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.1")
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
                self.assertEqual(
                    document["project"]["stable_key"], expected["project_key"]
                )
                self.assertEqual(document["project"]["name"], expected["project_name"])
                self.assertTrue(
                    all(
                        entity["as_of_date"] <= "2026-07-20"
                        for entity in (document["campus"], document["project"])
                    )
                )
                self.assertTrue(
                    all(
                        "captured-2026-07-21" not in evidence["key"]
                        for evidence in document["evidence"]
                    )
                )
                self.assertNotIn("/private/tmp", source_text)

        e_document, f_document = documents
        self.assertEqual(e_document["evidence"], f_document["evidence"])
        self.assertEqual(e_document["campus"], f_document["campus"])
        e_project = dict(e_document["project"])
        f_project = dict(f_document["project"])
        for field in ("stable_key", "name"):
            e_project.pop(field)
            f_project.pop(field)
        self.assertEqual(e_project, f_project)

    def test_capture_triples_are_exact_official_and_credential_free(self) -> None:
        evidence = {item["key"]: item for item in self._load(SOURCES[0])["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "filename_effective",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], expected["retrieved_at"])
                self.assertEqual(item["license"], "all-rights-reserved")
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['header_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
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
                self.assertEqual(
                    metadata["curl_size_header_bytes"], expected["header_bytes"]
                )
                self.assertEqual(metadata["curl_num_headers"], expected["num_headers"])
                self.assertEqual(
                    metadata["response_http_date"], expected["retrieved_at"]
                )
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified_at"]
                )
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                if expected["content_type"] == "application/pdf":
                    self.assertEqual(metadata["pdf_page_count"], expected["page_count"])
                    self.assertEqual(metadata["pdf_version"], expected["pdf_version"])
                    self.assertEqual(metadata["pdf_creator"], expected["pdf_creator"])
                    self.assertEqual(metadata["pdf_producer"], expected["pdf_producer"])
                self.assertIn("No retries", metadata["request_credentials_guardrail"])
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                self.assertTrue(
                    forbidden_telemetry_keys.isdisjoint(metadata),
                    forbidden_telemetry_keys & set(metadata),
                )
        source_text = SOURCES[0].read_text(encoding="utf-8")
        self.assertNotIn("__cf_bm", source_text)
        self.assertNotIn("_cfuvid", source_text)

    def test_offline_import_is_exact_idempotent_order_independent_and_valid(
        self,
    ) -> None:
        forward_sequence = SOURCES + SOURCES
        reverse_sources = tuple(reversed(SOURCES))
        reverse_sequence = reverse_sources + reverse_sources
        with ExitStack() as stack:
            self._block_network(stack)
            forward_temp, forward, forward_results = self._import_sequence(
                forward_sequence
            )
            reverse_temp, reverse, reverse_results = self._import_sequence(
                reverse_sequence
            )
            stack.callback(forward_temp.cleanup)
            stack.callback(forward.close)
            stack.callback(reverse_temp.cleanup)
            stack.callback(reverse.close)

            expected_results = (
                (2, 3, ()),
                (1, 0, ()),
                (0, 0, ()),
                (0, 0, ()),
            )
            for results in (forward_results, reverse_results):
                self.assertEqual(
                    tuple(
                        (
                            result.entities_created,
                            result.evidence_created,
                            result.warnings,
                        )
                        for result in results
                    ),
                    expected_results,
                )
                self.assertTrue(
                    all(
                        (
                            result.examined_elements,
                            result.imported_elements,
                            result.skipped_elements,
                        )
                        == (1, 1, 0)
                        for result in results
                    )
                )

            self.assertEqual(validate_database(forward), [])
            self.assertEqual(validate_database(reverse), [])
            self.assertEqual(
                self._database_state(forward), self._database_state(reverse)
            )
            counts = {
                table: forward.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 3,
                    "evidence": 3,
                    "entity_snapshots": 3,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                },
            )

            entities = tuple(
                tuple(row)
                for row in forward.execute(
                    "SELECT kind, stable_key, created_at "
                    "FROM entities ORDER BY kind, stable_key"
                )
            )
            self.assertEqual(
                entities,
                (
                    ("campus", CAMPUS_KEY, RECORDED_AT),
                    ("project", PROJECT_B1_KEY, RECORDED_AT),
                    ("project", PROJECT_B2_KEY, RECORDED_AT),
                ),
            )
            relations = tuple(
                tuple(row)
                for row in forward.execute(
                    "SELECT project_entities.stable_key, campus_entities.stable_key "
                    "FROM projects "
                    "JOIN entities AS project_entities "
                    "ON project_entities.id = projects.entity_id "
                    "JOIN entities AS campus_entities "
                    "ON campus_entities.id = projects.target_entity_id "
                    "ORDER BY project_entities.stable_key"
                )
            )
            self.assertEqual(
                relations,
                ((PROJECT_B1_KEY, CAMPUS_KEY), (PROJECT_B2_KEY, CAMPUS_KEY)),
            )

            snapshots = tuple(
                forward.execute(
                    "SELECT entities.stable_key, name, tags_json, latitude, "
                    "longitude, geometry_json, as_of_date, recorded_at, method, "
                    "confidence FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                tuple(row["stable_key"] for row in snapshots),
                (CAMPUS_KEY, PROJECT_B1_KEY, PROJECT_B2_KEY),
            )
            self.assertEqual(
                tuple(row["name"] for row in snapshots),
                (
                    "EcoDataCenter 2 Borlänge Data Center Campus",
                    "EcoDataCenter Borlänge Data Center B1",
                    "EcoDataCenter Borlänge Data Center B2",
                ),
            )
            for row in snapshots:
                self.assertIsNone(row["latitude"])
                self.assertIsNone(row["longitude"])
                self.assertIsNone(row["geometry_json"])
                self.assertEqual(row["as_of_date"], "2026-07-20")
                self.assertEqual(row["recorded_at"], RECORDED_AT)
                self.assertEqual(row["method"], "authoritative_locality")
                self.assertEqual(row["confidence"], 0.99)
                self.assertEqual(
                    json.loads(row["tags_json"]),
                    {
                        "address": ADDRESS,
                        "country": "Sweden",
                        "role:developer": "EcoDataCenter",
                        "role:operator": "EcoDataCenter",
                        "source_dataset": "curated_official_sources",
                    },
                )

            lifecycle = tuple(
                tuple(row)
                for row in forward.execute(
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                lifecycle,
                (
                    (
                        PROJECT_B1_KEY,
                        "under_construction",
                        "2025-12-31",
                        RECORDED_AT,
                        "authoritative_construction_start",
                        0.99,
                    ),
                    (
                        PROJECT_B2_KEY,
                        "under_construction",
                        "2025-12-31",
                        RECORDED_AT,
                        "authoritative_construction_start",
                        0.99,
                    ),
                ),
            )

    def test_adjoining_falun_and_borlange_sources_coexist_offline(self) -> None:
        forward_sequence = FALUN_SOURCES + SOURCES
        reverse_sequence = SOURCES + FALUN_SOURCES
        with ExitStack() as stack:
            self._block_network(stack)
            forward_temp, forward, forward_results = self._import_sequence(
                forward_sequence
            )
            reverse_temp, reverse, reverse_results = self._import_sequence(
                reverse_sequence
            )
            stack.callback(forward_temp.cleanup)
            stack.callback(forward.close)
            stack.callback(reverse_temp.cleanup)
            stack.callback(reverse.close)

            self.assertEqual(
                tuple(
                    (result.entities_created, result.evidence_created)
                    for result in forward_results
                ),
                ((2, 2), (1, 0), (2, 3), (1, 0)),
            )
            self.assertEqual(
                tuple(
                    (result.entities_created, result.evidence_created)
                    for result in reverse_results
                ),
                ((2, 3), (1, 0), (2, 2), (1, 0)),
            )
            self.assertTrue(
                all(
                    result.warnings == ()
                    for result in forward_results + reverse_results
                )
            )
            self.assertEqual(validate_database(forward), [])
            self.assertEqual(validate_database(reverse), [])
            self.assertEqual(
                self._database_state(forward), self._database_state(reverse)
            )

            counts = {
                table: forward.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 6,
                    "evidence": 5,
                    "entity_snapshots": 6,
                    "lifecycle_observations": 4,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                },
            )
            stable_keys = {
                row["stable_key"]
                for row in forward.execute("SELECT stable_key FROM entities")
            }
            self.assertEqual(
                stable_keys,
                {
                    CAMPUS_KEY,
                    PROJECT_B1_KEY,
                    PROJECT_B2_KEY,
                    FALUN_CAMPUS_KEY,
                    *FALUN_PROJECT_KEYS,
                },
            )
            evidence_rows = tuple(
                forward.execute("SELECT content_hash, metadata_json FROM evidence")
            )
            evidence_keys = {
                json.loads(row["metadata_json"])["curated_record_key"]
                for row in evidence_rows
            }
            self.assertEqual(
                evidence_keys,
                {
                    ANNUAL_KEY,
                    Q1_KEY,
                    SITE_KEY,
                    FALUN_ANNUAL_KEY,
                    FALUN_Q1_KEY,
                },
            )
            body_hash_counts: dict[str, int] = {}
            for row in evidence_rows:
                body_hash_counts[row["content_hash"]] = (
                    body_hash_counts.get(row["content_hash"], 0) + 1
                )
            self.assertEqual(
                body_hash_counts,
                {
                    CAPTURES[ANNUAL_KEY]["body_sha256"]: 2,
                    CAPTURES[Q1_KEY]["body_sha256"]: 2,
                    CAPTURES[SITE_KEY]["body_sha256"]: 1,
                },
            )

    def test_scope_preserves_b1_b2_without_capacity_status_or_coordinate_inference(
        self,
    ) -> None:
        documents = [self._load(source) for source in SOURCES]
        self.assertEqual(
            {document["project"]["stable_key"] for document in documents},
            {PROJECT_B1_KEY, PROJECT_B2_KEY},
        )
        self.assertEqual(
            {document["project"]["name"] for document in documents},
            {
                "EcoDataCenter Borlänge Data Center B1",
                "EcoDataCenter Borlänge Data Center B2",
            },
        )
        for document in documents:
            self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], "Sweden")
                self.assertEqual(entity["address"], ADDRESS)
                self.assertEqual(
                    entity["roles"],
                    {
                        "developer": ["EcoDataCenter"],
                        "operator": ["EcoDataCenter"],
                    },
                )
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["evidence_key"], SITE_KEY)
                self.assertEqual(entity["as_of_date"], "2026-07-20")

            self.assertEqual(
                document["lifecycle"],
                [
                    {
                        "entity": "project",
                        "value": "under_construction",
                        "evidence_key": ANNUAL_KEY,
                        "as_of_date": "2025-12-31",
                        "method": "authoritative_construction_start",
                        "confidence": 0.99,
                    }
                ],
            )
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            normalized_evidence_keys = {
                document["campus"]["evidence_key"],
                document["project"]["evidence_key"],
                *(row["evidence_key"] for row in document["lifecycle"]),
            }
            self.assertEqual(normalized_evidence_keys, {ANNUAL_KEY, SITE_KEY})

            evidence = {item["key"]: item for item in document["evidence"]}
            annual = evidence[ANNUAL_KEY]["metadata"]
            q1 = evidence[Q1_KEY]["metadata"]
            site = evidence[SITE_KEY]["metadata"]
            self.assertEqual(
                annual["construction_wording_as_reported"],
                (
                    "Work on building two data centers at the Borlänge site, "
                    "B1 and B2, began in 2025"
                ),
            )
            self.assertEqual(
                annual["reported_combined_b1_b2_capacity_upon_commissioning_mw"],
                24,
            )
            self.assertIn("shared evidence metadata only", annual["capacity_guardrail"])
            self.assertIn("not split", annual["capacity_guardrail"])
            self.assertIn(
                "not identified as B1 or B2", annual["adjacent_land_guardrail"]
            )
            self.assertEqual(q1["reported_new_contracted_capacity_mw"], 23)
            self.assertIn("platform-wide", q1["contracted_capacity_guardrail"])
            self.assertIn("creates no", q1["contracted_capacity_guardrail"])
            self.assertIn("does not name", q1["platform_status_guardrail"])
            self.assertIn("cannot roll", q1["platform_status_guardrail"])
            self.assertIn("May 13, 2026", q1["platform_status_guardrail"])
            self.assertEqual(
                site["official_site_address_as_reported"],
                "Kvarnsvedsvägen 420, 784 66 Borlänge",
            )
            self.assertEqual(
                site["site_construction_start_as_reported"],
                "Construction began in September 2025",
            )
            self.assertEqual(site["site_status_as_reported"], "Under construction")
            self.assertIn("never names B1 or B2", site["project_status_guardrail"])
            self.assertIn("cannot establish", site["project_status_guardrail"])
            self.assertIn(
                "creates no normalized coordinates", site["embedded_map_guardrail"]
            )
            self.assertEqual(site["reported_total_available_power_site_mw_up_to"], 600)
            self.assertEqual(
                site["reported_total_available_land_site_square_metres"], 200000
            )
            self.assertIn("metadata only", site["site_capacity_guardrail"])
            self.assertIn("not allocated", site["site_capacity_guardrail"])
            self.assertIn("not evidence of an actual", site["classification_guardrail"])

    def test_time_gate_fails_closed_before_any_database_write(self) -> None:
        for source in SOURCES:
            with (
                self.subTest(source=source.name),
                tempfile.TemporaryDirectory() as temp,
            ):
                connection, _ = initialize(Path(temp) / "atlas.sqlite")
                try:
                    with self.assertRaisesRegex(
                        ValueError,
                        "must not be later than the import recorded_at",
                    ):
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            source,
                            recorded_at="2026-07-21T05:10:13Z",
                        )
                    for table in (
                        "evidence",
                        "entities",
                        "entity_snapshots",
                        "lifecycle_observations",
                    ):
                        self.assertEqual(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0],
                            0,
                        )
                finally:
                    connection.close()

    def test_borlange_b1_b2_are_unseeded_in_v61_v62(self) -> None:
        capture_urls = {item["url"] for item in CAPTURES.values()}
        for release in RELEASES:
            with self.subTest(release=release.name):
                with (release / "entities.csv").open(
                    newline="", encoding="utf-8"
                ) as handle:
                    entities = list(csv.DictReader(handle))
                stable_keys = {row["stable_key"] for row in entities}
                self.assertTrue(
                    {CAMPUS_KEY, PROJECT_B1_KEY, PROJECT_B2_KEY}.isdisjoint(stable_keys)
                )
                borlange_rows = []
                for row in entities:
                    searchable = " ".join(
                        (row["stable_key"], row["name"], row["address"])
                    ).lower()
                    if "ecodatacenter" in searchable and "borl" in searchable:
                        borlange_rows.append(row)
                self.assertEqual(borlange_rows, [])

                inputs = json.loads(
                    (release / "source_inputs.json").read_text(encoding="utf-8")
                )["sources"]
                urls = {item["source_url"] for item in inputs}
                evidence_keys = {
                    item.get("provenance", {}).get("curated_record_key")
                    for item in inputs
                }
                self.assertTrue(capture_urls.isdisjoint(urls))
                self.assertTrue(
                    {ANNUAL_KEY, Q1_KEY, SITE_KEY}.isdisjoint(evidence_keys)
                )


if __name__ == "__main__":
    unittest.main()
