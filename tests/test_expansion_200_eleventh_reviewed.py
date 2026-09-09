"""Parker checkpoint: exact postal identity and conservative locator semantics."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_eleventh_reviewed as batch
from datacenter_atlas import expansion_200_tenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/curated-official-2026-09-08-americas-round11-flexential-parker-current-build.json"
GEOMETRY = ROOT / "sources/verified-construction-core-v0.18-americas-round11-flexential-parker-geometry-proposal.json"
CAMPUS = "curated:flexential-parker-compark-campus"
PROJECT = CAMPUS + ":first-data-center"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class EleventhReviewedDraftTests(unittest.TestCase):
    def test_dated_current_work_is_not_financing_permits_or_structural_completion(self) -> None:
        doc = read(SOURCE)
        curated._parse_document(SOURCE, "2026-09-09T01:00:00Z")
        self.assertEqual(doc["campus"]["stable_key"], CAMPUS)
        self.assertEqual(doc["project"]["stable_key"], PROJECT)
        self.assertEqual(len(doc["lifecycle"]), 1)
        status, evidence = doc["lifecycle"][0], doc["evidence"][0]
        self.assertEqual(status["as_of_date"], "2026-08-18")
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertEqual(status["evidence_key"], evidence["key"])
        self.assertEqual(evidence["published_at"], "2026-08-18T13:04:00Z")
        self.assertNotEqual(status["as_of_date"], evidence["retrieved_at"][:10])
        self.assertIn("not an onset date", evidence["metadata"]["observation_date_basis"])
        self.assertIn("not completion of the entire data center", evidence["metadata"]["successor_guardrail"])
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["roles"], {})
            self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(doc[entity]["geometry"])
        for field in ("workloads", "capacities", "operating_models"):
            self.assertEqual(doc[field], [])

    def test_exact_town_address_and_county_postal_alias_do_not_borrow_county_geometry(self) -> None:
        evidence = {e["key"]: e for e in read(GEOMETRY)["evidence"]}
        town = evidence["am11-parker-town-den12-address"]
        self.assertIsNone(town["published_at"])
        self.assertEqual(town["metadata"]["permit_date"], "2026-05-29")
        self.assertEqual(town["metadata"]["visually_reviewed_pdf_pages"], [2])
        self.assertEqual(town["metadata"]["project_address"], "15255 COMPARK BLVD")
        self.assertEqual(town["metadata"]["geographic_record_as_printed"], "223305207007")
        self.assertIn("not selected as physical activity", town["metadata"]["identity_scope"])
        county = evidence["am11-parker-county-postal-alias"]["metadata"]
        self.assertEqual(county["selected_pointer"], "/features/1/attributes")
        self.assertEqual(county["selected_attributes"]["STREET_NAME_FULL"], "15255 COMPARK BLVD")
        self.assertEqual(county["selected_attributes"]["PARCEL_SPN"], "223305207007")
        self.assertEqual(county["selected_attributes"]["POSTAL_NAME"], "ENGLEWOOD")
        self.assertEqual(county["selected_attributes"]["ZIP_CODE"], "80112")
        self.assertTrue(county["geometry_excluded"])
        self.assertNotIn("geometry", county)
        self.assertIn("not a reassignment", county["identity_scope"])
        self.assertIn("not borrowed", county["rights_scope"])

    def test_nad83_interpolation_is_not_native_wgs84_or_four_metre_site_accuracy(self) -> None:
        doc = read(GEOMETRY)
        evidence = {e["key"]: e for e in doc["evidence"]}
        point = evidence["am11-parker-census-address-range"]["metadata"]
        result = doc["results"][0]
        coordinates = [-104.811935209928, 39.560940360431]
        self.assertEqual(point["match_count"], 1)
        self.assertEqual(point["matched_address"], "15255 COMPARK BLVD, ENGLEWOOD, CO, 80112")
        self.assertEqual(point["tiger_line_id"], "649062766")
        self.assertEqual(point["source_crs"], "EPSG:4269")
        self.assertEqual(point["source_coordinates"], dict(zip(("x", "y"), coordinates)))
        transform = point["transformation"]
        self.assertEqual(transform["output_coordinates"], coordinates)
        self.assertEqual(transform["operation_accuracy_metres"], 4)
        self.assertIn("not source address-interpolation accuracy", transform["guardrail"])
        self.assertIn("zero matches", point["failed_alternative"])
        self.assertIsNone(point["horizontal_uncertainty_metres"])
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": coordinates})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_address_geocode")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "project_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertIn("Not a campus centre", result["semantics"]["precision_scope"])
        self.assertEqual(evidence["am11-census-nad83-faq"]["metadata"]["visually_reviewed_pdf_pages"], [2])
        self.assertIn("am11-census-public-use-citation", result["geometry_source_ids"])
        draft._geometry(result)

    def test_eight_new_bindings_are_used_and_only_one_existing_candidate_is_admitted(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 51)
        self.assertEqual(len(validated.sources), 282)
        self.assertEqual(new["geometry_identity_reviewed_at"], "2026-09-09")
        old_ids = {s["source_id"] for s in old["sources"]}
        new_sources = {s["source_id"]: s for s in new["sources"]}
        bindings = read(GEOMETRY)["source_binding_map"]
        self.assertEqual(len(bindings), 8)
        self.assertEqual(set(new_sources) - old_ids, {b["source_id"] for b in bindings})
        for binding in bindings:
            for field in ("path", "evidence_pointer"):
                self.assertEqual(new_sources[binding["source_id"]][field], binding[field])
        old_keys = {a["project_stable_key"] for a in old["acceptances"]}
        new_keys = {a["project_stable_key"] for a in new["acceptances"]}
        self.assertEqual(new_keys - old_keys, {PROJECT})
        addition = next(a for a in new["acceptances"] if a["project_stable_key"] == PROJECT)
        self.assertEqual(addition["parent_campus_stable_key"], CAMPUS)
        self.assertTrue({"am11-parker-pcl-structural-completion-caveat", "am11-flexential-index-successor-check"}
                        <= set(addition["distinctness_review"]["evidence_source_ids"]))
        for held in ("curated:microsoft-vaasa-mustasaari-finland-data-center-campus",
                     "curated:google-bermuda-hundred-chesterfield-campus"):
            self.assertNotIn(held, {a["parent_campus_stable_key"] for a in new["acceptances"]})

    def test_every_previous_row_feature_source_and_acceptance_is_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(new_dir / filename)}
            for row in table(old_dir / filename):
                self.assertEqual(row, current[row[key]])
        for feature in read(old_dir / "sites.geojson")["features"]:
            self.assertIn(feature, read(new_dir / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
        current = {a["project_stable_key"]: a for a in new["acceptances"]}
        for acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, acceptance)

    def test_exact_eleven_artifact_rebuild_and_partial_release_gates(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 151, "projects": 154, "evidence": 518,
            "countries": 41, "non_us_sites": 104,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 149,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 51, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 151, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 154, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 154)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-fifty-one-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
