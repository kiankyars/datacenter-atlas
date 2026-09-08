"""Corpus-free integration checks for the reviewed initial-three draft."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import verified_construction_core_v018 as draft
from datacenter_atlas.expansion_200_initial_three import (
    REVIEW_PINS,
    contract_path,
    draft_path,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / draft.BASELINE_RELATIVE_DIR


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class InitialThreeDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="atlas-initial-three-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name) / "draft"
        cls.manifest = draft.build_draft(
            contract_path(ROOT), REVIEW_PINS, cls.output, root=ROOT
        )

    def test_counts_are_additive_and_not_completion(self) -> None:
        self.assertEqual(self.manifest["counts"], {
            "physical_sites": 103, "projects": 106, "evidence": 259,
            "countries": 40, "non_us_sites": 72,
            "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 101,
        })
        self.assertEqual(self.manifest["release_status"], "draft")
        self.assertFalse(self.manifest["publishable_as_final"])
        self.assertFalse(self.manifest["objective_completion_claim"])
        self.assertFalse((self.output / "map.html").exists())

    def test_every_frozen_row_and_feature_is_preserved(self) -> None:
        for name in ("sites.csv", "projects.csv", "evidence.csv"):
            with self.subTest(table=name):
                self.assertTrue((self.output / name).read_bytes().startswith(
                    (BASELINE / name).read_bytes()
                ))
                inherited = rows(BASELINE / name)
                self.assertEqual(rows(self.output / name)[:len(inherited)], inherited)
        baseline = json.loads((BASELINE / "sites.geojson").read_text())
        actual = json.loads((self.output / "sites.geojson").read_text())
        self.assertEqual(actual["features"][:100], baseline["features"])

    def test_source_scoped_points_and_old_status_dates_survive(self) -> None:
        expected = {
            "curated:capitaland-dc-navi-mumbai-campus:tower-2":
                ([73.000187, 19.175772], "2026-07-29", "campus_locator"),
            "curated:capitaland-dc-itph-hyderabad:current-facility-build":
                ([78.38405032, 17.43532415], "2026-07-29", "campus_locator"),
            "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development":
                ([-118.21807054, 34.00507389], "2026-06-30", "project_locator"),
        }
        additions = rows(self.output / "projects.csv")[103:]
        self.assertEqual(len(additions), 3)
        self.assertEqual({row["project_stable_key"] for row in additions}, set(expected))
        for row in additions:
            point, status_date, scope = expected[row["project_stable_key"]]
            with self.subTest(project=row["project_stable_key"]):
                self.assertEqual(json.loads(row["geometry_json"]), {
                    "type": "Point", "coordinates": point,
                })
                self.assertEqual(row["status_as_of"], status_date)
                self.assertEqual(row["geometry_use_scope"], scope)
                self.assertEqual(row["horizontal_uncertainty_metres"], "")
                self.assertTrue(row["horizontal_uncertainty_unknown_reason"])
                self.assertEqual(row["independent_imagery_verification"], "false")
                for field in ("role_claims_json", "workloads_json",
                              "power_observations_json", "annual_energy_observations_json",
                              "efficiency_observations_json"):
                    self.assertEqual(json.loads(row[field]), [])

    def test_coverage_gates_use_the_expanded_cohort(self) -> None:
        report = json.loads((self.output / "selection-report.json").read_text())
        self.assertEqual(report["draft_delta_counts"], {
            "physical_sites": 3, "projects": 3, "evidence": 7,
        })
        gates = report["final_release_gates"]
        self.assertEqual(gates["imagery_outcomes_complete"], {
            "actual": 10, "required": 106, "passed": False,
        })
        self.assertEqual(gates["non_us_site_count"]["required_minimum"], 100)
        self.assertFalse(gates["non_us_site_count"]["passed"])
        self.assertFalse(gates["site_count"]["passed"])
        self.assertFalse(gates["blind_review"]["passed"])
        self.assertFalse(report["accepted_into_published_core"])

    def test_committed_draft_rebuilds_byte_for_byte(self) -> None:
        stored = draft_path(ROOT)
        draft.validate_draft(stored, contract_path(ROOT), REVIEW_PINS, root=ROOT)
        actual_files = {path.name for path in self.output.iterdir()}
        self.assertEqual({path.name for path in stored.iterdir()}, actual_files)
        for name in actual_files:
            with self.subTest(file=name):
                self.assertEqual((stored / name).read_bytes(), (self.output / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
