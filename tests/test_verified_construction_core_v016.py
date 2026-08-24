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
    CURRENT_V16_PREVIEW_DIR,
    CURRENT_V16_PREVIEW_ID,
    LEGACY_PREVIEW_V15_COMMIT,
    LEGACY_PREVIEW_V15_DIR,
    LEGACY_PREVIEW_V15_MANIFEST_SHA256,
    V16_BATCH_CONTRACT,
    V16_BATCH_CONTRACT_SHA256,
    V16_CAPTURE_EVIDENCE_IDS,
    V16_GEOMETRY_CAPTURE,
    V16_GEOMETRY_CAPTURE_SHA256,
    V16_PROJECT_KEYS,
    VerifiedConstructionCoreError,
    build_preview,
    validate_frozen_v15,
    validate_preview,
)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class VerifiedConstructionCoreV016Tests(unittest.TestCase):
    def test_profile_counts_frozen_base_and_portable_inventory(self) -> None:
        self.assertEqual(CURRENT_V16_PREVIEW_ID, "2026-08-20-preview-v0.16")
        self.assertEqual(CURRENT_V16_PREVIEW_DIR.name, CURRENT_V16_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v15()["preview_id"],
            "2026-08-20-preview-v0.15",
        )
        manifest = validate_preview(CURRENT_V16_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V15_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["base_preview_commit"], LEGACY_PREVIEW_V15_COMMIT)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 80,
                "projects": 83,
                "evidence": 200,
                "countries": 33,
                "non_us_sites": 58,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 78,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 116)
        self.assertEqual(
            hashlib.sha256(V16_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V16_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(V16_BATCH_CONTRACT.stat().st_size, 33_941)
        self.assertEqual(
            hashlib.sha256(V16_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V16_GEOMETRY_CAPTURE_SHA256,
        )
        self.assertEqual(V16_GEOMETRY_CAPTURE.stat().st_size, 31_597)
        portable_paths = {row["path"] for row in manifest["portable_source_inputs"]}
        self.assertIn(
            "definitions/verified-construction-core-v0.16-seven-country-diversity-site-batch.json",
            portable_paths,
        )
        self.assertIn(
            "sources/verified-construction-core-v0.16-seven-country-diversity-site-facts.json",
            portable_paths,
        )
        self.assertFalse(
            any(
                Path(path).suffix.lower() in {".pdf", ".html", ".htm"}
                for path in portable_paths
            )
        )

    def test_seven_distinct_non_us_sites_keep_locator_and_status_scope(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        capture = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V16_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V16_PROJECT_KEYS
        }
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V16_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(set(projects), V16_PROJECT_KEYS)
        self.assertEqual(len({row["site_id"] for row in projects.values()}), 7)
        self.assertNotIn("US", {row["country_iso_a2"] for row in projects.values()})
        self.assertEqual(
            {row["country_iso_a2"] for row in projects.values()},
            {"CO", "EG", "ID", "LT", "MY", "NL", "PT"},
        )
        self.assertFalse(any("smextp01" in key.lower() for key in projects))
        expected_ages = {
            "curated:digital-edge-cgk-campus-bekasi:cgk1": 73,
            "curated:pure-dc-ams01-amsterdam-westpoort-campus:data-hall-development": 85,
            "curated:racks-central-johor-ai-campus:rcjm1-first-phase": 51,
            "curated:scala-zona-franca-bogota-campus:sbogzb01": 30,
            "curated:start-campus-sines-data-campus:sin02-current-facility-build": 58,
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2": 71,
            "curated:telia-vilnius-data-center:new-data-center-current-build": 51,
        }
        for acceptance in contract["acceptances"]:
            project = projects[acceptance["project_stable_key"]]
            result = results[acceptance["locator_id"]]
            semantics = result["semantics"]
            geometry = verified_core._v15_result_geometry(result)
            self.assertEqual(json.loads(project["geometry_json"]), geometry)
            self.assertEqual(project["geometry_type"], geometry["type"])
            self.assertEqual(project["geometry_use_scope"], "campus_locator")
            self.assertEqual(project["geometry_source_entity_kind"], "campus")
            self.assertIs(semantics["official_boundary"], False)
            self.assertEqual(
                project["last_observed_physical_status"],
                acceptance["status"]["value"],
            )
            self.assertIn(
                project["last_observed_physical_status"],
                verified_core.PHYSICAL_STATUSES,
            )
            self.assertEqual(
                int(project["status_age_days_at_review"]),
                expected_ages[acceptance["project_stable_key"]],
            )
            for source_id in result["geometry_source_document_ids"]:
                evidence_id = verified_core._v16_capture_evidence(
                    documents[source_id]
                )["evidence_id"]
                self.assertIn("geometry", json.loads(evidence[evidence_id]["roles_json"]))
                self.assertIn(
                    project["project_id"],
                    json.loads(evidence[evidence_id]["project_ids_json"]),
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

    def test_lineage_classes_and_selection_accounting_are_explicit(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        lineage = {
            row["project_stable_key"]: row for row in contract["source_lineage"]
        }
        report = json.loads(
            (CURRENT_V16_PREVIEW_DIR / "selection-report.json").read_text(
                encoding="utf-8"
            )
        )
        accounting = report["source_selection_accounting"]
        self.assertEqual(accounting, contract["source_selection_accounting"])
        self.assertEqual(
            accounting["resulting_v97_first_failure_counts"],
            {
                "entity_kind_not_project": 49,
                "not_in_reviewed_site_geometry_allowlist": 64,
                "selected": 81,
                "status_not_physical": 12,
                "status_outside_90_day_window": 325,
            },
        )
        self.assertEqual(accounting["v97_pipeline_rows"], 531)
        self.assertEqual(accounting["v97_selected_projects"], 81)
        self.assertEqual(accounting["v97_nonselected_source_rows"], 450)
        self.assertEqual(accounting["post_v97_selected_projects"], 2)
        self.assertEqual(accounting["artifact_selected_projects"], 83)
        self.assertEqual(report["selected_project_count"], 83)
        self.assertEqual(report["non_selected_source_row_count"], 450)
        self.assertEqual(report["source_pipeline_row_count"], 531)
        self.assertEqual(
            report["non_selected_source_row_count"]
            + accounting["v97_selected_projects"],
            report["source_pipeline_row_count"],
        )
        self.assertEqual(
            report["selection_first_failure_counts"],
            accounting["resulting_v97_first_failure_counts"],
        )
        racks = lineage[
            "curated:racks-central-johor-ai-campus:rcjm1-first-phase"
        ]
        telia = lineage[
            "curated:telia-vilnius-data-center:new-data-center-current-build"
        ]
        self.assertEqual(
            racks["v14_topology"]["relationship_id"],
            "relationship:f51f4a43c48f7bf49fd0b9beea7c29c88daf1355b8c61821dbc0607e9d3dae3a",
        )
        self.assertEqual(
            telia["v14_topology"]["relationship_id"],
            "relationship:e07f1ff0271cb93b2eda6761392564818b7b498c2e4f5fcb4c269a4dffa59259",
        )
        rdh2 = lineage[
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2"
        ]
        self.assertEqual(
            rdh2["location_evidence_lineage"],
            {
                "classification": "portable_current_source_field_level_not_v97",
                "evidence_id": "9e125358-5e04-5826-b0ad-9fec2aeb71d2",
                "source_input_sha256": (
                    "910f4a3240f17c33454a09746dc3d1761f33c4ce5c7b80ce423db1d8b6113d88"
                ),
                "v97_evidence_presence": "absent",
            },
        )
        pure = lineage[
            "curated:pure-dc-ams01-amsterdam-westpoort-campus:data-hall-development"
        ]
        start = lineage[
            "curated:start-campus-sines-data-campus:sin02-current-facility-build"
        ]
        self.assertEqual(pure["v97_project"]["presence"], "absent")
        self.assertEqual(pure["v97_campus"]["presence"], "absent")
        self.assertEqual(start["v97_project"]["presence"], "absent")
        self.assertEqual(start["v97_campus"]["presence"], "required")
        for row in (pure, start):
            topology = row["source_local_topology"]
            self.assertEqual(
                topology["relationship_id"],
                verified_core._v16_source_local_relationship_id(
                    topology["project_entity_id"],
                    topology["campus_entity_id"],
                    topology["source_input_sha256"],
                ),
            )

    def test_exact_geometry_hashes_and_uncertainty_are_pinned(self) -> None:
        capture = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        results = {row["locator_id"]: row for row in capture["results"]}
        expected = {
            "digital-edge-cgk1-osm-giic-host-estate-polygon": (
                11_415,
                "bc2c85e9de0258e4acb1231d2715251bbb1d5a51335e1eedabd681a13b3ee7c0",
            ),
            "racks-central-rcjm1-osm-iskandar-halal-park-two-phase-union": (
                927,
                "bd636e9b192fca33247390a035d1faf568792055d6e0bb46547531eb0a8ebcb8",
            ),
            "telia-vilnius-osm-named-construction-area": (
                155,
                "38fb4a806349580de23a5842205341b9505cc438481a08022c5393edd1413203",
            ),
        }
        for locator_id, (byte_count, digest) in expected.items():
            geometry = verified_core._v15_result_geometry(results[locator_id])
            canonical = verified_core._json_bytes(geometry)[:-1]
            self.assertEqual(len(canonical), byte_count)
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        malaysia = verified_core._v15_result_geometry(
            results[
                "racks-central-rcjm1-osm-iskandar-halal-park-two-phase-union"
            ]
        )
        stored = verified_core._json_bytes(malaysia)
        self.assertEqual(len(stored), 928)
        self.assertEqual(
            hashlib.sha256(stored).hexdigest(),
            "791faac4b109498d4265f8035c8aa5af16a53d4eaf65b969ee4ec7c157deec06",
        )
        uncertainties = {
            row["project_stable_key"]: row["horizontal_uncertainty_metres"]
            for row in _rows_from(CURRENT_V16_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in V16_PROJECT_KEYS
        }
        self.assertEqual(
            uncertainties[
                "curated:start-campus-sines-data-campus:sin02-current-facility-build"
            ],
            "25",
        )
        self.assertEqual(sum(bool(value) for value in uncertainties.values()), 1)

    def test_rights_and_non_redistribution_are_exact(self) -> None:
        capture = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        self.assertEqual(
            {
                verified_core._v16_capture_evidence(document)["evidence_id"]
                for document in documents.values()
            },
            V16_CAPTURE_EVIDENCE_IDS,
        )
        for document in documents.values():
            self.assertIs(document["capture"]["redistributed"], False)
            self.assertEqual(document["capture"]["sha256"], document["content_hash"])
            self.assertNotIn("content", document["capture"])
            self.assertNotIn("path", document["capture"])
        self.assertEqual(
            sum(document["license"] == "ODbL-1.0" for document in documents.values()),
            5,
        )
        self.assertEqual(
            documents["scala-sbogzb01-ideca-address-point"]["license"],
            "CC-BY-4.0",
        )
        self.assertEqual(
            documents["pure-dc-ams01-pdok-bag-tower-1-address"]["license"],
            "Public-Domain-Mark-1.0",
        )
        self.assertEqual(
            documents["start-campus-sin02-apa-shared-campus-point"]["license"],
            "rights-status-uncertain-fact-extraction-only",
        )

    def test_inherits_v015_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V15_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V16_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited}, inherited
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V15_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V16_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
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
            verified_core._v16_contracts()

    def test_official_boundary_promotion_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        altered["results"][0]["semantics"]["official_boundary"] = True
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "v0.16 geometry semantics differ",
        )

    def test_osm_status_promotion_fails_closed(self) -> None:
        altered = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"]
            == "curated:telia-vilnius-data-center:new-data-center-current-build"
        )
        row["status"]["value"] = "operational"
        self._assert_altered_json_rejected(
            V16_BATCH_CONTRACT,
            altered,
            "v0.16 lifecycle differs",
        )

    def test_corpus_free_source_local_topology_tamper_fails_closed(self) -> None:
        altered = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["source_lineage"]
            if row["project_stable_key"]
            == "curated:pure-dc-ams01-amsterdam-westpoort-campus:data-hall-development"
        )
        row["source_local_topology"]["relationship_id"] = "relationship:" + (
            "0" * 64
        )
        original_load = verified_core._load_json

        def load_altered(path: Path) -> object:
            if Path(path).resolve() == V16_BATCH_CONTRACT.resolve():
                return altered
            return original_load(path)

        with (
            mock.patch.object(
                verified_core, "_load_json", side_effect=load_altered
            ),
            mock.patch.object(
                verified_core,
                "_v14_hydrated_crosscheck_available",
                return_value=False,
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.16 portable post-v97 lineage differs",
            ),
        ):
            verified_core._v16_contracts()

    def test_uncertainty_mutual_exclusion_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["results"]
            if row["locator_id"]
            == "start-campus-sin02-apa-shared-sin02-06-centroid"
        )
        row["semantics"]["horizontal_uncertainty_unknown_reason"] = "unknown"
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "v0.16 geometry semantics differ",
        )

    def test_malaysia_two_source_union_tamper_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["results"]
            if row["locator_id"]
            == "racks-central-rcjm1-osm-iskandar-halal-park-two-phase-union"
        )
        row["geometry_source_document_ids"] = row["geometry_source_document_ids"][:1]
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "v0.16 source or locator identity differs",
        )

    def test_malaysia_stored_container_hash_tamper_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["results"]
            if row["locator_id"]
            == "racks-central-rcjm1-osm-iskandar-halal-park-two-phase-union"
        )
        row["canonical_geometry"]["stored_json_sha256_with_newline"] = "0" * 64
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "v0.16 source-specific identity guardrail differs",
        )

    def test_encoded_indonesia_geometry_tamper_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        row = next(
            row
            for row in altered["results"]
            if row["locator_id"]
            == "digital-edge-cgk1-osm-giic-host-estate-polygon"
        )
        row["geometry_encoding"]["data"] = "AAAA"
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "encoded geometry cannot be decoded",
        )

    def test_raw_material_redistribution_fails_closed(self) -> None:
        altered = json.loads(V16_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))
        altered["source_documents"][0]["capture"]["redistributed"] = True
        self._assert_altered_json_rejected(
            V16_GEOMETRY_CAPTURE,
            altered,
            "v0.16 raw-source guardrail differs",
        )

    def test_hydrated_lineage_validator_is_invoked(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        with mock.patch.object(
            verified_core,
            "_v16_validate_hydrated_lineage",
            wraps=verified_core._v16_validate_hydrated_lineage,
        ) as validator:
            verified_core._v16_contracts()
        validator.assert_called_once()

    def test_hydrated_v97_project_row_tamper_fails_closed(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        original_load = verified_core._load_csv

        def load_altered(
            path: Path, expected_fields: object = None
        ) -> list[dict[str, str]]:
            rows = original_load(path, expected_fields)
            if Path(path).resolve() == (
                verified_core.SOURCE_RELEASE / "construction_pipeline.csv"
            ).resolve():
                rows = [dict(row) for row in rows]
                target = next(
                    row
                    for row in rows
                    if row["stable_key"]
                    == "curated:scala-zona-franca-bogota-campus:sbogzb01"
                )
                target["status_as_of"] = "2026-07-20"
            return rows

        with (
            mock.patch.object(
                verified_core, "_load_csv", side_effect=load_altered
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.16 hydrated lineage v97 project differs",
            ),
        ):
            verified_core._v16_contracts()

    def test_hydrated_v14_topology_tamper_fails_closed(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        original_load = verified_core._load_csv

        def load_altered(
            path: Path, expected_fields: object = None
        ) -> list[dict[str, str]]:
            rows = original_load(path, expected_fields)
            if Path(path).resolve() == (
                verified_core.ROOT
                / "exact_identity_decisions"
                / "2026-07-22-public-open-v14"
                / "relationships.csv"
            ).resolve():
                rows = [dict(row) for row in rows]
                target = next(
                    row
                    for row in rows
                    if row["relationship_id"]
                    == "relationship:f51f4a43c48f7bf49fd0b9beea7c29c88daf1355b8c61821dbc0607e9d3dae3a"
                )
                target["object_component_id"] = "exact:tampered"
            return rows

        with (
            mock.patch.object(
                verified_core, "_load_csv", side_effect=load_altered
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.16 hydrated lineage v14 topology differs",
            ),
        ):
            verified_core._v16_contracts()

    def test_hydrated_exact_status_evidence_projection_tamper_fails_closed(
        self,
    ) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        acceptance = next(
            row
            for row in contract["acceptances"]
            if row["project_stable_key"]
            == "curated:digital-edge-cgk-campus-bekasi:cgk1"
        )
        source_path = verified_core.ROOT / acceptance["source_input"]["path"]
        altered = json.loads(source_path.read_text(encoding="utf-8"))
        evidence = next(
            row
            for row in altered["evidence"]
            if row["key"] == acceptance["status"]["evidence_key"]
        )
        evidence["source_url"] = "https://example.invalid/semantic-drift"
        self._assert_altered_json_rejected(
            source_path,
            altered,
            "v0.16 hydrated exact status evidence projection differs",
        )

    def test_hydrated_exact_status_method_and_confidence_drift_fail_closed(
        self,
    ) -> None:
        original_contract = json.loads(
            V16_BATCH_CONTRACT.read_text(encoding="utf-8")
        )
        if not verified_core._v14_hydrated_crosscheck_available(
            original_contract
        ):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        original_load = verified_core._load_json
        project_key = "curated:digital-edge-cgk-campus-bekasi:cgk1"
        for field, value in (
            ("method", "physical_observation"),
            ("confidence", 0.97),
        ):
            with self.subTest(field=field):
                contract = json.loads(
                    V16_BATCH_CONTRACT.read_text(encoding="utf-8")
                )
                acceptance = next(
                    row
                    for row in contract["acceptances"]
                    if row["project_stable_key"] == project_key
                )
                acceptance["status"][field] = value
                source_path = (
                    verified_core.ROOT / acceptance["source_input"]["path"]
                )
                source = json.loads(source_path.read_text(encoding="utf-8"))
                lifecycle = next(
                    row
                    for row in source["lifecycle"]
                    if row["entity"] == "project"
                    and row["evidence_key"]
                    == acceptance["status"]["evidence_key"]
                )
                lifecycle[field] = value

                def load_altered(path: Path) -> object:
                    resolved = Path(path).resolve()
                    if resolved == V16_BATCH_CONTRACT.resolve():
                        return contract
                    if resolved == source_path.resolve():
                        return source
                    return original_load(path)

                with (
                    mock.patch.object(
                        verified_core,
                        "_load_json",
                        side_effect=load_altered,
                    ),
                    self.assertRaisesRegex(
                        VerifiedConstructionCoreError,
                        "v0.16 hydrated lineage v97 project projection differs",
                    ),
                ):
                    verified_core._v16_contracts()

    def _assert_rebuild_is_byte_exact(self, *, corpus_free: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            context = (
                mock.patch.object(
                    verified_core,
                    "_v14_hydrated_crosscheck_available",
                    return_value=False,
                )
                if corpus_free
                else mock.patch.object(
                    verified_core,
                    "_v14_hydrated_crosscheck_available",
                    wraps=verified_core._v14_hydrated_crosscheck_available,
                )
            )
            with context, mock.patch.object(
                verified_core,
                "_v16_validate_hydrated_lineage",
                wraps=verified_core._v16_validate_hydrated_lineage,
            ) as validator:
                build_preview(rebuilt)
            if corpus_free:
                validator.assert_not_called()
            else:
                self.assertGreater(validator.call_count, 0)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in CURRENT_V16_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V16_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = json.loads(V16_BATCH_CONTRACT.read_text(encoding="utf-8"))
        if not verified_core._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)

    def test_builder_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "refusing to overwrite"
        ):
            build_preview(CURRENT_V16_PREVIEW_DIR)

    def test_rehashed_artifact_tamper_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V16_PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:telia-vilnius-data-center:new-data-center-current-build"
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
                "v0.16 manifest semantics differ",
            ):
                validate_preview(clone)


if __name__ == "__main__":
    unittest.main()
