"""61-addition checkpoint: one Monarch campus with an explicitly limited locator."""

from __future__ import annotations

from collections import Counter
import csv
import importlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from datacenter_atlas import expansion_200_sixteenth_reviewed as batch
from datacenter_atlas import expansion_200_fifteenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = SOURCES / "curated-official-2026-09-09-americas-round16-monarch-current-build.json"
GEOMETRY = SOURCES / "verified-construction-core-v0.18-americas-round16-monarch-geometry-proposal.json"
RESEARCH = SOURCES / "research-expansion-200-americas-round16-2026-09-09.json"
POINT = [-82.11110964992228, 38.91694204176893]
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class SixteenthReviewedDraftTests(unittest.TestCase):
    def test_physical_report_day_does_not_invent_inspection_day_or_clear_partial_stop(self) -> None:
        doc = read(CURATED)
        evidence, status = doc["evidence"][0], doc["lifecycle"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["kind"], "government_record")
        self.assertEqual(urlparse(evidence["source_url"]).hostname, "dep.wv.gov")
        self.assertEqual(evidence["published_at"], "2026-07-14")
        self.assertEqual(metadata["reported_inspection_interval"], ["2026-07-11", "2026-07-14"])
        self.assertIn("precise inspection day", metadata["observation_date_basis"])
        self.assertIn("not supplied", metadata["observation_date_basis"])
        self.assertIn("not an onset date", metadata["observation_date_basis"])
        self.assertIn("land-disturbing/site preparation work", metadata["selected_scope"])
        self.assertIn("no claimed hall erection", metadata["selected_scope"])
        self.assertIn("separate drainage area", metadata["unresolved_partial_stop"])
        self.assertIn("No release of that restriction was found", metadata["unresolved_partial_stop"])
        self.assertIn("does not order a whole-campus shutdown", metadata["unresolved_partial_stop"])
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-07-14")
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertEqual(status["evidence_key"], evidence["key"])
        self.assertGreaterEqual(status["as_of_date"], "2026-05-22")
        self.assertLessEqual(status["as_of_date"], "2026-08-20")
        self.assertNotEqual(status["as_of_date"], evidence["retrieved_at"][:10])

    def test_integrated_campus_identity_excludes_pipeline_and_conflicting_template(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        application, locator = geometry["evidence"][:2]
        operator, participant, successor, notice = geometry["evidence"][7:]
        self.assertIn("three data centers and their microgrid", application["excerpt"])
        self.assertEqual(application["metadata"]["visually_reviewed_pdf_pages"], [7, 93, 221])
        self.assertIn("1100-acre", application["excerpt"])
        self.assertIn("2250-acre", application["excerpt"])
        self.assertIn("not fresh physical work", application["metadata"]["publication_date_basis"])
        self.assertIn("not independent verification of land contiguity", application["metadata"]["identity_scope"])
        self.assertIn("no explicit datum", application["metadata"]["coordinate_exclusions"])
        self.assertIn("conflicting2027 dateline", application["metadata"]["coordinate_exclusions"])
        self.assertIn("not silently merged", application["metadata"]["coordinate_exclusions"])
        self.assertIn("Glomfjord AI Data Centre", operator["metadata"]["excluded_wrong_record"])
        self.assertIn("neither Monarch location nor status", operator["metadata"]["excluded_wrong_record"])
        self.assertIn("broader future scope", operator["metadata"]["scope_caveat"])
        self.assertIn("An MOU is not actual physical-work evidence", participant["metadata"]["source_scope"])
        self.assertEqual(notice["metadata"]["read_only_request_form_data"], "messageID=39742")
        self.assertIn("SUBJECT says Mason", notice["metadata"]["subject_caveat"])
        self.assertIn("TEXTBODY repeatedly says Monarch", notice["metadata"]["subject_caveat"])
        self.assertIn("not construction evidence", notice["metadata"]["source_scope"])
        association = geometry["campus_association"]
        self.assertIn("press release itself does not printWVR113311", association["analyst_reconciliation"])
        excluded = association["excluded_registry_record"]
        self.assertEqual(excluded["permit_id"], "WVR312628")
        self.assertEqual(excluded["fac_name"], "M2 Pipeline")
        self.assertNotEqual(excluded["coordinates"], POINT)
        self.assertIn("Same responsible party does not make it a campus locator", excluded["reason"])
        self.assertEqual(locator["metadata"]["selected_record"]["permit_id"], "WVR113311")
        self.assertIn("not three new sites", geometry["distinctness_review"]["identity_rule"])
        self.assertEqual(successor["metadata"]["review_cutoff"], "2026-08-20")
        self.assertIn("No resumption", successor["metadata"]["limitations"])
        self.assertIn("remains unresolved", geometry["successor_review"]["outcome"])
        self.assertIn("neither refreshes status", geometry["successor_review"]["post_cutoff_discovery_excluded"])
        self.assertEqual(doc["project"]["stable_key"], doc["campus"]["stable_key"] + ":current-site-preparation")

    def test_exact_official_point_projection_is_consistent_not_survey_accuracy(self) -> None:
        geometry = read(GEOMETRY)
        locator, native = geometry["evidence"][1:3]
        meta = locator["metadata"]
        selected = meta["selected_record"]
        self.assertEqual(meta["record_count"], 1)
        self.assertEqual(selected["objectid"], 74754)
        self.assertEqual(selected["fac_name"], "Power Generation Pad South")
        self.assertEqual(selected["resp_name"], "MONARCH CLOUD CAMPUS, LLC")
        self.assertEqual(meta["source_crs"], "EPSG:4326")
        self.assertEqual(meta["coordinate_order"], "longitude,latitude")
        self.assertEqual(meta["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertIn("do not copy rounded latitude/longitude attributes", meta["derivation"])
        query = parse_qs(urlparse(locator["source_url"]).query)
        self.assertEqual(query["where"], ["permit_id = 'WVR113311'"])
        self.assertEqual(query["outSR"], ["4326"])
        self.assertEqual(native["metadata"]["source_crs"], "EPSG:3857")
        x, y = native["metadata"]["native_coordinates_metres"]
        self.assertEqual([x, y], [-9140566.9147, 4709781.206200004])
        computed = [math.degrees(x / 6378137),
                    math.degrees(2 * math.atan(math.exp(y / 6378137)) - math.pi / 2)]
        for actual, expected in zip(computed, POINT, strict=True):
            self.assertAlmostEqual(actual, expected, places=12)
        transform = native["metadata"]["independent_transform"]
        self.assertTrue(transform["same_permit_and_object_id"])
        self.assertEqual(transform["source_wgs84"], POINT)
        self.assertLess(max(transform["absolute_difference_degrees"]), 1e-12)
        self.assertIn("not physical survey accuracy", native["metadata"]["interpretation"])
        result = geometry["results"][0]
        self.assertEqual(result["geometry"], meta["geometry"])
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_source_entity_kind"], "campus")
        self.assertEqual(semantics["geometry_scope_class"], "official_constituent_campus_reference_point")
        self.assertEqual(semantics["geometry_authority_class"], "official_source")
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("No source numerical positional accuracy", semantics["horizontal_uncertainty_unknown_reason"])
        for excluded_scope in ("data-center hall", "construction footprint", "campus centroid", "boundary"):
            self.assertIn(excluded_scope, semantics["precision_scope"])
        draft._geometry(result)

    def test_narrow_rights_and_no_roles_or_capacity_inflation_survive_export(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        curated._parse_document(CURATED, "2026-09-09T05:00:00Z")
        locator, rights, context = geometry["evidence"][1], geometry["evidence"][4], geometry["evidence"][5]
        self.assertEqual(locator["license"], "no-open-license-asserted")
        self.assertIsNone(rights["metadata"]["licenseInfo"])
        self.assertIsNone(rights["metadata"]["accessInformation"])
        self.assertIn("No affirmative open licence inferred", rights["metadata"]["rights_interpretation"])
        self.assertIn("not a substitute CC licence or blanket waiver", context["metadata"]["rights_interpretation"])
        self.assertEqual(locator["metadata"]["rights_url"], context["source_url"])
        self.assertEqual(locator["metadata"]["license_metadata_url"], rights["source_url"])
        self.assertIn("No open licence, public-domain status, bulk GIS reuse right", geometry["rights_scope"])
        self.assertIn("Raw bodies and rendered plans stay temporary", geometry["rights_scope"])
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["roles"], {})
            self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(doc[entity]["geometry"])
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(doc[field], [])
        self.assertEqual(len(doc["lifecycle"]), 1)
        self.assertEqual(len(geometry["results"]), 1)
        row = next(row for row in table(batch.draft_path(ROOT) / "projects.csv")
                   if row["project_stable_key"] == doc["project"]["stable_key"])
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(row[field]))
        for field in ("owner", "operator", "users", "tenants", "customers", "horizontal_uncertainty_metres"):
            self.assertEqual(row[field], "")
        self.assertEqual(row["operating_model"], "unknown")
        self.assertEqual(row["geometry_type"], "Point")
        self.assertEqual(row["status_as_of"], "2026-07-14")

    def test_one_new_campus_and_twelve_source_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 61)
        self.assertEqual(len(validated.sources), 373)
        doc, geometry = read(CURATED), read(GEOMETRY)
        self.assertEqual(len(doc["evidence"]), 1)
        self.assertEqual(len(geometry["evidence"]), 11)
        for evidence in doc["evidence"] + geometry["evidence"]:
            with self.subTest(evidence=evidence["key"]):
                self.assertRegex(evidence["content_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(evidence["metadata"]["content_hash_verification"], "fetched_bytes_sha256")
                self.assertGreater(evidence["metadata"]["raw_capture_bytes"], 0)
                self.assertFalse(evidence["metadata"]["request_credentials_supplied"])
                self.assertEqual(evidence["metadata"]["http_status"], 200)
                self.assertTrue(evidence["attribution"])
                self.assertTrue(evidence["metadata"]["rights_scope"])
        old_ids = {source["source_id"] for source in old["sources"]}
        sources = {source["source_id"]: source for source in new["sources"]}
        bindings = geometry["source_binding_map"]
        proposed_ids = {binding["source_id"] for binding in bindings}
        self.assertEqual(len(bindings), 12)
        self.assertEqual(len(proposed_ids), 12)
        self.assertEqual(set(sources) - old_ids, proposed_ids)
        for binding in bindings:
            source = sources[binding["source_id"]]
            self.assertEqual(source["path"], binding["path"])
            self.assertEqual(source["evidence_pointer"], binding["evidence_pointer"])
        used = set(geometry["results"][0]["geometry_source_ids"])
        used.update(geometry["results"][0]["identity_source_ids"])
        used.update(geometry["successor_review"]["sources"])
        self.assertEqual(used, proposed_ids)
        for field, entity in (("project_stable_key", "project"), ("parent_campus_stable_key", "campus")):
            new_keys = {acceptance[field] for acceptance in new["acceptances"]}
            old_keys = {acceptance[field] for acceptance in old["acceptances"]}
            self.assertEqual(new_keys - old_keys, {doc[entity]["stable_key"]})
        acceptance = next(a for a in new["acceptances"]
                          if a["project_stable_key"] == doc["project"]["stable_key"])
        self.assertEqual(acceptance["status"]["source_id"], doc["evidence"][0]["key"])
        self.assertEqual(acceptance["status"]["record_pointer"], "/lifecycle/0")

    def test_research_holds_and_unselected_documents_do_not_become_acceptances(self) -> None:
        research, contract = read(RESEARCH), read(batch.contract_path(ROOT))
        self.assertEqual(len(research["ready_proposals"]), 1)
        self.assertEqual(research["ready_proposals"][0]["campus_stable_key"], read(CURATED)["campus"]["stable_key"])
        campus_keys = {acceptance["parent_campus_stable_key"] for acceptance in contract["acceptances"]}
        for hold in research["holds"]:
            with self.subTest(campus=hold["campus_stable_key"]):
                self.assertNotIn(hold["campus_stable_key"], campus_keys)
        self.assertTrue(research["pdf_review"]["raw_media_temporary"])
        self.assertIn(216, research["pdf_review"]["full_pages_visually_reviewed"])
        self.assertIn("Neither is silently corrected or selected", research["pdf_review"]["known_document_defects"])
        selected = [capture for capture in research["capture_ledger"]
                    if capture["disposition"] == "selected_factual_source"]
        self.assertEqual(len(selected), 12)
        self.assertEqual(research["capture_verification"]["hash_byte_errors"], [])

    def test_every_previous_row_byte_feature_source_and_acceptance_is_preserved(self) -> None:
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
        self.assertEqual(len(old_features), 160)
        self.assertEqual(len(new_features), 161)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
        current = {acceptance["project_stable_key"]: acceptance for acceptance in new["acceptances"]}
        for acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, acceptance)

    def test_exact_eleven_artifact_rebuild_and_partial_release_gates(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 161, "projects": 164, "evidence": 609,
            "countries": 41, "non_us_sites": 107,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 159,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 61, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 161, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 164, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 164)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-one-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
