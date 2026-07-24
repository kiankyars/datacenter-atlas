from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.satellite_calibration import (
    METRIC_NAMES,
    PREDECLARED_RULES,
    ROW_FIELDS,
    SCOPE_POLICY,
    SCOPE_POLICY_V2,
    SCOPE_POLICY_V3,
    SCOPE_POLICY_V4,
    SatelliteCalibrationError,
    evaluate_rule,
    validate_satellite_calibration,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-calibration-2026-07-18-analyst-reviews-v1.json"
)
BUNDLE = (
    PACKAGE_ROOT
    / "satellite_calibration"
    / "2026-07-18-analyst-reviews-v1"
)
CANDIDATE_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "candidate-fusion-2026-07-18-osm-planet-v9.json"
)
CANDIDATE_MANIFEST = (
    PACKAGE_ROOT
    / "candidate_fusion"
    / "2026-07-18-osm-planet-priority-v9"
    / "manifest.json"
)
DEFINITION_V2 = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-calibration-2026-07-18-analyst-reviews-v2.json"
)
BUNDLE_V2 = (
    PACKAGE_ROOT
    / "satellite_calibration"
    / "2026-07-18-analyst-reviews-v2"
)
CANDIDATE_DEFINITION_V10 = (
    PACKAGE_ROOT
    / "sources"
    / "candidate-fusion-2026-07-18-osm-planet-v10.json"
)
CANDIDATE_MANIFEST_V10 = (
    PACKAGE_ROOT
    / "candidate_fusion"
    / "2026-07-18-osm-planet-priority-v10"
    / "manifest.json"
)
DEFINITION_V3 = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-calibration-2026-07-18-analyst-reviews-v3.json"
)
BUNDLE_V3 = (
    PACKAGE_ROOT
    / "satellite_calibration"
    / "2026-07-18-analyst-reviews-v3"
)
CANDIDATE_DEFINITION_V11 = (
    PACKAGE_ROOT
    / "sources"
    / "candidate-fusion-2026-07-18-osm-planet-v11.json"
)
CANDIDATE_MANIFEST_V11 = (
    PACKAGE_ROOT
    / "candidate_fusion"
    / "2026-07-18-osm-planet-priority-v11"
    / "manifest.json"
)
DEFINITION_V4 = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-calibration-2026-07-18-analyst-reviews-v4.json"
)
BUNDLE_V4 = (
    PACKAGE_ROOT
    / "satellite_calibration"
    / "2026-07-18-analyst-reviews-v4"
)
CANDIDATE_DEFINITION_V13 = (
    PACKAGE_ROOT
    / "sources"
    / "candidate-fusion-2026-07-18-osm-planet-v13.json"
)
CANDIDATE_MANIFEST_V13 = (
    PACKAGE_ROOT
    / "candidate_fusion"
    / "2026-07-18-osm-planet-priority-v13"
    / "manifest.json"
)


def _records() -> list[dict]:
    return [
        json.loads(line)
        for line in (BUNDLE / "calibration-records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


class SatelliteCalibrationTests(unittest.TestCase):
    def test_frozen_v1_bundle_reproduces_offline(self):
        manifest = validate_satellite_calibration(
            BUNDLE, definition_path=DEFINITION
        )
        self.assertEqual(manifest["counts"]["count"], 25)
        self.assertEqual(
            manifest["counts"]["outcome_counts"], {"reject": 18, "retain": 7}
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            "2ead3e68d92581544a13d7447fd86603bdbdb6c094f4f7b9e3f68cc36a991629",
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "68171a2cdcc739b0ec0bfa0863ad13891f93727c576a7b72831d79e9393f35ee",
        )
        self.assertEqual(
            (BUNDLE / "manifest.sha256").read_text(encoding="ascii"),
            "68171a2cdcc739b0ec0bfa0863ad13891f93727c576a7b72831d79e9393f35ee  manifest.json\n",
        )
        self.assertEqual(BUNDLE.stat().st_mode & 0o777, 0o555)
        for path in BUNDLE.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_frozen_v2_bundle_reproduces_offline(self):
        manifest = validate_satellite_calibration(
            BUNDLE_V2, definition_path=DEFINITION_V2
        )
        self.assertEqual(
            manifest["counts"],
            {
                "count": 31,
                "outcome_counts": {"reject": 23, "retain": 8},
                "source_run_counts": {
                    "global-open-v3-active-001": 7,
                    "global-open-v3-proposed-001": 1,
                    "global-open-v3-unknown-010": 23,
                },
            },
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION_V2.read_bytes()).hexdigest(),
            "ed27fde056183dc0d568e87bdfeef2ff001faac24daeb171b2d2ebcde46cc09d",
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE_V2 / "manifest.json").read_bytes()).hexdigest(),
            "8aa1777c1e0cf8c90bf49c9b9ea790604910b5094a6369cf360a2d0b1e604203",
        )
        self.assertEqual(
            (BUNDLE_V2 / "manifest.sha256").read_text(encoding="ascii"),
            "8aa1777c1e0cf8c90bf49c9b9ea790604910b5094a6369cf360a2d0b1e604203  manifest.json\n",
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "2edbe78b6a10772fb4a948abd9cfeb994a97de976cf203ad94951ac091c98d0e",
                "README.md": "a58744d2da501d44121832a8e5a8c85a34bb800f29e1c2dabd0760a84553092a",
                "calibration-records.csv": "e52abbf67e0b897f72c0b61f04cb16196722dd77397056ec0f15754cd7a87717",
                "calibration-records.jsonl": "ac04bfb0d5e56ff52457c5628f6ca185e2a87a1360057d2643168191e86cc9d6",
                "summary.json": "332d8721e151e56723c3c30d4230edc572b13ac994c0af06d7526c94a8c53f95",
            },
        )
        self.assertEqual(BUNDLE_V2.stat().st_mode & 0o777, 0o555)
        for path in BUNDLE_V2.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_frozen_v3_bundle_reproduces_offline(self):
        manifest = validate_satellite_calibration(
            BUNDLE_V3, definition_path=DEFINITION_V3
        )
        self.assertEqual(
            manifest["counts"],
            {
                "count": 37,
                "outcome_counts": {"reject": 27, "retain": 10},
                "source_run_counts": {
                    "global-open-v3-active-001": 7,
                    "global-open-v3-proposed-001": 1,
                    "global-open-v3-unknown-010": 23,
                    "global-open-v3-unknown-013": 6,
                },
            },
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION_V3.read_bytes()).hexdigest(),
            "3e7e36c6f122927a75fdbc74780e5ef07a1bed0a31dd7898b3cb84b05181fd51",
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE_V3 / "manifest.json").read_bytes()).hexdigest(),
            "00e5e76a8ed200329702298e01f1be416504ea15b2153c77565f5a6742bbeb6d",
        )
        self.assertEqual(
            (BUNDLE_V3 / "manifest.sha256").read_text(encoding="ascii"),
            "00e5e76a8ed200329702298e01f1be416504ea15b2153c77565f5a6742bbeb6d  manifest.json\n",
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "2edbe78b6a10772fb4a948abd9cfeb994a97de976cf203ad94951ac091c98d0e",
                "README.md": "58c972368f25e5c09b219feae9af118ad33f6888d13dac21e97b5454e06be5d5",
                "calibration-records.csv": "568bffe59f5a038210b80e0f90587dbb72ec8591ab9e2ecfdd6fddabf909a7f5",
                "calibration-records.jsonl": "baf51e07149ccbec916b76722ec5456333d94ab24de5e7b736b7f7715534f97d",
                "summary.json": "0988e9754ab24c95d08391014bfe8b66efe68105f53d603ac0f12e8f8913ab10",
            },
        )
        self.assertEqual(BUNDLE_V3.stat().st_mode & 0o777, 0o555)
        for path in BUNDLE_V3.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_frozen_v4_bundle_reproduces_offline(self):
        manifest = validate_satellite_calibration(
            BUNDLE_V4, definition_path=DEFINITION_V4
        )
        self.assertEqual(
            manifest["counts"],
            {
                "count": 43,
                "outcome_counts": {"reject": 31, "retain": 12},
                "source_run_counts": {
                    "global-open-v3-active-001": 7,
                    "global-open-v3-proposed-001": 1,
                    "global-open-v3-unknown-010": 23,
                    "global-open-v3-unknown-013": 6,
                    "global-open-v3-unknown-015": 6,
                },
            },
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION_V4.read_bytes()).hexdigest(),
            "876d88ff2c8ad137799714408b39016bf10b12820f637c3c2ff9ab3f30283414",
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE_V4 / "manifest.json").read_bytes()).hexdigest(),
            "a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41",
        )
        self.assertEqual(
            (BUNDLE_V4 / "manifest.sha256").read_text(encoding="ascii"),
            "a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41  manifest.json\n",
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "2edbe78b6a10772fb4a948abd9cfeb994a97de976cf203ad94951ac091c98d0e",
                "README.md": "7ba5616eeb310794eeee993648c543df2454b878d1929f6dec9c70a9c8a7507c",
                "calibration-records.csv": "22019c683c9b28d9bbe7ba01f8af7194a37ac47f473b58638d62c3cd0745b0ce",
                "calibration-records.jsonl": "9242f98e2ecf75c4e98cff6d28c4416798f8261aa8c5f0ab13f1e358250d4376",
                "summary.json": "6b8261b0f8040c156283f530232ac969ec079cd8b298bdde5b84ab638e331a0f",
            },
        )
        self.assertEqual(BUNDLE_V4.stat().st_mode & 0o777, 0o555)
        for path in BUNDLE_V4.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_v2_definition_is_exactly_the_candidate_v10_review_set(self):
        definition = json.loads(DEFINITION_V2.read_text(encoding="utf-8"))
        candidate = json.loads(
            CANDIDATE_DEFINITION_V10.read_text(encoding="utf-8")
        )
        fusion = definition["candidate_fusion"]
        self.assertEqual(
            fusion["definition"],
            {
                "path": CANDIDATE_DEFINITION_V10.name,
                "bytes": 18625,
                "sha256": "3e8c321f17a0ff915dc55e79dcdb511b034bf5b225a8d97c8d02c15a091340e1",
            },
        )
        self.assertEqual(
            fusion["manifest"],
            {
                "path": "../candidate_fusion/2026-07-18-osm-planet-priority-v10/manifest.json",
                "bytes": 22781,
                "sha256": "83b51f75f2063815422fce3c308af8975a134b68b93aefd0b5ccbcad5c7bf3d4",
            },
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_MANIFEST_V10.read_bytes()).hexdigest(),
            fusion["manifest"]["sha256"],
        )
        expected = {
            spec["queue_id"]: (
                spec["report_path"],
                spec["report_sha256"],
                spec["path"],
                spec["sha256"],
            )
            for spec in candidate["inputs"]["satellite_analyst_reviews"]
        }
        actual = {
            pair["queue_id"]: (
                pair["report"]["path"],
                pair["report"]["sha256"],
                pair["review"]["path"],
                pair["review"]["sha256"],
            )
            for pair in definition["review_pairs"]
        }
        self.assertEqual(len(actual), 31)
        self.assertEqual(actual, expected)
        self.assertEqual(
            [pair["queue_id"] for pair in definition["review_pairs"]],
            sorted(actual),
        )
        self.assertEqual(
            sum(
                pair["source_run"] == "global-open-v3-unknown-010"
                for pair in definition["review_pairs"]
            ),
            23,
        )
        self.assertNotIn("unknown-009", DEFINITION_V2.read_text(encoding="utf-8"))

    def test_v3_definition_is_exactly_the_candidate_v11_review_set(self):
        definition_raw = DEFINITION_V3.read_bytes()
        definition = json.loads(definition_raw)
        candidate = json.loads(
            CANDIDATE_DEFINITION_V11.read_text(encoding="utf-8")
        )
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, sort_keys=True) + "\n").encode(),
        )
        fusion = definition["candidate_fusion"]
        self.assertEqual(
            fusion["definition"],
            {
                "path": CANDIDATE_DEFINITION_V11.name,
                "bytes": 21835,
                "sha256": "09e89ee0c9ad4c22ad081fca8c0a08fbaead8f3b1b6e1d85931a8f0974bb36cc",
            },
        )
        self.assertEqual(
            fusion["manifest"],
            {
                "path": "../candidate_fusion/2026-07-18-osm-planet-priority-v11/manifest.json",
                "bytes": 25873,
                "sha256": "6f4cd3558f9421fda49f503b0ee8a359d8e9cd3631a2ad23ba2cbae2c6c317dc",
            },
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_DEFINITION_V11.read_bytes()).hexdigest(),
            fusion["definition"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_MANIFEST_V11.read_bytes()).hexdigest(),
            fusion["manifest"]["sha256"],
        )
        expected = sorted(
            (
                spec["queue_id"],
                spec["report_path"],
                spec["report_sha256"],
                spec["path"],
                spec["sha256"],
            )
            for spec in candidate["inputs"]["satellite_analyst_reviews"]
        )
        actual = [
            (
                pair["queue_id"],
                pair["report"]["path"],
                pair["report"]["sha256"],
                pair["review"]["path"],
                pair["review"]["sha256"],
            )
            for pair in definition["review_pairs"]
        ]
        self.assertEqual(len(actual), 37)
        self.assertEqual(actual, expected)
        self.assertEqual(
            [pair["queue_id"] for pair in definition["review_pairs"]],
            sorted(pair["queue_id"] for pair in definition["review_pairs"]),
        )
        for pair in definition["review_pairs"]:
            for kind in ("report", "review"):
                checkpoint = pair[kind]
                path = (DEFINITION_V3.parent / checkpoint["path"]).resolve()
                raw = path.read_bytes()
                self.assertEqual(len(raw), checkpoint["bytes"])
                self.assertEqual(
                    hashlib.sha256(raw).hexdigest(), checkpoint["sha256"]
                )
                payload = json.loads(raw)
                if kind == "review":
                    self.assertFalse(payload["automated_promotion_allowed"])
                    self.assertFalse(payload["atlas_claims_created"])
                    self.assertFalse(
                        payload["scope"]["data_center_identity_confirmed"]
                    )
                    self.assertFalse(payload["scope"]["lifecycle_status_confirmed"])
                    self.assertFalse(payload["scope"]["operating_status_inferred"])
                    self.assertFalse(payload["scope"]["power_or_energy_inferred"])
                else:
                    self.assertFalse(payload["classification"]["identity_claim"])
                    self.assertFalse(payload["classification"]["lifecycle_claim"])
        self.assertEqual(
            sum(
                pair["source_run"] == "global-open-v3-unknown-013"
                for pair in definition["review_pairs"]
            ),
            6,
        )

    def test_v4_definition_is_exactly_the_candidate_v13_review_set(self):
        definition_raw = DEFINITION_V4.read_bytes()
        definition = json.loads(definition_raw)
        candidate = json.loads(
            CANDIDATE_DEFINITION_V13.read_text(encoding="utf-8")
        )
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, sort_keys=True) + "\n").encode(),
        )
        fusion = definition["candidate_fusion"]
        self.assertEqual(
            fusion["definition"],
            {
                "path": CANDIDATE_DEFINITION_V13.name,
                "bytes": 25045,
                "sha256": "63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33",
            },
        )
        self.assertEqual(
            fusion["manifest"],
            {
                "path": "../candidate_fusion/2026-07-18-osm-planet-priority-v13/manifest.json",
                "bytes": 28964,
                "sha256": "12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9",
            },
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_DEFINITION_V13.read_bytes()).hexdigest(),
            fusion["definition"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_MANIFEST_V13.read_bytes()).hexdigest(),
            fusion["manifest"]["sha256"],
        )
        expected = sorted(
            (
                spec["queue_id"],
                spec["report_path"],
                spec["report_sha256"],
                spec["path"],
                spec["sha256"],
            )
            for spec in candidate["inputs"]["satellite_analyst_reviews"]
        )
        actual = [
            (
                pair["queue_id"],
                pair["report"]["path"],
                pair["report"]["sha256"],
                pair["review"]["path"],
                pair["review"]["sha256"],
            )
            for pair in definition["review_pairs"]
        ]
        self.assertEqual(len(actual), 43)
        self.assertEqual(actual, expected)
        self.assertEqual(
            [pair["queue_id"] for pair in definition["review_pairs"]],
            sorted(pair["queue_id"] for pair in definition["review_pairs"]),
        )
        for pair in definition["review_pairs"]:
            for kind in ("report", "review"):
                checkpoint = pair[kind]
                path = (DEFINITION_V4.parent / checkpoint["path"]).resolve()
                raw = path.read_bytes()
                self.assertEqual(len(raw), checkpoint["bytes"])
                self.assertEqual(
                    hashlib.sha256(raw).hexdigest(), checkpoint["sha256"]
                )
                payload = json.loads(raw)
                if kind == "review":
                    self.assertFalse(payload["automated_promotion_allowed"])
                    self.assertFalse(payload["atlas_claims_created"])
                    self.assertFalse(
                        payload["scope"]["data_center_identity_confirmed"]
                    )
                    self.assertFalse(payload["scope"]["lifecycle_status_confirmed"])
                    self.assertFalse(payload["scope"]["operating_status_inferred"])
                    self.assertFalse(payload["scope"]["power_or_energy_inferred"])
                else:
                    self.assertFalse(payload["classification"]["identity_claim"])
                    self.assertFalse(payload["classification"]["lifecycle_claim"])
        self.assertEqual(
            sum(
                pair["source_run"] == "global-open-v3-unknown-015"
                for pair in definition["review_pairs"]
            ),
            6,
        )

    def test_v2_summary_recomputes_contingencies_without_generalization(self):
        summary = json.loads(
            (BUNDLE_V2 / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["scope"], SCOPE_POLICY_V2)
        self.assertFalse(summary["scope"]["sample_is_random"])
        self.assertTrue(summary["scope"]["sample_is_selected"])
        self.assertFalse(summary["scope"]["accuracy_generalization_claimed"])
        self.assertFalse(summary["scope"]["production_threshold_selected"])
        self.assertFalse(summary["scope"]["recall_denominator_available"])
        for distribution in summary["metric_distributions"].values():
            self.assertEqual(distribution["all"]["count"], 31)
            self.assertEqual(distribution["reject"]["count"], 23)
            self.assertEqual(distribution["retain"]["count"], 8)
        expected = {
            "any-filtered-component": (1, 22, 0, 8),
            "proposal-area-ge-10000-m2": (2, 21, 0, 8),
            "proposal-area-ge-50000-m2": (6, 17, 0, 8),
            "proposal-fraction-ge-0.01": (5, 18, 0, 8),
            "proposal-fraction-ge-0.05": (20, 3, 5, 3),
        }
        for evaluation in summary["rule_evaluations"]:
            self.assertEqual(
                tuple(evaluation["contingency"].values()),
                expected[evaluation["rule"]["id"]],
            )
            self.assertIn(
                "not a production threshold", evaluation["interpretation"]
            )

    def test_v3_summary_recomputes_contingencies_without_promotion(self):
        summary = json.loads(
            (BUNDLE_V3 / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["scope"], SCOPE_POLICY_V3)
        self.assertEqual(
            summary["sample"],
            {
                "count": 37,
                "outcome_counts": {"reject": 27, "retain": 10},
                "source_run_counts": {
                    "global-open-v3-active-001": 7,
                    "global-open-v3-proposed-001": 1,
                    "global-open-v3-unknown-010": 23,
                    "global-open-v3-unknown-013": 6,
                },
            },
        )
        for key in (
            "accuracy_generalization_claimed",
            "analyst_decision_is_construction_truth",
            "analyst_decision_is_pixel_truth",
            "automatic_merge_performed",
            "identity_claim_promoted",
            "lifecycle_claim_promoted",
            "operating_status_promoted",
            "power_or_energy_promoted",
            "production_threshold_selected",
            "recall_denominator_available",
            "type_or_workload_claim_promoted",
        ):
            self.assertFalse(summary["scope"][key])
        self.assertTrue(
            summary["scope"]["analyst_decision_is_site_aligned_followup_label"]
        )
        for distribution in summary["metric_distributions"].values():
            self.assertEqual(distribution["all"]["count"], 37)
            self.assertEqual(distribution["reject"]["count"], 27)
            self.assertEqual(distribution["retain"]["count"], 10)
        expected = {
            "any-filtered-component": (1, 26, 0, 10),
            "proposal-area-ge-10000-m2": (2, 25, 0, 10),
            "proposal-area-ge-50000-m2": (7, 20, 0, 10),
            "proposal-fraction-ge-0.01": (5, 22, 0, 10),
            "proposal-fraction-ge-0.05": (20, 7, 7, 3),
        }
        for evaluation in summary["rule_evaluations"]:
            self.assertEqual(
                tuple(evaluation["contingency"].values()),
                expected[evaluation["rule"]["id"]],
            )
            self.assertIn(
                "not a production threshold", evaluation["interpretation"]
            )

    def test_v4_summary_recomputes_contingencies_without_promotion(self):
        summary = json.loads(
            (BUNDLE_V4 / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["scope"], SCOPE_POLICY_V4)
        self.assertEqual(
            summary["sample"],
            {
                "count": 43,
                "outcome_counts": {"reject": 31, "retain": 12},
                "source_run_counts": {
                    "global-open-v3-active-001": 7,
                    "global-open-v3-proposed-001": 1,
                    "global-open-v3-unknown-010": 23,
                    "global-open-v3-unknown-013": 6,
                    "global-open-v3-unknown-015": 6,
                },
            },
        )
        for key in (
            "accuracy_generalization_claimed",
            "analyst_decision_is_construction_truth",
            "analyst_decision_is_pixel_truth",
            "automatic_merge_performed",
            "identity_claim_promoted",
            "lifecycle_claim_promoted",
            "operating_status_promoted",
            "power_or_energy_promoted",
            "production_threshold_selected",
            "recall_denominator_available",
            "type_or_workload_claim_promoted",
        ):
            self.assertFalse(summary["scope"][key])
        self.assertTrue(
            summary["scope"]["analyst_decision_is_site_aligned_followup_label"]
        )
        for distribution in summary["metric_distributions"].values():
            self.assertEqual(distribution["all"]["count"], 43)
            self.assertEqual(distribution["reject"]["count"], 31)
            self.assertEqual(distribution["retain"]["count"], 12)
        expected = {
            "any-filtered-component": (2, 29, 0, 12),
            "proposal-area-ge-10000-m2": (3, 28, 0, 12),
            "proposal-area-ge-50000-m2": (8, 23, 0, 12),
            "proposal-fraction-ge-0.01": (5, 26, 0, 12),
            "proposal-fraction-ge-0.05": (24, 7, 7, 5),
        }
        for evaluation in summary["rule_evaluations"]:
            self.assertEqual(
                tuple(evaluation["contingency"].values()),
                expected[evaluation["rule"]["id"]],
            )
            self.assertIn(
                "not a production threshold", evaluation["interpretation"]
            )

    def test_definition_is_exactly_the_candidate_v9_review_set(self):
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        candidate = json.loads(CANDIDATE_DEFINITION.read_text(encoding="utf-8"))
        fusion = definition["candidate_fusion"]
        self.assertEqual(
            fusion["definition"],
            {
                "path": CANDIDATE_DEFINITION.name,
                "bytes": 15427,
                "sha256": "e525b85df09feea10a354d41a0c0896a59963d9916e106b106aef13098f03871",
            },
        )
        self.assertEqual(
            fusion["manifest"],
            {
                "path": "../candidate_fusion/2026-07-18-osm-planet-priority-v9/manifest.json",
                "bytes": 19695,
                "sha256": "ea0ad82b3082c7473282196246da616f2957247a80ddd126abee5a030375db11",
            },
        )
        self.assertEqual(
            hashlib.sha256(CANDIDATE_MANIFEST.read_bytes()).hexdigest(),
            fusion["manifest"]["sha256"],
        )
        expected = {
            spec["queue_id"]: (
                spec["report_path"],
                spec["report_sha256"],
                spec["path"],
                spec["sha256"],
            )
            for spec in candidate["inputs"]["satellite_analyst_reviews"]
        }
        actual = {
            pair["queue_id"]: (
                pair["report"]["path"],
                pair["report"]["sha256"],
                pair["review"]["path"],
                pair["review"]["sha256"],
            )
            for pair in definition["review_pairs"]
        }
        self.assertEqual(len(actual), 25)
        self.assertEqual(actual, expected)
        self.assertEqual(
            [pair["queue_id"] for pair in definition["review_pairs"]],
            sorted(actual),
        )

    def test_rows_are_metric_only_hash_linked_calibration_records(self):
        records = _records()
        self.assertEqual(len(records), 25)
        self.assertTrue(all(set(record) == set(ROW_FIELDS) for record in records))
        self.assertEqual(
            {record["outcome"] for record in records}, {"retain", "reject"}
        )
        self.assertEqual(
            {record["source_run"] for record in records},
            {
                "global-open-v3-active-001",
                "global-open-v3-proposed-001",
                "global-open-v3-unknown-009",
            },
        )
        for record in records:
            self.assertEqual(set(METRIC_NAMES), set(record) & set(METRIC_NAMES))
            self.assertRegex(record["report_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(record["review_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(record["mgrs_tile"], record["mgrs_tile"].upper())
            encoded = json.dumps(record, sort_keys=True)
            self.assertNotRegex(encoded, r"\.(?:png|tif|tiff|geojson)\b")
        self.assertEqual(
            {path.name for path in BUNDLE.iterdir()},
            {
                "ATTRIBUTION.txt",
                "README.md",
                "calibration-records.csv",
                "calibration-records.jsonl",
                "manifest.json",
                "manifest.sha256",
                "summary.json",
            },
        )

    def test_summary_reports_distributions_and_descriptive_rule_counts(self):
        summary = json.loads((BUNDLE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["scope"], SCOPE_POLICY)
        self.assertFalse(summary["scope"]["sample_is_random"])
        self.assertTrue(summary["scope"]["sample_is_selected"])
        self.assertFalse(summary["scope"]["analyst_decision_is_pixel_truth"])
        self.assertFalse(summary["scope"]["analyst_decision_is_construction_truth"])
        self.assertFalse(summary["scope"]["recall_denominator_available"])
        self.assertFalse(summary["scope"]["accuracy_generalization_claimed"])
        self.assertFalse(summary["scope"]["production_threshold_selected"])
        self.assertFalse(summary["scope"]["raw_images_included"])
        self.assertEqual(set(summary["metric_distributions"]), set(METRIC_NAMES))
        for distribution in summary["metric_distributions"].values():
            self.assertEqual(distribution["all"]["count"], 25)
            self.assertEqual(distribution["reject"]["count"], 18)
            self.assertEqual(distribution["retain"]["count"], 7)
            for outcome in ("all", "reject", "retain"):
                self.assertLessEqual(
                    distribution[outcome]["min"], distribution[outcome]["median"]
                )
                self.assertLessEqual(
                    distribution[outcome]["median"], distribution[outcome]["max"]
                )
        expected = {
            "any-filtered-component": (1, 17, 0, 7),
            "proposal-area-ge-10000-m2": (2, 16, 0, 7),
            "proposal-area-ge-50000-m2": (5, 13, 0, 7),
            "proposal-fraction-ge-0.01": (5, 13, 0, 7),
            "proposal-fraction-ge-0.05": (15, 3, 4, 3),
        }
        for evaluation in summary["rule_evaluations"]:
            contingency = evaluation["contingency"]
            self.assertEqual(
                tuple(contingency.values()), expected[evaluation["rule"]["id"]]
            )
            self.assertIn("not a production threshold", evaluation["interpretation"])
            self.assertIn(
                "not a label-tuned or production threshold",
                evaluation["rule"]["rationale"],
            )

    def test_predeclared_rule_boundaries_are_inclusive(self):
        for rule in PREDECLARED_RULES:
            metric = rule["metric"]
            threshold = rule["threshold"]
            self.assertTrue(evaluate_rule({metric: threshold}, rule))
            self.assertFalse(evaluate_rule({metric: threshold - 0.000001}, rule))
        with self.assertRaisesRegex(SatelliteCalibrationError, "predeclared"):
            evaluate_rule(
                {"proposal_component_count": 1},
                {
                    "id": "post-hoc",
                    "metric": "proposal_component_count",
                    "operator": ">=",
                    "threshold": 1,
                    "unit": "count",
                    "rationale": "not declared",
                },
            )

    def test_quick_validation_fails_closed_on_tampered_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "calibration"
            shutil.copytree(BUNDLE, copied)
            summary_path = copied / "summary.json"
            summary_path.chmod(0o644)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["sample"]["count"] = 24
            summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SatelliteCalibrationError, "output changed: summary.json"
            ):
                validate_satellite_calibration(copied)


if __name__ == "__main__":
    unittest.main()
