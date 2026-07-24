from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.india_parivesh_environmental_clearances import (
    ASSESSMENT_LOCAL_DATE,
    AUDIT_REQUESTS,
    DOWNSTREAM_IMPORT_POLICY,
    EXPECTED_FILES,
    MAX_PAGES_PER_QUERY,
    MAX_RESULT_BEARING_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PAGE_SIZE_CEILING_IF_SUPPORTED,
    PINNED_RETRIEVAL_INVENTORY,
    PLANNED_QUERY_END_DATE,
    PLANNED_QUERY_START_DATE,
    QUERY_YEARS,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_TERMS,
    IndiaPARIVESHEnvironmentalClearanceError,
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


validate_main = _load_script(
    "validate_india_parivesh_environmental_clearances"
).main
build_main = _load_script("build_india_parivesh_environmental_clearances").main


def _refreeze(root: Path) -> None:
    for entry in root.rglob("*"):
        if not entry.is_symlink():
            entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


class IndiaPARIVESHEnvironmentalClearanceTests(unittest.TestCase):
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
            "decision_or_publication_count",
            "environmental_clearance_proposal_count",
            "project_count",
            "result_count",
            "site_count",
        ):
            self.assertIsNone(coverage[field])
        self.assertFalse(coverage["all_union_rows_classified"])
        self.assertEqual(set(coverage["classification_counts"].values()), {None})
        self.assertFalse(coverage["complete_for_india"])
        self.assertFalse(coverage["proposal_search_executed"])
        self.assertIsNone(coverage["observed_source_date_start"])
        self.assertIsNone(coverage["observed_source_date_end"])
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)

    def test_exact_terms_and_annual_query_shards_are_predeclared(self) -> None:
        self.assertEqual(
            SEARCH_TERMS,
            ("data centre", "data center", "datacentre", "datacenter"),
        )
        self.assertEqual(QUERY_YEARS, tuple(range(2006, 2027)))
        plan = query_plan()
        self.assertEqual(plan["planned_query_count"], 84)
        self.assertEqual(len(plan["rows"]), 84)
        self.assertEqual(
            plan["rows"][0],
            {
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "decision_or_publication_count": None,
                "environmental_clearance_proposal_count": None,
                "network_requests": 0,
                "pages_retrieved": 0,
                "planned_query_date_end_inclusive": "2006-12-31",
                "planned_query_date_start_inclusive": "2006-09-14",
                "project_count": None,
                "query_id": "y2006-t01",
                "result_count": None,
                "search_term": "data centre",
                "site_count": None,
                "status": "not_executed_rights_scope_not_affirmed",
            },
        )
        last = plan["rows"][-1]
        self.assertEqual(last["query_id"], "y2026-t04")
        self.assertEqual(last["search_term"], "datacenter")
        self.assertEqual(
            last["planned_query_date_start_inclusive"], "2026-01-01"
        )
        self.assertEqual(
            last["planned_query_date_end_inclusive"], "2026-07-18"
        )
        self.assertFalse(plan["observed_source_coverage_claimed"])
        self.assertEqual(
            plan["planned_query_date_start_inclusive"], "2006-09-14"
        )
        self.assertEqual(
            plan["planned_query_date_end_inclusive"], "2026-07-18"
        )
        self.assertIn("atlas-selected", plan["planned_lower_bound_basis"])
        self.assertIn("not evidence", plan["planned_lower_bound_basis"])
        for row in plan["rows"]:
            self.assertEqual(row["network_requests"], 0)
            self.assertEqual(row["pages_retrieved"], 0)
            self.assertIsNone(row["result_count"])
            self.assertEqual(set(row["classification_counts"].values()), {None})

    def test_future_query_plan_is_rights_gated_paced_and_capped(self) -> None:
        definition = source_definition()
        future = definition["future_authorized_query_contract"]
        self.assertIsNone(future["endpoint"])
        self.assertTrue(future["permission_scope_must_cover_proposal_and_result_metadata"])
        self.assertTrue(future["interface_and_schema_reverification_required"])
        self.assertTrue(future["exact_casefolded_literal_match_required"])
        self.assertTrue(future["human_classification_required"])
        self.assertFalse(future["automatic_fuzzy_match_permitted"])
        self.assertEqual(
            future["planned_query_date_start_inclusive"], "2006-09-14"
        )
        self.assertEqual(
            future["planned_query_date_end_inclusive"], "2026-07-18"
        )
        self.assertIn("atlas-selected", future["planned_lower_bound_basis"])
        coverage = definition["coverage_contract"]
        self.assertFalse(coverage["proposal_search_executed"])
        self.assertIsNone(coverage["observed_source_date_start"])
        self.assertIsNone(coverage["observed_source_date_end"])
        self.assertNotIn("date_start_inclusive", coverage)
        self.assertNotIn("date_end_inclusive", coverage)
        network = definition["network_policy_if_rights_later_clarified"]
        self.assertEqual(MIN_REQUEST_INTERVAL_SECONDS, 5.0)
        self.assertEqual(MAX_PAGES_PER_QUERY, 10)
        self.assertEqual(PAGE_SIZE_CEILING_IF_SUPPORTED, 100)
        self.assertEqual(MAX_RESULT_BEARING_REQUESTS, 840)
        self.assertEqual(network["maximum_result_bearing_requests"], 840)
        self.assertTrue(network["one_request_at_a_time"])
        self.assertTrue(network["response_body_hash_required"])
        self.assertTrue(
            network[
                "stop_before_first_result_request_unless_rights_gate_is_affirmative"
            ]
        )

    def test_rights_gate_keeps_data_gov_scope_separate(self) -> None:
        self.assertFalse(
            RIGHTS_POLICY[
                "affirmative_parivesh_proposal_record_reuse_scope_found"
            ]
        )
        self.assertTrue(
            RIGHTS_POLICY["current_parivesh_copyright_policy_requires_permission"]
        )
        self.assertTrue(
            RIGHTS_POLICY[
                "legacy_environmental_clearance_copyright_policy_requires_permission"
            ]
        )
        self.assertTrue(
            RIGHTS_POLICY["data_gov_godl_affirmative_for_published_dataset_resources"]
        )
        self.assertFalse(
            RIGHTS_POLICY["data_gov_godl_scope_affirmed_for_parivesh_project_rows"]
        )
        self.assertFalse(RIGHTS_POLICY["robots_rule_is_reuse_permission"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        alternative = source_definition()["data_gov_alternative"]
        self.assertEqual(alternative["file_size_metadata_bytes"], 386)
        self.assertEqual(alternative["resource_period"], "2022")
        self.assertEqual(alternative["geographic_unit"], "state_or_union_territory")
        self.assertFalse(alternative["project_level"])
        self.assertFalse(alternative["suitable_for_project_discovery"])
        self.assertFalse(alternative["file_body_requested"])
        self.assertIsNone(alternative["aggregate_row_count"])

    def test_robots_findings_do_not_overstate_access(self) -> None:
        definition = source_definition()
        access = definition["access"]
        self.assertEqual(access["current_robots_http_status"], 404)
        self.assertFalse(access["current_robots_rule_published"])
        self.assertEqual(access["legacy_robots_http_status"], 200)
        self.assertTrue(access["legacy_robots_allows_root"])
        findings = validate_release_bundle(PINNED_RELEASE)["source_inventory"][
            "robots_findings"
        ]
        self.assertFalse(findings["robots_rule_is_reuse_permission"])

    def test_proposal_project_site_and_physical_lifecycle_stay_separate(self) -> None:
        definition = source_definition()
        units = definition["unit_contract"]
        self.assertEqual(
            units["source_observation_unit"],
            "environmental_clearance_proposal_stage_record",
        )
        self.assertFalse(units["proposal_stage_record_is_atlas_project"])
        self.assertFalse(units["proposal_stage_record_is_atlas_site"])
        self.assertFalse(
            units["environmental_clearance_status_is_physical_lifecycle"]
        )
        for field in (
            "decision_or_publication_count",
            "environmental_clearance_proposal_count",
            "project_count",
            "result_count",
            "site_count",
        ):
            self.assertIsNone(units[field])

    def test_lifecycle_metrics_and_pii_all_fail_closed(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        lifecycle = assessment["lifecycle_boundary"]
        self.assertFalse(
            lifecycle["environmental_clearance_status_is_physical_lifecycle"]
        )
        self.assertIsNone(lifecycle["physical_construction_status"])
        self.assertIsNone(lifecycle["physical_operation_status"])
        metrics = assessment["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        self.assertIsNone(metrics["source_metric_statement_count"])
        self.assertIsNone(metrics["it_capacity_mw"])
        self.assertIsNone(metrics["annual_energy_consumption_mwh"])
        self.assertIsNone(metrics["pue"])
        self.assertFalse(assessment["pii_policy"]["applicant_capture_performed"])
        self.assertFalse(assessment["pii_policy"]["contacts_retained"])
        self.assertFalse(assessment["pii_policy"]["proposal_documents_retained"])
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")

    def test_no_downstream_import_or_automatic_merge_contract(self) -> None:
        for key in (
            "construction_master_import_permitted",
            "construction_map_import_permitted",
            "current_coverage_ledger_import_permitted",
            "explicit_positive_contract_present",
        ):
            self.assertFalse(DOWNSTREAM_IMPORT_POLICY[key])
        inference = source_definition()["inference_policy"]
        self.assertFalse(inference["automatic_entity_merge_permitted"])
        self.assertFalse(inference["automatic_project_merge_permitted"])
        self.assertFalse(inference["automatic_site_merge_permitted"])
        self.assertIsNone(inference["data_centre_type"])
        self.assertIsNone(inference["physical_lifecycle_status"])

    def test_controlled_audit_is_exact_and_has_no_source_traversal(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        inventory = PINNED_RETRIEVAL_INVENTORY
        requests = inventory["controlled_http_requests"]
        self.assertEqual(inventory["controlled_audit_requests"], 8)
        self.assertEqual(inventory["rights_and_access_metadata_requests"], 8)
        self.assertEqual(inventory["data_gov_metadata_requests"], 3)
        for field in (
            "data_gov_resource_body_requests",
            "project_detail_requests",
            "project_document_requests",
            "proposal_result_requests",
            "proposal_search_requests",
        ):
            self.assertEqual(inventory[field], 0)
        self.assertFalse(inventory["source_capture_started"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertEqual(
            [(row["method"], row["url"]) for row in requests],
            list(AUDIT_REQUESTS),
        )
        self.assertEqual(
            [row["http_status"] for row in requests],
            [200, 404, 200, 200, 200, 200, 200, 200],
        )
        self.assertTrue(all(len(row["sha256"]) == 64 for row in requests))
        self.assertTrue(all(row["response_body_retained"] is False for row in requests))
        self.assertTrue(all(row["tls_verification_bypassed"] is False for row in requests))
        self.assertEqual(requests[2]["method"], "POST")
        self.assertEqual(requests[2]["request_bytes"], 128)
        self.assertEqual(len(requests[2]["request_sha256"]), 64)
        for row in requests:
            url = row["url"].casefold()
            self.assertNotIn("track", url)
            if "proposal" in url:
                self.assertIn("data.gov.in/resource/", url)

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        inventory = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        for filename, expected in derive_release_files(inventory).items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), expected)

    def test_frozen_modes_manifest_and_content_tamper_detection(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            {entry.name for entry in PINNED_RELEASE.iterdir()}, EXPECTED_FILES
        )
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertFalse(entry.is_symlink())
            self.assertTrue(entry.is_file())
            self.assertEqual(entry.stat().st_mode & 0o777, 0o444)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            _refreeze(copied)
            with self.assertRaises(IndiaPARIVESHEnvironmentalClearanceError):
                validate_release_bundle(copied)
            thaw_for_test(copied)

    def test_symlinked_release_entry_and_external_definition_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            copied = temporary_path / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            observations = copied / "observations.jsonl"
            observations.unlink()
            observations.symlink_to(copied / "README.md")
            _refreeze(copied)
            with self.assertRaises(IndiaPARIVESHEnvironmentalClearanceError):
                validate_release_bundle(copied)
            thaw_for_test(copied)

            definition_link = temporary_path / "definition.json"
            definition_link.symlink_to(SOURCE_DEFINITION)
            with self.assertRaises(IndiaPARIVESHEnvironmentalClearanceError):
                validate_release_bundle(
                    PINNED_RELEASE,
                    definition_path=definition_link,
                )

    def test_validator_and_builder_counters_are_unambiguous_and_offline(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["validation_mode"], "offline")
        self.assertEqual(payload["validation_network_requests"], 0)
        self.assertEqual(payload["controlled_audit_requests"], 8)
        self.assertEqual(payload["proposal_search_requests"], 0)
        self.assertEqual(payload["proposal_result_requests"], 0)
        self.assertEqual(payload["project_detail_requests"], 0)
        self.assertEqual(payload["project_document_requests"], 0)
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
            self.assertEqual(payload["proposal_search_requests"], 0)
            self.assertEqual(payload["proposal_result_requests"], 0)
            self.assertEqual(payload["project_detail_requests"], 0)
            self.assertEqual(payload["project_document_requests"], 0)
            self.assertNotIn("network_requests", payload)
            self.assertEqual(
                definition.read_bytes(), canonical_json(source_definition())
            )
            built = validate_release_bundle(release, definition_path=definition)
            pinned = validate_release_bundle(PINNED_RELEASE)
            self.assertEqual(built["manifest"], pinned["manifest"])
            thaw_for_test(release)

    def test_dates_external_definition_and_hashes_are_pinned(self) -> None:
        self.assertEqual(ASSESSMENT_LOCAL_DATE.isoformat(), "2026-07-18")
        self.assertEqual(PLANNED_QUERY_START_DATE.isoformat(), "2006-09-14")
        self.assertEqual(PLANNED_QUERY_END_DATE.isoformat(), "2026-07-18")
        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes()),
            "d69ad0f60cc0c11d5f431b5ef7eccc89c5e429ef68eb65866b531860efc2cbd0",
        )
        self.assertEqual(
            sha256_bytes(SOURCE_DEFINITION.read_bytes()),
            "661c76bf7a95ff52552f04fa7722aa905f336458e410a99ac6ea216c11778aea",
        )
        self.assertEqual(
            sha256_bytes(
                (PINNED_RELEASE / "retrieval-inventory.json").read_bytes()
            ),
            "eb77b9a96e6350be4783f0588629a6fd222a07880ef38a8711000458dab03e26",
        )


if __name__ == "__main__":
    unittest.main()
