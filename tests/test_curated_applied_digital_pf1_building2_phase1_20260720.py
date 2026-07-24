from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "sources/curated-official-2026-07-20-applied-digital-pf1-building-2-"
    "phase-1-operational.json"
)
PARENT_SOURCE = (
    ROOT / "sources/curated-official-2026-07-19-applied-digital-pf1-second-150mw.json"
)
ARTIFACT = (
    ROOT
    / "source_artifacts/applied-digital-pf1-building-2-phase-1-2026-07-20-v1"
)
SOURCE_BYTES = 11_260
SOURCE_SHA256 = "e85a0998f34e851c03991434a048e40e140ce0de22d2600c0a5bf3b3b6429fd4"
PARENT_SOURCE_SHA256 = (
    "bb586f6351c3b97f099c485e067b6e1c843d795d612f76b00f0612470d381332"
)
RECORDED_AT = "2026-07-21T04:16:00Z"
EVIDENCE_KEY = (
    "applied-digital-pf1-building-2-phase-1-ready-for-service-2026-07-01-"
    "captured-2026-07-20"
)
CAMPUS_KEY = "epoch-ai:data-center:ae2c8749-c97f-5512-a0ad-a40ed8df37ce"
PARENT_PROJECT_KEY = (
    "curated:applied-digital-polaris-forge-1:second-150mw-facility"
)
PHASE_PROJECT_KEY = f"{PARENT_PROJECT_KEY}:phase-1"
ARTIFACT_FILE_SPECS = {
    "README.md": (
        2_097,
        "869303b3c69ff3f820014c457571faa3aff511cc5f72b032342689d84ec30bc1",
    ),
    "manifest.json": (
        861,
        "e541dedf6a4c93c86e84ac4efb41fbfb943ac7bb2de438ea05c0c2b96df8a5e5",
    ),
    "manifest.sha256": (
        80,
        "5ea674b8ff893b8ba16ef0750fed8a25d8ff664e104b1e50b844bcce65613118",
    ),
    "phase-boundaries.json": (
        2_499,
        "4766c741b5b36d4ca5a9544715891c4ecfa4e23fd4e66d8bce33b5890e423bc1",
    ),
    "retrieval-inventory.json": (
        2_471,
        "2c6ceb2de5a9aa99affea46874125a4c311766cef61bb987582fc352f0b6cbd7",
    ),
    "source-snapshot.json": (
        2_037,
        "326158d20715dce4a47cad5005d4879b2be06a29864e0acfe7e48fa5b153cba4",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AppliedDigitalPf1Building2Phase1Tests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated Applied Digital import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _import_child(self):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        result = CuratedOfficialSourceAdapterV11().import_file(
            connection,
            SOURCE,
            recorded_at=RECORDED_AT,
        )
        return temporary, connection, result

    def test_source_is_canonical_byte_pinned_and_phase_scoped(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE.stat().st_mode))
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
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["published_at"], "2026-07-01")
        self.assertEqual(evidence["retrieved_at"], "2026-07-21T04:15:26Z")
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(
            evidence["content_hash"],
            "df69726edbc12f5698f8224a348be32c9bb88c1cf93f354af84ba2c996ab7d68",
        )
        metadata = evidence["metadata"]
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 29_805)
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "55455fbd83328b32e309280d5ebd739b625bf7bdbc28beba2c2714b521c1ade9",
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "e80ffecc155c81099e4e5aa5bbb26c421108a765ebc21238a2ac4b7854137005",
        )
        self.assertIn("no Authorization", metadata["request_credentials_guardrail"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["reported_phase_1_operational_critical_it_mw"], 75)
        self.assertEqual(metadata["reported_campus_live_capacity_mw"], 175)
        self.assertEqual(
            metadata["reported_campus_full_build_contracted_critical_it_mw"], 400
        )
        self.assertEqual(metadata["parent_project_stable_key"], PARENT_PROJECT_KEY)
        self.assertIn(
            "operational 150 MW Building 2 row",
            metadata["full_building_capacity_guardrail"],
        )
        self.assertIn(
            "Neither creates a phase capacity row",
            metadata["capacity_non_additivity_guardrail"],
        )

        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PHASE_PROJECT_KEY)
        self.assertEqual(document["project"]["name"], "Polaris Forge 1 Building 2 Phase 1")
        self.assertEqual(
            document["project"]["roles"],
            {"developer": ["Applied Digital"], "operator": ["Applied Digital"]},
        )
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["address"], "Ellendale, North Dakota, United States")
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "operational",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-07-01",
                    "method": "authoritative_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-07-01",
                    "method": "company_disclosure",
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
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-07-01",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            {
                key: capacity[key]
                for key in (
                    "entity",
                    "metric",
                    "stage",
                    "unit",
                    "low",
                    "base",
                    "high",
                    "method",
                    "as_of_date",
                    "target_date",
                )
            },
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "operational",
                "unit": "MW",
                "low": 75,
                "base": 75,
                "high": 75,
                "method": "reported",
                "as_of_date": "2026-07-01",
                "target_date": None,
            },
        )
        for excluded in ("175 MW", "400 MW", "150 MW"):
            self.assertIn(excluded, capacity["notes"])

    def test_offline_import_has_one_exact_phase_claim_per_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    first = CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at=RECORDED_AT,
                    )
                    second = CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at=RECORDED_AT,
                    )
                self.assertEqual(first.entities_created, 2)
                self.assertEqual(first.evidence_created, 1)
                self.assertEqual(first.warnings, ())
                self.assertEqual(second.entities_created, 0)
                self.assertEqual(second.evidence_created, 0)
                self.assertEqual(second.warnings, ())
                self.assertEqual(validate_database(connection), [])
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
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
                        "operating_model_observations": 1,
                        "workload_observations": 1,
                        "capacity_estimates": 1,
                    },
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id"
                        )
                    ],
                    [
                        (
                            PHASE_PROJECT_KEY,
                            "operational",
                            "2026-07-01",
                            "authoritative_status_update",
                        )
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, unit, low, base, "
                            "high, method, as_of_date, target_date "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id"
                        )
                    ],
                    [
                        (
                            PHASE_PROJECT_KEY,
                            "critical_it_mw",
                            "operational",
                            "MW",
                            75.0,
                            75.0,
                            75.0,
                            "reported",
                            "2026-07-01",
                            None,
                        )
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, operating_model "
                            "FROM operating_model_observations JOIN entities "
                            "ON entities.id = operating_model_observations.entity_id"
                        )
                    ],
                    [(PHASE_PROJECT_KEY, "colocation")],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, workload "
                            "FROM workload_observations JOIN entities "
                            "ON entities.id = workload_observations.entity_id"
                        )
                    ],
                    [(PHASE_PROJECT_KEY, "ai_specialized_unspecified")],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE base IN (150, 175, 400) OR metric != 'critical_it_mw'"
                    ).fetchone()[0],
                    0,
                )
                snapshots = list(
                    connection.execute(
                        "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                        "tags_json FROM entity_snapshots JOIN entities "
                        "ON entities.id = entity_snapshots.entity_id "
                        "ORDER BY entities.stable_key"
                    )
                )
                self.assertEqual(
                    [row["stable_key"] for row in snapshots],
                    [PHASE_PROJECT_KEY, CAMPUS_KEY],
                )
                for row in snapshots:
                    self.assertIsNone(row["latitude"])
                    self.assertIsNone(row["longitude"])
                    self.assertIsNone(row["geometry_json"])
                    tags = json.loads(row["tags_json"])
                    self.assertEqual(tags["role:developer"], "Applied Digital")
                    self.assertEqual(tags["role:operator"], "Applied Digital")
                    self.assertNotIn("role:owner", tags)
                    self.assertNotIn("role:tenant", tags)
                    self.assertNotIn("role:customer", tags)
            finally:
                connection.close()

    def test_phase_child_is_distinct_and_does_not_mutate_parent_claims(self) -> None:
        self.assertEqual(sha256(PARENT_SOURCE), PARENT_SOURCE_SHA256)
        parent_document = json.loads(PARENT_SOURCE.read_text(encoding="utf-8"))
        child_document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(parent_document["project"]["stable_key"], PARENT_PROJECT_KEY)
        self.assertEqual(child_document["project"]["stable_key"], PHASE_PROJECT_KEY)
        self.assertNotEqual(
            parent_document["project"]["stable_key"],
            child_document["project"]["stable_key"],
        )
        self.assertEqual(
            parent_document["lifecycle"][0]["value"], "under_construction"
        )
        self.assertEqual(parent_document["capacities"][0]["base"], 150)
        self.assertEqual(parent_document["capacities"][0]["stage"], "contracted")

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        PARENT_SOURCE,
                        retrieved_at="2026-07-19T14:27:13Z",
                    )
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at=RECORDED_AT,
                    )
                self.assertEqual(validate_database(connection), [])
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 1), ("project", 2)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key, as_of_date"
                        )
                    ],
                    [
                        (PARENT_PROJECT_KEY, "under_construction", "2026-04-08"),
                        (PHASE_PROJECT_KEY, "operational", "2026-07-01"),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, base, as_of_date "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id "
                            "ORDER BY entities.stable_key, as_of_date"
                        )
                    ],
                    [
                        (
                            PARENT_PROJECT_KEY,
                            "critical_it_mw",
                            "contracted",
                            150.0,
                            "2026-04-23",
                        ),
                        (
                            PHASE_PROJECT_KEY,
                            "critical_it_mw",
                            "operational",
                            75.0,
                            "2026-07-01",
                        ),
                    ],
                )
            finally:
                connection.close()

    def test_per_evidence_time_gate_rejects_pre_capture_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:15:25Z",
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

    def test_artifact_is_hash_closed_compact_unseeded_and_raw_free(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            path = ARTIFACT / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertNotIn(b"<!DOCTYPE html", path.read_bytes())

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(
            {item["path"] for item in manifest["files"]},
            {
                "README.md",
                "phase-boundaries.json",
                "retrieval-inventory.json",
                "source-snapshot.json",
            },
        )
        for item in manifest["files"]:
            path = ARTIFACT / item["path"]
            self.assertEqual(len(path.read_bytes()), item["bytes"])
            self.assertEqual(sha256(path), item["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
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
        self.assertEqual(inventory["completed_response_requests"], 1)
        self.assertEqual(inventory["successful_http_requests"], 1)
        self.assertEqual(inventory["failed_http_requests"], 0)
        self.assertEqual(inventory["evidence_supporting_requests"], 1)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            inventory["temporary_capture_trash_path"],
            "/Users/kian/.Trash/dca-apld-pf1-phase1.eKfqxk",
        )
        for key in (
            "raw_response_bodies_retained_in_artifact",
            "raw_response_headers_retained_in_artifact",
            "curl_writeouts_retained_in_artifact",
            "publisher_media_retained",
        ):
            self.assertFalse(inventory[key])
        capture = inventory["controlled_http_requests"][0]
        self.assertEqual(capture["retrieved_at"], "2026-07-21T04:15:26Z")
        self.assertEqual(capture["body"]["bytes"], 29_805)
        self.assertEqual(
            capture["body"]["sha256"],
            "df69726edbc12f5698f8224a348be32c9bb88c1cf93f354af84ba2c996ab7d68",
        )
        self.assertFalse(capture["body"]["retained_in_artifact"])
        self.assertFalse(capture["headers"]["retained_in_artifact"])
        self.assertFalse(capture["curl_writeout"]["retained_in_artifact"])

        boundaries = json.loads(
            (ARTIFACT / "phase-boundaries.json").read_text(encoding="utf-8")
        )
        self.assertEqual(boundaries["parent_project"]["stable_key"], PARENT_PROJECT_KEY)
        self.assertEqual(
            boundaries["parent_project"]["source_sha256"], PARENT_SOURCE_SHA256
        )
        self.assertFalse(boundaries["parent_project"]["mutated_by_this_artifact"])
        self.assertEqual(boundaries["phase_child"]["stable_key"], PHASE_PROJECT_KEY)
        self.assertEqual(
            boundaries["phase_child"]["normalized_capacity"]["base"], 75
        )
        assertions = boundaries["semantic_assertions"]
        self.assertTrue(all(value is False for value in assertions.values()))
        non_child = boundaries["reported_non_child_totals"]
        self.assertEqual(
            {key: row["value"] for key, row in non_child.items()},
            {
                "campus_live_capacity_mw": 175,
                "campus_full_build_contracted_critical_it_mw": 400,
                "full_building_critical_it_mw": 150,
            },
        )
        for row in non_child.values():
            self.assertFalse(row["additive_with_phase_child"])

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["package_state"], "standalone_unseeded")
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        record = snapshot["source_records"][0]
        self.assertEqual(record["bytes"], SOURCE_BYTES)
        self.assertEqual(record["sha256"], SOURCE_SHA256)
        self.assertEqual(record["project_stable_key"], PHASE_PROJECT_KEY)
        self.assertEqual(record["parent_project_stable_key"], PARENT_PROJECT_KEY)
        self.assertFalse(record["coordinates_present"])
        self.assertFalse(record["geometry_present"])
        self.assertFalse(record["seeded"])


if __name__ == "__main__":
    unittest.main()
