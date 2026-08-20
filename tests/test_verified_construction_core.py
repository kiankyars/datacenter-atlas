from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import datacenter_atlas.verified_construction_core as verified_core

from datacenter_atlas.verified_construction_core import (
    IMAGERY_REVIEW_DEFINITION,
    LEGACY_PREVIEW_V01_DIR,
    LEGACY_PREVIEW_V02_DIR,
    OVERLAY_DEFINITION,
    PREVIEW_DIR,
    REVIEW_DEFINITION,
    SOURCE_RELEASE,
    VerifiedConstructionCoreError,
    build_preview,
    validate_frozen_v01,
    validate_frozen_v02,
    validate_preview,
)


def _rows(name: str) -> list[dict[str, str]]:
    return _rows_from(PREVIEW_DIR, name)


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, name: str, rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(rows[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    (path / name).write_text(buffer.getvalue(), encoding="utf-8", newline="")


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _refresh_unsigned_manifest(path: Path) -> None:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in manifest["files"]:
        payload = (path / name).read_bytes()
        manifest["files"][name] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    manifest_bytes = _canonical_json(manifest)
    manifest_path.write_bytes(manifest_bytes)
    (path / "manifest.sha256").write_text(
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )


class VerifiedConstructionCorePreviewTest(unittest.TestCase):
    def test_tracked_preview_is_closed_and_honestly_labelled(self) -> None:
        manifest = validate_preview()

        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 14,
                "projects": 15,
                "evidence": 36,
                "countries": 10,
                "non_us_sites": 11,
                "official_boundary_projects": 3,
                "reviewed_site_locator_projects": 12,
            },
        )
        self.assertEqual(manifest["release_status"], "preview")
        self.assertIs(manifest["publishable_as_final"], False)

    def test_geometry_precision_and_verification_posture_are_explicit(self) -> None:
        projects = _rows("projects.csv")
        boundary_keys = {
            row["project_stable_key"]
            for row in projects
            if row["geometry_type"] in {"Polygon", "MultiPolygon"}
        }
        self.assertEqual(
            boundary_keys,
            {
                "curated:coresite-de3-race-street-campus:de3",
                "curated:scala-praia-do-futuro-campus:sforpf01",
                "curated:verne-mantsala-data-center-campus:current-development",
            },
        )
        for row in projects:
            self.assertEqual(row["independent_imagery_verification"], "false")
            self.assertIn(
                row["verification_posture"],
                {
                    "recent_authoritative_physical_observation_plus_official_boundary",
                    "recent_authoritative_physical_observation_plus_reviewed_site_locator",
                },
            )
            self.assertNotIn("centroid", row["geometry_scope_class"])
            self.assertTrue(
                row["horizontal_uncertainty_metres"]
                or row["horizontal_uncertainty_unknown_reason"]
            )
            self.assertEqual(row["development_type"], "unknown")
            self.assertTrue(row["development_type_unknown_reason"])
            if not json.loads(row["power_observations_json"]):
                self.assertTrue(row["power_unknown_reason"])
            if not json.loads(row["annual_energy_observations_json"]):
                self.assertTrue(row["annual_energy_unknown_reason"])
            if not json.loads(row["efficiency_observations_json"]):
                self.assertTrue(row["efficiency_unknown_reason"])
            if not json.loads(row["workloads_json"]):
                self.assertTrue(row["workload_unknown_reason"])
        pozitrons = next(
            row
            for row in projects
            if row["project_stable_key"]
            == "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build"
        )
        self.assertEqual(json.loads(pozitrons["power_observations_json"]), [])
        self.assertEqual(
            [
                row["metric"]
                for row in json.loads(pozitrons["efficiency_observations_json"])
            ],
            ["pue"],
        )

    def test_v03_geometry_derivations_preserve_source_scope(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        verne = projects[
            "curated:verne-mantsala-data-center-campus:current-development"
        ]
        self.assertEqual(verne["geometry_source_entity_kind"], "campus")
        self.assertEqual(verne["geometry_derivation"], "direct_geometry")
        self.assertEqual(verne["geometry_type"], "Polygon")
        self.assertEqual(
            verne["geometry_scope_class"],
            "official_cadastral_campus_parcel_boundary",
        )
        self.assertEqual(
            verne["geometry_evidence_id"],
            "708cee21-4519-5840-a07c-2f1f8398cb87",
        )
        self.assertEqual(
            verne["status_evidence_id"],
            "0176052f-124b-5bf9-b361-a5c97cb98b62",
        )
        self.assertEqual(verne["status_age_days_at_review"], "64")

        expected_points = {
            "curated:maincubes-mainhub-nauen-campus:ber02": [
                12.8929999,
                52.5935,
            ],
            "curated:avaio-taurus-brandon-mississippi-campus:phase-one-current-campus-build": [
                -90.0185,
                32.2593,
            ],
        }
        for key, coordinates in expected_points.items():
            row = projects[key]
            self.assertEqual(row["geometry_source_entity_kind"], "project")
            self.assertEqual(row["geometry_derivation"], "coordinates_to_point")
            self.assertEqual(
                json.loads(row["geometry_json"]),
                {"type": "Point", "coordinates": coordinates},
            )
            self.assertTrue(row["horizontal_uncertainty_unknown_reason"])

        huechuraba = projects["curated:scala-huechuraba-campus:ssclhb01"]
        lampa = projects["curated:scala-lampa-campus:sscllp01"]
        for row, coordinates in (
            (huechuraba, [-70.67394, -33.36636]),
            (lampa, [-70.73915, -33.29298]),
        ):
            self.assertEqual(row["geometry_source_entity_kind"], "project")
            self.assertEqual(row["geometry_derivation"], "direct_geometry")
            self.assertEqual(row["horizontal_uncertainty_metres"], "50")
            self.assertEqual(
                json.loads(row["geometry_json"]),
                {"type": "Point", "coordinates": coordinates},
            )
        kao = projects["curated:kao-data-harlow-campus:klon-03-building"]
        self.assertEqual(kao["geometry_source_entity_kind"], "campus")
        self.assertEqual(kao["geometry_derivation"], "coordinates_to_point")
        self.assertEqual(
            kao["geometry_scope_class"],
            "government_report_campus_centre_point",
        )
        self.assertTrue(kao["horizontal_uncertainty_unknown_reason"])

    def test_imagery_provenance_preserves_portability_and_conflicts(self) -> None:
        report = json.loads((PREVIEW_DIR / "selection-report.json").read_text())
        records = {
            row["project_stable_key"]: row
            for row in report["imagery_review_provenance"]
        }
        self.assertEqual(len(records), 5)
        self.assertFalse(
            records["curated:coresite-de3-race-street-campus:de3"][
                "portable_identity_binding"
            ]
        )
        self.assertTrue(
            records["curated:maincubes-mainhub-nauen-campus:ber02"][
                "portable_identity_binding"
            ]
        )
        ber02_conflict = records[
            "curated:maincubes-mainhub-nauen-campus:ber02"
        ]["later_review_conflict"]
        self.assertEqual(ber02_conflict["blind_id"], "V83-X009")
        self.assertIs(ber02_conflict["supersedes_primary"], False)
        kao = records["curated:kao-data-harlow-campus:klon-03-building"]
        self.assertTrue(kao["portable_identity_binding"])
        self.assertEqual(kao["primary_blind_id"], "V57-B040")
        self.assertEqual(kao["primary_verdict"]["visual_verdict"], "U")
        self.assertEqual(kao["later_review_conflict"]["blind_id"], "V83-X037")
        self.assertIs(kao["later_review_conflict"]["supersedes_primary"], False)
        self.assertEqual(
            report["final_release_gates"]["imagery_outcomes_complete"]["actual"],
            5,
        )

    def test_previous_preview_remains_byte_frozen(self) -> None:
        manifest = validate_frozen_v01()
        self.assertEqual(LEGACY_PREVIEW_V01_DIR.name, "2026-08-19-preview-v0.1")
        self.assertEqual(
            manifest["counts"],
            {
                "countries": 6,
                "evidence": 23,
                "non_us_sites": 6,
                "official_boundary_projects": 2,
                "physical_sites": 8,
                "projects": 9,
                "reviewed_site_locator_projects": 7,
            },
        )
        v02 = validate_frozen_v02()
        self.assertEqual(LEGACY_PREVIEW_V02_DIR.name, "2026-08-20-preview-v0.2")
        self.assertEqual(
            v02["counts"],
            {
                "countries": 8,
                "evidence": 29,
                "non_us_sites": 8,
                "official_boundary_projects": 3,
                "physical_sites": 11,
                "projects": 12,
                "reviewed_site_locator_projects": 9,
            },
        )
        self.assertEqual(validate_preview(LEGACY_PREVIEW_V02_DIR), v02)

    def test_frozen_v02_validation_is_isolated_from_current_globals(self) -> None:
        missing = Path("/definitely-absent-v03-contract.json")
        with (
            mock.patch.object(verified_core, "REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "IMAGERY_REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "PROVENANCE_DEFINITION", missing),
            mock.patch.object(verified_core, "OVERLAY_DEFINITION", missing),
        ):
            self.assertEqual(
                validate_preview(LEGACY_PREVIEW_V02_DIR)["preview_id"],
                "2026-08-20-preview-v0.2",
            )

    def test_v03_provenance_clears_unsupported_roles_and_scopes_workloads(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        evidence = {row["evidence_id"]: row for row in _rows("evidence.csv")}
        workload_observations = [
            (project, workload)
            for project in projects.values()
            for workload in json.loads(project["workloads_json"])
        ]
        self.assertEqual(len(workload_observations), 3)
        self.assertEqual(
            {workload["deployment_scope"] for _, workload in workload_observations},
            {"intended"},
        )
        for project, workload in workload_observations:
            roles = json.loads(evidence[workload["evidence_id"]]["roles_json"])
            self.assertIn("workload", roles)
            self.assertIn("workload_scope:intended", roles)
            self.assertIn(
                project["project_id"],
                json.loads(
                    evidence[workload["evidence_id"]]["project_ids_json"]
                ),
            )

        role_claims = [
            (project, claim)
            for project in projects.values()
            for claim in json.loads(project["role_claims_json"])
        ]
        self.assertEqual(len(role_claims), 5)
        self.assertEqual({claim["role"] for _, claim in role_claims}, {"operator"})
        self.assertEqual(
            {claim["relationship_scope"] for _, claim in role_claims},
            {"intended"},
        )
        for project, claim in role_claims:
            evidence_row = evidence[claim["evidence_id"]]
            self.assertIn("role:operator", json.loads(evidence_row["roles_json"]))
            self.assertIn(
                project["project_id"],
                json.loads(evidence_row["project_ids_json"]),
            )
        self.assertIn("276847d4-183f-5995-ab80-90d4636b467b", evidence)
        for key in (
            "curated:cdc-eastern-creek-campus:ec5-current-build",
            "curated:cdc-eastern-creek-campus:ec6-current-build",
            "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion",
        ):
            self.assertEqual(projects[key]["owner"], "")
            self.assertEqual(projects[key]["operator"], "")
            self.assertEqual(json.loads(projects[key]["role_claims_json"]), [])
        report = json.loads((PREVIEW_DIR / "selection-report.json").read_text())
        self.assertEqual(
            len(report["provenance_decisions"]["excluded_source_roles"]), 4
        )

    def test_portable_v03_sources_are_manifest_bound(self) -> None:
        manifest = json.loads((PREVIEW_DIR / "manifest.json").read_text())
        inputs = manifest["portable_source_inputs"]
        self.assertEqual(len(inputs), 3)
        self.assertEqual(
            {row["path"] for row in inputs},
            {
                "sources/curated-official-2026-07-19-kao-klon03-harlow.json",
                "source_artifacts/site-coordinate-assessment-2026-07-21-v3/normalized-successors/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build-coordinate-v3.json",
                "source_artifacts/site-coordinate-assessment-2026-07-21-v3/normalized-successors/curated-official-2026-07-21-scala-sscllp01-lampa-current-build-coordinate-v3.json",
            },
        )
        for row in inputs:
            path = verified_core.ROOT / row["path"]
            self.assertEqual(path.stat().st_size, row["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        parent_pins = [
            row for row in inputs if row["parent_manifest_path"] is not None
        ]
        self.assertEqual(len(parent_pins), 2)
        self.assertEqual(
            {row["parent_manifest_sha256"] for row in parent_pins},
            {"acb675580c993e3af150f8a3e25f53a8d66a6d7b595b644088a84f1294acd43d"},
        )

    def test_site_project_geojson_and_selection_accounting_match(self) -> None:
        sites = _rows("sites.csv")
        projects = _rows("projects.csv")
        geojson = json.loads((PREVIEW_DIR / "sites.geojson").read_text())
        report = json.loads((PREVIEW_DIR / "selection-report.json").read_text())

        site_ids = {row["site_id"] for row in sites}
        self.assertEqual({row["site_id"] for row in projects}, site_ids)
        self.assertEqual(
            {feature["id"] for feature in geojson["features"]}, site_ids
        )
        self.assertEqual(report["source_pipeline_row_count"], 531)
        self.assertEqual(report["selected_project_count"], 15)
        self.assertEqual(report["non_selected_source_row_count"], 516)
        self.assertEqual(
            sum(report["selection_first_failure_counts"].values()), 531
        )
        self.assertEqual(report["selection_first_failure_counts"]["selected"], 15)
        self.assertIs(report["publishable_as_final"], False)
        self.assertFalse(report["final_release_gates"]["site_count"]["passed"])
        self.assertFalse(report["final_release_gates"]["blind_review"]["passed"])
        self.assertFalse(
            report["final_release_gates"]["clean_clone_rebuild"]["passed"]
        )
        self.assertEqual(
            {row["decision"] for row in report["reviewed_overlay_queue"]},
            {"excluded"},
        )

    def test_machine_readable_schema_covers_tables_and_relationships(self) -> None:
        schema = json.loads((PREVIEW_DIR / "schema.json").read_text())
        self.assertEqual(
            schema["format"],
            "datacenter-atlas-verified-construction-core-schema-v3",
        )
        self.assertEqual(
            set(schema["tables"]), {"projects.csv", "sites.csv", "evidence.csv"}
        )
        self.assertEqual(schema["geojson"]["geometry_equals"], ["sites.csv", "geometry_json"])
        self.assertEqual(schema["map"]["derived_from"], "sites.geojson")
        self.assertEqual(len(schema["json_embedded_evidence_fields"]), 5)
        self.assertEqual(
            schema["embedded_array_items"][
                "projects.csv:efficiency_observations_json"
            ]["allowed_metrics"],
            ["pue"],
        )
        self.assertIn("method", schema["embedded_types"]["typed_metric_observation"]["required_fields"])
        self.assertIn(
            "deployment_scope",
            schema["embedded_types"]["workload_observation"]["required_fields"],
        )
        self.assertEqual(
            schema["embedded_types"]["role_claim"]["allowed_roles"],
            ["customer", "operator", "owner", "tenant", "user"],
        )
        project_fields = {
            row["name"]: row for row in schema["tables"]["projects.csv"]["fields"]
        }
        self.assertEqual(
            project_fields["geometry_source_entity_kind"]["allowed_values"],
            ["project", "campus"],
        )
        self.assertEqual(
            project_fields["geometry_derivation"]["allowed_values"],
            ["direct_geometry", "coordinates_to_point"],
        )

    def test_artifact_is_portable_and_map_has_no_runtime_dependency(self) -> None:
        for path in PREVIEW_DIR.iterdir():
            if path.is_file():
                payload = path.read_bytes()
                self.assertNotIn(b"/Users/", payload, path.name)
                self.assertNotIn(b"../", payload, path.name)
        map_html = (PREVIEW_DIR / "map.html").read_text(encoding="utf-8")
        self.assertNotIn("<script src=", map_html)
        self.assertNotIn("<link rel=", map_html)
        attribution = (PREVIEW_DIR / "ATTRIBUTION.txt").read_text(encoding="utf-8")
        self.assertIn("© OpenStreetMap contributors | ODbL-1.0", attribution)
        self.assertIn(
            "Contains modified Copernicus Sentinel data 2024 and 2026.",
            attribution,
        )

    def test_tampered_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            with (clone / "sites.csv").open("ab") as handle:
                handle.write(b"tamper\n")
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "byte count differs"
            ):
                validate_preview(clone)

    def test_v03_review_contract_rejects_invalid_derivation(self) -> None:
        definition = json.loads(REVIEW_DEFINITION.read_text(encoding="utf-8"))
        definition["acceptances"][0]["geometry_derivation"] = "centroid"
        original_load = verified_core._load_json

        def load_with_bad_current(path: Path) -> object:
            if Path(path).resolve() == REVIEW_DEFINITION.resolve():
                return definition
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_with_bad_current
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "geometry derivation differs"
        ):
            verified_core._reviewed_acceptances()

    def test_v03_definition_semantics_are_release_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "reviewed-sites.json"
            definition = json.loads(REVIEW_DEFINITION.read_text(encoding="utf-8"))
            target = next(
                row
                for row in definition["acceptances"]
                if row["project_stable_key"]
                == "curated:kao-data-harlow-campus:klon-03-building"
            )
            target.update(
                {
                    "geometry_method": "satellite_verified_exact_building_footprint",
                    "geometry_scope_class": "official_building_footprint",
                    "horizontal_uncertainty_metres": 0,
                    "precision_scope": "Invented exact footprint claim.",
                }
            )
            bad_definition.write_bytes(_canonical_json(definition))
            with mock.patch.object(
                verified_core, "REVIEW_DEFINITION", bad_definition
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "review_definition_sha256 source hash differs",
            ):
                validate_preview()

    def test_imagery_conflict_cannot_silently_supersede_primary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "imagery-reviews.json"
            definition = json.loads(
                IMAGERY_REVIEW_DEFINITION.read_text(encoding="utf-8")
            )
            target = next(
                row
                for row in definition["records"]
                if row["project_stable_key"]
                == "curated:kao-data-harlow-campus:klon-03-building"
            )
            target["later_review_conflict"]["supersedes_primary"] = True
            bad_definition.write_bytes(_canonical_json(definition))
            with mock.patch.object(
                verified_core, "IMAGERY_REVIEW_DEFINITION", bad_definition
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "cannot supersede without adjudication"
            ):
                verified_core._imagery_contract()

    def test_imagery_delta_outcome_cannot_overclaim_primary_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "imagery-reviews.json"
            definition = json.loads(
                IMAGERY_REVIEW_DEFINITION.read_text(encoding="utf-8")
            )
            target = next(
                row
                for row in definition["records"]
                if row["project_stable_key"]
                == "curated:kao-data-harlow-campus:klon-03-building"
            )
            target["outcome"] = "construction_verified"
            bad_definition.write_bytes(_canonical_json(definition))
            with mock.patch.object(
                verified_core, "IMAGERY_REVIEW_DEFINITION", bad_definition
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "delta outcome differs"
            ):
                verified_core._imagery_contract()

    def test_coordinate_derivation_rejects_boolean_and_out_of_range_values(self) -> None:
        acceptance = {
            "project_stable_key": "test:project",
            "geometry_entity": "project",
            "geometry_derivation": "coordinates_to_point",
        }
        release = {
            "entity_kind": "project",
            "geometry_json": '{"coordinates":[0,0],"type":"Point"}',
            "latitude": "0",
            "longitude": "0",
        }
        campus_release = {"entity_kind": "campus"}
        for coordinates in (
            {"latitude": True, "longitude": 0},
            {"latitude": 91, "longitude": 0},
            {"latitude": 0, "longitude": -181},
        ):
            source = {
                "project": {"geometry": None, "coordinates": coordinates},
                "campus": {},
            }
            with self.subTest(coordinates=coordinates), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "coordinates are invalid"
            ):
                verified_core._resolve_reviewed_geometry(
                    acceptance, source, release, campus_release
                )

    def test_geometry_precision_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:ten-brinke-spata-data-center:active-construction"
            )
            target["horizontal_uncertainty_metres"] = "1"
            _write_rows(clone, "projects.csv", projects)

            sites = _rows_from(clone, "sites.csv")
            site = next(row for row in sites if row["site_id"] == target["site_id"])
            site["horizontal_uncertainty_metres"] = "1"
            _write_rows(clone, "sites.csv", sites)
            geojson = verified_core._geojson(sites)
            (clone / "sites.geojson").write_bytes(_canonical_json(geojson))
            (clone / "map.html").write_bytes(verified_core._map_html(geojson))
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "reviewed geometry precision contract differs|inherited project field differs",
            ):
                validate_preview(clone)

    def test_evidence_source_url_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            projects[0]["geometry_source_url"] = "https://example.invalid/wrong"
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "evidence source URL differs|inherited project field differs",
            ):
                validate_preview(clone)

    def test_workload_scope_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row for row in projects if json.loads(row["workloads_json"])
            )
            workloads = json.loads(target["workloads_json"])
            workloads[0]["deployment_scope"] = "operational"
            target["workloads_json"] = json.dumps(
                workloads, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "workload provenance differs"
            ):
                validate_preview(clone)

    def test_unbound_role_projection_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:cdc-eastern-creek-campus:ec5-current-build"
            )
            target["operator"] = "CDC Data Centres"
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "role projection differs"
            ):
                validate_preview(clone)

    def test_provenance_evidence_content_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            evidence = _rows_from(clone, "evidence.csv")
            target = next(
                row
                for row in evidence
                if row["evidence_id"]
                == "276847d4-183f-5995-ab80-90d4636b467b"
            )
            target["title"] = "Invented role evidence"
            target["content_hash"] = "0" * 64
            _write_rows(clone, "evidence.csv", evidence)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "provenance evidence content differs",
            ):
                validate_preview(clone)

    def test_inherited_evidence_content_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            evidence = _rows_from(clone, "evidence.csv")
            target = next(
                row
                for row in evidence
                if row["evidence_id"]
                == "0176052f-124b-5bf9-b361-a5c97cb98b62"
            )
            target["title"] = "Invented inherited evidence title"
            target["content_hash"] = "0" * 64
            _write_rows(clone, "evidence.csv", evidence)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "inherited evidence content differs",
            ):
                validate_preview(clone)

    def test_tampered_frozen_v02_cannot_be_semantic_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frozen = Path(temporary) / "preview-v0.2"
            shutil.copytree(LEGACY_PREVIEW_V02_DIR, frozen)
            projects = _rows_from(frozen, "projects.csv")
            projects[0]["operator"] = "Invented Holdings LLC"
            _write_rows(frozen, "projects.csv", projects)
            with mock.patch.object(
                verified_core, "LEGACY_PREVIEW_V02_DIR", frozen
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "frozen v0.2 member differs"
            ):
                validate_preview()

    def test_delta_authored_claim_posture_tamper_fails(self) -> None:
        variants = (
            {
                "development_type": "greenfield",
                "development_type_unknown_reason": "",
            },
            {
                "operating_model": "colocation",
                "operating_model_unknown_reason": "",
                "operating_model_evidence_id": (
                    "1337f6ef-1e09-5b6e-a1e0-55fbdcf95bf3"
                ),
            },
        )
        for changes in variants:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                clone = Path(temporary) / "preview"
                shutil.copytree(PREVIEW_DIR, clone)
                projects = _rows_from(clone, "projects.csv")
                target = next(
                    row
                    for row in projects
                    if row["project_stable_key"]
                    == "curated:kao-data-harlow-campus:klon-03-building"
                )
                target.update(changes)
                _write_rows(clone, "projects.csv", projects)
                _refresh_unsigned_manifest(clone)
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "current reviewed-site project projection differs",
                ):
                    validate_preview(clone)

    def test_site_name_tamper_fails_after_manifest_refresh(self) -> None:
        site_ids = (
            "vcc-site-00808116377785b5c125",
            "vcc-site-c48f4a7325dfc30566cd",
        )
        for site_id in site_ids:
            with self.subTest(site_id=site_id), tempfile.TemporaryDirectory() as temporary:
                clone = Path(temporary) / "preview"
                shutil.copytree(PREVIEW_DIR, clone)
                sites = _rows_from(clone, "sites.csv")
                target = next(row for row in sites if row["site_id"] == site_id)
                target["name"] = "Invented Site Name"
                _write_rows(clone, "sites.csv", sites)
                _refresh_unsigned_manifest(clone)
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "inherited site fields differ|site projection differs",
                ):
                    validate_preview(clone)

    def test_evidence_usage_extras_fail_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            evidence = _rows_from(clone, "evidence.csv")
            target = evidence[0]
            roles = json.loads(target["roles_json"])
            roles.append("role:owner")
            target["roles_json"] = json.dumps(
                sorted(roles), ensure_ascii=False, separators=(",", ":")
            )
            project_ids = json.loads(target["project_ids_json"])
            project_ids.append("invented-project-id")
            target["project_ids_json"] = json.dumps(
                sorted(project_ids), ensure_ascii=False, separators=(",", ":")
            )
            _write_rows(clone, "evidence.csv", evidence)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "evidence usage closure differs"
            ):
                validate_preview(clone)

    def test_inherited_geometry_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion"
            )
            target["latitude"] = "0"
            target["longitude"] = "0"
            target["geometry_json"] = '{"coordinates":[0,0],"type":"Point"}'
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "inherited project field differs"
            ):
                validate_preview(clone)

    def test_project_id_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            projects[0]["project_id"] = "invented-project-id"
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "inherited project field differs|project id differs",
            ):
                validate_preview(clone)

    def test_provenance_contract_cannot_reclassify_frozen_v02_claims(self) -> None:
        base = json.loads(
            verified_core.PROVENANCE_DEFINITION.read_text(encoding="utf-8")
        )
        variants: list[tuple[str, dict[str, object], str]] = []
        workload_scope = json.loads(json.dumps(base))
        workload_scope["workload_scope_bindings"][0]["deployment_scope"] = (
            "operational"
        )
        variants.append(
            ("workload_scope", workload_scope, "workload provenance identity differs")
        )
        workload_class = json.loads(json.dumps(base))
        workload_class["workload_scope_bindings"][0]["workload"] = "bitcoin_mining"
        variants.append(
            (
                "workload_class",
                workload_class,
                "workload bindings differ from frozen v0.2",
            )
        )
        invented_role = json.loads(json.dumps(base))
        invented_role["role_bindings"][0].update(
            {"party": "Invented Holdings", "role": "owner"}
        )
        variants.append(
            ("invented_role", invented_role, "role decisions differ from frozen v0.2")
        )
        removed_exclusions = json.loads(json.dumps(base))
        removed_exclusions["excluded_source_roles"] = []
        variants.append(
            (
                "removed_exclusions",
                removed_exclusions,
                "role decisions differ from frozen v0.2",
            )
        )
        original_load = verified_core._load_json
        for name, definition, error in variants:
            def load_with_variant(path: Path, definition: object = definition) -> object:
                if Path(path).resolve() == verified_core.PROVENANCE_DEFINITION.resolve():
                    return definition
                return original_load(path)

            with self.subTest(name=name), mock.patch.object(
                verified_core, "_load_json", side_effect=load_with_variant
            ), self.assertRaisesRegex(VerifiedConstructionCoreError, error):
                verified_core._provenance_contract()

    def test_point_coordinate_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:avaio-taurus-brandon-mississippi-campus:phase-one-current-campus-build"
            )
            target["latitude"] = "0"
            target["longitude"] = "0"
            _write_rows(clone, "projects.csv", projects)
            sites = _rows_from(clone, "sites.csv")
            site = next(row for row in sites if row["site_id"] == target["site_id"])
            site["latitude"] = "0"
            site["longitude"] = "0"
            _write_rows(clone, "sites.csv", sites)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "geometry representative coordinates differ|inherited project field differs",
            ):
                validate_preview(clone)

    def test_semantic_geojson_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            geojson_path = clone / "sites.geojson"
            geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
            point = next(
                feature
                for feature in geojson["features"]
                if feature["geometry"]["type"] == "Point"
            )
            point["geometry"]["coordinates"][0] += 0.5
            geojson_path.write_bytes(_canonical_json(geojson))
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "GeoJSON and site table differ"
            ):
                validate_preview(clone)

    def test_typed_metric_schema_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            with projects_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                fields = list(reader.fieldnames or ())
                rows = list(reader)
            target = next(
                row for row in rows if json.loads(row["power_observations_json"])
            )
            observations = json.loads(target["power_observations_json"])
            del observations[0]["method"]
            target["power_observations_json"] = json.dumps(
                observations, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            projects_path.write_text(buffer.getvalue(), encoding="utf-8", newline="")
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "observation schema differs|inherited project field differs",
            ):
                validate_preview(clone)

    def test_selection_report_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            report_path = clone / "selection-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["final_release_gates"]["site_count"].update(
                {"actual": 100, "passed": True}
            )
            report["reviewed_overlay_queue"][0]["decision"] = "accepted"
            report_path.write_bytes(_canonical_json(report))
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "selection-report values differ"
            ):
                validate_preview(clone)

    def test_readme_overclaim_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            (clone / "README.md").write_text(
                "# FINAL RELEASE\n\nAll sites are operational and independently "
                "satellite-verified.\n",
                encoding="utf-8",
            )
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "preview README differs"
            ):
                validate_preview(clone)

    @unittest.skipUnless(
        (SOURCE_RELEASE / "construction_pipeline.csv").is_file(),
        "ignored source corpus is not hydrated",
    )
    def test_overlay_geometry_reference_must_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            bad_definition = temporary_path / "overlays.json"
            definition = json.loads(OVERLAY_DEFINITION.read_text(encoding="utf-8"))
            definition["overlays"][0]["geometry_stable_key"] = (
                "osm:way/does-not-exist:development-project"
            )
            bad_definition.write_bytes(_canonical_json(definition))
            with (
                mock.patch.object(
                    verified_core, "OVERLAY_DEFINITION", bad_definition
                ),
                mock.patch.object(
                    verified_core,
                    "V03_OVERLAY_DEFINITION_SHA256",
                    hashlib.sha256(bad_definition.read_bytes()).hexdigest(),
                ),
                self.assertRaisesRegex(
                VerifiedConstructionCoreError, "geometry identity differs"
                ),
            ):
                verified_core.build_preview(temporary_path / "preview")

    @unittest.skipUnless(
        (SOURCE_RELEASE / "construction_pipeline.csv").is_file()
        and REVIEW_DEFINITION.is_file()
        and OVERLAY_DEFINITION.is_file(),
        "ignored source corpus is not hydrated",
    )
    def test_hydrated_source_rebuild_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            build_preview(rebuilt)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in PREVIEW_DIR.iterdir()},
            )
            for expected in PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )


if __name__ == "__main__":
    unittest.main()
