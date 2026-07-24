from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.epa_echo_frs_assessment import (
    EPAEchoFRSAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_pilot_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "epa-echo-frs-2026-07-18-v1"
)


def _document(filename: str) -> dict[str, object]:
    return json.loads(
        (PINNED_ASSESSMENT / filename).read_text(encoding="utf-8")
    )


class EPAEchoFRSAssessmentTests(unittest.TestCase):
    def test_pinned_assessment_and_review_pilot_validate_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        pilot = bundle["pilot"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "bounded_review_only_pending_exact_frs_field_lineage",
        )
        self.assertEqual(pilot["query"]["query_rows"], 928)
        self.assertEqual(len(pilot["leads"]), 4)
        self.assertEqual(pilot["construction_verified_rows"], 0)
        self.assertEqual(pilot["publication_eligible_rows"], 0)
        self.assertIsNone(pilot["unique_physical_site_count"])

    def test_cc0_scope_cannot_expand_to_all_echo_data(self) -> None:
        relaxed = deepcopy(_document("assessment.json"))
        relaxed["rights_assessment"][
            "cc0_applies_to_all_echo_program_data"
        ] = True
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "rights scope"
        ):
            validate_assessment_document(relaxed)

    def test_rest_probe_cannot_become_a_bulk_loop(self) -> None:
        expanded = deepcopy(_document("pilot.json"))
        expanded["query"]["bulk_loop_used"] = True
        expanded["query"]["executed_get_facilities_requests"] = 928
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "bounded query"
        ):
            validate_pilot_document(expanded)

    def test_naics_match_cannot_become_data_center_proof(self) -> None:
        promoted = deepcopy(_document("pilot.json"))
        promoted["leads"][0]["naics_is_data_center_proof"] = True
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "review lead controls"
        ):
            validate_pilot_document(promoted)

    def test_name_token_cannot_become_construction_lifecycle(self) -> None:
        promoted = deepcopy(_document("pilot.json"))
        promoted["leads"][0]["construction_verified"] = True
        promoted["leads"][0]["atlas_lifecycle_status"] = "under_construction"
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "unsupported field"
        ):
            validate_pilot_document(promoted)

    def test_pilot_rejects_typed_capacity_energy_pue_and_workload(self) -> None:
        promoted = deepcopy(_document("pilot.json"))
        promoted["leads"][0]["gross_power_capacity_mw"] = 100
        promoted["leads"][0]["annual_energy_mwh"] = 876000
        promoted["leads"][0]["pue"] = 1.2
        promoted["leads"][0]["operational_workload"] = "ai_training"
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "unsupported field"
        ):
            validate_pilot_document(promoted)

    def test_false_positive_cannot_replace_a_review_lead(self) -> None:
        promoted = deepcopy(_document("pilot.json"))
        promoted["leads"][0]["frs_registry_id"] = "110070251348"
        promoted["leads"][0]["facility_name"] = "JE DUNN CONSTRUCTION"
        with self.assertRaisesRegex(
            EPAEchoFRSAssessmentError, "identity set"
        ):
            validate_pilot_document(promoted)

    def test_bundle_rejects_unpinned_raw_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            (copied / "echo-response.json").write_text(
                "not retained\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                EPAEchoFRSAssessmentError, "file set"
            ):
                validate_assessment_bundle(copied)

    def test_bundle_rejects_manifest_sidecar_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            (copied / "manifest.sha256").write_text(
                f"{'0' * 64}  manifest.json\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                EPAEchoFRSAssessmentError, "sidecar"
            ):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
