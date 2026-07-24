from __future__ import annotations

import base64
from collections import Counter
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.error import URLError

from datacenter_atlas.epbc_referrals import (
    ASSESSMENT_FORMAT,
    ENTITY_LIST_ID,
    EPBCReferralsError,
    EVIDENCE_BOUNDARY,
    EXPECTED_CLASSIFICATION_COUNTS,
    EXPECTED_CLOSED_SET_SHA256,
    EXPECTED_NETWORK_REQUESTS,
    EXPECTED_POWER_SCOPE_SHA256,
    EXPECTED_QUERY_COUNTS,
    EXPECTED_UNIQUE_REFERRALS,
    GRID_ENDPOINT,
    MANIFEST_FILENAME,
    MAX_NETWORK_REQUESTS,
    PAGE_SIZE,
    RELEASE_FILENAMES,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_PHRASES,
    SORT_EXPRESSION,
    VIEW_ID,
    WEBSITE_ID,
    canonical_json,
    classify_result,
    extract_scoped_power_statements,
    grid_request_document,
    is_frozen_release,
    merge_query_rows,
    parse_all_referrals_contract,
    parse_antiforgery_token,
    parse_detail_page,
    parse_grid_response,
    sha256_bytes,
    sha256_file,
    source_definition,
    thaw_for_test,
    transport_expression,
    validate_capture_state_hash,
    validate_release_bundle,
    verify_portal_terms,
    write_release_bundle,
)
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str):
    path = _SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load EPBC script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FETCH_MODULE = _load_script("fetch_build_epbc_referrals")
BoundedFetcher = _FETCH_MODULE.BoundedFetcher
validate_main = _load_script("validate_epbc_referrals").main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _release_documents() -> dict[str, bytes]:
    return {name: (PINNED_RELEASE / name).read_bytes() for name in RELEASE_FILENAMES}


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


def _grid_layout(
    tooltip: str = "To search on partial text, use the asterisk (*) wildcard character.",
) -> str:
    layout = [
        {
            "Base64SecureConfiguration": "x" * 128,
            "Columns": [],
            "Configuration": {
                "EntityName": "incident",
                "FilterQueryStringParameterName": "filter",
                "PageQueryStringParameterName": "page",
                "PageSize": PAGE_SIZE,
                "PrimaryKeyName": "incidentid",
                "Search": {
                    "Enabled": True,
                    "SearchQueryStringParameterName": "query",
                    "TooltipText": tooltip,
                },
                "SortQueryStringParameterName": "sort",
                "ViewId": VIEW_ID,
            },
            "Id": VIEW_ID,
            "SortExpression": SORT_EXPRESSION,
        }
    ]
    return base64.b64encode(json.dumps(layout).encode("utf-8")).decode("ascii")


def _grid_row(record_id: str, *, title: str = "Example Data Centre") -> dict[str, object]:
    values = {
        "incidentid": record_id,
        "mara_industrytype": "Telecommunications",
        "mara_location": "Example locality",
        "mara_primarymarajurisdiction": "Example jurisdiction",
        "mara_proposerapprovalholdername": "Example Pty Ltd",
        "mara_validdate": "1/01/2026",
        "statecode": "Active",
        "statuscode": "Assessment Commenced",
        "ticketnumber": "2026/10000",
        "title": title,
    }
    return {
        "Attributes": [
            {"DisplayValue": value, "Name": name}
            for name, value in values.items()
        ],
        "Id": record_id,
    }


class EPBCReferralsTests(unittest.TestCase):
    def test_pinned_bundle_validates_offline_and_is_metadata_only(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["format"], ASSESSMENT_FORMAT)
        self.assertEqual(
            bundle["assessment"]["release_decision"]["status"],
            "rights_blocked_metadata_only",
        )
        self.assertEqual(
            bundle["query_summary"]["classification_counts"],
            EXPECTED_CLASSIFICATION_COUNTS,
        )
        self.assertEqual(
            bundle["query_summary"]["unique_referral_count"],
            EXPECTED_UNIQUE_REFERRALS,
        )
        self.assertIsNone(
            bundle["assessment"]["coverage_assessment"][
                "physical_unique_site_count"
            ]
        )
        self.assertFalse(
            bundle["assessment"]["coverage_assessment"]["australia_complete"]
        )
        self.assertEqual(
            bundle["retrieval_inventory"]["network_request_count"],
            EXPECTED_NETWORK_REQUESTS,
        )

    def test_rights_fail_closed_and_general_notice_does_not_override_terms(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["rights_assessment"], RIGHTS_POLICY)
        self.assertFalse(RIGHTS_POLICY["commercial_reuse_permission_clear"])
        self.assertFalse(
            RIGHTS_POLICY["portal_material_reproduction_or_distribution_permission_clear"]
        )
        self.assertTrue(RIGHTS_POLICY["release_is_metadata_only"])
        self.assertFalse(bundle["assessment"]["release_decision"]["atlas_merge_permitted"])

    def test_release_contains_no_rows_or_raw_portal_values(self) -> None:
        self.assertFalse(any(PINNED_RELEASE.rglob("raw")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.jsonl")))
        self.assertEqual(
            {child.name for child in PINNED_RELEASE.iterdir()},
            RELEASE_FILENAMES | {"manifest.json", "manifest.sha256"},
        )
        released = b"\n".join(
            child.read_bytes()
            for child in PINNED_RELEASE.iterdir()
            if child.is_file()
        ).decode("utf-8")
        for restricted_value in (
            "2025/10391",
            "2026/10560",
            "Project Ares",
            "Huntingwood",
            "96MW",
            "16 GWh",
            "1,038 MW",
        ):
            self.assertNotIn(restricted_value, released)

    def test_exact_search_contract_counts_and_hashes_are_pinned(self) -> None:
        summary = validate_release_bundle(PINNED_RELEASE)["query_summary"]
        self.assertEqual(
            [row["phrase"] for row in summary["queries"]], list(SEARCH_PHRASES)
        )
        self.assertEqual(
            [row["transport_expression"] for row in summary["queries"]],
            ["*data centre*", "*data center*", "*datacentre*"],
        )
        self.assertEqual(
            {row["phrase"]: row["item_count"] for row in summary["queries"]},
            EXPECTED_QUERY_COUNTS,
        )
        self.assertEqual(summary["closed_set_sha256"], EXPECTED_CLOSED_SET_SHA256)
        self.assertEqual(
            summary["power_scope_assessment"]["scoped_statement_set_sha256"],
            EXPECTED_POWER_SCOPE_SHA256,
        )
        self.assertEqual(summary["power_scope_assessment"]["raw_statement_occurrences"], 8)
        self.assertFalse(summary["power_scope_assessment"]["values_released"])

    def test_capture_state_self_hash_binds_every_quarantined_field(self) -> None:
        unhashed = {
            "format": "datacenter-atlas-epbc-quarantine-capture-v1",
            "network_attempt_count": EXPECTED_NETWORK_REQUESTS,
        }
        capture = unhashed | {
            "capture_state_sha256": sha256_bytes(canonical_json(unhashed))
        }
        self.assertEqual(
            validate_capture_state_hash(capture), capture["capture_state_sha256"]
        )
        capture["network_attempt_count"] += 1
        with self.assertRaisesRegex(EPBCReferralsError, "hash mismatch"):
            validate_capture_state_hash(capture)

    def test_source_definition_is_exact_and_uses_only_official_hosts(self) -> None:
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )
        definition = source_definition()
        self.assertEqual(definition["scope"]["search_phrases_exact"], list(SEARCH_PHRASES))
        self.assertEqual(
            definition["retrieval_policy"]["max_network_requests"],
            MAX_NETWORK_REQUESTS,
        )
        self.assertGreaterEqual(
            definition["retrieval_policy"]["minimum_request_interval_seconds"], 1
        )
        self.assertFalse(
            definition["retrieval_policy"]["attachments_or_documents_fetched"]
        )
        self.assertFalse(
            definition["retrieval_policy"]["public_comments_or_submissions_fetched"]
        )

    def test_entity_grid_contract_parser_requires_documented_wildcard(self) -> None:
        body = f"""
        <div id="EntityList{ENTITY_LIST_ID}">
          <div class="entity-grid entitylist"
            data-get-url="/_services/entity-grid-data.json/{WEBSITE_ID}"
            data-selected-view="{VIEW_ID}"
            data-view-layouts='{_grid_layout()}'></div>
        </div>
        """.encode()
        contract = parse_all_referrals_contract(body)
        self.assertEqual(contract["endpoint"], GRID_ENDPOINT)
        self.assertEqual(contract["view_id"], VIEW_ID)
        self.assertEqual(contract["entity_list_id"], ENTITY_LIST_ID)
        self.assertEqual(len(contract["base64_secure_configuration"]), 128)
        request = grid_request_document(contract, phrase="data centre", page=1)
        self.assertEqual(request["search"], "*data centre*")
        self.assertEqual(request["timezoneOffset"], 0)
        self.assertEqual(request["pageSize"], 10)

        invalid_layout = _grid_layout(
            "To search on partial text, use the asterisk (*) substring character."
        )
        invalid = body.replace(_grid_layout().encode(), invalid_layout.encode())
        with self.assertRaisesRegex(EPBCReferralsError, "wildcard"):
            parse_all_referrals_contract(invalid)

    def test_grid_response_preserves_rows_and_exact_id_deduplication(self) -> None:
        record_id = "11111111-1111-4111-8111-111111111111"
        response = canonical_json(
            {
                "ItemCount": 1,
                "MoreRecords": False,
                "NextPagePagingCookie": None,
                "PageCount": 1,
                "PageNumber": 1,
                "PageSize": 10,
                "Records": [_grid_row(record_id)],
            }
        )
        parsed_centre = parse_grid_response(
            response, phrase="data centre", expected_page=1
        )
        parsed_center = parse_grid_response(
            response, phrase="data center", expected_page=1
        )
        merged = merge_query_rows(
            {
                "data centre": parsed_centre["records"],
                "data center": parsed_center["records"],
                "datacentre": [],
            }
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]["matched_queries"], ["data centre", "data center"]
        )
        self.assertEqual(merged[0]["process_status"], "Assessment Commenced")

    def test_detail_parser_and_power_scope_do_not_promote_unsafe_values(self) -> None:
        record_id = "11111111-1111-4111-8111-111111111111"
        description = (
            "&lt;p&gt;Construction of a 96MW data centre with 500 MW IT capacity. "
            "Supporting solar generation is 1,200 MWp, battery storage is 16 GWh, "
            "and gas-fired generation is 1,038 MW.&lt;/p&gt;"
        )
        body = f"""
        <div class="applicationTitle">Example Data Centre</div>
        <span class="fieldLabel">EPBC Number: </span><span class="fieldtext">2026/10000</span>
        <span class="fieldLabel">Project Status: </span>
        <span class="fieldtext">Assessment Commenced</span>
        <input id="mara_personproposingaction_name" value="Example Pty Ltd" />
        <input id="mara_industrytype_name" value="Telecommunications" />
        <input id="mara_primarymarajurisdiction_name" value="Example jurisdiction" />
        <input id="mara_location" value="Example locality" />
        <input id="EntityFormView_EntityID" value="{record_id}" />
        <textarea id="mara_proposedactionoverview">{description}</textarea>
        <script>const id = "{record_id}";</script>
        """.encode()
        detail = parse_detail_page(body, expected_record_id=record_id)
        self.assertEqual(detail["epbc_number"], "2026/10000")
        self.assertEqual(
            classify_result(detail["title"], detail["description_plain_text"]),
            "direct_data_centre_project",
        )
        statements = extract_scoped_power_statements(detail["description_plain_text"])
        self.assertEqual(len(statements), 5)
        self.assertEqual(
            Counter(row["role"] for row in statements),
            Counter(
                {
                    "battery_storage_energy_capacity": 1,
                    "data_centre_facility_capacity_scope_unspecified": 1,
                    "data_centre_it_capacity": 1,
                    "supporting_gas_generation_capacity": 1,
                    "supporting_solar_generation_capacity": 1,
                }
            ),
        )
        self.assertTrue(
            next(row for row in statements if row["matched_text"] == "500 MW")[
                "is_data_centre_it_capacity"
            ]
        )
        for row in statements:
            self.assertFalse(row["annual_energy_consumption"])
        for role in (
            "supporting_gas_generation_capacity",
            "supporting_solar_generation_capacity",
        ):
            self.assertFalse(
                next(row for row in statements if row["role"] == role)[
                    "is_data_centre_it_capacity"
                ]
            )

    def test_portal_terms_parser_requires_every_restriction(self) -> None:
        body = b"""
        <p>You are prohibited from reproducing Our Material and from reselling or
        distributing Our Material, including re-transmitting the Our Material.</p>
        <p>You may download Our Material solely for your own use and must not make
        it available to third parties on any commercial terms.</p>
        """
        self.assertTrue(all(verify_portal_terms(body).values()))
        with self.assertRaisesRegex(EPBCReferralsError, "rights language"):
            verify_portal_terms(body.replace(b"commercial terms", b"other terms"))

    def test_antiforgery_token_is_parsed_but_never_in_release(self) -> None:
        token = "a" * 80
        body = (
            f'<input name="__RequestVerificationToken" type="hidden" value="{token}" />'
        ).encode()
        self.assertEqual(parse_antiforgery_token(body), token)
        inventory = validate_release_bundle(PINNED_RELEASE)["retrieval_inventory"]
        token_row = next(
            row for row in inventory["retrievals"] if row["request_id"] == "token"
        )
        self.assertFalse(token_row["raw_artifact_retained_in_operator_quarantine"])
        self.assertNotIn(token, (PINNED_RELEASE / "retrieval-inventory.json").read_text())

    def test_fetcher_enforces_cap_interval_and_retry_attempt_accounting(self) -> None:
        with self.assertRaisesRegex(EPBCReferralsError, "interval"):
            BoundedFetcher(timeout=1, min_interval=0, request_cap=1, max_attempts=1)
        with self.assertRaisesRegex(EPBCReferralsError, "cap"):
            BoundedFetcher(
                timeout=1,
                min_interval=1,
                request_cap=MAX_NETWORK_REQUESTS + 1,
                max_attempts=1,
            )
        fetcher = BoundedFetcher(
            timeout=1, min_interval=1, request_cap=1, max_attempts=2
        )
        fetcher._opener = mock.Mock()
        fetcher._opener.open.side_effect = URLError("synthetic failure")
        with mock.patch.object(_FETCH_MODULE.time, "sleep"):
            with self.assertRaisesRegex(EPBCReferralsError, "cap reached"):
                fetcher.fetch(
                    request_id="synthetic",
                    endpoint_kind="test",
                    url="https://epbcpublicportal.environment.gov.au/all-referrals/",
                    retain_raw=False,
                )
        self.assertEqual(fetcher.network_attempts, 1)

    def test_manifest_hashes_modes_and_source_inventory_are_exact(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            (PINNED_RELEASE / "manifest.sha256").read_text(encoding="ascii"),
            f"{sha256_file(PINNED_RELEASE / MANIFEST_FILENAME)}  {MANIFEST_FILENAME}\n",
        )
        source_inventory = bundle["source_inventory"]
        self.assertEqual(source_inventory["raw_artifact_count_in_release"], 0)
        retained = [
            row
            for row in bundle["retrieval_inventory"]["retrievals"]
            if row["raw_artifact_retained_in_operator_quarantine"]
        ]
        self.assertEqual(source_inventory["quarantined_raw_artifact_count"], 7)
        self.assertEqual(
            source_inventory["quarantined_raw_bytes"],
            sum(row["bytes"] for row in retained),
        )

    def test_same_documents_rebuild_to_same_frozen_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            write_release_bundle(output, _release_documents())
            validate_release_bundle(output)
            self.assertTrue(is_frozen_release(output))
            for filename in RELEASE_FILENAMES | {"manifest.json", "manifest.sha256"}:
                self.assertEqual(
                    (output / filename).read_bytes(),
                    (PINNED_RELEASE / filename).read_bytes(),
                )

    def test_validator_rejects_tamper_extra_files_and_writable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment = json.loads((copied / "assessment.json").read_text())
            assessment["coverage_assessment"]["physical_unique_site_count"] = 2
            (copied / "assessment.json").write_bytes(canonical_json(assessment))
            with self.assertRaises(EPBCReferralsError):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            (copied / "unexpected.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(EPBCReferralsError, "file set"):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            copied.chmod(0o755)
            with self.assertRaisesRegex(EPBCReferralsError, "not frozen"):
                validate_release_bundle(copied)

    def test_validator_cli_is_offline_and_reports_null_site_count(self) -> None:
        output = io.StringIO()
        with mock.patch("socket.socket", side_effect=AssertionError("network used")):
            with redirect_stdout(output):
                self.assertEqual(validate_main([str(PINNED_RELEASE)]), 0)
        report = json.loads(output.getvalue())
        self.assertIsNone(report["unique_physical_site_count"])
        self.assertEqual(report["status"], "rights_blocked_metadata_only")

    def test_evidence_boundary_never_treats_process_as_lifecycle(self) -> None:
        self.assertEqual(
            validate_release_bundle(PINNED_RELEASE)["assessment"]["evidence_boundary"],
            EVIDENCE_BOUNDARY,
        )
        self.assertTrue(EVIDENCE_BOUNDARY["portal_status_is_process_only"])
        self.assertFalse(EVIDENCE_BOUNDARY["construction_verified"])
        self.assertFalse(EVIDENCE_BOUNDARY["operation_verified"])
        self.assertIsNone(EVIDENCE_BOUNDARY["atlas_lifecycle_status"])
        self.assertFalse(
            EVIDENCE_BOUNDARY["supporting_generation_or_storage_mapped_to_it_load"]
        )


if __name__ == "__main__":
    unittest.main()
