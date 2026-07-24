from __future__ import annotations

import importlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_batch_explicit_v83 import (
    ExplicitV83BatchConfig,
    ExplicitSatelliteBatchV83Error,
    SELECTED_QUEUE_IDS,
    SELECTION_RECEIPT_FILENAME,
    SELECTION_RECEIPT_HASH_FILENAME,
    execute_explicit_satellite_batch_v83,
    validate_explicit_satellite_batch_v83,
)
from datacenter_atlas.satellite_catalog import (
    CatalogQuery,
    Provider,
    build_pair_manifest,
    manifest_json,
)
from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
)
from datacenter_atlas.satellite_queue_v83 import (
    ADDED_QUEUE_EXPECTATIONS,
    QUEUE,
)


RUN_AT = "2026-07-21T13:00:00Z"
CATALOG_AT = "2026-07-21T12:30:00Z"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent


def _pairs(arguments: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag.startswith("--") and "=" in flag:
            name, value = flag.split("=", 1)
            parsed[name] = value
            index += 1
        else:
            parsed[flag] = arguments[index + 1]
            index += 2
    return parsed


def _item(item_id: str, timestamp: str, bbox: tuple[float, ...]) -> dict:
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "bbox": list(bbox),
        "properties": {
            "datetime": timestamp,
            "eo:cloud_cover": 1,
            "grid:code": "MGRS-18SUJ",
        },
        "assets": {
            band: {"href": f"https://example.test/{item_id}/{band}.tif"}
            for band in ("B02", "B03", "B04", "B08", "B11", "SCL")
        },
    }


class _CatalogRunner:
    def __init__(self, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if self.returncode:
            return subprocess.CompletedProcess(command, self.returncode, "", "failure")
        arguments = _pairs(command[2:])
        output = Path(arguments["--output-dir"])
        output.mkdir(parents=True)
        bbox = tuple(float(value) for value in arguments["--bbox"].split(","))
        queue_id = output.parents[1].name
        baseline_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _item(
                        f"baseline-{queue_id}",
                        f"{arguments['--baseline-target']}T12:00:00Z",
                        bbox,
                    )
                ],
            }
        ).encode()
        current_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _item(
                        f"current-{queue_id}",
                        f"{arguments['--current-target']}T12:00:00Z",
                        bbox,
                    )
                ],
            }
        ).encode()
        baseline_query = CatalogQuery(
            bbox,
            arguments["--baseline-start"],
            arguments["--baseline-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        current_query = CatalogQuery(
            bbox,
            arguments["--current-start"],
            arguments["--current-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        manifest = build_pair_manifest(
            Provider(arguments["--provider"]),
            baseline_query,
            baseline_raw,
            current_query,
            current_raw,
            baseline_date=arguments["--baseline-target"],
            current_date=arguments["--current-target"],
            retrieved_at=CATALOG_AT,
            temporal_window_days=int(arguments["--temporal-window-days"]),
        )
        (output / "baseline-response.json").write_bytes(baseline_raw)
        (output / "current-response.json").write_bytes(current_raw)
        (output / "manifest.json").write_text(
            manifest_json(manifest), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "ok", "")


def _called_queue_ids(runner: _CatalogRunner) -> list[str]:
    return [
        Path(_pairs(command[2:])["--output-dir"]).parents[1].name
        for command in runner.calls
    ]


class ExplicitSatelliteBatchV83Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.queue = cls.root / "queue"
        cls.queue.mkdir()
        for filename in (
            QUEUE_FILENAME,
            MANIFEST_FILENAME,
            MANIFEST_HASH_FILENAME,
        ):
            (cls.queue / filename).write_bytes((QUEUE / filename).read_bytes())
        for path in cls.queue.iterdir():
            path.chmod(0o444)
        cls.queue.chmod(0o555)
        cls.config = ExplicitV83BatchConfig(minimum_interval_seconds=0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.queue.chmod(0o755)
        for path in cls.queue.iterdir():
            path.chmod(0o644)
        cls.temporary.cleanup()

    def test_workspace_shim_and_cli_are_importable_from_parent_workspace(self) -> None:
        implementation = importlib.import_module(
            "datacenter_atlas.datacenter_atlas.satellite_batch_explicit_v83"
        )
        shim = importlib.import_module("datacenter_atlas.satellite_batch_explicit_v83")
        self.assertIs(
            shim.validate_explicit_satellite_batch_v83,
            implementation.validate_explicit_satellite_batch_v83,
        )
        self.assertIs(
            shim.execute_explicit_satellite_batch_v83,
            implementation.execute_explicit_satellite_batch_v83,
        )
        self.assertEqual(shim.SELECTED_QUEUE_IDS, implementation.SELECTED_QUEUE_IDS)

        imported = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from datacenter_atlas.satellite_batch_explicit_v83 "
                    "import SELECTED_QUEUE_IDS; "
                    "assert len(SELECTED_QUEUE_IDS) == 4"
                ),
            ],
            cwd=WORKSPACE_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(imported.returncode, 0, imported.stderr)

        cli = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/run_satellite_explicit_v83.py"),
                "--help",
            ],
            cwd=WORKSPACE_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("four-project open-seed v83", cli.stdout)

    def test_receipt_represents_104_but_runs_only_ordered_four_once(self) -> None:
        output = self.root / "success"
        runner = _CatalogRunner()
        manifest = execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            command_runner=runner,
            sleep=lambda _: None,
            timestamp=lambda: RUN_AT,
        )
        self.assertEqual(_called_queue_ids(runner), list(SELECTED_QUEUE_IDS))
        self.assertTrue(
            all("--retries" in command and command[command.index("--retries") + 1] == "0" for command in runner.calls)
        )
        self.assertEqual(
            manifest["summary"],
            {
                "jobs_completed": 4,
                "jobs_failed": 0,
                "jobs_not_selected": 100,
                "jobs_pending": 100,
                "jobs_represented": 104,
                "jobs_selected_for_execution": 4,
                "jobs_unavailable_no_scene": 0,
                "selected_jobs_completed": 4,
                "selected_jobs_failed": 0,
                "selected_jobs_pending": 0,
                "selected_jobs_unavailable_no_scene": 0,
            },
        )
        self.assertEqual(
            manifest["lifetime_budget"],
            {
                "http_attempt_cap": 8,
                "http_attempts_remaining": 0,
                "http_attempts_reserved": 8,
            },
        )
        receipt_path = output / SELECTION_RECEIPT_FILENAME
        receipt = json.loads(receipt_path.read_bytes())
        self.assertEqual(
            receipt["selection"]["selected_queue_ids"], list(SELECTED_QUEUE_IDS)
        )
        self.assertEqual(receipt["representation"]["represented_jobs"], 104)
        self.assertEqual(receipt["representation"]["distinct_aois"], 100)
        self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o444)
        self.assertEqual(
            stat.S_IMODE((output / SELECTION_RECEIPT_HASH_FILENAME).stat().st_mode),
            0o444,
        )
        self.assertEqual(
            {
                path.suffix
                for path in output.rglob("*")
                if path.is_file()
            },
            {".json", ".sha256"},
        )
        network_failure = AssertionError("offline replay attempted network access")
        with patch.object(socket, "socket", side_effect=network_failure), patch.object(
            socket, "create_connection", side_effect=network_failure
        ), patch.object(socket, "getaddrinfo", side_effect=network_failure):
            self.assertEqual(
                validate_explicit_satellite_batch_v83(
                    self.queue, output, config=self.config
                ),
                manifest,
            )

        resume_runner = _CatalogRunner()
        resumed = execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            command_runner=resume_runner,
            sleep=lambda _: None,
            timestamp=lambda: "2026-07-21T13:01:00Z",
        )
        self.assertEqual(resume_runner.calls, [])
        self.assertEqual(resumed["lifetime_budget"]["http_attempts_reserved"], 8)

    def test_partial_runs_reserve_two_each_under_lifetime_eight(self) -> None:
        output = self.root / "partial"
        first_runner = _CatalogRunner()
        first = execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            max_jobs=2,
            max_http_attempts=4,
            command_runner=first_runner,
            sleep=lambda _: None,
            timestamp=lambda: RUN_AT,
        )
        self.assertEqual(_called_queue_ids(first_runner), list(SELECTED_QUEUE_IDS[:2]))
        self.assertEqual(first["summary"]["jobs_pending"], 102)
        self.assertEqual(first["lifetime_budget"]["http_attempts_reserved"], 4)

        second_runner = _CatalogRunner()
        second = execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            max_jobs=2,
            max_http_attempts=4,
            command_runner=second_runner,
            sleep=lambda _: None,
            timestamp=lambda: "2026-07-21T13:01:00Z",
        )
        self.assertEqual(_called_queue_ids(second_runner), list(SELECTED_QUEUE_IDS[2:]))
        self.assertEqual(second["summary"]["jobs_pending"], 100)
        self.assertEqual(second["lifetime_budget"]["http_attempts_reserved"], 8)

    def test_selection_is_exactly_four_projects_not_duplicate_campuses(self) -> None:
        rows = [
            json.loads(line)
            for line in (self.queue / QUEUE_FILENAME).read_bytes().splitlines()
        ]
        by_id = {row["queue_id"]: row for row in rows}
        selected = [by_id[queue_id] for queue_id in SELECTED_QUEUE_IDS]
        self.assertEqual(
            [row["queue_position"] for row in selected],
            [14, 25, 50, 102],
        )
        self.assertTrue(
            all(
                row["entity"]["kind"] == "project"
                and row["priority"]["tier"] == "active_construction"
                and row["priority"]["lifecycle_status"] == "under_construction"
                for row in selected
            )
        )
        duplicate_campuses = {
            queue_id
            for queue_id, expected in ADDED_QUEUE_EXPECTATIONS.items()
            if expected["kind"] == "campus"
        }
        self.assertTrue(duplicate_campuses.isdisjoint(SELECTED_QUEUE_IDS))
        self.assertEqual(
            {
                tuple(by_id[queue_id]["location"]["aoi_bbox_wgs84"])
                for queue_id in duplicate_campuses
            },
            {
                tuple(row["location"]["aoi_bbox_wgs84"])
                for row in selected
            },
        )

        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "four-job"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                self.root / "too-many-jobs",
                config=self.config,
                max_jobs=5,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "lifetime cap 8"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                self.root / "too-many-http",
                config=self.config,
                max_http_attempts=9,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )

    def test_receipt_tamper_and_unexpected_output_stop_before_commands(self) -> None:
        output = self.root / "tamper"
        execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            max_jobs=1,
            max_http_attempts=2,
            command_runner=_CatalogRunner(returncode=1),
            sleep=lambda _: None,
            timestamp=lambda: RUN_AT,
        )
        receipt = output / SELECTION_RECEIPT_FILENAME
        receipt.chmod(0o644)
        receipt.write_bytes(receipt.read_bytes() + b"\n")
        receipt.chmod(0o444)
        runner = _CatalogRunner()
        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "receipt changed"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                output,
                config=self.config,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        self.assertEqual(runner.calls, [])

        output = self.root / "adoption"
        first = execute_explicit_satellite_batch_v83(
            self.queue,
            output,
            config=self.config,
            max_jobs=1,
            max_http_attempts=2,
            command_runner=_CatalogRunner(returncode=1),
            sleep=lambda _: None,
            timestamp=lambda: RUN_AT,
        )
        unselected = next(
            task
            for task in first["jobs"].values()
            if not task["selected_for_execution"]
        )
        unexpected = output / unselected["output_directory"]
        unexpected.mkdir(parents=True)
        runner = _CatalogRunner()
        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "adoption prohibited"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                output,
                config=self.config,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        self.assertEqual(runner.calls, [])

    def test_late_job_collision_is_never_replaced_or_adopted(self) -> None:
        output = self.root / "late-collision"
        base_runner = _CatalogRunner()

        def collide(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            completed = base_runner(command, **kwargs)
            stage = Path(_pairs(command[2:])["--output-dir"])
            final = stage.parents[1] / "catalog"
            final.mkdir()
            (final / "sentinel.txt").write_text("do not replace", encoding="utf-8")
            return completed

        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "late catalog final collision"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                output,
                config=self.config,
                command_runner=collide,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        self.assertEqual(len(base_runner.calls), 1)
        sentinel = output / "jobs" / SELECTED_QUEUE_IDS[0] / "catalog" / "sentinel.txt"
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")
        runner = _CatalogRunner()
        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "adoption prohibited"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                output,
                config=self.config,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        self.assertEqual(runner.calls, [])

    def test_output_symlink_is_rejected(self) -> None:
        target = self.root / "symlink-target"
        target.mkdir()
        link = self.root / "symlink-output"
        link.symlink_to(target, target_is_directory=True)
        runner = _CatalogRunner()
        with self.assertRaisesRegex(ExplicitSatelliteBatchV83Error, "symlink"):
            execute_explicit_satellite_batch_v83(
                self.queue,
                link,
                config=self.config,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
        self.assertEqual(runner.calls, [])
        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
