"""Marfino and Pecém add two campuses without refreshing or widening source claims."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_third_reviewed as previous
from datacenter_atlas import expansion_200_twenty_fourth_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
MARFINO_CURATED = "curated-official-2026-09-09-europe-round26-cloud4y-marfino-current-build.json"
MARFINO_GEOMETRY = "verified-construction-core-v0.18-europe-round26-cloud4y-marfino-geometry-proposal.json"
PECEM_CURATED = "curated-official-2026-09-09-americas-round26-omnia-pecem-june16-current-build.json"
PECEM_GEOMETRY = "verified-construction-core-v0.18-americas-round26-omnia-pecem-geometry-proposal.json"
MARFINO = "curated:cloud4y-marfino-data-center-campus"
MARFINO_PROJECT = MARFINO + ":main-building-current-build"
PECEM = "curated:omnia-pecem-data-center-campus"
PECEM_PROJECT = PECEM + ":initial-tiktok-bytedance-build"
MARFINO_STATUS = "eu26-cloud4y-marfino-july13-current-build"
PECEM_STATUS = "am26-omnia-pecem-june16-official-site-visit"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def packets():
    return tuple(read(SOURCES / name) for name in
                 (MARFINO_CURATED, MARFINO_GEOMETRY, PECEM_CURATED, PECEM_GEOMETRY))


def evidence():
    return {row["key"]: row for document in packets() for row in document["evidence"]}


class TwentyFourthReviewedDraftTests(unittest.TestCase):
    def test_marfino_june_month_is_not_july_publication_or_exact_observation_day(self):
        doc, geometry, _, _ = packets()
        source = evidence()[MARFINO_STATUS]
        metadata = source["metadata"]
        self.assertEqual(source["published_at"], "2026-07-13")
        self.assertEqual(source["content_hash"],
                         "56ae80cde91de531ee48c3bde7dd03f4e9e4f202a782f7c45f5fe857e0263ce2")
        self.assertEqual(metadata["raw_capture_bytes"], 151546)
        self.assertEqual(metadata["status_as_of"], "2026-06-01")
        self.assertEqual(metadata["status_date_precision"], "month")
        self.assertEqual(metadata["source_observation_month"], "2026-06")
        self.assertEqual(metadata["source_observation_interval"], ["2026-06-01", "2026-06-30"])
        self.assertEqual(metadata["published_time_literal"], "2026-07-13T11:34:30+03:00")
        self.assertEqual(metadata["modified_time_literal"], "2026-07-13T14:32:59+03:00")
        self.assertIn("not an asserted observation day", metadata["status_as_of_normalization"])
        self.assertIn("July13 is only the article publication date", metadata["status_date_semantics"])
        self.assertIn("Neither publication, modification nor September retrieval refreshes lifecycle",
                      metadata["date_caveat"])
        self.assertEqual(doc["lifecycle"], [{
            "entity": "project", "value": "under_construction", "evidence_key": MARFINO_STATUS,
            "as_of_date": "2026-06-01", "method": "authoritative_physical_status_update",
            "confidence": 0.97,
        }])
        normalized = geometry["status_date_normalization"]
        for key in ("status_as_of", "status_date_precision", "source_observation_month",
                    "source_observation_interval"):
            self.assertEqual(normalized[key], metadata[key])
        self.assertEqual(normalized["publication_date"], source["published_at"])
        self.assertEqual(doc["campus"]["as_of_date"], "2026-06-01")
        self.assertEqual(doc["project"]["as_of_date"], "2026-06-01")

    def test_marfino_public_body_piles_not_future_slabs_or_operating_container(self):
        metadata = evidence()[MARFINO_STATUS]["metadata"]
        self.assertIn("later public #post-content-body HTML occurrence", metadata["literal_pointer"])
        self.assertIn("not in a JSON-LD articleBody field", metadata["literal_pointer"])
        pointers = metadata["literal_byte_pointers"][2:]
        self.assertEqual([row["offset"] for row in pointers], [97602, 98278, 99359, 107768])
        self.assertEqual([row["literal"] for row in pointers], [
            "Строящееся основное здание", "В июне залиты фундаменты",
            "бетон в сваях уже залит", "сейчас ведётся основное строительство",
        ])
        self.assertIn("Existing operating container center is expressly excluded", metadata["physical_scope"])
        self.assertIn("later planned modules are not new selected projects or sites", metadata["physical_scope"])
        self.assertIn("piles concreted with slabs still future", metadata["scope_caveats"])
        self.assertIn("cannot be described as completed approvals", metadata["scope_caveats"])

    def test_marfino_corporate_channel_bridge_does_not_assert_legal_rename_or_opening(self):
        by_key = evidence()
        status = by_key[MARFINO_STATUS]["metadata"]
        self.assertEqual(status["source_kind"], "operator_authored_corporate_blog_hosted_by_third_party")
        self.assertEqual(status["authority_dependencies"], [
            "eu26-cloud4y-marfino-operator-identity", "eu26-cloud4y-marfino-original-identity",
        ])
        self.assertIn("not proof of a legal name change", status["source_authority_basis"])
        identity = by_key["eu26-cloud4y-marfino-operator-identity"]["metadata"]
        self.assertIn("https://habr.com/ru/companies/cloud4y/articles/", identity["literal_pointer"])
        self.assertIn("No legal merger or rebranding date asserted", identity["branding_caveat"])
        self.assertIn("not selected as status", identity["marketing_caveat"])
        self.assertIn("Headquarters Avangardnaya3 is excluded", identity["address_scope"])
        historical = by_key["eu26-cloud4y-marfino-original-identity"]["metadata"]
        self.assertEqual(historical["use_scope"], "historical_project_identity_only")
        successor = by_key["eu26-cloud4y-marfino-successor-index"]["metadata"]
        self.assertEqual(successor["use_scope"], "bounded_successor_check_only")
        self.assertIn("Index absence is not proof of no successor", successor["limitations"])

    def test_marfino_operator_axes_follow_actual_handler_and_yandex_contract(self):
        _, geometry, _, _ = packets()
        result = geometry["results"][0]
        core._geometry(result)
        self.assertEqual(result["location_basis"], "first_party_site_coordinate")
        self.assertEqual(result["geometry"], {
            "type": "Point", "coordinates": [37.56629790523428, 56.07411594800743],
        })
        by_key = evidence()
        point = by_key["eu26-cloud4y-marfino-operator-point"]["metadata"]
        self.assertEqual(point["source_literal_coordinate_tokens"], {
            "data_js_long": "56.07411594800743", "data_js_lat": "37.56629790523428",
        })
        self.assertEqual(point["source_coordinate_order"], "latitude_longitude")
        self.assertEqual(point["source_crs"], "EPSG:4326")
        self.assertIsNone(point["source_accuracy_metres"])
        self.assertIn("«Марфино»", point["literal_pointer"])
        self.assertIn("Misleading operator attribute names", point["source_crs_scope"])
        self.assertIn("Headquarters default", point["excluded_coordinates"])
        code = by_key["eu26-cloud4y-marfino-map-code"]["metadata"]
        self.assertIn("Placemark([long,lat])", code["literal_pointer"])
        self.assertIn("browser execution not performed", code["runtime_scope"])
        order = by_key["eu26-yandex-jsapi-coordinate-order"]["metadata"]
        self.assertEqual(order["use_scope"], "coordinate_axis_order_only")
        self.assertIn("no coordorder", order["literal_pointer"])
        self.assertEqual(result["semantics"]["geometry_derivation"],
                         "operator_card_coordinate_pair_axis_reorder_only")
        self.assertIn("not construction boundary", result["semantics"]["precision_scope"])

    def test_pecem_official_june_visit_does_not_select_separate_railway_work(self):
        _, _, doc, _ = packets()
        source = evidence()[PECEM_STATUS]
        metadata = source["metadata"]
        self.assertEqual(source["kind"], "government_record")
        self.assertEqual(source["published_at"], "2026-06-16")
        self.assertEqual(source["content_hash"],
                         "b9c7ecbf573c60f8ca75a2123ebbdc20f6d309a6e51d045d1f90cbe79c8ecf1e")
        self.assertEqual(metadata["raw_capture_bytes"], 83749)
        self.assertEqual(metadata["source_observation_date"], "2026-06-16")
        self.assertEqual(metadata["status_date_precision"], "day")
        self.assertEqual(metadata["physical_short_excerpt"], "que está sendo construído pela OMNIA")
        self.assertEqual(metadata["physical_short_excerpt_byte_range"], [37954, 37992])
        self.assertIn("ASCOM–Casa Civil", metadata["authority_basis"])
        self.assertIn("on-site visit led by OMNIA", metadata["authority_basis"])
        self.assertIn("Transnordestina railway sections concern different works", metadata["scope_guardrail"])
        self.assertIn("not first construction day", metadata["date_caveat"])
        self.assertEqual(doc["lifecycle"], [{
            "entity": "project", "value": "under_construction", "evidence_key": PECEM_STATUS,
            "as_of_date": "2026-06-16", "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }])

    def test_pecem_old_keys_and_exact_corporate_project_bridge_exclude_offsite_points(self):
        _, _, doc, geometry = packets()
        association = geometry["campus_association"]
        original = read(ROOT / association["original_source_path"])
        self.assertTrue(association["old_keys_preserved"])
        self.assertTrue(association["one_campus_all_phases"])
        for field, expected in (("campus", PECEM), ("project", PECEM_PROJECT)):
            self.assertEqual(original[field]["stable_key"], expected)
            self.assertEqual(doc[field]["stable_key"], expected)
        self.assertIn("not new tenant or workload evidence",
                      evidence()[PECEM_STATUS]["metadata"]["project_label_scope"])
        point = evidence()["am26-pecem-semace-exact-campus-point"]["metadata"]
        self.assertEqual(point["source_project_name"], "Projeto Data Center Pecém")
        self.assertEqual(point["source_enterprise_id"], 127774)
        self.assertEqual(point["source_cnpj"], "55851548000137")
        self.assertEqual(point["post_body"]["filter"]["cpfCnpj"], point["source_cnpj"])
        self.assertEqual(point["source_spu"], "57022021344202405")
        self.assertEqual(point["source_li_spu"], "57022010023202558")
        self.assertIn("CDV DC I", point["identity_caveat"])
        self.assertIn("OMNIA BR PC01", point["identity_caveat"])
        self.assertIn("without inventing a rename date", point["identity_caveat"])
        self.assertIn("enterprise129195", point["excluded_points"])
        self.assertIn("camp129639", point["excluded_points"])
        permit = evidence()["am26-pecem-signed-installation-license"]["metadata"]
        self.assertIn("LI48/2025", permit["literal_pointer"])
        self.assertIn("Maracanaú business-office address is not the project site", permit["office_exclusion"])
        self.assertTrue(permit["no_status_refresh_from_permit"])

    def test_pecem_literal_applicant_marker_not_interpreted_permit_polygon(self):
        _, _, _, geometry = packets()
        result = geometry["results"][0]
        core._geometry(result)
        point = evidence()["am26-pecem-semace-exact-campus-point"]["metadata"]
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["geometry"], {
            "type": "Point", "coordinates": [-38.82234191894531, -3.65423321723938],
        })
        self.assertEqual(point["selected_coordinates"], result["geometry"]["coordinates"])
        self.assertEqual(point["coordinate_order"], "longitude, latitude")
        self.assertEqual(point["output_crs"], "EPSG:4326")
        self.assertIn("Original database/survey datum is not stated", point["source_crs"])
        self.assertIn("not an independently surveyed agency point", point["accuracy_scope"])
        self.assertIn("No geocoding", point["derivation"])
        permit = evidence()["am26-pecem-signed-installation-license"]["metadata"]
        self.assertEqual(permit["source_crs_literal"], "UTM, ZONA 24M, DATUM SIRGAS 2000")
        self.assertIn("N/E suffixes are transposed", permit["native_coordinate_caveat"])
        self.assertIn("For corroboration only", permit["native_coordinate_caveat"])
        self.assertFalse(permit["corroborative_check"]["full_polygon_selected"])
        semantics = evidence()["am26-pecem-map-wgs84-semantics"]["metadata"]
        self.assertIn("does not verify a survey datum", semantics["crs_caveat"])
        self.assertEqual(result["semantics"]["geometry_derivation"], "literal_official_public_project_marker")

    def test_rights_and_successor_limits_do_not_become_open_data_or_compliance_claims(self):
        by_key = evidence()
        self.assertEqual(Counter(row["license"] for row in by_key.values()), {
            "no-open-license-asserted": 16, "all-rights-reserved": 1, "CC-BY-4.0": 1,
        })
        self.assertIn("not provider results",
                      by_key["eu26-cloud4y-marfino-operator-point"]["metadata"]["rights_scope"])
        point = by_key["am26-pecem-semace-exact-campus-point"]["metadata"]
        self.assertIn("not an affirmative redistribution license", point["rights_scope"])
        self.assertFalse(point["raw_capture_redistributed"])
        map_contract = by_key["am26-pecem-map-wgs84-semantics"]["metadata"]
        self.assertIn("no Maps basemap, tile, imagery, API result", map_contract["rights_scope"])
        mpf = by_key["am26-pecem-mpf-conditions-context"]["metadata"]
        self.assertEqual(mpf["source_date"], "2026-05-20")
        self.assertEqual(mpf["event_date"], "2026-05-19")
        self.assertFalse(mpf["lifecycle_selected"])
        self.assertIn("unresolved regulatory concerns", mpf["review_caveat"])
        self.assertIn("cannot be treated as proof of compliance", mpf["review_caveat"])
        for number in (1, 2, 3):
            row = by_key[f"am26-pecem-semace-records-page{number}"]["metadata"]
            self.assertTrue(row["successor_only"])
            self.assertFalse(row["lifecycle_selected"])
            self.assertEqual(row["post_body"]["pagina"], number)
            self.assertIn("32distinct company licensing records", row["review_caveat"])
            self.assertIn("not proof of physical progress", row["review_caveat"])

    def test_two_campus_locators_add_no_roles_metrics_workloads_or_imagery(self):
        marfino, marfino_geometry, pecem, pecem_geometry = packets()
        parser = importlib.import_module(f"{baseline.__package__}.curated_v11")
        for filename, doc, geometry, campus, project, date in (
            (MARFINO_CURATED, marfino, marfino_geometry, MARFINO, MARFINO_PROJECT, "2026-06-01"),
            (PECEM_CURATED, pecem, pecem_geometry, PECEM, PECEM_PROJECT, "2026-06-16"),
        ):
            with self.subTest(campus=campus):
                parser._parse_document(SOURCES / filename, max(row["retrieved_at"] for row in doc["evidence"]))
                self.assertEqual(doc["campus"]["stable_key"], campus)
                self.assertEqual(doc["project"]["stable_key"], project)
                for key in ("campus", "project"):
                    self.assertEqual(doc[key]["roles"], {})
                    self.assertIsNone(doc[key]["coordinates"])
                    self.assertIsNone(doc[key]["geometry"])
                for key in ("operating_models", "workloads", "capacities"):
                    self.assertEqual(doc[key], [])
                result = geometry["results"][0]
                self.assertEqual(result["parent_campus_stable_key"], campus)
                self.assertEqual(result["project_stable_key"], project)
                self.assertEqual(result["display_anchor"], result["geometry"])
                self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
                rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                        if row["physical_site_stable_key"] == campus]
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["project_stable_key"], project)
                self.assertEqual(row["last_observed_physical_status"], "under_construction")
                self.assertEqual(row["status_as_of"], date)
                self.assertEqual(json.loads(row["geometry_json"]), result["geometry"])
                self.assertEqual(row["horizontal_uncertainty_metres"], "")
                self.assertEqual(row["operating_model"], "unknown")
                self.assertEqual(row["independent_imagery_verification"], "false")
                for field in ("workloads_json", "role_claims_json", "power_observations_json",
                              "annual_energy_observations_json", "efficiency_observations_json"):
                    self.assertFalse(json.loads(row[field]))
                for field in ("owner", "operator", "users", "tenants", "customers"):
                    self.assertEqual(row[field], "")
        self.assertEqual(marfino_geometry["distinctness_review"]["features"], 171)
        self.assertEqual(marfino_geometry["distinctness_review"]["overlaps"], [])
        self.assertEqual(marfino_geometry["distinctness_review"]["alias_matches"], [])
        self.assertEqual(marfino_geometry["distinctness_review"]["geometry_types"],
                         {"Point": 127, "Polygon": 42, "MultiPolygon": 2})
        self.assertEqual(pecem_geometry["distinctness_review"]["sites_compared"], 171)
        self.assertEqual(pecem_geometry["distinctness_review"]["projects_compared"], 174)
        self.assertEqual(pecem_geometry["distinctness_review"]["full_geometry_collisions"], [])
        self.assertEqual(pecem_geometry["distinctness_review"]["matched_selected_campuses"], [])
        self.assertNotEqual(marfino_geometry["results"][0]["geometry"], pecem_geometry["results"][0]["geometry"])

    def test_eighteen_bindings_close_against_portable_sources_without_temporary_files(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 73)
        by_key = evidence()
        self.assertEqual(len(by_key), 18)
        sources = {row["source_id"]: row for row in new["sources"]}
        self.assertEqual(len(validated.sources), 486)
        self.assertEqual(len(validated.sources), len(old["sources"]) + len(by_key))
        self.assertEqual(set(sources) - {row["source_id"] for row in old["sources"]}, set(by_key))
        for doc, geometry, expected_count in ((packets()[0], packets()[1], 8), (packets()[2], packets()[3], 10)):
            keys = {row["key"] for document in (doc, geometry) for row in document["evidence"]}
            bindings = geometry["source_binding_map"]
            self.assertEqual(len(bindings), expected_count)
            self.assertEqual({row["source_id"] for row in bindings}, keys)
            result = geometry["results"][0]
            self.assertLessEqual(set(result["geometry_source_ids"] + result["identity_source_ids"]), keys)
            acceptance = next(row for row in new["acceptances"]
                              if row["project_stable_key"] == doc["project"]["stable_key"])
            self.assertEqual(set(acceptance["distinctness_review"]["evidence_source_ids"]), keys)
            for binding in bindings:
                source_id = binding["source_id"]
                with self.subTest(source=source_id):
                    source = by_key[source_id]
                    core._source_evidence(source, source_id)
                    metadata = source["metadata"]
                    self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
                    self.assertRegex(source["content_hash"], r"^[a-f0-9]{64}$")
                    self.assertGreater(metadata["raw_capture_bytes"], 0)
                    self.assertEqual(metadata["http_status"], 200)
                    self.assertFalse(metadata["request_credentials_supplied"])
                    self.assertTrue(metadata["rights_scope"])
                    self.assertTrue(metadata["literal_pointer"])
                    self.assertTrue(metadata.get("raw_local_path") or metadata.get("raw_capture_temp_path"))
                    for pointer in metadata.get("literal_byte_pointers", []):
                        self.assertGreaterEqual(pointer["offset"], 0)
                        self.assertGreater(pointer["length"], 0)
                        self.assertLessEqual(pointer["offset"] + pointer["length"], metadata["raw_capture_bytes"])
                    for start, end in metadata.get("byte_ranges", []):
                        self.assertGreaterEqual(start, 0)
                        self.assertGreater(end, start)
                        self.assertLessEqual(end, metadata["raw_capture_bytes"])
                    self.assertEqual(sources[source_id]["path"], binding["path"])
                    self.assertEqual(sources[source_id]["evidence_pointer"], binding["evidence_pointer"])
                    value = read(ROOT / binding["path"])
                    for token in binding["evidence_pointer"].strip("/").split("/"):
                        value = value[int(token)] if isinstance(value, list) else value[token]
                    self.assertEqual(value, source)

    def test_all_171_prior_csv_rows_full_features_sources_and_acceptances_preserved(self):
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
        self.assertEqual(len(old_features), 171)
        self.assertEqual(len(new_features), 173)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        core.validate_batch(previous.contract_path(ROOT), previous.REVIEW_PINS, root=ROOT)
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
            raw = (ROOT / source["path"]).read_bytes()
            self.assertEqual(len(raw), source["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
            self.assertEqual(previous.REVIEW_PINS.source_sha256[source["source_id"]],
                             batch.REVIEW_PINS.source_sha256[source["source_id"]])
        self.assertLessEqual(set(previous.REVIEW_PINS.acceptance_sha256),
                             set(batch.REVIEW_PINS.acceptance_sha256))
        current = {item["project_stable_key"]: item for item in new["acceptances"]}
        for acceptance in old["acceptances"]:
            changed = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            changed["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(changed, acceptance)

    def test_eleven_artifact_byte_exact_rebuild_and_incomplete_final_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        old_counts = read(previous.draft_path(ROOT) / "manifest.json")["counts"]
        self.assertEqual(old_counts["evidence"] + len(evidence()), 722)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 173, "projects": 176, "evidence": 722,
            "countries": 43, "non_us_sites": 116, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 171,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 73, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 173, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 176, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 176)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-seventy-three-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
