"""Generalized, explicit-ID Sentinel-2 catalog coverage reselection.

Version 2 is a separate carrier from the frozen historical v1 implementation.
It accepts an explicit repeatable candidate inventory, canonicalizes it to queue
order, and derives either a full-cover comparable scene pair or a bound
``unresolved_multitile_or_supplemental_scene_required`` assessment from exact
archived catalog responses.  Only the explicit header-capture step may open
selected COGs, and it reads no raster pixels.  Build and validation are
offline, closed-world, atomic, and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
from typing import Any, Mapping, Sequence

from .satellite_batch import BATCH_MANIFEST_FILENAME, validate_satellite_batch
from .satellite_change import (
    REQUIRED_ASSETS,
    canonical_sha256,
    ensure_comparable,
    mgrs_tile,
    select_feature,
    validate_asset_href,
)
from .satellite_queue import (
    MANIFEST_FILENAME as QUEUE_MANIFEST_FILENAME,
    QUEUE_FILENAME,
    validate_queue_bundle,
)
from . import satellite_catalog_reselection as v1


RESELECTION_SCHEMA_VERSION = 2
RESELECTION_PIPELINE = "satellite_catalog_coverage_reselection_v2"
RESELECTION_MANIFEST_FILENAME = "batch-manifest.json"
JOB_MANIFEST_FILENAME = "manifest.json"
SOURCE_MANIFEST_FILENAME = "source-manifest.json"
HEADER_EVIDENCE_FILENAME = "grid-headers.json"
UNRESOLVED_FILENAME = "unresolved-multitile-needed.json"
HEADER_SCHEMA_VERSION = 2
HEADER_PIPELINE = "sentinel_cog_grid_header_evidence_v2"

RESELECTION_SCOPE = {
    "mode": "explicit_queue_id_offline_coverage_filtered_reselection",
    "network_access_during_build": False,
    "network_access_during_validation": False,
    "raw_provider_responses_modified": False,
    "raw_provider_response_bytes_copied_exactly": True,
    "atlas_mutation": False,
    "change_analysis_executed": False,
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
    "catalog_availability_is_not_change_evidence": True,
    "review_required": True,
}

HEADER_SCOPE = {
    "method": "rasterio_open_metadata_only",
    "pixel_reads": 0,
    "cog_input_bytes_archived": False,
    "http_request_count": None,
    "asset_open_operations_are_not_http_request_counts": True,
    "opens_selected_assets_only": True,
}

RANKING_POLICY = (
    "same_known_mgrs_tile",
    "closest_season",
    "lowest_combined_cloud_cover",
    "closest_targets",
    "stable_timestamps_and_ids",
)

BUILDER_FILES = (
    "datacenter_atlas/satellite_catalog_reselection.py",
    "datacenter_atlas/satellite_catalog_reselection_v2.py",
    "satellite_catalog_reselection_v2.py",
    "scripts/build_satellite_catalog_reselection_v2.py",
    "datacenter_atlas/satellite_batch.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_queue.py",
)

SatelliteCatalogReselectionV2Error = v1.SatelliteCatalogReselectionError


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def _timestamp(value: Any, field: str) -> str:
    return v1._timestamp(value, field)


def _absolute_directory(path: str | Path, label: str) -> Path:
    return v1._absolute_directory(path, label)


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    return v1._relative_parts(value, label)


def _regular_file(root: Path, relative: Any, label: str) -> Path:
    return v1._regular_file(root, relative, label)


def _decode_json(raw: bytes, label: str) -> Any:
    return v1._decode_json(raw, label)


def _canonical_json_file(path: Path, label: str) -> Any:
    raw = path.read_bytes()
    value = _decode_json(raw, label)
    if raw != _canonical_bytes(value):
        raise SatelliteCatalogReselectionV2Error(f"{label} is not canonical JSON")
    return value


def _runtime_lineage() -> dict[str, Any]:
    try:
        rasterio_version: str | None = distribution_version("rasterio")
    except PackageNotFoundError:
        rasterio_version = None
    gdal: str | None = None
    proj: str | None = None
    if rasterio_version is not None:
        try:
            import rasterio
        except (ImportError, OSError):
            pass
        else:
            gdal = getattr(rasterio, "__gdal_version__", None)
            proj = getattr(rasterio, "__proj_version__", None)
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": getattr(__import__("sys").implementation, "cache_tag", None),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "rasterio": rasterio_version,
        "gdal": gdal,
        "proj": proj,
    }


def _builder_lineage() -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[1]
    files = {
        relative: _file_record(_regular_file(package_root, relative, relative))
        for relative in BUILDER_FILES
    }
    return {"files": files, "runtime": _runtime_lineage()}


def _read_queue(queue: Path) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    manifest = validate_queue_bundle(queue)
    queue_path = _regular_file(queue, QUEUE_FILENAME, "queue JSONL")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(queue_path.read_bytes().splitlines(), start=1):
        value = _decode_json(line, f"queue line {line_number}")
        if not isinstance(value, dict):
            raise SatelliteCatalogReselectionV2Error(
                f"queue line {line_number} is not an object"
            )
        rows.append(value)
    return manifest, rows


def _queue_lineage(queue: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = _regular_file(queue, QUEUE_MANIFEST_FILENAME, "queue manifest")
    queue_path = _regular_file(queue, QUEUE_FILENAME, "queue JSONL")
    return {
        "manifest_file": QUEUE_MANIFEST_FILENAME,
        "manifest": _file_record(manifest_path),
        "queue_file": QUEUE_FILENAME,
        "queue": _file_record(queue_path),
        "queue_records": manifest["artifacts"][QUEUE_FILENAME]["records"],
    }


def _source_lineage(source: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _regular_file(
        source, BATCH_MANIFEST_FILENAME, "source catalog batch manifest"
    )
    return {
        "manifest_file": BATCH_MANIFEST_FILENAME,
        "manifest": _file_record(manifest),
        "schema_version": document["schema_version"],
        "pipeline": document["pipeline"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "jobs_completed": document["summary"]["jobs_completed"],
    }


def _source_job_files(
    source: Path, task: Mapping[str, Any], queue_id: str
) -> dict[str, Path]:
    return v1._source_job_files(source, task, queue_id)


def _features(document: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    return v1._features(document, label)


def _item_coverage(
    item: Mapping[str, Any],
    bbox: Sequence[float],
    epoch: str,
    *,
    header_by_href: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return v1._item_coverage(
        item,
        bbox,
        epoch,
        header_by_href=header_by_href,
    )


def _stac_grid(item: Mapping[str, Any], asset_name: str) -> dict[str, Any]:
    return v1._stac_grid(item, asset_name)


def _canonicalize_candidate_ids(
    queue_rows: Sequence[Mapping[str, Any]], queue_ids: Sequence[str]
) -> tuple[str, ...]:
    if isinstance(queue_ids, (str, bytes)) or not isinstance(queue_ids, Sequence):
        raise SatelliteCatalogReselectionV2Error(
            "candidate queue IDs must be a repeated sequence"
        )
    requested: set[str] = set()
    for index, queue_id in enumerate(queue_ids):
        if not isinstance(queue_id, str) or not queue_id.strip():
            raise SatelliteCatalogReselectionV2Error(
                f"candidate queue ID {index} must be non-empty text"
            )
        if queue_id != queue_id.strip():
            raise SatelliteCatalogReselectionV2Error(
                f"candidate queue ID {index} has surrounding whitespace"
            )
        requested.add(queue_id)
    if not requested:
        raise SatelliteCatalogReselectionV2Error(
            "at least one candidate queue ID is required"
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    positions: set[int] = set()
    for row in queue_rows:
        queue_id = row.get("queue_id")
        position = row.get("queue_position")
        if not isinstance(queue_id, str) or queue_id in by_id:
            raise SatelliteCatalogReselectionV2Error("queue contains duplicate IDs")
        if isinstance(position, bool) or not isinstance(position, int) or position <= 0:
            raise SatelliteCatalogReselectionV2Error(
                f"queue position is invalid for {queue_id}"
            )
        if position in positions:
            raise SatelliteCatalogReselectionV2Error(
                f"queue contains duplicate position {position}"
            )
        by_id[queue_id] = row
        positions.add(position)
    missing = sorted(requested - set(by_id))
    if missing:
        raise SatelliteCatalogReselectionV2Error(
            f"queue lacks explicit candidate IDs: {missing}"
        )
    return tuple(
        row["queue_id"]
        for row in sorted(by_id.values(), key=lambda value: value["queue_position"])
        if row["queue_id"] in requested
    )


def _record_datetime(record: Mapping[str, Any], label: str) -> datetime:
    value = record.get("datetime")
    if not isinstance(value, str):
        raise SatelliteCatalogReselectionV2Error(f"{label} datetime is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteCatalogReselectionV2Error(
            f"{label} datetime is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteCatalogReselectionV2Error(
            f"{label} datetime lacks a timezone"
        )
    return parsed.astimezone(UTC)


def _selection_configuration(
    source_manifest: Mapping[str, Any], queue_id: str
) -> tuple[date, date, int]:
    selection = source_manifest.get("queries", {}).get("selection", {})
    if not isinstance(selection, Mapping):
        raise SatelliteCatalogReselectionV2Error(
            f"source selection query is invalid for {queue_id}"
        )
    try:
        baseline_target = date.fromisoformat(selection["baseline_date"])
        current_target = date.fromisoformat(selection["current_date"])
        window = selection["temporal_window_days"]
    except (KeyError, TypeError, ValueError) as error:
        raise SatelliteCatalogReselectionV2Error(
            f"source selection query is invalid for {queue_id}"
        ) from error
    if baseline_target >= current_target:
        raise SatelliteCatalogReselectionV2Error(
            f"source selection dates are invalid for {queue_id}"
        )
    if isinstance(window, bool) or not isinstance(window, int) or not 0 <= window <= 366:
        raise SatelliteCatalogReselectionV2Error(
            f"source temporal window is invalid for {queue_id}"
        )
    return baseline_target, current_target, window


def _normalized_records(
    source_manifest: Mapping[str, Any],
    eligible_ids: Mapping[str, tuple[str, ...]],
    queue_id: str,
) -> dict[str, dict[str, Mapping[str, Any]]]:
    normalized = source_manifest.get("normalized_results")
    if not isinstance(normalized, Mapping) or set(normalized) != {"baseline", "current"}:
        raise SatelliteCatalogReselectionV2Error(
            f"source normalized results are invalid for {queue_id}"
        )
    result: dict[str, dict[str, Mapping[str, Any]]] = {}
    for epoch in ("baseline", "current"):
        values = normalized[epoch]
        if not isinstance(values, list):
            raise SatelliteCatalogReselectionV2Error(
                f"source normalized {epoch} results are invalid for {queue_id}"
            )
        by_id: dict[str, Mapping[str, Any]] = {}
        for record in values:
            if not isinstance(record, Mapping):
                raise SatelliteCatalogReselectionV2Error(
                    f"source normalized {epoch} record is invalid for {queue_id}"
                )
            item_id = record.get("item_id")
            if not isinstance(item_id, str) or item_id in by_id:
                raise SatelliteCatalogReselectionV2Error(
                    f"source normalized {epoch} IDs are invalid for {queue_id}"
                )
            by_id[item_id] = record
        missing = sorted(set(eligible_ids[epoch]) - set(by_id))
        if missing:
            raise SatelliteCatalogReselectionV2Error(
                f"eligible {epoch} features lack normalized records for {queue_id}: {missing}"
            )
        result[epoch] = by_id
    return result


def _select_comparable_pair(
    features_by_epoch: Mapping[str, Mapping[str, Mapping[str, Any]]],
    records_by_epoch: Mapping[str, Mapping[str, Mapping[str, Any]]],
    eligible_ids: Mapping[str, tuple[str, ...]],
    source_manifest: Mapping[str, Any],
    queue_id: str,
) -> tuple[
    dict[str, Mapping[str, Any]] | None,
    dict[str, Mapping[str, Any]] | None,
    dict[str, Any] | None,
    int,
]:
    baseline_target, current_target, window = _selection_configuration(
        source_manifest, queue_id
    )
    targets = {"baseline": baseline_target, "current": current_target}
    temporal: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {
        "baseline": [],
        "current": [],
    }
    for epoch in ("baseline", "current"):
        for item_id in eligible_ids[epoch]:
            record = records_by_epoch[epoch][item_id]
            timestamp = _record_datetime(record, f"{queue_id} {epoch} {item_id}")
            if abs((timestamp.date() - targets[epoch]).days) <= window:
                temporal[epoch].append((record, features_by_epoch[epoch][item_id]))

    ranked: list[
        tuple[
            tuple[Any, ...],
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
        ]
    ] = []
    for baseline_record, baseline_item in temporal["baseline"]:
        for current_record, current_item in temporal["current"]:
            try:
                ensure_comparable(baseline_item, current_item)
            except ValueError:
                continue
            if _stac_grid(baseline_item, "red") != _stac_grid(current_item, "red"):
                continue
            rank_record = v1._rank_record(
                baseline_record,
                current_record,
                baseline_target.isoformat(),
                current_target.isoformat(),
            )
            ranked.append(
                (
                    tuple(rank_record["rank"]),
                    baseline_record,
                    current_record,
                    baseline_item,
                    current_item,
                )
            )
    if not ranked:
        return None, None, None, 0
    rank, baseline_record, current_record, baseline_item, current_item = min(
        ranked, key=lambda option: option[0]
    )
    return (
        {"baseline": baseline_record, "current": current_record},
        {"baseline": baseline_item, "current": current_item},
        {"policy": list(RANKING_POLICY), "rank": list(rank)},
        len(ranked),
    )


@dataclass(frozen=True, slots=True)
class _PlannedJob:
    queue: Mapping[str, Any]
    source_task: Mapping[str, Any]
    source_files: Mapping[str, Path]
    source_manifest: Mapping[str, Any]
    original_items: Mapping[str, Mapping[str, Any]]
    selected_items: Mapping[str, Mapping[str, Any]]
    eligible_ids: Mapping[str, tuple[str, ...]]
    derived_manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReselectionPlanV2:
    queue: Path
    source: Path
    queue_manifest: Mapping[str, Any]
    source_document: Mapping[str, Any]
    queue_rows: tuple[dict[str, Any], ...]
    candidate_queue_ids: tuple[str, ...]
    jobs: tuple[_PlannedJob, ...]
    unresolved: Mapping[str, Any]


def _original_failure(
    source_manifest: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    bbox: Sequence[float],
    queue_id: str,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], list[str]]:
    original_ids = source_manifest.get("selected_ids")
    if not isinstance(original_ids, Mapping) or set(original_ids) != {"baseline", "current"}:
        raise SatelliteCatalogReselectionV2Error(
            f"source selected IDs are invalid for {queue_id}"
        )
    original_items = {
        epoch: select_feature(documents[epoch], original_ids[epoch])
        for epoch in ("baseline", "current")
    }
    original_coverage = {
        epoch: _item_coverage(original_items[epoch], bbox, epoch)
        for epoch in ("baseline", "current")
    }
    failed_epochs = [
        epoch
        for epoch in ("baseline", "current")
        if not original_coverage[epoch]["all_required_asset_windows_within_grid"]
    ]
    if not failed_epochs:
        raise SatelliteCatalogReselectionV2Error(
            f"source selection is already fully covered for {queue_id}"
        )
    return original_items, original_coverage, failed_epochs


def _source_descriptor(
    files: Mapping[str, Path],
    source_manifest: Mapping[str, Any],
    source_task: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "catalog_task_sha256": _canonical_hash(source_task),
        "raw_response_files_copied_exactly": True,
        "baseline_response": {
            "file": "baseline-response.json",
            **_file_record(files["baseline"]),
        },
        "current_response": {
            "file": "current-response.json",
            **_file_record(files["current"]),
        },
        "source_manifest": {
            "file": SOURCE_MANIFEST_FILENAME,
            **_file_record(files["manifest"]),
        },
        "retrieved_at": source_manifest.get("retrieved_at"),
        "queries": source_manifest.get("queries"),
    }


def _assess_candidate(
    queue_job: Mapping[str, Any],
    source_task: Mapping[str, Any],
    source: Path,
) -> tuple[_PlannedJob | None, dict[str, Any] | None]:
    queue_id = queue_job["queue_id"]
    files = _source_job_files(source, source_task, queue_id)
    documents: dict[str, Mapping[str, Any]] = {}
    for epoch in ("baseline", "current"):
        value = _decode_json(files[epoch].read_bytes(), f"{queue_id} {epoch} response")
        if not isinstance(value, Mapping):
            raise SatelliteCatalogReselectionV2Error(
                f"source {epoch} response is invalid for {queue_id}"
            )
        documents[epoch] = value
    source_manifest = _decode_json(files["manifest"].read_bytes(), f"{queue_id} source manifest")
    if not isinstance(source_manifest, Mapping):
        raise SatelliteCatalogReselectionV2Error(
            f"source manifest is invalid for {queue_id}"
        )
    bbox = queue_job["location"]["aoi_bbox_wgs84"]
    original_items, original_coverage, failed_epochs = _original_failure(
        source_manifest,
        documents,
        bbox,
        queue_id,
    )

    eligibility: dict[str, dict[str, Mapping[str, Any]]] = {}
    features_by_epoch: dict[str, dict[str, Mapping[str, Any]]] = {}
    eligible_ids: dict[str, tuple[str, ...]] = {}
    for epoch in ("baseline", "current"):
        eligibility[epoch] = {}
        features_by_epoch[epoch] = {}
        eligible: list[str] = []
        for feature in _features(documents[epoch], f"{queue_id} {epoch} response"):
            features_by_epoch[epoch][feature["id"]] = feature
            coverage = _item_coverage(feature, bbox, epoch)
            eligibility[epoch][feature["id"]] = coverage
            if coverage["all_required_asset_windows_within_grid"]:
                eligible.append(feature["id"])
        eligible_ids[epoch] = tuple(eligible)
    records_by_epoch = _normalized_records(source_manifest, eligible_ids, queue_id)
    selected_records, selected_items, rank, pair_count = _select_comparable_pair(
        features_by_epoch,
        records_by_epoch,
        eligible_ids,
        source_manifest,
        queue_id,
    )
    source_descriptor = _source_descriptor(files, source_manifest, source_task)
    original_selected = {
        epoch: {
            "id": original_items[epoch]["id"],
            "stac_feature_sha256": canonical_sha256(original_items[epoch]),
            "coverage": original_coverage[epoch],
        }
        for epoch in ("baseline", "current")
    }
    if selected_items is None or selected_records is None or rank is None:
        if not eligible_ids["baseline"]:
            reason = "no_full_cover_baseline_candidate"
        elif not eligible_ids["current"]:
            reason = "no_full_cover_current_candidate"
        else:
            reason = "no_comparable_full_cover_pair_in_temporal_windows"
        directory = queue_job["catalog_job"]["output_directory"]
        unresolved = {
            "queue_id": queue_id,
            "queue_position": queue_job["queue_position"],
            "entity": {
                "id": queue_job["entity"]["id"],
                "name": queue_job["entity"]["name"],
            },
            "aoi_bbox_wgs84": bbox,
            "queue_record_sha256": _canonical_hash(queue_job),
            "source_catalog_task_sha256": _canonical_hash(source_task),
            "source_artifacts": {
                "baseline_response": {
                    "file": f"{directory}/baseline-response.json",
                    **_file_record(files["baseline"]),
                },
                "current_response": {
                    "file": f"{directory}/current-response.json",
                    **_file_record(files["current"]),
                },
                "source_manifest": {
                    "file": f"{directory}/manifest.json",
                    **_file_record(files["manifest"]),
                },
            },
            "source_retrieved_at": source_manifest.get("retrieved_at"),
            "source_queries": source_manifest.get("queries"),
            "original_selected": original_selected,
            "original_selection_failed_full_support": True,
            "original_selection_failed_epochs": failed_epochs,
            "full_cover_eligible_ids": {
                epoch: list(eligible_ids[epoch]) for epoch in ("baseline", "current")
            },
            "comparable_pair_count": pair_count,
            "resolution_reason": reason,
            "outcome": "unresolved_multitile_or_supplemental_scene_required",
            "unavailable_no_scene_claim": False,
            "reselection_emitted": False,
            "change_analysis_executed": False,
        }
        return None, unresolved

    selected_ids = {
        epoch: selected_items[epoch]["id"] for epoch in ("baseline", "current")
    }
    original_ids = {
        epoch: original_items[epoch]["id"] for epoch in ("baseline", "current")
    }
    if selected_ids == original_ids:
        raise SatelliteCatalogReselectionV2Error(
            f"coverage reselection did not change the failed source pair for {queue_id}"
        )
    derived = {
        "schema_version": RESELECTION_SCHEMA_VERSION,
        "pipeline": RESELECTION_PIPELINE,
        "queue_id": queue_id,
        "queue_position": queue_job["queue_position"],
        "queue_record_sha256": _canonical_hash(queue_job),
        "entity": {
            "id": queue_job["entity"]["id"],
            "name": queue_job["entity"]["name"],
        },
        "output_directory": queue_job["catalog_job"]["output_directory"],
        "source": source_descriptor,
        "selection_policy": {
            "input": "exact_archived_baseline_and_current_stac_feature_collections",
            "candidate_filter": "all_required_asset_covering_and_interpolation_support_windows_within_grid",
            "pair_filter": "chronological_comparable_same_observed_stac_red_grid",
            "rank_after_filter": list(RANKING_POLICY),
            "network_access": False,
        },
        "eligible_ids": {
            epoch: list(eligible_ids[epoch]) for epoch in ("baseline", "current")
        },
        "comparable_pair_count": pair_count,
        "original_selection_failed_full_support": True,
        "original_selection_failed_epochs": failed_epochs,
        "original_selected_ids": original_ids,
        "selected_ids": selected_ids,
        "selection_rank": rank,
        "original_selected_features": original_selected,
        "selected_features": {
            epoch: {
                "id": selected_items[epoch]["id"],
                "datetime": selected_items[epoch]["properties"]["datetime"],
                "mgrs_tile": mgrs_tile(selected_items[epoch]),
                "stac_feature_sha256": canonical_sha256(selected_items[epoch]),
                "stac_grid_coverage": eligibility[epoch][selected_items[epoch]["id"]],
            }
            for epoch in ("baseline", "current")
        },
        "scope": dict(RESELECTION_SCOPE),
    }
    return (
        _PlannedJob(
            queue=queue_job,
            source_task=source_task,
            source_files=files,
            source_manifest=source_manifest,
            original_items=original_items,
            selected_items=selected_items,
            eligible_ids=eligible_ids,
            derived_manifest=derived,
        ),
        None,
    )


def plan_catalog_reselection_v2(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    queue_ids: Sequence[str],
) -> ReselectionPlanV2:
    """Plan explicit candidates from frozen queue and catalog artifacts only."""

    queue = _absolute_directory(queue_directory, "queue bundle")
    source = _absolute_directory(source_catalog_batch_directory, "source catalog batch")
    if queue.resolve() == source.resolve():
        raise SatelliteCatalogReselectionV2Error(
            "queue and source directories must differ"
        )
    queue_manifest, queue_rows = _read_queue(queue)
    source_document = validate_satellite_batch(queue, source)
    candidate_ids = _canonicalize_candidate_ids(queue_rows, queue_ids)
    queue_by_id = {row["queue_id"]: row for row in queue_rows}
    source_jobs = source_document.get("jobs")
    if not isinstance(source_jobs, Mapping):
        raise SatelliteCatalogReselectionV2Error(
            "source catalog batch job inventory is invalid"
        )
    missing = sorted(set(candidate_ids) - set(source_jobs))
    if missing:
        raise SatelliteCatalogReselectionV2Error(
            f"source catalog batch lacks explicit candidate tasks: {missing}"
        )
    jobs: list[_PlannedJob] = []
    unresolved_jobs: list[dict[str, Any]] = []
    for queue_id in candidate_ids:
        source_task = source_jobs[queue_id]
        if not isinstance(source_task, Mapping) or source_task.get("state") != "completed":
            raise SatelliteCatalogReselectionV2Error(
                f"explicit source catalog task is not completed: {queue_id}"
            )
        job, unresolved = _assess_candidate(
            queue_by_id[queue_id], source_task, source
        )
        if job is not None:
            jobs.append(job)
        else:
            assert unresolved is not None
            unresolved_jobs.append(unresolved)
    unresolved_document = {
        "schema_version": RESELECTION_SCHEMA_VERSION,
        "pipeline": "satellite_catalog_coverage_unresolved_assessment_v2",
        "candidate_queue_ids": list(candidate_ids),
        "meaning": (
            "An unresolved record means the exact archived responses do not contain "
            "a full-cover comparable pair after required-asset read-window and "
            "interpolation-support filtering. It is not a no-scene claim; a separately "
            "archived supplemental scene or a versioned multi-tile processor is required."
        ),
        "jobs": unresolved_jobs,
        "scope": dict(RESELECTION_SCOPE),
    }
    return ReselectionPlanV2(
        queue=queue,
        source=source,
        queue_manifest=queue_manifest,
        source_document=source_document,
        queue_rows=tuple(queue_rows),
        candidate_queue_ids=candidate_ids,
        jobs=tuple(jobs),
        unresolved=unresolved_document,
    )


def _candidate_bindings(plan: ReselectionPlanV2) -> dict[str, Any]:
    supported = {
        job.queue["queue_id"]: {
            "queue_position": job.queue["queue_position"],
            "queue_record_sha256": _canonical_hash(job.queue),
            "source_catalog_task_sha256": _canonical_hash(job.source_task),
            "original_selected_ids": dict(job.derived_manifest["original_selected_ids"]),
            "selected_ids": dict(job.derived_manifest["selected_ids"]),
            "selected_feature_sha256": {
                epoch: job.derived_manifest["selected_features"][epoch][
                    "stac_feature_sha256"
                ]
                for epoch in ("baseline", "current")
            },
        }
        for job in plan.jobs
    }
    unresolved = {
        job["queue_id"]: {
            "queue_position": job["queue_position"],
            "queue_record_sha256": job["queue_record_sha256"],
            "source_catalog_task_sha256": job["source_catalog_task_sha256"],
            "outcome": job["outcome"],
            "source_artifacts": job["source_artifacts"],
        }
        for job in plan.unresolved["jobs"]
    }
    return {
        "candidate_queue_ids": list(plan.candidate_queue_ids),
        "supported": supported,
        "unresolved": unresolved,
    }


def _expected_header_assets(
    plan: ReselectionPlanV2,
) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    queue_order = {queue_id: index for index, queue_id in enumerate(plan.candidate_queue_ids)}
    for job in plan.jobs:
        queue_id = job.queue["queue_id"]
        for epoch in ("baseline", "current"):
            item = job.selected_items[epoch]
            for asset_name in REQUIRED_ASSETS:
                href = item["assets"][asset_name]["href"]
                validate_asset_href(href)
                identity = {
                    "item_id": item["id"],
                    "asset": asset_name,
                    "epoch": epoch,
                }
                prior = assets.get(href)
                if prior is None:
                    assets[href] = {**identity, "queue_ids": [queue_id]}
                    continue
                if any(prior[field] != identity[field] for field in identity):
                    raise SatelliteCatalogReselectionV2Error(
                        f"selected asset href is shared by different identities: {href}"
                    )
                if queue_id not in prior["queue_ids"]:
                    prior["queue_ids"].append(queue_id)
                    prior["queue_ids"].sort(key=queue_order.__getitem__)
    return assets


def _header_binding(plan: ReselectionPlanV2) -> dict[str, Any]:
    bindings = _candidate_bindings(plan)
    return {
        "candidate_queue_ids": list(plan.candidate_queue_ids),
        "queue_bundle": _queue_lineage(plan.queue, plan.queue_manifest),
        "source_catalog_batch": _source_lineage(plan.source, plan.source_document),
        "candidate_bindings": bindings,
        "selection_plan_sha256": _canonical_hash(bindings),
    }


def capture_grid_header_evidence_v2(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    queue_ids: Sequence[str],
    output_file: str | Path,
    *,
    captured_at: str,
) -> dict[str, Any]:
    """Open selected COG metadata only; no raster pixel read is issued."""

    plan = plan_catalog_reselection_v2(
        queue_directory,
        source_catalog_batch_directory,
        queue_ids,
    )
    captured = _timestamp(captured_at, "header captured_at")
    path = Path(os.path.abspath(os.fspath(output_file)))
    if path.exists() or path.is_symlink():
        raise SatelliteCatalogReselectionV2Error(
            "header evidence output already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise SatelliteCatalogReselectionV2Error(
            "header evidence parent may not be a symlink"
        )
    _, rasterio, _, _ = v1._imports()
    expected = _expected_header_assets(plan)
    records: list[dict[str, Any]] = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", PROJ_NETWORK="OFF"):
        for href in sorted(expected):
            validate_asset_href(href)
            with rasterio.open(href) as dataset:
                records.append(
                    {
                        **expected[href],
                        "href": href,
                        "width": int(dataset.width),
                        "height": int(dataset.height),
                        "count": int(dataset.count),
                        "dtype": str(dataset.dtypes[0]),
                        "crs": str(dataset.crs),
                        "transform": list(dataset.transform)[:6],
                        "nodata": dataset.nodata,
                        "driver": str(dataset.driver),
                    }
                )
    document = {
        "schema_version": HEADER_SCHEMA_VERSION,
        "pipeline": HEADER_PIPELINE,
        "captured_at": captured,
        "scope": dict(HEADER_SCOPE),
        "runtime": _runtime_lineage(),
        **_header_binding(plan),
        "asset_open_operations": len(records),
        "assets": records,
    }
    raw = _canonical_bytes(document)
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    return document


def _validate_header_evidence(
    plan: ReselectionPlanV2,
    raw: bytes,
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    value = _decode_json(raw, "grid header evidence")
    if not isinstance(value, Mapping) or raw != _canonical_bytes(value):
        raise SatelliteCatalogReselectionV2Error(
            "grid header evidence must be canonical JSON"
        )
    expected_keys = {
        "schema_version",
        "pipeline",
        "captured_at",
        "scope",
        "runtime",
        "candidate_queue_ids",
        "queue_bundle",
        "source_catalog_batch",
        "candidate_bindings",
        "selection_plan_sha256",
        "asset_open_operations",
        "assets",
    }
    if set(value) != expected_keys:
        raise SatelliteCatalogReselectionV2Error(
            "grid header evidence schema is invalid"
        )
    if value.get("schema_version") != HEADER_SCHEMA_VERSION or value.get(
        "pipeline"
    ) != HEADER_PIPELINE:
        raise SatelliteCatalogReselectionV2Error(
            "grid header evidence identity is invalid"
        )
    _timestamp(value.get("captured_at"), "header captured_at")
    if value.get("scope") != HEADER_SCOPE:
        raise SatelliteCatalogReselectionV2Error(
            "grid header evidence scope changed"
        )
    if value.get("runtime") != _runtime_lineage():
        raise SatelliteCatalogReselectionV2Error("grid header runtime changed")
    binding = _header_binding(plan)
    if any(value.get(field) != binding[field] for field in binding):
        raise SatelliteCatalogReselectionV2Error(
            "grid header candidate or input lineage changed"
        )
    records = value.get("assets")
    if not isinstance(records, list) or value.get("asset_open_operations") != len(records):
        raise SatelliteCatalogReselectionV2Error(
            "grid header asset count is invalid"
        )
    expected = _expected_header_assets(plan)
    record_keys = {
        "item_id",
        "asset",
        "epoch",
        "queue_ids",
        "href",
        "width",
        "height",
        "count",
        "dtype",
        "crs",
        "transform",
        "nodata",
        "driver",
    }
    by_href: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping) or set(record) != record_keys:
            raise SatelliteCatalogReselectionV2Error(
                "grid header asset schema is invalid"
            )
        href = record.get("href")
        validate_asset_href(href)
        if href in by_href:
            raise SatelliteCatalogReselectionV2Error(
                "grid header hrefs are not unique"
            )
        by_href[href] = record
    if list(by_href) != sorted(by_href) or set(by_href) != set(expected):
        raise SatelliteCatalogReselectionV2Error(
            "grid header asset inventory is not the exact selected inventory"
        )
    selected_by_id = {
        item["id"]: item
        for job in plan.jobs
        for item in job.selected_items.values()
    }
    for href, identity in expected.items():
        record = by_href[href]
        if any(
            record[field] != identity[field]
            for field in ("item_id", "asset", "epoch", "queue_ids")
        ):
            raise SatelliteCatalogReselectionV2Error(
                f"grid header identity changed for {href}"
            )
        item = selected_by_id[identity["item_id"]]
        stac_grid = _stac_grid(item, identity["asset"])
        if (
            record["width"] != stac_grid["width"]
            or record["height"] != stac_grid["height"]
            or record["crs"] != stac_grid["crs"]
            or record["transform"] != stac_grid["transform"]
        ):
            raise SatelliteCatalogReselectionV2Error(
                f"grid header does not match archived STAC metadata for {href}"
            )
        if record["count"] != 1 or record["driver"] != "GTiff":
            raise SatelliteCatalogReselectionV2Error(
                f"grid header band/driver contract changed for {href}"
            )
        if not isinstance(record["dtype"], str) or not record["dtype"]:
            raise SatelliteCatalogReselectionV2Error(
                f"grid header dtype is invalid for {href}"
            )
        if record["nodata"] != 0:
            raise SatelliteCatalogReselectionV2Error(
                f"grid header nodata changed for {href}"
            )
    for job in plan.jobs:
        bbox = job.queue["location"]["aoi_bbox_wgs84"]
        for epoch in ("baseline", "current"):
            coverage = _item_coverage(
                job.selected_items[epoch],
                bbox,
                epoch,
                header_by_href=by_href,
            )
            if not coverage["all_required_asset_windows_within_grid"]:
                raise SatelliteCatalogReselectionV2Error(
                    f"selected observed headers do not cover {job.queue['queue_id']} {epoch}"
                )
    return value, by_href


def _job_manifest_with_headers(
    job: _PlannedJob,
    header_by_href: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    value = json.loads(json.dumps(job.derived_manifest))
    bbox = job.queue["location"]["aoi_bbox_wgs84"]
    for epoch in ("baseline", "current"):
        value["selected_features"][epoch]["observed_header_coverage"] = _item_coverage(
            job.selected_items[epoch],
            bbox,
            epoch,
            header_by_href=header_by_href,
        )
    return value


def _release_top_manifest(
    plan: ReselectionPlanV2,
    release: Path,
    *,
    generated_at: str,
    header_record: Mapping[str, Any],
    job_manifests: Mapping[str, Mapping[str, Any]],
    unresolved: Mapping[str, Any],
) -> dict[str, Any]:
    jobs: dict[str, Any] = {}
    for job in plan.jobs:
        queue_id = job.queue["queue_id"]
        directory = job.queue["catalog_job"]["output_directory"]
        job_dir = release.joinpath(*PurePosixPath(directory).parts)
        manifest = job_manifests[queue_id]
        jobs[queue_id] = {
            "queue_position": job.queue["queue_position"],
            "entity_id": job.queue["entity"]["id"],
            "state": "completed",
            "output_directory": directory,
            "original_selected_ids": manifest["original_selected_ids"],
            "selected_ids": manifest["selected_ids"],
            "selected_feature_sha256": {
                epoch: manifest["selected_features"][epoch]["stac_feature_sha256"]
                for epoch in ("baseline", "current")
            },
            "source_catalog_task_sha256": manifest["source"]["catalog_task_sha256"],
            "artifacts": {
                name: _file_record(job_dir / name)
                for name in (
                    "baseline-response.json",
                    "current-response.json",
                    SOURCE_MANIFEST_FILENAME,
                    JOB_MANIFEST_FILENAME,
                )
            },
        }
    supported_ids = tuple(job.queue["queue_id"] for job in plan.jobs)
    unresolved_ids = tuple(job["queue_id"] for job in unresolved["jobs"])
    unique_aois = {tuple(job.queue["location"]["aoi_bbox_wgs84"]) for job in plan.jobs}
    return {
        "schema_version": RESELECTION_SCHEMA_VERSION,
        "pipeline": RESELECTION_PIPELINE,
        "state": "complete",
        "generated_at": _timestamp(generated_at, "reselection generated_at"),
        "queue_bundle": _queue_lineage(plan.queue, plan.queue_manifest),
        "source_catalog_batch": _source_lineage(plan.source, plan.source_document),
        "builder": _builder_lineage(),
        "scope": dict(RESELECTION_SCOPE),
        "configuration": {
            "candidate_queue_ids": list(plan.candidate_queue_ids),
            "supported_queue_ids": list(supported_ids),
            "unresolved_queue_ids": list(unresolved_ids),
            "candidate_ids_canonicalized_to_queue_order": True,
            "duplicate_explicit_ids_deduplicated": True,
            "required_assets": list(REQUIRED_ASSETS),
            "ranking_policy": list(RANKING_POLICY),
            "interpolation_support_policy": {
                "baseline_red_native_pixels": 0,
                "baseline_other_reflectance_native_pixels": 1,
                "current_reflectance_native_pixels": 1,
                "scl_nearest_native_pixels": 0,
            },
        },
        "grid_header_evidence": {
            "file": HEADER_EVIDENCE_FILENAME,
            **_file_record(release / HEADER_EVIDENCE_FILENAME),
            "captured_at": header_record["captured_at"],
            "selection_plan_sha256": header_record["selection_plan_sha256"],
            "asset_open_operations": header_record["asset_open_operations"],
        },
        "unresolved_assessment": {
            "file": UNRESOLVED_FILENAME,
            **_file_record(release / UNRESOLVED_FILENAME),
            "jobs": len(unresolved["jobs"]),
        },
        "jobs": jobs,
        "summary": {
            "candidate_jobs_assessed": len(plan.candidate_queue_ids),
            "jobs_reselected": len(jobs),
            "unique_aois_reselected": len(unique_aois),
            "jobs_unresolved_multitile_needed": len(unresolved["jobs"]),
            "raw_provider_response_files_copied": 2 * len(jobs),
            "source_catalog_manifest_files_copied": len(jobs),
            "change_jobs_executed": 0,
            "atlas_rows_emitted": 0,
        },
    }


def _closed_tree(
    release: Path,
    plan: ReselectionPlanV2,
    *,
    require_frozen: bool,
) -> None:
    expected_files = {
        release / RESELECTION_MANIFEST_FILENAME,
        release / HEADER_EVIDENCE_FILENAME,
        release / UNRESOLVED_FILENAME,
    }
    expected_directories = {release}
    for job in plan.jobs:
        directory = release.joinpath(
            *_relative_parts(
                job.queue["catalog_job"]["output_directory"],
                "catalog output directory",
            )
        )
        current = directory
        while current != release:
            expected_directories.add(current)
            current = current.parent
        expected_files.update(
            directory / name
            for name in (
                "baseline-response.json",
                "current-response.json",
                SOURCE_MANIFEST_FILENAME,
                JOB_MANIFEST_FILENAME,
            )
        )
    for path in release.rglob("*"):
        if path.is_symlink():
            raise SatelliteCatalogReselectionV2Error(
                f"reselection release contains a symlink: {path}"
            )
        if path.is_dir() and path not in expected_directories:
            raise SatelliteCatalogReselectionV2Error(
                f"reselection release contains an unexpected directory: {path}"
            )
        if path.is_file() and path not in expected_files:
            raise SatelliteCatalogReselectionV2Error(
                f"reselection release contains an unexpected file: {path}"
            )
        if not path.is_dir() and not path.is_file():
            raise SatelliteCatalogReselectionV2Error(
                f"reselection release contains a non-regular path: {path}"
            )
    if not all(path.is_file() and not path.is_symlink() for path in expected_files):
        raise SatelliteCatalogReselectionV2Error(
            "reselection release is missing files"
        )
    if require_frozen:
        for directory in expected_directories:
            if stat.S_IMODE(directory.stat().st_mode) != 0o555:
                raise SatelliteCatalogReselectionV2Error(
                    f"reselection directory is not frozen: {directory}"
                )
        for path in expected_files:
            if stat.S_IMODE(path.stat().st_mode) != 0o444:
                raise SatelliteCatalogReselectionV2Error(
                    f"reselection file is not frozen: {path}"
                )


def _validate_release(
    plan: ReselectionPlanV2,
    release: Path,
    *,
    require_frozen: bool,
) -> dict[str, Any]:
    for input_root in (plan.queue, plan.source):
        resolved_release = release.resolve()
        resolved_input = input_root.resolve()
        if (
            resolved_release == resolved_input
            or resolved_input in resolved_release.parents
            or resolved_release in resolved_input.parents
        ):
            raise SatelliteCatalogReselectionV2Error(
                "reselection release must be separate from its inputs"
            )
    _closed_tree(release, plan, require_frozen=require_frozen)
    header_path = _regular_file(
        release, HEADER_EVIDENCE_FILENAME, "release grid header evidence"
    )
    header_value, header_by_href = _validate_header_evidence(
        plan, header_path.read_bytes()
    )
    job_manifests: dict[str, Mapping[str, Any]] = {}
    for job in plan.jobs:
        queue_id = job.queue["queue_id"]
        relative = job.queue["catalog_job"]["output_directory"]
        directory = release.joinpath(
            *_relative_parts(relative, "catalog output directory")
        )
        exact_pairs = (
            (directory / "baseline-response.json", job.source_files["baseline"]),
            (directory / "current-response.json", job.source_files["current"]),
            (directory / SOURCE_MANIFEST_FILENAME, job.source_files["manifest"]),
        )
        for copied, source in exact_pairs:
            if (
                copied.is_symlink()
                or not copied.is_file()
                or copied.read_bytes() != source.read_bytes()
            ):
                raise SatelliteCatalogReselectionV2Error(
                    f"exact source bytes changed for {queue_id}/{copied.name}"
                )
        manifest = _canonical_json_file(
            directory / JOB_MANIFEST_FILENAME,
            f"{queue_id} reselection manifest",
        )
        expected = _job_manifest_with_headers(job, header_by_href)
        if manifest != expected:
            raise SatelliteCatalogReselectionV2Error(
                f"reselection manifest does not reproduce for {queue_id}"
            )
        job_manifests[queue_id] = manifest
    unresolved = _canonical_json_file(
        _regular_file(release, UNRESOLVED_FILENAME, "unresolved assessment"),
        "unresolved assessment",
    )
    if unresolved != plan.unresolved:
        raise SatelliteCatalogReselectionV2Error(
            "unresolved assessment does not reproduce"
        )
    manifest = _canonical_json_file(
        _regular_file(release, RESELECTION_MANIFEST_FILENAME, "reselection manifest"),
        "reselection manifest",
    )
    if not isinstance(manifest, Mapping):
        raise SatelliteCatalogReselectionV2Error(
            "reselection manifest must be an object"
        )
    expected_top = _release_top_manifest(
        plan,
        release,
        generated_at=manifest.get("generated_at"),
        header_record=header_value,
        job_manifests=job_manifests,
        unresolved=unresolved,
    )
    if manifest != expected_top:
        raise SatelliteCatalogReselectionV2Error(
            "reselection top-level manifest does not reproduce"
        )
    return dict(manifest)


def validate_catalog_reselection_v2(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    queue_ids: Sequence[str],
    release_directory: str | Path,
) -> dict[str, Any]:
    """Validate one frozen v2 release without network access."""

    plan = plan_catalog_reselection_v2(
        queue_directory,
        source_catalog_batch_directory,
        queue_ids,
    )
    release = _absolute_directory(release_directory, "reselection release")
    return _validate_release(plan, release, require_frozen=True)


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(0o444)
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        directory.chmod(0o555)
    root.chmod(0o555)


def _remove_failed_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink():
        return
    stage.chmod(0o755)
    for path in stage.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)
        elif path.is_file() and not path.is_symlink():
            path.chmod(0o644)
    shutil.rmtree(stage)


def build_catalog_reselection_v2(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    queue_ids: Sequence[str],
    grid_header_evidence_file: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Atomically build and freeze one closed-world v2 release offline."""

    plan = plan_catalog_reselection_v2(
        queue_directory,
        source_catalog_batch_directory,
        queue_ids,
    )
    header_path = Path(os.path.abspath(os.fspath(grid_header_evidence_file)))
    if header_path.is_symlink() or not header_path.is_file():
        raise SatelliteCatalogReselectionV2Error(
            "grid header evidence is not a regular file"
        )
    header_raw = header_path.read_bytes()
    header_value, header_by_href = _validate_header_evidence(plan, header_raw)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.exists() or output.is_symlink():
        raise SatelliteCatalogReselectionV2Error(
            "reselection output already exists"
        )
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise SatelliteCatalogReselectionV2Error(
            "reselection output parent is invalid"
        )
    stage = output.with_name(f".{output.name}.staging-v2")
    if stage.exists() or stage.is_symlink():
        raise SatelliteCatalogReselectionV2Error(
            "reselection staging path already exists"
        )
    stage.mkdir(mode=0o755)
    moved = False
    try:
        (stage / HEADER_EVIDENCE_FILENAME).write_bytes(header_raw)
        job_manifests: dict[str, Mapping[str, Any]] = {}
        for job in plan.jobs:
            queue_id = job.queue["queue_id"]
            relative = job.queue["catalog_job"]["output_directory"]
            destination = stage.joinpath(
                *_relative_parts(relative, "catalog output directory")
            )
            destination.mkdir(parents=True)
            copies = {
                "baseline-response.json": job.source_files["baseline"],
                "current-response.json": job.source_files["current"],
                SOURCE_MANIFEST_FILENAME: job.source_files["manifest"],
            }
            for name, source_path in copies.items():
                shutil.copyfile(source_path, destination / name)
                if (destination / name).read_bytes() != source_path.read_bytes():
                    raise SatelliteCatalogReselectionV2Error(
                        f"exact source copy changed for {queue_id}/{name}"
                    )
            manifest = _job_manifest_with_headers(job, header_by_href)
            (destination / JOB_MANIFEST_FILENAME).write_bytes(
                _canonical_bytes(manifest)
            )
            job_manifests[queue_id] = manifest
        (stage / UNRESOLVED_FILENAME).write_bytes(_canonical_bytes(plan.unresolved))
        top = _release_top_manifest(
            plan,
            stage,
            generated_at=generated_at,
            header_record=header_value,
            job_manifests=job_manifests,
            unresolved=plan.unresolved,
        )
        (stage / RESELECTION_MANIFEST_FILENAME).write_bytes(_canonical_bytes(top))
        _validate_release(plan, stage, require_frozen=False)
        _fsync_tree(stage)
        _freeze_tree(stage)
        _validate_release(plan, stage, require_frozen=True)
        os.replace(stage, output)
        moved = True
        parent_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except BaseException:
        if not moved:
            _remove_failed_stage(stage)
        raise
    return validate_catalog_reselection_v2(
        queue_directory,
        source_catalog_batch_directory,
        queue_ids,
        output,
    )


def release_catalog_tasks_v2(
    document: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return supported v2 tasks in canonical queue order for a change runner."""

    configuration = document.get("configuration")
    jobs = document.get("jobs")
    if not isinstance(configuration, Mapping) or not isinstance(jobs, Mapping):
        raise SatelliteCatalogReselectionV2Error(
            "reselection job inventory is invalid"
        )
    supported = configuration.get("supported_queue_ids")
    if not isinstance(supported, list) or any(
        not isinstance(queue_id, str) for queue_id in supported
    ):
        raise SatelliteCatalogReselectionV2Error(
            "supported queue ID inventory is invalid"
        )
    if len(supported) != len(set(supported)) or set(jobs) != set(supported):
        raise SatelliteCatalogReselectionV2Error(
            "reselection job inventory is not canonical"
        )
    tasks: dict[str, dict[str, Any]] = {}
    for queue_id in supported:
        job = jobs[queue_id]
        artifacts = job["artifacts"]
        tasks[queue_id] = {
            "state": "completed",
            "output_directory": job["output_directory"],
            "selected_ids": dict(job["selected_ids"]),
            "artifacts": {
                "baseline-response.json": dict(artifacts["baseline-response.json"]),
                "current-response.json": dict(artifacts["current-response.json"]),
                "manifest.json": dict(artifacts["manifest.json"]),
            },
        }
    return tasks
