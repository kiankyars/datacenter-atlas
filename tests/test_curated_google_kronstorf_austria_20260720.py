from __future__ import annotations

from contextlib import ExitStack
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
SOURCE_NAME = "curated-official-2026-07-20-google-kronstorf-austria.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "763f11edfea3ce7ff7ec76093716d732a92a906562a3b7f3d17c3b08fa3a4e21"
SOURCE_BYTES = 8_196
RETRIEVED_AT = "2026-07-20T20:01:06Z"

CAMPUS_KEY = "curated:google-kronstorf-austria-data-center-campus"
PROJECT_KEY = "curated:google-kronstorf-austria-data-center-campus:current-development"
EVIDENCE_KEY = "google-kronstorf-groundbreaking-2026-04-23-captured-2026-07-20"
REQUESTED_URL = (
    "https://www.googlecloudpresscorner.com/2026-04-23-Google-Breaks-Ground-on-"
    "Data-Center-in-Kronstorf%2C-Austria"
)
EFFECTIVE_URL = (
    "https://www.googlecloudpresscorner.com/2026-04-23-Google-Breaks-Ground-on-"
    "Data-Center-in-Kronstorf,-Austria"
)
BODY_SHA256 = "fa9fb59cdd774842321c98f471f4b6eb70df6ab47dd4d1adb23c63bf062bed08"
HEADER_SHA256 = "da5e8b5de5fc39919e4ff2e615d5c1fe8ae7d712552fe5ec6dc7a8e11d5d69e4"
WRITEOUT_SHA256 = "4bc59942479de08cc50e2e455a5d39c81e6f9a58fb6a75c5844cb03b7ba85090"


class GoogleKronstorfAustriaCuratedTests(unittest.TestCase):
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

    def _database_state(
        self, path: Path = SOURCE_PATH, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
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
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT metric FROM capacity_estimates ORDER BY id",
                    "SELECT operating_model FROM operating_model_observations ORDER BY id",
                    "SELECT workload FROM workload_observations ORDER BY id",
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
        self.assertEqual(len(document["evidence"]), 1)

    def test_capture_quad_redirect_and_publication_semantics_are_exact(self) -> None:
        item = self._load()["evidence"][0]
        metadata = item["metadata"]
        self.assertEqual(item["key"], EVIDENCE_KEY)
        self.assertEqual(item["publisher"], "Google")
        self.assertEqual(item["source_family"], "google_cloud_press_corner")
        self.assertEqual(item["published_at"], "2026-04-23")
        self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(item["source_url"], EFFECTIVE_URL)
        self.assertEqual(item["content_hash"], BODY_SHA256)
        self.assertIn("57199-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("1962-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADER_SHA256)
        self.assertIn("15861-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 16_145)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["response_header_blocks"], 2)
        self.assertEqual(metadata["redirect_count"], 1)
        self.assertEqual(metadata["requested_url"], REQUESTED_URL)
        self.assertEqual(metadata["effective_url"], EFFECTIVE_URL)
        self.assertEqual(metadata["canonical_url"], EFFECTIVE_URL)
        self.assertIn("no publication time", metadata["published_date_semantics"])

    def test_scope_status_and_guardrails_are_exact(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Google Kronstorf Data Center Campus")
        self.assertEqual(
            project["name"], "Google Kronstorf Data Center Current Development"
        )
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Austria")
            self.assertEqual(entity["address"], "Kronstorf, Austria")
            self.assertEqual(entity["roles"], {"developer": ["Google"]})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["as_of_date"], "2026-04-23")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-04-23",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        metadata = document["evidence"][0]["metadata"]
        self.assertIn("under-construction", metadata["physical_scope"])
        self.assertIn("internal parent container", metadata["entity_model_guardrail"])
        self.assertIn(
            "must never be counted separately", metadata["entity_model_guardrail"]
        )
        self.assertIn("no source-verifiable address", metadata["location_guardrail"])
        self.assertIn("only as developer", metadata["role_guardrail"])
        self.assertIn("do not establish", metadata["workload_guardrail"])
        self.assertIn("reports no site IT capacity", metadata["capacity_guardrail"])
        self.assertIn("No annual energy", metadata["energy_guardrail"])
        self.assertIn("create no site PUE", metadata["sustainability_guardrail"])
        self.assertIn("provide no completion", metadata["forecast_guardrail"])

    def test_stable_and_evidence_keys_do_not_collide(self) -> None:
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

    def test_offline_import_is_exact_and_idempotent(self) -> None:
        once = self._database_state()
        twice = self._database_state(repetitions=2)
        self.assertEqual(once, twice)

        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            projects,
            capacities,
            operating_models,
            workloads,
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
            ((EVIDENCE_KEY, BODY_SHA256, RETRIEVED_AT, EFFECTIVE_URL),),
        )
        self.assertEqual(len(snapshots), 2)
        expected_tags = {
            "address": "Kronstorf, Austria",
            "country": "Austria",
            "role:developer": "Google",
            "source_dataset": "curated_official_sources",
        }
        for row in snapshots:
            self.assertEqual(json.loads(row[2]), expected_tags)
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[6], "2026-04-23")
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-04-23",
                    RETRIEVED_AT,
                    "authoritative_construction_start",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())

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
                        "operating_models": 0,
                        "snapshots": 2,
                        "workloads": 0,
                    },
                )


if __name__ == "__main__":
    unittest.main()
