"""Thirty-two-site checkpoint with explicit scope and prior-row preservation."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_fifth_reviewed as batch
from datacenter_atlas import expansion_200_fourth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
NEXTDC = SOURCES / "verified-construction-core-v0.18-asia-round5-nextdc-next-three-reviewed-geometry.json"
MERLIN = SOURCES / "verified-construction-core-v0.18-merlin-getafe-ii-reviewed-geometry.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FifthReviewedDraftTests(unittest.TestCase):
    def test_four_source_packages_keep_dated_physical_work_and_unknown_fields(self) -> None:
        expected = {
            "asia-round5-nextdc-m4-fy26-current-build": "site_preparation",
            "asia-round5-nextdc-ge1-fy26-current-build": "under_construction",
            "asia-round5-nextdc-kl1-fy26-current-build": "mep_electrical",
            "merlin-getafe-ii-reviewed-build": "site_preparation",
        }
        for name, stage in expected.items():
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            curated._parse_document(path, "2026-09-08T21:40:00Z")
            doc = read(path)
            self.assertEqual(len(doc["lifecycle"]), 1)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-06-30")
            self.assertEqual(doc["lifecycle"][0]["value"], stage)
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_nextdc_status_document_bindings_and_physical_dependencies(self) -> None:
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        selected = [a for a in validated.acceptances if a["project"]["stable_key"] in {
            r["project_stable_key"] for r in read(NEXTDC)["results"]}]
        self.assertEqual(len(selected), 3)
        for row in selected:
            source = validated.sources[row["acceptance"]["status"]["source_id"]]
            self.assertEqual(source["document"]["project"]["stable_key"], row["project"]["stable_key"])
            self.assertEqual(source["evidence"]["published_at"], "2026-08-27")
            self.assertEqual(row["status"]["as_of_date"], "2026-06-30")
            self.assertTrue(source["evidence"]["metadata"]["publication_after_lifecycle_cutoff"])
            self.assertIn("nextdc-round5-physical-definition", row["geometry"]["identity_source_ids"])

    def test_official_virtual_address_points_and_explicit_ge1_inference(self) -> None:
        doc = read(NEXTDC)
        self.assertEqual([r["geometry"]["coordinates"] for r in doc["results"][:2]], [
            [144.91146374858133, -37.82870623280992], [144.37274245303243, -38.05612850278812],
        ])
        for row in doc["results"][:2]:
            self.assertEqual(row["semantics"]["geometry_authority_class"], "official_source")
            self.assertEqual(row["semantics"]["geometry_scope_class"], "official_virtual_address_campus_reference_point")
            self.assertIn("vicmap-virtual-point-definition", row["geometry_source_ids"])
        self.assertEqual(doc["evidence"][5]["metadata"]["selected_definition"]["code"], "V")
        self.assertEqual(doc["evidence"][0]["license"], "CC-BY-4.0")
        self.assertIn("analyst inference", doc["results"][1]["semantics"]["precision_scope"])
        self.assertIn("nextdc-ge1-kapitol-identity", doc["results"][1]["identity_source_ids"])

    def test_kl1_opening_is_not_completion_of_remaining_fitout(self) -> None:
        doc = read(SOURCES / "curated-official-2026-09-08-asia-round5-nextdc-kl1-fy26-current-build.json")
        self.assertEqual(doc["evidence"][3]["published_at"], "2026-05-14")
        self.assertFalse(doc["evidence"][3]["metadata"]["selected_lifecycle"])
        self.assertIn("remaining 15 MW", doc["evidence"][0]["metadata"]["scope_guardrail"])
        locator = read(NEXTDC)
        self.assertEqual(locator["results"][2]["geometry"]["coordinates"], [101.6284258, 3.0946929])
        self.assertEqual(locator["evidence"][6]["license"], "ODbL-1.0")
        self.assertEqual(locator["evidence"][7]["metadata"]["selected_tags"]["ref"], "KL1")
        self.assertIn("same-named industrial-landuse result is not another campus", locator["results"][2]["semantics"]["precision_scope"])

    def test_getafe_ii_uses_literal_locator_and_retains_status_conflicts(self) -> None:
        doc = read(MERLIN)
        self.assertEqual(doc["results"][0]["geometry"]["coordinates"], [-3.70676, 40.311373])
        self.assertEqual(doc["evidence"][0]["content_hash"], "d2171b5dc409ad7f1c2f8ccb26198d2a7051a70ddc2a331e313204b5b463cedd")
        self.assertIsNone(doc["evidence"][0]["published_at"])
        self.assertIn("forecast", doc["evidence"][0]["metadata"]["status_not_selected"])
        source = read(SOURCES / "curated-official-2026-09-08-merlin-getafe-ii-reviewed-build.json")
        self.assertEqual(source["evidence"][1]["metadata"]["unselected_opening_text"], "20 MW / Now Open / Space Available")
        self.assertIn("origin is not proven", source["evidence"][1]["metadata"]["conflict_resolution"])
        self.assertIn("Fundidores40", source["evidence"][2]["excerpt"])
        self.assertEqual(source["evidence"][3]["metadata"]["release_dateline_date"], "2026-07-27")
        self.assertIn("analyst inference", source["evidence"][0]["metadata"]["identity_inference"])

    def test_all_four_locators_keep_unknown_accuracy_and_campus_only_scope(self) -> None:
        for path in (NEXTDC, MERLIN):
            for locator in read(path)["results"]:
                draft._geometry(locator)
                self.assertEqual(locator["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(locator["semantics"]["horizontal_uncertainty_metres"])
                self.assertTrue(locator["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_every_prior_row_source_and_acceptance_is_preserved(self) -> None:
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
            "physical_sites": 132, "projects": 135, "evidence": 386,
            "countries": 40, "non_us_sites": 93,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 130,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 32, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 135, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 135)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-two-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
