from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.datacenter_atlas.loudoun_data_center_assessment import (
    CALIBRATION_FILENAME,
    LoudounDataCenterAssessmentError,
    validate_assessment_bundle,
    validate_assessment_document,
    validate_calibration_document,
    validate_schema_document,
    write_assessment_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "loudoun-data-center-2026-07-18-v1"
)


class LoudounDataCenterAssessmentTests(unittest.TestCase):
    def test_frozen_metadata_and_aggregates_bundle_validates_offline(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        assessment = bundle["assessment"]
        calibration = bundle["calibration"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "rights_blocked_metadata_and_aggregates_only",
        )
        self.assertEqual(
            assessment["count_assessment"]["existing_parcel_records"], 139
        )
        self.assertEqual(
            assessment["count_assessment"]["pipeline_parcel_records"], 85
        )
        self.assertEqual(assessment["retrieval_batch"]["feature_rows_retrieved"], 0)
        self.assertIsNone(assessment["count_assessment"]["unique_site_count"])
        self.assertEqual(
            calibration["assessor_report"]["official_total"]["parcels"], 251
        )

    def test_rights_cannot_be_relaxed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"][
            "affirmative_public_database_redistribution_permission_found"
        ] = True
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "fail closed"
        ):
            validate_assessment_document(relaxed)

    def test_parcel_counts_cannot_be_promoted_or_summed(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["count_assessment"]["record_counts_summed"] = True
        promoted["count_assessment"]["unique_site_count"] = 224
        promoted["granularity_assessment"]["existing_records_are_buildings"] = True
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "count semantics"
        ):
            validate_assessment_document(promoted)

    def test_county_statuses_cannot_become_atlas_lifecycle(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["status_semantics"]["existing_built_status"][
            "atlas_auto_promotion"
        ] = True
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "status semantics"
        ):
            validate_schema_document(promoted)

    def test_status_distribution_preserves_source_typo(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / CALIBRATION_FILENAME).read_text(encoding="utf-8")
        )
        values = {
            record["value"]: record["count"]
            for record in document["gis_snapshot"]["distributions"][
                "existing_built_status"
            ]
        }
        self.assertEqual(values["BULT/UNDER CONSTRUCTION"], 1)
        normalized = deepcopy(document)
        normalized["gis_snapshot"]["distributions"]["existing_built_status"][
            2
        ]["value"] = "BUILT/UNDER CONSTRUCTION"
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "aggregate snapshot"
        ):
            validate_calibration_document(normalized)

    def test_assessor_rows_and_official_total_remain_distinct(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / CALIBRATION_FILENAME).read_text(encoding="utf-8")
        )
        reconciliation = document["assessor_report"]["reconciliation"]
        self.assertEqual(
            reconciliation["improved_parcels"]["category_row_sum"], 151
        )
        self.assertEqual(reconciliation["improved_parcels"]["official_total"], 153)
        self.assertEqual(
            reconciliation["complete_data_centers"]["category_row_sum"], 215
        )
        self.assertEqual(
            reconciliation["complete_data_centers"]["official_total"], 209
        )
        self.assertEqual(
            reconciliation["under_construction_data_centers"]["category_row_sum"],
            37,
        )
        self.assertEqual(
            reconciliation["under_construction_data_centers"]["official_total"],
            43,
        )
        composition = {
            record["normalized_type"]: record
            for record in document["assessor_report"][
                "parcel_composition_reconciliation"
            ]
        }
        self.assertEqual(composition["Retail/Colo"]["classified_parcel_sum"], 123)
        self.assertEqual(composition["Retail/Colo"]["parcels"], 125)
        self.assertFalse(composition["Retail/Colo"]["reconciles"])
        self.assertTrue(composition["Official total"]["reconciles"])
        repaired = deepcopy(document)
        repaired["assessor_report"]["official_total"]["complete_data_centers"] = 215
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "calibration"
        ):
            validate_calibration_document(repaired)

    def test_square_feet_cannot_become_power_or_energy(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["power_energy_semantics"][
            "floor_area_to_power_conversion_permitted"
        ] = True
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "power or energy"
        ):
            validate_schema_document(promoted)

    def test_schema_cannot_emit_feature_rows_or_geometry(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "schema.json").read_text(encoding="utf-8")
        )
        promoted = deepcopy(document)
        promoted["contains_feature_records"] = True
        promoted["contains_feature_attributes"] = True
        promoted["contains_feature_geometries"] = True
        with self.assertRaisesRegex(
            LoudounDataCenterAssessmentError, "metadata only"
        ):
            validate_schema_document(promoted)

    def test_bundle_rejects_unpinned_raw_feature_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            (copied / "existing-features.geojson").write_text(
                '{"features": [], "type": "FeatureCollection"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                LoudounDataCenterAssessmentError, "file set"
            ):
                validate_assessment_bundle(copied)

    def test_canonical_bundle_reproduces_byte_for_byte(self) -> None:
        bundle = validate_assessment_bundle(PINNED_ASSESSMENT)
        with tempfile.TemporaryDirectory() as temporary:
            reproduced = Path(temporary) / "reproduced"
            write_assessment_bundle(
                reproduced,
                bundle["assessment"],
                bundle["schema"],
                bundle["calibration"],
                freeze=False,
            )
            for original in PINNED_ASSESSMENT.iterdir():
                self.assertEqual(
                    original.read_bytes(),
                    (reproduced / original.name).read_bytes(),
                    original.name,
                )

    def test_tampered_frozen_payload_fails_manifest_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            copied.chmod(0o755)
            calibration_path = copied / CALIBRATION_FILENAME
            calibration_path.chmod(0o644)
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            calibration["assessor_report"]["official_total"]["parcels"] = 250
            calibration_path.write_text(
                json.dumps(calibration, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(LoudounDataCenterAssessmentError):
                validate_assessment_bundle(copied)


if __name__ == "__main__":
    unittest.main()
