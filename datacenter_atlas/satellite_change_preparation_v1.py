"""Prepare frozen v57 catalog records for single- or multi-tile change analysis.

The preparation is metadata-only. It reads archived STAC JSON, validates exact
lineage, and emits explicit processor bindings without opening imagery assets or
performing network requests.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .satellite_batch import BatchConfig, validate_satellite_batch
from .satellite_change import (
    ALGORITHM_VERSION as SINGLE_TILE_ALGORITHM_VERSION,
    REQUIRED_ASSETS,
    canonical_sha256,
    mgrs_tile,
)
from .satellite_change_mosaic import (
    ALGORITHM_VERSION as MULTI_TILE_ALGORITHM_VERSION,
    ItemBinding,
    SentinelMosaicContractError,
    discover_same_acquisition_bindings,
    epoch_metadata_coverage,
    grid_from_item,
    parse_rfc3339_instant,
    select_bound_items,
)
from .satellite_queue import validate_queue_bundle


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = Path(
    "sources/satellite-change-preparation-2026-07-20-open-seed-v57-active-v1.json"
)
OUTPUT_PATH = Path(
    "satellite_change_preparation/2026-07-20-open-seed-v57-active-v1"
)

DEFINITION_FORMAT = "datacenter-atlas-satellite-change-preparation-definition-v1"
RELEASE_FORMAT = "datacenter-atlas-satellite-change-preparation-v1"
SCHEMA_VERSION = 1
PREPARATION_ID = "2026-07-20-open-seed-v57-active-change-preparation-v1"
MAX_COMPATIBLE_COMPANIONS = 8
STATES = (
    "terminal_no_scene",
    "single_tile_ready",
    "multi_tile_ready",
    "multi_tile_blocked",
)
STATE_FILES = {
    "terminal_no_scene": "terminal-no-scene.jsonl",
    "single_tile_ready": "single-tile-ready.jsonl",
    "multi_tile_ready": "multi-tile-ready.jsonl",
    "multi_tile_blocked": "multi-tile-blocked.jsonl",
}
RELEASE_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "aoi-relationships.jsonl",
        "manifest.json",
        "manifest.sha256",
        "multi-tile-blocked.jsonl",
        "multi-tile-ready.jsonl",
        "single-tile-ready.jsonl",
        "source-inventory.json",
        "summary.json",
        "terminal-no-scene.jsonl",
    }
)

CLAIM_CONSTRAINTS = {
    "atlas_claim_created": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_status_claim_created": False,
    "construction_truth_claim_created": False,
    "data_centre_identity_claim_created": False,
    "data_centre_type_claim_created": False,
    "energy_claim_created": False,
    "imagery_downloaded": False,
    "imagery_opened": False,
    "lifecycle_claim_created": False,
    "network_requests_performed": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "raster_analysis_executed": False,
    "semianalysis_parity_claim_created": False,
    "site_identity_inference": False,
    "workload_claim_created": False,
}

RUNTIME = {
    "gdal": "3.12.1",
    "numpy": "2.5.1",
    "pillow": "12.3.0",
    "proj": "9.7.1",
    "python": "3.12.13",
    "rasterio": "1.5.0",
}

CATALOG_CONFIG = BatchConfig(
    priority_tiers=["active_construction"],
    user_agent=(
        "DataCenterAtlas/0.1 (open research satellite review queue; "
        "+https://github.com/kiankyars/semiconductors)"
    ),
    minimum_interval_seconds=1,
    timeout_seconds=60,
    catalog_retries=0,
    max_job_attempts=3,
    max_response_bytes=16_777_216,
)


class SatelliteChangePreparationV1Error(ValueError):
    """Raised when preparation lineage or metadata fails closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_jsonl(values: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        for value in values
    )


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SatelliteChangePreparationV1Error(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise SatelliteChangePreparationV1Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteChangePreparationV1Error(f"{label} is not valid JSON") from error


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangePreparationV1Error(f"{label} is not a regular file: {path}")
    return path.read_bytes()


def _pin(path: Path) -> dict[str, Any]:
    raw = _read_regular(path, "pinned file")
    return {
        "bytes": len(raw),
        "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
        "sha256": _sha(raw),
    }


def _path_pin(path: Path) -> dict[str, Any]:
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise SatelliteChangePreparationV1Error(
            f"pinned file is outside the package root: {path}"
        ) from error
    return {"path": relative, **_pin(path)}


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangePreparationV1Error(
            f"closed tree root is not a regular directory: {root}"
        )
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SatelliteChangePreparationV1Error(
                f"closed tree contains symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            directories += 1
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            files += 1
            raw = path.read_bytes()
            file_bytes += len(raw)
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha(raw)}\n"
                ).encode()
            )
        else:
            raise SatelliteChangePreparationV1Error(
                f"closed tree contains unsupported entry: {relative}"
            )
    return {
        "directories": directories,
        "file_bytes": file_bytes,
        "files": files,
        "inventory_sha256": digest.hexdigest(),
    }


def _root_path(relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise SatelliteChangePreparationV1Error(f"{label} path is invalid")
    parts = Path(relative).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise SatelliteChangePreparationV1Error(f"{label} path is not canonical")
    path = ROOT.joinpath(*parts)
    cursor = ROOT
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise SatelliteChangePreparationV1Error(
                f"{label} path traverses a symlink: {relative}"
            )
    return path


def _validate_file_pin(value: Any, label: str) -> Path:
    if not isinstance(value, Mapping) or set(value) != {
        "bytes",
        "mode",
        "path",
        "sha256",
    }:
        raise SatelliteChangePreparationV1Error(f"{label} pin schema is invalid")
    path = _root_path(value["path"], label)
    if _path_pin(path) != dict(value):
        raise SatelliteChangePreparationV1Error(f"{label} pin mismatch")
    return path


def _validate_tree_source(value: Any, label: str) -> Path:
    if not isinstance(value, Mapping) or set(value) != {"closed_tree", "directory"}:
        raise SatelliteChangePreparationV1Error(f"{label} source schema is invalid")
    directory = _root_path(value["directory"], label)
    if _tree_inventory(directory) != value["closed_tree"]:
        raise SatelliteChangePreparationV1Error(f"{label} closed-tree pin mismatch")
    return directory


def _rfc3339(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SatelliteChangePreparationV1Error(f"{label} must be RFC 3339 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteChangePreparationV1Error(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteChangePreparationV1Error(f"{label} lacks a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes]:
    path = Path(definition_path)
    raw = _read_regular(path, "preparation definition")
    value = _strict_json(raw, "preparation definition")
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise SatelliteChangePreparationV1Error(
            "preparation definition is not canonical pretty JSON"
        )
    expected_keys = {
        "builder",
        "claim_constraints",
        "expected_partition",
        "format",
        "generated_at",
        "preparation_id",
        "processors",
        "runtime",
        "schema_version",
        "sources",
    }
    if set(value) != expected_keys:
        raise SatelliteChangePreparationV1Error("preparation definition schema is invalid")
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["format"] != DEFINITION_FORMAT
        or value["preparation_id"] != PREPARATION_ID
        or _rfc3339(value["generated_at"], "definition generated_at")
        != value["generated_at"]
        or value["claim_constraints"] != CLAIM_CONSTRAINTS
        or value["runtime"] != RUNTIME
    ):
        raise SatelliteChangePreparationV1Error("preparation definition identity drift")
    if not isinstance(value["sources"], Mapping) or set(value["sources"]) != {
        "catalog_batch",
        "catalog_lock",
        "queue_bundle",
    }:
        raise SatelliteChangePreparationV1Error("definition source inventory is invalid")
    if not isinstance(value["processors"], Mapping) or set(value["processors"]) != {
        "multi_tile",
        "single_tile",
    }:
        raise SatelliteChangePreparationV1Error("definition processor inventory is invalid")
    if not isinstance(value["builder"], Mapping) or set(value["builder"]) != {
        "cli",
        "module",
        "outer_shim",
    }:
        raise SatelliteChangePreparationV1Error("definition builder inventory is invalid")
    expected_partition_keys = {
        "active_jobs",
        "distinct_aois",
        "jobs_in_shared_aois",
        "multi_tile_blocked",
        "multi_tile_ready",
        "partition_inventory_sha256",
        "shared_aoi_groups",
        "single_tile_ready",
        "terminal_no_scene",
    }
    expected = value["expected_partition"]
    if not isinstance(expected, Mapping) or set(expected) != expected_partition_keys:
        raise SatelliteChangePreparationV1Error("expected partition schema is invalid")
    for key in expected_partition_keys - {"partition_inventory_sha256"}:
        count = expected[key]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SatelliteChangePreparationV1Error(
                f"expected partition count is invalid: {key}"
            )
    digest = expected["partition_inventory_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SatelliteChangePreparationV1Error(
            "expected partition inventory hash is invalid"
        )
    for label, pin in value["builder"].items():
        _validate_file_pin(pin, f"builder {label}")
    for processor_name, processor in value["processors"].items():
        if not isinstance(processor, Mapping) or set(processor) != {
            "algorithm_version",
            "cli",
            "minimum_component_area_m2",
            "module",
        }:
            raise SatelliteChangePreparationV1Error(
                f"{processor_name} processor schema is invalid"
            )
        if processor["minimum_component_area_m2"] != 5_000:
            raise SatelliteChangePreparationV1Error(
                f"{processor_name} minimum-area pin drift"
            )
        _validate_file_pin(processor["module"], f"{processor_name} module")
        _validate_file_pin(processor["cli"], f"{processor_name} CLI")
    if (
        value["processors"]["single_tile"]["algorithm_version"]
        != SINGLE_TILE_ALGORITHM_VERSION
        or value["processors"]["multi_tile"]["algorithm_version"]
        != MULTI_TILE_ALGORITHM_VERSION
    ):
        raise SatelliteChangePreparationV1Error("processor algorithm pin drift")
    return value, raw


def _validated_sources(
    definition: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    queue_directory = _validate_tree_source(
        definition["sources"]["queue_bundle"], "queue bundle"
    )
    catalog_directory = _validate_tree_source(
        definition["sources"]["catalog_batch"], "catalog batch"
    )
    _validate_file_pin(definition["sources"]["catalog_lock"], "catalog lock")
    queue_manifest = validate_queue_bundle(queue_directory)
    batch_manifest = validate_satellite_batch(
        queue_directory,
        catalog_directory,
        config=CATALOG_CONFIG,
    )
    if queue_manifest["counts"]["queued_entities_by_priority_tier"].get(
        "active_construction"
    ) != 87:
        raise SatelliteChangePreparationV1Error("queue active-job count drift")
    if batch_manifest["state"] != "completed" or batch_manifest["summary"] != {
        "jobs_completed": 85,
        "jobs_failed": 0,
        "jobs_pending": 0,
        "jobs_selected": 87,
        "jobs_unavailable_no_scene": 2,
    }:
        raise SatelliteChangePreparationV1Error("catalog terminal partition drift")
    return queue_directory, catalog_directory, queue_manifest, batch_manifest


def _queue_rows(queue_directory: Path) -> list[dict[str, Any]]:
    path = queue_directory / "satellite-review-queue.jsonl"
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_bytes().splitlines(), start=1):
        value = _strict_json(line, f"queue row {index}")
        if not isinstance(value, dict) or value.get("queue_position") != index:
            raise SatelliteChangePreparationV1Error("queue row order drift")
        rows.append(value)
    return rows


def _response_document(
    catalog_directory: Path,
    job: Mapping[str, Any],
    epoch: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    filename = f"{epoch}-response.json"
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, Mapping) or filename not in artifacts:
        raise SatelliteChangePreparationV1Error(
            f"completed catalog job lacks {filename}"
        )
    checkpoint = artifacts[filename]
    path = catalog_directory / str(job["output_directory"]) / filename
    raw = _read_regular(path, f"{epoch} archived STAC response")
    if checkpoint != {"bytes": len(raw), "sha256": _sha(raw)}:
        raise SatelliteChangePreparationV1Error(
            f"{epoch} archived STAC response pin drift"
        )
    document = _strict_json(raw, f"{epoch} archived STAC response")
    if not isinstance(document, dict):
        raise SatelliteChangePreparationV1Error(
            f"{epoch} archived STAC response is not an object"
        )
    return document, {
        "bytes": len(raw),
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha(raw),
    }


def _features(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = document.get("features")
    if document.get("type") != "FeatureCollection" or not isinstance(values, list):
        raise SatelliteChangePreparationV1Error(
            "archived STAC response is not a FeatureCollection"
        )
    if any(not isinstance(value, Mapping) for value in values):
        raise SatelliteChangePreparationV1Error("archived STAC feature is not an object")
    return values


def _item(document: Mapping[str, Any], item_id: str) -> Mapping[str, Any]:
    matches = [value for value in _features(document) if value.get("id") == item_id]
    if len(matches) != 1:
        raise SatelliteChangePreparationV1Error(
            f"selected STAC item is not unique: {item_id}"
        )
    return matches[0]


def _asset_bindings(item: Mapping[str, Any]) -> dict[str, Any]:
    assets = item.get("assets")
    if not isinstance(assets, Mapping):
        raise SatelliteChangePreparationV1Error("selected STAC item lacks assets")
    result: dict[str, Any] = {}
    for asset_name in REQUIRED_ASSETS:
        value = assets.get(asset_name)
        if not isinstance(value, Mapping):
            raise SatelliteChangePreparationV1Error(
                f"selected STAC item lacks asset {asset_name}"
            )
        href = value.get("href")
        if not isinstance(href, str) or not href:
            raise SatelliteChangePreparationV1Error(
                f"selected STAC item asset {asset_name} lacks href"
            )
        grid = grid_from_item(item, asset_name)
        result[asset_name] = {
            "href": href,
            "href_sha256": _sha(href.encode("utf-8")),
            "proj_epsg": grid.epsg,
            "proj_shape": [grid.height, grid.width],
            "proj_transform": list(grid.transform_tuple),
        }
    return result


def _item_binding(
    item: Mapping[str, Any], binding: ItemBinding, role: str
) -> dict[str, Any]:
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise SatelliteChangePreparationV1Error("selected STAC item lacks properties")
    if canonical_sha256(item) != binding.stac_item_sha256:
        raise SatelliteChangePreparationV1Error("selected STAC item hash drift")
    tile = mgrs_tile(item)
    if not tile:
        raise SatelliteChangePreparationV1Error("selected STAC item lacks MGRS tile")
    return {
        "acquisition": {
            "datastrip_id": properties.get("s2:datastrip_id"),
            "datatake_id": properties.get("s2:datatake_id"),
        },
        "assets": _asset_bindings(item),
        "datetime_utc": parse_rfc3339_instant(
            properties.get("datetime"), f"selected item {binding.item_id} datetime"
        )
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "id": binding.item_id,
        "mgrs_tile": tile,
        "role": role,
        "stac_item_sha256": binding.stac_item_sha256,
    }


def _candidate_summary(
    document: Mapping[str, Any], binding: ItemBinding
) -> dict[str, Any]:
    item = _item(document, binding.item_id)
    return {
        "id": binding.item_id,
        "mgrs_tile": mgrs_tile(item),
        "stac_item_sha256": binding.stac_item_sha256,
    }


def _rejection_code(error: Exception) -> str:
    text = str(error)
    if "different CRS" in text:
        return "incompatible_crs"
    if "duplicate MGRS tile" in text:
        return "duplicate_mgrs_tile"
    if "pixel lattice" in text or "grid" in text:
        return "incompatible_grid"
    return "mosaic_contract_rejected"


def _assess_epoch(
    *,
    document: Mapping[str, Any],
    epoch: str,
    primary_id: str,
    response_pin: Mapping[str, Any],
    bbox: Sequence[float],
    transform_bounds: Callable[..., Sequence[float]],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    primary_item = _item(document, primary_id)
    primary = ItemBinding(primary_id, canonical_sha256(primary_item))
    try:
        selected_primary, primary_items = select_bound_items(document, primary, ())
        primary_coverage = epoch_metadata_coverage(
            selected_primary, primary_items, bbox, transform_bounds
        )
        discovered = (
            (primary,)
            if primary_coverage["complete"]
            else discover_same_acquisition_bindings(document, primary)
        )
    except (SentinelMosaicContractError, KeyError, TypeError) as error:
        raise SatelliteChangePreparationV1Error(
            f"{epoch} primary archived STAC contract failed"
        ) from error
    candidates = [binding for binding in discovered if binding.item_id != primary.item_id]
    compatible: list[ItemBinding] = []
    rejected: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            candidate_primary, candidate_items = select_bound_items(
                document, primary, (candidate,)
            )
            epoch_metadata_coverage(
                candidate_primary, candidate_items, bbox, transform_bounds
            )
            compatible.append(candidate)
        except (SentinelMosaicContractError, KeyError, TypeError) as error:
            rejected.append(
                {
                    **_candidate_summary(document, candidate),
                    "reason": str(error),
                    "reason_code": _rejection_code(error),
                }
            )

    solutions: list[tuple[tuple[ItemBinding, ...], dict[str, Any]]] = []
    too_many = len(compatible) > MAX_COMPATIBLE_COMPANIONS
    if not primary_coverage["complete"] and not too_many:
        for size in range(1, len(compatible) + 1):
            for subset in combinations(compatible, size):
                try:
                    subset_primary, subset_items = select_bound_items(
                        document, primary, subset
                    )
                    coverage = epoch_metadata_coverage(
                        subset_primary, subset_items, bbox, transform_bounds
                    )
                except (SentinelMosaicContractError, KeyError, TypeError):
                    continue
                if coverage["complete"]:
                    solutions.append((subset, coverage))
            if solutions:
                break

    if primary_coverage["complete"]:
        classification = "single_tile_complete"
        chosen: tuple[ItemBinding, ...] = ()
        selected_coverage: dict[str, Any] | None = primary_coverage
        blocker: dict[str, Any] | None = None
    elif len(solutions) == 1:
        classification = "multi_tile_complete"
        chosen, selected_coverage = solutions[0]
        blocker = None
    elif len(solutions) > 1:
        classification = "multi_tile_ambiguous"
        chosen = ()
        selected_coverage = None
        blocker = {
            "candidate_solutions": [
                [binding.as_dict() for binding in subset]
                for subset, _coverage in solutions
            ],
            "reason": "multiple_minimal_archived_companion_sets_cover_aoi",
        }
    else:
        classification = "multi_tile_missing"
        chosen = ()
        selected_coverage = None
        blocker = {
            "compatible_companion_limit_exceeded": too_many,
            "reason": (
                "compatible_companion_set_is_ambiguous"
                if too_many
                else "no_archived_compatible_companion_set_covers_aoi"
            ),
        }

    selected_primary, selected_items = select_bound_items(document, primary, chosen)
    by_id = {str(item["id"]): item for item in selected_items}
    selected_bindings = [_item_binding(selected_primary, primary, "primary")]
    selected_bindings.extend(
        _item_binding(by_id[binding.item_id], binding, "companion")
        for binding in chosen
    )
    record = {
        "archived_same_acquisition_candidates": [
            _candidate_summary(document, binding) for binding in candidates
        ],
        "archived_stac_response": dict(response_pin),
        "blocker": blocker,
        "classification": classification,
        "compatible_companion_candidates": [
            _candidate_summary(document, binding) for binding in compatible
        ],
        "epoch": epoch,
        "network_requests": 0,
        "primary": primary.as_dict(),
        "primary_only_coverage": primary_coverage,
        "rejected_companion_candidates": rejected,
        "selected_companions": [binding.as_dict() for binding in chosen],
        "selected_coverage": selected_coverage,
        "selected_item_asset_bindings": selected_bindings,
        "tile_coverage": {
            "archived_candidate_tiles": sorted(
                {
                    summary["mgrs_tile"]
                    for summary in (
                        _candidate_summary(document, binding) for binding in candidates
                    )
                    if summary["mgrs_tile"] is not None
                }
            ),
            "coverage_complete": bool(
                selected_coverage and selected_coverage.get("complete")
            ),
            "primary_tile": mgrs_tile(primary_item),
            "selected_tiles": [value["mgrs_tile"] for value in selected_bindings],
        },
    }
    return record, primary_item


def _cross_epoch_contract(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    baseline_time = parse_rfc3339_instant(
        baseline["properties"].get("datetime"), "baseline primary datetime"
    )
    current_time = parse_rfc3339_instant(
        current["properties"].get("datetime"), "current primary datetime"
    )
    if baseline_time >= current_time:
        raise SatelliteChangePreparationV1Error("baseline must precede current epoch")
    grids_equal = all(
        grid_from_item(baseline, asset) == grid_from_item(current, asset)
        for asset in ("red", "swir16", "scl")
    )
    return {
        "baseline_precedes_current": True,
        "primary_grids_equal_for_red_swir16_scl": grids_equal,
        "primary_mgrs_tile_equal": mgrs_tile(baseline) == mgrs_tile(current),
    }


def _number_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteChangePreparationV1Error("bbox coordinate is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise SatelliteChangePreparationV1Error("bbox coordinate is not finite")
    return format(number, ".15g")


def _single_arguments(
    row: Mapping[str, Any], epochs: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    return [
        "--baseline-stac",
        epochs["baseline"]["archived_stac_response"]["path"],
        "--baseline-id",
        epochs["baseline"]["primary"]["id"],
        "--current-stac",
        epochs["current"]["archived_stac_response"]["path"],
        "--current-id",
        epochs["current"]["primary"]["id"],
        "--bbox",
        ",".join(_number_text(value) for value in row["location"]["aoi_bbox_wgs84"]),
        "--entity-id",
        row["entity"]["id"],
        "--entity-name",
        row["entity"]["name"],
        "--output-dir",
        "{job_output_dir}",
        "--minimum-component-area-m2",
        "5000",
    ]


def _multi_arguments(
    row: Mapping[str, Any], epochs: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    arguments: list[str] = []
    for epoch in ("baseline", "current"):
        value = epochs[epoch]
        primary = value["primary"]
        arguments.extend(
            [
                f"--{epoch}-stac",
                value["archived_stac_response"]["path"],
                f"--{epoch}-stac-sha256",
                value["archived_stac_response"]["sha256"],
                f"--{epoch}-primary",
                f"{primary['id']}={primary['stac_item_sha256']}",
            ]
        )
        for companion in value["selected_companions"]:
            arguments.extend(
                [
                    f"--{epoch}-companion",
                    f"{companion['id']}={companion['stac_item_sha256']}",
                ]
            )
    arguments.extend(
        [
            "--bbox",
            ",".join(
                _number_text(value) for value in row["location"]["aoi_bbox_wgs84"]
            ),
            "--entity-id",
            row["entity"]["id"],
            "--entity-name",
            row["entity"]["name"],
            "--output-dir",
            "{job_output_dir}",
            "--minimum-component-area-m2",
            "5000",
        ]
    )
    return arguments


def _aoi_relationships(
    active_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[float, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in active_rows:
        grouped[tuple(row["location"]["aoi_bbox_wgs84"])].append(row)
    by_queue: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    for bbox, members in sorted(grouped.items(), key=lambda value: value[1][0]["queue_position"]):
        ordered = sorted(members, key=lambda value: value["queue_position"])
        relationship_id = "aoi-" + _sha(
            json.dumps(bbox, separators=(",", ":")).encode("utf-8")
        )[:24]
        member_rows = [
            {
                "entity_id": member["entity"]["id"],
                "queue_id": member["queue_id"],
                "queue_position": member["queue_position"],
            }
            for member in ordered
        ]
        relationship = {
            "aoi_bbox_wgs84": list(bbox),
            "aoi_relationship_id": relationship_id,
            "job_count": len(ordered),
            "jobs": member_rows,
            "processing_deduplicated": False,
            "relationship_only": True,
            "shared_aoi": len(ordered) > 1,
        }
        relationships.append(relationship)
        for member in ordered:
            by_queue[member["queue_id"]] = {
                "aoi_relationship_id": relationship_id,
                "job_count": len(ordered),
                "member_queue_ids": [value["queue_id"] for value in ordered],
                "processing_deduplicated": False,
                "shared_aoi": len(ordered) > 1,
            }
    return by_queue, relationships


def _common_row(
    queue_row: Mapping[str, Any], relationship: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "aoi_bbox_wgs84": queue_row["location"]["aoi_bbox_wgs84"],
        "aoi_relationship": dict(relationship),
        "claim_constraints": CLAIM_CONSTRAINTS,
        "entity": queue_row["entity"],
        "network_requests": 0,
        "preparation_only": True,
        "queue_id": queue_row["queue_id"],
        "queue_position": queue_row["queue_position"],
        "raster_analysis_executed": False,
        "schema_version": SCHEMA_VERSION,
    }


def _derive_rows(
    definition: Mapping[str, Any],
    queue_directory: Path,
    catalog_directory: Path,
    batch_manifest: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    try:
        from rasterio.warp import transform_bounds
    except ImportError as error:  # pragma: no cover - environment guard
        raise SatelliteChangePreparationV1Error(
            "metadata preparation requires the pinned rasterio runtime"
        ) from error
    queue_rows = _queue_rows(queue_directory)
    active_rows = [
        row for row in queue_rows if row["priority"]["tier"] == "active_construction"
    ]
    jobs = batch_manifest["jobs"]
    if [row["queue_id"] for row in active_rows] != [
        queue_id
        for queue_id, job in sorted(
            jobs.items(), key=lambda value: value[1]["queue_position"]
        )
    ]:
        raise SatelliteChangePreparationV1Error("catalog selection order drift")
    relationships_by_queue, relationships = _aoi_relationships(active_rows)
    rows: dict[str, list[dict[str, Any]]] = {state: [] for state in STATES}
    for queue_row in active_rows:
        queue_id = queue_row["queue_id"]
        job = jobs[queue_id]
        common = _common_row(queue_row, relationships_by_queue[queue_id])
        if job["state"] == "unavailable_no_scene":
            rows["terminal_no_scene"].append(
                {
                    **common,
                    "catalog_state": "unavailable_no_scene",
                    "execution": None,
                    "state": "terminal_no_scene",
                    "unavailability": job["unavailability"],
                }
            )
            continue
        if job["state"] != "completed":
            raise SatelliteChangePreparationV1Error(
                f"catalog job is not terminal: {queue_id}"
            )
        epochs: dict[str, dict[str, Any]] = {}
        primaries: dict[str, Mapping[str, Any]] = {}
        for epoch in ("baseline", "current"):
            document, response_pin = _response_document(
                catalog_directory, job, epoch
            )
            epoch_record, primary_item = _assess_epoch(
                document=document,
                epoch=epoch,
                primary_id=job["selected_ids"][epoch],
                response_pin=response_pin,
                bbox=queue_row["location"]["aoi_bbox_wgs84"],
                transform_bounds=transform_bounds,
            )
            epochs[epoch] = epoch_record
            primaries[epoch] = primary_item
        cross_epoch = _cross_epoch_contract(
            primaries["baseline"], primaries["current"]
        )
        classifications = {
            epochs["baseline"]["classification"],
            epochs["current"]["classification"],
        }
        if classifications == {"single_tile_complete"}:
            state = "single_tile_ready"
            processor = definition["processors"]["single_tile"]
            execution = {
                "arguments": _single_arguments(queue_row, epochs),
                "cli": processor["cli"]["path"],
                "runtime": definition["runtime"],
            }
        elif classifications.issubset(
            {"single_tile_complete", "multi_tile_complete"}
        ) and (
            cross_epoch["primary_mgrs_tile_equal"]
            and cross_epoch["primary_grids_equal_for_red_swir16_scl"]
        ):
            state = "multi_tile_ready"
            processor = definition["processors"]["multi_tile"]
            execution = {
                "arguments": _multi_arguments(queue_row, epochs),
                "cli": processor["cli"]["path"],
                "runtime": definition["runtime"],
            }
        else:
            state = "multi_tile_blocked"
            processor = definition["processors"]["multi_tile"]
            execution = None
        rows[state].append(
            {
                **common,
                "catalog_artifacts": {
                    filename: {
                        **checkpoint,
                        "path": (
                            catalog_directory
                            / str(job["output_directory"])
                            / filename
                        )
                        .relative_to(ROOT)
                        .as_posix(),
                    }
                    for filename, checkpoint in job["artifacts"].items()
                },
                "cross_epoch_contract": cross_epoch,
                "epochs": epochs,
                "execution": execution,
                "processor": processor,
                "state": state,
            }
        )
    partition_inventory = [
        [row["queue_position"], row["queue_id"], state]
        for state in STATES
        for row in rows[state]
    ]
    partition_inventory.sort()
    shared = [value for value in relationships if value["shared_aoi"]]
    summary = {
        "active_jobs": len(active_rows),
        "distinct_aois": len(relationships),
        "jobs_in_shared_aois": sum(value["job_count"] for value in shared),
        "multi_tile_blocked": len(rows["multi_tile_blocked"]),
        "multi_tile_ready": len(rows["multi_tile_ready"]),
        "partition_inventory_sha256": _sha(_canonical_json(partition_inventory)),
        "shared_aoi_groups": len(shared),
        "single_tile_ready": len(rows["single_tile_ready"]),
        "terminal_no_scene": len(rows["terminal_no_scene"]),
    }
    expected = dict(definition["expected_partition"])
    if summary != expected:
        raise SatelliteChangePreparationV1Error(
            "derived partition differs from definition: "
            f"expected={expected!r}; actual={summary!r}"
        )
    return rows, relationships, summary


def _source_inventory(
    definition: Mapping[str, Any], queue_directory: Path, catalog_directory: Path
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for source_group, directory in (
        ("queue_bundle", queue_directory),
        ("catalog_batch", catalog_directory),
    ):
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            pin = _path_pin(path)
            pin["source_group"] = source_group
            files[pin["path"]] = pin
    lock = _validate_file_pin(definition["sources"]["catalog_lock"], "catalog lock")
    lock_pin = _path_pin(lock)
    lock_pin["source_group"] = "catalog_lock"
    files[lock_pin["path"]] = lock_pin
    for group_name in ("builder",):
        for label, pin in definition[group_name].items():
            row = dict(pin)
            row["source_group"] = f"{group_name}:{label}"
            files[row["path"]] = row
    for processor_name, processor in definition["processors"].items():
        for label in ("module", "cli"):
            pin = dict(processor[label])
            existing = files.get(pin["path"])
            if existing is not None:
                continue
            pin["source_group"] = f"processor:{processor_name}:{label}"
            files[pin["path"]] = pin
    rows = [files[path] for path in sorted(files)]
    return {
        "files": rows,
        "schema_version": SCHEMA_VERSION,
        "source_file_count": len(rows),
    }


def _readme(summary: Mapping[str, Any]) -> bytes:
    text = f"""# V57 catalog-to-change preparation

This immutable, metadata-only bundle partitions all {summary['active_jobs']} active-construction queue jobs from the frozen v57 Earth Search catalog batch. It contains {summary['single_tile_ready']} single-tile-ready jobs, {summary['multi_tile_ready']} multi-tile-ready jobs, {summary['multi_tile_blocked']} multi-tile-blocked jobs, and {summary['terminal_no_scene']} terminal no-scene jobs.

Preparation reads only archived STAC JSON. It performs no network request, imagery download, imagery open, raster analysis, change execution, entity merge, site deduplication, or atlas mutation. Shared AOIs are explicit relationships only; every entity job remains present. Ready rows are processor inputs for later bounded execution, not identity, lifecycle, type, capacity, power, energy, PUE, workload, construction-truth, or site-count claims.
"""
    return text.encode("utf-8")


def _payloads(
    definition_path: str | Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    definition, definition_raw = _validate_definition(definition_path)
    queue_directory, catalog_directory, _queue_manifest, batch_manifest = (
        _validated_sources(definition)
    )
    rows, relationships, summary = _derive_rows(
        definition, queue_directory, catalog_directory, batch_manifest
    )
    source_inventory = _source_inventory(
        definition, queue_directory, catalog_directory
    )
    payloads: dict[str, bytes] = {
        "ATTRIBUTION.txt": (
            "Catalog metadata: Element 84 Earth Search v1. Imagery references: "
            "Copernicus Sentinel-2 Level-2A. No imagery asset was fetched.\n"
        ).encode("utf-8"),
        "README.md": _readme(summary),
        "aoi-relationships.jsonl": _canonical_jsonl(relationships),
        "source-inventory.json": _canonical_json(source_inventory),
        "summary.json": _canonical_json(
            {
                "claim_constraints": CLAIM_CONSTRAINTS,
                "preparation_id": PREPARATION_ID,
                "preparation_only": True,
                "runtime": definition["runtime"],
                "schema_version": SCHEMA_VERSION,
                **summary,
            }
        ),
    }
    for state, filename in STATE_FILES.items():
        ordered = sorted(rows[state], key=lambda row: row["queue_position"])
        payloads[filename] = _canonical_jsonl(ordered)
    artifacts = {
        filename: {"bytes": len(raw), "sha256": _sha(raw)}
        for filename, raw in sorted(payloads.items())
    }
    manifest = {
        "artifacts": artifacts,
        "builder": definition["builder"],
        "claim_constraints": CLAIM_CONSTRAINTS,
        "definition": {
            "bytes": len(definition_raw),
            "path": Path(definition_path).resolve().relative_to(ROOT).as_posix(),
            "sha256": _sha(definition_raw),
        },
        "format": RELEASE_FORMAT,
        "generated_at": definition["generated_at"],
        "preparation_id": PREPARATION_ID,
        "processors": definition["processors"],
        "runtime": definition["runtime"],
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "aoi_deduplication_applied": False,
            "entity_jobs_retained": 87,
            "imagery_downloads": 0,
            "imagery_opens": 0,
            "network_requests": 0,
            "preparation_only": True,
            "raster_analyses": 0,
        },
        "sources": definition["sources"],
        "summary": summary,
    }
    manifest_raw = _canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return payloads, manifest


def validate_satellite_change_preparation_v1(
    output_directory: str | Path,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    output = Path(output_directory)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangePreparationV1Error(
            f"preparation output is not a regular directory: {output}"
        )
    if {path.name for path in output.iterdir()} != RELEASE_FILES:
        raise SatelliteChangePreparationV1Error("preparation output inventory drift")
    expected, manifest = _payloads(definition_path)
    for filename in sorted(RELEASE_FILES):
        path = output / filename
        raw = _read_regular(path, f"preparation artifact {filename}")
        if raw != expected[filename]:
            raise SatelliteChangePreparationV1Error(
                f"preparation artifact differs: {filename}"
            )
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise SatelliteChangePreparationV1Error("preparation directory is not frozen")
    for path in output.iterdir():
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise SatelliteChangePreparationV1Error(
                f"preparation artifact is not frozen: {path.name}"
            )
    return manifest


def _thaw_and_remove(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    for child in path.iterdir():
        if not child.is_symlink():
            child.chmod(0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


def write_satellite_change_preparation_v1(
    output_directory: str | Path = ROOT / OUTPUT_PATH,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise SatelliteChangePreparationV1Error(
            f"refusing to replace preparation output: {output}"
        )
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteChangePreparationV1Error(
            f"preparation output parent is not a regular directory: {parent}"
        )
    payloads, _manifest = _payloads(definition_path)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    try:
        for filename, raw in sorted(payloads.items()):
            path = stage / filename
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(0o444)
        stage.chmod(0o555)
        validate_satellite_change_preparation_v1(
            stage, definition_path=definition_path
        )
        if output.exists() or output.is_symlink():
            raise SatelliteChangePreparationV1Error(
                f"preparation output appeared during publication: {output}"
            )
        os.rename(stage, output)
        descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        _thaw_and_remove(stage)
        raise
    return validate_satellite_change_preparation_v1(
        output, definition_path=definition_path
    )


__all__ = [
    "CLAIM_CONSTRAINTS",
    "DEFINITION_FORMAT",
    "DEFINITION_PATH",
    "OUTPUT_PATH",
    "PREPARATION_ID",
    "RELEASE_FILES",
    "RELEASE_FORMAT",
    "RUNTIME",
    "SCHEMA_VERSION",
    "SatelliteChangePreparationV1Error",
    "validate_satellite_change_preparation_v1",
    "write_satellite_change_preparation_v1",
]
