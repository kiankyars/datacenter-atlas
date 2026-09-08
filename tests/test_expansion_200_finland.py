"""Reviewed Finnish source scope and cumulative-five draft integration."""

from __future__ import annotations

import csv
from decimal import Decimal, localcontext
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft
from datacenter_atlas import expansion_200_initial_five as batch
from datacenter_atlas import expansion_200_initial_three as first


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "sources/verified-construction-core-v0.18-finland-two-geometry-facts.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FinlandDraftTests(unittest.TestCase):
    def test_curated_identity_is_separate_from_june_status(self) -> None:
        for slug, date in (("kirkkonummi-first-building", "2026-06-26"),
                           ("espoo-second-building", "2026-06-11")):
            path = ROOT / f"sources/curated-official-2026-09-08-microsoft-{slug}-current-build.json"
            parsed = curated._parse_document(path, "2026-09-08T19:09:41Z")
            payload = json.loads(path.read_text())
            self.assertEqual(len(parsed.evidence), 3)
            self.assertEqual(parsed.lifecycle[0].as_of_date, date)
            self.assertEqual(payload["lifecycle"][0]["evidence_key"], payload["evidence"][0]["key"])
            for entity in (payload["campus"], payload["project"]):
                self.assertEqual(entity["as_of_date"], "2026-09-08")
                self.assertEqual(entity["evidence_key"], payload["evidence"][1]["key"])
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
            if slug == "espoo-second-building":
                self.assertIsNone(payload["evidence"][0]["published_at"])
                self.assertIsNone(payload["evidence"][1]["published_at"])
                self.assertEqual(payload["evidence"][0]["metadata"]["meeting_date"], "2026-06-11")
                self.assertEqual(payload["evidence"][1]["metadata"]["decision_date"], "2025-03-20")

    def test_parcel_centroid_uses_exact_decimal_planar_arithmetic(self) -> None:
        payload = json.loads(GEOMETRY.read_text())
        derivation = payload["derivations"]["espoo"]
        points = [[Decimal(str(x)) for x in point] for point in derivation["native_coordinates"][0]]
        with localcontext() as context:
            context.prec = 40
            area2 = sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:]))
            center = [sum((a[i]+b[i])*(a[0]*b[1]-b[0]*a[1])
                          for a, b in zip(points, points[1:]))/(3*area2) for i in (0, 1)]
        self.assertEqual(float(abs(area2)/2), 167790.230503)
        self.assertEqual([float(x) for x in center], derivation["native_centroid"])
        self.assertEqual(payload["results"][1]["display_anchor"]["coordinates"],
                         [24.687531695669563, 60.23775070138893])
        self.assertEqual(payload["evidence"][1]["license"], "CC-BY-4.0")
        self.assertEqual(payload["evidence"][1]["metadata"]["parcel_identifier"], "49-65-3-1")
        self.assertEqual(payload["evidence"][1]["metadata"]["feature_count"], 1)

    def test_geometry_never_promotes_parcel_or_permit_to_dc_boundary(self) -> None:
        payload = json.loads(GEOMETRY.read_text())
        self.assertEqual(payload["results"][0]["geometry"]["coordinates"],
                         [24.5488365702344, 60.145133329678934])
        self.assertEqual(payload["derivations"]["kirkkonummi"]["native_easting_northing"],
                         [363900, 6670100])
        for row in payload["results"]:
            draft._geometry(row)
            self.assertIn(row["semantics"]["geometry_use_scope"], {"campus_locator", "project_locator"})
            self.assertIsNone(row["semantics"]["horizontal_uncertainty_metres"])
            self.assertTrue(row["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_cumulative_five_preserves_every_initial_three_row(self) -> None:
        for name, key in (("projects.csv", "project_id"), ("sites.csv", "site_id"),
                          ("evidence.csv", "evidence_id")):
            earlier = table(first.draft_path(ROOT) / name)
            later = {row[key]: row for row in table(batch.draft_path(ROOT) / name)}
            for row in earlier:
                self.assertEqual(later[row[key]], row)

    def test_cumulative_five_reproduces_and_keeps_gaps_explicit(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 105, "projects": 108, "evidence": 265,
            "countries": 40, "non_us_sites": 74,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 103,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        report = json.loads((stored / "selection-report.json").read_text())
        self.assertEqual(report["final_release_gates"]["imagery_outcomes_complete"],
                         {"actual": 10, "required": 108, "passed": False})
        with tempfile.TemporaryDirectory(prefix="atlas-five-rebuild-") as temp:
            rebuilt = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, rebuilt, root=ROOT)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in rebuilt.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (rebuilt / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
