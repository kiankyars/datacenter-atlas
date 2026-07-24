from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from datacenter_atlas.satellite_reselected_change_batch import (
    RESELECTED_CHANGE_BATCH_PIPELINE,
    ChangeBatchConfig,
    execute_satellite_reselected_change_batch,
    validate_reselected_change_inputs,
    validate_satellite_reselected_change_batch,
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
RUN_AT = "2026-07-19T09:00:00Z"


class _FailingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        return subprocess.CompletedProcess(
            command, 1, "", "intentional fixture failure"
        )


class SatelliteReselectedChangeBatchTests(unittest.TestCase):
    def test_inputs_bind_all_reselected_jobs_without_analysis(self) -> None:
        validated = validate_reselected_change_inputs(QUEUE, SOURCE, RELEASE)
        self.assertFalse(validated["change_analysis_executed"])
        self.assertEqual(validated["summary"]["jobs_validated"], 15)
        self.assertEqual(
            validated["summary"]["jobs_unresolved_multitile_needed"], 2
        )
        self.assertEqual(
            validated["selection"]["selected_queue_ids"],
            validated["selection"]["include_queue_ids"],
        )
        self.assertEqual(len(validated["selection"]["selected_queue_ids"]), 15)
        processor = validated["processor"]
        self.assertEqual(
            processor["algorithm_version"], "sentinel-2-l2a-change-v2"
        )
        self.assertTrue(
            processor["reselection_adapter"][
                "numerical_processor_reused_unchanged"
            ]
        )
        self.assertIn(
            "datacenter_atlas/satellite_reselected_change_batch.py",
            processor["files"],
        )
        self.assertIn(
            "datacenter_atlas/satellite_catalog_reselection.py",
            processor["files"],
        )

    def test_bounded_failure_checkpoint_round_trips_without_pixel_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _FailingRunner()
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            document = execute_satellite_reselected_change_batch(
                QUEUE,
                SOURCE,
                RELEASE,
                output,
                config=config,
                max_jobs=1,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(document["pipeline"], RESELECTED_CHANGE_BATCH_PIPELINE)
            self.assertEqual(document["summary"]["jobs_selected"], 15)
            self.assertEqual(document["summary"]["jobs_completed"], 0)
            self.assertEqual(document["summary"]["jobs_failed"], 1)
            self.assertEqual(document["summary"]["jobs_pending"], 14)
            self.assertEqual(len(runner.calls), 1)
            self.assertTrue(document["runs"][-1]["budget_exhausted"])
            first = document["jobs"][
                document["selection"]["selected_queue_ids"][0]
            ]
            self.assertEqual(first["state"], "failed")
            self.assertEqual(
                first["failures"][-1]["kind"], "command_exit"
            )
            self.assertTrue(
                first["catalog_reselection"][
                    "raw_provider_response_bytes_copied_exactly"
                ]
            )
            self.assertTrue(
                first["catalog_reselection"][
                    "all_required_asset_header_windows_within_grid"
                ]
            )
            self.assertEqual(
                validate_satellite_reselected_change_batch(
                    QUEUE, SOURCE, RELEASE, output, config=config
                ),
                document,
            )


if __name__ == "__main__":
    unittest.main()
