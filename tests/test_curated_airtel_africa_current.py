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
V18_DEFINITION = "open-seed-2026-07-19-v18.json"
KENYA_SOURCE = "curated-official-2026-07-19-airtel-nxtra-tatu-city-kenya.json"
LAGOS_SOURCE = "curated-official-2026-07-19-airtel-nxtra-eko-atlantic-lagos.json"
KENYA_SHA256 = "2f5b90543ae83a53181f19b491981140dc5f8dd3b85141058f47a004a658bc45"
LAGOS_SHA256 = "a02fe6b1a64c2db1bd9e42a137c696fb9019dce2da8f5c5b7a15723665895850"
RETRIEVED_AT = "2026-07-19T19:58:28Z"
CONTENT_HASH = "ede627f1dcba0e0e832d83e78bdbcff36e2e1d52cbd9851a5f267d816a7af064"
HEADERS_HASH = "4883e1afed01344273811727b4cfa07bf87bbfdad83a02d37c5e10068e6a61f4"
SOURCE_URL = "https://www.airtel.africa/data-centers"
EVIDENCE_KEY = (
    "airtel-africa-nxtra-kenya-lagos-construction-snapshot-captured-2026-07-19"
)
KENYA_CAMPUS_KEY = "curated:nxtra-tatu-city-kenya-data-center"
KENYA_PROJECT_KEY = "curated:nxtra-tatu-city-kenya-data-center:current-facility-build"
LAGOS_CAMPUS_KEY = "curated:nxtra-eko-atlantic-lagos-data-center"
LAGOS_PROJECT_KEY = (
    "curated:nxtra-eko-atlantic-lagos-data-center:current-facility-build"
)

EXPECTED: dict[str, dict[str, Any]] = {
    KENYA_SOURCE: {
        "sha256": KENYA_SHA256,
        "country": "Kenya",
        "address": "Tatu City, near Nairobi, Kenya",
        "campus_key": KENYA_CAMPUS_KEY,
        "project_key": KENYA_PROJECT_KEY,
        "method": "authoritative_construction_start",
    },
    LAGOS_SOURCE: {
        "sha256": LAGOS_SHA256,
        "country": "Nigeria",
        "address": "Eko Atlantic City, Lagos, Nigeria",
        "campus_key": LAGOS_CAMPUS_KEY,
        "project_key": LAGOS_PROJECT_KEY,
        "method": "authoritative_physical_status_update",
    },
}


class AirtelAfricaCurrentConstructionTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = EXPECTED[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Airtel Africa")
        self.assertEqual(evidence["source_family"], "airtel_africa_data_centers")
        self.assertIsNone(evidence["published_at"])
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("131994-byte", metadata["content_hash_scope"])
        self.assertIn("919-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["response_http_date"], "2026-07-17T11:50:12Z")
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["capture_request_epoch_milliseconds"], 1784491108661)
        self.assertEqual(
            metadata["capture_request_timestamp_utc"], "2026-07-19T19:58:28.661Z"
        )
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["effective_url"], SOURCE_URL)
        self.assertEqual(metadata["canonical_url"], SOURCE_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertIn("CDN x-iinfo", metadata["retrieved_at_semantics"])
        self.assertIn("predates this request", metadata["http_date_guardrail"])
        self.assertIn("published_at remains null", metadata["page_publication_guardrail"])
        self.assertIn("start-of-construction", metadata["kenya_status_scope"])
        self.assertIn("under_construction", metadata["lagos_status_scope"])
        self.assertEqual(metadata["kenya_reported_capacity_mw"], 44)
        self.assertEqual(metadata["lagos_reported_capacity_mw"], 38)
        self.assertIn("untyped evidence metadata", metadata["capacity_metric_guardrail"])
        self.assertIn("future forecast", metadata["forecast_guardrail"])
        self.assertIn("no normalized operating model", metadata["classification_guardrail"])
        self.assertIn("does not by itself assign", metadata["role_guardrail"])
        self.assertIn("named localities only", metadata["locality_guardrail"])
        self.assertIn("one evidence record", metadata["duplicate_render_guardrail"])
        self.assertIn("no typed grid connection", metadata["energy_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2025-09-09")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(len(document["lifecycle"]), 1)
        lifecycle = document["lifecycle"][0]
        self.assertEqual(lifecycle["entity"], "project")
        self.assertEqual(lifecycle["value"], "under_construction")
        self.assertEqual(lifecycle["evidence_key"], EVIDENCE_KEY)
        self.assertEqual(lifecycle["as_of_date"], "2025-09-09")
        self.assertEqual(lifecycle["method"], expected["method"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

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
                            retrieved_at=RETRIEVED_AT,
                        )
                self.assertEqual(validate_database(connection), [])
                return (
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, source_family, publisher, content_hash, metadata_json "
                        "FROM evidence"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, status, lifecycle_observations.as_of_date, "
                        "lifecycle_observations.method FROM lifecycle_observations JOIN entities "
                        "ON entities.id = lifecycle_observations.entity_id "
                        "ORDER BY entities.stable_key"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, latitude, longitude, geometry_json, tags_json "
                        "FROM entity_snapshots JOIN entities "
                        "ON entities.id = entity_snapshots.entity_id "
                        "ORDER BY entities.stable_key"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT metric, stage, low, base, high FROM capacity_estimates"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT workload FROM workload_observations"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT operating_model FROM operating_model_observations"
                    )],
                )
            finally:
                connection.close()

    def test_exact_sources_and_shared_evidence_import_offline_in_any_order(self) -> None:
        v18 = (ROOT / "sources" / V18_DEFINITION).read_text(encoding="utf-8")
        documents: dict[str, dict[str, Any]] = {}
        for name, expected in EXPECTED.items():
            path = ROOT / "sources" / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            self.assertNotIn(name, v18)
            document = self._load(name)
            self._assert_guardrails(name, document)
            documents[name] = document
        self.assertEqual(documents[KENYA_SOURCE]["evidence"], documents[LAGOS_SOURCE]["evidence"])

        forward = self._import_state([KENYA_SOURCE, LAGOS_SOURCE])
        reverse = self._import_state([LAGOS_SOURCE, KENYA_SOURCE])
        self.assertEqual(forward, reverse)
        self.assertEqual(
            forward[0],
            [
                ("campus", LAGOS_CAMPUS_KEY),
                ("campus", KENYA_CAMPUS_KEY),
                ("project", LAGOS_PROJECT_KEY),
                ("project", KENYA_PROJECT_KEY),
            ],
        )
        self.assertEqual(len(forward[1]), 1)
        self.assertEqual(forward[1][0][:4], (
            "company_disclosure",
            "airtel_africa_data_centers",
            "Airtel Africa",
            CONTENT_HASH,
        ))
        self.assertEqual(
            forward[2],
            [
                (
                    LAGOS_PROJECT_KEY,
                    "under_construction",
                    "2025-09-09",
                    "authoritative_physical_status_update",
                ),
                (
                    KENYA_PROJECT_KEY,
                    "under_construction",
                    "2025-09-09",
                    "authoritative_construction_start",
                ),
            ],
        )
        self.assertEqual(len(forward[3]), 4)
        for snapshot in forward[3]:
            self.assertIsNone(snapshot[1])
            self.assertIsNone(snapshot[2])
            self.assertIsNone(snapshot[3])
            self.assertFalse(
                any(key.startswith("role:") for key in json.loads(snapshot[4]))
            )
        self.assertEqual(forward[4], [])
        self.assertEqual(forward[5], [])
        self.assertEqual(forward[6], [])

    def test_each_source_alone_preserves_one_generic_project(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(source=name):
                state = self._import_state([name])
                self.assertEqual(
                    state[0],
                    [
                        ("campus", expected["campus_key"]),
                        ("project", expected["project_key"]),
                    ],
                )
                self.assertEqual(len(state[1]), 1)
                self.assertEqual(len(state[2]), 1)
                self.assertEqual(len(state[3]), 2)
                self.assertEqual(state[4:], ([], [], []))

    def test_semantic_mutations_fail_guardrails(self) -> None:
        for name in EXPECTED:
            document = self._load(name)
            mutations: list[dict[str, Any]] = []

            mutated = copy.deepcopy(document)
            mutated["capacities"] = [{"forbidden": "reported MW is untyped"}]
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["workloads"] = [{"forbidden": "future hosting is not workload"}]
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["operating_models"] = [
                {"forbidden": "portfolio services do not type a project"}
            ]
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["campus"]["roles"] = {"operator": ["Nxtra by Airtel Africa"]}
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["project"]["coordinates"] = {
                "latitude": 0.0,
                "longitude": 0.0,
            }
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["lifecycle"][0]["value"] = "commissioning"
            mutations.append(mutated)

            for mutation in mutations:
                with self.subTest(source=name, mutation=mutation):
                    with self.assertRaises(AssertionError):
                        self._assert_guardrails(name, mutation)


if __name__ == "__main__":
    unittest.main()
