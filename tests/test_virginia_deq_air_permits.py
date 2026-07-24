from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.virginia_deq_air_permits import (
    VirginiaDEQAirPermitsError,
    build_assessment_bundle,
    validate_applications_document,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_issued_permits_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT
    / "source_assessments"
    / "virginia-deq-air-permits-2026-07-13-v1"
)


def _document(filename: str) -> dict[str, object]:
    return json.loads(
        (PINNED_ASSESSMENT / filename).read_text(encoding="utf-8")
    )


def _issued_record(document: dict[str, object], permit_id: str) -> dict[str, object]:
    records = document["records"]
    assert isinstance(records, list)
    return next(
        record
        for record in records
        if record["registration_or_application_id"] == permit_id
    )


class VirginiaDEQAirPermitsTests(unittest.TestCase):
    def test_pinned_bundle_validates_offline_with_exact_counts(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        issued = bundle["issued_permits"]
        applications = bundle["applications"]
        self.assertEqual(len(issued["records"]), 198)
        self.assertEqual(issued["count_reconciliation"]["parsed_table_rows"], 198)
        self.assertEqual(
            issued["count_reconciliation"]["page_widget_reported_rows"], 194
        )
        self.assertEqual(len(applications["records"]), 1)
        self.assertEqual(
            applications["records"][0]["application_status"], "under_review"
        )
        self.assertEqual(
            assessment["coverage_assessment"]["construction_verified_rows"], 0
        )
        self.assertIsNone(issued["unique_physical_site_count"])

    def test_builder_recreates_every_bundle_byte(self) -> None:
        source = validate_assessment_bundle(PINNED_ASSESSMENT)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rebuilt"
            build_assessment_bundle(
                output,
                source["assessment"],
                source["issued_permits"],
                source["applications"],
            )
            for original in sorted(PINNED_ASSESSMENT.iterdir()):
                self.assertEqual(original.read_bytes(), (output / original.name).read_bytes())

    def test_all_rights_reserved_boundary_cannot_be_relaxed(self) -> None:
        relaxed = deepcopy(_document("assessment.json"))
        relaxed["rights_assessment"]["derived_record_publication_permitted"] = True
        with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "rights"):
            validate_assessment_document(relaxed)

    def test_issued_permit_cannot_become_construction_status(self) -> None:
        promoted = deepcopy(_document("issued_permits.json"))
        promoted["records"][0]["construction_verified"] = True
        promoted["records"][0]["atlas_lifecycle_status"] = "under_construction"
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "construction or operation"
        ):
            validate_issued_permits_document(promoted)

    def test_issued_permit_cannot_promote_generator_or_facility_metrics(self) -> None:
        promoted = deepcopy(_document("issued_permits.json"))
        promoted["records"][0]["gross_power_capacity_mw"] = 100
        promoted["records"][0]["annual_energy_mwh"] = 876000
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "unsupported Atlas field"
        ):
            validate_issued_permits_document(promoted)

    def test_under_review_application_cannot_become_issued(self) -> None:
        promoted = deepcopy(_document("applications.json"))
        promoted["records"][0]["application_status"] = "issued"
        promoted["records"][0]["record_status"] = "issued_permit"
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "identity or status"
        ):
            validate_applications_document(promoted)

    def test_generator_groups_cannot_be_summed_into_atlas_metrics(self) -> None:
        promoted = deepcopy(_document("applications.json"))
        record = promoted["records"][0]
        record["aggregate_generator_count"] = 125
        record["total_generator_electrical_nameplate_mw"] = 327.5
        record["it_load_mw"] = 327.5
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "summed or promoted"
        ):
            validate_applications_document(promoted)

    def test_source_date_anomaly_is_not_silently_repaired(self) -> None:
        repaired = deepcopy(_document("issued_permits.json"))
        record = _issued_record(repaired, "74333-1")
        record["issuance_date_iso"] = "2026-03-26"
        record["issuance_date_parse_status"] = "exact_mm_dd_yyyy"
        with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "date anomaly"):
            validate_issued_permits_document(repaired)

    def test_widget_and_parsed_row_counts_cannot_be_conflated(self) -> None:
        conflated = deepcopy(_document("issued_permits.json"))
        conflated["count_reconciliation"]["page_widget_reported_rows"] = 198
        with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "row-count"):
            validate_issued_permits_document(conflated)

    def test_exact_document_link_anomalies_are_preserved(self) -> None:
        inferred = deepcopy(_document("issued_permits.json"))
        unresolved = _issued_record(inferred, "74063-5")
        unresolved["permit_document_url"] = (
            "https://www.deq.virginia.gov/home/showpublisheddocument/1/1"
        )
        unresolved["permit_document_url_status"] = "resolved_official_url"
        with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "was inferred"):
            validate_issued_permits_document(inferred)

        split = deepcopy(_document("issued_permits.json"))
        shared = _issued_record(split, "74333-1")
        shared["permit_document_url"] = (
            "https://www.deq.virginia.gov/home/showpublisheddocument/2/2"
        )
        with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "shared official"):
            validate_issued_permits_document(split)

    def test_repeated_registration_numbers_remain_review_only(self) -> None:
        merged = deepcopy(_document("issued_permits.json"))
        merged["possible_duplicate_groups"][0]["merge_approved"] = True
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "review-only and unmerged"
        ):
            validate_issued_permits_document(merged)

    def test_semantically_valid_row_edit_still_breaks_frozen_snapshot(self) -> None:
        changed = deepcopy(_document("issued_permits.json"))
        changed["records"][0]["site_name"] = "Changed but structurally valid"
        with self.assertRaisesRegex(
            VirginiaDEQAirPermitsError, "frozen source assessment"
        ):
            validate_issued_permits_document(changed)

    def test_bundle_rejects_unpinned_raw_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            (copied / "permit.pdf").write_bytes(b"not retained")
            with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "file set"):
                validate_assessment_bundle(copied)

    def test_bundle_rejects_manifest_sidecar_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            (copied / "manifest.sha256").chmod(0o644)
            (copied / "manifest.sha256").write_text(
                f"{'0' * 64}  manifest.json\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(VirginiaDEQAirPermitsError, "sidecar"):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
