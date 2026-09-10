"""One Clydesdale campus with a draft-survey locator, not approved geometry."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_ninth_reviewed as previous
from datacenter_atlas import expansion_200_thirtieth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
CAMPUS = "curated:beale-tulsa-county-project-clydesdale-campus"
CURATED = "sources/curated-official-2026-09-09-root-round33-clydesdale-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-root-round33-clydesdale-geometry-proposal.json"
REVIEW = "sources/research-expansion-200-root-round33-clydesdale-review-2026-09-09.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirtiethReviewedDraftTests(unittest.TestCase):
    def test_one_distinct_campus_and_exact_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 85)
        self.assertEqual(len(contract["sources"]), 593)
        (addition,) = contract["acceptances"][84:]
        self.assertEqual(addition["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(addition["project_stable_key"], CAMPUS + ":current-campus-build")
        self.assertEqual(addition["country_iso_a2"], "US")
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 185, "projects": 188, "countries": 43,
            "non_us_sites": 122, "evidence": 829,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 183,
        })

    def test_august19_developer_body_status_not_old_planning_or_forecast(self):
        document = read(ROOT / CURATED)
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-08-19")
        self.assertEqual(source["content_hash"],
                         "745b13a8a1e059fbc83dfe19e5daca6dc7cd88b6a88b8354363b81c4bd2b9467")
        metadata = source["metadata"]
        self.assertTrue(metadata["lifecycle_selected"])
        self.assertIn("not an inspection date", metadata["date_semantics"])
        self.assertIn("not campus cancellation", metadata["successor_review"])
        self.assertEqual(metadata["raw_byte_anchors"][1]["byte_start_inclusive"], 40836)
        self.assertEqual(metadata["raw_byte_anchors"][1]["byte_end_exclusive"], 40939)
        for anchor in metadata["raw_byte_anchors"]:
            value = anchor["literal"].encode()
            self.assertEqual(hashlib.sha256(value).hexdigest(), anchor["sha256"])
            self.assertEqual(len(value), anchor["byte_end_exclusive"] - anchor["byte_start_inclusive"])

    def test_draft_survey_point_crs_and_unknown_accuracy(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {
            "type": "Point", "coordinates": [-95.91092189697753, 36.26982717564227],
        })
        self.assertEqual(result["geometry"], result["display_anchor"])
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertIn("not survey approval", result["semantics"]["precision_scope"])
        survey = proposal["evidence"][1]["metadata"]
        self.assertFalse(survey["registered_boundary"])
        self.assertFalse(survey["survey_final_approval"])
        self.assertEqual(survey["survey_derivation"]["source_crs"], "EPSG:6553")
        self.assertEqual(survey["survey_derivation"]["source_units"], "US survey foot")
        self.assertEqual(survey["survey_derivation"]["metes_bounds_course_count"], 18)
        self.assertNotIn("metes_bounds_courses", survey["survey_derivation"])
        self.assertLess(survey["survey_derivation"]["traverse_closure_error_feet"], 0.05)
        self.assertIn("not labelled", survey["survey_derivation"]["north_half_distance_derivation"])
        self.assertFalse(survey["transformation"]["ballpark_transformation"])
        self.assertTrue(survey["transformation"]["point_inside_reconstructed_draft_plat"])

    def test_historical_request_withdrawal_and_draft_fields_stay_explicit(self):
        proposal = read(ROOT / PROPOSAL)
        sources = {x["key"]: x for x in proposal["evidence"]}
        survey = sources["root33-clydesdale-draft-survey"]["metadata"]
        self.assertIn("March4,2025", survey["date_scope"])
        self.assertIn("March4,2026", survey["date_scope"])
        minutes = sources["root33-clydesdale-march4-draft-minutes"]["metadata"]
        self.assertTrue(minutes["draft_minutes"])
        self.assertEqual(minutes["pdf_pages_visually_reviewed"], [37])
        self.assertIn("not an asserted cancellation", minutes["scope"])
        for source in sources.values():
            self.assertFalse(source["metadata"]["lifecycle_selected"])

    def test_no_unsupported_roles_metrics_media_or_future_phases(self):
        document = read(ROOT / CURATED)
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(document[field], [])
        for entity in ("campus", "project"):
            self.assertEqual(document[entity]["roles"], {})
            self.assertIsNone(document[entity]["geometry"])
            self.assertIsNone(document[entity]["coordinates"])
        proposal = read(ROOT / PROPOSAL)
        self.assertTrue(proposal["research_only"])
        self.assertEqual(proposal["accepted_additional_sites"], 0)
        self.assertIn("No open licence", proposal["rights_scope"])
        self.assertIn("no publisher prose", proposal["rights_scope"])

    def test_portable_source_closure_and_independent_full_geometry_review(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(contract["geometry_identity_reviewed_at"], "2026-09-10")
        for spec in contract["sources"][587:]:
            raw = (ROOT / spec["path"]).read_bytes()
            self.assertEqual(len(raw), spec["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
            value = json.loads(raw)
            for token in spec["evidence_pointer"].strip("/").split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            EvidenceKind(value["kind"])
            core._source_evidence(value, spec["source_id"])
            self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
            self.assertEqual(value["metadata"]["http_status"], 200)
            self.assertFalse(value["metadata"]["request_credentials_supplied"])
            self.assertFalse(value["metadata"]["raw_capture_redistributed"])
        review = read(ROOT / REVIEW)
        self.assertEqual(review["baseline"]["sites"], 184)
        self.assertEqual(review["dedup"]["full_geometries_compared"], 184)
        self.assertEqual(review["dedup"]["full_plat_intersections"], [])
        self.assertEqual(review["source_review"]["raw_hashes_and_bytes_verified"], 6)
        independent = review["independent_review"]
        self.assertEqual(independent["blocking_findings"], [])
        self.assertEqual(independent["raw_captures_rehashed"], 6)
        self.assertTrue(independent["root_point_inside_independent_tract"])
        self.assertLess(independent["point_difference_metres"], 0.003)

    def test_every_previous_row_feature_and_source_pin_preserved(self):
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
        self.assertEqual(old["sources"], new["sources"][:587])
        for key, pin in previous.REVIEW_PINS.source_sha256.items():
            self.assertEqual(pin, batch.REVIEW_PINS.source_sha256[key])
        for old_acceptance, new_acceptance in zip(old["acceptances"], new["acceptances"], strict=False):
            new_acceptance["distinctness_review"]["batch_site_keys_sha256"] = (
                old_acceptance["distinctness_review"]["batch_site_keys_sha256"]
            )
            self.assertEqual(old_acceptance, new_acceptance)

    def test_eleven_artifact_rebuild_and_unmet_final_gates(self):
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
        with tempfile.TemporaryDirectory(prefix="atlas-thirtieth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
