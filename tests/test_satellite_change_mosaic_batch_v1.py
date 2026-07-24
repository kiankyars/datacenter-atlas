from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

try:
    from datacenter_atlas.datacenter_atlas import (
        satellite_change_mosaic_batch_v1 as batch,
    )
except ModuleNotFoundError:
    import datacenter_atlas.satellite_change_mosaic_batch_v1 as batch
from datacenter_atlas.satellite_change import CLEAR_SCL_CLASSES, report_source
from scripts.sentinel_change_mosaic import (
    GEOJSON_COLLECTION_PROPERTIES,
    REPORT_CLASSIFICATION,
)


ROOT = Path(__file__).resolve().parents[1]
PREPARATION = ROOT / batch.PREPARATION_DIRECTORY_PATH
DEFINITION = ROOT / batch.PREPARATION_DEFINITION_PATH
DEFAULT_OUTPUT = ROOT / batch.DEFAULT_OUTPUT_PATH


class _Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 21, 3, 0, tzinfo=UTC)

    def __call__(self) -> str:
        value = self.current.isoformat(timespec="seconds").replace("+00:00", "Z")
        self.current += timedelta(seconds=1)
        return value


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def _record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def _command_values(command: list[str]) -> dict[str, object]:
    values: dict[str, object] = {}
    index = 2
    while index < len(command):
        flag = command[index]
        if flag.startswith("--bbox="):
            values["--bbox"] = flag.split("=", 1)[1]
            index += 1
            continue
        value = command[index + 1]
        if flag.endswith("-companion"):
            values.setdefault(flag, [])
            assert isinstance(values[flag], list)
            values[flag].append(value)
        else:
            values[flag] = value
        index += 2
    return values


class _SuccessRunner:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if Path(command[1]) != ROOT / "scripts/sentinel_change_mosaic.py":
            return subprocess.CompletedProcess(command, 9, "", "wrong processor")
        values = _command_values(command)
        entity_id = str(values["--entity-id"])
        row = next(
            value
            for value in self.rows.values()
            if value["entity"]["id"] == entity_id  # type: ignore[index]
        )
        output = Path(str(values["--output-dir"]))
        output.mkdir(parents=True)
        for name, dimensions, color in (
            ("before.png", (2, 2), (20, 40, 60)),
            ("after.png", (2, 2), (30, 50, 70)),
            ("change-overlay.png", (2, 2), (80, 20, 20)),
            ("comparison.png", (6, 2), (30, 30, 30)),
        ):
            (output / name).write_bytes(_png(*dimensions, color))
        geojson = {
            "type": "FeatureCollection",
            "features": [],
            "properties": GEOJSON_COLLECTION_PROPERTIES,
        }
        (output / "change-proposals.geojson").write_bytes(
            batch._canonical_json(geojson)
        )
        baseline_primary, baseline_items, current_primary, current_items = (
            batch._load_bound_epochs(row)
        )
        prepared = batch._prepared_arguments(row)
        report = {
            "schema_version": batch.REPORT_SCHEMA_VERSION,
            "algorithm_version": batch.ALGORITHM_VERSION,
            "spectral_core_algorithm_version": batch.SPECTRAL_CORE_ALGORITHM_VERSION,
            "entity": {
                "id": row["entity"]["id"],  # type: ignore[index]
                "name": row["entity"]["name"],  # type: ignore[index]
            },
            "aoi_bbox_wgs84": row["aoi_bbox_wgs84"],
            "baseline": batch._epoch_summary(baseline_primary, baseline_items),
            "current": batch._epoch_summary(current_primary, current_items),
            "source": report_source(baseline_primary, current_primary),
            "classification": REPORT_CLASSIFICATION,
            "mosaic_contract": {
                "explicit_item_hash_bindings": True,
                "same_datatake_and_datastrip_required": True,
                "maximum_companion_sensing_time_delta_seconds": (
                    batch.MAX_COMPANION_TIME_DELTA_SECONDS
                ),
                "product_uri_identity_policy": "exact_except_mgrs_tile_token",
                "frozen_stac_response_sha256": {
                    "baseline": prepared["--baseline-stac-sha256"],
                    "current": prepared["--current-stac-sha256"],
                },
                "nonzero_overlap_conflict_policy": "reject",
                "missing_spatial_coverage_policy": "reject",
                "nodata_policy": "invalid_never_clear",
                "baseline_metadata_coverage": row["epochs"]["baseline"][  # type: ignore[index]
                    "selected_coverage"
                ],
                "current_metadata_coverage": row["epochs"]["current"][  # type: ignore[index]
                    "selected_coverage"
                ],
            },
            "grid": {
                "crs": "EPSG:32612",
                "width": 2,
                "height": 2,
                "pixel_area_m2": 100.0,
                "clear_scl_classes": sorted(CLEAR_SCL_CLASSES),
                "aoi_inclusion": "exact_wgs84_pixel_centers",
            },
            "thresholds": {
                "minimum_absolute_reflectance_change": 0.08,
                "adaptive_quantile": 0.98,
                "adaptive_absolute_reflectance_change": 0.1,
                "applied_absolute_reflectance_change": 0.1,
                "ndvi_loss": 0.15,
                "ndbi_gain": 0.15,
                "absolute_brightness_change": 0.12,
            },
            "radiometry": {
                "reflectance": (
                    "STAC raster scale and offset applied per epoch and band"
                ),
                "normalized_index_negative_reflectance_policy": "clip_to_zero",
            },
            "metrics": {
                "valid_pixel_fraction": 1.0,
                "proposal_pixel_fraction_of_valid": 0.0,
                "mean_baseline_ndvi": 0.2,
                "mean_current_ndvi": 0.2,
                "mean_ndvi_change": 0.0,
                "mean_ndbi_change": 0.0,
                "mean_absolute_reflectance_change": 0.0,
                "proposal_component_count": 0,
                "proposal_area_m2_after_component_filter": 0.0,
            },
            "outputs": {
                name: _record(output / name)
                for name in sorted(batch.REPORT_BOUND_FILES)
            },
        }
        (output / "report.json").write_bytes(batch._canonical_json(report))
        return subprocess.CompletedProcess(command, 0, "ok", "")


class _FailureRunner:
    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, "", "fixture failure")


class MosaicBatchV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = batch._validated_inputs(PREPARATION, DEFINITION)
        cls.rows = {
            queue_id: dict(row) for queue_id, row in cls.inputs.rows_by_id.items()
        }

    def config(self, *, attempts: int = 3) -> batch.MosaicBatchConfig:
        return batch.MosaicBatchConfig(
            timeout_seconds=60,
            minimum_interval_seconds=0,
            max_job_attempts=attempts,
        )

    def test_exact_frozen_partition_lineage_and_retained_production_incident(self) -> None:
        self.assertEqual(tuple(self.inputs.rows_by_id), batch.EXPECTED_QUEUE_IDS)
        self.assertEqual(
            tuple(row["queue_position"] for row in self.inputs.rows),
            batch.EXPECTED_QUEUE_POSITIONS,
        )
        self.assertEqual(
            self.inputs.lineage["closed_tree"]["inventory_sha256"],
            batch.PREPARATION_TREE_SHA256,
        )
        self.assertEqual(
            self.inputs.lineage["partition"]["sha256"], batch.READY_SHA256
        )
        incident_path = DEFAULT_OUTPUT / batch.BATCH_MANIFEST_FILENAME
        incident_raw = incident_path.read_bytes()
        self.assertEqual(
            sha256(incident_raw).hexdigest(),
            "8c23b3f6d548e302e958ac214af077bf94fe65ee4dc9db95407dd581a440a984",
        )
        incident = json.loads(incident_raw)
        self.assertEqual(incident["state"], "incomplete")
        self.assertEqual(incident["summary"]["jobs_completed"], 0)
        self.assertEqual(incident["summary"]["jobs_failed"], 6)
        self.assertEqual(
            {
                failure["kind"]
                for job in incident["jobs"].values()
                for failure in job["failures"]
            },
            {"command_exit"},
        )
        self.assertTrue(
            all(
                "mosaic has conflicting nonzero overlap" in failure["error"]
                for job in incident["jobs"].values()
                for failure in job["failures"]
            )
        )
        for row in self.inputs.rows:
            arguments = row["execution"]["arguments"]
            self.assertEqual(len(arguments), 26)
            self.assertEqual(arguments[-4:], ["--output-dir", "{job_output_dir}", "--minimum-component-area-m2", "5000"])

    def test_bounded_resume_exact_command_and_full_offline_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            runner = _SuccessRunner(self.rows)
            clock = _Clock()
            first = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=1,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=clock,
            )
            self.assertEqual(first["summary"]["jobs_completed"], 1)
            self.assertEqual(first["summary"]["jobs_pending"], 5)
            self.assertTrue(first["runs"][0]["budget_exhausted"])
            second = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=5,
                command_runner=runner,
                sleep=lambda _: None,
                timestamp=clock,
            )
            self.assertEqual(second["state"], "completed")
            self.assertEqual(second["summary"]["jobs_completed"], 6)
            self.assertEqual(second["summary"]["output_artifacts"], 36)
            self.assertEqual(len(runner.calls), 6)
            for command, queue_id in zip(
                runner.calls, batch.EXPECTED_QUEUE_IDS, strict=True
            ):
                self.assertEqual(Path(command[1]), ROOT / "scripts/sentinel_change_mosaic.py")
                self.assertNotIn("sentinel_change.py", command[1])
                values = _command_values(command)
                prepared = batch._prepared_arguments(self.rows[queue_id])
                for flag, value in prepared.items():
                    if flag == "--output-dir":
                        self.assertTrue(str(values[flag]).endswith("/.change.staging"))
                    else:
                        self.assertEqual(values[flag], value)
            validated = batch.validate_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
            )
            self.assertEqual(validated, second)

    def test_failure_retry_attempt_cap_and_config_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            clock = _Clock()
            failed = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(attempts=2),
                max_jobs=1,
                command_runner=_FailureRunner(),
                timestamp=clock,
            )
            first_id = batch.EXPECTED_QUEUE_IDS[0]
            self.assertEqual(failed["jobs"][first_id]["state"], "failed")
            self.assertEqual(failed["jobs"][first_id]["attempts"], 1)
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "configuration differs"
            ):
                batch.execute_satellite_change_mosaic_batch_v1(
                    PREPARATION,
                    output,
                    definition_path=DEFINITION,
                    config=self.config(attempts=3),
                    max_jobs=1,
                    command_runner=_SuccessRunner(self.rows),
                    timestamp=clock,
                )
            resumed = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(attempts=2),
                max_jobs=1,
                command_runner=_SuccessRunner(self.rows),
                timestamp=clock,
            )
            self.assertEqual(resumed["jobs"][first_id]["state"], "completed")
            self.assertEqual(resumed["jobs"][first_id]["attempts"], 2)
            self.assertEqual(len(resumed["jobs"][first_id]["failures"]), 1)

    def test_tampering_extra_missing_symlink_and_noncanonical_json_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            runner = _SuccessRunner(self.rows)
            document = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=1,
                command_runner=runner,
                timestamp=_Clock(),
            )
            first_id = batch.EXPECTED_QUEUE_IDS[0]
            change = output / document["jobs"][first_id]["output_directory"]
            report_path = change / "report.json"
            original_report = report_path.read_bytes()
            report_path.write_bytes(original_report.rstrip() + b"\n\n")
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "not canonical JSON"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )
            report_path.write_bytes(original_report)
            extra = change / "extra.txt"
            extra.write_text("extra\n")
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "file set differs"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )
            extra.unlink()
            missing = change / "before.png"
            original_png = missing.read_bytes()
            missing.unlink()
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "file set differs"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )
            missing.write_bytes(original_png)
            report_link = change / "report-link"
            report_link.symlink_to(report_path)
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "non-regular file"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )
            report_link.unlink()

    def test_report_contract_and_checkpoint_version_collision_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            document = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=1,
                command_runner=_SuccessRunner(self.rows),
                timestamp=_Clock(),
            )
            first_id = batch.EXPECTED_QUEUE_IDS[0]
            report_path = (
                output / document["jobs"][first_id]["output_directory"] / "report.json"
            )
            report = json.loads(report_path.read_text())
            report["algorithm_version"] = "wrong"
            report_path.write_bytes(batch._canonical_json(report))
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "version changed"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            document = batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=1,
                command_runner=_FailureRunner(),
                timestamp=_Clock(),
            )
            manifest = output / batch.BATCH_MANIFEST_FILENAME
            document["pipeline"] = "different-version"
            manifest.write_bytes(batch._canonical_json(document))
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "version collision"
            ):
                batch.validate_satellite_change_mosaic_batch_v1(
                    PREPARATION, output, definition_path=DEFINITION
                )

    def test_uncheckpointed_output_input_overlap_and_processor_drift_fail(self) -> None:
        with self.assertRaisesRegex(
            batch.SatelliteChangeMosaicBatchV1Error, "separate from"
        ):
            batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                PREPARATION,
                definition_path=DEFINITION,
                config=self.config(),
                command_runner=_FailureRunner(),
            )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            output.mkdir()
            (output / "orphan").write_text("orphan\n")
            with self.assertRaisesRegex(
                batch.SatelliteChangeMosaicBatchV1Error, "without a checkpoint"
            ):
                batch.execute_satellite_change_mosaic_batch_v1(
                    PREPARATION,
                    output,
                    definition_path=DEFINITION,
                    config=self.config(),
                    command_runner=_FailureRunner(),
                )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            batch.execute_satellite_change_mosaic_batch_v1(
                PREPARATION,
                output,
                definition_path=DEFINITION,
                config=self.config(),
                max_jobs=1,
                command_runner=_FailureRunner(),
                timestamp=_Clock(),
            )
            lineage = batch._processor_lineage()
            changed = json.loads(json.dumps(lineage))
            changed["algorithm_version"] = "drift"
            with patch.object(batch, "_processor_lineage", return_value=changed):
                with self.assertRaisesRegex(
                    batch.SatelliteChangeMosaicBatchV1Error,
                    "processor code or runtime changed",
                ):
                    batch.validate_satellite_change_mosaic_batch_v1(
                        PREPARATION, output, definition_path=DEFINITION
                    )

    def test_cli_validate_only_is_read_only_and_reports_errors(self) -> None:
        script = ROOT / "scripts/run_satellite_change_mosaic_batch_v1.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--validate-only",
                "--output-dir",
                str(ROOT / "does-not-exist-mosaic-run"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("satellite-change-mosaic-batch-v1 error", completed.stderr)
        self.assertFalse((ROOT / "does-not-exist-mosaic-run").exists())


if __name__ == "__main__":
    unittest.main()
