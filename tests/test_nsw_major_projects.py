from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import urlsplit

from datacenter_atlas.nsw_major_projects import (
    EXPECTED_RAW_INVENTORY_SHA256,
    MANIFEST_FILENAME,
    NONTERMINAL_STAGES,
    RELEASE_ID,
    REVIEW_POLICY,
    RIGHTS_POLICY,
    NSWMajorProjectsError,
    canonical_json,
    is_frozen_release,
    parse_list_rows,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _jsonl(filename: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (PINNED_RELEASE / filename)
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def _capture_inputs() -> tuple[dict[str, object], dict[str, bytes]]:
    capture = json.loads(
        (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
    )
    raw = {
        value["filename"]: (PINNED_RELEASE / value["filename"]).read_bytes()
        for value in capture["retrievals"].values()
    }
    return capture, raw


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


class NSWMajorProjectsTests(unittest.TestCase):
    def test_pinned_bundle_validates_offline_with_exact_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        coverage = assessment["coverage_assessment"]
        self.assertEqual(len(bundle["list_observations"]), 44)
        self.assertEqual(coverage["base_rows"], 35)
        self.assertEqual(coverage["modification_rows"], 9)
        self.assertEqual(len(bundle["active_observations"]), 22)
        self.assertEqual(coverage["active_base_rows"], 19)
        self.assertEqual(coverage["active_modification_rows"], 3)
        self.assertEqual(
            assessment["selection_assessment"]["stage_counts"],
            {
                "Assessment": 11,
                "Determination": 19,
                "Exhibition": 1,
                "Prepare EIS": 7,
                "Response to Submissions": 3,
                "Withdrawn": 2,
                "stage_missing": 1,
            },
        )
        self.assertEqual(coverage["construction_verified_rows"], 0)
        self.assertIsNone(coverage["unique_physical_site_count"])

    def test_source_definition_and_rights_scope_are_pinned(self) -> None:
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["rights_assessment"], RIGHTS_POLICY)
        self.assertFalse(RIGHTS_POLICY["raw_html_redistribution_eligible"])
        self.assertTrue(RIGHTS_POLICY["attribution_required"])
        self.assertFalse(RIGHTS_POLICY["source_document_bodies_fetched"])

    def test_all_list_rows_are_preserved_and_blank_stage_is_not_invented(self) -> None:
        rows = _jsonl("list-observations.jsonl")
        self.assertEqual(
            Counter(row["workflow_stage"] or "stage_missing" for row in rows),
            Counter(
                {
                    "Assessment": 11,
                    "Determination": 19,
                    "Exhibition": 1,
                    "Prepare EIS": 7,
                    "Response to Submissions": 3,
                    "Withdrawn": 2,
                    "stage_missing": 1,
                }
            ),
        )
        missing = [row for row in rows if row["workflow_stage"] is None]
        self.assertEqual([row["case_id"] for row in missing], ["SSD-59516710"])
        self.assertFalse(missing[0]["portal_nonterminal_subset_selected"])
        for page in range(5):
            parsed = parse_list_rows(
                (PINNED_RELEASE / f"raw/list-page-{page:05d}.html").read_bytes(),
                page=page,
            )
            self.assertEqual(len(parsed), 8 if page == 4 else 9)

    def test_high_priority_subset_uses_only_exact_list_stage_strings(self) -> None:
        rows = _jsonl("active-planning-observations.jsonl")
        self.assertEqual(
            Counter(row["selection_workflow_stage_exact"] for row in rows),
            Counter(
                {
                    "Assessment": 11,
                    "Prepare EIS": 7,
                    "Response to Submissions": 3,
                    "Exhibition": 1,
                }
            ),
        )
        for row in rows:
            self.assertIn(row["selection_workflow_stage_exact"], NONTERMINAL_STAGES)
            self.assertEqual(row["priority"], "high")
            self.assertEqual(row["evidence_scope"], REVIEW_POLICY)
            self.assertFalse(row["evidence_scope"]["construction_verified"])
            self.assertFalse(row["evidence_scope"]["operation_verified"])
            self.assertIsNone(row["evidence_scope"]["atlas_lifecycle_status"])

    def test_detail_metadata_coordinates_milestones_and_descriptions_are_exact(
        self,
    ) -> None:
        rows = _jsonl("active-planning-observations.jsonl")
        self.assertEqual(
            sum(
                bool(row["detail_metadata"]["department_project_description"])
                for row in rows
            ),
            22,
        )
        self.assertEqual(
            sum(bool(row["detail_metadata"]["coordinates"]) for row in rows), 22
        )
        for row in rows:
            detail = row["detail_metadata"]
            point = detail["coordinates"]
            self.assertEqual(point["crs"], "EPSG:4326")
            self.assertEqual(point["geometry_type"], "Point")
            self.assertEqual(
                detail["current_milestone"], row["selection_workflow_stage_exact"]
            )
            self.assertEqual(
                sum(
                    milestone["state"] == "current"
                    for milestone in detail["milestones"]
                ),
                1,
            )
            self.assertEqual(detail["development_type"], "Data Storage")

        mamre = next(row for row in rows if row["case_id"] == "SSD-92743706")
        self.assertEqual(
            mamre["detail_metadata"]["coordinates"],
            {
                "coordinate_order": "longitude_latitude",
                "crs": "EPSG:4326",
                "geometry_type": "Point",
                "latitude": -33.833794,
                "longitude": 150.784825,
                "source": "detail_page_drupal_settings_geofield",
            },
        )
        self.assertEqual(
            mamre["detail_metadata"]["current_status_text"],
            "Response to Submissions &amp; Prepare Amendment Report",
        )

    def test_power_phrases_remain_untyped_and_context_complete(self) -> None:
        rows = _jsonl("active-planning-observations.jsonl")
        statements = [
            statement
            for row in rows
            for statement in row["detail_metadata"]["power_statements"]
        ]
        self.assertEqual(len(statements), 10)
        self.assertEqual(
            {statement["matched_text"] for statement in statements},
            {
                "1 GW",
                "34.3 MW",
                "38 MW",
                "450 MW",
                "500MVA",
                "612 MW",
                "90MVA",
                "96MW",
                "126 MW",
                "202.4 MW",
            },
        )
        for row in rows:
            description = row["detail_metadata"]["department_project_description"]
            for statement in row["detail_metadata"]["power_statements"]:
                self.assertIsNone(statement["metric_type"])
                self.assertEqual(statement["context"], description)
        self.assertTrue(REVIEW_POLICY["power_statements_are_untyped_source_text"])
        self.assertIsNone(REVIEW_POLICY["gross_facility_power_mw"])
        self.assertIsNone(REVIEW_POLICY["it_capacity_mw"])
        self.assertIsNone(REVIEW_POLICY["annual_energy_mwh"])

    def test_modifications_are_separate_advisory_relationships(self) -> None:
        relationships = _jsonl("modification-relationships.jsonl")
        self.assertEqual(len(relationships), 9)
        self.assertEqual(
            sum(
                row["detail_main_project_field_confirmed"] is True
                for row in relationships
            ),
            3,
        )
        self.assertEqual(
            sum(
                row["detail_main_project_field_confirmed"] is None
                for row in relationships
            ),
            6,
        )
        for row in relationships:
            self.assertTrue(row["review_only"])
            self.assertFalse(row["auto_merge_permitted"])
            self.assertTrue(row["base_row_present"])

    def test_lga_text_disagreements_are_retained_not_reconciled(self) -> None:
        rows = _jsonl("active-planning-observations.jsonl")
        mismatches = [
            row
            for row in rows
            if not row["reconciliation"]["detail_lga_text_matches_list"]
        ]
        self.assertEqual(
            {row["case_id"] for row in mismatches},
            {"SSD-82211208", "SSD-63741210-Mod-1"},
        )
        values = {
            row["case_id"]: (
                row["local_government_area_text"],
                row["detail_metadata"]["local_government_areas"],
            )
            for row in mismatches
        }
        self.assertEqual(values["SSD-82211208"], ("Penrith, Blacktown", "Penrith"))
        self.assertEqual(
            values["SSD-63741210-Mod-1"],
            ("Fairfield City, Blacktown", "Fairfield City"),
        )

    def test_raw_inventory_is_exact_and_contains_no_attachment_fetches(self) -> None:
        inventory = json.loads(
            (PINNED_RELEASE / "source-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["artifact_count"], 27)
        self.assertEqual(inventory["raw_bytes"], 1_494_278)
        self.assertEqual(
            inventory["raw_inventory_sha256"], EXPECTED_RAW_INVENTORY_SHA256
        )
        self.assertEqual(
            Counter(
                "detail" if "/detail-" in row["filename"] else "list"
                for row in inventory["artifacts"]
            ),
            Counter({"detail": 22, "list": 5}),
        )
        for artifact in inventory["artifacts"]:
            self.assertTrue(artifact["filename"].endswith(".html"))
            parsed = urlsplit(artifact["url"])
            self.assertEqual(parsed.hostname, "www.planningportal.nsw.gov.au")
            self.assertTrue(parsed.path.startswith("/major-projects/projects"))
            self.assertNotIn("AttachRef", artifact["url"])
            self.assertNotIn("/prweb/", artifact["url"])
        self.assertFalse(any(PINNED_RELEASE.rglob("*.pdf")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.jpg")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.png")))

    def test_offline_rebuild_recreates_every_release_byte(self) -> None:
        capture, raw = _capture_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = write_release_bundle(
                Path(temporary) / "rebuilt", capture, raw, freeze=True
            )
            original_files = sorted(
                path.relative_to(PINNED_RELEASE)
                for path in PINNED_RELEASE.rglob("*")
                if path.is_file()
            )
            rebuilt_files = sorted(
                path.relative_to(rebuilt)
                for path in rebuilt.rglob("*")
                if path.is_file()
            )
            self.assertEqual(rebuilt_files, original_files)
            for filename in original_files:
                self.assertEqual(
                    (rebuilt / filename).read_bytes(),
                    (PINNED_RELEASE / filename).read_bytes(),
                )
            self.assertTrue(is_frozen_release(rebuilt))

    def test_release_is_frozen_and_manifest_hash_is_exact(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()),
            "650c9b6e194fea0dbe1ce28ecba0cb8f114b8ec7d6571a0ee1f31c41f0d660f2",
        )

    def test_raw_or_rights_tampering_fails_closed_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            raw = copied / "raw/list-page-00000.html"
            raw.write_bytes(raw.read_bytes() + b"\n")
            with self.assertRaisesRegex(NSWMajorProjectsError, "raw artifact mismatch"):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment_path = copied / "assessment.json"
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
            assessment["rights_assessment"]["raw_html_redistribution_eligible"] = True
            assessment_path.write_bytes(canonical_json(assessment))
            with self.assertRaisesRegex(
                NSWMajorProjectsError, "manifest does not bind"
            ):
                validate_release_bundle(copied)


if __name__ == "__main__":
    unittest.main()
