from __future__ import annotations

import copy
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
SOURCE_NAME = "curated-official-2026-07-20-aligned-iad06-frederick-topout.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 8_522
SOURCE_SHA256 = "1321b938e409635e883e6e417beb55ac56736bfc9d956bbefcc062df35192103"
RETRIEVED_AT = "2026-07-20T22:51:51Z"
PUBLISHED_AT = "2026-03-09T13:16:42.046Z"
AS_OF_DATE = "2026-03-09"

CAMPUS_KEY = "curated:aligned-quantum-frederick-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:iad06"
EVIDENCE_KEY = "turner-aligned-iad06-frederick-topout-2026-03-09-captured-2026-07-20"
SOURCE_URL = (
    "https://www.linkedin.com/posts/turner-construction-company_"
    "weve-topped-out-the-aligned-data-centers-activity-"
    "7436761886454353920-3Gzf"
)
BODY_BYTES = 354_983
BODY_SHA256 = "31083a50a0fa93148f3189c3876a7d083220dc0b746ae4dcc43454b7b589336b"
HEADER_BYTES = 5_348
HEADER_SHA256 = "4ed98a2929a33c27749b335c112f2200c79155c26f42ece9977606463c432ace"
ADDRESS = "Frederick, Maryland, United States"


class AlignedIad06FrederickTopoutCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Aligned IAD-06 curated import attempted network access")
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
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT metric FROM capacity_estimates ORDER BY id",
                    "SELECT operating_model FROM operating_model_observations "
                    "ORDER BY id",
                    "SELECT workload FROM workload_observations ORDER BY id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _assert_document_rejected(self, document: dict[str, Any], pattern: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source_path = temporary_path / SOURCE_NAME
            self._write_document(source_path, document)
            connection, _ = initialize(temporary_path / "atlas.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(ValueError, pattern):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        source_path,
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
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(), SOURCE_SHA256
        )
        text = SOURCE_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(
            text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
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

    def test_exact_public_linkedin_capture_is_hash_bound(self) -> None:
        evidence = self._load()["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Turner Construction Company")
        self.assertEqual(
            evidence["source_family"],
            "turner_construction_linkedin_company_posts",
        )
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(evidence["published_at"], PUBLISHED_AT)
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(evidence["content_hash"], BODY_SHA256)
        self.assertEqual(
            metadata["content_hash_scope"],
            "SHA-256 of the exact "
            f"{BODY_BYTES}-byte content-decoded public LinkedIn HTML response "
            "body captured with curl --compressed",
        )
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertEqual(
            metadata["capture_headers_scope"],
            f"SHA-256 of the exact {HEADER_BYTES}-byte raw HTTP "
            "response-header capture",
        )
        self.assertEqual(metadata["capture_headers_sha256"], HEADER_SHA256)
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["structured_date_published"], PUBLISHED_AT)
        self.assertEqual(
            metadata["retrieval_method"],
            "One unauthenticated curl --disable --retry 0 --connect-timeout 0 "
            "--max-time 0 --fail --location --compressed request captured the "
            "content-decoded public HTML body and raw response headers separately; "
            "connection and total timeouts and retries were explicitly disabled.",
        )
        self.assertIn("no Authorization", metadata["request_credentials_guardrail"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])

        forbidden = {
            "authorization",
            "cookie",
            "local_ip",
            "local_port",
            "remote_ip",
            "remote_port",
            "set-cookie",
        }
        self.assertTrue(forbidden.isdisjoint({field.casefold() for field in metadata}))

    def test_source_scoped_identity_locality_and_roles_are_narrow(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Aligned Frederick Data Center Campus")
        self.assertEqual(project["name"], "Aligned Data Centers IAD-06")
        for entity in (campus, project):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], ADDRESS)
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], AS_OF_DATE)
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_identity"], "Aligned Data Centers IAD-06")
        self.assertEqual(metadata["reported_locality"], "Frederick, Maryland")
        self.assertIn("source-scoped", metadata["identity_scope"])
        self.assertIn("do not safely allocate", metadata["role_guardrail"])
        self.assertIn("no street address", metadata["locality_guardrail"])
        self.assertIn("not merged", metadata["collision_guardrail"])

    def test_topout_is_exactly_shell_as_of_publication(self) -> None:
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
        self.assertEqual(metadata["status_wording_as_reported"], "topped out")
        self.assertEqual(
            metadata["reported_physical_milestone"],
            "completion of the structural phase",
        )
        for unsupported in (
            "MEP completion",
            "energization",
            "commissioning",
            "ready-for-service",
            "completion",
            "occupancy",
            "operation",
            "current load",
        ):
            self.assertIn(unsupported, metadata["physical_scope"])
        self.assertEqual(
            metadata["reported_elapsed_time_since_groundbreaking"],
            "less than five months",
        )
        self.assertIn(
            "no exact groundbreaking date", metadata["groundbreaking_guardrail"]
        )
        self.assertIn("No date is calculated", metadata["groundbreaking_guardrail"])

    def test_untyped_72_mw_and_building_dimensions_remain_metadata_only(self) -> None:
        document = self._load()
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_capacity_mw_untyped"], 72)
        self.assertEqual(metadata["reported_floor_area_square_feet"], 450_000)
        self.assertEqual(metadata["reported_story_count"], 2)
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        for unsupported_metric in (
            "critical IT capacity",
            "gross facility demand",
            "grid connection",
            "generation nameplate",
            "current load",
            "annual energy",
            "measured consumption",
        ):
            self.assertIn(unsupported_metric, metadata["capacity_exclusion"])
        self.assertIn("no PUE", metadata["energy_guardrail"])
        self.assertIn("not converted", metadata["energy_guardrail"])
        self.assertIn("no source-explicit", metadata["classification_guardrail"])
        self.assertIn("not a second data centre", metadata["entity_model_guardrail"])
        self.assertIn("no parcel", metadata["building_scope_guardrail"])

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

    def test_offline_import_is_exact_idempotent_and_order_independent(self) -> None:
        once = self._database_state()
        self.assertEqual(self._database_state(repetitions=2), once)

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
            self.assertEqual(self._database_state(reordered_path), once)

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
            ((EVIDENCE_KEY, BODY_SHA256, RETRIEVED_AT, SOURCE_URL),),
        )
        self.assertEqual(len(snapshots), 2)
        expected_tags = {
            "address": ADDRESS,
            "country": "United States",
            "source_dataset": "curated_official_sources",
        }
        for row in snapshots:
            self.assertEqual(json.loads(row[2]), expected_tags)
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[6], AS_OF_DATE)
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "shell",
                    AS_OF_DATE,
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())

    def test_semantic_mutations_cannot_weaken_shell_or_invent_coordinates(self) -> None:
        weak_shell = copy.deepcopy(self._load())
        weak_shell["lifecycle"][0]["method"] = "authoritative_status_update"
        self._assert_document_rejected(
            weak_shell,
            "construction status requires authoritative_construction_start",
        )

        invented_point = copy.deepcopy(self._load())
        invented_point["project"]["coordinates"] = {
            "latitude": 39.4,
            "longitude": -77.4,
        }
        self._assert_document_rejected(
            invented_point,
            "authoritative_locality requires null coordinates and geometry",
        )

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
            first = CuratedOfficialSourceAdapter().import_file(
                connection, source, retrieved_at={RETRIEVED_AT!r}
            )
            second = CuratedOfficialSourceAdapter().import_file(
                connection, source, retrieved_at={RETRIEVED_AT!r}
            )
        assert first.entities_created == 2
        assert first.evidence_created == 1
        assert second.entities_created == 0
        assert second.evidence_created == 0
        assert first.warnings == second.warnings == ()
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
        status = connection.execute(
            "SELECT status FROM lifecycle_observations"
        ).fetchone()[0]
        print(json.dumps({{"counts": counts, "status": status}}, sort_keys=True))
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
                        "counts": {
                            "capacity": 0,
                            "entities": 2,
                            "evidence": 1,
                            "lifecycle": 1,
                            "operating_models": 0,
                            "snapshots": 2,
                            "workloads": 0,
                        },
                        "status": "shell",
                    },
                )


if __name__ == "__main__":
    unittest.main()
