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
BASE_DEFINITION = "open-seed-2026-07-19-v19.json"
SOURCE = "curated-official-2026-07-19-ada-gru10-franco-da-rocha.json"
SOURCE_SHA256 = "28f9794c82b0eb9d0eb4a36b75a71402e9d0835bca080693512978fe0503eda2"
RETRIEVED_AT = "2026-07-19T20:16:33Z"
CONTENT_HASH = "db9408e1ad1730ebff2308429b348b12cc2b93bca01a02f6735376571d8fae5a"
HEADERS_HASH = "bc8ce10eb74c1cdb6a2971d53d5f36d3c10466a2fa998803aae4eca76828daab"
WRITEOUT_HASH = "b01da3546ca5d84065895c96d2622e6c1c876ad4f0fba317f727890c18351c67"
SOURCE_URL = (
    "https://adainfrastructure.com/en-US/insights/news/"
    "ada-infrastructure-announces-groundbreaking-of-its-first-data-center-"
    "campus-in-brazil"
)
EVIDENCE_KEY = (
    "ada-gru10-franco-da-rocha-groundbreaking-2026-06-25-captured-2026-07-19"
)
CAMPUS_KEY = "curated:ada-gru10-franco-da-rocha-campus"
PROJECT_KEY = "curated:ada-gru10-franco-da-rocha-campus:phase-1"


class AdaGru10Tests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / SOURCE).read_text(encoding="utf-8"))

    def _assert_guardrails(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Ada Infrastructure")
        self.assertEqual(evidence["source_family"], "ada_infrastructure_press_releases")
        self.assertEqual(evidence["published_at"], "2026-06-25")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("42414-byte", metadata["content_hash_scope"])
        self.assertIn("969-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertIn("261-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 8616)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["effective_url"], SOURCE_URL)
        self.assertEqual(metadata["canonical_url"], SOURCE_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("exact response HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("displayed on the individual", metadata["publication_date_scope"])
        self.assertIn("groundbreaking of the first phase", metadata["construction_wording_as_reported"])
        self.assertIn("one GRU10 Phase 1", metadata["status_scope"])
        self.assertEqual(metadata["reported_onsite_substation_count"], 2)
        self.assertEqual(metadata["reported_onsite_substation_total_capacity_mw"], 300)
        self.assertEqual(metadata["reported_phase_one_data_center_building_count"], 1)
        self.assertEqual(metadata["reported_phase_one_onsite_substation_count"], 1)
        self.assertEqual(metadata["reported_full_campus_maximum_data_center_building_count"], 3)
        self.assertIn("creates no normalized capacity row", metadata["capacity_metric_guardrail"])
        self.assertIn("future construction forecast", metadata["forecast_guardrail"])
        self.assertIn("no normalized workload", metadata["classification_guardrail"])
        self.assertIn("does not by itself assign", metadata["role_guardrail"])
        self.assertIn("named locality only", metadata["locality_guardrail"])
        self.assertIn("no generation asset", metadata["energy_guardrail"])
        self.assertIn("creates no additional", metadata["portfolio_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], "Brazil")
            self.assertEqual(
                entity["address"],
                "Franco da Rocha Municipality, Sao Paulo, Brazil",
            )
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2026-06-25")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-06-25",
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
            (ROOT / "sources" / BASE_DEFINITION).read_text(encoding="utf-8"),
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
                        "SELECT kind, source_family, publisher, content_hash FROM evidence"
                    )],
                    [
                        (
                            "company_disclosure",
                            "ada_infrastructure_press_releases",
                            "Ada Infrastructure",
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
                            "2026-06-25",
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
                    "SELECT latitude, longitude, geometry_json, tags_json "
                    "FROM entity_snapshots"
                ).fetchall()
                self.assertEqual(len(snapshots), 2)
                for snapshot in snapshots:
                    self.assertIsNone(snapshot["latitude"])
                    self.assertIsNone(snapshot["longitude"])
                    self.assertIsNone(snapshot["geometry_json"])
                    tags = json.loads(snapshot["tags_json"])
                    self.assertEqual(
                        tags["address"],
                        "Franco da Rocha Municipality, Sao Paulo, Brazil",
                    )
                    self.assertFalse(any(key.startswith("role:") for key in tags))

                metadata = json.loads(
                    connection.execute("SELECT metadata_json FROM evidence").fetchone()[0]
                )["record"]
                self.assertEqual(metadata["reported_onsite_substation_total_capacity_mw"], 300)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        document = self._load()
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["capacities"] = [{"forbidden": "300 MW is substation metadata"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"] = [{"forbidden": "design language is not workload"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["operating_models"] = [{"forbidden": "no project model is stated"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["campus"]["roles"] = {"developer": ["Ada Infrastructure"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["coordinates"] = {
            "latitude": -23.3,
            "longitude": -46.7,
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["method"] = "authoritative_physical_status_update"
        mutations.append(mutated)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(mutation)


if __name__ == "__main__":
    unittest.main()
