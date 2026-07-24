"""Atomic successor runner for six uniquely reselected v57 singleton jobs.

The numerical processor is the unchanged Sentinel mosaic-v3 CLI, invoked with
one explicitly hash-bound item per epoch and no companion flags.  This module
does not reopen catalog selection and does not weaken the v3 overlap policy.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from .satellite_change import (
    CLEAR_SCL_CLASSES,
    item_summary,
    parse_bbox,
    report_source,
)
from .satellite_change_mosaic import (
    ALGORITHM_VERSION,
    MAX_COMPANION_TIME_DELTA_SECONDS,
    REPORT_SCHEMA_VERSION,
    SPECTRAL_CORE_ALGORITHM_VERSION,
    SentinelMosaicContractError,
    parse_item_binding,
    select_bound_items,
)
from .satellite_change_singleton_preparation_v2 import (
    DEFINITION_PATH as PREPARATION_DEFINITION_PATH,
    EXPECTED_QUEUE_IDS,
    EXPECTED_QUEUE_POSITIONS,
    OUTPUT_PATH as PREPARATION_DIRECTORY_PATH,
    READY_FILENAME,
    SatelliteChangeSingletonPreparationV2Error,
    validate_satellite_change_singleton_preparation_v2,
)
from . import satellite_change_mosaic_batch_v1 as validation_base
from scripts.sentinel_change_mosaic import REPORT_CLASSIFICATION


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = Path(
    "satellite_change_runs/"
    "2026-07-20-open-seed-v57-active-singleton-v2-001"
)
BATCH_MANIFEST_FILENAME = "batch-manifest.json"
FREEZE_MANIFEST_FILENAME = "freeze.json"
FREEZE_SHA256_FILENAME = "freeze.sha256"
BATCH_FORMAT = "datacenter-atlas-satellite-change-singleton-batch-v2"
BATCH_SCHEMA_VERSION = 2
BATCH_PIPELINE = "satellite_review_change_singleton_batch_v2"
PREPARATION_DEFINITION_SHA256 = (
    "a99b9ee8e96d7cf9a4edc079b1f48afe21152a6332428dbeba9fbfbd28dcaa67"
)
PREPARATION_MANIFEST_SHA256 = (
    "def22b2a8db66c66515c91f1143c86f95b7e1905e1175304294e72c6b45f0183"
)
PREPARATION_READY_SHA256 = (
    "338b04682cceaaf87b76a795531855c38b480cbeeda837e68bc893adcbcd1b1e"
)
PREPARATION_TREE_SHA256 = (
    "da4a864024ba7ff800a3f81a322d0040bb72c52ee45742bdcc9f7b36133de6b7"
)
DEFAULT_TIMEOUT_SECONDS = 1_800.0
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1
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
    "datacenter_atlas/satellite_change_singleton_batch_v2.py",
    "satellite_change_singleton_batch_v2.py",
    "scripts/run_satellite_change_singleton_batch_v2.py",
    "datacenter_atlas/satellite_change_mosaic.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/models.py",
    "scripts/sentinel_change_mosaic.py",
)
SCOPE = {
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "candidate_scope": "v1_prepared_selected_item_bindings_only",
    "catalog_rediscovery": False,
    "catalog_reranking": False,
    "imagery_construction_status_inference": False,
    "imagery_construction_truth_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_energy_inference": False,
    "imagery_identity_inference": False,
    "imagery_it_capacity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_operator_inference": False,
    "imagery_power_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "mode": "visible_change_proposals_only",
    "review_required": True,
    "selected_items_per_epoch": 1,
    "unique_site_claim_created": False,
}


class SatelliteChangeSingletonBatchV2Error(ValueError):
    """Raised when singleton batch lineage, execution, or output drifts."""


@dataclass(frozen=True, slots=True)
class SingletonBatchConfig:
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS
    max_job_attempts: int = 2

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or float(self.timeout_seconds) <= 0
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                "timeout_seconds must be positive"
            )
        if (
            isinstance(self.minimum_interval_seconds, bool)
            or not isinstance(self.minimum_interval_seconds, (int, float))
            or float(self.minimum_interval_seconds) < 0
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                "minimum_interval_seconds must be non-negative"
            )
        if (
            isinstance(self.max_job_attempts, bool)
            or not isinstance(self.max_job_attempts, int)
            or self.max_job_attempts <= 0
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                "max_job_attempts must be positive"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_job_attempts": self.max_job_attempts,
            "minimum_interval_seconds": float(self.minimum_interval_seconds),
            "timeout_seconds": float(self.timeout_seconds),
        }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return _sha(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def _prepared_row_hash(row: Mapping[str, Any]) -> str:
    return _sha(
        (
            json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    )


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SatelliteChangeSingletonBatchV2Error(
            f"{label} is not UTF-8"
        ) from error

    def reject_constant(value: str) -> None:
        raise SatelliteChangeSingletonBatchV2Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteChangeSingletonBatchV2Error(
            f"{label} is not valid JSON"
        ) from error


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeSingletonBatchV2Error(
            f"expected regular file: {path}"
        )
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha(raw)}


def _package_path(relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise SatelliteChangeSingletonBatchV2Error(f"{label} path is invalid")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise SatelliteChangeSingletonBatchV2Error(
            f"{label} path is not canonical"
        )
    result = PACKAGE_ROOT.joinpath(*posix.parts)
    cursor = PACKAGE_ROOT
    for part in posix.parts:
        cursor /= part
        if cursor.is_symlink():
            raise SatelliteChangeSingletonBatchV2Error(
                f"{label} path traverses a symlink"
            )
    return result


def _argument_pairs(arguments: Any, label: str) -> list[tuple[str, str]]:
    if not isinstance(arguments, list) or not arguments or len(arguments) % 2:
        raise SatelliteChangeSingletonBatchV2Error(
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
            raise SatelliteChangeSingletonBatchV2Error(
                f"{label} contains an invalid pair"
            )
        pairs.append((flag, value))
    return pairs


def _prepared_arguments(row: Mapping[str, Any]) -> dict[str, str]:
    pairs = _argument_pairs(
        row["execution"]["arguments"], f"{row['queue_id']} prepared arguments"
    )
    flags = [flag for flag, _value in pairs]
    expected = [
        "--baseline-stac",
        "--baseline-stac-sha256",
        "--baseline-primary",
        "--current-stac",
        "--current-stac-sha256",
        "--current-primary",
        "--bbox",
        "--entity-id",
        "--entity-name",
        "--output-dir",
        "--minimum-component-area-m2",
    ]
    if flags != expected or any("companion" in flag for flag in flags):
        raise SatelliteChangeSingletonBatchV2Error(
            f"{row['queue_id']} prepared singleton flag inventory changed"
        )
    return dict(pairs)


def _read_rows(path: Path) -> tuple[dict[str, Any], ...]:
    if _file_record(path)["sha256"] != PREPARATION_READY_SHA256:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton-ready partition hash changed"
        )
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_bytes().splitlines(), 1):
        value = _strict_json(line, f"singleton-ready row {line_number}")
        if not isinstance(value, dict):
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton-ready row {line_number} is not an object"
            )
        rows.append(value)
    return tuple(rows)


def _processor_lineage() -> dict[str, Any]:
    files = {
        relative: _file_record(_package_path(relative, "processor file"))
        for relative in PROCESSOR_FILES
    }
    if files["datacenter_atlas/satellite_change_mosaic.py"]["sha256"] != (
        "68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071"
    ) or files["scripts/sentinel_change_mosaic.py"]["sha256"] != (
        "6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183"
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            "unchanged mosaic-v3 processor lineage drifted"
        )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "cli": "scripts/sentinel_change_mosaic.py",
        "files": files,
        "runtime": validation_base._runtime_lineage(),
        "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
    }


def _validate_preparation(
    preparation_directory: str | Path,
    definition_path: str | Path,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], dict[str, Any]]:
    preparation = Path(preparation_directory)
    definition = Path(definition_path)
    if _file_record(definition)["sha256"] != PREPARATION_DEFINITION_SHA256:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton preparation definition hash changed"
        )
    try:
        manifest = validate_satellite_change_singleton_preparation_v2(
            preparation, definition_path=definition
        )
    except SatelliteChangeSingletonPreparationV2Error as error:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton preparation validation failed: {error}"
        ) from error
    if _file_record(preparation / "manifest.json")["sha256"] != (
        PREPARATION_MANIFEST_SHA256
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton preparation manifest hash changed"
        )
    try:
        tree = validation_base._tree_inventory(preparation)
    except Exception as error:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton preparation tree validation failed: {error}"
        ) from error
    if tree["inventory_sha256"] != PREPARATION_TREE_SHA256:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton preparation tree changed"
        )
    rows = _read_rows(preparation / READY_FILENAME)
    if (
        tuple(row.get("queue_id") for row in rows) != EXPECTED_QUEUE_IDS
        or tuple(row.get("queue_position") for row in rows)
        != EXPECTED_QUEUE_POSITIONS
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton six-job selection changed"
        )
    for row in rows:
        values = _prepared_arguments(row)
        if (
            row.get("schema_version") != 2
            or row.get("state") != "singleton_ready"
            or row.get("selection_scope")
            != "v1_prepared_selected_item_bindings_only"
            or row.get("network_requests") != 0
            or row.get("raster_analysis_executed") is not False
            or values["--output-dir"] != "{job_output_dir}"
            or values["--entity-id"] != row["entity"]["id"]
            or values["--entity-name"] != row["entity"]["name"]
            or list(parse_bbox(values["--bbox"])) != row["aoi_bbox_wgs84"]
            or values["--minimum-component-area-m2"] != "5000"
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                f"prepared singleton row changed: {row.get('queue_id')}"
            )
        for epoch in ("baseline", "current"):
            if (
                row["epochs"][epoch]["selected_companions"] != []
                or row["epochs"][epoch]["selected_primary"][
                    "prior_prepared_role"
                ]
                != "companion"
                or row["epochs"][epoch]["selected_coverage"]["complete"]
                is not True
            ):
                raise SatelliteChangeSingletonBatchV2Error(
                    f"prepared singleton selection changed: {row['queue_id']}/{epoch}"
                )
    lineage = {
        "closed_tree": tree,
        "definition": {
            "path": definition.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(definition),
        },
        "directory": preparation.relative_to(PACKAGE_ROOT).as_posix(),
        "manifest": {
            "path": (
                preparation / "manifest.json"
            ).relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(preparation / "manifest.json"),
        },
        "partition": {
            "path": (
                preparation / READY_FILENAME
            ).relative_to(PACKAGE_ROOT).as_posix(),
            "records": len(rows),
            **_file_record(preparation / READY_FILENAME),
        },
        "preparation_id": manifest["preparation_id"],
    }
    return manifest, rows, lineage


def _load_bound_epochs(
    row: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    values = _prepared_arguments(row)
    result: list[Mapping[str, Any]] = []
    for epoch in ("baseline", "current"):
        path = _package_path(values[f"--{epoch}-stac"], f"{epoch} STAC")
        raw = path.read_bytes()
        if _sha(raw) != values[f"--{epoch}-stac-sha256"]:
            raise SatelliteChangeSingletonBatchV2Error(
                f"{row['queue_id']} {epoch} STAC response hash changed"
            )
        document = _strict_json(raw, f"{row['queue_id']} {epoch} STAC response")
        try:
            primary, items = select_bound_items(
                document, parse_item_binding(values[f"--{epoch}-primary"]), ()
            )
        except SentinelMosaicContractError as error:
            raise SatelliteChangeSingletonBatchV2Error(
                f"{row['queue_id']} {epoch} singleton binding changed: {error}"
            ) from error
        if len(items) != 1 or primary.get("id") != row["epochs"][epoch][
            "selected_primary"
        ]["id"]:
            raise SatelliteChangeSingletonBatchV2Error(
                f"{row['queue_id']} {epoch} selected singleton changed"
            )
        result.append(primary)
    return result[0], result[1]


def _epoch_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    properties = item["properties"]
    return {
        "primary_id": item["id"],
        "datatake_id": properties["s2:datatake_id"],
        "datastrip_id": properties["s2:datastrip_id"],
        "items": [item_summary(item)],
    }


def _validate_change_output(
    row: Mapping[str, Any], directory: Path
) -> dict[str, Any]:
    queue_id = str(row["queue_id"])
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton output is not a regular directory: {queue_id}"
        )
    entries = list(directory.iterdir())
    if (
        any(entry.is_symlink() or not entry.is_file() for entry in entries)
        or {entry.name for entry in entries} != OUTPUT_FILES
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton output inventory changed: {queue_id}"
        )
    report_path = directory / "report.json"
    report_raw = report_path.read_bytes()
    report = _strict_json(report_raw, f"{queue_id} report")
    if report_raw != _canonical_json(report):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report is not canonical: {queue_id}"
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
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report schema changed: {queue_id}"
        )
    if (
        report["schema_version"] != REPORT_SCHEMA_VERSION
        or report["algorithm_version"] != ALGORITHM_VERSION
        or report["spectral_core_algorithm_version"]
        != SPECTRAL_CORE_ALGORITHM_VERSION
        or report["entity"]
        != {"id": row["entity"]["id"], "name": row["entity"]["name"]}
        or report["aoi_bbox_wgs84"] != row["aoi_bbox_wgs84"]
        or report["classification"] != REPORT_CLASSIFICATION
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report identity changed: {queue_id}"
        )
    baseline, current = _load_bound_epochs(row)
    if (
        report["baseline"] != _epoch_summary(baseline)
        or report["current"] != _epoch_summary(current)
        or report["source"] != report_source(baseline, current)
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report scene lineage changed: {queue_id}"
        )
    values = _prepared_arguments(row)
    expected_contract = {
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
    if report["mosaic_contract"] != expected_contract:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report mosaic contract changed: {queue_id}"
        )
    if report["radiometry"] != {
        "reflectance": "STAC raster scale and offset applied per epoch and band",
        "normalized_index_negative_reflectance_policy": "clip_to_zero",
    }:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report radiometry changed: {queue_id}"
        )
    validation_base._validate_thresholds(report["thresholds"])
    metrics = validation_base._report_metrics(report["metrics"])
    outputs = report["outputs"]
    if not isinstance(outputs, Mapping) or set(outputs) != REPORT_BOUND_FILES:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report output bindings changed: {queue_id}"
        )
    for name in sorted(REPORT_BOUND_FILES):
        if outputs[name] != _file_record(directory / name):
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton report-bound artifact changed: {queue_id}/{name}"
            )
    grid = report["grid"]
    if not isinstance(grid, Mapping) or set(grid) != {
        "crs",
        "width",
        "height",
        "pixel_area_m2",
        "clear_scl_classes",
        "aoi_inclusion",
    }:
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report grid schema changed: {queue_id}"
        )
    width = validation_base._positive_integer(grid["width"], f"{queue_id} width")
    height = validation_base._positive_integer(grid["height"], f"{queue_id} height")
    validation_base._positive_number(grid["pixel_area_m2"], f"{queue_id} pixel area")
    if (
        not isinstance(grid["crs"], str)
        or not grid["crs"]
        or grid["clear_scl_classes"] != sorted(CLEAR_SCL_CLASSES)
        or grid["aoi_inclusion"] != "exact_wgs84_pixel_centers"
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton report grid values changed: {queue_id}"
        )
    for name in ("before.png", "after.png", "change-overlay.png"):
        if validation_base._png_dimensions(
            directory / name, f"{queue_id}/{name}"
        ) != (width, height):
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton PNG dimensions changed: {queue_id}/{name}"
            )
    if validation_base._png_dimensions(
        directory / "comparison.png", f"{queue_id}/comparison.png"
    ) != (width * 3, height):
        raise SatelliteChangeSingletonBatchV2Error(
            f"singleton comparison dimensions changed: {queue_id}"
        )
    validation_base._validate_geojson(
        directory / "change-proposals.geojson",
        expected_count=metrics["proposal_component_count"],
        expected_area_m2=float(metrics["proposal_area_m2_after_component_filter"]),
        minimum_component_area_m2=5000.0,
        bbox=parse_bbox(values["--bbox"]),
    )
    return {
        "artifacts": {
            name: _file_record(directory / name) for name in sorted(OUTPUT_FILES)
        },
        "report": {
            "algorithm_version": report["algorithm_version"],
            "classification": dict(report["classification"]),
            "metrics": metrics,
            "report_sha256": _sha(report_raw),
            "schema_version": report["schema_version"],
            "spectral_core_algorithm_version": report[
                "spectral_core_algorithm_version"
            ],
        },
    }


def _summary(document: Mapping[str, Any]) -> dict[str, int]:
    states = [job["state"] for job in document["jobs"].values()]
    return {
        "jobs_completed": states.count("completed"),
        "jobs_failed": states.count("failed"),
        "jobs_pending": states.count("pending"),
        "jobs_running": states.count("running"),
        "jobs_selected": len(states),
        "output_artifacts": sum(
            len(job["artifacts"] or {}) for job in document["jobs"].values()
        ),
    }


def _write_manifest(output: Path, document: dict[str, Any], at: str) -> None:
    document["updated_at"] = at
    document["summary"] = _summary(document)
    states = {job["state"] for job in document["jobs"].values()}
    document["state"] = "completed" if states == {"completed"} else "incomplete"
    raw = _canonical_json(document)
    temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteChangeSingletonBatchV2Error(
            "stale singleton batch manifest temporary exists"
        )
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output / BATCH_MANIFEST_FILENAME)


def _new_manifest(
    rows: Sequence[Mapping[str, Any]],
    preparation: Mapping[str, Any],
    preparation_lineage: Mapping[str, Any],
    processor: Mapping[str, Any],
    config: SingletonBatchConfig,
    created_at: str,
) -> dict[str, Any]:
    jobs: dict[str, Any] = {}
    for row in rows:
        queue_id = str(row["queue_id"])
        jobs[queue_id] = {
            "aoi_bbox_wgs84": list(row["aoi_bbox_wgs84"]),
            "artifacts": None,
            "attempts": 0,
            "completed_at": None,
            "entity": dict(row["entity"]),
            "execution": dict(row["execution"]),
            "failures": [],
            "output_directory": f"jobs/{queue_id}/change",
            "prepared_row_sha256": _prepared_row_hash(row),
            "queue_id": queue_id,
            "queue_position": row["queue_position"],
            "report": None,
            "selected_primary": {
                epoch: dict(row["epochs"][epoch]["selected_primary"])
                for epoch in ("baseline", "current")
            },
            "source_prepared_row_sha256": row["source_prepared_row_sha256"],
            "state": "pending",
        }
    document = {
        "configuration": config.as_dict(),
        "created_at": created_at,
        "determinism": {
            "artifact_inventory_sha256": None,
            "artifacts_compared": 0,
            "jobs_replayed": 0,
            "status": "not_verified",
            "verified_at": None,
        },
        "format": BATCH_FORMAT,
        "jobs": jobs,
        "pipeline": BATCH_PIPELINE,
        "preparation": dict(preparation_lineage),
        "processor": dict(processor),
        "runs": [],
        "schema_version": BATCH_SCHEMA_VERSION,
        "scope": dict(SCOPE),
        "selection": {
            "queue_ids": list(EXPECTED_QUEUE_IDS),
            "queue_positions": list(EXPECTED_QUEUE_POSITIONS),
            "selected_items_per_epoch": 1,
        },
        "state": "incomplete",
        "summary": {},
        "technical_incident": dict(preparation["technical_incident"]),
        "updated_at": created_at,
    }
    document["summary"] = _summary(document)
    return document


def _resolved_command(row: Mapping[str, Any], output: Path) -> list[str]:
    resolved: list[str] = []
    for flag, value in _argument_pairs(
        row["execution"]["arguments"], f"{row['queue_id']} arguments"
    ):
        if flag == "--output-dir":
            value = str(output)
        if flag == "--bbox" and value.startswith("-"):
            resolved.append(f"--bbox={value}")
        else:
            resolved.extend((flag, value))
    script = _package_path("scripts/sentinel_change_mosaic.py", "processor CLI")
    return [sys.executable, str(script), *resolved]


def _row_by_id(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["queue_id"]): row for row in rows}


@contextmanager
def _directory_lock(output: Path, *, exclusive: bool) -> Iterator[None]:
    lock = output.parent / f"{output.name}.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _load_manifest(output: Path) -> dict[str, Any]:
    path = output / BATCH_MANIFEST_FILENAME
    raw = _file_record(path) and path.read_bytes()
    value = _strict_json(raw, "singleton batch manifest")
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton batch manifest is not canonical"
        )
    return value


def _validate_document(
    document: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    preparation: Mapping[str, Any],
    preparation_lineage: Mapping[str, Any],
    processor: Mapping[str, Any],
    output: Path,
) -> None:
    required = {
        "configuration",
        "created_at",
        "determinism",
        "format",
        "jobs",
        "pipeline",
        "preparation",
        "processor",
        "runs",
        "schema_version",
        "scope",
        "selection",
        "state",
        "summary",
        "technical_incident",
        "updated_at",
    }
    if (
        set(document) != required
        or document["format"] != BATCH_FORMAT
        or document["pipeline"] != BATCH_PIPELINE
        or document["schema_version"] != BATCH_SCHEMA_VERSION
        or document["scope"] != SCOPE
        or document["preparation"] != preparation_lineage
        or document["processor"] != processor
        or document["technical_incident"] != preparation["technical_incident"]
        or document["summary"] != _summary(document)
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton batch manifest lineage changed"
        )
    if set(document["jobs"]) != set(EXPECTED_QUEUE_IDS) or document[
        "selection"
    ] != {
        "queue_ids": list(EXPECTED_QUEUE_IDS),
        "queue_positions": list(EXPECTED_QUEUE_POSITIONS),
        "selected_items_per_epoch": 1,
    }:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton batch manifest selection changed"
        )
    by_id = _row_by_id(rows)
    allowed_directories = {Path("."), Path("jobs")}
    allowed_files = {Path(BATCH_MANIFEST_FILENAME)}
    if (output / FREEZE_MANIFEST_FILENAME).exists():
        allowed_files |= {
            Path(FREEZE_MANIFEST_FILENAME),
            Path(FREEZE_SHA256_FILENAME),
        }
    for queue_id in EXPECTED_QUEUE_IDS:
        job = document["jobs"][queue_id]
        row = by_id[queue_id]
        if (
            job["queue_id"] != queue_id
            or job["queue_position"] != row["queue_position"]
            or job["entity"] != row["entity"]
            or job["aoi_bbox_wgs84"] != row["aoi_bbox_wgs84"]
            or job["execution"] != row["execution"]
            or job["prepared_row_sha256"] != _prepared_row_hash(row)
            or job["source_prepared_row_sha256"]
            != row["source_prepared_row_sha256"]
            or job["selected_primary"]
            != {
                epoch: row["epochs"][epoch]["selected_primary"]
                for epoch in ("baseline", "current")
            }
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton batch job lineage changed: {queue_id}"
            )
        job_root = Path("jobs") / queue_id
        change = job_root / "change"
        allowed_directories |= {job_root, change}
        if job["state"] == "completed":
            result = _validate_change_output(row, output / change)
            if job["artifacts"] != result["artifacts"] or job["report"] != result[
                "report"
            ]:
                raise SatelliteChangeSingletonBatchV2Error(
                    f"singleton batch recorded output changed: {queue_id}"
                )
            allowed_files |= {change / name for name in OUTPUT_FILES}
        elif job["state"] not in {"pending", "failed", "running"}:
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton batch job state changed: {queue_id}"
            )
    for path in [output, *sorted(output.rglob("*"))]:
        relative = Path(".") if path == output else path.relative_to(output)
        if path.is_symlink():
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton batch contains a symlink: {relative}"
            )
        if path.is_dir() and relative not in allowed_directories:
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton batch contains unexpected directory: {relative}"
            )
        if path.is_file() and relative not in allowed_files:
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton batch contains unexpected file: {relative}"
            )
    determinism = document["determinism"]
    if not isinstance(determinism, Mapping):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton determinism record is invalid"
        )
    if determinism.get("status") == "not_verified":
        if determinism != {
            "artifact_inventory_sha256": None,
            "artifacts_compared": 0,
            "jobs_replayed": 0,
            "status": "not_verified",
            "verified_at": None,
        }:
            raise SatelliteChangeSingletonBatchV2Error(
                "unverified singleton determinism record changed"
            )
    elif determinism.get("status") == "verified_byte_identical":
        inventory = _production_artifact_inventory(document)
        if determinism != {
            "artifact_inventory_sha256": _canonical_hash(inventory),
            "artifacts_compared": len(EXPECTED_QUEUE_IDS) * len(OUTPUT_FILES),
            "jobs_replayed": len(EXPECTED_QUEUE_IDS),
            "status": "verified_byte_identical",
            "verified_at": determinism.get("verified_at"),
        } or not isinstance(determinism.get("verified_at"), str):
            raise SatelliteChangeSingletonBatchV2Error(
                "verified singleton determinism record changed"
            )
    else:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton determinism status changed"
        )


def execute_satellite_change_singleton_batch_v2(
    preparation_directory: str | Path = PACKAGE_ROOT / PREPARATION_DIRECTORY_PATH,
    output_directory: str | Path = PACKAGE_ROOT / DEFAULT_OUTPUT_PATH,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    config: SingletonBatchConfig | None = None,
    max_jobs: int = 6,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Execute up to ``max_jobs`` prepared singleton rows with atomic publication."""

    if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or max_jobs <= 0:
        raise SatelliteChangeSingletonBatchV2Error("max_jobs must be positive")
    config = config or SingletonBatchConfig()
    preparation, rows, preparation_lineage = _validate_preparation(
        preparation_directory, definition_path
    )
    processor = _processor_lineage()
    output = Path(output_directory)
    if output.is_symlink():
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton batch output is a symlink"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with _directory_lock(output, exclusive=True):
        if (output / FREEZE_MANIFEST_FILENAME).exists():
            raise SatelliteChangeSingletonBatchV2Error(
                "singleton batch output is already frozen"
            )
        started = timestamp()
        if output.exists():
            if not output.is_dir() or not (output / BATCH_MANIFEST_FILENAME).is_file():
                raise SatelliteChangeSingletonBatchV2Error(
                    "refusing output replacement without a valid checkpoint"
                )
            document = _load_manifest(output)
            _validate_document(
                document, rows, preparation, preparation_lineage, processor, output
            )
            if document["configuration"] != config.as_dict():
                raise SatelliteChangeSingletonBatchV2Error(
                    "saved singleton batch configuration changed"
                )
        else:
            output.mkdir()
            (output / "jobs").mkdir()
            document = _new_manifest(
                rows, preparation, preparation_lineage, processor, config, started
            )
            _write_manifest(output, document, started)
        run = {
            "finished_at": None,
            "job_attempts": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "max_jobs": max_jobs,
            "run_number": len(document["runs"]) + 1,
            "started_at": started,
            "state": "running",
        }
        document["runs"].append(run)
        _write_manifest(output, document, started)
        by_id = _row_by_id(rows)
        invoked = 0
        for queue_id in EXPECTED_QUEUE_IDS:
            if invoked >= max_jobs:
                break
            job = document["jobs"][queue_id]
            if job["state"] == "completed" or job["attempts"] >= config.max_job_attempts:
                continue
            if invoked:
                sleep(float(config.minimum_interval_seconds))
            invoked += 1
            run["job_attempts"] += 1
            job["attempts"] += 1
            job["state"] = "running"
            _write_manifest(output, document, timestamp())
            job_root = output / "jobs" / queue_id
            job_root.mkdir(exist_ok=True)
            final = job_root / "change"
            stage = job_root / f".change.attempt-{job['attempts']}.staging"
            if final.exists() or stage.exists() or final.is_symlink() or stage.is_symlink():
                raise SatelliteChangeSingletonBatchV2Error(
                    f"singleton job output collision: {queue_id}"
                )
            stage.mkdir()
            try:
                completed = command_runner(
                    _resolved_command(by_id[queue_id], stage),
                    cwd=PACKAGE_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=float(config.timeout_seconds),
                    check=False,
                )
                if completed.returncode != 0:
                    stderr = (completed.stderr or "").strip()
                    raise SatelliteChangeSingletonBatchV2Error(
                        f"processor exited {completed.returncode}: {stderr[-4000:]}"
                    )
                result = _validate_change_output(by_id[queue_id], stage)
                os.rename(stage, final)
                job["artifacts"] = result["artifacts"]
                job["report"] = result["report"]
                job["completed_at"] = timestamp()
                job["state"] = "completed"
                run["jobs_completed"] += 1
            except Exception as error:
                if stage.exists() and not stage.is_symlink():
                    shutil.rmtree(stage)
                job["failures"].append(
                    {
                        "at": timestamp(),
                        "attempt": job["attempts"],
                        "error": str(error),
                    }
                )
                job["state"] = "failed"
                run["jobs_failed"] += 1
            _write_manifest(output, document, timestamp())
        run["finished_at"] = timestamp()
        run["state"] = "completed"
        _write_manifest(output, document, run["finished_at"])
        _validate_document(
            document, rows, preparation, preparation_lineage, processor, output
        )
        return document


def _production_artifact_inventory(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "artifacts": document["jobs"][queue_id]["artifacts"],
            "queue_id": queue_id,
        }
        for queue_id in EXPECTED_QUEUE_IDS
    ]


def verify_satellite_change_singleton_batch_v2_determinism(
    preparation_directory: str | Path = PACKAGE_ROOT / PREPARATION_DIRECTORY_PATH,
    output_directory: str | Path = PACKAGE_ROOT / DEFAULT_OUTPUT_PATH,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Replay all six jobs separately and require byte-identical output artifacts."""

    preparation, rows, preparation_lineage = _validate_preparation(
        preparation_directory, definition_path
    )
    processor = _processor_lineage()
    output = Path(output_directory)
    with _directory_lock(output, exclusive=True):
        if (output / FREEZE_MANIFEST_FILENAME).exists():
            raise SatelliteChangeSingletonBatchV2Error(
                "cannot replay an already frozen singleton batch"
            )
        document = _load_manifest(output)
        _validate_document(
            document, rows, preparation, preparation_lineage, processor, output
        )
        if document["state"] != "completed":
            raise SatelliteChangeSingletonBatchV2Error(
                "deterministic replay requires six completed jobs"
            )
        by_id = _row_by_id(rows)
        replay_root = Path(
            tempfile.mkdtemp(prefix=".singleton-v2-replay-", dir=output.parent)
        )
        compared = 0
        try:
            for index, queue_id in enumerate(EXPECTED_QUEUE_IDS):
                if index:
                    sleep(float(document["configuration"]["minimum_interval_seconds"]))
                destination = replay_root / queue_id
                destination.mkdir()
                completed = command_runner(
                    _resolved_command(by_id[queue_id], destination),
                    cwd=PACKAGE_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=float(document["configuration"]["timeout_seconds"]),
                    check=False,
                )
                if completed.returncode != 0:
                    raise SatelliteChangeSingletonBatchV2Error(
                        f"deterministic replay failed for {queue_id}: "
                        f"{(completed.stderr or '')[-4000:]}"
                    )
                result = _validate_change_output(by_id[queue_id], destination)
                if result["artifacts"] != document["jobs"][queue_id]["artifacts"]:
                    raise SatelliteChangeSingletonBatchV2Error(
                        f"deterministic replay artifact mismatch: {queue_id}"
                    )
                compared += len(result["artifacts"])
        finally:
            if replay_root.exists() and not replay_root.is_symlink():
                shutil.rmtree(replay_root)
        inventory = _production_artifact_inventory(document)
        document["determinism"] = {
            "artifact_inventory_sha256": _canonical_hash(inventory),
            "artifacts_compared": compared,
            "jobs_replayed": len(EXPECTED_QUEUE_IDS),
            "status": "verified_byte_identical",
            "verified_at": timestamp(),
        }
        _write_manifest(output, document, document["determinism"]["verified_at"])
        return document


def _freeze_inventory(output: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    directories = 0
    files = 0
    file_bytes = 0
    excluded = {FREEZE_MANIFEST_FILENAME, FREEZE_SHA256_FILENAME}
    for path in sorted(output.rglob("*"), key=lambda value: value.relative_to(output).as_posix()):
        relative = path.relative_to(output).as_posix()
        if relative in excluded:
            continue
        if path.is_symlink():
            raise SatelliteChangeSingletonBatchV2Error(
                f"freeze tree contains symlink: {relative}"
            )
        mode = f"{stat.S_IMODE(path.stat().st_mode):04o}"
        if path.is_dir():
            directories += 1
            records.append({"mode": mode, "path": relative, "type": "directory"})
        elif path.is_file():
            record = {
                "bytes": path.stat().st_size,
                "mode": mode,
                "path": relative,
                "sha256": _file_record(path)["sha256"],
                "type": "file",
            }
            records.append(record)
            files += 1
            file_bytes += record["bytes"]
        else:
            raise SatelliteChangeSingletonBatchV2Error(
                f"freeze tree contains unsupported entry: {relative}"
            )
    return {
        "directories": directories,
        "file_bytes": file_bytes,
        "files": files,
        "inventory_sha256": _canonical_hash(records),
        "records": records,
    }


def freeze_satellite_change_singleton_batch_v2(
    preparation_directory: str | Path = PACKAGE_ROOT / PREPARATION_DIRECTORY_PATH,
    output_directory: str | Path = PACKAGE_ROOT / DEFAULT_OUTPUT_PATH,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Freeze a complete, independently replayed batch and bind its closed tree."""

    preparation, rows, preparation_lineage = _validate_preparation(
        preparation_directory, definition_path
    )
    processor = _processor_lineage()
    output = Path(output_directory)
    with _directory_lock(output, exclusive=True):
        if (output / FREEZE_MANIFEST_FILENAME).exists():
            raise SatelliteChangeSingletonBatchV2Error(
                "singleton batch is already frozen"
            )
        document = _load_manifest(output)
        _validate_document(
            document, rows, preparation, preparation_lineage, processor, output
        )
        if document["state"] != "completed" or document["determinism"]["status"] != (
            "verified_byte_identical"
        ):
            raise SatelliteChangeSingletonBatchV2Error(
                "freeze requires six completed jobs and byte-identical replay"
            )
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o444)
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o555)
        inventory = _freeze_inventory(output)
        freeze = {
            "created_at": timestamp(),
            "format": "datacenter-atlas-satellite-change-singleton-freeze-v1",
            "inventory": inventory,
            "manifest": {
                "path": BATCH_MANIFEST_FILENAME,
                **_file_record(output / BATCH_MANIFEST_FILENAME),
            },
            "schema_version": 1,
        }
        freeze_raw = _canonical_json(freeze)
        freeze_path = output / FREEZE_MANIFEST_FILENAME
        sha_path = output / FREEZE_SHA256_FILENAME
        with freeze_path.open("xb") as stream:
            stream.write(freeze_raw)
            stream.flush()
            os.fsync(stream.fileno())
        with sha_path.open("xb") as stream:
            stream.write(
                f"{_sha(freeze_raw)}  {FREEZE_MANIFEST_FILENAME}\n".encode("ascii")
            )
            stream.flush()
            os.fsync(stream.fileno())
        freeze_path.chmod(0o444)
        sha_path.chmod(0o444)
        output.chmod(0o555)
        return freeze


def _validate_freeze(output: Path) -> dict[str, Any]:
    freeze_path = output / FREEZE_MANIFEST_FILENAME
    sha_path = output / FREEZE_SHA256_FILENAME
    freeze_raw = freeze_path.read_bytes()
    expected_sha = f"{_sha(freeze_raw)}  {FREEZE_MANIFEST_FILENAME}\n".encode("ascii")
    if sha_path.read_bytes() != expected_sha:
        raise SatelliteChangeSingletonBatchV2Error("freeze SHA-256 changed")
    freeze = _strict_json(freeze_raw, "singleton freeze manifest")
    if freeze_raw != _canonical_json(freeze) or freeze.get("inventory") != (
        _freeze_inventory(output)
    ):
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton frozen inventory changed"
        )
    if freeze.get("manifest") != {
        "path": BATCH_MANIFEST_FILENAME,
        **_file_record(output / BATCH_MANIFEST_FILENAME),
    }:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton frozen batch manifest changed"
        )
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton frozen root mode changed"
        )
    for path in output.rglob("*"):
        expected = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(path.stat().st_mode) != expected:
            raise SatelliteChangeSingletonBatchV2Error(
                f"singleton frozen mode changed: {path.relative_to(output)}"
            )
    return freeze


def validate_satellite_change_singleton_batch_v2(
    preparation_directory: str | Path = PACKAGE_ROOT / PREPARATION_DIRECTORY_PATH,
    output_directory: str | Path = PACKAGE_ROOT / DEFAULT_OUTPUT_PATH,
    *,
    definition_path: str | Path = PACKAGE_ROOT / PREPARATION_DEFINITION_PATH,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Perform full offline validation of prepared lineage and output bytes."""

    preparation, rows, preparation_lineage = _validate_preparation(
        preparation_directory, definition_path
    )
    processor = _processor_lineage()
    output = Path(output_directory)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangeSingletonBatchV2Error(
            "singleton batch output is not a regular directory"
        )
    with _directory_lock(output, exclusive=False):
        document = _load_manifest(output)
        _validate_document(
            document, rows, preparation, preparation_lineage, processor, output
        )
        frozen = (output / FREEZE_MANIFEST_FILENAME).exists()
        if require_frozen and not frozen:
            raise SatelliteChangeSingletonBatchV2Error(
                "singleton batch output is not frozen"
            )
        if frozen:
            _validate_freeze(output)
        return document
