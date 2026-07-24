from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-raxio-tz1-tanzania.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "14ef48f59ff1ea9365362a017e68446a362c9cdb748ddffce2ce4be6dc16abd1"
SOURCE_BYTES = 17_197
RETRIEVED_AT = "2026-07-20T19:42:23Z"

CAMPUS_KEY = "curated:raxio-tanzania-tz1-campus"
PROJECT_KEY = "curated:raxio-tanzania-tz1-campus:tz1-facility"
LOCATION_KEY = "raxio-tz1-location-page-captured-2026-07-20"
CAPITAL_KEY = "raxio-capital-expansion-2026-07-13-captured-2026-07-20"
CONSTRUCTION_KEY = "raxio-tanzania-construction-progress-2024-12-23-captured-2026-07-20"

CAPTURES: dict[str, dict[str, Any]] = {
    LOCATION_KEY: {
        "url": "https://www.raxiogroup.com/data-centres/tanzania/",
        "publisher": "Raxio Group",
        "source_family": "raxio_location_pages",
        "published_at": None,
        "body_bytes": 246_017,
        "body_sha256": (
            "3d2943fbf13815cc39a73cff0067e6107616dff5c0225030509df8dc05766dd7"
        ),
        "header_bytes": 1_483,
        "header_sha256": (
            "eef85fd1d49a7cef191df191dfd5ffb7951b818b4fc9a4251ffdbc114fcac5b3"
        ),
        "writeout_bytes": 9_585,
        "writeout_sha256": (
            "96e4aec7a8e4b878002a9cbc68fc57983cf77e89ec4330e6732b535e39c5229d"
        ),
        "content_type": "text/html; charset=UTF-8",
        "response_bytes": 53_692,
        "http_date": "2026-07-20T19:42:21Z",
    },
    CAPITAL_KEY: {
        "url": (
            "https://www.raxiogroup.com/raxio-tops-us380-million-in-committed-"
            "capital-as-roha-and-meridiam-boost-stakes-amid-sixfold-growth-"
            "surge-for-its-african-data-centres/"
        ),
        "publisher": "Raxio Group",
        "source_family": "raxio_newsroom",
        "published_at": "2026-07-13T08:14:21+00:00",
        "body_bytes": 220_564,
        "body_sha256": (
            "a101d2c4fcc5851a9e700ac973907b2cfde6daa7a5aa4f30b0c86328e378e2fd"
        ),
        "header_bytes": 1_569,
        "header_sha256": (
            "3a5bdd5bee84c6691b802701d19fab960e85d112c7636e775cfce1ccfe36b5fe"
        ),
        "writeout_bytes": 10_036,
        "writeout_sha256": (
            "8741ba44d1bb230bae758fa9bc62b080e8806602fb492e1bcf555515af2742e0"
        ),
        "content_type": "text/html; charset=UTF-8",
        "response_bytes": 32_895,
        "http_date": "2026-07-20T19:42:22Z",
    },
    CONSTRUCTION_KEY: {
        "url": (
            "https://www.linkedin.com/posts/raxiodatacentres_as-2024-draws-to-a-"
            "close-raxio-group-reflects-activity-7276831393429483520-ojME"
        ),
        "publisher": "Raxio Data Centres",
        "source_family": "raxio_linkedin_company_posts",
        "published_at": "2024-12-23T05:30:01.153Z",
        "body_bytes": 350_723,
        "body_sha256": (
            "d2cb3eb5e3da4dae448ca5f7c4c3746b14a17e8a8de239ce3a3ff9f7ac2174ac"
        ),
        "header_bytes": 5_348,
        "header_sha256": (
            "0f123c59eb466e87a93cbd10b3eae17b4e174fbdb846c48748e9648e48891c3f"
        ),
        "writeout_bytes": 17_802,
        "writeout_sha256": (
            "9722a88a6a0cd40b5b50fcb06a5adf39b1db78e7285cea89dcd7681a499fbc30"
        ),
        "content_type": "text/html; charset=utf-8",
        "response_bytes": 37_400,
        "http_date": RETRIEVED_AT,
    },
}


class RaxioTz1TanzaniaCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _database_state(
        self, path: Path = SOURCE_PATH, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
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
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "method, confidence, as_of_date, target_date, notes "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id ORDER BY metric",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT workload FROM workload_observations ORDER BY id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
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
        self.assertEqual(len(document["evidence"]), 3)

    def test_capture_quads_and_publication_times_are_exact(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['header_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["response_bytes"],
                )
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(item["source_url"], expected["url"])
                for field in ("requested_url", "effective_url", "canonical_url"):
                    self.assertEqual(metadata[field], expected["url"])

    def test_scope_status_metrics_and_guardrails_are_exact(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Raxio Tanzania TZ1 Campus")
        self.assertEqual(project["name"], "Raxio Tanzania TZ1")
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Tanzania")
            self.assertEqual(entity["address"], "Dar es Salaam, Tanzania")
            self.assertEqual(
                entity["roles"],
                {"developer": ["Raxio Group"], "operator": ["Raxio Group"]},
            )
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CONSTRUCTION_KEY,
                    "as_of_date": "2024-12-23",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.95,
                }
            ],
        )
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": LOCATION_KEY,
                    "as_of_date": "2026-07-20",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            [
                (row["metric"], row["stage"], row["base"])
                for row in document["capacities"]
            ],
            [("critical_it_mw", "planned", 6), ("pue", "design", 1.3)],
        )

        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertEqual(evidence[LOCATION_KEY]["reported_critical_it_mw"], 6)
        self.assertEqual(evidence[LOCATION_KEY]["reported_design_pue"], 1.3)
        self.assertEqual(evidence[LOCATION_KEY]["reported_racks"], 800)
        self.assertIn("No annual energy", evidence[LOCATION_KEY]["energy_guardrail"])
        self.assertIn(
            "no numeric latitude", evidence[LOCATION_KEY]["location_guardrail"]
        )
        self.assertIn(
            "internal parent container",
            evidence[LOCATION_KEY]["entity_model_guardrail"],
        )
        self.assertIn(
            "must never be counted separately",
            evidence[LOCATION_KEY]["entity_model_guardrail"],
        )
        self.assertIn(
            "under development",
            evidence[CAPITAL_KEY]["development_wording_as_reported"],
        )
        self.assertIn("dated 2024", evidence[CONSTRUCTION_KEY]["freshness_guardrail"])
        self.assertIn(
            "no independent", evidence[CONSTRUCTION_KEY]["independence_guardrail"]
        )

    def test_stable_and_evidence_keys_do_not_collide(self) -> None:
        claimed_stable = {CAMPUS_KEY, PROJECT_KEY}
        claimed_evidence = set(CAPTURES)
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
        twice = self._database_state(repetitions=2)
        self.assertEqual(once, twice)
        with tempfile.TemporaryDirectory() as temporary:
            reversed_path = Path(temporary) / SOURCE_NAME
            document = self._load()
            document["evidence"] = list(reversed(document["evidence"]))
            reversed_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reversed_state = self._database_state(reversed_path)
        self.assertEqual(once, reversed_state)

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
            tuple(
                sorted(
                    (
                        key,
                        expected["body_sha256"],
                        RETRIEVED_AT,
                        expected["url"],
                    )
                    for key, expected in CAPTURES.items()
                )
            ),
        )
        self.assertEqual(len(snapshots), 2)
        expected_tags = {
            "address": "Dar es Salaam, Tanzania",
            "country": "Tanzania",
            "role:developer": "Raxio Group",
            "role:operator": "Raxio Group",
            "source_dataset": "curated_official_sources",
        }
        for row in snapshots:
            self.assertEqual(json.loads(row[2]), expected_tags)
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[6], "2026-07-20")
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2024-12-23",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.95,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(
            [(row[1], row[2], row[3], row[5]) for row in capacities],
            [("critical_it_mw", "planned", "MW", 6.0), ("pue", "design", "ratio", 1.3)],
        )
        self.assertEqual(
            operating_models,
            (
                (
                    PROJECT_KEY,
                    "colocation",
                    "2026-07-20",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(workloads, ())


if __name__ == "__main__":
    unittest.main()
