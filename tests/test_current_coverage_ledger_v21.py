from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.current_coverage_v21 import (
    ADDED_2_SHA256,
    ADDED_ARTIFACT_IDS,
    ALL_ENTRIES_SHA256,
    ARTIFACT_KINDS_V4,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    BUNDLE_FORMAT_V4,
    DEFINITION_SCHEMA_VERSION_V4,
    EXCLUDED_CONCURRENT_ARTIFACT_MARKERS,
    EXCLUDED_DISCOVERY_ARTIFACTS,
    LEDGER_FORMAT_V4,
    LEDGER_SCHEMA_VERSION_V4,
    PARITY_GAPS_SHA256,
    RECORD_UNITS_V4,
    REMOVED_7_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_5_SHA256,
    REPLACEMENT_ARTIFACT_IDS,
    SATELLITE_ARTIFACT_ID,
    SATELLITE_REPLACEMENTS,
    TIMELINE_ARTIFACT_ID,
    UNCHANGED_40_SHA256,
    V20_BASE_LINEAGE,
    V21_DEFINITION_SHA256,
    V21_LEDGER_ID,
    build_current_coverage_ledger_v21,
    make_v21_definition,
    validate_current_coverage_ledger_v21,
    write_current_coverage_ledger_v21,
)


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
DEFINITION = ROOT / "sources/current-coverage-2026-07-21-v21.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v20.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-21-v21"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v20"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v21.py"

DEFINITION_PIN = (
    146_115,
    "116fdc6beb9c03ba386c80aab43de406049567246e7a40f439c5712b0101ea78",
)
LEDGER_PIN = (
    100_079,
    "9198ddec824d84826e74b5696fbf3746128c3e8a670d45e98282f15a95613d80",
)
MANIFEST_PIN = (
    27_661,
    "9870a32f953f09df8f5314fbd365ef6e563e2b86b964fa1795f725b535a983e3",
)
SIDECAR_PIN = (
    80,
    "c27ab348ee9f9f93fb1d520bac59042738446b903f45d4b2d045ff53991ea0ed",
)
BUNDLE_TREE_SHA256 = "7aa1fb23ca9f11b11eae05c2a531040d6e9289ffff1bc7040e429872791e3eb6"

CODE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v21.py": (
        75_240,
        "0429ff1317c247351608c2c6e421d0fbd30df73f47e41a1b0d1aef0ff2fa9d9f",
    ),
    ROOT / "current_coverage_v21.py": (
        150,
        "2b807118bcad2ba30c2684d566390e71d192cc2957b2a523daf7dfddb789758a",
    ),
    SCRIPT: (
        2_781,
        "6475941f55053a61e63c5db355c6f302186f9593eb5bff40e3b630dfaeb3425d",
    ),
}

BASE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v20.py": (
        49_253,
        "d53d63e326b7f9a1459b51fdf937b12fb3c73aa3bdeaa76a1217b5ba27d538ee",
    ),
    ROOT / "current_coverage_v20.py": (
        150,
        "3a173a062509392117c12d04cecd363a4f367044e42bd8d9367ec3d92040a291",
    ),
    BASE_DEFINITION: (
        143_354,
        "8a8aca77431ca21867f8f3317114b40cb41c642aacc9f333d7eb1f1a402410b3",
    ),
    BASE_BUNDLE / "current-coverage-ledger.json": (
        98_623,
        "6a500f9d5b54aa695d1914e7f0c102696ad3e5cfd35d7dcb3105f34760e7bc3a",
    ),
    BASE_BUNDLE / "manifest.json": (
        27_429,
        "9e5eaee21e02888f361258fb6ee71a86664831f4073144641d43ad95a6361a26",
    ),
    BASE_BUNDLE / "manifest.sha256": (
        80,
        "0ddf7f0699d1f8330df449956a7bafe86823dddbc124f8bccd30593d8368febf",
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


def _metrics(entry: dict) -> dict[str, object]:
    return {metric["label"]: metric["value"] for metric in entry["metrics"]}


def _module():
    return importlib.import_module(build_current_coverage_ledger_v21.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v21 attempted network access")
    with (
        patch.object(socket, "socket", side_effect=blocked),
        patch.object(socket, "create_connection", side_effect=blocked),
        patch.object(socket, "getaddrinfo", side_effect=blocked),
        patch.object(socket, "gethostbyname", side_effect=blocked),
    ):
        yield


class FrozenCurrentCoverageLedgerV21Tests(unittest.TestCase):
    def test_frozen_pins_modes_tree_and_schema_v4_are_exact(self) -> None:
        module = _module()
        self.assertEqual(V21_DEFINITION_SHA256, DEFINITION_PIN[1])
        for path, expected in {**CODE_PINS, **BASE_PINS}.items():
            self.assertEqual(_checkpoint(path), expected, path)
        self.assertEqual(_checkpoint(DEFINITION), DEFINITION_PIN)
        self.assertEqual(
            _checkpoint(BUNDLE / "current-coverage-ledger.json"), LEDGER_PIN
        )
        self.assertEqual(_checkpoint(BUNDLE / "manifest.json"), MANIFEST_PIN)
        self.assertEqual(_checkpoint(BUNDLE / "manifest.sha256"), SIDECAR_PIN)
        self.assertEqual(
            module._v20._v19._v14._tree_digest(BUNDLE, "v21 bundle"),
            (3, 1, BUNDLE_TREE_SHA256),
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )
        definition = json.loads(DEFINITION.read_text())
        ledger = json.loads((BUNDLE / "current-coverage-ledger.json").read_text())
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(definition["schema_version"], DEFINITION_SCHEMA_VERSION_V4)
        self.assertEqual(ledger["schema_version"], LEDGER_SCHEMA_VERSION_V4)
        self.assertEqual(manifest["schema_version"], LEDGER_SCHEMA_VERSION_V4)
        self.assertEqual(ledger["format"], LEDGER_FORMAT_V4)
        self.assertEqual(manifest["format"], BUNDLE_FORMAT_V4)
        self.assertEqual(definition["base_ledger"], V20_BASE_LINEAGE)
        self.assertEqual(ledger["base_ledger"], V20_BASE_LINEAGE)
        self.assertEqual(manifest["base_ledger"], V20_BASE_LINEAGE)

    def test_delta_is_exactly_40_inherited_five_core_and_two_added(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        self.assertEqual(
            ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v26": "construction-map-public-open-v27",
                "construction-master-public-open-v26": "construction-master-public-open-v27",
                "coverage-audit-public-open-v26": "coverage-audit-public-open-v27",
                "exact-identity-decisions-public-open-v5": "exact-identity-decisions-public-open-v6",
                "federation-public-open-v27": "federation-public-open-v28",
            },
        )
        self.assertEqual(
            SATELLITE_REPLACEMENTS,
            {
                "satellite-recovery-unknown033-review-v1": SATELLITE_ARTIFACT_ID,
                "satellite-unknown-batch-030": SATELLITE_ARTIFACT_ID,
            },
        )
        self.assertEqual(
            ADDED_ARTIFACT_IDS,
            {TIMELINE_ARTIFACT_ID, SATELLITE_ARTIFACT_ID},
        )
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(
            set(entries) - set(base_entries),
            REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS,
        )
        self.assertEqual(len(entries), 47)
        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        replacements = [
            entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
        ]
        added = [entries[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)]
        removed = [
            base_entries[artifact_id] for artifact_id in sorted(REMOVED_ARTIFACT_IDS)
        ]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual((len(unchanged), len(replacements), len(added)), (40, 5, 2))
        for artifact_id in unchanged_ids:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )
        self.assertEqual(_component_digest(unchanged), UNCHANGED_40_SHA256)
        self.assertEqual(_component_digest(replacements), REPLACEMENT_5_SHA256)
        self.assertEqual(_component_digest(added), ADDED_2_SHA256)
        self.assertEqual(_component_digest(removed), REMOVED_7_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        parity_gaps = json.loads(DEFINITION.read_text())["parity_gaps"]
        self.assertEqual(
            hashlib.sha256(_canonical_line(parity_gaps)).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_schema_v4_only_extends_the_two_controlled_vocabularies(self) -> None:
        module = _module()
        self.assertEqual(
            ARTIFACT_KINDS_V4 - module._legacy.ARTIFACT_KINDS,
            {"construction_timeline"},
        )
        self.assertEqual(
            RECORD_UNITS_V4 - module._legacy.RECORD_UNITS,
            {"lifecycle_observation"},
        )
        self.assertNotIn("construction_timeline", module._legacy.ARTIFACT_KINDS)
        self.assertNotIn("lifecycle_observation", module._legacy.RECORD_UNITS)
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        self.assertEqual(
            entries[TIMELINE_ARTIFACT_ID]["artifact_kind"],
            "construction_timeline",
        )
        self.assertEqual(
            entries[TIMELINE_ARTIFACT_ID]["record_units"],
            ["lifecycle_observation"],
        )
        ledger = json.loads((BUNDLE / "current-coverage-ledger.json").read_text())
        counts = ledger["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 47)
        self.assertEqual(counts["by_evidence_scope"]["review_only"], 30)
        self.assertEqual(counts["by_evidence_scope"]["source_scoped"], 6)
        self.assertEqual(counts["by_publication_mode"]["public_row_release"], 6)
        self.assertEqual(counts["by_record_unit"]["catalog_job"], 7)
        self.assertEqual(counts["by_record_unit"]["lifecycle_observation"], 1)
        self.assertEqual(counts["public_open_review_only_artifacts"], 26)

    def test_core_successor_metrics_and_last_observed_boundary_are_exact(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        map_metrics = _metrics(entries["construction-map-public-open-v27"])
        self.assertEqual(map_metrics["mapped_total_rows"], 108_993)
        self.assertEqual(map_metrics["unmapped_rows"], 320)
        self.assertEqual(map_metrics["default_visible_rows"], 6_499)
        self.assertIsNone(map_metrics["unique_physical_sites"])

        master_metrics = _metrics(entries["construction-master-public-open-v27"])
        self.assertEqual(master_metrics["total_master_rows"], 109_313)
        self.assertEqual(master_metrics["tier_a_rows"], 521)
        self.assertEqual(master_metrics["replacement_rows"], 401)
        self.assertEqual(master_metrics["satellite_recovery_rows"], 0)
        self.assertIsNone(master_metrics["unique_physical_sites"])
        self.assertIn(
            "last-observed",
            " ".join(entries["construction-master-public-open-v27"]["limitations"]),
        )

        coverage_metrics = _metrics(entries["coverage-audit-public-open-v27"])
        self.assertEqual(coverage_metrics["source_scoped_rows"], 16_208)
        self.assertEqual(coverage_metrics["coverage_groups"], 816)
        self.assertEqual(coverage_metrics["open_gaps"], 3_959)
        self.assertIsNone(coverage_metrics["unique_physical_sites"])

        identity_metrics = _metrics(entries["exact-identity-decisions-public-open-v6"])
        self.assertEqual(identity_metrics["exact_source_record_components"], 8_346)
        self.assertEqual(identity_metrics["canonical_topology_links"], 2_377)
        self.assertEqual(identity_metrics["raw_topology_links"], 2_782)
        self.assertEqual(identity_metrics["unresolved_candidate_references"], 100_538)
        self.assertIsNone(identity_metrics["unique_physical_sites"])

        federation_metrics = _metrics(entries["federation-public-open-v28"])
        self.assertEqual(federation_metrics["source_scoped_rows"], 16_208)
        self.assertEqual(federation_metrics["construction_pipeline_records"], 6_651)
        self.assertEqual(
            federation_metrics["non_review_construction_pipeline_records"], 521
        )
        self.assertEqual(
            federation_metrics["review_only_construction_pipeline_records"], 6_130
        )
        self.assertIsNone(federation_metrics["unique_physical_sites"])

    def test_timeline_and_unknown034_are_exact_and_non_additive(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        timeline = entries[TIMELINE_ARTIFACT_ID]
        timeline_metrics = _metrics(timeline)
        self.assertEqual(timeline["publication_mode"], "public_row_release")
        self.assertEqual(timeline["evidence_scope"], "source_scoped")
        self.assertEqual(timeline_metrics["raw_lifecycle_observations"], 459)
        self.assertEqual(timeline_metrics["entities_with_lifecycle_observations"], 443)
        self.assertEqual(timeline_metrics["source_families"], 197)
        self.assertEqual(timeline_metrics["current_status_classification"], "unknown")
        self.assertFalse(timeline_metrics["current_construction_claimed"])
        self.assertEqual(timeline_metrics["stt_status"], "under_construction")
        self.assertEqual(timeline_metrics["stt_freshness_class"], "stale_over_365_days")
        self.assertFalse(timeline_metrics["stt_current_construction_claim"])
        self.assertIsNone(timeline_metrics["unique_physical_sites"])

        satellite = entries[SATELLITE_ARTIFACT_ID]
        satellite_metrics = _metrics(satellite)
        self.assertEqual(satellite["evidence_scope"], "review_only")
        self.assertEqual(satellite_metrics["cumulative_jobs_completed"], 4_397)
        self.assertEqual(satellite_metrics["cumulative_jobs_unavailable_no_scene"], 303)
        self.assertEqual(satellite_metrics["cumulative_jobs_pending"], 2_036)
        self.assertEqual(satellite_metrics["cumulative_jobs_failed"], 0)
        self.assertEqual(satellite_metrics["delta_jobs_completed"], 22)
        self.assertEqual(satellite_metrics["delta_jobs_unavailable_no_scene"], 3)
        self.assertEqual(satellite_metrics["mode"], "catalog_only")
        self.assertFalse(satellite_metrics["imagery_assets_downloaded"])
        self.assertFalse(satellite_metrics["change_analysis_executed"])
        self.assertFalse(satellite_metrics["atlas_mutation"])
        self.assertIn("must not be added", " ".join(satellite["limitations"]))
        checkpoints = {row["checkpoint_id"]: row for row in satellite["checkpoints"]}
        self.assertEqual(
            checkpoints["batch_manifest"]["binding"],
            {
                "checkpoint_id": "continuation_manifest",
                "json_pointer": "/output/batch_manifest",
            },
        )

    def test_parity_refs_are_remapped_deduplicated_and_only_stale_text_changes(
        self,
    ) -> None:
        module = _module()
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_by_id = {gap["gap_id"]: gap for gap in base["parity_gaps"]}
        current_by_id = {gap["gap_id"]: gap for gap in current["parity_gaps"]}
        self.assertEqual(set(current_by_id), set(base_by_id))
        mapping = {**ARTIFACT_REPLACEMENTS, **SATELLITE_REPLACEMENTS}
        for gap_id, base_gap in base_by_id.items():
            expected = {
                mapping.get(artifact_id, artifact_id)
                for artifact_id in base_gap["affected_artifact_ids"]
            }
            if gap_id in module._TIMELINE_GAP_IDS:
                expected.add(TIMELINE_ARTIFACT_ID)
            current_gap = current_by_id[gap_id]
            self.assertEqual(current_gap["affected_artifact_ids"], sorted(expected))
            self.assertEqual(len(current_gap["affected_artifact_ids"]), len(expected))
            self.assertEqual(current_gap["status"], base_gap["status"])
            if gap_id in module._UPDATED_GAP_SUMMARIES:
                self.assertEqual(
                    current_gap["summary"], module._UPDATED_GAP_SUMMARIES[gap_id]
                )
            else:
                self.assertEqual(current_gap["summary"], base_gap["summary"])
        self.assertEqual(
            current_by_id["rights-blocked-source-lanes"]["summary"],
            base_by_id["rights-blocked-source-lanes"]["summary"],
        )
        all_refs = {
            artifact_id
            for gap in current["parity_gaps"]
            for artifact_id in gap["affected_artifact_ids"]
        }
        self.assertFalse(all_refs & REMOVED_ARTIFACT_IDS)
        self.assertIn(SATELLITE_ARTIFACT_ID, all_refs)
        self.assertIn(TIMELINE_ARTIFACT_ID, all_refs)

    def test_known_discovery_and_concurrent_change_lane_are_excluded(self) -> None:
        rendered = DEFINITION.read_text()
        ledger_rendered = (BUNDLE / "current-coverage-ledger.json").read_text()
        for artifact_id, spec in EXCLUDED_DISCOVERY_ARTIFACTS.items():
            self.assertNotIn(artifact_id, rendered)
            self.assertNotIn(artifact_id, ledger_rendered)
            path = ROOT / spec["path"]
            self.assertEqual(_checkpoint(path), (spec["bytes"], spec["sha256"]))
            self.assertEqual(json.loads(path.read_text())["artifact_id"], artifact_id)
        for marker in EXCLUDED_CONCURRENT_ARTIFACT_MARKERS:
            self.assertNotIn(marker, rendered)
            self.assertNotIn(marker, ledger_rendered)
        self.assertNotIn("delta-review", rendered)
        self.assertNotIn("change-analysis", rendered)

    def test_offline_double_replay_is_byte_exact(self) -> None:
        with _offline_guard():
            first = build_current_coverage_ledger_v21(DEFINITION)
            second = build_current_coverage_ledger_v21(DEFINITION)
            validated = validate_current_coverage_ledger_v21(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(validated, first.manifest)
        self.assertEqual(validated["ledger_id"], V21_LEDGER_ID)
        self.assertEqual(len(validated["input_checkpoints"]), 47)
        self.assertEqual(make_v21_definition(ROOT), DEFINITION.read_bytes())

    def test_collision_tamper_symlink_cli_and_import_carriers(self) -> None:
        module = _module()
        cached = build_current_coverage_ledger_v21(DEFINITION)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_path = Path(temporary)
            collision = temporary_path / "collision"
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_text("preserve\n")
            with (
                patch.object(
                    module, "build_current_coverage_ledger_v21", return_value=cached
                ),
                self.assertRaisesRegex(module.CurrentCoverageV21Error, "refusing"),
            ):
                write_current_coverage_ledger_v21(DEFINITION, collision)
            self.assertEqual(sentinel.read_text(), "preserve\n")

            tampered = temporary_path / "tampered"
            shutil.copytree(BUNDLE, tampered)
            tampered.chmod(0o755)
            target = tampered / "current-coverage-ledger.json"
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b"\n")
            for path in tampered.iterdir():
                path.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                module.CurrentCoverageV21Error, "not canonical"
            ):
                validate_current_coverage_ledger_v21(
                    tampered, definition_path=DEFINITION
                )

            symlink = temporary_path / "bundle-link"
            symlink.symlink_to(BUNDLE, target_is_directory=True)
            with self.assertRaisesRegex(
                module.CurrentCoverageV21Error, "regular directory"
            ):
                validate_current_coverage_ledger_v21(
                    symlink, definition_path=DEFINITION
                )

        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for cwd in (ROOT, PARENT):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import datacenter_atlas.current_coverage_v21 as m; "
                        "assert m.V21_LEDGER_ID == "
                        "'current-coverage-2026-07-21-v21'"
                    ),
                ],
                cwd=cwd,
                env=env,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        help_result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--validate-only", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
