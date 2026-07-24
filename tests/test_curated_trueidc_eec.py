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
SOURCE = "curated-official-2026-07-19-trueidc-eec-mega-data-center.json"
SOURCE_SHA256 = "29b8f8af4e9612b778cbc4d1015a75d0b76de938b85e5551a369d1b15d7feadb"
RETRIEVED_AT = "2026-07-19T20:23:56Z"
CONTENT_HASH = "c76de4570a8fcb7e65f4d4f2ca4a54c853f733bbc80f70e131fb795baa551f90"
HEADERS_HASH = "bc48492b55ef0862322985153d049db2f97ea10dee96d6eefe91046cc792e0f7"
WRITEOUT_HASH = "b3f3b4d18f4c4ad5a40b51d9c9447aeb11eb4b3cc7f9db33bbd8403cbc310d9d"
SOURCE_URL = (
    "https://www.trueidc.com/en/news-detail/232/"
    "new-data-center-groundbreaking-EEC"
)
EVIDENCE_KEY = (
    "trueidc-eec-mega-data-center-groundbreaking-2026-03-31-"
    "captured-2026-07-19"
)
CAMPUS_KEY = "curated:trueidc-eec-mega-data-center-campus"
PROJECT_KEY = "curated:trueidc-eec-mega-data-center-campus:phase-1"


class TrueIdcEecTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / SOURCE).read_text(encoding="utf-8"))

    def _assert_guardrails(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "True IDC")
        self.assertEqual(evidence["source_family"], "true_idc_news")
        self.assertEqual(evidence["published_at"], "2026-03-31")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("51577-byte", metadata["content_hash_scope"])
        self.assertIn("3661-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertIn("203-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_HASH)
        self.assertIn("transient session", metadata["capture_headers_sensitive_data_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 9505)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["effective_url"], SOURCE_URL)
        self.assertEqual(metadata["canonical_url"], SOURCE_URL)
        self.assertIn("og:url", metadata["canonical_url_basis"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("exact response HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("displayed on the individual", metadata["publication_date_scope"])
        self.assertIn("Breaking Ground", metadata["construction_wording_as_reported"])
        self.assertIn("one generic Phase 1", metadata["status_scope"])
        self.assertIn("distinct from", metadata["identity_scope"])
        self.assertEqual(metadata["reported_total_power_capacity_mw_maximum"], 250)
        self.assertIn("creates no normalized capacity row", metadata["capacity_metric_guardrail"])
        self.assertEqual(metadata["boi_promotion_aggregate_investment_baht_minimum"], 77_000_000_000)
        self.assertIn("several major projects", metadata["investment_guardrail"])
        self.assertEqual(metadata["phase_one_forecast_as_reported"], "scheduled to be operational by 2027")
        self.assertIn("future forecast", metadata["forecast_guardrail"])
        self.assertIn("ai_specialized_unspecified", metadata["ai_classification_scope"])
        self.assertIn("no additional normalized workload", metadata["classification_guardrail"])
        self.assertIn("does not by itself assign", metadata["role_guardrail"])
        self.assertIn("broad region only", metadata["locality_guardrail"])
        self.assertIn("no numeric value", metadata["pue_guardrail"])
        self.assertIn("qualitative", metadata["energy_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No publisher photograph", metadata["imagery_guardrail"])

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], "Thailand")
            self.assertEqual(entity["address"], "Eastern Economic Corridor, Thailand")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2026-03-31")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-03-31",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-03-31",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["capacities"], [])

    def test_exact_source_imports_offline_with_untyped_power(self) -> None:
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
                        "SELECT status, as_of_date, method FROM lifecycle_observations"
                    )],
                    [
                        (
                            "under_construction",
                            "2026-03-31",
                            "authoritative_construction_start",
                        )
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, as_of_date, method FROM workload_observations"
                    )],
                    [
                        (
                            "ai_specialized_unspecified",
                            "2026-03-31",
                            "company_disclosure",
                        )
                    ],
                )
                for table in (
                    "capacity_estimates",
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
                        "Eastern Economic Corridor, Thailand",
                    )
                    self.assertFalse(any(key.startswith("role:") for key in tags))

                metadata = json.loads(
                    connection.execute("SELECT metadata_json FROM evidence").fetchone()[0]
                )["record"]
                self.assertEqual(metadata["reported_total_power_capacity_mw_maximum"], 250)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        document = self._load()
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["capacities"] = [{"forbidden": "250 MW metric is ambiguous"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["operating_models"] = [{"forbidden": "hyperscale is design context"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"][0]["value"] = "ai_training"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"].append({"forbidden": "cloud is not another workload row"})
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["campus"]["roles"] = {"developer": ["True IDC"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["coordinates"] = {
            "latitude": 13.0,
            "longitude": 101.0,
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(mutation)


if __name__ == "__main__":
    unittest.main()
