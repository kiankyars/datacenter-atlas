"""One reviewed Trenton campus; legal attribution and locator limits stay explicit."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_eighth_reviewed as previous
from datacenter_atlas import expansion_200_twenty_ninth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas import verified_construction_core as legacy_core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
curated_v11 = importlib.import_module(f"{legacy_core.__package__}.curated_v11")
CAMPUS = "curated:prologis-trenton-project-mila-campus"
CURATED = "sources/curated-official-2026-09-09-root-round32-trenton-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-root-round32-trenton-geometry-proposal.json"
REVIEW = "sources/research-expansion-200-root-round32-trenton-review-2026-09-09.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class TwentyNinthReviewedDraftTests(unittest.TestCase):
    def test_one_distinct_campus_and_exact_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 84)
        self.assertEqual(len(contract["sources"]), 587)
        (addition,) = contract["acceptances"][83:]
        self.assertEqual(addition["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(addition["country_iso_a2"], "US")
        self.assertEqual(
            read(batch.draft_path(ROOT) / "manifest.json")["counts"],
            {
                "physical_sites": 184,
                "projects": 187,
                "countries": 43,
                "non_us_sites": 122,
                "evidence": 823,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 182,
            },
        )

    def test_status_is_developer_disclosure_not_judicial_inspection(self):
        document = read(ROOT / CURATED)
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertIn("Trenton Data Center Campus LLC", source["publisher"])
        self.assertIn("hosted by Supreme Court", source["publisher"])
        self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-08-20")
        metadata = source["metadata"]
        self.assertFalse(metadata["judicial_construction_finding"])
        self.assertFalse(metadata["sworn_statement"])
        self.assertEqual(metadata["pdf_pages_visually_reviewed"], [1, 10, 11])
        self.assertIn("post-cutoff", metadata["successor_review"])
        self.assertIn("not reporter narrative", metadata["authority_basis"])
        self.assertEqual(
            source["content_hash"],
            "efbd863c9b77ca2c15f37febc2bc6e42b521997a861350324d74a1d81ed5893d",
        )

    def test_exact_parcel_point_and_coordinate_system_are_explicit(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(
            result["geometry"],
            {"type": "Point", "coordinates": [-84.45971679023693, 39.45620000836149]},
        )
        self.assertEqual(result["geometry"], result["display_anchor"])
        self.assertEqual(result["location_basis"], "official_parcel")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        source = next(
            x
            for x in proposal["evidence"]
            if x["key"] == "root32-trenton-engineer-parcel"
        )
        metadata = source["metadata"]
        self.assertEqual(metadata["match_count"], 1)
        self.assertEqual(
            metadata["selected_attributes"]["current_pin"], "R8000060000011"
        )
        self.assertEqual(metadata["selected_attributes"]["current_objectid"], 200143116)
        self.assertIsNone(metadata["selected_attributes"]["current_acres"])
        transformation = metadata["transformation"]
        self.assertEqual(transformation["source_crs"], "EPSG:3735")
        self.assertEqual(transformation["source_units"], "US survey foot")
        self.assertEqual(transformation["native_ring_positions"], 55)
        self.assertTrue(transformation["executed"])
        self.assertFalse(transformation["ballpark_transformation"])
        self.assertTrue(transformation["point_inside_transformed_parcel"])
        self.assertTrue(transformation["point_inside_former_parcel_union"])
        self.assertIn(
            "not the unknown positional accuracy", transformation["accuracy_caveat"]
        )

    def test_former_parcels_and_preliminary_plans_are_not_extra_sites(self):
        proposal = read(ROOT / PROPOSAL)
        former = next(
            x
            for x in proposal["evidence"]
            if x["key"] == "root32-trenton-auditor-former-parcels"
        )
        metadata = former["metadata"]
        self.assertEqual(
            metadata["former_parcels"],
            [
                "R8000059000004",
                "R8000060000005",
                "R8000060000006",
                "R8000060000007",
                "R8000060000008",
            ],
        )
        self.assertEqual(metadata["parcel_id_field"], "PIN")
        plan = next(
            x
            for x in proposal["evidence"]
            if x["key"] == "root32-trenton-preliminary-site-plan"
        )
        self.assertFalse(plan["metadata"]["lifecycle_selected"])
        self.assertIn("one campus", plan["metadata"]["geometry_scope"])
        self.assertEqual(proposal["accepted_additional_sites"], 0)
        self.assertTrue(proposal["research_only"])

    def test_no_unsupported_metrics_roles_or_imagery(self):
        document = read(ROOT / CURATED)
        for key in ("capacities", "workloads", "operating_models"):
            self.assertEqual(document[key], [])
        for entity in ("campus", "project"):
            self.assertEqual(document[entity]["roles"], {})
            self.assertIsNone(document[entity]["coordinates"])
            self.assertIsNone(document[entity]["geometry"])
        proposal = read(ROOT / PROPOSAL)
        self.assertIn("No open licence", proposal["rights_scope"])
        self.assertIn("not a survey", proposal["rights_scope"])

    def test_source_closure_hashes_and_utc_review_date(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(contract["geometry_identity_reviewed_at"], "2026-09-10")
        specs = contract["sources"][576:]
        self.assertEqual(len(specs), 11)
        for spec in specs:
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
            self.assertLessEqual(value["retrieved_at"][:10], "2026-09-10")
        curated_v11._parse_document(ROOT / CURATED, "2026-09-10T00:30:00Z")

    def test_root_review_covers_all_full_geometries_and_raw_custody(self):
        review = read(ROOT / REVIEW)
        self.assertEqual(review["baseline"]["sites"], 183)
        self.assertEqual(
            review["baseline"]["sha256"],
            "948b65e10200009cbbea45030f978b7dc64fa64f72df2a341cba34ef25524467",
        )
        self.assertEqual(review["dedup"]["full_geometries_compared"], 183)
        self.assertEqual(review["dedup"]["full_parcel_intersections"], [])
        self.assertEqual(review["dedup"]["point_intersections"], [])
        self.assertEqual(review["source_review"]["raw_hashes_and_bytes_verified"], 11)
        self.assertEqual(review["completion"]["remaining_to_200"], 16)
        self.assertFalse(review["completion"]["objective_complete"])

    def test_all_prior_rows_features_and_source_pins_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for name, key in (
            ("projects.csv", "project_stable_key"),
            ("sites.csv", "physical_site_stable_key"),
            ("evidence.csv", "evidence_id"),
        ):
            current = {x[key]: x for x in table(after / name)}
            for row in table(before / name):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(
                Counter((before / name).read_bytes().splitlines(keepends=True)),
                Counter((after / name).read_bytes().splitlines(keepends=True)),
            )
        for feature in read(before / "sites.geojson")["features"]:
            self.assertIn(feature, read(after / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        self.assertEqual(old["sources"], new["sources"][:576])
        for source in old["sources"]:
            key = source["source_id"]
            self.assertEqual(
                previous.REVIEW_PINS.source_sha256[key],
                batch.REVIEW_PINS.source_sha256[key],
            )
        for old_acceptance, new_acceptance in zip(
            old["acceptances"], new["acceptances"], strict=False
        ):
            new_acceptance["distinctness_review"]["batch_site_keys_sha256"] = (
                old_acceptance["distinctness_review"]["batch_site_keys_sha256"]
            )
            self.assertEqual(old_acceptance, new_acceptance)

    def test_eleven_artifacts_rebuild_and_final_gaps_remain(self):
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
        self.assertFalse(gates["site_count"]["passed"])
        self.assertFalse(gates["blind_review"]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-twenty-ninth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(
                batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT
            )
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
