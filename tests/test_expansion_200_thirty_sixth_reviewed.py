"""HKG10 lot, Lahr address position, Raiden plot and the explicit CGK host-estate correction."""

from collections import Counter
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_fifth_reviewed as previous
from datacenter_atlas import expansion_200_thirty_sixth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
HKG10 = (
    "sources/curated-official-2026-10-09-apac-round43-goodman-hkg10-current-build.json",
    "sources/verified-construction-core-v0.18-apac-round43-goodman-hkg10-geometry-proposal.json",
)
LAHR = (
    "sources/curated-official-2026-10-09-europe-round43-leitwerk-lahr-current-build.json",
    "sources/verified-construction-core-v0.18-europe-round43-leitwerk-lahr-geometry-proposal.json",
)
RAIDEN = (
    "sources/curated-official-2026-10-09-asia-round43-raiden-turbhe-current-build.json",
    "sources/verified-construction-core-v0.18-asia-round43-raiden-turbhe-geometry-proposal.json",
)
ORDER = [HKG10, LAHR, RAIDEN]
AUDITS = (
    "sources/research-expansion-200-apac-round43-goodman-hkg10-root-review-2026-10-09.json",
    "sources/research-expansion-200-europe-round43-leitwerk-lahr-root-review-2026-10-09.json",
    "sources/research-expansion-200-asia-round43-raiden-turbhe-root-review-2026-10-09.json",
)
HOLDS = "sources/research-expansion-200-round43-holds-2026-10-09.json"
CGK_RECORD = "sources/verified-construction-core-v0.18-cgk-host-estate-locator-correction-v1.json"
CGK_PACKET = "sources/research-expansion-200-cgk-locator-round43-2026-10-09.json"
CGK_RECORD_SHA = "e2553c6d0264975cf98435f2d6835fcb5673d25e452b358a36096881fb18ab66"
CORRECTION_ID = "cgk-host-estate-locator-rescope-v1"
CGK_PROJECT = "curated:digital-edge-cgk-campus-bekasi:cgk1"
CGK_SITE = "curated:digital-edge-cgk-campus-bekasi"
CGK_PROJECT_ID = "b2e4945f-3d75-5d9b-b2bb-d65deb74c405"
STT_SITE = "curated:stt-jakarta-data-centre-campus"
SUPERSEDED = "8acab3b0-70c6-5dae-9ca3-3cbf6ae3b975"
CGK_ADDED = ("60324cce-b743-571c-ace0-813e7ae281bc", "7133f023-619a-5656-a041-7f9af60abb61")
SHARED_CRS = "491b3b57-f2fb-53b4-ad33-07902a6d2e19"
HOST_POSTURE = "recent_authoritative_physical_observation_plus_host_estate_context_only"
PREVIOUS_SOURCES = 661
ADMISSION_SOURCES = 27
FY26_SHA = "892c9d069276912a13d2ff100ff3260b1c2d26874693d644e0d34dce3a7d809d"
EWM_SHA = "1d942c2167e3a28de7fe758cb816868a40e5dbd32ef5ad475835025a6ce4726a"
RAIDEN_LETTER_SHA = "520b8b2e07c5ab755dc91bbe373a7c056c4c0ee17988fe58e664e020218c8668"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def lines(path):
    return Counter(path.read_bytes().splitlines(keepends=True))


def resolve(reference):
    path, pointer = reference.split("#", 1)
    value = read(ROOT / path)
    for token in pointer.strip("/").split("/"):
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def shoelace(points):
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area /= 2
    return [cx / (6 * area), cy / (6 * area)]


class ThirtySixthReviewedDraftTests(unittest.TestCase):
    def test_three_new_campuses_and_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(contract["schema_version"], core.SCHEMA_VERSION_V2)
        self.assertEqual(contract["batch_id"], "2026-10-09-thirty-sixth-reviewed-site-delta")
        self.assertEqual(contract["geometry_identity_reviewed_at"], "2026-10-09")
        self.assertEqual(len(contract["acceptances"]), 100)
        self.assertEqual(len(contract["sources"]), PREVIOUS_SOURCES + ADMISSION_SOURCES + 3)
        self.assertEqual([c["correction_id"] for c in contract["baseline_corrections"]], [CORRECTION_ID])
        additions = contract["acceptances"][97:]
        self.assertEqual([a["country_iso_a2"] for a in additions], ["HK", "DE", "IN"])
        for acceptance, (curated_path, _) in zip(additions, ORDER, strict=True):
            curated = read(ROOT / curated_path)
            self.assertEqual(acceptance["parent_campus_stable_key"], curated["campus"]["stable_key"])
            self.assertEqual(acceptance["project_stable_key"], curated["project"]["stable_key"])
        manifest = read(batch.draft_path(ROOT) / "manifest.json")
        self.assertEqual(manifest["format"], "datacenter-atlas-verified-construction-core-v018-draft-v2")
        self.assertEqual(manifest["counts"], {
            "physical_sites": 200, "projects": 203, "countries": 46,
            "non_us_sites": 134, "evidence": 925,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 197,
            "host_estate_context_projects": 1,
        })

    def test_every_selected_status_is_in_window_and_under_construction(self):
        expected = [("2026-06-30", FY26_SHA), ("2026-06-19", EWM_SHA), ("2026-08-03", RAIDEN_LETTER_SHA)]
        for (curated_path, _), (as_of, sha) in zip(ORDER, expected, strict=True):
            document = read(ROOT / curated_path)
            (status,) = document["lifecycle"]
            self.assertEqual(status["value"], "under_construction")
            self.assertEqual(status["method"], "authoritative_physical_status_update")
            self.assertEqual(status["as_of_date"], as_of)
            self.assertTrue("2026-05-22" <= as_of <= "2026-08-20")
            source = document["evidence"][0]
            self.assertEqual(source["key"], status["evidence_key"])
            self.assertEqual(source["content_hash"], sha)
            self.assertTrue(source["metadata"]["lifecycle_selected"])
            self.assertEqual(source["metadata"]["source_observation_date"], as_of)
            for other in document["evidence"][1:]:
                self.assertFalse(other["metadata"]["lifecycle_selected"])

    def test_hkg10_lot_is_the_cited_dd443_section_a_transformed_from_hk1980(self):
        listing = read(ROOT / HKG10[0])["evidence"][1]["metadata"]
        self.assertEqual(listing["listing_street_address"], "128 Texaco Road")
        self.assertIn("Section A of Lot No. 472 in D.D. 443", read(ROOT / HKG10[0])["evidence"][3]["metadata"]["literal_pointer"])
        proposal = read(ROOT / HKG10[1])
        (result,) = proposal["results"]
        lot = proposal["evidence"][0]["metadata"]
        self.assertEqual(result["location_basis"], "official_parcel")
        self.assertIn("EPSG:2326", lot["source_crs"])
        self.assertEqual(lot["coordinate_transformation"]["operation_accuracy_metres"], 1.0)
        ring = result["geometry"]["coordinates"][0]
        self.assertEqual(len(ring), lot["source_ring_vertex_count"])
        self.assertEqual(len(ring), 14)
        self.assertTrue(core._ring(ring))
        self.assertTrue(all(len(repr(v).split(".")[1]) <= 7 for point in ring for v in point))
        self.assertEqual(result["display_anchor"]["coordinates"], shoelace(ring))
        self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], ring))
        self.assertIn("463000472    A", proposal["evidence"][1]["metadata"]["literal_pointer"])
        self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])

    def test_lahr_point_is_the_official_inspire_address_position(self):
        proposal = read(ROOT / LAHR[1])
        (result,) = proposal["results"]
        point = proposal["evidence"][0]["metadata"]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": [7.8169919, 48.362257]})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "official_address_geocode")
        self.assertEqual(point["selected_point_lon_lat"], [7.8169919, 48.362257])
        self.assertEqual(point["native_xy"], [412373.215, 5357240.995])
        self.assertIn("EPSG:25832", point["source_crs"])
        self.assertIn("ETRS89 to WGS 84 (1)", point["transformation"])
        self.assertEqual(point["address_components_resolved"]["house_number"], "14")
        self.assertEqual(proposal["evidence"][0]["license"], "dl-de/by-2-0")
        self.assertFalse(any("osm" in key for key in result["geometry_source_ids"]))
        self.assertEqual(read(ROOT / LAHR[0])["evidence"][1]["metadata"]["site_address"].split(",")[0], "Einsteinallee 14")

    def test_raiden_polygon_is_the_named_kml_plot_bounded_by_the_ec(self):
        proposal = read(ROOT / RAIDEN[1])
        (result,) = proposal["results"]
        kml = proposal["evidence"][0]["metadata"]
        self.assertEqual(kml["selected_placemark"], "Raiden Plot Boundary")
        ring = result["geometry"]["coordinates"][0]
        self.assertEqual(ring, [[float(v) for v in t.split(",")[:2]] for t in kml["source_coordinate_tuples"]])
        self.assertEqual(len(ring), 9)
        self.assertTrue(core._ring(ring))
        self.assertEqual(result["display_anchor"]["coordinates"], shoelace(ring))
        self.assertTrue(core._inside_ring(result["display_anchor"]["coordinates"], ring))
        self.assertEqual(result["location_basis"], "official_named_site_feature")
        ec = read(ROOT / RAIDEN[0])["evidence"][3]["metadata"]
        self.assertEqual(ec["proposal_no"], "SIA/MH/INFRA2/531703/2025")
        self.assertTrue(core._inside_ring(ec["site_coordinate_decimal_lon_lat"], ring))
        self.assertLess(abs(kml["geodesic_area_square_metres_wgs84"] - ec["plot_area_m2_as_issued"]) / ec["plot_area_m2_as_issued"], 0.002)

    def test_audits_hold_packet_and_unadmitted_candidates(self):
        raw = (previous.draft_path(ROOT) / "sites.geojson").read_bytes()
        for path in AUDITS:
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn(".claude", text)
            audit = json.loads(text)
            review = audit["distinctness_review"]
            self.assertEqual(review["sites"], 197)
            self.assertEqual(review["geojson_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(review["full_geometry_intersections"], [])
            self.assertEqual(review["alias_matches"], [])
            self.assertFalse(audit["accepted_into_core"])
            for entry in audit.get("round43_apac_lane_other_decisions", []) + audit.get("round43_lane_holds", []):
                self.assertTrue(entry["note_path"].startswith(HOLDS + "#/"))
                decision = resolve(entry["note_path"])["decision"]
                self.assertEqual(decision.split("_")[0], entry["disposition"].split("_")[0])
        text = (ROOT / HOLDS).read_text(encoding="utf-8")
        self.assertNotIn(".claude", text)
        self.assertNotIn("/Users/", text)
        packet = json.loads(text)
        self.assertFalse(packet["accepted_into_core"])
        self.assertEqual(packet["accepted_additional_sites"], 0)
        groups = ("reserve_not_admitted", "holds", "rejections", "cross_lane_findings")
        ids = [item["id"] for group in groups for item in packet[group]]
        self.assertEqual(len(ids), len(set(ids)))
        captures = [c for group in groups for item in packet[group] for c in item.get("captures", [])]
        captures += [c for item in packet["holds"] for sub in item.get("candidates", []) for c in sub.get("captures", [])]
        self.assertGreater(len(captures), 60)
        for capture in captures:
            self.assertTrue(capture["path"].startswith("tmp/research-round4"))
            self.assertRegex(capture["sha256"], r"^[0-9a-f]{64}$")
        accepted = {a["parent_campus_stable_key"] for a in read(batch.contract_path(ROOT))["acceptances"]}
        (armstrong,) = packet["reserve_not_admitted"]
        self.assertNotIn(armstrong["campus_stable_key"], accepted)
        held = {item.get("campus_stable_key") for item in packet["holds"]} - {None}
        self.assertIn("curated:google-meitner-energy-center-data-center", held)
        self.assertFalse(held & accepted)
        self.assertFalse((ROOT / "sources/curated-official-2026-10-02-asia-round42-raiden-turbhe-current-build.json").exists())

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
        frozen_kinds = {row["kind"] for row in table(ROOT / core.BASELINE_RELATIVE_DIR / "evidence.csv")}
        for index, spec in enumerate(contract["sources"][PREVIOUS_SOURCES:]):
            raw = (ROOT / spec["path"]).read_bytes()
            self.assertEqual(len(raw), spec["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
            value = json.loads(raw)
            for token in spec["evidence_pointer"].strip("/").split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            date_only = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["retrieved_at"]) is not None
            core._source_evidence(value, spec["source_id"], inherited_date_only_retrieval=date_only)
            self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
            if index < ADMISSION_SOURCES:
                EvidenceKind(value["kind"])
                self.assertFalse(date_only)
                self.assertFalse(value["metadata"]["request_credentials_supplied"])
                self.assertFalse(value["metadata"]["raw_capture_redistributed"])
            else:
                # The correction keeps the frozen capture's own vocabulary rather than renaming it.
                self.assertEqual(spec["path"], CGK_RECORD)
                self.assertIn(value["kind"], frozen_kinds | {kind.value for kind in EvidenceKind})
                self.assertEqual(date_only, spec["source_id"] == "cgk-giic-host-estate-context")

    def test_correction_record_is_pinned_and_supersession_is_explicit(self):
        raw = (ROOT / CGK_RECORD).read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (78791, CGK_RECORD_SHA))
        self.assertNotIn(b".claude", raw)
        record = json.loads(raw)
        self.assertEqual(record["accepted_additional_sites"], 0)
        review_paths = record["raw_review_paths"]
        for path in review_paths["scan_scripts"] + review_paths["scan_outputs"]:
            # Ignored local copies, recorded with the workspace's absolute tmp/ path convention.
            self.assertRegex(path, r"^/.+/tmp/research-round43-cgk/review-scripts/[a-z_]+\.(py|json|out)$")
        invariants = record["preservation_invariants"]
        self.assertEqual(invariants["intersecting_site_rows_unchanged"], [STT_SITE])
        self.assertEqual(invariants["osm_way_version_unchanged"], 13)
        self.assertNotIn("stt_jakarta_rows_unchanged", invariants)
        for name in ("projects.csv", "sites.csv"):
            table_name = name.removesuffix(".csv")
            self.assertLessEqual(set(record["exact_row_deltas"][name]["unchanged_includes"]),
                                 set(core.TABLE_FIELDS[table_name]))
        precision = record["results"][0]["semantics"]["precision_scope"]
        self.assertIn("458-vertex community polygon (a closed way of 459 node references)", precision)
        self.assertIn("planar centroid of the estate's longitude/latitude ring", precision)
        self.assertNotIn("projected", precision)
        supersedes = record["supersedes"]
        old = read(ROOT / supersedes["source_path"])
        self.assertEqual(hashlib.sha256((ROOT / supersedes["source_path"]).read_bytes()).hexdigest(),
                         supersedes["source_file_sha256"])
        superseded = core._pointer(old, supersedes["evidence_pointer"])
        self.assertEqual(core.canonical_sha256(superseded), supersedes["evidence_record_sha256"])
        self.assertEqual(superseded["evidence_id"], SUPERSEDED)
        for field in ("source_url", "content_hash", "retrieved_at", "published_at", "license"):
            self.assertEqual(superseded[field], record["evidence"][0][field])
        reused = core._source_evidence(record["evidence"][0], "cgk", inherited_date_only_retrieval=True)
        self.assertEqual(reused["evidence_id"], CGK_ADDED[0])
        self.assertEqual(core._pointer(old, supersedes["geometry_pointer"])["geometry_source_document_id"],
                         superseded["source_id"])
        through = supersedes["inherited_unchanged_through"]
        self.assertEqual(through["release_path"], previous.DRAFT_RELATIVE_PATH)
        self.assertEqual(hashlib.sha256((previous.draft_path(ROOT) / "manifest.json").read_bytes()).hexdigest(),
                         through["manifest_sha256"])
        contract = read(batch.contract_path(ROOT))
        (correction,) = contract["baseline_corrections"]
        self.assertEqual(correction["frozen_rows"], supersedes["frozen_baseline_rows"])
        self.assertEqual(dict(batch.REVIEW_PINS.baseline_correction_sha256),
                         {CORRECTION_ID: core.canonical_sha256(correction)})
        self.assertNotIn(correction["identity_source_id"], {s["source_id"] for s in contract["sources"]})
        packet = read(ROOT / CGK_PACKET)["candidate"]
        self.assertEqual(packet["correction_record_draft"], CGK_RECORD)
        self.assertEqual(packet["correction_record_draft_sha256"], CGK_RECORD_SHA)

    def test_preceding_rows_change_only_by_the_enumerated_cgk_deltas(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        deltas = read(ROOT / CGK_RECORD)["exact_row_deltas"]
        for name, key, special in (("projects.csv", "project_stable_key", CGK_PROJECT),
                                   ("sites.csv", "physical_site_stable_key", CGK_SITE)):
            current = {x[key]: x for x in table(after / name)}
            for row in table(before / name):
                changed = {f: [v, current[row[key]][f]] for f, v in row.items() if current[row[key]][f] != v}
                self.assertEqual(changed, deltas[name]["changed"] if row[key] == special else {}, row[key])
            for field in ("latitude", "longitude", "geometry_json", "geometry_type"):
                self.assertEqual(
                    {r[key]: r for r in table(before / name)}[special][field], current[special][field]
                )
            removed = lines(before / name) - lines(after / name)
            self.assertEqual(sum(removed.values()), 1)
            self.assertTrue(next(iter(removed)).startswith(
                ("b2e4945f" if name == "projects.csv" else "vcc-site-f42f9f22874b1766554e").encode()))
        current = {x["evidence_id"]: x for x in table(after / "evidence.csv")}
        self.assertNotIn(SUPERSEDED, current)
        for identifier in CGK_ADDED:
            self.assertEqual(json.loads(current[identifier]["roles_json"]), ["geometry"])
            self.assertEqual(json.loads(current[identifier]["project_ids_json"]), [CGK_PROJECT_ID])
        for row in table(before / "evidence.csv"):
            if row["evidence_id"] == SUPERSEDED:
                continue
            changed = {f for f, v in row.items() if current[row["evidence_id"]][f] != v}
            self.assertEqual(changed, {"project_ids_json"} if row["evidence_id"] == SHARED_CRS else set())
        self.assertEqual(json.loads(current[SHARED_CRS]["project_ids_json"]),
                         sorted(json.loads({r["evidence_id"]: r for r in table(before / "evidence.csv")}[SHARED_CRS]["project_ids_json"]) + [CGK_PROJECT_ID]))
        self.assertEqual(sum((lines(before / "evidence.csv") - lines(after / "evidence.csv")).values()), 2)
        old_features = read(before / "sites.geojson")["features"]
        new_features = read(after / "sites.geojson")["features"]
        for index, feature in enumerate(old_features):
            if index != 34:
                self.assertIn(feature, new_features)
        old, new = old_features[34], new_features[34]
        self.assertEqual(old["geometry"], new["geometry"])
        self.assertEqual({k: v for k, v in old.items() if k != "properties"}, {k: v for k, v in new.items() if k != "properties"})
        self.assertEqual({k: [v, new["properties"][k]] for k, v in old["properties"].items() if new["properties"][k] != v},
                         deltas["sites.geojson"]["changed_properties"])
        old_contract, new_contract = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        self.assertEqual(old_contract["sources"], new_contract["sources"][:PREVIOUS_SOURCES])
        for key, pin in previous.REVIEW_PINS.source_sha256.items():
            self.assertEqual(pin, batch.REVIEW_PINS.source_sha256[key])
        for original, current_acceptance in zip(old_contract["acceptances"], new_contract["acceptances"], strict=False):
            current_acceptance["distinctness_review"]["batch_site_keys_sha256"] = original["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(original, current_acceptance)

    def test_cgk_is_host_estate_context_and_the_only_intersecting_pair(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        old_projects = {r["project_stable_key"]: r for r in table(before / "projects.csv")}
        projects = {r["project_stable_key"]: r for r in table(after / "projects.csv")}
        cgk = projects[CGK_PROJECT]
        self.assertEqual((cgk["geometry_use_scope"], cgk["geometry_source_entity_kind"], cgk["verification_posture"]),
                         ("host_estate_context", "host_estate", HOST_POSTURE))
        self.assertTrue(core._is_reviewed_locator(old_projects[CGK_PROJECT]))
        self.assertFalse(core._is_reviewed_locator(cgk))
        self.assertFalse(core.core._is_official_boundary(cgk))
        new_keys = set(projects) - set(old_projects)
        self.assertEqual(len(new_keys), 3)
        would_be = sum(map(core._is_reviewed_locator, old_projects.values())) + sum(
            core._is_reviewed_locator(projects[key]) for key in new_keys)
        actual = read(after / "manifest.json")["counts"]["reviewed_site_locator_projects"]
        self.assertEqual((would_be, actual), (198, 197))
        self.assertEqual(Counter(r["verification_posture"] for r in projects.values())[HOST_POSTURE], 1)
        self.assertEqual({r["physical_site_stable_key"]: r for r in table(before / "sites.csv")}[STT_SITE],
                         {r["physical_site_stable_key"]: r for r in table(after / "sites.csv")}[STT_SITE])
        report = read(after / "selection-report.json")
        self.assertEqual(report["format"], "datacenter-atlas-v018-draft-selection-v2")
        exceptions = report["locator_exceptions"]
        self.assertEqual(exceptions["host_estate_context_projects"], 1)
        (exception,) = exceptions["projects"]
        self.assertEqual(exception["project_stable_key"], CGK_PROJECT)
        self.assertEqual(exception["geometry_intersects_site_keys"], [STT_SITE])
        self.assertFalse(exception["counted_as_reviewed_site_locator"])
        self.assertFalse(exception["display_anchor_is_site_position"])
        (correction,) = report["baseline_corrections"]
        self.assertEqual(correction["count_effect"], read(ROOT / CGK_RECORD)["exact_row_deltas"]["counts_relative_to_thirty_fifth"])
        self.assertEqual(correction["evidence_rows"], {
            "removed": [SUPERSEDED], "added": sorted(CGK_ADDED), "association_only": [SHARED_CRS],
        })
        geometries = {r["physical_site_stable_key"]: json.loads(r["geometry_json"]) for r in table(after / "sites.csv")}
        self.assertEqual(len(geometries), 200)
        pairs = [pair for pair in combinations(sorted(geometries), 2)
                 if core._geometries_intersect(geometries[pair[0]], geometries[pair[1]])]
        self.assertEqual(pairs, [(CGK_SITE, STT_SITE)])
        located = {r["physical_site_stable_key"] for r in projects.values()
                   if core._is_reviewed_locator(r) or core.core._is_official_boundary(r)}
        self.assertEqual(set(geometries) - located, {CGK_SITE})

    def test_eleven_artifacts_reproduce_and_final_gates_stay_unmet(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        report = read(stored / "selection-report.json")
        self.assertFalse(report["objective_completion_claim"])
        gates = report["final_release_gates"]
        self.assertEqual(gates["site_count"], {"actual": 200, "required": 200, "passed": True})
        self.assertEqual(gates["additional_site_count"], {"actual": 100, "required": 100, "passed": True})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 203, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 203)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        self.assertFalse(gates["blind_review"]["passed"])
        self.assertFalse(gates["clean_clone_rebuild"]["passed"])
        self.assertFalse(gates["publication_authorized"]["passed"])
        provenance = read(stored / "review-provenance.json")
        self.assertEqual(provenance["independent_baseline_correction_review_sha256"],
                         dict(batch.REVIEW_PINS.baseline_correction_sha256))
        readme = (stored / "README.md").read_text(encoding="utf-8")
        self.assertIn("host-estate locality context only", readme)
        self.assertIn("1 superseded evidence row dropped; and 1 shared evidence row gaining only the "
                      "corrected project association.", readme)
        with tempfile.TemporaryDirectory(prefix="atlas-thirty-sixth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
