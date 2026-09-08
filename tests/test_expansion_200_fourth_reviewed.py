"""Twenty-eight-site checkpoint with preserved prior rows and scoped locators."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_fourth_reviewed as batch
from datacenter_atlas import expansion_200_third_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
NEXTDC = SOURCES / "verified-construction-core-v0.18-asia-round4-nextdc-four-reviewed-geometry.json"
MERLIN = SOURCES / "verified-construction-core-v0.18-merlin-two-reviewed-geometry.json"
LAPORTE = SOURCES / "verified-construction-core-v0.18-americas-round4-la-porte-geometry-facts.json"
LEBANON = SOURCES / "verified-construction-core-v0.18-americas-round4-meta-lebanon-geometry-facts.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FourthReviewedDraftTests(unittest.TestCase):
    def test_eight_source_packages_preserve_observation_dates_and_empty_fields(self) -> None:
        expected = {
            **{f"asia-round4-nextdc-{code}-fy26-current-build": ("2026-06-30", "mep_electrical")
               for code in ("m2", "m3", "s3")},
            "asia-round4-nextdc-s4-fy26-current-build": ("2026-06-30", "under_construction"),
            "merlin-bilbao-arasur-reviewed-build": ("2026-06-30", "under_construction"),
            "merlin-lisbon-reviewed-build": ("2026-07-27", "under_construction"),
            "americas-round4-microsoft-la-porte-current-build": ("2026-06-18", "under_construction"),
            "americas-round4-meta-lebanon-current-build": ("2026-07-06", "under_construction"),
        }
        for name, (date, stage) in expected.items():
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            curated._parse_document(path, "2026-09-08T21:15:00Z")
            doc = read(path)
            self.assertEqual(len(doc["lifecycle"]), 1)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], date)
            self.assertEqual(doc["lifecycle"][0]["value"], stage)
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_nextdc_retrospective_inventory_has_exact_project_document_bindings(self) -> None:
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        selected = [a for a in validated.acceptances
                    if a["project"]["stable_key"].startswith("curated:nextdc-")]
        self.assertEqual(len(selected), 4)
        for row in selected:
            status_id = row["acceptance"]["status"]["source_id"]
            source = validated.sources[status_id]
            self.assertEqual(source["document"]["project"]["stable_key"], row["project"]["stable_key"])
            self.assertEqual(source["evidence"]["published_at"], "2026-08-27")
            self.assertEqual(row["status"]["as_of_date"], "2026-06-30")
            self.assertTrue(source["evidence"]["metadata"]["publication_after_lifecycle_cutoff"])
            self.assertIn("nextdc-fy26-construction-definition", row["geometry"]["identity_source_ids"])

    def test_nextdc_points_keep_source_authority_and_conflicting_marker_explicit(self) -> None:
        doc = read(NEXTDC)
        self.assertEqual([r["geometry"]["coordinates"] for r in doc["results"]], [
            [144.8756939, -37.7080294], [144.8638438, -37.8048639],
            [151.1845739, -33.8190826], [150.82457, -33.82784],
        ])
        self.assertEqual([r["semantics"]["geometry_authority_class"] for r in doc["results"]],
                         ["official_source", "community_source", "community_source", "official_source"])
        self.assertEqual(doc["evidence"][1]["license"], "ODbL-1.0")
        self.assertIn("no OSM address tag", doc["results"][1]["semantics"]["precision_scope"])
        self.assertIn("Adjacent S6 is not separately counted", doc["results"][2]["semantics"]["precision_scope"])
        self.assertIn("rounded application longitude", doc["results"][3]["semantics"]["precision_scope"])
        extra = read(SOURCES / "verified-construction-core-v0.18-nextdc-m3-locator-discrepancy-review.json")
        self.assertEqual(extra["evidence"][1]["metadata"]["unselected_lon_lat"], [144.8645087, -37.8015782])
        self.assertEqual(extra["evidence"][2]["metadata"]["address_check_lon_lat"], [144.8654833, -37.8035123])
        self.assertIn("conflicting", extra["decision"])

    def test_merlin_counts_each_campus_once_and_hashes_redirect_headers(self) -> None:
        doc = read(MERLIN)
        self.assertEqual([r["geometry"]["coordinates"] for r in doc["results"]],
                         [[-2.909169, 42.697694], [-8.963743, 38.988289]])
        redirect = doc["evidence"][0]
        self.assertIn("HTTP response-header", redirect["metadata"]["content_hash_scope"])
        self.assertEqual(redirect["content_hash"], "62626e113a65b3cd6b98eff98fae6d46048f8c3ddac83e954641345e86467fd1")
        self.assertEqual(redirect["metadata"]["body_bytes"], 0)
        projects = [a["project_stable_key"] for a in read(batch.contract_path(ROOT))["acceptances"]]
        self.assertEqual(sum("merlin-edged-bilbao-arasur-campus:" in key for key in projects), 1)
        self.assertEqual(sum("merlin-lisbon-data-center-campus:" in key for key in projects), 1)
        for name, old in (
            ("bilbao-arasur", "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json"),
            ("lisbon", "curated-official-2026-07-20-merlin-lisbon-phase-2.json"),
        ):
            new = read(SOURCES / f"curated-official-2026-09-08-merlin-{name}-reviewed-build.json")
            previous_source = read(SOURCES / old)
            for entity in ("campus", "project"):
                self.assertEqual(new[entity]["stable_key"], previous_source[entity]["stable_key"])
                self.assertEqual(new[entity]["name"], previous_source[entity]["name"])

    def test_la_porte_is_constituent_parcel_not_entire_campus_or_future_expansion(self) -> None:
        doc = read(LAPORTE)
        locator = doc["results"][0]
        self.assertEqual(locator["geometry"]["type"], "Polygon")
        self.assertEqual(locator["display_anchor"]["coordinates"], [-86.69006414, 41.57958055])
        self.assertEqual(doc["evidence"][3]["metadata"]["selected_state_parcel_id"], "461107326005000058")
        self.assertEqual(doc["evidence"][2]["metadata"]["native_crs"], "EPSG:4326")
        self.assertIn("not the whole campus boundary", locator["semantics"]["precision_scope"])
        self.assertIn("proposed eastern expansion", locator["semantics"]["precision_scope"])
        source = read(SOURCES / "curated-official-2026-09-08-americas-round4-microsoft-la-porte-current-build.json")
        self.assertTrue(source["evidence"][1]["metadata"]["not_selected_as_day_precision_lifecycle"])
        self.assertEqual(source["evidence"][1]["metadata"]["source_observation_period"]["precision"], "month")

    def test_lebanon_is_exact_named_permit_locator_with_limited_datum_claim(self) -> None:
        doc = read(LEBANON)
        self.assertEqual(doc["results"][0]["geometry"]["coordinates"], [-86.53099064914196, 40.06429731968878])
        self.assertIn("Project Domino/META", doc["evidence"][0]["metadata"]["source_aliases"])
        meta = doc["evidence"][4]["metadata"]
        self.assertEqual(meta["selected_folder_id"], "FW-33468-0")
        self.assertEqual(meta["native_geometry_crs"], "EPSG:3857")
        self.assertEqual(meta["output_geometry_crs"], "EPSG:4326")
        self.assertIn("does not validate the original", meta["transform_provenance"]["accuracy_scope"])
        self.assertIn("not a data-center building", doc["results"][0]["semantics"]["precision_scope"])

    def test_all_new_locators_have_explicit_scope_and_unknown_accuracy(self) -> None:
        for path in (NEXTDC, MERLIN, LAPORTE, LEBANON):
            for locator in read(path)["results"]:
                draft._geometry(locator)
                self.assertEqual(locator["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(locator["semantics"]["horizontal_uncertainty_metres"])
                self.assertTrue(locator["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_every_prior_row_and_source_is_unchanged(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {r[key]: r for r in table(new_dir / filename)}
            for row in table(old_dir / filename):
                self.assertEqual(row, current[row[key]])
        for feature in read(old_dir / "sites.geojson")["features"]:
            self.assertIn(feature, read(new_dir / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
        current = {a["project_stable_key"]: a for a in new["acceptances"]}
        for old_acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[old_acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = old_acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, old_acceptance)

    def test_checkpoint_rebuilds_exactly_and_remains_partial(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 128, "projects": 131, "evidence": 362,
            "countries": 40, "non_us_sites": 89,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 126,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 28, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 131, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 131)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-twenty-eight-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
