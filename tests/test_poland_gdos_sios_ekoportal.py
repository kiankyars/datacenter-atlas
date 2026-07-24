from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.poland_gdos_sios_ekoportal import (
    AUDIT_REQUEST_START_INTERVAL_SECONDS,
    DOWNSTREAM_IMPORT_POLICY,
    EXPECTED_FILES,
    MAX_DIRECT_REQUEST_ATTEMPTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_TERMS,
    SIOS_PDF_EXPORT_PATH,
    SIOS_XLS_EXPORT_PATH,
    PolandGDOSSIOSAssessmentError,
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


validate_main = _load_script("validate_poland_gdos_sios_ekoportal").main
build_main = _load_script("build_poland_gdos_sios_ekoportal").main


class PolandGDOSSIOSAssessmentTests(unittest.TestCase):
    def test_pinned_release_is_zero_row_and_fail_closed(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE,
            definition_path=SOURCE_DEFINITION,
        )
        assessment = bundle["assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "robots_rights_coverage_blocked_metadata_only",
        )
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)
        self.assertFalse(assessment["coverage"]["complete_for_poland"])
        for field in (
            "document_card_count",
            "document_count",
            "project_count",
            "publication_count",
            "result_count",
            "site_count",
        ):
            self.assertIsNone(assessment["coverage"][field])
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")

    def test_exact_terms_are_only_a_gated_local_postfilter_plan(self) -> None:
        self.assertEqual(
            SEARCH_TERMS,
            ("centrum danych", "centra danych", "data center", "serwerownia"),
        )
        plan = query_plan()
        self.assertEqual([row["term"] for row in plan["rows"]], list(SEARCH_TERMS))
        for row in plan["rows"]:
            self.assertFalse(row["source_exact_phrase_semantics_documented"])
            self.assertFalse(row["exact_literal_local_postfilter_completed"])
            self.assertEqual(row["network_requests"], 0)
            self.assertEqual(row["pages_retrieved"], 0)
            self.assertIsNone(row["result_count"])
            self.assertEqual(
                row["status"],
                "not_executed_robots_rights_coverage_semantics_gate",
            )
        server_room = plan["rows"][-1]
        self.assertEqual(server_room["term_role"], "context_sensitive_server_room")
        self.assertTrue(
            plan["classification_contract_if_authorized"][
                "serwerownia_never_auto_promoted"
            ]
        )

    def test_endpoint_and_pagination_contract_are_truthful(self) -> None:
        endpoint = source_definition()["endpoint_contract"]
        self.assertEqual(endpoint["form_method"], "GET")
        self.assertEqual(endpoint["form_parameters"]["keywords"], (
            "keyword string, max 64 characters"
        ))
        self.assertEqual(endpoint["form_parameters"]["iid"], (
            "publisher or instance selector; empty form value 0"
        ))
        self.assertFalse(endpoint["query_match_semantics_documented"])
        self.assertFalse(endpoint["pagination_contract_documented"])
        self.assertIsNone(endpoint["pagination_parameter"])
        self.assertIsNone(endpoint["page_size"])
        self.assertFalse(endpoint["api_or_bulk_download_contract_found"])
        self.assertEqual(
            endpoint["export_routes_observed_but_not_requested"],
            [SIOS_PDF_EXPORT_PATH, SIOS_XLS_EXPORT_PATH],
        )
        network = source_definition()["network_policy_if_all_gates_later_clear"]
        self.assertEqual(
            network["maximum_pages_per_query_if_pagination_is_documented"],
            10,
        )
        self.assertEqual(
            network["maximum_result_bearing_requests_if_authorized"], 40
        )
        self.assertEqual(network["direct_request_attempt_cap"], 40)

    def test_robots_rights_and_national_access_gates_are_explicit(self) -> None:
        definition = source_definition()
        access = definition["access"]
        self.assertTrue(access["sios_robots_disallows_root_for_all_user_agents"])
        self.assertTrue(access["national_eia_officially_blocked_outside_poland"])
        self.assertEqual(access["national_eia_direct_home_probe_outcome"], "timeout")
        self.assertFalse(RIGHTS_POLICY[
            "affirmative_common_search_result_reuse_scope_found"
        ])
        self.assertTrue(RIGHTS_POLICY["gdos_general_reuse_surface_found"])
        self.assertTrue(RIGHTS_POLICY[
            "gdos_general_reuse_surface_reserves_third_party_rights"
        ])
        self.assertFalse(RIGHTS_POLICY[
            "gdos_reuse_surface_scope_affirmed_for_all_sios_publishers"
        ])
        self.assertFalse(RIGHTS_POLICY[
            "gov_pl_cc_by_sa_applies_to_linked_sios_results"
        ])
        self.assertFalse(RIGHTS_POLICY["robots_rule_is_reuse_permission"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])

    def test_scope_split_does_not_claim_national_all_authority_coverage(self) -> None:
        coverage = source_definition()["coverage_contract"]
        self.assertEqual(coverage["current_gdos_rdos_cards_start"], "2025-06-01")
        self.assertIn("not every Polish", coverage["current_register_scope"])
        self.assertFalse(coverage["complete_for_poland_claimed"])
        self.assertEqual(
            coverage["national_eia_database_statutory_entry_duty_start"],
            "2017-01-01",
        )
        self.assertFalse(coverage["national_eia_query_executed"])

    def test_direct_request_ledger_is_exact_paced_and_under_cap(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        inventory = PINNED_RETRIEVAL_INVENTORY
        self.assertEqual(inventory["direct_request_attempts"], 10)
        self.assertEqual(inventory["direct_request_attempt_cap"], 40)
        self.assertEqual(MAX_DIRECT_REQUEST_ATTEMPTS, 40)
        self.assertEqual(AUDIT_REQUEST_START_INTERVAL_SECONDS, 3.2)
        self.assertEqual(MIN_REQUEST_INTERVAL_SECONDS, 3.0)
        self.assertEqual(inventory["completed_response_requests"], 8)
        self.assertEqual(inventory["failed_timeout_requests"], 2)
        self.assertEqual(inventory["result_bearing_search_requests"], 0)
        self.assertEqual(inventory["search_export_requests"], 0)
        self.assertEqual(inventory["source_detail_requests"], 0)
        self.assertEqual(inventory["source_document_requests"], 0)
        self.assertFalse(inventory["search_capture_started"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])

    def test_proxy_research_is_not_misreported_as_direct_accounting(self) -> None:
        inventory = PINNED_RETRIEVAL_INVENTORY
        self.assertTrue(inventory["browser_proxy_research_used"])
        self.assertIsNone(inventory["browser_proxy_origin_request_count"])
        self.assertTrue(
            inventory[
                "browser_proxy_research_excluded_from_direct_request_arithmetic"
            ]
        )

    def test_administrative_units_lifecycle_and_metrics_stay_separate(self) -> None:
        definition = source_definition()
        units = definition["unit_contract"]
        self.assertEqual(
            units["source_observation_unit"],
            "public_environmental_document_card",
        )
        self.assertFalse(units["administrative_card_is_physical_project"])
        self.assertFalse(units["administrative_card_is_physical_site"])
        assessment = validate_release_bundle(PINNED_RELEASE)["assessment"]
        lifecycle = assessment["lifecycle_boundary"]
        self.assertFalse(lifecycle[
            "administrative_publication_is_physical_lifecycle"
        ])
        self.assertIsNone(lifecycle["physical_construction_status"])
        metrics = assessment["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        self.assertIsNone(metrics["it_capacity_mw"])
        self.assertIsNone(metrics["annual_energy_consumption_mwh"])

    def test_no_master_map_or_ledger_import(self) -> None:
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY[
            "construction_master_import_permitted"
        ])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY[
            "construction_map_import_permitted"
        ])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY[
            "current_coverage_ledger_import_permitted"
        ])

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        inventory = json.loads((PINNED_RELEASE / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        ))
        for filename, expected in derive_release_files(inventory).items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), expected)

    def test_frozen_modes_manifest_and_tamper_detection(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual({entry.name for entry in PINNED_RELEASE.iterdir()}, EXPECTED_FILES)
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
            with self.assertRaises(PolandGDOSSIOSAssessmentError):
                validate_release_bundle(copied)

    def test_validator_builder_and_hashes_are_deterministic(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["validation_mode"], "offline")
        self.assertEqual(payload["validation_network_requests"], 0)
        self.assertEqual(payload["controlled_audit_request_attempts"], 10)
        self.assertEqual(payload["result_bearing_search_requests"], 0)
        self.assertIsNone(payload["result_count"])

        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            definition = Path(temporary) / "definition.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(build_main([
                    "--output", str(release), "--definition", str(definition)
                ]), 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["build_network_requests"], 0)
            self.assertEqual(payload["direct_request_attempts"], 10)
            self.assertEqual(payload["result_bearing_search_requests"], 0)
            self.assertEqual(definition.read_bytes(), canonical_json(source_definition()))
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
