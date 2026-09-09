"""60-addition checkpoint: dated Lahti work and an exact official parcel join."""

from __future__ import annotations

from collections import Counter
import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse

from datacenter_atlas import expansion_200_fifteenth_reviewed as batch
from datacenter_atlas import expansion_200_fourteenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = SOURCES / "curated-official-2026-09-09-europe-round16-dayone-lahti-current-build.json"
GEOMETRY = SOURCES / "verified-construction-core-v0.18-europe-round16-dayone-lahti-geometry-proposal.json"
RESEARCH = SOURCES / "research-expansion-200-europe-round16-2026-09-09.json"
POINT = [25.703874164769484, 60.990755708567505]
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FifteenthReviewedDraftTests(unittest.TestCase):
    def test_august_work_uses_explicit_day_with_week_and_timestamp_caveats(self) -> None:
        doc = read(CURATED)
        evidence, status = doc["evidence"][0], doc["lifecycle"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(urlparse(evidence["source_url"]).hostname, "www.srv.fi")
        self.assertIn("2984-lahden-datakeskus/tiedotteet/", evidence["source_url"])
        self.assertEqual(evidence["published_at"], "2026-08-11T00:00:00Z")
        self.assertEqual(metadata["publication_date_literal"], "11.08.2026")
        self.assertEqual(metadata["date_precision"], "day")
        self.assertIn("canonical date placeholder", metadata["publication_timestamp_normalization"])
        self.assertEqual(metadata["visible_week_label"], "Viikko 32")
        self.assertIn("ISO week 33", metadata["week_label_caveat"])
        self.assertIn("earlier July 13/Viikko 22", metadata["week_label_caveat"])
        self.assertIn("no selected lifecycle", metadata["week_label_caveat"])
        self.assertIn("frame work approximately halfway", evidence["excerpt"])
        self.assertIn("not a normalized percentage", metadata["scope_guardrail"])
        self.assertIn("2027 operation are forecasts", metadata["scope_guardrail"])
        self.assertIn("bounded check, not proof of absence", metadata["successor_review"])
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-08-11")
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertEqual(status["evidence_key"], evidence["key"])
        self.assertGreaterEqual(status["as_of_date"], "2026-05-22")
        self.assertLessEqual(status["as_of_date"], "2026-08-20")
        self.assertNotEqual(status["as_of_date"], evidence["retrieved_at"][:10])

    def test_exact_city_permit_and_register_join_the_two_street_frontages(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        permit, register, city = geometry["evidence"][:3]
        address = doc["evidence"][1]
        self.assertIn("DayOne", address["excerpt"])
        self.assertIn("Ilmarisentie 3", address["excerpt"])
        self.assertIn("Helsinki corporate-office address", address["metadata"]["identity_scope"])
        self.assertEqual(permit["metadata"]["permit_identifier"], "398-2025-418")
        self.assertEqual(permit["metadata"]["parcel_identifier"], "398-5-966-7")
        self.assertEqual(permit["metadata"]["address_literal"], "Väinämöisentie 2a, 15200 LAHTI")
        self.assertEqual(permit["metadata"]["publication_date_literal"], "14.10.2025")
        self.assertEqual(register["metadata"]["permit_decision_date_literal"], "07.10.2025")
        self.assertEqual(register["metadata"]["register_date_literal"], "03.11.2025")
        self.assertEqual(permit["metadata"]["reviewed_pdf_pages"], [1, 6])
        self.assertEqual(register["metadata"]["reviewed_pdf_pages"], [5])
        for literal in ("2025-418", "398-5-966-7", "Ilmarisentie 3"):
            self.assertIn(literal, register["metadata"]["literal_pointer"])
        self.assertIn("not approximate road geocoding", register["metadata"]["identity_scope"])
        self.assertIn("DC-A", register["metadata"]["identity_scope"])
        self.assertIn("one campus", register["metadata"]["identity_scope"])
        self.assertIn("Ilmarisentie and Väinämöisentie", city["excerpt"])
        result = geometry["results"][0]
        for evidence in (address, permit, register, city):
            self.assertIn(evidence["key"], result["identity_source_ids"])
        for evidence in (permit, register, city):
            self.assertEqual(evidence["kind"], "government_record")
            self.assertNotEqual(evidence["key"], doc["lifecycle"][0]["evidence_key"])

    def test_nls_exact_reference_point_retains_crs_rights_and_unknown_accuracy(self) -> None:
        geometry = read(GEOMETRY)
        locator, service, policy = geometry["evidence"][3:]
        meta = locator["metadata"]
        self.assertEqual(meta["source_result_count"], 1)
        self.assertEqual(meta["source_feature_id"], "FI_CP_CADASTRALPARCEL_329674441")
        self.assertEqual(meta["parcel_identifier"], "398-5-966-7")
        self.assertEqual(meta["national_cadastral_reference"], "39800509660007")
        self.assertEqual(meta["source_reference_point"], [429880.746, 6762451.328])
        self.assertEqual((meta["source_crs"], meta["output_crs"]), ("EPSG:3067", "EPSG:4326"))
        self.assertEqual(meta["output_coordinate_order"], "longitude,latitude")
        self.assertEqual(meta["output_reference_point"], POINT)
        self.assertEqual(meta["transform_library"], "pyproj 3.8.0")
        self.assertIn("always_xy=True", meta["transform_request"])
        self.assertIn("Inverse of TM35FIN + EUREF-FIN to WGS 84 (1)", meta["transform_operation"])
        self.assertEqual(meta["transform_operation_accuracy_metres"], 1.0)
        self.assertIn("not measured cadastral-point accuracy", meta["accuracy_guardrail"])
        self.assertIn("No centroid is recomputed", meta["geometry_semantics"])
        self.assertIn("not construction dates", meta["temporal_guardrail"])
        self.assertEqual(locator["license"], "CC-BY-4.0")
        self.assertIn("INSPIRE Cadastral Parcels", locator["attribution"])
        self.assertIn("9 September 2026", locator["attribution"])
        self.assertIn("transformed from EPSG:3067 to EPSG:4326", locator["attribution"])
        self.assertIn(service["metadata"]["service_endpoint"], locator["source_url"])
        self.assertEqual(meta["rights_url"], policy["source_url"])
        self.assertEqual(meta["license_url"], policy["metadata"]["license_url"])
        self.assertIn("do not license SRV/city prose", meta["rights_scope"])
        result = geometry["results"][0]
        self.assertEqual(set(result["geometry_source_ids"]), {locator["key"], service["key"], policy["key"]})
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_authority_class"], "official_source")
        self.assertEqual(semantics["geometry_scope_class"], "official_parcel_reference_point")
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("do not establish survey accuracy", semantics["horizontal_uncertainty_unknown_reason"])
        draft._geometry(result)

    def test_old_keys_and_one_campus_scope_survive_without_roles_or_metrics(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        old = read(SOURCES / "curated-official-2026-07-19-dayone-kiverio-lahti.json")
        curated._parse_document(CURATED, "2026-09-09T05:00:00Z")
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["stable_key"], old[entity]["stable_key"])
            self.assertEqual(doc[entity]["name"], old[entity]["name"])
            self.assertEqual(doc[entity]["roles"], {})
            self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(doc[entity]["geometry"])
        for field in ("workloads", "capacities", "operating_models"):
            self.assertEqual(doc[field], [])
        self.assertEqual(len(doc["lifecycle"]), 1)
        self.assertEqual(len(geometry["results"]), 1)
        checks = geometry["independent_checks"]
        self.assertEqual(checks["baseline_sites_reviewed"], 159)
        self.assertTrue(checks["parcel_geometry_valid"])
        self.assertTrue(checks["reference_point_inside_parcel"])
        self.assertEqual(checks["parcel_ring_vertices_including_closure"], 153)
        self.assertEqual(checks["point_intersections_with_selected_features"], [])
        self.assertEqual(checks["parcel_intersections_with_selected_features"], [])
        self.assertIn("no mutual campus pair", checks["mutual_proposal_dedup"])
        self.assertIn("not this parcel", checks["alias_review"])
        precision = geometry["results"][0]["semantics"]["precision_scope"]
        self.assertIn("rejected road, wholesaler or service-area coordinates", precision)
        self.assertIn("Not a calculated centroid", precision)

    def test_one_new_campus_and_eight_auditable_source_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 60)
        self.assertEqual(len(validated.sources), 361)
        doc, geometry = read(CURATED), read(GEOMETRY)
        self.assertEqual(len(doc["evidence"]), 2)
        self.assertEqual(len(geometry["evidence"]), 6)
        for evidence in doc["evidence"] + geometry["evidence"]:
            with self.subTest(evidence=evidence["key"]):
                self.assertRegex(evidence["content_hash"], r"^[0-9a-f]{64}$")
                meta = evidence["metadata"]
                self.assertEqual(meta["content_hash_verification"], "fetched_bytes_sha256")
                self.assertGreater(meta["raw_capture_bytes"], 0)
                self.assertFalse(meta["request_credentials_supplied"])
                self.assertFalse(meta["raw_capture_redistributed"])
                self.assertEqual(meta["http_status"], 200)
                self.assertTrue(meta["rights_scope"])
        old_ids = {source["source_id"] for source in old["sources"]}
        sources = {source["source_id"]: source for source in new["sources"]}
        bindings = geometry["source_binding_map"]
        self.assertEqual(len(bindings), 8)
        self.assertEqual(len({b["source_id"] for b in bindings}), 8)
        self.assertEqual(set(sources) - old_ids, {b["source_id"] for b in bindings})
        for binding in bindings:
            source = sources[binding["source_id"]]
            self.assertEqual(source["path"], binding["path"])
            self.assertEqual(source["evidence_pointer"], binding["evidence_pointer"])
        for field, entity in (("project_stable_key", "project"), ("parent_campus_stable_key", "campus")):
            new_keys = {a[field] for a in new["acceptances"]}
            old_keys = {a[field] for a in old["acceptances"]}
            self.assertEqual(new_keys - old_keys, {doc[entity]["stable_key"]})
        acceptance = next(a for a in new["acceptances"]
                          if a["project_stable_key"] == doc["project"]["stable_key"])
        self.assertEqual(acceptance["status"]["source_id"], doc["evidence"][0]["key"])
        self.assertEqual(acceptance["status"]["record_pointer"], "/lifecycle/0")

    def test_round16_holds_supply_no_selected_lifecycle_or_borrowed_coordinates(self) -> None:
        research = read(RESEARCH)
        self.assertEqual(len(research["proposals"]), 1)
        self.assertEqual(research["proposals"][0]["new_selected_source_bindings"], 8)
        for hold in research["screened_holds"]:
            with self.subTest(name=hold["name"]):
                self.assertFalse(hold["selected_for_lifecycle"])
                self.assertIsNone(hold["coordinates"])
        selected = [capture for capture in research["raw_captures"] if capture["selected"]]
        self.assertEqual(len(selected), 8)
        self.assertTrue(all(capture["hash_verified"] for capture in selected))
        self.assertEqual(research["failed_request"]["http_status"], 404)
        self.assertFalse(research["failed_request"]["body_saved"])
        self.assertFalse(research["failed_request"]["retry_performed"])

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
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
        current = {a["project_stable_key"]: a for a in new["acceptances"]}
        for acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, acceptance)

    def test_exact_eleven_artifact_rebuild_and_partial_release_gates(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 160, "projects": 163, "evidence": 597,
            "countries": 41, "non_us_sites": 107,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 158,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 60, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 160, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 163, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 163)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
