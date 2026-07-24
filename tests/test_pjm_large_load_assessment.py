from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.pjm_large_load_assessment import (
    PJMLargeLoadAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_calibration_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "pjm-large-load-2026-07-18-v1"
)


class PJMLargeLoadAssessmentTests(unittest.TestCase):
    def test_pinned_metadata_only_bundle_validates_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        calibration = bundle["calibration"]
        self.assertEqual(len(assessment["official_artifacts"]), 42)
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "rights_blocked_metadata_only",
        )
        self.assertEqual(calibration["facility_lead_count"], 0)
        self.assertEqual(calibration["numeric_series_count"], 0)
        self.assertIsNone(calibration["unique_facility_count"])

    def test_rights_cannot_be_relaxed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"][
            "raw_artifact_cache_for_atlas_release_permitted"
        ] = True
        with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "fail closed"):
            validate_assessment_document(relaxed)

    def test_zone_aggregate_cannot_become_a_facility(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["granularity_assessment"]["canonical_facility_rows"] = 1
        promoted["granularity_assessment"]["publication_facility_leads"] = 1
        with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "granularity"):
            validate_assessment_document(promoted)

    def test_forecast_adjustment_cannot_become_facility_power(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "calibration.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["metric_semantics"]["pjm_forecast_adjustment_mw"][
            "atlas_facility_field"
        ] = "gross_power_capacity_mw"
        with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "semantics"):
            validate_calibration_document(promoted)

    def test_construction_commitment_cannot_become_lifecycle(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "calibration.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["status_semantics"]["construction_commitment"][
            "atlas_lifecycle_status"
        ] = "under_construction"
        with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "status semantics"):
            validate_calibration_document(promoted)

    def test_calibration_cannot_emit_a_project_row(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "calibration.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["review_leads"] = [{"source_id": "redacted"}]
        promoted["facility_lead_count"] = 1
        with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "metadata only"):
            validate_calibration_document(promoted)

    def test_bundle_rejects_unpinned_raw_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            (copied / "pjm-report.pdf").write_bytes(b"not retained\n")
            with self.assertRaisesRegex(PJMLargeLoadAssessmentError, "file set"):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
