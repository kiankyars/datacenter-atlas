"""Thane, three Israeli plots, two Texas address points, a Hong Kong lot and a named Singapore campus."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_fifth_reviewed as batch
from datacenter_atlas import expansion_200_thirty_fourth_reviewed as previous
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
THANE = (
    "sources/curated-official-2026-09-25-asia-round41-aws-thane-current-build.json",
    "sources/verified-construction-core-v0.18-asia-round41-aws-thane-geometry-proposal.json",
)
ISRAEL = {
    slug: (
        f"sources/curated-official-2026-09-25-mea-round41-mega-dc-{slug}-current-build.json",
        f"sources/verified-construction-core-v0.18-mea-round41-mega-dc-{slug}-geometry-proposal.json",
    )
    for slug in ("mdcil2", "mdcil5", "mdcil1")
}
CIPHER = {
    slug: (
        f"sources/curated-official-2026-09-25-americas-round41-cipher-{slug}-current-build.json",
        f"sources/verified-construction-core-v0.18-americas-round41-cipher-{slug}-geometry-proposal.json",
    )
    for slug in ("stingray", "blackpearl")
}
RANGE = (
    "sources/curated-official-2026-09-25-apac-round41-range-sandy-ridge-current-build.json",
    "sources/verified-construction-core-v0.18-apac-round41-range-sandy-ridge-geometry-proposal.json",
)
KEPPEL = (
    "sources/curated-official-2026-09-25-apac-round41-keppel-sgp9-current-build.json",
    "sources/verified-construction-core-v0.18-apac-round41-keppel-sgp9-geometry-proposal.json",
)
ORDER = [THANE, *ISRAEL.values(), *CIPHER.values(), RANGE, KEPPEL]
AUDITS = (
    "sources/research-expansion-200-asia-round41-aws-thane-root-review-2026-09-25.json",
    "sources/research-expansion-200-mea-round41-mega-dc-israel-root-review-2026-09-25.json",
    "sources/research-expansion-200-americas-round41-cipher-root-review-2026-09-25.json",
    "sources/research-expansion-200-apac-round41-range-keppel-root-review-2026-09-25.json",
)
PREVIOUS_SOURCES = 624
HYCR_SHA = "2bb04ea8bcabc0e9b3ae48acc828dc25e43570a31b77f4e6aa024aeb1f16fc9e"
KML_SHA = "911692641abf741b1bbac22ca091767ddb3973bb66742ebc49d9d24da00a12df"
MEGA_Q2_SHA = "c436004dc3b6e92c237d8b5e26e52cad8e7928359dd772f65628d1fbbe56b993"
CIPHER_Q2_SHA = "e11b4a4092c3d7844d87a421aa1129dd1b18fd4fec50590a8630205a730a05bc"
RANGE_H1_SHA = "53b580a1144d7f73feb43319e2224119a8618d9b9e34eccb9bdecf3f8e6dfab1"
KEPPEL_1H_SHA = "fa83d1a76931aaa802b04fea880e6cef8fcee3dd3b02fd95fd19e963b58c3ce8"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def shoelace(points):
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area /= 2
    return [cx / (6 * area), cy / (6 * area)]


class ThirtyFifthReviewedDraftTests(unittest.TestCase):
    def test_eight_new_campuses_and_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 97)
        self.assertEqual(len(contract["sources"]), 661)
        additions = contract["acceptances"][89:]
        self.assertEqual([a["country_iso_a2"] for a in additions], ["IN", "IL", "IL", "IL", "US", "US", "HK", "SG"])
        for acceptance, (curated_path, _) in zip(additions, ORDER, strict=True):
            curated = read(ROOT / curated_path)
            self.assertEqual(acceptance["parent_campus_stable_key"], curated["campus"]["stable_key"])
            self.assertEqual(acceptance["project_stable_key"], curated["project"]["stable_key"])
        self.assertEqual(read(batch.draft_path(ROOT) / "manifest.json")["counts"], {
            "physical_sites": 197, "projects": 200, "countries": 46,
            "non_us_sites": 131, "evidence": 897,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 195,
        })

    def test_every_selected_status_is_in_window_and_under_construction(self):
        expected = [
            ("2026-05-27", HYCR_SHA), ("2026-06-30", MEGA_Q2_SHA), ("2026-06-30", MEGA_Q2_SHA),
            ("2026-06-30", MEGA_Q2_SHA), ("2026-08-04", CIPHER_Q2_SHA), ("2026-08-04", CIPHER_Q2_SHA),
            ("2026-06-30", RANGE_H1_SHA), ("2026-07-30", KEPPEL_1H_SHA),
        ]
        for (curated_path, _), (as_of, sha) in zip(ORDER, expected, strict=True):
            document = read(ROOT / curated_path)
            (status,) = document["lifecycle"]
            self.assertEqual(status["value"], "under_construction")
            self.assertEqual(status["as_of_date"], as_of)
            self.assertTrue("2026-05-22" <= as_of <= "2026-08-20")
            source = document["evidence"][0]
            self.assertEqual(source["key"], status["evidence_key"])
            self.assertEqual(source["content_hash"], sha)
            self.assertTrue(source["metadata"]["lifecycle_selected"])
            self.assertEqual(source["metadata"]["source_observation_date"], as_of)
            for other in document["evidence"][1:]:
                self.assertFalse(other["metadata"]["lifecycle_selected"])

    def test_thane_report_bracketed_by_no_start_predecessor_and_later_upload(self):
        status, listing, identity = read(ROOT / THANE[0])["evidence"]
        metadata = status["metadata"]
        self.assertEqual(metadata["commencement_date_as_reported"], "2026-04-30")
        self.assertIn("Excavation", status["excerpt"].title())
        self.assertIn("confidentiality footer", metadata["rights_scope"])
        self.assertIn("not used as identity evidence", metadata["pdf_metadata_note"])
        self.assertEqual(listing["metadata"]["december_2025_remark"], "No construction work started at site")
        self.assertEqual(listing["metadata"]["june_2026_report_upload_at"][:10], "2026-05-30")
        self.assertEqual(identity["metadata"]["proposal_no"], "SIA/MH/INFRA2/477127/2024")
        self.assertIn("not interpreted as a finding", identity["metadata"]["clearance_type_guardrail"])

    def test_thane_polygon_is_the_exact_kml_ring_bounded_by_the_ec_annexure(self):
        proposal = read(ROOT / THANE[1])
        (result,) = proposal["results"]
        kml = proposal["evidence"][0]
        self.assertEqual(kml["content_hash"], KML_SHA)
        ring = result["geometry"]["coordinates"][0]
        tuples = kml["metadata"]["source_coordinate_tuples"]
        self.assertEqual(ring, [[float(v) for v in t.split(",")[:2]] for t in tuples])
        self.assertEqual(len(ring), 63)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        self.assertEqual((min(ys), min(xs), max(ys), max(xs)),
                         (19.2156222873089, 72.98466695600007, 19.22071689800581, 72.9899580532245))
        self.assertEqual(result["display_anchor"]["coordinates"], shoelace(ring))
        self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], ring))
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        self.assertEqual(kml["metadata"]["selected_placemark_index"], 0)

    def test_israeli_plots_keep_native_rings_and_recorded_datum_operation(self):
        for slug, (curated_path, proposal_path) in ISRAEL.items():
            proposal = read(ROOT / proposal_path)
            (result,) = proposal["results"]
            plot = proposal["evidence"][0]["metadata"]
            ring = result["geometry"]["coordinates"][0]
            self.assertEqual(result["location_basis"], "official_parcel")
            self.assertEqual(len(ring), plot["source_ring_vertex_count"])
            self.assertIn("EPSG:2039", plot["source_crs"])
            operation = plot["coordinate_transformation"]
            self.assertEqual(operation["name"], "Inverse of Israeli TM + Israel 1993 to WGS 84 (2)")
            self.assertEqual(operation["operation_accuracy_metres"], 0.5)
            self.assertTrue(all(len(repr(v).split(".")[1]) <= 7 for point in ring for v in point))
            self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], ring))
            self.assertIn("not a registered cadastral parcel", plot["plot_semantics"])
            self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
            status, fy = read(ROOT / curated_path)["evidence"][:2]
            self.assertEqual(status["published_at"], "2026-08-10")
            self.assertIn("June 30", status["metadata"]["date_semantics"])
            self.assertFalse(fy["metadata"]["lifecycle_selected"])
        plots = {s: read(ROOT / p)["evidence"][0]["metadata"]["plot_attributes"] for s, (_, p) in ISRAEL.items()}
        self.assertEqual({s: (a["num"], a["pl_number"]) for s, a in plots.items()}, {
            "mdcil2": ("200A", "632-0649806"), "mdcil5": ("10", "625-0866855"), "mdcil1": ("62", "420-1456037"),
        })
        self.assertEqual(read(ROOT / ISRAEL["mdcil5"][0])["evidence"][1]["metadata"]["cumulative_cost_thousand_nis_2025"], 185125)

    def test_texas_points_are_reproduced_address_points_not_directory_pins(self):
        expected = {"stingray": [-102.9824436, 32.3720672], "blackpearl": [-103.0669994, 31.6913247]}
        for slug, (curated_path, proposal_path) in CIPHER.items():
            proposal = read(ROOT / proposal_path)
            (result,) = proposal["results"]
            self.assertEqual(result["geometry"], {"type": "Point", "coordinates": expected[slug]})
            self.assertEqual(result["display_anchor"], result["geometry"])
            self.assertEqual(result["location_basis"], "official_address_geocode")
            point, native = proposal["evidence"]
            self.assertEqual(point["metadata"]["address_point_attributes"]["source"], "CSEC")
            self.assertEqual(point["metadata"]["selected_point_lon_lat"], expected[slug])
            self.assertIn("no datum transformation", native["metadata"]["crs_reproduction"])
        stingray = read(ROOT / CIPHER["stingray"][0])["evidence"]
        self.assertEqual(stingray[1]["metadata"]["site_address"], "110 SW 9001, Andrews, Texas 79717")
        black_pearl = read(ROOT / CIPHER["blackpearl"][0])
        self.assertIn("Phase I", black_pearl["evidence"][0]["metadata"]["physical_status_scope"])
        self.assertTrue(black_pearl["project"]["stable_key"].endswith(":aws-phase-2-site-preparation"))

    def test_range_lot_is_the_tendered_dd89_lot_transformed_from_hk1980(self):
        status, identity = read(ROOT / RANGE[0])["evidence"]
        self.assertEqual(status["published_at"], "2026-08-27")
        self.assertIn("NEXTDC", status["metadata"]["date_semantics"])
        self.assertEqual(identity["metadata"]["lot"], "DD 89 Lot 953")
        proposal = read(ROOT / RANGE[1])
        (result,) = proposal["results"]
        lot = proposal["evidence"][0]["metadata"]
        self.assertEqual(result["location_basis"], "official_parcel")
        self.assertIn("EPSG:2326", lot["source_crs"])
        self.assertEqual(lot["coordinate_transformation"]["operation_accuracy_metres"], 1.0)
        ring = result["geometry"]["coordinates"][0]
        self.assertEqual(len(ring), lot["source_ring_vertex_count"])
        self.assertTrue(core._ring(ring))
        self.assertEqual(result["display_anchor"]["coordinates"], shoelace(ring))
        self.assertIn("free of charge", lot["rights_scope"])

    def test_keppel_named_osm_campus_without_redistributed_onemap_point(self):
        status, identity = read(ROOT / KEPPEL[0])["evidence"]
        self.assertIn("SGP 9 commenced construction", status["metadata"]["literal_pointer"])
        self.assertIn("82 Genting Lane", identity["metadata"]["literal_pointer"])
        proposal = read(ROOT / KEPPEL[1])
        (result,) = proposal["results"]
        osm = proposal["evidence"][0]
        self.assertEqual(osm["license"], "ODbL-1.0")
        self.assertEqual(osm["metadata"]["selected_tags"]["name"], "Keppel Genting Lane Campus")
        self.assertEqual(result["geometry"]["coordinates"][0], osm["metadata"]["source_polygon_coordinates"])
        self.assertEqual(result["location_basis"], "community_named_site_feature")
        self.assertIn("neither selected nor redistributed", osm["metadata"]["identity_crosscheck"])
        text = json.dumps(proposal)
        self.assertNotIn("103.876442280651", text)
        self.assertNotIn("1.325045738480048", text)

    def test_audits_record_distinctness_holds_and_unfinished_cgk(self):
        raw = (previous.draft_path(ROOT) / "sites.geojson").read_bytes()
        for path in AUDITS:
            audit = read(ROOT / path)
            review = audit["distinctness_review"]
            self.assertEqual(review["sites"], 189)
            self.assertEqual(review["geojson_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(review["full_geometry_intersections"], [])
            self.assertEqual(review["alias_matches"], [])
            self.assertIn("CGK", audit["separate_unfinished_work"])
            self.assertTrue(audit["round41_holds_preserved"])
            self.assertFalse(audit["accepted_into_core"])

    def test_no_unsupported_roles_metrics_or_media(self):
        for curated_path, proposal_path in ORDER:
            curated = read(ROOT / curated_path)
            for field in ("capacities", "workloads", "operating_models"):
                self.assertEqual(curated[field], [])
            for entity in ("campus", "project"):
                self.assertEqual(curated[entity]["roles"], {})
                self.assertIsNone(curated[entity]["geometry"])
                self.assertIsNone(curated[entity]["coordinates"])
            self.assertTrue(read(ROOT / proposal_path)["research_only"])

    def test_portable_evidence_closure_and_kind_validation(self):
        contract = read(batch.contract_path(ROOT))
        for spec in contract["sources"][PREVIOUS_SOURCES:]:
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
        self.assertEqual(old["sources"], new["sources"][:PREVIOUS_SOURCES])
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
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-fifth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)
