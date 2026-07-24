from __future__ import annotations

import unittest

from datacenter_atlas.models import (
    Building,
    CapacityEstimate,
    CapacityMetric,
    EstimateMethod,
    Evidence,
    EvidenceKind,
)


class ModelTests(unittest.TestCase):
    def estimate(self, **overrides: object) -> CapacityEstimate:
        values = {
            "id": "estimate-1",
            "entity_id": "facility-1",
            "metric": CapacityMetric.CRITICAL_IT_MW,
            "low": 90.0,
            "base": 100.0,
            "high": 110.0,
            "method": EstimateMethod.REPORTED,
            "confidence": 0.9,
            "evidence_id": "evidence-1",
            "as_of_date": "2026-07-01",
            "recorded_at": "2026-07-02T00:00:00Z",
        }
        values.update(overrides)
        return CapacityEstimate(**values)  # type: ignore[arg-type]

    def test_capacity_metric_units_remain_semantically_distinct(self) -> None:
        self.assertEqual(CapacityMetric.GRID_CONNECTION_MW.unit, "MW")
        self.assertEqual(CapacityMetric.GROSS_FACILITY_MW.unit, "MW")
        self.assertEqual(CapacityMetric.CRITICAL_IT_MW.unit, "MW")
        self.assertEqual(CapacityMetric.GENERATION_NAMEPLATE_MW.unit, "MW")
        self.assertEqual(CapacityMetric.ANNUAL_ENERGY_MWH.unit, "MWh/year")
        self.assertEqual(CapacityMetric.PUE.unit, "ratio")

    def test_capacity_requires_ordered_low_base_high(self) -> None:
        with self.assertRaisesRegex(ValueError, "low <= base <= high"):
            self.estimate(low=101.0, base=100.0)

    def test_capacity_rejects_invalid_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            self.estimate(confidence=1.1)

    def test_pue_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUE"):
            self.estimate(metric=CapacityMetric.PUE, low=0.0, base=0.0, high=1.0)

    def test_evidence_requires_source_url_and_retrieval_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_url"):
            Evidence(
                id="e1",
                kind=EvidenceKind.THIRD_PARTY_DATASET,
                title="Example dataset",
                source_url="",
                retrieved_at="2026-07-17T00:00:00Z",
            )

    def test_building_requires_facility_parent(self) -> None:
        with self.assertRaisesRegex(ValueError, "facility_id"):
            Building("building-1", "stable", "evidence-1")


if __name__ == "__main__":
    unittest.main()
