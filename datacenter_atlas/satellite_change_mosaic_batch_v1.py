"""Atomic runner for the six frozen v57 multi-tile change jobs.

This versioned runner accepts only the closed ``multi_tile_ready`` partition
from the accepted v57 preparation.  It executes the exact prepared arguments
with ``scripts/sentinel_change_mosaic.py`` and substitutes only the per-job
staging directory.  Outputs remain review proposals: the runner creates no
atlas, identity, lifecycle, operating-status, type, capacity, power, energy,
PUE, workload, construction-truth, or unique-site claim.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import errno
import fcntl
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import struct
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import zlib

from .satellite_batch import validate_satellite_batch
from .satellite_change import CLEAR_SCL_CLASSES, item_summary, parse_bbox, report_source
from .satellite_change_mosaic import (
    ALGORITHM_VERSION,
    MAX_COMPANION_TIME_DELTA_SECONDS,
    REPORT_SCHEMA_VERSION,
    SPECTRAL_CORE_ALGORITHM_VERSION,
    SentinelMosaicContractError,
    parse_item_binding,
    select_bound_items,
)
from .satellite_change_preparation_v1 import (
    PREPARATION_ID,
    SatelliteChangePreparationV1Error,
    validate_satellite_change_preparation_v1,
)
from .satellite_queue import validate_queue_bundle
from scripts.sentinel_change_mosaic import (
    GEOJSON_COLLECTION_PROPERTIES,
    REPORT_CLASSIFICATION,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PREPARATION_DEFINITION_PATH = Path(
    "sources/satellite-change-preparation-2026-07-20-open-seed-v57-active-v1.json"
)
PREPARATION_DIRECTORY_PATH = Path(
    "satellite_change_preparation/2026-07-20-open-seed-v57-active-v1"
)
DEFAULT_OUTPUT_PATH = Path(
    "satellite_change_runs/"
    "2026-07-20-open-seed-v57-active-multi-tile-v1-001"
)
PREPARATION_MANIFEST_FILENAME = "manifest.json"
READY_FILENAME = "multi-tile-ready.jsonl"
BATCH_MANIFEST_FILENAME = "batch-manifest.json"
BATCH_SCHEMA_VERSION = 1
BATCH_PIPELINE = "satellite_review_change_mosaic_batch_v1"
DEFAULT_TIMEOUT_SECONDS = 1_800.0
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1
PREPARATION_DEFINITION_SHA256 = (
    "9700380bf1e45110d4b4efa8538ce3bc98793a79343ddfca018fc73ef962f8d8"
)
PREPARATION_MANIFEST_SHA256 = (
    "84073fc695a3ef500bd11d5077935083a7869cd4adb30db5342f6c0e215011ff"
)
PREPARATION_TREE_SHA256 = (
    "6ba201e2c634a98816fdca5d6cdef2f18b2d04a516a38d3d76370fbb74cd72b6"
)
READY_SHA256 = "5d9745f40fd495d129f08e8acd8a1dba76dd10ba6a800ec05dde33d0bcdd5ef1"
EXPECTED_QUEUE_IDS = (
    "satq-54c6402eb93d14f1ea754e66",
    "satq-cef871428da247c3ecfadec6",
    "satq-96fca962064e09f0dbafa93b",
    "satq-78500568b1f6227789ae36f4",
    "satq-fb6b6f815dad079c059cf412",
    "satq-0ffe3647dc32ee25ef77eab7",
)
EXPECTED_QUEUE_POSITIONS = (3, 13, 30, 38, 46, 87)
OUTPUT_FILES = frozenset(
    {
        "before.png",
        "after.png",
        "change-overlay.png",
        "comparison.png",
        "change-proposals.geojson",
        "report.json",
    }
)
REPORT_BOUND_FILES = OUTPUT_FILES - {"report.json"}
PROCESSOR_FILES = (
    "datacenter_atlas/satellite_change_mosaic_batch_v1.py",
    "datacenter_atlas/satellite_change_mosaic.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/models.py",
    "scripts/sentinel_change_mosaic.py",
)
SCOPE = {
    "mode": "visible_change_proposals_only",
    "review_required": True,
    "preparation_partition": "multi_tile_ready",
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_construction_status_inference": False,
    "imagery_construction_truth_inference": False,
    "imagery_operator_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_it_capacity_inference": False,
    "imagery_power_inference": False,
    "imagery_energy_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "unique_site_claim_created": False,
}
AOI_EDGE_TOLERANCE_METERS = 25.0


class SatelliteChangeMosaicBatchV1Error(ValueError):
    """Raised when lineage, checkpoint state, execution, or outputs drift."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256(raw)


def _canonical_jsonl_row(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SatelliteChangeMosaicBatchV1Error(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} is not valid JSON"
        ) from error


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SatelliteChangeMosaicBatchV1Error(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeMosaicBatchV1Error(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must be finite and positive"
        )
    return result


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeMosaicBatchV1Error(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must be finite and non-negative"
        )
    return result


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeMosaicBatchV1Error(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SatelliteChangeMosaicBatchV1Error(f"{field} must be finite")
    return result


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must be a non-empty RFC 3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _absolute_directory(path: str | Path, label: str, *, must_exist: bool) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate.is_symlink():
        raise SatelliteChangeMosaicBatchV1Error(f"{label} may not be a symlink")
    if must_exist and not candidate.is_dir():
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} is not a regular directory: {candidate}"
        )
    return candidate


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must be a safe POSIX relative path"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must be a safe POSIX relative path"
        )
    return pure.parts


def _safe_child(root: Path, relative: Any, label: str) -> Path:
    parts = _relative_parts(relative, label)
    candidate = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise SatelliteChangeMosaicBatchV1Error(f"{label} escapes its root")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} traverses a symlink: {current}"
            )
    return candidate


def _regular_file(root: Path, relative: Any, label: str) -> Path:
    path = _safe_child(root, relative, label)
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} is not a regular file: {path}"
        )
    return path


def _relative_to_package(path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(PACKAGE_ROOT.resolve()).as_posix()
    except ValueError as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must be inside the package root"
        ) from error


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeMosaicBatchV1Error(
            f"closed tree is not a regular directory: {root}"
        )
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"closed tree contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            directories += 1
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            files += 1
            file_bytes += len(raw)
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode()
            )
        else:
            raise SatelliteChangeMosaicBatchV1Error(
                f"closed tree contains an unsupported entry: {relative}"
            )
    return {
        "directories": directories,
        "files": files,
        "file_bytes": file_bytes,
        "inventory_sha256": digest.hexdigest(),
    }


@dataclass(frozen=True, slots=True)
class MosaicBatchConfig:
    """Configuration frozen by the first checkpoint; max_jobs is per invocation."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS
    max_job_attempts: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _positive_number(self.timeout_seconds, "timeout_seconds"),
        )
        object.__setattr__(
            self,
            "minimum_interval_seconds",
            _nonnegative_number(
                self.minimum_interval_seconds, "minimum_interval_seconds"
            ),
        )
        object.__setattr__(
            self,
            "max_job_attempts",
            _positive_integer(self.max_job_attempts, "max_job_attempts"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "visible_change_proposals_only",
            "timeout_seconds": self.timeout_seconds,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "max_job_attempts": self.max_job_attempts,
        }


def _config_from_document(value: Any) -> MosaicBatchConfig:
    if not isinstance(value, Mapping) or set(value) != {
        "mode",
        "timeout_seconds",
        "minimum_interval_seconds",
        "max_job_attempts",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch configuration schema is invalid"
        )
    if value.get("mode") != "visible_change_proposals_only":
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch configuration mode is invalid"
        )
    config = MosaicBatchConfig(
        timeout_seconds=value.get("timeout_seconds"),
        minimum_interval_seconds=value.get("minimum_interval_seconds"),
        max_job_attempts=value.get("max_job_attempts"),
    )
    if dict(value) != config.as_dict():
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch configuration is not canonical"
        )
    return config


def _runtime_lineage() -> dict[str, Any]:
    packages: dict[str, Any] = {}
    for import_name, distribution in (
        ("numpy", "numpy"),
        ("PIL", "Pillow"),
        ("rasterio", "rasterio"),
    ):
        try:
            package_version: str | None = distribution_version(distribution)
        except PackageNotFoundError:
            package_version = None
        packages[import_name] = {
            "distribution": distribution,
            "version": package_version,
        }
    geospatial_runtime: dict[str, str | None] = {"gdal": None, "proj": None}
    if packages["rasterio"]["version"] is not None:
        try:
            import rasterio
        except (ImportError, OSError):
            pass
        else:
            geospatial_runtime = {
                "gdal": getattr(rasterio, "__gdal_version__", None),
                "proj": getattr(rasterio, "__proj_version__", None),
            }
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": sys.implementation.cache_tag,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
            "descriptor": platform.platform(),
        },
        "zlib": {
            "compile_version": zlib.ZLIB_VERSION,
            "runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        },
        "geospatial_runtime": geospatial_runtime,
        "packages": packages,
        "required_packages_available": all(
            value["version"] is not None for value in packages.values()
        ),
    }


def _processor_lineage() -> dict[str, Any]:
    files: dict[str, Any] = {}
    for relative in PROCESSOR_FILES:
        path = _regular_file(PACKAGE_ROOT, relative, f"processor {relative}")
        files[relative] = _file_record(path)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
        "cli": "scripts/sentinel_change_mosaic.py",
        "files": files,
        "runtime": _runtime_lineage(),
    }


def _read_jsonl(path: Path, label: str) -> tuple[dict[str, Any], ...]:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must be non-empty newline-terminated JSONL"
        )
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        value = _decode_json(line, f"{label} line {line_number}")
        if not isinstance(value, dict) or _canonical_jsonl_row(value) != line:
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} line {line_number} is not canonical compact JSON"
            )
        rows.append(value)
    return tuple(rows)


def _argument_pairs(arguments: Any, label: str) -> list[tuple[str, str]]:
    if not isinstance(arguments, list) or not arguments or len(arguments) % 2:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must contain flag/value pairs"
        )
    pairs: list[tuple[str, str]] = []
    for index in range(0, len(arguments), 2):
        flag, value = arguments[index : index + 2]
        if (
            not isinstance(flag, str)
            or not flag.startswith("--")
            or not isinstance(value, str)
            or not value
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} contains an invalid flag/value pair"
            )
        pairs.append((flag, value))
    return pairs


def _validate_arguments(row: Mapping[str, Any]) -> None:
    queue_id = str(row.get("queue_id"))
    execution = row.get("execution")
    if not isinstance(execution, Mapping) or set(execution) != {
        "arguments",
        "cli",
        "runtime",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared execution schema changed for {queue_id}"
        )
    if execution.get("cli") != "scripts/sentinel_change_mosaic.py":
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared CLI changed for {queue_id}"
        )
    pairs = _argument_pairs(
        execution.get("arguments"), f"{queue_id} prepared arguments"
    )
    flags = [flag for flag, _ in pairs]
    expected = [
        "--baseline-stac",
        "--baseline-stac-sha256",
        "--baseline-primary",
        "--baseline-companion",
        "--current-stac",
        "--current-stac-sha256",
        "--current-primary",
        "--current-companion",
        "--bbox",
        "--entity-id",
        "--entity-name",
        "--output-dir",
        "--minimum-component-area-m2",
    ]
    if flags != expected:
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared argument order or inventory changed for {queue_id}"
        )
    values = {flag: value for flag, value in pairs}
    if values["--output-dir"] != "{job_output_dir}":
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared output placeholder changed for {queue_id}"
        )
    entity = row.get("entity")
    if not isinstance(entity, Mapping) or (
        values["--entity-id"] != entity.get("id")
        or values["--entity-name"] != entity.get("name")
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared entity arguments changed for {queue_id}"
        )
    if list(parse_bbox(values["--bbox"])) != row.get("aoi_bbox_wgs84"):
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared AOI arguments changed for {queue_id}"
        )
    if _positive_number(
        float(values["--minimum-component-area-m2"]),
        f"{queue_id} minimum component area",
    ) != 5_000.0:
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared component threshold changed for {queue_id}"
        )
    for flag in ("--baseline-stac", "--current-stac"):
        path = _regular_file(PACKAGE_ROOT, values[flag], f"{queue_id} {flag}")
        hash_flag = flag + "-sha256"
        if _file_record(path)["sha256"] != values[hash_flag]:
            raise SatelliteChangeMosaicBatchV1Error(
                f"prepared STAC hash changed for {queue_id}/{flag}"
            )
    for flag in (
        "--baseline-primary",
        "--baseline-companion",
        "--current-primary",
        "--current-companion",
    ):
        try:
            parse_item_binding(values[flag])
        except SentinelMosaicContractError as error:
            raise SatelliteChangeMosaicBatchV1Error(
                f"prepared item binding changed for {queue_id}/{flag}: {error}"
            ) from error
    runtime = execution.get("runtime")
    expected_runtime = {
        "python": platform.python_version(),
        "numpy": _runtime_lineage()["packages"]["numpy"]["version"],
        "pillow": _runtime_lineage()["packages"]["PIL"]["version"],
        "rasterio": _runtime_lineage()["packages"]["rasterio"]["version"],
        "gdal": _runtime_lineage()["geospatial_runtime"]["gdal"],
        "proj": _runtime_lineage()["geospatial_runtime"]["proj"],
    }
    if runtime != expected_runtime:
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared numerical runtime differs for {queue_id}"
        )


@dataclass(frozen=True, slots=True)
class _Inputs:
    preparation: Path
    definition: Path
    manifest: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    rows_by_id: Mapping[str, Mapping[str, Any]]
    lineage: Mapping[str, Any]
    upstream: Mapping[str, Any]


def _validate_upstream(manifest: Mapping[str, Any]) -> dict[str, Any]:
    sources = manifest.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != {
        "catalog_batch",
        "catalog_lock",
        "queue_bundle",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            "preparation upstream schema changed"
        )
    queue_relative = sources["queue_bundle"].get("directory")
    catalog_relative = sources["catalog_batch"].get("directory")
    queue = _safe_child(PACKAGE_ROOT, queue_relative, "upstream queue directory")
    catalog = _safe_child(
        PACKAGE_ROOT, catalog_relative, "upstream catalog directory"
    )
    try:
        queue_manifest = validate_queue_bundle(queue)
        catalog_manifest = validate_satellite_batch(queue, catalog)
    except Exception as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"upstream queue/catalog offline validation failed: {error}"
        ) from error
    queue_tree = _tree_inventory(queue)
    catalog_tree = _tree_inventory(catalog)
    if queue_tree != sources["queue_bundle"].get("closed_tree"):
        raise SatelliteChangeMosaicBatchV1Error("upstream queue tree changed")
    if catalog_tree != sources["catalog_batch"].get("closed_tree"):
        raise SatelliteChangeMosaicBatchV1Error("upstream catalog tree changed")
    queue_manifest_path = queue / "manifest.json"
    queue_file = queue / "satellite-review-queue.jsonl"
    catalog_manifest_path = catalog / "batch-manifest.json"
    return {
        "queue_bundle": {
            "directory": queue_relative,
            "closed_tree": queue_tree,
            "manifest": _file_record(queue_manifest_path),
            "queue": _file_record(queue_file),
            "pipeline": queue_manifest["pipeline"],
            "queue_jobs": queue_manifest["counts"]["queue_jobs"],
        },
        "catalog_batch": {
            "directory": catalog_relative,
            "closed_tree": catalog_tree,
            "manifest": _file_record(catalog_manifest_path),
            "pipeline": catalog_manifest["pipeline"],
            "state": catalog_manifest["state"],
            "jobs_selected": catalog_manifest["summary"]["jobs_selected"],
            "jobs_completed": catalog_manifest["summary"]["jobs_completed"],
            "jobs_unavailable_no_scene": catalog_manifest["summary"][
                "jobs_unavailable_no_scene"
            ],
        },
    }


def _validated_inputs(
    preparation_directory: str | Path,
    definition_path: str | Path,
) -> _Inputs:
    preparation = _absolute_directory(
        preparation_directory, "mosaic preparation", must_exist=True
    )
    definition = Path(os.path.abspath(os.fspath(definition_path)))
    if definition.is_symlink() or not definition.is_file():
        raise SatelliteChangeMosaicBatchV1Error(
            "preparation definition must be a regular file"
        )
    if _file_record(definition)["sha256"] != PREPARATION_DEFINITION_SHA256:
        raise SatelliteChangeMosaicBatchV1Error("preparation definition changed")
    try:
        manifest = validate_satellite_change_preparation_v1(
            preparation, definition_path=definition
        )
    except SatelliteChangePreparationV1Error as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"preparation failed offline validation: {error}"
        ) from error
    manifest_path = preparation / PREPARATION_MANIFEST_FILENAME
    ready_path = preparation / READY_FILENAME
    tree = _tree_inventory(preparation)
    if _file_record(manifest_path)["sha256"] != PREPARATION_MANIFEST_SHA256:
        raise SatelliteChangeMosaicBatchV1Error("preparation manifest changed")
    if _file_record(ready_path)["sha256"] != READY_SHA256:
        raise SatelliteChangeMosaicBatchV1Error("multi-tile-ready partition changed")
    if tree["inventory_sha256"] != PREPARATION_TREE_SHA256:
        raise SatelliteChangeMosaicBatchV1Error("preparation closed tree changed")
    if (
        manifest.get("preparation_id") != PREPARATION_ID
        or manifest.get("summary", {}).get("multi_tile_ready") != 6
        or manifest.get("processors", {}).get("multi_tile", {}).get(
            "algorithm_version"
        )
        != ALGORITHM_VERSION
    ):
        raise SatelliteChangeMosaicBatchV1Error("preparation identity changed")
    rows = _read_jsonl(ready_path, READY_FILENAME)
    queue_ids = tuple(row.get("queue_id") for row in rows)
    positions = tuple(row.get("queue_position") for row in rows)
    if queue_ids != EXPECTED_QUEUE_IDS or positions != EXPECTED_QUEUE_POSITIONS:
        raise SatelliteChangeMosaicBatchV1Error(
            "multi-tile-ready exact selection changed"
        )
    for row in rows:
        if (
            row.get("schema_version") != 1
            or row.get("state") != "multi_tile_ready"
            or row.get("preparation_only") is not True
            or row.get("raster_analysis_executed") is not False
            or row.get("network_requests") != 0
            or row.get("claim_constraints") != manifest.get("claim_constraints")
            or row.get("processor") != manifest["processors"]["multi_tile"]
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                f"prepared job contract changed for {row.get('queue_id')}"
            )
        _validate_arguments(row)
    upstream = _validate_upstream(manifest)
    lineage = {
        "preparation_id": PREPARATION_ID,
        "directory": _relative_to_package(preparation, "preparation directory"),
        "definition": {
            "path": _relative_to_package(definition, "preparation definition"),
            **_file_record(definition),
        },
        "manifest": {
            "path": (
                f"{_relative_to_package(preparation, 'preparation directory')}/"
                f"{PREPARATION_MANIFEST_FILENAME}"
            ),
            **_file_record(manifest_path),
        },
        "closed_tree": tree,
        "partition": {
            "file": READY_FILENAME,
            "records": len(rows),
            **_file_record(ready_path),
        },
    }
    return _Inputs(
        preparation=preparation,
        definition=definition,
        manifest=manifest,
        rows=rows,
        rows_by_id={str(row["queue_id"]): row for row in rows},
        lineage=lineage,
        upstream=upstream,
    )


def _expected_tasks(inputs: _Inputs) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for row in inputs.rows:
        queue_id = str(row["queue_id"])
        arguments = list(row["execution"]["arguments"])
        task = {
            "queue_id": queue_id,
            "queue_position": row["queue_position"],
            "prepared_row_sha256": _canonical_hash(row),
            "entity": {
                "id": row["entity"]["id"],
                "name": row["entity"]["name"],
            },
            "aoi_bbox_wgs84": list(row["aoi_bbox_wgs84"]),
            "catalog_artifacts": json.loads(json.dumps(row["catalog_artifacts"])),
            "execution": {
                "cli": row["execution"]["cli"],
                "arguments": arguments,
                "arguments_sha256": _canonical_hash(arguments),
                "runtime": dict(row["execution"]["runtime"]),
            },
            "output_directory": f"jobs/{queue_id}/change",
            "state": "pending",
            "attempts": 0,
            "last_attempt_started_at": None,
            "failures": [],
            "completed_at": None,
            "artifacts": None,
            "report": None,
        }
        tasks[queue_id] = task
    return tasks


def _selection(inputs: _Inputs) -> dict[str, Any]:
    selected = list(EXPECTED_QUEUE_IDS)
    return {
        "mode": "exact_prepared_partition",
        "partition": READY_FILENAME,
        "selected_queue_ids": selected,
        "selected_queue_ids_sha256": _canonical_hash(selected),
        "jobs_selected": len(selected),
        "processing_deduplicated": False,
    }


def _summary(document: Mapping[str, Any], config: MosaicBatchConfig) -> dict[str, int]:
    jobs = document["jobs"]
    counts = {
        state: sum(task.get("state") == state for task in jobs.values())
        for state in ("pending", "running", "failed", "completed")
    }
    return {
        "jobs_selected": len(jobs),
        "jobs_completed": counts["completed"],
        "jobs_failed": counts["failed"],
        "jobs_pending": counts["pending"],
        "jobs_running": counts["running"],
        "jobs_exhausted": sum(
            task.get("state") == "failed"
            and task.get("attempts") >= config.max_job_attempts
            for task in jobs.values()
        ),
        "output_artifacts": counts["completed"] * len(OUTPUT_FILES),
    }


def _update_document(
    document: dict[str, Any], config: MosaicBatchConfig, updated_at: str
) -> None:
    document["updated_at"] = updated_at
    document["summary"] = _summary(document, config)
    document["state"] = (
        "completed"
        if document["summary"]["jobs_completed"]
        == document["summary"]["jobs_selected"]
        else "incomplete"
    )


def _new_document(
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: MosaicBatchConfig,
    created_at: str,
) -> dict[str, Any]:
    document = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "pipeline": BATCH_PIPELINE,
        "state": "incomplete",
        "created_at": created_at,
        "updated_at": created_at,
        "preparation": dict(inputs.lineage),
        "upstream": json.loads(json.dumps(inputs.upstream)),
        "processor": dict(processor),
        "configuration": config.as_dict(),
        "selection": _selection(inputs),
        "scope": dict(SCOPE),
        "jobs": _expected_tasks(inputs),
        "summary": {},
        "runs": [],
    }
    _update_document(document, config, created_at)
    return document


def _write_checkpoint(
    output: Path,
    document: dict[str, Any],
    config: MosaicBatchConfig,
    updated_at: str,
) -> None:
    _update_document(document, config, updated_at)
    path = output / BATCH_MANIFEST_FILENAME
    temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
    if path.is_symlink():
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch manifest may not be a symlink"
        )
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteChangeMosaicBatchV1Error(
            "stale mosaic-batch checkpoint temporary exists"
        )
    with temporary.open("xb") as destination:
        destination.write(_canonical_json(document))
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)
    descriptor = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch manifest is not a regular file"
        )
    raw = path.read_bytes()
    document = _decode_json(raw, "mosaic-batch manifest")
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch manifest is not canonical JSON"
        )
    return document


def _failure(value: Any, queue_id: str, attempts: int) -> int:
    if not isinstance(value, Mapping) or set(value) != {
        "attempt",
        "at",
        "kind",
        "error",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"failure record is invalid for {queue_id}"
        )
    attempt = _positive_integer(value.get("attempt"), f"{queue_id} failure attempt")
    if attempt > attempts:
        raise SatelliteChangeMosaicBatchV1Error(
            f"failure attempt exceeds attempts for {queue_id}"
        )
    _timestamp(value.get("at"), f"{queue_id} failure timestamp")
    if value.get("kind") not in {
        "command_exit",
        "timeout",
        "output_validation",
        "execution_error",
        "interrupted",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"failure kind is invalid for {queue_id}"
        )
    if not isinstance(value.get("error"), str) or not value["error"]:
        raise SatelliteChangeMosaicBatchV1Error(
            f"failure error is invalid for {queue_id}"
        )
    if len(value["error"]) > 2_500:
        raise SatelliteChangeMosaicBatchV1Error(
            f"failure error is too long for {queue_id}"
        )
    return attempt


def _validate_runs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SatelliteChangeMosaicBatchV1Error("mosaic-batch runs must be an array")
    running = 0
    for index, run in enumerate(value, start=1):
        expected = {
            "run_number",
            "state",
            "started_at",
            "finished_at",
            "interruption_recorded_at",
            "max_jobs",
            "job_attempts",
            "jobs_completed",
            "jobs_failed",
            "jobs_interrupted",
            "jobs_recovered_after_publish",
            "budget_exhausted",
        }
        if not isinstance(run, dict) or set(run) != expected:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic run {index} schema is invalid"
            )
        if run.get("run_number") != index or run.get("state") not in {
            "running",
            "completed",
            "interrupted",
        }:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic run {index} identity is invalid"
            )
        _timestamp(run.get("started_at"), f"mosaic run {index} started_at")
        for field in (
            "max_jobs",
            "job_attempts",
            "jobs_completed",
            "jobs_failed",
            "jobs_interrupted",
            "jobs_recovered_after_publish",
        ):
            if field == "max_jobs":
                _positive_integer(run.get(field), f"mosaic run {index} {field}")
            else:
                _nonnegative_integer(run.get(field), f"mosaic run {index} {field}")
        if not isinstance(run.get("budget_exhausted"), bool):
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic run {index} budget flag is invalid"
            )
        if run["state"] == "running":
            running += 1
            if index != len(value) or any(
                run.get(field) is not None
                for field in ("finished_at", "interruption_recorded_at")
            ):
                raise SatelliteChangeMosaicBatchV1Error(
                    f"mosaic run {index} running state is invalid"
                )
        else:
            _timestamp(run.get("finished_at"), f"mosaic run {index} finished_at")
            if run["state"] == "interrupted":
                _timestamp(
                    run.get("interruption_recorded_at"),
                    f"mosaic run {index} interruption_recorded_at",
                )
            elif run.get("interruption_recorded_at") is not None:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"mosaic run {index} has an unexpected interruption timestamp"
                )
        if run["job_attempts"] > run["max_jobs"]:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic run {index} exceeded max_jobs"
            )
        outcomes = (
            run["jobs_completed"]
            + run["jobs_failed"]
            + run["jobs_interrupted"]
            + run["jobs_recovered_after_publish"]
        )
        expected_outcomes = (
            {run["job_attempts"], max(0, run["job_attempts"] - 1)}
            if run["state"] == "running"
            else {run["job_attempts"]}
        )
        if outcomes not in expected_outcomes:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic run {index} outcomes do not reconcile"
            )
    if running > 1:
        raise SatelliteChangeMosaicBatchV1Error(
            "multiple mosaic runs claim to be running"
        )
    return value


def _validate_checkpoint(
    document: Any,
    *,
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: MosaicBatchConfig,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "pipeline",
        "state",
        "created_at",
        "updated_at",
        "preparation",
        "upstream",
        "processor",
        "configuration",
        "selection",
        "scope",
        "jobs",
        "summary",
        "runs",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch manifest schema is invalid"
        )
    if (
        document.get("schema_version") != BATCH_SCHEMA_VERSION
        or document.get("pipeline") != BATCH_PIPELINE
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch manifest version collision"
        )
    if document.get("preparation") != dict(inputs.lineage):
        raise SatelliteChangeMosaicBatchV1Error("mosaic preparation lineage changed")
    if document.get("upstream") != inputs.upstream:
        raise SatelliteChangeMosaicBatchV1Error("mosaic upstream lineage changed")
    if document.get("processor") != dict(processor):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic processor code or runtime changed"
        )
    if document.get("configuration") != config.as_dict():
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch configuration changed"
        )
    if document.get("selection") != _selection(inputs):
        raise SatelliteChangeMosaicBatchV1Error("mosaic exact selection changed")
    if document.get("scope") != SCOPE:
        raise SatelliteChangeMosaicBatchV1Error("mosaic no-claims scope changed")
    _timestamp(document.get("created_at"), "mosaic-batch created_at")
    _timestamp(document.get("updated_at"), "mosaic-batch updated_at")
    jobs = document.get("jobs")
    expected_tasks = _expected_tasks(inputs)
    if not isinstance(jobs, dict) or set(jobs) != set(EXPECTED_QUEUE_IDS):
        raise SatelliteChangeMosaicBatchV1Error("mosaic task inventory changed")
    mutable = {
        "state",
        "attempts",
        "last_attempt_started_at",
        "failures",
        "completed_at",
        "artifacts",
        "report",
    }
    for queue_id, task in jobs.items():
        expected = expected_tasks[queue_id]
        if not isinstance(task, dict) or set(task) != set(expected):
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic task schema is invalid for {queue_id}"
            )
        for field in set(expected) - mutable:
            if task.get(field) != expected[field]:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"immutable mosaic task field {field} changed for {queue_id}"
                )
        state_value = task.get("state")
        if state_value not in {"pending", "running", "failed", "completed"}:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic task state is invalid for {queue_id}"
            )
        attempts = _nonnegative_integer(task.get("attempts"), f"{queue_id} attempts")
        if attempts > config.max_job_attempts:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic task exceeded attempt cap for {queue_id}"
            )
        failures = task.get("failures")
        if not isinstance(failures, list) or len(failures) > attempts:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic task failures are invalid for {queue_id}"
            )
        failure_attempts = [_failure(value, queue_id, attempts) for value in failures]
        expected_failures = {
            "pending": [],
            "running": list(range(1, attempts)),
            "failed": list(range(1, attempts + 1)),
            "completed": list(range(1, attempts)),
        }[state_value]
        if failure_attempts != expected_failures:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic attempt outcomes do not reconcile for {queue_id}"
            )
        if state_value == "pending":
            if attempts != 0 or task.get("last_attempt_started_at") is not None:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"pending mosaic task claims an attempt for {queue_id}"
                )
        else:
            if attempts == 0:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"non-pending mosaic task lacks an attempt for {queue_id}"
                )
            _timestamp(
                task.get("last_attempt_started_at"),
                f"{queue_id} last_attempt_started_at",
            )
        if state_value == "completed":
            _timestamp(task.get("completed_at"), f"{queue_id} completed_at")
            if not isinstance(task.get("artifacts"), dict) or not isinstance(
                task.get("report"), dict
            ):
                raise SatelliteChangeMosaicBatchV1Error(
                    f"completed mosaic task lacks provenance for {queue_id}"
                )
        elif any(
            task.get(field) is not None
            for field in ("completed_at", "artifacts", "report")
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                f"incomplete mosaic task claims output for {queue_id}"
            )
    runs = _validate_runs(document.get("runs"))
    if sum(run["job_attempts"] for run in runs) != sum(
        task["attempts"] for task in jobs.values()
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic run attempts do not reconcile with tasks"
        )
    all_failures = [failure for task in jobs.values() for failure in task["failures"]]
    interrupted = sum(failure["kind"] == "interrupted" for failure in all_failures)
    non_interrupted = len(all_failures) - interrupted
    if sum(run["jobs_interrupted"] for run in runs) != interrupted:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic interrupted outcomes do not reconcile"
        )
    if sum(run["jobs_failed"] for run in runs) != non_interrupted:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic failed outcomes do not reconcile"
        )
    completed = sum(task["state"] == "completed" for task in jobs.values())
    if sum(
        run["jobs_completed"] + run["jobs_recovered_after_publish"] for run in runs
    ) != completed:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic completed outcomes do not reconcile"
        )
    if document.get("summary") != _summary(document, config):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch summary does not reproduce"
        )
    expected_state = "completed" if completed == len(jobs) else "incomplete"
    if document.get("state") != expected_state:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch state does not match tasks"
        )
    return document


def _task_paths(output: Path, task: Mapping[str, Any]) -> tuple[Path, Path]:
    final = _safe_child(
        output,
        task["output_directory"],
        f"{task['queue_id']} output directory",
    )
    return final, final.with_name(f".{final.name}.staging")


def _clear_stage(stage: Path) -> None:
    if stage.is_symlink():
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic staging path may not be a symlink: {stage}"
        )
    if not stage.exists():
        return
    if not stage.is_dir():
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic staging path is not a directory: {stage}"
        )
    for path in stage.rglob("*"):
        if path.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic staging tree contains a symlink: {path}"
            )
    shutil.rmtree(stage)


def _prepare_parent(output: Path, final: Path) -> None:
    relative = final.relative_to(output)
    current = output
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic output parent may not be a symlink: {current}"
            )
        if current.exists() and not current.is_dir():
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic output parent is not a directory: {current}"
            )
        current.mkdir(exist_ok=True)


def _fsync_tree(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic staging output is not a closed file set: {path}"
            )
        with path.open("rb") as source:
            os.fsync(source.fileno())
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_input_bytes(inputs: _Inputs) -> None:
    manifest = inputs.preparation / PREPARATION_MANIFEST_FILENAME
    partition = inputs.preparation / READY_FILENAME
    expected = inputs.lineage
    if (
        _file_record(inputs.definition)
        != {key: expected["definition"][key] for key in ("bytes", "sha256")}
        or _file_record(manifest)
        != {key: expected["manifest"][key] for key in ("bytes", "sha256")}
        or _file_record(partition)
        != {key: expected["partition"][key] for key in ("bytes", "sha256")}
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic preparation bytes changed during execution"
        )
    for key, manifest_name in (
        ("queue_bundle", "manifest.json"),
        ("catalog_batch", "batch-manifest.json"),
    ):
        root = _safe_child(
            PACKAGE_ROOT,
            inputs.upstream[key]["directory"],
            f"upstream {key}",
        )
        if _file_record(root / manifest_name) != inputs.upstream[key]["manifest"]:
            raise SatelliteChangeMosaicBatchV1Error(
                f"upstream {key} manifest changed during execution"
            )


def _resolved_command(task: Mapping[str, Any], stage: Path) -> list[str]:
    arguments = list(task["execution"]["arguments"])
    resolved: list[str] = []
    for index in range(0, len(arguments), 2):
        flag, value = arguments[index : index + 2]
        if flag == "--output-dir":
            value = str(stage)
        if flag == "--bbox" and value.startswith("-"):
            resolved.append(f"--bbox={value}")
        else:
            resolved.extend((flag, value))
    script = _regular_file(
        PACKAGE_ROOT, "scripts/sentinel_change_mosaic.py", "mosaic processor CLI"
    )
    return [sys.executable, str(script), *resolved]


def _prepared_arguments(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for flag, value in _argument_pairs(
        row["execution"]["arguments"], f"{row['queue_id']} prepared arguments"
    ):
        if flag.endswith("-companion"):
            result.setdefault(flag, []).append(value)
        else:
            result[flag] = value
    return result


def _verify_catalog_artifacts(row: Mapping[str, Any]) -> None:
    queue_id = str(row["queue_id"])
    artifacts = row.get("catalog_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "baseline-response.json",
        "current-response.json",
        "manifest.json",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"prepared catalog artifact inventory changed for {queue_id}"
        )
    for name, record in artifacts.items():
        if not isinstance(record, Mapping) or set(record) != {
            "bytes",
            "path",
            "sha256",
        }:
            raise SatelliteChangeMosaicBatchV1Error(
                f"prepared catalog artifact record changed for {queue_id}/{name}"
            )
        path = _regular_file(
            PACKAGE_ROOT, record["path"], f"{queue_id} catalog artifact {name}"
        )
        if _file_record(path) != {
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }:
            raise SatelliteChangeMosaicBatchV1Error(
                f"catalog artifact changed for {queue_id}/{name}"
            )


def _load_bound_epochs(
    row: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]], Mapping[str, Any], Sequence[Mapping[str, Any]]]:
    values = _prepared_arguments(row)
    baseline_path = _regular_file(
        PACKAGE_ROOT, values["--baseline-stac"], "baseline STAC response"
    )
    current_path = _regular_file(
        PACKAGE_ROOT, values["--current-stac"], "current STAC response"
    )
    baseline_document = _decode_json(baseline_path.read_bytes(), "baseline STAC response")
    current_document = _decode_json(current_path.read_bytes(), "current STAC response")
    try:
        baseline_primary, baseline_items = select_bound_items(
            baseline_document,
            parse_item_binding(values["--baseline-primary"]),
            [parse_item_binding(value) for value in values["--baseline-companion"]],
        )
        current_primary, current_items = select_bound_items(
            current_document,
            parse_item_binding(values["--current-primary"]),
            [parse_item_binding(value) for value in values["--current-companion"]],
        )
    except SentinelMosaicContractError as error:
        raise SatelliteChangeMosaicBatchV1Error(
            f"bound mosaic STAC inputs are invalid for {row['queue_id']}: {error}"
        ) from error
    return baseline_primary, baseline_items, current_primary, current_items


def _epoch_summary(
    primary: Mapping[str, Any], items: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    properties = primary["properties"]
    return {
        "primary_id": primary["id"],
        "datatake_id": properties["s2:datatake_id"],
        "datastrip_id": properties["s2:datastrip_id"],
        "items": [
            item_summary(item)
            for item in sorted(items, key=lambda value: str(value["id"]))
        ],
    }


def _png_dimensions(path: Path, label: str) -> tuple[int, int]:
    raw = path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SatelliteChangeMosaicBatchV1Error(f"{label} is not a PNG")
    position = 8
    width: int | None = None
    height: int | None = None
    chunk_index = 0
    while position < len(raw):
        if len(raw) - position < 12:
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} has a truncated PNG chunk"
            )
        length = struct.unpack(">I", raw[position : position + 4])[0]
        chunk_type = raw[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(raw):
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} has a truncated PNG payload"
            )
        data = raw[position + 8 : position + 8 + length]
        stored_crc = struct.unpack(">I", raw[position + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != stored_crc:
            raise SatelliteChangeMosaicBatchV1Error(f"{label} has a PNG CRC mismatch")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"{label} lacks a valid PNG IHDR"
                )
            width, height = struct.unpack(">II", data[:8])
            if width <= 0 or height <= 0:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"{label} has invalid PNG dimensions"
                )
        if chunk_type == b"IEND":
            if length != 0 or end != len(raw) or width is None or height is None:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"{label} has an invalid PNG IEND"
                )
            return width, height
        position = end
        chunk_index += 1
    raise SatelliteChangeMosaicBatchV1Error(f"{label} is an incomplete PNG")


def _validate_position(
    value: Any, label: str, bbox: tuple[float, float, float, float]
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must contain two coordinates"
        )
    longitude = _finite_number(value[0], f"{label} longitude")
    latitude = _finite_number(value[1], f"{label} latitude")
    west, south, east, north = bbox
    latitude_tolerance = AOI_EDGE_TOLERANCE_METERS / 111_320.0
    maximum_latitude = min(89.999, max(abs(south), abs(north)))
    longitude_tolerance = AOI_EDGE_TOLERANCE_METERS / (
        111_320.0 * math.cos(math.radians(maximum_latitude))
    )
    if not (
        west - longitude_tolerance <= longitude <= east + longitude_tolerance
        and south - latitude_tolerance <= latitude <= north + latitude_tolerance
    ):
        raise SatelliteChangeMosaicBatchV1Error(f"{label} is outside the AOI")


def _validate_geometry(
    value: Any, label: str, bbox: tuple[float, float, float, float]
) -> None:
    if not isinstance(value, Mapping) or set(value) != {"type", "coordinates"}:
        raise SatelliteChangeMosaicBatchV1Error(f"{label} schema is invalid")
    if value["type"] == "Polygon":
        polygons = [value["coordinates"]]
    elif value["type"] == "MultiPolygon":
        polygons = value["coordinates"]
    else:
        raise SatelliteChangeMosaicBatchV1Error(
            f"{label} must be Polygon or MultiPolygon"
        )
    if not isinstance(polygons, list) or not polygons:
        raise SatelliteChangeMosaicBatchV1Error(f"{label} has no polygons")
    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise SatelliteChangeMosaicBatchV1Error(
                f"{label} polygon {polygon_index} has no rings"
            )
        for ring_index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"{label} polygon {polygon_index} ring {ring_index} is invalid"
                )
            for position_index, position in enumerate(ring):
                _validate_position(
                    position,
                    f"{label} polygon {polygon_index} ring {ring_index} "
                    f"position {position_index}",
                    bbox,
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
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report metrics schema is invalid"
        )
    result = dict(value)
    for field in expected - {"proposal_component_count"}:
        _finite_number(result[field], f"mosaic report metric {field}")
    for field in ("valid_pixel_fraction", "proposal_pixel_fraction_of_valid"):
        if not 0 <= float(result[field]) <= 1:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic report metric {field} is outside [0, 1]"
            )
    count = result["proposal_component_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report proposal count is invalid"
        )
    if float(result["proposal_area_m2_after_component_filter"]) < 0:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report proposal area is invalid"
        )
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
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report threshold schema is invalid"
        )
    for field in expected:
        _finite_number(value[field], f"mosaic report threshold {field}")
    if not 0 < float(value["adaptive_quantile"]) < 1:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report adaptive quantile is invalid"
        )
    if float(value["minimum_absolute_reflectance_change"]) <= 0 or float(
        value["applied_absolute_reflectance_change"]
    ) <= 0:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic report reflectance threshold is invalid"
        )


def _validate_geojson(
    path: Path,
    *,
    expected_count: int,
    expected_area_m2: float,
    minimum_component_area_m2: float,
    bbox: tuple[float, float, float, float],
) -> None:
    raw = path.read_bytes()
    document = _decode_json(raw, "mosaic proposals GeoJSON")
    if raw != _canonical_json(document):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic proposals GeoJSON is not canonical JSON"
        )
    if not isinstance(document, Mapping) or set(document) != {
        "type",
        "features",
        "properties",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic proposals GeoJSON schema is invalid"
        )
    if (
        document.get("type") != "FeatureCollection"
        or document.get("properties") != GEOJSON_COLLECTION_PROPERTIES
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic proposals lost their review-only scope"
        )
    features = document.get("features")
    if not isinstance(features, list) or len(features) != expected_count:
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic proposal count differs from report"
        )
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
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, Mapping) or set(feature) != {
            "type",
            "id",
            "geometry",
            "properties",
        }:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic proposal {index} schema is invalid"
            )
        if feature.get("type") != "Feature" or feature.get("id") != (
            f"change-proposal-{index}"
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic proposal {index} identity is invalid"
            )
        _validate_geometry(feature["geometry"], f"mosaic proposal {index}", bbox)
        properties = feature.get("properties")
        if not isinstance(properties, Mapping) or set(properties) != expected_properties:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic proposal {index} properties are invalid"
            )
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
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic proposal {index} scope changed"
            )
        area = _nonnegative_number(
            properties.get("area_m2"), f"mosaic proposal {index} area"
        )
        if area < minimum_component_area_m2:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic proposal {index} is below the component threshold"
            )
        area_total += area
    if round(area_total, 1) != round(expected_area_m2, 1):
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic proposal area differs from report"
        )


def _change_result(
    task: Mapping[str, Any], row: Mapping[str, Any], directory: Path
) -> dict[str, Any]:
    queue_id = str(task["queue_id"])
    _verify_catalog_artifacts(row)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic output is not a regular directory for {queue_id}"
        )
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic output contains a non-regular file for {queue_id}"
        )
    if {entry.name for entry in entries} != OUTPUT_FILES:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic output file set differs for {queue_id}"
        )
    report_path = directory / "report.json"
    report_raw = report_path.read_bytes()
    report = _decode_json(report_raw, f"{queue_id} mosaic report")
    if report_raw != _canonical_json(report):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report is not canonical JSON for {queue_id}"
        )
    expected_keys = {
        "schema_version",
        "algorithm_version",
        "spectral_core_algorithm_version",
        "entity",
        "aoi_bbox_wgs84",
        "baseline",
        "current",
        "source",
        "classification",
        "mosaic_contract",
        "grid",
        "thresholds",
        "radiometry",
        "metrics",
        "outputs",
    }
    if not isinstance(report, Mapping) or set(report) != expected_keys:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report schema is invalid for {queue_id}"
        )
    if (
        report.get("schema_version") != REPORT_SCHEMA_VERSION
        or report.get("algorithm_version") != ALGORITHM_VERSION
        or report.get("spectral_core_algorithm_version")
        != SPECTRAL_CORE_ALGORITHM_VERSION
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report version changed for {queue_id}"
        )
    if report.get("entity") != task["entity"] or report.get(
        "aoi_bbox_wgs84"
    ) != task["aoi_bbox_wgs84"]:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report entity or AOI changed for {queue_id}"
        )
    baseline_primary, baseline_items, current_primary, current_items = (
        _load_bound_epochs(row)
    )
    if report.get("baseline") != _epoch_summary(
        baseline_primary, baseline_items
    ) or report.get("current") != _epoch_summary(current_primary, current_items):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report scene lineage changed for {queue_id}"
        )
    if report.get("source") != report_source(baseline_primary, current_primary):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report source changed for {queue_id}"
        )
    if report.get("classification") != REPORT_CLASSIFICATION:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report lost its review-only scope for {queue_id}"
        )
    values = _prepared_arguments(row)
    expected_mosaic_contract = {
        "explicit_item_hash_bindings": True,
        "same_datatake_and_datastrip_required": True,
        "maximum_companion_sensing_time_delta_seconds": (
            MAX_COMPANION_TIME_DELTA_SECONDS
        ),
        "product_uri_identity_policy": "exact_except_mgrs_tile_token",
        "frozen_stac_response_sha256": {
            "baseline": values["--baseline-stac-sha256"],
            "current": values["--current-stac-sha256"],
        },
        "nonzero_overlap_conflict_policy": "reject",
        "missing_spatial_coverage_policy": "reject",
        "nodata_policy": "invalid_never_clear",
        "baseline_metadata_coverage": row["epochs"]["baseline"][
            "selected_coverage"
        ],
        "current_metadata_coverage": row["epochs"]["current"][
            "selected_coverage"
        ],
    }
    if report.get("mosaic_contract") != expected_mosaic_contract:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report input contract changed for {queue_id}"
        )
    if report.get("radiometry") != {
        "reflectance": "STAC raster scale and offset applied per epoch and band",
        "normalized_index_negative_reflectance_policy": "clip_to_zero",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report radiometry changed for {queue_id}"
        )
    _validate_thresholds(report.get("thresholds"))
    metrics = _report_metrics(report.get("metrics"))
    outputs = report.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != REPORT_BOUND_FILES:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report output inventory changed for {queue_id}"
        )
    for name in sorted(REPORT_BOUND_FILES):
        record = outputs[name]
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic report output record is invalid for {queue_id}/{name}"
            )
        if dict(record) != _file_record(directory / name):
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic report-bound output changed for {queue_id}/{name}"
            )
    grid = report.get("grid")
    if not isinstance(grid, Mapping) or set(grid) != {
        "crs",
        "width",
        "height",
        "pixel_area_m2",
        "clear_scl_classes",
        "aoi_inclusion",
    }:
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report grid schema changed for {queue_id}"
        )
    width = _positive_integer(grid.get("width"), f"{queue_id} grid width")
    height = _positive_integer(grid.get("height"), f"{queue_id} grid height")
    _positive_number(grid.get("pixel_area_m2"), f"{queue_id} pixel area")
    if (
        not isinstance(grid.get("crs"), str)
        or not grid["crs"]
        or grid.get("clear_scl_classes") != sorted(CLEAR_SCL_CLASSES)
        or grid.get("aoi_inclusion") != "exact_wgs84_pixel_centers"
    ):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic report grid values changed for {queue_id}"
        )
    for name in ("before.png", "after.png", "change-overlay.png"):
        if _png_dimensions(directory / name, f"{queue_id}/{name}") != (
            width,
            height,
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic PNG dimensions changed for {queue_id}/{name}"
            )
    if _png_dimensions(
        directory / "comparison.png", f"{queue_id}/comparison.png"
    ) != (width * 3, height):
        raise SatelliteChangeMosaicBatchV1Error(
            f"mosaic comparison dimensions changed for {queue_id}"
        )
    minimum_area = _positive_number(
        float(values["--minimum-component-area-m2"]),
        f"{queue_id} component threshold",
    )
    _validate_geojson(
        directory / "change-proposals.geojson",
        expected_count=metrics["proposal_component_count"],
        expected_area_m2=float(metrics["proposal_area_m2_after_component_filter"]),
        minimum_component_area_m2=minimum_area,
        bbox=parse_bbox(values["--bbox"]),
    )
    _verify_catalog_artifacts(row)
    return {
        "artifacts": {
            name: _file_record(directory / name) for name in sorted(OUTPUT_FILES)
        },
        "report": {
            "schema_version": report["schema_version"],
            "algorithm_version": report["algorithm_version"],
            "spectral_core_algorithm_version": report[
                "spectral_core_algorithm_version"
            ],
            "classification": dict(report["classification"]),
            "metrics": metrics,
            "report_sha256": _sha256(report_raw),
        },
    }


def _validate_output_tree(
    output: Path, document: Mapping[str, Any], inputs: _Inputs
) -> None:
    allowed_directories = {Path("."), Path("jobs")}
    allowed_files = {Path(BATCH_MANIFEST_FILENAME)}
    for queue_id, task in document["jobs"].items():
        job_directory = Path("jobs") / queue_id
        allowed_directories.add(job_directory)
        final, stage = _task_paths(output, task)
        if stage.exists() or stage.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"unfinished mosaic staging directory exists for {queue_id}"
            )
        if task["state"] == "completed":
            result = _change_result(task, inputs.rows_by_id[queue_id], final)
            if result["artifacts"] != task["artifacts"] or result["report"] != task[
                "report"
            ]:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"mosaic output differs from checkpoint for {queue_id}"
                )
            relative = Path(task["output_directory"])
            allowed_directories.add(relative)
            allowed_files.update(relative / name for name in OUTPUT_FILES)
        elif final.exists() or final.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"incomplete mosaic task has published output for {queue_id}"
            )
    for path in [output, *output.rglob("*")]:
        relative = Path(".") if path == output else path.relative_to(output)
        if path.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic output contains a symlink: {relative}"
            )
        if path.is_dir():
            if relative not in allowed_directories:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"mosaic output contains an extra directory: {relative}"
                )
        elif path.is_file():
            if relative not in allowed_files:
                raise SatelliteChangeMosaicBatchV1Error(
                    f"mosaic output contains an extra file: {relative}"
                )
        else:
            raise SatelliteChangeMosaicBatchV1Error(
                f"mosaic output contains an unsupported entry: {relative}"
            )


def _record_failure(
    task: dict[str, Any], *, at: str, kind: str, error: str
) -> None:
    task["failures"].append(
        {
            "attempt": task["attempts"],
            "at": at,
            "kind": kind,
            "error": (error.strip() or kind)[-2_500:],
        }
    )
    task["state"] = "failed"


def _recover_interrupted(
    output: Path,
    document: dict[str, Any],
    inputs: _Inputs,
    recovered_at: str,
) -> None:
    if not document["runs"] or document["runs"][-1]["state"] != "running":
        if any(task["state"] == "running" for task in document["jobs"].values()):
            raise SatelliteChangeMosaicBatchV1Error(
                "running mosaic task has no running invocation"
            )
        return
    run = document["runs"][-1]
    running_tasks = [
        task for task in document["jobs"].values() if task["state"] == "running"
    ]
    if len(running_tasks) > 1:
        raise SatelliteChangeMosaicBatchV1Error(
            "multiple mosaic tasks were left running"
        )
    for task in running_tasks:
        queue_id = task["queue_id"]
        final, stage = _task_paths(output, task)
        if final.exists() or final.is_symlink():
            result = _change_result(task, inputs.rows_by_id[queue_id], final)
            task.update(
                {
                    "state": "completed",
                    "completed_at": recovered_at,
                    "artifacts": result["artifacts"],
                    "report": result["report"],
                }
            )
            run["jobs_recovered_after_publish"] += 1
        else:
            _clear_stage(stage)
            _record_failure(
                task,
                at=recovered_at,
                kind="interrupted",
                error="previous mosaic invocation stopped before atomic publication",
            )
            run["jobs_interrupted"] += 1
    run["state"] = "interrupted"
    run["finished_at"] = recovered_at
    run["interruption_recorded_at"] = recovered_at


def _separate_output(output: Path, inputs: _Inputs) -> None:
    output_resolved = output.resolve(strict=False)
    roots = [
        inputs.preparation.resolve(),
        _safe_child(
            PACKAGE_ROOT,
            inputs.upstream["queue_bundle"]["directory"],
            "upstream queue",
        ).resolve(),
        _safe_child(
            PACKAGE_ROOT,
            inputs.upstream["catalog_batch"]["directory"],
            "upstream catalog",
        ).resolve(),
    ]
    for root in roots:
        if (
            output_resolved == root
            or root in output_resolved.parents
            or output_resolved in root.parents
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                "mosaic output must be separate from all frozen inputs"
            )


@contextmanager
def _directory_lock(directory: Path, *, exclusive: bool):
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    locked = False
    try:
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise SatelliteChangeMosaicBatchV1Error(
                    "mosaic output lock could not be acquired"
                ) from error
            raise SatelliteChangeMosaicBatchV1Error(
                "mosaic output is locked by another invocation"
            ) from error
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def validate_satellite_change_mosaic_batch_v1(
    preparation_directory: str | Path,
    output_directory: str | Path,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    config: MosaicBatchConfig | None = None,
) -> dict[str, Any]:
    """Perform full offline validation of inputs, checkpoint state, and outputs."""

    inputs = _validated_inputs(preparation_directory, definition_path)
    output = _absolute_directory(
        output_directory, "mosaic-batch output", must_exist=True
    )
    _separate_output(output, inputs)
    with _directory_lock(output, exclusive=False):
        temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
        if temporary.exists() or temporary.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                "mosaic output contains an unfinished checkpoint temporary"
            )
        document = _load_checkpoint(output / BATCH_MANIFEST_FILENAME)
        saved_config = _config_from_document(document.get("configuration"))
        if config is not None and (
            not isinstance(config, MosaicBatchConfig) or config != saved_config
        ):
            raise SatelliteChangeMosaicBatchV1Error(
                "saved mosaic configuration differs from expected"
            )
        processor = _processor_lineage()
        document = _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=saved_config,
        )
        _validate_output_tree(output, document, inputs)
        return document


def execute_satellite_change_mosaic_batch_v1(
    preparation_directory: str | Path,
    output_directory: str | Path,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    config: MosaicBatchConfig | None = None,
    max_jobs: int = 1,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Run at most ``max_jobs`` exact prepared jobs and checkpoint atomically."""

    max_jobs = _positive_integer(max_jobs, "max_jobs")
    if config is not None and not isinstance(config, MosaicBatchConfig):
        raise SatelliteChangeMosaicBatchV1Error(
            "config must be a MosaicBatchConfig"
        )
    inputs = _validated_inputs(preparation_directory, definition_path)
    output = _absolute_directory(
        output_directory, "mosaic-batch output", must_exist=False
    )
    _separate_output(output, inputs)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangeMosaicBatchV1Error(
            "mosaic-batch output is not a regular directory"
        )
    with _directory_lock(output, exclusive=True):
        checkpoint = output / BATCH_MANIFEST_FILENAME
        temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
        if temporary.exists() or temporary.is_symlink():
            raise SatelliteChangeMosaicBatchV1Error(
                "stale mosaic checkpoint temporary exists"
            )
        started_at = _timestamp(timestamp(), "mosaic invocation started_at")
        processor = _processor_lineage()
        if checkpoint.exists() or checkpoint.is_symlink():
            document = _load_checkpoint(checkpoint)
            saved_config = _config_from_document(document.get("configuration"))
            if config is not None and config != saved_config:
                raise SatelliteChangeMosaicBatchV1Error(
                    "saved mosaic configuration differs from requested"
                )
            config = saved_config
            document = _validate_checkpoint(
                document,
                inputs=inputs,
                processor=processor,
                config=config,
            )
            _recover_interrupted(output, document, inputs, started_at)
            _write_checkpoint(output, document, config, started_at)
            document = _validate_checkpoint(
                document,
                inputs=inputs,
                processor=processor,
                config=config,
            )
            _validate_output_tree(output, document, inputs)
        else:
            if any(output.iterdir()):
                raise SatelliteChangeMosaicBatchV1Error(
                    "mosaic output contains files without a checkpoint"
                )
            config = config or MosaicBatchConfig()
            document = _new_document(inputs, processor, config, started_at)
            _write_checkpoint(output, document, config, started_at)

        run = {
            "run_number": len(document["runs"]) + 1,
            "state": "running",
            "started_at": started_at,
            "finished_at": None,
            "interruption_recorded_at": None,
            "max_jobs": max_jobs,
            "job_attempts": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "jobs_interrupted": 0,
            "jobs_recovered_after_publish": 0,
            "budget_exhausted": False,
        }
        document["runs"].append(run)
        _write_checkpoint(output, document, config, started_at)

        invoked = False
        for queue_id in EXPECTED_QUEUE_IDS:
            task = document["jobs"][queue_id]
            if task["state"] == "completed" or task["attempts"] >= (
                config.max_job_attempts
            ):
                continue
            if run["job_attempts"] >= max_jobs:
                run["budget_exhausted"] = True
                break
            if invoked and config.minimum_interval_seconds:
                sleep(config.minimum_interval_seconds)
            invoked = True
            _verify_input_bytes(inputs)
            if _processor_lineage() != document["processor"]:
                raise SatelliteChangeMosaicBatchV1Error(
                    "mosaic processor changed during execution"
                )
            final, stage = _task_paths(output, task)
            if final.exists() or final.is_symlink():
                raise SatelliteChangeMosaicBatchV1Error(
                    f"refusing to overwrite mosaic output for {queue_id}"
                )
            _clear_stage(stage)
            _prepare_parent(output, final)
            attempt_at = _timestamp(timestamp(), f"{queue_id} attempt timestamp")
            task["attempts"] += 1
            task["state"] = "running"
            task["last_attempt_started_at"] = attempt_at
            run["job_attempts"] += 1
            _write_checkpoint(output, document, config, attempt_at)
            failure_kind: str | None = None
            failure_detail: str | None = None
            try:
                _verify_catalog_artifacts(inputs.rows_by_id[queue_id])
                command = _resolved_command(task, stage)
                completed = command_runner(
                    command,
                    cwd=PACKAGE_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=config.timeout_seconds,
                )
                if completed.returncode != 0:
                    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
                    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
                    detail = (stderr or stdout).strip()
                    failure_kind = "command_exit"
                    failure_detail = f"mosaic command exited {completed.returncode}"
                    if detail:
                        failure_detail += ": " + detail[-2_000:]
                else:
                    result = _change_result(
                        task, inputs.rows_by_id[queue_id], stage
                    )
                    _fsync_tree(stage)
                    if _change_result(
                        task, inputs.rows_by_id[queue_id], stage
                    ) != result:
                        raise SatelliteChangeMosaicBatchV1Error(
                            "validated mosaic output changed before publication"
                        )
                    _verify_input_bytes(inputs)
                    if _processor_lineage() != document["processor"]:
                        raise SatelliteChangeMosaicBatchV1Error(
                            "mosaic processor changed during the job"
                        )
                    os.replace(stage, final)
                    descriptor = os.open(
                        final.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    )
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    completed_at = _timestamp(
                        timestamp(), f"{queue_id} completion timestamp"
                    )
                    task.update(
                        {
                            "state": "completed",
                            "completed_at": completed_at,
                            "artifacts": result["artifacts"],
                            "report": result["report"],
                        }
                    )
                    run["jobs_completed"] += 1
            except subprocess.TimeoutExpired as error:
                failure_kind = "timeout"
                failure_detail = (
                    f"mosaic command exceeded {config.timeout_seconds:g} seconds: "
                    f"{error}"
                )
            except SatelliteChangeMosaicBatchV1Error as error:
                failure_kind = "output_validation"
                failure_detail = f"{type(error).__name__}: {error}"
            except Exception as error:
                failure_kind = "execution_error"
                failure_detail = f"{type(error).__name__}: {error}"
            if failure_kind is not None:
                failed_at = _timestamp(timestamp(), f"{queue_id} failure timestamp")
                _record_failure(
                    task,
                    at=failed_at,
                    kind=failure_kind,
                    error=failure_detail or failure_kind,
                )
                run["jobs_failed"] += 1
                _clear_stage(stage)
            checkpoint_at = _timestamp(
                timestamp(), f"{queue_id} checkpoint timestamp"
            )
            _write_checkpoint(output, document, config, checkpoint_at)

        finished_at = _timestamp(timestamp(), "mosaic invocation finished_at")
        run["state"] = "completed"
        run["finished_at"] = finished_at
        _write_checkpoint(output, document, config, finished_at)
        document = _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=config,
        )
        _validate_output_tree(output, document, inputs)
        return document


__all__ = [
    "BATCH_MANIFEST_FILENAME",
    "BATCH_PIPELINE",
    "BATCH_SCHEMA_VERSION",
    "DEFAULT_MINIMUM_INTERVAL_SECONDS",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "EXPECTED_QUEUE_IDS",
    "MosaicBatchConfig",
    "OUTPUT_FILES",
    "PREPARATION_DEFINITION_PATH",
    "PREPARATION_DIRECTORY_PATH",
    "SCOPE",
    "SatelliteChangeMosaicBatchV1Error",
    "execute_satellite_change_mosaic_batch_v1",
    "validate_satellite_change_mosaic_batch_v1",
]
