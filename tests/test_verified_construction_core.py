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
    CURRENT_V08_PREVIEW_DIR,
    CURRENT_V08_PREVIEW_ID,
    CURRENT_V09_PREVIEW_DIR,
    CURRENT_V09_PREVIEW_ID,
    CURRENT_V10_PREVIEW_DIR,
    CURRENT_V10_PREVIEW_ID,
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
    load_current_v08_profile,
    load_current_v09_profile,
    load_current_v10_profile,
    validate_frozen_preview,
    validate_frozen_v01,
    validate_frozen_v02,
    validate_frozen_v03,
    validate_frozen_v04,
    validate_frozen_v05,
    validate_frozen_v06,
    validate_frozen_v07,
    validate_frozen_v09,
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
                VerifiedConstructionCoreError,
                "frozen v0.7 manifest hash differs|v0.7 manifest semantics differ",
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
                    verified_core._build_v07_preview(rebuilt)
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

    def test_current_v08_profile_and_frozen_v07_are_exact(self) -> None:
        self.assertEqual(CURRENT_V08_PREVIEW_ID, "2026-08-20-preview-v0.8")
        self.assertEqual(CURRENT_V08_PREVIEW_DIR.name, CURRENT_V08_PREVIEW_ID)
        self.assertEqual(
            verified_core.LEGACY_PREVIEW_V07_MANIFEST_SHA256,
            "36d3f40d2a6ce8c4cf960adb680a3788a216552ca2e53c72fedc7aa3d5d97d6a",
        )
        self.assertEqual(
            verified_core.LEGACY_PREVIEW_V07_COMMIT,
            "86bb4c589a0a6bf3e6d07a2a94c399b69fb016d6",
        )
        self.assertEqual(
            validate_frozen_v07()["counts"],
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
        self.assertEqual(
            validate_preview_dispatch(verified_core.LEGACY_PREVIEW_V07_DIR)[
                "preview_id"
            ],
            "2026-08-20-preview-v0.7",
        )
        self.assertEqual(
            (CURRENT_V08_PREVIEW_DIR / "manifest.sha256").read_text(),
            "a916aa4a438510ac5c1c26b359c7581dc18ca55de4c40ffd59c93424cad70b08"
            "  manifest.json\n",
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "current v0.8 definition pins are incomplete",
        ):
            load_current_v08_profile({})
        pins = {
            field: hashlib.sha256(path.read_bytes()).hexdigest()
            for field, path in verified_core.CURRENT_V08_DEFINITION_PATHS
        }
        profile = load_current_v08_profile(pins)
        self.assertEqual(profile.base_preview_dir, verified_core.LEGACY_PREVIEW_V07_DIR)
        self.assertEqual(
            profile.base_manifest_sha256,
            verified_core.LEGACY_PREVIEW_V07_MANIFEST_SHA256,
        )
        self.assertEqual(profile.base_commit, verified_core.LEGACY_PREVIEW_V07_COMMIT)

    def test_v08_artifact_counts_source_targets_and_claims_are_exact(self) -> None:
        manifest = validate_preview_dispatch(CURRENT_V08_PREVIEW_DIR)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 41,
                "projects": 44,
                "evidence": 100,
                "countries": 25,
                "non_us_sites": 35,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 39,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 57)
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V08_PREVIEW_DIR, "projects.csv")
        }
        delta_keys = set(verified_core.V08_BRIDGE_PROFILES)
        for key in delta_keys:
            row = projects[key]
            self.assertEqual(row["independent_imagery_verification"], "false")
            self.assertEqual(
                row["imagery_review_outcome"], "not_reviewed_for_core_preview"
            )
            self.assertEqual(json.loads(row["workloads_json"]), [])
        macquarie = projects[
            "curated:macquarie-ic3-super-west-facility:phase-1-build"
        ]
        self.assertEqual(macquarie["geometry_source_entity_kind"], "project")
        self.assertEqual(macquarie["geometry_use_scope"], "campus_locator")
        self.assertEqual(
            [row["base"] for row in json.loads(macquarie["power_observations_json"])],
            [6.0],
        )
        self.assertEqual(json.loads(macquarie["efficiency_observations_json"]), [])
        colt = projects[
            "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build"
        ]
        self.assertEqual(colt["geometry_source_entity_kind"], "building")
        self.assertEqual(colt["geometry_use_scope"], "project_locator")
        vie13 = projects[
            "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build"
        ]
        self.assertEqual(vie13["operating_model"], "colocation")
        self.assertEqual(
            vie13["operating_model_evidence_id"],
            "7305379e-4152-58ec-9152-c2d7af3d39c1",
        )
        self.assertEqual(json.loads(vie13["power_observations_json"]), [])
        cdc = projects["curated:cdc-laverton-melbourne-campus:current-build"]
        self.assertEqual(cdc["operator"], "CDC Data Centres")
        self.assertEqual(
            json.loads(cdc["role_claims_json"]),
            [
                {
                    "evidence_id": "d05112cf-0117-5f1a-9b7a-4087ec4f5c8f",
                    "party": "CDC Data Centres",
                    "relationship_scope": "intended",
                    "role": "operator",
                }
            ],
        )
        borealis = projects[
            "curated:borealis-blonduos-data-center-campus:expansion-current-build"
        ]
        self.assertEqual(borealis["operator"], "")
        base_evidence = {
            row["evidence_id"]
            for row in _rows_from(CURRENT_V07_PREVIEW_DIR, "evidence.csv")
        }
        current_evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V08_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(
            set(current_evidence) - base_evidence,
            verified_core.V08_EVIDENCE_IDS,
        )
        project_key_by_id = {
            row["project_id"]: row["project_stable_key"]
            for row in _rows_from(CURRENT_V08_PREVIEW_DIR, "projects.csv")
        }
        evidence_projection = {
            evidence_id: (
                json.loads(current_evidence[evidence_id]["roles_json"]),
                [
                    project_key_by_id[project_id]
                    for project_id in json.loads(
                        current_evidence[evidence_id]["project_ids_json"]
                    )
                ],
            )
            for evidence_id in verified_core.V08_EVIDENCE_IDS
        }
        borealis_key = (
            "curated:borealis-blonduos-data-center-campus:expansion-current-build"
        )
        cdc_key = "curated:cdc-laverton-melbourne-campus:current-build"
        colt_key = (
            "curated:colt-frankfurt3-sossenheim-campus:"
            "frankfurt3-current-facility-build"
        )
        enka_key = (
            "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build"
        )
        equinix_key = "curated:equinix-mu4-munich-data-center:phase-3"
        macquarie_key = "curated:macquarie-ic3-super-west-facility:phase-1-build"
        pure_key = "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build"
        vie13_key = (
            "curated:digital-realty-vienna-vie13-vie16-expansion:"
            "vie13-phase-1-current-build"
        )
        self.assertEqual(
            evidence_projection,
            {
                "0ba37f72-6f9b-5d8f-8b8e-8b66e03dbb11": (
                    ["context:project_context"],
                    [macquarie_key],
                ),
                "0dd3dc39-1457-5bc3-b7d2-7ff44183aed3": (
                    ["context:geometry_identity"],
                    [enka_key],
                ),
                "10cad266-3d5e-591d-a1c4-8ded1e082c7b": (
                    ["typed_metric:critical_it_mw"],
                    [macquarie_key],
                ),
                "4302b7fb-1bf4-5dc7-abf5-9ba24f4556fa": (
                    ["physical_status"],
                    [equinix_key],
                ),
                "4bbf6d0c-4fcb-5dd0-9504-4322a80117b8": (
                    ["geometry"],
                    [vie13_key],
                ),
                "654559c0-3ba5-519b-8215-80eaaf854f5a": (
                    ["physical_status"],
                    [macquarie_key],
                ),
                "6b7130b5-f5f5-50c8-9689-6b8e348e0015": (
                    ["physical_status"],
                    [enka_key],
                ),
                "7305379e-4152-58ec-9152-c2d7af3d39c1": (
                    ["operating_model"],
                    [vie13_key],
                ),
                "7b2675bd-76c0-54b0-82d1-3f5d6cb328b2": (
                    ["geometry"],
                    [macquarie_key],
                ),
                "959963fd-1d27-5927-a972-8a04fd97727e": (
                    ["geometry"],
                    [enka_key],
                ),
                "9ef151e3-b5f8-5421-b9df-f5ac0bfca4a6": (
                    ["physical_status"],
                    [vie13_key],
                ),
                "a63792de-87ff-5a78-8a99-e53260b301f1": (
                    ["typed_metric:critical_it_mw"],
                    [enka_key],
                ),
                "a9d0173c-a00c-5936-b2d2-493a61fc0d53": (
                    ["physical_status"],
                    [pure_key],
                ),
                "b24c0246-2488-55e4-9022-3609124fd8c8": (
                    ["geometry"],
                    [borealis_key],
                ),
                "bd494c0b-3936-5cc0-844a-67cd0db22812": (
                    ["physical_status"],
                    [borealis_key],
                ),
                "bf2135c6-1aa5-58e8-a318-7e67915aa1bb": (
                    ["physical_status", "typed_metric:critical_it_mw"],
                    [colt_key],
                ),
                "d05112cf-0117-5f1a-9b7a-4087ec4f5c8f": (
                    ["physical_status", "role:operator"],
                    [cdc_key],
                ),
                "d0865f65-7e1e-59ab-989c-2d49ec5ce196": (
                    ["geometry"],
                    [colt_key],
                ),
                "e07bd94a-9734-5f78-a7b6-d69e757357c2": (
                    ["geometry"],
                    [cdc_key],
                ),
                "ee256a2f-4e9b-5224-a6ce-e4f95c4a11ed": (
                    ["geometry"],
                    [pure_key],
                ),
                "efe5b5c9-7394-5f0c-951b-051197168c49": (
                    ["geometry"],
                    [equinix_key],
                ),
            },
        )
        self.assertIn(
            "context:project_context",
            json.loads(
                current_evidence[
                    "0ba37f72-6f9b-5d8f-8b8e-8b66e03dbb11"
                ]["roles_json"]
            ),
        )
        self.assertIn(
            "operating_model",
            json.loads(
                current_evidence[
                    "7305379e-4152-58ec-9152-c2d7af3d39c1"
                ]["roles_json"]
            ),
        )
        report = json.loads(
            (CURRENT_V08_PREVIEW_DIR / "selection-report.json").read_text()
        )
        self.assertEqual(
            report["selection_first_failure_counts"],
            verified_core.V08_SELECTION_FIRST_FAILURE_COUNTS,
        )
        self.assertEqual(
            len(report["provenance_decisions"]["context_evidence_bindings"]),
            2,
        )
        map_html = (CURRENT_V08_PREVIEW_DIR / "map.html").read_text()
        self.assertIn("© OpenStreetMap contributors", map_html)
        self.assertIn("Verified Construction Core v0.8 preview", map_html)

    def test_v08_source_target_and_hash_seams_fail_closed(self) -> None:
        reviewed = json.loads(verified_core.V08_REVIEW_DEFINITION.read_text())
        overlays = json.loads(verified_core.V08_OVERLAY_DEFINITION.read_text())
        acceptance_by_key = {
            row["project_stable_key"]: row for row in reviewed["acceptances"]
        }
        overlay_by_key = {
            row["source_project_stable_key"]: row for row in overlays["overlays"]
        }
        mac_key = "curated:macquarie-ic3-super-west-facility:phase-1-build"
        mac = dict(acceptance_by_key[mac_key])
        self.assertEqual(mac["geometry_entity"], "project")
        self.assertEqual(mac["geometry_target_entity_kind"], "campus")
        mac["geometry_target_entity_kind"] = "project"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "immutable bridge profile differs"
        ):
            verified_core._validate_v08_bridge(
                mac, overlay_by_key[mac_key], hydrated_crosscheck=False
            )
        colt_key = (
            "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build"
        )
        colt = dict(acceptance_by_key[colt_key])
        colt["bridge_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "immutable bridge profile differs"
        ):
            verified_core._validate_v08_bridge(
                colt, overlay_by_key[colt_key], hydrated_crosscheck=False
            )
        direct_path = (
            verified_core.ROOT
            / acceptance_by_key[
                "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build"
            ]["bridge_path"]
        )
        direct = json.loads(direct_path.read_text())
        direct_acceptance = acceptance_by_key[
            "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build"
        ]
        verified_core._validate_v08_direct_geometry(direct, direct_acceptance)
        direct["geometry_evidence"]["geometry_canonical_sha256"] = hashlib.sha256(
            _canonical_json(direct["geometry_entity"]["geometry"])
        ).hexdigest()
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "direct geometry projection differs"
        ):
            verified_core._validate_v08_direct_geometry(direct, direct_acceptance)

        def assert_rejected_after_bridge_hash_refresh(
            project_key: str,
            altered_bridge: dict[str, object],
            message: str,
            acceptance_changes: dict[str, object] | None = None,
            altered_source: dict[str, object] | None = None,
            hydrated_crosscheck: bool = False,
        ) -> None:
            acceptance = dict(acceptance_by_key[project_key])
            acceptance.update(acceptance_changes or {})
            source_payload = None
            refreshed_source_sha256 = None
            if altered_source is not None:
                source_payload = _canonical_json(altered_source)
                refreshed_source_sha256 = hashlib.sha256(source_payload).hexdigest()
                source_binding = {
                    "path": acceptance["source_input_path"],
                    "bytes": len(source_payload),
                    "sha256": refreshed_source_sha256,
                }
                acceptance["source_input_bytes"] = len(source_payload)
                acceptance["source_input_sha256"] = refreshed_source_sha256
                acceptance["portable_input_binding"] = source_binding
                altered_bridge["construction_source"]["input"] = source_binding
            payload = _canonical_json(altered_bridge)
            refreshed_sha256 = hashlib.sha256(payload).hexdigest()
            acceptance["bridge_sha256"] = refreshed_sha256
            acceptance["bridge_bytes"] = len(payload)
            refreshed_profile = dict(verified_core.V08_BRIDGE_PROFILES[project_key])
            refreshed_profile["bridge_sha256"] = refreshed_sha256
            if refreshed_source_sha256 is not None:
                refreshed_profile["source_sha256"] = refreshed_source_sha256
            original_repository_input = verified_core._repository_input
            with tempfile.TemporaryDirectory() as temporary:
                altered_path = Path(temporary) / "geometry-bridge.json"
                altered_path.write_bytes(payload)
                altered_source_path = Path(temporary) / "source.json"
                if source_payload is not None:
                    altered_source_path.write_bytes(source_payload)

                def repository_input(
                    path_text: str, expected_sha256: str, field: str
                ) -> Path:
                    if (
                        path_text == acceptance["bridge_path"]
                        and field == "geometry bridge"
                    ):
                        self.assertEqual(expected_sha256, refreshed_sha256)
                        return altered_path
                    if (
                        source_payload is not None
                        and path_text == acceptance["source_input_path"]
                        and field == "v0.8 source input"
                    ):
                        self.assertEqual(expected_sha256, refreshed_source_sha256)
                        return altered_source_path
                    return original_repository_input(
                        path_text, expected_sha256, field
                    )

                with mock.patch.dict(
                    verified_core.V08_BRIDGE_PROFILES,
                    {project_key: refreshed_profile},
                ), mock.patch.object(
                    verified_core,
                    "_repository_input",
                    side_effect=repository_input,
                ), self.assertRaisesRegex(VerifiedConstructionCoreError, message):
                    verified_core._validate_v08_bridge(
                        acceptance,
                        overlay_by_key[project_key],
                        hydrated_crosscheck=hydrated_crosscheck,
                    )

        direct = json.loads(direct_path.read_text())
        direct["geometry_entity"]["source_license"] = "CC0-1.0"
        direct["geometry_evidence"]["license"] = "CC0-1.0"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "direct source metadata differs"
        ):
            verified_core._validate_v08_direct_geometry(
                direct, direct_acceptance
            )
        assert_rejected_after_bridge_hash_refresh(
            direct_acceptance["project_stable_key"],
            direct,
            "geometry profile differs",
        )

        borealis_key = (
            "curated:borealis-blonduos-data-center-campus:expansion-current-build"
        )
        borealis_path = verified_core.ROOT / acceptance_by_key[borealis_key][
            "bridge_path"
        ]
        borealis = json.loads(borealis_path.read_text())
        borealis["rights"]["mixed_rights"] = "All sources relicensed as CC0."
        assert_rejected_after_bridge_hash_refresh(
            borealis_key,
            borealis,
            "rights profile differs",
        )

        borealis = json.loads(borealis_path.read_text())
        borealis["geometry_entity"]["source_row"]["line"] += 1
        assert_rejected_after_bridge_hash_refresh(
            borealis_key,
            borealis,
            "geometry profile differs",
        )

        borealis = json.loads(borealis_path.read_text())
        rejected_claims = borealis["review_decision"]["rejected_claims"][:-1]
        borealis["review_decision"]["rejected_claims"] = rejected_claims
        assert_rejected_after_bridge_hash_refresh(
            borealis_key,
            borealis,
            "review decision profile differs",
            {"rejected_claims": rejected_claims},
        )

        cdc_key = "curated:cdc-laverton-melbourne-campus:current-build"
        cdc_acceptance = dict(acceptance_by_key[cdc_key])
        cdc_acceptance["country"] = "Germany"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "publication target projection differs"
        ):
            verified_core._validate_v08_bridge(
                cdc_acceptance,
                overlay_by_key[cdc_key],
                hydrated_crosscheck=True,
            )

        direct = json.loads(direct_path.read_text())
        direct["geometry_entity"]["entity_id"] = (
            "00000000-0000-0000-0000-000000000000"
        )
        fake_id_acceptance = dict(direct_acceptance)
        fake_id_acceptance["geometry_entity_id"] = direct["geometry_entity"][
            "entity_id"
        ]
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "direct geometry projection differs"
        ):
            verified_core._validate_v08_direct_geometry(
                direct, fake_id_acceptance
            )
        assert_rejected_after_bridge_hash_refresh(
            direct_acceptance["project_stable_key"],
            direct,
            "geometry profile differs",
            {"geometry_entity_id": direct["geometry_entity"]["entity_id"]},
        )

        mac_key = "curated:macquarie-ic3-super-west-facility:phase-1-build"
        mac_path = verified_core.ROOT / acceptance_by_key[mac_key]["bridge_path"]
        mac = json.loads(mac_path.read_text())
        mac_source_path = verified_core.ROOT / acceptance_by_key[mac_key][
            "source_input_path"
        ]
        mac_source = json.loads(mac_source_path.read_text())
        project_capacity = next(
            row for row in mac_source["capacities"] if row["entity"] == "project"
        )
        project_capacity.update(
            {
                "metric": "pue",
                "stage": "design",
                "unit": "ratio",
                "low": 1.5,
                "base": 1.5,
                "high": 1.5,
            }
        )
        evidence_by_key = {row["key"]: row for row in mac_source["evidence"]}
        mac_project = verified_core._v08_source_entity_projection(
            mac_source, evidence_by_key, entity_kind="project"
        )
        mac["construction_source"]["project"].update(mac_project)
        hydration_modes = (
            (False, True)
            if _hydrated_vcc_source_inputs_are_present()
            else (False,)
        )
        for hydrated in hydration_modes:
            with self.subTest(attack="mac-project-capacity", hydrated=hydrated):
                assert_rejected_after_bridge_hash_refresh(
                    mac_key,
                    mac,
                    "v97 project projection differs",
                    altered_source=mac_source,
                    hydrated_crosscheck=hydrated,
                )

        vie_source_path = verified_core.ROOT / direct_acceptance["source_input_path"]
        vie_source = json.loads(vie_source_path.read_text())
        operating_model_evidence = next(
            row
            for row in vie_source["evidence"]
            if row["key"]
            == "digital-realty-vie13-vie16-brochure-updated-2026-06-03-captured-2026-07-20"
        )
        operating_model_evidence.update(
            {
                "source_url": "https://attacker.invalid/evidence",
                "publisher": "Attacker",
                "license": "CC0-1.0",
                "attribution": "Attacker",
            }
        )
        direct = json.loads(direct_path.read_text())
        for hydrated in hydration_modes:
            with self.subTest(attack="vie-evidence-laundering", hydrated=hydrated):
                assert_rejected_after_bridge_hash_refresh(
                    direct_acceptance["project_stable_key"],
                    direct,
                    "used source evidence differs",
                    altered_source=vie_source,
                    hydrated_crosscheck=hydrated,
                )

    def test_v08_overlay_schema_is_not_self_describing(self) -> None:
        overlay = json.loads(verified_core.V08_OVERLAY_DEFINITION.read_text())
        overlay["required_fields"].append("attacker_field")
        for row in overlay["overlays"]:
            row["attacker_field"] = "accepted-by-self-description"
        original_load = verified_core._load_json

        def load_with_refreshed_overlay(path: Path) -> object:
            if Path(path).resolve() == verified_core.V08_OVERLAY_DEFINITION.resolve():
                return overlay
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_with_refreshed_overlay
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.8 overlay required fields differ"
        ):
            verified_core._v08_contracts(hydrated_crosscheck=False)

    def test_v08_corpus_free_and_hydrated_rebuilds_are_byte_exact(self) -> None:
        for hydrated in (False, True):
            if hydrated and not _hydrated_vcc_source_inputs_are_present():
                continue
            with self.subTest(hydrated=hydrated), tempfile.TemporaryDirectory() as temporary:
                rebuilt = Path(temporary) / "preview"
                with mock.patch.object(
                    verified_core,
                    "_v08_hydrated_crosscheck_available",
                    return_value=hydrated,
                ):
                    verified_core._build_v08_preview(rebuilt)
                self.assertEqual(
                    {path.name for path in rebuilt.iterdir()},
                    {path.name for path in CURRENT_V08_PREVIEW_DIR.iterdir()},
                )
                for expected in CURRENT_V08_PREVIEW_DIR.iterdir():
                    self.assertEqual(
                        (rebuilt / expected.name).read_bytes(),
                        expected.read_bytes(),
                        expected.name,
                    )

    def test_current_v09_profile_and_frozen_v08_are_exact(self) -> None:
        self.assertEqual(CURRENT_V09_PREVIEW_ID, "2026-08-20-preview-v0.9")
        self.assertEqual(CURRENT_V09_PREVIEW_DIR.name, CURRENT_V09_PREVIEW_ID)
        self.assertEqual(
            verified_core.LEGACY_PREVIEW_V08_MANIFEST_SHA256,
            "a916aa4a438510ac5c1c26b359c7581dc18ca55de4c40ffd59c93424cad70b08",
        )
        self.assertEqual(
            verified_core.LEGACY_PREVIEW_V08_COMMIT,
            "26782bec3107fdbc778af2b57aa425f013a6a243",
        )
        self.assertEqual(
            verified_core.validate_frozen_v08()["counts"],
            {
                "physical_sites": 41,
                "projects": 44,
                "evidence": 100,
                "countries": 25,
                "non_us_sites": 35,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 39,
            },
        )
        self.assertEqual(
            validate_preview_dispatch(CURRENT_V08_PREVIEW_DIR)["preview_id"],
            CURRENT_V08_PREVIEW_ID,
        )
        self.assertEqual(
            (CURRENT_V09_PREVIEW_DIR / "manifest.sha256").read_text(),
            "d9d9975f8e70dbe8aab14c82f0af4aed1cd9d25d8eb3566ae458c60026c7b5c8"
            "  manifest.json\n",
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "current v0.9 definition pins are incomplete",
        ):
            load_current_v09_profile({})
        pins = {
            field: hashlib.sha256(path.read_bytes()).hexdigest()
            for field, path in verified_core.CURRENT_V09_DEFINITION_PATHS
        }
        profile = load_current_v09_profile(pins)
        self.assertEqual(profile.base_preview_dir, CURRENT_V08_PREVIEW_DIR)
        self.assertEqual(
            profile.base_manifest_sha256,
            verified_core.LEGACY_PREVIEW_V08_MANIFEST_SHA256,
        )
        self.assertEqual(profile.base_commit, verified_core.LEGACY_PREVIEW_V08_COMMIT)

    def test_v09_artifact_counts_evidence_and_guardrails_are_exact(self) -> None:
        manifest = validate_preview_dispatch(CURRENT_V09_PREVIEW_DIR)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 44,
                "projects": 47,
                "evidence": 108,
                "countries": 25,
                "non_us_sites": 37,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 42,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 66)
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V09_PREVIEW_DIR, "projects.csv")
        }
        delta_keys = set(verified_core.V09_BRIDGE_PROFILES)
        for key in delta_keys:
            row = projects[key]
            self.assertEqual(row["last_observed_physical_status"], "under_construction")
            self.assertEqual(row["independent_imagery_verification"], "false")
            self.assertEqual(
                row["imagery_review_outcome"], "not_reviewed_for_core_preview"
            )
            self.assertEqual(json.loads(row["workloads_json"]), [])

        marsden_key = "curated:cdc-marsden-park-campus:early-construction"
        marsden = projects[marsden_key]
        self.assertEqual(marsden["geometry_source_entity_kind"], "facility")
        self.assertEqual(marsden["geometry_use_scope"], "campus_locator")
        self.assertEqual(json.loads(marsden["power_observations_json"]), [])
        self.assertEqual(json.loads(marsden["efficiency_observations_json"]), [])
        self.assertEqual(marsden["operator"], "CDC Data Centres")
        self.assertEqual(
            json.loads(marsden["role_claims_json"]),
            [
                {
                    "evidence_id": "56fa3df3-1fe1-50af-80c1-0e2f0f14d610",
                    "party": "CDC Data Centres",
                    "relationship_scope": "intended",
                    "role": "operator",
                }
            ],
        )

        cermak_key = (
            "curated:digital-realty-330-east-cermak-chicago:"
            "current-facility-build"
        )
        cermak = projects[cermak_key]
        self.assertEqual(cermak["geometry_source_entity_kind"], "building")
        self.assertEqual(cermak["geometry_use_scope"], "project_locator")
        self.assertEqual(
            cermak["geometry_evidence_id"],
            "b2a12b58-767d-5517-9d63-a5d6fc6e9426",
        )
        self.assertIn("openstreetmap.org/way/210537873", cermak["geometry_source_url"])
        self.assertNotIn("cityofchicago", cermak["geometry_source_url"].lower())

        ntt_key = "curated:ntt-frankfurt-1-campus:7-3mw-expansion"
        ntt = projects[ntt_key]
        self.assertEqual(ntt["geometry_source_entity_kind"], "facility")
        self.assertEqual(ntt["geometry_use_scope"], "campus_locator")
        self.assertEqual(
            json.loads(ntt["power_observations_json"]),
            [
                {
                    "as_of_date": "2026-07-19",
                    "base": 7.3,
                    "confidence": 0.99,
                    "evidence_id": "603f155d-0c9d-5428-8e24-36a685af8aa7",
                    "high": 7.3,
                    "low": 7.3,
                    "method": "reported",
                    "metric": "critical_it_mw",
                    "notes": (
                        "Additional critical IT load for the distinct expansion that "
                        "the current page says is under construction; planned capacity "
                        "stage does not itself assert energization or operation."
                    ),
                    "stage": "planned",
                    "target_date": None,
                    "unit": "MW",
                }
            ],
        )
        self.assertEqual(json.loads(ntt["efficiency_observations_json"]), [])
        self.assertEqual(json.loads(ntt["role_claims_json"]), [])
        self.assertNotIn("70.1", ntt["power_observations_json"])
        self.assertNotIn("77.4", ntt["power_observations_json"])
        self.assertNotIn("120", ntt["power_observations_json"])

        base_evidence = {
            row["evidence_id"]
            for row in _rows_from(CURRENT_V08_PREVIEW_DIR, "evidence.csv")
        }
        current_evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V09_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(
            set(current_evidence) - base_evidence,
            verified_core.V09_EVIDENCE_IDS,
        )
        project_key_by_id = {
            row["project_id"]: row["project_stable_key"] for row in projects.values()
        }
        projection = {
            evidence_id: (
                json.loads(current_evidence[evidence_id]["roles_json"]),
                [
                    project_key_by_id[project_id]
                    for project_id in json.loads(
                        current_evidence[evidence_id]["project_ids_json"]
                    )
                ],
            )
            for evidence_id in verified_core.V09_EVIDENCE_IDS
        }
        self.assertEqual(
            projection,
            {
                "1df077b4-ffa3-5938-a5fe-88d5b4028ad4": (
                    ["context:geometry_identity"],
                    [ntt_key],
                ),
                "39cdd4b0-60f0-5d50-9a38-59d72c0a9d53": (
                    ["context:geometry_identity"],
                    [cermak_key],
                ),
                "56fa3df3-1fe1-50af-80c1-0e2f0f14d610": (
                    ["physical_status", "role:operator"],
                    [marsden_key],
                ),
                "603f155d-0c9d-5428-8e24-36a685af8aa7": (
                    ["physical_status", "typed_metric:critical_it_mw"],
                    [ntt_key],
                ),
                "9f47299f-1ce7-579f-b0b8-1bd454faabd5": (
                    ["physical_status"],
                    [cermak_key],
                ),
                "b2a12b58-767d-5517-9d63-a5d6fc6e9426": (
                    ["geometry"],
                    [cermak_key],
                ),
                "ce28239d-1c35-5043-9373-97416961a743": (
                    ["geometry"],
                    [marsden_key],
                ),
                "eb188ade-b0ff-5b98-bbd4-83cee821ca4b": (
                    ["geometry"],
                    [ntt_key],
                ),
            },
        )
        report = json.loads(
            (CURRENT_V09_PREVIEW_DIR / "selection-report.json").read_text()
        )
        self.assertEqual(
            report["selection_first_failure_counts"],
            verified_core.V09_SELECTION_FIRST_FAILURE_COUNTS,
        )
        self.assertEqual(
            report["final_release_gates"]["imagery_outcomes_complete"],
            {"actual": 10, "required": 47, "passed": False},
        )
        self.assertEqual(
            len(report["provenance_decisions"]["context_evidence_bindings"]),
            4,
        )

    def test_v09_city_notice_is_exact_visible_and_manifest_bound(self) -> None:
        contracts = verified_core._v09_contracts(hydrated_crosscheck=False)
        city_terms = contracts["city_terms"]
        legal_notice = verified_core._v09_city_legal_notice(city_terms)
        self.assertEqual(
            hashlib.sha256(city_terms["required_disclaimer"].encode()).hexdigest(),
            verified_core.V09_CITY_NOTICE_SHA256,
        )
        for name in ("README.md", "ATTRIBUTION.txt"):
            content = (CURRENT_V09_PREVIEW_DIR / name).read_text()
            self.assertIn(legal_notice, content)
            self.assertIn("Attribution: City of Chicago", content)
            self.assertIn(verified_core.V09_CITY_TERMS_URL, content)
            self.assertIn(city_terms["additional_terms_requirement"], content)
        with tempfile.TemporaryDirectory() as temporary:
            altered = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V09_PREVIEW_DIR, altered)
            readme = altered / "README.md"
            readme.write_text(
                readme.read_text().replace(
                    city_terms["required_disclaimer"], "[notice removed]"
                ),
                encoding="utf-8",
            )
            _refresh_unsigned_manifest(altered)
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.9 manifest semantics differ|v0.9 generated member differs",
            ):
                verified_core._validate_v09_preview_dispatch(altered)

    def test_v09_capture_source_and_release_refreshes_fail_closed(self) -> None:
        reviewed = json.loads(verified_core.V09_REVIEW_DEFINITION.read_text())
        acceptance_by_key = {
            row["project_stable_key"]: row for row in reviewed["acceptances"]
        }
        cermak_key = (
            "curated:digital-realty-330-east-cermak-chicago:"
            "current-facility-build"
        )
        cermak_acceptance = json.loads(
            json.dumps(acceptance_by_key[cermak_key])
        )
        cermak_bridge = json.loads(
            (verified_core.ROOT / cermak_acceptance["bridge_path"]).read_text()
        )
        cermak_acceptance["portable_capture_bindings"] = cermak_acceptance[
            "portable_capture_bindings"
        ][:-1]
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.9 capture inventory differs"
        ):
            verified_core._v09_load_capture_bindings(
                cermak_acceptance, cermak_bridge
            )

        cermak_acceptance = next(
            row
            for row in reviewed["acceptances"]
            if row["project_stable_key"] == cermak_key
        )
        city_binding = next(
            row
            for row in cermak_acceptance["portable_capture_bindings"]
            if row["capture_role"] == "identity_context"
        )
        city_capture = json.loads(
            (verified_core.ROOT / city_binding["path"]).read_text()
        )
        city_capture.pop("rights")
        city_payload = _canonical_json(city_capture)
        city_sha256 = hashlib.sha256(city_payload).hexdigest()
        refreshed_acceptance = json.loads(json.dumps(cermak_acceptance))
        refreshed_bridge = json.loads(json.dumps(cermak_bridge))
        refreshed_binding = next(
            row
            for row in refreshed_acceptance["portable_capture_bindings"]
            if row["capture_role"] == "identity_context"
        )
        refreshed_binding.update(
            {"bytes": len(city_payload), "sha256": city_sha256}
        )
        refreshed_bridge["identity_bridge_evidence"][0]["capture_reference"].update(
            {"bytes": len(city_payload), "sha256": city_sha256}
        )
        capture_id = city_binding["capture_id"]
        refreshed_profile = dict(verified_core.V09_CAPTURE_PROFILES[capture_id])
        refreshed_profile.update(
            {"bytes": len(city_payload), "sha256": city_sha256}
        )
        original_repository_input = verified_core._repository_input
        with tempfile.TemporaryDirectory() as temporary:
            altered_capture = Path(temporary) / "capture.json"
            altered_capture.write_bytes(city_payload)

            def repository_input(
                path_text: str, expected_sha256: str, field: str
            ) -> Path:
                if path_text == city_binding["path"]:
                    self.assertEqual(expected_sha256, city_sha256)
                    return altered_capture
                return original_repository_input(path_text, expected_sha256, field)

            with mock.patch.dict(
                verified_core.V09_CAPTURE_PROFILES,
                {capture_id: refreshed_profile},
            ), mock.patch.object(
                verified_core,
                "_repository_input",
                side_effect=repository_input,
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "v0.9 capture identity differs"
            ):
                verified_core._v09_load_capture_bindings(
                    refreshed_acceptance, refreshed_bridge
                )

        marsden_key = "curated:cdc-marsden-park-campus:early-construction"
        marsden_acceptance = json.loads(
            json.dumps(acceptance_by_key[marsden_key])
        )
        marsden_bridge = json.loads(
            (verified_core.ROOT / marsden_acceptance["bridge_path"]).read_text()
        )
        source_path = verified_core.ROOT / marsden_acceptance["source_input_path"]
        altered_source = json.loads(source_path.read_text())
        altered_source["guardrail_bypass"] = True
        source_payload = _canonical_json(altered_source)
        source_sha256 = hashlib.sha256(source_payload).hexdigest()
        source_binding = {
            "path": marsden_acceptance["source_input_path"],
            "bytes": len(source_payload),
            "sha256": source_sha256,
        }
        marsden_acceptance.update(
            {
                "source_input_bytes": len(source_payload),
                "source_input_sha256": source_sha256,
                "portable_input_binding": source_binding,
            }
        )
        marsden_bridge["construction_source"]["input"] = source_binding
        with tempfile.TemporaryDirectory() as temporary:
            altered_path = Path(temporary) / "source.json"
            altered_path.write_bytes(source_payload)

            def source_repository_input(
                path_text: str, expected_sha256: str, field: str
            ) -> Path:
                if path_text == source_binding["path"]:
                    self.assertEqual(expected_sha256, source_sha256)
                    return altered_path
                return original_repository_input(path_text, expected_sha256, field)

            with mock.patch.object(
                verified_core,
                "_repository_input",
                side_effect=source_repository_input,
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "v0.9 source record differs"
            ):
                verified_core._v09_validate_construction_source(
                    marsden_bridge,
                    marsden_acceptance,
                    hydrated_crosscheck=False,
                )

        canonical_marsden = json.loads(
            (verified_core.ROOT / acceptance_by_key[marsden_key]["bridge_path"])
            .read_text()
        )
        canonical_marsden["construction_source"]["release"]["release_id"] = (
            "attacker-release"
        )
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.9 source release differs"
        ):
            verified_core._v09_validate_construction_source(
                canonical_marsden,
                acceptance_by_key[marsden_key],
                hydrated_crosscheck=False,
            )

    def test_v09_ntt_segment_escape_is_rejected_after_fact_repin(self) -> None:
        project_key = "curated:ntt-frankfurt-1-campus:7-3mw-expansion"
        acceptance = next(
            row
            for row in json.loads(
                verified_core.V09_REVIEW_DEFINITION.read_text()
            )["acceptances"]
            if row["project_stable_key"] == project_key
        )
        bridge = json.loads(
            (verified_core.ROOT / acceptance["bridge_path"]).read_text()
        )
        container = {
            "type": "Polygon",
            "coordinates": [
                [
                    [0.0, 0.0],
                    [4.0, 0.0],
                    [4.0, 4.0],
                    [3.0, 4.0],
                    [3.0, 1.0],
                    [1.0, 1.0],
                    [1.0, 4.0],
                    [0.0, 4.0],
                    [0.0, 0.0],
                ]
            ],
        }
        evidence = bridge["identity_bridge_evidence"][0]
        fact = evidence["fact_payload"]
        bridge["geometry_entity"]["geometry"] = container
        fact["frozen_geometry_container"]["geometry_sha256"] = hashlib.sha256(
            verified_core._v09_json_without_lf(container)
        ).hexdigest()
        objects = fact["osm_address_objects"]
        objects[0]["geometry"] = {"type": "Point", "coordinates": [0.5, 0.5]}
        objects[1]["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [0.5, 3.0],
                    [3.5, 3.0],
                    [3.5, 2.5],
                    [0.5, 2.5],
                    [0.5, 3.0],
                ]
            ],
        }
        objects[2]["geometry"] = {"type": "Point", "coordinates": [3.5, 0.5]}
        fact_sha256 = hashlib.sha256(_canonical_json(fact)).hexdigest()
        evidence["fact_payload_canonical_sha256"] = fact_sha256
        evidence["content_hash"] = fact_sha256
        with mock.patch.object(
            verified_core, "V09_NTT_IDENTITY_FACT_SHA256", fact_sha256
        ), mock.patch.object(
            verified_core,
            "_official_evidence_id",
            return_value=evidence["evidence_id"],
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "v0.9 NTT address segment containment differs",
        ):
            verified_core._v09_validate_ntt_identity(bridge)

    def test_v09_overlay_schema_and_city_selection_fail_closed(self) -> None:
        overlay = json.loads(verified_core.V09_OVERLAY_DEFINITION.read_text())
        overlay["required_fields"].append("attacker_field")
        for row in overlay["overlays"]:
            row["attacker_field"] = "accepted-by-self-description"
        original_load = verified_core._load_json

        def load_with_refreshed_overlay(path: Path) -> object:
            if Path(path).resolve() == verified_core.V09_OVERLAY_DEFINITION.resolve():
                return overlay
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_with_refreshed_overlay
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.9 overlay contract differs"
        ):
            verified_core._v09_contracts(hydrated_crosscheck=False)

        city_profile = next(
            profile
            for capture_id, profile in verified_core.V09_CAPTURE_PROFILES.items()
            if "city-building-footprint" in capture_id
        )
        city_capture = json.loads(
            (verified_core.ROOT / city_profile["path"]).read_text()
        )
        self.assertNotIn("fact_payload_canonical_bytes", city_capture["selection"])
        self.assertNotIn("fact_payload_canonical_sha256", city_capture["selection"])
        cermak_key = (
            "curated:digital-realty-330-east-cermak-chicago:"
            "current-facility-build"
        )
        cermak_bridge = verified_core._v09_contracts(
            hydrated_crosscheck=False
        )["bridges"][cermak_key]
        rejected = cermak_bridge["lineage_context"][
            "hard_rejected_global_v3_source_objects"
        ]["objects"]
        self.assertEqual(
            {row["stable_key"] for row in rejected},
            {"osm:way/156520409", "osm:node/10910879064"},
        )
        self.assertTrue(
            all(
                row["contributes_to_identity"] is False
                and row["contributes_to_geometry"] is False
                for row in rejected
            )
        )

    def test_v09_corpus_free_and_hydrated_rebuilds_are_byte_exact(self) -> None:
        for hydrated in (False, True):
            if hydrated and not _hydrated_vcc_source_inputs_are_present():
                continue
            with self.subTest(hydrated=hydrated), tempfile.TemporaryDirectory() as temporary:
                rebuilt = Path(temporary) / "preview"
                with mock.patch.object(
                    verified_core,
                    "_v09_hydrated_crosscheck_available",
                    return_value=hydrated,
                ):
                    verified_core._build_v09_preview(rebuilt)
                self.assertEqual(
                    {path.name for path in rebuilt.iterdir()},
                    {path.name for path in CURRENT_V09_PREVIEW_DIR.iterdir()},
                )
                for expected in CURRENT_V09_PREVIEW_DIR.iterdir():
                    self.assertEqual(
                        (rebuilt / expected.name).read_bytes(),
                        expected.read_bytes(),
                        expected.name,
                    )

    def test_v10_profile_counts_evidence_and_attribution(self) -> None:
        self.assertEqual(CURRENT_V10_PREVIEW_ID, "2026-08-20-preview-v0.10")
        self.assertEqual(CURRENT_V10_PREVIEW_DIR.name, CURRENT_V10_PREVIEW_ID)
        pins = {
            field: hashlib.sha256(path.read_bytes()).hexdigest()
            for field, path in verified_core.CURRENT_V10_DEFINITION_PATHS
        }
        profile = load_current_v10_profile(pins)
        self.assertEqual(profile.base_preview_id, CURRENT_V09_PREVIEW_ID)
        self.assertEqual(
            validate_frozen_v09(CURRENT_V09_PREVIEW_DIR)["preview_id"],
            CURRENT_V09_PREVIEW_ID,
        )
        manifest = validate_preview_dispatch(CURRENT_V10_PREVIEW_DIR)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 47,
                "projects": 50,
                "evidence": 116,
                "countries": 25,
                "non_us_sites": 39,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 45,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 72)
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V10_PREVIEW_DIR, "projects.csv")
        }
        delta_keys = set(verified_core.V10_BRIDGE_PROFILES)
        self.assertEqual(delta_keys, set(projects) - {
            row["project_stable_key"]
            for row in _rows_from(CURRENT_V09_PREVIEW_DIR, "projects.csv")
        })
        colt = projects[
            "curated:colt-london-hayes-campus:london4-current-facility-build"
        ]
        self.assertEqual(
            json.loads(colt["power_observations_json"])[0]["base"], 31.0
        )
        for key in delta_keys:
            self.assertEqual(projects[key]["workloads_json"], "[]")
            self.assertEqual(projects[key]["role_claims_json"], "[]")
            self.assertEqual(projects[key]["operating_model"], "unknown")
        expected_roles = {
            "0cad69d1-3151-5073-af8e-73f8401bf2cb": ["geometry"],
            "465b57e0-58b6-56aa-8b00-728b9cc9c201": ["physical_status"],
            "6bf6472d-a1f7-53fd-b0d5-2317d80df706": ["physical_status"],
            "6e4b0bfe-23de-5439-9dc0-3688a382a285": [
                "typed_metric:critical_it_mw"
            ],
            "850336d5-4d8f-5821-ae65-cb195961e7b6": [
                "context:geometry_identity",
                "geometry",
            ],
            "b0d7fbf5-7de2-58e0-a54f-d6fec6d08a6a": [
                "context:geometry_identity"
            ],
            "c0b3ca09-1341-5395-9301-9f6a2d67cf0c": [
                "context:geometry_identity",
                "geometry",
            ],
            "e0cbb7f3-f4ab-52c7-a4ed-10424c78e411": ["physical_status"],
        }
        evidence = {
            row["evidence_id"]: json.loads(row["roles_json"])
            for row in _rows_from(CURRENT_V10_PREVIEW_DIR, "evidence.csv")
            if row["evidence_id"] in expected_roles
        }
        self.assertEqual(evidence, expected_roles)
        notice = verified_core._v10_city_legal_notice_from_base()
        for name in ("README.md", "ATTRIBUTION.txt"):
            self.assertIn(
                notice,
                (CURRENT_V10_PREVIEW_DIR / name).read_text(encoding="utf-8"),
            )
        attribution = (CURRENT_V10_PREVIEW_DIR / "ATTRIBUTION.txt").read_text()
        self.assertIn("© OpenStreetMap contributors", attribution)
        self.assertIn("Regierungspräsidium Darmstadt", attribution)

    def test_v10_inherits_v09_rows_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row
                for row in _rows_from(CURRENT_V09_PREVIEW_DIR, filename)
            }
            current = {
                row[key]: row
                for row in _rows_from(CURRENT_V10_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited}, inherited
            )

    def test_v10_flat_rows_status_scope_and_topology_fail_closed(self) -> None:
        contracts = verified_core._v10_contracts(hydrated_crosscheck=False)
        for project_key in sorted(verified_core.V10_BRIDGE_PROFILES):
            with self.subTest(project_key=project_key):
                acceptance = contracts["acceptance_by_key"][project_key]
                bridge = json.loads(
                    (verified_core.ROOT / acceptance["bridge_path"]).read_text()
                )
                construction = bridge["construction_source"]
                profile = dict(verified_core.V10_BRIDGE_PROFILES[project_key])
                construction["project"]["status_age_days_at_review"] = 0
                profile["construction_sha256"] = hashlib.sha256(
                    _canonical_json(construction)
                ).hexdigest()
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "full v97 entity projection differs",
                ):
                    verified_core._v10_validate_construction_source(
                        bridge,
                        acceptance,
                        profile,
                        hydrated_crosscheck=False,
                    )

        project_key = (
            "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build"
        )
        acceptance = contracts["acceptance_by_key"][project_key]
        bridge = json.loads(
            (verified_core.ROOT / acceptance["bridge_path"]).read_text()
        )
        construction = bridge["construction_source"]
        capacity = construction["capacity_estimate"]
        capacity["entity_kind"] = "attacker_scope"
        binding = construction["release_rows"]["capacity_estimate"]
        _replace_embedded_csv_row(binding, verified_core.V10_CAPACITY_FIELDS, capacity)
        profile = dict(verified_core.V10_BRIDGE_PROFILES[project_key])
        profile["release_rows_sha256"] = hashlib.sha256(
            _canonical_json(construction["release_rows"])
        ).hexdigest()
        profile["construction_sha256"] = hashlib.sha256(
            _canonical_json(construction)
        ).hexdigest()
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "capacity observation projection differs",
        ):
            verified_core._v10_validate_construction_source(
                bridge,
                acceptance,
                profile,
                hydrated_crosscheck=False,
            )

        bridge = json.loads(
            (verified_core.ROOT / acceptance["bridge_path"]).read_text()
        )
        construction = bridge["construction_source"]
        construction["project_to_campus"]["relationship_type"] = "attacker"
        profile = dict(verified_core.V10_BRIDGE_PROFILES[project_key])
        profile["topology_sha256"] = hashlib.sha256(
            _canonical_json(construction["project_to_campus"])
        ).hexdigest()
        profile["construction_sha256"] = hashlib.sha256(
            _canonical_json(construction)
        ).hexdigest()
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "topology relationship projection differs",
        ):
            verified_core._v10_validate_construction_source(
                bridge,
                acceptance,
                profile,
                hydrated_crosscheck=False,
            )

    def test_v10_geometry_contract_resists_coherent_profile_refresh(self) -> None:
        contracts = verified_core._v10_contracts(hydrated_crosscheck=False)

        def assert_rejected(
            project_key: str,
            mutate: object,
            error: str = "v0.10 immutable bridge profile differs",
        ) -> None:
            acceptance = json.loads(
                json.dumps(contracts["acceptance_by_key"][project_key])
            )
            overlay = json.loads(
                json.dumps(contracts["overlay_by_key"][project_key])
            )
            bridge = json.loads(
                (verified_core.ROOT / acceptance["bridge_path"]).read_text()
            )
            profile = dict(verified_core.V10_BRIDGE_PROFILES[project_key])
            profile["semantic_hashes"] = dict(profile["semantic_hashes"])
            mutate(acceptance, overlay, bridge, profile)
            for field in profile["semantic_hashes"]:
                profile["semantic_hashes"][field] = hashlib.sha256(
                    _canonical_json(bridge[field])
                ).hexdigest()
            with tempfile.TemporaryDirectory() as temporary:
                bridge_path = Path(temporary) / "bridge.json"
                bridge_payload = _canonical_json(bridge)
                bridge_path.write_bytes(bridge_payload)
                bridge_sha256 = hashlib.sha256(bridge_payload).hexdigest()
                for row in (acceptance, overlay):
                    row["bridge_bytes"] = len(bridge_payload)
                    row["bridge_sha256"] = bridge_sha256
                profile["bridge_bytes"] = len(bridge_payload)
                profile["bridge_sha256"] = bridge_sha256
                profile["acceptance_sha256"] = hashlib.sha256(
                    _canonical_json(acceptance)
                ).hexdigest()
                profile["overlay_sha256"] = hashlib.sha256(
                    _canonical_json(overlay)
                ).hexdigest()
                original_repository_input = verified_core._repository_input

                def repository_input(
                    path_text: str, expected_sha256: str, label: str
                ) -> Path:
                    if label == "v0.10 bridge":
                        return bridge_path
                    return original_repository_input(
                        path_text, expected_sha256, label
                    )

                with mock.patch.dict(
                    verified_core.V10_BRIDGE_PROFILES,
                    {project_key: profile},
                ), mock.patch.object(
                    verified_core,
                    "_repository_input",
                    side_effect=repository_input,
                ), self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    error,
                ):
                    verified_core._validate_v10_bridge(
                        acceptance,
                        overlay,
                        hydrated_crosscheck=False,
                    )

        oracle_key = (
            "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build"
        )

        def swap_oracle_target(
            acceptance: dict[str, object],
            overlay: dict[str, object],
            bridge: dict[str, object],
            profile: dict[str, object],
        ) -> None:
            project = bridge["construction_source"]["project"]
            for row in (acceptance, overlay):
                row["geometry_target_entity_kind"] = "project"
                row["geometry_target_entity_stable_key"] = project["stable_key"]
                row["geometry_target_entity_id"] = project["entity_id"]
                row["geometry_use_scope"] = "project_locator"
            decision = bridge["review_decision"]
            decision["geometry_target_entity_kind"] = "project"
            decision["geometry_target_entity_stable_key"] = project["stable_key"]
            decision["geometry_target_entity_id"] = project["entity_id"]
            decision["geometry_use_scope"] = "project_locator"
            profile["target_kind"] = "project"
            profile["target_stable_key"] = project["stable_key"]
            profile["target_entity_id"] = project["entity_id"]

        assert_rejected(oracle_key, swap_oracle_target)

        def rewrite_oracle_publication_bindings(
            acceptance: dict[str, object],
            overlay: dict[str, object],
            bridge: dict[str, object],
            profile: dict[str, object],
        ) -> None:
            fake_id = "00000000-0000-5000-8000-000000000001"
            for row in (acceptance, overlay):
                row["physical_site_entity_id"] = fake_id
                row["geometry_evidence_id"] = fake_id
                row["project_to_campus_relationship_id"] = "relationship:attacker"
            profile["geometry_evidence_id"] = fake_id

        assert_rejected(oracle_key, rewrite_oracle_publication_bindings)

        def relocate_oracle_geometry(
            acceptance: dict[str, object],
            overlay: dict[str, object],
            bridge: dict[str, object],
            profile: dict[str, object],
        ) -> None:
            binding = bridge["geometry_capture"]["entity_source_row"]
            raw_row = base64.b64decode(binding["raw_csv_record_base64"])
            row = next(
                csv.DictReader(
                    io.StringIO(raw_row.decode("utf-8")),
                    fieldnames=verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS,
                )
            )
            geometry = json.loads(row["geometry_json"])
            geometry["coordinates"] = [
                [
                    [longitude + 1.0, latitude + 1.0]
                    for longitude, latitude in ring
                ]
                for ring in geometry["coordinates"]
            ]
            longitude = float(row["longitude"]) + 1.0
            latitude = float(row["latitude"]) + 1.0
            row["geometry_json"] = json.dumps(
                geometry,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            row["longitude"] = str(longitude)
            row["latitude"] = str(latitude)
            _replace_embedded_csv_row(
                binding,
                verified_core.GLOBAL_GEOMETRY_ENTITY_FIELDS,
                row,
            )
            bridge["geometry_entity"]["geometry"] = geometry
            bridge["geometry_entity"]["longitude"] = longitude
            bridge["geometry_entity"]["latitude"] = latitude
            profile["longitude"] = longitude
            profile["latitude"] = latitude

        assert_rejected(
            oracle_key,
            relocate_oracle_geometry,
            "v0.10 independent geometry source contract differs",
        )

        colt_key = (
            "curated:colt-london-hayes-campus:london4-current-facility-build"
        )

        def relocate_colt_source(
            acceptance: dict[str, object],
            overlay: dict[str, object],
            bridge: dict[str, object],
            profile: dict[str, object],
        ) -> None:
            fake_id = "00000000-0000-5000-8000-000000000000"
            for row in (acceptance, overlay):
                row["geometry_entity_id"] = fake_id
            bridge["geometry_entity"]["entity_id"] = fake_id
            profile["geometry_entity_id"] = fake_id

        assert_rejected(colt_key, relocate_colt_source)

        def restore_misleading_live_method(
            acceptance: dict[str, object],
            overlay: dict[str, object],
            bridge: dict[str, object],
            profile: dict[str, object],
        ) -> None:
            method = (
                "live_openstreetmap_exact_colt_london4_named_building_polygon_"
                "as_project_locator"
            )
            for row in (acceptance, overlay):
                row["geometry_method"] = method
            bridge["review_decision"]["geometry_method"] = method

        assert_rejected(colt_key, restore_misleading_live_method)

    def test_v10_capture_rights_and_scope_semantics_fail_closed(self) -> None:
        contracts = verified_core._v10_contracts(hydrated_crosscheck=False)
        cyrus_key = (
            "curated:cyrusone-fra7-frankfurt-westside-campus:"
            "current-multi-building-development"
        )
        cyrus_acceptance = contracts["acceptance_by_key"][cyrus_key]
        cyrus_path = verified_core.ROOT / cyrus_acceptance["bridge_path"]
        cyrus = json.loads(cyrus_path.read_text())
        hvbg = cyrus["identity_bridge_evidence"][1]
        hvbg["fact_payload"]["official_hessian_horizontal_crs"] = (
            "EPSG:9999 attacker CRS"
        )
        hvbg_payload = _canonical_json(hvbg["fact_payload"])
        hvbg["fact_payload_canonical"] = {
            "bytes": len(hvbg_payload),
            "sha256": hashlib.sha256(hvbg_payload).hexdigest(),
        }
        hvbg["rights_scope"] = "attacker redistribution grant"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "v0.10 Cyrus transform replay differs",
        ):
            verified_core._v10_validate_cyrus_geometry(cyrus)

        cyrus = json.loads(cyrus_path.read_text())
        cyrus["rights"]["mixed_rights"] = "all source bodies relicensed"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "v0.10 Cyrus rights semantics differ",
        ):
            verified_core._v10_validate_rights_semantics(cyrus, cyrus_key)

        colt_key = (
            "curated:colt-london-hayes-campus:london4-current-facility-build"
        )
        colt_acceptance = contracts["acceptance_by_key"][colt_key]
        colt_path = verified_core.ROOT / colt_acceptance["bridge_path"]
        colt_profile = verified_core.V10_BRIDGE_PROFILES[colt_key]
        for label, mutation in (
            (
                "bool-as-int",
                lambda bridge: bridge["geometry_capture"]["request"].update(
                    {"credentials_supplied": 0}
                ),
            ),
            (
                "drift-authority",
                lambda bridge: bridge["geometry_capture"].update(
                    {
                        "capture_stability": {
                            "body_refetch_reproducibility": "guaranteed",
                            "reason": "trust future live authority",
                            "portable_authority": "discard embedded bytes",
                        }
                    }
                ),
            ),
        ):
            with self.subTest(label=label):
                colt = json.loads(colt_path.read_text())
                mutation(colt)
                with self.assertRaises(VerifiedConstructionCoreError):
                    verified_core._v10_validate_colt_geometry(colt, colt_profile)

        for field, value in (
            ("object_id", 1495920405),
            ("ordered_node_ids", [1, 2, 3, 1]),
            ("tags", {"name": "attacker relocation"}),
        ):
            with self.subTest(fact_field=field):
                colt = json.loads(colt_path.read_text())
                identity = colt["identity_bridge_evidence"][0]
                identity["fact_payload"][field] = value
                fact_payload = _canonical_json(identity["fact_payload"])
                identity["fact_payload_canonical"] = {
                    "bytes": len(fact_payload),
                    "sha256": hashlib.sha256(fact_payload).hexdigest(),
                }
                with self.assertRaises(VerifiedConstructionCoreError):
                    verified_core._v10_validate_colt_geometry(colt, colt_profile)

        colt = json.loads(colt_path.read_text())
        colt["rights"]["geometry_source"] = "attacker relicensing"
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "v0.10 OSM rights semantics differ",
        ):
            verified_core._v10_validate_rights_semantics(colt, colt_key)

        oracle_key = (
            "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build"
        )
        oracle_acceptance = contracts["acceptance_by_key"][oracle_key]
        oracle_path = verified_core.ROOT / oracle_acceptance["bridge_path"]
        for field in ("capacity_estimates_json", "workloads_json"):
            with self.subTest(project_leakage=field):
                oracle = json.loads(oracle_path.read_text())
                construction = oracle["construction_source"]
                construction["project"][field] = construction["campus"][field]
                profile = dict(verified_core.V10_BRIDGE_PROFILES[oracle_key])
                profile["construction_sha256"] = hashlib.sha256(
                    _canonical_json(construction)
                ).hexdigest()
                with self.assertRaisesRegex(
                    VerifiedConstructionCoreError,
                    "v0.10 full v97 entity projection differs",
                ):
                    verified_core._v10_validate_construction_source(
                        oracle,
                        oracle_acceptance,
                        profile,
                        hydrated_crosscheck=False,
                    )

    def test_v10_definition_bool_manifest_and_hydration_attacks_fail(self) -> None:
        overlay = json.loads(verified_core.V10_OVERLAY_DEFINITION.read_text())
        overlay["required_fields"].append(overlay["required_fields"][0])
        original_load = verified_core._load_json

        def load_overlay(path: Path) -> object:
            if Path(path).resolve() == verified_core.V10_OVERLAY_DEFINITION.resolve():
                return overlay
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_overlay
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.10 overlay contract differs"
        ):
            verified_core._v10_contracts(hydrated_crosscheck=False)

        reviewed = json.loads(verified_core.V10_REVIEW_DEFINITION.read_text())
        reviewed["attacker_schema_extension"] = True

        def load_reviewed(path: Path) -> object:
            if Path(path).resolve() == verified_core.V10_REVIEW_DEFINITION.resolve():
                return reviewed
            return original_load(path)

        with mock.patch.object(
            verified_core, "_load_json", side_effect=load_reviewed
        ), self.assertRaisesRegex(
            VerifiedConstructionCoreError, "v0.10 reviewed-site contract differs"
        ):
            verified_core._v10_contracts(hydrated_crosscheck=False)

        with tempfile.TemporaryDirectory() as temporary:
            altered = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V10_PREVIEW_DIR, altered)
            manifest_path = altered / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["publishable_as_final"] = 0
            payload = _canonical_json(manifest)
            manifest_path.write_bytes(payload)
            (altered / "manifest.sha256").write_text(
                f"{hashlib.sha256(payload).hexdigest()}  manifest.json\n"
            )
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError, "v0.10 manifest files differ"
            ):
                validate_preview_dispatch(altered)

        original_is_file = Path.is_file
        present = verified_core.ROOT / (
            "releases/2026-07-22-open-seed-v97/construction_pipeline.csv"
        )
        missing = verified_core.ROOT / (
            "releases/2026-07-22-open-seed-v97/capacity_estimates.csv"
        )

        def partial_is_file(path: Path) -> bool:
            if path == present:
                return True
            if path == missing:
                return False
            return original_is_file(path)

        with mock.patch.object(Path, "is_file", partial_is_file), self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "hydrated cross-check inputs are only partially present",
        ):
            verified_core._v10_hydrated_crosscheck_available()

    def test_v10_corpus_free_and_hydrated_rebuilds_are_byte_exact(self) -> None:
        for hydrated in (False, True):
            if hydrated and not verified_core._v10_hydrated_crosscheck_available():
                continue
            with self.subTest(hydrated=hydrated), tempfile.TemporaryDirectory() as temporary:
                rebuilt = Path(temporary) / "preview"
                with mock.patch.object(
                    verified_core,
                    "_v10_hydrated_crosscheck_available",
                    return_value=hydrated,
                ):
                    verified_core.build_preview(rebuilt)
                self.assertEqual(
                    {path.name for path in rebuilt.iterdir()},
                    {path.name for path in CURRENT_V10_PREVIEW_DIR.iterdir()},
                )
                for expected in CURRENT_V10_PREVIEW_DIR.iterdir():
                    self.assertEqual(
                        (rebuilt / expected.name).read_bytes(),
                        expected.read_bytes(),
                        expected.name,
                    )


if __name__ == "__main__":
    unittest.main()
