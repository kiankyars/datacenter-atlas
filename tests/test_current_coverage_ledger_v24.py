from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.datacenter_atlas import current_coverage_v24 as core
from datacenter_atlas import current_coverage_v24 as shim


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v24.py"
FINAL_DEFINITION = ROOT / core.V24_DEFINITION_PATH
FINAL_BUNDLE = ROOT / core.V24_BUNDLE_PATH


def metrics(entry: dict) -> dict[str, object]:
    return {metric["label"]: metric["value"] for metric in entry["metrics"]}


class CurrentCoverageLedgerV24Tests(unittest.TestCase):
    def test_exact_v23_successor_delta_and_component_fuses(self) -> None:
        preview = core.preview_v24_delta(ROOT)
        self.assertEqual(preview["base_entries"], 50)
        self.assertEqual(
            preview["final_entries"], 50 + len(core.ADDED_ARTIFACT_IDS)
        )
        self.assertEqual(preview["pending_replacement_ids"], [])
        self.assertEqual(
            preview["accepted_added_ids"], sorted(core.ADDED_ARTIFACT_IDS)
        )
        self.assertEqual(
            preview["accepted_replacement_ids"],
            sorted(core.REPLACEMENT_ARTIFACT_IDS),
        )
        self.assertEqual(
            preview["historical_retained_ids"],
            sorted(core.HISTORICAL_ARTIFACT_IDS),
        )

        base_definition, _ = core._load_v23_base(ROOT)
        accepted = core._validate_accepted_inputs(ROOT)
        base = {entry["artifact_id"]: entry for entry in base_definition["entries"]}
        unchanged = [
            base[artifact_id]
            for artifact_id in sorted(
                set(base)
                - core.REMOVED_ARTIFACT_IDS
                - core.HISTORICAL_ARTIFACT_IDS
            )
        ]
        removed = [
            base[artifact_id]
            for artifact_id in sorted(core.REMOVED_ARTIFACT_IDS)
        ]
        historical = list(core._historical_entries(base).values())
        replacements = [
            accepted[artifact_id]
            for artifact_id in sorted(core.REPLACEMENT_ARTIFACT_IDS)
        ]
        additions = [
            accepted[artifact_id]
            for artifact_id in sorted(core.ADDED_ARTIFACT_IDS)
        ]
        self.assertEqual(
            (
                len(unchanged),
                len(removed),
                len(historical),
                len(replacements),
                len(additions),
            ),
            (40, 8, 2, 8, len(core.ADDED_ARTIFACT_IDS)),
        )
        self.assertEqual(
            core._component_digest(unchanged), core.UNCHANGED_40_SHA256
        )
        self.assertEqual(core._component_digest(removed), core.REMOVED_8_SHA256)
        self.assertEqual(
            core._component_digest(historical), core.HISTORICAL_2_SHA256
        )
        self.assertEqual(
            core._component_digest(replacements), core.REPLACEMENT_8_SHA256
        )
        self.assertEqual(
            core._component_digest(additions), core.ADDED_ARTIFACTS_SHA256
        )

    def test_public_chain_metrics_queue_and_historical_reviews(self) -> None:
        accepted = core._validate_accepted_inputs(ROOT)
        self.assertEqual(set(accepted), core.NEW_ARTIFACT_IDS)

        seed = metrics(accepted["seed-epoch-official-v83"])
        self.assertEqual(seed["source_scoped_entity_rows"], 905)
        self.assertEqual(seed["lifecycle_freshness_records"], 506)
        self.assertFalse(seed["current_status_inferred"])
        timeline = metrics(accepted["construction-timeline-public-open-v7"])
        self.assertEqual(timeline["raw_lifecycle_observations"], 526)
        self.assertEqual(timeline["current_status_classification"], "unknown")
        self.assertFalse(timeline["current_construction_claimed"])
        federation = metrics(accepted["federation-public-open-v34"])
        self.assertEqual(federation["source_scoped_rows"], 16_330)
        self.assertEqual(federation["construction_pipeline_records"], 6_712)
        self.assertIsNone(federation["unique_physical_sites"])
        identity = metrics(accepted["exact-identity-decisions-public-open-v10"])
        self.assertEqual(identity["exact_source_record_components"], 8_468)
        self.assertEqual(identity["unresolved_candidate_references"], 100_539)
        self.assertIsNone(identity["physical_site_lower_bound"])
        self.assertIsNone(identity["physical_site_upper_bound"])
        master = metrics(accepted["construction-master-public-open-v30"])
        self.assertEqual(master["total_master_rows"], 109_374)
        self.assertEqual(master["status_under_construction_rows"], 449)
        self.assertIsNone(master["unique_physical_sites"])
        construction_map = metrics(accepted["construction-map-public-open-v30"])
        self.assertEqual(construction_map["mapped_total_rows"], 109_002)
        self.assertEqual(construction_map["unmapped_rows"], 372)
        self.assertIsNone(construction_map["unique_physical_sites"])
        coverage = metrics(accepted["coverage-audit-public-open-v30"])
        self.assertEqual(coverage["source_scoped_rows"], 16_330)
        self.assertEqual(coverage["open_gaps"], 4_469)
        self.assertIsNone(coverage["unique_physical_sites"])
        queue = metrics(accepted["satellite-queue-open-seed-v83"])
        self.assertEqual(queue["queue_jobs"], 200)
        self.assertEqual(queue["active_construction_priority_jobs"], 104)
        self.assertEqual(queue["skipped_missing_coordinates"], 705)
        self.assertFalse(queue["network_requests_performed"])
        catalog = metrics(
            accepted[
                "satellite-catalog-open-seed-v83-active-explicit-"
                "new-projects-final-v1"
            ]
        )
        self.assertEqual(catalog["jobs_represented"], 104)
        self.assertEqual(catalog["jobs_selected_for_execution"], 4)
        self.assertEqual(catalog["jobs_completed"], 3)
        self.assertEqual(catalog["jobs_unavailable_no_scene"], 1)
        self.assertEqual(catalog["jobs_pending"], 100)
        self.assertFalse(catalog["atlas_mutation"])
        self.assertFalse(catalog["change_analysis_executed"])
        review = metrics(
            accepted[
                "satellite-change-review-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2"
            ]
        )
        self.assertEqual(review["analyst_decisions"], 3)
        self.assertEqual(review["promotion_uncertain_for_manual_followup"], 1)
        self.assertEqual(review["promotion_rejected"], 2)
        self.assertEqual(review["promotion_retained_for_manual_followup"], 0)
        self.assertEqual(review["machine_run_jobs_completed_once"], 3)
        self.assertEqual(review["machine_run_failures"], 0)
        self.assertFalse(review["atlas_mutation"])
        self.assertFalse(review["construction_status_claim_created"])
        self.assertFalse(review["unique_site_claim_created"])

        base_definition, _ = core._load_v23_base(ROOT)
        base = {entry["artifact_id"]: entry for entry in base_definition["entries"]}
        historical = core._historical_entries(base)
        self.assertEqual(set(historical), core.HISTORICAL_ARTIFACT_IDS)
        for artifact_id, entry in historical.items():
            self.assertEqual(
                entry["current_role"], "public_supporting_review_lane"
            )
            rendered = json.dumps(entry, sort_keys=True)
            self.assertIn("historical", rendered)
            self.assertIn("seed-v83 satellite coverage", rendered)
            self.assertIn("open-seed-v71", rendered, artifact_id)

    def test_nonledger_lineage_is_complete_and_nonadditive(self) -> None:
        decisions = core.NON_LEDGER_ARTIFACT_DECISIONS
        expected_wrappers = {
            "site-coordinate-assessment-2026-07-21-v5",
            "global-official-builds-next-tranche-2026-07-21-v1",
            "global-official-builds-regional-gap-2026-07-21-v1",
            "global-official-builds-china-gap-2026-07-21-v1",
            "global-official-builds-asia-gap-2026-07-21-v1",
            "global-official-builds-latam-caribbean-gap-2026-07-21-v1",
            "global-official-builds-africa-gap-2026-07-21-v1",
            "global-official-builds-middle-east-turkiye-gap-2026-07-21-v1",
            "global-official-builds-cee-gap-2026-07-21-v1",
            "global-official-builds-oceania-gap-2026-07-21-v1",
        }
        self.assertTrue(expected_wrappers <= decisions.keys())
        for artifact_id in expected_wrappers:
            self.assertEqual(
                decisions[artifact_id]["reason"],
                "subsumed_nonadditive_seed_provenance",
            )
        for version in range(74, 83):
            self.assertEqual(
                decisions[f"seed-epoch-official-v{version}"]["reason"],
                "superseded_nonadditive_seed_lineage",
            )
        self.assertEqual(
            decisions["satellite-queue-open-seed-v73"]["reason"],
            "superseded_noncurrent_queue_lineage",
        )
        self.assertEqual(
            decisions[
                "global-official-builds-canada-mexico-caribbean-gap-"
                "2026-07-21-v1"
            ]["reason"],
            "pending_seed_integration",
        )
        self.assertEqual(
            decisions[
                "satellite-change-open-seed-v83-active-explicit-"
                "new-projects-final-v1"
            ]["reason"],
            "unreviewed_machine_change_has_no_schema_v4_contract_kind",
        )
        self.assertEqual(
            decisions[
                "satellite-change-v83-post-run-order-assertion-incident-v1"
            ]["reason"],
            "technical_incident_has_no_schema_v4_contract_kind",
        )
        self.assertEqual(
            decisions[
                "satellite-review-v83-premature-publication-control-incident-v1"
            ]["reason"],
            "technical_incident_has_no_schema_v4_contract_kind",
        )

        raw = core.make_v24_definition(ROOT, generated_at=core.V24_GENERATED_AT)
        definition = json.loads(raw)
        artifact_ids = {entry["artifact_id"] for entry in definition["entries"]}
        self.assertTrue(artifact_ids.isdisjoint(decisions))
        self.assertEqual(core._sha256(raw), core.V24_DEFINITION_SHA256)

    def test_scope_and_parity_claims_remain_false(self) -> None:
        raw = core.make_v24_definition(ROOT, generated_at=core.V24_GENERATED_AT)
        definition = json.loads(raw)
        scope = definition["scope"]
        self.assertFalse(scope["benchmark_parity_claimed"])
        self.assertFalse(scope["global_completeness_claimed"])
        self.assertFalse(scope["source_scoped_rows_are_unique_physical_sites"])
        self.assertIsNone(scope["unique_physical_site_count"])
        gaps = {gap["gap_id"]: gap for gap in definition["parity_gaps"]}
        self.assertEqual(gaps["benchmark-parity-not-computed"]["status"], "not_computed")
        self.assertIn(
            "No licensed, row-level external benchmark denominator",
            gaps["benchmark-parity-not-computed"]["summary"],
        )
        self.assertIn("historical", gaps["satellite-review-backlog"]["summary"])

    def test_root_mode_transition_success_and_collision_rollback(self) -> None:
        def prepared(root: Path) -> core._PreparedV24Publication:
            bundle_stage = root / ".bundle-stage"
            bundle_stage.mkdir()
            for filename in core.BUNDLE_FILES:
                path = bundle_stage / filename
                path.write_bytes(filename.encode("ascii"))
                path.chmod(0o444)
            bundle_stage.chmod(0o555)
            definition_stage = root / ".definition-stage"
            definition_stage.write_bytes(b"owned-definition")
            definition_stage.chmod(0o444)
            return core._PreparedV24Publication(
                bundle_identity=core._path_identity(bundle_stage, directory=True),
                bundle_member_identities={
                    path.name: core._path_identity(path, directory=False)
                    for path in bundle_stage.iterdir()
                },
                bundle_stage=bundle_stage,
                bundle_tree_sha256=core._tree_digest(bundle_stage),
                definition_identity=core._path_identity(
                    definition_stage, directory=False
                ),
                definition_raw=b"owned-definition",
                definition_stage=definition_stage,
                generated_at=datetime.now(timezone.utc),
            )

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v24-mode-success-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            staged = prepared(root)
            final_definition = root / "definition"
            final_bundle = root / "bundle"
            observed_modes: list[int] = []
            original = core._v22._v21._promote_noreplace

            def checking(source: Path, destination: Path) -> None:
                if source == staged.bundle_stage:
                    observed_modes.append(stat.S_IMODE(source.stat().st_mode))
                original(source, destination)

            with patch.object(core._v22._v21, "_promote_noreplace", checking):
                core._promote_staged_pair(staged, final_definition, final_bundle)
            self.assertEqual(observed_modes, [0o755])
            self.assertEqual(stat.S_IMODE(final_bundle.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(final_definition.stat().st_mode), 0o444)
            final_bundle.chmod(0o755)

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v24-mode-rollback-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            staged = prepared(root)
            final_definition = root / "definition"
            final_bundle = root / "bundle"
            final_definition.write_bytes(b"external-arrival")
            with self.assertRaises(core.CurrentCoverageV24Error):
                core._promote_staged_pair(staged, final_definition, final_bundle)
            self.assertFalse(final_bundle.exists())
            self.assertEqual(final_definition.read_bytes(), b"external-arrival")
            self.assertEqual(stat.S_IMODE(staged.bundle_stage.stat().st_mode), 0o555)
            core._discard_bundle_stage(
                staged.bundle_stage,
                staged.bundle_identity,
                staged.bundle_member_identities,
            )
            core._discard_file_stage(
                staged.definition_stage, staged.definition_identity
            )

    def test_frozen_final_inventory_modes_ctimes_and_cli(self) -> None:
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertFalse(FINAL_DEFINITION.is_symlink())
        self.assertTrue(FINAL_BUNDLE.is_dir())
        self.assertFalse(FINAL_BUNDLE.is_symlink())
        self.assertEqual(stat.S_IMODE(FINAL_DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(FINAL_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in FINAL_BUNDLE.iterdir()
            )
        )
        raw = core.make_v24_definition(ROOT, generated_at=core.V24_GENERATED_AT)
        self.assertEqual(FINAL_DEFINITION.read_bytes(), raw)
        manifest = core.validate_current_coverage_ledger_v24(
            FINAL_BUNDLE, definition_path=FINAL_DEFINITION
        )
        self.assertEqual(manifest["ledger_id"], core.V24_LEDGER_ID)
        ledger = json.loads((FINAL_BUNDLE / core.LEDGER_FILENAME).read_text())
        self.assertEqual(
            ledger["artifact_inventory_counts"]["artifacts"],
            50 + len(core.ADDED_ARTIFACT_IDS),
        )
        target = datetime.fromisoformat(core.V24_GENERATED_AT.replace("Z", "+00:00"))
        core._assert_final_root_ctimes((FINAL_DEFINITION, FINAL_BUNDLE), target)

        self.assertIs(core.preview_v24_delta, shim.preview_v24_delta)
        for working_directory in (ROOT, PARENT):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--validate-only"],
                cwd=working_directory,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["ledger_id"], core.V24_LEDGER_ID)
            self.assertEqual(payload["generated_at"], core.V24_GENERATED_AT)

    def test_pins_and_tree_tampering_fail_closed(self) -> None:
        label = "satellite queue v83 manifest"
        original = core._ACCEPTED_FILES[label]
        tampered = (*original[:2], "0" * 64, original[3])
        with patch.dict(core._ACCEPTED_FILES, {label: tampered}):
            with self.assertRaisesRegex(core.CurrentCoverageV24Error, "pin or mode"):
                core._validate_accepted_inputs(ROOT)
        tree_label = "satellite queue v83"
        tree_path, _ = core._ACCEPTED_TREES[tree_label]
        with patch.dict(
            core._ACCEPTED_TREES, {tree_label: (tree_path, "0" * 64)}
        ):
            with self.assertRaisesRegex(core.CurrentCoverageV24Error, "tree changed"):
                core._validate_accepted_inputs(ROOT)


if __name__ == "__main__":
    unittest.main()
