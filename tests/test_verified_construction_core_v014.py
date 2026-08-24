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
    CURRENT_V14_PREVIEW_DIR,
    CURRENT_V14_PREVIEW_ID,
    LEGACY_PREVIEW_V13_COMMIT,
    LEGACY_PREVIEW_V13_DIR,
    LEGACY_PREVIEW_V13_MANIFEST_SHA256,
    V14_BATCH_CONTRACT,
    V14_BATCH_CONTRACT_SHA256,
    V14_CAPTURE_EVIDENCE_IDS,
    V14_GEOMETRY_CAPTURE,
    V14_GEOMETRY_CAPTURE_SHA256,
    V14_PROJECT_KEYS,
    VerifiedConstructionCoreError,
    build_preview,
    validate_frozen_v13,
    validate_preview,
)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class VerifiedConstructionCoreV014Tests(unittest.TestCase):
    def test_profile_counts_frozen_base_and_portable_inventory(self) -> None:
        self.assertEqual(CURRENT_V14_PREVIEW_ID, "2026-08-20-preview-v0.14")
        self.assertEqual(CURRENT_V14_PREVIEW_DIR.name, CURRENT_V14_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v13()["preview_id"],
            "2026-08-20-preview-v0.13",
        )
        manifest = validate_preview(CURRENT_V14_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V13_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["base_preview_commit"], LEGACY_PREVIEW_V13_COMMIT)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 68,
                "projects": 71,
                "evidence": 170,
                "countries": 27,
                "non_us_sites": 46,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 66,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 100)
        self.assertEqual(
            hashlib.sha256(V14_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V14_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(V14_BATCH_CONTRACT.stat().st_size, 21_333)
        self.assertEqual(
            hashlib.sha256(V14_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V14_GEOMETRY_CAPTURE_SHA256,
        )
        self.assertEqual(V14_GEOMETRY_CAPTURE.stat().st_size, 23_717)
        portable_paths = {row["path"] for row in manifest["portable_source_inputs"]}
        self.assertIn(
            "definitions/verified-construction-core-v0.14-nine-us-address-locator-batch.json",
            portable_paths,
        )
        self.assertIn(
            "sources/verified-construction-core-v0.14-us-address-locator-facts.json",
            portable_paths,
        )
        self.assertFalse(
            any(Path(path).suffix.lower() in {".pdf", ".html", ".htm"} for path in portable_paths)
        )
        self.assertFalse(any("parcel" in Path(path).name.lower() for path in portable_paths))

    def test_nine_distinct_sites_keep_exact_locator_and_status_scope(self) -> None:
        contract = json.loads(V14_BATCH_CONTRACT.read_text(encoding="utf-8"))
        capture = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V14_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V14_PROJECT_KEYS
        }
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V14_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(set(projects), V14_PROJECT_KEYS)
        self.assertEqual(len({row["site_id"] for row in projects.values()}), 9)
        self.assertEqual({row["geometry_type"] for row in projects.values()}, {"Point"})
        expected_ages = {
            "curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development": 71,
            "curated:bitdeer-wenatchee-washington-campus:2026-ai-conversion-site-preparation": 30,
            "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build": 65,
            "curated:microsoft-heath-oh-datacenter:initial-site-preparation": 50,
            "curated:microsoft-new-albany-oh-datacenter:initial-site-preparation": 50,
            "curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction": 30,
            "curated:microsoft-hebron-oh-datacenter:initial-site-preparation": 50,
            "curated:qts-cedar-rapids-data-center-campus:current-campus-development": 36,
            "curated:jefferson-lab-newport-news-campus:jldc-building": 69,
        }
        for acceptance in contract["acceptances"]:
            project = projects[acceptance["project_stable_key"]]
            result = results[acceptance["locator_id"]]
            profile = acceptance["semantics_profile"]
            semantics = contract[f"{profile}_geometry_semantics"]
            self.assertEqual(
                json.loads(project["geometry_json"]),
                {
                    "coordinates": [result["longitude"], result["latitude"]],
                    "type": "Point",
                },
            )
            self.assertEqual(float(project["longitude"]), result["longitude"])
            self.assertEqual(float(project["latitude"]), result["latitude"])
            self.assertEqual(
                project["physical_site_stable_key"],
                acceptance["parent_campus_stable_key"],
            )
            self.assertEqual(
                project["last_observed_physical_status"],
                acceptance["status"]["value"],
            )
            self.assertEqual(project["status_as_of"], acceptance["status"]["as_of_date"])
            self.assertEqual(
                project["status_evidence_id"], acceptance["status"]["evidence_id"]
            )
            self.assertEqual(
                int(project["status_age_days_at_review"]),
                expected_ages[acceptance["project_stable_key"]],
            )
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
            self.assertEqual(project["horizontal_uncertainty_metres"], "")
            self.assertTrue(project["horizontal_uncertainty_unknown_reason"])
            self.assertEqual(project["independent_imagery_verification"], "false")
            self.assertEqual(
                project["verification_posture"],
                "recent_authoritative_physical_observation_plus_reviewed_site_locator",
            )
            geometry_document = documents[result["geometry_source_document_id"]]
            geometry_evidence_id = verified_core._v14_capture_evidence(
                geometry_document
            )["evidence_id"]
            geometry_evidence = evidence[geometry_evidence_id]
            self.assertIn("geometry", json.loads(geometry_evidence["roles_json"]))
            self.assertIn(
                project["project_id"],
                json.loads(geometry_evidence["project_ids_json"]),
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

    def test_geometry_profiles_and_normalization_disclosures_are_narrow(self) -> None:
        capture = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        qts = results["qts-cedar-rapids-dc1-first-party-pin"]
        self.assertEqual(qts["geometry_source_document_id"], "qts-cedar-rapids-first-party-map-pin")
        self.assertEqual([qts["longitude"], qts["latitude"]], [-91.754301, 41.907294])
        self.assertIn("Fairfax", qts["normalization_note"])
        self.assertIn("census-qts-cedar-rapids-address-match", qts["identity_source_document_ids"])
        self.assertTrue(
            documents["qts-cedar-rapids-first-party-map-pin"]["facts"][
                "dc2_dc3_geometry_not_inferred"
            ]
        )
        jlab = results["jefferson-lab-12000-jefferson-avenue"]
        self.assertIn("23605", jlab["matched_address"])
        self.assertIn("23606", jlab["normalization_note"])
        self.assertIn("broad laboratory-campus locator", jlab["normalization_note"])
        alviso = results["microsoft-alviso-city-address-point"]
        self.assertEqual(alviso["geometry_source_document_id"], "san-jose-alviso-address-point")
        city = documents["san-jose-alviso-private-development-record"]
        self.assertEqual(city["facts"]["facility_id"], 749)
        self.assertEqual(city["facts"]["developer_name"], "Microsoft")
        self.assertIn("CP23-016", city["facts"]["file_numbers"])
        self.assertIs(city["facts"]["polygon_rejected"], True)
        report = json.loads(
            (CURRENT_V14_PREVIEW_DIR / "selection-report.json").read_text(
                encoding="utf-8"
            )
        )
        batch = report["nine_us_address_locator_batch"]
        self.assertEqual(batch["geometry_types"], {"Point": 9})
        self.assertEqual(
            batch["geometry_use_scopes"],
            {"campus_locator": 8, "project_locator": 1},
        )
        self.assertIs(batch["official_boundary"], False)
        self.assertEqual(report["official_boundary_project_count"], 5)

    def test_capture_rights_are_explicit_and_raw_material_is_not_redistributed(self) -> None:
        capture = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        self.assertEqual(len(documents), 16)
        self.assertEqual(
            {
                verified_core._v14_capture_evidence(document)["evidence_id"]
                for document in documents.values()
            },
            V14_CAPTURE_EVIDENCE_IDS,
        )
        for document in documents.values():
            raw = document["raw_capture"]
            self.assertIs(raw["redistributed"], False)
            self.assertEqual(raw["sha256"], document["content_hash"])
            self.assertNotIn("content", raw)
            self.assertNotIn("path", raw)
        self.assertEqual(
            documents["washington-current-parcels-wenatchee-address"]["license"],
            "use-restrictions-fact-extraction-only",
        )
        self.assertEqual(
            documents["licking-county-microsoft-owner-address-facts"]["license"],
            "rights-status-uncertain-fact-extraction-only",
        )
        self.assertTrue(
            documents["licking-county-microsoft-owner-address-facts"]
            ["metadata_capture"]["license_and_terms_blank"]
        )
        self.assertIs(
            documents["washington-current-parcels-wenatchee-address"]["facts"]
            ["parcel_polygon_rejected"],
            True,
        )
        self.assertIs(
            documents["village-of-hebron-microsoft-data-center-minutes"]["facts"]
            ["current_323_n_high_parcel_not_claimed_by_minutes"],
            True,
        )

    def test_inherits_v013_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V13_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V14_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited}, inherited
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V13_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V14_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
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
        contract = json.loads(V14_BATCH_CONTRACT.read_text(encoding="utf-8"))
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
                "v0.14 hydrated cross-check inputs are only partially present",
            ),
        ):
            verified_core._v14_hydrated_crosscheck_available(contract)

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
            verified_core._v14_contracts()

    def test_official_boundary_promotion_fails_closed(self) -> None:
        altered = json.loads(V14_BATCH_CONTRACT.read_text(encoding="utf-8"))
        altered["census_geometry_semantics"]["official_boundary"] = True
        self._assert_altered_json_rejected(
            V14_BATCH_CONTRACT,
            altered,
            "v0.14 census geometry semantics differ",
        )

    def test_qts_census_point_substitution_fails_closed(self) -> None:
        altered = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        qts = next(
            row
            for row in altered["results"]
            if row["locator_id"] == "qts-cedar-rapids-dc1-first-party-pin"
        )
        qts["longitude"] = -91.751083365349
        qts["latitude"] = 41.90559767783
        qts["geometry_source_document_id"] = "census-qts-cedar-rapids-address-match"
        self._assert_altered_json_rejected(
            V14_GEOMETRY_CAPTURE,
            altered,
            "v0.14 source or locator identity differs",
        )

    def test_raw_parcel_redistribution_promotion_fails_closed(self) -> None:
        altered = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        washington = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "washington-current-parcels-wenatchee-address"
        )
        washington["raw_capture"]["redistributed"] = True
        self._assert_altered_json_rejected(
            V14_GEOMETRY_CAPTURE,
            altered,
            "v0.14 raw-source guardrail differs",
        )

    def test_embedded_raw_material_fails_closed(self) -> None:
        altered = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        washington = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "washington-current-parcels-wenatchee-address"
        )
        washington["raw_capture"]["content"] = "raw parcel response"
        self._assert_altered_json_rejected(
            V14_GEOMETRY_CAPTURE,
            altered,
            "v0.14 raw-source guardrail differs",
        )

    def test_uncertain_parcel_rights_cannot_be_reclassified(self) -> None:
        altered = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        licking = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "licking-county-microsoft-owner-address-facts"
        )
        licking["license"] = "public-domain-us-government"
        self._assert_altered_json_rejected(
            V14_GEOMETRY_CAPTURE,
            altered,
            "v0.14 raw-source guardrail differs",
        )

    def test_alviso_development_polygon_promotion_fails_closed(self) -> None:
        altered = json.loads(V14_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        city = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "san-jose-alviso-private-development-record"
        )
        city["facts"]["polygon_rejected"] = False
        self._assert_altered_json_rejected(
            V14_GEOMETRY_CAPTURE,
            altered,
            "v0.14 normalization or Alviso identity guardrail differs",
        )

    def _assert_rebuild_is_byte_exact(self, *, corpus_free: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            if corpus_free:
                with mock.patch.object(
                    verified_core,
                    "_v14_hydrated_crosscheck_available",
                    return_value=False,
                ):
                    build_preview(rebuilt)
            else:
                build_preview(rebuilt)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in CURRENT_V14_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V14_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = json.loads(V14_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)

    def test_builder_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "refusing to overwrite"
        ):
            build_preview(CURRENT_V14_PREVIEW_DIR)

    def test_rehashed_artifact_tamper_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V14_PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"].startswith(
                    "curated:qts-cedar-rapids"
                )
            )
            target["geometry_use_scope"] = "official_boundary"
            with projects_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=verified_core.PROJECT_FIELDS
                )
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
                "v0.14 manifest semantics differ",
            ):
                validate_preview(clone)


if __name__ == "__main__":
    unittest.main()
