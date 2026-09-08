"""Source scope and frozen-row checks for the twelve-site expansion checkpoint."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_initial_five as earlier
from datacenter_atlas import expansion_200_second_reviewed as batch
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
EUROPE = SOURCES / "verified-construction-core-v0.18-goodman-europe-three-geometry-facts.json"
FRANKFURT = SOURCES / "verified-construction-core-v0.18-goodman-fra02-geometry-facts.json"
US = SOURCES / "verified-construction-core-v0.18-us-research-geometry-facts.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class SecondReviewedDraftTests(unittest.TestCase):
    def test_goodman_identity_does_not_refresh_june_construction(self) -> None:
        for slug in ("par01-paris", "par02-paris", "ams01-amsterdam", "fra02-frankfurt"):
            location = SOURCES / f"curated-official-2026-09-08-goodman-{slug}-reviewed-location.json"
            status = SOURCES / f"curated-official-2026-09-08-goodman-{slug}-fy26-current-build.json"
            curated._parse_document(location, "2026-09-08T19:41:03Z")
            curated._parse_document(status, "2026-09-08T19:41:03Z")
            identity, physical = read(location), read(status)
            self.assertEqual(identity["lifecycle"], [])
            self.assertEqual(physical["lifecycle"][0]["as_of_date"], "2026-06-30")
            self.assertEqual(physical["lifecycle"][0]["value"], "under_construction")
            for entity in ("campus", "project"):
                self.assertEqual(identity[entity]["stable_key"], physical[entity]["stable_key"])
                self.assertEqual(identity[entity]["as_of_date"], "2026-09-08")
                self.assertEqual(identity[entity]["roles"], {})
                self.assertIsNone(identity[entity]["coordinates"])
                self.assertIsNone(identity[entity]["geometry"])

    def test_exact_paris_addresses_and_amsterdam_notice_point(self) -> None:
        payload = read(EUROPE)
        for index, feature_id, coordinates in (
            (0, "93073_0419_00013", [2.569445, 48.967618]),
            (1, "94078_1123_00034", [2.447152, 48.760391]),
        ):
            metadata = payload["evidence"][index]["metadata"]
            self.assertEqual(metadata["selected_feature_id"], feature_id)
            self.assertEqual(metadata["selected_type"], "housenumber")
            self.assertEqual(payload["results"][index]["geometry"]["coordinates"], coordinates)
        amsterdam = payload["evidence"][2]["metadata"]
        self.assertEqual(amsterdam["source_crs"], "EPSG:28992")
        self.assertEqual(amsterdam["source_wkt"], "POINT(108545 488162)")
        self.assertEqual(payload["results"][2]["geometry"]["coordinates"],
                         [4.704939898256592, 52.37935680103495])
        record = read(SOURCES / "curated-official-2026-09-08-goodman-ams01-amsterdam-reviewed-location.json")
        identity = record["evidence"][0]["metadata"]["selected_project_metadata"]
        self.assertEqual(identity["prjt_id"], 1000235227)
        self.assertEqual(identity["address_line1"], "Hybrideweg 105")
        self.assertIn("No certification", record["evidence"][0]["metadata"]["excluded_claims"])

    def test_frankfurt_uses_published_marker_not_viewport(self) -> None:
        payload = read(FRANKFURT)
        identity = read(SOURCES / "curated-official-2026-09-08-goodman-fra02-frankfurt-reviewed-location.json")
        self.assertEqual(payload["evidence"][0], identity["evidence"][2])
        self.assertEqual(payload["results"][0]["geometry"]["coordinates"], [8.685529, 50.0427])
        metadata = payload["evidence"][0]["metadata"]
        self.assertEqual(metadata["rejected_viewport_center"]["longitude"], 8.683335)
        self.assertIn("!3d50.0427!4d8.685529", metadata["effective_url"])
        self.assertTrue(all(e["published_at"] is None for e in identity["evidence"]))

    def test_us_constituents_and_event_dates_remain_explicit(self) -> None:
        payload = read(US)
        for index, date in ((1, "2025-02-25"), (5, "2026-08-04"),
                            (6, "2026-07-23"), (10, "2026-03-13")):
            evidence = payload["evidence"][index]
            self.assertIsNone(evidence["published_at"])
            self.assertEqual(evidence["metadata"]["source_event_date"]["date"], date)
        for index in (0, 1, 3):
            for entity in ("campus", "project"):
                identity = payload["identities"][index][entity]
                self.assertEqual(identity["roles"], {})
                self.assertEqual(identity["method"], "authoritative_locality")
                self.assertIsNone(identity["coordinates"])
                self.assertIsNone(identity["geometry"])
            self.assertEqual(payload["results"][index]["semantics"]["geometry_use_scope"],
                             "campus_locator")
        portal = payload["evidence"][12]["metadata"]
        self.assertEqual(portal["government_host"], "maps.buckscounty.gov")
        self.assertEqual(portal["portal_organization_id"], "SP47Tddf7RK32lBU")
        self.assertIn(portal["portal_organization_id"], payload["evidence"][2]["source_url"])
        self.assertEqual(payload["results"][1]["geometry"]["coordinates"],
                         [-77.49150786, 38.96099867])
        self.assertIn("not asserted to locate the unnamed 96 MW", payload["results"][1]["semantics"]["precision_scope"])
        self.assertEqual(payload["results"][3]["geometry"]["coordinates"],
                         [-100.867099886006, 33.780636279018])
        self.assertIn("Phase II's separate 1003 FM 193", payload["results"][3]["semantics"]["precision_scope"])

    def test_polygon_anchor_and_all_geometry_scopes(self) -> None:
        us = read(US)
        amazon = us["results"][0]
        ring = amazon["geometry"]["coordinates"][0]
        self.assertEqual(len(ring), 41)
        self.assertEqual(ring[0], ring[-1])
        midpoint = [(min(p[i] for p in ring)+max(p[i] for p in ring))/2 for i in (0, 1)]
        self.assertEqual(amazon["display_anchor"]["coordinates"], midpoint)
        for path in (EUROPE, FRANKFURT, US):
            for geometry in read(path)["results"]:
                draft._geometry(geometry)
                self.assertEqual(geometry["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(geometry["semantics"]["horizontal_uncertainty_metres"])
                self.assertTrue(geometry["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_research_holds_are_not_selected(self) -> None:
        contract = read(batch.contract_path(ROOT))
        selected = {row["project_stable_key"] for row in contract["acceptances"]}
        self.assertNotIn(read(US)["identities"][2]["project_stable_key"], selected)
        self.assertFalse(any("freestone" in row["source_id"] for row in contract["sources"]))
        review = read(ROOT / "research/expansion-200/americas-review-2026-09-08.json")
        captures = {row["capture_id"] for row in review["captures"]}
        self.assertEqual(len(captures), len(review["captures"]))
        for row in review["decisions"]:
            self.assertFalse(row["accepted_into_core"])
            self.assertNotIn(row["project_stable_key"], selected)
            self.assertTrue(set(row["capture_ids"]) <= captures)
        handoff = read(ROOT / "research/expansion-200/us-locator-handoff-2026-09-08.json")
        self.assertFalse(handoff["accepted_into_core"])
        self.assertEqual(handoff["geometry_fact_package"]["sha256"], hashlib.sha256(US.read_bytes()).hexdigest())

    def test_every_five_site_checkpoint_row_and_map_feature_is_preserved(self) -> None:
        for name, key in (("projects.csv", "project_id"), ("sites.csv", "site_id"),
                          ("evidence.csv", "evidence_id")):
            previous = table(earlier.draft_path(ROOT) / name)
            current = {row[key]: row for row in table(batch.draft_path(ROOT) / name)}
            for row in previous:
                self.assertEqual(current[row[key]], row)
        for path in earlier.draft_path(ROOT).glob("*.geojson"):
            previous = read(path)["features"]
            current = read(batch.draft_path(ROOT) / path.name)["features"]
            for feature in previous:
                self.assertIn(feature, current)

    def test_twelve_site_checkpoint_reproduces_with_expanded_gaps(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 112, "projects": 115, "evidence": 295,
            "countries": 40, "non_us_sites": 78,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 110,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        report = read(stored / "selection-report.json")
        self.assertEqual(report["final_release_gates"]["imagery_outcomes_complete"],
                         {"actual": 10, "required": 115, "passed": False})
        selected = {row["project_stable_key"] for row in read(batch.contract_path(ROOT))["acceptances"]}
        for row in table(stored / "projects.csv"):
            if row["project_stable_key"] in selected:
                self.assertLessEqual(row["status_as_of"], "2026-08-20")
                self.assertGreaterEqual(row["status_as_of"], "2026-05-22")
                self.assertEqual(row["role_claims_json"], "[]")
                self.assertEqual(row["power_observations_json"], "[]")
        with tempfile.TemporaryDirectory(prefix="atlas-twelve-rebuild-") as temp:
            rebuilt = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, rebuilt, root=ROOT)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in rebuilt.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (rebuilt / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
