"""Offline, coverage-aware reselection of frozen Sentinel-2 catalog responses.

This lane never edits or filters the raw provider responses.  It derives a new
selection manifest beside exact byte copies of those responses and binds the
selected features to metadata-only COG header observations.  The output is an
input for the side-by-side reselected change runner; it is not compatible with
the legacy catalog-batch validator and never claims that a derived response is
raw provider output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
from typing import Any, Iterable, Mapping, Sequence

from .satellite_batch import BATCH_MANIFEST_FILENAME, validate_satellite_batch
from .satellite_catalog import select_scene_pair
from .satellite_change import (
    REQUIRED_ASSETS,
    canonical_sha256,
    ensure_comparable,
    mgrs_tile,
    select_feature,
    validate_asset_href,
    validate_item,
)
from .satellite_queue import (
    MANIFEST_FILENAME as QUEUE_MANIFEST_FILENAME,
    QUEUE_FILENAME,
    validate_queue_bundle,
)


RESELECTION_SCHEMA_VERSION = 1
RESELECTION_PIPELINE = "satellite_catalog_coverage_reselection"
RESELECTION_MANIFEST_FILENAME = "batch-manifest.json"
JOB_MANIFEST_FILENAME = "manifest.json"
SOURCE_MANIFEST_FILENAME = "source-manifest.json"
HEADER_EVIDENCE_FILENAME = "grid-headers.json"
UNRESOLVED_FILENAME = "unresolved-multitile-needed.json"
HEADER_SCHEMA_VERSION = 1
HEADER_PIPELINE = "sentinel_cog_grid_header_evidence"

# These are the exact active-lane rows found by the 2026-07-19 closed-world
# edge audit.  France positions 14/15 deliberately remain unresolved below.
SUPPORTED_QUEUE_IDS = (
    "satq-4d34785d2d5cd9d464f7f92a",  # 26
    "satq-3a5dbdef8b0fd5a8f4e53bf1",  # 27
    "satq-3a6e7cebee3418935b32d558",  # 33
    "satq-10fa7fdd321e3f562fa65cf1",  # 34
    "satq-72ddffe07d04ec5163bcf3aa",  # 35
    "satq-5cdc52edd17f467464429e58",  # 36
    "satq-fc2dcd4f6d2f02bafd480ac0",  # 53
    "satq-6dd98f29dab9b90554179a0d",  # 54
    "satq-e8612036e6a617b646454ce1",  # 55
    "satq-debb4591c15c3a24397ff1e6",  # 59
    "satq-0384b818546e954492a85864",  # 60
    "satq-85b107c03206533613a36a61",  # 61
    "satq-adf57ea98a8cd232f18bf64b",  # 62
    "satq-e289e0ed299bb7598f1d609f",  # 73
    "satq-afa8c56e14cc2d85e6170460",  # 74
)
UNRESOLVED_QUEUE_IDS = (
    "satq-b04cfd38a1d3ffa8b8872e94",  # 14
    "satq-ed31dd145f53c3c54c522ff7",  # 15
)

RESELECTION_SCOPE = {
    "mode": "offline_coverage_filtered_reselection",
    "network_access_during_build": False,
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
    "review_required": True,
}

HEADER_SCOPE = {
    "method": "rasterio_open_metadata_only",
    "pixel_reads": 0,
    "cog_input_bytes_archived": False,
    "http_request_count": None,
    "asset_open_operations_are_not_http_request_counts": True,
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
    "scripts/build_satellite_catalog_reselection.py",
)


class SatelliteCatalogReselectionError(ValueError):
    """Raised when frozen inputs, coverage, lineage, or output is invalid."""


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
    if not isinstance(value, str) or not value.strip():
        raise SatelliteCatalogReselectionError(
            f"{field} must be a non-empty RFC 3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteCatalogReselectionError(
            f"{field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteCatalogReselectionError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _absolute_directory(path: str | Path, label: str) -> Path:
    result = Path(os.path.abspath(os.fspath(path)))
    if result.is_symlink() or not result.is_dir():
        raise SatelliteCatalogReselectionError(
            f"{label} is not a regular directory: {result}"
        )
    return result


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SatelliteCatalogReselectionError(
            f"{label} must be a safe POSIX relative path"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise SatelliteCatalogReselectionError(
            f"{label} must be a safe POSIX relative path"
        )
    return pure.parts


def _regular_file(root: Path, relative: Any, label: str) -> Path:
    parts = _relative_parts(relative, label)
    path = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise SatelliteCatalogReselectionError(f"{label} escapes its root")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteCatalogReselectionError(f"{label} traverses a symlink")
    if path.is_symlink() or not path.is_file():
        raise SatelliteCatalogReselectionError(f"{label} is not a regular file")
    return path


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SatelliteCatalogReselectionError(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise SatelliteCatalogReselectionError(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteCatalogReselectionError(f"{label} is not valid JSON") from error


def _canonical_json_file(path: Path, label: str) -> Any:
    raw = path.read_bytes()
    value = _decode_json(raw, label)
    if raw != _canonical_bytes(value):
        raise SatelliteCatalogReselectionError(f"{label} is not canonical JSON")
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
            raise SatelliteCatalogReselectionError(
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


def _imports() -> tuple[Any, Any, Any, Any]:
    try:
        from affine import Affine
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds
    except ImportError as error:
        raise SatelliteCatalogReselectionError(
            "coverage-aware reselection requires rasterio"
        ) from error
    return Affine, rasterio, transform_bounds, from_bounds


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SatelliteCatalogReselectionError(f"{field} must be a positive integer")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteCatalogReselectionError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SatelliteCatalogReselectionError(f"{field} must be finite")
    return result


def _stac_grid(item: Mapping[str, Any], asset_name: str) -> dict[str, Any]:
    asset = item["assets"][asset_name]
    shape = asset.get("proj:shape")
    transform = asset.get("proj:transform")
    epsg = asset.get("proj:epsg", item.get("properties", {}).get("proj:epsg"))
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in shape)
    ):
        raise SatelliteCatalogReselectionError(
            f"STAC item {item['id']} asset {asset_name} has invalid proj:shape"
        )
    if not isinstance(transform, list) or len(transform) not in {6, 9}:
        raise SatelliteCatalogReselectionError(
            f"STAC item {item['id']} asset {asset_name} has invalid proj:transform"
        )
    values = [_finite_number(value, "proj:transform value") for value in transform]
    if len(values) == 9 and values[6:] != [0.0, 0.0, 1.0]:
        raise SatelliteCatalogReselectionError(
            f"STAC item {item['id']} asset {asset_name} has a non-affine transform"
        )
    first = values[:6]
    if first[1] != 0 or first[3] != 0 or first[0] <= 0 or first[4] >= 0:
        raise SatelliteCatalogReselectionError(
            f"STAC item {item['id']} asset {asset_name} grid is not north-up"
        )
    if isinstance(epsg, bool) or not isinstance(epsg, int) or epsg <= 0:
        raise SatelliteCatalogReselectionError(
            f"STAC item {item['id']} asset {asset_name} has invalid proj:epsg"
        )
    return {
        "crs": f"EPSG:{epsg}",
        "height": shape[0],
        "width": shape[1],
        "transform": first,
    }


def _support_pixels(epoch: str, asset_name: str) -> int:
    if epoch not in {"baseline", "current"}:
        raise SatelliteCatalogReselectionError("epoch must be baseline or current")
    if asset_name == "scl":
        return 0
    if epoch == "baseline" and asset_name == "red":
        return 0
    return 1


def _coverage_record(
    item: Mapping[str, Any],
    asset_name: str,
    bbox: Sequence[float],
    epoch: str,
    *,
    grid_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    Affine, rasterio, transform_bounds, from_bounds = _imports()
    grid = dict(grid_override) if grid_override is not None else _stac_grid(item, asset_name)
    expected_keys = {"crs", "height", "width", "transform"}
    if set(grid) != expected_keys:
        raise SatelliteCatalogReselectionError("asset grid evidence schema is invalid")
    height = _positive_integer(grid["height"], "asset grid height")
    width = _positive_integer(grid["width"], "asset grid width")
    transform_values = grid["transform"]
    if not isinstance(transform_values, list) or len(transform_values) != 6:
        raise SatelliteCatalogReselectionError("asset grid transform is invalid")
    transform = Affine(*[_finite_number(value, "asset grid transform") for value in transform_values])
    crs = grid["crs"]
    if not isinstance(crs, str) or not crs.startswith("EPSG:"):
        raise SatelliteCatalogReselectionError("asset grid CRS is invalid")
    with rasterio.Env(PROJ_NETWORK="OFF"):
        projected = transform_bounds("EPSG:4326", crs, *bbox)
    fractional = from_bounds(*projected, transform=transform)
    column_start = math.floor(float(fractional.col_off))
    row_start = math.floor(float(fractional.row_off))
    column_stop = math.ceil(float(fractional.col_off + fractional.width))
    row_stop = math.ceil(float(fractional.row_off + fractional.height))
    if column_stop <= column_start or row_stop <= row_start:
        raise SatelliteCatalogReselectionError("AOI produces an empty asset window")
    support = _support_pixels(epoch, asset_name)
    supported = (
        column_start - support,
        row_start - support,
        column_stop + support,
        row_stop + support,
    )
    within = (
        supported[0] >= 0
        and supported[1] >= 0
        and supported[2] <= width
        and supported[3] <= height
    )
    return {
        "asset": asset_name,
        "href": item["assets"][asset_name]["href"],
        "crs": crs,
        "height": height,
        "width": width,
        "transform": list(transform)[:6],
        "covering_window": [
            column_start,
            row_start,
            column_stop - column_start,
            row_stop - row_start,
        ],
        "interpolation_support_pixels": support,
        "supported_window": [
            supported[0],
            supported[1],
            supported[2] - supported[0],
            supported[3] - supported[1],
        ],
        "within_grid": within,
    }


def _item_coverage(
    item: Mapping[str, Any],
    bbox: Sequence[float],
    epoch: str,
    *,
    header_by_href: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    validate_item(item)
    assets: list[dict[str, Any]] = []
    for asset_name in REQUIRED_ASSETS:
        href = item["assets"][asset_name]["href"]
        override = None
        if header_by_href is not None:
            header = header_by_href.get(href)
            if header is None:
                raise SatelliteCatalogReselectionError(
                    f"header evidence is missing selected asset {href}"
                )
            override = {
                "crs": header["crs"],
                "height": header["height"],
                "width": header["width"],
                "transform": header["transform"],
            }
        assets.append(
            _coverage_record(
                item,
                asset_name,
                bbox,
                epoch,
                grid_override=override,
            )
        )
    return {
        "item_id": item["id"],
        "epoch": epoch,
        "all_required_asset_windows_within_grid": all(
            asset["within_grid"] for asset in assets
        ),
        "assets": assets,
    }


def _features(document: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    if document.get("type") != "FeatureCollection" or not isinstance(
        document.get("features"), list
    ):
        raise SatelliteCatalogReselectionError(
            f"{label} must be a STAC FeatureCollection"
        )
    result: list[Mapping[str, Any]] = []
    ids: set[str] = set()
    for index, feature in enumerate(document["features"]):
        if not isinstance(feature, Mapping):
            raise SatelliteCatalogReselectionError(f"{label} feature {index} is invalid")
        validate_item(feature)
        item_id = feature["id"]
        if item_id in ids:
            raise SatelliteCatalogReselectionError(f"{label} has duplicate item {item_id}")
        ids.add(item_id)
        result.append(feature)
    return result


def _seasonal_distance(first: datetime, second: datetime) -> int:
    first_day = date(2000, first.month, first.day)
    second_day = date(2000, second.month, second.day)
    distance = abs((first_day - second_day).days)
    return min(distance, 366 - distance)


def _record_datetime(record: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(record["datetime"]).replace("Z", "+00:00"))


def _rank_record(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    baseline_target: str,
    current_target: str,
) -> dict[str, Any]:
    baseline_datetime = _record_datetime(baseline)
    current_datetime = _record_datetime(current)
    baseline_target_datetime = datetime.combine(
        date.fromisoformat(baseline_target), datetime.min.time(), UTC
    )
    current_target_datetime = datetime.combine(
        date.fromisoformat(current_target), datetime.min.time(), UTC
    )
    same_known_tile = (
        baseline.get("mgrs_tile") is not None
        and baseline.get("mgrs_tile") == current.get("mgrs_tile")
    )
    return {
        "policy": list(RANKING_POLICY),
        "rank": [
            0 if same_known_tile else 1,
            _seasonal_distance(baseline_datetime, current_datetime),
            float(baseline["cloud_cover"]) + float(current["cloud_cover"]),
            abs((baseline_datetime - baseline_target_datetime).total_seconds())
            + abs((current_datetime - current_target_datetime).total_seconds()),
            baseline["datetime"],
            current["datetime"],
            baseline["item_id"],
            current["item_id"],
        ],
    }


def _source_job_files(
    source: Path, task: Mapping[str, Any], queue_id: str
) -> dict[str, Path]:
    directory = task.get("output_directory")
    if not isinstance(directory, str):
        raise SatelliteCatalogReselectionError(
            f"source task output directory is invalid for {queue_id}"
        )
    return {
        "baseline": _regular_file(
            source, f"{directory}/baseline-response.json", f"{queue_id} baseline response"
        ),
        "current": _regular_file(
            source, f"{directory}/current-response.json", f"{queue_id} current response"
        ),
        "manifest": _regular_file(
            source, f"{directory}/manifest.json", f"{queue_id} source manifest"
        ),
    }


@dataclass(frozen=True, slots=True)
class _PlannedJob:
    queue: Mapping[str, Any]
    source_task: Mapping[str, Any]
    source_files: Mapping[str, Path]
    source_manifest: Mapping[str, Any]
    baseline_document: Mapping[str, Any]
    current_document: Mapping[str, Any]
    original_items: Mapping[str, Mapping[str, Any]]
    selected_items: Mapping[str, Mapping[str, Any]]
    eligible_ids: Mapping[str, tuple[str, ...]]
    derived_manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReselectionPlan:
    queue: Path
    source: Path
    queue_manifest: Mapping[str, Any]
    source_document: Mapping[str, Any]
    queue_rows: tuple[dict[str, Any], ...]
    jobs: tuple[_PlannedJob, ...]
    unresolved: Mapping[str, Any]


def _job_plan(
    queue_job: Mapping[str, Any],
    source_task: Mapping[str, Any],
    source: Path,
) -> _PlannedJob:
    queue_id = queue_job["queue_id"]
    files = _source_job_files(source, source_task, queue_id)
    baseline_raw = files["baseline"].read_bytes()
    current_raw = files["current"].read_bytes()
    manifest_raw = files["manifest"].read_bytes()
    baseline_document = _decode_json(baseline_raw, f"{queue_id} baseline response")
    current_document = _decode_json(current_raw, f"{queue_id} current response")
    source_manifest = _decode_json(manifest_raw, f"{queue_id} source manifest")
    if not all(isinstance(value, Mapping) for value in (
        baseline_document, current_document, source_manifest
    )):
        raise SatelliteCatalogReselectionError(f"source JSON shape is invalid for {queue_id}")
    bbox = queue_job["location"]["aoi_bbox_wgs84"]
    documents = {"baseline": baseline_document, "current": current_document}
    eligible_features: dict[str, list[Mapping[str, Any]]] = {}
    eligibility: dict[str, dict[str, Mapping[str, Any]]] = {}
    for epoch, document in documents.items():
        eligibility[epoch] = {}
        eligible_features[epoch] = []
        for feature in _features(document, f"{queue_id} {epoch} response"):
            coverage = _item_coverage(feature, bbox, epoch)
            eligibility[epoch][feature["id"]] = coverage
            if coverage["all_required_asset_windows_within_grid"]:
                eligible_features[epoch].append(feature)

    normalized = source_manifest.get("normalized_results")
    if not isinstance(normalized, Mapping) or set(normalized) != {"baseline", "current"}:
        raise SatelliteCatalogReselectionError(
            f"source normalized results are invalid for {queue_id}"
        )
    eligible_ids = {
        epoch: tuple(feature["id"] for feature in eligible_features[epoch])
        for epoch in ("baseline", "current")
    }
    records: list[Mapping[str, Any]] = []
    for epoch in ("baseline", "current"):
        raw_records = normalized[epoch]
        if not isinstance(raw_records, list):
            raise SatelliteCatalogReselectionError(
                f"source normalized {epoch} results are invalid for {queue_id}"
            )
        by_id = {record.get("item_id"): record for record in raw_records if isinstance(record, Mapping)}
        if len(by_id) != len(raw_records):
            raise SatelliteCatalogReselectionError(
                f"source normalized {epoch} IDs are invalid for {queue_id}"
            )
        missing = sorted(set(eligible_ids[epoch]) - set(by_id))
        if missing:
            raise SatelliteCatalogReselectionError(
                f"eligible {epoch} features lack normalized records for {queue_id}: {missing}"
            )
        records.extend(by_id[item_id] for item_id in eligible_ids[epoch])

    selection = source_manifest.get("queries", {}).get("selection", {})
    try:
        selected_records = select_scene_pair(
            records,
            baseline_date=selection["baseline_date"],
            current_date=selection["current_date"],
            temporal_window_days=selection["temporal_window_days"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SatelliteCatalogReselectionError(
            f"coverage-filtered selection failed for {queue_id}: {error}"
        ) from error
    selected_items = {
        epoch: select_feature(documents[epoch], selected_records[epoch]["item_id"])
        for epoch in ("baseline", "current")
    }
    ensure_comparable(selected_items["baseline"], selected_items["current"])
    baseline_red = _stac_grid(selected_items["baseline"], "red")
    current_red = _stac_grid(selected_items["current"], "red")
    if baseline_red != current_red:
        raise SatelliteCatalogReselectionError(
            f"selected red grids differ across epochs for {queue_id}"
        )
    original_ids = source_manifest.get("selected_ids")
    if not isinstance(original_ids, Mapping) or set(original_ids) != {"baseline", "current"}:
        raise SatelliteCatalogReselectionError(
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
    if all(
        value["all_required_asset_windows_within_grid"]
        for value in original_coverage.values()
    ):
        raise SatelliteCatalogReselectionError(
            f"source selection is already fully covered for {queue_id}"
        )
    rank = _rank_record(
        selected_records["baseline"],
        selected_records["current"],
        selection["baseline_date"],
        selection["current_date"],
    )
    output_directory = queue_job["catalog_job"]["output_directory"]
    derived = {
        "schema_version": RESELECTION_SCHEMA_VERSION,
        "pipeline": RESELECTION_PIPELINE,
        "queue_id": queue_id,
        "queue_position": queue_job["queue_position"],
        "entity": {
            "id": queue_job["entity"]["id"],
            "name": queue_job["entity"]["name"],
        },
        "output_directory": output_directory,
        "source": {
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
        },
        "selection_policy": {
            "input": "exact_archived_stac_feature_collections",
            "candidate_filter": "all_required_asset_covering_and_interpolation_support_windows_within_grid",
            "rank_after_filter": list(RANKING_POLICY),
            "network_access": False,
        },
        "eligible_ids": {
            epoch: list(eligible_ids[epoch]) for epoch in ("baseline", "current")
        },
        "original_selected_ids": dict(original_ids),
        "selected_ids": {
            epoch: selected_items[epoch]["id"] for epoch in ("baseline", "current")
        },
        "selection_rank": rank,
        "original_selected_features": {
            epoch: {
                "id": original_items[epoch]["id"],
                "stac_feature_sha256": canonical_sha256(original_items[epoch]),
                "coverage": original_coverage[epoch],
            }
            for epoch in ("baseline", "current")
        },
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
    return _PlannedJob(
        queue=queue_job,
        source_task=source_task,
        source_files=files,
        source_manifest=source_manifest,
        baseline_document=baseline_document,
        current_document=current_document,
        original_items=original_items,
        selected_items=selected_items,
        eligible_ids=eligible_ids,
        derived_manifest=derived,
    )


def _unresolved_plan(
    queue_by_id: Mapping[str, Mapping[str, Any]],
    source_document: Mapping[str, Any],
    source: Path,
) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    for queue_id in UNRESOLVED_QUEUE_IDS:
        queue_job = queue_by_id[queue_id]
        source_task = source_document["jobs"][queue_id]
        files = _source_job_files(source, source_task, queue_id)
        documents = {
            "baseline": _decode_json(files["baseline"].read_bytes(), "baseline response"),
            "current": _decode_json(files["current"].read_bytes(), "current response"),
        }
        source_manifest = _decode_json(files["manifest"].read_bytes(), "source manifest")
        bbox = queue_job["location"]["aoi_bbox_wgs84"]
        eligible: dict[str, list[str]] = {}
        selected: dict[str, Any] = {}
        for epoch in ("baseline", "current"):
            eligible[epoch] = [
                feature["id"]
                for feature in _features(documents[epoch], f"{queue_id} {epoch}")
                if _item_coverage(feature, bbox, epoch)[
                    "all_required_asset_windows_within_grid"
                ]
            ]
            item = select_feature(documents[epoch], source_manifest["selected_ids"][epoch])
            selected[epoch] = {
                "id": item["id"],
                "stac_feature_sha256": canonical_sha256(item),
                "coverage": _item_coverage(item, bbox, epoch),
            }
        if eligible["baseline"]:
            raise SatelliteCatalogReselectionError(
                f"unresolved France baseline unexpectedly has a full-cover feature: {queue_id}"
            )
        jobs.append(
            {
                "queue_id": queue_id,
                "queue_position": queue_job["queue_position"],
                "entity": {
                    "id": queue_job["entity"]["id"],
                    "name": queue_job["entity"]["name"],
                },
                "aoi_bbox_wgs84": bbox,
                "source_artifacts": {
                    "baseline_response": {
                        "file": (
                            f"{queue_job['catalog_job']['output_directory']}"
                            "/baseline-response.json"
                        ),
                        **_file_record(files["baseline"]),
                    },
                    "current_response": {
                        "file": (
                            f"{queue_job['catalog_job']['output_directory']}"
                            "/current-response.json"
                        ),
                        **_file_record(files["current"]),
                    },
                    "source_manifest": {
                        "file": (
                            f"{queue_job['catalog_job']['output_directory']}"
                            "/manifest.json"
                        ),
                        **_file_record(files["manifest"]),
                    },
                },
                "source_retrieved_at": source_manifest.get("retrieved_at"),
                "source_queries": source_manifest.get("queries"),
                "original_selected": selected,
                "full_cover_eligible_ids": eligible,
                "outcome": "unresolved_multitile_or_supplemental_scene_required",
                "unavailable_no_scene_claim": False,
                "reselection_emitted": False,
                "change_analysis_executed": False,
            }
        )
    return {
        "schema_version": RESELECTION_SCHEMA_VERSION,
        "pipeline": "satellite_catalog_coverage_unresolved_assessment",
        "meaning": (
            "The archived responses contain no full-cover baseline feature.  This is "
            "not a no-scene claim; a separately archived supplemental same-datatake "
            "tile or a versioned multi-tile processor is required."
        ),
        "jobs": jobs,
        "scope": dict(RESELECTION_SCOPE),
    }


def plan_catalog_reselection(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
) -> ReselectionPlan:
    """Reproduce the exact supported coverage-filtered selection in memory."""

    queue = _absolute_directory(queue_directory, "queue bundle")
    source = _absolute_directory(source_catalog_batch_directory, "source catalog batch")
    if queue.resolve() == source.resolve():
        raise SatelliteCatalogReselectionError("queue and source directories must differ")
    queue_manifest, queue_rows = _read_queue(queue)
    source_document = validate_satellite_batch(queue, source)
    queue_by_id = {row["queue_id"]: row for row in queue_rows}
    if len(queue_by_id) != len(queue_rows):
        raise SatelliteCatalogReselectionError("queue contains duplicate IDs")
    required = set(SUPPORTED_QUEUE_IDS) | set(UNRESOLVED_QUEUE_IDS)
    if not required <= set(queue_by_id):
        raise SatelliteCatalogReselectionError(
            f"queue lacks required edge-audit IDs: {sorted(required - set(queue_by_id))}"
        )
    if not required <= set(source_document["jobs"]):
        raise SatelliteCatalogReselectionError(
            "source catalog batch lacks required edge-audit tasks"
        )
    for queue_id in required:
        if source_document["jobs"][queue_id]["state"] != "completed":
            raise SatelliteCatalogReselectionError(
                f"required source catalog task is not completed: {queue_id}"
            )
    position_order = [queue_by_id[queue_id]["queue_position"] for queue_id in SUPPORTED_QUEUE_IDS]
    if position_order != sorted(position_order):
        raise SatelliteCatalogReselectionError("supported queue IDs are not in queue order")
    jobs = tuple(
        _job_plan(queue_by_id[queue_id], source_document["jobs"][queue_id], source)
        for queue_id in SUPPORTED_QUEUE_IDS
    )
    unresolved = _unresolved_plan(queue_by_id, source_document, source)
    return ReselectionPlan(
        queue=queue,
        source=source,
        queue_manifest=queue_manifest,
        source_document=source_document,
        queue_rows=tuple(queue_rows),
        jobs=jobs,
        unresolved=unresolved,
    )


def _expected_header_assets(plan: ReselectionPlan) -> dict[str, dict[str, str]]:
    assets: dict[str, dict[str, str]] = {}
    for job in plan.jobs:
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
                if prior is not None and prior != identity:
                    # Duplicate entity-bound jobs use the same href and identity.
                    if prior["item_id"] != identity["item_id"] or prior["asset"] != identity["asset"]:
                        raise SatelliteCatalogReselectionError(
                            f"selected asset href is shared by different assets: {href}"
                        )
                else:
                    assets[href] = identity
    return assets


def capture_grid_header_evidence(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    output_file: str | Path,
    *,
    captured_at: str,
) -> dict[str, Any]:
    """Open selected COG metadata only and write a canonical header snapshot.

    This is the only network-capable operation in this module.  It performs no
    raster pixel reads and deliberately makes no HTTP-request-count claim.
    """

    plan = plan_catalog_reselection(queue_directory, source_catalog_batch_directory)
    captured = _timestamp(captured_at, "header captured_at")
    path = Path(os.path.abspath(os.fspath(output_file)))
    if path.exists() or path.is_symlink():
        raise SatelliteCatalogReselectionError("header evidence output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise SatelliteCatalogReselectionError("header evidence parent may not be a symlink")
    _, rasterio, _, _ = _imports()
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
    plan: ReselectionPlan,
    raw: bytes,
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    value = _decode_json(raw, "grid header evidence")
    if not isinstance(value, Mapping) or raw != _canonical_bytes(value):
        raise SatelliteCatalogReselectionError(
            "grid header evidence must be canonical JSON"
        )
    if set(value) != {
        "schema_version",
        "pipeline",
        "captured_at",
        "scope",
        "runtime",
        "asset_open_operations",
        "assets",
    }:
        raise SatelliteCatalogReselectionError("grid header evidence schema is invalid")
    if value.get("schema_version") != HEADER_SCHEMA_VERSION or value.get(
        "pipeline"
    ) != HEADER_PIPELINE:
        raise SatelliteCatalogReselectionError("grid header evidence identity is invalid")
    _timestamp(value.get("captured_at"), "header captured_at")
    if value.get("scope") != HEADER_SCOPE:
        raise SatelliteCatalogReselectionError("grid header evidence scope changed")
    if value.get("runtime") != _runtime_lineage():
        raise SatelliteCatalogReselectionError("grid header runtime changed")
    records = value.get("assets")
    if not isinstance(records, list) or value.get("asset_open_operations") != len(records):
        raise SatelliteCatalogReselectionError("grid header asset count is invalid")
    expected = _expected_header_assets(plan)
    by_href: dict[str, Mapping[str, Any]] = {}
    record_keys = {
        "item_id",
        "asset",
        "epoch",
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
    for record in records:
        if not isinstance(record, Mapping) or set(record) != record_keys:
            raise SatelliteCatalogReselectionError("grid header asset schema is invalid")
        href = record.get("href")
        validate_asset_href(href)
        if href in by_href:
            raise SatelliteCatalogReselectionError("grid header hrefs are not unique")
        by_href[href] = record
    if list(by_href) != sorted(by_href) or set(by_href) != set(expected):
        raise SatelliteCatalogReselectionError(
            "grid header asset inventory is not the exact selected inventory"
        )
    selected_by_id = {
        item["id"]: item
        for job in plan.jobs
        for item in job.selected_items.values()
    }
    for href, identity in expected.items():
        record = by_href[href]
        if any(record[field] != identity[field] for field in ("item_id", "asset", "epoch")):
            # Epoch may differ for a duplicate href only if the same item were used
            # twice, which the temporal ordering contract forbids.
            raise SatelliteCatalogReselectionError(
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
            raise SatelliteCatalogReselectionError(
                f"grid header does not match archived STAC metadata for {href}"
            )
        if record["count"] != 1 or record["driver"] != "GTiff":
            raise SatelliteCatalogReselectionError(
                f"grid header band/driver contract changed for {href}"
            )
        if not isinstance(record["dtype"], str) or not record["dtype"]:
            raise SatelliteCatalogReselectionError(f"grid header dtype is invalid for {href}")
        if record["nodata"] != 0:
            raise SatelliteCatalogReselectionError(f"grid header nodata changed for {href}")
    # Re-run every selected coverage check on the observed headers, not only
    # the archived STAC projection extension.
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
                raise SatelliteCatalogReselectionError(
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
    plan: ReselectionPlan,
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
    unique_aois = {
        tuple(job.queue["location"]["aoi_bbox_wgs84"]) for job in plan.jobs
    }
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
            "supported_queue_ids": list(SUPPORTED_QUEUE_IDS),
            "unresolved_queue_ids": list(UNRESOLVED_QUEUE_IDS),
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
            "asset_open_operations": header_record["asset_open_operations"],
        },
        "unresolved_assessment": {
            "file": UNRESOLVED_FILENAME,
            **_file_record(release / UNRESOLVED_FILENAME),
            "jobs": len(unresolved["jobs"]),
        },
        "jobs": jobs,
        "summary": {
            "jobs_reselected": len(jobs),
            "unique_aois_reselected": len(unique_aois),
            "jobs_unresolved_multitile_needed": len(unresolved["jobs"]),
            "raw_provider_response_files_copied": 2 * len(jobs),
            "source_catalog_manifest_files_copied": len(jobs),
            "change_jobs_executed": 0,
            "atlas_rows_emitted": 0,
        },
    }


def build_catalog_reselection(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    grid_header_evidence_file: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Build and immediately offline-validate one immutable reselection release."""

    plan = plan_catalog_reselection(queue_directory, source_catalog_batch_directory)
    header_path = Path(os.path.abspath(os.fspath(grid_header_evidence_file)))
    if header_path.is_symlink() or not header_path.is_file():
        raise SatelliteCatalogReselectionError("grid header evidence is not a regular file")
    header_raw = header_path.read_bytes()
    header_value, header_by_href = _validate_header_evidence(plan, header_raw)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.exists() or output.is_symlink():
        raise SatelliteCatalogReselectionError("reselection output already exists")
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise SatelliteCatalogReselectionError("reselection output parent is invalid")
    stage = output.with_name(f".{output.name}.staging")
    if stage.exists() or stage.is_symlink():
        raise SatelliteCatalogReselectionError("reselection staging path already exists")
    stage.mkdir()
    try:
        (stage / HEADER_EVIDENCE_FILENAME).write_bytes(header_raw)
        job_manifests: dict[str, Mapping[str, Any]] = {}
        for job in plan.jobs:
            queue_id = job.queue["queue_id"]
            relative = job.queue["catalog_job"]["output_directory"]
            destination = stage.joinpath(*_relative_parts(relative, "catalog output directory"))
            destination.mkdir(parents=True)
            copies = {
                "baseline-response.json": job.source_files["baseline"],
                "current-response.json": job.source_files["current"],
                SOURCE_MANIFEST_FILENAME: job.source_files["manifest"],
            }
            for name, source_path in copies.items():
                shutil.copyfile(source_path, destination / name)
                if (destination / name).read_bytes() != source_path.read_bytes():
                    raise SatelliteCatalogReselectionError(
                        f"exact source copy changed for {queue_id}/{name}"
                    )
            manifest = _job_manifest_with_headers(job, header_by_href)
            (destination / JOB_MANIFEST_FILENAME).write_bytes(_canonical_bytes(manifest))
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
        validate_catalog_reselection(
            queue_directory,
            source_catalog_batch_directory,
            stage,
        )
        for path in stage.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(stage, output)
        parent_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return validate_catalog_reselection(
        queue_directory,
        source_catalog_batch_directory,
        output,
    )


def _closed_tree(release: Path, plan: ReselectionPlan) -> None:
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
            raise SatelliteCatalogReselectionError(
                f"reselection release contains a symlink: {path}"
            )
        if path.is_dir() and path not in expected_directories:
            raise SatelliteCatalogReselectionError(
                f"reselection release contains an unexpected directory: {path}"
            )
        if path.is_file() and path not in expected_files:
            raise SatelliteCatalogReselectionError(
                f"reselection release contains an unexpected file: {path}"
            )
        if not path.is_dir() and not path.is_file():
            raise SatelliteCatalogReselectionError(
                f"reselection release contains a non-regular path: {path}"
            )
    if not all(path.is_file() and not path.is_symlink() for path in expected_files):
        raise SatelliteCatalogReselectionError("reselection release is missing files")


def validate_catalog_reselection(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    release_directory: str | Path,
) -> dict[str, Any]:
    """Rebuild and validate a reselection release with no network access."""

    plan = plan_catalog_reselection(queue_directory, source_catalog_batch_directory)
    release = _absolute_directory(release_directory, "reselection release")
    for input_root in (plan.queue, plan.source):
        resolved_release = release.resolve()
        resolved_input = input_root.resolve()
        if (
            resolved_release == resolved_input
            or resolved_input in resolved_release.parents
            or resolved_release in resolved_input.parents
        ):
            raise SatelliteCatalogReselectionError(
                "reselection release must be separate from its inputs"
            )
    _closed_tree(release, plan)
    header_path = _regular_file(
        release, HEADER_EVIDENCE_FILENAME, "release grid header evidence"
    )
    header_raw = header_path.read_bytes()
    header_value, header_by_href = _validate_header_evidence(plan, header_raw)
    job_manifests: dict[str, Mapping[str, Any]] = {}
    for job in plan.jobs:
        queue_id = job.queue["queue_id"]
        relative = job.queue["catalog_job"]["output_directory"]
        directory = release.joinpath(*_relative_parts(relative, "catalog output directory"))
        exact_pairs = (
            (directory / "baseline-response.json", job.source_files["baseline"]),
            (directory / "current-response.json", job.source_files["current"]),
            (directory / SOURCE_MANIFEST_FILENAME, job.source_files["manifest"]),
        )
        for copied, source in exact_pairs:
            if copied.is_symlink() or not copied.is_file() or copied.read_bytes() != source.read_bytes():
                raise SatelliteCatalogReselectionError(
                    f"exact source bytes changed for {queue_id}/{copied.name}"
                )
        manifest_path = directory / JOB_MANIFEST_FILENAME
        manifest = _canonical_json_file(manifest_path, f"{queue_id} reselection manifest")
        expected = _job_manifest_with_headers(job, header_by_href)
        if manifest != expected:
            raise SatelliteCatalogReselectionError(
                f"reselection manifest does not reproduce for {queue_id}"
            )
        job_manifests[queue_id] = manifest
    unresolved_path = _regular_file(
        release, UNRESOLVED_FILENAME, "unresolved assessment"
    )
    unresolved = _canonical_json_file(unresolved_path, "unresolved assessment")
    if unresolved != plan.unresolved:
        raise SatelliteCatalogReselectionError(
            "unresolved assessment does not reproduce"
        )
    manifest_path = _regular_file(
        release, RESELECTION_MANIFEST_FILENAME, "reselection manifest"
    )
    manifest = _canonical_json_file(manifest_path, "reselection manifest")
    if not isinstance(manifest, Mapping):
        raise SatelliteCatalogReselectionError("reselection manifest must be an object")
    expected_top = _release_top_manifest(
        plan,
        release,
        generated_at=manifest.get("generated_at"),
        header_record=header_value,
        job_manifests=job_manifests,
        unresolved=unresolved,
    )
    if manifest != expected_top:
        raise SatelliteCatalogReselectionError(
            "reselection top-level manifest does not reproduce"
        )
    return dict(manifest)


def release_catalog_tasks(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the strict legacy-shaped task adapter used by the new runner."""

    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping) or set(jobs) != set(SUPPORTED_QUEUE_IDS):
        raise SatelliteCatalogReselectionError(
            "reselection job inventory is not canonical"
        )
    tasks: dict[str, dict[str, Any]] = {}
    for queue_id in SUPPORTED_QUEUE_IDS:
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
