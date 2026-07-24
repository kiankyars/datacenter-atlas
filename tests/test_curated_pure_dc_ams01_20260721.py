from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime
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
RECORDED_AT = "2026-07-21T02:40:00Z"
SOURCE_NAME = (
    "curated-official-2026-07-21-pure-dc-ams01-amsterdam-westpoort-"
    "current-build.json"
)
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 11_296
SOURCE_SHA256 = "38faffdec1c464f4e5870355b247bbf3af228888ad3429f647b01db216ac33f6"
FIRST_PENDING_REFERENCE_VERSION = 59
FIRST_PENDING_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v59.json"
)
FIRST_PENDING_DEFINITION_SHA256 = (
    "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
)
FIRST_PENDING_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v59" / "manifest.json"
)
FIRST_PENDING_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "pure-dc-ams01-amsterdam-westpoort-2026-07-21-v1"
)

ARTIFACT_FILE_SPECS = {
    "README.md": (
        2_616,
        "942ca4d38df22d832eb8236f573048c556e6db99e5978c1e745ce823d38780c9",
    ),
    "manifest.json": (
        859,
        "9dff5e3acaa4709905d3d28af5ece6a792afc6cb49d0d461019e05b410eaa430",
    ),
    "manifest.sha256": (
        80,
        "cd0fe47b6043f251564771f32a4f4a20fbbd5a2d25660f94194011626b6224fc",
    ),
    "identity-resolution.json": (
        5_518,
        "002a84d73e5a6168213eecea58f5fa14e3a83e9932596c8b1bae6b91c4a4d8fb",
    ),
    "retrieval-inventory.json": (
        3_701,
        "c0150eb115662cdeab5a04d02cd2a00d51e6750559131911afff330e4d5d3496",
    ),
    "source-snapshot.json": (
        2_841,
        "5a90deb584e690683948e7615e6417624017723aa1447e052bc203181abc3372",
    ),
}

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "ams01_campus_page": {
        "evidence_key": "pure-dc-ams01-amsterdam-campus-page-captured-2026-07-21",
        "url": "https://puredc.com/amsterdam",
        "published_at": None,
        "body": (
            89_639,
            "40c58a7d526be42e169440defc831270b1d548b3b5910a8b99719cdba9b7dcd4",
        ),
        "headers": (
            850,
            "6cfd4528ea08fc038ac4f658477abcc9795b580134e9d90443d3bd5a7dc03a44",
        ),
        "writeout": (
            9_407,
            "1970604894f9414725b35420139dde25fa1edd619ddeb4086fa19142f560beab",
        ),
        "wire": 20_885,
    },
    "ams01_financing_article": {
        "evidence_key": (
            "pure-dc-amsterdam-financing-current-build-2026-05-27-"
            "captured-2026-07-21"
        ),
        "url": (
            "https://puredc.com/2026/05/27/pure-dc-secures-2-7-billion-to-"
            "accelerate-ai-infrastructure-growth-across-europe-and-the-middle-east"
        ),
        "published_at": "2026-05-27",
        "body": (
            88_169,
            "3b66e738b66ecff72c4886f30427463f4a6f4105bb7e448a609847b514f7434b",
        ),
        "headers": (
            850,
            "f37512782e3f808a3903bc09bf7a95c1019f4f0a53600f9466962c2a088c506a",
        ),
        "writeout": (
            9_818,
            "6f7f0b0358db1ba7c0b536807ed80bfe6e01ff2c3e20eae8eb25a3247b792080",
        ),
        "wire": 21_986,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PureDcAms01CuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Pure DC AMS01 curated import attempted network access")
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
        self.assertEqual(len(document["evidence"]), 2)
        self.assertEqual(
            {item["key"] for item in document["evidence"]},
            {spec["evidence_key"] for spec in CAPTURE_SPECS.values()},
        )
        self.assertTrue(
            all(item["kind"] == "company_disclosure" for item in document["evidence"])
        )
        self.assertTrue(
            all(
                urlparse(item["source_url"]).hostname == "puredc.com"
                for item in document["evidence"]
            )
        )
        self.assertEqual(
            document["campus"]["stable_key"],
            "curated:pure-dc-ams01-amsterdam-westpoort-campus",
        )
        self.assertEqual(
            document["project"]["stable_key"],
            (
                "curated:pure-dc-ams01-amsterdam-westpoort-campus:"
                "data-hall-development"
            ),
        )
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "Netherlands")
            self.assertEqual(entity["address"], "Westpoort, Amsterdam, Netherlands")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CAPTURE_SPECS["ams01_financing_article"][
                        "evidence_key"
                    ],
                    "as_of_date": "2026-05-27",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            document["project"]["evidence_key"],
            CAPTURE_SPECS["ams01_campus_page"]["evidence_key"],
        )
        self.assertEqual(document["project"]["as_of_date"], "2026-07-21")

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
                            result.evidence_created, 2 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities ORDER BY 1, 2",
                    "SELECT source_url, content_hash, retrieved_at "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id ORDER BY 1, 3",
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
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            path = artifact / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)
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
            {
                "README.md",
                "identity-resolution.json",
                "retrieval-inventory.json",
                "source-snapshot.json",
            },
        )
        for entry in manifest["files"]:
            path = artifact / entry["path"]
            self.assertEqual(len(path.read_bytes()), entry["bytes"])
            self.assertEqual(sha256(path), entry["sha256"])
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

    def test_capture_inventory_is_exact_closed_and_credential_free(self) -> None:
        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 2)
        self.assertEqual(inventory["completed_response_requests"], 2)
        self.assertEqual(inventory["successful_http_requests"], 2)
        self.assertEqual(inventory["failed_http_requests"], 0)
        self.assertEqual(inventory["evidence_supporting_requests"], 2)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            Path(inventory["temporary_capture_trash_path"]).name,
            "puredc-ams01-1WrvPW",
        )
        self.assertFalse(inventory["raw_response_bodies_retained_in_artifact"])
        self.assertFalse(inventory["raw_response_headers_retained_in_artifact"])
        self.assertFalse(inventory["curl_writeouts_retained_in_artifact"])

        requests = {
            item["request_id"]: item
            for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        for request_id, expected in CAPTURE_SPECS.items():
            with self.subTest(request=request_id):
                item = requests[request_id]
                source = evidence[expected["evidence_key"]]
                self.assertEqual(item["requested_url"], expected["url"])
                self.assertEqual(item["effective_url"], expected["url"])
                self.assertEqual(item["retrieved_at"], "2026-07-21T02:33:53Z")
                self.assertEqual(item["curl_exit_code"], 0)
                self.assertEqual(item["http_status"], 200)
                self.assertEqual(item["http_version"], "HTTP/2")
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
                self.assertEqual(source["source_url"], expected["url"])
                self.assertEqual(source["published_at"], expected["published_at"])
                self.assertEqual(source["content_hash"], expected["body"][1])
                metadata = source["metadata"]
                self.assertEqual(metadata["capture_request_id"], request_id)
                self.assertEqual(metadata["capture_headers_bytes"], expected["headers"][0])
                self.assertEqual(metadata["capture_headers_sha256"], expected["headers"][1])
                self.assertEqual(
                    metadata["capture_curl_writeout_bytes"], expected["writeout"][0]
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"], expected["writeout"][1]
                )
                self.assertIn("moved", metadata["capture_guardrail"])
                self.assertIn("remain recoverable", metadata["capture_guardrail"])

    def test_status_freshness_capacity_and_identity_guardrails_are_exact(self) -> None:
        document = self._load()
        self._assert_semantics(document)
        evidence = {item["key"]: item for item in document["evidence"]}
        campus = evidence[CAPTURE_SPECS["ams01_campus_page"]["evidence_key"]]
        financing = evidence[
            CAPTURE_SPECS["ams01_financing_article"]["evidence_key"]
        ]
        campus_metadata = campus["metadata"]
        financing_metadata = financing["metadata"]

        self.assertEqual(campus_metadata["building_count_as_reported"], 3)
        self.assertIn("78 MW", campus_metadata["capacity_guardrail"])
        self.assertIn("26 MW", campus_metadata["capacity_guardrail"])
        self.assertIn("future design target", campus_metadata["pue_guardrail"])
        self.assertIn("private substation", campus_metadata["substation_guardrail"])
        self.assertIn("anonymous towers", campus_metadata["identity_scope"])
        self.assertIn("no publication date", campus_metadata["status_scope"])
        self.assertEqual(
            financing_metadata["construction_wording_as_reported"],
            "The Amsterdam facility is fully leased with construction currently underway.",
        )
        self.assertIn(
            "last-observed status dated 2026-05-27",
            financing_metadata["currentness_guardrail"],
        )
        recorded_at = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        for item in document["evidence"]:
            retrieved_at = datetime.fromisoformat(
                item["retrieved_at"].replace("Z", "+00:00")
            )
            self.assertLessEqual(retrieved_at, recorded_at)

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        boundary = snapshot["semantic_boundary"]
        self.assertTrue(all(value is False for value in boundary.values()))
        self.assertEqual(snapshot["totals"]["capacity_estimates"], 0)

        resolution = json.loads(
            (ARTIFACT / "identity-resolution.json").read_text(encoding="utf-8")
        )
        self.assertEqual(resolution["resolution"], "distinct_sites_false_friend")
        self.assertEqual(
            resolution["existing_stable_key"],
            "curated:goodman-ams01-amsterdam-data-centre-campus",
        )
        self.assertFalse(resolution["merge_allowed"])
        self.assertFalse(resolution["duplicate_suppression_allowed"])
        pdok = {
            item["request_id"]: item for item in resolution["pdok_controlled_requests"]
        }
        self.assertEqual(
            pdok["goodman_address"]["resolution_fields"]["gemeentenaam"],
            "Haarlemmermeer",
        )
        self.assertEqual(
            pdok["westpoort"]["resolution_fields"]["gemeentenaam"],
            "Amsterdam",
        )
        self.assertTrue(resolution["capture_disposition"]["recoverable"])
        self.assertTrue(
            all(value is False for value in resolution["guardrails"].values())
        )

    def test_import_is_offline_idempotent_and_evidence_order_independent(self) -> None:
        document = self._load()
        once = self._database_state(document)
        self.assertEqual(self._database_state(document, repetitions=2), once)
        reversed_evidence = copy.deepcopy(document)
        reversed_evidence["evidence"].reverse()
        self.assertEqual(self._database_state(reversed_evidence), once)
        entities, evidence, lifecycle, snapshots, capacities, models, workloads = once
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(len(lifecycle), 1)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(capacities, ())
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            (lifecycle[0][1], lifecycle[0][2], lifecycle[0][4]),
            (
                "under_construction",
                "2026-05-27",
                "authoritative_physical_status_update",
            ),
        )

    def test_artifact_is_immutable_hash_bound_and_contains_no_raw_capture(self) -> None:
        self._validate_artifact(ARTIFACT)
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
            b"http/2 200",
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
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        source_record = snapshot["source_records"][0]
        self.assertEqual(source_record["path"], f"sources/{SOURCE_NAME}")
        self.assertEqual(source_record["bytes"], SOURCE_BYTES)
        self.assertEqual(source_record["sha256"], SOURCE_SHA256)
        self.assertEqual(source_record["last_observed_status"], "under_construction")
        self.assertEqual(source_record["last_observed_status_date"], "2026-05-27")
        self.assertFalse(source_record["seeded"])

    def test_source_and_artifact_tampering_or_semantic_leaks_are_detected(self) -> None:
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

            future_capture = copy.deepcopy(original)
            future_capture["evidence"][0]["retrieved_at"] = "2026-07-22T00:00:00Z"
            future_path = root / "future-capture.json"
            self._write_document(future_path, future_capture)
            connection, _ = initialize(root / "future.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        future_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            copied_artifact = root / "artifact"
            shutil.copytree(ARTIFACT, copied_artifact)
            inventory_path = copied_artifact / "retrieval-inventory.json"
            inventory_path.chmod(0o644)
            inventory_path.write_bytes(inventory_path.read_bytes() + b" ")
            with self.assertRaises(AssertionError):
                self._validate_artifact(copied_artifact, check_modes=False)

        capacity_leak = copy.deepcopy(original)
        capacity_leak["capacities"].append(
            {
                "entity": "campus",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 78,
                "base": 78,
                "high": 78,
                "method": "source_reported",
                "confidence": 0.99,
                "evidence_key": original["evidence"][0]["key"],
                "as_of_date": "2026-07-21",
                "target_date": None,
                "notes": "Invalid semantic leak from an untyped total-site figure.",
            }
        )
        with self.assertRaises(AssertionError):
            self._assert_semantics(capacity_leak)

        coordinate_leak = copy.deepcopy(original)
        coordinate_leak["campus"]["coordinates"] = {
            "latitude": 52.4,
            "longitude": 4.8,
        }
        with self.assertRaises(AssertionError):
            self._assert_semantics(coordinate_leak)

    def test_keys_are_collision_free_and_source_remains_pending_unseeded(self) -> None:
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
            hashlib.sha256(FIRST_PENDING_DEFINITION.read_bytes()).hexdigest(),
            FIRST_PENDING_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FIRST_PENDING_MANIFEST.read_bytes()).hexdigest(),
            FIRST_PENDING_MANIFEST_SHA256,
        )
        forbidden = stable_keys | evidence_keys | {SOURCE_NAME}
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
                self.assertNotIn(SOURCE_NAME, selected_inputs)
                pending = definition.get("freshness_contract", {}).get(
                    "next_local_day_inputs_pending", []
                )
                if version < FIRST_PENDING_REFERENCE_VERSION:
                    self.assertNotIn(f"sources/{SOURCE_NAME}", pending or [])
                    continue
                self.assertEqual(pending, [f"sources/{SOURCE_NAME}"])

        release_inputs = ROOT / "releases" / "2026-07-20-open-seed-v58" / "source_inputs.json"
        release_text = release_inputs.read_text(encoding="utf-8")
        self.assertEqual(
            sorted(marker for marker in forbidden if marker in release_text),
            [],
        )

    def test_source_imports_offline_in_both_workspace_layouts(self) -> None:
        expected = {
            "capacity": 0,
            "entities": 2,
            "evidence": 2,
            "lifecycle": 1,
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
                assert result.evidence_created == (2 if iteration == 0 else 0)
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
            "SELECT status, as_of_date FROM lifecycle_observations "
            "ORDER BY as_of_date DESC LIMIT 1"
        ).fetchone()
        assert tuple(current) == ("under_construction", "2026-05-27")
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
