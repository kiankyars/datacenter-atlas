"""Three distinct round24 campuses preserve the complete preceding checkpoint."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_first_reviewed as previous
from datacenter_atlas import expansion_200_twenty_second_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
PACKETS = {
    "aurora": (
        "curated-official-2026-09-09-americas-round24-qts-aurora-dc2-current-build.json",
        "verified-construction-core-v0.18-americas-round24-qts-aurora-geometry-proposal.json",
    ),
    "fechenheim": (
        "curated-official-2026-09-09-europe-round24-fechenheim-uw04-current-build.json",
        "verified-construction-core-v0.18-europe-round24-fechenheim-geometry-proposal.json",
    ),
    "daou": (
        "curated-official-2026-09-09-asia-round24-daou-jukjeon-halfyear-current-build.json",
        "verified-construction-core-v0.18-asia-round24-daou-jukjeon-geometry-proposal.json",
    ),
}
EXPECTED = {
    "aurora": ("curated:qts-aurora-den1-campus", ":dc2-current-fit-out", "2026-08-19", 11),
    "fechenheim": (
        "curated:digital-realty-fra20-frankfurt", ":uw04-substation-current-build", "2026-07-02", 10,
    ),
    "daou": ("curated:daou-jukjeon-cdc-campus", ":current-build", "2026-08-14", 6),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def packet(name):
    return tuple(read(SOURCES / filename) for filename in PACKETS[name])


def evidence():
    return {
        row["key"]: row
        for filenames in PACKETS.values()
        for filename in filenames
        for row in read(SOURCES / filename)["evidence"]
    }


class TwentySecondReviewedDraftTests(unittest.TestCase):
    def test_aurora_actual_inspection_is_not_an_issue_date_or_cancelled_visit(self):
        doc, geometry = packet("aurora")
        source = doc["evidence"][0]
        meta = source["metadata"]
        self.assertEqual(source["kind"], "government_record")
        self.assertEqual(source["publisher"], "City of Aurora, Colorado")
        self.assertIsNone(source["published_at"])
        self.assertEqual(meta["source_observation_date"], "2026-08-19")
        self.assertEqual(meta["source_inspection_timestamp_literal"], "8/19/2026 12:37:59 PM")
        self.assertIsNone(meta["source_timezone"])
        self.assertEqual(meta["status_date_precision"], "day")
        self.assertEqual(meta["permit_literal"], "25-2569691-LT")
        self.assertEqual(meta["inspection_type_literal"], "Drywall")
        self.assertEqual(meta["inspection_result_literal"], "OK")
        self.assertEqual(meta["address_literal"], "1140 N GUN CLUB RD")
        self.assertIn("cancelled-on-site", meta["excluded_rows"])
        self.assertIn("wrong inspection", meta["excluded_rows"])
        identity = geometry["evidence"][0]["metadata"]
        self.assertEqual(identity["permit_number_literal"], "25-2569691-000-00")
        self.assertEqual(identity["folder_type_literal"], "LT")
        self.assertEqual(identity["folder_rsn"], 1937937)
        self.assertEqual(identity["property_rsn"], 227490)
        self.assertIn("not silently equated", identity["cross_view_permit_normalization"])
        successor = evidence()["am24-aurora-postcutoff-inspection-context"]["metadata"]
        self.assertTrue(successor["successor_only"])
        self.assertTrue(successor["post_reference_date_excluded_from_status"])
        self.assertFalse(successor["lifecycle_selected"])
        self.assertTrue(all("q.com" not in row["source_url"] for row in geometry["evidence"]))

    def test_aurora_exact_native_address_point_retains_datum_and_rights_caveats(self):
        _, geometry = packet("aurora")
        result = geometry["results"][0]
        core._geometry(result)
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["geometry"]["coordinates"], [-104.71239001410385, 39.73378311392442])
        by_key = evidence()
        point = by_key["am24-aurora-city-wgs84-address-point"]["metadata"]
        self.assertEqual(point["source_objectid"], 58597929)
        self.assertEqual(point["source_address_id"], "777076746")
        self.assertEqual(point["source_property_rsn"], 227490)
        self.assertEqual(point["query_parameters"], {
            "returnGeometry": True, "outSR": 4326, "datumTransformation": 1188,
        })
        native = by_key["am24-aurora-city-native-address-context"]["metadata"]
        self.assertEqual(native["native_coordinates"], [3221510.2228432745, 1693120.3680016845])
        self.assertIn("EPSG:2232", native["native_crs"])
        self.assertIn("not used", native["excluded_stored_attributes"])
        check = native["independent_transform_check"]
        self.assertEqual(check["datum_operation_epsg"], 1188)
        self.assertEqual(check["operation_accuracy_metres_not_source_position_accuracy"], 4)
        self.assertFalse(check["best_available"])
        self.assertEqual(check["missing_preferred_grid"], "us_noaa_cohpgn.tif")
        self.assertIn("07/05/2024", native["successor_scope"])
        self.assertIn("DC1", native["successor_scope"])
        self.assertIn("indemnification", geometry["rights_scope"])
        self.assertIn("not affirmative redistribution permission", geometry["rights_scope"])
        self.assertTrue(all(row["license"] == "no-open-license-asserted" for row in geometry["evidence"]))

    def test_fechenheim_selects_uw04_not_old_halls_or_an_invented_trade_milestone(self):
        doc, geometry = packet("fechenheim")
        source = doc["evidence"][0]
        meta = source["metadata"]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(source["publisher"], "Adolf Lupp GmbH + Co KG")
        self.assertEqual(source["published_at"], "2026-07-02")
        self.assertEqual(meta["selected_wording"], [
            "entsteht ein Umspannwerksgebäude", "an der Umsetzung beteiligt",
        ])
        self.assertEqual(meta["modified_time_literal"], "2026-08-11T11:36:09+02:00")
        self.assertEqual(meta["hidden_updated_time_literal"], "2026-08-11T13:36:09+02:00")
        self.assertIn("no July 2 version snapshot", meta["edit_caveat"])
        self.assertIn("UW04 substation building only", meta["physical_scope"])
        self.assertIn("No claim that listed excavation", meta["excluded_scope"])
        self.assertIn("isAccessibleForFree:false", meta["linkedin_exclusion"])
        old = read(SOURCES / "curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json")
        self.assertEqual(doc["campus"]["stable_key"], old["campus"]["stable_key"])
        self.assertNotEqual(doc["project"]["stable_key"], old["project"]["stable_key"])
        bridge = geometry["evidence"][1]["metadata"]
        self.assertEqual(bridge["visible_page_date"], "2025-11-26")
        self.assertEqual(bridge["body_dateline"], "2025-11-27")
        self.assertIn("separate operating constituent", bridge["completion_scope"])

    def test_fechenheim_fra20_marker_is_only_a_same_campus_constituent_locator(self):
        _, geometry = packet("fechenheim")
        result = geometry["results"][0]
        core._geometry(result)
        self.assertEqual(result["geometry"]["coordinates"], [8.752816, 50.125936])
        self.assertEqual(result["location_basis"], "first_party_site_coordinate")
        point = geometry["evidence"][0]["metadata"]
        self.assertEqual(point["source_node_title"], "FRA20")
        self.assertEqual(point["source_site_code"], "FRA20")
        self.assertEqual(point["source_address"], "Hugo-Junkers-Strasse 5a, 60386 Frankfurt am Main")
        self.assertEqual(point["source_crs"], "EPSG:4326")
        marker = point["marker_identity"]
        for key in ("location_latitude_override", "location_longitude_override", "field_second_line"):
            self.assertEqual(marker[key], [])
        self.assertEqual(marker["site_code_fallback"], "FRA20")
        self.assertEqual(len(result["geometry_source_ids"]), 7)
        self.assertIn("Not the UW04 building", result["semantics"]["precision_scope"])
        by_key = evidence()
        runtime = by_key["eu24-fechenheim-webpack-contract"]["metadata"]
        self.assertIn("5170:09fe70abdb9673fb", runtime["symbols"])
        self.assertIn("current-runtime dependency identity", runtime["linkage"])
        crs = by_key["eu24-fechenheim-google-wgs84-contract"]
        self.assertEqual(crs["license"], "CC-BY-4.0")
        self.assertIn("does not license map data", crs["metadata"]["rights_scope"])

    def test_daou_current_filing_date_is_separate_from_period_end_and_forecasts(self):
        doc, _ = packet("daou")
        source = doc["evidence"][0]
        meta = source["metadata"]
        self.assertEqual(source["publisher"], "Daou Technology Inc.")
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertIsNone(source["published_at"])
        self.assertEqual(meta["filing_date"], "2026-08-14")
        self.assertEqual(meta["observed_on"], "2026-08-14")
        self.assertEqual(meta["reporting_period_end"], "2026-06-30")
        self.assertEqual(meta["status_observation_basis"], "contemporaneous_current_construction_in_dated_issuer_filing")
        self.assertIn("not a claimed inspection", meta["date_scope"])
        self.assertIn("current-at-filing", meta["date_scope"])
        self.assertEqual(meta["source_literal_short_anchor"], "현재 구축 중 인 용인 죽전")
        self.assertEqual(meta["second_literal_short_anchor"], "구축중인 죽전CDC")
        self.assertIn("Generic under_construction only", meta["physical_scope"])
        research = read(SOURCES / "research-expansion-200-asia-round24-2026-09-09.json")
        later = research["candidates"][0]["successor_review"]["post_cutoff_IR"]
        self.assertFalse(later["selected_as_evidence"])
        self.assertEqual(later["creation_metadata"], "2026-09-01T10:23:33Z")
        for held in research["candidates"][1:]:
            self.assertTrue(held["disposition"].startswith("hold_"))
            self.assertEqual(held["source_ids"], [])
            self.assertIsNone(held["coordinates"])

    def test_daou_uses_operator_marker_not_google_place_pin_or_headquarters(self):
        _, geometry = packet("daou")
        result = geometry["results"][0]
        core._geometry(result)
        self.assertEqual(result["geometry"]["coordinates"], [127.132427, 37.332064])
        self.assertEqual(result["location_basis"], "first_party_site_coordinate")
        point = geometry["evidence"][0]["metadata"]
        self.assertEqual(point["source_crs"], "EPSG:4326")
        self.assertEqual(point["exact_address_as_published"], "경기도 용인시 죽전동 23-11, 12, 13")
        self.assertEqual(point["source_literal_coordinate_tokens"], {
            "latitude": "37.332064", "longitude": "127.132427",
        })
        excluded = point["excluded_coordinate_pair"]
        self.assertEqual([excluded["longitude"], excluded["latitude"]], [127.1324266, 37.3320386])
        self.assertNotEqual(result["geometry"]["coordinates"], [excluded["longitude"], excluded["latitude"]])
        self.assertIn("not copied from Google", point["point_provenance"])
        parent = evidence()["asia24-daou-parent-idc-authority"]["metadata"]
        self.assertIn("headquarters", parent["excluded_locator"])
        self.assertEqual(geometry["evidence"][2]["license"], "all-rights-reserved")
        self.assertIn("not an open-data licence", geometry["evidence"][2]["excerpt"])
        self.assertIsNone(point["source_accuracy_metres"])
        self.assertIn("One Jukjeon campus", geometry["distinctness_review"]["campus_grouping"])

    def test_three_campuses_have_one_project_each_and_no_new_roles_metrics_or_imagery(self):
        rows = table(batch.draft_path(ROOT) / "projects.csv")
        sites = table(batch.draft_path(ROOT) / "sites.csv")
        for name, (campus, suffix, day, _) in EXPECTED.items():
            with self.subTest(campus=name):
                doc, geometry = packet(name)
                parser = importlib.import_module(f"{baseline.__package__}.curated_v11")
                parser._parse_document(SOURCES / PACKETS[name][0], "2026-09-09T09:00:00Z")
                self.assertEqual(doc["campus"]["stable_key"], campus)
                self.assertEqual(doc["project"]["stable_key"], campus + suffix)
                self.assertEqual(doc["lifecycle"][0]["value"], "under_construction")
                self.assertEqual(doc["lifecycle"][0]["as_of_date"], day)
                for key in ("campus", "project"):
                    self.assertEqual(doc[key]["roles"], {})
                    self.assertIsNone(doc[key]["coordinates"])
                    self.assertIsNone(doc[key]["geometry"])
                for key in ("operating_models", "workloads", "capacities"):
                    self.assertEqual(doc[key], [])
                selected = [row for row in rows if row["physical_site_stable_key"] == campus]
                self.assertEqual(len(selected), 1)
                row = selected[0]
                self.assertEqual(row["project_stable_key"], campus + suffix)
                self.assertEqual(row["status_as_of"], day)
                self.assertEqual(row["operating_model"], "unknown")
                for field in ("workloads_json", "role_claims_json", "power_observations_json",
                              "annual_energy_observations_json", "efficiency_observations_json"):
                    self.assertFalse(json.loads(row[field]))
                site = next(row for row in sites if row["physical_site_stable_key"] == campus)
                self.assertEqual(site["project_count"], "1")
                semantics = geometry["results"][0]["semantics"]
                self.assertIsNone(semantics["horizontal_uncertainty_metres"])
                self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
                self.assertEqual(semantics["geometry_authority_class"], "official_source")

    def test_twenty_seven_new_source_bindings_are_closed_without_temporary_files(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 70)
        self.assertEqual(len(validated.sources), 457)
        by_key = evidence()
        self.assertEqual(len(by_key), 27)
        sources = {row["source_id"]: row for row in new["sources"]}
        self.assertEqual(set(sources) - {row["source_id"] for row in old["sources"]}, set(by_key))
        new_acceptances = {row["project_stable_key"]: row for row in new["acceptances"]}
        for name, (campus, suffix, _, count) in EXPECTED.items():
            _, geometry = packet(name)
            bindings = geometry["source_binding_map"]
            self.assertEqual(len(bindings), count)
            result = geometry["results"][0]
            ids = {row["source_id"] for row in bindings}
            self.assertEqual(ids, set(result["geometry_source_ids"] + result["identity_source_ids"]))
            self.assertLessEqual(ids, set(new_acceptances[campus + suffix]["distinctness_review"]["evidence_source_ids"]))
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
                    self.assertIn("rights_scope", metadata)
                    self.assertTrue(metadata.get("literal_pointer") or metadata.get("byte_ranges"))
                    for start, end in metadata.get("byte_ranges", []):
                        self.assertGreaterEqual(start, 0)
                        self.assertGreater(end, start)
                        self.assertLessEqual(end, metadata["raw_capture_bytes"])
                    self.assertTrue(metadata.get("raw_capture_temp_path") or metadata.get("raw_local_path"))
                    self.assertEqual(sources[source_id]["path"], binding["path"])
                    self.assertEqual(sources[source_id]["evidence_pointer"], binding["evidence_pointer"])
                    value = read(ROOT / binding["path"])
                    for token in binding["evidence_pointer"].strip("/").split("/"):
                        value = value[int(token)] if isinstance(value, list) else value[token]
                    self.assertEqual(value, source)

    def test_every_prior_csv_row_full_feature_source_and_acceptance_is_preserved(self):
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
        self.assertEqual(len(old_features), 167)
        self.assertEqual(len(new_features), 170)
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

    def test_eleven_artifact_byte_exact_rebuild_and_incomplete_final_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 170, "projects": 173, "evidence": 693, "countries": 42,
            "non_us_sites": 113, "official_boundary_projects": 5, "reviewed_site_locator_projects": 168,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 70, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 170, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 173, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 173)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-seventy-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
