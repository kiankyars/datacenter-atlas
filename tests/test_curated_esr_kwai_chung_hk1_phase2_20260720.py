from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-esr-kwai-chung-hk1-phase-2.json"
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 20_866
SOURCE_SHA256 = "ecee59847d664d6ca65856cdce1f83c6755218db6cd74449dcce1540111c69f2"
RECORDED_AT = "2026-07-21T05:21:00Z"
ARTIFACT = (
    ROOT / "source_artifacts" / "esr-kwai-chung-hk1-phase-2-official-2026-07-20-v2"
)
REJECTED_ARTIFACT = (
    ROOT / "source_artifacts" / "esr-kwai-chung-hk1-phase-2-official-2026-07-20-v1"
)

REPORT_KEY = "esr-data-centre-sustainability-report-2025-2026-hk1-captured-2026-07-20"
PORTFOLIO_KEY = "esr-data-centres-portfolio-kwai-chung-hk1-captured-2026-07-20"
POST_KEY = "esr-linkedin-hkdc1-phase-2-commenced-2026-03-27-captured-2026-07-20"
CAMPUS_KEY = "curated:esr-kwai-chung-hk1-data-centre"
PROJECT_KEY = f"{CAMPUS_KEY}:phase-2-conversion"

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "hk1_sustainability_report": {
        "evidence_key": REPORT_KEY,
        "host": "esrassets.s3.ap-southeast-1.amazonaws.com",
        "retrieved_at": "2026-07-21T05:19:18Z",
        "body": (
            9_727_778,
            "c0c2a769559c77427054a2e1181c2b800cd527e975119c623106ec194bfb12f8",
        ),
        "headers": (
            457,
            "f013a50109e6317bb26aa013fd8bd98e8180e2a8aedf5b9dd4f5d8fe08c939a3",
        ),
        "writeout": (
            16_165,
            "26dd1e0e386b5946475237dbbd074f6920244be3beb0bd69db5ef3381330345d",
        ),
        "wire": 9_727_778,
        "http_version": "HTTP/1.1",
        "content_type": "application/pdf",
    },
    "hk1_portfolio_page": {
        "evidence_key": PORTFOLIO_KEY,
        "host": "www.esr.com",
        "retrieved_at": "2026-07-21T05:19:21Z",
        "body": (
            417_607,
            "ffb42ab037b99f2c4b2e75ebadca3c98a169b265d6cf1827f16e3220da517b1b",
        ),
        "headers": (
            761,
            "cc9bfbd308bcb0ea9be1965eee751ec43e5c95223913f3d3f0a8b46b0ff4cf8e",
        ),
        "writeout": (
            16_299,
            "3b7b111640d2ba9760001d70920de959363255a2c0b0815922566b8da246c617",
        ),
        "wire": 63_713,
        "http_version": "HTTP/2",
        "content_type": "text/html",
    },
    "hk1_phase_2_linkedin_post": {
        "evidence_key": POST_KEY,
        "host": "www.linkedin.com",
        "retrieved_at": "2026-07-21T05:19:22Z",
        "body": (
            321_275,
            "74b8784d211d41d933e4bc1e48836db9549f004aa8590c51c91121174abbc2d1",
        ),
        "headers": (
            5_348,
            "3164e3daf2a9e1c5d11985c81ad7c4bce05c0cec1ee0e0027ed7570bbd9dae2d",
        ),
        "writeout": (
            17_713,
            "ea90692d93d4b075efc9e66566a3f016dbb021754367aa86b5cfe0daed42d786",
        ),
        "wire": 36_263,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        3_665,
        "91ba62db7565fe11eb550efac2dc0a086d4e23946dd12465bb376d26710b3d5e",
    ),
    "manifest.json": (
        702,
        "580c1dd2ff839ebbefee33737f7386401914b04062d5556a1d39d889dfae0ff0",
    ),
    "manifest.sha256": (
        80,
        "b81e4fb525b0ed104257c73429206e830f76e1ee58a269e0331111e5d5fc9748",
    ),
    "retrieval-inventory.json": (
        5_656,
        "695c3befcb2759bc6f67e20879bc6774e252a8f0defaa1887080d059f2a08dac",
    ),
    "source-snapshot.json": (
        4_836,
        "39f7a17424c43eaaa66f61508ff2636a3bb00550df06d2c0eef2b5f6f8974bb6",
    ),
}


def sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class EsrKwaiChungHk1Phase2CuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("ESR HK1 Phase 2 import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _write_document(self, file_path: Path, document: dict[str, Any]) -> None:
        file_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _database_state(
        self, document: dict[str, Any], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            source_copy = temp_root / "source.json"
            self._write_document(source_copy, document)
            connection, _ = initialize(temp_root / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection, source_copy, recorded_at=RECORDED_AT
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(
                            result.entities_created, 2 if iteration == 0 else 0
                        )
                        self.assertEqual(
                            result.evidence_created, 3 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY 1, 2",
                    "SELECT source_url, content_hash, retrieved_at "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY 1, 3",
                    "SELECT entities.stable_key, as_of_date, latitude, longitude, "
                    "geometry_json, tags_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "as_of_date, target_date, notes FROM capacity_estimates "
                    "JOIN entities ON entities.id = capacity_estimates.entity_id "
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
            {file_path.name for file_path in artifact.iterdir() if file_path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            file_path = artifact / name
            self.assertTrue(file_path.is_file())
            self.assertFalse(file_path.is_symlink())
            self.assertEqual(len(file_path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(file_path), expected_hash)
            if check_modes:
                self.assertEqual(stat.S_IMODE(file_path.stat().st_mode), 0o444)

        manifest_text = (artifact / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
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
            file_path = artifact / entry["path"]
            self.assertEqual(len(file_path.read_bytes()), entry["bytes"])
            self.assertEqual(sha256(file_path), entry["sha256"])
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
            text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertTrue(
            all(
                evidence["key"].endswith("captured-2026-07-20")
                for evidence in document["evidence"]
            )
        )
        self.assertTrue(
            all(
                evidence["metadata"]["capture_artifact_id"]
                == "esr-kwai-chung-hk1-phase-2-official-2026-07-20-v2"
                for evidence in document["evidence"]
            )
        )
        self.assertTrue(
            all(
                snapshot["as_of_date"] <= "2026-07-20"
                for snapshot in (document["campus"], document["project"])
            )
        )
        self.assertTrue(
            all(
                estimate["as_of_date"] <= "2026-07-20"
                for estimate in document["capacities"]
            )
        )

    def test_capture_inventory_is_exact_closed_and_credential_free(self) -> None:
        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 3)
        self.assertEqual(inventory["completed_response_requests"], 3)
        self.assertEqual(inventory["successful_http_requests"], 3)
        self.assertEqual(inventory["failed_http_requests"], 0)
        self.assertEqual(inventory["evidence_supporting_requests"], 3)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            Path(inventory["temporary_capture_trash_path"]).name,
            "esr-hk1-phase2-MfsGY5",
        )
        for field in (
            "raw_response_bodies_retained_in_artifact",
            "raw_response_headers_retained_in_artifact",
            "curl_writeouts_retained_in_artifact",
            "pdf_text_extraction_retained_in_artifact",
            "publisher_media_retained",
        ):
            self.assertFalse(inventory[field])

        requests = {
            item["request_id"]: item for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        for request_id, expected in CAPTURE_SPECS.items():
            with self.subTest(request=request_id):
                item = requests[request_id]
                source = evidence[expected["evidence_key"]]
                self.assertEqual(
                    urlparse(item["requested_url"]).hostname, expected["host"]
                )
                self.assertEqual(item["requested_url"], item["effective_url"])
                self.assertEqual(item["retrieved_at"], expected["retrieved_at"])
                self.assertEqual(item["curl_exit_code"], 0)
                self.assertEqual(item["http_status"], 200)
                self.assertEqual(item["http_version"], expected["http_version"])
                self.assertEqual(item["content_type"], expected["content_type"])
                self.assertEqual(item["wire_download_bytes"], expected["wire"])
                self.assertEqual(
                    (item["body"]["bytes"], item["body"]["sha256"]),
                    expected["body"],
                )
                self.assertEqual(
                    (item["headers"]["bytes"], item["headers"]["sha256"]),
                    expected["headers"],
                )
                self.assertEqual(
                    (
                        item["curl_writeout"]["bytes"],
                        item["curl_writeout"]["sha256"],
                    ),
                    expected["writeout"],
                )
                self.assertFalse(item["body"]["retained_in_artifact"])
                self.assertFalse(item["headers"]["retained_in_artifact"])
                self.assertFalse(item["curl_writeout"]["retained_in_artifact"])
                self.assertEqual(source["source_url"], item["requested_url"])
                self.assertEqual(source["retrieved_at"], expected["retrieved_at"])
                self.assertEqual(source["content_hash"], expected["body"][1])
                metadata = source["metadata"]
                self.assertEqual(metadata["capture_request_id"], request_id)
                self.assertEqual(
                    metadata["capture_headers_bytes"], expected["headers"][0]
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers"][1]
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_bytes"], expected["writeout"][0]
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"], expected["writeout"][1]
                )
                self.assertIn("moved intact", metadata["capture_guardrail"])
                self.assertIn("remain recoverable", metadata["capture_guardrail"])

    def test_phase_status_capacity_and_exclusions_are_exact(self) -> None:
        document = self._load()
        self.assertEqual(
            [item["key"] for item in document["evidence"]],
            [REPORT_KEY, PORTFOLIO_KEY, POST_KEY],
        )
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "Hong Kong")
            self.assertEqual(
                entity["address"],
                "11-19 Wing Yip Street, Kwai Chung, New Territories, Hong Kong",
            )
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": POST_KEY,
                    "as_of_date": "2026-03-27",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 2)
        capacities = {
            (item["entity"], item["metric"]): item for item in document["capacities"]
        }
        self.assertEqual(
            set(capacities),
            {("campus", "gross_facility_mw"), ("campus", "critical_it_mw")},
        )
        self.assertEqual(capacities[("campus", "gross_facility_mw")]["base"], 50)
        self.assertEqual(capacities[("campus", "critical_it_mw")]["base"], 22)
        for capacity in capacities.values():
            self.assertEqual(capacity["stage"], "planned")
            self.assertIsNone(capacity["target_date"])
            self.assertIn("full HK1", capacity["notes"])
            self.assertIn("different, non-additive campus metric", capacity["notes"])

        evidence = {item["key"]: item for item in document["evidence"]}
        report = evidence[REPORT_KEY]["metadata"]
        portfolio = evidence[PORTFOLIO_KEY]["metadata"]
        post = evidence[POST_KEY]["metadata"]
        self.assertEqual(
            report["facility_load_wording_as_reported"],
            "50 MW facility load, 100% pre-leased",
        )
        self.assertEqual(
            portfolio["it_load_wording_as_reported"],
            "significant IT load capacity of 22MW",
        )
        self.assertEqual(
            post["page_date_published_metadata"], "2026-03-27T02:00:01.812Z"
        )
        self.assertIn("commenced Phase 2", post["construction_wording_as_reported"])
        self.assertIn("not represented as the exact day", post["status_date_guardrail"])
        self.assertIn("no explicit IT-load", post["phase_2_capacity_guardrail"])
        self.assertIn("AI-enabled", post["classification_guardrail"])
        self.assertIn("comments", post["official_post_extraction_scope"])

    def test_offline_import_is_exact_idempotent_and_order_independent(self) -> None:
        document = self._load()
        once = self._database_state(document)
        self.assertEqual(self._database_state(document, repetitions=2), once)
        reversed_evidence = copy.deepcopy(document)
        reversed_evidence["evidence"].reverse()
        self.assertEqual(self._database_state(reversed_evidence), once)
        entities, evidence, lifecycle, snapshots, capacities, models, workloads = once
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(evidence), 3)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-03-27",
                    "authoritative_physical_status_update",
                ),
            ),
        )
        self.assertEqual(len(snapshots), 2)
        for snapshot in snapshots:
            self.assertEqual(snapshot[1], "2026-07-20")
            self.assertIsNone(snapshot[2])
            self.assertIsNone(snapshot[3])
            self.assertIsNone(snapshot[4])
            tags = json.loads(snapshot[5])
            self.assertFalse(any(key.startswith("role:") for key in tags))
        self.assertEqual(len(capacities), 2)
        normalized = {(row[1], row[5], row[7]) for row in capacities}
        self.assertEqual(
            normalized,
            {
                ("critical_it_mw", 22.0, "2026-07-20"),
                ("gross_facility_mw", 50.0, "2026-06-30"),
            },
        )
        self.assertTrue(all(row[0] == CAMPUS_KEY for row in capacities))
        self.assertTrue(all(row[2] == "planned" for row in capacities))
        self.assertTrue(all(row[8] is None for row in capacities))
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())

    def test_per_evidence_time_gate_rolls_back_before_latest_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with (
                    self._offline(),
                    self.assertRaisesRegex(
                        ValueError, "must not be later than the import recorded_at"
                    ),
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T05:19:21Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_artifact_is_immutable_hash_bound_and_contains_no_raw_capture(self) -> None:
        self._validate_artifact(ARTIFACT)
        forbidden_suffixes = {
            ".body",
            ".headers",
            ".pdf",
            ".html",
            ".htm",
            ".txt",
        }
        self.assertEqual(
            [
                file_path
                for file_path in ARTIFACT.rglob("*")
                if file_path.suffix in forbidden_suffixes
            ],
            [],
        )
        serialized = b"\n".join(
            file_path.read_bytes()
            for file_path in ARTIFACT.iterdir()
            if file_path.is_file()
        ).lower()
        for raw_marker in (
            b"%pdf-",
            b"<!doctype html",
            b"set-cookie:",
            b'"certs":',
        ):
            self.assertNotIn(raw_marker, serialized)

        snapshot_text = (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        snapshot = json.loads(snapshot_text)
        self.assertEqual(
            snapshot_text, json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        self.assertEqual(
            snapshot["supersedes_artifact_id"],
            "esr-kwai-chung-hk1-phase-2-official-2026-07-20-v1",
        )
        self.assertEqual(
            snapshot["superseded_manifest_sha256"],
            "55e6966f730dcc721c652721bbab9794d231f94437d6d652f843f04203023c0f",
        )
        self.assertEqual(
            snapshot["superseded_tree_sha256"],
            "604d61223f6126e3ceceb612dd815dff5985d2d3bbe7bc2196dc9899391a5318",
        )
        self.assertTrue(REJECTED_ARTIFACT.is_dir())
        source_record = snapshot["source_records"][0]
        self.assertEqual(source_record["path"], f"sources/{SOURCE_NAME}")
        self.assertEqual(source_record["bytes"], SOURCE_BYTES)
        self.assertEqual(source_record["sha256"], SOURCE_SHA256)
        self.assertEqual(source_record["last_observed_status"], "under_construction")
        self.assertEqual(source_record["last_observed_status_date"], "2026-03-27")
        self.assertFalse(source_record["seeded"])
        self.assertTrue(
            all(value is False for value in snapshot["semantic_boundary"].values())
        )
        self.assertFalse(snapshot["status_boundary"]["exact_start_day_claimed"])
        self.assertFalse(snapshot["capacity_boundary"]["phase_2_capacity_normalized"])
        self.assertEqual(
            snapshot["capacity_boundary"]["phase_2_untyped_estimate_mw"], 16
        )

    def test_tampering_and_future_capture_are_rejected(self) -> None:
        original = self._load()
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            invalid_hash = copy.deepcopy(original)
            invalid_hash["evidence"][0]["content_hash"] = "not-a-sha256"
            invalid_source = temp_root / "invalid-hash.json"
            self._write_document(invalid_source, invalid_hash)
            connection, _ = initialize(temp_root / "invalid.sqlite")
            try:
                with (
                    self._offline(),
                    self.assertRaisesRegex(
                        ValueError, "content_hash must be a lowercase SHA-256"
                    ),
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, invalid_source, recorded_at=RECORDED_AT
                    )
            finally:
                connection.close()

            future_capture = copy.deepcopy(original)
            future_capture["evidence"][0]["retrieved_at"] = "2026-07-22T00:00:00Z"
            future_source = temp_root / "future-capture.json"
            self._write_document(future_source, future_capture)
            connection, _ = initialize(temp_root / "future.sqlite")
            try:
                with (
                    self._offline(),
                    self.assertRaisesRegex(
                        ValueError, "must not be later than the import recorded_at"
                    ),
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, future_source, recorded_at=RECORDED_AT
                    )
            finally:
                connection.close()

            copied_artifact = temp_root / "artifact"
            shutil.copytree(ARTIFACT, copied_artifact)
            inventory_path = copied_artifact / "retrieval-inventory.json"
            inventory_path.chmod(0o644)
            inventory_path.write_bytes(inventory_path.read_bytes() + b" ")
            with self.assertRaises(AssertionError):
                self._validate_artifact(copied_artifact, check_modes=False)

    def test_every_capture_precedes_recorded_at(self) -> None:
        recorded_at = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        for evidence in self._load()["evidence"]:
            retrieved_at = datetime.fromisoformat(
                evidence["retrieved_at"].replace("Z", "+00:00")
            )
            self.assertLessEqual(retrieved_at, recorded_at)


if __name__ == "__main__":
    unittest.main()
