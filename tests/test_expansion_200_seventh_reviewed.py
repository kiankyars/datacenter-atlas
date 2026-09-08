"""Forty-site checkpoint: date bridges, rehost limits and unchanged prior rows."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_seventh_reviewed as batch
from datacenter_atlas import expansion_200_sixth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
DVZ = SOURCES / "verified-construction-core-v0.18-europe-round5-dvz-proposed-geometry.json"
DF1 = SOURCES / "verified-construction-core-v0.18-americas-round5-df1-geometry-facts.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class SeventhReviewedDraftTests(unittest.TestCase):
    def test_two_packages_preserve_dates_and_unknown_fields(self) -> None:
        expected = {
            "europe-round5-dvz-schwerin-proposed-build": "2026-07-31",
            "americas-round5-df1-current-build": "2026-07-27",
        }
        for name, day in expected.items():
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            doc = read(path)
            parser = curated.legacy if doc["schema_version"] == "1.0" else curated
            parser._parse_document(path, doc["evidence"][0]["retrieved_at"]
                                   if parser is curated.legacy else "2026-09-08T22:30:00Z")
            self.assertEqual(len(doc["lifecycle"]), 1)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], day)
            self.assertEqual(doc["lifecycle"][0]["value"], "under_construction")
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_new_bindings_are_closed_and_locators_are_not_official_boundaries(self) -> None:
        v = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(v.acceptances), 40)
        self.assertEqual(len(v.sources), 201)
        for row in v.acceptances[-2:]:
            a, geom = row["acceptance"], row["geometry"]
            self.assertIn(a["identity"]["source_id"], geom["identity_source_ids"])
            self.assertEqual(v.sources[a["status"]["source_id"]]["document"]["project"]["stable_key"],
                             row["project"]["stable_key"])
            draft._geometry(geom)
            self.assertEqual(geom["location_basis"], "community_named_site_feature")
            self.assertEqual(geom["semantics"]["geometry_authority_class"], "community_source")
            self.assertEqual(geom["semantics"]["geometry_use_scope"], "campus_locator")
            self.assertIsNone(geom["semantics"]["horizontal_uncertainty_metres"])

    def test_dvz_publication_bridge_is_bound_without_resolving_foundation_conflict(self) -> None:
        doc = read(SOURCES / "curated-official-2026-09-08-europe-round5-dvz-schwerin-proposed-build.json")
        self.assertEqual(doc["evidence"][5]["source_url"], "https://www.dvz-mv.de/news")
        self.assertEqual(doc["evidence"][5]["published_at"], "2026-07-31")
        keys = doc["evidence"][0]["metadata"]["publication_bridge_source_keys"]
        self.assertEqual(set(keys), {doc["evidence"][i]["key"] for i in (1, 2, 5)})
        self.assertIn("conflict", doc["evidence"][0]["metadata"]["event_guardrail"])
        geom = read(DVZ)["results"][0]
        self.assertTrue({"dvz-issue-publication", "dvz-issue-pdf-link", "dvz-news-index-date"}
                        <= set(geom["identity_source_ids"]))
        self.assertEqual(geom["geometry"]["coordinates"], [11.3811071, 53.6469747])
        self.assertEqual(read(DVZ)["evidence"][0]["metadata"]["object_id"], 1545965488)

    def test_df1_rehost_and_unknown_datum_are_not_promoted(self) -> None:
        doc = read(DF1)
        for index in (3, 4, 5):
            self.assertIn("not been independently byte-matched", doc["evidence"][index]["metadata"]["rehost_provenance"])
            self.assertIn("not distributed", doc["evidence"][index]["metadata"]["rights_scope"])
        well = doc["evidence"][4]["metadata"]
        self.assertTrue(well["not_selected_as_geometry"])
        self.assertEqual(well["datum"], "not specified in form")
        geom = doc["results"][0]
        self.assertNotEqual(geom["geometry"]["coordinates"], well["decimal_arithmetic_only"])
        self.assertEqual(geom["geometry"]["coordinates"], [-92.68620569018782, 31.38257035])
        self.assertEqual(doc["provider_review"]["provider_object"]["id"], 1545345944)
        self.assertIn("am5df1-current-status", geom["identity_source_ids"])
        self.assertIn("not a project centroid", geom["semantics"]["precision_scope"].lower())

    def test_new_campuses_count_once_with_no_selected_imagery(self) -> None:
        v = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        rows = v.acceptances[-2:]
        self.assertEqual(len({r["campus"]["stable_key"] for r in rows}), 2)
        for row in rows:
            d = row["acceptance"]["distinctness_review"]
            self.assertEqual(d["scope"], "single_physical_site")
            self.assertEqual(d["equivalent_campus_keys"], [row["campus"]["stable_key"]])

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
            "physical_sites": 140, "projects": 143, "evidence": 437,
            "countries": 40, "non_us_sites": 98,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 138,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 40, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 143, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 143)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-forty-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
