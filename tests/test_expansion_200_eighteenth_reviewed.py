"""63-addition checkpoint: Conesville pad work and an official parcel locator."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from datacenter_atlas import expansion_200_eighteenth_reviewed as batch
from datacenter_atlas import expansion_200_seventeenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = SOURCES / "curated-official-2026-09-09-americas-round20-conesville-july-pad-work.json"
GEOMETRY = SOURCES / "verified-construction-core-v0.18-americas-round20-conesville-geometry-proposal.json"
RESEARCH = SOURCES / "research-expansion-200-americas-round20-conesville-2026-09-09.json"
CAMPUS = "curated:aligned-conesville-cmh02-campus"
PROJECT = CAMPUS + ":current-site-preparation"
POINT = [-81.87484638244284, 40.18252252973112]
NATIVE_POINT = [2143186.248523869, 188568.9888619395]
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def evidence_by_key() -> dict[str, dict]:
    return {item["key"]: item for item in read(CURATED)["evidence"] + read(GEOMETRY)["evidence"]}


class EighteenthReviewedDraftTests(unittest.TestCase):
    def test_july_interval_dates_site_preparation_not_campus_completion(self) -> None:
        doc, research = read(CURATED), read(RESEARCH)
        self.assertEqual(len(doc["evidence"]), 1)
        evidence = doc["evidence"][0]
        meta = evidence["metadata"]
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(urlparse(evidence["source_url"]).hostname, "ccucoal.com")
        self.assertEqual(evidence["published_at"], "2026-06-08")
        self.assertEqual(meta["source_published_time"], "2026-06-08T02:04:27+00:00")
        self.assertEqual(meta["source_modified_time"], "2026-08-24T02:11:16+00:00")
        self.assertEqual(meta["status_date_precision"], "month")
        self.assertEqual(meta["source_observation_month"], "2026-07")
        self.assertEqual(meta["source_observation_interval"], ["2026-07-01", "2026-07-31"])
        self.assertGreaterEqual(meta["source_observation_interval"][0], "2026-05-22")
        self.assertLessEqual(meta["source_observation_interval"][1], "2026-08-20")
        self.assertTrue(meta["lifecycle_selected"])
        self.assertIn("not an asserted exact", meta["status_as_of_normalization"])
        self.assertIn("not completion or operation", meta["scope_guardrail"])
        self.assertEqual(len(doc["lifecycle"]), 1)
        status = doc["lifecycle"][0]
        self.assertEqual(status["value"], "site_preparation")
        self.assertEqual(status["as_of_date"], "2026-07-01")
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertEqual(status["evidence_key"], evidence["key"])
        for other_date in (evidence["published_at"], evidence["retrieved_at"][:10],
                           meta["source_modified_time"][:10]):
            self.assertNotEqual(status["as_of_date"], other_date)
        self.assertFalse(research["candidate"]["normalized_date_is_exact_day"])
        self.assertEqual(research["candidate"]["normalized_as_of_date"], status["as_of_date"])
        self.assertEqual(doc["campus"]["stable_key"], CAMPUS)
        self.assertEqual(doc["project"]["stable_key"], PROJECT)

    def test_explicit_county_datum_operation_and_exact_constituent_point(self) -> None:
        evidence, geometry = evidence_by_key(), read(GEOMETRY)
        point = evidence["am20-conesville-county-centroid"]
        native = evidence["am20-conesville-county-native-centroid"]["metadata"]
        query = parse_qs(urlparse(point["source_url"]).query)
        self.assertEqual(query["objectIds"], ["27692"])
        self.assertEqual(query["returnGeometry"], ["false"])
        self.assertEqual(query["returnCentroid"], ["true"])
        self.assertEqual(query["outSR"], ["4326"])
        self.assertEqual(query["datumTransformation"], ["1188"])
        self.assertEqual(point["metadata"]["query_parameters"], {
            "objectIds": "27692", "returnGeometry": False, "returnCentroid": True,
            "outSR": 4326, "datumTransformation": 1188,
        })
        self.assertEqual([point["metadata"]["selected_longitude"],
                          point["metadata"]["selected_latitude"]], POINT)
        self.assertEqual(native["native_centroid"], NATIVE_POINT)
        self.assertIn("EPSG:3734", native["native_crs"])
        self.assertIn("EPSG:4326", point["metadata"]["source_crs"])
        conversion = native["independent_conversion"]
        self.assertEqual(conversion["result"], [-81.87484638244284, 40.18252253066136])
        self.assertGreater(conversion["difference_from_selected_point_metres"], 0)
        self.assertLess(conversion["difference_from_selected_point_metres"], 0.001)
        self.assertEqual(conversion["operation_accuracy_metres_not_source_position_accuracy"], 4)
        self.assertEqual(len(geometry["results"]), 1)
        result = geometry["results"][0]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_parcel")
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_authority_class"], "official_source")
        self.assertEqual(semantics["geometry_scope_class"], "official_constituent_parcel_reference_point")
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertTrue(semantics["horizontal_uncertainty_unknown_reason"])
        self.assertIn("not a whole-campus centroid", semantics["precision_scope"])
        self.assertIn("not source feature accuracy", semantics["horizontal_uncertainty_unknown_reason"])
        draft._geometry(result)

    def test_parcel_identity_and_public_rights_are_separate_from_status(self) -> None:
        evidence, geometry = evidence_by_key(), read(GEOMETRY)
        identity = evidence["am20-conesville-county-parcel-identity"]
        self.assertEqual(identity["kind"], "government_record")
        self.assertEqual(identity["metadata"]["meeting_date"], "2026-07-15")
        self.assertEqual(identity["metadata"]["parcel_id_literal"], "010-00000806-09")
        self.assertIn("0100000080609", identity["metadata"]["parcel_query_normalization"])
        self.assertIn("July 16", identity["metadata"]["date_caveat"])
        self.assertFalse(identity["metadata"]["lifecycle_selected"])
        self.assertTrue(geometry["campus_association"]["no_new_site_for_phases"])
        self.assertTrue(geometry["campus_association"]["analyst_reconciliation"])
        rights = evidence["am20-conesville-county-rights"]
        self.assertEqual(rights["license"], "no-open-license-asserted")
        self.assertEqual(rights["metadata"]["license_info_literal"], "")
        self.assertEqual(rights["metadata"]["access_literal"], "public")
        self.assertIn("not grant an open licence", rights["excerpt"])
        self.assertIn("No source polygon", rights["metadata"]["rights_scope"])
        for item in geometry["evidence"]:
            self.assertFalse(item["metadata"]["lifecycle_selected"])
            self.assertFalse(item["metadata"]["raw_capture_redistributed"])
            self.assertEqual(item["license"], "no-open-license-asserted")
        locator_sources = set(geometry["results"][0]["geometry_source_ids"])
        for suffix in ("public-gis", "viewer-config", "webmap", "layer", "rights"):
            self.assertIn("am20-conesville-county-" + suffix, locator_sources)

    def test_conflicting_operator_marker_and_completion_forecasts_are_excluded(self) -> None:
        geometry, research = read(GEOMETRY), read(RESEARCH)
        rejected = research["locator_review"]["rejected_locators"]
        marker = next(item for item in rejected if "literal_operator_point" in item)
        self.assertEqual(marker["literal_record_id"], 8648)
        self.assertEqual(marker["literal_operator_point"], [-81.88217927286354, 40.18504161834269])
        self.assertNotEqual(marker["literal_operator_point"], POINT)
        stored_fields = next(item for item in rejected if "values_for_oid27692" in item)
        self.assertEqual(stored_fields["values_for_oid27692"], [40.17677303, -81.86627277])
        self.assertTrue(geometry["successor_review"]["no_ongoing_august_claim"])
        self.assertEqual(geometry["successor_review"]["reference_cutoff"], "2026-08-20")
        self.assertIn("forecast", geometry["successor_review"]["finding"])
        self.assertTrue(research["successor_review"]["no_exhaustive_negative_claim"])
        self.assertEqual(geometry["distinctness_review"]["sites_compared"], 162)
        self.assertEqual(geometry["distinctness_review"]["full_geometry_collisions"], [])
        self.assertEqual(geometry["distinctness_review"]["matched_selected_campuses"], [])
        rows = table(batch.draft_path(ROOT) / "projects.csv")
        additions = [row for row in rows if row["physical_site_stable_key"] == CAMPUS]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["project_stable_key"], PROJECT)
        self.assertEqual(additions[0]["status_as_of"], "2026-07-01")
        self.assertEqual(additions[0]["last_observed_physical_status"], "site_preparation")
        for row in rows:
            key = row["physical_site_stable_key"]
            self.assertNotIn("railtel-techno-noida", key)
            self.assertNotIn("techno-digital-kolkata", key)

    def test_no_roles_capacity_workload_or_imagery_inferred(self) -> None:
        doc = read(CURATED)
        curated._parse_document(CURATED, "2026-09-09T07:00:00Z")
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["roles"], {})
            self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(doc[entity]["geometry"])
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(doc[field], [])
        row = next(row for row in table(batch.draft_path(ROOT) / "projects.csv")
                   if row["project_stable_key"] == PROJECT)
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(row[field]))
        for field in ("owner", "operator", "users", "tenants", "customers", "horizontal_uncertainty_metres"):
            self.assertEqual(row[field], "")
        self.assertEqual(row["operating_model"], "unknown")

    def test_one_acceptance_and_eleven_source_bindings_close_exactly(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 63)
        self.assertEqual(len(validated.sources), 393)
        geometry, research = read(GEOMETRY), read(RESEARCH)
        evidence = evidence_by_key()
        self.assertEqual(len(evidence), 11)
        self.assertEqual(research["selected_source_closure"]["binding_count"], 11)
        bindings = {binding["source_id"]: binding for binding in geometry["source_binding_map"]}
        sources = {source["source_id"]: source for source in new["sources"]}
        old_ids = {source["source_id"] for source in old["sources"]}
        self.assertEqual(set(sources) - old_ids, set(evidence))
        self.assertEqual(set(bindings), set(evidence))
        for key, item in evidence.items():
            with self.subTest(source=key):
                self.assertRegex(item["content_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(item["metadata"]["content_hash_verification"], "fetched_bytes_sha256")
                self.assertGreater(item["metadata"]["raw_capture_bytes"], 0)
                self.assertEqual(item["metadata"]["http_status"], 200)
                self.assertFalse(item["metadata"]["request_credentials_supplied"])
                self.assertTrue(item["attribution"])
                self.assertTrue(item["metadata"]["rights_scope"])
                self.assertEqual(sources[key]["path"], bindings[key]["path"])
                self.assertEqual(sources[key]["evidence_pointer"], bindings[key]["evidence_pointer"])
                pointed = read(ROOT / bindings[key]["path"])
                for part in bindings[key]["evidence_pointer"].split("/")[1:]:
                    pointed = pointed[int(part)] if isinstance(pointed, list) else pointed[part]
                self.assertEqual(pointed, item)
                draft._source_evidence(item, key)
        result = geometry["results"][0]
        self.assertEqual(set(result["geometry_source_ids"] + result["identity_source_ids"]), set(evidence))
        old_projects = {item["project_stable_key"] for item in old["acceptances"]}
        additions = [item for item in new["acceptances"] if item["project_stable_key"] not in old_projects]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["project_stable_key"], PROJECT)
        self.assertEqual(additions[0]["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(additions[0]["status"]["source_id"], "am20-conesville-july-pad-work")
        self.assertEqual(additions[0]["status"]["record_pointer"], "/lifecycle/0")
        self.assertEqual(set(additions[0]["distinctness_review"]["evidence_source_ids"]), set(evidence))

    def test_all_predecessor_rows_features_source_bytes_and_acceptances_are_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            old_path, new_path = old_dir / filename, new_dir / filename
            current = {row[key]: row for row in table(new_path)}
            for row in table(old_path):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(Counter(old_path.read_bytes().splitlines(keepends=True)),
                                 Counter(new_path.read_bytes().splitlines(keepends=True)))
        old_features = read(old_dir / "sites.geojson")["features"]
        new_features = read(new_dir / "sites.geojson")["features"]
        self.assertEqual(len(old_features), 162)
        self.assertEqual(len(new_features), 163)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
            raw = (ROOT / source["path"]).read_bytes()
            self.assertEqual(len(raw), source["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
            self.assertEqual(batch.REVIEW_PINS.source_sha256[source["source_id"]],
                             previous.REVIEW_PINS.source_sha256[source["source_id"]])
        current = {item["project_stable_key"]: item for item in new["acceptances"]}
        for acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, acceptance)

    def test_exact_eleven_artifact_rebuild_and_partial_release_gates(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 163, "projects": 166, "evidence": 629,
            "countries": 42, "non_us_sites": 108,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 161,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 63, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 163, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 166, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 166)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-three-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
