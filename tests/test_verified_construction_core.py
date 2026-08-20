from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import datacenter_atlas.verified_construction_core as verified_core

from datacenter_atlas.verified_construction_core import (
    CURRENT_V07_PREVIEW_DIR,
    CURRENT_V07_PREVIEW_ID,
    LEGACY_PREVIEW_V01_DIR,
    LEGACY_PREVIEW_V02_DIR,
    LEGACY_PREVIEW_V03_DIR,
    LEGACY_PREVIEW_V04_DIR,
    LEGACY_PREVIEW_V05_COMMIT,
    LEGACY_PREVIEW_V05_DIR,
    LEGACY_PREVIEW_V06_COMMIT,
    LEGACY_PREVIEW_V06_DIR,
    LEGACY_PREVIEW_V06_MANIFEST_SHA256,
    OVERLAY_DEFINITION,
    PREVIEW_DIR,
    REVIEW_DEFINITION,
    SOURCE_RELEASE,
    VerifiedConstructionCoreError,
    load_current_v07_profile,
    validate_frozen_preview,
    validate_frozen_v01,
    validate_frozen_v02,
    validate_frozen_v03,
    validate_frozen_v04,
    validate_frozen_v05,
    validate_frozen_v06,
    validate_preview as validate_preview_dispatch,
)


def validate_preview(path: Path = PREVIEW_DIR) -> dict[str, object]:
    """Exercise the semantic v0.6 validator in legacy tests."""
    manifest = json.loads((Path(path) / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("preview_id") == "2026-08-20-preview-v0.6":
        return verified_core._validate_v06_preview_dispatch(Path(path))
    return validate_preview_dispatch(Path(path))


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


def _replace_embedded_csv_row(
    binding: dict[str, object], fields: tuple[str, ...], row: dict[str, str]
) -> bytes:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerow(
        [row[field] for field in fields]
    )
    payload = buffer.getvalue().encode("utf-8")
    binding.update(
        {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "raw_csv_record_base64": base64.b64encode(payload).decode("ascii"),
        }
    )
    return payload


def _hydrated_vcc_source_inputs_are_present() -> bool:
    required = (
        SOURCE_RELEASE / "construction_pipeline.csv",
        SOURCE_RELEASE / "entities.csv",
        SOURCE_RELEASE / "evidence.csv",
        verified_core.ROOT / "releases/2026-07-18-global-open-v3/entities.csv",
        verified_core.ROOT / "releases/2026-07-18-global-open-v3/evidence.csv",
        verified_core.ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/component-members.csv",
        verified_core.ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/relationships.csv",
    )
    return all(path.is_file() for path in required)


class VerifiedConstructionCorePreviewTest(unittest.TestCase):
    def _validate_refreshed_bridge(
        self,
        canonical_path: Path,
        bridge: dict[str, object],
        *,
        input_replacements: dict[str, Path] | None = None,
    ) -> dict[str, object]:
        replacements = input_replacements or {}
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
                if path_text in replacements:
                    replacement = replacements[path_text]
                    self.assertEqual(
                        hashlib.sha256(replacement.read_bytes()).hexdigest(),
                        expected_sha256,
                    )
                    return replacement
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
        manifest = validate_preview(PREVIEW_DIR)

        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 26,
                "projects": 29,
                "evidence": 63,
                "countries": 17,
                "non_us_sites": 20,
                "official_boundary_projects": 4,
                "reviewed_site_locator_projects": 25,
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
                "curated:green-mountain-undheim-campus:current-two-building-development",
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
                "curated:amazon-salem-township-innovation-campus:active-buildout",
                "curated:green-campus-zrh1-lupfig:data-center-4",
                "curated:microsoft-mount-pleasant-datacenter-campus:second-facility",
                "curated:qscale-q01-levis-campus:building-b",
                "curated:related-openai-oracle-stargate-michigan-saline:current-build",
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-3",
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-5",
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-6",
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

    def test_v05_osm_bridges_preserve_scope_workloads_and_unknowns(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        keys = {
            "green": "curated:green-campus-zrh1-lupfig:data-center-4",
            "saline": "curated:related-openai-oracle-stargate-michigan-saline:current-build",
            "mount": "curated:microsoft-mount-pleasant-datacenter-campus:second-facility",
            "salem": "curated:amazon-salem-township-innovation-campus:active-buildout",
        }
        for key in keys.values():
            row = projects[key]
            self.assertEqual(row["geometry_type"], "Polygon")
            self.assertEqual(row["geometry_source_entity_kind"], "campus")
            self.assertEqual(row["geometry_derivation"], "cross_source_overlay")
            self.assertEqual(row["geometry_authority_class"], "community_mapped")
            self.assertEqual(row["geometry_use_scope"], "campus_locator")
            self.assertEqual(row["independent_imagery_verification"], "false")
            self.assertEqual(row["operating_model"], "unknown")
            self.assertEqual(row["operator"], "")
            self.assertEqual(json.loads(row["power_observations_json"]), [])
            self.assertEqual(json.loads(row["annual_energy_observations_json"]), [])

        overlays = verified_core._reviewed_overlays(hydrated_crosscheck=False)
        green_overlay = next(
            row
            for row in overlays["overlays"]
            if row["source_project_stable_key"] == keys["green"]
        )
        green_bridge = overlays["bridges_by_overlay_id"][green_overlay["overlay_id"]]
        self.assertEqual(green_bridge["geometry_entity"]["entity_kind"], "building")
        self.assertEqual(
            green_bridge["review_decision"]["geometry_use_scope"],
            "campus_locator",
        )
        self.assertIn(
            "project_or_phase_footprint",
            green_bridge["review_decision"]["rejected_claims"],
        )

        saline = projects[keys["saline"]]
        self.assertEqual(
            json.loads(saline["workloads_json"]),
            [
                {
                    "as_of_date": "2026-06-01",
                    "confidence": 0.99,
                    "deployment_scope": "intended",
                    "evidence_id": "ec302d8d-d1c0-594f-88f7-708f6642e827",
                    "method": "company_disclosure",
                    "workload": "ai_specialized_unspecified",
                }
            ],
        )
        self.assertEqual(saline["customers"], "OpenAI; Oracle")
        self.assertEqual(
            [claim["relationship_scope"] for claim in json.loads(saline["role_claims_json"])],
            ["intended", "intended"],
        )
        saline_overlay = next(
            row
            for row in overlays["overlays"]
            if row["source_project_stable_key"] == keys["saline"]
        )
        saline_bridge = overlays["bridges_by_overlay_id"][saline_overlay["overlay_id"]]
        campus_capacity = saline_bridge["construction_source"]["campus"][
            "capacity_estimates_json"
        ]
        self.assertEqual(
            [row["metric"] for row in campus_capacity],
            ["annual_energy_mwh", "grid_connection_mw"],
        )
        self.assertEqual(
            saline["imagery_review_outcome"],
            "tracked_identity_bound_visible_change_followup_only_no_construction_claim",
        )

        salem = projects[keys["salem"]]
        self.assertEqual(
            json.loads(salem["workloads_json"])[0]["workload"], "mixed"
        )
        self.assertEqual(
            json.loads(salem["workloads_json"])[0]["deployment_scope"],
            "intended",
        )
        for key in (keys["mount"], keys["salem"]):
            self.assertEqual(
                projects[key]["imagery_review_outcome"],
                "tracked_identity_bound_uncertain_unsuperseded_no_construction_claim",
            )
        self.assertEqual(
            projects[keys["green"]]["imagery_review_outcome"],
            "not_reviewed_for_core_preview",
        )

    def test_imagery_provenance_preserves_portability_and_conflicts(self) -> None:
        report = json.loads((PREVIEW_DIR / "selection-report.json").read_text())
        records = {
            row["project_stable_key"]: row
            for row in report["imagery_review_provenance"]
        }
        self.assertEqual(len(records), 9)
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
        undheim = records[
            "curated:green-mountain-undheim-campus:current-two-building-development"
        ]
        self.assertEqual(
            undheim["review_type"], "publisher_contractor_drone_context"
        )
        self.assertTrue(undheim["portable_identity_binding"])
        self.assertFalse(undheim["independent_imagery_verification"])
        self.assertTrue(undheim["no_claim_guardrail"])
        for field in (
            "used_for_geometry",
            "used_for_status",
            "used_for_capacity",
            "used_for_progress",
            "used_for_building_count",
        ):
            self.assertFalse(undheim[field])
        self.assertEqual(
            report["final_release_gates"]["imagery_outcomes_complete"]["actual"],
            9,
        )

    def test_v06_country_delta_preserves_geometry_and_claim_scope(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        pune = projects[
            "curated:adaniconnex-pune-data-center-campus:pnq04-current-build"
        ]
        self.assertEqual(pune["geometry_source_entity_kind"], "project")
        self.assertEqual(pune["geometry_derivation"], "direct_geometry")
        self.assertEqual(pune["geometry_use_scope"], "project_locator")
        self.assertEqual(json.loads(pune["power_observations_json"]), [])

        stt = [
            projects[f"curated:stt-jakarta-data-centre-campus:stt-jakarta-{number}"]
            for number in (3, 5, 6)
        ]
        self.assertEqual(len({row["site_id"] for row in stt}), 1)
        for row in stt:
            self.assertEqual(row["geometry_derivation"], "cross_source_overlay")
            self.assertEqual(row["geometry_authority_class"], "community_mapped")
            self.assertEqual(row["geometry_use_scope"], "campus_locator")
        self.assertEqual(
            [json.loads(row["power_observations_json"])[0]["base"] for row in stt],
            [24.0, 40.0, 40.0],
        )

        undheim = projects[
            "curated:green-mountain-undheim-campus:current-two-building-development"
        ]
        self.assertEqual(undheim["geometry_derivation"], "official_parcel_union")
        self.assertEqual(undheim["geometry_use_scope"], "official_boundary")
        self.assertEqual(undheim["geometry_authority_class"], "official_source")
        self.assertEqual(
            undheim["imagery_review_outcome"],
            "first_party_contractor_drone_imagery_present_not_independently_verified",
        )
        self.assertFalse(
            json.loads(undheim["independent_imagery_verification"])
        )

        for key in (
            "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment",
            "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build",
            "curated:skygard-osl1-hovinbyen-campus:phase-2",
        ):
            self.assertEqual(projects[key]["geometry_use_scope"], "campus_locator")
            self.assertEqual(projects[key]["geometry_authority_class"], "official_source")
        self.assertEqual(
            json.loads(
                projects[
                    "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build"
                ]["power_observations_json"]
            ),
            [],
        )
        skygard_roles = json.loads(
            projects["curated:skygard-osl1-hovinbyen-campus:phase-2"][
                "role_claims_json"
            ]
        )
        self.assertEqual(
            [(row["role"], row["relationship_scope"], row["party"]) for row in skygard_roles],
            [("operator", "intended", "Skygard")],
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
        v04 = validate_frozen_v04()
        self.assertEqual(LEGACY_PREVIEW_V04_DIR.name, "2026-08-20-preview-v0.4")
        self.assertEqual(
            v04["counts"],
            {
                "countries": 12,
                "evidence": 40,
                "non_us_sites": 13,
                "official_boundary_projects": 3,
                "physical_sites": 16,
                "projects": 17,
                "reviewed_site_locator_projects": 14,
            },
        )
        self.assertEqual(validate_preview(LEGACY_PREVIEW_V04_DIR), v04)
        v05 = validate_frozen_v05()
        self.assertEqual(LEGACY_PREVIEW_V05_DIR.name, "2026-08-20-preview-v0.5")
        self.assertEqual(
            LEGACY_PREVIEW_V05_COMMIT,
            "30d4259bca2557da81fb85b805eff0ddd35868a4",
        )
        self.assertEqual(
            v05["counts"],
            {
                "countries": 13,
                "evidence": 48,
                "non_us_sites": 14,
                "official_boundary_projects": 3,
                "physical_sites": 20,
                "projects": 21,
                "reviewed_site_locator_projects": 18,
            },
        )
        self.assertEqual(validate_preview(LEGACY_PREVIEW_V05_DIR), v05)
        v06 = validate_frozen_v06()
        self.assertEqual(LEGACY_PREVIEW_V06_DIR.name, "2026-08-20-preview-v0.6")
        self.assertEqual(
            LEGACY_PREVIEW_V06_MANIFEST_SHA256,
            "05070fab668b1ddd575745cefe3dc36600cd27b48f90702939229c1372674bd5",
        )
        self.assertEqual(
            LEGACY_PREVIEW_V06_COMMIT,
            "ec9cfe665e79cf76ea6b209a5a6e33c8fd1553c6",
        )
        self.assertEqual(
            v06["counts"],
            {
                "countries": 17,
                "evidence": 63,
                "non_us_sites": 20,
                "official_boundary_projects": 4,
                "physical_sites": 26,
                "projects": 29,
                "reviewed_site_locator_projects": 25,
            },
        )
        self.assertEqual(validate_frozen_preview(LEGACY_PREVIEW_V06_DIR), v06)

    def test_current_v07_profile_requires_explicit_complete_definition_pins(
        self,
    ) -> None:
        self.assertEqual(CURRENT_V07_PREVIEW_ID, "2026-08-20-preview-v0.7")
        self.assertEqual(CURRENT_V07_PREVIEW_DIR.name, CURRENT_V07_PREVIEW_ID)
        self.assertEqual(
            verified_core.V07_REVIEW_DEFINITION_SHA256,
            "e6fd80ddb57b49f40cc939a56bc4764e265b2580dc95cba22a4a07cfbd7cb096",
        )
        self.assertEqual(
            verified_core.V07_IMAGERY_REVIEW_DEFINITION_SHA256,
            "93afb53f21a7931202237d0688237a74fd8b7aa01646700785c1f368d69f4e42",
        )
        self.assertEqual(
            verified_core.V07_PROVENANCE_DEFINITION_SHA256,
            "ef4d730fe87bcf2f2e6a99831f2a045023d4f7024d273fc0c82ba52b52648d6f",
        )
        self.assertEqual(
            verified_core.V07_OVERLAY_DEFINITION_SHA256,
            "aa857c31d1b747749fec75b94afc16c48f8a0b28bc025d66f4a58b830cdfff3d",
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "current v0.7 definition pins are incomplete",
        ):
            load_current_v07_profile({})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (
                ("review_definition_sha256", root / "reviewed-sites.json"),
                ("imagery_review_definition_sha256", root / "imagery.json"),
                ("provenance_definition_sha256", root / "provenance.json"),
                ("overlay_definition_sha256", root / "overlays.json"),
            )
            pins = {}
            for index, (field, path) in enumerate(paths):
                path.write_text(f'{{"fixture":{index}}}\n', encoding="utf-8")
                pins[field] = hashlib.sha256(path.read_bytes()).hexdigest()
            with mock.patch.object(
                verified_core, "CURRENT_V07_DEFINITION_PATHS", paths
            ):
                profile = load_current_v07_profile(pins)
            self.assertEqual(profile.preview_id, CURRENT_V07_PREVIEW_ID)
            self.assertEqual(profile.preview_dir, CURRENT_V07_PREVIEW_DIR)
            self.assertEqual(profile.base_preview_id, "2026-08-20-preview-v0.6")
            self.assertEqual(profile.base_preview_dir, LEGACY_PREVIEW_V06_DIR)
            self.assertEqual(
                profile.base_manifest_sha256,
                LEGACY_PREVIEW_V06_MANIFEST_SHA256,
            )
            self.assertEqual(profile.base_commit, LEGACY_PREVIEW_V06_COMMIT)
            self.assertEqual(
                profile.definition_pins,
                tuple(
                    (field, path, pins[field]) for field, path in paths
                ),
            )

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

    def test_frozen_v04_validation_is_isolated_from_v05_globals(self) -> None:
        missing = Path("/definitely-absent-v05-contract.json")
        with (
            mock.patch.object(verified_core, "REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "IMAGERY_REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "PROVENANCE_DEFINITION", missing),
            mock.patch.object(verified_core, "OVERLAY_DEFINITION", missing),
            mock.patch.object(verified_core, "PREVIEW_ID", "invented-preview"),
        ):
            self.assertEqual(
                validate_preview(LEGACY_PREVIEW_V04_DIR)["preview_id"],
                "2026-08-20-preview-v0.4",
            )

    def test_frozen_v04_member_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview-v0.4"
            shutil.copytree(LEGACY_PREVIEW_V04_DIR, clone)
            with (clone / "projects.csv").open("ab") as handle:
                handle.write(b"tamper\n")
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "frozen v0.4 member differs"
            ):
                validate_frozen_v04(clone)

    def test_frozen_v05_member_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview-v0.5"
            shutil.copytree(LEGACY_PREVIEW_V05_DIR, clone)
            with (clone / "projects.csv").open("ab") as handle:
                handle.write(b"tamper\n")
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "frozen v0.5 member differs"
            ):
                validate_frozen_v05(clone)

    def test_frozen_v06_dispatch_is_isolated_from_future_globals(self) -> None:
        missing = Path("/definitely-absent-v07-contract.json")
        with (
            mock.patch.object(verified_core, "REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "IMAGERY_REVIEW_DEFINITION", missing),
            mock.patch.object(verified_core, "PROVENANCE_DEFINITION", missing),
            mock.patch.object(verified_core, "OVERLAY_DEFINITION", missing),
            mock.patch.object(verified_core, "PREVIEW_ID", CURRENT_V07_PREVIEW_ID),
            mock.patch.object(
                verified_core,
                "LEGACY_PREVIEW_V06_MANIFEST_SHA256",
                "0" * 64,
            ),
        ):
            self.assertEqual(
                validate_preview_dispatch(LEGACY_PREVIEW_V06_DIR)["preview_id"],
                "2026-08-20-preview-v0.6",
            )

    def test_frozen_v06_member_tamper_and_symlink_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clone = root / "preview-v0.6"
            shutil.copytree(LEGACY_PREVIEW_V06_DIR, clone)
            with (clone / "map.html").open("ab") as handle:
                handle.write(b"tamper\n")
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "frozen v0.6 member differs: map.html",
            ):
                validate_frozen_v06(clone)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clone = root / "preview-v0.6"
            shutil.copytree(LEGACY_PREVIEW_V06_DIR, clone)
            external = root / "external-map.html"
            external.write_bytes((clone / "map.html").read_bytes())
            (clone / "map.html").unlink()
            (clone / "map.html").symlink_to(external)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "frozen v0.6 member differs: map.html",
            ):
                validate_frozen_v06(clone)

    def test_v04_v05_v06_and_current_manifest_trust_roots_must_not_be_symlinks(
        self,
    ) -> None:
        cases = (
            (
                "v04",
                LEGACY_PREVIEW_V04_DIR,
                validate_frozen_v04,
                "frozen v0.4 manifest trust root differs",
            ),
            (
                "v05",
                LEGACY_PREVIEW_V05_DIR,
                validate_frozen_v05,
                "frozen v0.5 manifest trust root differs",
            ),
            (
                "frozen-v06",
                LEGACY_PREVIEW_V06_DIR,
                validate_frozen_v06,
                "frozen v0.6 manifest trust root differs",
            ),
            (
                "v06",
                PREVIEW_DIR,
                validate_preview,
                "preview manifest trust root differs",
            ),
        )
        for label, source, validator, error in cases:
            for member in ("manifest.json", "manifest.sha256"):
                with (
                    self.subTest(preview=label, member=member),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary)
                    clone = root / label
                    shutil.copytree(source, clone)
                    external = root / f"external-{member}"
                    external.write_bytes((clone / member).read_bytes())
                    (clone / member).unlink()
                    (clone / member).symlink_to(external)
                    with self.assertRaisesRegex(
                        VerifiedConstructionCoreError, error
                    ):
                        validator(clone)

    def test_v03_provenance_clears_unsupported_roles_and_scopes_workloads(self) -> None:
        projects = {row["project_stable_key"]: row for row in _rows("projects.csv")}
        evidence = {row["evidence_id"]: row for row in _rows("evidence.csv")}
        workload_observations = [
            (project, workload)
            for project in projects.values()
            for workload in json.loads(project["workloads_json"])
        ]
        self.assertEqual(len(workload_observations), 5)
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
        self.assertEqual(len(role_claims), 8)
        self.assertEqual(
            {claim["role"] for _, claim in role_claims},
            {"customer", "operator"},
        )
        self.assertEqual(
            {claim["relationship_scope"] for _, claim in role_claims},
            {"intended"},
        )
        for project, claim in role_claims:
            evidence_row = evidence[claim["evidence_id"]]
            self.assertIn(
                f"role:{claim['role']}", json.loads(evidence_row["roles_json"])
            )
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
            len(report["provenance_decisions"]["excluded_source_roles"]), 8
        )

    def test_portable_v06_sources_bridges_and_captures_are_manifest_bound(self) -> None:
        manifest = json.loads((PREVIEW_DIR / "manifest.json").read_text())
        inputs = manifest["portable_source_inputs"]
        self.assertEqual(len(inputs), 25)
        expected_paths = {
            "sources/curated-official-2026-07-19-stt-jakarta-3.json",
            "sources/curated-official-2026-07-19-stt-jakarta-5.json",
            "sources/curated-official-2026-07-19-stt-jakarta-6.json",
            "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json",
            "sources/curated-official-2026-07-20-green-mountain-undheim.json",
            "sources/curated-official-2026-07-21-adaniconnex-pune-pnq04-current-build.json",
            "sources/curated-official-2026-07-22-nscale-kvandal-narvik-current-build.json",
            "sources/curated-official-2026-07-22-skygard-osl1-phase-2-current-build.json",
            "sources/verified-construction-core-v0.6-adaniconnex-pnq04-project-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-goodman-hkg09-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-green-mountain-undheim-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-kvandal-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-kvandal-kartverket-wfs-capture.json",
            "sources/verified-construction-core-v0.6-skygard-osl1-phase-2-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-stt-jakarta-3-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-stt-jakarta-5-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-stt-jakarta-6-campus-geometry-bridge.json",
            "sources/verified-construction-core-v0.6-undheim-kartverket-capture/manifest.json",
            "sources/verified-construction-core-v0.6-undheim-kartverket-capture/openapi.json",
        }
        expected_paths.update(
            f"sources/verified-construction-core-v0.6-undheim-kartverket-capture/1121-46-{parcel}-epsg{epsg}.json"
            for parcel in (316, 317, 319)
            for epsg in (4258, 25832)
        )
        self.assertEqual(
            {row["path"] for row in inputs},
            expected_paths,
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
        self.assertEqual(len(parent_pins), 15)
        self.assertEqual(
            sorted(len(row["parent_manifests"]) for row in parent_pins),
            [1] * 7 + [2] * 4 + [3] * 4,
        )

    def test_v05_validate_only_succeeds_in_tracked_clean_clone(self) -> None:
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=verified_core.ROOT,
            check=True,
            capture_output=True,
        ).stdout
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "clean-clone"
            clone.mkdir()
            for raw_path in listed.split(b"\0"):
                if not raw_path:
                    continue
                relative = Path(raw_path.decode("utf-8"))
                source = verified_core.ROOT / relative
                if not source.is_file() or source.is_symlink():
                    continue
                destination = clone / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            self.assertFalse(
                (clone / "releases/2026-07-22-open-seed-v97/construction_pipeline.csv").exists()
            )
            self.assertFalse(
                (clone / "releases/2026-07-18-global-open-v3/entities.csv").exists()
            )
            self.assertFalse(
                (
                    clone
                    / "exact_identity_decisions/2026-07-22-public-open-v14/component-members.csv"
                ).exists()
            )
            patched_paths = {
                "ROOT": clone,
                "SOURCE_RELEASE": clone
                / "releases/2026-07-22-open-seed-v97",
                "REVIEW_DEFINITION": clone
                / "definitions/verified-construction-core-v0.5-reviewed-sites.json",
                "IMAGERY_REVIEW_DEFINITION": clone
                / "definitions/verified-construction-core-v0.5-imagery-reviews.json",
                "PROVENANCE_DEFINITION": clone
                / "definitions/verified-construction-core-v0.5-provenance.json",
                "OVERLAY_DEFINITION": clone
                / "definitions/verified-construction-core-reviewed-overlays-v3.json",
                "PREVIEW_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.5",
                "LEGACY_PREVIEW_V01_DIR": clone
                / "verified_construction_core/2026-08-19-preview-v0.1",
                "LEGACY_PREVIEW_V02_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.2",
                "LEGACY_PREVIEW_V03_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.3",
                "LEGACY_PREVIEW_V04_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.4",
                "GEOMETRY_RELEASES": {
                    release_id: clone / path.relative_to(verified_core.ROOT)
                    for release_id, path in verified_core.GEOMETRY_RELEASES.items()
                },
            }
            with mock.patch.multiple(verified_core, **patched_paths):
                manifest = validate_preview(patched_paths["PREVIEW_DIR"])
            self.assertEqual(manifest["preview_id"], "2026-08-20-preview-v0.5")

    def test_v06_validate_only_succeeds_with_portable_capture_inputs(self) -> None:
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=verified_core.ROOT,
            check=True,
            capture_output=True,
        ).stdout
        relative_paths = {
            Path(raw_path.decode("utf-8"))
            for raw_path in listed.split(b"\0")
            if raw_path
        }
        portable_inputs = verified_core._portable_source_inputs()
        relative_paths.update(Path(row["path"]) for row in portable_inputs)
        relative_paths.update(
            path.relative_to(verified_core.ROOT)
            for path in (
                verified_core.REVIEW_DEFINITION,
                verified_core.IMAGERY_REVIEW_DEFINITION,
                verified_core.PROVENANCE_DEFINITION,
                verified_core.OVERLAY_DEFINITION,
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "clean-clone"
            clone.mkdir()
            for relative in sorted(relative_paths):
                source = verified_core.ROOT / relative
                if not source.is_file() or source.is_symlink():
                    continue
                destination = clone / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            current_preview = (
                clone / "verified_construction_core/2026-08-20-preview-v0.6"
            )
            shutil.copytree(PREVIEW_DIR, current_preview, dirs_exist_ok=True)

            undheim_inputs = [
                row["path"]
                for row in portable_inputs
                if "v0.6-undheim-kartverket-capture/" in row["path"]
            ]
            self.assertEqual(len(undheim_inputs), 8)
            self.assertTrue(all((clone / path).is_file() for path in undheim_inputs))
            self.assertFalse(
                (clone / "releases/2026-07-22-open-seed-v97/construction_pipeline.csv").exists()
            )

            patched_paths = {
                "ROOT": clone,
                "SOURCE_RELEASE": clone / "releases/2026-07-22-open-seed-v97",
                "REVIEW_DEFINITION": clone
                / "definitions/verified-construction-core-v0.6-reviewed-sites.json",
                "IMAGERY_REVIEW_DEFINITION": clone
                / "definitions/verified-construction-core-v0.6-imagery-reviews.json",
                "PROVENANCE_DEFINITION": clone
                / "definitions/verified-construction-core-v0.6-provenance.json",
                "OVERLAY_DEFINITION": clone
                / "definitions/verified-construction-core-reviewed-overlays-v4.json",
                "PREVIEW_DIR": current_preview,
                "LEGACY_PREVIEW_V01_DIR": clone
                / "verified_construction_core/2026-08-19-preview-v0.1",
                "LEGACY_PREVIEW_V02_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.2",
                "LEGACY_PREVIEW_V03_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.3",
                "LEGACY_PREVIEW_V04_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.4",
                "LEGACY_PREVIEW_V05_DIR": clone
                / "verified_construction_core/2026-08-20-preview-v0.5",
                "GEOMETRY_RELEASES": {
                    release_id: clone / path.relative_to(verified_core.ROOT)
                    for release_id, path in verified_core.GEOMETRY_RELEASES.items()
                },
            }
            with mock.patch.multiple(verified_core, **patched_paths):
                manifest = validate_preview(current_preview)
            self.assertEqual(manifest["preview_id"], "2026-08-20-preview-v0.6")

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
        self.assertEqual(report["selected_project_count"], 29)
        self.assertEqual(report["non_selected_source_row_count"], 502)
        self.assertEqual(
            sum(report["selection_first_failure_counts"].values()), 531
        )
        self.assertEqual(report["selection_first_failure_counts"]["selected"], 29)
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
            14,
        )

    def test_machine_readable_schema_covers_tables_and_relationships(self) -> None:
        schema = json.loads((PREVIEW_DIR / "schema.json").read_text())
        self.assertEqual(
            schema["format"],
            "datacenter-atlas-verified-construction-core-schema-v6",
        )
        self.assertEqual(
            set(schema["tables"]), {"projects.csv", "sites.csv", "evidence.csv"}
        )
        self.assertEqual(schema["geojson"]["geometry_equals"], ["sites.csv", "geometry_json"])
        self.assertEqual(
            schema["map"]["derived_from"], ["sites.geojson", "evidence.csv"]
        )
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
            [
                "direct_geometry",
                "coordinates_to_point",
                "cross_source_overlay",
                "official_parcel_union",
            ],
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
        self.assertNotIn("<img", map_html)
        self.assertNotIn("fetch(", map_html)
        self.assertNotIn("XMLHttpRequest", map_html)
        self.assertIn(
            '<a href="https://www.openstreetmap.org/copyright">'
            "© OpenStreetMap contributors</a> — ODbL 1.0",
            map_html,
        )
        self.assertIn(
            '<a href="https://www.kartverket.no/en/api-and-data/terms-of-use">'
            "© Kartverket</a> — CC BY 4.0",
            map_html,
        )
        self.assertIn(
            '<a href="ATTRIBUTION.txt">Full attribution and source terms</a>',
            map_html,
        )
        attribution = (PREVIEW_DIR / "ATTRIBUTION.txt").read_text(encoding="utf-8")
        self.assertIn("© OpenStreetMap contributors | ODbL-1.0", attribution)
        self.assertIn(
            "Contains modified Copernicus Sentinel data 2024 and 2026.",
            attribution,
        )

    def test_map_attribution_is_derived_from_selected_geometry_evidence(self) -> None:
        evidence = _rows("evidence.csv")
        self.assertEqual(
            verified_core._map_attribution_notices(evidence),
            (
                (
                    "© OpenStreetMap contributors",
                    "ODbL 1.0",
                    "https://www.openstreetmap.org/copyright",
                ),
                (
                    "© Kartverket",
                    "CC BY 4.0",
                    "https://www.kartverket.no/en/api-and-data/terms-of-use",
                ),
            ),
        )
        without_osm_geometry = [
            row
            for row in evidence
            if row["source_family"] != "openstreetmap"
            or "geometry" not in json.loads(row["roles_json"])
        ]
        irrelevant_osm_evidence = {
            **evidence[0],
            "evidence_id": "evidence:irrelevant-openstreetmap",
            "source_family": "openstreetmap",
            "roles_json": '["physical_status"]',
        }
        self.assertEqual(
            verified_core._map_attribution_notices(
                [*without_osm_geometry, irrelevant_osm_evidence]
            ),
            (
                (
                    "© Kartverket",
                    "CC BY 4.0",
                    "https://www.kartverket.no/en/api-and-data/terms-of-use",
                ),
            ),
        )
        without_open_data_geometry = [
            row
            for row in without_osm_geometry
            if not row["source_family"].startswith("kartverket_")
            or "geometry" not in json.loads(row["roles_json"])
        ]
        self.assertEqual(
            verified_core._map_attribution_notices(
                [*without_open_data_geometry, irrelevant_osm_evidence]
            ),
            (),
        )

    def test_map_attribution_removal_fails_after_manifest_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            map_path = clone / "map.html"
            map_html = map_path.read_text(encoding="utf-8")
            map_path.write_text(
                map_html.replace(
                    '<a href="https://www.openstreetmap.org/copyright">'
                    "© OpenStreetMap contributors</a> — ODbL 1.0 · ",
                    "",
                ),
                encoding="utf-8",
            )
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "preview map and GeoJSON differ"
            ):
                validate_preview(clone)

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

    def test_v06_definition_semantics_are_release_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_definition = Path(temporary) / "reviewed-sites.json"
            definition = json.loads(REVIEW_DEFINITION.read_text(encoding="utf-8"))
            target = definition["acceptances"][0]
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
                validate_preview(PREVIEW_DIR)

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
            VerifiedConstructionCoreError, "geometry bridge v0.6 semantics differ"
        ):
            verified_core._reviewed_overlays(hydrated_crosscheck=False)

    def test_v06_official_point_cannot_be_coherently_relocated(self) -> None:
        cases = (
            (
                "verified-construction-core-v0.6-adaniconnex-pnq04-project-geometry-bridge.json",
                lambda payload: payload.update(
                    {
                        "latitude_dms": "19º38ʹ48.15ʺ",
                        "latitude_decimal": 19.6467083333,
                    }
                ),
            ),
            (
                "verified-construction-core-v0.6-goodman-hkg09-campus-geometry-bridge.json",
                lambda payload: payload["response"].update(
                    {"wgsLat": 23.367898205}
                ),
            ),
            (
                "verified-construction-core-v0.6-skygard-osl1-phase-2-campus-geometry-bridge.json",
                lambda payload: payload["address"]["representasjonspunkt"].update(
                    {"lat": 60.9294098}
                ),
            ),
        )
        for name, update_fact in cases:
            with self.subTest(bridge=name):
                path = verified_core.ROOT / "sources" / name
                tampered = json.loads(path.read_text(encoding="utf-8"))
                entity = tampered["geometry_entity"]
                entity["latitude"] += 1
                entity["geometry"]["coordinates"][1] += 1
                evidence = tampered["geometry_evidence"]
                update_fact(evidence["fact_payload"])
                evidence["fact_payload_canonical_sha256"] = hashlib.sha256(
                    _canonical_json(evidence["fact_payload"])
                ).hexdigest()
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "official point rights contract differs",
                ):
                    self._validate_refreshed_bridge(path, tampered)

    def test_v06_official_point_rights_cannot_be_relicensed(self) -> None:
        for name in (
            "verified-construction-core-v0.6-adaniconnex-pnq04-project-geometry-bridge.json",
            "verified-construction-core-v0.6-goodman-hkg09-campus-geometry-bridge.json",
            "verified-construction-core-v0.6-skygard-osl1-phase-2-campus-geometry-bridge.json",
        ):
            with self.subTest(bridge=name):
                path = verified_core.ROOT / "sources" / name
                tampered = json.loads(path.read_text(encoding="utf-8"))
                tampered["geometry_evidence"]["license"] = "CC0-1.0"
                tampered["geometry_entity"]["source_license"] = "CC0-1.0"
                tampered["rights"]["geometry_source"] = "Relicensed as CC0."
                tampered["rights"]["geometry_license_url"] = (
                    "https://creativecommons.org/publicdomain/zero/1.0/"
                )
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "official point rights contract differs",
                ):
                    self._validate_refreshed_bridge(path, tampered)

    def test_v06_geometry_evidence_publication_metadata_is_frozen(self) -> None:
        official_point_names = (
            "verified-construction-core-v0.6-adaniconnex-pnq04-project-geometry-bridge.json",
            "verified-construction-core-v0.6-goodman-hkg09-campus-geometry-bridge.json",
            "verified-construction-core-v0.6-skygard-osl1-phase-2-campus-geometry-bridge.json",
        )
        for name in official_point_names:
            with self.subTest(bridge=name, field="published_at"):
                path = verified_core.ROOT / "sources" / name
                tampered = json.loads(path.read_text(encoding="utf-8"))
                tampered["geometry_evidence"]["published_at"] = "2099-01-01T00:00:00Z"
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "official point rights contract differs",
                ):
                    self._validate_refreshed_bridge(path, tampered)

        branch_cases = (
            (
                "verified-construction-core-v0.6-green-mountain-undheim-geometry-bridge.json",
                ("source_family", "published_at", "retrieved_at"),
                "Undheim evidence differs",
            ),
            (
                "verified-construction-core-v0.6-kvandal-campus-geometry-bridge.json",
                ("kind", "title", "source_family", "published_at", "retrieved_at"),
                "Kvandal evidence differs",
            ),
        )
        for name, fields, message in branch_cases:
            for field in fields:
                with self.subTest(bridge=name, field=field):
                    path = verified_core.ROOT / "sources" / name
                    tampered = json.loads(path.read_text(encoding="utf-8"))
                    tampered["geometry_evidence"][field] = f"attacker-{field}"
                    with self.assertRaisesRegex(
                        VerifiedConstructionCoreError, message
                    ):
                        self._validate_refreshed_bridge(path, tampered)

    def test_v06_horizontal_uncertainty_reason_is_frozen(self) -> None:
        overlays = json.loads(OVERLAY_DEFINITION.read_text(encoding="utf-8"))[
            "overlays"
        ]
        self.assertEqual(len(overlays), 8)
        for overlay in overlays:
            path = verified_core.ROOT / overlay["bridge_path"]
            with self.subTest(bridge=path.name):
                tampered = json.loads(path.read_text(encoding="utf-8"))
                tampered["review_decision"][
                    "horizontal_uncertainty_unknown_reason"
                ] = "Attacker supplied uncertainty posture."
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "geometry bridge v0.6 semantics differ",
                ):
                    self._validate_refreshed_bridge(path, tampered)

    def test_v06_stt_embedded_row_cannot_be_coherently_relocated(self) -> None:
        path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.6-stt-jakarta-3-campus-geometry-bridge.json"
        )
        tampered = json.loads(path.read_text(encoding="utf-8"))
        entity = tampered["geometry_entity"]
        source_row = entity["source_row"]
        values = next(
            csv.reader(
                io.StringIO(
                    base64.b64decode(source_row["raw_csv_record_base64"]).decode(
                        "utf-8"
                    )
                )
            )
        )
        row = dict(
            zip(verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS, values, strict=True)
        )
        geometry = json.loads(row["geometry_json"])
        geometry["coordinates"] = [
            [[longitude + 1, latitude] for longitude, latitude in ring]
            for ring in geometry["coordinates"]
        ]
        row["longitude"] = str(float(row["longitude"]) + 1)
        row["geometry_json"] = json.dumps(
            geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        _replace_embedded_csv_row(
            source_row, verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS, row
        )
        entity["longitude"] += 1
        entity["geometry"] = geometry
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "geometry bridge OSM semantics differ"
        ):
            self._validate_refreshed_bridge(path, tampered)

    def test_v06_identity_proof_cohorts_cannot_be_stripped(self) -> None:
        for name in (
            "verified-construction-core-v0.6-goodman-hkg09-campus-geometry-bridge.json",
            "verified-construction-core-v0.6-green-mountain-undheim-geometry-bridge.json",
            "verified-construction-core-v0.6-skygard-osl1-phase-2-campus-geometry-bridge.json",
            "verified-construction-core-v0.6-stt-jakarta-3-campus-geometry-bridge.json",
            "verified-construction-core-v0.6-kvandal-campus-geometry-bridge.json",
        ):
            with self.subTest(bridge=name):
                path = verified_core.ROOT / "sources" / name
                tampered = json.loads(path.read_text(encoding="utf-8"))
                tampered["identity_bridge_evidence"] = tampered[
                    "identity_bridge_evidence"
                ][1:]
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "identity evidence cohort differs",
                ):
                    self._validate_refreshed_bridge(path, tampered)

    def test_v06_kvandal_capture_anchor_cannot_be_refreshed(self) -> None:
        path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.6-kvandal-campus-geometry-bridge.json"
        )
        tampered = json.loads(path.read_text(encoding="utf-8"))
        capture_path_text = tampered["geometry_release"]["capture"]["path"]
        capture = json.loads(
            (verified_core.ROOT / capture_path_text).read_text(encoding="utf-8")
        )
        capture["feature"]["official_representative_point"]["coordinates"][0] += 1
        with tempfile.TemporaryDirectory() as temporary:
            replacement = Path(temporary) / "capture.json"
            replacement.write_bytes(_canonical_json(capture))
            tampered["geometry_release"]["capture"].update(
                {
                    "bytes": replacement.stat().st_size,
                    "sha256": hashlib.sha256(replacement.read_bytes()).hexdigest(),
                }
            )
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "Kvandal capture differs"
            ):
                self._validate_refreshed_bridge(
                    path,
                    tampered,
                    input_replacements={capture_path_text: replacement},
                )

    def test_v06_undheim_capture_member_cannot_be_relocated(self) -> None:
        path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.6-green-mountain-undheim-geometry-bridge.json"
        )
        tampered = json.loads(path.read_text(encoding="utf-8"))
        release = tampered["geometry_release"]
        member_name = "1121-46-316-epsg25832.json"
        member_path_text = release["members"][member_name]["path"]
        manifest_path_text = release["manifest"]["path"]
        member = json.loads(
            (verified_core.ROOT / member_path_text).read_text(encoding="utf-8")
        )
        for point in member["features"][0]["geometry"]["coordinates"][0]:
            point[0] += 100000
        manifest = json.loads(
            (verified_core.ROOT / manifest_path_text).read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            member_replacement = temporary_path / member_name
            member_replacement.write_bytes(_canonical_json(member))
            member_binding = {
                "bytes": member_replacement.stat().st_size,
                "sha256": hashlib.sha256(member_replacement.read_bytes()).hexdigest(),
            }
            release["members"][member_name].update(member_binding)
            manifest["members"][member_name].update(member_binding)
            manifest_replacement = temporary_path / "manifest.json"
            manifest_replacement.write_bytes(_canonical_json(manifest))
            release["manifest"].update(
                {
                    "bytes": manifest_replacement.stat().st_size,
                    "sha256": hashlib.sha256(
                        manifest_replacement.read_bytes()
                    ).hexdigest(),
                }
            )
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "Undheim members differ"
            ):
                self._validate_refreshed_bridge(
                    path,
                    tampered,
                    input_replacements={
                        member_path_text: member_replacement,
                        manifest_path_text: manifest_replacement,
                    },
                )

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

    def test_green_building_cannot_be_relabelled_as_facility_container(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.5-green-zrh1-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        entity = tampered["geometry_entity"]
        source_row = entity["source_row"]
        values = next(
            csv.reader(
                io.StringIO(
                    base64.b64decode(source_row["raw_csv_record_base64"]).decode(
                        "utf-8"
                    )
                )
            )
        )
        row = dict(
            zip(verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS, values, strict=True)
        )
        row["entity_kind"] = "facility"
        row["entity_id"] = verified_core.atlas_stable_id(
            "entity", row["stable_key"], "facility"
        )
        _replace_embedded_csv_row(
            source_row, verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS, row
        )
        projection = verified_core._global_geometry_entity_projection(row)
        entity.clear()
        entity.update(projection)
        entity["source_row"] = source_row

        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "geometry bridge parent source-row binding differs",
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

        attacker_allowlist = json.loads(
            json.dumps(verified_core.BRIDGE_PARENT_ROW_BINDINGS)
        )
        attacker_allowlist[
            "curated:green-campus-zrh1-lupfig:data-center-4"
        ]["geometry_entity"].update(
            {"bytes": source_row["bytes"], "sha256": source_row["sha256"]}
        )
        with (
            mock.patch.object(
                verified_core, "BRIDGE_PARENT_ROW_BINDINGS", attacker_allowlist
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "geometry bridge OSM entity differs",
            ),
        ):
            self._validate_refreshed_bridge(bridge_path, tampered)

    def test_green_identity_predicate_rejects_refreshed_address_claim(self) -> None:
        bridge_path = (
            verified_core.ROOT
            / "sources/verified-construction-core-v0.5-green-zrh1-campus-geometry-bridge.json"
        )
        tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
        evidence = tampered["identity_bridge_evidence"][0]
        evidence["address_extraction"]["street"] = "Invented Street"
        with (
            mock.patch.object(verified_core, "GREEN_IDENTITY_EVIDENCE", evidence),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "geometry bridge Green address identity differs",
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
                "preview inherited project field differs|current reviewed-site project projection differs|reviewed geometry or imagery contract differs",
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
            (clone / "map.html").write_bytes(
                verified_core._map_html(
                    geojson,
                    _rows_from(clone, "evidence.csv"),
                )
            )
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
                "evidence source URL differs|inherited project field differs|current reviewed-site geometry evidence differs",
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
                "workload provenance differs|current reviewed-site project projection differs|inherited project field differs",
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
                validate_preview(PREVIEW_DIR)

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
                    == "curated:green-campus-zrh1-lupfig:data-center-4"
                )
                target.update(changes)
                _write_rows(clone, "projects.csv", projects)
                _refresh_unsigned_manifest(clone)
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "current reviewed-site project projection differs|current reviewed-site typed metrics differ|inherited project field differs",
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

    def test_saline_campus_capacity_cannot_be_promoted_to_project(self) -> None:
        overlays = verified_core._reviewed_overlays(hydrated_crosscheck=False)
        overlay = next(
            row
            for row in overlays["overlays"]
            if row["source_project_stable_key"]
            == "curated:related-openai-oracle-stargate-michigan-saline:current-build"
        )
        capacities = overlays["bridges_by_overlay_id"][overlay["overlay_id"]][
            "construction_source"
        ]["campus"]["capacity_estimates_json"]
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(PREVIEW_DIR, clone)
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:related-openai-oracle-stargate-michigan-saline:current-build"
            )
            target["power_observations_json"] = json.dumps(
                [row for row in capacities if row["metric"] == "grid_connection_mw"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            target["power_unknown_reason"] = ""
            target["annual_energy_observations_json"] = json.dumps(
                [row for row in capacities if row["metric"] == "annual_energy_mwh"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            target["annual_energy_unknown_reason"] = ""
            _write_rows(clone, "projects.csv", projects)
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "current reviewed-site typed metrics differ|current reviewed-site project projection differs|inherited project field differs",
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
        _hydrated_vcc_source_inputs_are_present(),
        "hydration-only: seven ignored source inputs are not all present",
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
                    "V06_OVERLAY_DEFINITION_SHA256",
                    hashlib.sha256(bad_definition.read_bytes()).hexdigest(),
                ),
                self.assertRaisesRegex(
                    VerifiedConstructionCoreError, "geometry bridge source hash differs"
                ),
            ):
                verified_core._build_v06_preview(temporary_path / "preview")

    @unittest.skipUnless(
        _hydrated_vcc_source_inputs_are_present(),
        "hydration-only: seven ignored source inputs are not all present",
    )
    def test_hydrated_source_rebuild_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            verified_core._build_v06_preview(rebuilt)
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

    def test_v07_artifact_counts_claims_and_attribution_are_frozen(self) -> None:
        manifest = validate_preview_dispatch(CURRENT_V07_PREVIEW_DIR)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 33,
                "projects": 36,
                "evidence": 79,
                "countries": 23,
                "non_us_sites": 27,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 31,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 41)
        report = json.loads(
            (CURRENT_V07_PREVIEW_DIR / "selection-report.json").read_text()
        )
        self.assertEqual(
            report["selection_first_failure_counts"],
            verified_core.V07_SELECTION_FIRST_FAILURE_COUNTS,
        )
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V07_PREVIEW_DIR, "projects.csv")
        }
        alto = projects[
            "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it"
        ]
        self.assertEqual(alto["operator"], "Alto Infrastructure")
        self.assertEqual(
            {row["deployment_scope"] for row in json.loads(alto["workloads_json"])},
            {"intended"},
        )
        self.assertEqual(len(json.loads(alto["workloads_json"])), 3)
        walqa = projects["curated:aws-walqa-huesca-data-center:current-build"]
        self.assertEqual(walqa["operator"], "")
        self.assertEqual(
            walqa["imagery_review_outcome"],
            "tracked_blind_reject_locally_unsealed_identity_no_construction_claim",
        )
        sel3 = projects[
            "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2"
        ]
        self.assertEqual(sel3["country"], "Korea, Republic of")
        self.assertEqual(sel3["geometry_derivation"], "cross_source_geometry")
        map_html = (CURRENT_V07_PREVIEW_DIR / "map.html").read_text()
        for label in (
            "OpenStreetMap",
            "Kartverket",
            "Direction générale des Finances publiques (DGFiP) — Cadastre Etalab — millésime 1 June 2026",
            "Lands Department",
            "Valsts zemes dienests",
            "City and County of Denver",
        ):
            self.assertIn(label, map_html)
        self.assertNotIn("<script src=", map_html)
        self.assertNotIn("<link rel=", map_html)
        schema = json.loads((CURRENT_V07_PREVIEW_DIR / "schema.json").read_text())
        self.assertEqual(
            schema["map"]["derived_from"], ["sites.geojson", "evidence.csv"]
        )

    def test_v07_refreshed_manifest_and_bridge_pins_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V07_PREVIEW_DIR, clone)
            map_path = clone / "map.html"
            map_path.write_text(
                map_path.read_text().replace("City and County of Denver", "Denver"),
                encoding="utf-8",
            )
            _refresh_unsigned_manifest(clone)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "v0.7 manifest semantics differ"
            ):
                validate_preview_dispatch(clone)
        reviewed = json.loads(
            (verified_core.ROOT / "definitions/verified-construction-core-v0.7-reviewed-sites.json").read_text()
        )
        acceptance = reviewed["acceptances"][0]
        original = acceptance["bridge_sha256"]
        acceptance["bridge_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "immutable bridge profile differs"
        ):
            verified_core._validate_v07_bridge(
                acceptance, {}, hydrated_crosscheck=False
            )
        acceptance["bridge_sha256"] = original

    def test_v07_overlay_required_fields_are_not_self_describing(self) -> None:
        overlay_path = (
            verified_core.ROOT
            / "definitions/verified-construction-core-reviewed-overlays-v5.json"
        )
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        overlay["required_fields"].append("attacker_field")
        for row in overlay["overlays"]:
            row["attacker_field"] = "accepted-by-self-described-schema"
        original_load = verified_core._load_json

        def load_with_refreshed_overlay(path: Path) -> object:
            if Path(path).resolve() == overlay_path.resolve():
                return overlay
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_with_refreshed_overlay
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "overlay required fields differ"
        ):
            verified_core._v07_contracts(hydrated_crosscheck=False)

    def test_v07_corpus_free_and_hydrated_rebuilds_are_byte_exact(self) -> None:
        for hydrated in (False, True):
            if hydrated and not _hydrated_vcc_source_inputs_are_present():
                continue
            with self.subTest(hydrated=hydrated), tempfile.TemporaryDirectory() as temporary:
                rebuilt = Path(temporary) / "preview"
                with mock.patch.object(
                    verified_core,
                    "_v07_hydrated_crosscheck_available",
                    return_value=hydrated,
                ):
                    verified_core.build_preview(rebuilt)
                self.assertEqual(
                    {path.name for path in rebuilt.iterdir()},
                    {path.name for path in CURRENT_V07_PREVIEW_DIR.iterdir()},
                )
                for expected in CURRENT_V07_PREVIEW_DIR.iterdir():
                    self.assertEqual(
                        (rebuilt / expected.name).read_bytes(),
                        expected.read_bytes(),
                        expected.name,
                    )


if __name__ == "__main__":
    unittest.main()
