from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-cdc-beard-be1.json"
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 8_943
SOURCE_SHA256 = "0ba3f8fc5bc23a82b6b2b49c578a1518f94aa8122bcd19c6a6f5246f24989b5a"
RECORDED_AT = "2026-07-21T05:40:00Z"
ARTIFACT = ROOT / "source_artifacts/cdc-beard-be1-official-2026-07-20-v1"
V63_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
V63_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v63/entities.csv"

EVIDENCE_KEY = "cdc-canberra-beard-be1-location-page-captured-2026-07-20"
CAMPUS_KEY = "curated:cdc-beard-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:be1-current-build"

CAPTURE_BODY = (
    109_984,
    "2ed5c67bfe164a1941dcbc6425cb3610afc60ddba5525bd487fd720821468eed",
)
CAPTURE_HEADERS = (
    3_412,
    "54afea59236c1f456117988cfcbbdb3bca038ff5c857866edcfea46baff8c286",
)
CAPTURE_WRITEOUT = (
    9_381,
    "98e1ea9ee723d2d5dd61c8d883d77d0280553a4243a66caa690e977a93f6d7f7",
)
ARTIFACT_FILE_SPECS = {
    "README.md": (
        1_466,
        "b5b8459d1110af1a04b088445b3d983ad4cb9170dfd777d5854afb5d30bd8d3f",
    ),
    "manifest.json": (
        1_036,
        "67af53ceaa386754320958e250e7da6fea2257f47817047b27e881fdf2d403ee",
    ),
    "manifest.sha256": (
        80,
        "c7e17934593a634f738127211aafcbe17629da4f20057803646ee11782e03523",
    ),
    "retrieval-inventory.json": (
        2_567,
        "069ff16aa97f8508f96cd4cf05e03f6c4685dc979a9115b80d53b39f2477a3a4",
    ),
    "source-snapshot.json": (
        1_522,
        "81f163b40a5a9df042cadbd7a2274020635cea6cd3749da07a447e426cacfb7e",
    ),
}


def sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class CdcBeardBe1CuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError(
            "CDC Beard BE1 curated import attempted network access"
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import(self, *, repetitions: int = 1):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = []
        with self._offline():
            for _ in range(repetitions):
                results.append(
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at=RECORDED_AT,
                    )
                )
        return temporary, connection, results

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        text = data.decode("utf-8")
        document = json.loads(text)
        self.assertEqual(
            text,
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertNotIn("captured-2026-07-21", text)
        self.assertNotIn('"as_of_date": "2026-07-21"', text)
        self.assertEqual([row["key"] for row in document["evidence"]], [EVIDENCE_KEY])

    def test_capture_facts_and_compact_frozen_artifact_are_exact(self) -> None:
        evidence = self._load()["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["content_hash"], CAPTURE_BODY[1])
        self.assertEqual(evidence["retrieved_at"], "2026-07-21T05:32:34Z")
        self.assertEqual(evidence["published_at"], None)
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertIn(str(CAPTURE_BODY[0]), metadata["content_hash_scope"])
        self.assertEqual(
            (metadata["capture_headers_bytes"], metadata["capture_headers_sha256"]),
            CAPTURE_HEADERS,
        )
        self.assertEqual(
            (
                metadata["capture_curl_writeout_bytes"],
                metadata["capture_curl_writeout_sha256"],
            ),
            CAPTURE_WRITEOUT,
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version"], "HTTP/2")
        self.assertEqual(metadata["wire_download_bytes"], 40_866)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["requested_url"], metadata["effective_url"])
        self.assertEqual(metadata["effective_url"], metadata["canonical_url"])

        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {item.name for item in ARTIFACT.iterdir() if item.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            file_path = ARTIFACT / name
            self.assertFalse(file_path.is_symlink())
            self.assertEqual(len(file_path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(file_path), expected_hash)
            self.assertEqual(stat.S_IMODE(file_path.stat().st_mode), 0o444)

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(
            set(manifest["closed_file_set"]),
            set(ARTIFACT_FILE_SPECS),
        )
        self.assertFalse(manifest["raw_capture_redistributed"])
        for entry in manifest["files"]:
            file_path = ARTIFACT / entry["path"]
            self.assertEqual(len(file_path.read_bytes()), entry["bytes"])
            self.assertEqual(sha256(file_path), entry["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )

        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 1)
        self.assertEqual(inventory["successful_http_requests"], 1)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            Path(inventory["temporary_capture_trash_path"]).name,
            "dca-cdc-be1-y4fq47",
        )
        request = inventory["controlled_http_requests"][0]
        self.assertEqual(
            (request["body"]["bytes"], request["body"]["sha256"]), CAPTURE_BODY
        )
        self.assertEqual(
            (request["headers"]["bytes"], request["headers"]["sha256"]),
            CAPTURE_HEADERS,
        )
        self.assertEqual(
            (
                request["curl_writeout"]["bytes"],
                request["curl_writeout"]["sha256"],
            ),
            CAPTURE_WRITEOUT,
        )
        for field in (
            "raw_response_bodies_retained_in_artifact",
            "raw_response_headers_retained_in_artifact",
            "curl_writeouts_retained_in_artifact",
            "response_cookies_retained_in_artifact",
            "publisher_media_retained",
        ):
            self.assertFalse(inventory[field])

    def test_offline_import_is_exact_valid_and_idempotent(self) -> None:
        temporary, connection, results = self._import(repetitions=2)
        try:
            self.assertEqual(results[0].entities_created, 2)
            self.assertEqual(results[0].evidence_created, 1)
            self.assertEqual(results[0].warnings, ())
            self.assertEqual(results[1].entities_created, 0)
            self.assertEqual(results[1].evidence_created, 0)
            self.assertEqual(results[1].warnings, ())
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 1,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                },
            )
            entities = list(
                connection.execute(
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key"
                )
            )
            self.assertEqual(
                [tuple(row) for row in entities],
                [("campus", CAMPUS_KEY), ("project", PROJECT_KEY)],
            )
            project_target = connection.execute(
                "SELECT target.stable_key FROM projects "
                "JOIN entities AS project ON project.id = projects.entity_id "
                "JOIN entities AS target ON target.id = projects.target_entity_id "
                "WHERE project.stable_key = ?",
                (PROJECT_KEY,),
            ).fetchone()
            self.assertEqual(project_target["stable_key"], CAMPUS_KEY)
        finally:
            connection.close()
            temporary.cleanup()

    def test_status_locality_and_null_claim_dimensions_are_exact(self) -> None:
        temporary, connection, _ = self._import()
        try:
            lifecycle = connection.execute(
                "SELECT entities.stable_key, status, as_of_date, method, confidence "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(lifecycle),
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-07-20",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json, entity_snapshots.as_of_date, entity_snapshots.method "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            for row in snapshots:
                self.assertEqual(row["latitude"], None)
                self.assertEqual(row["longitude"], None)
                self.assertEqual(row["geometry_json"], None)
                self.assertEqual(row["as_of_date"], "2026-07-20")
                self.assertEqual(row["method"], "authoritative_locality")
                tags = json.loads(row["tags_json"])
                self.assertEqual(tags["address"], "Beard, Canberra, Australia")
                self.assertEqual(tags["country"], "Australia")
                self.assertFalse(any(key.startswith("role:") for key in tags))
        finally:
            connection.close()
            temporary.cleanup()

    def test_39_mw_and_portfolio_language_cannot_expand_claim_scope(self) -> None:
        document = self._load()
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["capacity_wording_as_reported"], "Total capacity 39 MW"
        )
        self.assertIn("untyped source metadata", metadata["capacity_guardrail"])
        self.assertIn("last-observed", metadata["currentness_guardrail"])
        self.assertIn("physical-build threshold", metadata["physical_threshold_scope"])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {})
            self.assertEqual(entity["coordinates"], None)
            self.assertEqual(entity["geometry"], None)
            self.assertEqual(entity["country"], "Australia")

        serialized = json.dumps(document)
        for prohibited in (
            '"critical_it_mw"',
            '"gross_facility_mw"',
            '"grid_connection_mw"',
            '"generation_mw"',
            '"annual_energy_mwh"',
            '"pue"',
            '"tenant"',
            '"customer"',
            '"workload"',
        ):
            self.assertNotIn(prohibited, serialized)

    def test_project_is_absent_from_frozen_v63_and_source_selection(self) -> None:
        with V63_ENTITIES.open(newline="", encoding="utf-8") as handle:
            stable_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertNotIn(CAMPUS_KEY, stable_keys)
        self.assertNotIn(PROJECT_KEY, stable_keys)

        definition = json.loads(V63_DEFINITION.read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in definition["curated_inputs"]}
        self.assertNotIn(f"sources/{SOURCE_NAME}", paths)
        self.assertFalse(
            any(key.startswith("curated:cdc-beard-campus") for key in stable_keys)
        )


if __name__ == "__main__":
    unittest.main()
