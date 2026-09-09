"""53-addition checkpoint: named Flexential phases and ODbL locators."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twelfth_reviewed as batch
from datacenter_atlas import expansion_200_eleventh_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = (
    SOURCES / "curated-official-2026-09-08-americas-round11-flexential-hillsboro5-current-build.json",
    SOURCES / "curated-official-2026-09-09-flexential-douglasville2-current-build.json",
)
GEOMETRY = (
    SOURCES / "verified-construction-core-v0.18-americas-round11-flexential-hillsboro5-geometry-proposal.json",
    SOURCES / "verified-construction-core-v0.18-flexential-douglasville2-reviewed-geometry.json",
)
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class TwelfthReviewedDraftTests(unittest.TestCase):
    def test_current_work_is_dated_but_exact_hall_capacity_and_operation_remain_unknown(self) -> None:
        for path in CURATED:
            with self.subTest(path=path):
                doc = read(path)
                curated._parse_document(path, "2026-09-09T03:00:00Z")
                status, evidence = doc["lifecycle"][0], doc["evidence"][0]
                self.assertEqual(len(doc["lifecycle"]), 1)
                self.assertEqual(status["as_of_date"], "2026-08-18")
                self.assertEqual(status["value"], "under_construction")
                self.assertEqual(status["evidence_key"], evidence["key"])
                self.assertEqual(evidence["published_at"], "2026-08-18T13:04:00Z")
                self.assertNotEqual(status["as_of_date"], evidence["retrieved_at"][:10])
                self.assertIn("analyst reconciliation", evidence["metadata"]["identity_inference"])
                self.assertTrue(evidence["metadata"]["contrary_evidence"])
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("workloads", "capacities", "operating_models"):
                    self.assertEqual(doc[field], [])

    def test_hillsboro_phase_and_operational_sounding_sources_are_preserved(self) -> None:
        doc = read(GEOMETRY[0])
        ev = {e["key"]: e for e in doc["evidence"]}
        address = ev["am11-hillsboro5-owner-address"]["metadata"]
        self.assertEqual(address["exact_address"], "4975 NE Starr Boulevard, Hillsboro, Oregon")
        self.assertIn("operational-sounding", address["contrary_language"])
        self.assertIn("one physical site", address["adjacent_campus_scope"])
        self.assertEqual(ev["am11-hillsboro5-2025-identity"]["published_at"][:10], "2025-09-04")
        self.assertIn("not selected as an independent July", ev["am11-hillsboro5-esg-completion-context"]["excerpt"])
        brochure = ev["am11-hillsboro5-owner-brochure-caveat"]
        self.assertIsNone(brochure["published_at"])
        self.assertEqual(brochure["metadata"]["visually_reviewed_pdf_pages"], [1, 2])
        self.assertIn("not asserted as publication", brochure["metadata"]["publication_date_guardrail"])
        way = ev["am11-hillsboro5-osm-exact-way-identity"]["metadata"]
        self.assertEqual(way["osm_id"], 1080170580)
        self.assertEqual(way["selected_tags"]["addr:housenumber"], "4975")
        self.assertIn("not used to locate H5", way["excluded_objects"])

    def test_named_community_points_are_not_boundaries_or_neighbor_substitutions(self) -> None:
        expected = [
            (0, "am11-hillsboro5-osm-named-building-point", [-122.9394058, 45.5564617]),
            (1, "am12-douglasville2-osm-point", [-84.6112399, 33.7307026]),
        ]
        for i, key, point in expected:
            doc = read(GEOMETRY[i])
            evidence = next(e for e in doc["evidence"] if e["key"] == key)
            result = doc["results"][0]
            self.assertEqual(evidence["license"], "ODbL-1.0")
            self.assertIn("OpenStreetMap", evidence["attribution"])
            self.assertEqual(evidence["metadata"]["source_crs"], "EPSG:4326")
            self.assertEqual(result["geometry"], {"type": "Point", "coordinates": point})
            self.assertEqual(result["geometry"], evidence["metadata"]["geometry"])
            self.assertEqual(result["display_anchor"], result["geometry"])
            self.assertEqual(result["location_basis"], "community_named_site_feature")
            self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
            self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
            self.assertIn("boundary", result["semantics"]["precision_scope"])
            self.assertIn("am11-osm-rights-attribution", result["geometry_source_ids"])
            draft._geometry(result)
        d = read(GEOMETRY[1])
        ev = {e["key"]: e for e in d["evidence"]}
        self.assertEqual(ev["am12-douglasville2-osm-way"]["metadata"]["osm_id"], 1258702591)
        self.assertEqual(ev["am12-douglasville2-osm-way"]["metadata"]["selected_tags"]["addr:housenumber"], "1750")
        census = ev["am12-douglasville2-census-unselected"]["metadata"]
        self.assertFalse(census["geometry_selected"])
        self.assertEqual(census["matched_address"], "1750 N RIVER RD, LITHIA SPRINGS, GA, 30122")
        self.assertNotIn("geometry", census)

    def test_two_new_campuses_and_seventeen_new_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 53)
        self.assertEqual(len(validated.sources), 299)
        old_ids = {s["source_id"] for s in old["sources"]}
        ids = {s["source_id"] for s in new["sources"]}
        proposed = {b["source_id"] for p in GEOMETRY for b in read(p)["source_binding_map"]}
        self.assertEqual(ids - old_ids, proposed - old_ids)
        self.assertEqual(len(ids - old_ids), 17)
        new_keys = {a["project_stable_key"] for a in new["acceptances"]}
        old_keys = {a["project_stable_key"] for a in old["acceptances"]}
        self.assertEqual(new_keys - old_keys, {read(p)["project"]["stable_key"] for p in CURATED})
        new_campuses = {a["parent_campus_stable_key"] for a in new["acceptances"]}
        old_campuses = {a["parent_campus_stable_key"] for a in old["acceptances"]}
        self.assertEqual(new_campuses - old_campuses, {read(p)["campus"]["stable_key"] for p in CURATED})
        self.assertEqual(len(new_campuses - old_campuses), 2)

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
            "physical_sites": 153, "projects": 156, "evidence": 535,
            "countries": 41, "non_us_sites": 104,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 151,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 53, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 153, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 156, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 156)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-fifty-three-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
