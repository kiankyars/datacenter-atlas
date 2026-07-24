from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T07:02:56Z"
AS_OF_DATE = "2025-12-09"
PUBLISHED_AT = "2025-12-09T03:55:37.341Z"
SOURCE_URL = (
    "https://www.linkedin.com/posts/princetondg_princetondg-datacenter-"
    "activity-7404005778480750592-k_9z"
)
EVIDENCE_KEY = (
    "pdg-jh1-johor-phases-4-5-milestones-2025-12-09-captured-2026-07-20"
)
CAMPUS_KEY = "curated:pdg-jh1-johor-campus"
LOCALITY = "Johor, Malaysia"
ROLES = {"developer": ["Princeton Digital Group"]}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-pdg-jh1-johor-phase-4.json": {
        "sha256": (
            "48fcdcba2a0911553110dd4c22940ef4955cde1a5a3c7d4edddf6a451537c94b"
        ),
        "project_key": CAMPUS_KEY + ":phase-4-third-building",
        "project_name": "PDG JH1 Phase 4 (Third Building)",
        "status": "shell",
        "method": "authoritative_physical_status_update",
    },
    "curated-official-2026-07-20-pdg-jh1-johor-phase-5.json": {
        "sha256": (
            "baacbb508a3cca52bd56f2b2f224bc080b154b644e05474c0115667538837a7c"
        ),
        "project_key": CAMPUS_KEY + ":phase-5-fourth-building",
        "project_name": "PDG JH1 Phase 5 (Fourth Building)",
        "status": "under_construction",
        "method": "authoritative_construction_start",
    },
}
SOURCE_ORDER = tuple(SOURCE_SPECS)
PROJECT_KEYS = {spec["project_key"] for spec in SOURCE_SPECS.values()}
ENTITY_NAMES = {
    CAMPUS_KEY: "PDG JH1 Johor Campus",
    **{
        spec["project_key"]: spec["project_name"]
        for spec in SOURCE_SPECS.values()
    },
}
CAPTURE = {
    "body_bytes": 373_200,
    "body_sha256": (
        "cda0b76b7c25211b0cdb027c0cf0e7e2d57d91683bc6f359e91c016df69719cc"
    ),
    "headers_bytes": 5_301,
    "headers_sha256": (
        "86a8653f2d38900e7b9348c419f6a027ef61824340b0cba5d5377e6e07e2709f"
    ),
    "writeout_bytes": 17_659,
    "writeout_sha256": (
        "ea90054bfa23a462f6282d938fac7acbce1bb82c2f82f532ab8b818d078b69ee"
    ),
}
SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class PdgJh1JohorPhases45Tests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        error = AssertionError("curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(
        self, source_order: Iterable[str], *, repeat: int = 1
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for _ in range(repeat):
                    for name in source_order:
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                expected_counts = {
                    "evidence": 1,
                    "entities": 3,
                    "campuses": 1,
                    "projects": 2,
                    "entity_snapshots": 3,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                }
                for table, expected in expected_counts.items():
                    observed = connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    self.assertEqual(observed, expected, table)
                return self._state(connection)
            finally:
                connection.close()

    def test_sources_are_canonical_hash_pinned_and_reuse_one_capture(self) -> None:
        documents: dict[str, dict[str, Any]] = {}
        for name, expected in SOURCE_SPECS.items():
            path = self._path(name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            text = path.read_text(encoding="utf-8")
            document = json.loads(text)
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            documents[name] = document

        evidence = [document["evidence"][0] for document in documents.values()]
        self.assertEqual(evidence[0], evidence[1])
        row = evidence[0]
        self.assertEqual(row["key"], EVIDENCE_KEY)
        self.assertEqual(row["kind"], "company_disclosure")
        self.assertEqual(row["source_url"], SOURCE_URL)
        self.assertEqual(row["publisher"], "Princeton Digital Group")
        self.assertEqual(
            row["source_family"],
            "princeton_digital_group_linkedin_company_posts",
        )
        self.assertEqual(row["published_at"], PUBLISHED_AT)
        self.assertEqual(row["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(row["content_hash"], CAPTURE["body_sha256"])

        metadata = row["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(CAPTURE["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(
            str(CAPTURE["headers_bytes"]), metadata["capture_headers_scope"]
        )
        self.assertEqual(
            metadata["capture_headers_sha256"], CAPTURE["headers_sha256"]
        )
        self.assertIn(
            str(CAPTURE["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], CAPTURE["writeout_sha256"]
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertIsNone(metadata["content_encoding_as_received"])
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"], CAPTURE["body_bytes"]
        )
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["structured_date_published"], PUBLISHED_AT)

    def test_stable_keys_and_evidence_do_not_collide_with_prior_curated_inventory(self) -> None:
        collisions: list[tuple[str, str]] = []
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path.name in SOURCE_SPECS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None and entity.get("stable_key") in {
                    CAMPUS_KEY,
                    *PROJECT_KEYS,
                }:
                    collisions.append((path.name, entity["stable_key"]))
            for evidence in document.get("evidence", []):
                if evidence.get("key") == EVIDENCE_KEY:
                    collisions.append((path.name, EVIDENCE_KEY))
                if evidence.get("content_hash") == CAPTURE["body_sha256"]:
                    collisions.append((path.name, CAPTURE["body_sha256"]))
        self.assertEqual(collisions, [])

    def test_source_semantics_are_strict_status_only_and_metadata_power_only(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        for name, document in documents.items():
            expected = SOURCE_SPECS[name]
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
            self.assertEqual(document["campus"]["name"], ENTITY_NAMES[CAMPUS_KEY])
            self.assertEqual(document["project"]["stable_key"], expected["project_key"])
            self.assertEqual(document["project"]["name"], expected["project_name"])

            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], "Malaysia")
                self.assertEqual(entity["address"], LOCALITY)
                self.assertEqual(entity["roles"], ROLES)
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
                self.assertEqual(entity["as_of_date"], AS_OF_DATE)
                self.assertEqual(entity["method"], "authoritative_locality")

            self.assertEqual(
                document["lifecycle"],
                [
                    {
                        "entity": "project",
                        "value": expected["status"],
                        "evidence_key": EVIDENCE_KEY,
                        "as_of_date": AS_OF_DATE,
                        "method": expected["method"],
                        "confidence": 0.99,
                    }
                ],
            )
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])

        metadata = next(iter(documents.values()))["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_campus_untyped_mw"], 200)
        self.assertIn("metadata only", metadata["capacity_guardrail"])
        for forbidden_metric in (
            "critical IT load",
            "gross facility demand",
            "grid connection",
            "generation nameplate",
            "annual energy",
            "current consumption",
        ):
            self.assertIn(forbidden_metric, metadata["capacity_guardrail"])
        self.assertEqual(metadata["phase_4_building_ordinal_as_reported"], 3)
        self.assertEqual(metadata["phase_5_building_ordinal_as_reported"], 4)
        self.assertIn("shell", metadata["phase_4_physical_scope"])
        self.assertIn("generic under_construction", metadata["phase_5_physical_scope"])
        self.assertIn("no identities", metadata["uninstantiated_buildings_guardrail"])
        self.assertIn("developer only", metadata["developer_scope"])
        self.assertIn("no owner", metadata["developer_scope"])
        self.assertIn("marketing context only", metadata["classification_guardrail"])
        self.assertIn("no operating model", metadata["classification_guardrail"])
        self.assertIn("no PUE", metadata["efficiency_guardrail"])
        self.assertIn("computer vision", metadata["imagery_guardrail"])

    def test_import_creates_one_campus_two_projects_and_is_order_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                first = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in SOURCE_ORDER
                ]
                self.assertEqual(
                    [
                        (result.entities_created, result.evidence_created, result.warnings)
                        for result in first
                    ],
                    [(2, 1, ()), (1, 0, ())],
                )
                frozen = self._state(connection)
                repeated = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in SOURCE_ORDER
                ]
                self.assertEqual(
                    [
                        (result.entities_created, result.evidence_created, result.warnings)
                        for result in repeated
                    ],
                    [(0, 0, ()), (0, 0, ())],
                )
                self.assertEqual(self._state(connection), frozen)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

        forward = self._build(SOURCE_ORDER)
        reverse = self._build(reversed(SOURCE_ORDER))
        repeated_forward = self._build(SOURCE_ORDER, repeat=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated_forward)

    def test_isolated_database_has_only_supported_normalized_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in SOURCE_ORDER:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(validate_database(connection), [])

                snapshots = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.kind, e.stable_key, s.name, s.latitude, s.longitude,
                               s.geometry_json, s.tags_json, s.as_of_date, s.method
                        FROM entity_snapshots AS s
                        JOIN entities AS e ON e.id = s.entity_id
                        ORDER BY e.kind, e.stable_key
                        """
                    )
                ]
                self.assertEqual(len(snapshots), 3)
                for (
                    kind,
                    stable_key,
                    name,
                    latitude,
                    longitude,
                    geometry,
                    tags_json,
                    as_of_date,
                    method,
                ) in snapshots:
                    self.assertIn(kind, {"campus", "project"})
                    self.assertEqual(name, ENTITY_NAMES[stable_key])
                    self.assertIsNone(latitude)
                    self.assertIsNone(longitude)
                    self.assertIsNone(geometry)
                    self.assertEqual(
                        json.loads(tags_json),
                        {
                            "address": LOCALITY,
                            "country": "Malaysia",
                            "role:developer": "Princeton Digital Group",
                            "source_dataset": "curated_official_sources",
                        },
                    )
                    self.assertEqual(as_of_date, AS_OF_DATE)
                    self.assertEqual(method, "authoritative_locality")

                project_targets = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT project.stable_key, target.stable_key
                        FROM projects AS p
                        JOIN entities AS project ON project.id = p.entity_id
                        JOIN entities AS target ON target.id = p.target_entity_id
                        """
                    )
                }
                self.assertEqual(
                    project_targets,
                    {(project_key, CAMPUS_KEY) for project_key in PROJECT_KEYS},
                )
                lifecycle = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, l.status, l.as_of_date, l.method
                        FROM lifecycle_observations AS l
                        JOIN entities AS e ON e.id = l.entity_id
                        """
                    )
                }
                self.assertEqual(
                    lifecycle,
                    {
                        (
                            SOURCE_SPECS[name]["project_key"],
                            SOURCE_SPECS[name]["status"],
                            AS_OF_DATE,
                            SOURCE_SPECS[name]["method"],
                        )
                        for name in SOURCE_ORDER
                    },
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    1,
                )
                for table in (
                    "capacity_estimates",
                    "operating_model_observations",
                    "workload_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
