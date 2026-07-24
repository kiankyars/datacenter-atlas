from __future__ import annotations

from contextlib import ExitStack
import csv
from datetime import date
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
SOURCE_NAME = "curated-official-2026-07-20-digital-realty-vie13-phase-1.json"
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 20_350
SOURCE_SHA256 = "ddf94f3bbf02d4a4d9a4afeafc4c9eb5ce76f817f8d93b1f9033869801d14e4e"
RECORDED_AT = "2026-07-21T05:50:00Z"
ARTIFACT = (
    ROOT / "source_artifacts" / "digital-realty-vie13-phase-1-official-2026-07-20-v1"
)
V63_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
V63_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v63/entities.csv"

POST_KEY = (
    "digital-realty-vie13-linkedin-current-construction-2026-06-18-captured-2026-07-20"
)
BROCHURE_KEY = (
    "digital-realty-vie13-vie16-brochure-updated-2026-06-03-captured-2026-07-20"
)
CAMPUS_KEY = "curated:digital-realty-vienna-vie13-vie16-expansion"
PROJECT_KEY = f"{CAMPUS_KEY}:vie13-phase-1-current-build"

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "digital_realty_vie13_linkedin_post": {
        "evidence_key": POST_KEY,
        "retrieved_at": "2026-07-21T05:43:03Z",
        "body": (
            295_393,
            "f4840f3349c84440e0664b1ccf2a4a9ce224611b466afcffaeea1363b166824b",
        ),
        "headers": (
            5_379,
            "dfb08c50e3690d9256638bace3810eb19bcf818b21ca94689667256061684b90",
        ),
        "writeout": (
            17_705,
            "4f1717e2e326dc3620b57b432b224a1b6c0124ef17869ec88a053caea617db64",
        ),
        "wire": 25_713,
        "content_type": "text/html; charset=utf-8",
    },
    "digital_realty_vie13_short_link": {
        "evidence_key": None,
        "retrieved_at": "2026-07-21T05:43:04Z",
        "body": (
            1_202,
            "b32c8d76bb573e441ea9bea8e2c1811154d2da3e58ff4e5000b1e337db2bf14f",
        ),
        "headers": (
            138,
            "34d6799b0114bec9656097d5f908891ab58bf98749ba905cafd359b51fd3c4ea",
        ),
        "writeout": (
            16_063,
            "c07ed3760b912d98d39fdb0ebbd4965fe27265284f3ddb2625977f2fd9ce044f",
        ),
        "wire": 1_202,
        "content_type": "text/html; charset=UTF-8",
    },
    "digital_realty_vie13_brochure": {
        "evidence_key": BROCHURE_KEY,
        "retrieved_at": "2026-07-21T05:43:04Z",
        "body": (
            7_270_904,
            "66e9c7094c707fb10771765dfe5349251a042847e881aec7a93bc30b7b5d0d17",
        ),
        "headers": (
            670,
            "5a40752f347cbf0a2526f6a106a8569caff8d85c520541830e983f5e40a1bf55",
        ),
        "writeout": (
            12_953,
            "553b76038c9c35333e627a118237599933ba558392a707eff998471b54464ed3",
        ),
        "wire": 7_270_904,
        "content_type": "application/pdf; charset=utf-8",
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        2_034,
        "f7db5dd10fe9945fcb74f1a1751d3caadb24d48a43e0d9c4623cbe6517763827",
    ),
    "manifest.json": (
        1_066,
        "3738746a6633ff9546909b4ac3c2eaaadb33b398c721bb2f27fb3605a836baa6",
    ),
    "manifest.sha256": (
        80,
        "f4d7c5dc0035806cdfceb7fd552c8eddefbe1920934c5b7963739e2396da504a",
    ),
    "retrieval-inventory.json": (
        6_013,
        "0a396df5882542f5020716c2605c586ce98fab62f63238cc2a961037dd7bd75f",
    ),
    "source-snapshot.json": (
        2_776,
        "b34b6661cfe77d076103cc28bc67d53c2cf08a02a5ced82610b69404d2e12a4f",
    ),
}


def sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class DigitalRealtyVie13Phase1CuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError(
            "Digital Realty VIE13 curated import attempted network access"
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
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [POST_KEY, BROCHURE_KEY],
        )
        self.assertNotIn("captured-2026-07-21", text)
        self.assertNotIn('"as_of_date": "2026-07-21"', text)
        local_ceiling = date.fromisoformat("2026-07-20")
        for entity in (document["campus"], document["project"]):
            self.assertLessEqual(
                date.fromisoformat(entity["as_of_date"]), local_ceiling
            )
        for group in (
            "lifecycle",
            "operating_models",
            "workloads",
            "capacities",
        ):
            for row in document[group]:
                self.assertLessEqual(
                    date.fromisoformat(row["as_of_date"]), local_ceiling
                )

    def test_capture_facts_and_compact_frozen_artifact_are_exact(self) -> None:
        document = self._load()
        evidence_by_key = {row["key"]: row for row in document["evidence"]}
        for request_id in (
            "digital_realty_vie13_linkedin_post",
            "digital_realty_vie13_brochure",
        ):
            spec = CAPTURE_SPECS[request_id]
            evidence = evidence_by_key[spec["evidence_key"]]
            metadata = evidence["metadata"]
            self.assertEqual(evidence["content_hash"], spec["body"][1])
            self.assertEqual(evidence["retrieved_at"], spec["retrieved_at"])
            self.assertEqual(evidence["license"], "all-rights-reserved")
            self.assertIn(str(spec["body"][0]), metadata["content_hash_scope"])
            self.assertEqual(metadata["capture_request_id"], request_id)
            self.assertEqual(
                (
                    metadata["capture_headers_bytes"],
                    metadata["capture_headers_sha256"],
                ),
                spec["headers"],
            )
            self.assertEqual(
                (
                    metadata["capture_curl_writeout_bytes"],
                    metadata["capture_curl_writeout_sha256"],
                ),
                spec["writeout"],
            )
            self.assertEqual(metadata["wire_download_bytes"], spec["wire"])
            self.assertEqual(metadata["content_type"], spec["content_type"])
            self.assertEqual(metadata["http_status"], 200)
            self.assertEqual(metadata["http_version"], "HTTP/2")
            self.assertEqual(metadata["redirect_count"], 0)
            self.assertEqual(metadata["requested_url"], metadata["effective_url"])

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
        self.assertEqual(set(manifest["closed_file_set"]), set(ARTIFACT_FILE_SPECS))
        self.assertFalse(manifest["raw_capture_redistributed"])
        self.assertFalse(manifest["publisher_media_redistributed"])
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
        self.assertEqual(inventory["direct_request_attempts"], 3)
        self.assertEqual(inventory["successful_http_requests"], 3)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            Path(inventory["temporary_capture_trash_path"]).name,
            "dca-digital-realty-vie13-20260720-SEl18o",
        )
        requests = {
            row["request_id"]: row for row in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for request_id, spec in CAPTURE_SPECS.items():
            request = requests[request_id]
            self.assertEqual(request["evidence_key"], spec["evidence_key"])
            self.assertEqual(request["retrieved_at"], spec["retrieved_at"])
            self.assertEqual(
                (request["body"]["bytes"], request["body"]["sha256"]),
                spec["body"],
            )
            self.assertEqual(
                (request["headers"]["bytes"], request["headers"]["sha256"]),
                spec["headers"],
            )
            self.assertEqual(
                (
                    request["curl_writeout"]["bytes"],
                    request["curl_writeout"]["sha256"],
                ),
                spec["writeout"],
            )
            self.assertEqual(request["wire_download_bytes"], spec["wire"])
            self.assertEqual(request["content_type"], spec["content_type"])
        self.assertEqual(
            requests["digital_realty_vie13_short_link"]["meta_refresh_destination"],
            evidence_by_key[BROCHURE_KEY]["source_url"],
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
            self.assertEqual(results[0].evidence_created, 2)
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
                    "evidence": 2,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "operating_model_observations": 1,
                    "workload_observations": 0,
                    "capacity_estimates": 1,
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

    def test_status_locality_model_and_capacity_scopes_are_exact(self) -> None:
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
                    "2026-06-18",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json, entity_snapshots.as_of_date FROM entity_snapshots "
                    "JOIN entities ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY 1"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            self.assertEqual(
                [row["as_of_date"] for row in snapshots],
                ["2026-06-03", "2026-06-18"],
            )
            for row in snapshots:
                self.assertEqual(row["latitude"], None)
                self.assertEqual(row["longitude"], None)
                self.assertEqual(row["geometry_json"], None)
                tags = json.loads(row["tags_json"])
                self.assertEqual(tags["address"], "Vienna, Austria")
                self.assertEqual(tags["country"], "Austria")
                self.assertFalse(any(key.startswith("role:") for key in tags))

            model = connection.execute(
                "SELECT entities.stable_key, operating_model, as_of_date, method "
                "FROM operating_model_observations JOIN entities "
                "ON entities.id = operating_model_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(model),
                (PROJECT_KEY, "colocation", "2026-06-03", "company_disclosure"),
            )
            capacity = connection.execute(
                "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                "as_of_date, target_date, method FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(capacity),
                (
                    CAMPUS_KEY,
                    "critical_it_mw",
                    "planned",
                    "MW",
                    40.0,
                    40.0,
                    40.0,
                    "2026-06-03",
                    None,
                    "reported",
                ),
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_untyped_phase_and_conflicting_future_power_cannot_expand_claims(
        self,
    ) -> None:
        document = self._load()
        post = document["evidence"][0]["metadata"]
        brochure = document["evidence"][1]["metadata"]
        self.assertIn("untyped metadata", post["phase_1_capacity_guardrail"])
        self.assertIn("last-observed", post["currentness_guardrail"])
        self.assertIn("physical-build threshold", post["physical_threshold_scope"])
        self.assertIn("conflicting, nonadditive", brochure["expandability_guardrail"])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        self.assertEqual(document["capacities"][0]["entity"], "campus")
        self.assertEqual(document["capacities"][0]["base"], 40)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {})
            self.assertEqual(entity["coordinates"], None)
            self.assertEqual(entity["geometry"], None)
        serialized = json.dumps(document)
        for prohibited in (
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
        self.assertNotIn('"base": 5', serialized)
        self.assertNotIn('"base": 64', serialized)
        self.assertNotIn('"base": 65', serialized)

    def test_project_is_absent_from_frozen_v63_and_source_selection(self) -> None:
        with V63_ENTITIES.open(newline="", encoding="utf-8") as handle:
            stable_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertNotIn(CAMPUS_KEY, stable_keys)
        self.assertNotIn(PROJECT_KEY, stable_keys)
        self.assertFalse(
            any(
                key.startswith("curated:digital-realty-vienna-vie13")
                for key in stable_keys
            )
        )

        definition = json.loads(V63_DEFINITION.read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in definition["curated_inputs"]}
        self.assertNotIn(f"sources/{SOURCE_NAME}", paths)


if __name__ == "__main__":
    unittest.main()
