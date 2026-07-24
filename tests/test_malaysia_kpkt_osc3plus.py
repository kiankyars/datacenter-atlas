from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.malaysia_kpkt_osc3plus import (
    AUDIT_URLS,
    DOWNSTREAM_IMPORT_POLICY,
    END_DATE,
    EXPECTED_FILES,
    MAX_MEETING_PAGE_REQUESTS,
    MAX_MEETING_PAGES_PER_PBT,
    MAX_PBT_CALENDAR_REQUESTS,
    MEETING_PATH_PATTERN,
    MIN_REQUEST_INTERVAL_SECONDS,
    PBT_ALLOWLIST,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_TERMS,
    START_DATE,
    MalaysiaKPKTOSC3PlusError,
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


validate_main = _load_script("validate_malaysia_kpkt_osc3plus").main
build_main = _load_script("build_malaysia_kpkt_osc3plus").main


class MalaysiaKPKTOSC3PlusTests(unittest.TestCase):
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
            "agenda_presentation_item_count",
            "calendar_event_count",
            "meeting_page_count",
            "project_count",
            "result_count",
            "site_count",
        ):
            self.assertIsNone(coverage[field])
        self.assertFalse(coverage["all_union_rows_classified"])
        self.assertEqual(set(coverage["classification_counts"].values()), {None})
        self.assertEqual(assessment["atlas_decision"]["retained_source_rows"], 0)

    def test_exact_allowlist_and_search_literals_are_predeclared(self) -> None:
        self.assertEqual(
            [row["code"] for row in PBT_ALLOWLIST],
            ["MBJB", "MBIP", "MPKu", "MBPG", "MPSep"],
        )
        self.assertEqual(
            SEARCH_TERMS,
            (
                "pusat data",
                "data centre",
                "data center",
                "pusat ibu sawat komputer",
            ),
        )
        self.assertEqual(
            {
                row["code"]: (
                    row["local_authority_area"],
                    row["state"],
                    row["country"],
                )
                for row in PBT_ALLOWLIST
            },
            {
                "MBJB": ("Johor Bahru", "Johor", "Malaysia"),
                "MBIP": ("Iskandar Puteri", "Johor", "Malaysia"),
                "MPKu": ("Kulai", "Johor", "Malaysia"),
                "MBPG": ("Pasir Gudang", "Johor", "Malaysia"),
                "MPSep": ("Sepang", "Selangor", "Malaysia"),
            },
        )
        coverage = source_definition()["coverage_contract"]
        self.assertEqual(coverage["scope_type"], "selected_pbt_allowlist")
        self.assertFalse(coverage["complete_for_malaysia_claimed"])
        self.assertFalse(coverage["complete_for_johor_claimed"])
        self.assertFalse(coverage["complete_for_selangor_claimed"])
        plan = query_plan()
        self.assertEqual(len(plan["rows"]), 5)
        for row, pbt in zip(plan["rows"], PBT_ALLOWLIST, strict=True):
            self.assertEqual(row["pbt_code"], pbt["code"])
            self.assertEqual(row["pbt_url"], pbt["url"])
            self.assertEqual(
                row["status"], "not_executed_rights_scope_not_affirmed"
            )
            self.assertEqual(row["pbt_calendar_network_requests"], 0)
            self.assertEqual(row["meeting_page_network_requests"], 0)
            self.assertIsNone(row["result_count"])
            self.assertIsNone(row["calendar_event_count"])
            self.assertIsNone(row["meeting_page_count"])
            self.assertIsNone(row["agenda_presentation_item_count"])
            self.assertEqual(set(row["classification_counts"].values()), {None})

    def test_future_traversal_is_bounded_discovered_only_and_rights_gated(self) -> None:
        definition = source_definition()
        traversal = definition["future_authorized_traversal_contract"]
        self.assertEqual(traversal["meeting_path_pattern"], MEETING_PATH_PATTERN)
        self.assertTrue(traversal["accept_only_allowlisted_pbt_pages"])
        self.assertTrue(
            traversal["discover_meeting_links_from_allowlisted_pages_only"]
        )
        self.assertFalse(
            traversal["integer_guessing_of_meeting_ids_permitted"]
        )
        self.assertEqual(
            traversal["observation_key"], ["meeting_id", "presentation_ordinal"]
        )
        self.assertEqual(
            traversal["calendar_event_date_start_inclusive"], "2026-01-01"
        )
        self.assertEqual(
            traversal["calendar_event_date_end_inclusive"], "2026-07-18"
        )
        network = definition["network_policy_if_rights_later_clarified"]
        self.assertEqual(MIN_REQUEST_INTERVAL_SECONDS, 5.0)
        self.assertEqual(MAX_PBT_CALENDAR_REQUESTS, 5)
        self.assertEqual(MAX_MEETING_PAGES_PER_PBT, 100)
        self.assertEqual(MAX_MEETING_PAGE_REQUESTS, 500)
        self.assertTrue(network["one_request_at_a_time"])
        self.assertTrue(network["response_body_hash_required"])
        self.assertTrue(network["stop_and_null_counts_on_cap_or_error"])
        self.assertTrue(
            network[
                "stop_before_first_pbt_request_unless_rights_gate_is_affirmative"
            ]
        )

    def test_dbkl_gap_is_preserved_and_cyberjaya_is_not_a_substitute(self) -> None:
        gap = source_definition()["dbkl_coverage_gap"]
        self.assertTrue(gap["dbkl_uncovered"])
        self.assertFalse(gap["mpsep_is_dbkl_substitute"])
        self.assertFalse(gap["cyberjaya_is_kuala_lumpur_city"])
        self.assertEqual(gap["dbkl_requests_performed"], 0)
        self.assertIsNone(gap["dbkl_result_count"])
        mpsep = next(row for row in PBT_ALLOWLIST if row["code"] == "MPSep")
        self.assertIn("not a DBKL substitute", mpsep["role"])
        self.assertEqual(mpsep["state"], "Selangor")
        source_gap = validate_release_bundle(PINNED_RELEASE)["source_inventory"][
            "dbkl_uncovered_gap"
        ]
        self.assertEqual(source_gap["network_requests"], 0)
        self.assertIsNone(source_gap["result_count"])

    def test_rights_and_robots_findings_do_not_overstate_access(self) -> None:
        definition = source_definition()
        self.assertEqual(definition["access"]["service_landing_http_status"], 200)
        self.assertEqual(
            definition["access"]["primary_host_robots_http_status"], 200
        )
        self.assertTrue(
            definition["access"]["primary_host_robots_has_empty_generic_disallow"]
        )
        self.assertEqual(
            set(definition["access"]["policy_endpoint_http_statuses"].values()),
            {500},
        )
        self.assertFalse(RIGHTS_POLICY["affirmative_automated_reuse_scope_found"])
        self.assertFalse(RIGHTS_POLICY["policy_endpoints_available_during_audit"])
        self.assertFalse(RIGHTS_POLICY["robots_rule_is_reuse_permission"])
        self.assertFalse(
            RIGHTS_POLICY["meeting_or_agenda_metadata_publication_permitted"]
        )
        self.assertTrue(
            RIGHTS_POLICY[
                "rights_clarification_required_before_pbt_or_meeting_request"
            ]
        )
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])

    def test_unit_lifecycle_metric_and_pii_boundaries_fail_closed(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        units = assessment["unit_boundary"]
        self.assertEqual(units["source_observation_unit"], "agenda_presentation_item")
        self.assertFalse(units["agenda_presentation_item_is_atlas_project"])
        self.assertFalse(units["agenda_presentation_item_is_atlas_site"])
        lifecycle = assessment["lifecycle_boundary"]
        self.assertFalse(lifecycle["administrative_status_is_physical_lifecycle"])
        self.assertIsNone(lifecycle["physical_construction_status"])
        self.assertIsNone(lifecycle["physical_operation_status"])
        metrics = assessment["metric_boundary"]
        self.assertEqual(metrics["retained_metric_rows"], 0)
        self.assertIsNone(metrics["source_metric_statement_count"])
        self.assertIsNone(metrics["it_capacity_mw"])
        self.assertIsNone(metrics["annual_energy_consumption_mwh"])
        self.assertFalse(assessment["pii_policy"]["applicant_capture_performed"])
        self.assertFalse(assessment["pii_policy"]["contacts_retained"])
        self.assertFalse(assessment["pii_policy"]["meeting_items_retained"])
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

    def test_controlled_audit_is_minimal_hash_bound_and_not_result_bearing(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        inventory = PINNED_RETRIEVAL_INVENTORY
        requests = inventory["controlled_http_requests"]
        self.assertEqual(inventory["controlled_audit_requests"], 6)
        self.assertEqual(inventory["result_bearing_traversal_requests"], 0)
        self.assertEqual(inventory["pbt_calendar_requests"], 0)
        self.assertEqual(inventory["meeting_page_requests"], 0)
        self.assertFalse(inventory["source_capture_started"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertEqual([row["url"] for row in requests], list(AUDIT_URLS))
        self.assertEqual(
            [row["http_status"] for row in requests],
            [200, 200, 500, 500, 500, 500],
        )
        expected_keys = {
            "bytes",
            "content_type",
            "http_status",
            "method",
            "response_date",
            "sha256",
            "url",
        }
        self.assertTrue(all(set(row) == expected_keys for row in requests))
        self.assertTrue(all(len(row["sha256"]) == 64 for row in requests))
        self.assertTrue(all("/pbt/" not in row["url"] for row in requests))
        self.assertTrue(all("/takwim/meeting/" not in row["url"] for row in requests))
        self.assertTrue(all("body" not in key for row in requests for key in row))

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
            with self.assertRaises(MalaysiaKPKTOSC3PlusError):
                validate_release_bundle(copied)

    def test_symlinked_release_entry_and_external_definition_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            copied = temporary_path / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            observations = copied / "observations.jsonl"
            observations.unlink()
            observations.symlink_to(copied / "README.md")
            copied.chmod(0o555)
            for entry in copied.rglob("*"):
                if not entry.is_symlink():
                    entry.chmod(0o444)
            with self.assertRaises(MalaysiaKPKTOSC3PlusError):
                validate_release_bundle(copied)

            definition_link = temporary_path / "definition.json"
            definition_link.symlink_to(SOURCE_DEFINITION)
            with self.assertRaises(MalaysiaKPKTOSC3PlusError):
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
        self.assertEqual(payload["controlled_audit_requests"], 6)
        self.assertEqual(payload["result_bearing_traversal_requests"], 0)
        self.assertEqual(payload["pbt_calendar_requests"], 0)
        self.assertEqual(payload["meeting_page_requests"], 0)
        self.assertNotIn("network_requests", payload)
        self.assertIsNone(payload["result_count"])
        self.assertIsNone(payload["agenda_presentation_item_count"])

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
            self.assertEqual(payload["controlled_audit_requests"], 6)
            self.assertEqual(payload["result_bearing_traversal_requests"], 0)
            self.assertEqual(payload["pbt_calendar_requests"], 0)
            self.assertEqual(payload["meeting_page_requests"], 0)
            self.assertNotIn("network_requests", payload)
            self.assertEqual(
                definition.read_bytes(), canonical_json(source_definition())
            )
            built = validate_release_bundle(release, definition_path=definition)
            pinned = validate_release_bundle(PINNED_RELEASE)
            self.assertEqual(built["manifest"], pinned["manifest"])
            thaw_for_test(release)

    def test_dates_external_definition_and_hashes_are_pinned(self) -> None:
        self.assertEqual(START_DATE.isoformat(), "2026-01-01")
        self.assertEqual(END_DATE.isoformat(), "2026-07-18")
        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes()),
            "d6ba588b5d0f8af6e7bbb0aa36146774db75d664684e0fa62a242b12e0bdbc3c",
        )
        self.assertEqual(
            sha256_bytes(SOURCE_DEFINITION.read_bytes()),
            "51f38721b0a9ba8489204291bbea79af5d9930d32ed3fcdbea224019a3ad35f6",
        )
        self.assertEqual(
            sha256_bytes(
                (PINNED_RELEASE / "retrieval-inventory.json").read_bytes()
            ),
            "d02d60db610d4819157612e3ec12f9eb025f7528e6e163fda8aae79e40c7e83b",
        )


if __name__ == "__main__":
    unittest.main()
