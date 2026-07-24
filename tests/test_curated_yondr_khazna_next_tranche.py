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
V16_DEFINITION = "open-seed-2026-07-19-v16.json"
YONDR_SOURCE = "curated-official-2026-07-19-yondr-slough-third-building.json"
AUH4_SOURCE = "curated-official-2026-07-19-khazna-auh4-mafraq.json"
AUH8_SOURCE = "curated-official-2026-07-19-khazna-auh8-masdar-city.json"
QAJ1_SOURCE = "curated-official-2026-07-19-khazna-qaj1-ajman.json"

SOURCES: dict[str, dict[str, Any]] = {
    YONDR_SOURCE: {
        "sha256": "74e07cff7e1058c9d956e329f11d4ad72f0fe9fb66b3dc5c64858867a5123e32",
        "retrieved_at": "2026-07-19T19:24:35Z",
        "campus_key": "curated:yondr-london-slough-data-center-campus",
        "project_key": (
            "curated:yondr-london-slough-data-center-campus:third-building"
        ),
        "country": "United Kingdom",
        "address": "Slough, United Kingdom",
        "status": "under_construction",
        "method": "authoritative_physical_status_update",
        "as_of_date": "2026-02-20",
    },
    AUH4_SOURCE: {
        "sha256": "529c6f247336e6d4b7953b6980c0f2c10810191bcfe754f695571444d5d6a1b4",
        "retrieved_at": "2026-07-19T19:28:32Z",
        "campus_key": "curated:khazna-auh4-mafraq-data-center",
        "project_key": (
            "curated:khazna-auh4-mafraq-data-center:current-facility-build"
        ),
        "country": "United Arab Emirates",
        "address": "Mafraq, Abu Dhabi, United Arab Emirates",
        "status": "under_construction",
        "method": "authoritative_construction_start",
        "as_of_date": "2025-04-21",
    },
    AUH8_SOURCE: {
        "sha256": "74b2cdeb870e1aadb374943aff5798bf8360af164a665c1d867d4da305642b22",
        "retrieved_at": "2026-07-19T19:28:32Z",
        "campus_key": "curated:khazna-auh8-masdar-city-data-center",
        "project_key": (
            "curated:khazna-auh8-masdar-city-data-center:current-facility-build"
        ),
        "country": "United Arab Emirates",
        "address": "Masdar City, Abu Dhabi, United Arab Emirates",
        "status": "under_construction",
        "method": "authoritative_construction_start",
        "as_of_date": "2025-04-21",
    },
    QAJ1_SOURCE: {
        "sha256": "34524821d70715fae1070ddf632cbb78c746c0c83282572f8aac406d880e42e5",
        "retrieved_at": "2026-07-19T19:28:32Z",
        "campus_key": "curated:khazna-qaj1-ajman-data-center",
        "project_key": (
            "curated:khazna-qaj1-ajman-data-center:current-facility-build"
        ),
        "country": "United Arab Emirates",
        "address": "Ajman, United Arab Emirates",
        "status": "shell",
        "method": "authoritative_physical_status_update",
        "as_of_date": "2025-04-21",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "7cb3b3fe110add00db98298fdc91d3a04f395d3275104bd70d91bf9ab4eea928": {
        "body_bytes": 74017,
        "headers_bytes": 1009,
        "headers_sha256": "5bba76e9c5ad6f5e97a7bf26faf767730ba72877bb18f674e20f68b54213ce80",
        "response_date": "2026-07-19T19:24:35Z",
        "content_length": None,
        "url": (
            "https://www.yondrgroup.com/newsroom/press-release/"
            "yondr-group-secures-inaugural-abs-financing-for-its-london-campus/"
        ),
    },
    "fc0fb8a55d0a0d320ff96b831eea2b2f2c260a2492e29993735616a9e064a311": {
        "body_bytes": 80413,
        "headers_bytes": 1009,
        "headers_sha256": "a4f22d2e5d5ca902552a6e0797acbb315d7270d154d3779fe43d93220b1adb7b",
        "response_date": "2026-07-19T19:24:35Z",
        "content_length": None,
        "url": (
            "https://www.yondrgroup.com/newsroom/press-release/"
            "yondr-group-breaks-ground-on-third-phase-of-100mw-london-campus/"
        ),
    },
    "8488186266dbdfe8f60530383d6a918415895d9de82ceef78fb718e7c6955c7c": {
        "body_bytes": 70941,
        "headers_bytes": 1031,
        "headers_sha256": "edae1788098610d53bb7a25b0b1d73d70bae9be99ac45bb668f3d073030d97e6",
        "response_date": "2026-07-19T19:28:32Z",
        "content_length": 17116,
        "url": (
            "https://khaznadatacenters.com/press-release/"
            "khazna-expands-infrastructure-to-accelerate-uaes-leadership-in-"
            "artificial-intelligence/"
        ),
    },
}


class YondrKhaznaNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(len(document["lifecycle"]), 1)
        lifecycle = document["lifecycle"][0]
        self.assertEqual(lifecycle["entity"], "project")
        self.assertEqual(lifecycle["value"], expected["status"])
        self.assertEqual(lifecycle["method"], expected["method"])
        self.assertEqual(lifecycle["as_of_date"], expected["as_of_date"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["capacities"], [])

        if name == QAJ1_SOURCE:
            self.assertEqual(len(document["workloads"]), 1)
            workload = document["workloads"][0]
            self.assertEqual(workload["entity"], "project")
            self.assertEqual(workload["value"], "ai_specialized_unspecified")
            self.assertEqual(workload["as_of_date"], "2025-04-21")
            self.assertEqual(workload["method"], "company_disclosure")
        else:
            self.assertEqual(document["workloads"], [])

        if name == YONDR_SOURCE:
            self.assertEqual(len(document["evidence"]), 2)
            current, groundbreaking = document["evidence"]
            self.assertEqual(
                current["metadata"]["third_building_status_as_reported"],
                "currently under construction",
            )
            self.assertEqual(
                groundbreaking["metadata"]["third_building_capacity_as_reported_mw"],
                40,
            )
            self.assertIn(
                "untyped metadata",
                groundbreaking["metadata"]["capacity_metric_guardrail"],
            )
            self.assertIn(
                "forward-looking forecast",
                current["metadata"]["completion_forecast_guardrail"],
            )
        else:
            self.assertEqual(len(document["evidence"]), 1)
            metadata = document["evidence"][0]["metadata"]
            self.assertEqual(
                metadata["auh4_auh8_combined_capacity_as_reported_mw"], 60
            )
            self.assertIn(
                "not allocated between them",
                metadata["combined_capacity_guardrail"],
            )
            self.assertEqual(metadata["qaj1_capacity_as_reported_mw"], 100)
            self.assertIn(
                "untyped metadata", metadata["qaj1_capacity_guardrail"]
            )
            self.assertIn(
                "only ai_specialized_unspecified", metadata["qaj1_ai_scope"]
            )
            self.assertIn(
                "design capability",
                metadata["auh4_auh8_classification_guardrail"],
            )

    def _import_state(self, order: list[str]) -> tuple[list[tuple[Any, ...]], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name in order:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                self.assertEqual(validate_database(connection), [])
                return (
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, stable_key FROM entities "
                            "ORDER BY kind, stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT title, content_hash, metadata_json FROM evidence "
                            "ORDER BY content_hash"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, workload, as_of_date, method "
                            "FROM workload_observations JOIN entities "
                            "ON entities.id = workload_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, name, latitude, longitude, "
                            "geometry_json, tags_json FROM entity_snapshots "
                            "JOIN entities ON entities.id = entity_snapshots.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                )
            finally:
                connection.close()

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        v16_definition = (ROOT / "sources" / V16_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name, expected in SOURCES.items():
            self.assertNotIn(name, v16_definition)
            self.assertNotIn(expected["campus_key"], v16_definition)
            self.assertNotIn(expected["project_key"], v16_definition)

            source_path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                expected["sha256"],
            )
            document = self._load(name)
            self._assert_guardrails(name, document)
            self.assertEqual(
                {row["retrieved_at"] for row in document["evidence"]},
                {expected["retrieved_at"]},
            )
            for evidence in document["evidence"]:
                capture = CAPTURES[evidence["content_hash"]]
                metadata = evidence["metadata"]
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
                self.assertIn(
                    str(capture["headers_bytes"]), metadata["capture_headers_scope"]
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], capture["headers_sha256"]
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(
                    metadata["response_http_date"], capture["response_date"]
                )
                self.assertIsNone(metadata["http_last_modified_at"])
                self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    capture["content_length"],
                )
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(evidence["source_url"], capture["url"])
                self.assertEqual(metadata["requested_url"], capture["url"])
                self.assertEqual(metadata["effective_url"], capture["url"])
                self.assertEqual(metadata["canonical_url"], capture["url"])
                self.assertNotIn("request_started_at", metadata)
                self.assertNotIn("request_start_utc", metadata)
                self.assertIn(
                    "no request-start artifact was supplied",
                    metadata["retrieval_method"],
                )
                self.assertIn("not redistributed", metadata["rights_scope"])

        khazna_evidence = [
            self._load(name)["evidence"] for name in (AUH4_SOURCE, AUH8_SOURCE, QAJ1_SOURCE)
        ]
        self.assertEqual(khazna_evidence[0], khazna_evidence[1])
        self.assertEqual(khazna_evidence[0], khazna_evidence[2])

        state = self._import_state(list(SOURCES))
        self.assertEqual(len(state[0]), 8)
        self.assertEqual(len(state[1]), 3)
        self.assertEqual(
            [(row[1], row[2], row[3]) for row in state[2]],
            [
                ("under_construction", "2025-04-21", "authoritative_construction_start"),
                ("under_construction", "2025-04-21", "authoritative_construction_start"),
                ("shell", "2025-04-21", "authoritative_physical_status_update"),
                ("under_construction", "2026-02-20", "authoritative_physical_status_update"),
            ],
        )
        self.assertEqual(
            state[3],
            [
                (
                    SOURCES[QAJ1_SOURCE]["project_key"],
                    "ai_specialized_unspecified",
                    "2025-04-21",
                    "company_disclosure",
                )
            ],
        )
        for row in state[4]:
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertFalse(
                any(key.startswith("role:") for key in json.loads(row[5]))
            )

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name in SOURCES:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_khazna_shared_evidence_is_import_order_invariant(self) -> None:
        forward = [AUH4_SOURCE, AUH8_SOURCE, QAJ1_SOURCE]
        self.assertEqual(self._import_state(forward), self._import_state(list(reversed(forward))))

    def test_semantic_mutations_fail_guardrails(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(documents[YONDR_SOURCE])
        mutated["capacities"] = [{"forbidden": "40 MW untyped"}]
        mutations.append((YONDR_SOURCE, mutated))

        mutated = copy.deepcopy(documents[AUH4_SOURCE])
        mutated["capacities"] = [{"forbidden": "30 MW allocation"}]
        mutations.append((AUH4_SOURCE, mutated))

        mutated = copy.deepcopy(documents[AUH8_SOURCE])
        mutated["workloads"] = [{"forbidden": "design capability"}]
        mutations.append((AUH8_SOURCE, mutated))

        mutated = copy.deepcopy(documents[QAJ1_SOURCE])
        mutated["lifecycle"][0]["value"] = "under_construction"
        mutations.append((QAJ1_SOURCE, mutated))

        mutated = copy.deepcopy(documents[QAJ1_SOURCE])
        mutated["workloads"][0]["value"] = "ai_training"
        mutations.append((QAJ1_SOURCE, mutated))

        mutated = copy.deepcopy(documents[AUH4_SOURCE])
        mutated["campus"]["coordinates"] = {"latitude": 24.4, "longitude": 54.6}
        mutations.append((AUH4_SOURCE, mutated))

        mutated = copy.deepcopy(documents[YONDR_SOURCE])
        mutated["project"]["roles"] = {"operator": ["Yondr Group"]}
        mutations.append((YONDR_SOURCE, mutated))

        for name, mutated in mutations:
            with self.subTest(name=name, mutation=mutated):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(name, mutated)


if __name__ == "__main__":
    unittest.main()
