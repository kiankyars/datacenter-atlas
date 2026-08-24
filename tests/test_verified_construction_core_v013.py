from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from datacenter_atlas import verified_construction_core as verified_core
from datacenter_atlas.verified_construction_core import (
    CURRENT_V13_PREVIEW_DIR,
    CURRENT_V13_PREVIEW_ID,
    LEGACY_PREVIEW_V12_COMMIT,
    LEGACY_PREVIEW_V12_DIR,
    LEGACY_PREVIEW_V12_MANIFEST_SHA256,
    V13_BATCH_CONTRACT,
    V13_BATCH_CONTRACT_SHA256,
    V13_CAPTURE_EVIDENCE_IDS,
    V13_GEOMETRY_CAPTURE,
    V13_GEOMETRY_CAPTURE_SHA256,
    V13_PROJECT_KEYS,
    VerifiedConstructionCoreError,
    build_v13_preview as build_preview,
    validate_frozen_v12,
    validate_preview,
)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class VerifiedConstructionCoreV013Tests(unittest.TestCase):
    def test_profile_counts_frozen_base_and_source_inventory(self) -> None:
        self.assertEqual(CURRENT_V13_PREVIEW_ID, "2026-08-20-preview-v0.13")
        self.assertEqual(CURRENT_V13_PREVIEW_DIR.name, CURRENT_V13_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v12()["preview_id"],
            "2026-08-20-preview-v0.12",
        )
        manifest = validate_preview(CURRENT_V13_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V12_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["base_preview_commit"], LEGACY_PREVIEW_V12_COMMIT)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 59,
                "projects": 62,
                "evidence": 145,
                "countries": 27,
                "non_us_sites": 46,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 57,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 89)
        self.assertEqual(
            hashlib.sha256(V13_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V13_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(V13_BATCH_CONTRACT.stat().st_size, 11_555)
        self.assertEqual(
            hashlib.sha256(V13_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V13_GEOMETRY_CAPTURE_SHA256,
        )
        self.assertEqual(V13_GEOMETRY_CAPTURE.stat().st_size, 52_229)
        portable_paths = {row["path"] for row in manifest["portable_source_inputs"]}
        self.assertIn(
            "definitions/verified-construction-core-v0.13-six-site-geometry-batch.json",
            portable_paths,
        )
        self.assertIn(
            "sources/verified-construction-core-v0.13-six-site-geometry-facts.json",
            portable_paths,
        )
        self.assertFalse(
            any(
                Path(path).suffix.lower() in {".pdf", ".html"}
                for path in portable_paths
            )
        )
        self.assertFalse(any("imagery" in path.lower() for path in portable_paths))

    def test_six_distinct_sites_have_exact_locator_and_status_scope(self) -> None:
        contract = json.loads(V13_BATCH_CONTRACT.read_text(encoding="utf-8"))
        capture = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        locators = {row["locator_id"]: row for row in capture["geometries"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V13_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V13_PROJECT_KEYS
        }
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V13_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(set(projects), V13_PROJECT_KEYS)
        self.assertEqual(len({row["site_id"] for row in projects.values()}), 6)
        self.assertEqual(
            {row["geometry_type"] for row in projects.values()},
            {"Point", "Polygon"},
        )
        self.assertEqual(
            sum(row["geometry_type"] == "Point" for row in projects.values()),
            3,
        )
        expected_ages = {
            "goodman-syd01-ssd-66777221-point": 31,
            "firstcolo-fra7-factsheet-point": 66,
            "xtx-kajaani-parcel-205-7-4-1": 56,
            "qts-cambois-wider-campus-ngr-point": 50,
            "bitzero-namsskogan-parcel-5044-50-44": 66,
            "ezditek-ruh01-osm-way-1544103564": 63,
        }
        for acceptance in contract["acceptances"]:
            project = projects[acceptance["project_stable_key"]]
            locator = locators[acceptance["locator_id"]]
            semantics = locator["semantics"]
            longitude, latitude = locator["display_anchor"]["coordinates"]
            self.assertEqual(json.loads(project["geometry_json"]), locator["geometry"])
            self.assertEqual(float(project["longitude"]), longitude)
            self.assertEqual(float(project["latitude"]), latitude)
            self.assertEqual(
                project["physical_site_stable_key"],
                acceptance["parent_campus_stable_key"],
            )
            self.assertEqual(
                project["last_observed_physical_status"],
                acceptance["status"]["value"],
            )
            self.assertEqual(
                project["status_as_of"], acceptance["status"]["as_of_date"]
            )
            self.assertEqual(
                project["status_evidence_id"], acceptance["status"]["evidence_id"]
            )
            self.assertEqual(
                int(project["status_age_days_at_review"]),
                expected_ages[acceptance["locator_id"]],
            )
            self.assertLessEqual(int(project["status_age_days_at_review"]), 90)
            for field in (
                "geometry_source_entity_kind",
                "geometry_derivation",
                "geometry_method",
                "geometry_scope_class",
                "geometry_authority_class",
                "geometry_use_scope",
            ):
                self.assertEqual(project[field], semantics[field], field)
            self.assertIs(semantics["official_boundary"], False)
            self.assertNotEqual(project["geometry_use_scope"], "official_boundary")
            self.assertEqual(
                project["geometry_precision_scope"], semantics["precision_scope"]
            )
            self.assertEqual(project["horizontal_uncertainty_metres"], "")
            self.assertTrue(project["horizontal_uncertainty_unknown_reason"])
            self.assertEqual(project["independent_imagery_verification"], "false")
            self.assertEqual(
                project["verification_posture"],
                "recent_authoritative_physical_observation_plus_reviewed_site_locator",
            )
            geometry_document = next(
                row
                for row in capture["source_documents"]
                if row["source_id"] == locator["geometry_source_document_id"]
            )
            geometry_evidence = evidence[geometry_document["evidence_id"]]
            self.assertIn("geometry", json.loads(geometry_evidence["roles_json"]))
            self.assertIn(
                project["project_id"], json.loads(geometry_evidence["project_ids_json"])
            )
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

    def test_cadastral_parcels_are_official_campus_locators_not_boundaries(
        self,
    ) -> None:
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V13_PREVIEW_DIR, "projects.csv")
        }
        expected = {
            "curated:xtx-markets-kajaani-data-center-campus:second-data-center": (
                "nls_official_cadastral_parcel_polygon_as_campus_locator",
                "official_cadastral_parcel_as_campus_locator",
            ),
            "curated:bitzero-namsskogan-data-center-campus:2026-power-infrastructure-expansion": (
                "kartverket_official_cadastral_parcel_polygon_as_campus_locator",
                "official_cadastral_parcel_as_campus_locator",
            ),
        }
        for project_key, (method, scope_class) in expected.items():
            project = projects[project_key]
            self.assertEqual(project["geometry_type"], "Polygon")
            self.assertEqual(project["geometry_authority_class"], "official_source")
            self.assertEqual(project["geometry_use_scope"], "campus_locator")
            self.assertEqual(project["geometry_method"], method)
            self.assertEqual(project["geometry_scope_class"], scope_class)
            self.assertNotIn("official_boundary", project["geometry_use_scope"])
        report = json.loads(
            (CURRENT_V13_PREVIEW_DIR / "selection-report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["official_boundary_project_count"], 5)
        self.assertIs(report["six_site_geometry_batch"]["official_boundary"], False)

    def test_qts_and_ruh01_keep_narrow_non_overclaiming_semantics(self) -> None:
        capture = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        locators = {row["locator_id"]: row for row in capture["geometries"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        qts = locators["qts-cambois-wider-campus-ngr-point"]
        qts_source = documents["qts-cambois-environment-agency-report"]
        self.assertEqual(
            qts["display_anchor"]["coordinates"],
            [-1.533627047468273, 55.15092301981584],
        )
        self.assertTrue(qts_source["facts"]["phase_a_point_rejected"])
        self.assertNotEqual(
            qts_source["facts"]["phase_a_national_grid_reference"],
            qts_source["facts"]["wider_campus_national_grid_reference"],
        )
        self.assertIn("not the Phase A point", qts["semantics"]["precision_scope"])

        ruh = locators["ezditek-ruh01-osm-way-1544103564"]
        way = documents["ezditek-ruh01-osm-way"]
        changeset = documents["ezditek-ruh01-osm-changeset"]
        self.assertEqual(
            ruh["semantics"]["geometry_authority_class"], "community_mapped"
        )
        self.assertEqual(ruh["semantics"]["geometry_use_scope"], "project_locator")
        self.assertIs(ruh["semantics"]["official_boundary"], False)
        self.assertEqual(way["facts"]["way_id"], 1_544_103_564)
        self.assertEqual(way["facts"]["version"], 1)
        self.assertEqual(way["facts"]["changeset"], 186_307_556)
        self.assertEqual(
            way["facts"]["tags"],
            {
                "building": "yes",
                "operator": "Ezditek",
                "ref": "RUH01",
                "telecom": "data_center",
            },
        )
        self.assertEqual(changeset["facts"]["imagery_used"], "Esri World Imagery")
        self.assertIn("No Esri imagery or pixels", ruh["imagery_guardrail"])

    def test_capture_rights_are_explicit_and_raw_material_is_not_redistributed(
        self,
    ) -> None:
        capture = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        self.assertEqual(len(documents), 11)
        self.assertEqual(
            {row["evidence_id"] for row in documents.values() if row["evidence_id"]},
            V13_CAPTURE_EVIDENCE_IDS,
        )
        for document in documents.values():
            raw = document["raw_capture"]
            self.assertIs(raw["redistributed"], False)
            self.assertEqual(
                set(raw) - {"bytes", "sha256", "redistributed"},
                {"volatility_notice"}
                if document["source_id"] == "xtx-kajaani-nls-parcel"
                else set(),
            )
            self.assertNotIn("content", raw)
            self.assertNotIn("path", raw)
        self.assertEqual(documents["xtx-kajaani-nls-parcel"]["license"], "CC-BY-4.0")
        self.assertIn(
            "not a claim that a later live response is byte-identical",
            documents["xtx-kajaani-nls-parcel"]["raw_capture"]["volatility_notice"],
        )
        self.assertEqual(
            documents["bitzero-namsskogan-kartverket-parcel"]["license"],
            "CC-BY-4.0",
        )
        self.assertEqual(documents["ezditek-ruh01-osm-way"]["license"], "ODbL-1.0")
        for source_id in (
            "goodman-syd01-nsw-planning-application",
            "firstcolo-fra7-factsheet",
            "qts-cambois-environment-agency-report",
            "bitzero-namsskogan-sec-lease",
            "bitzero-namsskogan-sec-aif",
        ):
            self.assertEqual(
                documents[source_id]["license"],
                "all-rights-reserved-fact-extraction-only",
            )

    def test_inherits_v012_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V12_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V13_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited},
                inherited,
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V12_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V13_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
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
        contract = json.loads(V13_BATCH_CONTRACT.read_text(encoding="utf-8"))
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
                "v0.13 hydrated cross-check inputs are only partially present",
            ),
        ):
            verified_core._v13_hydrated_crosscheck_available(contract)

    def _assert_altered_json_rejected(
        self,
        target_path: Path,
        altered: dict[str, object],
        message: str,
    ) -> None:
        original_load = verified_core._load_json

        def load_altered(path: Path) -> object:
            if Path(path).resolve() == target_path.resolve():
                return altered
            return original_load(path)

        with (
            mock.patch.object(verified_core, "_load_json", side_effect=load_altered),
            self.assertRaisesRegex(VerifiedConstructionCoreError, message),
        ):
            verified_core._v13_contracts()

    def test_batch_official_boundary_promotion_fails_closed(self) -> None:
        altered = json.loads(V13_BATCH_CONTRACT.read_text(encoding="utf-8"))
        altered["batch_invariants"]["official_boundary"] = True
        self._assert_altered_json_rejected(
            V13_BATCH_CONTRACT,
            altered,
            "v0.13 batch invariants differ",
        )

    def test_cadastral_locator_boundary_promotion_fails_closed(self) -> None:
        altered = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        xtx = next(
            row
            for row in altered["geometries"]
            if row["locator_id"] == "xtx-kajaani-parcel-205-7-4-1"
        )
        xtx["semantics"]["official_boundary"] = True
        xtx["semantics"]["geometry_use_scope"] = "official_boundary"
        self._assert_altered_json_rejected(
            V13_GEOMETRY_CAPTURE,
            altered,
            "v0.13 geometry semantics differ",
        )

    def test_community_geometry_authority_promotion_fails_closed(self) -> None:
        altered = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        ruh = next(
            row
            for row in altered["geometries"]
            if row["locator_id"] == "ezditek-ruh01-osm-way-1544103564"
        )
        ruh["semantics"]["geometry_authority_class"] = "official_source"
        self._assert_altered_json_rejected(
            V13_GEOMETRY_CAPTURE,
            altered,
            "v0.13 geometry semantics differ",
        )

    def test_qts_wider_campus_point_substitution_fails_closed(self) -> None:
        altered = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        qts = next(
            row
            for row in altered["geometries"]
            if row["locator_id"] == "qts-cambois-wider-campus-ngr-point"
        )
        qts["geometry"]["coordinates"] = [-1.522, 55.149]
        qts["display_anchor"]["coordinates"] = [-1.522, 55.149]
        self._assert_altered_json_rejected(
            V13_GEOMETRY_CAPTURE,
            altered,
            "v0.13 geometry semantics differ",
        )

    def test_volatile_wfs_live_reproducibility_promotion_fails_closed(self) -> None:
        altered = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        xtx = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "xtx-kajaani-nls-parcel"
        )
        xtx["raw_capture"]["volatility_notice"] = "Live bytes are reproducible."
        self._assert_altered_json_rejected(
            V13_GEOMETRY_CAPTURE,
            altered,
            "v0.13 source-specific geometry facts differ",
        )

    def test_raw_all_rights_redistribution_promotion_fails_closed(self) -> None:
        altered = json.loads(V13_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        goodman = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "goodman-syd01-nsw-planning-application"
        )
        goodman["raw_capture"]["redistributed"] = True
        self._assert_altered_json_rejected(
            V13_GEOMETRY_CAPTURE,
            altered,
            "v0.13 source-document semantics differ",
        )

    def _assert_rebuild_is_byte_exact(self, *, corpus_free: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            if corpus_free:
                with mock.patch.object(
                    verified_core,
                    "_v13_hydrated_crosscheck_available",
                    return_value=False,
                ):
                    build_preview(rebuilt)
            else:
                build_preview(rebuilt)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in CURRENT_V13_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V13_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = json.loads(V13_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v13_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)

    def test_builder_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "refusing to overwrite"
        ):
            build_preview(CURRENT_V13_PREVIEW_DIR)

    def test_rehashed_artifact_tamper_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V13_PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"].startswith("curated:xtx-markets")
            )
            target["geometry_use_scope"] = "official_boundary"
            with projects_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=verified_core.PROJECT_FIELDS)
                writer.writeheader()
                writer.writerows(projects)
            manifest_path = clone / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["projects.csv"] = {
                "bytes": projects_path.stat().st_size,
                "sha256": hashlib.sha256(projects_path.read_bytes()).hexdigest(),
            }
            manifest_bytes = verified_core._json_bytes(manifest)
            manifest_path.write_bytes(manifest_bytes)
            (clone / "manifest.sha256").write_text(
                f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.13 manifest semantics differ",
            ):
                validate_preview(clone)


if __name__ == "__main__":
    unittest.main()
