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
    CURRENT_V15_PREVIEW_DIR,
    CURRENT_V15_PREVIEW_ID,
    LEGACY_PREVIEW_V14_COMMIT,
    LEGACY_PREVIEW_V14_DIR,
    LEGACY_PREVIEW_V14_MANIFEST_SHA256,
    V15_BATCH_CONTRACT,
    V15_BATCH_CONTRACT_SHA256,
    V15_CAPTURE_EVIDENCE_IDS,
    V15_GEOMETRY_CAPTURE,
    V15_GEOMETRY_CAPTURE_SHA256,
    V15_PROJECT_KEYS,
    VerifiedConstructionCoreError,
    build_v15_preview as build_preview,
    validate_frozen_v14,
    validate_preview,
)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class VerifiedConstructionCoreV015Tests(unittest.TestCase):
    def test_profile_counts_frozen_base_and_portable_inventory(self) -> None:
        self.assertEqual(CURRENT_V15_PREVIEW_ID, "2026-08-20-preview-v0.15")
        self.assertEqual(CURRENT_V15_PREVIEW_DIR.name, CURRENT_V15_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v14()["preview_id"],
            "2026-08-20-preview-v0.14",
        )
        manifest = validate_preview(CURRENT_V15_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V14_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["base_preview_commit"], LEGACY_PREVIEW_V14_COMMIT)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 73,
                "projects": 76,
                "evidence": 183,
                "countries": 27,
                "non_us_sites": 51,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 71,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 107)
        self.assertEqual(
            hashlib.sha256(V15_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V15_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(V15_BATCH_CONTRACT.stat().st_size, 11_739)
        self.assertEqual(
            hashlib.sha256(V15_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V15_GEOMETRY_CAPTURE_SHA256,
        )
        self.assertEqual(V15_GEOMETRY_CAPTURE.stat().st_size, 45_127)
        portable_paths = {row["path"] for row in manifest["portable_source_inputs"]}
        self.assertIn(
            "definitions/verified-construction-core-v0.15-five-global-site-geometry-batch.json",
            portable_paths,
        )
        self.assertIn(
            "sources/verified-construction-core-v0.15-five-global-site-geometry-facts.json",
            portable_paths,
        )
        self.assertFalse(
            any(
                Path(path).suffix.lower() in {".pdf", ".html", ".htm"}
                for path in portable_paths
            )
        )

    def test_five_distinct_non_us_sites_keep_exact_geometry_and_status_scope(self) -> None:
        contract = json.loads(V15_BATCH_CONTRACT.read_text(encoding="utf-8"))
        capture = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V15_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V15_PROJECT_KEYS
        }
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V15_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(set(projects), V15_PROJECT_KEYS)
        self.assertEqual(len({row["site_id"] for row in projects.values()}), 5)
        self.assertNotIn("US", {row["country_iso_a2"] for row in projects.values()})
        self.assertEqual(
            {row["geometry_type"] for row in projects.values()},
            {"Point", "Polygon", "MultiPolygon"},
        )
        expected_ages = {
            "curated:atnorth-fin04-kouvola-campus:phase-1": 30,
            "curated:cdc-beard-campus:be1-current-build": 31,
            "curated:estructure-cal3-rocky-view-campus:initial-build": 30,
            "curated:green-mountain-fra-mainz-campus:current-three-building-development": 30,
            "curated:hyperco-loviisa-data-center-campus:current-development": 49,
        }
        for acceptance in contract["acceptances"]:
            project = projects[acceptance["project_stable_key"]]
            result = results[acceptance["locator_id"]]
            semantics = result["semantics"]
            geometry = verified_core._v15_result_geometry(result)
            self.assertEqual(json.loads(project["geometry_json"]), geometry)
            self.assertEqual(project["geometry_type"], geometry["type"])
            self.assertEqual(
                [float(project["longitude"]), float(project["latitude"])],
                result["display_anchor"]["coordinates"],
            )
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
            geometry_document = documents[result["geometry_source_document_id"]]
            geometry_evidence_id = verified_core._v15_capture_evidence(
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

    def test_geometry_identity_rights_and_historical_scope_are_exact(self) -> None:
        capture = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        self.assertEqual(
            {
                verified_core._v15_capture_evidence(document)["evidence_id"]
                for document in documents.values()
            },
            V15_CAPTURE_EVIDENCE_IDS,
        )
        for document in documents.values():
            raw = document["raw_capture"]
            self.assertIs(raw["redistributed"], False)
            self.assertEqual(raw["sha256"], document["content_hash"])
            self.assertNotIn("content", raw)
            self.assertNotIn("path", raw)
        self.assertEqual(
            documents["atnorth-fin04-nls-parcel"]["license"], "CC-BY-4.0"
        )
        self.assertNotIn(
            "srsName",
            documents["atnorth-fin04-nls-parcel"]["source_url"],
        )
        self.assertEqual(
            documents["hyperco-loviisa-ryhti-building-point"]["license"],
            "CC-BY-4.0",
        )
        self.assertEqual(
            documents["cdc-beard-be1-act-retired-block"]["facts"][
                "lifecycle_stage"
            ],
            "RETIRED",
        )
        act_rights = documents["cdc-beard-be1-act-retired-block"][
            "rights_metadata"
        ]
        self.assertEqual(
            act_rights["service_item_id"],
            "802b1fe9b1bc480ba41d6a653ec40b62",
        )
        self.assertEqual(act_rights["layer_id"], 0)
        self.assertEqual(act_rights["layer_name"], "ACTGOV BLOCK")
        self.assertEqual(
            act_rights["license_label"],
            "Creative Commons By Attribution 4.0",
        )
        self.assertEqual(
            act_rights["item_metadata"]["sha256"],
            "1b2a42f718e59418e1688639b1a79571bd8896a9396d650b0ed1b448088a0ce3",
        )
        self.assertEqual(
            act_rights["service_metadata"]["sha256"],
            "058ce2f6b406a3355151af5c6009fea6434182f5c5ee0e5ed03c770ed2684743",
        )
        self.assertEqual(
            documents["green-mountain-fra-mainz-energieatlas-point"]["license"],
            "all-rights-reserved-fact-extraction-only",
        )
        fin_geometry = verified_core._v15_result_geometry(
            results["atnorth-fin04-property-286-423-20-1"]
        )
        self.assertEqual(fin_geometry["type"], "MultiPolygon")
        self.assertEqual(len(fin_geometry["coordinates"]), 3)
        self.assertEqual(
            [len(polygon[0]) for polygon in fin_geometry["coordinates"]],
            [97, 617, 507],
        )
        cdc = results["cdc-beard-be1-historical-block-24-section-11"]
        self.assertEqual(
            verified_core._v15_result_geometry(cdc)["type"], "Polygon"
        )
        self.assertIn("historical project locator", cdc["semantics"]["precision_scope"])
        self.assertIs(cdc["semantics"]["official_boundary"], False)

    def test_inherits_v014_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V14_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V15_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited}, inherited
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V14_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V15_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
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
            verified_core._v15_contracts()

    def test_official_boundary_promotion_fails_closed(self) -> None:
        altered = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        cdc = next(
            row
            for row in altered["results"]
            if row["locator_id"] == "cdc-beard-be1-historical-block-24-section-11"
        )
        cdc["semantics"]["official_boundary"] = True
        self._assert_altered_json_rejected(
            V15_GEOMETRY_CAPTURE,
            altered,
            "v0.15 geometry semantics differ",
        )

    def test_retired_cdc_lifecycle_promotion_fails_closed(self) -> None:
        altered = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        cdc = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "cdc-beard-be1-act-retired-block"
        )
        cdc["facts"]["lifecycle_stage"] = "CURRENT"
        self._assert_altered_json_rejected(
            V15_GEOMETRY_CAPTURE,
            altered,
            "v0.15 source-specific identity guardrail differs",
        )

    def test_act_rights_chain_tamper_fails_closed(self) -> None:
        altered = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        cdc = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "cdc-beard-be1-act-retired-block"
        )
        cdc["rights_metadata"]["item_metadata"]["sha256"] = "0" * 64
        self._assert_altered_json_rejected(
            V15_GEOMETRY_CAPTURE,
            altered,
            "v0.15 source-specific identity guardrail differs",
        )

    def test_encoded_geometry_tamper_fails_closed(self) -> None:
        altered = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        fin = next(
            row
            for row in altered["results"]
            if row["locator_id"] == "atnorth-fin04-property-286-423-20-1"
        )
        fin["geometry_encoding"]["data"] = "AAAA"
        self._assert_altered_json_rejected(
            V15_GEOMETRY_CAPTURE,
            altered,
            "v0.15 encoded geometry cannot be decoded",
        )

    def test_raw_material_redistribution_fails_closed(self) -> None:
        altered = json.loads(V15_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        mainz = next(
            row
            for row in altered["source_documents"]
            if row["source_id"] == "green-mountain-fra-mainz-energieatlas-point"
        )
        mainz["raw_capture"]["redistributed"] = True
        self._assert_altered_json_rejected(
            V15_GEOMETRY_CAPTURE,
            altered,
            "v0.15 raw-source guardrail differs",
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
                {path.name for path in CURRENT_V15_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V15_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = json.loads(V15_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)

    def test_builder_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "refusing to overwrite"
        ):
            build_preview(CURRENT_V15_PREVIEW_DIR)

    def test_rehashed_artifact_tamper_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V15_PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:cdc-beard-campus:be1-current-build"
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
                "v0.15 manifest semantics differ",
            ):
                validate_preview(clone)


if __name__ == "__main__":
    unittest.main()
