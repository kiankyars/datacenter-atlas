from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest

import datacenter_atlas.satellite_change_batch as generic_carrier
from datacenter_atlas.datacenter_atlas.satellite_change_batch_explicit_v1 import (
    _atomic_promote_noreplace,
    _derived_carrier,
)
from datacenter_atlas.satellite_change_batch_explicit_v1 import (
    CATALOG_MANIFEST_SHA256,
    ExplicitChangeBatchConfig,
    ExplicitSatelliteChangeBatchV1Error,
    PIPELINE,
    REPRESENTED_ACTIVE_JOB_COUNT,
    SELECTED_QUEUE_IDS,
    SELECTION_RECEIPT_SHA256,
    UNSELECTED_PENDING_JOB_COUNT,
    execute_explicit_satellite_change_batch_v1,
    validate_explicit_change_inputs,
)


RUN_AT = "2026-07-21T14:30:00Z"


class _FailingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 19, "", "fixture failure")


class ExplicitSatelliteChangeBatchV1Tests(unittest.TestCase):
    def test_exact_frozen_inputs_validate_offline(self) -> None:
        document = validate_explicit_change_inputs()
        self.assertEqual(len(document["jobs"]), REPRESENTED_ACTIVE_JOB_COUNT)
        self.assertEqual(document["summary"]["selected_jobs_completed"], 11)
        self.assertEqual(document["summary"]["jobs_pending"], 87)
        self.assertEqual(
            document["selection_receipt"]["sha256"], SELECTION_RECEIPT_SHA256
        )

    def test_derived_carrier_is_isolated_and_exactly_replaces_job_promotion(self) -> None:
        derived = _derived_carrier()
        self.assertIsNot(derived, generic_carrier)
        self.assertEqual(derived.CHANGE_BATCH_PIPELINE, PIPELINE)
        self.assertIn(
            "_adapter_promote_noreplace",
            derived._execute_satellite_change_batch_locked.__code__.co_names,
        )
        self.assertIs(generic_carrier.os.replace, __import__("os").replace)
        self.assertEqual(derived.CHANGE_SCOPE["unexpected_output_adoption"], False)
        self.assertEqual(derived.CHANGE_SCOPE["max_job_attempts"], 1)

    def test_atomic_promotion_refuses_late_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "final"
            stage.mkdir()
            destination.mkdir()
            (stage / "stage.txt").write_text("stage", encoding="utf-8")
            (destination / "final.txt").write_text("final", encoding="utf-8")
            with self.assertRaisesRegex(
                ExplicitSatelliteChangeBatchV1Error, "refusing overwrite"
            ):
                _atomic_promote_noreplace(stage, destination)
            self.assertEqual((stage / "stage.txt").read_text(), "stage")
            self.assertEqual((destination / "final.txt").read_text(), "final")

    def test_execution_exposes_only_receipt_jobs_and_attempts_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _FailingRunner()
            document = execute_explicit_satellite_change_batch_v1(
                output,
                config=ExplicitChangeBatchConfig(minimum_interval_seconds=0),
                max_jobs=1,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(tuple(document["jobs"]), SELECTED_QUEUE_IDS)
            first = document["jobs"][SELECTED_QUEUE_IDS[0]]
            self.assertEqual(first["state"], "failed")
            self.assertEqual(first["attempts"], 1)
            self.assertTrue(
                all(
                    document["jobs"][queue_id]["state"] == "pending"
                    for queue_id in SELECTED_QUEUE_IDS[1:]
                )
            )
            self.assertEqual(document["configuration"]["max_job_attempts"], 1)
            self.assertEqual(document["catalog_batches"][0]["jobs_represented"], 98)
            self.assertEqual(
                document["catalog_batches"][0]["unselected_pending_jobs"],
                UNSELECTED_PENDING_JOB_COUNT,
            )
            self.assertEqual(
                document["catalog_batches"][0]["manifest_sha256"],
                CATALOG_MANIFEST_SHA256,
            )

    def test_nonempty_new_output_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            output.mkdir()
            (output / "unexpected.txt").write_text("do not adopt", encoding="utf-8")
            runner = _FailingRunner()
            with self.assertRaisesRegex(
                ExplicitSatelliteChangeBatchV1Error,
                "contains files without a checkpoint",
            ):
                execute_explicit_satellite_change_batch_v1(
                    output,
                    config=ExplicitChangeBatchConfig(minimum_interval_seconds=0),
                    max_jobs=1,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])
            self.assertEqual((output / "unexpected.txt").read_text(), "do not adopt")


if __name__ == "__main__":
    unittest.main()
