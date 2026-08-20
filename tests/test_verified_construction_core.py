from __future__ import annotations

import base64
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
    LEGACY_PREVIEW_V01_DIR,
    LEGACY_PREVIEW_V02_DIR,
    LEGACY_PREVIEW_V03_DIR,
    OVERLAY_DEFINITION,
    PREVIEW_DIR,
    REVIEW_DEFINITION,
    SOURCE_RELEASE,
    VerifiedConstructionCoreError,
    build_preview,
    validate_frozen_v01,
    validate_frozen_v02,
    validate_frozen_v03,
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
    def _validate_refreshed_bridge(
        self, canonical_path: Path, bridge: dict[str, object]
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            refreshed_path = Path(temporary) / canonical_path.name
            refreshed_path.write_bytes(_canonical_json(bridge))
            refreshed_sha256 = hashlib.sha256(refreshed_path.read_bytes()).hexdigest()
            relative_path = canonical_path.relative_to(verified_core.ROOT).as_posix()
            original_repository_input = verified_core._repository_input

            def repository_input(
                path_text: str, expected_sha256: str, field: str
            ) -> Path:
                if path_text == relative_path and field == "geometry bridge":
                    self.assertEqual(expected_sha256, refreshed_sha256)
                    return refreshed_path
                return original_repository_input(path_text, expected_sha256, field)

            with mock.patch.object(
                verified_core, "_repository_input", side_effect=repository_input
            ):
                return verified_core._validate_geometry_bridge(
                    relative_path,
                    refreshed_sha256,
                    hydrated_crosscheck=False,
                )

    def test_tracked_preview_is_closed_and_honestly_labelled(self) -> None:
        manifest = validate_preview()

        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 16,
                "projects": 17,
                "evidence": 40,
                "countries": 12,
                "non_us_sites": 13,
                "official_boundary_projects": 3,
                "reviewed_site_locator_projects": 14,
            },
        )
        self.assertEqual(manifest["release_status"], "preview")
        self.assertIs(manifest["publishable_as_final"], False)

    def test_geometry_precision_and_verification_posture_are_explicit(self) -> None:
        projects = _rows("projects.csv")
        official_boundary_keys = {
            row["project_stable_key"]
            for row in projects
            if row["geometry_authority_class"] == "official_source"
            and row["geometry_use_scope"] == "official_boundary"
        }
        self.assertEqual(
            official_boundary_keys,
            {
                "curated:coresite-de3-race-street-campus:de3",
                "curated:scala-praia-do-futuro-campus:sforpf01",
                "curated:verne-mantsala-data-center-campus:current-development",
            },
        )
        community_locator_keys = {
            row["project_stable_key"]
            for row in projects
            if row["geometry_authority_class"] == "community_mapped"
        }
        self.assertEqual(
            community_locator_keys,
            {
                "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion",
                "curated:qscale-q01-levis-campus:building-b",
            },
        )
        self.assertTrue(
            all(
                row["geometry_use_scope"] == "campus_locator"
                and row["verification_posture"].endswith("reviewed_site_locator")
                for row in projects
                if row["project_stable_key"] in community_locator_keys
            )
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

    def test_v04_osm_bridges_are_locator_only_and_preserve_official_claims(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        atnorth = projects[
            "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion"
        ]
        qscale = projects["curated:qscale-q01-levis-campus:building-b"]
        for row in (atnorth, qscale):
            self.assertEqual(row["geometry_type"], "Polygon")
            self.assertEqual(row["geometry_derivation"], "cross_source_overlay")
            self.assertEqual(row["geometry_authority_class"], "community_mapped")
            self.assertEqual(row["geometry_use_scope"], "campus_locator")
            self.assertEqual(
                row["verification_posture"],
                "recent_authoritative_physical_observation_plus_reviewed_site_locator",
            )
            self.assertEqual(row["independent_imagery_verification"], "false")
            self.assertEqual(
                row["imagery_review_outcome"], "not_reviewed_for_core_preview"
            )
            self.assertEqual(row["operating_model"], "unknown")
            self.assertEqual(row["operator"], "")
            self.assertEqual(json.loads(row["workloads_json"]), [])
            self.assertTrue(row["horizontal_uncertainty_unknown_reason"])

        self.assertEqual(atnorth["last_observed_physical_status"], "under_construction")
        self.assertEqual(atnorth["status_as_of"], "2026-07-21")
        self.assertEqual(atnorth["status_age_days_at_review"], "30")
        self.assertEqual(
            atnorth["status_evidence_id"],
            "5d2dd8ab-e30c-5a8d-816e-6b5b744cc665",
        )
        self.assertEqual(json.loads(atnorth["power_observations_json"]), [])
        self.assertEqual(json.loads(atnorth["annual_energy_observations_json"]), [])
        self.assertEqual(json.loads(atnorth["efficiency_observations_json"]), [])

        self.assertEqual(qscale["last_observed_physical_status"], "under_construction")
        self.assertEqual(qscale["status_as_of"], "2026-06-04")
        self.assertEqual(qscale["status_age_days_at_review"], "77")
        power = json.loads(qscale["power_observations_json"])
        self.assertEqual(len(power), 1)
        self.assertEqual(
            (power[0]["metric"], power[0]["stage"], power[0]["base"]),
            ("critical_it_mw", "design", 60.0),
        )
        self.assertEqual(json.loads(qscale["annual_energy_observations_json"]), [])
        self.assertEqual(json.loads(qscale["efficiency_observations_json"]), [])

        sites = {row["site_id"]: row for row in _rows("sites.csv")}
        for project in (atnorth, qscale):
            site = sites[project["site_id"]]
            self.assertEqual(
                json.loads(site["geometry_authority_classes_json"]),
                ["community_mapped"],
            )
            self.assertEqual(
                json.loads(site["geometry_use_scopes_json"]), ["campus_locator"]
            )

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
        v03 = validate_frozen_v03()
        self.assertEqual(LEGACY_PREVIEW_V03_DIR.name, "2026-08-20-preview-v0.3")
        self.assertEqual(
            v03["counts"],
            {
                "countries": 10,
                "evidence": 36,
                "non_us_sites": 11,
                "official_boundary_projects": 3,
                "physical_sites": 14,
                "projects": 15,
                "reviewed_site_locator_projects": 12,
            },
        )
        self.assertEqual(validate_preview(LEGACY_PREVIEW_V03_DIR), v03)

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

    def test_frozen_v03_validation_is_isolated_from_v04_globals(self) -> None:
        missing = Path("/definitely-absent-v04-contract.json")
        with (
            mock.patch.object(verified_core, "REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "IMAGERY_REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "PROVENANCE_DEFINITION", missing),
            mock.patch.object(verified_core, "OVERLAY_DEFINITION", missing),
            mock.patch.object(verified_core, "PREVIEW_ID", "invented-preview"),
        ):
            self.assertEqual(
                validate_preview(LEGACY_PREVIEW_V03_DIR)["preview_id"],
                "2026-08-20-preview-v0.3",
            )

    def test_frozen_v03_member_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview-v0.3"
            shutil.copytree(LEGACY_PREVIEW_V03_DIR, clone)
            with (clone / "projects.csv").open("ab") as handle:
                handle.write(b"tamper\n")
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "frozen v0.3 member differs"
            ):
                validate_frozen_v03(clone)

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
            len(report["provenance_decisions"]["excluded_source_roles"]), 6
        )

    def test_portable_v04_sources_and_bridges_are_manifest_bound(self) -> None:
        manifest = json.loads((PREVIEW_DIR / "manifest.json").read_text())
        inputs = manifest["portable_source_inputs"]
        self.assertEqual(len(inputs), 4)
        self.assertEqual(
            {row["path"] for row in inputs},
            {
                "sources/curated-official-2026-07-21-atnorth-ice02-phase-2-current-build.json",
                "sources/curated-official-2026-07-21-qscale-q01-building-b-current-build.json",
                "sources/verified-construction-core-v0.4-atnorth-ice02-campus-geometry-bridge.json",
                "sources/verified-construction-core-v0.4-qscale-q01-campus-geometry-bridge.json",
            },
        )
        for row in inputs:
            path = verified_core.ROOT / row["path"]
            self.assertEqual(path.stat().st_size, row["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            for parent in row["parent_manifests"]:
                parent_path = verified_core.ROOT / parent["path"]
                self.assertEqual(
                    hashlib.sha256(parent_path.read_bytes()).hexdigest(),
                    parent["sha256"],
                )
        parent_pins = [row for row in inputs if row["parent_manifests"]]
        self.assertEqual(len(parent_pins), 2)
        self.assertTrue(all(len(row["parent_manifests"]) == 3 for row in parent_pins))

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
        self.assertEqual(report["selected_project_count"], 17)
        self.assertEqual(report["non_selected_source_row_count"], 514)
        self.assertEqual(
            sum(report["selection_first_failure_counts"].values()), 531
        )
        self.assertEqual(report["selection_first_failure_counts"]["selected"], 17)
        self.assertIs(report["publishable_as_final"], False)
        self.assertFalse(report["final_release_gates"]["site_count"]["passed"])
        self.assertFalse(report["final_release_gates"]["blind_review"]["passed"])
        self.assertFalse(
            report["final_release_gates"]["clean_clone_rebuild"]["passed"]
        )
        self.assertEqual(
            [row["decision"] for row in report["reviewed_overlay_queue"]].count(
                "accepted"
            ),
            2,
        )

    def test_machine_readable_schema_covers_tables_and_relationships(self) -> None:
        schema = json.loads((PREVIEW_DIR / "schema.json").read_text())
        self.assertEqual(
            schema["format"],
            "datacenter-atlas-verified-construction-core-schema-v4",
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
            ["direct_geometry", "coordinates_to_point", "cross_source_overlay"],
        )
        self.assertEqual(
            project_fields["geometry_authority_class"]["allowed_values"],
            ["official_source", "community_mapped"],
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

    def test_v04_definition_semantics_are_release_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "reviewed-sites.json"
            definition = json.loads(REVIEW_DEFINITION.read_text(encoding="utf-8"))
            target = next(
                row
                for row in definition["acceptances"]
                if row["project_stable_key"]
                == "curated:qscale-q01-levis-campus:building-b"
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

    def test_bridge_cannot_promote_community_geometry_to_official_boundary(self) -> None:
        overlays = json.loads(OVERLAY_DEFINITION.read_text(encoding="utf-8"))
        bridge_path = verified_core.ROOT / overlays["overlays"][0]["bridge_path"]
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        tampered["review_decision"]["geometry_authority_class"] = "official_source"
        tampered["review_decision"]["geometry_use_scope"] = "official_boundary"
        original_load = verified_core._load_json

        def load_with_tampered_bridge(path: Path) -> object:
            if Path(path).resolve() == bridge_path.resolve():
                return tampered
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_with_tampered_bridge
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "geometry bridge review decision differs"
        ):
            verified_core._reviewed_overlays(hydrated_crosscheck=False)

    def test_refreshed_bridge_pin_cannot_relocate_geometry_projection(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-atnorth-ice02-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        tampered["geometry_entity"].update(
            {
                "name": "Invented Equatorial Facility",
                "country": "Brazil",
                "latitude": 0.0,
                "longitude": 0.0,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [0.01, 0.0], [0.01, 0.01], [0.0, 0.0]]
                    ],
                },
            }
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge entity source projection differs",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_refreshed_bridge_pin_cannot_rewrite_v14_identity_projection(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-atnorth-ice02-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        tampered["construction_source"]["project_to_campus"]["relationship"][
            "object_component_id"
        ] = "exact:" + "0" * 64
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge topology relationship differs",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_refreshed_bridge_pin_cannot_relabel_v14_subject_line(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-atnorth-ice02-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        tampered["construction_source"]["project_to_campus"]["subject_member"][
            "source_row"
        ]["line"] = 2
        attacker_allowlist = json.loads(
            json.dumps(verified_core.BRIDGE_PARENT_ROW_BINDINGS)
        )
        attacker_allowlist[
            "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion"
        ]["subject_member"]["line"] = 2
        with mock.patch.object(
            verified_core, "BRIDGE_PARENT_ROW_BINDINGS", attacker_allowlist
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge parent source-row binding differs",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_refreshed_bridge_pin_cannot_replace_qscale_geometry_parent_row(
        self,
    ) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-qscale-q01-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        entity = tampered["geometry_entity"]
        source_row = entity["source_row"]
        raw_record = base64.b64decode(source_row["raw_csv_record_base64"])
        values = next(csv.reader(io.StringIO(raw_record.decode("utf-8"))))
        row = dict(zip(verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS, values, strict=True))
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.01, -0.01],
                    [0.01, -0.01],
                    [0.01, 0.01],
                    [-0.01, 0.01],
                    [-0.01, -0.01],
                ]
            ],
        }
        row.update(
            {
                "latitude": "0.0",
                "longitude": "0.0",
                "geometry_json": json.dumps(
                    geometry,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator="\n").writerow(
            [row[field] for field in verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS]
        )
        replaced_record = buffer.getvalue().encode()
        source_row.update(
            {
                "bytes": len(replaced_record),
                "sha256": hashlib.sha256(replaced_record).hexdigest(),
                "raw_csv_record_base64": base64.b64encode(replaced_record).decode(),
            }
        )
        entity.update({"latitude": 0.0, "longitude": 0.0, "geometry": geometry})
        self.assertEqual(
            verified_core._global_geometry_entity_projection(row),
            {field: value for field, value in entity.items() if field != "source_row"},
        )
        attacker_allowlist = json.loads(
            json.dumps(verified_core.BRIDGE_PARENT_ROW_BINDINGS)
        )
        attacker_allowlist["curated:qscale-q01-levis-campus:building-b"][
            "geometry_entity"
        ].update({"bytes": source_row["bytes"], "sha256": source_row["sha256"]})
        with mock.patch.object(
            verified_core, "BRIDGE_PARENT_ROW_BINDINGS", attacker_allowlist
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge parent source-row binding differs",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_qscale_identity_predicate_rejects_refreshed_address_claim(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-qscale-q01-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        evidence = tampered["identity_bridge_evidence"][0]
        evidence["address_extraction"]["street"] = "Invented Street"
        with (
            mock.patch.object(verified_core, "QSCALE_IDENTITY_EVIDENCE", evidence),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "geometry bridge QScale address identity differs",
            ),
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_refreshed_review_pin_cannot_override_bridge_semantics(self) -> None:
        acceptances = verified_core._reviewed_acceptances()
        target = next(
            row
            for row in acceptances
            if row["project_stable_key"]
            == "curated:qscale-q01-levis-campus:building-b"
        )
        tampered = {
            **target,
            "geometry_method": "satellite_verified_exact_building_footprint",
            "geometry_scope_class": "official_cadastral_building_b_footprint",
            "precision_scope": (
                "Survey-accurate Building B construction footprint independently "
                "verified by satellite."
            ),
        }
        overlays = verified_core._reviewed_overlays(hydrated_crosscheck=False)
        bridge = overlays["bridges_by_overlay_id"][target["geometry_overlay_id"]]
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "refreshed review overlay semantics differ",
        ):
            verified_core._validate_bridge_acceptance_semantics(
                tampered, bridge, label="refreshed review"
            )

    def test_coherent_bridge_and_review_overclaim_fails_allowlist(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.4-qscale-q01-campus-geometry-bridge.json"
        )
        tampered_bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        tampered_bridge["review_decision"].update(
            {
                "geometry_method": "satellite_verified_exact_building_footprint",
                "geometry_scope_class": "official_cadastral_building_b_footprint",
                "precision_scope": (
                    "Survey-accurate Building B construction footprint independently "
                    "verified by satellite."
                ),
            }
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge allowlisted review semantics differ",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered_bridge)

    def test_artifact_authority_scope_tamper_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:qscale-q01-levis-campus:building-b"
            )
            target["geometry_authority_class"] = "official_source"
            target["geometry_use_scope"] = "official_boundary"
            target["verification_posture"] = (
                "recent_authoritative_physical_observation_plus_official_boundary"
            )
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "current reviewed-site project projection differs|reviewed geometry or imagery contract differs",
            ):
                validate_preview(clone)

    def test_imagery_conflict_cannot_silently_supersede_primary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "imagery-reviews.json"
            definition = json.loads(
                (
                    verified_core.ROOT
                    / "definitions/verified-construction-core-v0.3-imagery-reviews.json"
                ).read_text(encoding="utf-8")
            )
            target = next(
                row
                for row in definition["records"]
                if row["project_stable_key"]
                == "curated:kao-data-harlow-campus:klon-03-building"
            )
            target["later_review_conflict"]["supersedes_primary"] = True
            bad_definition.write_bytes(_canonical_json(definition))
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "cannot supersede without adjudication"
            ):
                verified_core._imagery_contract_v03(bad_definition)

    def test_imagery_delta_outcome_cannot_overclaim_primary_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "imagery-reviews.json"
            definition = json.loads(
                (
                    verified_core.ROOT
                    / "definitions/verified-construction-core-v0.3-imagery-reviews.json"
                ).read_text(encoding="utf-8")
            )
            target = next(
                row
                for row in definition["records"]
                if row["project_stable_key"]
                == "curated:kao-data-harlow-campus:klon-03-building"
            )
            target["outcome"] = "construction_verified"
            bad_definition.write_bytes(_canonical_json(definition))
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "delta outcome differs"
            ):
                verified_core._imagery_contract_v03(bad_definition)

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
                    acceptance, source, release, campus_release, None
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
                VerifiedConstructionCoreError,
                "workload provenance differs|inherited project field differs",
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
                VerifiedConstructionCoreError,
                "role projection differs|inherited project field differs",
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
                "provenance evidence content differs|inherited evidence content differs",
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
                    == "curated:qscale-q01-levis-campus:building-b"
                )
                target.update(changes)
                _write_rows(clone, "projects.csv", projects)
                _refresh_unsigned_manifest(clone)
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "current reviewed-site project projection differs|current reviewed-site typed metrics differ",
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
                VerifiedConstructionCoreError,
                "evidence usage closure differs|inherited evidence content differs",
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
            (
                verified_core.ROOT
                / "definitions/verified-construction-core-v0.3-provenance.json"
            ).read_text(encoding="utf-8")
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
        for name, definition, error in variants:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                bad_definition = Path(temporary) / "verified-construction-core-v0.3-provenance.json"
                bad_definition.write_bytes(_canonical_json(definition))
                with self.assertRaisesRegex(VerifiedConstructionCoreError, error):
                    verified_core._provenance_contract_v03(bad_definition)

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
            definition["overlays"][0]["bridge_path"] = "sources/does-not-exist.json"
            bad_definition.write_bytes(_canonical_json(definition))
            with (
                mock.patch.object(
                    verified_core, "OVERLAY_DEFINITION", bad_definition
                ),
                mock.patch.object(
                    verified_core,
                    "V04_OVERLAY_DEFINITION_SHA256",
                    hashlib.sha256(bad_definition.read_bytes()).hexdigest(),
                ),
                self.assertRaisesRegex(
                    VerifiedConstructionCoreError, "geometry bridge source hash differs"
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
