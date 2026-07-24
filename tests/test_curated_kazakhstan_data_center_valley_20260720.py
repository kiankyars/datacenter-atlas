from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T01:21:00Z"
SOURCE_NAME = (
    "curated-official-2026-07-20-kazakhstan-data-center-valley-ekibastuz.json"
)
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 28_090
SOURCE_SHA256 = "5ef79026207a4da1c904c39659e4cf700a09841c2c8c4979482c859d15d17abc"
FIRST_ACCEPTED_SEED_VERSION = 59
FIRST_ACCEPTED_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v59.json"
)
FIRST_ACCEPTED_DEFINITION_SHA256 = (
    "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
)
FIRST_ACCEPTED_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v59" / "manifest.json"
)
FIRST_ACCEPTED_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "kazakhstan-data-center-valley-ekibastuz-2026-07-20-v1"
)
CAPTURE_DIRECTORY = Path("/private/tmp/kazakhstan-dcv-capture.UTORk1")

ARTIFACT_FILE_SPECS = {
    "README.md": (
        2_324,
        "be270a83d156969cba59bc8f976443c4a2089068750053ee810c4bca56360df6",
    ),
    "manifest.json": (
        706,
        "4de4e7d8847f2f20fe884a46adfafb5a1fa65153aaade24d368759b3a3473c2a",
    ),
    "manifest.sha256": (
        80,
        "9fbdcbd04dd2654b9d85fa28ec2913f795530b07a0463598e575f4a14079d57d",
    ),
    "retrieval-inventory.json": (
        6_307,
        "eea8738afb3098e8f860a0fe17709ca3f738d89b34131ea74c2a1416ebb536cd",
    ),
    "source-snapshot.json": (
        1_930,
        "8ed28f4b5f37c8c7acf4ba125029ebd213e341a9fb8f1abaa6f29b90f20642f0",
    ),
}

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    (
        "kazakhstan-prime-minister-data-center-valley-ekibastuz-plan-"
        "2026-01-30-captured-2026-07-20"
    ): {
        "request_id": "jan30",
        "url": (
            "https://primeminister.kz/en/news/olzhas-bektenov-inspected-the-"
            "implementation-of-the-presidents-instructions-on-the-data-center-"
            "valley-project-in-ekibastuz-31031"
        ),
        "published_at": "2026-01-30",
        "retrieved_at": "2026-07-21T01:20:02Z",
        "body": (
            59_678,
            "88099066a774024282eade9ab1f760be2adc5c39563bf68b6ca771af64f67c68",
        ),
        "headers": (
            1_370,
            "94e77254292ef776f7910c54dfabb19bc5c4942c9ff5a7f019452006a8547398",
        ),
        "writeout": (
            24_733,
            "9702db46a3fa49239f62e751fbad1ccf98a7b0f586428fad31a341aeff6ecc64",
        ),
        "download": 23_138,
    },
    (
        "kazakhstan-prime-minister-data-center-valley-ekibastuz-plan-"
        "2026-02-25-captured-2026-07-20"
    ): {
        "request_id": "feb25",
        "url": (
            "https://primeminister.kz/en/news/olzhas-bektenov-holds-meeting-on-"
            "implementation-of-presidential-instructions-within-the-data-center-"
            "valley-project-31118"
        ),
        "published_at": "2026-02-25",
        "retrieved_at": "2026-07-21T01:20:04Z",
        "body": (
            58_006,
            "7b7825d2eedd8f9c50c1d289398228ce1172044aa055ace272980098c55b0e67",
        ),
        "headers": (
            1_370,
            "c23984730b14e7686cde3c4b923e222d9079f3aba57e88196a9dfd37900b4827",
        ),
        "writeout": (
            24_701,
            "73015df1e3d3b3a022550ee9d0d55da991436c99d354ab93a85c6e4dead322a3",
        ),
        "download": 22_527,
    },
    (
        "kazakhstan-prime-minister-data-center-valley-ekibastuz-site-work-"
        "2026-05-25-captured-2026-07-20"
    ): {
        "request_id": "may25",
        "url": (
            "https://primeminister.kz/en/news/olzhas-bektenov-reviews-progress-"
            "in-preparation-for-the-data-center-valley-project-implementation-31418"
        ),
        "published_at": "2026-05-25",
        "retrieved_at": "2026-07-21T01:20:05Z",
        "body": (
            57_591,
            "f53224666c73188f0c51bea8a2ad625d1653e853c40a3f1a79d9f22cfd1c75fd",
        ),
        "headers": (
            1_370,
            "9312e64c9143d7dbc3e4ebb80df70e4decbcb5eefe8bf51714701319ceac9e15",
        ),
        "writeout": (
            24_633,
            "2534310524837cf38dabfa49239de6134500bb39372477d6fa328fb0142c00a1",
        ),
        "download": 22_240,
    },
    (
        "kazakhstan-prime-minister-data-center-valley-construction-began-"
        "2026-07-01-captured-2026-07-20"
    ): {
        "request_id": "jul01",
        "url": (
            "https://primeminister.kz/en/news/kazakhstan-is-forming-the-"
            "technological-foundation-of-the-digital-economy-31594"
        ),
        "published_at": "2026-07-01",
        "retrieved_at": "2026-07-21T01:20:07Z",
        "body": (
            59_933,
            "440e5964a81b7de6424e1ed4df23297a4cbeaa1d6ff6bf67825a888345875293",
        ),
        "headers": (
            1_370,
            "082478dece56ef6179d2beeee5126dfa57c9f86551d6447bac80b373554e4c22",
        ),
        "writeout": (
            24_537,
            "137178911723e986d35b84bcfacb106da1283dc483393c5db3da5e9f964f1179",
        ),
        "download": 23_942,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KazakhstanDataCenterValleyCuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Kazakhstan curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write_document(self, path: Path, document: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _assert_semantics(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(len(document["evidence"]), 4)
        self.assertEqual(
            {item["key"] for item in document["evidence"]},
            set(CAPTURE_SPECS),
        )
        self.assertTrue(
            all(item["kind"] == "government_record" for item in document["evidence"])
        )
        self.assertTrue(
            all(
                urlparse(item["source_url"]).hostname == "primeminister.kz"
                for item in document["evidence"]
            )
        )
        self.assertEqual(
            {item["published_at"] for item in document["evidence"]},
            {"2026-01-30", "2026-02-25", "2026-05-25", "2026-07-01"},
        )
        self.assertEqual(
            document["campus"]["stable_key"],
            "curated:kazakhstan-data-center-valley-ekibastuz",
        )
        self.assertEqual(
            document["project"]["stable_key"],
            (
                "curated:kazakhstan-data-center-valley-ekibastuz:"
                "initial-campus-development"
            ),
        )
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "Kazakhstan")
            self.assertEqual(
                entity["address"], "Ekibastuz, Pavlodar Region, Kazakhstan"
            )
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(
            [
                (
                    item["entity"],
                    item["value"],
                    item["as_of_date"],
                    item["method"],
                )
                for item in document["lifecycle"]
            ],
            [
                (
                    "project",
                    "site_preparation",
                    "2026-05-25",
                    "authoritative_physical_status_update",
                ),
                (
                    "project",
                    "under_construction",
                    "2026-07-01",
                    "authoritative_physical_status_update",
                ),
            ],
        )
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])

    def _database_state(
        self, document: dict[str, Any], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            self._write_document(source, document)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            source,
                            recorded_at=RECORDED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(
                            result.entities_created, 2 if iteration == 0 else 0
                        )
                        self.assertEqual(
                            result.evidence_created, 4 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities ORDER BY 1, 2",
                    "SELECT source_url, content_hash, retrieved_at "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY 1, 3",
                    "SELECT entities.stable_key, as_of_date, method, latitude, "
                    "longitude FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1",
                    "SELECT entity_id, metric, stage, base FROM capacity_estimates "
                    "ORDER BY 1, 2",
                    "SELECT entity_id, operating_model "
                    "FROM operating_model_observations ORDER BY 1, 2",
                    "SELECT entity_id, workload FROM workload_observations "
                    "ORDER BY 1, 2",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _validate_artifact(self, artifact: Path, *, check_modes: bool = True) -> None:
        self.assertEqual(
            {path.name for path in artifact.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_sha256) in ARTIFACT_FILE_SPECS.items():
            path = artifact / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            self.assertEqual(len(data), expected_bytes)
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected_sha256)
            if check_modes:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        manifest_text = (artifact / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(
            (artifact / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(
            {entry["path"] for entry in manifest["files"]},
            {"README.md", "retrieval-inventory.json", "source-snapshot.json"},
        )
        for entry in manifest["files"]:
            data = (artifact / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )

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
        self._assert_semantics(document)

    def test_capture_metadata_is_exact_closed_and_credential_free(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURE_SPECS))
        forbidden_telemetry = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for key, expected in CAPTURE_SPECS.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], expected["retrieved_at"])
                self.assertEqual(item["content_hash"], expected["body"][1])
                self.assertIn(
                    f"{expected['body'][0]}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['headers'][0]}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers"][1]
                )
                self.assertIn(
                    f"{expected['writeout'][0]}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout"][1],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/1.1")
                self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["download"],
                )
                self.assertEqual(metadata["decoded_body_bytes"], expected["body"][0])
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download"],
                )
                self.assertEqual(metadata["curl_size_header_bytes"], 1_370)
                self.assertEqual(metadata["curl_num_headers"], 15)
                self.assertEqual(metadata["response_http_date"], item["retrieved_at"])
                self.assertEqual(metadata["requested_url"], item["source_url"])
                self.assertEqual(metadata["effective_url"], item["source_url"])
                self.assertEqual(metadata["canonical_url"], item["source_url"])
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("credential-free", metadata["retrieval_method"])
                self.assertIn(
                    "were removed after validation",
                    metadata["capture_artifact_guardrail"],
                )
                self.assertTrue(
                    forbidden_telemetry.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )

    def test_physical_status_and_plan_guardrails_are_exact(self) -> None:
        document = self._load()
        evidence = {item["published_at"]: item["metadata"] for item in document["evidence"]}

        january = evidence["2026-01-30"]
        self.assertEqual(january["reported_planned_step_down_substation_capacity_mw"], 300)
        self.assertEqual(
            january["reported_future_step_down_substation_expandable_capacity_mw"],
            1000,
        )
        self.assertIn(
            "step-down-substation infrastructure",
            january["infrastructure_capacity_guardrail"],
        )
        self.assertIn("plans only", january["status_scope"])

        february = evidence["2026-02-25"]
        self.assertEqual(
            february["reported_future_campus_energy_capacity_gw_untyped_upper_bound"],
            1,
        )
        self.assertEqual(february["reported_future_ai_data_center_stage_count"], 4)
        self.assertEqual(
            february["reported_future_ai_data_center_capacity_per_stage_mw_untyped"],
            50,
        )
        self.assertEqual(february["reported_future_design_pue"], 1.25)
        self.assertIn("design", february["pue_guardrail"])
        self.assertIn("No stage", february["stage_capacity_guardrail"])

        may = evidence["2026-05-25"]
        self.assertEqual(may["geodetic_works_status_as_reported"], "completed")
        self.assertEqual(
            may["engineering_geological_surveys_status_as_reported"], "underway"
        )
        self.assertEqual(
            may["future_modular_block_pit_excavation_status_as_reported"],
            "underway",
        )
        self.assertEqual(may["construction_equipment_status_as_reported"], "mobilized")
        self.assertEqual(may["construction_personnel_status_as_reported"], "mobilized")
        self.assertIn("site_preparation", may["physical_status_scope"])

        july = evidence["2026-07-01"]
        self.assertEqual(
            july["construction_wording_as_reported"],
            "This year, construction of a world-class Data Center Valley began.",
        )
        self.assertEqual(
            july["reported_future_campus_target_capacity_gw_untyped_lower_bound"],
            1,
        )
        self.assertIn("under_construction", july["physical_status_scope"])
        self.assertIn("untyped future target", july["capacity_guardrail"])
        self.assertIn("not used", july["june_agreements_guardrail"])

        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])

    def test_import_is_offline_idempotent_and_evidence_order_independent(self) -> None:
        document = self._load()
        once = self._database_state(document)
        self.assertEqual(self._database_state(document, repetitions=2), once)
        reversed_evidence = copy.deepcopy(document)
        reversed_evidence["evidence"].reverse()
        self.assertEqual(self._database_state(reversed_evidence), once)
        entities, evidence, lifecycle, snapshots, capacities, models, workloads = once
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(evidence), 4)
        self.assertEqual(len(lifecycle), 2)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(capacities, ())
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            [(row[1], row[2]) for row in lifecycle],
            [("site_preparation", "2026-05-25"), ("under_construction", "2026-07-01")],
        )

    def test_artifact_is_immutable_hash_bound_and_contains_no_raw_capture(self) -> None:
        self._validate_artifact(ARTIFACT)
        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 4)
        self.assertEqual(inventory["completed_response_requests"], 4)
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertFalse(inventory["raw_response_headers_retained"])
        self.assertFalse(inventory["curl_writeouts_retained"])
        requests = {
            item["evidence_key"]: item
            for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for key, expected in CAPTURE_SPECS.items():
            item = requests[key]
            self.assertEqual(item["request_id"], expected["request_id"])
            self.assertEqual(item["url"], expected["url"])
            self.assertEqual(item["retrieved_at"], expected["retrieved_at"])
            self.assertFalse(item["request_credentials_supplied"])
            for field in ("body", "headers", "curl_writeout"):
                expected_field = "writeout" if field == "curl_writeout" else field
                self.assertEqual(item[field]["bytes"], expected[expected_field][0])
                self.assertEqual(item[field]["sha256"], expected[expected_field][1])
                self.assertFalse(item[field]["retained"])

        self.assertFalse(CAPTURE_DIRECTORY.exists())
        forbidden_suffixes = {".body", ".headers", ".writeout", ".html", ".htm"}
        self.assertEqual(
            [path for path in ARTIFACT.rglob("*") if path.suffix in forbidden_suffixes],
            [],
        )
        serialized = b"\n".join(
            path.read_bytes() for path in ARTIFACT.iterdir() if path.is_file()
        ).lower()
        for raw_marker in (
            b"<!doctype html",
            b"http/1.1 200 ok",
            b"set-cookie:",
            b'"certs":',
        ):
            self.assertNotIn(raw_marker, serialized)

        snapshot_text = (ARTIFACT / "source-snapshot.json").read_text(
            encoding="utf-8"
        )
        snapshot = json.loads(snapshot_text)
        self.assertEqual(
            snapshot_text,
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(snapshot["release_integration"], "none")
        source_record = snapshot["source_records"][0]
        self.assertEqual(source_record["path"], f"sources/{SOURCE_NAME}")
        self.assertEqual(source_record["bytes"], SOURCE_BYTES)
        self.assertEqual(source_record["sha256"], SOURCE_SHA256)
        self.assertEqual(source_record["current_status"], "under_construction")
        self.assertEqual(source_record["current_status_as_of_date"], "2026-07-01")
        self.assertFalse(source_record["seeded"])

    def test_source_and_artifact_tampering_are_detected(self) -> None:
        original = self._load()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid_hash = copy.deepcopy(original)
            invalid_hash["evidence"][0]["content_hash"] = "not-a-sha256"
            invalid_path = root / "invalid-hash.json"
            self._write_document(invalid_path, invalid_hash)
            connection, _ = initialize(root / "invalid.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "content_hash must be a lowercase SHA-256"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        invalid_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            weak_method = copy.deepcopy(original)
            weak_method["lifecycle"][1]["method"] = "authoritative_status_update"
            weak_path = root / "weak-method.json"
            self._write_document(weak_path, weak_method)
            connection, _ = initialize(root / "weak.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "construction status requires"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        weak_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            copied_artifact = root / "artifact"
            shutil.copytree(ARTIFACT, copied_artifact)
            snapshot_path = copied_artifact / "source-snapshot.json"
            snapshot_path.chmod(0o644)
            snapshot_path.write_bytes(snapshot_path.read_bytes() + b" ")
            with self.assertRaises(AssertionError):
                self._validate_artifact(copied_artifact, check_modes=False)

        capacity_leak = copy.deepcopy(original)
        capacity_leak["capacities"].append(
            {
                "entity": "campus",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 1000,
                "base": 1000,
                "high": 1000,
                "method": "source_reported",
                "confidence": 0.99,
                "evidence_key": original["evidence"][3]["key"],
                "as_of_date": "2026-07-01",
                "target_date": None,
                "notes": "Invalid semantic leak from an untyped future target.",
            }
        )
        with self.assertRaises(AssertionError):
            self._assert_semantics(capacity_leak)

        coordinate_leak = copy.deepcopy(original)
        coordinate_leak["campus"]["coordinates"] = [51.0, 75.0]
        with self.assertRaises(AssertionError):
            self._assert_semantics(coordinate_leak)

    def test_keys_are_collision_free_and_seed_lineage_is_exact(self) -> None:
        document = self._load()
        stable_keys = {
            document["campus"]["stable_key"],
            document["project"]["stable_key"],
        }
        evidence_keys = {item["key"] for item in document["evidence"]}
        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("*.json")):
            if path.name == SOURCE_NAME:
                continue
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            existing_stable = {
                entity["stable_key"]
                for entity in (existing.get("campus"), existing.get("project"))
                if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str)
            }
            existing_evidence = {
                item["key"]
                for item in existing.get("evidence", [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            }
            stable_overlap = sorted(stable_keys & existing_stable)
            evidence_overlap = sorted(evidence_keys & existing_evidence)
            if stable_overlap or evidence_overlap:
                collisions[path.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(collisions, {})

        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_DEFINITION.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_MANIFEST.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_MANIFEST_SHA256,
        )
        for path in sorted((ROOT / "sources").glob("open-seed-*.json")):
            version_text = path.stem.rpartition("-v")[2]
            self.assertTrue(version_text.isdecimal(), path.name)
            version = int(version_text)
            definition = json.loads(path.read_text(encoding="utf-8"))
            selected_inputs = {
                Path(item["path"]).name: item["sha256"]
                for item in definition["curated_inputs"]
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            with self.subTest(seed_definition=path.name):
                if version < FIRST_ACCEPTED_SEED_VERSION:
                    self.assertNotIn(SOURCE_NAME, selected_inputs)
                    continue
                self.assertEqual(selected_inputs.get(SOURCE_NAME), SOURCE_SHA256)

    def test_source_imports_offline_in_both_workspace_layouts(self) -> None:
        expected = {
            "capacity": 0,
            "entities": 2,
            "evidence": 4,
            "lifecycle": 2,
            "operating_models": 0,
            "snapshots": 2,
            "workloads": 0,
        }
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated_v11 import CuratedOfficialSourceAdapterV11
from {package}.database import initialize
from {package}.service import validate_database

with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for iteration in range(2):
                result = CuratedOfficialSourceAdapterV11().import_file(
                    connection, Path({str(SOURCE)!r}), recorded_at={RECORDED_AT!r}
                )
                assert result.warnings == ()
                assert result.entities_created == (2 if iteration == 0 else 0)
                assert result.evidence_created == (4 if iteration == 0 else 0)
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        current = connection.execute(
            "SELECT status, as_of_date FROM lifecycle_observations ORDER BY as_of_date DESC LIMIT 1"
        ).fetchone()
        assert tuple(current) == ("under_construction", "2026-07-01")
        print(json.dumps(counts, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
