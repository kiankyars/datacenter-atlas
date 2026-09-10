"""Chennai project KML, not the unrelated Taramani office marker."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_first_reviewed as previous
from datacenter_atlas import expansion_200_thirty_second_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
CURATED = "sources/curated-official-2026-09-10-asia-round36-chennai-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-asia-round36-chennai-geometry-proposal.json"
KML_SHA = "d81e269d9496bee594ba88fd2bcd218f9af430e15118e580b31ba20e6c3e8d4e"
RING = [
    [80.16032636756182, 13.11105250246097],
    [80.1610991137769, 13.11109438263244],
    [80.16109798123352, 13.11189854616338],
    [80.16053579083204, 13.11186688665677],
    [80.15947222100409, 13.11193592401078],
    [80.15943786913193, 13.11106213708188],
    [80.16032636756182, 13.11105250246097],
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirtySecondReviewedDraftTests(unittest.TestCase):
    def test_one_new_india_campus_and_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 87)
        self.assertEqual(len(contract["sources"]), 611)
        (addition,) = contract["acceptances"][86:]
        curated = read(ROOT / CURATED)
        self.assertEqual(addition["parent_campus_stable_key"], curated["campus"]["stable_key"])
        self.assertEqual(addition["project_stable_key"], curated["project"]["stable_key"])
        self.assertEqual(addition["country_iso_a2"], "IN")
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 187, "projects": 190, "countries": 44,
            "non_us_sites": 124, "evidence": 847,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 185,
        })

    def test_july29_construction_observation_not_future_completion(self):
        document = read(ROOT / CURATED)
        (status,) = document["lifecycle"]
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-07-29")
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(source["published_at"], "2026-07-29")
        self.assertEqual(source["content_hash"],
                         "5ce78c489021757c8e3f7978039ee3efc256cc58a569625c6f0fc446ea9321af")
        self.assertIn("shell", json.dumps(source).lower())
        self.assertIn("inspection", json.dumps(source).lower())

    def test_source_ring_preserved_without_office_pin_or_bbox_replacement(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {"type": "Polygon", "coordinates": [RING]})
        self.assertNotEqual(result["display_anchor"]["coordinates"], [80.24607172, 12.98597025])
        self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], RING))
        self.assertEqual(result["semantics"]["geometry_authority_class"], "official_source")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertIn("cadastral", json.dumps(result).lower())
        (kml,) = [e for e in proposal["evidence"] if e["content_hash"] == KML_SHA]
        self.assertIn("963db531-1544-4984-8bef-f68e8a9a0ade", kml["source_url"])
        self.assertIn("version=1.1", kml["source_url"])
        self.assertIn("WGS84", json.dumps(proposal).replace("WGS 84", "WGS84"))

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
        for spec in contract["sources"][605:]:
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
        self.assertEqual(old["sources"], new["sources"][:605])
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
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-second-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)
