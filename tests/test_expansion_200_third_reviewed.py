"""Twenty-site checkpoint: exact admissions and one explicit datum correction."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_second_reviewed as previous
from datacenter_atlas import expansion_200_third_reviewed as batch
from datacenter_atlas import verified_construction_core as core
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
EUROPE = SOURCES / "verified-construction-core-v0.18-europe-next-three-reviewed-geometry.json"
MADRID = SOURCES / "verified-construction-core-v0.18-iron-madrid-geometry-facts.json"
US = SOURCES / "verified-construction-core-v0.18-iron-mountain-us-three-geometry-facts.json"
PAJU = SOURCES / "verified-construction-core-v0.18-lg-uplus-paju-reviewed-geometry.json"
HELIOS = SOURCES / "verified-construction-core-v0.18-helios-census-datum-correction-v2.json"
HELIOS_PROJECT = "curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build"
HELIOS_SITE = "curated:galaxy-helios-data-center-campus"
OLD_LOCATOR_ID = "7704fbf3-5115-594f-a369-d6d02cc6b821"
NEW_LOCATOR_ID = "50b56d5c-226f-57f8-b2b1-9d79212c26eb"
DATUM_ID = "69ecb4cd-be02-55fa-b978-732f307eeb00"
curated = importlib.import_module(f"{core.__package__}.curated_v11")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ThirdReviewedDraftTests(unittest.TestCase):
    def test_eight_new_source_packages_do_not_invent_fields(self) -> None:
        names = [
            "goodman-mad01-madrid-reviewed-build",
            "iron-mountain-lon3-reviewed-build",
            "iron-mountain-amsterdam-reviewed-build",
            "iron-mountain-madrid-reviewed-build",
            "iron-mountain-va-9-phase-1-q2-current-build",
            "iron-mountain-mia-1-miami-q2-current-build",
            "iron-mountain-nje-1-new-jersey-q2-current-build",
            "lg-uplus-paju-current-build-and-parcel-bridge",
        ]
        for name in names:
            path = SOURCES / f"curated-official-2026-09-08-{name}.json"
            curated._parse_document(path, "2026-09-08T20:29:00Z")
            doc = read(path)
            self.assertEqual(len(doc["lifecycle"]), 1)
            observation = doc["lifecycle"][0]
            self.assertEqual(observation["value"], "under_construction")
            self.assertEqual(observation["method"], "authoritative_physical_status_update")
            self.assertEqual(observation["as_of_date"],
                             "2026-06-05" if name.startswith("lg-uplus") else "2026-06-30")
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
                self.assertIsNone(doc[entity]["geometry"])
            for field in ("workloads", "capacities", "operating_models"):
                self.assertEqual(doc[field], [])

    def test_europe_exact_points_and_inferred_alias_scope(self) -> None:
        europe = read(EUROPE)
        self.assertEqual([r["geometry"]["coordinates"] for r in europe["results"]], [
            [-3.546397, 40.444143],
            [-0.6200648150277306, 51.520247952919846],
            [4.664735411619385, 52.39172475368806],
        ])
        self.assertIn("analyst identity inference", europe["results"][2]["semantics"]["precision_scope"])
        self.assertIn("20 MW held-development", europe["results"][2]["semantics"]["precision_scope"])
        old = read(SOURCES / "curated-official-2026-07-20-iron-mountain-ams-2-amsterdam.json")
        new = read(SOURCES / "curated-official-2026-09-08-iron-mountain-amsterdam-reviewed-build.json")
        self.assertEqual(new["evidence"][2:], old["evidence"][1:])
        contract = read(batch.contract_path(ROOT))
        accepted = next(a for a in contract["acceptances"] if "ams-2-10mw" in a["project_stable_key"])
        self.assertIn("earlier March 31", accepted["distinctness_review"]["reason"])
        self.assertIn("identity only", accepted["distinctness_review"]["reason"])

    def test_iron_madrid_is_one_campus_at_exact_portal_four(self) -> None:
        doc = read(MADRID)
        match = doc["evidence"][0]["metadata"]["selected_result"]
        self.assertEqual(match["id"], "13.PV.MUN_281300326955")
        self.assertEqual(match["portalNumber"], 4)
        self.assertEqual(match["refCatastral"], "7989302VK5778N")
        self.assertEqual(doc["results"][0]["geometry"]["coordinates"],
                         [-3.498520384597765, 40.458191566488146])
        self.assertEqual(doc["evidence"][0]["metadata"]["source_crs"], "EPSG:4326")
        self.assertIn("cartociudad-service-crs", doc["results"][0]["geometry_source_ids"])
        selected = [a for a in read(batch.contract_path(ROOT))["acceptances"]
                    if a["parent_campus_stable_key"] == "curated:iron-mountain-madrid-data-center-campus"]
        self.assertEqual(len(selected), 1)
        self.assertIn("mad-2-mad-3", selected[0]["project_stable_key"])

    def test_census_source_datum_is_not_site_accuracy(self) -> None:
        doc = read(US)
        expected = [
            [-77.542924596694, 38.772750339621],
            [-80.247555757503, 25.88415986431],
            [-74.327943023032, 40.529931107088],
        ]
        for index, point in enumerate(expected):
            transform = doc["evidence"][index + 6]["metadata"]["transformation"]
            self.assertEqual(transform["source_crs"], "EPSG:4269")
            self.assertEqual(transform["target_crs"], "EPSG:4326")
            self.assertEqual(transform["source_point"], point)
            self.assertEqual(transform["wgs84_lon_lat"], point)
            self.assertIn("NAD83 to WGS 84 (1)", transform["operation"])
            self.assertIsNone(transform["horizontal_uncertainty_metres"])
            self.assertEqual(doc["results"][index]["geometry"]["coordinates"], point)
            self.assertIn("us2-census-datum-faq", doc["results"][index]["geometry_source_ids"])
        self.assertIn("VA-9's 11530 Elevate Drive address was not matched", doc["results"][0]["semantics"]["precision_scope"])
        self.assertEqual(doc["evidence"][9], read(HELIOS)["evidence"][1])

    def test_paju_joins_exact_parcel_and_unique_historical_factory(self) -> None:
        doc = read(SOURCES / "curated-official-2026-09-08-lg-uplus-paju-current-build-and-parcel-bridge.json")
        self.assertEqual(doc["project"]["country"], "Korea, Republic of")
        self.assertEqual(doc["project"]["evidence_key"], doc["evidence"][5]["key"])
        register = doc["evidence"][2]["metadata"]
        self.assertEqual(register["factory_name"], "희성전자(주)")
        self.assertIn("1239-1", register["factory_parcel_address"])
        self.assertEqual(register["site_area_square_metres"], 73712.2)
        self.assertEqual(register["site_area_square_metres"], doc["evidence"][1]["metadata"]["site_area_square_metres"])
        self.assertIn("row3841", register["literal_pointer"])
        self.assertEqual(doc["evidence"][5]["metadata"]["attachment_uuid"],
                         "f85cdfff-69e1-4e2c-85d9-3b625cc99ed0")
        self.assertIn("noncommercial", doc["evidence"][5]["license"])
        locator = read(PAJU)
        self.assertEqual(locator["results"][0]["geometry"]["coordinates"], [126.7561012, 37.8141287])
        self.assertEqual(locator["evidence"][0]["license"], "ODbL-1.0")
        self.assertEqual(locator["evidence"][1]["metadata"]["selected_tags"]["name"], "희성전자")
        self.assertEqual(locator["results"][0]["semantics"]["geometry_authority_class"], "community_source")
        self.assertIn("not the current AIDC footprint", locator["results"][0]["semantics"]["precision_scope"])

    def test_every_new_locator_is_scoped_and_has_unknown_accuracy(self) -> None:
        for path in (EUROPE, MADRID, US, PAJU, HELIOS):
            for locator in read(path)["results"]:
                draft._geometry(locator)
                self.assertEqual(locator["semantics"]["geometry_use_scope"], "campus_locator")
                self.assertIsNone(locator["semantics"]["horizontal_uncertainty_metres"])
                self.assertTrue(locator["semantics"]["horizontal_uncertainty_unknown_reason"])

    def test_helios_supersession_is_explicit_and_raw_capture_unchanged(self) -> None:
        doc = read(HELIOS)
        supersedes = doc["supersedes"]
        path = ROOT / supersedes["source_path"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), supersedes["source_file_sha256"])
        old = read(path)
        self.assertEqual(draft.canonical_sha256(old["evidence"][11]), supersedes["evidence_record_sha256"])
        self.assertEqual(draft.canonical_sha256(old["results"][3]), supersedes["geometry_record_sha256"])
        for field in ("source_url", "content_hash", "retrieved_at"):
            self.assertEqual(old["evidence"][11][field], doc["evidence"][0][field])
        self.assertEqual(old["results"][3]["geometry"], doc["results"][0]["geometry"])
        self.assertNotEqual(old["evidence"][11]["key"], doc["evidence"][0]["key"])
        self.assertEqual(doc["accepted_additional_sites"], 0)

    def test_earlier_rows_change_only_for_documented_provenance(self) -> None:
        old_dir, new_dir = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for filename, key, special, allowed in (
            ("projects.csv", "project_stable_key", HELIOS_PROJECT, {"geometry_method", "geometry_evidence_id"}),
            ("sites.csv", "physical_site_stable_key", HELIOS_SITE, {"geometry_methods_json", "geometry_evidence_ids_json"}),
        ):
            current = {r[key]: r for r in table(new_dir / filename)}
            for row in table(old_dir / filename):
                changed = {k for k, value in row.items() if current[row[key]][k] != value}
                self.assertEqual(changed, allowed if row[key] == special else set())
        projects = {r["project_stable_key"]: r for r in table(new_dir / "projects.csv")}
        self.assertEqual(projects[HELIOS_PROJECT]["geometry_evidence_id"], NEW_LOCATOR_ID)
        self.assertEqual(projects[HELIOS_PROJECT]["geometry_method"],
                         "census_single_exact_address_match_then_explicit_nad83_to_wgs84")
        current = {r["evidence_id"]: r for r in table(new_dir / "evidence.csv")}
        self.assertNotIn(OLD_LOCATOR_ID, current)
        self.assertIn(NEW_LOCATOR_ID, current)
        self.assertIn(DATUM_ID, current)
        for row in table(old_dir / "evidence.csv"):
            if row["evidence_id"] == OLD_LOCATOR_ID:
                continue
            changed = {k for k, value in row.items() if current[row["evidence_id"]][k] != value}
            shared_crs = row["evidence_id"] == "4791ed5e-b266-5f0f-b86f-d183cc829ba2"
            self.assertEqual(changed, {"project_ids_json"} if shared_crs else set())
            if shared_crs:
                self.assertEqual(json.loads(current[row["evidence_id"]]["project_ids_json"]),
                                 ["e3f1fc38-bc59-5373-803f-d5c86d817096", "f8900f55-087d-5d51-aef2-820402bcbdc2"])
        for feature in read(old_dir / "sites.geojson")["features"]:
            self.assertIn(feature, read(new_dir / "sites.geojson")["features"])

    def test_checkpoint_rebuilds_exactly_and_remains_partial(self) -> None:
        stored = batch.draft_path(ROOT)
        manifest = draft.validate_draft(stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 120, "projects": 123, "evidence": 329,
            "countries": 40, "non_us_sites": 83,
            "official_boundary_projects": 5, "reviewed_site_locator_projects": 118,
        })
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["additional_site_count"], {"actual": 20, "required": 100, "passed": False})
        self.assertEqual(gates["imagery_outcomes_complete"], {"actual": 10, "required": 123, "passed": False})
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 123)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        with tempfile.TemporaryDirectory(prefix="atlas-twenty-rebuild-") as temp:
            output = Path(temp) / "draft"
            draft.build_draft(batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT)
            self.assertEqual(len(list(stored.iterdir())), 11)
            self.assertEqual({p.name for p in stored.iterdir()}, {p.name for p in output.iterdir()})
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
