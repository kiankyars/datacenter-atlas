from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.current_coverage_v20 import (
    ADDED_ARTIFACT_IDS,
    ALL_ENTRIES_SHA256,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    PARITY_GAPS_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_5_SHA256,
    REPLACEMENT_ARTIFACT_IDS,
    UNCHANGED_42_SHA256,
    V19_BASE_LINEAGE,
    V20_DEFINITION_SHA256,
    V20_GENERATED_AT,
    V20_LEDGER_ID,
    build_current_coverage_ledger_v20,
    make_v20_definition,
    validate_current_coverage_ledger_v20,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v20.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v19.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v20"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v19"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v20.py"

DEFINITION_SHA256 = "8a8aca77431ca21867f8f3317114b40cb41c642aacc9f333d7eb1f1a402410b3"
LEDGER_SHA256 = "6a500f9d5b54aa695d1914e7f0c102696ad3e5cfd35d7dcb3105f34760e7bc3a"
MANIFEST_SHA256 = "9e5eaee21e02888f361258fb6ee71a86664831f4073144641d43ad95a6361a26"
SIDECAR_SHA256 = "0ddf7f0699d1f8330df449956a7bafe86823dddbc124f8bccd30593d8368febf"
V20_TREE_SHA256 = "96994eed8d97aba06f7f303bd39a75f3459bb0862150a72020513b72f403758f"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v20.py": (
        49_253,
        "d53d63e326b7f9a1459b51fdf937b12fb3c73aa3bdeaa76a1217b5ba27d538ee",
    ),
    ROOT / "current_coverage_v20.py": (
        150,
        "3a173a062509392117c12d04cecd363a4f367044e42bd8d9367ec3d92040a291",
    ),
    SCRIPT: (
        2_781,
        "0f1afa49266c94b951f53fe78dc5ba121ead3f68117cf960b176f0b6f8522e0b",
    ),
    DEFINITION: (143_354, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (98_623, LEDGER_SHA256),
    BUNDLE / "manifest.json": (27_429, MANIFEST_SHA256),
    BUNDLE / "manifest.sha256": (80, SIDECAR_SHA256),
}

BASE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v19.py": (
        55_568,
        "ea6f08c025727d5702f20e6d7c195cd56881fd4fd2861f3f8ce75bb6d39bb378",
    ),
    ROOT / "current_coverage_v19.py": (
        150,
        "5d66572dc18aa43dd6ebe68c20d7316032059100b449916353c7f27c2bf91e8e",
    ),
    BASE_DEFINITION: (
        142_460,
        "6ffd11fdeab77cb92c9c820c917f0a0e02f68c417907b70aec8059fbae9dee04",
    ),
    BASE_BUNDLE / "current-coverage-ledger.json": (
        98_188,
        "143dacb68947f1d6483a47da1ebd294648a40d0ca2aab2deba078ec36fbd124a",
    ),
    BASE_BUNDLE / "manifest.json": (
        27_429,
        "bcfe53a5a23e3c8dbca40feb646cfff93abd24614a60382266dd830376074f42",
    ),
    BASE_BUNDLE / "manifest.sha256": (
        80,
        "79ff81352c85ae188d5ecd2d9390e1f6a29905452ed60dbdc3bbeef05fcdc5c6",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, _sha256(path)


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _component_digest(entries: list[dict]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _entry_map(document: dict) -> dict[str, dict]:
    return {entry["artifact_id"]: entry for entry in document["entries"]}


def _implementation_module():
    return importlib.import_module(build_current_coverage_ledger_v20.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v20 attempted network access")
    with (
        patch.object(socket, "socket", side_effect=blocked),
        patch.object(socket, "create_connection", side_effect=blocked),
        patch.object(socket, "getaddrinfo", side_effect=blocked),
        patch.object(socket, "gethostbyname", side_effect=blocked),
    ):
        yield


class FrozenCurrentCoverageLedgerV20Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_and_pins_v19(self) -> None:
        self.assertEqual(V20_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, expected in {**FILE_PINS, **BASE_PINS}.items():
            self.assertEqual(_checkpoint(path), expected, path)

        module = _implementation_module()
        with _offline_guard():
            module._v19.validate_current_coverage_ledger_v19(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
            first = build_current_coverage_ledger_v20(DEFINITION)
            second = build_current_coverage_ledger_v20(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v20(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v20(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V20_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V19_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 47)
        self.assertEqual(
            module._v19._v14._tree_digest(BUNDLE, "v20 bundle"),
            (3, 1, V20_TREE_SHA256),
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_exactly_42_inherited_and_five_replacements(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        self.assertEqual(
            ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v24": "construction-map-public-open-v26",
                "construction-master-public-open-v24": "construction-master-public-open-v26",
                "coverage-audit-public-open-v24": "coverage-audit-public-open-v26",
                "exact-identity-decisions-public-open-v3": "exact-identity-decisions-public-open-v5",
                "federation-public-open-v25": "federation-public-open-v27",
            },
        )
        self.assertEqual(ADDED_ARTIFACT_IDS, set())
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(set(entries) - set(base_entries), REPLACEMENT_ARTIFACT_IDS)
        self.assertEqual(len(entries), 47)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        replacements = [
            entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
        ]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual((len(unchanged), len(replacements)), (42, 5))
        for artifact_id in unchanged_ids:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )
        self.assertEqual(_component_digest(unchanged), UNCHANGED_42_SHA256)
        self.assertEqual(_component_digest(replacements), REPLACEMENT_5_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(
                _canonical_line(json.loads(DEFINITION.read_text())["parity_gaps"])
            ).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_timeline_v2_is_deliberately_deferred_not_added(self) -> None:
        document = json.loads(DEFINITION.read_text())
        ids = {entry["artifact_id"] for entry in document["entries"]}
        self.assertFalse(any("construction-timeline" in artifact_id for artifact_id in ids))
        self.assertEqual(document["base_ledger"], V19_BASE_LINEAGE)
        self.assertEqual(len(ids), 47)
        self.assertEqual(make_v20_definition(ROOT), DEFINITION.read_bytes())

    def test_successor_metrics_and_currentness_boundaries_are_exact(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))

        def metrics(artifact_id: str) -> dict[str, object]:
            return {
                row["label"]: row["value"]
                for row in entries[artifact_id]["metrics"]
            }

        map_metrics = metrics("construction-map-public-open-v26")
        self.assertEqual(map_metrics["mapped_total_rows"], 108_987)
        self.assertEqual(map_metrics["unmapped_rows"], 298)
        self.assertEqual(map_metrics["default_visible_rows"], 6_493)
        self.assertIsNone(map_metrics["unique_physical_sites"])

        master_metrics = metrics("construction-master-public-open-v26")
        self.assertEqual(master_metrics["total_master_rows"], 109_285)
        self.assertEqual(master_metrics["tier_a_rows"], 493)
        self.assertEqual(master_metrics["replacement_rows"], 373)
        self.assertEqual(master_metrics["satellite_recovery_rows"], 0)
        self.assertIsNone(master_metrics["unique_physical_sites"])
        self.assertIn(
            "last-observed",
            " ".join(entries["construction-master-public-open-v26"]["limitations"]),
        )

        coverage_metrics = metrics("coverage-audit-public-open-v26")
        self.assertEqual(coverage_metrics["source_scoped_rows"], 16_155)
        self.assertEqual(coverage_metrics["coverage_groups"], 754)
        self.assertEqual(coverage_metrics["open_gaps"], 3_736)
        self.assertEqual(coverage_metrics["methodology_support_jobs"], 74)
        self.assertEqual(coverage_metrics["methodology_support_views"], 71)
        self.assertIsNone(coverage_metrics["unique_physical_sites"])

        identity_metrics = metrics("exact-identity-decisions-public-open-v5")
        self.assertEqual(identity_metrics["exact_source_record_components"], 8_293)
        self.assertEqual(identity_metrics["canonical_topology_links"], 2_349)
        self.assertEqual(identity_metrics["raw_topology_links"], 2_754)
        self.assertEqual(identity_metrics["unresolved_candidate_references"], 100_537)
        self.assertIsNone(identity_metrics["unique_physical_sites"])

        federation_metrics = metrics("federation-public-open-v27")
        self.assertEqual(federation_metrics["source_scoped_rows"], 16_155)
        self.assertEqual(federation_metrics["construction_pipeline_records"], 6_623)
        self.assertEqual(
            federation_metrics["non_review_construction_pipeline_records"], 493
        )
        self.assertEqual(
            federation_metrics["review_only_construction_pipeline_records"], 6_130
        )
        self.assertIsNone(federation_metrics["unique_physical_sites"])

        audit_manifest = json.loads(
            (
                ROOT
                / "audits/2026-07-20-public-open-coverage-v26/manifest.json"
            ).read_text()
        )
        self.assertEqual(audit_manifest["as_of"], "2026-07-20")
        self.assertFalse(audit_manifest["scope"]["current_status_inferred"])
        self.assertEqual(
            audit_manifest["scope"]["lifecycle_status_semantics"], "last_observed"
        )

    def test_inherited_imagery_review_remains_byte_exact_and_review_only(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        review_id = "satellite-change-review-open-seed-v56-active-review-v1"
        self.assertEqual(
            _canonical_line(entries[review_id]), _canonical_line(base_entries[review_id])
        )
        self.assertEqual(entries[review_id]["evidence_scope"], "review_only")
        review_metrics = {
            row["label"]: row["value"] for row in entries[review_id]["metrics"]
        }
        self.assertFalse(review_metrics["atlas_mutation"])
        self.assertFalse(review_metrics["capacity_claim_created"])
        self.assertFalse(review_metrics["site_count_claim_created"])

    def test_parity_gap_references_are_exactly_remapped(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(
            [gap["gap_id"] for gap in current["parity_gaps"]],
            [gap["gap_id"] for gap in base["parity_gaps"]],
        )
        for base_gap, current_gap in zip(
            base["parity_gaps"], current["parity_gaps"], strict=True
        ):
            expected = sorted(
                ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in base_gap["affected_artifact_ids"]
            )
            self.assertEqual(current_gap["affected_artifact_ids"], expected)
            self.assertEqual(current_gap["status"], base_gap["status"])
            self.assertEqual(current_gap["summary"], base_gap["summary"])

    def test_generated_at_is_past_and_after_all_replacement_inputs(self) -> None:
        generated_at = datetime.fromisoformat(V20_GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated_at, datetime.now(UTC))
        source_times = [
            "2026-07-21T05:05:01Z",
            "2026-07-21T05:05:00Z",
            "2026-07-21T05:35:00Z",
            "2026-07-21T04:50:00Z",
            "2026-07-21T04:45:00Z",
        ]
        for value in source_times:
            observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            self.assertLessEqual(observed, generated_at)


if __name__ == "__main__":
    unittest.main()
