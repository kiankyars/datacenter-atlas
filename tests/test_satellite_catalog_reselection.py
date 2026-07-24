from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.satellite_catalog_reselection import (
    HEADER_EVIDENCE_FILENAME,
    RESELECTION_SCOPE,
    SOURCE_MANIFEST_FILENAME,
    SUPPORTED_QUEUE_IDS,
    UNRESOLVED_FILENAME,
    UNRESOLVED_QUEUE_IDS,
    SatelliteCatalogReselectionError,
    release_catalog_tasks,
    validate_catalog_reselection,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
QUEUE = PACKAGE_ROOT / "satellite_review_queues/2026-07-18-global-open-v3"
SOURCE = (
    PACKAGE_ROOT
    / "satellite_review_runs/2026-07-18-global-open-v3-active-001"
)
RELEASE = (
    PACKAGE_ROOT
    / "satellite_catalog_reselection_runs"
    / "2026-07-19-global-open-v3-active-edge-reselection-001"
)

EXPECTED_SELECTIONS = {
    26: ("S2A_31TFJ_20240612_0_L2A", "S2C_31TFJ_20260612_0_L2A"),
    27: ("S2A_31TFJ_20240612_0_L2A", "S2C_31TFJ_20260612_0_L2A"),
    33: ("S2B_18STJ_20240703_0_L2A", "S2B_18STJ_20260703_0_L2A"),
    34: ("S2B_18STJ_20240703_0_L2A", "S2B_18STJ_20260703_0_L2A"),
    35: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    36: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    53: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    54: ("S2A_32TNR_20240619_0_L2A", "S2C_32TNR_20260619_0_L2A"),
    55: ("S2A_32TNR_20240619_0_L2A", "S2C_32TNR_20260619_0_L2A"),
    59: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    60: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    61: ("S2B_14SPB_20240704_0_L2A", "S2B_14SPB_20260704_0_L2A"),
    62: ("S2B_14SPB_20240704_0_L2A", "S2B_14SPB_20260704_0_L2A"),
    73: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
    74: ("S2B_30UYC_20240626_0_L2A", "S2C_30UYC_20260624_0_L2A"),
}


class SatelliteCatalogReselectionTests(unittest.TestCase):
    def test_release_reproduces_exact_copies_and_full_supported_coverage(self) -> None:
        manifest = validate_catalog_reselection(QUEUE, SOURCE, RELEASE)
        self.assertEqual(manifest["scope"], RESELECTION_SCOPE)
        self.assertEqual(
            manifest["summary"],
            {
                "atlas_rows_emitted": 0,
                "change_jobs_executed": 0,
                "jobs_reselected": 15,
                "jobs_unresolved_multitile_needed": 2,
                "raw_provider_response_files_copied": 30,
                "source_catalog_manifest_files_copied": 15,
                "unique_aois_reselected": 9,
            },
        )
        self.assertEqual(set(manifest["jobs"]), set(SUPPORTED_QUEUE_IDS))
        tasks = release_catalog_tasks(manifest)
        self.assertEqual(list(tasks), list(SUPPORTED_QUEUE_IDS))

        for queue_id in SUPPORTED_QUEUE_IDS:
            top = manifest["jobs"][queue_id]
            expected = EXPECTED_SELECTIONS[top["queue_position"]]
            self.assertEqual(
                top["selected_ids"],
                {"baseline": expected[0], "current": expected[1]},
            )
            release_job = RELEASE / top["output_directory"]
            source_job = SOURCE / top["output_directory"]
            self.assertEqual(
                (release_job / "baseline-response.json").read_bytes(),
                (source_job / "baseline-response.json").read_bytes(),
            )
            self.assertEqual(
                (release_job / "current-response.json").read_bytes(),
                (source_job / "current-response.json").read_bytes(),
            )
            self.assertEqual(
                (release_job / SOURCE_MANIFEST_FILENAME).read_bytes(),
                (source_job / "manifest.json").read_bytes(),
            )
            derived = json.loads((release_job / "manifest.json").read_text())
            self.assertNotEqual(
                derived["selected_ids"], derived["original_selected_ids"]
            )
            for epoch in ("baseline", "current"):
                feature = derived["selected_features"][epoch]
                self.assertIn(feature["id"], derived["eligible_ids"][epoch])
                for coverage_name in (
                    "stac_grid_coverage",
                    "observed_header_coverage",
                ):
                    coverage = feature[coverage_name]
                    self.assertTrue(
                        coverage["all_required_asset_windows_within_grid"]
                    )
                    self.assertEqual(len(coverage["assets"]), 6)
                    self.assertTrue(
                        all(asset["within_grid"] for asset in coverage["assets"])
                    )

        headers = json.loads((RELEASE / HEADER_EVIDENCE_FILENAME).read_text())
        self.assertEqual(headers["asset_open_operations"], 60)
        self.assertEqual(headers["scope"]["pixel_reads"], 0)
        self.assertIsNone(headers["scope"]["http_request_count"])
        self.assertTrue(
            headers["scope"][
                "asset_open_operations_are_not_http_request_counts"
            ]
        )

    def test_france_is_bound_and_unresolved_not_unavailable(self) -> None:
        unresolved = json.loads((RELEASE / UNRESOLVED_FILENAME).read_text())
        self.assertIn("not a no-scene claim", unresolved["meaning"])
        self.assertEqual(
            [job["queue_id"] for job in unresolved["jobs"]],
            list(UNRESOLVED_QUEUE_IDS),
        )
        for job in unresolved["jobs"]:
            self.assertEqual(job["full_cover_eligible_ids"]["baseline"], [])
            self.assertGreaterEqual(
                len(job["full_cover_eligible_ids"]["current"]), 1
            )
            self.assertFalse(job["unavailable_no_scene_claim"])
            self.assertEqual(
                job["outcome"],
                "unresolved_multitile_or_supplemental_scene_required",
            )
            self.assertEqual(
                set(job["original_selected"]), {"baseline", "current"}
            )
            self.assertEqual(
                set(job["source_queries"]),
                {"provider", "baseline", "current", "selection"},
            )
            for epoch, artifact_name in (
                ("baseline", "baseline_response"),
                ("current", "current_response"),
            ):
                artifact = job["source_artifacts"][artifact_name]
                source_path = SOURCE / artifact["file"]
                self.assertEqual(len(source_path.read_bytes()), artifact["bytes"])
                self.assertEqual(
                    job["source_queries"][epoch]["raw_response_sha256"],
                    artifact["sha256"],
                )
            source_manifest = job["source_artifacts"]["source_manifest"]
            self.assertEqual(
                len((SOURCE / source_manifest["file"]).read_bytes()),
                source_manifest["bytes"],
            )

    def test_validator_rejects_changed_bytes_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(RELEASE, copied)
            manifest = json.loads((copied / "batch-manifest.json").read_text())
            first = manifest["jobs"][SUPPORTED_QUEUE_IDS[0]]
            response = copied / first["output_directory"] / "baseline-response.json"
            response.chmod(0o644)
            response.write_bytes(response.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                SatelliteCatalogReselectionError, "exact source bytes changed"
            ):
                validate_catalog_reselection(QUEUE, SOURCE, copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(RELEASE, copied)
            copied.chmod(0o755)
            (copied / "unexpected.txt").write_text("not allowed", encoding="utf-8")
            with self.assertRaisesRegex(
                SatelliteCatalogReselectionError, "unexpected file"
            ):
                validate_catalog_reselection(QUEUE, SOURCE, copied)


if __name__ == "__main__":
    unittest.main()
