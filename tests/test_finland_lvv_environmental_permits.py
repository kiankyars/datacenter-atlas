from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.finland_lvv_environmental_permits import (
    DATE_BASES,
    DOWNSTREAM_IMPORT_POLICY,
    END_DATE,
    EXPECTED_FILES,
    MAX_RESULT_BEARING_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PAGE_SIZE,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_TERMS,
    START_DATE,
    FinlandLVVPermitError,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    query_plan,
    query_request_body,
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


validate_main = _load_script("validate_finland_lvv_environmental_permits").main
build_main = _load_script("build_finland_lvv_environmental_permits").main


class FinlandLVVEnvironmentalPermitTests(unittest.TestCase):
    def test_pinned_release_is_fail_closed_with_null_source_counts(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE,
            definition_path=SOURCE_DEFINITION,
        )
        assessment = bundle["assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "rights_scope_unconfirmed_metadata_only",
        )
        coverage = assessment["coverage"]
        for field in (
            "result_count",
            "license_or_permit_case_count",
            "publication_count",
            "project_count",
            "site_count",
        ):
            self.assertIsNone(coverage[field])
        self.assertFalse(coverage["all_union_rows_classified"])
        self.assertEqual(set(coverage["classification_counts"].values()), {None})
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)

    def test_closed_plan_has_four_exact_terms_two_date_bases(self) -> None:
        plan = query_plan()
        self.assertEqual(len(plan["rows"]), 8)
        self.assertEqual(
            [(row["term"], row["date_basis"]) for row in plan["rows"]],
            [
                (term, date_basis)
                for term in SEARCH_TERMS
                for date_basis in DATE_BASES
            ],
        )
        self.assertEqual(
            set(SEARCH_TERMS),
            {"datakeskus", "datakeskukset", "data center", "data centre"},
        )
        for row in plan["rows"]:
            self.assertEqual(
                row["status"], "not_executed_rights_scope_not_affirmed"
            )
            self.assertEqual(row["network_requests"], 0)
            self.assertEqual(row["pages_retrieved"], 0)
            self.assertIsNone(row["result_count"])
            self.assertEqual(set(row["classification_counts"].values()), {None})

    def test_request_bodies_are_date_bounded_paged_and_exact(self) -> None:
        created = query_request_body("datakeskus", "case_created")
        self.assertEqual(created["createdStart"], "2016-01-01T00:00:00Z")
        self.assertEqual(created["createdEnd"], "2026-07-18T23:59:59Z")
        self.assertIsNone(created["documentPublishStart"])
        self.assertEqual(created["fetchNext"], PAGE_SIZE)
        self.assertEqual(created["offset"], 0)
        published = query_request_body(
            "data centre",
            "latest_document_published",
            offset=PAGE_SIZE,
        )
        self.assertIsNone(published["createdStart"])
        self.assertEqual(
            published["documentPublishStart"], "2016-01-01T00:00:00Z"
        )
        self.assertEqual(
            published["documentPublishEnd"], "2026-07-18T23:59:59Z"
        )
        with self.assertRaises(FinlandLVVPermitError):
            query_request_body("palvelinkeskus", "case_created")
        with self.assertRaises(FinlandLVVPermitError):
            query_request_body("datakeskus", "case_created", offset=1)

    def test_future_network_contract_is_paced_capped_and_rights_gated(self) -> None:
        network = source_definition()["network_policy_if_rights_later_clarified"]
        self.assertEqual(network["minimum_request_interval_seconds"], 5.0)
        self.assertEqual(MIN_REQUEST_INTERVAL_SECONDS, 5.0)
        self.assertEqual(network["maximum_result_bearing_requests"], 320)
        self.assertEqual(MAX_RESULT_BEARING_REQUESTS, 320)
        self.assertTrue(network["response_body_hash_required"])
        self.assertTrue(network["stop_and_null_counts_on_cap_or_error"])
        self.assertTrue(
            network["stop_before_first_query_unless_rights_gate_is_affirmative"]
        )

    def test_rights_gate_distinguishes_open_api_from_open_data_scope(self) -> None:
        definition = source_definition()
        self.assertTrue(definition["access"]["api_openapi_available"])
        self.assertTrue(
            definition["access"][
                "api_machine_access_verified_with_synthetic_no_match"
            ]
        )
        self.assertFalse(RIGHTS_POLICY["affirmative_retained_data_scope_found"])
        self.assertTrue(
            RIGHTS_POLICY["cc_by_4_0_applies_to_lvv_produced_open_data"]
        )
        self.assertFalse(
            RIGHTS_POLICY[
                "environmental_permit_service_listed_in_open_data_catalogue"
            ]
        )
        self.assertFalse(RIGHTS_POLICY["permit_case_metadata_publication_permitted"])
        self.assertTrue(
            RIGHTS_POLICY["rights_clarification_required_before_capture"]
        )
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])

    def test_robots_findings_do_not_overstate_the_locale_prefixed_yva_path(self) -> None:
        robots = validate_release_bundle(PINNED_RELEASE)["source_inventory"][
            "robots_findings"
        ]
        self.assertEqual(robots["primary_service_host"]["robots_http_status"], 404)
        self.assertFalse(
            robots["primary_service_host"]["robots_rule_published"]
        )
        yva = robots["ymparisto_host"]
        self.assertEqual(yva["canonical_finnish_search_path"], "/fi/search")
        self.assertIn("/search/", yva["disallowed_paths_include"])
        self.assertFalse(
            yva["canonical_path_is_exact_prefix_match_for_listed_disallow"]
        )
        self.assertFalse(yva["robots_rule_is_reuse_permission"])

    def test_case_publication_project_and_site_units_stay_separate(self) -> None:
        definition = source_definition()
        units = definition["unit_contract"]
        self.assertEqual(units["api_search_result_unit"], "permit_case_search_record")
        self.assertFalse(units["document_publication_is_case_record"])
        self.assertFalse(units["permit_case_is_atlas_project"])
        self.assertFalse(units["permit_case_is_atlas_site"])
        self.assertIsNone(units["publication_count"])
        self.assertIsNone(units["project_count"])
        self.assertIsNone(units["site_count"])

    def test_process_lifecycle_metrics_and_pii_all_fail_closed(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        lifecycle = assessment["lifecycle_boundary"]
        self.assertFalse(lifecycle["permit_process_status_is_physical_lifecycle"])
        self.assertIsNone(lifecycle["physical_construction_status"])
        self.assertIsNone(lifecycle["physical_operation_status"])
        metrics = assessment["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        self.assertIsNone(metrics["source_metric_statement_count"])
        self.assertIsNone(metrics["it_capacity_mw"])
        self.assertIsNone(metrics["annual_energy_consumption_mwh"])
        self.assertFalse(assessment["pii_policy"]["applicant_capture_performed"])
        self.assertFalse(assessment["pii_policy"]["contacts_retained"])
        self.assertFalse(
            assessment["pii_policy"]["natural_person_applicants_retained"]
        )
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")

    def test_no_downstream_import_or_automatic_merge_contract(self) -> None:
        self.assertFalse(
            DOWNSTREAM_IMPORT_POLICY["construction_master_import_permitted"]
        )
        self.assertFalse(
            DOWNSTREAM_IMPORT_POLICY["construction_map_import_permitted"]
        )
        self.assertFalse(
            DOWNSTREAM_IMPORT_POLICY[
                "current_coverage_ledger_import_permitted"
            ]
        )
        inference = source_definition()["inference_policy"]
        self.assertFalse(inference["automatic_entity_merge_permitted"])
        self.assertFalse(inference["automatic_project_merge_permitted"])
        self.assertFalse(inference["automatic_site_merge_permitted"])

    def test_controlled_audit_is_hash_bound_and_has_no_result_query(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        requests = PINNED_RETRIEVAL_INVENTORY["controlled_http_requests"]
        self.assertEqual(PINNED_RETRIEVAL_INVENTORY["network_requests"], 8)
        self.assertEqual(
            PINNED_RETRIEVAL_INVENTORY["result_bearing_search_requests"], 0
        )
        self.assertFalse(PINNED_RETRIEVAL_INVENTORY["search_capture_started"])
        self.assertEqual([row["http_status"] for row in requests].count(404), 1)
        self.assertTrue(all(len(row["sha256"]) == 64 for row in requests))
        self.assertTrue(all(row["body_retained"] is False for row in requests))
        self.assertEqual(requests[3]["method"], "POST")
        self.assertEqual(requests[3]["bytes"], 2)

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
            with self.assertRaises(FinlandLVVPermitError):
                validate_release_bundle(copied)

    def test_validator_and_builder_are_offline_and_reproducible(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["validation_mode"], "offline")
        self.assertEqual(payload["validation_network_requests"], 0)
        self.assertEqual(payload["controlled_audit_requests"], 8)
        self.assertEqual(payload["result_bearing_search_requests"], 0)
        self.assertNotIn("network_requests", payload)
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
            self.assertEqual(payload["controlled_audit_requests"], 8)
            self.assertEqual(payload["result_bearing_search_requests"], 0)
            self.assertNotIn("network_requests", payload)
            self.assertEqual(
                definition.read_bytes(), canonical_json(source_definition())
            )
            built = validate_release_bundle(release, definition_path=definition)
            pinned = validate_release_bundle(PINNED_RELEASE)
            self.assertEqual(built["manifest"], pinned["manifest"])
            thaw_for_test(release)

    def test_bounded_dates_external_definition_and_hashes_are_pinned(self) -> None:
        self.assertEqual(START_DATE.isoformat(), "2016-01-01")
        self.assertEqual(END_DATE.isoformat(), "2026-07-18")
        self.assertEqual(SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition()))
        manifest_hash = sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes())
        definition_hash = sha256_bytes(SOURCE_DEFINITION.read_bytes())
        self.assertEqual(
            manifest_hash,
            "4b224e8d0e38311da34ea29461abfc41b1f2b1c3d459928e57ac623770ea0799",
        )
        self.assertEqual(
            definition_hash,
            "d09b8a0b1e537ab035e46518882f94d58aeec6e2685a3badbcc40b983764b7fb",
        )


if __name__ == "__main__":
    unittest.main()
