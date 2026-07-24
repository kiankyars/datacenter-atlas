from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-digipower-columbiana-shell.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
V2_SOURCE_PATH = (
    ROOT / "sources" / "curated-official-2026-07-20-digipower-columbiana-shell-v2.json"
)
SOURCE_BYTES = 13_473
SOURCE_SHA256 = "7728f26d064c0ec3a47ac34aa60fdb635770a7b49e2fa90c4a0de91ca91e2ace"
PDF_URL = (
    "https://thankful-miracle-1ed8bdfdaf.media.strapiapp.com/"
    "Digi_Power_X_Provides_Operations_and_Financial_Update_4a179c433b.pdf"
)
LANDING_URL = (
    "https://www.digipowerx.com/press-releases/"
    "digi-power-x-provides-operations-and-financial-update-"
    "mcz9e1tgeok5z5s3kgli75yh"
)
API_URL = (
    "https://thankful-miracle-1ed8bdfdaf.strapiapp.com/api/press-releases/"
    "mcz9e1tgeok5z5s3kgli75yh?populate%5Bpdf_file%5D%5Bfields%5D=url%2Cname"
)
EVIDENCE_KEY = (
    "digipower-columbiana-shell-update-2026-07-07-captured-2026-07-20"
)
CAMPUS_KEY = "curated:digipowerx-columbiana-ai-data-center-campus"
PROJECT_KEY = (
    "curated:digipowerx-columbiana-ai-data-center-campus:"
    "purpose-built-flagship-vertical-build"
)
RETRIEVED_AT = "2026-07-20T08:30:56Z"
AS_OF_DATE = "2026-07-07"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"


class DigiPowerColumbianaShellCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Digi Power X curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _state(
        self,
        source_path: Path = SOURCE_PATH,
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(result.entities_created, 2 if iteration == 0 else 0)
                        self.assertEqual(result.evidence_created, 1 if iteration == 0 else 0)
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, "
                    "method, confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            path = Path(temporary) / SOURCE_NAME
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    path,
                    retrieved_at=RETRIEVED_AT,
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE_PATH.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE_PATH.stat().st_mode), 0o644)
        self.assertEqual(SOURCE_PATH.stat().st_size, SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
            SOURCE_SHA256,
        )
        text = SOURCE_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
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

    def test_pdf_capture_is_exact_closed_and_visually_verified(self) -> None:
        record = self._load()["evidence"][0]
        metadata = record["metadata"]
        self.assertEqual(record["key"], EVIDENCE_KEY)
        self.assertEqual(record["source_url"], PDF_URL)
        self.assertEqual(record["publisher"], "Digi Power X Inc.")
        self.assertEqual(record["source_family"], "digipowerx_press_releases")
        self.assertEqual(record["published_at"], AS_OF_DATE)
        self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(
            record["content_hash"],
            "ebcddc3bc3e8d35325e56fe7b81803a90a3a69938d1451401051f8eea135f734",
        )
        self.assertIn("267810-byte", metadata["content_hash_scope"])
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "adef54c7a443ebe796f24eee9d7a509a37238ec3291d3b357b33b8d104a06e6f",
        )
        self.assertIn("973-byte", metadata["capture_headers_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "241c598c667c9abc5231b242bf137f040a9ab37fd18c8802e55766020830bdaf",
        )
        self.assertIn("13040-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_exit_code"], 0)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertIsNone(metadata["content_encoding_as_received"])
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 267_810)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 267_810)
        self.assertEqual(metadata["curl_size_header_bytes"], 973)
        self.assertEqual(metadata["curl_num_headers"], 16)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], "2026-07-07T12:37:16Z")
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], PDF_URL)
        self.assertEqual(metadata["pdf_pages"], 5)
        self.assertEqual(metadata["pdf_version"], "1.7")
        self.assertTrue(metadata["pdf_tagged"])
        self.assertFalse(metadata["pdf_encrypted"])
        self.assertFalse(metadata["pdf_javascript"])
        self.assertIn("All five pages", metadata["pdf_visual_verification"])
        self.assertIn("no OCR", metadata["pdf_visual_verification"])

        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "cookie",
            "local_ip",
            "local_port",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        self.assertTrue(
            forbidden_telemetry_keys.isdisjoint(
                {field.casefold() for field in metadata}
            )
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])

    def test_official_api_lineage_binds_the_exact_pdf(self) -> None:
        metadata = self._load()["evidence"][0]["metadata"]
        self.assertEqual(metadata["official_landing_page_url"], LANDING_URL)
        self.assertEqual(metadata["official_api_url"], API_URL)
        self.assertEqual(metadata["official_api_response_body_bytes"], 790)
        self.assertEqual(
            metadata["official_api_response_body_sha256"],
            "5a98e74a47ab0ab563ac7ae25ad4eb5ea875c7488362cd8e54d243a7b39a5ec2",
        )
        self.assertEqual(metadata["official_api_response_headers_bytes"], 1269)
        self.assertEqual(
            metadata["official_api_response_headers_sha256"],
            "6a9f1c1e1363deaec0b2955705dff008412d9a0f1caa629bcfdffa32404e7d38",
        )
        self.assertEqual(metadata["official_api_curl_writeout_bytes"], 9906)
        self.assertEqual(
            metadata["official_api_curl_writeout_sha256"],
            "e3441c43efc8d3089b31b6a9859280021f93f2f6e579d965efd99b0f7c924b54",
        )
        self.assertEqual(metadata["official_api_http_status"], 200)
        self.assertEqual(metadata["official_api_http_version_as_received"], "HTTP/2")
        self.assertEqual(
            metadata["official_api_content_type"],
            "application/json; charset=utf-8",
        )
        self.assertEqual(metadata["official_api_content_encoding_as_received"], "gzip")
        self.assertEqual(metadata["official_api_curl_size_download_bytes_as_received"], 472)
        self.assertEqual(metadata["official_api_curl_size_header_bytes"], 1269)
        self.assertEqual(metadata["official_api_curl_num_headers"], 21)
        self.assertEqual(metadata["official_api_redirect_count"], 0)
        self.assertEqual(metadata["official_api_document_id"], "mcz9e1tgeok5z5s3kgli75yh")
        self.assertEqual(metadata["official_api_pdf_document_id"], "oqn5rq0fo23jm3bkvlea4keu")
        self.assertEqual(
            metadata["official_api_pdf_name"],
            "Digi Power X Provides Operations and Financial Update.pdf",
        )
        self.assertEqual(
            metadata["reported_publication_time_text"],
            "Tuesday, 07 July 2026 07:30 AM",
        )
        self.assertIn("no UTC offset is inferred", metadata["publication_time_guardrail"])

    def test_scope_is_one_unmapped_columbiana_campus_and_one_buildout(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Digi Power X Columbiana AI Data Center Campus")
        self.assertEqual(
            project["name"],
            "Digi Power X Columbiana Purpose-Built Flagship Vertical Build",
        )
        expected_roles = {
            "developer": ["Digi Power X"],
            "operator": ["Digi Power X"],
        }
        self.assertEqual(campus["roles"], expected_roles)
        self.assertEqual(project["roles"], expected_roles)
        for entity in (campus, project):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], "Columbiana, Alabama, United States")
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.95)
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("city-level campus identity only", metadata["location_scope"])
        self.assertIn("unique_site_counted remains false", metadata["site_resolution_guardrail"])
        self.assertIn("combined active flagship-buildout", metadata["phase_scope_guardrail"])

    def test_lifecycle_is_exactly_shell_without_phase_or_operational_leakage(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["reported_physical_work"],
            [
                "site and civil work completed or superseded for the active shell scope",
                "building shell being erected",
                "vertical construction underway",
            ],
        )
        for unsupported in (
            "shell completion",
            "MEP",
            "energization",
            "commissioning",
            "completion",
            "occupancy",
            "operation",
        ):
            self.assertIn(unsupported, metadata["construction_scope"])
        self.assertIn("ARMS 200", metadata["operational_module_guardrail"])
        self.assertIn("does not make the active flagship build operational", metadata["operational_module_guardrail"])

    def test_forecast_mw_create_no_capacity_or_energy_rows(self) -> None:
        document = self._load()
        self.assertEqual(document["capacities"], [])
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_phase_2_targeted_commissioning_mw_untyped"], 40)
        self.assertEqual(metadata["reported_fiscal_2027_target_ai_colocation_mw_untyped"], 90)
        self.assertEqual(metadata["reported_fiscal_2027_additional_ai_colocation_mw_untyped"], 50)
        self.assertEqual(metadata["reported_fiscal_2027_gpu_as_a_service_mw_untyped"], 10)
        self.assertIn("forward-looking", metadata["capacity_guardrail"])
        self.assertIn("remain non-additive metadata", metadata["capacity_guardrail"])
        self.assertIn("no normalized capacity rows", metadata["capacity_guardrail"])
        self.assertIn("no current electrical load", metadata["energy_guardrail"])
        self.assertIn("not converted into MWh", metadata["energy_guardrail"])

    def test_type_is_future_colocation_and_broad_ai_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "company_disclosure",
                    "confidence": 0.95,
                }
            ],
        )
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("future-project colocation", metadata["operating_model_scope"])
        for unsupported in ("AI training", "AI inference", "HPC", "installed accelerators"):
            self.assertIn(unsupported, metadata["workload_scope"])

    def test_offline_import_is_valid_exact_and_idempotent(self) -> None:
        state = self._state()
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = state
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(
            evidence,
            ((
                EVIDENCE_KEY,
                "ebcddc3bc3e8d35325e56fe7b81803a90a3a69938d1451401051f8eea135f734",
                RETRIEVED_AT,
                PDF_URL,
            ),),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(
            lifecycle,
            ((PROJECT_KEY, "shell", AS_OF_DATE, RETRIEVED_AT, "authoritative_physical_status_update", 0.99),),
        )
        self.assertEqual(capacities, ())
        self.assertEqual(
            models,
            ((PROJECT_KEY, "colocation", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.95),),
        )
        self.assertEqual(
            workloads,
            ((PROJECT_KEY, "ai_specialized_unspecified", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.99),),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(self._state(repetitions=2), state)

    def test_keys_are_collision_free_and_v44_is_unchanged(self) -> None:
        entity_keys: set[str] = set()
        evidence_keys: set[str] = set()
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path in {SOURCE_PATH, V2_SOURCE_PATH}:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                record = document.get(field)
                if isinstance(record, dict) and isinstance(record.get("stable_key"), str):
                    entity_keys.add(record["stable_key"])
            for record in document.get("evidence", []):
                if isinstance(record, dict) and isinstance(record.get("key"), str):
                    evidence_keys.add(record["key"])
        self.assertNotIn(CAMPUS_KEY, entity_keys)
        self.assertNotIn(PROJECT_KEY, entity_keys)
        self.assertNotIn(EVIDENCE_KEY, evidence_keys)

        v44 = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
        self.assertEqual(hashlib.sha256(v44.read_bytes()).hexdigest(), V44_SHA256)
        self.assertNotIn(SOURCE_NAME, v44.read_text(encoding="utf-8"))

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load())
        document["evidence"][0]["retrieved_at"] = "2026-07-20T08:30:57Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_method_for_shell_status(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 33.2,
            "longitude": -86.6,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
