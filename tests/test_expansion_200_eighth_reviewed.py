"""43-addition checkpoint: explicit identity, datum and retrospective-date bounds."""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_eighth_reviewed as batch
from datacenter_atlas import expansion_200_seventh_reviewed as previous
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
LAGOS = SOURCES / "verified-construction-core-v0.18-africa-round7-nxtra-los1-geometry-proposal.json"
SUMARE = SOURCES / "verified-construction-core-v0.18-regions-round8-sumare-geometry-proposal.json"
LUEBBENAU = SOURCES / "verified-construction-core-v0.18-europe-round7-luebbenau-address-geometry-proposal.json"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class EighthReviewedDraftTests(unittest.TestCase):
    def test_three_packages_keep_physical_dates_and_unknown_fields(self) -> None:
        expected = {
            "africa-round7-nxtra-los1-current-build": "2026-07-23",
            "regions-round8-ascenty-sumare3-current-build": "2026-05-28",
            "europe-round7-luebbenau-current-build": "2026-08-18",
        }
        for name, day in expected.items():
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            doc = read(path)
            curated._parse_document(path, "2026-09-08T22:55:00Z")
            self.assertEqual(len(doc["lifecycle"]), 1)
            self.assertEqual(doc["lifecycle"][0]["as_of_date"], day)
            self.assertEqual(doc["lifecycle"][0]["value"], "under_construction")
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_bindings_are_closed_and_points_are_only_campus_locators(self) -> None:
        validated = draft.validate_batch(batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(len(validated.acceptances), 43)
        self.assertEqual(len(validated.sources), 223)
        for row in validated.acceptances[-3:]:
            acceptance, geometry = row["acceptance"], row["geometry"]
            self.assertIn(acceptance["identity"]["source_id"], geometry["identity_source_ids"])
            self.assertEqual(geometry["geometry"]["type"], "Point")
            self.assertEqual(geometry["semantics"]["geometry_authority_class"], "official_source")
            self.assertEqual(geometry["semantics"]["geometry_use_scope"], "campus_locator")
            self.assertIsNone(geometry["semantics"]["horizontal_uncertainty_metres"])
            draft._geometry(geometry)

    def test_lagos_preserves_explicit_inference_and_exact_operator_marker(self) -> None:
        doc = read(LAGOS)
        geometry = doc["results"][0]
        self.assertIn("explicit analyst inference", doc["root_review"]["identity_review"])
        self.assertIn("not LOS1", doc["root_review"]["identity_review"])
        self.assertEqual(geometry["geometry"]["coordinates"], [3.42139, 6.4175])
        self.assertEqual(geometry["location_basis"], "first_party_site_coordinate")
        self.assertEqual(set(geometry["geometry_source_ids"]),
                         {"nxtra-los1-operator-point", "nxtra-map-wgs84"})
        self.assertIn("nxtra-rights", geometry["identity_source_ids"])
        self.assertEqual(doc["evidence"][0]["metadata"]["literal_lat_lon"], [6.4175, 3.42139])

    def test_sumare_binds_marker_trace_and_ceo_authority_without_new_footprint(self) -> None:
        doc = read(SUMARE)
        geometry = doc["results"][0]
        self.assertEqual(geometry["geometry"]["coordinates"], [-47.212871, -22.812328])
        self.assertEqual(geometry["location_basis"], "first_party_site_coordinate")
        self.assertTrue({f"sumare-coordinate-contract-{i}" for i in range(1, 6)}
                        <= set(geometry["geometry_source_ids"]))
        self.assertIn("sumare-ceo-authority", geometry["identity_source_ids"])
        self.assertIn("not the SUM03 building", geometry["semantics"]["precision_scope"])
        self.assertEqual(doc["evidence"][6]["publisher"], "Google")
        self.assertEqual(doc["evidence"][6]["license"], "CC-BY-4.0")
        curated = read(SOURCES / "curated-official-2026-09-08-regions-round8-ascenty-sumare3-current-build.json")
        self.assertEqual(curated["evidence"][2]["key"], "regions8-ascenty-ceo-authority-code-conduct")
        self.assertIsNone(curated["evidence"][2]["published_at"])

    def test_luebbenau_keeps_later_publication_and_address_precision_limits(self) -> None:
        doc = read(LUEBBENAU)
        geometry = doc["results"][0]
        curated = read(SOURCES / "curated-official-2026-09-08-europe-round7-luebbenau-current-build.json")
        self.assertEqual(curated["evidence"][0]["published_at"], "2026-08-24")
        self.assertEqual(curated["lifecycle"][0]["as_of_date"], "2026-08-18")
        self.assertEqual(doc["evidence"][0]["metadata"]["object_id"], "DEBBAL01000d9qPu")
        self.assertEqual(doc["evidence"][0]["metadata"]["source_matches"], 1)
        self.assertEqual(doc["evidence"][0]["metadata"]["source_crs"], "EPSG:4326")
        self.assertEqual(geometry["geometry"]["coordinates"], [13.960999567308617, 51.84710977414326])
        self.assertEqual(geometry["location_basis"], "official_address_geocode")
        self.assertIn("parcel point", geometry["semantics"]["precision_scope"])
        self.assertIn("lgb-search-rights", geometry["geometry_source_ids"])

    def test_held_mixed_use_roadworks_have_no_lifecycle_and_are_not_admitted(self) -> None:
        held = read(SOURCES / "curated-official-2026-09-08-europe-round7-heusenstamm-site-works.json")
        self.assertEqual(held["lifecycle"], [])
        accepted = read(batch.contract_path(ROOT))["acceptances"]
        self.assertNotIn(held["campus"]["stable_key"],
                         {row["parent_campus_stable_key"] for row in accepted})
        self.assertEqual(read(SOURCES / "research-expansion-200-equinix-q2-root-review-2026-09-08.json")
                         ["decision"], "hold_not_admitted")

    def test_every_previous_row_feature_binding_and_acceptance_is_preserved(self) -> None:
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

    def test_exact_rebuild_reaches_non_us_threshold_but_remains_partial(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 143, "projects": 146, "evidence": 459,
            "countries": 41, "non_us_sites": 101,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 141,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 43, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 146, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 146)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-forty-three-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
