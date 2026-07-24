from __future__ import annotations

from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SOURCE_NAME = "curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "c31ecbe7fb4b8e47de2683c0b321d5dd3e59dda1fbf596218ceab0ef7e191f94"
SOURCE_BYTES = 11_187
RETRIEVED_AT = "2026-07-20T19:58:23Z"

EVIDENCE_KEY = (
    "digital-edge-bgrimm-chonburi-eec-groundbreaking-2025-09-04-captured-2026-07-20"
)
CAMPUS_KEY = "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:current-development"
SOURCE_URL = (
    "https://www.digitaledgedc.com/resources/newsroom/"
    "digital-edge-bgrimm-thailand-eec-data-center/"
)
BODY_SHA256 = "449843d800a5ba175833634054b308369afdae02ea19ead284893f2152e6e7a9"
HEADERS_SHA256 = "8054d770636cdfb60864da3f86da103e601f4fdee1143990742a85319d16301c"
WRITEOUT_SHA256 = "ca4a2f2ef94d620f764f4c75449980b5113a9d9860da05ef7d4329b43988e339"


class DigitalEdgeBGrimmChonburiCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write_document(self, path: Path, document: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _database_state(
        self, source_path: Path = SOURCE_PATH, repetitions: int = 1
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
                        self.assertEqual(
                            result.entities_created, 2 if iteration == 0 else 0
                        )
                        self.assertEqual(
                            result.evidence_created, 1 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload FROM workload_observations "
                    "JOIN entities ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, metric, stage, base "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
        self.assertEqual(stat.S_IMODE(SOURCE_PATH.stat().st_mode), 0o644)
        self.assertEqual(SOURCE_PATH.stat().st_size, SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(), SOURCE_SHA256
        )

        text = SOURCE_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(
            text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(document["schema_version"], "1.0")
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

    def test_capture_triple_publication_and_response_facts_are_exact(self) -> None:
        document = self._load()
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        metadata = evidence["metadata"]

        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["publisher"], "Digital Edge")
        self.assertEqual(evidence["source_family"], "digital_edge_newsroom")
        self.assertEqual(evidence["published_at"], "2025-09-04T02:27:18+00:00")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(evidence["content_hash"], BODY_SHA256)
        self.assertIn("213984-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("1065-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertIn("14578-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)

        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_exit_code"], 0)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 35_048)
        self.assertEqual(metadata["curl_size_header_bytes"], 1_065)
        self.assertEqual(metadata["curl_num_headers"], 17)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], RETRIEVED_AT)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertIn("HTML canonical", metadata["canonical_url_basis"])
        self.assertEqual(
            metadata["structured_published_at"], "2025-09-04T02:27:18+00:00"
        )
        self.assertEqual(
            metadata["structured_modified_at"], "2026-06-01T03:56:31+00:00"
        )

        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
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
        self.assertIn("One credential-free", metadata["retrieval_method"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertIn("No authorization", metadata["request_metadata_guardrail"])

    def test_entities_status_and_future_colocation_are_narrow(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        expected_roles = {"developer": ["B.Grimm Power", "Digital Edge"]}

        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(
            campus["name"], "Digital Edge B.Grimm Chonburi EEC Data Center Campus"
        )
        self.assertEqual(
            project["name"],
            "Digital Edge B.Grimm Chonburi EEC Current Data Center Development",
        )
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Thailand")
            self.assertEqual(
                entity["address"], "Chonburi, Eastern Economic Corridor, Thailand"
            )
            self.assertEqual(entity["roles"], expected_roles)
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2025-09-04")
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2025-09-04",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2025-09-04",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

    def test_raw_power_forecast_locality_and_no_double_count_guardrails(self) -> None:
        metadata = self._load()["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_untyped_power_mw"], 100)
        self.assertIn("not typed", metadata["capacity_guardrail"])
        self.assertIn("creates no capacity row", metadata["capacity_guardrail"])
        self.assertEqual(metadata["reported_ready_for_service_forecast"], "Q4 2026")
        self.assertIn("no target_date", metadata["forecast_guardrail"])
        self.assertEqual(
            metadata["reported_thailand_portfolio_investment_plan_usd"],
            1_000_000_000,
        )
        self.assertIn("portfolio", metadata["investment_scope"])
        self.assertIn("not a site-specific project cost", metadata["investment_scope"])
        self.assertIn("Bangkok campus", metadata["locality_guardrail"])
        self.assertIn("creates no Bangkok identity", metadata["locality_guardrail"])
        self.assertIn("future-project colocation", metadata["operating_model_scope"])
        self.assertIn(
            "creates no normalized workload", metadata["classification_guardrail"]
        )
        self.assertIn("No energy or PUE row", metadata["energy_guardrail"])
        self.assertIn("developer roles", metadata["role_scope"])
        self.assertIn("internal parent container", metadata["entity_model_guardrail"])
        self.assertIn("must never be added", metadata["entity_model_guardrail"])
        self.assertIn("one physical site", metadata["entity_model_guardrail"])
        self.assertIn("contribute nothing", metadata["imagery_guardrail"])

    def test_stable_and_evidence_keys_do_not_collide_with_curated_sources(self) -> None:
        claimed_stable = {CAMPUS_KEY, PROJECT_KEY}
        claimed_evidence = {EVIDENCE_KEY}
        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE_PATH:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            stable_keys = {
                entity["stable_key"]
                for entity in (document.get("campus"), document.get("project"))
                if isinstance(entity, dict) and "stable_key" in entity
            }
            evidence_keys = {
                item["key"]
                for item in document.get("evidence", [])
                if isinstance(item, dict) and "key" in item
            }
            stable_overlap = sorted(claimed_stable & stable_keys)
            evidence_overlap = sorted(claimed_evidence & evidence_keys)
            if stable_overlap or evidence_overlap:
                collisions[path.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(collisions, {})

    def test_offline_import_is_exact_idempotent_and_order_independent(self) -> None:
        once = self._database_state()
        twice = self._database_state(repetitions=2)
        self.assertEqual(once, twice)

        with tempfile.TemporaryDirectory() as temporary:
            reordered_path = Path(temporary) / SOURCE_NAME
            document = self._load()
            reordered = {
                key: (
                    [
                        {field: value for field, value in reversed(list(item.items()))}
                        for item in reversed(value)
                    ]
                    if key == "evidence"
                    else value
                )
                for key, value in reversed(list(document.items()))
            }
            self._write_document(reordered_path, reordered)
            reordered_state = self._database_state(reordered_path)
        self.assertEqual(once, reordered_state)

        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            projects,
            operating_models,
            workloads,
            capacities,
        ) = once
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(
            evidence,
            ((EVIDENCE_KEY, BODY_SHA256, RETRIEVED_AT, SOURCE_URL),),
        )
        self.assertEqual(len(snapshots), 2)
        snapshot_by_key = {row[0]: row for row in snapshots}
        for stable_key in (CAMPUS_KEY, PROJECT_KEY):
            row = snapshot_by_key[stable_key]
            self.assertEqual(
                json.loads(row[2]),
                {
                    "address": "Chonburi, Eastern Economic Corridor, Thailand",
                    "country": "Thailand",
                    "role:developer": "B.Grimm Power; Digital Edge",
                    "source_dataset": "curated_official_sources",
                },
            )
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[6], "2025-09-04")
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2025-09-04",
                    RETRIEVED_AT,
                    "authoritative_construction_start",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(
            operating_models,
            (
                (
                    PROJECT_KEY,
                    "colocation",
                    "2025-09-04",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(workloads, ())
        self.assertEqual(capacities, ())

    def test_adapter_rejects_invented_coordinates_and_weak_construction_method(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            connection, _ = initialize(temporary_path / "atlas.sqlite")
            try:
                coordinates = copy.deepcopy(self._load())
                coordinates["campus"]["coordinates"] = {
                    "latitude": 13.0,
                    "longitude": 101.0,
                }
                coordinates_path = temporary_path / "coordinates.json"
                self._write_document(coordinates_path, coordinates)
                with self.assertRaisesRegex(
                    ValueError, "authoritative_locality requires null coordinates"
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        coordinates_path,
                        retrieved_at=RETRIEVED_AT,
                    )

                weak_status = copy.deepcopy(self._load())
                weak_status["lifecycle"][0]["method"] = "analyst_synthesis"
                weak_status_path = temporary_path / "weak-status.json"
                self._write_document(weak_status_path, weak_status)
                with self.assertRaisesRegex(ValueError, "construction status requires"):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        weak_status_path,
                        retrieved_at=RETRIEVED_AT,
                    )
            finally:
                connection.close()

    def test_source_imports_offline_in_both_workspace_layouts(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated import CuratedOfficialSourceAdapter
from {package}.database import initialize
from {package}.service import validate_database

source = Path({str(SOURCE_PATH)!r})
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            result = CuratedOfficialSourceAdapter().import_file(
                connection, source, retrieved_at={RETRIEVED_AT!r}
            )
        assert result.entities_created == 2
        assert result.evidence_created == 1
        assert result.warnings == ()
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        print(json.dumps(counts, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "capacity": 0,
                        "entities": 2,
                        "evidence": 1,
                        "lifecycle": 1,
                        "operating_models": 1,
                        "snapshots": 2,
                        "workloads": 0,
                    },
                )


if __name__ == "__main__":
    unittest.main()
