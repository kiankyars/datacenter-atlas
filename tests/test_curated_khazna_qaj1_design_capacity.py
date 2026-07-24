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
BASE_SOURCE = "curated-official-2026-07-19-khazna-qaj1-ajman.json"
DESIGN_SOURCE = "curated-official-2026-07-19-khazna-qaj1-tier-iii-design.json"
DESIGN_SHA256 = "7366625bdc8a737943bfdc8eee6f5ffbf753efb6602393f5b1fdedfb672482af"
BASE_RETRIEVED_AT = "2026-07-19T19:28:32Z"
DESIGN_RETRIEVED_AT = "2026-07-19T19:42:43Z"
CAMPUS_KEY = "curated:khazna-qaj1-ajman-data-center"
PROJECT_KEY = "curated:khazna-qaj1-ajman-data-center:current-facility-build"
EVIDENCE_KEY = (
    "khazna-qaj1-tier-iii-design-certification-2026-02-24-captured-2026-07-19"
)
CONTENT_HASH = "21445bbf241aec3b379417d7e2111477b535b829f542a87ffce4dfb641fd2698"
HEADERS_HASH = "668706a6670d2a3a6867574321f9a1241e2cbd266b356b4397c175727352c689"
SOURCE_URL = (
    "https://khaznadatacenters.com/press-release/"
    "khazna-awarded-tier-iii-certification-of-design-documents-for-ajman-"
    "uae-facility/"
)


class KhaznaQAJ1DesignCapacityTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / DESIGN_SOURCE).read_text(encoding="utf-8"))

    def _assert_guardrails(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["published_at"], "2026-02-24")
        self.assertEqual(evidence["retrieved_at"], DESIGN_RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("71153-byte", metadata["content_hash_scope"])
        self.assertIn("1030-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 17317)
        self.assertEqual(metadata["response_http_date"], DESIGN_RETRIEVED_AT)
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
        self.assertEqual(metadata["facility_code_as_reported"], "QAJ01")
        self.assertEqual(metadata["total_it_load_as_reported_mw"], 100)
        self.assertEqual(metadata["data_hall_count_as_reported"], 20)
        self.assertEqual(metadata["per_data_hall_it_capacity_as_reported_mw"], 5)
        self.assertIn("same Khazna QAJ1 facility", metadata["identity_scope"])
        self.assertIn("creates no lifecycle observation", metadata["certification_scope_guardrail"])
        self.assertIn("without creating per-hall rows", metadata["capacity_scope"])
        self.assertIn("creates no additional training", metadata["workload_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], "United Arab Emirates")
            self.assertEqual(entity["address"], "Ajman, United Arab Emirates")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["as_of_date"], "2026-02-24")

        self.assertEqual(document["lifecycle"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(capacity["entity"], "project")
        self.assertEqual(capacity["metric"], "critical_it_mw")
        self.assertEqual(capacity["stage"], "planned")
        self.assertEqual(capacity["unit"], "MW")
        self.assertEqual((capacity["low"], capacity["base"], capacity["high"]), (100, 100, 100))
        self.assertEqual(capacity["method"], "reported")
        self.assertEqual(capacity["evidence_key"], EVIDENCE_KEY)
        self.assertEqual(capacity["as_of_date"], "2026-02-24")
        self.assertIsNone(capacity["target_date"])

    def _import_state(self, order: list[str]) -> tuple[list[tuple[Any, ...]], ...]:
        retrieved_at = {
            BASE_SOURCE: BASE_RETRIEVED_AT,
            DESIGN_SOURCE: DESIGN_RETRIEVED_AT,
        }
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(socket, "socket", side_effect=AssertionError("network used")), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name in order:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=retrieved_at[name],
                        )
                self.assertEqual(validate_database(connection), [])
                return (
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT content_hash FROM evidence ORDER BY content_hash"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT status, as_of_date, method FROM lifecycle_observations"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT workload, as_of_date, method FROM workload_observations"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, metric, stage, low, base, high, unit, "
                        "target_date FROM capacity_estimates JOIN entities "
                        "ON entities.id = capacity_estimates.entity_id"
                    )],
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, entity_snapshots.as_of_date, latitude, "
                        "longitude, geometry_json, tags_json FROM entity_snapshots "
                        "JOIN entities ON entities.id = entity_snapshots.entity_id "
                        "ORDER BY entities.stable_key, entity_snapshots.as_of_date"
                    )],
                )
            finally:
                connection.close()

    def test_exact_design_source_imports_offline(self) -> None:
        definition = (ROOT / "sources" / V16_DEFINITION).read_text(encoding="utf-8")
        self.assertNotIn(DESIGN_SOURCE, definition)
        self.assertNotIn(CONTENT_HASH, definition)
        source_path = ROOT / "sources" / DESIGN_SOURCE
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), DESIGN_SHA256)
        self._assert_guardrails(self._load())

        state = self._import_state([DESIGN_SOURCE])
        self.assertEqual(state[0], [("campus", CAMPUS_KEY), ("project", PROJECT_KEY)])
        self.assertEqual(state[1], [(CONTENT_HASH,)])
        self.assertEqual(state[2], [])
        self.assertEqual(state[3], [])
        self.assertEqual(
            state[4],
            [(PROJECT_KEY, "critical_it_mw", "planned", 100.0, 100.0, 100.0, "MW", None)],
        )
        self.assertEqual(len(state[5]), 2)
        for row in state[5]:
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertFalse(any(key.startswith("role:") for key in json.loads(row[5])))

    def test_base_and_design_sources_reuse_identity_in_any_order(self) -> None:
        forward = self._import_state([BASE_SOURCE, DESIGN_SOURCE])
        reverse = self._import_state([DESIGN_SOURCE, BASE_SOURCE])
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward[0]), 2)
        self.assertEqual(len(forward[1]), 2)
        self.assertEqual(
            forward[2], [("shell", "2025-04-21", "authoritative_physical_status_update")]
        )
        self.assertEqual(
            forward[3], [("ai_specialized_unspecified", "2025-04-21", "company_disclosure")]
        )
        self.assertEqual(len(forward[4]), 1)
        self.assertEqual(len(forward[5]), 4)

    def test_semantic_mutations_fail_guardrails(self) -> None:
        document = self._load()
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["capacities"][0]["metric"] = "gross_facility_mw"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["capacities"].append(copy.deepcopy(mutated["capacities"][0]))
        mutated["capacities"][1].update({"low": 5, "base": 5, "high": 5})
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"] = [{"forbidden": "design certificate is not physical status"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"] = [{"forbidden": "training and inference capability"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["roles"] = {"operator": ["Khazna Data Centers"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["campus"]["coordinates"] = {"latitude": 25.4, "longitude": 55.5}
        mutations.append(mutated)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(mutation)


if __name__ == "__main__":
    unittest.main()
