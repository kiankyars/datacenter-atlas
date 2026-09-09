"""Red Oak adds one first-phase project, located by a constituent address point."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_fifth_reviewed as previous
from datacenter_atlas import expansion_200_twenty_sixth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
CAMPUS = "curated:databank-red-oak-campus"
PROJECT = f"{CAMPUS}:first-phase-current-build"
POINT = [-96.73491416900481, 32.53823002269006]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def added_acceptances():
    return read(batch.contract_path(ROOT))["acceptances"][75:]


def selected_documents():
    contract = read(batch.contract_path(ROOT))
    acceptance, = added_acceptances()
    sources = {item["source_id"]: item for item in contract["sources"]}
    return tuple(read(ROOT / sources[acceptance[key]["source_id"]]["path"])
                 for key in ("status", "geometry"))


class TwentySixthReviewedDraftTests(unittest.TestCase):
    def test_first_phase_status_not_a_dfw10_specific_work_observation(self):
        acceptance, = added_acceptances()
        self.assertEqual(acceptance["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(acceptance["project_stable_key"], PROJECT)
        self.assertEqual(acceptance["country_iso_a2"], "US")
        doc, proposal = selected_documents()
        self.assertEqual(doc["campus"]["stable_key"], CAMPUS)
        self.assertEqual(doc["project"]["stable_key"], PROJECT)
        self.assertEqual(proposal["results"][0]["project_stable_key"], PROJECT)
        status, = doc["evidence"]
        self.assertEqual(status["key"], "am29-redoak-july26-current-build")
        self.assertEqual(status["kind"], "company_disclosure")
        self.assertEqual(status["published_at"], "2026-07-26")
        metadata = status["metadata"]
        self.assertEqual(metadata["status_date_precision"], "day")
        self.assertEqual(metadata["source_observation_date"], "2026-07-26")
        self.assertEqual(metadata["source_publication_timestamp"], "2026-07-26T18:47:32+00:00")
        self.assertEqual(metadata["source_modified_timestamp"], "2026-07-29T18:47:55+00:00")
        self.assertIn("do not refresh", metadata["date_semantics"])
        self.assertIn("DFW9–DFW12", metadata["project_scope"])
        self.assertIn("DFW10 is an exact-address locator constituent only", metadata["project_scope"])
        self.assertIn("unchanged and unselected", metadata["project_scope"])
        self.assertIn("currently underway", {
            item["literal"] for item in metadata["literal_byte_anchors"]
        })
        observation, = doc["lifecycle"]
        self.assertEqual(observation["entity"], "project")
        self.assertEqual(observation["value"], "under_construction")
        self.assertEqual(observation["as_of_date"], "2026-07-26")
        self.assertEqual(observation["evidence_key"], status["key"])

    def test_dfw10_address_is_a_constituent_campus_locator_only(self):
        _, proposal = selected_documents()
        sources = {item["key"]: item for item in proposal["evidence"]}
        address = sources["am29-redoak-operator-dfw10-address"]
        campus = sources["am29-redoak-operator-campus-identity"]
        for source in (address, campus):
            self.assertIsNone(source["published_at"])
            self.assertTrue(source["metadata"]["identity_only"])
            self.assertFalse(source["metadata"]["lifecycle_selected"])
            self.assertTrue(source["metadata"]["source_date_unknown"])
            self.assertIn("3330 Batchler Rd.", {
                item["literal"] for item in source["metadata"]["literal_byte_anchors"]
            })
        point = sources["am29-redoak-ellis-address-point"]["metadata"]
        self.assertEqual(point["source_object_id"], 70622)
        self.assertEqual(point["match_count"], 1)
        self.assertEqual(point["matched_address"], "3330 Batchler Rd, Red Oak")
        self.assertEqual(point["placement"], "Site")
        self.assertIsNone(point["landmark_name"])
        self.assertIsNone(point["parcel_id"])
        self.assertFalse(point["lifecycle_selected"])
        self.assertEqual(point["date_updated_not_construction_date"], 1750271405000)
        result, = proposal["results"]
        self.assertLessEqual({address["key"], campus["key"]}, set(result["identity_source_ids"]))
        self.assertIn("DFW10 address", result["semantics"]["precision_scope"])
        self.assertIn("not an observed active-work footprint", point["identity_caveat"])
        self.assertTrue(proposal["campus_association"]["no_new_site_for_phases"])
        contractor = sources["am29-redoak-yates-dfw10-identity"]
        self.assertIsNone(contractor["published_at"])
        self.assertTrue(contractor["metadata"]["publication_date_unknown"])
        self.assertTrue(contractor["metadata"]["identity_only"])
        self.assertFalse(contractor["metadata"]["lifecycle_selected"])
        self.assertIn("not assigned to July 26", contractor["metadata"]["scope_caveat"])
        self.assertIn(contractor["key"], result["identity_source_ids"])
        self.assertNotIn(contractor["key"], result["geometry_source_ids"])

    def test_native_2276_transform_accuracy_is_not_feature_accuracy(self):
        _, proposal = selected_documents()
        sources = {item["key"]: item for item in proposal["evidence"]}
        point = sources["am29-redoak-ellis-address-point"]["metadata"]
        self.assertEqual(point["source_point_xy"], [2512411.4033679664, 6883322.76911889])
        for field in ("source_crs", "source_stored_crs", "response_crs"):
            self.assertEqual(point[field], "EPSG:2276")
        self.assertEqual(point["output_crs"], "EPSG:4326")
        layer = sources["am29-redoak-ellis-address-layer"]["metadata"]
        self.assertEqual(layer["source_stored_crs"], "EPSG:2276")
        self.assertEqual(layer["service_extent_crs"], "EPSG:3857")
        transform = point["transformation"]
        self.assertEqual(transform["result"], POINT)
        self.assertIn("always_xy=True", transform["method"])
        self.assertIn("NAD83 to WGS 84 (1)", transform["operation_description"])
        self.assertIn("xy_in=us-ft", transform["operation_pipeline"])
        self.assertEqual(transform["operation_accuracy_metres_not_source_position_accuracy"], 4)
        self.assertTrue(transform["transformer_group_default_best_available"])
        self.assertTrue(transform["unavailable_grid_operations"])
        self.assertFalse(transform["network_grid_download_performed"])
        self.assertTrue(transform["executed"])
        self.assertIsNone(transform["feature_horizontal_uncertainty_metres"])
        semantics = proposal["results"][0]["semantics"]
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("not feature accuracy", semantics["horizontal_uncertainty_unknown_reason"])

    def test_county_copyright_and_blank_licence_are_not_open_permission(self):
        doc, proposal = selected_documents()
        sources = {item["key"]: item for item in proposal["evidence"]}
        rights = sources["am29-redoak-ellis-webmap-rights"]["metadata"]
        self.assertEqual(rights["access"], "public")
        self.assertEqual(rights["license_info"], "")
        self.assertEqual(sources["am29-redoak-ellis-copyright"]["metadata"]["license_info"],
                         "All rights reserved")
        terms = sources["am29-redoak-databank-terms"]["metadata"]
        self.assertTrue(terms["terms_do_not_grant_redistribution"])
        self.assertTrue(terms["protected_content_not_redistributed"])
        for source in doc["evidence"] + proposal["evidence"]:
            self.assertEqual(source["license"], "no-open-license-asserted")
            self.assertFalse(source["metadata"]["raw_capture_redistributed"])
            self.assertTrue(source["metadata"]["rights_scope"])
        self.assertIn("isolated official address-point coordinate", proposal["rights_scope"])
        self.assertIn("not treated as an affirmative redistribution grant", proposal["rights_scope"])

    def test_dfw9_expected_opening_does_not_complete_first_phase_or_campus(self):
        doc, proposal = selected_documents()
        caveat = doc["evidence"][0]["metadata"]["successor_caveat"]
        self.assertIn("Expected August DFW9 opening", caveat)
        self.assertIn("not proven campus completion", caveat)
        successor = proposal["successor_review"]
        self.assertEqual(successor["reference_cutoff"], "2026-08-20")
        self.assertIn("forecast is not an actual completion event", successor["finding"])
        source = next(item for item in proposal["evidence"]
                      if item["key"] == "am29-redoak-official-successor-index")
        self.assertTrue(source["metadata"]["successor_only"])
        self.assertFalse(source["metadata"]["lifecycle_selected"])
        self.assertEqual(source["metadata"]["cutoff"], "2026-08-20")
        self.assertIn("does not refresh July construction", source["metadata"]["finding_scope"])
        self.assertEqual(proposal["distinctness_review"]["sites_compared"], 175)
        self.assertEqual(proposal["distinctness_review"]["full_geometry_collisions"], [])
        self.assertEqual(proposal["distinctness_review"]["matched_selected_campuses"], [])

    def test_one_new_project_uses_the_campus_only_point_without_imagery(self):
        self.assertEqual(len(added_acceptances()), 1)
        doc, proposal = selected_documents()
        result, = proposal["results"]
        core._geometry(result)
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["semantics"]["geometry_authority_class"], "official_source")
        self.assertEqual(result["semantics"]["geometry_source_entity_kind"], "campus")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertEqual(result["semantics"]["geometry_scope_class"], "official_address_reference_point")
        self.assertEqual(result["parent_campus_stable_key"], doc["campus"]["stable_key"])
        rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                if row["physical_site_stable_key"] == CAMPUS]
        self.assertEqual(len(rows), 1)
        row, = rows
        self.assertEqual(row["project_stable_key"], PROJECT)
        self.assertEqual(row["last_observed_physical_status"], "under_construction")
        self.assertEqual(row["status_as_of"], "2026-07-26")
        self.assertEqual(json.loads(row["geometry_json"]), result["geometry"])
        self.assertEqual(row["horizontal_uncertainty_metres"], "")
        self.assertEqual(row["independent_imagery_verification"], "false")

    def test_no_new_metrics_roles_workloads_or_other_buildings_selected(self):
        doc, _ = selected_documents()
        for field in ("operating_models", "workloads", "capacities"):
            self.assertEqual(doc[field], [])
        for field in ("campus", "project"):
            self.assertEqual(doc[field]["roles"], {})
            self.assertIsNone(doc[field]["coordinates"])
            self.assertIsNone(doc[field]["geometry"])
        rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                if row["physical_site_stable_key"] == CAMPUS]
        row, = rows
        self.assertNotIn(row["project_stable_key"], {f"{CAMPUS}:dfw{number}" for number in range(9, 17)})
        self.assertEqual(row["operating_model"], "unknown")
        for field in ("owner", "operator", "users", "tenants", "customers"):
            self.assertEqual(row[field], "")
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(row[field]))

    def test_all_thirteen_new_bindings_are_portable_hashed_and_used_by_review(self):
        before = read(previous.contract_path(ROOT))
        after = read(batch.contract_path(ROOT))
        doc, proposal = selected_documents()
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        old_ids = {row["source_id"] for row in before["sources"]}
        specs = [row for row in after["sources"] if row["source_id"] not in old_ids]
        ids = {row["source_id"] for row in specs}
        self.assertEqual(len(validated.acceptances), 76)
        self.assertEqual(len(specs), 13)
        self.assertEqual(len(validated.sources), len(before["sources"]) + 13)
        self.assertEqual(ids, {item["key"] for item in doc["evidence"] + proposal["evidence"]})
        self.assertEqual(ids, {item["source_id"] for item in proposal["source_binding_map"]})
        self.assertEqual(ids, {source_id for acceptance in added_acceptances()
                               for source_id in acceptance["distinctness_review"]["evidence_source_ids"]})
        bindings = {item["source_id"]: item for item in proposal["source_binding_map"]}
        for spec in specs:
            with self.subTest(source=spec["source_id"]):
                self.assertEqual(spec["path"], bindings[spec["source_id"]]["path"])
                self.assertEqual(spec["evidence_pointer"], bindings[spec["source_id"]]["evidence_pointer"])
                raw = (ROOT / spec["path"]).read_bytes()
                self.assertEqual(len(raw), spec["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
                value = json.loads(raw)
                for token in spec["evidence_pointer"].strip("/").split("/"):
                    value = value[int(token)] if isinstance(value, list) else value[token]
                self.assertEqual(value["key"], spec["source_id"])
                self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
                core._source_evidence(value, spec["source_id"])
                metadata = value["metadata"]
                self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
                self.assertEqual(metadata["http_status"], 200)
                self.assertFalse(metadata["request_credentials_supplied"])
                self.assertGreater(metadata["raw_capture_bytes"], 0)
                self.assertTrue(metadata["literal_pointer"])
                self.assertTrue(metadata["rights_scope"])

    def test_every_previous_csv_row_full_feature_and_source_pin_is_preserved(self):
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
        self.assertEqual(len(old_features), 175)
        self.assertEqual(len(new_features), 176)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        core.validate_batch(previous.contract_path(ROOT), previous.REVIEW_PINS, root=ROOT)
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
            self.assertEqual(previous.REVIEW_PINS.source_sha256[source["source_id"]],
                             batch.REVIEW_PINS.source_sha256[source["source_id"]])
        current = {item["project_stable_key"]: item for item in new["acceptances"]}
        for acceptance in old["acceptances"]:
            changed = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            changed["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(changed, acceptance)

    def test_eleven_artifacts_rebuild_byte_exactly_with_incomplete_final_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 176, "projects": 179, "evidence": 757,
            "countries": 43, "non_us_sites": 117, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 174,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 76, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 176, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 179, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 179)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-seventy-six-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
