"""66-addition checkpoint preserves Bulk work scopes and every prior record."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_nineteenth_reviewed as previous
from datacenter_atlas import expansion_200_twentieth_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "sources/verified-construction-core-v0.18-europe-round22-bulk-geometry-proposal.json"
RESEARCH = ROOT / "sources/research-expansion-200-europe-round22-2026-09-09.json"
CASES = {
    "n01": {
        "curated": ROOT / "sources/curated-official-2026-09-09-europe-round22-bulk-n01-q2-current-build.json",
        "campus": "curated:bulk-n01-vennesla-campus",
        "project": "curated:bulk-n01-vennesla-campus:current-new-facility-construction",
        "point": [7.892050100000001, 58.2575732],
        "address": {
            "@type": "PostalAddress", "streetAddress": "Stølevegen 39",
            "addressLocality": "Øvrebø", "postalCode": "4715 Øvrebø", "addressCountry": "NO",
        },
    },
    "dk01": {
        "curated": ROOT / "sources/curated-official-2026-09-09-europe-round22-bulk-dk01-q2-current-build.json",
        "campus": "curated:bulk-dk01-esbjerg-campus",
        "project": "curated:bulk-dk01-esbjerg-campus:current-new-building-construction",
        "point": [8.4955427, 55.5092486],
        "address": {
            "@type": "PostalAddress", "streetAddress": "Guldborgsundvej 14",
            "addressLocality": "Esbjerg", "postalCode": "6705 Esbjerg", "addressCountry": "DK",
        },
    },
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def evidence_by_key():
    items = list(read(GEOMETRY)["evidence"])
    for case in CASES.values():
        items.extend(read(case["curated"])["evidence"])
    return {item["key"]: item for item in items}


class TwentiethReviewedDraftTests(unittest.TestCase):
    def test_quarter_end_physical_observation_is_not_publication_or_start_day(self):
        for code, case in CASES.items():
            with self.subTest(campus=code):
                doc = read(case["curated"])
                self.assertEqual(doc["schema_version"], "1.1")
                self.assertEqual(len(doc["evidence"]), 1)
                evidence = doc["evidence"][0]
                meta = evidence["metadata"]
                self.assertEqual(evidence["key"], f"eu22-bulk-{code}-june30-construction")
                self.assertEqual(evidence["kind"], "company_disclosure")
                self.assertEqual(evidence["publisher"], "Bulk Infrastructure Group AS")
                self.assertEqual(evidence["published_at"], "2026-07-16")
                self.assertEqual(meta["source_observation_date"], "2026-06-30")
                self.assertEqual(meta["selected_status_date"], "2026-06-30")
                self.assertEqual(meta["status_date_precision"], "day")
                self.assertIn("not a construction-start date", meta["status_as_of_normalization"])
                self.assertIn("independently of the financial capitalization", meta["source_authority_basis"])
                self.assertEqual(meta["pdf_review"]["full_pages_visually_reviewed"], [1, 2, 4, 17])
                self.assertEqual(len(doc["lifecycle"]), 1)
                lifecycle = doc["lifecycle"][0]
                self.assertEqual(lifecycle["entity"], "project")
                self.assertEqual(lifecycle["value"], "under_construction")
                self.assertEqual(lifecycle["as_of_date"], "2026-06-30")
                self.assertEqual(lifecycle["evidence_key"], evidence["key"])
                self.assertEqual(lifecycle["method"], "authoritative_physical_status_update")
        publication = evidence_by_key()["eu22-bulk-q2-publication"]
        self.assertEqual(publication["published_at"], "2026-07-16")
        self.assertIn("not a second physical observation", publication["metadata"]["temporal_guardrail"])

    def test_literal_schema_coordinates_are_bound_to_each_exact_campus_url_and_address(self):
        by_key = evidence_by_key()
        for code, case in CASES.items():
            with self.subTest(campus=code):
                evidence = by_key[f"eu22-bulk-{code}-operator-coordinate"]
                meta = evidence["metadata"]
                url = f"https://bulkinfrastructure.com/data-centers/locations/{code}"
                self.assertEqual(evidence["source_url"], url)
                self.assertIsNone(evidence["published_at"])
                self.assertEqual(meta["source_entity_url"], url)
                self.assertEqual(meta["source_context"], "https://schema.org")
                self.assertEqual(meta["source_type"], "LocalBusiness")
                self.assertEqual(meta["source_address"], case["address"])
                self.assertEqual(meta["source_geo"], {
                    "@type": "GeoCoordinates", "longitude": case["point"][0],
                    "latitude": case["point"][1],
                })
                self.assertEqual(meta["source_point"], case["point"])
                self.assertEqual(meta["source_crs"], "EPSG:4326")
                self.assertEqual(meta["coordinate_order"], "longitude,latitude")
                self.assertIn("same-object URL", meta["identity_scope"])
                self.assertIn("Oslo is not selected", meta["identity_scope"])
                self.assertIn("opening hours do not establish", meta["temporal_guardrail"])
                self.assertEqual(evidence["license"], "no-open-license-asserted")
        crs = by_key["eu22-schema-geocoordinates-wgs84"]
        self.assertEqual(crs["source_url"], "https://schema.org/GeoCoordinates")
        self.assertEqual(crs["metadata"]["source_crs"], "EPSG:4326")
        self.assertEqual(crs["metadata"]["axis_mapping"],
                         "schema.org longitude -> GeoJSON x; schema.org latitude -> GeoJSON y")

    def test_literal_operator_points_are_locators_not_boundaries_or_survey_accuracy(self):
        results = read(GEOMETRY)["results"]
        self.assertEqual(len(results), 2)
        for code, case in CASES.items():
            with self.subTest(campus=code):
                result = next(row for row in results if row["project_stable_key"] == case["project"])
                self.assertEqual(result["parent_campus_stable_key"], case["campus"])
                self.assertEqual(result["geometry"], {"type": "Point", "coordinates": case["point"]})
                self.assertEqual(result["display_anchor"], result["geometry"])
                self.assertEqual(result["location_basis"], "first_party_site_coordinate")
                self.assertEqual(set(result["geometry_source_ids"]), {
                    f"eu22-bulk-{code}-operator-coordinate", "eu22-schema-geocoordinates-wgs84",
                })
                semantics = result["semantics"]
                self.assertEqual(semantics["geometry_authority_class"], "official_source")
                self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
                self.assertEqual(semantics["geometry_source_entity_kind"], "campus")
                self.assertEqual(semantics["geometry_derivation"],
                                 "source_attribute_decimal_coordinates_to_point_without_centroiding")
                self.assertIsNone(semantics["horizontal_uncertainty_metres"])
                self.assertIn("not asserted at the exact point", semantics["precision_scope"])
                self.assertIn("do not establish survey accuracy", semantics["horizontal_uncertainty_unknown_reason"])
                core._geometry(result)

    def test_corroboration_does_not_replace_operator_points_or_refresh_lifecycle(self):
        evidence = evidence_by_key()
        community = evidence["eu22-bulk-n01-nominatim-crosscheck"]
        self.assertEqual(community["license"], "ODbL-1.0")
        meta = community["metadata"]
        self.assertEqual(meta["osm_relation_id"], 13780899)
        self.assertEqual(meta["source_result_count"], 1)
        self.assertEqual(meta["source_geojson"]["type"], "MultiPolygon")
        self.assertTrue(meta["operator_point_contained"])
        self.assertFalse(meta["provider_point_selected"])
        self.assertFalse(meta["community_boundary_selected"])
        self.assertIn("ODbL is not assigned to the separate operator point", meta["rights_scope"])
        osm = evidence["eu22-bulk-n01-osm-identity"]["metadata"]
        self.assertEqual(osm["osm_relation_version"], 3)
        self.assertEqual(osm["selected_tags"]["name"], "Bulk N01 Campus")
        self.assertEqual(osm["member_way_ids"], [635828688, 1029902506])
        self.assertIn("not a construction observation", osm["temporal_guardrail"])
        address = evidence["eu22-bulk-dk01-government-address"]["metadata"]
        self.assertEqual(address["street_address"], "Guldborgsundvej 14, 6705 Esbjerg Ø")
        self.assertEqual(address["parcel_identifier"], "1aæ - Kærsing Gde., Bryndum")
        self.assertIn("not an inferred corporate-office coordinate", address["identity_scope"])
        brochure = evidence["eu22-bulk-n01-brochure-context"]["metadata"]
        self.assertFalse(brochure["source_dms_selected"])
        self.assertTrue(brochure["source_dms_crs_unknown"])
        self.assertIn("not treated as an exact publication day", brochure["publication_date_semantics"])

    def test_one_project_per_campus_without_new_roles_capacity_or_workloads(self):
        projects = table(batch.draft_path(ROOT) / "projects.csv")
        parser = importlib.import_module(f"{baseline.__package__}.curated_v11")
        for code, case in CASES.items():
            with self.subTest(campus=code):
                doc = read(case["curated"])
                parser._parse_document(case["curated"], "2026-09-09T08:00:00Z")
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["stable_key"], case[entity])
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("capacities", "workloads", "operating_models"):
                    self.assertEqual(doc[field], [])
                meta = doc["evidence"][0]["metadata"]
                self.assertIn("existing", meta["physical_scope"])
                self.assertIn("OSIX is not admitted", meta["excluded_scopes"])
                self.assertIn("older operating halls do not supersede", meta["successor_review"])
                rows = [row for row in projects if row["physical_site_stable_key"] == case["campus"]]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["project_stable_key"], case["project"])
                self.assertEqual(rows[0]["status_as_of"], "2026-06-30")
                for field in ("workloads_json", "role_claims_json", "power_observations_json",
                              "annual_energy_observations_json", "efficiency_observations_json"):
                    self.assertFalse(json.loads(rows[0][field]))
                self.assertEqual(rows[0]["operating_model"], "unknown")

    def test_two_acceptances_close_exactly_eleven_new_source_bindings(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 66)
        self.assertEqual(len(validated.sources), 414)
        evidence = evidence_by_key()
        self.assertEqual(len(evidence), 11)
        bindings = {item["source_id"]: item for item in read(GEOMETRY)["source_binding_map"]}
        sources = {item["source_id"]: item for item in new["sources"]}
        self.assertEqual(set(sources) - {item["source_id"] for item in old["sources"]}, set(evidence))
        self.assertEqual(set(bindings), set(evidence))
        for key, item in evidence.items():
            with self.subTest(source=key):
                meta = item["metadata"]
                self.assertEqual(meta["content_hash_verification"], "fetched_bytes_sha256")
                self.assertGreater(meta["raw_capture_bytes"], 0)
                self.assertEqual(meta["http_status"], 200)
                self.assertFalse(meta["request_credentials_supplied"])
                self.assertTrue(meta["rights_scope"])
                self.assertEqual(sources[key]["path"], bindings[key]["path"])
                self.assertEqual(sources[key]["evidence_pointer"], bindings[key]["evidence_pointer"])
                pointed = read(ROOT / bindings[key]["path"])
                for token in bindings[key]["evidence_pointer"].strip("/").split("/"):
                    pointed = pointed[int(token)] if isinstance(pointed, list) else pointed[token]
                self.assertEqual(pointed, item)
                raw = (ROOT / sources[key]["path"]).read_bytes()
                self.assertEqual(len(raw), sources[key]["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sources[key]["sha256"])
                core._source_evidence(item, key)
        additions = {item["project_stable_key"]: item for item in new["acceptances"]
                     if item["project_stable_key"] not in {row["project_stable_key"] for row in old["acceptances"]}}
        self.assertEqual(set(additions), {case["project"] for case in CASES.values()})
        review_sources = set()
        for case in CASES.values():
            addition = additions[case["project"]]
            self.assertEqual(addition["parent_campus_stable_key"], case["campus"])
            review_sources.update(addition["distinctness_review"]["evidence_source_ids"])
        self.assertEqual(review_sources, set(evidence))

    def test_research_capture_bindings_and_excluded_routes_need_no_temporary_corpus(self):
        research = read(RESEARCH)
        captures = {item["raw_local_path"]: item for item in research["captures"]}
        for item in evidence_by_key().values():
            capture = captures[item["metadata"]["raw_capture_temp_path"]]
            self.assertEqual(capture["sha256"], item["content_hash"])
            self.assertEqual(capture["bytes"], item["metadata"]["raw_capture_bytes"])
            self.assertEqual(capture["source_url"], item["source_url"])
        self.assertEqual({item["project_stable_key"] for item in research["candidates"]},
                         {case["project"] for case in CASES.values()})
        spatial = research["spatial_review"]
        self.assertEqual(spatial["baseline_physical_sites"], 164)
        for code in CASES:
            self.assertEqual(spatial[code]["intersections"], [])
        self.assertTrue(spatial["n01"]["community_polygon_contains_primary_point"])
        self.assertEqual(spatial["n01"]["community_polygon_baseline_intersections"], [])
        failed = [item for item in research["captures"] if item["http_status"] != 200]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["http_status"], 455)
        self.assertIsNone(failed[0]["sha256"])
        self.assertIsNone(failed[0]["bytes"])
        self.assertIn("no alternate-client retry", research["successor_review"]["stopped_route"])

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
        self.assertEqual(len(old_features), 164)
        self.assertEqual(len(new_features), 166)
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

    def test_exact_eleven_artifact_rebuild_and_incomplete_release_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 166, "projects": 169, "evidence": 650, "countries": 42,
            "non_us_sites": 111, "official_boundary_projects": 5, "reviewed_site_locator_projects": 164,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 66, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 166, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 169, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 169)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-six-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
