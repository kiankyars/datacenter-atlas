"""Thirty-eight-site checkpoint: physical status, exact locators and frozen rows."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_sixth_reviewed as batch
from datacenter_atlas import expansion_200_fifth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
ASIA = SOURCES / "verified-construction-core-v0.18-asia-round6-ai-tech-tomakomai-geometry-proposal.json"
EUROPE = SOURCES / "verified-construction-core-v0.18-europe-round5-two-proposed-geometry.json"
SWISS = SOURCES / "verified-construction-core-v0.18-europe-round5-flexbase-proposed-geometry.json"
AMERICA = SOURCES / "verified-construction-core-v0.18-americas-round5-geometry-facts.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class SixthReviewedDraftTests(unittest.TestCase):
    def test_six_packages_preserve_exact_dates_and_unknown_fields(self) -> None:
        expected = {
            "asia-round6-ai-tech-tomakomai-phase1-current-build": "2026-06-19",
            "europe-round5-noris-fra1-proposed-build": "2026-06-10",
            "europe-round5-nebius-pajarila-proposed-build": "2026-08-11",
            "europe-round5-flexbase-laufenburg-proposed-build": "2026-06-18",
            "americas-round5-pf1-current-build": "2026-07-27",
            "americas-round5-pf2-current-build": "2026-07-27",
        }
        for name, day in expected.items():
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            doc = read(path)
            parser = curated.legacy if doc["schema_version"] == "1.0" else curated
            parser._parse_document(path, doc["evidence"][0]["retrieved_at"]
                                   if parser is curated.legacy else "2026-09-08T22:10:00Z")
            self.assertEqual(len(doc["lifecycle"]), 1)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], day)
            self.assertEqual(doc["lifecycle"][0]["value"], "under_construction")
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_new_bindings_and_geometry_authority_are_explicit(self) -> None:
        v = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        rows = v.acceptances[-6:]
        self.assertEqual(len(rows), 6)
        self.assertEqual(len(v.sources), 183)
        for row in rows:
            a = row["acceptance"]
            self.assertIn(a["identity"]["source_id"], row["geometry"]["identity_source_ids"])
            self.assertEqual(v.sources[a["status"]["source_id"]]["document"]["project"]["stable_key"],
                             row["project"]["stable_key"])
            draft._geometry(row["geometry"])
            self.assertEqual(row["geometry"]["semantics"]["geometry_use_scope"], "campus_locator")
            self.assertIsNone(row["geometry"]["semantics"]["horizontal_uncertainty_metres"])
            self.assertTrue(row["geometry"]["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_tomakomai_is_one_attributed_reference_parcel_not_official_boundary(self) -> None:
        doc = read(ASIA)
        row = doc["geometry_records"][0]
        self.assertEqual(row["location_basis"], "community_named_site_feature")
        self.assertEqual(row["semantics"]["geometry_authority_class"], "community_source")
        self.assertEqual(row["geometry"]["type"], "Polygon")
        self.assertEqual(len(row["geometry"]["coordinates"][0]), 10)
        e = doc["evidence"][0]
        self.assertEqual(row["geometry"], e["metadata"]["source_geometry"])
        self.assertEqual(e["metadata"]["source_feature_id"], "H000000728")
        self.assertEqual(e["metadata"]["selected_attributes"]["地番"], "32-17")
        self.assertEqual(e["metadata"]["source_crs"], "OGC:CRS84")
        self.assertIn("version-unspecified", e["license"])
        self.assertIn("custom-terms", e["license"])
        self.assertTrue(doc["evidence"][3]["metadata"]["modification_disclosure_required"])

    def test_german_and_finnish_locators_preserve_source_caveats(self) -> None:
        doc = read(EUROPE)
        noris, nebius = doc["results"]
        self.assertEqual(noris["location_basis"], "community_named_site_feature")
        self.assertEqual(noris["geometry"]["coordinates"], [8.5325882, 50.1629204])
        self.assertIn("Kronbacher", doc["evidence"][0]["metadata"]["address_spelling_caveat"])
        self.assertEqual(nebius["location_basis"], "official_address_geocode")
        self.assertEqual(nebius["geometry"]["coordinates"], [28.285490465043303, 61.055863394051165])
        self.assertIn("unverified", doc["evidence"][1]["metadata"]["native_crs"])
        self.assertEqual(doc["evidence"][2]["metadata"]["target_crs"], "EPSG:4326")
        self.assertFalse(doc["evidence"][2]["metadata"]["outofbounds"])

    def test_swiss_mixed_use_scope_does_not_infer_data_center_capacity(self) -> None:
        doc = read(SWISS)
        self.assertEqual(doc["results"][0]["geometry"]["coordinates"], [8.0511054, 47.5536415])
        self.assertEqual(doc["results"][0]["location_basis"], "community_named_site_feature")
        self.assertIn("12538696123", doc["evidence"][0]["metadata"]["excluded_feature"])
        self.assertIn("mixed-use", doc["results"][0]["semantics"]["precision_scope"])
        source = read(SOURCES / "curated-official-2026-09-08-europe-round5-flexbase-laufenburg-proposed-build.json")
        self.assertEqual(source["capacities"], [])
        self.assertIn("battery", source["evidence"][0]["metadata"]["scope_guardrail"])

    def test_north_dakota_constituent_locators_and_completion_scope(self) -> None:
        doc = read(AMERICA)
        pf1, pf2 = doc["results"][1:]
        self.assertEqual(pf1["geometry"]["coordinates"], [-98.574269, 46.014383])
        self.assertIn("NAD83", pf1["semantics"]["geometry_method"])
        self.assertIn("not the still-building project", pf1["semantics"]["precision_scope"])
        self.assertEqual(doc["evidence"][6]["metadata"]["coordinate_crs"], "EPSG:4269")
        self.assertEqual(pf2["geometry"]["type"], "Polygon")
        self.assertEqual(doc["evidence"][12]["metadata"]["selected_fields"]["GISPIN"], "75000000120020")
        self.assertIn("public-domain", doc["evidence"][10]["license"])
        for code in ("pf1", "pf2"):
            source = read(SOURCES / f"curated-official-2026-09-08-americas-round5-{code}-current-build.json")
            self.assertIn("Completed first PF1 building", source["evidence"][0]["metadata"]["status_scope"])

    def test_held_vaughan_and_research_proposals_do_not_inflate_admissions(self) -> None:
        contract = read(batch.contract_path(ROOT))
        keys = {a["parent_campus_stable_key"] for a in contract["acceptances"]}
        self.assertNotIn("curated:microsoft-vaughan-ontario-campus", keys)
        self.assertEqual(len(keys), 38)
        self.assertIn("Vaughan remains held", read(AMERICA)["root_review"]["review_result"])

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
            "physical_sites": 138, "projects": 141, "evidence": 419,
            "countries": 40, "non_us_sites": 97,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 136,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 38, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 141, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 141)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-eight-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
