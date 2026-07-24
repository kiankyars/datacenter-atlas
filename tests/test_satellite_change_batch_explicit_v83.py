from __future__ import annotations

import importlib
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.satellite_change_batch as generic_carrier
from datacenter_atlas.datacenter_atlas.satellite_change_batch_explicit_v83 import (
    _atomic_promote_noreplace,
    _derived_carrier,
)
from datacenter_atlas.satellite_change_batch_explicit_v83 import (
    CATALOG_UNAVAILABLE_JOB_COUNT,
    DEFAULT_OUTPUT_PATH,
    EXCLUDED_QUEUE_IDS,
    ExplicitChangeBatchV83Config,
    ExplicitSatelliteChangeBatchV83Error,
    PINNED_RUNTIME,
    PIPELINE,
    REPRESENTED_ACTIVE_JOB_COUNT,
    SELECTED_QUEUE_IDS,
    execute_explicit_satellite_change_batch_v83,
    validate_explicit_change_inputs_v83,
    validate_explicit_satellite_change_batch_v83,
)
from datacenter_atlas.satellite_change_batch_explicit_v83_audit import (
    ExplicitSatelliteChangeBatchV83AuditError,
    STAGE_MANIFEST_SHA256,
    STAGE_PHYSICAL_TREE_SHA256,
    physical_tree_sha256,
    validate_explicit_satellite_change_batch_v83_audit,
)


RUN_AT = "2026-07-21T19:00:00Z"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
INCIDENT = (
    PROJECT_ROOT
    / "satellite_change_run_incidents/"
    "2026-07-21-open-seed-v83-post-run-order-assertion-v1"
)
INCIDENT_SHA256 = "2a1df815a1c3c7ea1d7a2762ed1ec34266e06312219a8e40a8d7239506c7a5a7"
INCIDENT_PHYSICAL_TREE_SHA256 = (
    "b5605169b5668a339989fa518cae18f61e54e79a70be58470c521da921217ee4"
)


class _FailingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 19, "", "fixture failure")


def _make_writable(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


class ExplicitSatelliteChangeBatchV83Tests(unittest.TestCase):
    def test_exact_inputs_selection_exclusion_and_runtime_validate_offline(self) -> None:
        document = validate_explicit_change_inputs_v83()
        self.assertEqual(len(document["jobs"]), REPRESENTED_ACTIVE_JOB_COUNT)
        self.assertEqual(document["summary"]["selected_jobs_completed"], 3)
        self.assertEqual(
            document["summary"]["selected_jobs_unavailable_no_scene"],
            CATALOG_UNAVAILABLE_JOB_COUNT,
        )
        unavailable = document["jobs"][EXCLUDED_QUEUE_IDS[0]]
        self.assertEqual(unavailable["state"], "unavailable_no_scene")
        self.assertEqual(unavailable["attempts"], 1)
        self.assertEqual(PINNED_RUNTIME["python_version"], "3.12.13")

    def test_derived_carrier_is_isolated_and_no_replace(self) -> None:
        derived = _derived_carrier()
        self.assertIsNot(derived, generic_carrier)
        self.assertEqual(derived.CHANGE_BATCH_PIPELINE, PIPELINE)
        self.assertIn(
            "_adapter_promote_noreplace",
            derived._execute_satellite_change_batch_locked.__code__.co_names,
        )
        self.assertFalse(derived.CHANGE_SCOPE["unexpected_output_adoption"])
        self.assertEqual(derived.CHANGE_SCOPE["max_job_attempts"], 1)

    def test_execution_exposes_three_jobs_once_and_accounts_for_jashore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _FailingRunner()
            document = execute_explicit_satellite_change_batch_v83(
                output,
                config=ExplicitChangeBatchV83Config(minimum_interval_seconds=0),
                max_jobs=1,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(tuple(document["jobs"]), SELECTED_QUEUE_IDS)
            self.assertEqual(document["jobs"][SELECTED_QUEUE_IDS[0]]["state"], "failed")
            self.assertEqual(document["jobs"][SELECTED_QUEUE_IDS[0]]["attempts"], 1)
            self.assertEqual(
                document["selection"]["exclude_queue_ids"], list(EXCLUDED_QUEUE_IDS)
            )
            self.assertEqual(
                document["selection"]["counts"][
                    "exclusion_ids_without_completed_catalog"
                ],
                1,
            )
            self.assertFalse(
                document["scope"]["imagery_identity_inference"]
            )
            self.assertFalse(document["scope"]["imagery_power_inference"])

    def test_nonempty_output_and_late_collision_are_never_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "change-run"
            output.mkdir()
            sentinel = output / "unexpected.txt"
            sentinel.write_text("do not adopt", encoding="utf-8")
            runner = _FailingRunner()
            with self.assertRaisesRegex(
                ExplicitSatelliteChangeBatchV83Error,
                "contains files without a checkpoint",
            ):
                execute_explicit_satellite_change_batch_v83(
                    output,
                    config=ExplicitChangeBatchV83Config(
                        minimum_interval_seconds=0
                    ),
                    max_jobs=1,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not adopt")

            stage = root / "stage"
            destination = root / "final"
            stage.mkdir()
            destination.mkdir()
            (stage / "stage.txt").write_text("stage", encoding="utf-8")
            (destination / "final.txt").write_text("final", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "refusing overwrite"):
                _atomic_promote_noreplace(stage, destination)
            self.assertEqual((stage / "stage.txt").read_text(), "stage")
            self.assertEqual((destination / "final.txt").read_text(), "final")

    def test_workspace_shim_and_cli_are_importable_from_parent(self) -> None:
        implementation = importlib.import_module(
            "datacenter_atlas.datacenter_atlas.satellite_change_batch_explicit_v83"
        )
        shim = importlib.import_module(
            "datacenter_atlas.satellite_change_batch_explicit_v83"
        )
        self.assertIs(
            shim.execute_explicit_satellite_change_batch_v83,
            implementation.execute_explicit_satellite_change_batch_v83,
        )
        cli = subprocess.run(
            [
                sys.executable,
                str(
                    PROJECT_ROOT
                    / "scripts/run_satellite_change_batch_explicit_v83.py"
                ),
                "--help",
            ],
            cwd=WORKSPACE_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("v83 three-job change tranche", cli.stdout)

    def test_frozen_final_replays_offline_and_tamper_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ExplicitSatelliteChangeBatchV83Error,
            "runnable inventory changed",
        ):
            validate_explicit_satellite_change_batch_v83(DEFAULT_OUTPUT_PATH)
        document = validate_explicit_satellite_change_batch_v83_audit(
            DEFAULT_OUTPUT_PATH
        )
        self.assertEqual(document["summary"]["jobs_selected"], 3)
        self.assertEqual(
            tuple(document["selection"]["selected_queue_ids"]),
            SELECTED_QUEUE_IDS,
        )
        self.assertEqual(
            hashlib.sha256(
                (DEFAULT_OUTPUT_PATH / "batch-manifest.json").read_bytes()
            ).hexdigest(),
            STAGE_MANIFEST_SHA256,
        )
        self.assertEqual(
            physical_tree_sha256(DEFAULT_OUTPUT_PATH),
            STAGE_PHYSICAL_TREE_SHA256,
        )
        network_failure = AssertionError("offline replay attempted network access")
        with patch.object(socket, "socket", side_effect=network_failure), patch.object(
            socket, "create_connection", side_effect=network_failure
        ), patch.object(socket, "getaddrinfo", side_effect=network_failure):
            self.assertEqual(
                validate_explicit_satellite_change_batch_v83_audit(
                    DEFAULT_OUTPUT_PATH
                ),
                document,
            )

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied-final"
            shutil.copytree(DEFAULT_OUTPUT_PATH, copied)
            report = next(copied.glob("jobs/*/change/report.json"))
            report.chmod(0o644)
            report.write_bytes(report.read_bytes() + b"\n")
            report.chmod(0o444)
            with self.assertRaises(ExplicitSatelliteChangeBatchV83AuditError):
                validate_explicit_satellite_change_batch_v83_audit(copied)
            _make_writable(copied)

    def test_post_run_order_assertion_is_frozen_as_technical_incident(self) -> None:
        path = INCIDENT / "incident.json"
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), INCIDENT_SHA256)
        self.assertEqual(
            physical_tree_sha256(INCIDENT), INCIDENT_PHYSICAL_TREE_SHA256
        )
        document = json.loads(raw)
        self.assertTrue(
            document["assertion_failure"]["technical_not_model_outcome"]
        )
        self.assertFalse(document["impact"]["job_retried"])
        self.assertFalse(document["impact"]["frozen_stage_bytes_modified"])
        self.assertEqual(
            document["lineage"]["final_mode_sensitive_tree_sha256"],
            STAGE_PHYSICAL_TREE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
