"""50-addition checkpoint: source-bound locators and physical-phase guardrails."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_tenth_reviewed as batch
from datacenter_atlas import expansion_200_ninth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
PORTUS = SOURCES / "verified-construction-core-v0.18-europe-mena-round10-portus-muc2-proposed-geometry.json"
META = SOURCES / "verified-construction-core-v0.18-meta-round10-reviewed-geometry.json"
ETOBICOKE = SOURCES / "verified-construction-core-v0.18-americas-round10-etobicoke-geometry-proposal.json"
GEOMETRY_PACKAGES = (PORTUS, META, ETOBICOKE)
CURATED_NAMES = {
    "europe-mena-round10-portus-muc2-current-build": "2026-05-28",
    "meta-el-paso-july28-current-build": "2026-07-28",
    "meta-richland-july16-current-build": "2026-07-16",
    "americas-round10-etobicoke-current-build": "2026-08-05",
}
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def curated_path(name: str) -> Path:
    return SOURCES / f"curated-official-2026-09-08-{name}.json"


def evidence_by_key(doc: dict) -> dict[str, dict]:
    return {row["key"]: row for row in doc["evidence"]}


class TenthReviewedDraftTests(unittest.TestCase):
    def test_four_packages_keep_physical_dates_and_unknown_fields(self) -> None:
        for name, day in CURATED_NAMES.items():
            with self.subTest(name=name):
                path = curated_path(name)
                doc = read(path)
                curated._parse_document(path, "2026-09-09T00:00:00Z")
                self.assertEqual(len(doc["lifecycle"]), 1)
                status = doc["lifecycle"][0]
                self.assertEqual(status["as_of_date"], day)
                self.assertEqual(status["value"], "under_construction")
                self.assertEqual(status["evidence_key"], doc["evidence"][0]["key"])
                self.assertEqual(doc["evidence"][0]["published_at"][:10], day)
                self.assertNotEqual(day, doc["evidence"][0]["retrieved_at"][:10])
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("workloads", "capacities", "operating_models"):
                    self.assertEqual(doc[field], [])

    def test_thirty_one_new_bindings_are_closed_and_point_scopes_remain_explicit(self) -> None:
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 50)
        self.assertEqual(len(validated.sources), 274)
        contract_sources = {source["source_id"]: source
                            for source in read(batch.contract_path(ROOT))["sources"]}
        previous_ids = {source["source_id"]
                        for source in read(previous.contract_path(ROOT))["sources"]}
        bindings = [binding for path in GEOMETRY_PACKAGES
                    for binding in read(path)["source_binding_map"]]
        binding_ids = {binding["source_id"] for binding in bindings}
        self.assertEqual(len(bindings), 31)
        self.assertEqual(len(binding_ids), 31)
        self.assertEqual(set(contract_sources) - previous_ids, binding_ids)
        for binding in bindings:
            source = contract_sources[binding["source_id"]]
            self.assertEqual(source["path"], binding["path"])
            self.assertEqual(source["evidence_pointer"], binding["evidence_pointer"])
        new_keys = {read(curated_path(name))["project"]["stable_key"] for name in CURATED_NAMES}
        rows = [row for row in validated.acceptances
                if row["acceptance"]["project_stable_key"] in new_keys]
        self.assertEqual(len(rows), 4)
        for row in rows:
            acceptance, geometry = row["acceptance"], row["geometry"]
            self.assertIn(acceptance["identity"]["source_id"], geometry["identity_source_ids"])
            self.assertEqual(geometry["geometry"]["type"], "Point")
            self.assertEqual(geometry["display_anchor"], geometry["geometry"])
            semantics = geometry["semantics"]
            official = "etobicoke" in acceptance["project_stable_key"]
            self.assertEqual(semantics["geometry_source_entity_kind"],
                             "project" if official else "campus")
            self.assertEqual(semantics["geometry_authority_class"],
                             "official_source" if official else "community_source")
            self.assertEqual(semantics["geometry_use_scope"],
                             "project_locator" if official else "campus_locator")
            self.assertIsNone(semantics["horizontal_uncertainty_metres"])
            self.assertTrue(semantics["horizontal_uncertainty_unknown_reason"])
            draft._geometry(geometry)

    def test_community_points_preserve_source_coordinates_without_precision_inference(self) -> None:
        portus, meta = read(PORTUS), read(META)
        expected = [
            (portus["results"][0], portus["evidence"][0], [11.7688419, 48.1585332], "source_point"),
            (meta["results"][0], meta["evidence"][0], [-106.3631625, 31.9940441],
             "source_coordinate_values_longitude_latitude"),
            (meta["results"][1], meta["evidence"][2], [-91.6360844, 32.5289242],
             "source_coordinate_values_longitude_latitude"),
        ]
        for result, source, point, field in expected:
            with self.subTest(key=result["project_stable_key"]):
                self.assertEqual(result["geometry"]["coordinates"], point)
                self.assertEqual(source["metadata"][field], point)
                self.assertEqual(source["license"], "ODbL-1.0")
                self.assertIn("OpenStreetMap", source["attribution"])
                self.assertEqual(source["metadata"]["rights_url"],
                                 "https://www.openstreetmap.org/copyright")
                self.assertEqual(result["location_basis"], "community_named_site_feature")
                self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        for result, source in ((meta["results"][0], meta["evidence"][0]),
                               (meta["results"][1], meta["evidence"][2])):
            metadata = source["metadata"]
            self.assertEqual(result["geometry"]["coordinates"],
                             [float(metadata["literal_longitude"]),
                              float(metadata["literal_latitude"])])

    def test_el_paso_approximate_campus_and_registration_date_are_not_overstated(self) -> None:
        geometry = read(META)
        source = geometry["evidence"][1]
        self.assertEqual(source["metadata"]["object_id"], 1547686701)
        self.assertEqual(source["metadata"]["selected_tags"]["note"],
                         "boundary very approximate")
        self.assertEqual(source["metadata"]["source_ring_count"], 1)
        scope = geometry["results"][0]["semantics"]["precision_scope"]
        self.assertIn("boundary very approximate", scope)
        self.assertIn("cross-state northern edge", scope)
        self.assertIn("neither the rectangle nor", scope)
        self.assertIn("is selected as a legal boundary", scope)
        source = read(curated_path("meta-el-paso-july28-current-build"))
        registry = evidence_by_key(source)["meta10-elpaso-tdlr-identity"]
        self.assertIsNone(registry["published_at"])
        self.assertEqual(registry["metadata"]["registration_date"], "2026-04-15")
        self.assertIn("not publication", registry["metadata"]["registration_date_semantics"])
        self.assertIn("regulatory review, not physical", registry["metadata"]["identity_scope"])
        self.assertEqual(source["lifecycle"][0]["as_of_date"], "2026-07-28")
        self.assertIn("not the joint venture", source["evidence"][0]["metadata"]
                      ["physical_status_guardrail"])

    def test_richland_whole_campus_point_does_not_select_phase_two_buildings(self) -> None:
        geometry = read(META)
        source = geometry["evidence"][3]
        self.assertEqual(source["metadata"]["object_id"], 19710316)
        self.assertEqual(source["metadata"]["source_ring_count"], 3)
        self.assertEqual(source["metadata"]["selected_tags"]["website"],
                         "https://datacenters.atmeta.com/richland-parish-data-center/")
        scope = geometry["results"][1]["semantics"]["precision_scope"]
        self.assertIn("northern component", scope)
        self.assertIn("not a particular first building", scope)
        self.assertIn("Phase 2 construction", scope)
        doc = read(curated_path("meta-richland-july16-current-build"))
        evidence = evidence_by_key(doc)
        self.assertIn("No Phase 2 building construction", evidence["meta10-richland-current-status"]
                      ["metadata"]["physical_status_guardrail"])
        phase = evidence["meta10-richland-phase-scope"]
        self.assertIsNone(phase["published_at"])
        self.assertIn("June 2027", phase["excerpt"])
        self.assertIn("not a fresh lifecycle observation", phase["metadata"]["identity_scope"])
        self.assertEqual(doc["project"]["stable_key"],
                         "curated:meta-richland-parish-data-center:current-development")

    def test_portus_exact_certificate_address_excludes_operator_pin_and_muc1_status(self) -> None:
        doc = read(curated_path("europe-mena-round10-portus-muc2-current-build"))
        evidence = evidence_by_key(doc)
        certificate = evidence["europe10-portus-muc1-certified-site-address"]
        self.assertIsNone(certificate["published_at"])
        self.assertEqual(certificate["metadata"]["document_date"], "2026-06-16")
        self.assertIn("Location block", certificate["excerpt"])
        self.assertIn("Marsstraße 5, 85551 Kirchheim", certificate["excerpt"])
        self.assertIn("not transferred to MUC2", certificate["metadata"]["identity_scope"])
        identity = evidence["europe10-portus-munich-campus-identity"]["metadata"]
        self.assertEqual(identity["excluded_operator_coordinate"], [11.7662373, 48.1585287])
        result = read(PORTUS)["results"][0]
        self.assertNotEqual(result["geometry"]["coordinates"], identity["excluded_operator_coordinate"])
        self.assertIn("not MUC2's building", result["semantics"]["precision_scope"])
        self.assertTrue({"portus-munich-campus-identity", "portus-muc1-certified-site-address",
                         "portus-download-authority"} <= set(result["identity_source_ids"]))
        point = read(PORTUS)["evidence"][0]["metadata"]
        self.assertEqual(point["selected_source_label"], "Spacenet")
        self.assertEqual(point["source_result_count"], 1)
        self.assertIn("no unproven rename", point["identity_scope"])
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-05-28")

    def test_etobicoke_exact_land_identifier_point_crs_and_licence_are_bound(self) -> None:
        doc = read(ETOBICOKE)
        evidence = evidence_by_key(doc)
        point = evidence["am10-etobicoke-oar-land-point"]
        metadata = point["metadata"]
        self.assertEqual(metadata["result_count"], 3)
        self.assertEqual(metadata["selected_record_pointer"], "/result/records/2")
        attributes = metadata["selected_attributes"]
        self.assertEqual(attributes["ADDRESS_POINT_ID"], 30029368)
        self.assertEqual(attributes["ADDRESS_ID"], 1512790)
        self.assertEqual(attributes["ADDRESS_FULL"], "48 Lowe's Pl")
        self.assertEqual(attributes["ADDRESS_CLASS"], "L")
        self.assertEqual(attributes["ADDRESS_CLASS_DESC"], "Land")
        self.assertEqual(attributes["MUNICIPALITY_NAME"], "Etobicoke")
        self.assertEqual(metadata["geometry"]["coordinates"], [-79.5482231836428, 43.7087107176944])
        self.assertEqual(doc["results"][0]["geometry"], metadata["geometry"])
        self.assertEqual(doc["results"][0]["location_basis"], "official_address_geocode")
        self.assertEqual(metadata["source_crs"], "EPSG:4326")
        self.assertEqual(point["license"], "Open Government Licence - Toronto")
        self.assertEqual(metadata["attribution_statement"],
                         "Contains information licensed under the Open Government Licence - Toronto.")
        crs = evidence["am10-etobicoke-oar-crs-corroboration"]["metadata"]
        self.assertEqual(crs["same_address_point_id"], 30029368)
        self.assertEqual(crs["response_crs_value"], 4326)
        self.assertEqual(crs["geometry"]["x"], metadata["geometry"]["coordinates"][0])
        self.assertAlmostEqual(crs["geometry"]["y"], metadata["geometry"]["coordinates"][1], places=12)
        self.assertIn("notspecified", evidence["am10-toronto-oar-catalog"]["metadata"]
                      ["license_metadata_discrepancy"])
        self.assertTrue({"am10-etobicoke-oar-land-point", "am10-etobicoke-oar-crs-corroboration",
                         "am10-toronto-oar-catalog", "am10-toronto-oar-license-binding",
                         "am10-toronto-ogl"} <= set(doc["results"][0]["geometry_source_ids"]))
        self.assertIn("Not the new building footprint", doc["results"][0]["semantics"]["precision_scope"])

    def test_etobicoke_conditional_occupancy_and_conflicting_onsets_are_not_completion(self) -> None:
        doc = read(curated_path("americas-round10-etobicoke-current-build"))
        metadata = doc["evidence"][0]["metadata"]
        self.assertIn("not that occupancy was issued", metadata["successor_guardrail"])
        self.assertIn("not operational", metadata["successor_guardrail"])
        self.assertIn("May 2024", metadata["onset_conflict"])
        self.assertIn("November 21, 2024", metadata["onset_conflict"])
        self.assertIn("No onset date is normalized", metadata["onset_conflict"])
        self.assertEqual(doc["lifecycle"][0]["value"], "under_construction")
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-08-05")
        motion = evidence_by_key(read(ETOBICOKE))["am10-etobicoke-city-datacenter-address"]
        self.assertIsNone(motion["published_at"])
        self.assertEqual(motion["metadata"]["source_document_date"], "2026-07-22")
        self.assertIn("not evidence that occupancy was granted", motion["excerpt"])

    def test_only_four_distinct_projects_and_campuses_are_added_and_holds_stay_out(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        old_keys = {row["project_stable_key"] for row in old["acceptances"]}
        new_keys = {row["project_stable_key"] for row in new["acceptances"]}
        expected = {read(curated_path(name))["project"]["stable_key"] for name in CURATED_NAMES}
        self.assertEqual(new_keys - old_keys, expected)
        old_campuses = {row["parent_campus_stable_key"] for row in old["acceptances"]}
        new_campuses = {row["parent_campus_stable_key"] for row in new["acceptances"]}
        expected_campuses = {read(curated_path(name))["campus"]["stable_key"] for name in CURATED_NAMES}
        self.assertEqual(len(expected_campuses), 4)
        self.assertEqual(new_campuses - old_campuses, expected_campuses)
        self.assertFalse(any("vaughan" in key or "markham" in key for key in new_campuses))
        for held in ("curated:meta-tulsa-oklahoma-data-center",
                     "curated:ntt-frankfurt-5-hattersheim-campus",
                     "curated:bell-ai-fabric-sherwood-campus",
                     "curated:edgeconnex-heusenstamm-campus"):
            self.assertNotIn(held, new_campuses)

    def test_every_previous_row_feature_binding_and_acceptance_is_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(new_dir / filename)}
            for row in table(old_dir / filename):
                self.assertEqual(row, current[row[key]])
        for feature in read(old_dir / "sites.geojson")["features"]:
            self.assertIn(feature, read(new_dir / "sites.geojson")["features"])
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
            "physical_sites": 150, "projects": 153, "evidence": 510,
            "countries": 41, "non_us_sites": 104,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 148,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 50, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 150, "required": 200, "passed": False})
        self.assertEqual(gates["non_us_site_count"],
                         {"actual": 104, "required_minimum": 100, "passed": True})
        self.assertEqual(gates["country_count"],
                         {"actual": 41, "required_minimum": 40, "passed": True})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 153, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 153)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-fifty-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
