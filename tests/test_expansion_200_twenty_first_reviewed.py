"""Vineland adds one site while preserving equipment stops and prior records."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twentieth_reviewed as previous
from datacenter_atlas import expansion_200_twenty_first_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "sources/curated-official-2026-09-09-us-round23-dataone-vineland-phase2-current-build.json"
GEOMETRY = ROOT / "sources/verified-construction-core-v0.18-us-round23-dataone-vineland-geometry-proposal.json"
RESEARCH = ROOT / "sources/research-expansion-200-us-round23-dataone-vineland-2026-09-09.json"
GEO_RESEARCH = ROOT / "sources/research-expansion-200-us-round23-dataone-vineland-geometry-2026-09-09.json"
CAMPUS = "curated:dataone-vineland-ai-data-center-campus"
PROJECT = CAMPUS + ":phase-2-expansion-current-build"
STATUS = "us23-vineland-phase2-aug7-construction"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def evidence():
    return {row["key"]: row for path in (CURATED, GEOMETRY, RESEARCH)
            for row in read(path)["evidence"]}


class TwentyFirstReviewedDraftTests(unittest.TestCase):
    def test_current_government_notice_is_not_the_future_hearing_or_retrieval_date(self):
        doc = read(CURATED)
        parser = importlib.import_module(f"{baseline.__package__}.curated_v11")
        parser._parse_document(CURATED, "2026-09-09T08:00:00Z")
        self.assertEqual(len(doc["evidence"]), 1)
        source = doc["evidence"][0]
        self.assertEqual(source["key"], STATUS)
        self.assertEqual(source["kind"], "government_record")
        self.assertEqual(source["publisher"], "City of Vineland Planning Board")
        self.assertEqual(source["published_at"], "2026-08-07")
        meta = source["metadata"]
        self.assertEqual(meta["selected_status_date"], "2026-08-07")
        self.assertEqual(meta["source_parcel"], "Vineland Block 7503 Lot 35.01")
        self.assertEqual(meta["pdf_review"]["full_pages_visually_reviewed"], [1])
        self.assertIn("August 17 hearing is future procedure", meta["status_as_of_normalization"])
        self.assertIn("September retrieval does not refresh", meta["status_as_of_normalization"])
        self.assertEqual(doc["lifecycle"], [{
            "entity": "project", "value": "under_construction", "evidence_key": STATUS,
            "as_of_date": "2026-08-07", "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }])
        pub = evidence()["us23-vineland-aug7-publication"]
        self.assertEqual(pub["metadata"]["linked_pdf_url"], source["source_url"])
        self.assertEqual(pub["metadata"]["source_publication_date"], "2026-08-07")

    def test_orders_retain_checked_box_and_specific_equipment_qualifications(self):
        by_key = evidence()
        for code, day, violation, scope in (
            ("lng", "2026-08-06", "V-26-00008", "LNG tank installation only"),
            ("bloom", "2026-08-10", "V-26-00009", "work in reference to Bloom Energy units"),
        ):
            with self.subTest(equipment=code):
                source = by_key[f"us23-vineland-{code}-stop-order"]
                meta = source["metadata"]
                self.assertEqual(source["kind"], "government_record")
                self.assertEqual(meta["document_date"], day)
                self.assertEqual(meta["violation_id"], violation)
                self.assertTrue(meta["all_construction_checkbox_checked"])
                self.assertEqual(meta["explicit_scope_qualification"], scope)
                self.assertEqual(meta["source_street_address"], "3963 S LINCOLN AVE, Vineland City, NJ")
                self.assertTrue(meta["visual_review"]["complete_page_scan_reviewed"])
                self.assertIn("No equipment work, permit compliance or rescission", meta["reviewed_scope"])
        self.assertEqual(by_key["us23-vineland-order-host-chain"]["kind"], "news")
        self.assertIn("reverses the equipment dates", by_key["us23-vineland-order-host-chain"]["metadata"]["source_discrepancy"])
        for key in ("us23-vineland-aug18-successor", "us23-vineland-aug28-scope-context",
                    "us23-vineland-operator-successor-context", "us23-vineland-nebius-successor-context"):
            self.assertFalse(by_key[key]["metadata"]["selected_lifecycle"])
        self.assertEqual(by_key["us23-vineland-aug18-successor"]["kind"], "news")
        self.assertIn("not a construction permit", by_key["us23-vineland-aug18-successor"]["metadata"]["temporal_guardrail"])

    def test_exact_single_parcel_has_explicit_datum_and_unknown_accuracy(self):
        doc = read(GEOMETRY)
        self.assertEqual(len(doc["results"]), 1)
        result = doc["results"][0]
        core._geometry(result)
        self.assertEqual(result["project_stable_key"], PROJECT)
        self.assertEqual(result["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(result["location_basis"], "official_parcel")
        self.assertEqual(result["geometry"]["type"], "Polygon")
        self.assertEqual(len(result["geometry"]["coordinates"]), 1)
        self.assertEqual(len(result["geometry"]["coordinates"][0]), 24)
        self.assertEqual(result["display_anchor"], {"type": "Point", "coordinates": [-75.01347153097437, 39.42519221884926]})
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertEqual(semantics["geometry_authority_class"], "official_source")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("Not a surveyed cadastral boundary", semantics["precision_scope"])
        self.assertIn("Old Lot 33.01 is not added", semantics["precision_scope"])
        native = evidence()["us23-dataone-vineland-parcel-native"]["metadata"]
        self.assertEqual(native["selected_attributes"], {
            "OBJECTID_1": 131906, "MUN": "VINELAND CITY", "BLOCK": "7503", "LOT": "35.01",
            "UNIQUEID": "0614-7503-35.01-00000", "ParcelAddr": "3963 S LINCOLN AVE",
            "Owner": "DATAONE VINELAND, LLC",
        })
        self.assertIn("not selected", native["excluded_coordinate_attributes"])
        conversion = evidence()["us23-dataone-vineland-parcel-wgs84"]["metadata"]["coordinate_derivation"]
        self.assertEqual(conversion["native_crs"], "EPSG:3424")
        self.assertEqual(conversion["target_crs"], "EPSG:4326")
        self.assertEqual(conversion["requested_datumTransformation"], 1188)
        self.assertIn("not source-parcel positional accuracy", conversion["operation_accuracy_not_locator_accuracy"])
        self.assertIn("unavailable locally", conversion["unselected_grid_warning"])

    def test_isolated_fact_reuse_is_not_an_open_licence_or_export_permission(self):
        by_key = evidence()
        self.assertTrue(all(row["license"] == "no-open-license-asserted" for row in by_key.values()))
        config = by_key["us23-dataone-vineland-viewer-config"]["metadata"]
        self.assertFalse(config["public_route"]["enableExport"])
        self.assertEqual(config["public_route"]["fields"], ["BLOCK", "LOT"])
        item = by_key["us23-dataone-vineland-parcel-item"]["metadata"]
        self.assertIsNone(item["licenseInfo"])
        self.assertEqual(item["access"], "public")
        self.assertIn("not an open-data grant", item["rights_scope"])
        review = read(RESEARCH)["root_admission_review"]
        self.assertIn("one isolated factual parcel locator", review["rights_review"])
        self.assertIn("neither enabled nor bypassed", review["rights_review"])

    def test_one_existing_campus_identity_and_no_new_roles_or_metrics(self):
        old = read(ROOT / "sources/curated-official-2026-07-21-dataone-vineland-phase-2-current-build.json")
        doc = read(CURATED)
        for key in ("campus", "project"):
            self.assertEqual(doc[key]["stable_key"], old[key]["stable_key"])
            self.assertEqual(doc[key]["name"], old[key]["name"])
            self.assertEqual(doc[key]["roles"], {})
            self.assertIsNone(doc[key]["coordinates"])
            self.assertIsNone(doc[key]["geometry"])
        for key in ("operating_models", "workloads", "capacities"):
            self.assertEqual(doc[key], [])
        rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                if row["physical_site_stable_key"] == CAMPUS]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_stable_key"], PROJECT)
        self.assertEqual(rows[0]["status_as_of"], "2026-08-07")
        self.assertEqual(rows[0]["operating_model"], "unknown")
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(rows[0][field]))

    def test_exact_sixteen_new_bindings_and_capture_metadata_close(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 67)
        self.assertEqual(len(validated.sources), 430)
        by_key = evidence()
        self.assertEqual(len(by_key), 16)
        sources = {row["source_id"]: row for row in new["sources"]}
        self.assertEqual(set(sources) - {row["source_id"] for row in old["sources"]}, set(by_key))
        bindings = {row["source_id"]: row for path in (GEOMETRY, RESEARCH)
                    for row in read(path)["source_binding_map"]}
        self.assertEqual(set(bindings), set(by_key))
        captures = {row["raw_local_path"]: row for row in
                    read(RESEARCH)["captures"] + read(GEO_RESEARCH)["raw_captures"]}
        for key, source in by_key.items():
            with self.subTest(source=key):
                core._source_evidence(source, key)
                meta = source["metadata"]
                capture = captures[meta["raw_capture_temp_path"]]
                self.assertEqual(capture["sha256"], source["content_hash"])
                self.assertEqual(capture["bytes"], meta["raw_capture_bytes"])
                self.assertEqual(capture["source_url"], source["source_url"])
                self.assertEqual(capture["http_status"], 200)
                self.assertFalse(capture["request_credentials_supplied"])
                self.assertEqual(sources[key]["path"], bindings[key]["path"])
                self.assertEqual(sources[key]["evidence_pointer"], bindings[key]["evidence_pointer"])
                value = read(ROOT / bindings[key]["path"])
                for token in bindings[key]["evidence_pointer"].strip("/").split("/"):
                    value = value[int(token)] if isinstance(value, list) else value[token]
                self.assertEqual(value, source)
        added = new["acceptances"][-1]
        self.assertEqual(added["project_stable_key"], PROJECT)
        self.assertEqual(set(added["distinctness_review"]["evidence_source_ids"]), set(by_key))
        spatial = read(GEO_RESEARCH)["spatial_review"]
        self.assertEqual(spatial["baseline_feature_count"], 166)
        self.assertEqual(spatial["intersections"], [])
        self.assertAlmostEqual(spatial["nearest_full_geometry_metres"], 83391.13252896965, places=3)

    def test_all_prior_rows_full_features_sources_and_acceptances_are_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(after / filename)}
            for row in table(before / filename):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(Counter((before / filename).read_bytes().splitlines(keepends=True)),
                                 Counter((after / filename).read_bytes().splitlines(keepends=True)))
        old_features = read(before / "sites.geojson")["features"]
        new_features = read(after / "sites.geojson")["features"]
        self.assertEqual(len(old_features), 166)
        self.assertEqual(len(new_features), 167)
        for feature in old_features:
            self.assertIn(feature, new_features)
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

    def test_eleven_artifact_rebuild_and_incomplete_release_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 167, "projects": 170, "evidence": 666, "countries": 42,
            "non_us_sites": 111, "official_boundary_projects": 5, "reviewed_site_locator_projects": 165,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 67, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 167, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 170, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 170)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-seven-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
