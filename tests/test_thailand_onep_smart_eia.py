from __future__ import annotations

from contextlib import redirect_stdout
import ast
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.thailand_onep_smart_eia import (
    DATASET_NAME,
    DATASET_TITLE,
    DOWNSTREAM_IMPORT_POLICY,
    ENGLISH_DIRECT_TERMS,
    EXPECTED_FILES,
    LICENCE_LABEL,
    MAX_BODY_BYTES,
    MAX_CANDIDATE_UNION,
    MAX_RECORDS,
    MAX_REDIRECTS,
    MAX_REVIEW_SHARD,
    PACKAGE_SHOW_URL,
    PINNED_RETRIEVAL_INVENTORY,
    PINNED_SNAPSHOT_AUDIT,
    RELEASE_ID,
    REQUEST_TIMEOUT_SECONDS,
    RESOURCE_URL,
    SOURCE_ID,
    THAI_DIRECT_TERMS,
    ThailandONEPSmartEIAError,
    approval_date_gregorian,
    approval_year_gregorian,
    audit_capture_bodies,
    build_review_shards,
    canonical_json,
    derive_complete_candidates,
    is_frozen_release,
    matched_terms,
    sha256_bytes,
    source_definition,
    stable_observation_id,
    thaw_for_test,
    validate_release_bundle,
    validate_retrieval_inventory,
    validate_snapshot_audit,
    validate_snapshot_payload,
    write_release_bundle,
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


validate_main = _load_script("validate_thailand_onep_smart_eia").main


def source_row(**changes: str) -> dict[str, str]:
    row = {
        "approve_date": "12/09/2567",
        "approve_number": "ทส 1009.5/1",
        "category": "อาคาร การจัดสรรที่ดิน และบริการชุมชน",
        "code": "256709-01",
        "name": "โครงการศูนย์ข้อมูล คลาวด์ ระยอง",
        "owner": "บริษัทตัวอย่าง จำกัด",
        "province": "ระยอง",
        "reporter": "บริษัทที่ปรึกษา จำกัด",
        "year": "2567",
        "zone": "ภาคตะวันออก",
    }
    row.update(changes)
    return row


def complete_payload(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "currentPage": 1,
        "dataList": rows,
        "totalCount": len(rows),
        "totalPage": 1,
    }


def package_payload() -> dict[str, object]:
    return {
        "help": "https://onep.gdcatalog.go.th/api/3/action/help_show?name=package_show",
        "result": {
            "accessible_condition": "ไม่มี",
            "data_category": "ข้อมูลสาธารณะ",
            "last_updated_date": "2024-07-01",
            "license_id": LICENCE_LABEL,
            "license_title": LICENCE_LABEL,
            "metadata_modified": "2024-07-08T07:52:31.733119",
            "name": DATASET_NAME,
            "private": False,
            "resources": [
                {
                    "datastore_active": False,
                    "datastore_contains_all_records_of_source_file": False,
                    "format": "JSON",
                    "resource_last_updated_date": "2024-01-30",
                    "url": RESOURCE_URL,
                }
            ],
            "title": DATASET_TITLE,
        },
        "success": True,
    }


class ThailandONEPSmartEIATests(unittest.TestCase):
    def test_module_has_no_silent_duplicate_literal_dict_keys(self) -> None:
        module_path = (
            PROJECT_ROOT / "datacenter_atlas" / "thailand_onep_smart_eia.py"
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

    def test_exact_thai_english_and_idc_terms_are_high_precision(self) -> None:
        for term in THAI_DIRECT_TERMS:
            with self.subTest(term=term):
                self.assertIn(term, matched_terms(f"โครงการ {term} แห่งใหม่"))
        for term in ENGLISH_DIRECT_TERMS:
            with self.subTest(term=term):
                self.assertIn(term, matched_terms(f"New {term.upper()} campus"))
        self.assertIn("IDC", matched_terms("New IDC campus"))
        self.assertFalse(matched_terms("IDCard service building"))
        self.assertFalse(matched_terms("myidcservice building"))
        self.assertFalse(matched_terms("ศูนย์ข้อมูลทั่วไป"))
        self.assertIn(
            "ศูนย์ข้อมูล+context",
            matched_terms("โครงการศูนย์ข้อมูล คลาวด์ ระยอง"),
        )
        self.assertFalse(matched_terms("data centering laboratory"))

    def test_complete_snapshot_derives_tier_c_report_not_lifecycle(self) -> None:
        payload = complete_payload([source_row()])
        summary = validate_snapshot_payload(payload, require_complete=True)
        self.assertTrue(summary["complete"])
        observations = derive_complete_candidates(payload)
        self.assertEqual(len(observations), 1)
        row = observations[0]
        self.assertEqual(row["source_tier"], "C")
        self.assertEqual(
            row["source_unit"],
            "ONEP-approved environmental-assessment report observation",
        )
        for field in (
            "annual_energy_consumption_mwh",
            "coordinates",
            "data_centre_type",
            "gross_facility_power_mw",
            "it_capacity_mw",
            "lifecycle_status",
            "operator",
            "project_status",
            "pue",
        ):
            self.assertIsNone(row[field])
        self.assertFalse(row["owner_is_operator"])
        self.assertEqual(row["approval_date_gregorian"], "2024-09-12")

    def test_future_dated_complete_snapshot_fails_before_derivation(self) -> None:
        payload = complete_payload(
            [
                source_row(
                    approve_date="30/12/2569",
                    code="256912-99",
                    year="2569",
                )
            ]
        )
        audit_summary = validate_snapshot_payload(payload, require_complete=False)
        self.assertTrue(audit_summary["complete"])
        self.assertEqual(
            audit_summary["future_dated_row_count_at_assessment_date"], 1
        )
        with self.assertRaisesRegex(
            ThailandONEPSmartEIAError, "approval dates after the assessment date"
        ):
            validate_snapshot_payload(payload, require_complete=True)
        with self.assertRaisesRegex(
            ThailandONEPSmartEIAError, "approval dates after the assessment date"
        ):
            derive_complete_candidates(payload)

    def test_deterministic_ids_deduplication_and_collisions(self) -> None:
        row = source_row()
        self.assertEqual(stable_observation_id(row), stable_observation_id(dict(row)))
        observations = derive_complete_candidates(complete_payload([row, dict(row)]))
        self.assertEqual(len(observations), 1)
        conflicting = dict(row, name="โครงการ IDC อื่น")
        with self.assertRaisesRegex(
            ThailandONEPSmartEIAError, "conflicting ONEP source-key collision"
        ):
            derive_complete_candidates(complete_payload([row, conflicting]))
        second = source_row(code="256709-02")
        self.assertNotEqual(stable_observation_id(row), stable_observation_id(second))

    def test_malformed_truncated_and_capped_snapshots_fail_closed(self) -> None:
        truncated = {
            "currentPage": 1,
            "dataList": [source_row()],
            "totalCount": 2,
            "totalPage": 2,
        }
        self.assertFalse(validate_snapshot_payload(truncated, require_complete=False)["complete"])
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "paginated or truncated"):
            derive_complete_candidates(truncated)
        capped = dict(truncated, totalCount=MAX_RECORDS + 1)
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "record cap"):
            validate_snapshot_payload(capped, require_complete=False)
        malformed = complete_payload([source_row()])
        malformed["dataList"] = [dict(source_row(), unexpected="field")]
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "row schema changed"):
            validate_snapshot_payload(malformed, require_complete=True)
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "duplicate JSON key"):
            audit_capture_bodies(
                b'{"success":true,"success":false}',
                canonical_json(complete_payload([])),
                "นโยบายการคุ้มครองข้อมูลส่วนบุคคล".encode(),
                "ไม่พบข้อมูล".encode(),
            )

    def test_buddhist_era_date_and_year_conversion_are_strict(self) -> None:
        self.assertEqual(approval_date_gregorian("18/07/2569"), "2026-07-18")
        self.assertEqual(approval_year_gregorian("2535"), 1992)
        for invalid in ("18-07-2569", "31/02/2569", "18/07/9999"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ThailandONEPSmartEIAError):
                    approval_date_gregorian(invalid)
        with self.assertRaises(ThailandONEPSmartEIAError):
            approval_year_gregorian("69")

    def test_review_shards_are_term_year_province_and_never_truncated(self) -> None:
        observations = derive_complete_candidates(complete_payload([source_row()]))
        shards = build_review_shards(observations)
        self.assertEqual(len(shards), 1)
        self.assertEqual(shards[0]["approval_year_gregorian"], "2024")
        self.assertEqual(shards[0]["province"], "ระยอง")
        self.assertEqual(shards[0]["exact_match_term"], "ศูนย์ข้อมูล+context")
        too_large = [
            {
                "approval_date_gregorian": "2024-09-12",
                "matched_terms": ["data center"],
                "observation_id": f"id-{index:04d}",
                "province": "ระยอง",
            }
            for index in range(MAX_REVIEW_SHARD + 1)
        ]
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "review shard exceeds cap"):
            build_review_shards(too_large)
        with self.assertRaisesRegex(ThailandONEPSmartEIAError, "candidate union exceeds"):
            build_review_shards(too_large * 2)

    def test_offline_capture_audit_binds_raw_canonical_schema_and_counts(self) -> None:
        package_body = canonical_json(package_payload())
        snapshot_body = canonical_json(complete_payload([source_row()]))
        audit = audit_capture_bodies(
            package_body,
            snapshot_body,
            "นโยบายการคุ้มครองข้อมูลส่วนบุคคล".encode(),
            "ไม่พบข้อมูล".encode(),
        )
        self.assertEqual(audit["package"]["raw_sha256"], sha256_bytes(package_body))
        self.assertEqual(
            audit["snapshot"]["canonical_sha256"], sha256_bytes(snapshot_body)
        )
        self.assertTrue(audit["snapshot"]["complete"])
        self.assertEqual(audit["snapshot"]["returned_code_collision_count"], 0)
        self.assertEqual(audit["matching_diagnostic"]["global_candidate_count"], 1)

    def test_pinned_capture_is_exactly_bounded_and_hash_bound(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        validate_snapshot_audit(PINNED_SNAPSHOT_AUDIT)
        inventory = PINNED_RETRIEVAL_INVENTORY
        self.assertEqual(inventory["controlled_http_requests"], 4)
        self.assertEqual(inventory["package_show_requests"], 1)
        self.assertEqual(inventory["resource_snapshot_requests"], 1)
        self.assertEqual(inventory["pagination_requests"], 0)
        self.assertEqual(inventory["maximum_redirects_per_request"], MAX_REDIRECTS)
        self.assertEqual(inventory["timeout_seconds_per_request"], REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(inventory["maximum_body_bytes"], MAX_BODY_BYTES)
        self.assertTrue(inventory["curl_content_decoding_enabled"])
        self.assertEqual([row["redirect_count"] for row in inventory["controlled_requests"]], [0] * 4)
        self.assertEqual(inventory["controlled_requests"][1]["transfer_bytes"], 15488)
        self.assertEqual(inventory["controlled_requests"][1]["bytes"], 86108)
        self.assertEqual(inventory["controlled_requests"][1]["http_content_encoding"], "gzip")
        self.assertEqual(PINNED_SNAPSHOT_AUDIT["snapshot"]["source_report_total_count"], 13793)
        self.assertEqual(PINNED_SNAPSHOT_AUDIT["snapshot"]["returned_row_count"], 94)
        self.assertEqual(PINNED_SNAPSHOT_AUDIT["snapshot"]["total_page"], 138)
        self.assertEqual(
            PINNED_SNAPSHOT_AUDIT["snapshot"][
                "future_dated_row_count_at_assessment_date"
            ],
            3,
        )
        changed = json.loads(json.dumps(inventory))
        changed["pagination_requests"] = 1
        with self.assertRaises(ThailandONEPSmartEIAError):
            validate_retrieval_inventory(changed)

    def test_definition_preserves_literal_licence_and_no_inference(self) -> None:
        definition = source_definition()
        self.assertEqual(SOURCE_ID, RELEASE_ID)
        self.assertEqual(
            definition["rights_policy"]["dataset_record_reuse_label_literal"],
            "Creative Commons Attributions",
        )
        self.assertIsNone(definition["rights_policy"]["licence_version"])
        self.assertIsNone(definition["rights_policy"]["licence_url"])
        self.assertFalse(
            definition["rights_policy"]["linked_pdf_excel_or_document_rights_inferred"]
        )
        self.assertEqual(definition["network_policy"]["maximum_ckan_package_show_requests"], 1)
        self.assertEqual(definition["network_policy"]["maximum_json_resource_snapshot_requests"], 1)
        self.assertFalse(definition["network_policy"]["pagination_guessing_permitted"])
        self.assertEqual(definition["review_contract"]["candidate_union_cap"], MAX_CANDIDATE_UNION)
        for key, permitted in DOWNSTREAM_IMPORT_POLICY.items():
            if key.endswith("_permitted"):
                self.assertFalse(permitted)

    def test_pinned_release_is_frozen_zero_row_and_self_reproducing(self) -> None:
        self.assertEqual({path.name for path in PINNED_RELEASE.iterdir()}, EXPECTED_FILES)
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        self.assertEqual(
            bundle["assessment"]["atlas_decision"]["status"],
            "snapshot_rejected_incomplete_page_metadata_only",
        )
        self.assertEqual(bundle["assessment"]["atlas_decision"]["retained_source_rows"], 0)
        self.assertEqual((PINNED_RELEASE / "observations.jsonl").read_bytes(), b"")
        self.assertEqual((PINNED_RELEASE / "review-shards.jsonl").read_bytes(), b"")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / RELEASE_ID
            write_release_bundle(output)
            self.assertTrue(is_frozen_release(output))
            reproduced = validate_release_bundle(
                output, definition_path=SOURCE_DEFINITION
            )
            self.assertEqual(reproduced["manifest"], bundle["manifest"])

    def test_release_tampering_and_extra_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            (copied / "observations.jsonl").write_bytes(b"{}\n")
            with self.assertRaises(ThailandONEPSmartEIAError):
                validate_release_bundle(copied, require_frozen=False)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            (copied / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ThailandONEPSmartEIAError, "file set"):
                validate_release_bundle(copied, require_frozen=False)

    def test_validator_script_reports_offline_zero_row_status(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["mode"], "offline_validate")
        self.assertEqual(summary["http_requests"], 0)
        self.assertEqual(summary["retained_source_rows"], 0)
        self.assertTrue(summary["frozen"])
        self.assertRegex(summary["manifest_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
