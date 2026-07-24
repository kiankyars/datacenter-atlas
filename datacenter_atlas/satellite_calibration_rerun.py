"""Fail-closed, bounded execution of exact algorithm-v2 calibration reruns."""

from __future__ import annotations

from collections import Counter
import hashlib
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import math
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
import zlib

from .satellite_calibration_rereview import (
    TARGET_ALGORITHM,
    SatelliteCalibrationRereviewError,
    validate_satellite_calibration_rereview,
)
from .satellite_change import (
    ALGORITHM_VERSION,
    CLEAR_SCL_CLASSES,
    REPORT_SCHEMA_VERSION,
    canonical_sha256,
    ensure_comparable,
    item_summary,
    parse_bbox,
    report_source,
    select_feature,
)


OUTPUT_FORMAT = "datacenter-atlas-satellite-calibration-v2-rerun-batch-v1"
EXPECTED_CHANGE_FILES = frozenset(
    {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
        "report.json",
    }
)
REPORT_BOUND_FILES = EXPECTED_CHANGE_FILES - {"report.json"}
AOI_EDGE_TOLERANCE_METERS = 25.0
PINNED_UV_COMMAND = (
    "uv run --python 3.12 --with numpy==2.5.1 --with pillow==12.3.0 "
    "--with rasterio==1.5.0 python scripts/run_satellite_calibration_reruns.py"
)
PINNED_RUNTIME = {
    "python_version": "3.12.13",
    "packages": {"numpy": "2.5.1", "Pillow": "12.3.0", "rasterio": "1.5.0"},
    "gdal": "3.12.1",
    "proj": "9.7.1",
    "zlib_compile": "1.2.12",
    "zlib_runtime": "1.2.12",
}
REPORT_CLASSIFICATION = {
    "label": "large_spectral_change_candidate",
    "identity_claim": False,
    "lifecycle_claim": False,
    "operating_status_claim": False,
    "power_claim": False,
    "energy_claim": False,
    "operator_claim": False,
    "data_centre_type_claim": False,
    "it_capacity_claim": False,
    "pue_claim": False,
    "workload_claim": False,
    "review_required": True,
    "limitations": [
        "10 m optical change cannot by itself identify a data centre.",
        "Single-date pairs are vulnerable to seasonal, atmospheric, and registration effects.",
        "Operator, data-centre type, IT capacity, PUE, workload, power, energy, and operating status cannot be inferred from this evidence bundle.",
    ],
}
GEOJSON_COLLECTION_PROPERTIES = {
    "schema_version": REPORT_SCHEMA_VERSION,
    "algorithm_version": ALGORITHM_VERSION,
    "meaning": "imagery change proposal only; not a data-centre identification",
    "identity_claim": False,
    "lifecycle_claim": False,
    "operating_status_claim": False,
    "power_claim": False,
    "energy_claim": False,
    "operator_claim": False,
    "data_centre_type_claim": False,
    "it_capacity_claim": False,
    "pue_claim": False,
    "workload_claim": False,
    "review_required": True,
}
MANIFEST_KEYS = frozenset(
    {
        "configuration",
        "format",
        "input_validation",
        "jobs",
        "preparation_dir",
        "processor",
        "runtime",
        "schema_version",
        "scope",
        "state",
        "summary",
    }
)
CONFIGURATION_KEYS = frozenset(
    {
        "max_attempts",
        "max_jobs",
        "minimum_interval_seconds",
        "start_index",
        "timeout_seconds",
    }
)
JOB_KEYS = frozenset(
    {
        "artifacts",
        "attempts",
        "blind_item_id",
        "failure",
        "historical_identity_sha256",
        "historical_queue_id",
        "rerun_spec_sha256",
        "state",
    }
)
SCOPE = {
    "labels_reused": 0,
    "numerical_change_evidence_only": True,
    "v2_calibration_claimed": False,
}
_FORBIDDEN_KEY_PARTS = frozenset({"decision", "outcome", "review"})


class SatelliteCalibrationRerunError(ValueError):
    """Raised when rerun validation or bounded execution fails closed."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _processor_canonical_json(value: Any) -> bytes:
    """Reproduce the frozen processor's default ASCII-escaped JSON writer."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _normalize(path: Path, label: str) -> Path:
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise SatelliteCalibrationRerunError(f"{label} path cannot be normalized") from error


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")

        def reject_constant(value: str) -> None:
            raise SatelliteCalibrationRerunError(
                f"{label} contains non-finite number {value}"
            )

        value = json.loads(text, parse_constant=reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteCalibrationRerunError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteCalibrationRerunError(f"{label} must be an object")
    return value


def _specs(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    try:
        lines = path.read_bytes().splitlines()
    except OSError as error:
        raise SatelliteCalibrationRerunError("rerun specs are unreadable") from error
    for index, line in enumerate(lines, 1):
        try:
            text = line.decode("utf-8")

            def reject_constant(value: str) -> None:
                raise SatelliteCalibrationRerunError(
                    f"rerun spec line {index} contains non-finite number {value}"
                )

            value = json.loads(text, parse_constant=reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SatelliteCalibrationRerunError(
                f"rerun spec line {index} is invalid JSON"
            ) from error
        if not isinstance(value, dict) or line + b"\n" != _canonical_line(value):
            raise SatelliteCalibrationRerunError(
                f"rerun spec line {index} is not canonical"
            )
        values.append(value)
    return values


def _project_path(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SatelliteCalibrationRerunError(f"{label} path is invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise SatelliteCalibrationRerunError(f"{label} path escapes the project")
    resolved = (project_root / relative).resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise SatelliteCalibrationRerunError(f"{label} path escapes the project") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise SatelliteCalibrationRerunError(f"{label} is missing")
    return resolved


def _verify_file(path: Path, descriptor: Mapping[str, Any], label: str) -> None:
    if set(descriptor) != {"bytes", "path", "sha256"} and set(descriptor) != {
        "bytes",
        "sha256",
    }:
        raise SatelliteCalibrationRerunError(f"{label} descriptor schema is invalid")
    if _checkpoint(path) != {
        "bytes": descriptor.get("bytes"),
        "sha256": descriptor.get("sha256"),
    }:
        raise SatelliteCalibrationRerunError(f"{label} checkpoint mismatch")


def _definition_project_root(definition_path: Path) -> Path:
    return _normalize(definition_path, "definition").parent.parent


def _runtime_lineage(*, require_packages: bool = False) -> dict[str, Any]:
    packages: dict[str, Any] = {}
    imported: dict[str, Any] = {}
    for import_name, distribution in (
        ("numpy", "numpy"),
        ("PIL", "Pillow"),
        ("rasterio", "rasterio"),
    ):
        try:
            package_version: str | None = distribution_version(distribution)
        except PackageNotFoundError:
            package_version = None
        import_error: str | None = None
        try:
            imported[import_name] = import_module(import_name)
        except (ImportError, OSError) as error:
            import_error = type(error).__name__
        packages[import_name] = {
            "distribution": distribution,
            "import_error": import_error,
            "runtime_version": getattr(imported.get(import_name), "__version__", None),
            "version": package_version,
        }
    rasterio = imported.get("rasterio")
    geospatial_runtime = {
        "gdal": getattr(rasterio, "__gdal_version__", None),
        "proj": getattr(rasterio, "__proj_version__", None),
    }
    available = all(
        value["version"] is not None
        and value["runtime_version"] is not None
        and value["import_error"] is None
        for value in packages.values()
    )
    result = {
        "geospatial_runtime": geospatial_runtime,
        "packages": packages,
        "pinned_uv_command": PINNED_UV_COMMAND,
        "platform": {
            "architecture": platform.architecture()[0],
            "descriptor": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
            "system": platform.system(),
        },
        "python": {
            "cache_tag": sys.implementation.cache_tag,
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "required_packages_available": available,
        "zlib": {
            "compile_version": zlib.ZLIB_VERSION,
            "runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        },
    }
    if require_packages:
        _require_pinned_runtime(result)
    return result


def _require_pinned_runtime(runtime: Mapping[str, Any]) -> None:
    if runtime.get("required_packages_available") is not True:
        raise SatelliteCalibrationRerunError(
            "numerical runtime is incomplete; use the documented pinned uv command"
        )
    if runtime.get("python", {}).get("version") != PINNED_RUNTIME["python_version"]:
        raise SatelliteCalibrationRerunError("numerical Python version is not pinned")
    for import_name, distribution in (
        ("numpy", "numpy"),
        ("PIL", "Pillow"),
        ("rasterio", "rasterio"),
    ):
        if runtime.get("packages", {}).get(import_name, {}).get("version") != PINNED_RUNTIME[
            "packages"
        ][distribution]:
            raise SatelliteCalibrationRerunError(
                f"numerical {distribution} version is not pinned"
            )
        if runtime.get("packages", {}).get(import_name, {}).get(
            "runtime_version"
        ) != PINNED_RUNTIME["packages"][distribution]:
            raise SatelliteCalibrationRerunError(
                f"imported numerical {distribution} version is not pinned"
            )
    if runtime.get("geospatial_runtime") != {
        "gdal": PINNED_RUNTIME["gdal"],
        "proj": PINNED_RUNTIME["proj"],
    }:
        raise SatelliteCalibrationRerunError("GDAL/PROJ runtime is not pinned")
    if runtime.get("zlib") != {
        "compile_version": PINNED_RUNTIME["zlib_compile"],
        "runtime_version": PINNED_RUNTIME["zlib_runtime"],
    }:
        raise SatelliteCalibrationRerunError("zlib runtime is not pinned")


def _assert_runtime(expected: Mapping[str, Any]) -> None:
    current = _runtime_lineage(require_packages=True)
    if current != expected:
        raise SatelliteCalibrationRerunError("numerical runtime drifted during shard")


def _revalidate_spec_inputs(project_root: Path, spec: Mapping[str, Any]) -> None:
    for label, descriptor in spec["processor"]["files"].items():
        path = _project_path(project_root, descriptor["path"], f"processor {label}")
        _verify_file(path, descriptor, f"processor {label}")
    for name, descriptor in spec["source_catalog_artifacts"].items():
        path = _project_path(project_root, descriptor["path"], name)
        _verify_file(path, descriptor, name)


def _verify_runtime_snapshot(runtime_dir: Path, processor: Mapping[str, Any]) -> None:
    for label, descriptor in processor["files"].items():
        path = runtime_dir / descriptor["path"]
        if not path.is_file() or path.is_symlink():
            raise SatelliteCalibrationRerunError(f"processor runtime {label} is missing")
        _verify_file(path, descriptor, f"processor runtime {label}")


def _forbidden_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered == "review_required":
        return False
    return any(part in lowered for part in _FORBIDDEN_KEY_PARTS)


def _reject_forbidden_keys(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _forbidden_key(key):
                raise SatelliteCalibrationRerunError(
                    f"{label} contains forbidden key {key}"
                )
            _reject_forbidden_keys(child, label)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child, label)


def validate_satellite_calibration_rerun_inputs(
    preparation_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    """Validate all local bindings without opening remote imagery."""

    definition_path = _normalize(definition_path, "definition")
    preparation_dir = _normalize(preparation_dir, "preparation")
    try:
        validate_satellite_calibration_rereview(
            preparation_dir, definition_path=definition_path
        )
    except SatelliteCalibrationRereviewError as error:
        raise SatelliteCalibrationRerunError(str(error)) from error
    project_root = _definition_project_root(definition_path)
    try:
        preparation_dir.relative_to(project_root)
    except ValueError as error:
        raise SatelliteCalibrationRerunError("preparation directory is outside project") from error
    specs = _specs(preparation_dir / "rerun-specs.jsonl")
    queue = {
        row["blind_item_id"]: row
        for row in _specs(preparation_dir / "reviewer-queue.jsonl")
    }
    if len(specs) != 43 or len(queue) != 43:
        raise SatelliteCalibrationRerunError("expected exactly 43 rerun inputs")
    seen_blind: set[str] = set()
    seen_queue: set[str] = set()
    total_catalog_bytes = 0
    catalog_mode_counts: Counter[str] = Counter()
    processor_reference: Mapping[str, Any] | None = None
    for spec in specs:
        blind_id = spec.get("blind_item_id")
        queue_id = spec.get("historical_queue_id")
        if blind_id in seen_blind or queue_id in seen_queue:
            raise SatelliteCalibrationRerunError("rerun identity is duplicated")
        seen_blind.add(blind_id)
        seen_queue.add(queue_id)
        if blind_id not in queue:
            raise SatelliteCalibrationRerunError("rerun spec has no blind queue row")
        if queue[blind_id].get("rerun_spec_sha256") != _sha256(_canonical_line(spec)):
            raise SatelliteCalibrationRerunError("rerun spec queue binding mismatch")
        processor = spec.get("processor")
        if not isinstance(processor, Mapping) or processor.get(
            "algorithm_version"
        ) != TARGET_ALGORITHM:
            raise SatelliteCalibrationRerunError("rerun algorithm mismatch")
        if processor_reference is None:
            processor_reference = processor
        elif processor != processor_reference:
            raise SatelliteCalibrationRerunError("rerun processor bindings differ")
        files = processor.get("files")
        if not isinstance(files, Mapping) or set(files) != {
            "models",
            "module",
            "package_init",
            "script",
        }:
            raise SatelliteCalibrationRerunError("rerun processor file set mismatch")
        for label, descriptor in files.items():
            path = _project_path(project_root, descriptor.get("path"), f"processor {label}")
            _verify_file(path, descriptor, f"processor {label}")
        artifacts = spec.get("source_catalog_artifacts")
        if not isinstance(artifacts, Mapping) or set(artifacts) != {
            "baseline-response.json",
            "current-response.json",
            "manifest.json",
        }:
            raise SatelliteCalibrationRerunError("source catalog artifact set mismatch")
        resolved: dict[str, Path] = {}
        for name, descriptor in artifacts.items():
            path = _project_path(project_root, descriptor.get("path"), name)
            _verify_file(path, descriptor, name)
            catalog_mode_counts[f"{path.stat().st_mode & 0o777:04o}"] += 1
            resolved[name] = path
            total_catalog_bytes += descriptor["bytes"]
        catalog_manifest = _json(resolved["manifest.json"], "catalog manifest")
        selected = spec.get("selected_scenes")
        if not isinstance(selected, Mapping) or set(selected) != {"baseline", "current"}:
            raise SatelliteCalibrationRerunError("selected scene schema mismatch")
        selected_ids = {
            epoch: selected[epoch].get("id") for epoch in ("baseline", "current")
        }
        if catalog_manifest.get("selected_ids") != selected_ids:
            raise SatelliteCalibrationRerunError("selected catalog IDs differ")
        for epoch in ("baseline", "current"):
            response = _json(resolved[f"{epoch}-response.json"], f"{epoch} response")
            try:
                feature = select_feature(response, selected_ids[epoch])
            except ValueError as error:
                raise SatelliteCalibrationRerunError(
                    f"selected {epoch} feature is missing"
                ) from error
            if canonical_sha256(feature) != selected[epoch].get("stac_item_sha256"):
                raise SatelliteCalibrationRerunError(
                    f"selected {epoch} feature hash mismatch"
                )
        expected_arguments = [
            "--baseline-stac",
            artifacts["baseline-response.json"]["path"],
            "--baseline-id",
            selected["baseline"]["id"],
            "--current-stac",
            artifacts["current-response.json"]["path"],
            "--current-id",
            selected["current"]["id"],
            "--bbox",
            ",".join(str(value) for value in spec["aoi_bbox_wgs84"]),
            "--entity-id",
            spec["entity"]["id"],
            "--entity-name",
            spec["entity"]["name"],
            "--output-dir",
            "{job_output_dir}",
            "--minimum-component-area-m2",
            str(processor["minimum_component_area_m2"]),
        ]
        execution = spec.get("execution")
        if not isinstance(execution, Mapping) or set(execution) != {
            "arguments",
            "script",
        }:
            raise SatelliteCalibrationRerunError("rerun execution schema mismatch")
        if execution.get("arguments") != expected_arguments:
            raise SatelliteCalibrationRerunError("rerun argument binding mismatch")
        if execution.get("script") != files["script"]["path"]:
            raise SatelliteCalibrationRerunError("rerun script binding mismatch")
    return {
        "algorithm_version": TARGET_ALGORITHM,
        "catalog_artifact_bytes_verified": total_catalog_bytes,
        "catalog_artifact_mode_counts": dict(sorted(catalog_mode_counts.items())),
        "input_validation_only": True,
        "numerical_jobs_executed": 0,
        "preparation_manifest": _checkpoint(preparation_dir / "manifest.json"),
        "processor_files": specs[0]["processor"]["files"],
        "rerun_specs_validated": len(specs),
        "runtime": _runtime_lineage(require_packages=False),
        "source_catalog_artifacts_validated": len(specs) * 3,
        "unique_aois": len({tuple(spec["aoi_bbox_wgs84"]) for spec in specs}),
        "unique_blind_items": len(seen_blind),
        "unique_historical_queue_ids": len(seen_queue),
        "v2_calibration_claimed": False,
    }


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteCalibrationRerunError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SatelliteCalibrationRerunError(f"{label} must be finite")
    return result


def _positive_number(value: Any, label: str) -> float:
    result = _finite_number(value, label)
    if result <= 0:
        raise SatelliteCalibrationRerunError(f"{label} must be positive")
    return result


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SatelliteCalibrationRerunError(f"{label} must be a positive integer")
    return value


def _png_dimensions(path: Path, label: str) -> tuple[int, int]:
    raw = path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SatelliteCalibrationRerunError(f"{label} is not a PNG")
    position = 8
    width: int | None = None
    height: int | None = None
    chunk_index = 0
    saw_end = False
    while position < len(raw):
        if len(raw) - position < 12:
            raise SatelliteCalibrationRerunError(f"{label} has a truncated PNG chunk")
        length = struct.unpack(">I", raw[position : position + 4])[0]
        chunk_type = raw[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(raw):
            raise SatelliteCalibrationRerunError(f"{label} has a truncated PNG payload")
        data = raw[position + 8 : position + 8 + length]
        stored_crc = struct.unpack(">I", raw[position + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != stored_crc:
            raise SatelliteCalibrationRerunError(f"{label} has a PNG CRC mismatch")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                raise SatelliteCalibrationRerunError(f"{label} lacks a valid PNG IHDR")
            width, height = struct.unpack(">II", data[:8])
            if width <= 0 or height <= 0:
                raise SatelliteCalibrationRerunError(f"{label} has invalid PNG dimensions")
        if chunk_type == b"IEND":
            if length != 0 or end != len(raw):
                raise SatelliteCalibrationRerunError(f"{label} has an invalid PNG IEND")
            saw_end = True
            break
        position = end
        chunk_index += 1
    if not saw_end or width is None or height is None:
        raise SatelliteCalibrationRerunError(f"{label} is an incomplete PNG")
    return width, height


def _validate_position(
    value: Any, label: str, aoi_bbox: tuple[float, float, float, float]
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise SatelliteCalibrationRerunError(f"{label} must be a two-coordinate position")
    longitude = _finite_number(value[0], f"{label} longitude")
    latitude = _finite_number(value[1], f"{label} latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise SatelliteCalibrationRerunError(f"{label} is outside WGS84 bounds")
    west, south, east, north = aoi_bbox
    latitude_tolerance = AOI_EDGE_TOLERANCE_METERS / 111_320.0
    maximum_absolute_latitude = min(89.999, max(abs(south), abs(north)))
    longitude_tolerance = AOI_EDGE_TOLERANCE_METERS / (
        111_320.0 * math.cos(math.radians(maximum_absolute_latitude))
    )
    if not (
        west - longitude_tolerance <= longitude <= east + longitude_tolerance
        and south - latitude_tolerance <= latitude <= north + latitude_tolerance
    ):
        raise SatelliteCalibrationRerunError(f"{label} is outside the exact AOI")


def _validate_geometry(
    value: Any, label: str, aoi_bbox: tuple[float, float, float, float]
) -> None:
    if not isinstance(value, Mapping) or set(value) != {"type", "coordinates"}:
        raise SatelliteCalibrationRerunError(f"{label} schema is invalid")
    kind = value.get("type")
    coordinates = value.get("coordinates")
    if kind == "Polygon":
        polygons = [coordinates]
    elif kind == "MultiPolygon":
        polygons = coordinates
    else:
        raise SatelliteCalibrationRerunError(f"{label} must be Polygon or MultiPolygon")
    if not isinstance(polygons, list) or not polygons:
        raise SatelliteCalibrationRerunError(f"{label} has no polygons")
    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise SatelliteCalibrationRerunError(
                f"{label} polygon {polygon_index} has no rings"
            )
        for ring_index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise SatelliteCalibrationRerunError(
                    f"{label} polygon {polygon_index} ring {ring_index} is invalid"
                )
            for position_index, position in enumerate(ring):
                _validate_position(
                    position,
                    f"{label} polygon {polygon_index} ring {ring_index} position {position_index}",
                    aoi_bbox,
                )


def _report_metrics(value: Any) -> dict[str, Any]:
    expected = {
        "valid_pixel_fraction",
        "proposal_pixel_fraction_of_valid",
        "mean_baseline_ndvi",
        "mean_current_ndvi",
        "mean_ndvi_change",
        "mean_ndbi_change",
        "mean_absolute_reflectance_change",
        "proposal_component_count",
        "proposal_area_m2_after_component_filter",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SatelliteCalibrationRerunError("change report metrics schema is invalid")
    result = dict(value)
    for field in expected - {"proposal_component_count"}:
        _finite_number(result[field], f"change report metric {field}")
    for field in ("valid_pixel_fraction", "proposal_pixel_fraction_of_valid"):
        if not 0 <= float(result[field]) <= 1:
            raise SatelliteCalibrationRerunError(f"change metric {field} is outside [0,1]")
    count = result["proposal_component_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise SatelliteCalibrationRerunError("proposal count is invalid")
    if float(result["proposal_area_m2_after_component_filter"]) < 0:
        raise SatelliteCalibrationRerunError("proposal area is negative")
    return result


def _validate_thresholds(value: Any) -> None:
    expected = {
        "minimum_absolute_reflectance_change",
        "adaptive_quantile",
        "adaptive_absolute_reflectance_change",
        "applied_absolute_reflectance_change",
        "ndvi_loss",
        "ndbi_gain",
        "absolute_brightness_change",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SatelliteCalibrationRerunError("change report threshold schema is invalid")
    for field in expected:
        _finite_number(value[field], f"change report threshold {field}")
    if not 0 < float(value["adaptive_quantile"]) < 1:
        raise SatelliteCalibrationRerunError("adaptive quantile is invalid")
    if float(value["minimum_absolute_reflectance_change"]) <= 0 or float(
        value["applied_absolute_reflectance_change"]
    ) <= 0:
        raise SatelliteCalibrationRerunError("reflectance thresholds are invalid")


def _selected_features(
    spec: Mapping[str, Any],
    project_root: Path,
    *,
    snapshot_dir: Path | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for epoch in ("baseline", "current"):
        name = f"{epoch}-response.json"
        path = (
            snapshot_dir / name
            if snapshot_dir is not None
            else _project_path(
                project_root,
                spec["source_catalog_artifacts"][name]["path"],
                name,
            )
        )
        _verify_file(path, spec["source_catalog_artifacts"][name], name)
        document = _json(path, f"{epoch} STAC response")
        try:
            feature = select_feature(document, spec["selected_scenes"][epoch]["id"])
        except ValueError as error:
            raise SatelliteCalibrationRerunError(f"selected {epoch} STAC is invalid") from error
        if canonical_sha256(feature) != spec["selected_scenes"][epoch][
            "stac_item_sha256"
        ]:
            raise SatelliteCalibrationRerunError(f"selected {epoch} STAC hash mismatch")
        selected.append(feature)
    try:
        ensure_comparable(selected[0], selected[1])
    except ValueError as error:
        raise SatelliteCalibrationRerunError("selected STAC pair is not comparable") from error
    return selected[0], selected[1]


def _validate_geojson(
    path: Path,
    *,
    expected_count: int,
    expected_area_m2: float,
    minimum_component_area_m2: float,
    aoi_bbox: tuple[float, float, float, float],
) -> None:
    raw = path.read_bytes()
    document = _json(path, "change proposals GeoJSON")
    if raw != _processor_canonical_json(document):
        raise SatelliteCalibrationRerunError("change proposals GeoJSON is not canonical")
    if set(document) != {"type", "features", "properties"} or document.get(
        "type"
    ) != "FeatureCollection":
        raise SatelliteCalibrationRerunError("change proposals GeoJSON schema is invalid")
    if document.get("properties") != GEOJSON_COLLECTION_PROPERTIES:
        raise SatelliteCalibrationRerunError("change proposals lost no-inference scope")
    features = document.get("features")
    if not isinstance(features, list) or len(features) != expected_count:
        raise SatelliteCalibrationRerunError("proposal count differs from report")
    expected_properties = {
        "class",
        "area_m2",
        "identity_claim",
        "lifecycle_claim",
        "operating_status_claim",
        "power_claim",
        "energy_claim",
        "operator_claim",
        "data_centre_type_claim",
        "it_capacity_claim",
        "pue_claim",
        "workload_claim",
        "review_required",
    }
    area_total = 0.0
    for index, feature in enumerate(features, 1):
        label = f"change proposal {index}"
        if not isinstance(feature, Mapping) or set(feature) != {
            "type",
            "id",
            "geometry",
            "properties",
        }:
            raise SatelliteCalibrationRerunError(f"{label} schema is invalid")
        if feature.get("type") != "Feature" or feature.get("id") != f"change-proposal-{index}":
            raise SatelliteCalibrationRerunError(f"{label} identity is invalid")
        _validate_geometry(feature.get("geometry"), f"{label} geometry", aoi_bbox)
        properties = feature.get("properties")
        if not isinstance(properties, Mapping) or set(properties) != expected_properties:
            raise SatelliteCalibrationRerunError(f"{label} properties are invalid")
        if properties.get("class") != "large_spectral_change_candidate" or any(
            properties.get(field) is not False
            for field in (
                "identity_claim",
                "lifecycle_claim",
                "operating_status_claim",
                "power_claim",
                "energy_claim",
                "operator_claim",
                "data_centre_type_claim",
                "it_capacity_claim",
                "pue_claim",
                "workload_claim",
            )
        ) or properties.get("review_required") is not True:
            raise SatelliteCalibrationRerunError(f"{label} lost no-inference scope")
        area = _finite_number(properties.get("area_m2"), f"{label} area")
        if area < minimum_component_area_m2:
            raise SatelliteCalibrationRerunError(f"{label} is below minimum area")
        area_total += area
    if round(area_total, 1) != round(expected_area_m2, 1):
        raise SatelliteCalibrationRerunError("proposal areas differ from report")


def _validated_change_output(
    path: Path,
    spec: Mapping[str, Any],
    project_root: Path,
    *,
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    if not path.is_dir() or path.is_symlink():
        raise SatelliteCalibrationRerunError("change output directory is missing")
    entries = list(path.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SatelliteCalibrationRerunError("change output contains a non-regular file")
    if {entry.name for entry in entries} != EXPECTED_CHANGE_FILES:
        raise SatelliteCalibrationRerunError("change output file set mismatch")
    report_path = path / "report.json"
    report_raw = report_path.read_bytes()
    report = _json(report_path, "change report")
    if report_raw != _processor_canonical_json(report):
        raise SatelliteCalibrationRerunError("change report is not canonical JSON")
    _reject_forbidden_keys(report, "change report")
    expected_report_keys = {
        "schema_version",
        "algorithm_version",
        "entity",
        "aoi_bbox_wgs84",
        "baseline",
        "current",
        "source",
        "classification",
        "grid",
        "thresholds",
        "radiometry",
        "metrics",
        "outputs",
    }
    if set(report) != expected_report_keys:
        raise SatelliteCalibrationRerunError("change report schema is invalid")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION or report.get(
        "algorithm_version"
    ) != TARGET_ALGORITHM:
        raise SatelliteCalibrationRerunError("change report version mismatch")
    if report.get("entity") != spec.get("entity") or report.get(
        "aoi_bbox_wgs84"
    ) != spec.get("aoi_bbox_wgs84"):
        raise SatelliteCalibrationRerunError("change report entity or AOI mismatch")
    baseline, current = _selected_features(
        spec, project_root, snapshot_dir=snapshot_dir
    )
    if report.get("baseline") != item_summary(baseline) or report.get(
        "current"
    ) != item_summary(current):
        raise SatelliteCalibrationRerunError("change report STAC lineage mismatch")
    if report.get("source") != report_source(baseline, current):
        raise SatelliteCalibrationRerunError("change report source mismatch")
    if report.get("classification") != REPORT_CLASSIFICATION:
        raise SatelliteCalibrationRerunError("change report lost no-inference scope")
    if report.get("radiometry") != {
        "reflectance": "STAC raster scale and offset applied per scene and band",
        "normalized_index_negative_reflectance_policy": "clip_to_zero",
    }:
        raise SatelliteCalibrationRerunError("change report radiometry mismatch")
    _validate_thresholds(report.get("thresholds"))
    metrics = _report_metrics(report.get("metrics"))
    outputs = report.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != REPORT_BOUND_FILES:
        raise SatelliteCalibrationRerunError("change report output inventory mismatch")
    for name in sorted(REPORT_BOUND_FILES):
        record = outputs[name]
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise SatelliteCalibrationRerunError(f"change output {name} record is invalid")
        if dict(record) != _checkpoint(path / name):
            raise SatelliteCalibrationRerunError(f"change output {name} checkpoint mismatch")
    grid = report.get("grid")
    if not isinstance(grid, Mapping) or set(grid) != {
        "crs",
        "width",
        "height",
        "pixel_area_m2",
        "clear_scl_classes",
    }:
        raise SatelliteCalibrationRerunError("change report grid schema is invalid")
    width = _positive_integer(grid.get("width"), "grid width")
    height = _positive_integer(grid.get("height"), "grid height")
    _positive_number(grid.get("pixel_area_m2"), "grid pixel area")
    if not isinstance(grid.get("crs"), str) or not grid["crs"] or grid.get(
        "clear_scl_classes"
    ) != sorted(CLEAR_SCL_CLASSES):
        raise SatelliteCalibrationRerunError("change report grid values are invalid")
    for name in ("before.png", "after.png", "change-overlay.png"):
        if _png_dimensions(path / name, name) != (width, height):
            raise SatelliteCalibrationRerunError(f"{name} dimensions mismatch")
    if _png_dimensions(path / "comparison.png", "comparison.png") != (
        width * 3,
        height,
    ):
        raise SatelliteCalibrationRerunError("comparison.png dimensions mismatch")
    minimum_area = _positive_number(
        spec["processor"]["minimum_component_area_m2"], "minimum component area"
    )
    _validate_geojson(
        path / "change-proposals.geojson",
        expected_count=metrics["proposal_component_count"],
        expected_area_m2=float(metrics["proposal_area_m2_after_component_filter"]),
        minimum_component_area_m2=minimum_area,
        aoi_bbox=parse_bbox(spec["aoi_bbox_wgs84"]),
    )
    return {
        "artifacts": {
            name: _checkpoint(path / name) for name in sorted(EXPECTED_CHANGE_FILES)
        },
        "report": report,
    }


def _validate_configuration(value: Any, spec_count: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != CONFIGURATION_KEYS:
        raise SatelliteCalibrationRerunError("rerun configuration schema is invalid")
    result = dict(value)
    start = result["start_index"]
    maximum = result["max_jobs"]
    attempts = result["max_attempts"]
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise SatelliteCalibrationRerunError("rerun start index is invalid")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        raise SatelliteCalibrationRerunError("rerun max jobs is invalid")
    if start + maximum > spec_count:
        raise SatelliteCalibrationRerunError("rerun shard exceeds the spec inventory")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 5:
        raise SatelliteCalibrationRerunError("rerun max attempts is invalid")
    if _finite_number(result["timeout_seconds"], "timeout seconds") <= 0:
        raise SatelliteCalibrationRerunError("timeout must be positive")
    if _finite_number(result["minimum_interval_seconds"], "minimum interval") < 0:
        raise SatelliteCalibrationRerunError("minimum interval must be non-negative")
    return result


def _validate_failure(value: Any, configuration: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise SatelliteCalibrationRerunError("failed rerun evidence is invalid")
    kind = value.get("kind")
    if kind == "timeout":
        if set(value) != {"kind", "timeout_seconds"} or value.get(
            "timeout_seconds"
        ) != configuration["timeout_seconds"]:
            raise SatelliteCalibrationRerunError("timeout failure schema is invalid")
    elif kind == "process_exit":
        if set(value) != {"kind", "returncode", "stderr_tail"}:
            raise SatelliteCalibrationRerunError("process failure schema is invalid")
        returncode = value.get("returncode")
        stderr = value.get("stderr_tail")
        if isinstance(returncode, bool) or not isinstance(returncode, int) or returncode == 0:
            raise SatelliteCalibrationRerunError("process failure return code is invalid")
        if not isinstance(stderr, str) or len(stderr) > 4_000:
            raise SatelliteCalibrationRerunError("process failure stderr is invalid")
    elif kind == "invalid_output":
        if set(value) != {"kind", "message"} or not isinstance(
            value.get("message"), str
        ) or not value["message"]:
            raise SatelliteCalibrationRerunError("output failure schema is invalid")
    else:
        raise SatelliteCalibrationRerunError("rerun failure kind is invalid")


def validate_satellite_calibration_rerun_output(
    preparation_dir: Path, output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    """Validate one immutable numerical shard entirely offline."""

    definition_path = _normalize(definition_path, "definition")
    preparation_dir = _normalize(preparation_dir, "preparation")
    output_dir = _normalize(output_dir, "output")
    expected_input_validation = validate_satellite_calibration_rerun_inputs(
        preparation_dir, definition_path=definition_path
    )
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise SatelliteCalibrationRerunError("rerun output is not a regular directory")
    if output_dir.stat().st_mode & 0o777 != 0o555:
        raise SatelliteCalibrationRerunError("rerun output directory mode must be 0555")
    manifest_path = output_dir / "batch-manifest.json"
    sidecar_path = output_dir / "manifest.sha256"
    if not manifest_path.is_file() or not sidecar_path.is_file():
        raise SatelliteCalibrationRerunError("rerun manifest or sidecar is missing")
    manifest_raw = manifest_path.read_bytes()
    manifest = _json(manifest_path, "rerun manifest")
    if manifest_raw != _canonical_json(manifest):
        raise SatelliteCalibrationRerunError("rerun manifest is not canonical")
    if sidecar_path.read_bytes() != (
        f"{_sha256(manifest_raw)}  batch-manifest.json\n".encode("ascii")
    ):
        raise SatelliteCalibrationRerunError("rerun manifest sidecar mismatch")
    _reject_forbidden_keys(manifest, "rerun manifest")
    if set(manifest) != MANIFEST_KEYS:
        raise SatelliteCalibrationRerunError("rerun manifest top-level schema is invalid")
    if manifest["format"] != OUTPUT_FORMAT or manifest["schema_version"] != 1:
        raise SatelliteCalibrationRerunError("rerun output format is unsupported")
    if manifest["input_validation"] != expected_input_validation:
        raise SatelliteCalibrationRerunError("rerun preparation binding mismatch")
    runtime = manifest["runtime"]
    _require_pinned_runtime(runtime)
    if runtime != expected_input_validation["runtime"]:
        raise SatelliteCalibrationRerunError("rerun runtime binding mismatch")
    _assert_runtime(runtime)
    project_root = _definition_project_root(definition_path)
    expected_preparation = str(preparation_dir.relative_to(project_root))
    if manifest["preparation_dir"] != expected_preparation:
        raise SatelliteCalibrationRerunError("rerun preparation path mismatch")
    specs = _specs(preparation_dir / "rerun-specs.jsonl")
    configuration = _validate_configuration(manifest["configuration"], len(specs))
    selected = specs[
        configuration["start_index"] : configuration["start_index"]
        + configuration["max_jobs"]
    ]
    if manifest["processor"] != selected[0]["processor"]:
        raise SatelliteCalibrationRerunError("rerun processor binding mismatch")
    if manifest["scope"] != SCOPE:
        raise SatelliteCalibrationRerunError("rerun scope is invalid")
    runtime_dir = output_dir / "processor_runtime"
    _verify_runtime_snapshot(runtime_dir, manifest["processor"])
    jobs = manifest["jobs"]
    if not isinstance(jobs, Mapping) or set(jobs) != {
        spec["blind_item_id"] for spec in selected
    }:
        raise SatelliteCalibrationRerunError("rerun job set mismatch")
    expected_files = {"batch-manifest.json", "manifest.sha256"}
    expected_directories = {"jobs", "processor_runtime"}
    for descriptor in manifest["processor"]["files"].values():
        relative = Path("processor_runtime") / descriptor["path"]
        expected_files.add(relative.as_posix())
        for parent in relative.parents:
            if parent.as_posix() != ".":
                expected_directories.add(parent.as_posix())
    state_counts: Counter[str] = Counter()
    for spec in selected:
        blind_id = spec["blind_item_id"]
        job = jobs[blind_id]
        if not isinstance(job, Mapping) or set(job) != JOB_KEYS:
            raise SatelliteCalibrationRerunError("rerun job schema is invalid")
        expected_job_binding = {
            "blind_item_id": blind_id,
            "historical_identity_sha256": spec["historical_identity_sha256"],
            "historical_queue_id": spec["historical_queue_id"],
            "rerun_spec_sha256": _sha256(_canonical_line(spec)),
        }
        if any(job[key] != value for key, value in expected_job_binding.items()):
            raise SatelliteCalibrationRerunError("rerun job/spec binding mismatch")
        attempts = job["attempts"]
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not (
            1 <= attempts <= configuration["max_attempts"]
        ):
            raise SatelliteCalibrationRerunError("rerun attempt count is invalid")
        state = job["state"]
        state_counts[state] += 1
        change_dir = output_dir / "jobs" / blind_id / "change"
        if state == "completed":
            if job["failure"] is not None:
                raise SatelliteCalibrationRerunError("completed rerun retains a failure")
            validated = _validated_change_output(change_dir, spec, project_root)
            if job["artifacts"] != validated["artifacts"]:
                raise SatelliteCalibrationRerunError("rerun artifact manifest mismatch")
            expected_directories.update({f"jobs/{blind_id}", f"jobs/{blind_id}/change"})
            expected_files.update(
                f"jobs/{blind_id}/change/{name}" for name in EXPECTED_CHANGE_FILES
            )
        elif state == "failed":
            if job["artifacts"] is not None:
                raise SatelliteCalibrationRerunError("failed rerun has artifacts")
            _validate_failure(job["failure"], configuration)
            if change_dir.exists() or change_dir.is_symlink():
                raise SatelliteCalibrationRerunError("failed rerun published artifacts")
        else:
            raise SatelliteCalibrationRerunError("rerun job state is invalid")
    expected_summary = {
        "jobs_completed": state_counts.get("completed", 0),
        "jobs_failed": state_counts.get("failed", 0),
        "jobs_selected": len(selected),
    }
    if manifest["summary"] != expected_summary or set(manifest["summary"]) != set(
        expected_summary
    ):
        raise SatelliteCalibrationRerunError("rerun summary mismatch")
    expected_state = (
        "completed" if expected_summary["jobs_failed"] == 0 else "completed_with_failures"
    )
    if manifest["state"] != expected_state:
        raise SatelliteCalibrationRerunError("rerun batch state mismatch")
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise SatelliteCalibrationRerunError("rerun output contains a symlink")
        relative = path.relative_to(output_dir).as_posix()
        if path.is_dir():
            actual_directories.add(relative)
            if path.stat().st_mode & 0o777 != 0o555:
                raise SatelliteCalibrationRerunError(
                    f"rerun directory mode mismatch: {relative}"
                )
        elif path.is_file():
            actual_files.add(relative)
            if path.stat().st_mode & 0o777 != 0o444:
                raise SatelliteCalibrationRerunError(
                    f"rerun file mode mismatch: {relative}"
                )
        else:
            raise SatelliteCalibrationRerunError("rerun output has a special file")
    if actual_files != expected_files or actual_directories != expected_directories:
        raise SatelliteCalibrationRerunError("rerun output tree is not closed")
    return manifest


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        _fsync_path(path)
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_path(path)


def _freeze_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)
    for path in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _cleanup_staging(staging: Path) -> None:
    if not staging.exists():
        return
    for path in staging.rglob("*"):
        try:
            os.chmod(path, 0o755 if path.is_dir() else 0o644)
        except OSError:
            pass
    os.chmod(staging, 0o755)
    shutil.rmtree(staging)


def execute_satellite_calibration_reruns(
    preparation_dir: Path,
    output_dir: Path,
    *,
    definition_path: Path,
    start_index: int = 0,
    max_jobs: int = 1,
    max_attempts: int = 2,
    timeout_seconds: float = 1800.0,
    minimum_interval_seconds: float = 1.1,
) -> dict[str, Any]:
    """Execute one bounded shard and publish only after offline validation."""

    definition_path = _normalize(definition_path, "definition")
    preparation_dir = _normalize(preparation_dir, "preparation")
    output_dir = _normalize(output_dir, "output")
    validation = validate_satellite_calibration_rerun_inputs(
        preparation_dir, definition_path=definition_path
    )
    specs = _specs(preparation_dir / "rerun-specs.jsonl")
    configuration = _validate_configuration(
        {
            "max_attempts": max_attempts,
            "max_jobs": max_jobs,
            "minimum_interval_seconds": minimum_interval_seconds,
            "start_index": start_index,
            "timeout_seconds": timeout_seconds,
        },
        len(specs),
    )
    selected = specs[start_index : start_index + max_jobs]
    runtime = validation["runtime"]
    _require_pinned_runtime(runtime)
    if output_dir.exists() or output_dir.is_symlink():
        raise SatelliteCalibrationRerunError("output already exists")
    project_root = _definition_project_root(definition_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    jobs_dir = staging / "jobs"
    attempts_dir = staging / ".attempts"
    runtime_dir = staging / "processor_runtime"
    jobs_dir.mkdir()
    attempts_dir.mkdir()
    runtime_dir.mkdir()
    jobs: dict[str, Any] = {}
    last_started: float | None = None
    try:
        for descriptor in selected[0]["processor"]["files"].values():
            source = _project_path(project_root, descriptor["path"], "processor runtime")
            destination = runtime_dir / descriptor["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            _verify_file(destination, descriptor, "processor runtime snapshot")
        for spec in selected:
            blind_id = spec["blind_item_id"]
            _assert_runtime(runtime)
            _revalidate_spec_inputs(project_root, spec)
            _verify_runtime_snapshot(runtime_dir, spec["processor"])
            job_result: dict[str, Any] = {
                "artifacts": None,
                "attempts": 0,
                "blind_item_id": blind_id,
                "failure": None,
                "historical_identity_sha256": spec["historical_identity_sha256"],
                "historical_queue_id": spec["historical_queue_id"],
                "rerun_spec_sha256": _sha256(_canonical_line(spec)),
                "state": "failed",
            }
            input_snapshot_dir = attempts_dir / f"{blind_id}-inputs"
            input_snapshot_dir.mkdir()
            substitutions: dict[str, str] = {}
            for name, descriptor in spec["source_catalog_artifacts"].items():
                source = _project_path(project_root, descriptor["path"], name)
                destination = input_snapshot_dir / name
                shutil.copyfile(source, destination)
                _verify_file(destination, descriptor, f"{name} execution snapshot")
                substitutions[descriptor["path"]] = str(destination)
            for attempt in range(1, max_attempts + 1):
                if last_started is not None:
                    remaining = minimum_interval_seconds - (time.monotonic() - last_started)
                    if remaining > 0:
                        time.sleep(remaining)
                _assert_runtime(runtime)
                _revalidate_spec_inputs(project_root, spec)
                _verify_runtime_snapshot(runtime_dir, spec["processor"])
                attempt_output = attempts_dir / f"{blind_id}-{attempt}"
                arguments = [
                    (
                        str(attempt_output)
                        if value == "{job_output_dir}"
                        else substitutions.get(value, value)
                    )
                    for value in spec["execution"]["arguments"]
                ]
                command = [
                    sys.executable,
                    "-B",
                    str(runtime_dir / spec["execution"]["script"]),
                    *arguments,
                ]
                environment = os.environ.copy()
                environment["PYTHONDONTWRITEBYTECODE"] = "1"
                last_started = time.monotonic()
                job_result["attempts"] = attempt
                try:
                    result = subprocess.run(
                        command,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                        env=environment,
                    )
                except subprocess.TimeoutExpired:
                    job_result["failure"] = {
                        "kind": "timeout",
                        "timeout_seconds": timeout_seconds,
                    }
                    if attempt_output.exists():
                        shutil.rmtree(attempt_output)
                    continue
                if result.returncode != 0:
                    stderr = result.stderr if isinstance(result.stderr, str) else ""
                    job_result["failure"] = {
                        "kind": "process_exit",
                        "returncode": result.returncode,
                        "stderr_tail": stderr[-4_000:],
                    }
                    if attempt_output.exists():
                        shutil.rmtree(attempt_output)
                    continue
                try:
                    validated = _validated_change_output(
                        attempt_output,
                        spec,
                        project_root,
                        snapshot_dir=input_snapshot_dir,
                    )
                except SatelliteCalibrationRerunError as error:
                    job_result["failure"] = {
                        "kind": "invalid_output",
                        "message": str(error),
                    }
                    if attempt_output.exists():
                        shutil.rmtree(attempt_output)
                    continue
                destination = jobs_dir / blind_id / "change"
                destination.parent.mkdir()
                os.replace(attempt_output, destination)
                job_result.update(
                    {
                        "artifacts": validated["artifacts"],
                        "failure": None,
                        "state": "completed",
                    }
                )
                break
            shutil.rmtree(input_snapshot_dir)
            jobs[blind_id] = job_result
        shutil.rmtree(attempts_dir)
        for spec in selected:
            _revalidate_spec_inputs(project_root, spec)
        _verify_runtime_snapshot(runtime_dir, selected[0]["processor"])
        _assert_runtime(runtime)
        state_counts = Counter(job["state"] for job in jobs.values())
        manifest = {
            "configuration": configuration,
            "format": OUTPUT_FORMAT,
            "input_validation": validation,
            "jobs": jobs,
            "preparation_dir": str(preparation_dir.relative_to(project_root)),
            "processor": selected[0]["processor"],
            "runtime": runtime,
            "schema_version": 1,
            "scope": SCOPE,
            "state": (
                "completed"
                if state_counts.get("failed", 0) == 0
                else "completed_with_failures"
            ),
            "summary": {
                "jobs_completed": state_counts.get("completed", 0),
                "jobs_failed": state_counts.get("failed", 0),
                "jobs_selected": len(selected),
            },
        }
        _reject_forbidden_keys(manifest, "rerun manifest")
        manifest_raw = _canonical_json(manifest)
        (staging / "batch-manifest.json").write_bytes(manifest_raw)
        (staging / "manifest.sha256").write_text(
            f"{_sha256(manifest_raw)}  batch-manifest.json\n", encoding="ascii"
        )
        _fsync_tree(staging)
        _freeze_tree(staging)
        _fsync_tree(staging)
        validated_manifest = validate_satellite_calibration_rerun_output(
            preparation_dir, staging, definition_path=definition_path
        )
        if output_dir.exists() or output_dir.is_symlink():
            raise SatelliteCalibrationRerunError("output appeared before publication")
        os.replace(staging, output_dir)
        _fsync_path(output_dir.parent)
        return validated_manifest
    except Exception:
        _cleanup_staging(staging)
        raise
