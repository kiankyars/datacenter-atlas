from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from datacenter_atlas import verified_construction_core as verified_core
from datacenter_atlas.verified_construction_core import (
    CURRENT_V12_PREVIEW_DIR,
    CURRENT_V12_PREVIEW_ID,
    LEGACY_PREVIEW_V11_DIR,
    LEGACY_PREVIEW_V11_MANIFEST_SHA256,
    V12_BATCH_CONTRACT,
    V12_BATCH_CONTRACT_SHA256,
    V12_GEOMETRY_CAPTURE,
    V12_GEOMETRY_CAPTURE_SHA256,
    V12_GEOMETRY_EVIDENCE_ID,
    V12_PROJECT_KEYS,
    VerifiedConstructionCoreError,
    validate_frozen_v11,
    validate_preview,
)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class VerifiedConstructionCoreV012Tests(unittest.TestCase):
    def test_profile_counts_census_geometry_and_claim_scope(self) -> None:
        self.assertEqual(CURRENT_V12_PREVIEW_ID, "2026-08-20-preview-v0.12")
        self.assertEqual(CURRENT_V12_PREVIEW_DIR.name, CURRENT_V12_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v11()["preview_id"],
            "2026-08-20-preview-v0.11",
        )
        manifest = validate_preview(CURRENT_V12_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V11_MANIFEST_SHA256,
        )
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 53,
                "projects": 56,
                "evidence": 129,
                "countries": 26,
                "non_us_sites": 40,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 51,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 81)
        self.assertEqual(
            hashlib.sha256(V12_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V12_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(V12_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V12_GEOMETRY_CAPTURE_SHA256,
        )

        contract = json.loads(V12_BATCH_CONTRACT.read_text(encoding="utf-8"))
        capture = json.loads(V12_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        expected_coordinates = {
            "coreweave-lancaster-216-greenfield-road": (
                -76.25609093817,
                40.048690947149,
            ),
            "lancium-abilene-617-fm-2404": (
                -99.774790370504,
                32.509551980071,
            ),
            "ntt-dallas-2060-lookout-drive": (
                -96.654368299801,
                32.982500800175,
            ),
            "qts-york-2143-hands-mill-highway": (
                -81.103431663732,
                35.035399273352,
            ),
            "trg-hou2-2626-spring-cypress-road": (
                -95.455736245303,
                30.066026434779,
            ),
        }
        self.assertEqual(capture["benchmark"], "Public_AR_Current")
        self.assertEqual(capture["match_status"], "Match")
        self.assertEqual(
            {
                row["locator_id"]: (row["longitude"], row["latitude"])
                for row in capture["results"]
            },
            expected_coordinates,
        )
        self.assertEqual(len(contract["acceptances"]), 5)
        self.assertEqual(
            {row["project_stable_key"] for row in contract["acceptances"]},
            V12_PROJECT_KEYS,
        )
        self.assertTrue(
            all(
                row["relationship"]
                == {
                    "relationship_id": row["relationship"]["relationship_id"],
                    "relationship_type": "project_targets",
                    "decision_basis": "explicit_parent",
                }
                for row in contract["acceptances"]
            )
        )
        ntt = next(
            row
            for row in contract["acceptances"]
            if row["project_stable_key"].endswith(":tx4")
        )
        qts = next(
            row
            for row in contract["acceptances"]
            if row["project_stable_key"].startswith("curated:qts-york")
        )
        self.assertIn("2060 Lookout Drive", ntt["scope_guardrail"])
        self.assertIn("2008 Lookout Drive", ntt["scope_guardrail"])
        self.assertEqual(qts["address_scope"], "parent_campus_only")

        locators = {row["locator_id"]: row for row in capture["results"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V12_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V12_PROJECT_KEYS
        }
        self.assertEqual(set(projects), V12_PROJECT_KEYS)
        for acceptance in contract["acceptances"]:
            project = projects[acceptance["project_stable_key"]]
            longitude, latitude = expected_coordinates[acceptance["locator_id"]]
            self.assertEqual(float(project["longitude"]), longitude)
            self.assertEqual(float(project["latitude"]), latitude)
            self.assertEqual(
                json.loads(project["geometry_json"]),
                {
                    "coordinates": [
                        locators[acceptance["locator_id"]]["longitude"],
                        locators[acceptance["locator_id"]]["latitude"],
                    ],
                    "type": "Point",
                },
            )
            self.assertEqual(
                project["physical_site_stable_key"],
                acceptance["parent_campus_stable_key"],
            )
            self.assertEqual(
                project["last_observed_physical_status"],
                acceptance["status"]["value"],
            )
            self.assertEqual(
                project["status_evidence_id"],
                acceptance["status"]["evidence_id"],
            )
            self.assertEqual(project["geometry_source_entity_kind"], "campus")
            self.assertEqual(project["geometry_derivation"], "official_address_geocode")
            self.assertEqual(
                project["geometry_method"],
                "census_public_ar_current_street_range_interpolation",
            )
            self.assertEqual(project["geometry_use_scope"], "campus_locator")
            self.assertEqual(project["independent_imagery_verification"], "false")
            for field in (
                "workloads_json",
                "role_claims_json",
                "power_observations_json",
                "annual_energy_observations_json",
                "efficiency_observations_json",
            ):
                self.assertEqual(project[field], "[]", field)
            for field in ("owner", "operator", "users", "tenants", "customers"):
                self.assertEqual(project[field], "", field)

        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V12_PREVIEW_DIR, "evidence.csv")
        }
        geometry_evidence = evidence[V12_GEOMETRY_EVIDENCE_ID]
        self.assertEqual(json.loads(geometry_evidence["roles_json"]), ["geometry"])
        self.assertEqual(
            set(json.loads(geometry_evidence["project_ids_json"])),
            {row["project_id"] for row in projects.values()},
        )
        for name in ("README.md", "ATTRIBUTION.txt", "map.html"):
            text = (CURRENT_V12_PREVIEW_DIR / name).read_text(encoding="utf-8")
            self.assertIn("Census Geocoder Public_AR_Current", text)

    def test_inherits_v011_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V11_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V12_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited}, inherited
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V11_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V12_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        inherited_features = {
            row["properties"]["site_id"]: row for row in inherited_geojson["features"]
        }
        current_features = {
            row["properties"]["site_id"]: row for row in current_geojson["features"]
        }
        self.assertEqual(
            {site_id: current_features[site_id] for site_id in inherited_features},
            inherited_features,
        )

    def test_partial_hydration_fails_closed(self) -> None:
        contract = json.loads(V12_BATCH_CONTRACT.read_text(encoding="utf-8"))
        bindings = contract["hydrated_crosscheck_inputs"]
        present = verified_core.ROOT / bindings[0]["path"]
        missing = verified_core.ROOT / bindings[1]["path"]
        original_is_file = Path.is_file

        def partial_is_file(path: Path) -> bool:
            if path == present:
                return True
            if path == missing:
                return False
            return original_is_file(path)

        with (
            mock.patch.object(Path, "is_file", partial_is_file),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.12 hydrated cross-check inputs are only partially present",
            ),
        ):
            verified_core._v12_hydrated_crosscheck_available(contract)

    def test_contract_semantics_fail_closed(self) -> None:
        altered = json.loads(V12_BATCH_CONTRACT.read_text(encoding="utf-8"))
        altered["geometry_semantics"]["official_boundary"] = 0
        original_load = verified_core._load_json

        def load_altered(path: Path) -> object:
            if Path(path).resolve() == V12_BATCH_CONTRACT.resolve():
                return altered
            return original_load(path)

        with (
            mock.patch.object(verified_core, "_load_json", side_effect=load_altered),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError, "v0.12 geometry semantics differ"
            ),
        ):
            verified_core._v12_contracts()

    def _assert_rebuild_is_byte_exact(self, *, corpus_free: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            if corpus_free:
                with mock.patch.object(
                    verified_core,
                    "_v12_hydrated_crosscheck_available",
                    return_value=False,
                ):
                    verified_core.build_preview(rebuilt)
            else:
                verified_core.build_preview(rebuilt)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in CURRENT_V12_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V12_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = json.loads(V12_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v12_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)


if __name__ == "__main__":
    unittest.main()
