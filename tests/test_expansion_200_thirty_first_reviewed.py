"""Yguazu campus electrical expansion, not the future Tier-III building."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirtieth_reviewed as previous
from datacenter_atlas import expansion_200_thirty_first_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
CAMPUS = "curated:hive-yguazu-paraguay-campus"
CURATED = "sources/curated-official-2026-09-10-root-round34-hive-yguazu-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-root-round34-hive-yguazu-geometry-proposal.json"
REVIEW = "sources/research-expansion-200-root-round34-hive-yguazu-review-2026-09-10.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirtyFirstReviewedDraftTests(unittest.TestCase):
    def test_one_distinct_campus_and_exact_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 86)
        self.assertEqual(len(contract["sources"]), 605)
        (addition,) = contract["acceptances"][85:]
        self.assertEqual(addition["parent_campus_stable_key"], CAMPUS)
        self.assertEqual(addition["project_stable_key"], CAMPUS + ":2026-100mw-expansion")
        self.assertEqual(addition["country_iso_a2"], "PY")
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 186, "projects": 189, "countries": 44,
            "non_us_sites": 123, "evidence": 841,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 184,
        })

    def test_august14_substation_status_not_future_building_or_financial_date(self):
        document = read(ROOT / CURATED)
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-08-14")
        self.assertEqual(source["content_hash"],
                         "2c1fda383f064fdfaca0784188b009bfec7854ed5700b657a8c58338b44f50a0")
        metadata = source["metadata"]
        self.assertTrue(metadata["lifecycle_selected"])
        self.assertIn("June30 is the financial period end", metadata["date_semantics"])
        self.assertIn("future Tier-III building are excluded", metadata["status"]["scope"])
        self.assertIn("leaves capacity allocation undecided", metadata["successor_review"])
        self.assertIn("Electrical-Infrastructure", document["project"]["name"])
        self.assertEqual(metadata["raw_byte_anchors"][0]["byte_start_inclusive"], 2058865)
        self.assertEqual(metadata["raw_byte_anchors"][1]["byte_start_inclusive"], 2240669)
        self.assertTrue(all(not a["content_redistributed"] for a in metadata["raw_byte_anchors"]))

    def test_exact_regulator_geojson_not_naked_coordinate_fields(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {
            "type": "Point", "coordinates": [-55.0113748914513, -25.4844770233465],
        })
        self.assertEqual(result["geometry"], result["display_anchor"])
        self.assertEqual(result["geometry_source_ids"], [
            "root34-hive-mades-exp83461-geojson-point",
            "root34-mades-public-geojson-client",
            "root34-rfc7946-coordinate-contract",
        ])
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        sources = {x["key"]: x for x in proposal["evidence"]}
        point = sources[result["geometry_source_ids"][0]]
        self.assertEqual(point["content_hash"],
                         "7634de9d86da7a53d2bb14ed2a9a25b2046fdb16edccddc3b17a9579ecf2f89a")
        self.assertEqual(point["metadata"]["source_crs"], "OGC:CRS84")
        self.assertIn("not averaged", point["metadata"]["detail_field_difference_scope"])
        self.assertIn("Not an independent geodetic survey", point["metadata"]["coordinate_contract_inference"])
        self.assertIn("not a surveyed", result["semantics"]["precision_scope"])

    def test_regulator_identity_and_agreement_date_stay_separate_from_status(self):
        sources = {x["key"]: x for x in read(ROOT / PROPOSAL)["evidence"]}
        acquisition = sources["r33-hive-zunz-acquisition-bridge"]
        self.assertIsNone(acquisition["published_at"])
        self.assertEqual(acquisition["metadata"]["agreement_effective_date"], "2025-03-17")
        for year in (2024, 2026):
            source = sources[f"r33-hive-zunz-mades-parcel-{year}"]
            self.assertEqual(source["metadata"]["pdf_pages_visually_reviewed"], [1, 2, 3])
            self.assertEqual(source["metadata"]["parcel_identifiers"]["finca"], "1534")
            self.assertEqual(source["metadata"]["parcel_identifiers"]["padron"], "33")
            self.assertFalse(source["metadata"]["lifecycle_selected"])
            self.assertEqual(source["metadata"]["pdf_decode"]["method"], "JSON.parse then base64 decode")
        self.assertTrue(all(not s["metadata"]["lifecycle_selected"] for s in sources.values()))

    def test_no_unsupported_roles_metrics_or_media(self):
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

    def test_portable_source_closure_and_full_geometry_review(self):
        contract = read(batch.contract_path(ROOT))
        for spec in contract["sources"][593:]:
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
        self.assertEqual(review["dedup"]["full_geometries_compared"], 185)
        self.assertEqual(review["dedup"]["point_intersections"], [])
        self.assertEqual(review["dedup"]["alias_matches"], [])
        self.assertEqual(review["source_review"]["raw_hashes_and_bytes_verified"], 12)
        self.assertEqual(review["source_review"]["decoded_pdfs_verified"], 2)
        self.assertEqual(review["independent_review"]["blocking_findings"], [])
        self.assertEqual(review["independent_review"]["raw_captures_rehashed"], 12)
        self.assertEqual(review["independent_review"]["full_preceding_geometries_compared"], 185)
        self.assertEqual(review["independent_review"]["byte_exact_generated_payloads"], 11)

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
        self.assertEqual(old["sources"], new["sources"][:593])
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
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-first-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
