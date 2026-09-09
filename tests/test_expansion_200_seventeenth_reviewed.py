"""62-addition checkpoint: one Greenergy expansion, with source-language limits."""

from __future__ import annotations

from collections import Counter
import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse

from datacenter_atlas import expansion_200_seventeenth_reviewed as batch
from datacenter_atlas import expansion_200_sixteenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = SOURCES / "curated-official-2026-09-09-europe-round18-greenergy-huuru-current-build.json"
GEOMETRY = SOURCES / "verified-construction-core-v0.18-europe-round18-greenergy-huuru-geometry-proposal.json"
RESEARCH = SOURCES / "research-expansion-200-europe-round18-2026-09-09.json"
POINT = [24.561964619163426, 59.38609935]
RING = [
    [24.5603585, 59.3862645], [24.5607717, 59.3864269],
    [24.5610488, 59.3865382], [24.5612947, 59.3866324],
    [24.5615371, 59.3867253], [24.5615638, 59.3867382],
    [24.5616475, 59.3867711], [24.5619097, 59.3868742],
    [24.5631593, 59.3869654], [24.5636093, 59.3854234],
    [24.5616562, 59.3849227], [24.5615261, 59.3850573],
    [24.5612997, 59.3852914], [24.5606759, 59.3859342],
    [24.5603585, 59.3862645],
]
NODE_IDS = [
    9606202019, 9606202075, 9606202060, 9606202081, 9606202061,
    9606202091, 9606202036, 9606202020, 9606202021, 9606202022,
    9606202023, 9606202042, 9606202055, 9606202058, 9606202019,
]
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def interior_scanline_point(ring: list[list[float]]) -> list[float]:
    """Reproduce this enclosure's widest interior scanline without a GIS package."""
    latitudes = [coordinate[1] for coordinate in ring[:-1]]
    middle = (min(latitudes) + max(latitudes)) / 2
    below = max(latitude for latitude in latitudes if latitude <= middle)
    above = min(latitude for latitude in latitudes if latitude > middle)
    latitude = (below + above) / 2
    crossings = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > latitude) != (y2 > latitude):
            crossings.append(x1 + (latitude - y1) * (x2 - x1) / (y2 - y1))
    crossings.sort()
    if not crossings or len(crossings) % 2:
        raise AssertionError("Closed enclosure has invalid scanline intersections")
    intervals = list(zip(crossings[::2], crossings[1::2]))
    left, right = max(intervals, key=lambda interval: interval[1] - interval[0])
    if not left < right:
        raise AssertionError("Representative point has no interior interval")
    return [(left + right) / 2, latitude]


class SeventeenthReviewedDraftTests(unittest.TestCase):
    def test_direct_preparatory_work_wins_over_staffing_and_language_caveats(self) -> None:
        doc = read(CURATED)
        english, finnish, owner = doc["evidence"]
        status = doc["lifecycle"][0]
        self.assertEqual(english["kind"], "company_disclosure")
        self.assertEqual(urlparse(english["source_url"]).hostname, "www.caverion.com")
        self.assertEqual(urlparse(finnish["source_url"]).hostname, "www.caverion.fi")
        for evidence in (english, finnish):
            self.assertEqual(evidence["published_at"], "2026-07-31")
            self.assertEqual(evidence["metadata"]["date_precision"], "day")
            self.assertEqual(evidence["metadata"]["publication_date_literal"], "31.07.2026")
        self.assertIn("employed on site", english["excerpt"])
        self.assertFalse(english["metadata"]["lifecycle_selected"])
        self.assertIn("Context only", english["metadata"]["lifecycle_basis"])
        caveat = english["metadata"]["wording_caveat"]
        self.assertIn("Finnish release", caveat)
        self.assertIn("omits on site", caveat)
        self.assertIn("future tense", caveat)
        self.assertFalse(finnish["metadata"]["lifecycle_selected"])
        self.assertIn("not as a second physical-work observation", finnish["metadata"]["translation_caveat"])
        self.assertIn("no current headcount is accepted", caveat)
        self.assertEqual(owner["kind"], "company_disclosure")
        self.assertEqual(urlparse(owner["source_url"]).hostname, "tensor.estate")
        self.assertEqual(owner["published_at"], "2026-07-30")
        self.assertEqual(owner["metadata"]["date_precision"], "day")
        self.assertIn("preparatory construction work has already begun", owner["metadata"]["lifecycle_basis"])
        self.assertIn("selected conservatively as site_preparation", owner["metadata"]["lifecycle_basis"])
        self.assertIn("English translation", owner["metadata"]["translation_caveat"])
        self.assertIn("was not obtained or inspected", owner["metadata"]["translation_caveat"])
        self.assertIn("not a verified July current workforce count", owner["metadata"]["staffing_caveat"])
        self.assertEqual(status["value"], "site_preparation")
        self.assertEqual(status["as_of_date"], "2026-07-30")
        self.assertEqual(status["evidence_key"], owner["key"])
        self.assertEqual(status["method"], "authoritative_physical_status_update")
        self.assertGreaterEqual(status["as_of_date"], "2026-05-22")
        self.assertLessEqual(status["as_of_date"], "2026-08-20")
        self.assertNotEqual(status["as_of_date"], owner["retrieved_at"][:10])
        self.assertIn("not an independently known construction-start day", owner["metadata"]["date_semantics"])

    def test_existing_operating_halls_are_not_selected_as_new_construction(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        contact, context = geometry["evidence"][:2]
        self.assertIn("Office / Data Center", contact["excerpt"])
        self.assertIn("Alajaama tee 1", contact["excerpt"])
        self.assertIn("not an assumed company-office geocode", contact["metadata"]["identity_scope"])
        self.assertIn("inside its existing building", context["excerpt"])
        self.assertFalse(context["metadata"]["lifecycle_selected"])
        self.assertEqual(context["metadata"]["date_precision"], "month")
        self.assertIsNone(context["published_at"])
        self.assertEqual(len(doc["lifecycle"]), 1)
        self.assertEqual(len(geometry["results"]), 1)
        self.assertIn("Existing operating halls are not treated as new construction", doc["evidence"][0]["metadata"]["scope_guardrail"])
        self.assertEqual(doc["project"]["stable_key"], doc["campus"]["stable_key"] + ":data-hall-expansion")
        rows = table(batch.draft_path(ROOT) / "projects.csv")
        additions = [row for row in rows if row["physical_site_stable_key"] == doc["campus"]["stable_key"]]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["project_stable_key"], doc["project"]["stable_key"])
        self.assertEqual(additions[0]["status_as_of"], "2026-07-30")
        self.assertEqual(additions[0]["last_observed_physical_status"], "site_preparation")

    def test_exact_osm_nodes_reproduce_interior_point_without_raw_capture_or_gis(self) -> None:
        geometry = read(GEOMETRY)
        osm = geometry["evidence"][2]
        meta = osm["metadata"]
        self.assertEqual(osm["kind"], "openstreetmap")
        self.assertEqual(urlparse(osm["source_url"]).path, "/api/0.6/way/1043819046/full.json")
        self.assertEqual(meta["source_feature_id"], 1043819046)
        self.assertEqual(meta["source_feature_version"], 3)
        self.assertEqual(meta["source_feature_timestamp"], "2024-04-18T20:30:43Z")
        self.assertEqual(meta["source_node_count_including_closure"], 15)
        self.assertEqual(meta["source_node_ids"], NODE_IDS)
        self.assertEqual(meta["source_ring_coordinates"], RING)
        self.assertEqual(len(set(NODE_IDS[:-1])), 14)
        self.assertEqual(RING[0], RING[-1])
        computed = interior_scanline_point(meta["source_ring_coordinates"])
        for actual, expected in zip(computed, POINT, strict=True):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertEqual(meta["output_reference_point"], POINT)
        self.assertEqual(meta["source_crs"], "EPSG:4326")
        self.assertEqual(meta["output_crs"], "EPSG:4326")
        self.assertEqual(meta["output_coordinate_order"], "longitude,latitude")
        self.assertIn("no CRS transformation", meta["geometry_derivation"])
        tags = meta["source_tags"]
        self.assertEqual(tags["name"], "Greenergy Data Centers")
        self.assertEqual(tags["addr:street"], "Alajaama tee")
        self.assertEqual(tags["addr:housenumber"], "1")
        self.assertEqual(tags["addr:postcode"], "76911")
        self.assertEqual(tags["website"], "https://www.greenergydatacenters.com")
        self.assertEqual(tags["contact:phone"], "+372 7700 252")
        result = geometry["results"][0]
        self.assertEqual(result["geometry"], {"type": "Point", "coordinates": POINT})
        self.assertEqual(result["display_anchor"], result["geometry"])
        self.assertEqual(result["location_basis"], "community_named_site_feature")
        semantics = result["semantics"]
        self.assertEqual(semantics["geometry_authority_class"], "community_source")
        self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
        self.assertIsNone(semantics["horizontal_uncertainty_metres"])
        self.assertIn("not survey accuracy", semantics["horizontal_uncertainty_unknown_reason"])
        self.assertIn("Not a surveyed or official boundary", semantics["precision_scope"])
        draft._geometry(result)

    def test_odbl_scoped_rights_and_absence_of_new_roles_metrics_survive_export(self) -> None:
        doc, geometry = read(CURATED), read(GEOMETRY)
        curated._parse_document(CURATED, "2026-09-09T06:00:00Z")
        osm, rights, crs = geometry["evidence"][2:5]
        self.assertEqual(osm["license"], "ODbL-1.0")
        self.assertEqual(osm["attribution"], "OpenStreetMap contributors")
        self.assertEqual(osm["metadata"]["rights_url"], rights["source_url"])
        self.assertEqual(osm["metadata"]["license_url"], "https://opendatacommons.org/licenses/odbl/1-0/")
        self.assertIn("share-alike", rights["excerpt"])
        self.assertIn("not automatically to all other publishers", rights["metadata"]["rights_scope"])
        self.assertIn("WGS84 degrees", crs["excerpt"])
        self.assertIn("not a measured positional-accuracy claim", crs["metadata"]["rights_scope"])
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["roles"], {})
            self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(doc[entity]["geometry"])
        for field in ("capacities", "workloads", "operating_models"):
            self.assertEqual(doc[field], [])
        row = next(row for row in table(batch.draft_path(ROOT) / "projects.csv")
                   if row["project_stable_key"] == doc["project"]["stable_key"])
        for field in ("workloads_json", "role_claims_json", "power_observations_json",
                      "annual_energy_observations_json", "efficiency_observations_json"):
            self.assertFalse(json.loads(row[field]))
        for field in ("owner", "operator", "users", "tenants", "customers", "horizontal_uncertainty_metres"):
            self.assertEqual(row[field], "")
        self.assertEqual(row["operating_model"], "unknown")

    def test_one_new_campus_and_nine_new_source_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 62)
        self.assertEqual(len(validated.sources), 382)
        doc, geometry, research = read(CURATED), read(GEOMETRY), read(RESEARCH)
        self.assertEqual(len(doc["evidence"]), 3)
        self.assertEqual(len(geometry["evidence"]), 5)
        evidence = doc["evidence"] + geometry["evidence"] + [geometry["successor_evidence"]]
        old_ids = {source["source_id"] for source in old["sources"]}
        sources = {source["source_id"]: source for source in new["sources"]}
        keys = {item["key"] for item in evidence}
        self.assertEqual(len(keys), 9)
        self.assertEqual(set(sources) - old_ids, keys)
        bindings = research["source_binding_map"]
        self.assertEqual(set(bindings), keys)
        for item in evidence:
            with self.subTest(source=item["key"]):
                key = item["key"]
                self.assertRegex(item["content_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(item["metadata"]["content_hash_verification"], "fetched_bytes_sha256")
                self.assertGreater(item["metadata"]["raw_capture_bytes"], 0)
                self.assertFalse(item["metadata"]["request_credentials_supplied"])
                self.assertEqual(item["metadata"]["http_status"], 200)
                self.assertTrue(item["attribution"])
                self.assertTrue(item["metadata"]["rights_scope"])
                self.assertEqual(sources[key]["path"], bindings[key]["path"])
                self.assertEqual(sources[key]["evidence_pointer"], bindings[key]["pointer"])
                pointed = read(ROOT / bindings[key]["path"])
                for part in bindings[key]["pointer"].split("/")[1:]:
                    pointed = pointed[int(part)] if isinstance(pointed, list) else pointed[part]
                self.assertEqual(pointed, item)
                draft._source_evidence(item, key)
        result = geometry["results"][0]
        self.assertEqual(set(result["geometry_source_ids"] + result["identity_source_ids"]),
                         keys - {geometry["successor_evidence"]["key"]})
        additions = [acceptance for acceptance in new["acceptances"]
                     if acceptance["project_stable_key"] not in {a["project_stable_key"] for a in old["acceptances"]}]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["parent_campus_stable_key"], doc["campus"]["stable_key"])
        self.assertEqual(additions[0]["project_stable_key"], doc["project"]["stable_key"])
        self.assertEqual(additions[0]["status"]["source_id"], doc["evidence"][2]["key"])
        self.assertEqual(additions[0]["status"]["record_pointer"], "/lifecycle/0")
        self.assertEqual(set(additions[0]["distinctness_review"]["evidence_source_ids"]), keys)

    def test_direct_august_successor_and_review_addendum_do_not_refresh_lifecycle(self) -> None:
        doc, geometry, research = read(CURATED), read(GEOMETRY), read(RESEARCH)
        successor = geometry["successor_evidence"]
        self.assertEqual(successor["kind"], "company_disclosure")
        self.assertEqual(successor["published_at"], "2026-08-12")
        self.assertEqual(urlparse(successor["source_url"]).hostname, "tensor.estate")
        self.assertEqual(successor["metadata"]["date_precision"], "day")
        self.assertFalse(successor["metadata"]["lifecycle_selected"])
        self.assertEqual(successor["metadata"]["review_cutoff"], "2026-08-20")
        self.assertIn("scheduled for later in 2026", successor["excerpt"])
        self.assertIn("does not report that the expansion is complete or operating", successor["excerpt"])
        self.assertIn("Existing operating halls are not the expansion", successor["metadata"]["scope_guardrail"])
        self.assertIn("does not prove the absence", successor["metadata"]["scope_guardrail"])
        self.assertEqual(len(doc["lifecycle"]), 1)
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-07-30")
        review = research["root_review_addendum"]
        self.assertEqual(review["physical_status"], "site_preparation")
        self.assertEqual(review["selected_status_date"], "2026-07-30")
        self.assertEqual(review["selected_binding_count"], 9)
        self.assertEqual(review["raw_capture_count"], 11)
        self.assertEqual(review["superseded_provisional_screen"]["selected_status_date"], "2026-07-31")
        self.assertIn("supersedes the provisional staffing-only basis", review["change_basis"])

    def test_holds_and_javascript_shell_do_not_supply_selected_evidence(self) -> None:
        research, contract = read(RESEARCH), read(batch.contract_path(ROOT))
        self.assertEqual(len(research["proposals"]), 1)
        proposal = research["proposals"][0]
        self.assertEqual(proposal["dedup"]["baseline_sites_reviewed"], 161)
        self.assertEqual(proposal["dedup"]["point_intersections_with_selected_features"], [])
        self.assertEqual(proposal["dedup"]["full_enclosure_intersections_with_selected_features"], [])
        self.assertIn("Nebius Tallinn", proposal["dedup"]["alias_review"])
        sources = {source["source_id"] for source in contract["sources"]}
        selected = [capture for capture in research["raw_captures"] if capture["selected"]]
        self.assertEqual(len(selected), 9)
        for capture in selected:
            self.assertIn(capture["evidence_key"], sources)
        shell = next(capture for capture in research["raw_captures"]
                     if capture["tag"] == "greenergy-simmons-successor.html")
        self.assertFalse(shell["selected"])
        self.assertIsNone(shell["evidence_key"])
        self.assertIn("not the article", shell["body_caveat"])
        for hold in research["screened_holds"]:
            self.assertFalse(hold["selected_for_lifecycle"])
            self.assertIsNone(hold["coordinates"])
        dornan = research["screened_holds"][0]
        self.assertEqual(dornan["reported_physical_work_date"], "2026-07-29")
        self.assertEqual(dornan["publication_date"], "2026-08-26")
        self.assertEqual(dornan["decision"], "hold_named_identity_and_exact_locator")

    def test_every_previous_row_byte_feature_source_and_acceptance_is_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            old_path, new_path = old_dir / filename, new_dir / filename
            current = {row[key]: row for row in table(new_path)}
            for row in table(old_path):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(Counter(old_path.read_bytes().splitlines(keepends=True)),
                                 Counter(new_path.read_bytes().splitlines(keepends=True)))
        old_features = read(old_dir / "sites.geojson")["features"]
        new_features = read(new_dir / "sites.geojson")["features"]
        self.assertEqual(len(old_features), 161)
        self.assertEqual(len(new_features), 162)
        for feature in old_features:
            self.assertIn(feature, new_features)
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        for source in old["sources"]:
            self.assertIn(source, new["sources"])
        current = {acceptance["project_stable_key"]: acceptance for acceptance in new["acceptances"]}
        for acceptance in old["acceptances"]:
            updated = json.loads(json.dumps(current[acceptance["project_stable_key"]]))
            updated["distinctness_review"]["batch_site_keys_sha256"] = acceptance["distinctness_review"]["batch_site_keys_sha256"]
            self.assertEqual(updated, acceptance)

    def test_exact_eleven_artifact_rebuild_and_partial_release_gates(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 162, "projects": 165, "evidence": 618,
            "countries": 42, "non_us_sites": 108,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 160,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 62, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 162, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 165, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 165)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-sixty-two-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({path.name for path in stored.iterdir()}, {path.name for path in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
