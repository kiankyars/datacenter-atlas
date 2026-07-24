from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "curated-official-2026-07-20-creekstone-delta-gigasite.json"
SOURCE_SHA256 = "9fa05e548c624f96ed3d6c5bfbf51681e05fdfc6483df7f10b2b9c110338da90"
RETRIEVED_AT = "2026-07-20T06:14:45Z"
CAMPUS_KEY = "curated:creekstone-delta-gigasite-campus"
PROJECT_KEY = CAMPUS_KEY + ":current-campus-development"

CAPTURES: dict[str, dict[str, Any]] = {
    "creekstone-delta-project-page-current-captured-2026-07-20": {
        "kind": "company_disclosure",
        "publisher": "Creekstone Energy",
        "family": "creekstone_energy_project_pages",
        "published_at": None,
        "url": "https://www.creekstone.energy/delta",
        "body_bytes": 23484,
        "body_hash": "2874e9401dd7be4d35695b4cc2bb23502a4d95bb594a9964b158dc5caa4ace4e",
        "headers_bytes": 484,
        "headers_hash": "a5baa48bbd8954a4e2fec33073ce3b765d8a39293e109a198434c57055bb15c5",
        "writeout_bytes": 16186,
        "writeout_hash": "714fba06a714c94bfeea011b34c2c42aed7251fa5255c50be4a75e6cd4510c67",
        "download_bytes": 5929,
        "last_modified": "2026-07-17T10:40:29Z",
        "content_type": "text/html; charset=utf-8",
    },
    "creekstone-delta-progress-page-current-captured-2026-07-20": {
        "kind": "company_disclosure",
        "publisher": "Creekstone Energy",
        "family": "creekstone_energy_progress_pages",
        "published_at": None,
        "url": "https://www.creekstone.energy/progress",
        "body_bytes": 15244,
        "body_hash": "390cbcfdce7b65548737382d9058c1e5c5038e6129f77273f514c118a69acd37",
        "headers_bytes": 487,
        "headers_hash": "beb7c3fe8721097b7c625b8147b9929ff9dbf4f04407d0cb7fba9e42c916c0bb",
        "writeout_bytes": 16202,
        "writeout_hash": "7de79694e2a5d3f90d18e2fca3126d1aa6e1a204e6be3bc02799b661d0c69354",
        "download_bytes": 4099,
        "last_modified": "2026-07-17T05:28:50Z",
        "content_type": "text/html; charset=utf-8",
    },
    "utah-goed-creekstone-delta-construction-2026-04-09-captured-2026-07-20": {
        "kind": "government_record",
        "publisher": "Utah Governor's Office of Economic Opportunity",
        "family": "utah_governors_office_economic_opportunity",
        "published_at": "2026-04-09T16:20:32Z",
        "url": (
            "https://business.utah.gov/tax-credits/"
            "creekstone-energy-llc-commits-17-billion-to-millard-county-"
            "data-center-project/"
        ),
        "body_bytes": 111064,
        "body_hash": "23f81d5308df21f0156088a70303787f762d2b0c8a7bbe744399d4a4a7ca2612",
        "headers_bytes": 1245,
        "headers_hash": "86ce1686193703add394b36118fb184c2f2f06d07a3810397a4e3505ecb7cb65",
        "writeout_bytes": 12985,
        "writeout_hash": "ae059f01076ed28780338b972d3e9c9414ce9bc1eddbfc3022aa036d7b4f9c85",
        "download_bytes": 23461,
        "last_modified": "2026-04-09T16:20:35Z",
        "content_type": "text/html; charset=UTF-8",
    },
}


class CreekstoneDeltaCuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Creekstone curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_exact_source_is_canonical_byte_pinned_and_semantically_narrow(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        document = self._load()
        self.assertEqual(
            SOURCE.read_text(encoding="utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 3)
        self.assertEqual(
            {item["retrieved_at"] for item in document["evidence"]},
            {RETRIEVED_AT},
        )
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(
                entity["address"],
                "Near Delta, Millard County, Utah, United States",
            )
            self.assertEqual(entity["roles"], {"developer": ["Creekstone Energy"]})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "creekstone-delta-project-page-current-captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-20",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": (
                        "creekstone-delta-project-page-current-captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-20",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )

    def test_exact_capture_provenance_is_byte_bound(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["kind"], expected["kind"])
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["content_hash"], expected["body_hash"])
                self.assertIn(
                    f"exact {expected['body_bytes']}-byte",
                    metadata["content_hash_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_hash"]
                )
                self.assertIn(
                    f"exact {expected['headers_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_hash"],
                )
                self.assertIn(
                    f"exact {expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertIsNone(metadata["http_content_length_bytes_as_received"])
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download_bytes"],
                )
                self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertIn("retries disabled", metadata["retrieval_method"])
                self.assertIn(
                    "no Authorization", metadata["request_credentials_guardrail"]
                )

    def test_ambiguous_power_physical_stage_and_roles_cannot_leak(self) -> None:
        document = self._load()
        project_metadata = document["evidence"][0]["metadata"]
        progress_metadata = document["evidence"][1]["metadata"]
        government_metadata = document["evidence"][2]["metadata"]
        for wording in (
            "220 MW",
            ">10 GW",
            "43,000 Dth/day initial capacity (230 MW)",
        ):
            self.assertIn(wording, json.dumps(document, ensure_ascii=False))
        self.assertIn("No normalized capacity row", project_metadata["phase_one_capacity_guardrail"])
        self.assertIn("creates no capacity row", project_metadata["full_build_power_guardrail"])
        self.assertIn("not electrical output", project_metadata["gas_interconnect_guardrail"])
        self.assertIn("presently documented field work centers on gas", project_metadata["status_scope"])
        self.assertIn("creates no separate lifecycle row", progress_metadata["physical_scope"])
        self.assertIn("supporting developer only", project_metadata["role_scope"])
        self.assertIn("aims to establish", government_metadata["capacity_guardrail"])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])

    def test_keys_do_not_collide_with_other_curated_sources(self) -> None:
        document = self._load()
        entity_keys = {document["campus"]["stable_key"], document["project"]["stable_key"]}
        evidence_keys = {item["key"] for item in document["evidence"]}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE:
                continue
            other = json.loads(path.read_text(encoding="utf-8"))
            other_entities = {
                record["stable_key"]
                for name in ("campus", "project")
                if isinstance((record := other.get(name)), dict)
            }
            other_evidence = {item["key"] for item in other.get("evidence", [])}
            self.assertFalse(entity_keys & other_entities, path.name)
            self.assertFalse(evidence_keys & other_evidence, path.name)

    def test_import_is_offline_valid_idempotent_and_exact(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    first = CuratedOfficialSourceAdapter().import_file(
                        connection, SOURCE, retrieved_at=RETRIEVED_AT
                    )
                    second = CuratedOfficialSourceAdapter().import_file(
                        connection, SOURCE, retrieved_at=RETRIEVED_AT
                    )
                self.assertEqual(first.entities_created, 2)
                self.assertEqual(first.evidence_created, 3)
                self.assertEqual(first.warnings, ())
                self.assertEqual(second.entities_created, 0)
                self.assertEqual(second.evidence_created, 0)
                self.assertEqual(second.warnings, ())
                self.assertEqual(validate_database(connection), [])
                expected_counts = {
                    "entities": 2,
                    "evidence": 3,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "workload_observations": 1,
                    "operating_model_observations": 0,
                    "capacity_estimates": 0,
                }
                for table, expected in expected_counts.items():
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        expected,
                        table,
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
