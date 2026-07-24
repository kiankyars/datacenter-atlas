from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.cleanview_assessment import (
    CleanviewAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_schema_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "cleanview-2026-07-18-v1"
)


class CleanviewAssessmentTests(unittest.TestCase):
    def test_pinned_metadata_only_bundle_validates_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        schema = bundle["schema"]
        self.assertEqual(len(assessment["official_artifacts"]), 14)
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "api_and_rights_blocked_metadata_only",
        )
        self.assertEqual(assessment["retrieval_batch"]["data_endpoint_requests"], 0)
        self.assertEqual(schema["facility_lead_count"], 0)
        self.assertIsNone(schema["unique_facility_count"])

    def test_rights_cannot_be_relaxed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"][
            "affirmative_public_redistribution_permission_found"
        ] = True
        with self.assertRaisesRegex(CleanviewAssessmentError, "fail closed"):
            validate_assessment_document(relaxed)

    def test_api_cannot_be_marked_anonymous_or_bounded(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        weakened = deepcopy(document)
        weakened["access_assessment"]["anonymous_access_documented"] = True
        weakened["access_assessment"]["minimal_bounded_data_probe_possible"] = True
        with self.assertRaisesRegex(CleanviewAssessmentError, "access boundary"):
            validate_assessment_document(weakened)

    def test_example_count_cannot_become_current_count(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["coverage_assessment"]["live_record_count"] = 1176
        promoted["coverage_assessment"][
            "example_total_count_is_current_verified_count"
        ] = True
        with self.assertRaisesRegex(CleanviewAssessmentError, "coverage"):
            validate_assessment_document(promoted)

    def test_capacity_cannot_become_typed_facility_power(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["capacity_semantics"][
            "atlas_it_load_mapping_permitted"
        ] = True
        with self.assertRaisesRegex(CleanviewAssessmentError, "capacity semantics"):
            validate_schema_document(promoted)

    def test_status_cannot_become_construction_evidence(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["status_semantics"]["planned_means_under_construction"] = True
        with self.assertRaisesRegex(CleanviewAssessmentError, "status semantics"):
            validate_schema_document(promoted)

    def test_schema_cannot_emit_a_facility_lead(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["facility_leads"] = [{"project_name": "example"}]
        promoted["facility_lead_count"] = 1
        with self.assertRaisesRegex(CleanviewAssessmentError, "source rows"):
            validate_schema_document(promoted)

    def test_bundle_rejects_unpinned_raw_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            (copied / "cleanview-response.json").write_text(
                "not retained\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(CleanviewAssessmentError, "file set"):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
