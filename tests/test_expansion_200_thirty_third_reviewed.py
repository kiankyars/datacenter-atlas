"""EDGE2 phase 3 and its named community building, not the brochure point."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_second_reviewed as previous
from datacenter_atlas import expansion_200_thirty_third_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
CURATED = "sources/curated-official-2026-09-10-asia-round37-edge2-phase3-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-asia-round37-edge2-geometry-proposal.json"
OSM_SHA = "74c8b42aa2d935c08ed3f748e3e41fa6beb3a00eb44b101d900f990bf5041430"
RING = [
    [106.8347789, -6.2139353],
    [106.8349378, -6.213673],
    [106.8355145, -6.2140183],
    [106.8353556, -6.2142806],
    [106.8347789, -6.2139353],
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirtyThirdReviewedDraftTests(unittest.TestCase):
    def test_one_new_indonesia_campus_and_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 88)
        self.assertEqual(len(contract["sources"]), 618)
        (addition,) = contract["acceptances"][87:]
        curated = read(ROOT / CURATED)
        self.assertEqual(addition["parent_campus_stable_key"], curated["campus"]["stable_key"])
        self.assertEqual(addition["project_stable_key"], curated["project"]["stable_key"])
        self.assertEqual(addition["country_iso_a2"], "ID")
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 188, "projects": 191, "countries": 44,
            "non_us_sites": 125, "evidence": 854,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 186,
        })

    def test_june30_phase3_observation_not_issuance_or_cost_percentage(self):
        document = read(ROOT / CURATED)
        (status,) = document["lifecycle"]
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-06-30")
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertIsNone(source["published_at"])
        self.assertEqual(source["metadata"]["report_authorized_for_issuance_date"], "2026-07-29")
        self.assertEqual(source["content_hash"],
                         "9f1480b169d2df05a37977879ecb81f77ccadccf8cf619e830f4878beb64b6c0")
        self.assertIn("cost-based", source["metadata"]["cost_guardrail"])
        self.assertIn("not a completion", source["metadata"]["forecast_guardrail"])
        self.assertIn("phase 2", source["metadata"]["project_scope"])
        self.assertFalse(document["evidence"][1]["metadata"]["lifecycle_selected"])
        self.assertEqual(document["evidence"][1]["published_at"], "2024-02-28")

    def test_exact_osm_ring_preserved_as_locator_not_official_boundary(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {"type": "Polygon", "coordinates": [RING]})
        self.assertEqual(result["display_anchor"]["coordinates"], [106.8351467, -6.2139768])
        self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], RING))
        self.assertEqual(result["semantics"]["geometry_authority_class"], "community_source")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertEqual(result["semantics"]["geometry_scope_class"],
                         "community_mapped_constituent_building_outline")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        (osm,) = [e for e in proposal["evidence"] if e["content_hash"] == OSM_SHA]
        self.assertTrue(osm["source_url"].endswith("/way/1230327255/full.json"))
        self.assertEqual(osm["metadata"]["source_polygon_coordinates"], RING)
        self.assertEqual(osm["metadata"]["source_coordinate_precision_decimal_places"], 7)
        self.assertEqual(osm["metadata"]["ordered_node_ids"],
                         [11409722905, 11409722902, 11409722903, 11409722904, 11409722905])
        self.assertFalse(osm["metadata"]["lifecycle_selected"])
        self.assertIn("WGS84", json.dumps(proposal))
        self.assertIn("ODbL-1.0", json.dumps(proposal))

    def test_conflicting_brochure_point_and_redirect_not_geometry(self):
        proposal = read(ROOT / PROPOSAL)
        brochure = proposal["evidence"][3]
        point = brochure["metadata"]["rejected_printed_point"]
        self.assertEqual(point, [106.8373, -6.2138])
        self.assertFalse(core._inside_ring(point, RING))
        self.assertNotIn(brochure["key"], proposal["results"][0]["geometry_source_ids"])
        self.assertIn("datum", brochure["metadata"]["rejection_reason"])
        corroboration = proposal["evidence"][4]
        self.assertEqual(corroboration["kind"], "third_party_dataset")
        self.assertIn(corroboration["key"], proposal["results"][0]["identity_source_ids"])
        self.assertNotIn(corroboration["key"], proposal["results"][0]["geometry_source_ids"])
        self.assertFalse(corroboration["metadata"]["geometry_selected"])
        self.assertFalse(corroboration["metadata"]["lifecycle_selected"])
        self.assertTrue(core._inside_ring(corroboration["metadata"]["displayed_geocode"], RING))
        self.assertIn("generic educational page", proposal["evidence"][0]["metadata"]["website_guardrail"])
        self.assertEqual(proposal["distinctness_review"]["sites"], 187)
        self.assertEqual(proposal["distinctness_review"]["full_geometry_intersections"], [])
        self.assertEqual(proposal["distinctness_review"]["alias_matches"], [])

    def test_no_unsupported_roles_metrics_or_media(self):
        curated = read(ROOT / CURATED)
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(curated[field], [])
        for entity in ("campus", "project"):
            self.assertEqual(curated[entity]["roles"], {})
            self.assertIsNone(curated[entity]["geometry"])
            self.assertIsNone(curated[entity]["coordinates"])
        self.assertTrue(read(ROOT / PROPOSAL)["research_only"])

    def test_portable_evidence_closure_and_kind_validation(self):
        contract = read(batch.contract_path(ROOT))
        for spec in contract["sources"][611:]:
            raw = (ROOT / spec["path"]).read_bytes()
            self.assertEqual(len(raw), spec["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
            value = json.loads(raw)
            for token in spec["evidence_pointer"].strip("/").split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            EvidenceKind(value["kind"])
            core._source_evidence(value, spec["source_id"])
            self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
            self.assertFalse(value["metadata"]["request_credentials_supplied"])
            self.assertFalse(value["metadata"]["raw_capture_redistributed"])

    def test_preceding_rows_features_and_source_pins_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for name, key in (("projects.csv", "project_stable_key"),
                          ("sites.csv", "physical_site_stable_key"),
                          ("evidence.csv", "evidence_id")):
            current = {x[key]: x for x in table(after / name)}
            for row in table(before / name):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(Counter((before / name).read_bytes().splitlines(keepends=True)),
                                 Counter((after / name).read_bytes().splitlines(keepends=True)))
        for feature in read(before / "sites.geojson")["features"]:
            self.assertIn(feature, read(after / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        self.assertEqual(old["sources"], new["sources"][:611])
        for key, pin in previous.REVIEW_PINS.source_sha256.items():
            self.assertEqual(pin, batch.REVIEW_PINS.source_sha256[key])
        for original, current in zip(old["acceptances"], new["acceptances"], strict=False):
            current["distinctness_review"]["batch_site_keys_sha256"] = original["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(original, current)

    def test_eleven_artifacts_reproduce_and_final_gates_stay_unmet(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["imagery_outcomes_complete"]["actual"], 10)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        self.assertFalse(gates["site_count"]["passed"])
        self.assertFalse(gates["blind_review"]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-third-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)
