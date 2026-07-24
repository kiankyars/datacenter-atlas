"""Build and validate the seven-row Sentinel mosaic-v3 preparation release.

This module is deliberately metadata-only.  It reads already archived STAC
responses, derives explicit same-acquisition item bindings under the accepted
mosaic-v3 contract, and publishes execution specifications without opening or
downloading imagery and without executing the change processor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import ctypes
from datetime import timezone
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any

from .satellite_change import canonical_sha256, mgrs_tile
from .satellite_change_mosaic import (
    ALGORITHM_VERSION,
    REQUIRED_ASSETS,
    SPECTRAL_CORE_ALGORITHM_VERSION,
    ItemBinding,
    SentinelMosaicContractError,
    grid_from_item,
    parse_rfc3339_instant,
    preflight_archived_epoch,
    select_bound_items,
)


DEFINITION_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-definition-v2"
RELEASE_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-v2"
SCHEMA_VERSION = 2
CONTENT_SCHEMA_VERSION = 1
READY_STATE = "metadata_ready_for_explicit_mosaic_attempt"
BLOCKED_STATE = "blocked_archived_current_companion_missing"
BLOCKER = "archived_current_response_missing_same_acquisition_companion_for_complete_coverage"
BLOCKED_QUEUE_ID = "satq-3a5dbdef8b0fd5a8f4e53bf1"
EXPECTED_QUEUE_IDS = (
    "satq-0384b818546e954492a85864",
    "satq-19ba8a09e793d8f73ba71804",
    BLOCKED_QUEUE_ID,
    "satq-718ecc6958a13cc59ccf71b9",
    "satq-73a81fb1881277f022fa7b5b",
    "satq-84c0eaa9ff38437a843f0ff6",
    "satq-f1aa8182923776809ac99da4",
)
PROCESSOR_PATHS = {
    "cli": "scripts/sentinel_change_mosaic.py",
    "module": "datacenter_atlas/satellite_change_mosaic.py",
}
BUILDER_PATHS = {
    "cli": "scripts/build_satellite_mosaic_preparation.py",
    "module": "datacenter_atlas/satellite_mosaic_preparation.py",
}
CLAIM_CONSTRAINTS = {
    "construction_truth_claim": False,
    "data_centre_identity_claim": False,
    "data_centre_type_claim": False,
    "energy_claim": False,
    "imagery_downloaded": False,
    "imagery_opened": False,
    "lifecycle_claim": False,
    "mosaic_execution_performed": False,
    "network_requests_performed": False,
    "operator_claim": False,
    "power_claim": False,
    "production_calibration_claim": False,
    "pue_claim": False,
    "semianalysis_parity_claim": False,
    "workload_claim": False,
}
PUBLICATION_CONTRACT = {
    "atomic_no_clobber_rename": True,
    "existing_regular_parent_required": True,
    "frozen_file_inode_fsync_after_chmod": True,
    "frozen_staging_validation_before_rename": True,
    "lexical_symlink_rejection_before_resolution": True,
    "never_false_success": True,
    "parent_directory_fd_binding": True,
    "path_identity_binding": "st_dev_and_st_ino",
    "rollback_and_cleanup_errors_are_reported": True,
    "target_cleanup_requires_expected_inode": True,
}
RELEASE_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "blocked.jsonl",
        "manifest.json",
        "manifest.sha256",
        "mosaic-specs.jsonl",
        "source-inventory.json",
        "summary.json",
    }
)


class SatelliteMosaicPreparationError(ValueError):
    """Raised when a source or release violates the preparation contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mode(path: Path) -> str:
    return f"{path.stat().st_mode & 0o777:04o}"


def _pin(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "mode": _mode(path), "sha256": _sha(raw)}


def _is_relative(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_symlink_components(path: Path, root: Path, label: str) -> None:
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not _is_relative(lexical, root):
        raise SatelliteMosaicPreparationError(f"{label} is outside the project")
    current = root
    for part in lexical.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteMosaicPreparationError(f"{label} traverses a symlink")


def _project_root(definition_path: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(definition_path.expanduser())))
    if lexical.parent.name != "sources":
        raise SatelliteMosaicPreparationError("definition must be inside sources/")
    root = lexical.parent.parent.resolve(strict=True)
    _reject_symlink_components(lexical, root, "definition")
    return root


def _inside(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SatelliteMosaicPreparationError(f"{label} path is invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise SatelliteMosaicPreparationError(f"{label} path escapes the project")
    lexical = Path(os.path.abspath(os.fspath(root / relative)))
    _reject_symlink_components(lexical, root, label)
    resolved = lexical.resolve(strict=False)
    if not _is_relative(resolved, root):
        raise SatelliteMosaicPreparationError(f"{label} path escapes the project")
    return resolved


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SatelliteMosaicPreparationError(f"{label} is invalid JSON") from error


def _read_json(path: Path, label: str, *, canonical: bool = False) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} is unreadable") from error
    value = _strict_json(raw, label)
    if not isinstance(value, dict):
        raise SatelliteMosaicPreparationError(f"{label} must be an object")
    if canonical and raw != canonical_json(value):
        raise SatelliteMosaicPreparationError(f"{label} is not canonical JSON")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} is unreadable") from error
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        value = _strict_json(line, f"{label} line {number}")
        if not isinstance(value, dict):
            raise SatelliteMosaicPreparationError(
                f"{label} line {number} must be an object"
            )
        rows.append(value)
    if raw != canonical_jsonl(rows):
        raise SatelliteMosaicPreparationError(f"{label} is not canonical JSONL")
    return rows


def _verify_pin(path: Path, expected: Mapping[str, Any], label: str) -> None:
    if set(expected) != {"bytes", "mode", "sha256"}:
        raise SatelliteMosaicPreparationError(f"{label} pin schema is invalid")
    if not path.is_file() or path.is_symlink():
        raise SatelliteMosaicPreparationError(f"{label} is not a regular file")
    if _pin(path) != dict(expected):
        raise SatelliteMosaicPreparationError(f"{label} pin mismatch")


def _validate_source_group(
    root: Path, name: str, group: Mapping[str, Any]
) -> Path:
    if set(group) != {"directories", "directory", "directory_mode", "files"}:
        raise SatelliteMosaicPreparationError(f"{name} source schema drift")
    directory = _inside(root, group["directory"], name)
    if (
        not directory.is_dir()
        or directory.is_symlink()
        or not isinstance(group["directory_mode"], str)
        or _mode(directory) != group["directory_mode"]
    ):
        raise SatelliteMosaicPreparationError(f"{name} directory drift")
    files = group["files"]
    directories = group["directories"]
    if not isinstance(files, dict) or not files or not isinstance(directories, dict):
        raise SatelliteMosaicPreparationError(f"{name} source closure is invalid")
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for node in directory.rglob("*"):
        relative = node.relative_to(directory).as_posix()
        if node.is_symlink():
            raise SatelliteMosaicPreparationError(f"{name}/{relative} is a symlink")
        if node.is_dir():
            actual_directories.add(relative)
        elif node.is_file():
            actual_files.add(relative)
        else:
            raise SatelliteMosaicPreparationError(
                f"{name}/{relative} is not a regular filesystem node"
            )
    if actual_files != set(files) or actual_directories != set(directories):
        raise SatelliteMosaicPreparationError(f"{name} source tree is not closed")
    for relative, expected_mode in sorted(directories.items()):
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(expected_mode, str)
        ):
            raise SatelliteMosaicPreparationError(
                f"{name} directory pin is invalid"
            )
        path = _inside(root, str(Path(group["directory"]) / relative), name)
        if not path.is_dir() or path.is_symlink() or _mode(path) != expected_mode:
            raise SatelliteMosaicPreparationError(
                f"{name}/{relative} directory mode mismatch"
            )
    for relative, expected in sorted(files.items()):
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise SatelliteMosaicPreparationError(f"{name} file pin is invalid")
        path = _inside(root, str(Path(group["directory"]) / relative), name)
        _verify_pin(path, expected, f"{name}/{relative}")
    return directory


def _validate_expected_cases(cases: Any) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or len(cases) != 7:
        raise SatelliteMosaicPreparationError("definition must pin exactly seven cases")
    result: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "aoi_bbox_wgs84",
            "blind_item_id",
            "entity",
            "epochs",
            "expected_state",
            "historical_queue_id",
        }:
            raise SatelliteMosaicPreparationError("case schema drift")
        queue_id = case["historical_queue_id"]
        if queue_id not in EXPECTED_QUEUE_IDS:
            raise SatelliteMosaicPreparationError("case has unexpected queue ID")
        expected_state = BLOCKED_STATE if queue_id == BLOCKED_QUEUE_ID else READY_STATE
        if case["expected_state"] != expected_state:
            raise SatelliteMosaicPreparationError("case expected state drift")
        bbox = case["aoi_bbox_wgs84"]
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in bbox
            )
            or not (bbox[0] < bbox[2] and bbox[1] < bbox[3])
        ):
            raise SatelliteMosaicPreparationError("case AOI is invalid")
        entity = case["entity"]
        if (
            not isinstance(entity, dict)
            or set(entity) != {"id", "name"}
            or not all(isinstance(entity[key], str) and entity[key] for key in entity)
        ):
            raise SatelliteMosaicPreparationError("case entity is invalid")
        epochs = case["epochs"]
        if not isinstance(epochs, dict) or set(epochs) != {"baseline", "current"}:
            raise SatelliteMosaicPreparationError("case epoch set drift")
        for epoch_name in ("baseline", "current"):
            epoch = epochs[epoch_name]
            if not isinstance(epoch, dict) or set(epoch) != {
                "companions",
                "epoch",
                "primary",
            }:
                raise SatelliteMosaicPreparationError("case epoch schema drift")
            if epoch["epoch"] != epoch_name:
                raise SatelliteMosaicPreparationError("case epoch label drift")
            primary = epoch["primary"]
            companions = epoch["companions"]
            if not isinstance(primary, dict) or set(primary) != {
                "id",
                "stac_item_sha256",
            }:
                raise SatelliteMosaicPreparationError("case primary binding drift")
            try:
                ItemBinding(primary["id"], primary["stac_item_sha256"])
            except SentinelMosaicContractError as error:
                raise SatelliteMosaicPreparationError(
                    "case primary binding drift"
                ) from error
            if not isinstance(companions, list):
                raise SatelliteMosaicPreparationError("case companions must be an array")
            parsed: list[ItemBinding] = []
            for companion in companions:
                if not isinstance(companion, dict) or set(companion) != {
                    "id",
                    "stac_item_sha256",
                }:
                    raise SatelliteMosaicPreparationError(
                        "case companion binding drift"
                    )
                try:
                    parsed.append(
                        ItemBinding(
                            companion["id"], companion["stac_item_sha256"]
                        )
                    )
                except SentinelMosaicContractError as error:
                    raise SatelliteMosaicPreparationError(
                        "case companion binding drift"
                    ) from error
            if list(sorted(parsed)) != parsed:
                raise SatelliteMosaicPreparationError("case companions are not sorted")
        result.append(case)
    if [case["historical_queue_id"] for case in result] != list(EXPECTED_QUEUE_IDS):
        raise SatelliteMosaicPreparationError("case ordering or queue partition drift")
    return result


def _source_state(
    definition_path: Path, output_dir: Path | None = None
) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    root = _project_root(definition_path)
    definition_path = Path(os.path.abspath(os.fspath(definition_path.expanduser())))
    definition = _read_json(definition_path, "definition", canonical=True)
    if _mode(definition_path) != "0444":
        raise SatelliteMosaicPreparationError("definition mode must be 0444")
    if set(definition) != {
        "cases",
        "claim_constraints",
        "expected_partition",
        "format",
        "generated_at",
        "processor",
        "publication_contract",
        "release_id",
        "schema_version",
        "sources",
    }:
        raise SatelliteMosaicPreparationError("definition schema drift")
    if (
        definition["format"] != DEFINITION_FORMAT
        or definition["schema_version"] != SCHEMA_VERSION
    ):
        raise SatelliteMosaicPreparationError("definition format mismatch")
    if definition["claim_constraints"] != CLAIM_CONSTRAINTS:
        raise SatelliteMosaicPreparationError("claim constraints drift")
    if definition["publication_contract"] != PUBLICATION_CONTRACT:
        raise SatelliteMosaicPreparationError("publication contract drift")
    if definition["expected_partition"] != {
        "blocked": 1,
        "blocked_queue_id": BLOCKED_QUEUE_ID,
        "metadata_ready": 6,
        "total": 7,
    }:
        raise SatelliteMosaicPreparationError("expected partition drift")
    _validate_expected_cases(definition["cases"])
    processor = definition["processor"]
    if not isinstance(processor, dict) or set(processor) != {
        "algorithm_version",
        "files",
        "minimum_component_area_m2",
        "spectral_core_algorithm_version",
    }:
        raise SatelliteMosaicPreparationError("processor schema drift")
    if (
        processor["algorithm_version"] != ALGORITHM_VERSION
        or processor["spectral_core_algorithm_version"]
        != SPECTRAL_CORE_ALGORITHM_VERSION
        or processor["minimum_component_area_m2"] != 5000
        or not isinstance(processor["files"], dict)
        or set(processor["files"]) != set(PROCESSOR_PATHS)
    ):
        raise SatelliteMosaicPreparationError("processor contract drift")
    processor_paths: dict[str, Path] = {}
    for name, expected_path in sorted(PROCESSOR_PATHS.items()):
        source = processor["files"][name]
        if not isinstance(source, dict) or set(source) != {
            "bytes",
            "mode",
            "path",
            "sha256",
        }:
            raise SatelliteMosaicPreparationError(f"processor {name} pin drift")
        if source["path"] != expected_path:
            raise SatelliteMosaicPreparationError(f"processor {name} path drift")
        path = _inside(root, source["path"], f"processor {name}")
        _verify_pin(
            path,
            {key: source[key] for key in ("bytes", "mode", "sha256")},
            f"processor {name}",
        )
        processor_paths[name] = path
    sources = definition["sources"]
    if not isinstance(sources, dict) or set(sources) != {
        "aggregate",
        "catalogs",
        "preparation",
    }:
        raise SatelliteMosaicPreparationError("source schema drift")
    catalogs = sources["catalogs"]
    if not isinstance(catalogs, dict) or set(catalogs) != set(EXPECTED_QUEUE_IDS):
        raise SatelliteMosaicPreparationError("catalog source partition drift")
    directories = {
        "aggregate": _validate_source_group(root, "aggregate", sources["aggregate"]),
        "preparation": _validate_source_group(
            root, "preparation", sources["preparation"]
        ),
    }
    for queue_id in EXPECTED_QUEUE_IDS:
        group = catalogs[queue_id]
        if not isinstance(group, dict):
            raise SatelliteMosaicPreparationError("catalog source schema drift")
        if set(group.get("files", {})) != {
            "baseline-response.json",
            "current-response.json",
            "manifest.json",
        }:
            raise SatelliteMosaicPreparationError("catalog file set drift")
        expected_suffix = f"jobs/{queue_id}/catalog"
        if not str(group.get("directory", "")).endswith(expected_suffix):
            raise SatelliteMosaicPreparationError("catalog path does not match queue ID")
        directories[f"catalog:{queue_id}"] = _validate_source_group(
            root, f"catalog:{queue_id}", group
        )
    nodes: list[tuple[str, Path]] = [
        ("definition", definition_path),
        *directories.items(),
        *((f"processor:{name}", path) for name, path in processor_paths.items()),
    ]
    if output_dir is not None:
        output_lexical = Path(os.path.abspath(os.fspath(output_dir.expanduser())))
        _reject_symlink_components(output_lexical, root, "output")
        nodes.append(("output", output_lexical))
    for index, (left_name, left_path) in enumerate(nodes):
        for right_name, right_path in nodes[index + 1 :]:
            if _is_relative(left_path, right_path) or _is_relative(
                right_path, left_path
            ):
                raise SatelliteMosaicPreparationError(
                    f"{left_name} overlaps {right_name}"
                )
    return definition, root, directories


def _verify_manifest_sidecar(directory: Path, label: str) -> dict[str, Any]:
    manifest_raw = (directory / "manifest.json").read_bytes()
    expected = f"{_sha(manifest_raw)}  manifest.json\n".encode("ascii")
    if (directory / "manifest.sha256").read_bytes() != expected:
        raise SatelliteMosaicPreparationError(f"{label} manifest sidecar mismatch")
    manifest = _read_json(directory / "manifest.json", f"{label} manifest", canonical=True)
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise SatelliteMosaicPreparationError(f"{label} manifest outputs missing")
    for relative, expected_pin in outputs.items():
        if not isinstance(relative, str) or not isinstance(expected_pin, dict):
            raise SatelliteMosaicPreparationError(f"{label} output pin is invalid")
        _verify_pin(directory / relative, expected_pin, f"{label}/{relative}")
    return manifest


def _unique(rows: Sequence[Mapping[str, Any]], key: str, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise SatelliteMosaicPreparationError(f"{label} has invalid or duplicate {key}")
        result[value] = row
    return result


def _archive_pin(
    definition: Mapping[str, Any], queue_id: str, epoch: str
) -> dict[str, Any]:
    group = definition["sources"]["catalogs"][queue_id]
    filename = f"{epoch}-response.json"
    pin = group["files"][filename]
    return {
        "bytes": pin["bytes"],
        "mode": pin["mode"],
        "path": f"{group['directory']}/{filename}",
        "sha256": pin["sha256"],
    }


def _load_archive(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if _sha(raw) != expected_sha256:
        raise SatelliteMosaicPreparationError(f"{label} response hash mismatch")
    value = _strict_json(raw, label)
    if not isinstance(value, dict):
        raise SatelliteMosaicPreparationError(f"{label} response must be an object")
    return value


def _selected_item_summary(
    item: Mapping[str, Any], binding: ItemBinding, role: str
) -> dict[str, Any]:
    if canonical_sha256(item) != binding.stac_item_sha256:
        raise SatelliteMosaicPreparationError("selected item hash drift")
    instant = parse_rfc3339_instant(
        item["properties"].get("datetime"), f"selected item {binding.item_id} datetime"
    )
    return {
        "datetime_utc": instant.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "id": binding.item_id,
        "mgrs_tile": mgrs_tile(item),
        "role": role,
        "stac_item_sha256": binding.stac_item_sha256,
    }


def _derive_epoch(
    *,
    archive_path: Path,
    archive_pin: Mapping[str, Any],
    bbox: Sequence[float],
    epoch: str,
    expected: Mapping[str, Any],
    transform_bounds: Any,
) -> tuple[dict[str, Any], Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    primary = ItemBinding(
        expected["primary"]["id"], expected["primary"]["stac_item_sha256"]
    )
    companions = tuple(
        ItemBinding(value["id"], value["stac_item_sha256"])
        for value in expected["companions"]
    )
    document = _load_archive(archive_path, archive_pin["sha256"], epoch)
    try:
        preflight = preflight_archived_epoch(
            document, primary, bbox, transform_bounds
        )
        primary_item, items = select_bound_items(document, primary, companions)
    except (SentinelMosaicContractError, KeyError, TypeError) as error:
        raise SatelliteMosaicPreparationError(
            f"{epoch} archived STAC contract failed"
        ) from error
    discovered = preflight["proposed_explicit_bindings"]
    expected_bindings = [primary.as_dict(), *(binding.as_dict() for binding in companions)]
    expected_bindings.sort(key=lambda value: value["id"])
    if discovered != expected_bindings:
        raise SatelliteMosaicPreparationError(
            f"{epoch} discovered bindings differ from definition"
        )
    by_id = {str(item["id"]): item for item in items}
    selected = [_selected_item_summary(primary_item, primary, "primary")]
    selected.extend(
        _selected_item_summary(by_id[binding.item_id], binding, "companion")
        for binding in companions
    )
    coverage = preflight["coverage"]
    if (
        set(coverage.get("assets", {})) != set(REQUIRED_ASSETS)
        or preflight.get("network_requests") != 0
        or preflight.get("algorithm_version") != ALGORITHM_VERSION
        or preflight.get("spectral_core_algorithm_version")
        != SPECTRAL_CORE_ALGORITHM_VERSION
    ):
        raise SatelliteMosaicPreparationError(f"{epoch} preflight contract drift")
    properties = primary_item["properties"]
    result = {
        "acquisition": {
            "datastrip_id": properties["s2:datastrip_id"],
            "datatake_id": properties["s2:datatake_id"],
        },
        "archived_stac_response": dict(archive_pin),
        "companions": [binding.as_dict() for binding in companions],
        "coverage": coverage,
        "epoch": epoch,
        "metadata_solvable": preflight["metadata_solvable"],
        "network_requests": 0,
        "primary": primary.as_dict(),
        "selected_items": selected,
    }
    return result, primary_item, items


def _validate_cross_epoch(
    baseline_primary: Mapping[str, Any], current_primary: Mapping[str, Any]
) -> dict[str, Any]:
    baseline_datetime = parse_rfc3339_instant(
        baseline_primary["properties"].get("datetime"), "baseline primary datetime"
    )
    current_datetime = parse_rfc3339_instant(
        current_primary["properties"].get("datetime"), "current primary datetime"
    )
    if baseline_datetime >= current_datetime:
        raise SatelliteMosaicPreparationError("baseline must precede current epoch")
    if mgrs_tile(baseline_primary) != mgrs_tile(current_primary):
        raise SatelliteMosaicPreparationError("primary MGRS tile differs across epochs")
    for asset in ("red", "swir16", "scl"):
        if grid_from_item(baseline_primary, asset) != grid_from_item(
            current_primary, asset
        ):
            raise SatelliteMosaicPreparationError(
                f"primary {asset} grid differs across epochs"
            )
    return {
        "baseline_precedes_current": True,
        "primary_grids_exactly_equal": ["red", "scl", "swir16"],
        "primary_mgrs_tile": mgrs_tile(baseline_primary),
    }


def _number_text(value: int | float) -> str:
    return format(float(value), ".15g")


def _execution_arguments(
    case: Mapping[str, Any], epochs: Mapping[str, Mapping[str, Any]]
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
        for companion in value["companions"]:
            arguments.extend(
                [
                    f"--{epoch}-companion",
                    f"{companion['id']}={companion['stac_item_sha256']}",
                ]
            )
    arguments.extend(
        [
            "--bbox",
            ",".join(_number_text(value) for value in case["aoi_bbox_wgs84"]),
            "--entity-id",
            case["entity"]["id"],
            "--entity-name",
            case["entity"]["name"],
            "--output-dir",
            "{job_output_dir}",
            "--minimum-component-area-m2",
            "5000",
        ]
    )
    return arguments


def _source_inventory(definition: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for group_name in ("aggregate", "preparation"):
        group = definition["sources"][group_name]
        for relative, pin in sorted(group["files"].items()):
            rows.append(
                {
                    "bytes": pin["bytes"],
                    "mode": pin["mode"],
                    "path": f"{group['directory']}/{relative}",
                    "sha256": pin["sha256"],
                    "source_group": group_name,
                }
            )
    for queue_id in EXPECTED_QUEUE_IDS:
        group = definition["sources"]["catalogs"][queue_id]
        for relative, pin in sorted(group["files"].items()):
            rows.append(
                {
                    "bytes": pin["bytes"],
                    "mode": pin["mode"],
                    "path": f"{group['directory']}/{relative}",
                    "sha256": pin["sha256"],
                    "source_group": f"catalog:{queue_id}",
                }
            )
    for name, pin in sorted(definition["processor"]["files"].items()):
        rows.append({**pin, "source_group": f"processor:{name}"})
    rows.sort(key=lambda row: (row["path"], row["source_group"]))
    if len({row["path"] for row in rows}) != len(rows):
        raise SatelliteMosaicPreparationError("source inventory contains duplicate paths")
    return {
        "files": rows,
        "schema_version": CONTENT_SCHEMA_VERSION,
        "source_file_count": len(rows),
    }


def _derive_payload_rows(
    definition: Mapping[str, Any], directories: Mapping[str, Path]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        from rasterio.warp import transform_bounds
    except ImportError as error:  # pragma: no cover - environment guard
        raise SatelliteMosaicPreparationError(
            "metadata validation requires the pinned rasterio runtime"
        ) from error
    aggregate_manifest = _verify_manifest_sidecar(
        directories["aggregate"], "aggregate"
    )
    preparation_manifest = _verify_manifest_sidecar(
        directories["preparation"], "preparation"
    )
    aggregate_summary = aggregate_manifest.get("summary")
    if (
        aggregate_manifest.get("format")
        != "datacenter-atlas-satellite-calibration-v2-aggregate-v1"
        or not isinstance(aggregate_summary, dict)
        or aggregate_summary.get("numerical_items") != 43
        or aggregate_summary.get("blind_items_ready_for_review") != 36
        or aggregate_summary.get("blind_items_blocked_multitile") != 7
    ):
        raise SatelliteMosaicPreparationError("aggregate partition drift")
    if (
        preparation_manifest.get("format")
        != "datacenter-atlas-satellite-calibration-rereview-preparation-v1"
        or preparation_manifest.get("preparation_id")
        != "algorithm-v2-rereview-preparation-2026-07-19-v1"
    ):
        raise SatelliteMosaicPreparationError("preparation manifest drift")
    blocked_rows = _read_jsonl(
        directories["aggregate"] / "blocked-multitile.jsonl",
        "aggregate blocked rows",
    )
    rerun_rows = _read_jsonl(
        directories["preparation"] / "rerun-specs.jsonl", "rerun specs"
    )
    if len(blocked_rows) != 7 or len(rerun_rows) != 43:
        raise SatelliteMosaicPreparationError("source row count drift")
    blocked_by_blind = _unique(blocked_rows, "blind_item_id", "blocked rows")
    rerun_by_blind = _unique(rerun_rows, "blind_item_id", "rerun rows")
    cases = {case["historical_queue_id"]: case for case in definition["cases"]}
    blocked_queue_ids: set[str] = set()
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for blind_id, aggregate_row in sorted(blocked_by_blind.items()):
        rerun = rerun_by_blind.get(blind_id)
        if rerun is None:
            raise SatelliteMosaicPreparationError("blocked row lacks rerun specification")
        queue_id = rerun.get("historical_queue_id")
        if queue_id not in cases or queue_id in blocked_queue_ids:
            raise SatelliteMosaicPreparationError("blocked queue mapping drift")
        blocked_queue_ids.add(queue_id)
        case = cases[queue_id]
        if (
            aggregate_row.get("state") != "blocked_multitile_required"
            or aggregate_row.get("blocker")
            != "aoi_crosses_scene_asset_requires_multitile_mosaic"
            or aggregate_row.get("rerun_spec_sha256")
            != _sha(canonical_line(rerun))
            or aggregate_row.get("blind_item_id") != case["blind_item_id"]
            or rerun.get("entity") != case["entity"]
            or rerun.get("aoi_bbox_wgs84") != case["aoi_bbox_wgs84"]
            or aggregate_row.get("entity") != case["entity"]
            or aggregate_row.get("aoi_bbox_wgs84") != case["aoi_bbox_wgs84"]
        ):
            raise SatelliteMosaicPreparationError("blocked source identity drift")
        selected_scenes = rerun.get("selected_scenes")
        artifacts = rerun.get("source_catalog_artifacts")
        if (
            not isinstance(selected_scenes, dict)
            or set(selected_scenes) != {"baseline", "current"}
            or not isinstance(artifacts, dict)
            or set(artifacts)
            != {"baseline-response.json", "current-response.json", "manifest.json"}
        ):
            raise SatelliteMosaicPreparationError("rerun source schema drift")
        catalog_group = definition["sources"]["catalogs"][queue_id]
        catalog_manifest = _read_json(
            directories[f"catalog:{queue_id}"] / "manifest.json",
            f"catalog {queue_id} manifest",
        )
        if (
            catalog_manifest.get("schema_version") != 1
            or catalog_manifest.get("selected_ids")
            != {
                "baseline": case["epochs"]["baseline"]["primary"]["id"],
                "current": case["epochs"]["current"]["primary"]["id"],
            }
        ):
            raise SatelliteMosaicPreparationError("catalog selected IDs drift")
        for filename, artifact in artifacts.items():
            pin = catalog_group["files"][filename]
            expected_path = f"{catalog_group['directory']}/{filename}"
            if artifact != {
                "bytes": pin["bytes"],
                "path": expected_path,
                "sha256": pin["sha256"],
            }:
                raise SatelliteMosaicPreparationError("rerun catalog pin drift")
        epochs: dict[str, dict[str, Any]] = {}
        primary_items: dict[str, Mapping[str, Any]] = {}
        selected_epoch_items: dict[str, tuple[Mapping[str, Any], ...]] = {}
        for epoch in ("baseline", "current"):
            expected_epoch = case["epochs"][epoch]
            if selected_scenes[epoch] != expected_epoch["primary"]:
                raise SatelliteMosaicPreparationError("primary scene binding drift")
            archive_pin = _archive_pin(definition, queue_id, epoch)
            epoch_record, primary_item, items = _derive_epoch(
                archive_path=directories[f"catalog:{queue_id}"]
                / f"{epoch}-response.json",
                archive_pin=archive_pin,
                bbox=case["aoi_bbox_wgs84"],
                epoch=epoch,
                expected=expected_epoch,
                transform_bounds=transform_bounds,
            )
            epochs[epoch] = epoch_record
            primary_items[epoch] = primary_item
            selected_epoch_items[epoch] = items
        cross_epoch = _validate_cross_epoch(
            primary_items["baseline"], primary_items["current"]
        )
        common = {
            "algorithm_version": ALGORITHM_VERSION,
            "aoi_bbox_wgs84": case["aoi_bbox_wgs84"],
            "blind_item_id": blind_id,
            "claim_constraints": CLAIM_CONSTRAINTS,
            "cross_epoch_contract": cross_epoch,
            "entity": case["entity"],
            "epochs": epochs,
            "execution_performed": False,
            "historical_queue_id": queue_id,
            "imagery_downloaded": False,
            "imagery_opened": False,
            "network_requests": 0,
            "processor": definition["processor"],
            "schema_version": CONTENT_SCHEMA_VERSION,
            "source_rows": {
                "aggregate_blocked_row_sha256": _sha(canonical_line(aggregate_row)),
                "rerun_spec_sha256": _sha(canonical_line(rerun)),
            },
            "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
        }
        metadata_ready = all(epochs[epoch]["metadata_solvable"] for epoch in epochs)
        if metadata_ready:
            if case["expected_state"] != READY_STATE:
                raise SatelliteMosaicPreparationError("blocked case became ready")
            ready.append(
                {
                    **common,
                    "execution": {
                        "arguments": _execution_arguments(case, epochs),
                        "output_placeholder": "{job_output_dir}",
                        "script": PROCESSOR_PATHS["cli"],
                    },
                    "state": READY_STATE,
                }
            )
            continue
        if queue_id != BLOCKED_QUEUE_ID or case["expected_state"] != BLOCKED_STATE:
            raise SatelliteMosaicPreparationError("unexpected metadata blocker")
        if not epochs["baseline"]["metadata_solvable"] or epochs["current"]["metadata_solvable"]:
            raise SatelliteMosaicPreparationError("MRS5 blocker epoch drift")
        baseline_tiles = {
            item["mgrs_tile"] for item in epochs["baseline"]["selected_items"]
        }
        current_tiles = {
            item["mgrs_tile"] for item in epochs["current"]["selected_items"]
        }
        missing_tiles = sorted(baseline_tiles - current_tiles)
        if missing_tiles != ["31TFJ"] or epochs["current"]["companions"]:
            raise SatelliteMosaicPreparationError("MRS5 missing companion drift")
        blocked.append(
            {
                **common,
                "blocker": BLOCKER,
                "missing_binding": {
                    "epoch": "current",
                    "item_id": None,
                    "mgrs_tile": "31TFJ",
                    "stac_item_sha256": None,
                },
                "state": BLOCKED_STATE,
            }
        )
    if blocked_queue_ids != set(EXPECTED_QUEUE_IDS):
        raise SatelliteMosaicPreparationError("seven-row source partition drift")
    ready.sort(key=lambda row: row["historical_queue_id"])
    blocked.sort(key=lambda row: row["historical_queue_id"])
    if len(ready) != 6 or len(blocked) != 1:
        raise SatelliteMosaicPreparationError("derived 6+1 partition drift")
    summary = {
        "algorithm_version": ALGORITHM_VERSION,
        "blocked": 1,
        "blocked_queue_id": BLOCKED_QUEUE_ID,
        "claim_constraints": CLAIM_CONSTRAINTS,
        "execution_specs": 6,
        "imagery_downloads": 0,
        "imagery_opened": 0,
        "metadata_ready": 6,
        "mosaic_executions": 0,
        "network_requests": 0,
        "preparation_only": True,
        "release_id": definition["release_id"],
        "schema_version": SCHEMA_VERSION,
        "publication_mechanics_version": 2,
        "source_rows": 7,
        "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
    }
    return ready, blocked, summary


def _readme(definition: Mapping[str, Any]) -> bytes:
    return (
        "# Sentinel mosaic-v3 blocked-row preparation\n\n"
        "This immutable, metadata-only release binds the seven algorithm-v2 "
        "calibration rows that stopped at a single-scene boundary to the accepted "
        "Sentinel mosaic-v3 contract. Six rows have explicit primary and companion "
        "item IDs and canonical STAC item hashes for both epochs. The MRS5 row "
        "remains blocked because its archived current response has no same-acquisition "
        "31TFJ companion.\n\n"
        "No network request, imagery download, imagery read, or mosaic execution was "
        "performed. `mosaic-specs.jsonl` is a preparation interface, not an execution "
        "release or a calibration result. `blocked.jsonl` does not guess or substitute "
        "a missing item. Satellite metadata and future visible-change output establish "
        "no data-centre identity, construction lifecycle, type, operator, capacity, "
        "power, energy, PUE, workload, or SemiAnalysis parity.\n\n"
        "Version 2 supersedes version 1 only for publication mechanics. It binds "
        "the validated staging and target directory identities, fsyncs frozen file "
        "inodes after chmod, uses an atomic no-clobber rename, and reports every "
        "publication, rollback, or cleanup failure without a success fallback.\n\n"
        f"Release ID: `{definition['release_id']}`.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains metadata derived from archived Sentinel-2 L2A STAC responses. "
        "Copernicus Sentinel data attribution applies. No imagery is redistributed "
        "by this preparation release.\n"
    ).encode("utf-8")


def _builder_pins(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, relative in sorted(BUILDER_PATHS.items()):
        path = _inside(root, relative, f"builder {name}")
        if not path.is_file() or path.is_symlink():
            raise SatelliteMosaicPreparationError(f"builder {name} is invalid")
        result[name] = {"path": relative, **_pin(path)}
    return result


def _payloads(
    definition_path: Path, output_dir: Path | None = None
) -> tuple[dict[str, bytes], dict[str, Any], Path]:
    definition, root, directories = _source_state(definition_path, output_dir)
    ready, blocked, summary = _derive_payload_rows(definition, directories)
    inventory = _source_inventory(definition)
    summary["source_file_pins"] = inventory["source_file_count"]
    payloads = {
        "ATTRIBUTION.txt": _attribution(),
        "README.md": _readme(definition),
        "blocked.jsonl": canonical_jsonl(blocked),
        "mosaic-specs.jsonl": canonical_jsonl(ready),
        "source-inventory.json": canonical_json(inventory),
        "summary.json": canonical_json(summary),
    }
    manifest = {
        "builder": _builder_pins(root),
        "definition": {
            "path": definition_path.resolve(strict=True).relative_to(root).as_posix(),
            **_pin(definition_path),
        },
        "format": RELEASE_FORMAT,
        "outputs": {
            name: {"bytes": len(raw), "mode": "0444", "sha256": _sha(raw)}
            for name, raw in sorted(payloads.items())
        },
        "processor": definition["processor"],
        "publication_contract": definition["publication_contract"],
        "release_id": definition["release_id"],
        "schema_version": SCHEMA_VERSION,
        "sources": definition["sources"],
        "summary": summary,
    }
    payloads["manifest.json"] = canonical_json(manifest)
    payloads["manifest.sha256"] = (
        f"{_sha(payloads['manifest.json'])}  manifest.json\n".encode("ascii")
    )
    return payloads, manifest, root


_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _identity_text(value: tuple[int, int]) -> str:
    return f"dev={value[0]},ino={value[1]}"


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _stat_at(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _require_directory_identity_at(
    parent_fd: int,
    name: str,
    expected: tuple[int, int],
    label: str,
) -> os.stat_result:
    value = _stat_at(parent_fd, name)
    if value is None:
        raise SatelliteMosaicPreparationError(f"{label} is absent")
    if not stat.S_ISDIR(value.st_mode) or _identity(value) != expected:
        raise SatelliteMosaicPreparationError(
            f"{label} identity mismatch: expected {_identity_text(expected)}, "
            f"found {_identity_text(_identity(value))}"
        )
    return value


def _require_directory_path_identity(
    path: Path, expected: tuple[int, int], label: str
) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(value.st_mode) or _identity(value) != expected:
        raise SatelliteMosaicPreparationError(
            f"{label} path identity mismatch: expected {_identity_text(expected)}, "
            f"found {_identity_text(_identity(value))}"
        )
    return value


def _require_open_directory_identity(
    directory_fd: int, expected: tuple[int, int], label: str
) -> os.stat_result:
    value = os.fstat(directory_fd)
    if not stat.S_ISDIR(value.st_mode) or _identity(value) != expected:
        raise SatelliteMosaicPreparationError(
            f"{label} descriptor identity mismatch"
        )
    return value


def _open_bound_directory(
    path: Path, root: Path, label: str
) -> tuple[Path, int, tuple[int, int]]:
    lexical = Path(os.path.abspath(os.fspath(path.expanduser())))
    _reject_symlink_components(lexical, root, label)
    try:
        before = os.lstat(lexical)
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(before.st_mode):
        raise SatelliteMosaicPreparationError(f"{label} is not a regular directory")
    try:
        descriptor = os.open(lexical, _DIRECTORY_OPEN_FLAGS)
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} cannot be opened safely") from error
    expected = _identity(before)
    try:
        _require_open_directory_identity(descriptor, expected, label)
        _require_directory_path_identity(lexical, expected, label)
    except Exception:
        os.close(descriptor)
        raise
    return lexical, descriptor, expected


def _open_output_parent(
    output_dir: Path, root: Path
) -> tuple[Path, Path, int, tuple[int, int]]:
    output = Path(os.path.abspath(os.fspath(output_dir.expanduser())))
    _reject_symlink_components(output, root, "output")
    if output == root or output.name in {"", ".", ".."}:
        raise SatelliteMosaicPreparationError("output path is invalid")
    parent, parent_fd, parent_identity = _open_bound_directory(
        output.parent, root, "output parent"
    )
    if _stat_at(parent_fd, output.name) is not None:
        os.close(parent_fd)
        raise SatelliteMosaicPreparationError("output already exists")
    return output, parent, parent_fd, parent_identity


def _read_all(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_bound_release_tree(
    directory_fd: int, expected_identity: tuple[int, int]
) -> dict[str, bytes]:
    root_stat = _require_open_directory_identity(
        directory_fd, expected_identity, "release"
    )
    if root_stat.st_mode & 0o777 != 0o555:
        raise SatelliteMosaicPreparationError("release directory mode mismatch")
    names = set(os.listdir(directory_fd))
    if names != RELEASE_FILES:
        raise SatelliteMosaicPreparationError("release file set is not closed")
    result: dict[str, bytes] = {}
    for name in sorted(names):
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o777 != 0o444:
            raise SatelliteMosaicPreparationError(
                f"release file mode or type mismatch: {name}"
            )
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                raise SatelliteMosaicPreparationError(
                    f"release file identity changed while opening: {name}"
                )
            raw = _read_all(descriptor)
            after = os.fstat(descriptor)
            if (
                _identity(after) != _identity(opened)
                or after.st_size != len(raw)
                or after.st_mode & 0o777 != 0o444
            ):
                raise SatelliteMosaicPreparationError(
                    f"release file changed while reading: {name}"
                )
        finally:
            os.close(descriptor)
        path_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _identity(path_after) != _identity(before):
            raise SatelliteMosaicPreparationError(
                f"release file path identity changed: {name}"
            )
        result[name] = raw
    return result


def _sync_parent(parent_fd: int, phase: str) -> None:
    try:
        os.fsync(parent_fd)
    except OSError as error:
        raise OSError(error.errno, f"{phase}: {error.strerror}") from error


def _rename_noreplace(parent_fd: int, source_name: str, target_name: str) -> None:
    if (
        not source_name
        or not target_name
        or "/" in source_name
        or "/" in target_name
        or source_name in {".", ".."}
        or target_name in {".", ".."}
    ):
        raise SatelliteMosaicPreparationError("rename names must be single components")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    target = os.fsencode(target_name)
    if sys.platform == "darwin":
        function = library.renameatx_np
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(parent_fd, source, parent_fd, target, 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(parent_fd, source, parent_fd, target, 0x00000001)
    else:  # pragma: no cover - supported publication hosts are Darwin/Linux
        raise OSError(errno.ENOTSUP, "atomic no-clobber directory rename unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), target_name)


def _create_staging(
    parent_fd: int, target_name: str
) -> tuple[str, int, tuple[int, int]]:
    for _ in range(100):
        name = f".{target_name}.staging-{secrets.token_hex(8)}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        identity = _identity(value)
        try:
            descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
            _require_open_directory_identity(descriptor, identity, "staging")
        except Exception as open_error:
            cleanup_errors: list[str] = []
            try:
                _require_directory_identity_at(parent_fd, name, identity, "staging")
                os.rmdir(name, dir_fd=parent_fd)
            except Exception as cleanup_error:
                cleanup_errors.append(f"staging cleanup failed: {_error_text(cleanup_error)}")
            try:
                _sync_parent(parent_fd, "staging-creation cleanup parent fsync")
            except Exception as sync_error:
                cleanup_errors.append(f"cleanup parent fsync failed: {_error_text(sync_error)}")
            detail = " | ".join(cleanup_errors)
            raise SatelliteMosaicPreparationError(
                f"staging open failed: {_error_text(open_error)}"
                + (f" | {detail}" if detail else "")
            ) from open_error
        return name, descriptor, identity
    raise SatelliteMosaicPreparationError("could not allocate a unique staging name")


def _write_payloads(directory_fd: int, payloads: Mapping[str, bytes]) -> None:
    for name, raw in sorted(payloads.items()):
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    os.fsync(directory_fd)


def _freeze_staging(
    parent_fd: int,
    staging_name: str,
    staging_fd: int,
    staging_identity: tuple[int, int],
) -> None:
    _require_directory_identity_at(
        parent_fd, staging_name, staging_identity, "staging"
    )
    _require_open_directory_identity(staging_fd, staging_identity, "staging")
    names = set(os.listdir(staging_fd))
    if names != RELEASE_FILES:
        raise SatelliteMosaicPreparationError("staging file set is not closed")
    for name in sorted(names):
        before = os.stat(name, dir_fd=staging_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SatelliteMosaicPreparationError(
                f"staging node is not a regular file: {name}"
            )
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=staging_fd)
        try:
            opened = os.fstat(descriptor)
            if _identity(opened) != _identity(before):
                raise SatelliteMosaicPreparationError(
                    f"staging file identity changed while opening: {name}"
                )
            os.fchmod(descriptor, 0o444)
            # This fsync is intentionally after chmod so the frozen inode mode,
            # data, and prior file fsync all precede publication.
            os.fsync(descriptor)
            frozen = os.fstat(descriptor)
            if _identity(frozen) != _identity(opened) or frozen.st_mode & 0o777 != 0o444:
                raise SatelliteMosaicPreparationError(
                    f"staging file did not freeze durably: {name}"
                )
        finally:
            os.close(descriptor)
        path_after = os.stat(name, dir_fd=staging_fd, follow_symlinks=False)
        if _identity(path_after) != _identity(before):
            raise SatelliteMosaicPreparationError(
                f"staging file path identity changed: {name}"
            )
    os.fchmod(staging_fd, 0o555)
    os.fsync(staging_fd)
    frozen_root = _require_directory_identity_at(
        parent_fd, staging_name, staging_identity, "staging"
    )
    if frozen_root.st_mode & 0o777 != 0o555:
        raise SatelliteMosaicPreparationError("staging directory mode mismatch")


def _cleanup_bound_tree(
    parent_fd: int,
    name: str,
    tree_fd: int,
    expected_identity: tuple[int, int],
) -> None:
    _require_directory_identity_at(parent_fd, name, expected_identity, "cleanup tree")
    _require_open_directory_identity(tree_fd, expected_identity, "cleanup tree")
    os.fchmod(tree_fd, 0o700)
    os.fsync(tree_fd)
    for child_name in sorted(os.listdir(tree_fd)):
        before = os.stat(child_name, dir_fd=tree_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SatelliteMosaicPreparationError(
                f"cleanup refused non-regular node: {child_name}"
            )
        descriptor = os.open(child_name, _FILE_READ_FLAGS, dir_fd=tree_fd)
        try:
            opened = os.fstat(descriptor)
            if _identity(opened) != _identity(before):
                raise SatelliteMosaicPreparationError(
                    f"cleanup file identity changed: {child_name}"
                )
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        path_after = os.stat(child_name, dir_fd=tree_fd, follow_symlinks=False)
        if _identity(path_after) != _identity(before):
            raise SatelliteMosaicPreparationError(
                f"cleanup path replacement detected: {child_name}"
            )
        os.unlink(child_name, dir_fd=tree_fd)
    os.fsync(tree_fd)
    _require_directory_identity_at(parent_fd, name, expected_identity, "cleanup tree")
    os.rmdir(name, dir_fd=parent_fd)
    _sync_parent(parent_fd, "cleanup parent fsync")
    if _stat_at(parent_fd, name) is not None:
        raise SatelliteMosaicPreparationError("cleanup name still exists")


def _recover_publication_failure(
    *,
    primary_error: BaseException,
    parent_path: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staging_name: str,
    target_name: str,
    tree_fd: int,
    tree_identity: tuple[int, int],
) -> None:
    errors = [f"primary failure: {_error_text(primary_error)}"]
    try:
        _require_open_directory_identity(parent_fd, parent_identity, "output parent")
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
    except Exception as error:
        errors.append(f"parent identity check failed: {_error_text(error)}")

    target = _stat_at(parent_fd, target_name)
    staging = _stat_at(parent_fd, staging_name)
    target_matches = target is not None and _identity(target) == tree_identity
    staging_matches = staging is not None and _identity(staging) == tree_identity

    if target_matches:
        if staging is not None:
            errors.append("rollback destination is occupied; target rollback not attempted")
        else:
            try:
                _require_directory_identity_at(
                    parent_fd, target_name, tree_identity, "rollback target"
                )
                _rename_noreplace(parent_fd, target_name, staging_name)
                _require_directory_identity_at(
                    parent_fd, staging_name, tree_identity, "rolled-back staging"
                )
                staging_matches = True
                target_matches = False
            except Exception as error:
                errors.append(f"rollback rename failed: {_error_text(error)}")
            else:
                try:
                    _sync_parent(parent_fd, "rollback parent fsync")
                except Exception as error:
                    errors.append(f"rollback parent fsync failed: {_error_text(error)}")

    target = _stat_at(parent_fd, target_name)
    staging = _stat_at(parent_fd, staging_name)
    target_matches = target is not None and _identity(target) == tree_identity
    staging_matches = staging is not None and _identity(staging) == tree_identity
    cleanup_name = staging_name if staging_matches else target_name if target_matches else None
    if cleanup_name is not None:
        try:
            _cleanup_bound_tree(
                parent_fd, cleanup_name, tree_fd, tree_identity
            )
        except Exception as error:
            errors.append(f"cleanup failed: {_error_text(error)}")
    else:
        errors.append("validated tree is no longer bound to staging or target name")

    target_after = _stat_at(parent_fd, target_name)
    if target_after is not None:
        if _identity(target_after) == tree_identity:
            errors.append("validated target remains after failed recovery")
        else:
            errors.append(
                "target path contains a substituted tree that was preserved: "
                f"{_identity_text(_identity(target_after))}"
            )
    staging_after = _stat_at(parent_fd, staging_name)
    if staging_after is not None and _identity(staging_after) == tree_identity:
        errors.append("validated staging tree remains after failed recovery")
    try:
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
    except Exception as error:
        errors.append(f"final parent identity check failed: {_error_text(error)}")
    raise SatelliteMosaicPreparationError(
        "publication failed | " + " | ".join(errors)
    ) from primary_error


def validate_satellite_mosaic_preparation(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = _project_root(definition_path)
    output, directory_fd, output_identity = _open_bound_directory(
        output_dir, root, "output"
    )
    try:
        actual = _read_bound_release_tree(directory_fd, output_identity)
        expected, manifest, _ = _payloads(definition_path, output)
        for name in RELEASE_FILES:
            if actual[name] != expected[name]:
                raise SatelliteMosaicPreparationError(
                    f"{name} differs from deterministic reproduction"
                )
        parsed = _strict_json(actual["manifest.json"], "release manifest")
        if not isinstance(parsed, dict) or actual["manifest.json"] != canonical_json(parsed):
            raise SatelliteMosaicPreparationError("release manifest is not canonical JSON")
        if parsed != manifest:
            raise SatelliteMosaicPreparationError("manifest semantic mismatch")
        _require_open_directory_identity(directory_fd, output_identity, "output")
        _require_directory_path_identity(output, output_identity, "output")
        return manifest
    finally:
        os.close(directory_fd)


def write_satellite_mosaic_preparation(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = _project_root(definition_path)
    output, parent_path, parent_fd, parent_identity = _open_output_parent(
        output_dir, root
    )
    staging_name: str | None = None
    tree_fd: int | None = None
    tree_identity: tuple[int, int] | None = None
    try:
        # Full source closure and deterministic payload reproduction complete
        # before a staging directory is created.
        payloads, manifest, _ = _payloads(definition_path, output)
        _require_open_directory_identity(parent_fd, parent_identity, "output parent")
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
        if _stat_at(parent_fd, output.name) is not None:
            raise SatelliteMosaicPreparationError("output appeared before staging")
        staging_name, tree_fd, tree_identity = _create_staging(
            parent_fd, output.name
        )
        try:
            _write_payloads(tree_fd, payloads)
            _freeze_staging(parent_fd, staging_name, tree_fd, tree_identity)
            _sync_parent(parent_fd, "frozen staging parent fsync")
            staging_path = parent_path / staging_name
            validated = validate_satellite_mosaic_preparation(
                staging_path, definition_path=definition_path
            )
            if validated != manifest:
                raise SatelliteMosaicPreparationError(
                    "frozen staging validation returned a differing manifest"
                )
            _require_open_directory_identity(tree_fd, tree_identity, "staging")
            _require_directory_identity_at(
                parent_fd, staging_name, tree_identity, "staging"
            )
            _require_directory_path_identity(parent_path, parent_identity, "output parent")
            if _stat_at(parent_fd, output.name) is not None:
                raise SatelliteMosaicPreparationError("output appeared before publication")
            _rename_noreplace(parent_fd, staging_name, output.name)
            _require_directory_identity_at(
                parent_fd, output.name, tree_identity, "published target"
            )
            if _stat_at(parent_fd, staging_name) is not None:
                raise SatelliteMosaicPreparationError(
                    "staging name remains after publication rename"
                )
            _sync_parent(parent_fd, "publication parent fsync")
            _require_open_directory_identity(tree_fd, tree_identity, "published target")
            _require_directory_identity_at(
                parent_fd, output.name, tree_identity, "published target"
            )
            _require_directory_path_identity(parent_path, parent_identity, "output parent")
            return manifest
        except BaseException as primary_error:
            _recover_publication_failure(
                primary_error=primary_error,
                parent_path=parent_path,
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                staging_name=staging_name,
                target_name=output.name,
                tree_fd=tree_fd,
                tree_identity=tree_identity,
            )
            raise AssertionError("unreachable")
    finally:
        if tree_fd is not None:
            os.close(tree_fd)
        os.close(parent_fd)
