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
BASE_DEFINITIONS = (
    "open-seed-2026-07-19-v18.json",
    "open-seed-2026-07-19-v19.json",
)
SOURCE = "curated-official-2026-07-19-meeza-mvault6-um-garn.json"
SOURCE_SHA256 = "7c1b94944516e860b704e0a48891a9cdc62cfdae6cd6dc258bb82bed7bcf1c00"
RETRIEVED_AT = "2026-07-19T20:05:07Z"
CONTENT_HASH = "b5199caaab2bed3dbe94466d99c815b4f25ff5ef35d97babd41df2b6f41020cf"
HEADERS_HASH = "6ce594873846c07b86002f9700b7c6995bf305bf1789803a09c871e734fd437e"
SOURCE_URL = (
    "https://www.meeza.net/meeza-achieves-10-1-net-profit-growth-during-"
    "2025-and-board-of-directors-recommends-cash-dividend-of-8-5-of-"
    "nominal-share-value/"
)
EVIDENCE_KEY = (
    "meeza-mvault6-um-garn-under-construction-2026-02-23-captured-2026-07-19"
)
CAMPUS_KEY = "curated:meeza-mvault6-um-garn-campus"
PROJECT_KEY = "curated:meeza-mvault6-um-garn-campus:current-campus-build"


class MeezaMVault6Tests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / SOURCE).read_text(encoding="utf-8"))

    def _assert_guardrails(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "MEEZA")
        self.assertEqual(evidence["source_family"], "meeza_news_and_press_releases")
        self.assertEqual(evidence["published_at"], "2026-02-23")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        self.assertEqual(evidence["source_url"], SOURCE_URL)

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("47809-byte", metadata["content_hash_scope"])
        self.assertIn("850-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertIsNone(metadata["content_encoding_as_received"])
        self.assertEqual(metadata["http_transfer_encoding_as_received"], "chunked")
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["requested_url"], SOURCE_URL)
        self.assertEqual(metadata["effective_url"], SOURCE_URL)
        self.assertEqual(metadata["canonical_url"], SOURCE_URL)
        self.assertEqual(metadata["publisher_shortlink"], "https://www.meeza.net/?p=64606")
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertIn("without response content encoding", metadata["retrieval_method"])
        self.assertIn("exact response HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("displayed on the individual", metadata["publication_date_scope"])
        self.assertIn("is under construction", metadata["construction_wording_as_reported"])
        self.assertIn("generic M-Vault 6", metadata["status_scope"])
        self.assertEqual(metadata["reported_campus_scale_mw"], 24)
        self.assertEqual(metadata["reported_first_operational_increment_mw"], 6)
        self.assertIn("untyped evidence metadata", metadata["capacity_metric_guardrail"])
        self.assertIn("future forecast", metadata["forecast_guardrail"])
        self.assertIn("do not create entities", metadata["sibling_project_guardrail"])
        self.assertIn("no normalized workload", metadata["classification_guardrail"])
        self.assertIn("does not by itself assign", metadata["role_guardrail"])
        self.assertIn("named locality only", metadata["locality_guardrail"])
        self.assertIn("financial or corporate metrics", metadata["financial_guardrail"])
        self.assertIn("no typed grid connection", metadata["energy_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], "Qatar")
            self.assertEqual(entity["address"], "Um Garn, Qatar")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], "2026-02-23")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-02-23",
                    "method": "authoritative_physical_status_update",
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
        for definition in BASE_DEFINITIONS:
            self.assertNotIn(
                SOURCE,
                (ROOT / "sources" / definition).read_text(encoding="utf-8"),
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
                            "meeza_news_and_press_releases",
                            "MEEZA",
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
                            "2026-02-23",
                            "authoritative_physical_status_update",
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
                    self.assertEqual(tags["address"], "Um Garn, Qatar")
                    self.assertFalse(any(key.startswith("role:") for key in tags))

                metadata = json.loads(
                    connection.execute("SELECT metadata_json FROM evidence").fetchone()[0]
                )["record"]
                self.assertEqual(metadata["reported_campus_scale_mw"], 24)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        document = self._load()
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["capacities"] = [{"forbidden": "24 and 6 MW remain untyped"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"] = [{"forbidden": "corporate demand is not workload"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["operating_models"] = [{"forbidden": "no project model is stated"}]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["campus"]["roles"] = {"operator": ["MEEZA"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["coordinates"] = {
            "latitude": 25.4,
            "longitude": 51.4,
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["method"] = "authoritative_construction_start"
        mutations.append(mutated)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_guardrails(mutation)


if __name__ == "__main__":
    unittest.main()
