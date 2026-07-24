from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib

from datacenter_atlas.satellite_calibration_rereview import (
    FORBIDDEN_REVIEW_KEYS,
    SatelliteCalibrationRereviewError,
    validate_satellite_calibration_rereview,
    write_satellite_calibration_rereview,
)
from datacenter_atlas.satellite_calibration_rerun import (
    GEOJSON_COLLECTION_PROPERTIES,
    PINNED_RUNTIME,
    PINNED_UV_COMMAND,
    REPORT_CLASSIFICATION,
    SatelliteCalibrationRerunError,
    _canonical_json,
    _processor_canonical_json,
    execute_satellite_calibration_reruns,
    validate_satellite_calibration_rerun_inputs,
    validate_satellite_calibration_rerun_output,
)
from datacenter_atlas.satellite_change import (
    CLEAR_SCL_CLASSES,
    REPORT_SCHEMA_VERSION,
    canonical_sha256,
    item_summary,
    report_source,
    select_feature,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json"
)
BUNDLE = (
    PACKAGE_ROOT
    / "satellite_calibration_rereview"
    / "2026-07-19-algorithm-v2-preparation-v1"
)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _checkpoint(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _canonical(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _argument(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(scanlines))
        + _chunk(b"IEND", b"")
    )


def _pinned_runtime() -> dict:
    return {
        "geospatial_runtime": {
            "gdal": PINNED_RUNTIME["gdal"],
            "proj": PINNED_RUNTIME["proj"],
        },
        "packages": {
            "numpy": {
                "distribution": "numpy",
                "import_error": None,
                "runtime_version": PINNED_RUNTIME["packages"]["numpy"],
                "version": PINNED_RUNTIME["packages"]["numpy"],
            },
            "PIL": {
                "distribution": "Pillow",
                "import_error": None,
                "runtime_version": PINNED_RUNTIME["packages"]["Pillow"],
                "version": PINNED_RUNTIME["packages"]["Pillow"],
            },
            "rasterio": {
                "distribution": "rasterio",
                "import_error": None,
                "runtime_version": PINNED_RUNTIME["packages"]["rasterio"],
                "version": PINNED_RUNTIME["packages"]["rasterio"],
            },
        },
        "pinned_uv_command": PINNED_UV_COMMAND,
        "platform": {
            "architecture": platform.architecture()[0],
            "descriptor": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
            "system": platform.system(),
        },
        "python": {
            "cache_tag": "cpython-312",
            "implementation": "CPython",
            "version": PINNED_RUNTIME["python_version"],
        },
        "required_packages_available": True,
        "zlib": {
            "compile_version": PINNED_RUNTIME["zlib_compile"],
            "runtime_version": PINNED_RUNTIME["zlib_runtime"],
        },
    }


PINNED_TEST_RUNTIME = _pinned_runtime()


@contextmanager
def _runtime(runtime: dict | None = None):
    with patch(
        "datacenter_atlas.satellite_calibration_rerun._runtime_lineage",
        return_value=copy.deepcopy(runtime or PINNED_TEST_RUNTIME),
    ):
        yield


def _fake_success(command, **kwargs):
    if "-B" not in command:
        raise AssertionError("runner omitted -B")
    if kwargs.get("env", {}).get("PYTHONDONTWRITEBYTECODE") != "1":
        raise AssertionError("runner omitted PYTHONDONTWRITEBYTECODE")
    output = Path(_argument(command, "--output-dir"))
    output.mkdir(parents=True)
    for name in ("after.png", "before.png", "change-overlay.png"):
        (output / name).write_bytes(_png(1, 1))
    (output / "comparison.png").write_bytes(_png(3, 1))
    proposals = {
        "features": [],
        "properties": GEOJSON_COLLECTION_PROPERTIES,
        "type": "FeatureCollection",
    }
    (output / "change-proposals.geojson").write_bytes(_canonical(proposals))
    baseline_document = json.loads(Path(_argument(command, "--baseline-stac")).read_text())
    current_document = json.loads(Path(_argument(command, "--current-stac")).read_text())
    baseline = select_feature(baseline_document, _argument(command, "--baseline-id"))
    current = select_feature(current_document, _argument(command, "--current-id"))
    report = {
        "algorithm_version": "sentinel-2-l2a-change-v2",
        "aoi_bbox_wgs84": [
            float(value) for value in _argument(command, "--bbox").split(",")
        ],
        "baseline": item_summary(baseline),
        "classification": REPORT_CLASSIFICATION,
        "current": item_summary(current),
        "entity": {
            "id": _argument(command, "--entity-id"),
            "name": _argument(command, "--entity-name"),
        },
        "grid": {
            "clear_scl_classes": sorted(CLEAR_SCL_CLASSES),
            "crs": "EPSG:32612",
            "height": 1,
            "pixel_area_m2": 100.0,
            "width": 1,
        },
        "metrics": {
            "mean_absolute_reflectance_change": 0.0,
            "mean_baseline_ndvi": 0.0,
            "mean_current_ndvi": 0.0,
            "mean_ndbi_change": 0.0,
            "mean_ndvi_change": 0.0,
            "proposal_area_m2_after_component_filter": 0.0,
            "proposal_component_count": 0,
            "proposal_pixel_fraction_of_valid": 0.0,
            "valid_pixel_fraction": 0.0,
        },
        "outputs": {
            name: _checkpoint(output / name)
            for name in (
                "after.png",
                "before.png",
                "change-overlay.png",
                "change-proposals.geojson",
                "comparison.png",
            )
        },
        "radiometry": {
            "normalized_index_negative_reflectance_policy": "clip_to_zero",
            "reflectance": "STAC raster scale and offset applied per scene and band",
        },
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": report_source(baseline, current),
        "thresholds": {
            "absolute_brightness_change": 0.1,
            "adaptive_absolute_reflectance_change": 0.1,
            "adaptive_quantile": 0.9,
            "applied_absolute_reflectance_change": 0.1,
            "minimum_absolute_reflectance_change": 0.08,
            "ndbi_gain": 0.12,
            "ndvi_loss": -0.12,
        },
    }
    (output / "report.json").write_bytes(_canonical(report))
    return subprocess.CompletedProcess(command, 0, stdout="fixture", stderr="")


def _fake_failure(command, **_kwargs):
    return subprocess.CompletedProcess(command, 2, stdout="", stderr="fixture failure")


def _manifest_path(shard: Path) -> Path:
    return shard / "batch-manifest.json"


def _resign_manifest(shard: Path, manifest: dict) -> None:
    path = _manifest_path(shard)
    sidecar = shard / "manifest.sha256"
    os.chmod(path, 0o644)
    os.chmod(sidecar, 0o644)
    raw = _canonical(manifest)
    path.write_bytes(raw)
    sidecar.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  batch-manifest.json\n"
    )
    os.chmod(path, 0o444)
    os.chmod(sidecar, 0o444)


def _resign_completed(shard: Path, *, rewrite_report: bool = True) -> None:
    manifest = json.loads(_manifest_path(shard).read_text())
    blind_id = next(iter(manifest["jobs"]))
    change = shard / "jobs" / blind_id / "change"
    report_path = change / "report.json"
    report = json.loads(report_path.read_text())
    if rewrite_report:
        report["outputs"] = {
            name: _checkpoint(change / name)
            for name in (
                "after.png",
                "before.png",
                "change-overlay.png",
                "change-proposals.geojson",
                "comparison.png",
            )
        }
        os.chmod(report_path, 0o644)
        report_path.write_bytes(_canonical(report))
        os.chmod(report_path, 0o444)
    manifest["jobs"][blind_id]["artifacts"] = {
        name: _checkpoint(change / name)
        for name in (
            "after.png",
            "before.png",
            "change-overlay.png",
            "change-proposals.geojson",
            "comparison.png",
            "report.json",
        )
    }
    _resign_manifest(shard, manifest)


def _copy_frozen(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


class SatelliteCalibrationRereviewTests(unittest.TestCase):
    def test_frozen_bundle_reproduces_offline(self):
        manifest = validate_satellite_calibration_rereview(
            BUNDLE, definition_path=DEFINITION
        )
        self.assertEqual(manifest["counts"]["historical_items"], 43)
        self.assertEqual(manifest["counts"]["unique_aois"], 43)
        self.assertEqual(manifest["counts"]["algorithm_v2_outputs_available"], 0)
        self.assertEqual(manifest["counts"]["blind_items_blocked_missing_output"], 43)
        self.assertFalse(manifest["counts"]["v2_calibration_claimed"])
        self.assertEqual(manifest["counts"]["analyst_decisions_performed"], 0)
        self.assertEqual(manifest["counts"]["labels_reused"], 0)

    def test_reviewer_queue_is_blind_and_blocked(self):
        rows = _rows(BUNDLE / "reviewer-queue.jsonl")
        self.assertEqual(len(rows), 43)
        self.assertEqual(len({row["blind_item_id"] for row in rows}), 43)
        self.assertEqual(len({tuple(row["aoi_bbox_wgs84"]) for row in rows}), 43)
        self.assertTrue(all(row["algorithm_v2_output"] is None for row in rows))
        self.assertTrue(
            all(
                row["mapping_status"] == "unavailable_no_exact_identity_output"
                and row["review_material_status"]
                == "blocked_algorithm_v2_output_unavailable"
                and row["preparation_only"] is True
                for row in rows
            )
        )
        all_keys = {key for row in rows for key in _keys(row)}
        self.assertFalse(FORBIDDEN_REVIEW_KEYS & all_keys)
        raw = (BUNDLE / "reviewer-queue.jsonl").read_text().lower()
        self.assertNotIn('"retain"', raw)
        self.assertNotIn('"reject"', raw)

    def test_weak_overlaps_are_not_substituted(self):
        summary = json.loads((BUNDLE / "summary.json").read_text())
        self.assertEqual(
            summary["mapping_audit"],
            {
                "exact_v2_outputs": 0,
                "historical_items_with_aoi_only_or_weaker_overlap": 2,
                "historical_items_with_scene_pair_only_or_weaker_overlap": 13,
                "weak_matches_substituted": 0,
            },
        )

    def test_run_inventory_binds_every_frozen_run_and_v2_code_hash(self):
        inventory = json.loads((BUNDLE / "run-inventory.json").read_text())
        runs = inventory["frozen_runs"]
        self.assertEqual(len(runs), 5)
        v2 = [run for run in runs if run["algorithm_version"].endswith("-v2")]
        self.assertEqual(len(v2), 4)
        self.assertEqual(sum(run["verified_completed_reports"] for run in v2), 43)
        for run in v2:
            self.assertEqual(
                run["processor_files"]["datacenter_atlas/satellite_change.py"]["sha256"],
                "d18ee916c7e96bef7fed704960bb92292be954e0f4d7a8982f58b979acc662f2",
            )
            self.assertEqual(
                run["processor_files"]["scripts/sentinel_change.py"]["sha256"],
                "745c737d28fca65dddb37a0d56396d815c5d52cf90f697d714769aa52d59b78f",
            )

    def test_sealed_lineage_is_separate_one_to_one_and_non_reusable(self):
        queue_ids = {row["blind_item_id"] for row in _rows(BUNDLE / "reviewer-queue.jsonl")}
        lineage = _rows(BUNDLE / "sealed" / "lineage.jsonl")
        self.assertEqual(queue_ids, {row["blind_item_id"] for row in lineage})
        self.assertEqual(len(lineage), 43)
        self.assertTrue(
            all(
                row["policy"]
                == {
                    "may_join_before_blind_review_closes": False,
                    "may_seed_algorithm_v2_decision": False,
                    "provenance_only": True,
                }
                for row in lineage
            )
        )
        self.assertEqual((BUNDLE / "sealed").stat().st_mode & 0o777, 0o500)
        self.assertEqual(
            (BUNDLE / "sealed" / "lineage.jsonl").stat().st_mode & 0o777,
            0o400,
        )

    def test_closed_tree_modes_and_manifest_hash(self):
        self.assertEqual(BUNDLE.stat().st_mode & 0o777, 0o555)
        for name in (
            "ATTRIBUTION.txt",
            "README.md",
            "manifest.json",
            "manifest.sha256",
            "reviewer-queue.jsonl",
            "rerun-specs.jsonl",
            "run-inventory.json",
            "summary.json",
        ):
            self.assertEqual((BUNDLE / name).stat().st_mode & 0o777, 0o444)
        digest = hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest()
        self.assertEqual(
            (BUNDLE / "manifest.sha256").read_text(),
            f"{digest}  manifest.json\n",
        )

    def test_writer_refuses_existing_output(self):
        with self.assertRaisesRegex(SatelliteCalibrationRereviewError, "already exists"):
            write_satellite_calibration_rereview(DEFINITION, BUNDLE)

    def test_all_43_rerun_specs_validate_without_numerical_execution(self):
        result = validate_satellite_calibration_rerun_inputs(
            BUNDLE, definition_path=DEFINITION
        )
        self.assertEqual(result["rerun_specs_validated"], 43)
        self.assertEqual(result["source_catalog_artifacts_validated"], 129)
        self.assertEqual(result["unique_aois"], 43)
        self.assertEqual(result["unique_historical_queue_ids"], 43)
        self.assertEqual(result["numerical_jobs_executed"], 0)
        self.assertTrue(result["input_validation_only"])
        self.assertFalse(result["v2_calibration_claimed"])
        self.assertEqual(result["runtime"]["pinned_uv_command"], PINNED_UV_COMMAND)

    def test_relative_input_paths_are_normalized(self):
        previous = Path.cwd()
        try:
            os.chdir(PACKAGE_ROOT)
            result = validate_satellite_calibration_rerun_inputs(
                Path("satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1"),
                definition_path=Path(
                    "sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json"
                ),
            )
        finally:
            os.chdir(previous)
        self.assertEqual(result["rerun_specs_validated"], 43)

    def test_rerun_specs_bind_exact_processor_scenes_and_commands(self):
        specs = _rows(BUNDLE / "rerun-specs.jsonl")
        self.assertEqual(len(specs), 43)
        self.assertEqual(len({row["historical_queue_id"] for row in specs}), 43)
        for spec in specs:
            self.assertEqual(spec["status"], "ready_for_exact_algorithm_v2_rerun")
            self.assertEqual(
                spec["processor"]["files"]["module"]["sha256"],
                "d18ee916c7e96bef7fed704960bb92292be954e0f4d7a8982f58b979acc662f2",
            )
            self.assertEqual(
                spec["processor"]["files"]["script"]["sha256"],
                "745c737d28fca65dddb37a0d56396d815c5d52cf90f697d714769aa52d59b78f",
            )
            self.assertEqual(
                set(spec["source_catalog_artifacts"]),
                {"baseline-response.json", "current-response.json", "manifest.json"},
            )
            self.assertIn("{job_output_dir}", spec["execution"]["arguments"])
            self.assertNotIn("decision", set(_keys(spec)))
            self.assertNotIn("outcome", set(_keys(spec)))

    def test_extra_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            _copy_frozen(BUNDLE, copied)
            os.chmod(copied, 0o755)
            (copied / "extra.json").write_text("{}\n")
            os.chmod(copied / "extra.json", 0o444)
            os.chmod(copied, 0o555)
            with self.assertRaisesRegex(SatelliteCalibrationRereviewError, "not closed"):
                validate_satellite_calibration_rereview(copied, definition_path=DEFINITION)

    def test_queue_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            _copy_frozen(BUNDLE, copied)
            queue = copied / "reviewer-queue.jsonl"
            os.chmod(queue, 0o644)
            queue.write_bytes(
                queue.read_bytes().replace(
                    b'"preparation_only":true', b'"preparation_only":false', 1
                )
            )
            os.chmod(queue, 0o444)
            with self.assertRaisesRegex(
                SatelliteCalibrationRereviewError, "does not reproduce"
            ):
                validate_satellite_calibration_rereview(copied, definition_path=DEFINITION)

    def test_sealed_mode_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            _copy_frozen(BUNDLE, copied)
            os.chmod(copied / "sealed" / "lineage.jsonl", 0o444)
            with self.assertRaisesRegex(SatelliteCalibrationRereviewError, "mode mismatch"):
                validate_satellite_calibration_rereview(copied, definition_path=DEFINITION)


class SatelliteCalibrationRerunOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.completed = root / "completed"
        cls.failure = root / "failure"
        with _runtime(), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run",
            side_effect=_fake_success,
        ):
            execute_satellite_calibration_reruns(
                BUNDLE,
                cls.completed,
                definition_path=DEFINITION,
                start_index=0,
                max_jobs=1,
                max_attempts=1,
                timeout_seconds=10,
                minimum_interval_seconds=0,
            )
        with _runtime(), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run",
            side_effect=_fake_failure,
        ):
            execute_satellite_calibration_reruns(
                BUNDLE,
                cls.failure,
                definition_path=DEFINITION,
                start_index=1,
                max_jobs=1,
                max_attempts=1,
                timeout_seconds=10,
                minimum_interval_seconds=0,
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _validate(self, path: Path):
        with _runtime():
            return validate_satellite_calibration_rerun_output(
                BUNDLE, path, definition_path=DEFINITION
            )

    def test_completed_fixture_validates_offline(self):
        manifest = self._validate(self.completed)
        self.assertEqual(manifest["state"], "completed")
        self.assertEqual(
            manifest["summary"],
            {"jobs_completed": 1, "jobs_failed": 0, "jobs_selected": 1},
        )

    def test_processor_json_contract_preserves_default_ascii_escaping(self):
        value = {"entity": {"name": "Datacenter Mutualisé Lorrain facility"}}
        self.assertEqual(_processor_canonical_json(value), _canonical(value))
        self.assertIn(b"Mutualis\\u00e9", _processor_canonical_json(value))
        self.assertNotEqual(_processor_canonical_json(value), _canonical_json(value))

    def test_failure_fixture_validates_offline(self):
        manifest = self._validate(self.failure)
        self.assertEqual(manifest["state"], "completed_with_failures")
        self.assertEqual(
            manifest["summary"],
            {"jobs_completed": 0, "jobs_failed": 1, "jobs_selected": 1},
        )

    def test_relative_output_paths_are_normalized(self):
        previous = Path.cwd()
        try:
            os.chdir(PACKAGE_ROOT)
            with _runtime():
                manifest = validate_satellite_calibration_rerun_output(
                    Path(os.path.relpath(BUNDLE, PACKAGE_ROOT)),
                    Path(os.path.relpath(self.completed, PACKAGE_ROOT)),
                    definition_path=Path(os.path.relpath(DEFINITION, PACKAGE_ROOT)),
                )
        finally:
            os.chdir(previous)
        self.assertEqual(manifest["state"], "completed")

    def test_snapshot_uses_no_bytecode_and_publishes_no_pycache(self):
        self.assertFalse(any("__pycache__" in path.parts for path in self.completed.rglob("*")))

    def test_42_plus_2_rejects_before_output_or_subprocess(self):
        with tempfile.TemporaryDirectory() as temporary, _runtime(), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run"
        ) as runner:
            output = Path(temporary) / "never-created"
            with self.assertRaisesRegex(
                SatelliteCalibrationRerunError, "exceeds the spec inventory"
            ):
                execute_satellite_calibration_reruns(
                    BUNDLE,
                    output,
                    definition_path=DEFINITION,
                    start_index=42,
                    max_jobs=2,
                )
            runner.assert_not_called()
            self.assertFalse(output.exists())

    def test_missing_runtime_rejects_before_output_or_subprocess(self):
        missing = copy.deepcopy(PINNED_TEST_RUNTIME)
        missing["required_packages_available"] = False
        missing["packages"]["rasterio"]["version"] = None
        with tempfile.TemporaryDirectory() as temporary, _runtime(missing), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run"
        ) as runner:
            output = Path(temporary) / "never-created"
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "incomplete"):
                execute_satellite_calibration_reruns(
                    BUNDLE, output, definition_path=DEFINITION
                )
            runner.assert_not_called()
            self.assertFalse(output.exists())

    def test_runtime_drift_rejects_without_publication(self):
        drift = copy.deepcopy(PINNED_TEST_RUNTIME)
        drift["platform"]["descriptor"] = "drifted"
        calls = [copy.deepcopy(PINNED_TEST_RUNTIME), drift]

        def lineage(**_kwargs):
            return calls.pop(0) if calls else drift

        with tempfile.TemporaryDirectory() as temporary, patch(
            "datacenter_atlas.satellite_calibration_rerun._runtime_lineage",
            side_effect=lineage,
        ), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run"
        ) as runner:
            output = Path(temporary) / "never-created"
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "drifted"):
                execute_satellite_calibration_reruns(
                    BUNDLE, output, definition_path=DEFINITION
                )
            runner.assert_not_called()
            self.assertFalse(output.exists())

    def test_forced_prepublish_validation_failure_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary, _runtime(), patch(
            "datacenter_atlas.satellite_calibration_rerun.subprocess.run",
            side_effect=_fake_success,
        ), patch(
            "datacenter_atlas.satellite_calibration_rerun.validate_satellite_calibration_rerun_output",
            side_effect=SatelliteCalibrationRerunError("forced prepublish failure"),
        ):
            output = Path(temporary) / "never-published"
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "forced"):
                execute_satellite_calibration_reruns(
                    BUNDLE,
                    output,
                    definition_path=DEFINITION,
                    max_attempts=1,
                    timeout_seconds=10,
                    minimum_interval_seconds=0,
                )
            self.assertFalse(output.exists())

    def test_text_png_with_recomputed_hashes_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            target = next(copied.glob("jobs/*/change/before.png"))
            os.chmod(target, 0o644)
            target.write_text("not png\n")
            os.chmod(target, 0o444)
            _resign_completed(copied)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "not a PNG"):
                self._validate(copied)

    def test_wrong_png_dimensions_with_recomputed_hashes_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            target = next(copied.glob("jobs/*/change/before.png"))
            os.chmod(target, 0o644)
            target.write_bytes(_png(2, 1))
            os.chmod(target, 0o444)
            _resign_completed(copied)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "dimensions mismatch"):
                self._validate(copied)

    def test_malformed_geojson_with_recomputed_hashes_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            target = next(copied.glob("jobs/*/change/change-proposals.geojson"))
            os.chmod(target, 0o644)
            target.write_bytes(_canonical({"type": "FeatureCollection", "features": []}))
            os.chmod(target, 0o444)
            _resign_completed(copied)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "schema is invalid"):
                self._validate(copied)

    def test_cross_aoi_geojson_with_recomputed_hashes_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            change = next(copied.glob("jobs/*/change"))
            report_path = change / "report.json"
            report = json.loads(report_path.read_text())
            report["metrics"]["proposal_component_count"] = 1
            report["metrics"]["proposal_area_m2_after_component_filter"] = 5000.0
            properties = {
                "area_m2": 5000.0,
                "class": "large_spectral_change_candidate",
                "data_centre_type_claim": False,
                "energy_claim": False,
                "identity_claim": False,
                "it_capacity_claim": False,
                "lifecycle_claim": False,
                "operating_status_claim": False,
                "operator_claim": False,
                "power_claim": False,
                "pue_claim": False,
                "review_required": True,
                "workload_claim": False,
            }
            proposals = {
                "features": [
                    {
                        "geometry": {
                            "coordinates": [[[179.0, 80.0], [179.1, 80.0], [179.1, 80.1], [179.0, 80.0]]],
                            "type": "Polygon",
                        },
                        "id": "change-proposal-1",
                        "properties": properties,
                        "type": "Feature",
                    }
                ],
                "properties": GEOJSON_COLLECTION_PROPERTIES,
                "type": "FeatureCollection",
            }
            proposal_path = change / "change-proposals.geojson"
            os.chmod(proposal_path, 0o644)
            proposal_path.write_bytes(_canonical(proposals))
            os.chmod(proposal_path, 0o444)
            report["outputs"]["change-proposals.geojson"] = _checkpoint(proposal_path)
            os.chmod(report_path, 0o644)
            report_path.write_bytes(_canonical(report))
            os.chmod(report_path, 0o444)
            _resign_completed(copied)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "outside the exact AOI"):
                self._validate(copied)

    def test_noncanonical_report_with_recomputed_manifest_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            report_path = next(copied.glob("jobs/*/change/report.json"))
            os.chmod(report_path, 0o644)
            report_path.write_bytes(report_path.read_bytes() + b" \n")
            os.chmod(report_path, 0o444)
            _resign_completed(copied, rewrite_report=False)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "not canonical"):
                self._validate(copied)

    def test_extra_report_key_with_recomputed_manifest_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            report_path = next(copied.glob("jobs/*/change/report.json"))
            report = json.loads(report_path.read_text())
            report["extra"] = False
            os.chmod(report_path, 0o644)
            report_path.write_bytes(_canonical(report))
            os.chmod(report_path, 0o444)
            _resign_completed(copied, rewrite_report=False)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "schema is invalid"):
                self._validate(copied)

    def test_recomputed_sidecar_decision_tamper_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            manifest = json.loads(_manifest_path(copied).read_text())
            manifest["decision"] = "hidden"
            _resign_manifest(copied, manifest)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "forbidden key"):
                self._validate(copied)

    def test_recomputed_sidecar_failure_review_tamper_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.failure, copied)
            manifest = json.loads(_manifest_path(copied).read_text())
            blind_id = next(iter(manifest["jobs"]))
            manifest["jobs"][blind_id]["failure"]["review"] = "hidden"
            _resign_manifest(copied, manifest)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "forbidden key"):
                self._validate(copied)

    def test_extra_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            os.chmod(copied, 0o755)
            (copied / "extra.json").write_text("{}\n")
            os.chmod(copied / "extra.json", 0o444)
            os.chmod(copied, 0o555)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "tree is not closed"):
                self._validate(copied)

    def test_mode_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            target = next(copied.glob("jobs/*/change/report.json"))
            os.chmod(target, 0o644)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "file mode mismatch"):
                self._validate(copied)

    def test_manifest_sidecar_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "shard"
            _copy_frozen(self.completed, copied)
            sidecar = copied / "manifest.sha256"
            os.chmod(sidecar, 0o644)
            sidecar.write_text("0" * 64 + "  batch-manifest.json\n")
            os.chmod(sidecar, 0o444)
            with self.assertRaisesRegex(SatelliteCalibrationRerunError, "sidecar mismatch"):
                self._validate(copied)


if __name__ == "__main__":
    unittest.main()
