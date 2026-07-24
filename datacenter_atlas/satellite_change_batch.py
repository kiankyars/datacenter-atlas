"""Atomic, resumable execution of validated satellite change proposals.

The runner consumes one immutable satellite-review queue plus one or more
offline-validated catalog batches.  It only schedules catalog tasks already
checkpointed as ``completed`` and executes the queue's exact
``change_job_template``.  Every output remains an analyst-review proposal; no
atlas fact or identity, lifecycle, operating-status, power, or energy claim is
created here; operator, data-centre type, IT capacity, PUE, and workload are
also explicitly outside the inference scope.
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
import struct
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import zlib

from .satellite_batch import (
    BATCH_MANIFEST_FILENAME as CATALOG_BATCH_MANIFEST_FILENAME,
    validate_satellite_batch,
)
from .satellite_change import (
    ALGORITHM_VERSION,
    CLEAR_SCL_CLASSES,
    REPORT_SCHEMA_VERSION,
    ensure_comparable,
    item_summary,
    parse_bbox,
    report_source,
    select_feature,
)
from .satellite_queue import (
    MANIFEST_FILENAME as QUEUE_MANIFEST_FILENAME,
    QUEUE_FILENAME,
    REVIEW_CONSTRAINTS,
    validate_queue_bundle,
)


CHANGE_BATCH_MANIFEST_FILENAME = "batch-manifest.json"
CHANGE_BATCH_SCHEMA_VERSION = 1
CHANGE_BATCH_PIPELINE = "satellite_review_change_batch"
DEFAULT_TIMEOUT_SECONDS = 1_800.0
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1
AOI_EDGE_TOLERANCE_METERS = 25.0
PROCESSOR_FILES = (
    "datacenter_atlas/satellite_change_batch.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_batch.py",
    "datacenter_atlas/satellite_queue.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/models.py",
    "scripts/sentinel_change.py",
)
CHANGE_FILES = frozenset(
    {
        "before.png",
        "after.png",
        "change-overlay.png",
        "comparison.png",
        "change-proposals.geojson",
        "report.json",
    }
)
REPORT_BOUND_FILES = CHANGE_FILES - {"report.json"}
CHANGE_ARGUMENT_FLAGS = (
    "--baseline-stac",
    "--baseline-id",
    "--current-stac",
    "--current-id",
    "--bbox",
    "--entity-id",
    "--entity-name",
    "--output-dir",
    "--minimum-component-area-m2",
)
SELECTED_ID_POINTERS = {
    "{selected_ids.baseline}": "/selected_ids/baseline",
    "{selected_ids.current}": "/selected_ids/current",
}
CHANGE_SCOPE = {
    "mode": "visible_change_proposals_only",
    "atlas_mutation": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_power_inference": False,
    "imagery_energy_inference": False,
    "imagery_operator_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_it_capacity_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "review_required": True,
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


class SatelliteChangeBatchError(ValueError):
    """Raised when input lineage, a checkpoint, command, or output is invalid."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SatelliteChangeBatchError(f"{field} must be a non-empty RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteChangeBatchError(f"{field} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteChangeBatchError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SatelliteChangeBatchError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SatelliteChangeBatchError(f"{field} must be a non-negative integer")
    return value


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeBatchError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise SatelliteChangeBatchError(f"{field} must be finite and positive")
    return result


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeBatchError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SatelliteChangeBatchError(f"{field} must be finite and non-negative")
    return result


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return _sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SatelliteChangeBatchError(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise SatelliteChangeBatchError(f"{label} contains non-finite number {value}")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteChangeBatchError(f"{label} is not valid JSON") from error


def _canonical_external_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class ChangeBatchConfig:
    """Settings pinned by the first checkpoint; invocation caps stay separate."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS
    max_job_attempts: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "timeout_seconds", _positive_number(self.timeout_seconds, "timeout_seconds")
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


def _config_from_document(value: Any) -> ChangeBatchConfig:
    if not isinstance(value, Mapping) or set(value) != {
        "mode",
        "timeout_seconds",
        "minimum_interval_seconds",
        "max_job_attempts",
    }:
        raise SatelliteChangeBatchError("change-batch configuration schema is invalid")
    if value.get("mode") != "visible_change_proposals_only":
        raise SatelliteChangeBatchError("change-batch configuration mode is invalid")
    config = ChangeBatchConfig(
        timeout_seconds=value.get("timeout_seconds"),
        minimum_interval_seconds=value.get("minimum_interval_seconds"),
        max_job_attempts=value.get("max_job_attempts"),
    )
    if dict(value) != config.as_dict():
        raise SatelliteChangeBatchError("change-batch configuration is not canonical")
    return config


def _absolute_directory(path: str | Path, label: str, *, must_exist: bool) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate.is_symlink():
        raise SatelliteChangeBatchError(f"{label} may not be a symlink")
    if must_exist and not candidate.is_dir():
        raise SatelliteChangeBatchError(f"{label} is not a regular directory: {candidate}")
    return candidate


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SatelliteChangeBatchError(f"{label} must be a safe POSIX relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise SatelliteChangeBatchError(f"{label} must be a safe POSIX relative path")
    return pure.parts


def _safe_child(root: Path, relative: Any, label: str) -> Path:
    parts = _relative_parts(relative, label)
    candidate = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise SatelliteChangeBatchError(f"{label} escapes its root")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteChangeBatchError(f"{label} traverses a symlink: {current}")
    return candidate


def _regular_file(root: Path, relative: Any, label: str) -> Path:
    path = _safe_child(root, relative, label)
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeBatchError(f"{label} is not a regular file: {path}")
    return path


def _read_queue_jobs(
    queue: Path, manifest: Mapping[str, Any]
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    raw = _regular_file(queue, QUEUE_FILENAME, "queue JSONL").read_bytes()
    expected = manifest["artifacts"][QUEUE_FILENAME]
    if len(raw) != expected["bytes"] or _sha256(raw) != expected["sha256"]:
        raise SatelliteChangeBatchError(
            "queue JSONL changed after closed-world validation"
        )
    for line_number, line in enumerate(raw.splitlines(), start=1):
        value = _decode_json(line, f"queue line {line_number}")
        if not isinstance(value, dict):
            raise SatelliteChangeBatchError(f"queue line {line_number} is not an object")
        jobs.append(value)
    return jobs


def _queue_lineage(queue: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    manifest_raw = _regular_file(
        queue, QUEUE_MANIFEST_FILENAME, "queue manifest"
    ).read_bytes()
    artifact = manifest["artifacts"][QUEUE_FILENAME]
    return {
        "pipeline": manifest["pipeline"],
        "generated_at": manifest["generated_at"],
        "manifest_file": QUEUE_MANIFEST_FILENAME,
        "manifest_bytes": len(manifest_raw),
        "manifest_sha256": _sha256(manifest_raw),
        "queue_file": QUEUE_FILENAME,
        "queue_bytes": artifact["bytes"],
        "queue_sha256": artifact["sha256"],
        "queue_jobs": artifact["records"],
    }


def _processor_lineage(package_root: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for relative in PROCESSOR_FILES:
        path = _regular_file(package_root, relative, f"processor {relative}")
        files[relative] = _file_record(path)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "files": files,
        "runtime": _runtime_lineage(),
    }


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
    geospatial_runtime: dict[str, str | None] = {
        "gdal": None,
        "proj": None,
    }
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


def _catalog_lineage(
    index: int, root: Path, document: Mapping[str, Any]
) -> dict[str, Any]:
    raw = _regular_file(
        root, CATALOG_BATCH_MANIFEST_FILENAME, f"catalog batch {index} manifest"
    ).read_bytes()
    if _decode_json(raw, f"catalog batch {index} manifest") != document:
        raise SatelliteChangeBatchError(
            f"catalog batch {index} manifest changed after offline validation"
        )
    return {
        "index": index,
        "schema_version": document["schema_version"],
        "pipeline": document["pipeline"],
        "state": document["state"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "manifest_file": CATALOG_BATCH_MANIFEST_FILENAME,
        "manifest_bytes": len(raw),
        "manifest_sha256": _sha256(raw),
        "queue_manifest_sha256": document["queue_bundle"]["manifest_sha256"],
        "jobs_selected": document["summary"]["jobs_selected"],
        "jobs_completed": document["summary"]["jobs_completed"],
        "jobs_unavailable_no_scene": document["summary"][
            "jobs_unavailable_no_scene"
        ],
        "jobs_failed": document["summary"]["jobs_failed"],
        "jobs_pending": document["summary"]["jobs_pending"],
    }


def _json_pointer(document: Any, pointer: str, label: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise SatelliteChangeBatchError(f"{label} is not an absolute JSON pointer")
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            raise SatelliteChangeBatchError(f"{label} does not resolve")
        current = current[token]
    return current


def _argument_pairs(arguments: Any, label: str) -> dict[str, str]:
    if not isinstance(arguments, list) or len(arguments) != 2 * len(
        CHANGE_ARGUMENT_FLAGS
    ):
        raise SatelliteChangeBatchError(f"{label} must contain the exact flag/value pairs")
    parsed: dict[str, str] = {}
    flags: list[str] = []
    for index in range(0, len(arguments), 2):
        flag, value = arguments[index : index + 2]
        if not isinstance(flag, str) or not isinstance(value, str):
            raise SatelliteChangeBatchError(f"{label} contains a non-text pair")
        if flag in parsed:
            raise SatelliteChangeBatchError(f"{label} repeats {flag}")
        parsed[flag] = value
        flags.append(flag)
    if tuple(flags) != CHANGE_ARGUMENT_FLAGS:
        raise SatelliteChangeBatchError(f"{label} flag order or inventory changed")
    return parsed


@dataclass(frozen=True, slots=True)
class _Inputs:
    queue: Path
    queue_manifest: Mapping[str, Any]
    queue_jobs: tuple[dict[str, Any], ...]
    queue_by_id: Mapping[str, Mapping[str, Any]]
    queue_lineage: Mapping[str, Any]
    catalog_roots: tuple[Path, ...]
    catalog_documents: tuple[Mapping[str, Any], ...]
    catalog_lineages: tuple[Mapping[str, Any], ...]
    completed_sources: Mapping[str, tuple[int, Mapping[str, Any]]]


def _validated_inputs(
    queue_directory: str | Path,
    catalog_batch_directories: Sequence[str | Path],
) -> _Inputs:
    queue = _absolute_directory(queue_directory, "queue bundle", must_exist=True)
    queue_manifest = validate_queue_bundle(queue)
    if queue_manifest["configuration"]["provider"] != "earth-search-v1":
        raise SatelliteChangeBatchError(
            "change processor source contract currently supports only earth-search-v1 queues"
        )
    queue_jobs = tuple(_read_queue_jobs(queue, queue_manifest))
    queue_by_id = {job["queue_id"]: job for job in queue_jobs}
    if len(queue_by_id) != len(queue_jobs):
        raise SatelliteChangeBatchError("validated queue contains duplicate queue IDs")

    if isinstance(catalog_batch_directories, (str, bytes, Path)):
        raise SatelliteChangeBatchError(
            "catalog_batch_directories must be a non-empty sequence"
        )
    raw_catalogs = tuple(catalog_batch_directories)
    if not raw_catalogs:
        raise SatelliteChangeBatchError(
            "at least one catalog batch directory is required"
        )

    catalog_roots: list[Path] = []
    catalog_documents: list[Mapping[str, Any]] = []
    catalog_lineages: list[Mapping[str, Any]] = []
    completed_sources: dict[str, tuple[int, Mapping[str, Any]]] = {}
    seen_roots: set[Path] = set()
    for index, value in enumerate(raw_catalogs):
        root = _absolute_directory(
            value, f"catalog batch {index}", must_exist=True
        )
        resolved = root.resolve()
        if resolved in seen_roots:
            raise SatelliteChangeBatchError("catalog batch directories must be unique")
        seen_roots.add(resolved)
        try:
            document = validate_satellite_batch(queue, root)
        except Exception as error:
            raise SatelliteChangeBatchError(
                f"catalog batch {index} failed offline validation: {error}"
            ) from error
        if document["queue_bundle"]["manifest_sha256"] != _queue_lineage(
            queue, queue_manifest
        )["manifest_sha256"]:
            raise SatelliteChangeBatchError(
                f"catalog batch {index} is bound to a different queue manifest"
            )
        lineage = _catalog_lineage(index, root, document)
        for queue_id, task in document["jobs"].items():
            if task["state"] != "completed":
                continue
            if queue_id in completed_sources:
                previous = completed_sources[queue_id][0]
                raise SatelliteChangeBatchError(
                    f"completed queue job {queue_id} appears in catalog batches "
                    f"{previous} and {index}"
                )
            completed_sources[queue_id] = (index, task)
        catalog_roots.append(root)
        catalog_documents.append(document)
        catalog_lineages.append(lineage)

    if not completed_sources:
        raise SatelliteChangeBatchError(
            "catalog batches contain no completed jobs eligible for change analysis"
        )
    return _Inputs(
        queue=queue,
        queue_manifest=queue_manifest,
        queue_jobs=queue_jobs,
        queue_by_id=queue_by_id,
        queue_lineage=_queue_lineage(queue, queue_manifest),
        catalog_roots=tuple(catalog_roots),
        catalog_documents=tuple(catalog_documents),
        catalog_lineages=tuple(catalog_lineages),
        completed_sources=completed_sources,
    )


def _resolved_template(
    job: Mapping[str, Any],
    catalog_root: Path,
    catalog_task: Mapping[str, Any],
) -> dict[str, Any]:
    queue_id = job["queue_id"]
    template = job.get("change_job_template")
    if not isinstance(template, Mapping) or set(template) != {
        "script",
        "arguments",
        "catalog_manifest",
        "selected_id_json_pointers",
        "output_directory",
    }:
        raise SatelliteChangeBatchError(
            f"change template schema changed for {queue_id}"
        )
    if template.get("script") != "scripts/sentinel_change.py":
        raise SatelliteChangeBatchError(
            f"change processor changed for {queue_id}"
        )
    if template.get("selected_id_json_pointers") != SELECTED_ID_POINTERS:
        raise SatelliteChangeBatchError(
            f"selected-ID pointer contract changed for {queue_id}"
        )
    if template.get("catalog_manifest") != (
        f"{catalog_task['output_directory']}/manifest.json"
    ):
        raise SatelliteChangeBatchError(
            f"change template catalog manifest differs from completed task for {queue_id}"
        )

    catalog_manifest_path = _regular_file(
        catalog_root,
        template["catalog_manifest"],
        f"{queue_id} catalog manifest",
    )
    catalog_manifest = _decode_json(
        catalog_manifest_path.read_bytes(), f"{queue_id} catalog manifest"
    )
    selected_ids: dict[str, str] = {}
    bindings: dict[str, Any] = {}
    for placeholder, pointer in SELECTED_ID_POINTERS.items():
        value = _json_pointer(
            catalog_manifest, pointer, f"{queue_id} selected-ID pointer {pointer}"
        )
        key = pointer.rsplit("/", 1)[-1]
        if not isinstance(value, str) or not value:
            raise SatelliteChangeBatchError(
                f"{queue_id} selected-ID pointer {pointer} is not non-empty text"
            )
        selected_ids[key] = value
        bindings[placeholder] = {"json_pointer": pointer, "value": value}
    if selected_ids != catalog_task.get("selected_ids"):
        raise SatelliteChangeBatchError(
            f"catalog selected IDs changed for {queue_id}"
        )

    arguments = list(template.get("arguments", []))
    parsed = _argument_pairs(arguments, f"{queue_id} change arguments")
    if parsed["--baseline-stac"] != (
        f"{catalog_task['output_directory']}/baseline-response.json"
    ) or parsed["--current-stac"] != (
        f"{catalog_task['output_directory']}/current-response.json"
    ):
        raise SatelliteChangeBatchError(
            f"change template STAC inputs differ from completed task for {queue_id}"
        )
    if parsed["--output-dir"] != template.get("output_directory"):
        raise SatelliteChangeBatchError(
            f"change template output path disagrees for {queue_id}"
        )
    if parsed["--entity-id"] != job["entity"]["id"] or parsed[
        "--entity-name"
    ] != job["entity"]["name"]:
        raise SatelliteChangeBatchError(
            f"change template entity binding changed for {queue_id}"
        )
    if list(parse_bbox(parsed["--bbox"])) != job["location"]["aoi_bbox_wgs84"]:
        raise SatelliteChangeBatchError(
            f"change template AOI changed for {queue_id}"
        )
    _positive_number(
        float(parsed["--minimum-component-area-m2"]),
        f"{queue_id} minimum component area",
    )

    token_counts = {
        placeholder: arguments.count(placeholder) for placeholder in SELECTED_ID_POINTERS
    }
    if any(count != 1 for count in token_counts.values()):
        raise SatelliteChangeBatchError(
            f"change template selected-ID placeholders changed for {queue_id}"
        )
    resolved_arguments = [
        bindings[value]["value"] if value in bindings else value for value in arguments
    ]
    if any("{selected_ids." in value for value in resolved_arguments):
        raise SatelliteChangeBatchError(
            f"change template has an unresolved selected-ID placeholder for {queue_id}"
        )
    _argument_pairs(resolved_arguments, f"{queue_id} resolved change arguments")
    return {
        "template_sha256": _canonical_hash(template),
        "script": template["script"],
        "arguments": resolved_arguments,
        "selected_id_bindings": bindings,
        "output_directory": template["output_directory"],
    }


def _immutable_task(
    job: Mapping[str, Any],
    inputs: _Inputs,
    catalog_index: int,
    catalog_task: Mapping[str, Any],
) -> dict[str, Any]:
    catalog_root = inputs.catalog_roots[catalog_index]
    template = _resolved_template(job, catalog_root, catalog_task)
    _load_selected_stac(
        {"queue_id": job["queue_id"], "change_job": template}, catalog_root
    )
    lineage = inputs.catalog_lineages[catalog_index]
    return {
        "queue_id": job["queue_id"],
        "queue_position": job["queue_position"],
        "entity": {"id": job["entity"]["id"], "name": job["entity"]["name"]},
        "priority": {
            "rank": job["priority"]["rank"],
            "tier": job["priority"]["tier"],
        },
        "catalog_source": {
            "catalog_batch_index": catalog_index,
            "catalog_batch_manifest_sha256": lineage["manifest_sha256"],
            "catalog_task_sha256": _canonical_hash(catalog_task),
            "catalog_output_directory": catalog_task["output_directory"],
            "catalog_manifest": job["change_job_template"]["catalog_manifest"],
            "selected_ids": dict(catalog_task["selected_ids"]),
            "artifacts": dict(catalog_task["artifacts"]),
        },
        "change_job": template,
    }


def _task_template(immutable: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **json.loads(json.dumps(immutable)),
        "state": "pending",
        "attempts": 0,
        "last_attempt_started_at": None,
        "failures": [],
        "completed_at": None,
        "artifacts": None,
        "report": None,
    }


def _validated_queue_ids(
    values: Sequence[str] | None, inputs: _Inputs, label: str
) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        raise SatelliteChangeBatchError(f"{label} must be a sequence of queue IDs")
    requested = tuple(values)
    if not requested:
        raise SatelliteChangeBatchError(f"{label} may not be empty when supplied")
    if any(not isinstance(value, str) or not value for value in requested):
        raise SatelliteChangeBatchError(f"{label} must contain non-empty text IDs")
    if len(set(requested)) != len(requested):
        raise SatelliteChangeBatchError(f"{label} contains duplicate queue IDs")
    unknown = sorted(set(requested) - set(inputs.queue_by_id))
    if unknown:
        raise SatelliteChangeBatchError(
            f"{label} contains queue IDs absent from the immutable queue: {unknown}"
        )
    order = {job["queue_id"]: job["queue_position"] for job in inputs.queue_jobs}
    return tuple(sorted(requested, key=order.__getitem__))


def _exclusion_file(
    path: str | Path, inputs: _Inputs
) -> tuple[tuple[str, ...], dict[str, Any]]:
    file_path = Path(os.path.abspath(os.fspath(path)))
    if file_path.is_symlink() or not file_path.is_file():
        raise SatelliteChangeBatchError(
            f"exclusion file is not a regular file: {file_path}"
        )
    raw = file_path.read_bytes()
    document = _decode_json(raw, "change-batch exclusion file")
    if raw != _canonical_bytes(document):
        raise SatelliteChangeBatchError(
            "change-batch exclusion file is not canonical pretty JSON"
        )
    if not isinstance(document, Mapping) or set(document) != {
        "schema_version",
        "purpose",
        "queue_manifest_sha256",
        "queue_ids",
    }:
        raise SatelliteChangeBatchError("change-batch exclusion file schema is invalid")
    if document.get("schema_version") != 1 or document.get("purpose") != (
        "satellite_change_batch_exclusions"
    ):
        raise SatelliteChangeBatchError("change-batch exclusion file identity is invalid")
    if document.get("queue_manifest_sha256") != inputs.queue_lineage[
        "manifest_sha256"
    ]:
        raise SatelliteChangeBatchError(
            "change-batch exclusion file is bound to a different queue"
        )
    queue_ids = _validated_queue_ids(
        document.get("queue_ids"), inputs, "exclusion file queue_ids"
    )
    assert queue_ids is not None
    if list(queue_ids) != document["queue_ids"]:
        raise SatelliteChangeBatchError(
            "change-batch exclusion IDs are not in deterministic queue order"
        )
    return queue_ids, {
        "kind": "canonical_exclusion_file",
        "file": file_path.name,
        "bytes": len(raw),
        "sha256": _sha256(raw),
    }


def _build_selection(
    inputs: _Inputs,
    *,
    include_queue_ids: Sequence[str] | None,
    exclusion_file: str | Path | None,
) -> dict[str, Any]:
    included = _validated_queue_ids(
        include_queue_ids, inputs, "include_queue_ids"
    )
    excluded: tuple[str, ...] = ()
    source: dict[str, Any] | None = None
    if exclusion_file is not None:
        excluded, source = _exclusion_file(exclusion_file, inputs)
    if included is None and source is None:
        raise SatelliteChangeBatchError(
            "first run requires explicit include_queue_ids or a queue-bound exclusion file"
        )
    if included is not None and set(included) & set(excluded):
        raise SatelliteChangeBatchError(
            "included and excluded queue IDs must not overlap"
        )
    completed = set(inputs.completed_sources)
    if included is not None:
        missing = sorted(set(included) - completed)
        if missing:
            raise SatelliteChangeBatchError(
                "explicitly included queue IDs lack completed catalog jobs: "
                f"{missing}"
            )
        selected = [queue_id for queue_id in included if queue_id not in set(excluded)]
    else:
        selected = [
            job["queue_id"]
            for job in inputs.queue_jobs
            if job["queue_id"] in completed and job["queue_id"] not in set(excluded)
        ]
    if not selected:
        raise SatelliteChangeBatchError("change-batch selection contains no runnable jobs")
    excluded_completed = [queue_id for queue_id in excluded if queue_id in completed]
    not_in_inclusion = (
        len(completed - set(included)) if included is not None else 0
    )
    return {
        "mode": "explicit_inclusion" if included is not None else "exclusion_file",
        "include_queue_ids": list(included) if included is not None else None,
        "exclude_queue_ids": list(excluded),
        "selection_source": source,
        "selected_queue_ids": selected,
        "counts": {
            "catalog_completed_jobs": len(completed),
            "jobs_selected": len(selected),
            "catalog_completed_jobs_excluded": len(excluded_completed),
            "catalog_completed_jobs_not_in_inclusion": not_in_inclusion,
            "exclusion_ids_without_completed_catalog": len(excluded)
            - len(excluded_completed),
        },
    }


def _validate_selection_source(value: Any, *, required: bool) -> dict[str, Any] | None:
    if not required:
        if value is not None:
            raise SatelliteChangeBatchError(
                "saved exclusion source must be absent when no IDs are excluded"
            )
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "kind",
        "file",
        "bytes",
        "sha256",
    }:
        raise SatelliteChangeBatchError("saved exclusion source is invalid")
    if value.get("kind") != "canonical_exclusion_file":
        raise SatelliteChangeBatchError("saved exclusion source kind is invalid")
    file_name = value.get("file")
    if (
        not isinstance(file_name, str)
        or not file_name
        or file_name in {".", ".."}
        or "/" in file_name
        or "\\" in file_name
        or Path(file_name).name != file_name
    ):
        raise SatelliteChangeBatchError("saved exclusion source file is unsafe")
    _positive_integer(value.get("bytes"), "saved exclusion source bytes")
    digest = value.get("sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SatelliteChangeBatchError("saved exclusion source sha256 is invalid")
    return dict(value)


def _validate_selection(value: Any, inputs: _Inputs) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "mode",
        "include_queue_ids",
        "exclude_queue_ids",
        "selection_source",
        "selected_queue_ids",
        "counts",
    }:
        raise SatelliteChangeBatchError("change-batch selection schema is invalid")
    mode = value.get("mode")
    if mode not in {"explicit_inclusion", "exclusion_file"}:
        raise SatelliteChangeBatchError("change-batch selection mode is invalid")
    included = _validated_queue_ids(
        value.get("include_queue_ids"), inputs, "saved include_queue_ids"
    )
    excluded_value = value.get("exclude_queue_ids")
    if not isinstance(excluded_value, list):
        raise SatelliteChangeBatchError("saved exclude_queue_ids must be an array")
    excluded = _validated_queue_ids(
        excluded_value, inputs, "saved exclude_queue_ids"
    ) if excluded_value else ()
    source = _validate_selection_source(
        value.get("selection_source"), required=bool(excluded)
    )
    if mode == "explicit_inclusion":
        if included is None:
            raise SatelliteChangeBatchError("explicit inclusion has no included queue IDs")
    else:
        if included is not None or not excluded or source is None:
            raise SatelliteChangeBatchError("exclusion-file selection source is invalid")
    if included is not None and set(included) & set(excluded):
        raise SatelliteChangeBatchError("saved inclusion and exclusion IDs overlap")

    # Rebuild the exact effective inventory from copied IDs.  The source file's
    # exact hash remains provenance; execution does not depend on a mutable path.
    completed = set(inputs.completed_sources)
    if included is not None:
        if not set(included) <= completed:
            raise SatelliteChangeBatchError(
                "saved inclusion contains a job without completed catalog input"
            )
        selected = [queue_id for queue_id in included if queue_id not in set(excluded)]
    else:
        selected = [
            job["queue_id"]
            for job in inputs.queue_jobs
            if job["queue_id"] in completed and job["queue_id"] not in set(excluded)
        ]
    excluded_completed = [queue_id for queue_id in excluded if queue_id in completed]
    expected_counts = {
        "catalog_completed_jobs": len(completed),
        "jobs_selected": len(selected),
        "catalog_completed_jobs_excluded": len(excluded_completed),
        "catalog_completed_jobs_not_in_inclusion": (
            len(completed - set(included)) if included is not None else 0
        ),
        "exclusion_ids_without_completed_catalog": len(excluded)
        - len(excluded_completed),
    }
    canonical_included = list(included) if included is not None else None
    if canonical_included != value.get("include_queue_ids"):
        raise SatelliteChangeBatchError("saved inclusion order is not canonical")
    if list(excluded) != value.get("exclude_queue_ids"):
        raise SatelliteChangeBatchError("saved exclusion order is not canonical")
    if value.get("selected_queue_ids") != selected or value.get("counts") != expected_counts:
        raise SatelliteChangeBatchError("saved change-batch selection does not reproduce")
    return dict(value)


def _expected_tasks(
    inputs: _Inputs, selection: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    output_directories: set[str] = set()
    selected = set(selection["selected_queue_ids"])
    for job in inputs.queue_jobs:
        queue_id = job["queue_id"]
        if queue_id not in selected:
            continue
        source = inputs.completed_sources.get(queue_id)
        if source is None:
            continue
        catalog_index, catalog_task = source
        immutable = _immutable_task(
            job, inputs, catalog_index, catalog_task
        )
        output_directory = immutable["change_job"]["output_directory"]
        _relative_parts(output_directory, f"{queue_id} change output directory")
        if output_directory in output_directories:
            raise SatelliteChangeBatchError(
                f"change output directory is shared by multiple jobs: {output_directory}"
            )
        output_directories.add(output_directory)
        tasks[queue_id] = _task_template(immutable)
    if set(tasks) != selected:
        raise SatelliteChangeBatchError(
            "selected catalog task inventory does not match the validated queue"
        )
    return tasks


def _summary(document: Mapping[str, Any], config: ChangeBatchConfig) -> dict[str, int]:
    tasks = document["jobs"]
    counts = {
        state: sum(task.get("state") == state for task in tasks.values())
        for state in ("pending", "running", "failed", "completed")
    }
    return {
        "catalog_completed_jobs": document["selection"]["counts"][
            "catalog_completed_jobs"
        ],
        "jobs_selected": len(tasks),
        "jobs_completed": counts["completed"],
        "jobs_failed": counts["failed"],
        "jobs_pending": counts["pending"],
        "jobs_running": counts["running"],
        "jobs_exhausted": sum(
            task.get("state") == "failed"
            and task.get("attempts") >= config.max_job_attempts
            for task in tasks.values()
        ),
        "catalog_completed_jobs_excluded": document["selection"]["counts"][
            "catalog_completed_jobs_excluded"
        ],
        "catalog_completed_jobs_not_in_inclusion": document["selection"]["counts"][
            "catalog_completed_jobs_not_in_inclusion"
        ],
        "exclusion_ids_without_completed_catalog": document["selection"]["counts"][
            "exclusion_ids_without_completed_catalog"
        ],
    }


def _update_document(
    document: dict[str, Any], config: ChangeBatchConfig, updated_at: str
) -> None:
    document["updated_at"] = updated_at
    document["summary"] = _summary(document, config)
    document["state"] = (
        "completed"
        if document["summary"]["jobs_completed"]
        == document["summary"]["jobs_selected"]
        else "incomplete"
    )


def _write_checkpoint(
    output: Path,
    document: dict[str, Any],
    config: ChangeBatchConfig,
    updated_at: str,
) -> None:
    _update_document(document, config, updated_at)
    path = output / CHANGE_BATCH_MANIFEST_FILENAME
    temporary = output / f".{CHANGE_BATCH_MANIFEST_FILENAME}.tmp"
    if path.is_symlink():
        raise SatelliteChangeBatchError("change-batch manifest may not be a symlink")
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteChangeBatchError("stale change-batch checkpoint temporary exists")
    with temporary.open("xb") as destination:
        destination.write(_canonical_bytes(document))
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(output, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _new_document(
    *,
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: ChangeBatchConfig,
    selection: Mapping[str, Any],
    expected_tasks: Mapping[str, Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    document = {
        "schema_version": CHANGE_BATCH_SCHEMA_VERSION,
        "pipeline": CHANGE_BATCH_PIPELINE,
        "state": "incomplete",
        "created_at": created_at,
        "updated_at": created_at,
        "queue_bundle": dict(inputs.queue_lineage),
        "catalog_batches": [dict(value) for value in inputs.catalog_lineages],
        "processor": dict(processor),
        "configuration": config.as_dict(),
        "selection": dict(selection),
        "scope": dict(CHANGE_SCOPE),
        "jobs": {
            queue_id: json.loads(json.dumps(task))
            for queue_id, task in expected_tasks.items()
        },
        "summary": {},
        "runs": [],
    }
    _update_document(document, config, created_at)
    return document


def _failure(value: Any, queue_id: str, attempts: int) -> int:
    if not isinstance(value, Mapping) or set(value) != {
        "attempt",
        "at",
        "kind",
        "error",
    }:
        raise SatelliteChangeBatchError(f"failure record is invalid for {queue_id}")
    attempt = _positive_integer(value.get("attempt"), f"{queue_id} failure attempt")
    if attempt > attempts:
        raise SatelliteChangeBatchError(
            f"failure attempt exceeds task attempts for {queue_id}"
        )
    _timestamp(value.get("at"), f"{queue_id} failure timestamp")
    if value.get("kind") not in {
        "command_exit",
        "timeout",
        "output_validation",
        "execution_error",
        "interrupted",
    }:
        raise SatelliteChangeBatchError(f"failure kind is invalid for {queue_id}")
    if not isinstance(value.get("error"), str) or not value["error"]:
        raise SatelliteChangeBatchError(f"failure error is invalid for {queue_id}")
    if len(value["error"]) > 2_500:
        raise SatelliteChangeBatchError(f"failure error is too long for {queue_id}")
    return attempt


def _validate_runs(value: Any, tasks: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SatelliteChangeBatchError("change-batch runs must be an array")
    running = 0
    for index, run in enumerate(value, start=1):
        if not isinstance(run, dict) or set(run) != {
            "run_number",
            "state",
            "started_at",
            "finished_at",
            "interruption_recorded_at",
            "max_jobs",
            "job_attempts",
            "jobs_completed",
            "jobs_failed",
            "jobs_recovered_after_publish",
            "jobs_interrupted",
            "budget_exhausted",
        }:
            raise SatelliteChangeBatchError(f"change-batch run {index} schema is invalid")
        if run.get("run_number") != index:
            raise SatelliteChangeBatchError("change-batch run numbers are not contiguous")
        state = run.get("state")
        if state not in {"running", "completed", "interrupted"}:
            raise SatelliteChangeBatchError(f"change-batch run {index} state is invalid")
        _timestamp(run.get("started_at"), f"change-batch run {index} started_at")
        if state == "completed":
            _timestamp(run.get("finished_at"), f"change-batch run {index} finished_at")
            if run.get("interruption_recorded_at") is not None:
                raise SatelliteChangeBatchError(
                    f"completed change-batch run {index} claims interruption"
                )
        elif state == "interrupted":
            if run.get("finished_at") is not None:
                raise SatelliteChangeBatchError(
                    f"interrupted change-batch run {index} claims a finish"
                )
            _timestamp(
                run.get("interruption_recorded_at"),
                f"change-batch run {index} interruption_recorded_at",
            )
        else:
            running += 1
            if run.get("finished_at") is not None or run.get(
                "interruption_recorded_at"
            ) is not None:
                raise SatelliteChangeBatchError(
                    f"running change-batch run {index} has terminal timestamps"
                )
        _positive_integer(run.get("max_jobs"), f"change-batch run {index} max_jobs")
        for field in (
            "job_attempts",
            "jobs_completed",
            "jobs_failed",
            "jobs_recovered_after_publish",
            "jobs_interrupted",
        ):
            _nonnegative_integer(
                run.get(field), f"change-batch run {index} {field}"
            )
        if run["job_attempts"] > run["max_jobs"]:
            raise SatelliteChangeBatchError(f"change-batch run {index} exceeded its cap")
        resolved_attempts = sum(
            run[field]
            for field in (
                "jobs_completed",
                "jobs_failed",
                "jobs_recovered_after_publish",
                "jobs_interrupted",
            )
        )
        unresolved_attempts = run["job_attempts"] - resolved_attempts
        recovery_outcomes = (
            run["jobs_recovered_after_publish"] + run["jobs_interrupted"]
        )
        if state == "interrupted":
            if recovery_outcomes > 1:
                raise SatelliteChangeBatchError(
                    f"interrupted change-batch run {index} has multiple recovery outcomes"
                )
        elif recovery_outcomes != 0:
            raise SatelliteChangeBatchError(
                f"non-interrupted change-batch run {index} claims a recovery outcome"
            )
        if state == "running":
            if unresolved_attempts not in {0, 1}:
                raise SatelliteChangeBatchError(
                    f"running change-batch run {index} attempt outcomes do not reconcile"
                )
        elif unresolved_attempts != 0:
            raise SatelliteChangeBatchError(
                f"terminal change-batch run {index} attempt outcomes do not reconcile"
            )
        if not isinstance(run.get("budget_exhausted"), bool):
            raise SatelliteChangeBatchError(
                f"change-batch run {index} budget flag is invalid"
            )
    if running > 1 or (running and value[-1]["state"] != "running"):
        raise SatelliteChangeBatchError(
            "only the last change-batch run may remain running"
        )
    running_tasks = sum(task.get("state") == "running" for task in tasks.values())
    if running_tasks > 1 or (running_tasks and not running):
        raise SatelliteChangeBatchError(
            "running task inventory does not match running invocation"
        )
    return value


def _validate_checkpoint(
    document: Any,
    *,
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: ChangeBatchConfig,
    selection: Mapping[str, Any],
    expected_tasks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "pipeline",
        "state",
        "created_at",
        "updated_at",
        "queue_bundle",
        "catalog_batches",
        "processor",
        "configuration",
        "selection",
        "scope",
        "jobs",
        "summary",
        "runs",
    }:
        raise SatelliteChangeBatchError("change-batch manifest schema is invalid")
    if document.get("schema_version") != CHANGE_BATCH_SCHEMA_VERSION or document.get(
        "pipeline"
    ) != CHANGE_BATCH_PIPELINE:
        raise SatelliteChangeBatchError("change-batch manifest identity is invalid")
    if document.get("queue_bundle") != dict(inputs.queue_lineage):
        raise SatelliteChangeBatchError("change-batch queue lineage changed")
    if document.get("catalog_batches") != [
        dict(value) for value in inputs.catalog_lineages
    ]:
        raise SatelliteChangeBatchError("change-batch catalog lineage changed")
    if document.get("processor") != dict(processor):
        raise SatelliteChangeBatchError("change processor code changed")
    if document.get("configuration") != config.as_dict():
        raise SatelliteChangeBatchError("change-batch configuration changed")
    if document.get("selection") != dict(selection):
        raise SatelliteChangeBatchError("change-batch selection changed")
    if document.get("scope") != CHANGE_SCOPE:
        raise SatelliteChangeBatchError("change-batch no-inference scope changed")
    _timestamp(document.get("created_at"), "change-batch created_at")
    _timestamp(document.get("updated_at"), "change-batch updated_at")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != set(expected_tasks):
        raise SatelliteChangeBatchError(
            "change-batch task inventory changed"
        )
    mutable_fields = {
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
            raise SatelliteChangeBatchError(f"change task schema is invalid for {queue_id}")
        for field in set(expected) - mutable_fields:
            if task.get(field) != expected[field]:
                raise SatelliteChangeBatchError(
                    f"immutable change task field {field} changed for {queue_id}"
                )
        state = task.get("state")
        if state not in {"pending", "running", "failed", "completed"}:
            raise SatelliteChangeBatchError(f"change task state is invalid for {queue_id}")
        attempts = _nonnegative_integer(task.get("attempts"), f"{queue_id} attempts")
        if attempts > config.max_job_attempts:
            raise SatelliteChangeBatchError(f"change task exceeded attempt cap for {queue_id}")
        failures = task.get("failures")
        if not isinstance(failures, list) or len(failures) > attempts:
            raise SatelliteChangeBatchError(f"change task failures are invalid for {queue_id}")
        failure_attempts = [_failure(value, queue_id, attempts) for value in failures]
        expected_failure_attempts = {
            "pending": [],
            "running": list(range(1, attempts)),
            "completed": list(range(1, attempts)),
            "failed": list(range(1, attempts + 1)),
        }[state]
        if failure_attempts != expected_failure_attempts:
            raise SatelliteChangeBatchError(
                f"change task attempt outcomes do not reconcile for {queue_id}"
            )
        if state == "pending":
            if attempts != 0 or task.get("last_attempt_started_at") is not None:
                raise SatelliteChangeBatchError(
                    f"pending change task claims an attempt for {queue_id}"
                )
        else:
            if attempts == 0:
                raise SatelliteChangeBatchError(
                    f"non-pending change task has no attempt for {queue_id}"
                )
            _timestamp(
                task.get("last_attempt_started_at"),
                f"{queue_id} last_attempt_started_at",
            )
        if state == "completed":
            _timestamp(task.get("completed_at"), f"{queue_id} completed_at")
            if not isinstance(task.get("artifacts"), dict) or not isinstance(
                task.get("report"), dict
            ):
                raise SatelliteChangeBatchError(
                    f"completed change task lacks output provenance for {queue_id}"
                )
        elif any(
            task.get(field) is not None for field in ("completed_at", "artifacts", "report")
        ):
            raise SatelliteChangeBatchError(
                f"incomplete change task claims output provenance for {queue_id}"
            )
    runs = _validate_runs(document.get("runs"), jobs)
    task_attempts = sum(task["attempts"] for task in jobs.values())
    run_attempts = sum(run["job_attempts"] for run in runs)
    if run_attempts != task_attempts:
        raise SatelliteChangeBatchError(
            "change-batch run attempts do not reconcile with task attempts"
        )
    completed_tasks = sum(task["state"] == "completed" for task in jobs.values())
    completed_outcomes = sum(
        run["jobs_completed"] + run["jobs_recovered_after_publish"] for run in runs
    )
    if completed_outcomes != completed_tasks:
        raise SatelliteChangeBatchError(
            "change-batch completed outcomes do not reconcile with completed tasks"
        )
    failures = [
        failure
        for task in jobs.values()
        for failure in task["failures"]
    ]
    interrupted_failures = sum(
        failure["kind"] == "interrupted" for failure in failures
    )
    non_interrupted_failures = len(failures) - interrupted_failures
    if sum(run["jobs_interrupted"] for run in runs) != interrupted_failures:
        raise SatelliteChangeBatchError(
            "change-batch interrupted outcomes do not reconcile with interrupted failures"
        )
    if sum(run["jobs_failed"] for run in runs) != non_interrupted_failures:
        raise SatelliteChangeBatchError(
            "change-batch failed outcomes do not reconcile with non-interrupted failures"
        )
    if document.get("summary") != _summary(document, config):
        raise SatelliteChangeBatchError("change-batch summary does not reproduce")
    expected_state = (
        "completed"
        if document["summary"]["jobs_completed"]
        == document["summary"]["jobs_selected"]
        else "incomplete"
    )
    if document.get("state") != expected_state:
        raise SatelliteChangeBatchError("change-batch state does not match task states")
    return document


def _stage_directory(final: Path) -> Path:
    return final.with_name(f".{final.name}.staging")


def _clear_stage(stage: Path) -> None:
    if stage.is_symlink():
        raise SatelliteChangeBatchError(f"change staging path may not be a symlink: {stage}")
    if not stage.exists():
        return
    if not stage.is_dir():
        raise SatelliteChangeBatchError(f"change staging path is not a directory: {stage}")
    for path in stage.rglob("*"):
        if path.is_symlink():
            raise SatelliteChangeBatchError(
                f"change staging tree contains a symlink: {path}"
            )
    shutil.rmtree(stage)


def _prepare_parent(output: Path, final: Path) -> None:
    relative = final.relative_to(output)
    current = output
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise SatelliteChangeBatchError(
                f"change output parent may not be a symlink: {current}"
            )
        if current.exists() and not current.is_dir():
            raise SatelliteChangeBatchError(
                f"change output parent is not a directory: {current}"
            )
        current.mkdir(exist_ok=True)


def _fsync_tree(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise SatelliteChangeBatchError(
                f"change staging output is not a closed regular-file set: {path}"
            )
        with path.open("rb") as source:
            os.fsync(source.fileno())
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _complete_task(
    task: dict[str, Any], result: Mapping[str, Any], completed_at: str
) -> None:
    task.update(
        {
            "state": "completed",
            "completed_at": completed_at,
            "artifacts": result["artifacts"],
            "report": result["report"],
        }
    )


def _record_failure(
    task: dict[str, Any], *, at: str, kind: str, error: str
) -> None:
    message = error.strip() or kind
    task["failures"].append(
        {
            "attempt": task["attempts"],
            "at": at,
            "kind": kind,
            "error": message[-2_500:],
        }
    )
    task["state"] = "failed"


def _task_paths(
    output: Path, task: Mapping[str, Any]
) -> tuple[Path, Path]:
    final = _safe_child(
        output,
        task["change_job"]["output_directory"],
        f"{task['queue_id']} change output directory",
    )
    return final, _stage_directory(final)


def _catalog_root(inputs: _Inputs, task: Mapping[str, Any]) -> Path:
    index = task["catalog_source"]["catalog_batch_index"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(
        inputs.catalog_roots
    ):
        raise SatelliteChangeBatchError(
            f"catalog source index is invalid for {task['queue_id']}"
        )
    return inputs.catalog_roots[index]


def _verify_catalog_artifacts(task: Mapping[str, Any], catalog_root: Path) -> None:
    source = task["catalog_source"]
    artifacts = source.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "baseline-response.json",
        "current-response.json",
        "manifest.json",
    }:
        raise SatelliteChangeBatchError(
            f"catalog artifact lineage is invalid for {task['queue_id']}"
        )
    directory = source["catalog_output_directory"]
    for name, expected in artifacts.items():
        path = _regular_file(
            catalog_root,
            f"{directory}/{name}",
            f"{task['queue_id']} catalog artifact {name}",
        )
        if _file_record(path) != expected:
            raise SatelliteChangeBatchError(
                f"catalog artifact changed for {task['queue_id']}/{name}"
            )


def _verify_input_manifest_bytes(inputs: _Inputs) -> None:
    queue_manifest = _regular_file(
        inputs.queue, QUEUE_MANIFEST_FILENAME, "queue manifest"
    )
    queue_file = _regular_file(inputs.queue, QUEUE_FILENAME, "queue JSONL")
    if _file_record(queue_manifest) != {
        "bytes": inputs.queue_lineage["manifest_bytes"],
        "sha256": inputs.queue_lineage["manifest_sha256"],
    } or _file_record(queue_file) != {
        "bytes": inputs.queue_lineage["queue_bytes"],
        "sha256": inputs.queue_lineage["queue_sha256"],
    }:
        raise SatelliteChangeBatchError("immutable queue bytes changed during execution")
    for index, (root, lineage) in enumerate(
        zip(inputs.catalog_roots, inputs.catalog_lineages, strict=True)
    ):
        path = _regular_file(
            root,
            CATALOG_BATCH_MANIFEST_FILENAME,
            f"catalog batch {index} manifest",
        )
        if _file_record(path) != {
            "bytes": lineage["manifest_bytes"],
            "sha256": lineage["manifest_sha256"],
        }:
            raise SatelliteChangeBatchError(
                f"catalog batch {index} manifest changed during execution"
            )


def _validate_output_tree(
    output: Path, document: Mapping[str, Any], inputs: _Inputs
) -> None:
    allowed_directories: set[Path] = {output}
    allowed_files: set[Path] = {output / CHANGE_BATCH_MANIFEST_FILENAME}
    running_stages: list[Path] = []
    for task in document["jobs"].values():
        final, stage = _task_paths(output, task)
        current = final.parent
        while current != output:
            allowed_directories.add(current)
            current = current.parent
        state = task["state"]
        if state == "completed":
            result = _change_result(task, final, _catalog_root(inputs, task))
            if task["artifacts"] != result["artifacts"] or task["report"] != result[
                "report"
            ]:
                raise SatelliteChangeBatchError(
                    f"completed change output changed for {task['queue_id']}"
                )
            allowed_directories.add(final)
            allowed_files.update(final / name for name in CHANGE_FILES)
            if stage.exists() or stage.is_symlink():
                raise SatelliteChangeBatchError(
                    f"completed change task has staging residue: {task['queue_id']}"
                )
        elif state == "running":
            if final.exists() or final.is_symlink():
                # Atomic publication can precede its checkpoint.  Validate it as
                # recoverable output but do not silently adopt it here.
                _change_result(task, final, _catalog_root(inputs, task))
                allowed_directories.add(final)
                allowed_files.update(final / name for name in CHANGE_FILES)
            elif stage.exists() or stage.is_symlink():
                if stage.is_symlink() or not stage.is_dir():
                    raise SatelliteChangeBatchError(
                        f"running change stage is not a regular directory: {stage}"
                    )
                running_stages.append(stage)
                allowed_directories.add(stage)
                for path in stage.rglob("*"):
                    if path.is_symlink() or not path.is_file():
                        raise SatelliteChangeBatchError(
                            f"running change stage contains a non-regular path: {path}"
                        )
                    allowed_files.add(path)
            if final.exists() and stage.exists():
                raise SatelliteChangeBatchError(
                    f"running change task has both final and staging output: {task['queue_id']}"
                )
        elif final.exists() or final.is_symlink() or stage.exists() or stage.is_symlink():
            raise SatelliteChangeBatchError(
                f"non-running incomplete task has unexpected output: {task['queue_id']}"
            )

    for path in output.rglob("*"):
        if path.is_symlink():
            raise SatelliteChangeBatchError(f"change-batch output contains a symlink: {path}")
        if path.is_dir():
            if path not in allowed_directories:
                raise SatelliteChangeBatchError(
                    f"change-batch output contains an unexpected directory: {path}"
                )
        elif path.is_file():
            if path not in allowed_files:
                raise SatelliteChangeBatchError(
                    f"change-batch output contains an unexpected file: {path}"
                )
        else:
            raise SatelliteChangeBatchError(
                f"change-batch output contains a non-regular path: {path}"
            )


def _command(
    task: Mapping[str, Any],
    *,
    catalog_root: Path,
    stage: Path,
    package_root: Path,
) -> list[str]:
    _verify_catalog_artifacts(task, catalog_root)
    _load_selected_stac(task, catalog_root)
    script = _regular_file(
        package_root, task["change_job"]["script"], "change processor script"
    )
    arguments = list(task["change_job"]["arguments"])
    parsed = _argument_pairs(arguments, f"{task['queue_id']} resolved arguments")
    replacements = {
        "--baseline-stac": str(
            _regular_file(
                catalog_root,
                parsed["--baseline-stac"],
                f"{task['queue_id']} baseline STAC input",
            ).resolve()
        ),
        "--current-stac": str(
            _regular_file(
                catalog_root,
                parsed["--current-stac"],
                f"{task['queue_id']} current STAC input",
            ).resolve()
        ),
        "--output-dir": str(stage.resolve(strict=False)),
    }
    for flag, replacement in replacements.items():
        value_index = arguments.index(flag) + 1
        arguments[value_index] = replacement
    bbox_index = arguments.index("--bbox")
    bbox_value = arguments[bbox_index + 1]
    arguments[bbox_index : bbox_index + 2] = [f"--bbox={bbox_value}"]
    return [sys.executable, str(script), *arguments]


def _recover_interrupted_run(
    output: Path,
    document: dict[str, Any],
    inputs: _Inputs,
    config: ChangeBatchConfig,
    recovered_at: str,
) -> None:
    if not document["runs"] or document["runs"][-1]["state"] != "running":
        return
    run = document["runs"][-1]
    running_tasks = [
        task for task in document["jobs"].values() if task["state"] == "running"
    ]
    if len(running_tasks) > 1:
        raise SatelliteChangeBatchError("multiple change tasks were left running")
    if running_tasks:
        task = running_tasks[0]
        final, stage = _task_paths(output, task)
        if final.exists() or final.is_symlink():
            if stage.exists() or stage.is_symlink():
                raise SatelliteChangeBatchError(
                    "interrupted change task has both final and staging output"
                )
            result = _change_result(task, final, _catalog_root(inputs, task))
            _complete_task(task, result, recovered_at)
            run["jobs_recovered_after_publish"] += 1
        else:
            if stage.exists() or stage.is_symlink():
                _clear_stage(stage)
            _record_failure(
                task,
                at=recovered_at,
                kind="interrupted",
                error="interrupted before atomic change output publication was checkpointed",
            )
            run["jobs_interrupted"] += 1
    run["state"] = "interrupted"
    run["interruption_recorded_at"] = recovered_at
    _write_checkpoint(output, document, config, recovered_at)


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeBatchError("change-batch manifest is not a regular file")
    raw = path.read_bytes()
    document = _decode_json(raw, "change-batch manifest")
    if not isinstance(document, dict) or raw != _canonical_bytes(document):
        raise SatelliteChangeBatchError("change-batch manifest is not canonical JSON")
    return document


def _saved_context(
    document: Mapping[str, Any], inputs: _Inputs
) -> tuple[ChangeBatchConfig, dict[str, Any], dict[str, dict[str, Any]]]:
    config = _config_from_document(document.get("configuration"))
    selection = _validate_selection(document.get("selection"), inputs)
    expected_tasks = _expected_tasks(inputs, selection)
    return config, selection, expected_tasks


def _separate_output(output: Path, inputs: _Inputs) -> None:
    output_resolved = output.resolve(strict=False)
    for label, root in (
        ("queue bundle", inputs.queue),
        *(
            (f"catalog batch {index}", root)
            for index, root in enumerate(inputs.catalog_roots)
        ),
    ):
        resolved = root.resolve()
        if (
            output_resolved == resolved
            or resolved in output_resolved.parents
            or output_resolved in resolved.parents
        ):
            raise SatelliteChangeBatchError(
                f"change-batch output must be separate from {label}"
            )


@contextmanager
def _directory_lock(directory: Path, *, exclusive: bool):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    locked = False
    try:
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise SatelliteChangeBatchError(
                    "change-batch output directory lock could not be acquired"
                ) from error
            mode = "execution" if exclusive else "validation"
            raise SatelliteChangeBatchError(
                f"change-batch output is locked by another invocation; {mode} cannot start"
            ) from error
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def validate_satellite_change_batch(
    queue_directory: str | Path,
    catalog_batch_directories: Sequence[str | Path],
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    include_queue_ids: Sequence[str] | None = None,
    exclusion_file: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a closed output tree while holding a non-blocking shared lock."""

    inputs = _validated_inputs(queue_directory, catalog_batch_directories)
    output = _absolute_directory(
        output_directory, "change-batch output", must_exist=True
    )
    _separate_output(output, inputs)
    with _directory_lock(output, exclusive=False):
        return _validate_satellite_change_batch_locked(
            queue_directory,
            catalog_batch_directories,
            output_directory,
            config=config,
            include_queue_ids=include_queue_ids,
            exclusion_file=exclusion_file,
        )


def _validate_satellite_change_batch_locked(
    queue_directory: str | Path,
    catalog_batch_directories: Sequence[str | Path],
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    include_queue_ids: Sequence[str] | None = None,
    exclusion_file: str | Path | None = None,
) -> dict[str, Any]:
    """Validate all queue, catalog, checkpoint, and completed outputs offline."""

    inputs = _validated_inputs(queue_directory, catalog_batch_directories)
    package_root = Path(__file__).resolve().parents[1]
    processor = _processor_lineage(package_root)
    output = _absolute_directory(
        output_directory, "change-batch output", must_exist=True
    )
    _separate_output(output, inputs)
    temporary = output / f".{CHANGE_BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteChangeBatchError(
            "change-batch output contains an unfinished checkpoint temporary"
        )
    document = _load_checkpoint(output / CHANGE_BATCH_MANIFEST_FILENAME)
    saved_config, selection, expected_tasks = _saved_context(document, inputs)
    if config is not None:
        if not isinstance(config, ChangeBatchConfig) or config != saved_config:
            raise SatelliteChangeBatchError(
                "saved change-batch configuration differs from expected"
            )
    if include_queue_ids is not None or exclusion_file is not None:
        supplied = _build_selection(
            inputs,
            include_queue_ids=include_queue_ids,
            exclusion_file=exclusion_file,
        )
        if supplied != selection:
            raise SatelliteChangeBatchError(
                "saved change-batch selection differs from supplied selection"
            )
    document = _validate_checkpoint(
        document,
        inputs=inputs,
        processor=processor,
        config=saved_config,
        selection=selection,
        expected_tasks=expected_tasks,
    )
    _validate_output_tree(output, document, inputs)
    return document


def execute_satellite_change_batch(
    queue_directory: str | Path,
    catalog_batch_directories: Sequence[str | Path],
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    include_queue_ids: Sequence[str] | None = None,
    exclusion_file: str | Path | None = None,
    max_jobs: int = 1,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Execute one bounded invocation under an output-directory OS lock."""

    _positive_integer(max_jobs, "max_jobs")
    if config is not None and not isinstance(config, ChangeBatchConfig):
        raise SatelliteChangeBatchError("config must be a ChangeBatchConfig")
    inputs = _validated_inputs(queue_directory, catalog_batch_directories)
    output = _absolute_directory(
        output_directory, "change-batch output", must_exist=False
    )
    _separate_output(output, inputs)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangeBatchError("change-batch output is not a regular directory")
    with _directory_lock(output, exclusive=True):
        return _execute_satellite_change_batch_locked(
            queue_directory,
            catalog_batch_directories,
            output_directory,
            config=config,
            include_queue_ids=include_queue_ids,
            exclusion_file=exclusion_file,
            max_jobs=max_jobs,
            command_runner=command_runner,
            sleep=sleep,
            timestamp=timestamp,
        )


def _execute_satellite_change_batch_locked(
    queue_directory: str | Path,
    catalog_batch_directories: Sequence[str | Path],
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    include_queue_ids: Sequence[str] | None = None,
    exclusion_file: str | Path | None = None,
    max_jobs: int = 1,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Run a bounded sequential change batch and atomically checkpoint each job.

    First creation requires an explicit inclusion or a canonical queue-bound
    exclusion file.  Later invocations may omit both and resume the selection
    copied into the manifest.
    """

    max_jobs = _positive_integer(max_jobs, "max_jobs")
    if config is not None and not isinstance(config, ChangeBatchConfig):
        raise SatelliteChangeBatchError("config must be a ChangeBatchConfig")
    inputs = _validated_inputs(queue_directory, catalog_batch_directories)
    package_root = Path(__file__).resolve().parents[1]
    processor = _processor_lineage(package_root)
    output = _absolute_directory(
        output_directory, "change-batch output", must_exist=False
    )
    _separate_output(output, inputs)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangeBatchError("change-batch output is not a regular directory")
    checkpoint = output / CHANGE_BATCH_MANIFEST_FILENAME
    temporary = output / f".{CHANGE_BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_symlink() or not temporary.is_file():
            raise SatelliteChangeBatchError(
                "change-batch checkpoint temporary is not a regular file"
            )
        temporary.unlink()

    started_at = _timestamp(timestamp(), "change-batch invocation started_at")
    if checkpoint.exists() or checkpoint.is_symlink():
        document = _load_checkpoint(checkpoint)
        saved_config, selection, expected_tasks = _saved_context(document, inputs)
        if config is not None and config != saved_config:
            raise SatelliteChangeBatchError(
                "saved change-batch configuration differs from requested configuration"
            )
        config = saved_config
        if include_queue_ids is not None or exclusion_file is not None:
            supplied = _build_selection(
                inputs,
                include_queue_ids=include_queue_ids,
                exclusion_file=exclusion_file,
            )
            if supplied != selection:
                raise SatelliteChangeBatchError(
                    "saved change-batch selection differs from requested selection"
                )
        document = _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
        )
        _validate_output_tree(output, document, inputs)
        _recover_interrupted_run(
            output, document, inputs, config, started_at
        )
        document = _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
        )
        _validate_output_tree(output, document, inputs)
    else:
        if any(output.iterdir()):
            raise SatelliteChangeBatchError(
                "change-batch output contains files without a checkpoint manifest"
            )
        config = config or ChangeBatchConfig()
        selection = _build_selection(
            inputs,
            include_queue_ids=include_queue_ids,
            exclusion_file=exclusion_file,
        )
        expected_tasks = _expected_tasks(inputs, selection)
        document = _new_document(
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
            created_at=started_at,
        )
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
        "jobs_recovered_after_publish": 0,
        "jobs_interrupted": 0,
        "budget_exhausted": False,
    }
    document["runs"].append(run)
    _write_checkpoint(output, document, config, started_at)

    invoked = False
    for queue_id in selection["selected_queue_ids"]:
        task = document["jobs"][queue_id]
        if task["state"] == "completed" or task["attempts"] >= config.max_job_attempts:
            continue
        if run["job_attempts"] >= max_jobs:
            run["budget_exhausted"] = True
            break
        if invoked and config.minimum_interval_seconds:
            sleep(config.minimum_interval_seconds)
        invoked = True
        _verify_input_manifest_bytes(inputs)
        if _processor_lineage(package_root) != document["processor"]:
            raise SatelliteChangeBatchError(
                "change processor code or numerical runtime changed during execution"
            )
        final, stage = _task_paths(output, task)
        if final.exists() or final.is_symlink():
            raise SatelliteChangeBatchError(
                f"refusing to overwrite change output for {queue_id}: {final}"
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
            command = _command(
                task,
                catalog_root=_catalog_root(inputs, task),
                stage=stage,
                package_root=package_root,
            )
            completed = command_runner(
                command,
                cwd=package_root,
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
                failure_detail = f"change command exited {completed.returncode}"
                if detail:
                    failure_detail += ": " + detail[-2_000:]
            else:
                result = _change_result(task, stage, _catalog_root(inputs, task))
                _fsync_tree(stage)
                if _change_result(
                    task, stage, _catalog_root(inputs, task)
                ) != result:
                    raise SatelliteChangeBatchError(
                        "validated change output changed before atomic publication"
                    )
                _verify_input_manifest_bytes(inputs)
                if _processor_lineage(package_root) != document["processor"]:
                    raise SatelliteChangeBatchError(
                        "change processor code or numerical runtime changed during the job"
                    )
                os.replace(stage, final)
                parent_fd = os.open(final.parent, os.O_RDONLY)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                completed_at = _timestamp(
                    timestamp(), f"{queue_id} completion timestamp"
                )
                _complete_task(task, result, completed_at)
                run["jobs_completed"] += 1
        except subprocess.TimeoutExpired as error:
            failure_kind = "timeout"
            failure_detail = (
                f"change command exceeded {config.timeout_seconds:g} seconds: {error}"
            )
        except SatelliteChangeBatchError as error:
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
        checkpoint_at = _timestamp(timestamp(), f"{queue_id} checkpoint timestamp")
        _write_checkpoint(output, document, config, checkpoint_at)

    finished_at = _timestamp(timestamp(), "change-batch invocation finished_at")
    run["state"] = "completed"
    run["finished_at"] = finished_at
    _write_checkpoint(output, document, config, finished_at)
    document = _validate_checkpoint(
        document,
        inputs=inputs,
        processor=processor,
        config=config,
        selection=selection,
        expected_tasks=expected_tasks,
    )
    _validate_output_tree(output, document, inputs)
    return document





def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangeBatchError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SatelliteChangeBatchError(f"{field} must be finite")
    return result


def _png_dimensions(path: Path, label: str) -> tuple[int, int]:
    raw = path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SatelliteChangeBatchError(f"{label} is not a PNG")
    position = 8
    width: int | None = None
    height: int | None = None
    saw_end = False
    chunk_index = 0
    while position < len(raw):
        if len(raw) - position < 12:
            raise SatelliteChangeBatchError(f"{label} has a truncated PNG chunk")
        length = struct.unpack(">I", raw[position : position + 4])[0]
        chunk_type = raw[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(raw):
            raise SatelliteChangeBatchError(f"{label} has a truncated PNG payload")
        data = raw[position + 8 : position + 8 + length]
        stored_crc = struct.unpack(">I", raw[position + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != stored_crc:
            raise SatelliteChangeBatchError(f"{label} has a PNG CRC mismatch")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                raise SatelliteChangeBatchError(f"{label} lacks a valid PNG IHDR")
            width, height = struct.unpack(">II", data[:8])
            if width <= 0 or height <= 0:
                raise SatelliteChangeBatchError(f"{label} has invalid PNG dimensions")
        if chunk_type == b"IEND":
            if length != 0 or end != len(raw):
                raise SatelliteChangeBatchError(f"{label} has an invalid PNG IEND")
            saw_end = True
            break
        position = end
        chunk_index += 1
    if not saw_end or width is None or height is None:
        raise SatelliteChangeBatchError(f"{label} is an incomplete PNG")
    return width, height


def _validate_position(
    value: Any,
    label: str,
    aoi_bbox: tuple[float, float, float, float],
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise SatelliteChangeBatchError(f"{label} must be a two-coordinate position")
    longitude = _finite_number(value[0], f"{label} longitude")
    latitude = _finite_number(value[1], f"{label} latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise SatelliteChangeBatchError(f"{label} is outside WGS84 bounds")

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
        raise SatelliteChangeBatchError(
            f"{label} is outside the queue AOI (beyond the 25 m pixel-edge tolerance)"
        )


def _validate_ring(
    value: Any,
    label: str,
    aoi_bbox: tuple[float, float, float, float],
) -> None:
    if not isinstance(value, list) or len(value) < 4:
        raise SatelliteChangeBatchError(f"{label} must contain at least four positions")
    for index, position in enumerate(value):
        _validate_position(position, f"{label} position {index}", aoi_bbox)
    if value[0] != value[-1]:
        raise SatelliteChangeBatchError(f"{label} is not closed")


def _validate_geometry(
    value: Any,
    label: str,
    aoi_bbox: tuple[float, float, float, float],
) -> None:
    if not isinstance(value, Mapping) or set(value) != {"type", "coordinates"}:
        raise SatelliteChangeBatchError(f"{label} schema is invalid")
    kind = value.get("type")
    coordinates = value.get("coordinates")
    if kind == "Polygon":
        polygons = [coordinates]
    elif kind == "MultiPolygon":
        polygons = coordinates
    else:
        raise SatelliteChangeBatchError(f"{label} must be Polygon or MultiPolygon")
    if not isinstance(polygons, list) or not polygons:
        raise SatelliteChangeBatchError(f"{label} has no polygons")
    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise SatelliteChangeBatchError(
                f"{label} polygon {polygon_index} has no rings"
            )
        for ring_index, ring in enumerate(polygon):
            _validate_ring(
                ring,
                f"{label} polygon {polygon_index} ring {ring_index}",
                aoi_bbox,
            )


def _validate_geojson(
    path: Path,
    *,
    expected_count: int,
    expected_area_m2: float,
    minimum_component_area_m2: float,
    aoi_bbox: tuple[float, float, float, float],
) -> None:
    raw = path.read_bytes()
    document = _decode_json(raw, "change proposals GeoJSON")
    if raw != _canonical_external_json(document):
        raise SatelliteChangeBatchError("change proposals GeoJSON is not canonical JSON")
    if not isinstance(document, Mapping) or set(document) != {
        "type",
        "features",
        "properties",
    }:
        raise SatelliteChangeBatchError("change proposals GeoJSON schema is invalid")
    if document.get("type") != "FeatureCollection":
        raise SatelliteChangeBatchError("change proposals must be a FeatureCollection")
    if document.get("properties") != GEOJSON_COLLECTION_PROPERTIES:
        raise SatelliteChangeBatchError(
            "change proposals lost their proposal-only scope"
        )
    features = document.get("features")
    if not isinstance(features, list) or len(features) != expected_count:
        raise SatelliteChangeBatchError(
            "change proposal feature count differs from the report"
        )
    area_total = 0.0
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
    for index, feature in enumerate(features, start=1):
        label = f"change proposal {index}"
        if not isinstance(feature, Mapping) or set(feature) != {
            "type",
            "id",
            "geometry",
            "properties",
        }:
            raise SatelliteChangeBatchError(f"{label} schema is invalid")
        if feature.get("type") != "Feature" or feature.get("id") != (
            f"change-proposal-{index}"
        ):
            raise SatelliteChangeBatchError(f"{label} identity is invalid")
        _validate_geometry(feature.get("geometry"), f"{label} geometry", aoi_bbox)
        properties = feature.get("properties")
        if not isinstance(properties, Mapping) or set(properties) != expected_properties:
            raise SatelliteChangeBatchError(f"{label} properties schema is invalid")
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
            raise SatelliteChangeBatchError(
                f"{label} lost its proposal-only classification"
            )
        area = _nonnegative_number(properties.get("area_m2"), f"{label} area_m2")
        if area < minimum_component_area_m2:
            raise SatelliteChangeBatchError(
                f"{label} is below the queue's minimum component area"
            )
        area_total += area
    if round(area_total, 1) != round(expected_area_m2, 1):
        raise SatelliteChangeBatchError(
            "change proposal areas do not reproduce the report total"
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
        raise SatelliteChangeBatchError("change report metrics schema is invalid")
    result = dict(value)
    for field in sorted(expected - {"proposal_component_count"}):
        _finite_number(result[field], f"change report metric {field}")
    for field in ("valid_pixel_fraction", "proposal_pixel_fraction_of_valid"):
        if not 0 <= float(result[field]) <= 1:
            raise SatelliteChangeBatchError(f"change report metric {field} is outside [0, 1]")
    count = result["proposal_component_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise SatelliteChangeBatchError(
            "change report proposal_component_count must be a non-negative integer"
        )
    if float(result["proposal_area_m2_after_component_filter"]) < 0:
        raise SatelliteChangeBatchError("change report proposal area must be non-negative")
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
        raise SatelliteChangeBatchError("change report threshold schema is invalid")
    for field in expected:
        _finite_number(value[field], f"change report threshold {field}")
    if not 0 < float(value["adaptive_quantile"]) < 1:
        raise SatelliteChangeBatchError("change report adaptive quantile is invalid")
    if float(value["minimum_absolute_reflectance_change"]) <= 0 or float(
        value["applied_absolute_reflectance_change"]
    ) <= 0:
        raise SatelliteChangeBatchError("change report reflectance thresholds are invalid")


def _load_selected_stac(
    task: Mapping[str, Any], catalog_root: Path
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    arguments = _argument_pairs(
        task["change_job"]["arguments"],
        f"{task['queue_id']} resolved change arguments",
    )
    baseline_path = _regular_file(
        catalog_root,
        arguments["--baseline-stac"],
        f"{task['queue_id']} baseline STAC response",
    )
    current_path = _regular_file(
        catalog_root,
        arguments["--current-stac"],
        f"{task['queue_id']} current STAC response",
    )
    try:
        baseline = select_feature(
            _decode_json(baseline_path.read_bytes(), "baseline STAC response"),
            arguments["--baseline-id"],
        )
        current = select_feature(
            _decode_json(current_path.read_bytes(), "current STAC response"),
            arguments["--current-id"],
        )
        ensure_comparable(baseline, current)
    except (TypeError, ValueError) as error:
        raise SatelliteChangeBatchError(
            f"selected STAC inputs are invalid for {task['queue_id']}: {error}"
        ) from error
    return baseline, current


def _change_result(
    task: Mapping[str, Any], directory: Path, catalog_root: Path
) -> dict[str, Any]:
    queue_id = task["queue_id"]
    _verify_catalog_artifacts(task, catalog_root)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeBatchError(
            f"change output is not a regular directory for {queue_id}"
        )
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SatelliteChangeBatchError(
            f"change output contains a non-regular file for {queue_id}"
        )
    if {entry.name for entry in entries} != CHANGE_FILES:
        raise SatelliteChangeBatchError(
            f"change output file set does not match the contract for {queue_id}"
        )

    report_path = directory / "report.json"
    report_raw = report_path.read_bytes()
    report = _decode_json(report_raw, f"{queue_id} change report")
    if report_raw != _canonical_external_json(report):
        raise SatelliteChangeBatchError(
            f"change report is not canonical JSON for {queue_id}"
        )
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
    if not isinstance(report, Mapping) or set(report) != expected_report_keys:
        raise SatelliteChangeBatchError(f"change report schema is invalid for {queue_id}")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION or report.get(
        "algorithm_version"
    ) != ALGORITHM_VERSION:
        raise SatelliteChangeBatchError(f"change report version changed for {queue_id}")
    arguments = _argument_pairs(
        task["change_job"]["arguments"], f"{queue_id} resolved change arguments"
    )
    if report.get("entity") != task["entity"] or report.get(
        "aoi_bbox_wgs84"
    ) != list(parse_bbox(arguments["--bbox"])):
        raise SatelliteChangeBatchError(
            f"change report entity or AOI differs from the queue for {queue_id}"
        )
    baseline, current = _load_selected_stac(task, catalog_root)
    if report.get("baseline") != item_summary(baseline) or report.get(
        "current"
    ) != item_summary(current):
        raise SatelliteChangeBatchError(
            f"change report scene lineage differs from exact STAC inputs for {queue_id}"
        )
    if report.get("source") != report_source(baseline, current):
        raise SatelliteChangeBatchError(f"change report source changed for {queue_id}")
    if report.get("classification") != REPORT_CLASSIFICATION:
        raise SatelliteChangeBatchError(
            f"change report lost its no-inference scope for {queue_id}"
        )
    if report.get("radiometry") != {
        "reflectance": "STAC raster scale and offset applied per scene and band",
        "normalized_index_negative_reflectance_policy": "clip_to_zero",
    }:
        raise SatelliteChangeBatchError(f"change report radiometry changed for {queue_id}")
    _validate_thresholds(report.get("thresholds"))
    metrics = _report_metrics(report.get("metrics"))

    outputs = report.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != REPORT_BOUND_FILES:
        raise SatelliteChangeBatchError(
            f"change report output inventory changed for {queue_id}"
        )
    for name in sorted(REPORT_BOUND_FILES):
        record = outputs[name]
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise SatelliteChangeBatchError(
                f"change report output record is invalid for {queue_id}/{name}"
            )
        if dict(record) != _file_record(directory / name):
            raise SatelliteChangeBatchError(
                f"change report-bound artifact changed for {queue_id}/{name}"
            )

    grid = report.get("grid")
    if not isinstance(grid, Mapping) or set(grid) != {
        "crs",
        "width",
        "height",
        "pixel_area_m2",
        "clear_scl_classes",
    }:
        raise SatelliteChangeBatchError(f"change report grid schema is invalid for {queue_id}")
    width = _positive_integer(grid.get("width"), f"{queue_id} grid width")
    height = _positive_integer(grid.get("height"), f"{queue_id} grid height")
    _positive_number(grid.get("pixel_area_m2"), f"{queue_id} pixel area")
    if not isinstance(grid.get("crs"), str) or not grid["crs"] or grid.get(
        "clear_scl_classes"
    ) != sorted(CLEAR_SCL_CLASSES):
        raise SatelliteChangeBatchError(f"change report grid values are invalid for {queue_id}")
    for name in ("before.png", "after.png", "change-overlay.png"):
        if _png_dimensions(directory / name, f"{queue_id}/{name}") != (width, height):
            raise SatelliteChangeBatchError(
                f"PNG dimensions differ from report grid for {queue_id}/{name}"
            )
    if _png_dimensions(
        directory / "comparison.png", f"{queue_id}/comparison.png"
    ) != (width * 3, height):
        raise SatelliteChangeBatchError(
            f"comparison PNG dimensions are invalid for {queue_id}"
        )

    minimum_area = _positive_number(
        float(arguments["--minimum-component-area-m2"]),
        f"{queue_id} minimum component area",
    )
    _validate_geojson(
        directory / "change-proposals.geojson",
        expected_count=metrics["proposal_component_count"],
        expected_area_m2=float(metrics["proposal_area_m2_after_component_filter"]),
        minimum_component_area_m2=minimum_area,
        aoi_bbox=parse_bbox(arguments["--bbox"]),
    )
    _verify_catalog_artifacts(task, catalog_root)
    return {
        "artifacts": {
            name: _file_record(directory / name) for name in sorted(CHANGE_FILES)
        },
        "report": {
            "algorithm_version": report["algorithm_version"],
            "classification": dict(report["classification"]),
            "metrics": metrics,
            "report_sha256": _sha256(report_raw),
        },
    }
