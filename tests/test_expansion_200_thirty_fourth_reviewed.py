"""Bossier's current build and applicant-map interior locator, not an estate centroid."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_third_reviewed as previous
from datacenter_atlas import expansion_200_thirty_fourth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
CURATED = "sources/curated-official-2026-09-10-americas-round38-stack-bossier-current-build.json"
PROPOSAL = "sources/verified-construction-core-v0.18-americas-round38-stack-bossier-geometry-proposal.json"
AUDIT = "sources/research-expansion-200-americas-round38-stack-bossier-root-review-2026-09-10.json"
MAP_SHA = "5b1ba57fa706c41a28920d3cd6e06c87f7dd38a744df56decf4d49b0919f8f8d"
FORMAT_SHA = "638f531b57ceb50b4f0b86a6740a57438ccecb0e434e32f0209d9c8200ecc44b"
POINT = [-93.73567, 32.75561]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirtyFourthReviewedDraftTests(unittest.TestCase):
    def test_one_new_us_campus_and_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 89)
        self.assertEqual(len(contract["sources"]), 624)
        (addition,) = contract["acceptances"][88:]
        curated = read(ROOT / CURATED)
        self.assertEqual(addition["parent_campus_stable_key"], curated["campus"]["stable_key"])
        self.assertEqual(addition["project_stable_key"], curated["project"]["stable_key"])
        self.assertEqual(addition["country_iso_a2"], "US")
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 189, "projects": 192, "countries": 44,
            "non_us_sites": 125, "evidence": 860,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 187,
        })

    def test_june10_current_statement_not_plat_or_august_update(self):
        document = read(ROOT / CURATED)
        (status,) = document["lifecycle"]
        self.assertEqual(status["value"], "under_construction")
        self.assertEqual(status["as_of_date"], "2026-06-10")
        source = document["evidence"][0]
        self.assertEqual(source["kind"], "company_disclosure")
        self.assertEqual(source["published_at"], "2026-06-10")
        self.assertEqual(source["content_hash"],
                         "d820f9a6c8474cb1b50bc7f9da021223f7bca7337025180519472e59d568479e")
        self.assertIn("publication-normalized", source["metadata"]["date_semantics"])
        self.assertIn("Broad under_construction", source["metadata"]["physical_status_scope"])
        self.assertEqual(status["evidence_key"], source["key"])
        for other in document["evidence"][1:]:
            self.assertFalse(other["metadata"]["lifecycle_selected"])
        parish, proceedings, amazon = document["evidence"][1:]
        self.assertEqual(parish["published_at"], "2026-03-20")
        self.assertEqual(parish["metadata"]["event_date"], "2026-03-18")
        self.assertEqual(proceedings["published_at"], "2026-04-15")
        self.assertEqual(proceedings["metadata"]["event_date"], "2026-03-18")
        self.assertEqual(amazon["published_at"], "2026-02-23")
        self.assertEqual(amazon["metadata"]["page_updated_at"], "2026-08-18")
        self.assertIn("six data-center buildings", proceedings["metadata"]["identity_scope"])

    def test_exact_interior_locator_and_explicit_non_boundary_semantics(self):
        proposal = read(ROOT / PROPOSAL)
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(result["semantics"]["geometry_authority_class"], "official_source")
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
        self.assertEqual(len(proposal["evidence"]), 2)
        self.assertEqual({e["content_hash"] for e in proposal["evidence"]}, {MAP_SHA, FORMAT_SHA})
        self.assertEqual(set(result["geometry_source_ids"]), {e["key"] for e in proposal["evidence"]})
        self.assertNotEqual(POINT, [-93.736122, 32.753977])
        for source in proposal["evidence"]:
            self.assertFalse(source["metadata"]["lifecycle_selected"])

    def test_portable_project_vector_reconstructs_native_interior_point(self):
        metadata = read(ROOT / PROPOSAL)["evidence"][0]["metadata"]
        georef = metadata["georeference"]
        path = metadata["selected_path"]
        numerics = metadata["numerical_reproduction"]
        self.assertEqual(len(path["pdf_page_points"]), 335)
        self.assertEqual(path["stroke_rgb"], [0, 0, 0])
        self.assertEqual(georef["lpts_unit_square_pairs"], [[0, 0], [0, 1], [1, 1], [1, 0]])
        self.assertEqual(georef["gpts_latitude_longitude_pairs"], [
            [32.72684, -93.76368], [32.77236, -93.76431],
            [32.7728, -93.71885], [32.72728, -93.71824],
        ])
        self.assertIn("NAD_1983_2011", georef["source_crs_wkt"])
        self.assertEqual(georef["recognized_equivalent_epsg"], 6477)
        self.assertFalse(numerics["allow_ballpark"])
        x0, y0, x1, y1 = georef["viewport_bbox_pdf_user_space"]
        controls = georef["gpts_projected_controls_us_survey_feet"]
        ring = []
        for x, y in path["pdf_page_points"]:
            u = (x-x0)/(x1-x0)
            v = (path["page_height_pdf_points"]-y-y0)/(y1-y0)
            weights = [(1-u)*(1-v), (1-u)*v, u*v, u*(1-v)]
            ring.append([sum(weights[k]*controls[k][axis] for k in range(4)) for axis in (0, 1)])
        self.assertEqual(ring[0], ring[-1])
        ordinates = sorted({point[1] for point in ring})
        middle = (ordinates[0]+ordinates[-1])/2
        lower = max(y for y in ordinates if y <= middle)
        upper = min(y for y in ordinates if y > middle)
        scan_y = (lower+upper)/2
        crossings = sorted(
            ax+(scan_y-ay)*(bx-ax)/(by-ay)
            for (ax, ay), (bx, by) in zip(ring, ring[1:]) if (ay > scan_y) != (by > scan_y)
        )
        self.assertEqual(len(crossings) % 2, 0)
        left, right = max(zip(crossings[::2], crossings[1::2]), key=lambda pair: pair[1]-pair[0])
        interior = [(left+right)/2, scan_y]
        self.assertEqual(interior, [2900930.5120895035, 822704.1535681961])
        self.assertEqual(interior, numerics["source_native_representative_point_us_survey_feet"])
        self.assertEqual(interior, numerics["unmodified_native_representative_point_us_survey_feet"])
        self.assertTrue(core._inside_ring(interior, ring))
        self.assertEqual(numerics["topology_audit"]["normalized_hole_count"], 1)
        self.assertTrue(numerics["topology_audit"]["representative_point_unchanged"])
        self.assertEqual(numerics["rounded_selected_point"], POINT)

    def test_independent_derivation_keeps_source_datum_topology_and_uncertainty(self):
        audit = read(ROOT / AUDIT)
        geometry = audit["independent_geometry_review"]
        self.assertEqual(geometry["exact_viewport_bbox"], [19.000137329, 92.519571792, 594, 774])
        self.assertIn("EPSG:6477", geometry["source_projected_crs"])
        self.assertIn("EPSG:6318", geometry["source_geographic_crs"])
        self.assertEqual(geometry["control_precision_decimal_places"], 5)
        self.assertIn("335-point", geometry["source_path"])
        self.assertIn("not an algorithm prescribed", geometry["method"])
        self.assertIn("make_valid", geometry["normalization"])
        self.assertIn("identical before and after", geometry["normalization"])
        self.assertEqual(geometry["native_representative_point_us_survey_feet"],
                         [2900930.5120895035, 822704.1535681961])
        self.assertEqual(geometry["display_locator_longitude_latitude"], POINT)
        self.assertEqual(geometry["transform_operation_accuracy_metres"], 2)
        self.assertIn("allow_ballpark=False", geometry["transform"])
        self.assertIsNone(geometry["horizontal_uncertainty_metres"])
        self.assertIn("not positional accuracy", geometry["uncertainty_caveat"])
        specification = audit["normative_format_review"]
        self.assertEqual(specification["sha256"], FORMAT_SHA)
        self.assertEqual(specification["pdf_pages_visually_reviewed"], [49, 50, 51, 52, 131, 132])
        self.assertIn("ExtensionLevel 3", specification["title"])

    def test_distinctness_conservative_full_geometry_and_unverified_applicant_scope(self):
        audit = read(ROOT / AUDIT)
        review = audit["distinctness_review"]
        raw = (previous.draft_path(ROOT) / "sites.geojson").read_bytes()
        self.assertEqual(len(raw), review["geojson_bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), review["geojson_sha256"])
        self.assertEqual(review["sites"], 188)
        self.assertEqual(review["full_geometry_intersections"], [])
        self.assertEqual(review["alias_matches"], [])
        self.assertIn("larger red landholding", review["method"])
        self.assertIn("not verified", audit["identity_review"]["corps_caveat"])
        self.assertIn("Section 32", audit["identity_review"]["section_discrepancy"])
        self.assertIn("not an exhaustive", audit["lifecycle_review"]["absence_limit"])
        self.assertIn("CGK", audit["separate_unfinished_work"])

    def test_no_unsupported_roles_metrics_or_media(self):
        curated = read(ROOT / CURATED)
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(curated[field], [])
        for entity in ("campus", "project"):
            self.assertEqual(curated[entity]["roles"], {})
            self.assertIsNone(curated[entity]["geometry"])
            self.assertIsNone(curated[entity]["coordinates"])
        self.assertTrue(read(ROOT / PROPOSAL)["research_only"])
        rights = curated["evidence"][1]["metadata"]["rights_scope"]
        self.assertIn("not extended to the newspaper PDF", rights)
        self.assertEqual(curated["evidence"][2]["license"], "all-rights-reserved")

    def test_portable_evidence_closure_and_kind_validation(self):
        contract = read(batch.contract_path(ROOT))
        for spec in contract["sources"][618:]:
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
        self.assertEqual(old["sources"], new["sources"][:618])
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
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-fourth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)
