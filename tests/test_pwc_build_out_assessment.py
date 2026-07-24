from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.pwc_build_out_assessment import (
    PWCBuildOutAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_schema_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "pwc-build-out-2026-07-18-v1"
)


class PWCBuildOutAssessmentTests(unittest.TestCase):
    def test_pinned_metadata_only_bundle_validates_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "rights_blocked_metadata_only",
        )
        self.assertEqual(assessment["count_assessment"]["building_records"], 243)
        self.assertEqual(
            assessment["count_assessment"]["campus_project_records"], 72
        )
        self.assertEqual(
            assessment["count_assessment"][
                "planning_site_application_records"
            ],
            61,
        )
        self.assertIsNone(assessment["count_assessment"]["unique_site_count"])
        self.assertEqual(assessment["retrieval_batch"]["feature_rows_retrieved"], 0)

    def test_rights_cannot_be_relaxed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"][
            "affirmative_public_redistribution_permission_found"
        ] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "fail closed"):
            validate_assessment_document(relaxed)

    def test_site_item_cc_by_sa_cannot_be_promoted_to_layer_license(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["rights_assessment"][
            "portal_site_item_license_scope_covers_layers_9_10_11"
        ] = True
        promoted["rights_assessment"][
            "portal_site_item_license_treated_as_layer_data_license"
        ] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "fail closed"):
            validate_assessment_document(promoted)

    def test_layer_counts_cannot_be_summed_as_unique_sites(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["count_assessment"]["record_counts_summed"] = True
        promoted["count_assessment"]["unique_site_count"] = 376
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "count semantics"):
            validate_assessment_document(promoted)

    def test_entity_levels_cannot_be_auto_merged(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        merged = deepcopy(document)
        merged["granularity_assessment"]["auto_merge_permitted"] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "granularity"):
            validate_assessment_document(merged)

    def test_under_construction_remains_snapshot_scoped_evidence(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["status_semantics"]["county_under_construction_evidence"][
            "atlas_auto_promotion"
        ] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "status evidence"):
            validate_schema_document(promoted)

    def test_gfa_cannot_become_power_or_energy(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["power_energy_semantics"][
            "power_capacity_inference_permitted"
        ] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "power or energy"):
            validate_schema_document(promoted)

    def test_schema_cannot_emit_feature_rows_or_geometry(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["contains_feature_records"] = True
        promoted["contains_addresses_coordinates_or_feature_geometries"] = True
        with self.assertRaisesRegex(PWCBuildOutAssessmentError, "metadata only"):
            validate_schema_document(promoted)

    def test_bundle_rejects_unpinned_raw_feature_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            (copied / "layer-9-features.json").write_text(
                '{"features": []}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(PWCBuildOutAssessmentError, "file set"):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
