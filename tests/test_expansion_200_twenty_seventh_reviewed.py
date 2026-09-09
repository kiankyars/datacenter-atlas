"""New campus admissions preserve preceding rows and source-specific limitations."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_sixth_reviewed as previous
from datacenter_atlas import expansion_200_twenty_seventh_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
RIOT = "curated:riot-rockdale-site"
ELMINA = "wikidata:Q136745002"
DATAR = "curated:datar-rellingen-campus"
LANCIENNE = "osm:way/1383040176"
LEVIS = "osm:way/1383040174"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def additions():
    return read(batch.contract_path(ROOT))["acceptances"][76:]


def documents(campus):
    (acceptance,) = [
        row for row in additions() if row["parent_campus_stable_key"] == campus
    ]
    sources = {
        row["source_id"]: row for row in read(batch.contract_path(ROOT))["sources"]
    }
    return tuple(
        read(ROOT / sources[acceptance[key]["source_id"]]["path"])
        for key in ("status", "geometry")
    )


class TwentySeventhReviewedDraftTests(unittest.TestCase):
    def test_five_distinct_admissions_and_exact_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 81)
        self.assertEqual(len(contract["sources"]), 559)
        self.assertEqual(
            {row["parent_campus_stable_key"] for row in additions()},
            {RIOT, ELMINA, DATAR, LANCIENNE, LEVIS},
        )
        self.assertEqual(
            Counter(row["country_iso_a2"] for row in additions()),
            {"CA": 2, "US": 1, "MY": 1, "DE": 1},
        )
        counts = read(batch.draft_path(ROOT) / "manifest.json")["counts"]
        self.assertEqual(
            counts,
            {
                "physical_sites": 181,
                "projects": 184,
                "countries": 43,
                "non_us_sites": 121,
                "evidence": 795,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 179,
            },
        )

    def test_datar_current_build_is_separate_from_later_operations(self):
        doc, proposal = documents(DATAR)
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-07-17")
        metadata = doc["evidence"][0]["metadata"]
        self.assertIn(
            "Exact interview/inspection day", metadata["status_date_semantics"]
        )
        self.assertIn("later operating preparation", metadata["physical_scope"])
        native = next(
            row
            for row in proposal["evidence"]
            if row["key"] == "eu30-datar-osm-native-node"
        )
        self.assertEqual(native["metadata"]["source_object_id"], "node/11707884695")
        self.assertFalse(native["metadata"]["lifecycle_selected"])
        self.assertEqual(native["license"], "ODbL-1.0")
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"]["coordinates"], [9.8728278, 53.6349521])
        self.assertEqual(
            result["semantics"]["geometry_scope_class"], "named_site_address_point"
        )
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])

    def test_quebec_active_register_is_not_four_aggregate_sites(self):
        for campus in (LANCIENNE, LEVIS):
            doc, proposal = documents(campus)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-06-08")
            self.assertEqual(
                doc["project"]["stable_key"], f"{campus}:development-project"
            )
            self.assertEqual(len(proposal["results"]), 2)
            self.assertEqual(len(proposal["source_binding_map"]), 11)
        self.assertEqual(
            len([row for row in additions() if row["country_iso_a2"] == "CA"]), 2
        )

    def test_quebec_geocoded_and_community_placements_keep_uncertainty(self):
        _, proposal = documents(LANCIENNE)
        address, levis = proposal["results"]
        self.assertEqual(
            address["geometry"]["coordinates"], [-71.34675196270454, 46.79188968009724]
        )
        self.assertEqual(
            address["semantics"]["geometry_scope_class"],
            "official_interpolated_address_reference_point",
        )
        self.assertIn(
            "1m datum", address["semantics"]["horizontal_uncertainty_unknown_reason"]
        )
        self.assertIsNone(address["semantics"]["horizontal_uncertainty_metres"])
        sources = {row["key"]: row for row in proposal["evidence"]}
        quality = sources["am30-rqa-guide-quality"]["metadata"]
        self.assertTrue(quality["certified_validity_not_accuracy"])
        self.assertEqual(quality["rejected_levis_quality"], "Incertaine")
        osm = sources["am30-levis-osm-named-campus"]["metadata"]
        self.assertEqual(len(osm["node_coordinate_records"]), 13)
        self.assertEqual(osm["source_ring_lon_lat"][0], osm["source_ring_lon_lat"][-1])
        self.assertTrue(osm["derivation"]["point_strictly_within_source_polygon"])
        self.assertEqual(
            levis["geometry"]["coordinates"], [-71.2587356420411, 46.7079338]
        )
        self.assertEqual(
            levis["semantics"]["geometry_authority_class"], "community_source"
        )
        self.assertNotIn("am30-lancienne-rqa-address", levis["geometry_source_ids"])
        self.assertIsNone(levis["semantics"]["horizontal_uncertainty_metres"])

    def test_riot_selects_only_the_unfinished_second_deployment(self):
        doc, proposal = documents(RIOT)
        self.assertEqual(
            doc["project"]["stable_key"], f"{RIOT}:amd-expansion-phases-3-4"
        )
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-08-10")
        (source,) = doc["evidence"]
        self.assertEqual(source["metadata"]["source_observation_date"], "2026-08-10")
        self.assertIn("June 30", source["metadata"]["date_semantics"])
        self.assertIn(
            "Completed initial phases are excluded", source["metadata"]["scope"]
        )
        self.assertIn(
            "Construction is now underway",
            {
                anchor["literal"]
                for anchor in source["metadata"]["literal_byte_anchors"]
            },
        )
        self.assertIn(
            "not a dated completion", proposal["successor_review"]["scope_caveat"]
        )
        self.assertIn(
            "initial", proposal["distinctness_review"]["preservation"].lower()
        )
        self.assertTrue(proposal["campus_association"]["no_new_site_for_phases"])

    def test_riot_participant_filing_is_identity_not_a_judicial_finding(self):
        _, proposal = documents(RIOT)
        sources = {row["key"]: row for row in proposal["evidence"]}
        filing = sources["am30-riot-court-site-address"]["metadata"]
        self.assertTrue(filing["identity_only"])
        self.assertFalse(filing["lifecycle_selected"])
        self.assertEqual(filing["source_pages_visually_reviewed"], [1, 2])
        self.assertIn("not a judicial finding", filing["authority_caveat"])
        self.assertIn("unsigned", filing["authority_caveat"])
        (result,) = proposal["results"]
        self.assertIn("am30-riot-whinstone-acquisition", result["identity_source_ids"])
        self.assertIn("am30-riot-court-site-address", result["identity_source_ids"])
        self.assertNotIn("am30-riot-court-site-address", result["geometry_source_ids"])

    def test_riot_native_projection_does_not_claim_position_accuracy(self):
        _, proposal = documents(RIOT)
        source = next(
            row
            for row in proposal["evidence"]
            if row["key"] == "am30-riot-txgio-address-point"
        )
        metadata = source["metadata"]
        self.assertEqual(metadata["object_id"], 8633415)
        self.assertEqual(
            metadata["source_feature_attributes"]["full_addr"],
            "2721 CHARLES MARTIN HALL RD",
        )
        self.assertEqual(
            metadata["source_point_xy"], [-10806768.7607, 3577792.666699998]
        )
        self.assertEqual(metadata["response_crs"], "EPSG:3857")
        transform = metadata["transformation"]
        point = [-97.0788554968219, 30.57589508119766]
        self.assertEqual(transform["wgs84_point"], point)
        for actual, expected in zip(
            transform["independent_inverse_formula_point"], point
        ):
            self.assertAlmostEqual(actual, expected, places=11)
        self.assertEqual(transform["reported_operation_accuracy_metres"], -1)
        self.assertIsNone(metadata["source_positional_accuracy_metres"])
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": point})
        self.assertEqual(
            result["semantics"]["geometry_authority_class"], "official_source"
        )
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])

    def test_elmina_interview_date_is_not_publication_or_office_geometry(self):
        doc, proposal = documents(ELMINA)
        (source,) = doc["evidence"]
        self.assertEqual(source["published_at"], "2026-08-20")
        self.assertEqual(source["metadata"]["source_observation_date"], "2026-08-15")
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-08-15")
        self.assertEqual(
            doc["project"]["stable_key"],
            "curated:google-elmina-business-park-data-center:current-campus-build",
        )
        self.assertIn(
            "not an inspection or commencement", source["metadata"]["date_semantics"]
        )
        excluded = " ".join(source["metadata"]["excluded_evidence"])
        self.assertIn("Axiata Tower", excluded)
        self.assertIn("Microsoft Malaysia", excluded)
        self.assertIn("forecast", excluded)
        self.assertIn("core-and-shell", proposal["successor_review"]["scope_guardrail"])
        self.assertIn(
            "not selected", proposal["successor_review"]["unselected_developer_caution"]
        )
        self.assertIn(
            "unchanged and unselected", proposal["distinctness_review"]["preservation"]
        )

    def test_elmina_community_point_has_no_synthetic_accuracy_or_osm_geometry(self):
        _, proposal = documents(ELMINA)
        sources = {row["key"]: row for row in proposal["evidence"]}
        source = sources["as30-elmina-wikidata-point"]
        self.assertEqual(source["kind"], "third_party_dataset")
        self.assertEqual(source["license"], "CC0-1.0")
        metadata = source["metadata"]
        self.assertEqual(metadata["coordinate_reference_count"], 0)
        self.assertEqual(metadata["source_coordinate_precision_degrees"], 1e-8)
        self.assertIsNone(metadata["horizontal_accuracy_metres"])
        self.assertEqual(metadata["source_globe"], "http://www.wikidata.org/entity/Q2")
        (result,) = proposal["results"]
        self.assertEqual(
            result["geometry"]["coordinates"], [101.51973036271843, 3.222618484316103]
        )
        self.assertEqual(result["location_basis"], "community_named_site_feature")
        self.assertEqual(
            result["semantics"]["geometry_authority_class"], "community_source"
        )
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertFalse(
            any("osm" in key.lower() for key in result["geometry_source_ids"])
        )
        self.assertEqual(
            sources["as30-wikidata-coordinate-crs"]["license"], "CC-BY-SA-4.0"
        )
        self.assertEqual(
            sources["as30-google-ken-siah-authority"]["published_at"], "2023-09-26"
        )

    def test_new_admissions_have_scoped_status_and_no_synthesized_other_claims(self):
        rows = {
            row["project_stable_key"]: row
            for row in table(batch.draft_path(ROOT) / "projects.csv")
        }
        for acceptance in additions():
            with self.subTest(project=acceptance["project_stable_key"]):
                doc, proposal = documents(acceptance["parent_campus_stable_key"])
                for field in ("capacities", "operating_models", "workloads"):
                    self.assertEqual(doc[field], [])
                for field in ("campus", "project"):
                    self.assertEqual(doc[field]["roles"], {})
                    self.assertIsNone(doc[field]["coordinates"])
                    self.assertIsNone(doc[field]["geometry"])
                (observation,) = doc["lifecycle"]
                self.assertEqual(observation["value"], "under_construction")
                self.assertGreaterEqual(observation["as_of_date"], "2026-05-22")
                self.assertLessEqual(observation["as_of_date"], "2026-08-20")
                (result,) = [
                    result
                    for result in proposal["results"]
                    if result["project_stable_key"] == acceptance["project_stable_key"]
                ]
                core._geometry(result)
                row = rows[acceptance["project_stable_key"]]
                self.assertEqual(json.loads(row["geometry_json"]), result["geometry"])
                self.assertEqual(row["status_as_of"], observation["as_of_date"])
                self.assertEqual(row["independent_imagery_verification"], "false")
                self.assertEqual(row["operating_model"], "unknown")
                for field in ("owner", "operator", "users", "tenants", "customers"):
                    self.assertEqual(row[field], "")

    def test_every_new_binding_is_portable_hashed_and_used(self):
        before = read(previous.contract_path(ROOT))
        after = read(batch.contract_path(ROOT))
        core.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        old_ids = {row["source_id"] for row in before["sources"]}
        specs = [row for row in after["sources"] if row["source_id"] not in old_ids]
        used = {
            key
            for acceptance in additions()
            for key in acceptance["distinctness_review"]["evidence_source_ids"]
        }
        self.assertEqual({spec["source_id"] for spec in specs}, used)
        for spec in specs:
            with self.subTest(source=spec["source_id"]):
                raw = (ROOT / spec["path"]).read_bytes()
                self.assertEqual(len(raw), spec["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
                value = json.loads(raw)
                for token in spec["evidence_pointer"].strip("/").split("/"):
                    value = (
                        value[int(token)] if isinstance(value, list) else value[token]
                    )
                self.assertEqual(value["key"], spec["source_id"])
                self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
                core._source_evidence(value, spec["source_id"])
                EvidenceKind(value["kind"])
                self.assertEqual(value["metadata"]["http_status"], 200)
                self.assertFalse(value["metadata"]["request_credentials_supplied"])
                self.assertFalse(
                    value["metadata"].get("raw_capture_redistributed", False)
                )

    def test_every_prior_row_full_feature_and_source_pin_is_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (
            ("projects.csv", "project_stable_key"),
            ("sites.csv", "physical_site_stable_key"),
            ("evidence.csv", "evidence_id"),
        ):
            current = {row[key]: row for row in table(after / filename)}
            for row in table(before / filename):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(
                Counter((before / filename).read_bytes().splitlines(keepends=True)),
                Counter((after / filename).read_bytes().splitlines(keepends=True)),
            )
        old_features = read(before / "sites.geojson")["features"]
        new_features = read(after / "sites.geojson")["features"]
        self.assertEqual(len(old_features), 176)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        core.validate_batch(
            previous.contract_path(ROOT), previous.REVIEW_PINS, root=ROOT
        )
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
            self.assertEqual(
                previous.REVIEW_PINS.source_sha256[source["source_id"]],
                batch.REVIEW_PINS.source_sha256[source["source_id"]],
            )
        current = {row["project_stable_key"]: row for row in new["acceptances"]}
        for acceptance in old["acceptances"]:
            revised = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            revised["distinctness_review"]["batch_site_keys_sha256"] = acceptance[
                "distinctness_review"
            ]["batch_site_keys_sha256"]
            self.assertEqual(revised, acceptance)

    def test_eleven_artifacts_rebuild_without_completing_final_release_gates(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(
            stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT
        )
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["imagery_outcomes_complete"]["actual"], 10)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in (
            "site_count",
            "additional_site_count",
            "imagery_outcomes_complete",
            "blind_review",
            "clean_clone_rebuild",
            "publication_authorized",
        ):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(
            prefix="atlas-twenty-seventh-rebuild-"
        ) as temp:
            output = Path(temp) / "draft"
            core.build_draft(
                batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT
            )
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual(
                {path.name for path in stored.iterdir()},
                {path.name for path in output.iterdir()},
            )
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
