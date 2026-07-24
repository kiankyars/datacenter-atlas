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

from datacenter_atlas.datacenter_atlas import current_coverage_v23 as core
from datacenter_atlas import current_coverage_v23 as shim


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v23.py"
FINAL_DEFINITION = ROOT / core.V23_DEFINITION_PATH
FINAL_BUNDLE = ROOT / core.V23_BUNDLE_PATH


def metrics(entry: dict) -> dict[str, object]:
    return {metric["label"]: metric["value"] for metric in entry["metrics"]}


class CurrentCoverageLedgerV23Tests(unittest.TestCase):
    def test_exact_47_to_50_delta_and_component_fuses(self) -> None:
        preview = core.preview_v23_delta(ROOT)
        self.assertEqual(preview["base_entries"], 47)
        self.assertEqual(preview["final_entries"], 50)
        self.assertEqual(preview["pending_replacement_ids"], [])
        self.assertEqual(preview["accepted_added_ids"], sorted(core.ADDED_ARTIFACT_IDS))
        self.assertEqual(
            preview["accepted_replacement_ids"],
            sorted(core.REPLACEMENT_ARTIFACT_IDS),
        )
        self.assertEqual(
            core.UNCHANGED_40_SHA256,
            "6178822f9c84a39cabef04a370b852b70db3bc25906202f4734ed0dbe14a19d1",
        )
        self.assertEqual(
            core.REMOVED_7_SHA256,
            "5e0ea4d1b2ecda8d0727e505b76ea2f5a63a750956ea9ccc05f6b1f52881882d",
        )
        self.assertEqual(
            core.REPLACEMENT_7_SHA256,
            "b8d432d15ea68eb42bb96dcfd74f775f8d4b8bbc0f898c2883d61c2665982636",
        )
        self.assertEqual(
            core.ADDED_3_SHA256,
            "ff85fe539125d339c76761fc3e7d40b9cc03158668563ba4799bef833b151d6f",
        )
        self.assertEqual(
            core.ALL_ENTRIES_SHA256,
            "d5aee68f2a2c773390b9084b779c4d4a4f365b07263adfff0aa4fe4757258696",
        )
        self.assertEqual(
            core.PARITY_GAPS_SHA256,
            "4924e50bc8bff0be416d3b0d04a3b906a0024e3e3b642678826ca6c2f08b3f69",
        )

        base_definition, _ = core._load_v22_base(ROOT)
        accepted = core._validate_accepted_inputs(ROOT)
        base = {entry["artifact_id"]: entry for entry in base_definition["entries"]}
        unchanged = [
            base[artifact_id]
            for artifact_id in sorted(set(base) - core.REMOVED_ARTIFACT_IDS)
        ]
        removed = [base[artifact_id] for artifact_id in sorted(core.REMOVED_ARTIFACT_IDS)]
        replacements = [
            accepted[artifact_id]
            for artifact_id in sorted(core.REPLACEMENT_ARTIFACT_IDS)
        ]
        additions = [
            accepted[artifact_id] for artifact_id in sorted(core.ADDED_ARTIFACT_IDS)
        ]
        self.assertEqual(
            (len(unchanged), len(removed), len(replacements), len(additions)),
            (40, 7, 7, 3),
        )
        self.assertEqual(core._component_digest(unchanged), core.UNCHANGED_40_SHA256)
        self.assertEqual(core._component_digest(removed), core.REMOVED_7_SHA256)
        self.assertEqual(core._component_digest(replacements), core.REPLACEMENT_7_SHA256)
        self.assertEqual(core._component_digest(additions), core.ADDED_3_SHA256)

    def test_replacements_and_three_review_contracts_bind_exact_metrics(self) -> None:
        accepted = core._validate_accepted_inputs(ROOT)
        self.assertEqual(set(accepted), core.NEW_ARTIFACT_IDS)

        seed = metrics(accepted["seed-epoch-official-v73"])
        self.assertEqual(seed["source_scoped_entity_rows"], 818)
        self.assertEqual(seed["lifecycle_freshness_records"], 462)
        self.assertFalse(seed["current_status_inferred"])
        timeline = metrics(accepted["construction-timeline-public-open-v6"])
        self.assertEqual(timeline["raw_lifecycle_observations"], 479)
        self.assertEqual(timeline["current_status_classification"], "unknown")
        self.assertFalse(timeline["current_construction_claimed"])
        federation = metrics(accepted["federation-public-open-v33"])
        self.assertEqual(federation["source_scoped_rows"], 16_243)
        self.assertEqual(federation["construction_pipeline_records"], 6_670)
        self.assertIsNone(federation["unique_physical_sites"])
        identity = metrics(accepted["exact-identity-decisions-public-open-v9"])
        self.assertEqual(identity["exact_source_record_components"], 8_381)
        self.assertEqual(identity["unresolved_candidate_references"], 100_539)
        self.assertIsNone(identity["physical_site_lower_bound"])
        self.assertIsNone(identity["physical_site_upper_bound"])
        master = metrics(accepted["construction-master-public-open-v29"])
        self.assertEqual(master["total_master_rows"], 109_332)
        self.assertEqual(master["status_under_construction_rows"], 412)
        self.assertIsNone(master["unique_physical_sites"])
        construction_map = metrics(accepted["construction-map-public-open-v29"])
        self.assertEqual(construction_map["mapped_total_rows"], 108_998)
        self.assertEqual(construction_map["unmapped_rows"], 334)
        self.assertIsNone(construction_map["unique_physical_sites"])
        coverage = metrics(accepted["coverage-audit-public-open-v29"])
        self.assertEqual(coverage["source_scoped_rows"], 16_243)
        self.assertEqual(coverage["open_gaps"], 4_103)
        self.assertIsNone(coverage["unique_physical_sites"])

        catalog = metrics(
            accepted["satellite-catalog-open-seed-v71-active-explicit-final-v1"]
        )
        self.assertEqual(catalog["jobs_represented"], 98)
        self.assertEqual(catalog["jobs_selected_for_execution"], 11)
        self.assertEqual(catalog["jobs_pending"], 87)
        self.assertFalse(catalog["change_analysis_executed"])
        queue = metrics(accepted["satellite-queue-open-seed-v71"])
        self.assertEqual(queue["queue_jobs"], 189)
        self.assertEqual(queue["active_construction_priority_jobs"], 98)
        self.assertEqual(queue["skipped_missing_coordinates"], 621)
        review = metrics(
            accepted[
                "satellite-change-review-open-seed-v71-active-explicit-11-review-v1"
            ]
        )
        self.assertEqual(review["analyst_decisions"], 11)
        self.assertEqual(review["promotion_retained_for_manual_followup"], 7)
        self.assertEqual(review["promotion_rejected"], 4)
        self.assertEqual(review["visible_change_clear"], 7)
        self.assertEqual(review["visible_change_ambiguous"], 4)
        self.assertEqual(review["source_artifacts_hash_bound"], 66)
        for label in (
            "atlas_mutation",
            "automated_promotion_allowed",
            "capacity_claim_created",
            "construction_status_claim_created",
            "current_status_claim_created",
            "data_centre_identity_claim_created",
            "data_centre_type_claim_created",
            "energy_claim_created",
            "power_claim_created",
            "site_count_claim_created",
            "unique_site_claim_created",
        ):
            self.assertFalse(review[label], label)

    def test_nonledger_decisions_are_explicit_and_nonadditive(self) -> None:
        self.assertEqual(
            {decision["reason"] for decision in core.NON_LEDGER_ARTIFACT_DECISIONS.values()},
            {
                "subsumed_nonadditive_seed_provenance",
                "technical_incident_has_no_schema_v4_contract_kind",
                "unreviewed_machine_change_has_no_schema_v4_contract_kind",
            },
        )
        raw = core.make_v23_definition(ROOT, generated_at=core.V23_GENERATED_AT)
        definition = json.loads(raw)
        artifact_ids = {entry["artifact_id"] for entry in definition["entries"]}
        self.assertTrue(
            artifact_ids.isdisjoint(core.NON_LEDGER_ARTIFACT_DECISIONS)
        )
        rendered = raw.decode("utf-8")
        for artifact_id in core.NON_LEDGER_ARTIFACT_DECISIONS:
            self.assertNotIn(artifact_id, rendered)
        self.assertEqual(core._sha256(raw), core.V23_DEFINITION_SHA256)

    def test_root_mode_transition_success_and_collision_rollback(self) -> None:
        def prepared(root: Path) -> core._PreparedV23Publication:
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
            return core._PreparedV23Publication(
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
            prefix="current-coverage-v23-mode-success-", dir="/private/tmp"
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
            prefix="current-coverage-v23-mode-rollback-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            staged = prepared(root)
            final_definition = root / "definition"
            final_bundle = root / "bundle"
            final_definition.write_bytes(b"external-arrival")
            with self.assertRaises(core.CurrentCoverageV23Error):
                core._promote_staged_pair(staged, final_definition, final_bundle)
            self.assertFalse(final_bundle.exists())
            self.assertEqual(final_definition.read_bytes(), b"external-arrival")
            self.assertEqual(stat.S_IMODE(staged.bundle_stage.stat().st_mode), 0o555)
            self.assertTrue(
                core._path_has_identity(
                    staged.bundle_stage, staged.bundle_identity, directory=True
                )
            )
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
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in FINAL_BUNDLE.iterdir())
        )
        raw = core.make_v23_definition(ROOT, generated_at=core.V23_GENERATED_AT)
        self.assertEqual(FINAL_DEFINITION.read_bytes(), raw)
        manifest = core.validate_current_coverage_ledger_v23(
            FINAL_BUNDLE, definition_path=FINAL_DEFINITION
        )
        self.assertEqual(manifest["ledger_id"], core.V23_LEDGER_ID)
        ledger = json.loads((FINAL_BUNDLE / core.LEDGER_FILENAME).read_text())
        inventory = ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 50)
        self.assertEqual(inventory["by_access_tier"], {"local_restricted": 6, "public_open": 44})
        self.assertEqual(inventory["by_evidence_scope"]["review_only"], 33)
        self.assertEqual(inventory["by_record_unit"]["catalog_job"], 9)
        self.assertEqual(inventory["by_record_unit"]["catalog_link"], 7)
        self.assertEqual(inventory["by_record_unit"]["review_record"], 17)
        self.assertEqual(inventory["by_record_unit"]["aggregate_report_metric"], 6)
        target = datetime.fromisoformat(core.V23_GENERATED_AT.replace("Z", "+00:00"))
        core._assert_final_root_ctimes((FINAL_DEFINITION, FINAL_BUNDLE), target)

        self.assertIs(core.preview_v23_delta, shim.preview_v23_delta)
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
            self.assertEqual(payload["ledger_id"], core.V23_LEDGER_ID)
            self.assertEqual(payload["generated_at"], core.V23_GENERATED_AT)

    def test_pins_and_tree_tampering_fail_closed(self) -> None:
        label = "satellite change review v71 manifest"
        original = core._ACCEPTED_FILES[label]
        tampered = (*original[:2], "0" * 64, original[3])
        with patch.dict(core._ACCEPTED_FILES, {label: tampered}):
            with self.assertRaisesRegex(core.CurrentCoverageV23Error, "pin or mode"):
                core._validate_accepted_inputs(ROOT)
        tree_label = "satellite change review v71"
        tree_path, _ = core._ACCEPTED_TREES[tree_label]
        with patch.dict(core._ACCEPTED_TREES, {tree_label: (tree_path, "0" * 64)}):
            with self.assertRaisesRegex(core.CurrentCoverageV23Error, "tree changed"):
                core._validate_accepted_inputs(ROOT)


if __name__ == "__main__":
    unittest.main()
