from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.south_korea_eiass_nier import (
    AUDIT_REQUEST_START_INTERVAL_SECONDS,
    CONDITIONAL_ENGLISH_TERMS,
    DOWNSTREAM_IMPORT_POLICY,
    EIA_LIST_PATH,
    EXPECTED_FILES,
    MAX_DIRECT_REQUEST_ATTEMPTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PINNED_RETRIEVAL_INVENTORY,
    PRE_STRATEGY_SMALL_LIST_PATH,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_TERMS,
    SouthKoreaEIASSNIERAssessmentError,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    query_plan,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    validate_retrieval_inventory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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


validate_main = _load_script("validate_south_korea_eiass_nier").main
build_main = _load_script("build_south_korea_eiass_nier").main
audit_module = _load_script("audit_south_korea_eiass_nier")


def _refreeze(root: Path) -> None:
    for entry in root.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


class SouthKoreaEIASSNIERAssessmentTests(unittest.TestCase):
    def test_pinned_release_is_zero_row_and_fail_closed(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE,
            definition_path=SOURCE_DEFINITION,
        )
        assessment = bundle["assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "credential_and_reproducibility_gates_blocked_metadata_only",
        )
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)
        self.assertFalse(assessment["coverage"]["complete_for_south_korea"])
        for field in (
            "environmental_assessment_record_count",
            "project_count",
            "result_count",
            "site_count",
        ):
            self.assertIsNone(assessment["coverage"][field])
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")

    def test_current_machine_readable_endpoints_and_access_are_exact(self) -> None:
        definition = source_definition()
        endpoints = definition["endpoint_contracts"]
        shared = endpoints["shared_semantics"]
        self.assertTrue(shared["machine_readable_project_list_endpoints_found"])
        self.assertTrue(shared["service_key_required"])
        self.assertFalse(shared["anonymous_invocation_documented"])
        self.assertTrue(shared["pagination_fields_documented"])
        access = definition["access"]
        self.assertTrue(access["data_go_free"])
        self.assertEqual(access["development_review"], "automatic_approval")
        self.assertEqual(access["operation_review"], "automatic_approval")
        self.assertEqual(access["data_go_development_traffic_value"], 10000)
        self.assertIsNone(access["data_go_development_traffic_period"])
        self.assertFalse(access["api_invocation_performed"])

        eia = endpoints["environmental_impact_assessment_discussion_list"]
        self.assertEqual(eia["operation_path"], EIA_LIST_PATH)
        self.assertEqual(eia["required_query_parameters"], ["serviceKey", "pageNo"])
        self.assertIn("searchText", eia["optional_query_parameters"])
        small = endpoints["pre_strategy_small_scale_discussion_list"]
        self.assertEqual(small["operation_path"], PRE_STRATEGY_SMALL_LIST_PATH)
        self.assertEqual(
            small["required_query_parameters"],
            ["serviceKey", "pageNo", "numOfRows"],
        )

    def test_rights_and_type_one_semantics_are_scoped_to_api_resources(self) -> None:
        self.assertTrue(RIGHTS_POLICY["api_metadata_affirms_attribution_reuse_scope"])
        self.assertTrue(RIGHTS_POLICY["api_metadata_marks_third_party_rights_included"])
        self.assertTrue(RIGHTS_POLICY["data_go_policy_type_one_requires_attribution"])
        self.assertTrue(
            RIGHTS_POLICY[
                "data_go_policy_type_one_allows_commercial_and_noncommercial_use"
            ]
        )
        self.assertTrue(RIGHTS_POLICY["data_go_policy_type_one_allows_derivative_works"])
        self.assertTrue(
            RIGHTS_POLICY["eiass_official_rights_pages_observed_via_browser_proxy"]
        )
        self.assertTrue(RIGHTS_POLICY["eiass_footer_all_rights_reserved"])
        self.assertTrue(
            RIGHTS_POLICY["eiass_unmarked_material_requires_prior_consultation"]
        )
        self.assertFalse(RIGHTS_POLICY["eiass_direct_rights_page_request_made"])
        self.assertFalse(RIGHTS_POLICY["eiass_web_result_reuse_scope_affirmed"])
        self.assertFalse(RIGHTS_POLICY["robots_rule_is_reuse_permission"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])

    def test_pagination_and_search_semantics_do_not_overclaim(self) -> None:
        contracts = source_definition()["endpoint_contracts"]
        for name in (
            "environmental_impact_assessment_discussion_list",
            "pre_strategy_small_scale_discussion_list",
        ):
            endpoint = contracts[name]
            self.assertEqual(
                endpoint["response_pagination_fields"],
                ["numOfRows", "pageNo", "totalCount"],
            )
            self.assertFalse(endpoint["page_number_base_documented"])
            self.assertFalse(endpoint["page_size_default_documented"])
            self.assertFalse(endpoint["page_size_maximum_documented"])
            self.assertIsNone(endpoint["page_size_default"])
            self.assertIsNone(endpoint["page_size_maximum"])
        shared = contracts["shared_semantics"]
        self.assertFalse(shared["exact_phrase_matching_documented"])
        self.assertFalse(shared["substring_matching_documented"])
        self.assertFalse(shared["stable_sort_documented"])
        self.assertFalse(shared["snapshot_or_as_of_semantics_documented"])

    def test_korean_literals_and_conditional_english_stay_unsubmitted(self) -> None:
        self.assertEqual(SEARCH_TERMS, ("데이터센터", "데이터 센터"))
        self.assertEqual(CONDITIONAL_ENGLISH_TERMS, ("data center", "data centre"))
        plan = query_plan()
        self.assertFalse(plan["english_terms_enabled"])
        self.assertEqual(plan["source_queries_submitted"], 0)
        self.assertFalse(plan["search_capture_started"])
        self.assertEqual(
            [row["term"] for row in plan["rows"]],
            list(SEARCH_TERMS + CONDITIONAL_ENGLISH_TERMS),
        )
        for row in plan["rows"]:
            self.assertEqual(row["network_requests"], 0)
            self.assertEqual(row["pages_retrieved"], 0)
            self.assertIsNone(row["result_count"])
            self.assertFalse(row["source_exact_phrase_semantics_documented"])
            self.assertFalse(row["exact_literal_local_postfilter_completed"])
        self.assertTrue(
            all(
                row["status"] == "not_enabled_gates_failed"
                for row in plan["rows"]
                if row["term_language"] == "en"
            )
        )

    def test_migration_notice_is_precise_and_attachment_not_claimed(self) -> None:
        migration = source_definition()["migration_notice"]
        self.assertEqual(migration["notice_date"], "2025-05-07")
        self.assertEqual(migration["old_kei_api_count"], 22)
        self.assertTrue(migration["old_kei_services_discontinued"])
        self.assertEqual(migration["reason"], "EIASS transferred from KEI to NIER")
        self.assertEqual(
            migration["replacement_description"],
            "identical NIER OpenAPI services",
        )
        self.assertTrue(migration["attachment_labelled_recovering"])
        self.assertFalse(migration["attachment_requested"])
        self.assertFalse(migration["replacement_mapping_attachment_contents_verified"])

    def test_direct_request_ledger_is_exact_paced_and_under_cap(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        inventory = PINNED_RETRIEVAL_INVENTORY
        self.assertEqual(inventory["direct_request_attempts"], 10)
        self.assertEqual(inventory["direct_request_attempt_cap"], 40)
        self.assertEqual(MAX_DIRECT_REQUEST_ATTEMPTS, 40)
        self.assertEqual(AUDIT_REQUEST_START_INTERVAL_SECONDS, 3.2)
        self.assertEqual(MIN_REQUEST_INTERVAL_SECONDS, 3.0)
        self.assertEqual(inventory["completed_response_requests"], 7)
        self.assertEqual(inventory["failed_network_requests"], 3)
        self.assertEqual(inventory["successful_http_200_requests"], 6)
        self.assertEqual(inventory["http_error_responses"], 1)
        self.assertEqual(inventory["result_bearing_api_requests"], 0)
        self.assertEqual(inventory["result_bearing_search_requests"], 0)
        self.assertEqual(inventory["source_attachment_requests"], 0)
        self.assertFalse(inventory["search_capture_started"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])
        self.assertEqual(
            [row["http_status"] for row in inventory["controlled_http_requests"]],
            [200, None, None, 200, 200, 200, 200, 500, None, 200],
        )

    def test_robots_outcomes_are_fail_closed_not_rights_claims(self) -> None:
        access = source_definition()["access"]
        self.assertEqual(access["api_host_robots_http_status"], 500)
        self.assertFalse(access["api_host_robots_policy_obtained"])
        self.assertEqual(access["www_eiass_robots_outcome"], "network_error")
        self.assertEqual(
            access["canonical_eiass_robots_outcome"], "tls_handshake_failure"
        )
        self.assertFalse(RIGHTS_POLICY["robots_rule_is_reuse_permission"])

    def test_proxy_research_is_separate_from_direct_request_arithmetic(self) -> None:
        inventory = PINNED_RETRIEVAL_INVENTORY
        self.assertTrue(inventory["browser_proxy_research_used"])
        self.assertIsNone(inventory["browser_proxy_origin_request_count"])
        self.assertTrue(
            inventory[
                "browser_proxy_research_excluded_from_direct_request_arithmetic"
            ]
        )

    def test_administrative_lifecycle_metrics_and_imports_stay_separate(self) -> None:
        definition = source_definition()
        units = definition["unit_contract"]
        self.assertEqual(
            units["source_observation_unit"],
            "environmental_assessment_discussion_status_record",
        )
        self.assertFalse(units["administrative_record_is_physical_project"])
        self.assertFalse(units["administrative_record_is_physical_site"])
        assessment = validate_release_bundle(PINNED_RELEASE)["assessment"]
        lifecycle = assessment["lifecycle_boundary"]
        self.assertFalse(lifecycle["administrative_eia_stage_is_physical_lifecycle"])
        self.assertIsNone(lifecycle["physical_construction_status"])
        metrics = assessment["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        self.assertIsNone(metrics["it_capacity_mw"])
        self.assertIsNone(metrics["annual_energy_consumption_mwh"])
        for key in (
            "construction_master_import_permitted",
            "construction_map_import_permitted",
            "current_coverage_ledger_import_permitted",
        ):
            self.assertFalse(DOWNSTREAM_IMPORT_POLICY[key])

    def test_network_audit_script_cannot_call_result_paths_or_terms(self) -> None:
        all_requests = (
            audit_module.ROBOTS_REQUESTS
            + audit_module.DATA_GO_METADATA_REQUESTS
            + audit_module.EIASS_METADATA_REQUESTS
            + audit_module.KOGL_METADATA_REQUESTS
        )
        urls = [url for _, url in all_requests]
        self.assertTrue(urls)
        for url in urls:
            audit_module._assert_safe_url(url)
            self.assertNotIn(EIA_LIST_PATH, url)
            self.assertNotIn(PRE_STRATEGY_SMALL_LIST_PATH, url)
            lowered = url.casefold()
            for term in SEARCH_TERMS + CONDITIONAL_ENGLISH_TERMS:
                self.assertNotIn(term.casefold(), lowered)
        self.assertEqual(audit_module.MAX_DIRECT_REQUEST_ATTEMPTS, 40)
        self.assertEqual(audit_module.MIN_REQUEST_START_INTERVAL_SECONDS, 3.0)

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        inventory = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        for filename, expected in derive_release_files(inventory).items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), expected)

    def test_frozen_modes_manifest_and_tamper_detection(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            {entry.name for entry in PINNED_RELEASE.iterdir()}, EXPECTED_FILES
        )
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertEqual(
                entry.stat().st_mode & 0o777,
                0o555 if entry.is_dir() else 0o444,
            )
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            _refreeze(copied)
            with self.assertRaises(SouthKoreaEIASSNIERAssessmentError):
                validate_release_bundle(copied)
            thaw_for_test(copied)

    def test_validator_builder_and_hashes_are_deterministic(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["validation_mode"], "offline")
        self.assertEqual(payload["validation_network_requests"], 0)
        self.assertEqual(payload["controlled_audit_request_attempts"], 10)
        self.assertEqual(payload["result_bearing_api_requests"], 0)
        self.assertIsNone(payload["result_count"])

        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            definition = Path(temporary) / "definition.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    build_main(
                        [
                            "--output",
                            str(release),
                            "--definition",
                            str(definition),
                        ]
                    ),
                    0,
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["build_network_requests"], 0)
            self.assertEqual(payload["direct_request_attempts"], 10)
            self.assertEqual(payload["result_bearing_api_requests"], 0)
            self.assertEqual(
                definition.read_bytes(), canonical_json(source_definition())
            )
            built = validate_release_bundle(release, definition_path=definition)
            pinned = validate_release_bundle(PINNED_RELEASE)
            self.assertEqual(built["manifest"], pinned["manifest"])
            thaw_for_test(release)

        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )
        self.assertEqual(
            len(sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes())),
            64,
        )


if __name__ == "__main__":
    unittest.main()
