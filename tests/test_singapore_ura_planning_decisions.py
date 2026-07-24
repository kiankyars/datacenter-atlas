from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date, datetime
import ast
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.singapore_ura_planning_decisions import (
    ANNUAL_YEARS,
    API_TERMS_URL,
    BOUNDARY_PROBE_YEAR,
    DEVELOPMENT_REGISTER_URL,
    DIRECT_TERMS,
    DOWNSTREAM_IMPORT_POLICY,
    END_YEAR,
    EXPECTED_FILES,
    FORBIDDEN_STANDALONE_TERMS,
    OPEN_DATA_LICENCE_URL,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    REVIEW_TERMS,
    RIGHTS_POLICY,
    SOURCE_ID,
    START_YEAR,
    SingaporeURAPlanningDecisionError,
    annual_request_url,
    canonical_json,
    delta_request_url,
    derive_release_files,
    is_frozen_release,
    query_plan,
    require_success_result,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    validate_retrieval_inventory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
NULL_COUNT_FIELDS = {
    "classification_direct_count",
    "classification_excluded_count",
    "classification_review_count",
    "decision_count",
    "license_or_permit_count",
    "metric_statement_count",
    "project_count",
    "result_count",
    "search_count",
    "site_count",
}


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_main = _load_script("validate_singapore_ura_planning_decisions").main
build_main = _load_script("build_singapore_ura_planning_decisions").main


class SingaporeURAPlanningDecisionTests(unittest.TestCase):
    def test_module_has_no_silent_duplicate_literal_dict_keys(self) -> None:
        module_path = (
            PROJECT_ROOT
            / "datacenter_atlas"
            / "singapore_ura_planning_decisions.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys = [
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            self.assertEqual(
                len(literal_keys),
                len(set(literal_keys)),
                f"duplicate literal key in dict at line {node.lineno}",
            )

    def test_pinned_release_is_fail_closed_and_all_source_counts_are_null(
        self,
    ) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE,
            definition_path=SOURCE_DEFINITION,
        )
        assessment = bundle["assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "credential_required_metadata_only",
        )
        self.assertEqual(SOURCE_ID, RELEASE_ID)
        self.assertEqual(set(assessment["coverage"]) & NULL_COUNT_FIELDS, NULL_COUNT_FIELDS)
        for field in NULL_COUNT_FIELDS:
            self.assertIsNone(assessment["coverage"][field])
            self.assertIsNone(bundle["schema"]["source_counts"][field])
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)
        self.assertEqual(bundle["schema"]["retained_planning_decision_rows"], 0)
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")

    def test_boundary_probe_and_exact_2001_through_2026_plan_are_closed(
        self,
    ) -> None:
        plan = query_plan()
        boundary = plan["boundary_probe"]
        self.assertEqual(BOUNDARY_PROBE_YEAR, 2000)
        self.assertEqual(boundary["year"], 2000)
        self.assertEqual(boundary["request_url"], annual_request_url(2000))
        self.assertEqual(boundary["network_requests"], 0)
        self.assertEqual(set(boundary["counts"]), NULL_COUNT_FIELDS)
        self.assertEqual(set(boundary["counts"].values()), {None})

        rows = plan["annual_backfill"]["rows"]
        self.assertEqual(START_YEAR, 2001)
        self.assertEqual(END_YEAR, 2026)
        self.assertEqual(tuple(row["year"] for row in rows), ANNUAL_YEARS)
        self.assertEqual(len(rows), 26)
        for row in rows:
            self.assertEqual(row["request_url"], annual_request_url(row["year"]))
            self.assertEqual(row["network_requests"], 0)
            self.assertEqual(
                row["status"], "not_executed_no_authorized_credentials"
            )
            self.assertEqual(set(row["counts"].values()), {None})
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            annual_request_url(1999)
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            annual_request_url(2027)
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            annual_request_url(True)

    def test_daily_delta_and_tombstone_contract_are_predeclared(self) -> None:
        plan = query_plan()["daily_delta_contract"]
        self.assertEqual(plan["parameter"], "last_dnload_date")
        self.assertEqual(plan["date_format"], "dd/mm/yyyy")
        self.assertEqual(plan["maximum_lookback"], "one year")
        self.assertEqual(plan["update_frequency"], "daily")
        self.assertFalse(plan["year_and_last_dnload_date_may_be_combined"])
        self.assertEqual(plan["network_requests"], 0)
        self.assertEqual(set(plan["counts"].values()), {None})
        self.assertEqual(
            delta_request_url(date(2026, 7, 18)),
            (
                "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
                "?service=Planning_Decision&last_dnload_date=18/07/2026"
            ),
        )
        tombstone = plan["tombstone_contract"]
        self.assertEqual(tombstone["delete_ind_exact_value"], "Yes")
        self.assertEqual(tombstone["key"], "exact dr_id")
        self.assertFalse(tombstone["deleted_record_is_retained_as_active_decision"])
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            delta_request_url(datetime(2026, 7, 18, 1, 0))

    def test_success_gate_requires_transport_status_exact_status_and_array(
        self,
    ) -> None:
        self.assertEqual(require_success_result({"Status": "Success", "Result": []}), [])
        rows = [{"dr_id": "1"}]
        self.assertEqual(
            require_success_result(
                json.dumps({"Status": "Success", "Result": rows}).encode()
            ),
            rows,
        )
        failing_payloads = (
            b'{"Status":"Error","Message":"Invalid input.","Result":""}',
            {"Status": "success", "Result": []},
            {"Status": "Success", "Result": ""},
            {"Status": "Success"},
            [],
            b"not-json",
        )
        for payload in failing_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(SingaporeURAPlanningDecisionError):
                    require_success_result(payload)
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            require_success_result({"Status": "Success", "Result": []}, http_status=403)
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            require_success_result({"Status": "Success", "Result": []}, http_status=True)

    def test_controlled_audit_is_exact_hash_bound_and_body_free(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        inventory = PINNED_RETRIEVAL_INVENTORY
        requests = inventory["controlled_http_requests"]
        self.assertEqual(inventory["network_requests"], 7)
        self.assertEqual(inventory["documentation_requests"], 5)
        self.assertEqual(inventory["unauthenticated_error_probe_requests"], 2)
        self.assertEqual(inventory["token_error_probe_requests"], 1)
        self.assertEqual(inventory["planning_error_probe_requests"], 1)
        for field in (
            "captcha_automation_requests",
            "captured_success_envelopes",
            "credentialed_requests",
            "registration_submissions",
            "result_bearing_requests",
            "retained_source_rows",
        ):
            self.assertEqual(inventory[field], 0)
        self.assertFalse(inventory["planning_capture_started"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertFalse(inventory["http_200_error_envelope_means_zero"])
        self.assertEqual(
            [row["http_status"] for row in requests],
            [200, 200, 403, 403, 200, 200, 200],
        )
        self.assertTrue(all(row["body_retained"] is False for row in requests))
        self.assertTrue(all(row["access_key_header_sent"] is False for row in requests))
        self.assertTrue(all(row["token_header_sent"] is False for row in requests))
        self.assertTrue(all(len(row["sha256"]) == 64 for row in requests))
        self.assertEqual(requests[-2]["application_message"], "Invalid Access Key")
        self.assertEqual(requests[-1]["application_message"], "Invalid input.")
        self.assertTrue(all(row["application_status"] == "Error" for row in requests[-2:]))
        self.assertTrue(all(row["result_is_array"] is False for row in requests[-2:]))

    def test_inventory_counter_or_hash_tampering_is_rejected(self) -> None:
        changed = json.loads(json.dumps(PINNED_RETRIEVAL_INVENTORY))
        changed["network_requests"] = 6
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            validate_retrieval_inventory(changed)
        changed = json.loads(json.dumps(PINNED_RETRIEVAL_INVENTORY))
        changed["controlled_http_requests"][0]["sha256"] = "0" * 64
        with self.assertRaises(SingaporeURAPlanningDecisionError):
            validate_retrieval_inventory(changed)

    def test_access_rights_and_robots_findings_do_not_overclaim(self) -> None:
        definition = source_definition()
        access = definition["access"]
        self.assertTrue(access["registration_required"])
        self.assertTrue(access["access_key_required"])
        self.assertTrue(access["daily_token_required"])
        self.assertFalse(access["registration_performed"])
        self.assertFalse(access["captcha_automation_performed"])
        self.assertFalse(access["access_key_present_during_assessment"])
        self.assertFalse(access["daily_token_present_during_assessment"])
        self.assertFalse(access["authorized_row_capture_exists"])
        self.assertEqual(RIGHTS_POLICY["api_specific_open_data_licence_url"], OPEN_DATA_LICENCE_URL)
        self.assertEqual(RIGHTS_POLICY["api_terms_of_service_url"], API_TERMS_URL)
        self.assertTrue(RIGHTS_POLICY["attribution_required_for_future_authorized_use"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        self.assertFalse(RIGHTS_POLICY["source_record_capture_authorized_in_this_assessment"])
        robots = validate_release_bundle(PINNED_RELEASE)["source_inventory"]["robots_findings"]
        self.assertEqual(robots["http_status"], 200)
        self.assertFalse(robots["generic_user_agent_group_present"])
        self.assertEqual(robots["googlebot_disallow_value"], "")
        self.assertEqual(robots["searchsg_disallow_value"], "")
        self.assertFalse(robots["robots_is_access_or_reuse_permission"])

    def test_classification_vocabulary_is_predeclared_and_conservative(self) -> None:
        contract = source_definition()["classification_contract"]
        self.assertEqual(tuple(contract["direct_terms"]), DIRECT_TERMS)
        self.assertEqual(tuple(contract["review_terms"]), REVIEW_TERMS)
        self.assertEqual(
            tuple(contract["forbidden_standalone_terms"]),
            FORBIDDEN_STANDALONE_TERMS,
        )
        self.assertFalse(contract["review_terms_are_direct_matches"])
        self.assertTrue(contract["vocabulary_is_predeclared_before_capture"])
        self.assertNotIn("DC", DIRECT_TERMS)
        self.assertNotIn("cloud", DIRECT_TERMS)

    def test_record_unit_development_polygon_and_downstream_import_stay_separate(
        self,
    ) -> None:
        definition = source_definition()
        unit = definition["unit_contract"]
        self.assertEqual(unit["deduplication_key"], "exact dr_id")
        self.assertTrue(unit["one_retained_row_per_dr_id"])
        self.assertFalse(unit["automatic_merge_by_address_or_lot_permitted"])
        self.assertFalse(unit["planning_decision_is_atlas_project"])
        self.assertFalse(unit["planning_decision_is_atlas_site"])
        polygons = definition["development_register_boundary"]
        self.assertEqual(polygons["development_register_url"], DEVELOPMENT_REGISTER_URL)
        self.assertTrue(polygons["polygon_source_is_separate"])
        self.assertFalse(polygons["joined_to_planning_decisions"])
        self.assertFalse(polygons["exact_join_key_documented"])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["construction_master_import_permitted"])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["construction_map_import_permitted"])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["current_coverage_ledger_import_permitted"])

    def test_regulatory_lifecycle_and_metrics_never_become_physical_facts(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        lifecycle = bundle["assessment"]["lifecycle_boundary"]
        self.assertFalse(lifecycle["planning_decision_is_physical_lifecycle"])
        self.assertIsNone(lifecycle["regulatory_status"])
        self.assertIsNone(lifecycle["physical_construction_status"])
        self.assertIsNone(lifecycle["physical_operation_status"])
        inference = bundle["definition"]["inference_policy"]
        for field in (
            "coordinates",
            "data_centre_capacity",
            "data_centre_type",
            "facility_operator",
            "gross_facility_power_mw",
            "it_capacity_mw",
            "physical_lifecycle_status",
        ):
            self.assertIsNone(inference[field])
        metrics = bundle["assessment"]["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        for field in (
            "annual_energy_consumption_mwh",
            "backup_generation_capacity_mw",
            "gross_facility_power_mw",
            "it_capacity_mw",
            "metric_scope",
            "pue",
            "source_metric_statement_count",
        ):
            self.assertIsNone(metrics[field])

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        inventory = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        for filename, expected in derive_release_files(inventory).items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), expected)

    def test_frozen_modes_manifest_content_tamper_and_symlink_rejection(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            {entry.name for entry in PINNED_RELEASE.iterdir()}, EXPECTED_FILES
        )
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.iterdir():
            self.assertEqual(entry.stat().st_mode & 0o777, 0o444)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            assessment = copied / "assessment.json"
            assessment.chmod(0o644)
            assessment.write_bytes(assessment.read_bytes() + b" ")
            assessment.chmod(0o444)
            with self.assertRaisesRegex(
                SingaporeURAPlanningDecisionError,
                "canonical JSON|derived file differs",
            ):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            inventory = copied / "retrieval-inventory.json"
            inventory.chmod(0o644)
            inventory.write_bytes(inventory.read_bytes() + b" ")
            inventory.chmod(0o444)
            with self.assertRaisesRegex(
                SingaporeURAPlanningDecisionError,
                "canonical JSON",
            ):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            with self.assertRaisesRegex(
                SingaporeURAPlanningDecisionError,
                "modes are not frozen",
            ):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            copied.chmod(0o755)
            observations = copied / "observations.jsonl"
            observations.chmod(0o644)
            observations.unlink()
            observations.symlink_to(PINNED_RELEASE / "observations.jsonl")
            with self.assertRaisesRegex(
                SingaporeURAPlanningDecisionError,
                "regular files without symlinks",
            ):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            external = Path(temporary) / "definition.json"
            external.symlink_to(SOURCE_DEFINITION)
            with self.assertRaisesRegex(
                SingaporeURAPlanningDecisionError,
                "regular file",
            ):
                validate_release_bundle(
                    PINNED_RELEASE,
                    definition_path=external,
                )

    def test_validator_and_builder_are_offline_and_reproducible(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["validation_mode"], "offline")
        self.assertEqual(payload["validation_network_requests"], 0)
        self.assertEqual(payload["controlled_audit_requests"], 7)
        self.assertEqual(payload["result_bearing_requests"], 0)
        self.assertEqual(payload["source_rows"], 0)
        self.assertIsNone(payload["result_count"])
        self.assertIsNone(payload["decision_count"])

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
            self.assertEqual(payload["controlled_audit_requests"], 7)
            self.assertEqual(payload["credentialed_requests"], 0)
            self.assertEqual(payload["result_bearing_requests"], 0)
            self.assertEqual(payload["source_rows"], 0)
            self.assertEqual(
                definition.read_bytes(), canonical_json(source_definition())
            )
            built = validate_release_bundle(release, definition_path=definition)
            pinned = validate_release_bundle(PINNED_RELEASE)
            self.assertEqual(built["manifest"], pinned["manifest"])
            with self.assertRaises(SingaporeURAPlanningDecisionError):
                build_main(
                    [
                        "--output",
                        str(release),
                        "--definition",
                        str(definition),
                    ]
                )

    def test_external_definition_and_release_hashes_are_pinned(self) -> None:
        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes()),
            "a023a1708691209fdb15e5d2249a5e0656d8ff7b6a075b9d41bf5d050b0a1e33",
        )
        self.assertEqual(
            sha256_bytes(SOURCE_DEFINITION.read_bytes()),
            "fbdb252b125cb647b0a440e1010446e31c80cf7c545449e505baafe96a14e5c3",
        )
        self.assertEqual(
            sha256_bytes(
                (PINNED_RELEASE / "retrieval-inventory.json").read_bytes()
            ),
            "7c9ec4f93f4344855c89b1619b2f7a6bf93354df187f2ed583390cdfcf478063",
        )


if __name__ == "__main__":
    unittest.main()
