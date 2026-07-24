from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.edgemode_assessment import (
    EdgeModeAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_pilot_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "edgemode-2026-07-18-v1"
)


class EdgeModeAssessmentTests(unittest.TestCase):
    def test_pinned_assessment_and_pilot_validate_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        pilot = bundle["pilot"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "bounded_sec_edgar_pilot_only",
        )
        self.assertEqual(len(pilot["leads"]), 9)
        self.assertIsNone(pilot["unique_facility_count"])
        self.assertEqual(pilot["construction_verified_rows"], 0)
        self.assertEqual(pilot["typed_capacity_rows"], 0)

    def test_direct_website_rights_cannot_be_relaxed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"]["edgemode_website"][
            "direct_release_permitted"
        ] = True
        with self.assertRaisesRegex(EdgeModeAssessmentError, "fail closed"):
            validate_assessment_document(relaxed)

    def test_edgar_reuse_basis_cannot_be_removed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        weakened = deepcopy(document)
        weakened["rights_assessment"]["sec_edgar"][
            "public_filing_content_free_to_access_and_reuse"
        ] = False
        with self.assertRaisesRegex(EdgeModeAssessmentError, "reuse decision"):
            validate_assessment_document(weakened)

    def test_pilot_rejects_lifecycle_promotion(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "pilot.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["leads"][0]["atlas_lifecycle_status"] = "under_construction"
        promoted["leads"][0]["construction_verified"] = True
        with self.assertRaisesRegex(EdgeModeAssessmentError, "unsupported field"):
            validate_pilot_document(promoted)

    def test_pilot_rejects_typed_power(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "pilot.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["leads"][0]["it_load_mw"] = 360
        promoted["typed_capacity_rows"] = 1
        with self.assertRaisesRegex(EdgeModeAssessmentError, "review-only"):
            validate_pilot_document(promoted)

    def test_bundle_rejects_unpinned_raw_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            (copied / "edgemode-homepage.html").write_text(
                "not retained\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(EdgeModeAssessmentError, "file set"):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
