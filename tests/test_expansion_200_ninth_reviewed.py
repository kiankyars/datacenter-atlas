"""46-addition checkpoint: address provenance, marker rounding and phase bounds."""

from __future__ import annotations

import csv
import importlib
import json
from math import floor
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_ninth_reviewed as batch
from datacenter_atlas import expansion_200_eighth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
WINTERTHUR = SOURCES / "verified-construction-core-v0.18-europe-mena-round9-winterthur-proposed-geometry.json"
HUT8 = SOURCES / "verified-construction-core-v0.18-americas-round9-hut8-geometry-proposal.json"
CURATED_NAMES = {
    "europe-mena-round9-winterthur-zrh12-current-build": "2026-07-30",
    "hut8-river-bend-q2-current-build": "2026-08-04",
    "hut8-beacon-point-q2-current-build": "2026-08-04",
}
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def curated_path(name: str) -> Path:
    return SOURCES / f"curated-official-2026-09-08-{name}.json"


class NinthReviewedDraftTests(unittest.TestCase):
    def test_three_packages_keep_physical_dates_and_unknown_fields(self) -> None:
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
                self.assertEqual(doc["evidence"][0]["published_at"], day)
                self.assertNotEqual(day, doc["evidence"][0]["retrieved_at"][:10])
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("workloads", "capacities", "operating_models"):
                    self.assertEqual(doc[field], [])

    def test_bindings_are_closed_and_all_three_points_are_campus_locators(self) -> None:
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 46)
        self.assertEqual(len(validated.sources), 243)
        contract_sources = {source["source_id"]: source
                            for source in read(batch.contract_path(ROOT))["sources"]}
        bindings = read(WINTERTHUR)["source_binding_map"] + read(HUT8)["source_binding_map"]
        self.assertEqual(len(bindings), 20)
        self.assertEqual(len({binding["source_id"] for binding in bindings}), 20)
        for binding in bindings:
            source = contract_sources[binding["source_id"]]
            self.assertEqual(source["path"], binding["path"])
            self.assertEqual(source["evidence_pointer"], binding["evidence_pointer"])
        for row in validated.acceptances[-3:]:
            acceptance, geometry = row["acceptance"], row["geometry"]
            self.assertIn(acceptance["identity"]["source_id"], geometry["identity_source_ids"])
            self.assertEqual(geometry["geometry"]["type"], "Point")
            self.assertEqual(geometry["semantics"]["geometry_source_entity_kind"], "campus")
            self.assertEqual(geometry["semantics"]["geometry_authority_class"], "official_source")
            self.assertEqual(geometry["semantics"]["geometry_use_scope"], "campus_locator")
            self.assertIsNone(geometry["semantics"]["horizontal_uncertainty_metres"])
            draft._geometry(geometry)

    def test_winterthur_binds_exact_download_record_rights_and_official_transform(self) -> None:
        doc = read(WINTERTHUR)
        geometry = doc["results"][0]
        download, stac, transform = doc["evidence"][:3]
        metadata = download["metadata"]
        self.assertEqual(metadata["source_crs"], "EPSG:2056")
        self.assertEqual(metadata["source_record_count"], 3302075)
        self.assertEqual(metadata["source_matches"], 1)
        self.assertEqual(metadata["source_member_bytes"], 468155263)
        self.assertEqual(metadata["source_member_sha256"],
                         "6e986fa96a943f8b0c2f8962f5c2d7963856eb31065e5dc4996e5b9974cdbe18")
        self.assertEqual(metadata["literal_record"]["ADR_EGAID"], "102586517")
        self.assertEqual(metadata["literal_record"]["STN_LABEL"], "Fabrikstrasse")
        self.assertEqual(metadata["literal_record"]["ADR_NUMBER"], "12")
        self.assertEqual(metadata["literal_record"]["ZIP_LABEL"], "8404 Winterthur")
        self.assertEqual(metadata["literal_record"]["ADR_EASTING"], "2699653.019")
        self.assertEqual(metadata["literal_record"]["ADR_NORTHING"], "1261946.623")
        self.assertEqual(stac["metadata"]["checksum_multihash"][4:].lower(),
                         download["content_hash"])
        self.assertEqual(transform["metadata"]["input_coordinates"], [2699653.019, 1261946.623])
        self.assertEqual(transform["metadata"]["input_source_key"], download["key"])
        self.assertEqual(geometry["geometry"]["coordinates"],
                         [8.76128018116464, 47.50071815284883])
        self.assertEqual(geometry["location_basis"], "official_address_geocode")
        self.assertEqual(download["license"], "swisstopo-free-geodata-terms-2021-03-01")
        self.assertEqual(download["attribution"], "© swisstopo")
        self.assertIn("offline Atlas data publication", metadata["rights_scope"])
        self.assertEqual(set(geometry["geometry_source_ids"]), {
            "winterthur-official-address-download", "swisstopo-address-stac",
            "winterthur-reframe-transform", "swisstopo-address-scope",
            "swisstopo-ogd-rights", "swisstopo-bgdi-terms", "swisstopo-reframe-manual",
        })
        self.assertEqual(doc["evidence"][6]["license"], "swisstopo-report-A-public-domain")

    def test_winterthur_identity_inference_and_conflicting_pin_remain_explicit(self) -> None:
        doc = read(WINTERTHUR)
        geometry = doc["results"][0]
        identity = doc["root_review"]["identity_review"]
        self.assertIn("Explicit analyst inference", identity)
        self.assertIn("not the ZRH12 code", identity)
        self.assertEqual(set(geometry["identity_source_ids"]), {
            "winterthur-current-finishing", "winterthur-operator-address",
            "winterthur-dpr-zrh12", "winterthur-dpr-erne-zrh12",
        })
        self.assertIn("not the ZRH12 building", geometry["semantics"]["precision_scope"])
        self.assertNotEqual(geometry["geometry"]["coordinates"], [8.7713397, 47.5020821])
        self.assertIn("excluded", doc["root_review"]["distinctness_review"])
        source = read(curated_path("europe-mena-round9-winterthur-zrh12-current-build"))
        self.assertEqual(source["evidence"][3]["published_at"], "2026-01-15")
        self.assertEqual(source["lifecycle"][0]["as_of_date"], "2026-07-30")
        self.assertIn("not selected as geometry", source["evidence"][1]["metadata"]["identity_scope"])

    def test_hut8_preserves_raw_values_and_operator_rendered_rounding(self) -> None:
        doc = read(HUT8)
        expected = (
            ([-91.2995134, 30.7278924], [-91.299513, 30.727892]),
            ([-97.614758, 27.834525], [-97.614758, 27.834525]),
        )
        for index, (raw, rendered) in enumerate(expected):
            with self.subTest(index=index):
                proposal, geometry = doc["proposals"][index], doc["results"][index]
                self.assertEqual(proposal["source_coordinate_values_longitude_latitude"], raw)
                self.assertEqual(doc["evidence"][index]["metadata"]
                                 ["source_coordinate_values_longitude_latitude"], raw)
                self.assertEqual([floor(value * 1000000 + 0.5) / 1000000 for value in raw],
                                 rendered)
                self.assertEqual(proposal["geometry"], geometry["geometry"])
                self.assertEqual(geometry["geometry"]["coordinates"], rendered)
                self.assertEqual(geometry["display_anchor"], geometry["geometry"])
                self.assertEqual(geometry["location_basis"], "first_party_site_coordinate")
                self.assertIn("six-decimal marker rounding", geometry["semantics"]["geometry_derivation"])
                self.assertIn("phase-specific location", geometry["semantics"]["precision_scope"])
                self.assertTrue({"hut8-platform-locations", "hut8-marker-code",
                                 "hut8-mapbox-crs", "hut8-rfc7946"}
                                <= set(geometry["geometry_source_ids"]))
                self.assertIn("hut8-rights", geometry["identity_source_ids"])
                self.assertEqual(doc["evidence"][index]["license"], "all-rights-reserved")
        self.assertEqual(doc["evidence"][4]["publisher"], "Mapbox")
        self.assertEqual(doc["evidence"][5]["license"], "IETF-Trust-Legal-Provisions")
        self.assertEqual(doc["evidence"][6]["license"], "all-rights-reserved")

    def test_hut8_phase_two_and_postcutoff_cms_stage_do_not_replace_physical_status(self) -> None:
        doc = read(HUT8)
        conflict = doc["root_review"]["conflicting_cms_stage"]
        self.assertIn("status=step2", conflict)
        self.assertIn("statusHeading=Commercialization", conflict)
        self.assertIn("2026-08-27T14:34:04Z", conflict)
        self.assertIn("not treated as lifecycle corroboration or a construction cessation", conflict)
        self.assertIn("Phase 2 commercialization", doc["root_review"]["physical_date_review"])
        self.assertIn("June 30 quarter-end is not substituted", doc["root_review"]["physical_date_review"])
        docs = [read(curated_path(f"hut8-{name}-q2-current-build"))
                for name in ("river-bend", "beacon-point")]
        self.assertEqual(docs[0]["evidence"][0]["content_hash"],
                         docs[1]["evidence"][0]["content_hash"])
        for source in docs:
            self.assertIn("No Phase 2 construction", source["evidence"][0]["metadata"]
                          ["physical_status_guardrail"])
            self.assertIsNone(source["evidence"][1]["published_at"])
            self.assertEqual(source["lifecycle"][0]["as_of_date"], "2026-08-04")
            accepted = [row for row in read(batch.contract_path(ROOT))["acceptances"]
                        if row["parent_campus_stable_key"] == source["campus"]["stable_key"]]
            self.assertEqual(len(accepted), 1)
            self.assertEqual(accepted[0]["project_stable_key"], source["project"]["stable_key"])

    def test_held_candidates_are_excluded_and_only_three_projects_are_added(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        old_keys = {row["project_stable_key"] for row in old["acceptances"]}
        new_keys = {row["project_stable_key"] for row in new["acceptances"]}
        expected = {read(curated_path(name))["project"]["stable_key"] for name in CURATED_NAMES}
        self.assertEqual(new_keys - old_keys, expected)
        campus_keys = {row["parent_campus_stable_key"] for row in new["acceptances"]}
        for held in ("curated:ntt-frankfurt-5-hattersheim-campus",
                     "curated:bell-ai-fabric-sherwood-campus",
                     "curated:edgeconnex-heusenstamm-campus"):
            self.assertNotIn(held, campus_keys)
        self.assertFalse(any("umatilla" in key for key in campus_keys))
        held = read(SOURCES / "curated-official-2026-09-08-europe-round7-heusenstamm-site-works.json")
        self.assertEqual(held["lifecycle"], [])

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
            "physical_sites": 146, "projects": 149, "evidence": 479,
            "countries": 41, "non_us_sites": 102,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 144,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 46, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 146, "required": 200, "passed": False})
        self.assertEqual(gates["non_us_site_count"],
                         {"actual": 102, "required_minimum": 100, "passed": True})
        self.assertEqual(gates["country_count"],
                         {"actual": 41, "required_minimum": 40, "passed": True})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 149, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 149)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-forty-six-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
