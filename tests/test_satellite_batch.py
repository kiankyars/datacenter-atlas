from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.satellite_batch import (
    BATCH_MANIFEST_FILENAME,
    BATCH_SCHEMA_VERSION,
    DEFAULT_MAX_RESPONSE_BYTES,
    PRIOR_BATCH_SCHEMA_VERSION,
    BatchConfig,
    SatelliteBatchError,
    execute_satellite_queue,
    validate_satellite_batch,
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
    QueueConfig,
    build_queue_bundle,
)


RUN_AT = "2026-07-18T23:00:00Z"
CATALOG_AT = "2026-07-18T22:30:00Z"
NO_SCENE_ERROR = (
    "Traceback (most recent call last):\n"
    "datacenter_atlas.satellite_catalog.CatalogValidationError: "
    "no scene falls within the baseline temporal window\n"
)


def _feature(entity_id: str, status: str) -> dict:
    return {
        "type": "Feature",
        "id": entity_id,
        "geometry": None,
        "properties": {
            "entity_id": entity_id,
            "entity_kind": "facility",
            "stable_key": f"fixture:{entity_id}",
            "name": f"Site {entity_id}",
            "latitude": 38.9,
            "longitude": -77.0,
            "status": status,
            "status_as_of": "2026-07-01",
            "snapshot_evidence_id": f"snapshot-{entity_id}",
            "status_evidence_id": f"status-{entity_id}",
            "source_family": "fixture",
            "source_url": f"https://example.test/{entity_id}",
            "source_license": "CC0-1.0",
            "country": "United States",
            "country_iso_a2": "US",
            "country_iso_a3": "USA",
        },
    }


def _queue_bundle(path: Path, *features: dict) -> None:
    atlas = (
        json.dumps(
            {
                "type": "FeatureCollection",
                "atlas_as_of": "2026-07-18",
                "atlas_recorded_at": "2026-07-18T20:00:00Z",
                "attribution": ["Fixture attribution"],
                "features": list(features),
            }
        )
        + "\n"
    ).encode()
    bundle = build_queue_bundle(
        atlas,
        source_name="atlas.geojson",
        generated_at="2026-07-18T21:00:00Z",
        config=QueueConfig(
            baseline_target="2024-06-15",
            current_target="2026-06-15",
            query_window_days=30,
            aoi_half_side_km=2,
        ),
    )
    path.mkdir()
    (path / QUEUE_FILENAME).write_bytes(bundle.queue_bytes)
    (path / MANIFEST_FILENAME).write_bytes(bundle.manifest_bytes)
    (path / MANIFEST_HASH_FILENAME).write_bytes(bundle.manifest_hash_bytes)


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


def _pairs(arguments: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag.startswith("--") and "=" in flag:
            name, value = flag.split("=", 1)
            parsed[name] = value
            index += 1
            continue
        parsed[flag] = arguments[index + 1]
        index += 2
    return parsed


class _CatalogRunner:
    def __init__(
        self,
        *,
        returncode: int = 0,
        returncodes: tuple[int, ...] | None = None,
        stderr: str = "fixture failure",
    ) -> None:
        self.returncode = returncode
        self.returncodes = list(returncodes or ())
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        returncode = self.returncodes.pop(0) if self.returncodes else self.returncode
        if returncode:
            return subprocess.CompletedProcess(command, returncode, "", self.stderr)
        arguments = _pairs(command[2:])
        output = Path(arguments["--output-dir"])
        output.mkdir(parents=True)
        bbox = tuple(float(value) for value in arguments["--bbox"].split(","))
        baseline_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _item(
                        f"baseline-{output.parent.name}",
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
                        f"current-{output.parent.name}",
                        f"{arguments['--current-target']}T12:00:00Z",
                        bbox,
                    )
                ],
            }
        ).encode()
        provider = Provider(arguments["--provider"])
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
            provider,
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


class SatelliteBatchTests(unittest.TestCase):
    def test_no_scene_is_terminal_and_resume_does_not_retry_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(
                queue,
                _feature("first", "under_construction"),
                _feature("second", "under_construction"),
            )
            config = BatchConfig(minimum_interval_seconds=0.1)
            runner = _CatalogRunner(
                returncodes=(1, 0),
                stderr=NO_SCENE_ERROR,
            )
            manifest = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=2,
                max_http_attempts=4,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )

            self.assertEqual(manifest["state"], "completed")
            self.assertEqual(manifest["summary"]["jobs_completed"], 1)
            self.assertEqual(manifest["summary"]["jobs_failed"], 0)
            self.assertEqual(manifest["summary"]["jobs_pending"], 0)
            self.assertEqual(
                manifest["summary"]["jobs_unavailable_no_scene"], 1
            )
            self.assertEqual(
                manifest["last_run"]["jobs_unavailable_no_scene"], 1
            )
            unavailable = next(
                task
                for task in manifest["jobs"].values()
                if task["state"] == "unavailable_no_scene"
            )
            outcome = unavailable["unavailability"]
            self.assertEqual(outcome["window"], "baseline")
            self.assertEqual(
                outcome["raw_reason"],
                "no scene falls within the baseline temporal window",
            )
            self.assertEqual(outcome["query_window"]["target_date"], "2024-06-15")
            self.assertEqual(outcome["query_window"]["temporal_window_days"], 30)
            self.assertIn(
                "CatalogValidationError", unavailable["failures"][-1]["error"]
            )

            resume_runner = _CatalogRunner()
            resumed = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=2,
                max_http_attempts=4,
                command_runner=resume_runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(resume_runner.calls, [])

    def test_schema_one_no_scene_failure_migrates_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(
                queue,
                _feature("first", "under_construction"),
                _feature("second", "under_construction"),
            )
            config = BatchConfig(minimum_interval_seconds=0.1)
            first_run = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=1,
                max_http_attempts=2,
                command_runner=_CatalogRunner(returncode=1, stderr=NO_SCENE_ERROR),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            legacy = json.loads(json.dumps(first_run))
            legacy["schema_version"] = 1
            legacy["configuration"].pop("max_response_bytes")
            legacy.pop("response_limit_migration")
            legacy["summary"].pop("jobs_unavailable_no_scene")
            legacy["summary"]["jobs_failed"] = 1
            legacy["last_run"].pop("jobs_unavailable_no_scene")
            legacy["last_run"]["jobs_failed"] = 1
            for task in legacy["jobs"].values():
                task.pop("unavailability")
                if task["state"] == "unavailable_no_scene":
                    task["state"] = "failed"
            (output / BATCH_MANIFEST_FILENAME).write_text(
                json.dumps(legacy, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            runner = _CatalogRunner()
            resumed = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=1,
                max_http_attempts=2,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(resumed["schema_version"], BATCH_SCHEMA_VERSION)
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(resumed["summary"]["jobs_completed"], 1)
            self.assertEqual(resumed["summary"]["jobs_unavailable_no_scene"], 1)
            self.assertEqual(resumed["summary"]["jobs_failed"], 0)
            migrated = next(
                task
                for task in resumed["jobs"].values()
                if task["state"] == "unavailable_no_scene"
            )
            self.assertEqual(migrated["attempts"], 1)
            migration = resumed["response_limit_migration"]
            self.assertEqual(migration["source_schema_version"], 1)
            self.assertFalse(migration["historical_acquisition_bounded"])

    def test_other_catalog_validation_error_remains_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(queue, _feature("active", "under_construction"))
            config = BatchConfig(minimum_interval_seconds=0.1)
            first = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=1,
                max_http_attempts=2,
                command_runner=_CatalogRunner(
                    returncode=1,
                    stderr=(
                        "datacenter_atlas.satellite_catalog.CatalogValidationError: "
                        "no chronological scene pair exists in temporal windows\n"
                    ),
                ),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            failed = next(iter(first["jobs"].values()))
            self.assertEqual(failed["state"], "failed")
            self.assertIsNone(failed["unavailability"])
            self.assertEqual(first["summary"]["jobs_unavailable_no_scene"], 0)

            resumed = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=1,
                max_http_attempts=2,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            completed = next(iter(resumed["jobs"].values()))
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(completed["attempts"], 2)

    def test_priority_selection_runs_catalog_only_and_resume_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(
                queue,
                _feature("active", "under_construction"),
                _feature("unknown", "unknown"),
                _feature("operating", "operational"),
            )
            runner = _CatalogRunner()
            config = BatchConfig(
                priority_tiers=("active_construction",),
                user_agent="Atlas fixture/1.0 (test@example.test)",
                minimum_interval_seconds=0.25,
                max_response_bytes=123_456,
            )
            manifest = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=5,
                max_http_attempts=10,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(manifest["state"], "completed")
            self.assertEqual(manifest["summary"]["jobs_selected"], 1)
            self.assertEqual(manifest["last_run"]["http_attempts_reserved"], 2)
            self.assertFalse(manifest["scope"]["change_analysis_executed"])
            self.assertFalse(manifest["scope"]["imagery_identity_inference"])
            self.assertFalse(manifest["scope"]["imagery_lifecycle_inference"])
            self.assertFalse(manifest["scope"]["imagery_power_inference"])
            self.assertEqual(len(runner.calls), 1)
            command = runner.calls[0]
            self.assertIn("catalog_satellite.py", command[1])
            self.assertNotIn("sentinel_change.py", " ".join(command))
            self.assertTrue(
                any(argument.startswith("--bbox=-") for argument in command[2:])
            )
            command_arguments = _pairs(command[2:])
            self.assertEqual(command_arguments["--user-agent"], config.user_agent)
            self.assertEqual(command_arguments["--minimum-interval-seconds"], "0.25")
            self.assertEqual(command_arguments["--max-response-bytes"], "123456")
            self.assertEqual(
                manifest["configuration"]["max_response_bytes"], 123_456
            )
            self.assertIsNone(manifest["response_limit_migration"])

            resume_runner = _CatalogRunner()
            resumed = execute_satellite_queue(
                queue,
                output,
                config=config,
                max_jobs=5,
                max_http_attempts=10,
                command_runner=resume_runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(resume_runner.calls, [])
            self.assertEqual(
                json.loads((output / BATCH_MANIFEST_FILENAME).read_text()), resumed
            )
            self.assertEqual(
                validate_satellite_batch(queue, output, config=config), resumed
            )

    def test_completed_output_tampering_stops_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(queue, _feature("active", "under_construction"))
            config = BatchConfig(minimum_interval_seconds=0.1)
            execute_satellite_queue(
                queue,
                output,
                config=config,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            baseline = next(output.glob("jobs/*/catalog/baseline-response.json"))
            baseline.write_bytes(baseline.read_bytes() + b"\n")
            runner = _CatalogRunner()
            with self.assertRaisesRegex(SatelliteBatchError, "catalog"):
                validate_satellite_batch(queue, output, config=config)
            with self.assertRaisesRegex(SatelliteBatchError, "catalog output"):
                execute_satellite_queue(
                    queue,
                    output,
                    config=config,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])

    def test_schema_two_validates_unchanged_then_migrates_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(queue, _feature("active", "under_construction"))
            config = BatchConfig(minimum_interval_seconds=0.1)
            current = execute_satellite_queue(
                queue,
                output,
                config=config,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            prior = json.loads(json.dumps(current))
            prior["schema_version"] = PRIOR_BATCH_SCHEMA_VERSION
            prior["configuration"].pop("max_response_bytes")
            prior.pop("response_limit_migration")
            checkpoint = output / BATCH_MANIFEST_FILENAME
            checkpoint.write_text(
                json.dumps(prior, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = checkpoint.read_bytes()

            validated = validate_satellite_batch(queue, output, config=config)
            self.assertEqual(validated["schema_version"], PRIOR_BATCH_SCHEMA_VERSION)
            self.assertEqual(checkpoint.read_bytes(), before)
            with self.assertRaisesRegex(
                SatelliteBatchError, "saved batch configuration differs"
            ):
                validate_satellite_batch(
                    queue,
                    output,
                    config=BatchConfig(
                        minimum_interval_seconds=0.1,
                        max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES - 1,
                    ),
                )
            nondefault_runner = _CatalogRunner()
            with self.assertRaisesRegex(SatelliteBatchError, "default response cap"):
                execute_satellite_queue(
                    queue,
                    output,
                    config=BatchConfig(
                        minimum_interval_seconds=0.1,
                        max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES - 1,
                    ),
                    command_runner=nondefault_runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(nondefault_runner.calls, [])
            self.assertEqual(checkpoint.read_bytes(), before)

            runner = _CatalogRunner()
            migrated = execute_satellite_queue(
                queue,
                output,
                config=config,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(runner.calls, [])
            self.assertEqual(migrated["schema_version"], BATCH_SCHEMA_VERSION)
            self.assertEqual(
                migrated["configuration"]["max_response_bytes"],
                DEFAULT_MAX_RESPONSE_BYTES,
            )
            migration = migrated["response_limit_migration"]
            self.assertEqual(
                migration["source_schema_version"], PRIOR_BATCH_SCHEMA_VERSION
            )
            self.assertFalse(migration["historical_acquisition_bounded"])
            self.assertTrue(
                migration["historical_response_files_validated_within_cap"]
            )
            self.assertEqual(migration["historical_terminal_jobs_validated"], 1)
            self.assertEqual(migration["historical_completed_jobs"], 1)
            self.assertEqual(migration["historical_response_files"], 2)
            self.assertGreater(migration["largest_historical_response_bytes"], 0)

    def test_schema_two_oversized_history_fails_before_rewrite_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(queue, _feature("active", "under_construction"))
            config = BatchConfig(minimum_interval_seconds=0.1)
            current = execute_satellite_queue(
                queue,
                output,
                config=config,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            prior = json.loads(json.dumps(current))
            prior["schema_version"] = PRIOR_BATCH_SCHEMA_VERSION
            prior["configuration"].pop("max_response_bytes")
            prior.pop("response_limit_migration")
            checkpoint = output / BATCH_MANIFEST_FILENAME
            checkpoint.write_text(
                json.dumps(prior, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = checkpoint.read_bytes()
            baseline = next(output.glob("jobs/*/catalog/baseline-response.json"))
            baseline.write_bytes(b"x" * (DEFAULT_MAX_RESPONSE_BYTES + 1))
            runner = _CatalogRunner()

            with self.assertRaisesRegex(SatelliteBatchError, "exceeding"):
                execute_satellite_queue(
                    queue,
                    output,
                    config=config,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])
            self.assertEqual(checkpoint.read_bytes(), before)

    def test_response_limit_must_be_positive(self) -> None:
        with self.assertRaisesRegex(SatelliteBatchError, "max_response_bytes"):
            BatchConfig(max_response_bytes=0)

    def test_http_budget_reserves_worst_case_and_checkpoints_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(
                queue,
                _feature("first", "under_construction"),
                _feature("second", "under_construction"),
            )
            runner = _CatalogRunner(returncode=1)
            manifest = execute_satellite_queue(
                queue,
                output,
                config=BatchConfig(
                    minimum_interval_seconds=0.1,
                    catalog_retries=1,
                ),
                max_jobs=5,
                max_http_attempts=4,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(manifest["last_run"]["http_attempts_reserved"], 4)
            self.assertTrue(manifest["last_run"]["budget_exhausted"])
            self.assertEqual(manifest["summary"]["jobs_failed"], 1)
            self.assertEqual(manifest["summary"]["jobs_pending"], 1)
            failed = next(
                task for task in manifest["jobs"].values() if task["state"] == "failed"
            )
            self.assertEqual(failed["attempts"], 1)
            self.assertIn("exited 1", failed["failures"][0]["error"])

    def test_interrupted_attempt_is_recorded_and_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            output = root / "run"
            _queue_bundle(queue, _feature("active", "under_construction"))
            config = BatchConfig(minimum_interval_seconds=0.1)

            def interrupt(*args: object, **kwargs: object) -> None:
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_queue(
                    queue,
                    output,
                    config=config,
                    command_runner=interrupt,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            interrupted = json.loads(
                (output / BATCH_MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            interrupted_task = next(iter(interrupted["jobs"].values()))
            self.assertEqual(interrupted_task["state"], "pending")
            self.assertEqual(interrupted_task["attempts"], 1)

            resumed = execute_satellite_queue(
                queue,
                output,
                config=config,
                command_runner=_CatalogRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(resumed["jobs"].values()))
            self.assertEqual(task["state"], "completed")
            self.assertEqual(task["attempts"], 2)
            self.assertEqual(task["failures"][0]["attempt"], 1)
            self.assertIn("interrupted", task["failures"][0]["error"])

    def test_queue_tampering_is_rejected_before_command_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            _queue_bundle(queue, _feature("active", "under_construction"))
            queue_path = queue / QUEUE_FILENAME
            queue_path.write_bytes(queue_path.read_bytes() + b"{}\n")
            runner = _CatalogRunner()
            with self.assertRaises(ValueError):
                execute_satellite_queue(
                    queue,
                    root / "run",
                    config=BatchConfig(minimum_interval_seconds=0.1),
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
