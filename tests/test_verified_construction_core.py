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
    OVERLAY_DEFINITION,
    PREVIEW_DIR,
    REVIEW_DEFINITION,
    SOURCE_RELEASE,
    VerifiedConstructionCoreError,
    build_preview,
    validate_preview,
)


def _rows(name: str) -> list[dict[str, str]]:
    with (PREVIEW_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
                "physical_sites": 8,
                "projects": 9,
                "evidence": 23,
                "countries": 6,
                "non_us_sites": 6,
                "official_boundary_projects": 2,
                "reviewed_site_locator_projects": 7,
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
        self.assertEqual(report["selected_project_count"], 9)
        self.assertEqual(report["non_selected_source_row_count"], 522)
        self.assertEqual(
            sum(report["selection_first_failure_counts"].values()), 531
        )
        self.assertEqual(report["selection_first_failure_counts"]["selected"], 9)
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
            "datacenter-atlas-verified-construction-core-schema-v1",
        )
        self.assertEqual(
            set(schema["tables"]), {"projects.csv", "sites.csv", "evidence.csv"}
        )
        self.assertEqual(schema["geojson"]["geometry_equals"], ["sites.csv", "geometry_json"])
        self.assertEqual(schema["map"]["derived_from"], "sites.geojson")
        self.assertEqual(len(schema["json_embedded_evidence_fields"]), 4)
        self.assertEqual(
            schema["embedded_array_items"][
                "projects.csv:efficiency_observations_json"
            ]["allowed_metrics"],
            ["pue"],
        )
        self.assertIn("method", schema["embedded_types"]["typed_metric_observation"]["required_fields"])

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
                VerifiedConstructionCoreError, "observation schema differs"
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
            with mock.patch.object(
                verified_core, "OVERLAY_DEFINITION", bad_definition
            ), self.assertRaisesRegex(
                VerifiedConstructionCoreError, "geometry identity differs"
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
