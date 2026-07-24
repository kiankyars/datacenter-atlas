from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.japan_moe_casebook import (
    CASEBOOK_URL,
    DOWNSTREAM_IMPORT_POLICY,
    JapanMOECasebookError,
    LANDING_URL,
    MAX_DIRECT_REQUEST_ATTEMPTS,
    MIN_REQUEST_START_INTERVAL_SECONDS,
    RELEASE_EXPECTED_FILES,
    RELEASE_ID,
    RIGHTS_POLICY,
    SOURCE_ARTIFACT_EXPECTED_FILES,
    SOURCE_ARTIFACT_MANIFEST_SHA256,
    SOURCE_ARTIFACT_TREE_SHA256,
    TERMS_URL,
    canonical_json,
    default_source_artifact_path,
    is_frozen_bundle,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    validate_retrieval_inventory,
    validate_source_artifact,
    validate_source_snapshot,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_SOURCE_ARTIFACT = default_source_artifact_path()
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_main = _load_script("build_japan_moe_casebook").main
validate_main = _load_script("validate_japan_moe_casebook").main
audit_module = _load_script("audit_japan_moe_casebook")


def _rehash_release(root: Path) -> None:
    payload_names = sorted(
        RELEASE_EXPECTED_FILES - {"manifest.json", "manifest.sha256"}
    )
    files = []
    for name in payload_names:
        body = (root / name).read_bytes()
        files.append(
            {
                "bytes": len(body),
                "path": name,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    manifest = {
        "files": files,
        "format": "datacenter-atlas-japan-moe-casebook-manifest-v1",
        "release_id": RELEASE_ID,
        "tree_sha256": hashlib.sha256(canonical_json(files)).hexdigest(),
    }
    manifest_body = canonical_json(manifest)
    (root / "manifest.json").write_bytes(manifest_body)
    (root / "manifest.sha256").write_text(
        f"{hashlib.sha256(manifest_body).hexdigest()}  manifest.json\n",
        encoding="ascii",
    )


class JapanMOECasebookTests(unittest.TestCase):
    def test_pinned_artifact_and_release_are_exact_and_frozen(self) -> None:
        source = validate_source_artifact(PINNED_SOURCE_ARTIFACT)
        bundle = validate_release_bundle(
            PINNED_RELEASE,
            definition_path=SOURCE_DEFINITION,
            source_artifact_path=PINNED_SOURCE_ARTIFACT,
        )
        self.assertTrue(
            is_frozen_bundle(PINNED_SOURCE_ARTIFACT, SOURCE_ARTIFACT_EXPECTED_FILES)
        )
        self.assertTrue(is_frozen_bundle(PINNED_RELEASE, RELEASE_EXPECTED_FILES))
        self.assertEqual(len(source["snapshot"]["overview_cases"]), 9)
        self.assertEqual(len(source["snapshot"]["detail_cases"]), 8)
        self.assertEqual(len(bundle["observations"]), 10)
        self.assertEqual(len(bundle["metrics"]), 24)
        self.assertEqual(len(bundle["programs"]), 6)

    def test_reconciliation_preserves_the_nine_vs_eight_discrepancy(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        reconciliation = bundle["reconciliation"]
        self.assertEqual(
            (
                reconciliation["overview_case_count"],
                reconciliation["detail_case_count"],
                reconciliation["matched_count"],
                reconciliation["overview_only_count"],
                reconciliation["detail_only_count"],
                reconciliation["normalized_case_observation_count"],
            ),
            (9, 8, 7, 2, 1, 10),
        )
        self.assertIsNone(reconciliation["physical_site_count"])
        by_relation = {}
        for row in bundle["observations"]:
            by_relation.setdefault(row["casebook_relation"], []).append(row)
        self.assertEqual(len(by_relation["overview_only"]), 2)
        self.assertEqual(len(by_relation["detail_only"]), 1)
        self.assertEqual(by_relation["detail_only"][0]["operator_ja"], "合同会社WM")
        self.assertEqual(by_relation["detail_only"][0]["municipality_ja"], "福岡県京都郡")
        self.assertEqual(
            {row["operator_ja"] for row in by_relation["overview_only"]},
            {"フロントエンド", "アオスフィールド"},
        )

    def test_metric_literals_and_scopes_are_not_silently_corrected(self) -> None:
        metrics = {
            row["metric_id"]: row
            for row in validate_release_bundle(PINNED_RELEASE)["metrics"]
        }
        self.assertEqual(metrics["metric-011"]["reported_value"], 1.1)
        self.assertEqual(metrics["metric-011"]["reported_unit"], "MWh/year")
        self.assertTrue(metrics["metric-011"]["source_internal_consistency_warning"])
        self.assertTrue(metrics["metric-012"]["source_internal_consistency_warning"])
        self.assertIsNone(metrics["metric-007"]["normalized_mwh_per_year"])
        self.assertIsNone(metrics["metric-008"]["normalized_mwh_per_year"])
        self.assertEqual(metrics["metric-007"]["reported_unit"], "MWh")
        self.assertEqual(metrics["metric-008"]["reported_unit"], "MWh")
        self.assertEqual(metrics["metric-005"]["actuality"], "forecast_fy2027")
        self.assertEqual(metrics["metric-005"]["temporal_scope"], "FY27_forecast")
        self.assertIn("shared by the logistics building", metrics["metric-021"]["scope"])
        self.assertEqual(
            metrics["metric-021"]["subsidy_scope"],
            "explicitly_outside_subsidy_self_funded",
        )
        self.assertTrue(metrics["metric-023"]["certificates_included"])

    def test_savings_generation_and_program_labels_do_not_become_site_metrics(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        for row in bundle["observations"]:
            for field in (
                "annual_energy_consumption_mwh",
                "data_centre_type",
                "it_load_mw",
                "physical_construction_status",
                "physical_operating_status",
                "physical_site_id",
                "power_capacity_mw",
                "pue",
            ):
                self.assertIsNone(row[field])
            self.assertFalse(row["program_category_is_physical_data_centre_type"])
            self.assertFalse(row["program_participation_is_lifecycle_evidence"])
        for metric in bundle["metrics"]:
            self.assertFalse(metric["is_energy_consumption_metric"])
            self.assertFalse(metric["is_it_or_power_capacity_metric"])
        boundary = bundle["assessment"]["metric_boundary"]
        self.assertFalse(boundary["energy_savings_are_energy_consumption"])
        self.assertFalse(boundary["generation_is_energy_consumption"])
        self.assertIsNone(boundary["annual_energy_consumption_mwh"])

    def test_program_years_are_budget_cohorts_not_lifecycle_dates(self) -> None:
        programs = validate_release_bundle(PINNED_RELEASE)["programs"]
        self.assertEqual(
            [(row["fiscal_year"], row["gregorian_fiscal_year"]) for row in programs],
            [("R7", 2025), ("R6", 2024), ("R5", 2023), ("R4", 2022), ("R3", 2021), ("R3", 2021)],
        )
        for row in programs:
            self.assertEqual(
                row["case_mapping_status"],
                "fiscal_year_only_not_program_item_specific",
            )
            self.assertIsNone(row["construction_lifecycle_implication"])
            self.assertIsNone(row["operating_lifecycle_implication"])

    def test_rights_policy_excludes_images_logo_raw_and_third_party_bodies(
        self,
    ) -> None:
        self.assertTrue(RIGHTS_POLICY["attribution_required"])
        self.assertTrue(RIGHTS_POLICY["editing_and_processor_disclosure_required"])
        self.assertTrue(RIGHTS_POLICY["pdl_1_0_default_applies_unless_otherwise_noted"])
        self.assertFalse(RIGHTS_POLICY["moe_logo_reuse_permitted_by_this_lane"])
        self.assertFalse(
            RIGHTS_POLICY[
                "source_images_or_diagrams_redistribution_permitted_by_this_lane"
            ]
        )
        self.assertFalse(
            RIGHTS_POLICY["third_party_body_redistribution_permitted_by_this_lane"]
        )
        self.assertFalse(RIGHTS_POLICY["third_party_rights_clearance_verified"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        names = {entry.name for entry in PINNED_SOURCE_ARTIFACT.iterdir()}
        self.assertFalse(names & {"casebook.pdf", "terms.html", "landing.html"})
        inventory = validate_release_bundle(PINNED_RELEASE)["source_inventory"]
        self.assertFalse(inventory["source_images_redistributed"])
        self.assertFalse(inventory["third_party_bodies_redistributed"])

    def test_direct_request_ledger_is_exact_paced_bounded_and_official_only(
        self,
    ) -> None:
        source = validate_source_artifact(PINNED_SOURCE_ARTIFACT)
        inventory = validate_retrieval_inventory(source["retrieval"])
        self.assertEqual(inventory["direct_request_attempts"], 3)
        self.assertEqual(inventory["direct_request_attempt_cap"], 12)
        self.assertEqual(MAX_DIRECT_REQUEST_ATTEMPTS, 12)
        self.assertEqual(MIN_REQUEST_START_INTERVAL_SECONDS, 3.2)
        self.assertEqual(inventory["third_party_requests"], 0)
        self.assertEqual(
            [row["url"] for row in inventory["controlled_http_requests"]],
            [TERMS_URL, LANDING_URL, CASEBOOK_URL],
        )
        self.assertEqual(
            [row["sha256"] for row in inventory["controlled_http_requests"]],
            [
                "7e1d986aa7381e0134edbb9e16aa346ee103274230fb9d6b2a0bc6f3caae6686",
                "f70014890897752702ca366ccc52dfd77a458301b28f060b8a29f0ebc8f402e0",
                "8be7d6b16cdb6adaedf65906b4e5e4709154302496522f728a567169b7f35d0d",
            ],
        )
        self.assertIsNone(inventory["browser_proxy_origin_request_count"])
        self.assertTrue(
            inventory[
                "browser_proxy_research_excluded_from_direct_request_arithmetic"
            ]
        )

    def test_source_artifact_hash_pins_are_exact(self) -> None:
        bundle = validate_source_artifact(PINNED_SOURCE_ARTIFACT)
        self.assertEqual(
            (PINNED_SOURCE_ARTIFACT / "manifest.sha256")
            .read_text(encoding="ascii")
            .split()[0],
            SOURCE_ARTIFACT_MANIFEST_SHA256,
        )
        self.assertEqual(bundle["manifest"]["tree_sha256"], SOURCE_ARTIFACT_TREE_SHA256)
        definition = source_definition()
        self.assertEqual(
            definition["build_contract"]["source_artifact_manifest_sha256"],
            SOURCE_ARTIFACT_MANIFEST_SHA256,
        )

    def test_rebuild_is_byte_deterministic_and_uses_zero_network_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            definition = Path(temporary) / "definition.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = build_main(
                    [
                        "--source-artifact", str(PINNED_SOURCE_ARTIFACT),
                        "--output", str(output),
                        "--definition", str(definition),
                    ]
                )
            self.assertEqual(result, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["build_network_requests"], 0)
            self.assertEqual(
                report["build_mode"],
                "offline_from_frozen_structured_source_artifact",
            )
            for name in RELEASE_EXPECTED_FILES:
                self.assertEqual(
                    (output / name).read_bytes(),
                    (PINNED_RELEASE / name).read_bytes(),
                )
            self.assertEqual(definition.read_bytes(), SOURCE_DEFINITION.read_bytes())
            thaw_for_test(output)

    def test_manifest_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, release)
            thaw_for_test(release)
            (release / "metrics.jsonl").write_bytes(
                (release / "metrics.jsonl").read_bytes() + b" "
            )
            with self.assertRaisesRegex(JapanMOECasebookError, "manifest"):
                validate_release_bundle(release, require_frozen=False)

    def test_semantic_metric_tamper_is_rejected_even_as_writable_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, release)
            thaw_for_test(release)
            first = json.loads(
                (release / "observations.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            first["annual_energy_consumption_mwh"] = 1000.0
            lines = (release / "observations.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            lines[0] = json.dumps(
                first,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            (release / "observations.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            _rehash_release(release)
            with self.assertRaisesRegex(JapanMOECasebookError, "must remain null"):
                validate_release_bundle(release, require_frozen=False)

    def test_frozen_mode_rejects_writable_copy_and_explicit_draft_mode_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, release)
            thaw_for_test(release)
            with self.assertRaisesRegex(JapanMOECasebookError, "not frozen"):
                validate_release_bundle(release)
            bundle = validate_release_bundle(
                release,
                source_artifact_path=PINNED_SOURCE_ARTIFACT,
                require_frozen=False,
            )
            self.assertEqual(len(bundle["observations"]), 10)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = validate_main(
                    [
                        "--release", str(release),
                        "--definition", str(SOURCE_DEFINITION),
                        "--source-artifact", str(PINNED_SOURCE_ARTIFACT),
                        "--allow-writable-release",
                    ]
                )
            self.assertEqual(result, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["validation_mode"], "offline_writable_release_allowed")
            self.assertEqual(report["validation_network_requests"], 0)

    def test_source_snapshot_exact_schema_rejects_extra_fields(self) -> None:
        source = validate_source_artifact(PINNED_SOURCE_ARTIFACT)
        snapshot = deepcopy(source["snapshot"])
        snapshot["unexpected"] = True
        with self.assertRaisesRegex(JapanMOECasebookError, "keys differ"):
            validate_source_snapshot(snapshot, source["retrieval"])

    def test_audit_cli_is_terms_first_allowlisted_and_capped(self) -> None:
        self.assertEqual(audit_module.MAX_DIRECT_REQUEST_ATTEMPTS, 12)
        self.assertEqual(audit_module.MIN_REQUEST_START_INTERVAL_SECONDS, 3.2)
        self.assertEqual(
            [row[1] for row in audit_module.REQUESTS],
            [TERMS_URL, LANDING_URL, CASEBOOK_URL],
        )
        with self.assertRaises(ValueError):
            audit_module._assert_allowed("https://example.com/third-party")

    def test_downstream_imports_remain_fail_closed(self) -> None:
        for key in (
            "construction_map_import_permitted",
            "construction_master_import_permitted",
            "current_coverage_ledger_import_permitted",
        ):
            self.assertFalse(DOWNSTREAM_IMPORT_POLICY[key])


if __name__ == "__main__":
    unittest.main()
