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
SOURCE = "curated-official-2026-07-19-sdaia-hexagon-riyadh.json"
SOURCE_SHA256 = "73d7ca1c5d5ecdfd187c03457b421b2ef4e13a2b9ef305899e1b2ffb383c9ed8"
RETRIEVED_AT = "2026-07-19T19:52:50Z"
CONTENT_HASH = "8abe8623782f6f6a096ca7d8ecf9508a51fa545cfd8443b30cc3e65a80985ee7"
HEADERS_HASH = "61266732e9894e5cefbd014489ea3f40dd87a4cd7ed2dc0fb47ceee5435df34a"
SOURCE_URL = "https://www.spa.gov.sa/en/N2480096"
EVIDENCE_KEY = (
    "sdaia-hexagon-riyadh-foundation-stone-2026-01-01-captured-2026-07-19"
)
CAMPUS_KEY = "curated:sdaia-hexagon-riyadh-government-data-center"
PROJECT_KEY = (
    "curated:sdaia-hexagon-riyadh-government-data-center:current-facility-build"
)


class SdaiaHexagonRiyadhTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / SOURCE).read_text(encoding="utf-8"))

    def _assert_guardrails(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "government_record")
        self.assertEqual(evidence["publisher"], "Saudi Press Agency")
        self.assertEqual(
            evidence["source_family"], "saudi_press_agency_government_news"
        )
        self.assertEqual(evidence["published_at"], "2026-01-01")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("178320-byte", metadata["content_hash_scope"])
        self.assertIn("945-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["effective_url"], SOURCE_URL)
        self.assertEqual(metadata["canonical_url"], SOURCE_URL)
        self.assertNotIn("request_started_at", metadata)
        self.assertNotIn("request_start_utc", metadata)
        self.assertIn(
            "no request-start artifact was supplied", metadata["retrieval_method"]
        )
        self.assertIn(
            "official start of construction",
            metadata["construction_wording_as_reported"],
        )
        self.assertIn("generic project", metadata["status_scope"])
        self.assertEqual(metadata["reported_total_capacity_mw"], 480)
        self.assertIn("untyped evidence metadata", metadata["capacity_metric_guardrail"])
        self.assertEqual(metadata["reported_area_lower_bound_square_feet"], 30000000)
        self.assertIn("not a source-verifiable parcel", metadata["area_guardrail"])
        self.assertIn("reported design or classification", metadata["tier_guardrail"])
        self.assertIn("no normalized workload", metadata["government_use_guardrail"])
        self.assertIn("does not by itself assign", metadata["role_guardrail"])
        self.assertIn("city-level locality", metadata["locality_guardrail"])
        self.assertIn("not independently validated", metadata["superlative_guardrail"])
        self.assertIn("no typed grid connection", metadata["energy_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], "Saudi Arabia")
            self.assertEqual(entity["address"], "Riyadh, Saudi Arabia")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2026-01-01")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-01-01",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

    def test_exact_source_imports_offline_without_derived_metrics(self) -> None:
        source_path = ROOT / "sources" / SOURCE
        self.assertEqual(
            hashlib.sha256(source_path.read_bytes()).hexdigest(), SOURCE_SHA256
        )
        self.assertNotIn(
            SOURCE,
            (ROOT / "sources" / V18_DEFINITION).read_text(encoding="utf-8"),
        )
        self._assert_guardrails(self._load())

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
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        source_path,
                        retrieved_at=RETRIEVED_AT,
                    )

                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 1)
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key"
                    )],
                    [("campus", CAMPUS_KEY), ("project", PROJECT_KEY)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, source_family, publisher, content_hash "
                        "FROM evidence"
                    )],
                    [
                        (
                            "government_record",
                            "saudi_press_agency_government_news",
                            "Saudi Press Agency",
                            CONTENT_HASH,
                        )
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT status, as_of_date, method FROM lifecycle_observations"
                    )],
                    [
                        (
                            "under_construction",
                            "2026-01-01",
                            "authoritative_construction_start",
                        )
                    ],
                )
                for table in (
                    "capacity_estimates",
                    "workload_observations",
                    "operating_model_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                    )

                snapshots = connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                ).fetchall()
                self.assertEqual(len(snapshots), 2)
                for snapshot in snapshots:
                    self.assertIsNone(snapshot["latitude"])
                    self.assertIsNone(snapshot["longitude"])
                    self.assertIsNone(snapshot["geometry_json"])
                    tags = json.loads(snapshot["tags_json"])
                    self.assertEqual(tags["address"], "Riyadh, Saudi Arabia")
                    self.assertFalse(any(key.startswith("role:") for key in tags))

                metadata = json.loads(
                    connection.execute("SELECT metadata_json FROM evidence").fetchone()[0]
                )["record"]
                self.assertEqual(metadata["reported_total_capacity_mw"], 480)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_source_guardrails(self) -> None:
        document = self._load()
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["capacities"] = [{"forbidden": "480 MW is untyped"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"] = [{"forbidden": "government purpose is not workload"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["operating_models"] = [
            {"forbidden": "government data center is not a normalized model"}
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["campus"]["roles"] = {"operator": ["SDAIA"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["coordinates"] = {
            "latitude": 24.7,
            "longitude": 46.7,
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["method"] = "physical_observation"
        mutations.append(mutated)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(mutation)


if __name__ == "__main__":
    unittest.main()
