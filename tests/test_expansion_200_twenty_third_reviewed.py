"""DigiCo preparatory works add one campus without rewriting the predecessor."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_second_reviewed as previous
from datacenter_atlas import expansion_200_twenty_third_reviewed as batch
from datacenter_atlas import verified_construction_core as baseline
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = "curated-official-2026-09-09-asia-round25-digico-syd1-early-works.json"
GEOMETRY = "verified-construction-core-v0.18-asia-round25-digico-syd1-geometry-proposal.json"
CAMPUS = "curated:digico-syd1-ultimo-campus"
PROJECT = CAMPUS + ":current-site-preparation"
STATUS_SOURCE = "asia25-shape-aug19-syd1-early-works"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def packets():
    return read(SOURCES / CURATED), read(SOURCES / GEOMETRY)


def evidence():
    return {row["key"]: row for document in packets() for row in document["evidence"]}


class TwentyThirdReviewedDraftTests(unittest.TestCase):
    def test_only_public_preview_statement_and_issuer_ceo_authority_are_selected(self):
        by_key = evidence()
        status = by_key[STATUS_SOURCE]
        metadata = status["metadata"]
        self.assertEqual(status["content_hash"],
                         "f41cef1aee614f10e056d3246e532bf2593428221148e0a23a74d5bb93bae197")
        self.assertEqual(metadata["raw_capture_bytes"], 102335)
        self.assertIn("Public preview segments #1-31 only", metadata["literal_pointer"])
        self.assertIn("Public #4 and #10", metadata["literal_pointer"])
        self.assertIn("public #24-27", metadata["literal_pointer"])
        self.assertIn("Hidden/gated #32-62 are excluded and not relied upon", metadata["literal_pointer"])
        self.assertNotIn("#51", metadata["literal_pointer"])
        self.assertNotIn("#52", metadata["literal_pointer"])
        self.assertIn("Only rendered public segments #1-31 selected", metadata["public_preview_scope"])
        self.assertIn("hidden/gated #32-62 excluded", metadata["public_preview_scope"])
        self.assertIn("No audio, original full-call replay or complete-call verification is claimed",
                      metadata["public_preview_scope"])
        self.assertEqual(metadata["literal_byte_pointers"][0], {
            "offset": 64080, "length": 42,
            "literal": "already doing early works there to prepare",
        })
        authority = by_key[metadata["authority_evidence_dependency"]]
        self.assertEqual(authority["key"], "asia25-shape-ceo-issuer-authority")
        self.assertEqual(authority["publisher"], "SHAPE Australia Corporation Limited")
        self.assertEqual(authority["source_family"], "shape_official_results")
        self.assertEqual(authority["metadata"]["document_date"], "2026-08-19")
        self.assertEqual(authority["metadata"]["visual_review_pages"], [6])
        self.assertEqual(authority["metadata"]["use_scope"], "speaker_role_authority_only")
        self.assertIn("Peter Marix-Evans, Chief Executive Officer and Managing Director",
                      authority["metadata"]["literal_pointer"])
        self.assertIn("registered office is not used", authority["metadata"]["excluded_locator"])

    def test_contractor_observation_date_is_not_period_end_or_later_operator_report(self):
        doc, _ = packets()
        source = evidence()[STATUS_SOURCE]
        metadata = source["metadata"]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(source["source_family"], "shape_executive_statement_third_party_transcription")
        self.assertIn("EarningsAPI", source["publisher"])
        self.assertIn("Peter Marix-Evans", source["publisher"])
        self.assertIsNone(source["published_at"])
        self.assertTrue(metadata["published_date_unknown"])
        self.assertEqual(metadata["observed_on"], "2026-08-19")
        self.assertEqual(metadata["event_date"], "2026-08-19")
        self.assertEqual(metadata["status_date_precision"], "day")
        self.assertEqual(metadata["reporting_period_end"], "2026-06-30")
        self.assertEqual(metadata["status_observation_basis"],
                         "dated_first_person_contractor_statement_reproduced_by_transcript_publisher")
        self.assertIn("not been audio-verified", metadata["authority_scope"])
        self.assertIn("not an inferred inspection", metadata["date_scope"])
        self.assertEqual(doc["lifecycle"], [{
            "entity": "project", "value": "site_preparation", "evidence_key": STATUS_SOURCE,
            "as_of_date": "2026-08-19", "method": "authoritative_physical_status_update",
            "confidence": 0.93,
        }])

    def test_completed_first_stage_and_eci_are_not_selected_as_main_construction(self):
        by_key = evidence()
        status = by_key[STATUS_SOURCE]["metadata"]
        self.assertIn("site_preparation", status["physical_scope"])
        self.assertIn("No installed MW", status["physical_scope"])
        self.assertIn("Completed 20 MW phase is explicitly excluded", status["successor_scope"])
        identity = by_key["asia25-shape-syd1-project-identity"]["metadata"]
        self.assertEqual(identity["document_date"], "2026-08-19")
        self.assertEqual(identity["use_scope"], "contractor_project_identity_and_phase_separation_only")
        self.assertEqual(identity["visual_review_pages"], [18, 25])
        self.assertIn("currently ECI", identity["literal_pointer"])
        self.assertIn("belongs to IRT, not DigiCo", identity["physical_status_exclusion"])
        self.assertIn("do not date present construction", identity["physical_status_exclusion"])
        successor = by_key["asia25-digico-aug21-phase-successor-context"]["metadata"]
        self.assertEqual(successor["document_date"], "2026-08-21")
        self.assertFalse(successor["lifecycle_evidence_selected"])
        self.assertEqual(successor["use_scope"], "post_cutoff_phase_separation_and_successor_context_only")
        self.assertIn("not inferred to August20 or June30", successor["date_scope"])
        self.assertIn("no capacity", successor["metric_guardrail"])

    def test_exact_government_point_preserves_coarse_precision_and_unknown_accuracy(self):
        _, geometry = packets()
        result = geometry["results"][0]
        core._geometry(result)
        self.assertEqual(result["project_stable_key"], PROJECT)
        self.assertEqual(result["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": [151.197, -33.875]})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        source = evidence()["asia25-digico-syd1-nsw-project-point"]
        self.assertEqual(source["kind"], "government_record")
        self.assertEqual(source["publisher"], "NSW Department of Planning, Housing and Infrastructure")
        point = source["metadata"]
        self.assertEqual(point["source_geojson_geometry"], result["geometry"])
        self.assertEqual(point["government_entity_id"], "75575896")
        self.assertEqual(point["application_number"], "SSD-69637456")
        self.assertEqual(point["source_crs"], "EPSG:4326")
        self.assertEqual(point["source_literal_coordinate_tokens"], ["151.197", "-33.875"])
        self.assertEqual(point["source_coordinate_decimal_places"], 3)
        self.assertIsNone(point["source_accuracy_metres"])
        self.assertIn("not an independently surveyed datum", point["source_crs_scope"])
        self.assertIn("Default map_center", point["excluded_coordinates"])
        self.assertIn("not selected", point["excluded_coordinates"])
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertEqual(semantics["geometry_authority_class"], "official_source")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("outside building footprints", semantics["precision_scope"])
        self.assertIn("not a surveyed point", semantics["precision_scope"])
        self.assertIn("Decimal resolution is not measured positional accuracy",
                      semantics["horizontal_uncertainty_unknown_reason"])

    def test_locator_rights_do_not_relicense_applicant_material_or_google_maps(self):
        by_key = evidence()
        point = by_key["asia25-digico-syd1-nsw-project-point"]
        rights = by_key["asia25-nsw-planning-rights"]
        self.assertEqual(point["license"], "CC-BY-4.0-Department-material-scope")
        self.assertEqual(rights["license"], point["license"])
        self.assertEqual(point["metadata"]["rights_evidence_dependency"], rights["key"])
        self.assertEqual(point["metadata"]["crs_evidence_dependency"], "asia25-google-geographic-crs")
        self.assertIn("Applicant plans", point["metadata"]["rights_scope"])
        self.assertIn("Google basemap data", point["metadata"]["rights_scope"])
        self.assertIn("No applicant/third-party document", rights["metadata"]["rights_scope"])
        crs = by_key["asia25-google-geographic-crs"]
        self.assertEqual(crs["license"], "CC-BY-4.0")
        self.assertEqual(crs["metadata"]["use_scope"], "coordinate_system_semantics_only")
        self.assertIn("no map content", crs["metadata"]["rights_scope"])
        transcript_rights = by_key["asia25-earningsapi-rights"]
        self.assertEqual(transcript_rights["license"], "all-rights-reserved")
        self.assertIn("not an open-data licence", transcript_rights["metadata"]["rights_assessment"])
        self.assertEqual(by_key[STATUS_SOURCE]["metadata"]["rights_evidence_dependency"],
                         transcript_rights["key"])

    def test_one_ultimo_campus_not_other_syd1_codes_has_no_new_roles_metrics_or_imagery(self):
        doc, geometry = packets()
        parser = importlib.import_module(f"{baseline.__package__}.curated_v11")
        parser._parse_document(SOURCES / CURATED, max(row["retrieved_at"] for row in doc["evidence"]))
        self.assertEqual(doc["campus"]["stable_key"], CAMPUS)
        self.assertEqual(doc["project"]["stable_key"], PROJECT)
        for key in ("campus", "project"):
            self.assertEqual(doc[key]["roles"], {})
            self.assertIsNone(doc[key]["coordinates"])
            self.assertIsNone(doc[key]["geometry"])
        for key in ("operating_models", "workloads", "capacities"):
            self.assertEqual(doc[key], [])
        distinctness = geometry["distinctness_review"]
        self.assertEqual(distinctness["physical_sites"], 170)
        self.assertEqual(distinctness["projects"], 173)
        self.assertEqual(distinctness["alias_matches"], [])
        self.assertEqual(distinctness["geometry_types"], {"Point": 126, "Polygon": 42, "MultiPolygon": 2})
        self.assertIn("Sydney East/SYD1E and Sydney West/SYD1W", distinctness["campus_grouping"])
        self.assertIn("GreenSquare SYD1 Norwest", distinctness["campus_grouping"])
        self.assertIn("not merged by code alone", distinctness["campus_grouping"])
        self.assertEqual(evidence()["asia25-dem-syd1-address-campus-identity"]["metadata"]
                         ["exact_address_as_published"], "400 Harris Street, Ultimo")
        rows = [row for row in table(batch.draft_path(ROOT) / "projects.csv")
                if row["physical_site_stable_key"] == CAMPUS]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["project_stable_key"], PROJECT)
        self.assertEqual(row["last_observed_physical_status"], "site_preparation")
        self.assertEqual(row["status_as_of"], "2026-08-19")
        self.assertEqual(json.loads(row["geometry_json"]), geometry["results"][0]["geometry"])
        self.assertEqual(row["horizontal_uncertainty_metres"], "")
        self.assertEqual(row["operating_model"], "unknown")
        self.assertEqual(row["independent_imagery_verification"], "false")
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(row[field]))
        for field in ("owner", "operator", "users", "tenants", "customers"):
            self.assertEqual(row[field], "")
        site = next(row for row in table(batch.draft_path(ROOT) / "sites.csv")
                    if row["physical_site_stable_key"] == CAMPUS)
        self.assertEqual(site["project_count"], "1")

    def test_eleven_new_source_bindings_are_closed_without_reading_temporary_files(self):
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 71)
        by_key = evidence()
        self.assertEqual(len(by_key), 11)
        sources = {row["source_id"]: row for row in new["sources"]}
        self.assertEqual(len(validated.sources), 468)
        self.assertEqual(len(validated.sources), len(old["sources"]) + len(by_key))
        self.assertEqual(set(sources) - {row["source_id"] for row in old["sources"]}, set(by_key))
        _, geometry = packets()
        bindings = geometry["source_binding_map"]
        self.assertEqual(len(bindings), len(by_key))
        self.assertEqual({row["source_id"] for row in bindings}, set(by_key))
        result = geometry["results"][0]
        self.assertLessEqual(set(result["geometry_source_ids"] + result["identity_source_ids"]), set(by_key))
        acceptance = next(row for row in new["acceptances"] if row["project_stable_key"] == PROJECT)
        self.assertEqual(set(acceptance["distinctness_review"]["evidence_source_ids"]), set(by_key))
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
        self.assertEqual(len(old_features), 170)
        self.assertEqual(len(new_features), 171)
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
        self.assertEqual(old_counts["evidence"] + len(evidence()), 704)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 171, "projects": 174, "evidence": 704,
            "countries": 42, "non_us_sites": 114, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 169,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 71, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 171, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 174, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 174)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-seventy-one-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
