"""56-addition checkpoint: honest date precision and exact source-bound locators."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirteenth_reviewed as batch
from datacenter_atlas import expansion_200_twelfth_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
CURATED = (
    SOURCES / "curated-official-2026-09-09-chesterfield-round14-peanut-july-build.json",
    SOURCES / "curated-official-2026-09-09-chesterfield-round14-chirisa-digital-drive-july-build.json",
    SOURCES / "curated-official-2026-09-09-europe-mena-round12-noris-nbg6-ba3-current-build.json",
)
GEOMETRY = (
    SOURCES / "verified-construction-core-v0.18-chesterfield-round14-geometry-proposal.json",
    SOURCES / "verified-construction-core-v0.18-europe-mena-round12-noris-nbg6-ba3-geometry-proposal.json",
)
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirteenthReviewedDraftTests(unittest.TestCase):
    def test_month_precision_does_not_invent_a_work_day_or_new_site_per_building(self) -> None:
        for path in CURATED[:2]:
            with self.subTest(path=path):
                doc = read(path)
                status, evidence = doc["lifecycle"][0], doc["evidence"][0]
                self.assertEqual(status["value"], "under_construction")
                self.assertEqual(status["as_of_date"], "2026-07-01")
                self.assertIsNone(evidence["published_at"])
                meta = evidence["metadata"]
                self.assertEqual(meta["status_date_precision"], "month")
                self.assertEqual(meta["source_observation_interval"], ["2026-07-01", "2026-07-31"])
                self.assertIn("not an asserted observation day", meta["status_as_of_normalization"])
                self.assertIn("count", meta["campus_scope"].lower())
        peanut, chirisa = (read(p) for p in CURATED[:2])
        old = read(SOURCES / "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json")
        for entity in ("campus", "project"):
            self.assertEqual(peanut[entity]["stable_key"], old[entity]["stable_key"])
        self.assertIn("CTP/DDC", chirisa["evidence"][0]["metadata"]["identity_inference"])
        self.assertIn("operating CTP", chirisa["evidence"][0]["metadata"]["identity_inference"])

    def test_noris_original_post_and_cross_document_phase_identity_are_explicit(self) -> None:
        doc = read(CURATED[2])
        evidence = doc["evidence"][0]
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-08-13")
        self.assertEqual(evidence["published_at"], "2026-08-13T08:32:16Z")
        self.assertEqual(evidence["metadata"]["publication_timestamp_literal"], "2026-08-13T08:32:16.762Z")
        self.assertIn("does not print NBG6 or BA3", evidence["metadata"]["identity_inference"])
        self.assertIn("analyst inference", evidence["metadata"]["identity_inference"])
        self.assertIn("second IT area", evidence["excerpt"])
        self.assertNotIn("second IT floor", evidence["excerpt"])
        self.assertIn("one physical NBG6 campus", doc["evidence"][1]["metadata"]["campus_grouping"])
        eco = read(GEOMETRY[1])["evidence"][5]
        self.assertEqual(eco["kind"], "other")
        self.assertIn("No lifecycle assertion", eco["metadata"]["date_guardrail"])

    def test_source_specific_points_keep_rights_authority_and_accuracy_limits(self) -> None:
        county, noris = (read(p) for p in GEOMETRY)
        expected = [
            (county, 0, "round14-peanut-county-centroid", [-77.30489173364066, 37.34632783459711], "CC0-1.0", "official_source"),
            (county, 1, "round14-chirisa-county-address-centroid", [-77.33425619418317, 37.356171271028536], "CC0-1.0", "official_source"),
            (noris, 0, "europe12-noris-nbg6-ba3-community-point", [11.1314551, 49.4100304], "ODbL-1.0", "community_source"),
        ]
        for doc, index, key, point, license_name, authority in expected:
            evidence = next(e for e in doc["evidence"] if e["key"] == key)
            result = doc["results"][index]
            self.assertEqual(evidence["license"], license_name)
            self.assertTrue(evidence["attribution"])
            self.assertEqual(evidence["metadata"]["source_crs"], "EPSG:4326")
            self.assertEqual(result["geometry"], {"type": "Point", "coordinates": point})
            self.assertEqual(result["display_anchor"], result["geometry"])
            semantics = result["semantics"]
            self.assertEqual(semantics["geometry_authority_class"], authority)
            self.assertEqual(semantics["geometry_use_scope"], "campus_locator")
            self.assertIsNone(semantics["horizontal_uncertainty_metres"])
            self.assertIn("boundary", semantics["precision_scope"])
            draft._geometry(result)
        ev = {e["key"]: e for e in county["evidence"]}
        self.assertIn("caac62a09b49446b8a20744963ba1d23", ev["round14-county-exact-layer-catalog-binding"]["excerpt"])
        self.assertEqual(ev["round14-county-open-gis-cc0-terms"]["metadata"]["visually_reviewed_pdf_pages"], [1])
        self.assertIn("821655752900001", ev["round14-chirisa-county-address-centroid"]["metadata"]["identifier_caveat"])
        self.assertEqual(ev["round14-chirisa-county-address-centroid"]["metadata"]["selected_feature"]["OBJECTID"], 148078)
        self.assertEqual(noris["evidence"][1]["metadata"]["selected_tags"]["name"], "noris network NBG6 BA3")

    def test_intake_adds_no_unsupported_roles_metrics_workloads_or_geometry(self) -> None:
        for path in CURATED:
            with self.subTest(path=path):
                curated._parse_document(path, "2026-09-09T04:00:00Z")
                doc = read(path)
                self.assertEqual(len(doc["lifecycle"]), 1)
                for entity in ("campus", "project"):
                    self.assertEqual(doc[entity]["roles"], {})
                    self.assertIsNone(doc[entity]["coordinates"])
                    self.assertIsNone(doc[entity]["geometry"])
                for field in ("workloads", "capacities", "operating_models"):
                    self.assertEqual(doc[field], [])

    def test_three_new_campuses_and_twenty_seven_new_bindings_are_closed(self) -> None:
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 56)
        self.assertEqual(len(validated.sources), 326)
        old_ids = {s["source_id"] for s in old["sources"]}
        ids = {s["source_id"] for s in new["sources"]}
        proposed = {b["source_id"] for p in GEOMETRY for b in read(p)["source_binding_map"]}
        self.assertEqual(ids - old_ids, proposed)
        self.assertEqual(len(ids - old_ids), 27)
        for field, entity in (("project_stable_key", "project"), ("parent_campus_stable_key", "campus")):
            new_keys = {a[field] for a in new["acceptances"]}
            old_keys = {a[field] for a in old["acceptances"]}
            self.assertEqual(new_keys - old_keys, {read(p)[entity]["stable_key"] for p in CURATED})
            self.assertEqual(len(new_keys - old_keys), 3)

    def test_every_previous_row_feature_source_and_acceptance_is_preserved(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key in (("projects.csv", "project_stable_key"),
                              ("sites.csv", "physical_site_stable_key"), ("evidence.csv", "evidence_id")):
            current = {row[key]: row for row in table(new_dir / filename)}
            for row in table(old_dir / filename):
                self.assertEqual(row, current[row[key]])
        for feature in read(old_dir / "sites.geojson")["features"]:
            self.assertIn(feature, read(new_dir / "sites.geojson")["features"])
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
            "physical_sites": 156, "projects": 159, "evidence": 562,
            "countries": 41, "non_us_sites": 105,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 154,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 56, "required": 100, "passed": False})
        self.assertEqual(gates["site_count"], {"actual": 156, "required": 200, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 159, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 159)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        for gate in ("blind_review", "clean_clone_rebuild", "publication_authorized"):
            self.assertFalse(gates[gate]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-fifty-six-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
