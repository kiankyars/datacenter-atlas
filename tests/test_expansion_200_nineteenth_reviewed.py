"""64-addition checkpoint preserves Procergs construction scope and prior rows."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_eighteenth_reviewed as previous
from datacenter_atlas import expansion_200_nineteenth_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "sources/curated-official-2026-09-09-americas-round21-procergs-july-current-build.json"
GEOMETRY = ROOT / "sources/verified-construction-core-v0.18-americas-round21-procergs-geometry-proposal.json"
RESEARCH = ROOT / "sources/research-expansion-200-americas-round21-2026-09-09.json"
CAMPUS = "curated:procergs-porto-alegre-praca-dos-acorianos-campus"
PROJECT = CAMPUS + ":new-substation-6033"
POINT = [-51.2308141, -30.038629]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class NineteenthReviewedDraftTests(unittest.TestCase):
    def test_explicit_july_new_substation_scope_not_completed_halls(self):
        doc = read(CURATED)
        evidence = doc["evidence"][0]
        meta = evidence["metadata"]
        self.assertEqual(evidence["kind"], "government_record")
        self.assertIsNone(evidence["published_at"])
        self.assertEqual(meta["status_date_precision"], "month")
        self.assertEqual(meta["source_observation_month"], "2026-07")
        self.assertEqual(meta["source_observation_interval"], ["2026-07-01", "2026-07-31"])
        self.assertIn("not an asserted observation day", meta["status_as_of_normalization"])
        self.assertIn("Existing halls may operate concurrently", meta["physical_scope"])
        self.assertIn("financial, not physical completion", meta["source_template_caveats"])
        self.assertEqual(doc["project"]["stable_key"], PROJECT)
        self.assertEqual(doc["campus"]["stable_key"], CAMPUS)
        self.assertEqual(len(doc["lifecycle"]), 1)
        status = doc["lifecycle"][0]
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-07-01")
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertEqual(status["evidence_key"], evidence["key"])
        self.assertEqual(meta["pdf_review"]["full_pages_visually_reviewed"], [1, 2, 3, 4, 5, 6])

    def test_exact_named_community_object_and_independent_dc_address(self):
        doc = read(GEOMETRY)
        by_key = {item["key"]: item for item in doc["evidence"]}
        point = by_key["am21-procergs-nominatim-point"]
        way = by_key["am21-procergs-osm-way-identity"]["metadata"]
        self.assertEqual(point["metadata"]["source_point"], POINT)
        self.assertEqual(point["license"], "ODbL-1.0")
        self.assertEqual(way["osm_way_id"], 112410783)
        self.assertEqual(way["osm_way_version"], 18)
        self.assertEqual(way["selected_tags"]["short_name"], "PROCERGS")
        self.assertEqual(way["selected_tags"]["website"], "https://www.procergs.rs.gov.br/")
        self.assertEqual(way["source_crs"], "EPSG:4326")
        self.assertEqual(len(way["source_ring_coordinates"]), 21)
        self.assertEqual(way["source_ring_coordinates"][0], way["source_ring_coordinates"][-1])
        self.assertTrue(way["selected_point_contained"])
        address = by_key["am21-procergs-official-dc-address"]["metadata"]
        contract = by_key["am21-procergs-contract6033-location"]["metadata"]
        self.assertIn("not merely a corporate-office", address["identity_scope"])
        self.assertIn("not an executed contract", contract["template_caveat"])
        self.assertEqual(address["pdf_review"]["full_pages_visually_reviewed"], [35])
        self.assertEqual(contract["pdf_review"]["full_pages_visually_reviewed"], [1])
        result = doc["results"][0]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertEqual(result["semantics"]["geometry_authority_class"], "community_source")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertIn("address labels differ", result["semantics"]["precision_scope"])
        core._geometry(result)

    def test_no_inferred_roles_metrics_operation_or_extra_projects(self):
        doc = read(CURATED)
        importlib.import_module(f"{baseline.__package__}.curated_v11")._parse_document(CURATED, "2026-09-09T07:00:00Z")
        for name in ("campus", "project"):
            self.assertEqual(doc[name]["roles"], {})
            self.assertIsNone(doc[name]["coordinates"])
            self.assertIsNone(doc[name]["geometry"])
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(doc[field], [])
        rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                if row["physical_site_stable_key"] == CAMPUS]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_stable_key"], PROJECT)
        self.assertEqual(rows[0]["status_as_of"], "2026-07-01")
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(rows[0][field]))
        self.assertEqual(rows[0]["operating_model"], "unknown")
        successor = read(GEOMETRY)["evidence"][-1]
        self.assertEqual(successor["published_at"], "2026-08-17")
        self.assertIn("not proof of commissioning", successor["metadata"]["successor_scope"])

    def test_one_acceptance_and_ten_exact_source_bindings(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 64)
        self.assertEqual(len(validated.sources), 403)
        geometry = read(GEOMETRY)
        evidence = {item["key"]: item for item in read(CURATED)["evidence"] + geometry["evidence"]}
        self.assertEqual(len(evidence), 10)
        bindings = {item["source_id"]: item for item in geometry["source_binding_map"]}
        sources = {item["source_id"]: item for item in new["sources"]}
        self.assertEqual(set(sources) - {item["source_id"] for item in old["sources"]}, set(evidence))
        self.assertEqual(set(bindings), set(evidence))
        for key, item in evidence.items():
            self.assertEqual(item["metadata"]["content_hash_verification"], "fetched_bytes_sha256")
            self.assertGreater(item["metadata"]["raw_capture_bytes"], 0)
            self.assertEqual(item["metadata"]["http_status"], 200)
            self.assertFalse(item["metadata"]["request_credentials_supplied"])
            self.assertTrue(item["metadata"]["rights_scope"])
            self.assertEqual(sources[key]["path"], bindings[key]["path"])
            self.assertEqual(sources[key]["evidence_pointer"], bindings[key]["evidence_pointer"])
            core._source_evidence(item, key)
        addition = new["acceptances"][-1]
        self.assertEqual(addition["project_stable_key"], PROJECT)
        self.assertEqual(addition["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(set(addition["distinctness_review"]["evidence_source_ids"]), set(evidence))

    def test_all_prior_rows_features_and_source_bytes_are_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(after / filename)}
            for row in table(before / filename):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(Counter((before / filename).read_bytes().splitlines(keepends=True)),
                                 Counter((after / filename).read_bytes().splitlines(keepends=True)))
        self.assertEqual(len(read(before / "sites.geojson")["features"]), 163)
        self.assertEqual(len(read(after / "sites.geojson")["features"]), 164)
        for feature in read(before / "sites.geojson")["features"]:
            self.assertIn(feature, read(after / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
            raw = (ROOT / source["path"]).read_bytes()
            self.assertEqual(len(raw), source["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
        current = {item["project_stable_key"]: item for item in new["acceptances"]}
        for acceptance in old["acceptances"]:
            changed = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            changed["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(changed, acceptance)

    def test_exact_artifact_rebuild_and_incomplete_release_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 164, "projects": 167, "evidence": 639, "countries": 42,
            "non_us_sites": 109, "official_boundary_projects": 5, "reviewed_site_locator_projects": 162,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 64, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 164, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 167, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 167)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-four-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
