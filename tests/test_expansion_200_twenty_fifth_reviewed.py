"""Palm Coast and Leipzig add two precisely scoped construction projects."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_fourth_reviewed as previous
from datacenter_atlas import expansion_200_twenty_fifth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def added_acceptances():
    return read(batch.contract_path(ROOT))["acceptances"][73:]


def selected_documents(acceptance):
    contract = read(batch.contract_path(ROOT))
    sources = {item["source_id"]: item for item in contract["sources"]}
    return tuple(read(ROOT / sources[acceptance[key]["source_id"]]["path"])
                 for key in ("status", "geometry"))


class TwentyFifthReviewedDraftTests(unittest.TestCase):
    def test_leipzig_fourth_section_not_operating_halls_or_financial_period(self):
        acceptance = next(item for item in added_acceptances() if item["country_iso_a2"] == "DE")
        self.assertEqual(acceptance["parent_campus_stable_key"], "curated:envia-tel-datacenter-leipzig-campus")
        self.assertEqual(acceptance["project_stable_key"],
                         "curated:envia-tel-datacenter-leipzig-campus:leipzig-2-fourth-section-current-build")
        doc, _ = selected_documents(acceptance)
        status = doc["evidence"][0]
        self.assertEqual(status["key"], "eu28-envia-leipzig-may27-current-build")
        self.assertEqual(status["published_at"], "2026-05-27")
        self.assertEqual(status["metadata"]["status_date_precision"], "day")
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-05-27")
        self.assertIn("Fourth construction section", status["metadata"]["physical_scope"])
        self.assertIn("sections1–3 are excluded", status["metadata"]["physical_scope"])
        self.assertIn("2025 financial period", status["metadata"]["status_date_semantics"])
        self.assertEqual(status["license"], "no-open-license-asserted")

    def test_leipzig_literal_constituent_centroid_and_separate_source_rights(self):
        acceptance = next(item for item in added_acceptances() if item["country_iso_a2"] == "DE")
        _, proposal = selected_documents(acceptance)
        result = proposal["results"][0]
        self.assertEqual(result["geometry"]["coordinates"], [12.4728004, 51.3726832])
        self.assertEqual(result["location_basis"], "community_named_site_feature")
        self.assertEqual(result["semantics"]["geometry_authority_class"], "community_source")
        self.assertEqual(result["semantics"]["geometry_scope_class"], "constituent_building_point_for_shared_campus")
        self.assertLessEqual({"eu28-envia-leipzig2-exact-address", "eu28-envia-campus-directions"},
                             set(result["identity_source_ids"]))
        sources = {item["key"]: item for item in proposal["evidence"]}
        point = sources["eu28-envia-osm-address-building-centroid"]
        self.assertEqual(point["metadata"]["source_crs"], "EPSG:4326")
        self.assertEqual(point["metadata"]["source_object_id"], "way/394151488")
        self.assertEqual(point["license"], "ODbL-1.0")
        self.assertEqual(sources["eu28-envia-leipzig2-exact-address"]["license"], "no-open-license-asserted")
        self.assertIn("not fourth", result["semantics"]["precision_scope"].lower().replace("a fourth", "fourth"))

    def test_palm_coast_stored_harn_crs_not_intermediate_response_crs(self):
        acceptance = next(item for item in added_acceptances() if item["country_iso_a2"] == "US")
        self.assertEqual(acceptance["parent_campus_stable_key"], "curated:dc-blox-palm-coast-cls-campus")
        self.assertEqual(acceptance["project_stable_key"],
                         "curated:dc-blox-palm-coast-cls-campus:approved-first-building-current-build")
        _, proposal = selected_documents(acceptance)
        sources = {item["key"]: item for item in proposal["evidence"]}
        point = sources["am28-palmcoast-city-address-point"]["metadata"]
        self.assertEqual(point["native_point"], [593395.180339247, 1876493.363847576])
        self.assertIn("EPSG:2881", point["source_crs"])
        conversion = point["selected_conversion"]
        expected = [-81.1973193341733, 29.495434584291427]
        self.assertEqual(conversion["result"], expected)
        self.assertEqual(proposal["results"][0]["geometry"]["coordinates"], expected)
        self.assertIn("NAD83(HARN) to WGS 84 (3)", conversion["operation_description"])
        self.assertEqual(conversion["operation_accuracy_metres_not_source_position_accuracy"], 1)
        self.assertTrue(conversion["transformer_group_best_available"])
        self.assertEqual(conversion["unavailable_operations"], [])
        self.assertFalse(conversion["network_grid_download_performed"])
        self.assertEqual(point["source_feature"]["object_id"], 93663)
        self.assertEqual(point["source_feature"]["parcel_id"], "05-12-31-5855-00000-0071")
        self.assertEqual(point["source_feature"]["confidential_field"], "No")
        self.assertTrue(point["containment_audit"]["point_within_exact_lot7b"])
        self.assertEqual(len(point["excluded_earlier_coordinate_routes"]), 2)
        for excluded in point["excluded_earlier_coordinate_routes"]:
            self.assertNotEqual(excluded["coordinates"], expected)
            self.assertGreater(excluded["difference_from_selected_point_metres"], 0)
        self.assertIn("EPSG:2881", sources["am28-palmcoast-city-address-layer"]["metadata"]["stored_source_crs"])

    def test_palm_coast_plan_approval_and_area_conflict_are_not_status_or_metrics(self):
        acceptance = next(item for item in added_acceptances() if item["country_iso_a2"] == "US")
        doc, proposal = selected_documents(acceptance)
        status = doc["evidence"][0]
        self.assertEqual(status["key"], "am28-palmcoast-city-june19-build")
        self.assertEqual(status["metadata"]["source_observation_date"], "2026-06-19")
        self.assertIn("A second building was not approved", status["metadata"]["scope_guardrail"])
        self.assertIn("colocation capabilities", status["metadata"]["scope_guardrail"])
        plan = next(item for item in proposal["evidence"] if item["key"] == "am28-palmcoast-city-approved-plan")
        self.assertIsNone(plan["published_at"])
        self.assertEqual(plan["metadata"]["approval_date"], "2025-11-12")
        self.assertFalse(plan["metadata"]["lifecycle_selected"])
        identity = plan["metadata"]["historical_plan_identity"]
        self.assertEqual(identity["project_address"], "1035 Town Center Blvd")
        self.assertEqual(identity["approved_site_lot"], "7B")
        self.assertIn("1109 Town Center Blvd", plan["metadata"]["plan_current_address_bridge"])
        self.assertIn("34,875", plan["metadata"]["unselected_dimensions"])
        self.assertIn("33,760", plan["metadata"]["unselected_dimensions"])
        self.assertEqual(plan["license"], "no-open-license-asserted")

    def test_two_new_projects_use_day_observations_and_campus_only_points(self):
        additions = added_acceptances()
        self.assertEqual(len(additions), 2)
        self.assertEqual({item["country_iso_a2"] for item in additions}, {"US", "DE"})
        projects = {row["project_stable_key"]: row for row in table(batch.draft_path(ROOT) / "projects.csv")}
        for acceptance in additions:
            with self.subTest(project=acceptance["project_stable_key"]):
                doc, proposal = selected_documents(acceptance)
                self.assertEqual(len(doc["lifecycle"]), 1)
                result = proposal["results"][0]
                core._geometry(result)
                self.assertEqual(result["geometry"]["type"], "Point")
                self.assertEqual(result["display_anchor"], result["geometry"])
                self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
                self.assertEqual(result["parent_campus_stable_key"], doc["campus"]["stable_key"])
                self.assertEqual(result["project_stable_key"], doc["project"]["stable_key"])
                row = projects[acceptance["project_stable_key"]]
                self.assertEqual(row["last_observed_physical_status"], "under_construction")
                expected_date = "2026-06-19" if acceptance["country_iso_a2"] == "US" else "2026-05-27"
                self.assertEqual(row["status_as_of"], expected_date)
                self.assertEqual(json.loads(row["geometry_json"]), result["geometry"])
                self.assertEqual(row["horizontal_uncertainty_metres"], "")
                self.assertEqual(row["independent_imagery_verification"], "false")

    def test_no_new_metrics_roles_workloads_or_completed_phases_selected(self):
        projects = table(batch.draft_path(ROOT) / "projects.csv")
        for acceptance in added_acceptances():
            doc, _ = selected_documents(acceptance)
            for field in ("operating_models", "workloads", "capacities"):
                self.assertEqual(doc[field], [])
            for field in ("campus", "project"):
                self.assertEqual(doc[field]["roles"], {})
                self.assertIsNone(doc[field]["coordinates"])
                self.assertIsNone(doc[field]["geometry"])
            rows = [row for row in projects if row["physical_site_stable_key"] == acceptance["parent_campus_stable_key"]]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["operating_model"], "unknown")
            for field in ("owner", "operator", "users", "tenants", "customers"):
                self.assertEqual(row[field], "")
            for field in ("workloads_json", "role_claims_json", "power_observations_json",
                          "annual_energy_observations_json", "efficiency_observations_json"):
                self.assertFalse(json.loads(row[field]))

    def test_all_new_bindings_are_portable_hashed_and_used_by_review(self):
        before = read(previous.contract_path(ROOT))
        after = read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        old_ids = {row["source_id"] for row in before["sources"]}
        specs = [row for row in after["sources"] if row["source_id"] not in old_ids]
        ids = {row["source_id"] for row in specs}
        self.assertEqual(len(validated.acceptances), 75)
        self.assertEqual(len(validated.sources), len(before["sources"]) + len(ids))
        self.assertEqual(ids, {source_id for acceptance in added_acceptances()
                               for source_id in acceptance["distinctness_review"]["evidence_source_ids"]})
        for spec in specs:
            with self.subTest(source=spec["source_id"]):
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
        self.assertEqual(len(old_features), 173)
        self.assertEqual(len(new_features), 175)
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
        old_counts = read(previous.draft_path(ROOT) / "manifest.json")["counts"]
        additional_bindings = len(batch.REVIEW_PINS.source_sha256) - len(previous.REVIEW_PINS.source_sha256)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 175, "projects": 178, "evidence": old_counts["evidence"] + additional_bindings,
            "countries": 43, "non_us_sites": 117, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 173,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 75, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 175, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 178, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 178)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-seventy-five-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
