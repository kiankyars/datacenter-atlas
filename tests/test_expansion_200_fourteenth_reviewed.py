"""59-addition checkpoint: primary work reports and scoped reusable locators."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse

from datacenter_atlas import expansion_200_fourteenth_reviewed as batch
from datacenter_atlas import expansion_200_thirteenth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = (
    SOURCES / "curated-official-2026-09-09-core-scientific-pecos-round15-ceo-current-build.json",
    SOURCES / "curated-official-2026-09-09-americas-round15-lake-mariner-cb5-current-build.json",
    SOURCES / "curated-official-2026-09-09-europe-round15-csc-lumi-ai-current-build.json",
)
GEOMETRY = (
    SOURCES / "verified-construction-core-v0.18-pecos-round15-reviewed-geometry.json",
    SOURCES / "verified-construction-core-v0.18-americas-round15-lake-mariner-geometry-proposal.json",
    SOURCES / "verified-construction-core-v0.18-europe-round15-csc-lumi-ai-geometry-proposal.json",
)
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FourteenthReviewedDraftTests(unittest.TestCase):
    def test_exact_fresh_dates_use_primary_current_work_not_retrieval_or_forecasts(self) -> None:
        expected = (
            ("2026-06-02", "2026-06-02T16:10:25Z", "www.linkedin.com"),
            ("2026-08-05", "2026-08-05T11:00:00Z", "investors.terawulf.com"),
            ("2026-08-20", "2026-08-20T09:33:31Z", "csc.fi"),
        )
        for path, (day, published_at, host) in zip(CURATED, expected, strict=True):
            with self.subTest(path=path):
                doc = read(path)
                evidence, status = doc["evidence"][0], doc["lifecycle"][0]
                self.assertEqual(evidence["kind"], "company_disclosure")
                self.assertEqual(evidence["published_at"], published_at)
                self.assertEqual(urlparse(evidence["source_url"]).hostname, host)
                self.assertEqual(status["value"], "under_construction")
                self.assertEqual(status["as_of_date"], day)
                self.assertEqual(status["method"], "authoritative_physical_status_update")
                self.assertEqual(status["evidence_key"], evidence["key"])
                self.assertGreaterEqual(day, "2026-05-22")
                self.assertLessEqual(day, "2026-08-20")
                self.assertNotEqual(day, evidence["retrieved_at"][:10])

    def test_pecos_executive_authority_and_contrary_transcript_scope_are_retained(self) -> None:
        doc, geometry = read(CURATED[0]), read(GEOMETRY[0])
        status, authority = doc["evidence"]
        meta = status["metadata"]
        self.assertEqual(meta["publication_timestamp_literal"], "2026-06-02T16:10:25.494Z")
        self.assertEqual(meta["author_profile_url"], "https://www.linkedin.com/in/adamtsullivan")
        self.assertIn("adamtsullivan", authority["metadata"]["source_pointer"])
        self.assertIn("April 27", meta["authority_bridge"])
        self.assertTrue(meta["transcript_not_selected_for_lifecycle"])
        self.assertIn("building fully complete", meta["contrary_evidence"])
        self.assertIn("not whole-HDC completion", meta["contrary_evidence"])
        evidence = {e["key"]: e for e in geometry["evidence"]}
        caveat = evidence["am15-pecos-july-transcript-completion-caveat"]
        self.assertEqual(caveat["kind"], "news")
        self.assertFalse(caveat["metadata"]["lifecycle_selected"])
        speakers = {speaker["name"]: speaker for speaker in caveat["metadata"]["speakers"]}
        self.assertEqual(set(speakers), {"Adam Sullivan", "Matt Brown"})
        self.assertEqual(speakers["Adam Sullivan"]["role"], "Chief Executive Officer")
        self.assertEqual(speakers["Adam Sullivan"]["attributed_clause"], "building fully complete")
        self.assertEqual(speakers["Adam Sullivan"]["questioner_label"], "Darren Aftahi")
        self.assertEqual(speakers["Matt Brown"]["role"], "Chief Operating Officer")
        self.assertIn("full shell due in coming weeks", speakers["Matt Brown"]["attributed_clause"])
        self.assertEqual(speakers["Matt Brown"]["questioner_label"], "John Peterson")
        self.assertIn("not audio-verified identities", caveat["metadata"]["source_pointer"])
        self.assertIn("not listened to", caveat["metadata"]["transcript_review_limitations"])
        self.assertEqual(caveat["metadata"]["primary_replacement_source_id"], status["key"])
        self.assertIn(caveat["key"], geometry["extra_review_source_ids"])
        self.assertNotIn(caveat["key"], geometry["results"][0]["identity_source_ids"])
        self.assertIn("Cottonwood1and2", evidence["am15-pecos-owner-campus-alias"]["metadata"]["campus_scope"])
        self.assertIn("do not count a second campus", evidence["am15-pecos-osm-exact-relation-tags"]["metadata"]["scope"])
        self.assertEqual(geometry["existing_seed_identity"]["stable_key"], "osm:relation/20669718")
        self.assertEqual(geometry["existing_seed_identity"]["entity_kind"], "facility")

    def test_cb5_address_interpolation_excludes_cb3_and_preserves_epoch_campus(self) -> None:
        doc, geometry = read(CURATED[1]), read(GEOMETRY[1])
        status = doc["evidence"][0]
        self.assertIn("currently ongoing construction", status["metadata"]["observation_date_basis"])
        self.assertIn("Delivered CB-3", status["metadata"]["excluded_scope"])
        self.assertIn("not inherited by CB-5", status["metadata"]["excluded_scope"])
        address, locator = geometry["evidence"][:2]
        self.assertIn("colocation building number 5 at 7725 Lake Road", address["excerpt"])
        self.assertIn("not a corporate mailing address", address["metadata"]["identity_scope"])
        meta = locator["metadata"]
        self.assertEqual(meta["match_count"], 1)
        self.assertEqual(meta["matched_address"], "7725 LAKE RD, BARKER, NY, 14012")
        self.assertEqual((meta["from_address"], meta["to_address"], meta["side"]), ("7809", "7701", "R"))
        self.assertEqual((meta["source_crs"], meta["output_crs"]), ("EPSG:4269", "EPSG:4326"))
        transform = meta["transformation"]
        self.assertTrue(transform["executed"])
        self.assertEqual(transform["pyproj_version"], "3.8.0")
        self.assertEqual(transform["operation_epsg"], 1188)
        self.assertEqual(transform["reported_operation_accuracy_metres"], 4)
        self.assertIn("not the unknown accuracy", transform["accuracy_caveat"])
        self.assertEqual(meta["source_coordinates_xy"], transform["output_coordinates_xy"])
        self.assertEqual(geometry["results"][0]["geometry"]["coordinates"], transform["output_coordinates_xy"])
        self.assertEqual(geometry["evidence"][2]["metadata"]["visually_reviewed_pdf_pages"], [2, 9])
        self.assertIn("No federal rights inferred for private issuer", meta["rights_scope"])
        old_identity = geometry["distinctness_review"]["old_inventory"]
        old_review = SOURCES / "satellite-change-blind-review-2026-07-20-open-seed-v57-single-tile-v1.json"
        self.assertIn(json.dumps(old_identity["stable_key"]), old_review.read_text(encoding="utf-8"))
        self.assertEqual(old_identity["name"], "Fluidstack Lake Mariner")
        self.assertEqual(doc["campus"]["stable_key"], old_identity["stable_key"])
        self.assertEqual(doc["project"]["stable_key"], old_identity["stable_key"] + ":cb-5-current-build")

    def test_csc_same_hall_identity_preserves_keys_and_community_locator_limits(self) -> None:
        doc, geometry = read(CURATED[2]), read(GEOMETRY[2])
        old = read(SOURCES / "curated-official-2026-07-19-csc-lumi-ai-kajaani.json")
        for entity in ("campus", "project"):
            self.assertEqual(doc[entity]["stable_key"], old[entity]["stable_key"])
        current, identity, address = doc["evidence"]
        self.assertEqual(current["metadata"]["modification_timestamp_literal"], "2026-08-20T09:50:34+00:00")
        self.assertIn("March 2026", current["metadata"]["imagery_guardrail"])
        self.assertIn("not promoted to an August observation", current["metadata"]["imagery_guardrail"])
        self.assertIn("share that same hall", identity["excerpt"])
        self.assertIn("no extra site or project", identity["metadata"]["identity_scope"])
        self.assertIn("Tehdaskatu 15", address["excerpt"])
        point, way = geometry["evidence"][:2]
        self.assertEqual(point["metadata"]["source_result_count"], 1)
        tags = way["metadata"]["selected_tags"]
        self.assertEqual((tags["name"], tags["alt_name"], tags["addr:housenumber"]), ("CSC", "LUMI", "15"))
        self.assertNotIn("operator", tags)
        self.assertNotIn("telecom", tags)
        self.assertIn("not a claim that CSC published this coordinate", way["metadata"]["identity_inference"])
        checks = geometry["independent_geometry_checks"]
        self.assertTrue(checks["provider_point_inside_source_ring"])
        self.assertTrue(checks["csc_and_xtx_bounding_boxes_disjoint"])
        self.assertFalse(checks["candidate_inside_any_of_156_selected_polygon_or_multipolygon_geometries"])

    def test_intake_adds_no_roles_metrics_workloads_or_false_geometry_precision(self) -> None:
        expected = (
            ([-103.8026586, 31.5341897], "community_source", "campus_locator", 3),
            ([-78.602908090738, 43.348937013719], "official_source", "project_locator", 1),
            ([27.691477, 64.2319866], "community_source", "campus_locator", 0),
        )
        for path, geometry_path, (point, authority, use, evidence_index) in zip(CURATED, GEOMETRY, expected, strict=True):
            with self.subTest(path=path):
                curated._parse_document(path, "2026-09-09T05:00:00Z")
                doc, geometry = read(path), read(geometry_path)
                self.assertEqual(len(doc["lifecycle"]), 1)
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("workloads", "capacities", "operating_models"):
                    self.assertEqual(doc[field], [])
                self.assertEqual(len(geometry["results"]), 1)
                result = geometry["results"][0]
                self.assertEqual(result["geometry"], {"type": "Point", "coordinates": point})
                self.assertEqual(result["display_anchor"], result["geometry"])
                semantics = result["semantics"]
                self.assertEqual(semantics["geometry_authority_class"], authority)
                self.assertEqual(semantics["geometry_use_scope"], use)
                self.assertIsNone(semantics["horizontal_uncertainty_metres"])
                self.assertIn("boundary", semantics["precision_scope"])
                self.assertTrue(semantics["horizontal_uncertainty_unknown_reason"])
                locator = geometry["evidence"][evidence_index]
                self.assertTrue(locator["attribution"])
                if authority == "community_source":
                    self.assertEqual(locator["license"], "ODbL-1.0")
                    self.assertEqual(locator["metadata"]["source_crs"], "EPSG:4326")
                    self.assertEqual(result["location_basis"], "community_named_site_feature")
                else:
                    self.assertEqual(result["location_basis"], "official_address_geocode")
                draft._geometry(result)

    def test_three_new_campuses_and_twenty_seven_source_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 59)
        self.assertEqual(len(validated.sources), 353)
        self.assertEqual([len(read(p)["evidence"]) for p in CURATED], [2, 1, 3])
        self.assertEqual([len(read(p)["evidence"]) for p in GEOMETRY], [10, 6, 5])
        old_ids = {s["source_id"] for s in old["sources"]}
        sources = {s["source_id"]: s for s in new["sources"]}
        bindings = [b for p in GEOMETRY for b in read(p)["source_binding_map"]]
        proposed_ids = {b["source_id"] for b in bindings}
        self.assertEqual(len(bindings), 27)
        self.assertEqual(len(proposed_ids), 27)
        self.assertEqual(set(sources) - old_ids, proposed_ids)
        for binding in bindings:
            with self.subTest(source_id=binding["source_id"]):
                source = sources[binding["source_id"]]
                self.assertEqual(source["path"], binding["path"])
                self.assertEqual(source["evidence_pointer"], binding["evidence_pointer"])
        for field, entity in (("project_stable_key", "project"), ("parent_campus_stable_key", "campus")):
            new_keys = {a[field] for a in new["acceptances"]}
            old_keys = {a[field] for a in old["acceptances"]}
            self.assertEqual(new_keys - old_keys, {read(p)[entity]["stable_key"] for p in CURATED})
            self.assertEqual(len(new_keys - old_keys), 3)
        for curated_path, geometry_path in zip(CURATED, GEOMETRY, strict=True):
            doc = read(curated_path)
            status_id = next(b["source_id"] for b in read(geometry_path)["source_binding_map"]
                             if ROOT / b["path"] == curated_path and b["evidence_pointer"] == "/evidence/0")
            acceptance = next(a for a in new["acceptances"] if a["project_stable_key"] == doc["project"]["stable_key"])
            self.assertEqual(acceptance["status"]["source_id"], status_id)
            self.assertEqual(acceptance["status"]["record_pointer"], "/lifecycle/0")

    def test_every_previous_row_feature_source_and_acceptance_is_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(new_dir / filename)}
            for row in table(old_dir / filename):
                self.assertEqual(row, current[row[key]])
        old_features = read(old_dir / "sites.geojson")["features"]
        new_features = read(new_dir / "sites.geojson")["features"]
        for feature in old_features:
            self.assertIn(feature, new_features)
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
            "physical_sites": 159, "projects": 162, "evidence": 589,
            "countries": 41, "non_us_sites": 106,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 157,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 59, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 159, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 162, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 162)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-fifty-nine-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
