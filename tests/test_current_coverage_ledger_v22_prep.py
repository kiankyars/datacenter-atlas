from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.datacenter_atlas import current_coverage_v22 as core
from datacenter_atlas import current_coverage_v22 as shim


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v22.py"
FINAL_DEFINITION = ROOT / core.V22_DEFINITION_PATH
FINAL_BUNDLE = ROOT / core.V22_BUNDLE_PATH
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-21-v21.json"
BASE_LEDGER = (
    ROOT
    / "current_coverage_ledgers/2026-07-21-v21/current-coverage-ledger.json"
)


def entry_map(document: dict) -> dict[str, dict]:
    return {entry["artifact_id"]: entry for entry in document["entries"]}


def metrics(entry: dict) -> dict[str, object]:
    return {metric["label"]: metric["value"] for metric in entry["metrics"]}


class CurrentCoverageLedgerV22PrepTests(unittest.TestCase):
    def test_base_delta_and_pending_fuses_are_exact(self) -> None:
        preview = core.preview_v22_delta(ROOT)
        self.assertEqual(
            preview,
            {
                "accepted_replacement_ids": [
                    "construction-map-public-open-v28",
                    "construction-master-public-open-v28",
                    "construction-timeline-public-open-v5",
                    "coverage-audit-public-open-v28",
                    "exact-identity-decisions-public-open-v8",
                    "federation-public-open-v31",
                    "seed-epoch-official-v71",
                ],
                "base_entries": 47,
                "final_entries": 47,
                "parity_gaps_sha256": core.PARITY_GAPS_SHA256,
                "pending_replacement_ids": [],
                "removed_7_sha256": core.REMOVED_7_SHA256,
                "replacement_7_sha256": core.REPLACEMENT_7_SHA256,
                "unchanged_40_sha256": core.UNCHANGED_40_SHA256,
            },
        )
        self.assertEqual(
            core.ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v27": (
                    "construction-map-public-open-v28"
                ),
                "construction-master-public-open-v27": (
                    "construction-master-public-open-v28"
                ),
                "construction-timeline-public-open-v3": (
                    "construction-timeline-public-open-v5"
                ),
                "coverage-audit-public-open-v27": (
                    "coverage-audit-public-open-v28"
                ),
                "exact-identity-decisions-public-open-v6": (
                    "exact-identity-decisions-public-open-v8"
                ),
                "federation-public-open-v28": "federation-public-open-v31",
                "seed-epoch-official-v56": "seed-epoch-official-v71",
            },
        )
        self.assertEqual(
            core.REPLACEMENT_7_SHA256,
            "5e0ea4d1b2ecda8d0727e505b76ea2f5a63a750956ea9ccc05f6b1f52881882d",
        )
        self.assertEqual(
            core.ALL_ENTRIES_SHA256,
            "0e040c51333e9d3c01d9fc00d4071da0aa420ca0528a4176f28a1f8019cb8daa",
        )
        self.assertEqual(
            core.V22_DEFINITION_SHA256,
            "ee84ae4fd321ff4eb31e9d48359b18b8cb6d960d7ed4bf80a5d822e2386bd483",
        )
        self.assertEqual(core.pending_downstream_pins(), ())
        self.assertEqual(core.PENDING_DOWNSTREAM_PIN_BLUEPRINT, {})

    def test_seven_accepted_replacements_bind_to_exact_local_metrics(self) -> None:
        accepted = core._validate_accepted_inputs(ROOT)
        self.assertEqual(
            set(accepted),
            {
                "construction-map-public-open-v28",
                "construction-master-public-open-v28",
                "construction-timeline-public-open-v5",
                "coverage-audit-public-open-v28",
                "exact-identity-decisions-public-open-v8",
                "federation-public-open-v31",
                "seed-epoch-official-v71",
            },
        )
        construction_map = metrics(accepted["construction-map-public-open-v28"])
        self.assertEqual(construction_map["default_visible_rows"], 6_502)
        self.assertEqual(construction_map["mapped_replacement_rows"], 103)
        self.assertEqual(construction_map["mapped_tier_a_rows"], 222)
        self.assertEqual(construction_map["mapped_tier_b_rows"], 6_280)
        self.assertEqual(construction_map["mapped_tier_c_rows"], 102_494)
        self.assertEqual(construction_map["mapped_total_rows"], 108_996)
        self.assertEqual(construction_map["master_total_rows"], 109_328)
        self.assertEqual(construction_map["unmapped_rows"], 332)
        self.assertIsNone(construction_map["unique_physical_sites"])

        master = metrics(accepted["construction-master-public-open-v28"])
        self.assertEqual(master["replacement_rows"], 416)
        self.assertEqual(master["tier_a_rows"], 536)
        self.assertEqual(master["tier_b_rows"], 6_298)
        self.assertEqual(master["tier_c_rows"], 102_494)
        self.assertEqual(master["total_master_rows"], 109_328)
        self.assertEqual(master["status_under_construction_rows"], 408)
        self.assertIsNone(master["unique_physical_sites"])

        coverage = metrics(accepted["coverage-audit-public-open-v28"])
        self.assertEqual(coverage["coverage_groups"], 835)
        self.assertEqual(coverage["open_gaps"], 4_056)
        self.assertEqual(coverage["source_scoped_rows"], 16_235)
        self.assertIsNone(coverage["unique_physical_sites"])

        federation = metrics(accepted["federation-public-open-v31"])
        self.assertEqual(federation["source_scoped_rows"], 16_235)
        self.assertEqual(federation["construction_pipeline_records"], 6_666)
        self.assertEqual(
            federation["non_review_construction_pipeline_records"], 536
        )
        self.assertEqual(
            federation["review_only_construction_pipeline_records"], 6_130
        )
        self.assertIsNone(federation["unique_physical_sites"])

        identity = metrics(accepted["exact-identity-decisions-public-open-v8"])
        self.assertEqual(identity["exact_source_record_components"], 8_373)
        self.assertEqual(identity["canonical_topology_links"], 2_392)
        self.assertEqual(identity["raw_topology_links"], 2_797)
        self.assertEqual(identity["unresolved_candidate_references"], 100_538)
        self.assertIsNone(identity["physical_site_lower_bound"])
        self.assertIsNone(identity["physical_site_upper_bound"])
        self.assertIsNone(identity["unique_physical_sites"])

        timeline = metrics(accepted["construction-timeline-public-open-v5"])
        self.assertEqual(timeline["raw_lifecycle_observations"], 474)
        self.assertEqual(timeline["entities_with_lifecycle_observations"], 458)
        self.assertEqual(timeline["source_families"], 203)
        self.assertEqual(timeline["current_status_classification"], "unknown")
        self.assertFalse(timeline["current_construction_claimed"])
        self.assertFalse(timeline["stt_current_construction_claim"])

        seed = accepted["seed-epoch-official-v71"]
        seed_metrics = metrics(seed)
        self.assertEqual(seed_metrics["source_scoped_entity_rows"], 810)
        self.assertEqual(seed_metrics["campus_rows"], 427)
        self.assertEqual(seed_metrics["project_rows"], 383)
        self.assertEqual(seed_metrics["lifecycle_freshness_records"], 458)
        self.assertEqual(seed_metrics["lifecycle_status_semantics"], "last_observed")
        self.assertFalse(seed_metrics["current_status_inferred"])
        self.assertEqual(seed_metrics["publication_contract_version"], 4)
        self.assertEqual(
            seed["record_units"],
            [
                "capacity_observation",
                "construction_pipeline_record",
                "lifecycle_observation",
                "source_scoped_entity_row",
            ],
        )

    def test_schema_scope_inventory_and_parity_semantics_are_preserved(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text())
        base_ledger = json.loads(BASE_LEDGER.read_text())
        self.assertEqual(core.DEFINITION_SCHEMA_VERSION_V4, 4)
        self.assertEqual(core.LEDGER_SCHEMA_VERSION_V4, 4)
        self.assertEqual(core.SCOPE_POLICY, base_definition["scope"])
        inventory = deepcopy(base_ledger["artifact_inventory_counts"])
        inventory["by_record_unit"]["lifecycle_observation"] += 1
        self.assertEqual(inventory["artifacts"], 47)
        self.assertEqual(inventory["by_access_tier"], {"local_restricted": 6, "public_open": 41})
        self.assertEqual(inventory["by_evidence_scope"]["source_scoped"], 6)
        self.assertEqual(inventory["by_record_unit"]["lifecycle_observation"], 2)

        base_gaps = {gap["gap_id"]: gap for gap in base_definition["parity_gaps"]}
        gaps = {gap["gap_id"]: gap for gap in core.preview_parity_gaps(ROOT)}
        self.assertEqual(set(gaps), set(base_gaps))
        self.assertEqual(
            {gap["status"] for gap in gaps.values()},
            {gap["status"] for gap in base_gaps.values()},
        )
        for gap_id, gap in gaps.items():
            self.assertEqual(len(gap["affected_artifact_ids"]), len(set(gap["affected_artifact_ids"])))
            self.assertTrue(core.REMOVED_ARTIFACT_IDS.isdisjoint(gap["affected_artifact_ids"]))
            if gap_id not in core._UPDATED_GAP_SUMMARIES:
                self.assertEqual(gap["summary"], base_gaps[gap_id]["summary"])
        for gap_id in core._UPDATED_GAP_SUMMARIES:
            self.assertIn("458", gaps[gap_id]["summary"])
            self.assertNotIn("443", gaps[gap_id]["summary"])
        self.assertEqual(
            core._sha256(core._canonical_line(list(gaps.values()))),
            core.PARITY_GAPS_SHA256,
        )

    def test_frozen_final_paths_validate_and_unpaired_writes_stay_closed(self) -> None:
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertFalse(FINAL_DEFINITION.is_symlink())
        self.assertTrue(FINAL_BUNDLE.is_dir())
        self.assertFalse(FINAL_BUNDLE.is_symlink())
        self.assertEqual(stat.S_IMODE(FINAL_DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(FINAL_BUNDLE.stat().st_mode), 0o555)
        raw = core.make_v22_definition(
            ROOT, generated_at=core.V22_GENERATED_AT
        )
        self.assertEqual(core._sha256(raw), core.V22_DEFINITION_SHA256)
        self.assertEqual(FINAL_DEFINITION.read_bytes(), raw)
        self.assertEqual(
            core._tree_digest(FINAL_BUNDLE),
            "56652ef22510a9ec96cb3913db5c69d7a4e47898a2bd161ca5e2a85297554803",
        )
        manifest = core.validate_current_coverage_ledger_v22(
            FINAL_BUNDLE, definition_path=FINAL_DEFINITION
        )
        self.assertEqual(manifest["ledger_id"], core.V22_LEDGER_ID)
        with self.assertRaisesRegex(
            core.CurrentCoverageV22Error, "final definition must remain absent"
        ):
            core.preflight_v22_publication(ROOT)
        with self.assertRaisesRegex(core.CurrentCoverageV22Error, "must remain absent"):
            core.write_v22_definition(
                ROOT, FINAL_DEFINITION, generated_at=core.V22_GENERATED_AT
            )
        with self.assertRaisesRegex(core.CurrentCoverageV22Error, "must remain absent"):
            core.write_current_coverage_ledger_v22(
                FINAL_DEFINITION, FINAL_BUNDLE
            )
        target = datetime.fromisoformat(
            core.V22_GENERATED_AT.replace("Z", "+00:00")
        )
        core._assert_final_root_ctimes((FINAL_DEFINITION, FINAL_BUNDLE), target)

    def test_prepublication_future_early_exposure_symlink_and_digest_fuses(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        future = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        past = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v22-prepublication-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "staged-definition.json"
            future_document = {
                "generated_at": future,
                "ledger_id": core.V22_LEDGER_ID,
                "schema_version": core.DEFINITION_SCHEMA_VERSION_V4,
            }
            stage.write_bytes(core._canonical_json(future_document))
            final_definition = root / "final-definition.json"
            final_bundle = root / "final-bundle"
            bundle_stage = root / "staged-bundle"
            bundle_stage.mkdir()
            self.assertEqual(
                core.validate_private_staging_boundary(
                    stage,
                    bundle_stage,
                    final_definition,
                    final_bundle,
                    wall_clock=now,
                ),
                datetime.fromisoformat(future.replace("Z", "+00:00")),
            )
            final_definition.write_bytes(stage.read_bytes())
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error,
                "final v22 definition was exposed before generated_at",
            ):
                core.validate_prepublication_boundary(
                    stage, final_definition, final_bundle, wall_clock=now
                )
            final_definition.unlink()
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error, "generated_at is not yet live"
            ):
                core.validate_prepublication_boundary(
                    stage, final_definition, final_bundle, wall_clock=now
                )

            final_bundle.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error,
                "final v22 bundle was exposed before generated_at",
            ):
                core.validate_prepublication_boundary(
                    stage, final_definition, final_bundle, wall_clock=now
                )
            final_bundle.unlink()
            stage.write_bytes(
                core._canonical_json({**future_document, "generated_at": past})
            )
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error,
                "staged v22 definition digest changed",
            ):
                core.validate_prepublication_boundary(
                    stage, final_definition, final_bundle, wall_clock=now
                )
            linked_stage = root / "linked-stage.json"
            linked_stage.symlink_to(stage)
            with self.assertRaisesRegex(core.CurrentCoverageV22Error, "regular file"):
                core.validate_prepublication_boundary(
                    linked_stage, final_definition, final_bundle, wall_clock=now
                )
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error, "rename predates generated_at"
            ):
                core._assert_final_root_ctimes((stage, bundle_stage), datetime.fromisoformat(future.replace("Z", "+00:00")))
            core._assert_final_root_ctimes(
                (stage, bundle_stage), datetime.fromisoformat(past.replace("Z", "+00:00"))
            )

    def test_definition_is_frozen_and_second_promotion_collision_rolls_back(self) -> None:
        raw = core.make_v22_definition(ROOT, generated_at=core.V22_GENERATED_AT)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".v22-mode-test-", suffix=".json", dir=ROOT / "sources"
        )
        definition_stage = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(raw)
            definition_stage.chmod(0o444)
            core._validate_v22_definition(definition_stage, require_live=False)
            definition_stage.chmod(0o644)
            with self.assertRaisesRegex(
                core.CurrentCoverageV22Error, "frozen 0444"
            ):
                core._validate_v22_definition(definition_stage, require_live=False)
        finally:
            definition_stage.chmod(0o600)
            definition_stage.unlink()

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v22-pair-rollback-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
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
            prepared = core._PreparedV22Publication(
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
            final_definition = root / "definition"
            final_bundle = root / "bundle"
            final_definition.write_bytes(b"external-arrival")
            with self.assertRaises(core.CurrentCoverageV22Error):
                core._promote_staged_pair(
                    prepared, final_definition, final_bundle
                )
            self.assertEqual(final_definition.read_bytes(), b"external-arrival")
            self.assertFalse(final_bundle.exists())
            self.assertTrue(
                core._path_has_identity(
                    bundle_stage, prepared.bundle_identity, directory=True
                )
            )
            core._discard_bundle_stage(
                bundle_stage,
                prepared.bundle_identity,
                prepared.bundle_member_identities,
            )
            core._discard_file_stage(
                definition_stage, prepared.definition_identity
            )

    def test_pin_and_tree_tampering_are_rejected_without_writes(self) -> None:
        label = "coverage v28 manifest"
        original = core._ACCEPTED_FILES[label]
        tampered = (*original[:2], "0" * 64, original[3])
        with patch.dict(core._ACCEPTED_FILES, {label: tampered}):
            with self.assertRaisesRegex(core.CurrentCoverageV22Error, "pin or mode"):
                core._validate_accepted_inputs(ROOT)
        tree_label = "coverage v28"
        tree_path, _ = core._ACCEPTED_TREES[tree_label]
        with patch.dict(core._ACCEPTED_TREES, {tree_label: (tree_path, "0" * 64)}):
            with self.assertRaisesRegex(core.CurrentCoverageV22Error, "tree changed"):
                core._validate_accepted_inputs(ROOT)
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertTrue(FINAL_BUNDLE.is_dir())

    def test_alias_cli_and_both_working_directories_validate_frozen_final(self) -> None:
        self.assertIs(core.preview_v22_delta, shim.preview_v22_delta)
        self.assertIs(core.preflight_v22_publication, shim.preflight_v22_publication)
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
            self.assertEqual(payload["ledger_id"], core.V22_LEDGER_ID)
            self.assertEqual(payload["generated_at"], core.V22_GENERATED_AT)
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertTrue(FINAL_BUNDLE.is_dir())


if __name__ == "__main__":
    unittest.main()
