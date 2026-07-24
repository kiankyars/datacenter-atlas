"""Reselect unique complete singleton tiles from six frozen v57 bindings.

This successor is deliberately narrower than catalog reselection.  It examines
only the two item identities already selected and hash-bound in each epoch of
the immutable v1 ``multi_tile_ready`` rows.  It never discovers, ranks, or
substitutes another archived catalog candidate.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .satellite_change import REQUIRED_ASSETS, canonical_sha256, mgrs_tile
from .satellite_change_mosaic import (
    ALGORITHM_VERSION,
    ItemBinding,
    SentinelMosaicContractError,
    epoch_metadata_coverage,
    grid_from_item,
    parse_rfc3339_instant,
    select_bound_items,
)
from . import satellite_change_preparation_v1 as predecessor


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = Path(
    "sources/satellite-change-singleton-preparation-2026-07-20-"
    "open-seed-v57-active-v2.json"
)
OUTPUT_PATH = Path(
    "satellite_change_preparation/"
    "2026-07-20-open-seed-v57-active-singleton-v2"
)
DEFINITION_FORMAT = (
    "datacenter-atlas-satellite-change-singleton-preparation-definition-v2"
)
RELEASE_FORMAT = "datacenter-atlas-satellite-change-singleton-preparation-v2"
SCHEMA_VERSION = 2
PREPARATION_ID = (
    "2026-07-20-open-seed-v57-active-singleton-reselection-preparation-v2"
)
READY_FILENAME = "singleton-ready.jsonl"
RELEASE_FILES = frozenset(
    {
        "README.md",
        "manifest.json",
        "manifest.sha256",
        READY_FILENAME,
        "source-inventory.json",
        "summary.json",
        "technical-incident.json",
    }
)
EXPECTED_QUEUE_IDS = (
    "satq-54c6402eb93d14f1ea754e66",
    "satq-cef871428da247c3ecfadec6",
    "satq-96fca962064e09f0dbafa93b",
    "satq-78500568b1f6227789ae36f4",
    "satq-fb6b6f815dad079c059cf412",
    "satq-0ffe3647dc32ee25ef77eab7",
)
EXPECTED_QUEUE_POSITIONS = (3, 13, 30, 38, 46, 87)


class SatelliteChangeSingletonPreparationV2Error(ValueError):
    """Raised when frozen lineage or unique-singleton selection drifts."""


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
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} is not UTF-8"
        ) from error

    def reject_constant(value: str) -> None:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} is not valid JSON"
        ) from error


def _regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} is not a regular file: {path}"
        )
    return path.read_bytes()


def _pin(path: Path) -> dict[str, Any]:
    raw = _regular(path, "pinned file")
    return {
        "bytes": len(raw),
        "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
        "sha256": _sha(raw),
    }


def _path(relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise SatelliteChangeSingletonPreparationV2Error(f"{label} path is invalid")
    parts = Path(relative).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} path is not canonical"
        )
    result = ROOT.joinpath(*parts)
    cursor = ROOT
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise SatelliteChangeSingletonPreparationV2Error(
                f"{label} path traverses a symlink"
            )
    return result


def _validate_pin(value: Any, label: str) -> Path:
    if not isinstance(value, Mapping) or set(value) != {
        "bytes",
        "mode",
        "path",
        "sha256",
    }:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} pin schema is invalid"
        )
    path = _path(value["path"], label)
    if {"path": value["path"], **_pin(path)} != dict(value):
        raise SatelliteChangeSingletonPreparationV2Error(f"{label} pin mismatch")
    return path


def _rfc3339(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} must be RFC 3339 text"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{label} lacks a timezone"
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _definition(path: str | Path) -> tuple[dict[str, Any], Path]:
    definition_path = Path(path)
    raw = _regular(definition_path, "singleton preparation definition")
    value = _strict_json(raw, "singleton preparation definition")
    required = {
        "builder",
        "claim_constraints",
        "expected_rebindings",
        "format",
        "generated_at",
        "preparation_id",
        "preserved_lineage",
        "processor",
        "runtime",
        "schema_version",
        "selection_policy",
        "source_preparation",
        "technical_incident",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation definition schema is invalid"
        )
    if (
        value["format"] != DEFINITION_FORMAT
        or value["schema_version"] != SCHEMA_VERSION
        or value["preparation_id"] != PREPARATION_ID
        or value["processor"].get("algorithm_version") != ALGORITHM_VERSION
    ):
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation definition identity changed"
        )
    _rfc3339(value["generated_at"], "definition generated_at")
    policy = value["selection_policy"]
    if policy != {
        "candidate_scope": "v1_prepared_selected_item_bindings_only",
        "catalog_rediscovery": False,
        "catalog_reranking": False,
        "complete_all_required_assets": list(REQUIRED_ASSETS),
        "cross_epoch_equal_grids": list(REQUIRED_ASSETS),
        "cross_epoch_same_mgrs_tile": True,
        "require_unique_complete_pair": True,
        "swir16_interpolation_halo_pixels": 1,
    }:
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton selection policy changed"
        )
    for group in ("builder", "preserved_lineage"):
        records = value[group]
        if not isinstance(records, Mapping) or not records:
            raise SatelliteChangeSingletonPreparationV2Error(
                f"definition {group} is invalid"
            )
        for name, record in records.items():
            _validate_pin(record, f"{group}/{name}")
    processor = value["processor"]
    if not isinstance(processor, Mapping) or set(processor) != {
        "algorithm_version",
        "cli",
        "minimum_component_area_m2",
        "module",
    }:
        raise SatelliteChangeSingletonPreparationV2Error(
            "processor definition is invalid"
        )
    _validate_pin(processor["cli"], "processor CLI")
    _validate_pin(processor["module"], "processor module")
    if processor["minimum_component_area_m2"] != 5000:
        raise SatelliteChangeSingletonPreparationV2Error(
            "processor component threshold changed"
        )
    expected = value["expected_rebindings"]
    if (
        not isinstance(expected, list)
        or len(expected) != 6
        or tuple(row.get("queue_id") for row in expected) != EXPECTED_QUEUE_IDS
        or tuple(row.get("queue_position") for row in expected)
        != EXPECTED_QUEUE_POSITIONS
    ):
        raise SatelliteChangeSingletonPreparationV2Error(
            "expected singleton rebindings changed"
        )
    return value, definition_path


def _predecessor_rows(
    definition: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    source = definition["source_preparation"]
    if not isinstance(source, Mapping) or set(source) != {
        "closed_tree",
        "definition",
        "directory",
        "manifest",
        "ready_partition",
    }:
        raise SatelliteChangeSingletonPreparationV2Error(
            "source preparation definition is invalid"
        )
    directory = _path(source["directory"], "source preparation")
    source_definition = _validate_pin(
        source["definition"], "source preparation definition"
    )
    manifest_path = _validate_pin(source["manifest"], "source preparation manifest")
    ready_path = _validate_pin(
        source["ready_partition"], "source preparation ready partition"
    )
    try:
        manifest = predecessor.validate_satellite_change_preparation_v1(
            directory, definition_path=source_definition
        )
        tree = predecessor._tree_inventory(directory)
    except Exception as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"source preparation validation failed: {error}"
        ) from error
    if tree != source["closed_tree"] or manifest_path != directory / "manifest.json":
        raise SatelliteChangeSingletonPreparationV2Error(
            "source preparation closed lineage changed"
        )
    if ready_path != directory / "multi-tile-ready.jsonl":
        raise SatelliteChangeSingletonPreparationV2Error(
            "source preparation partition path changed"
        )
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(ready_path.read_bytes().splitlines(), 1):
        value = _strict_json(line, f"source row {line_number}")
        if not isinstance(value, dict):
            raise SatelliteChangeSingletonPreparationV2Error(
                f"source row {line_number} is not an object"
            )
        rows.append(value)
    if (
        tuple(row.get("queue_id") for row in rows) != EXPECTED_QUEUE_IDS
        or tuple(row.get("queue_position") for row in rows)
        != EXPECTED_QUEUE_POSITIONS
    ):
        raise SatelliteChangeSingletonPreparationV2Error(
            "source six-job selection changed"
        )
    return rows, manifest, directory


def _response(row: Mapping[str, Any], epoch: str) -> Mapping[str, Any]:
    record = row["epochs"][epoch]["archived_stac_response"]
    path = _path(record["path"], f"{row['queue_id']} {epoch} STAC response")
    raw = _regular(path, f"{row['queue_id']} {epoch} STAC response")
    if len(raw) != record["bytes"] or _sha(raw) != record["sha256"]:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{row['queue_id']} {epoch} STAC response pin changed"
        )
    value = _strict_json(raw, f"{row['queue_id']} {epoch} STAC response")
    if not isinstance(value, Mapping):
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{row['queue_id']} {epoch} STAC response is not an object"
        )
    return value


def _features(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    values = (
        [document]
        if document.get("type") == "Feature"
        else document.get("features")
    )
    if not isinstance(values, list) or any(not isinstance(row, Mapping) for row in values):
        raise SatelliteChangeSingletonPreparationV2Error(
            "archived STAC response feature inventory is invalid"
        )
    result: dict[str, Mapping[str, Any]] = {}
    for item in values:
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in result:
            raise SatelliteChangeSingletonPreparationV2Error(
                "archived STAC response item IDs are invalid"
            )
        result[item_id] = item
    return result


def _coverage_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    assets = value.get("assets")
    if not isinstance(assets, Mapping) or set(assets) != set(REQUIRED_ASSETS):
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton coverage asset inventory changed"
        )
    for asset_name in REQUIRED_ASSETS:
        record = assets[asset_name]
        expected_halo = 1 if asset_name == "swir16" else 0
        if record.get("interpolation_halo_pixels") != expected_halo:
            raise SatelliteChangeSingletonPreparationV2Error(
                f"singleton {asset_name} interpolation halo changed"
            )
    return {"assets": dict(assets), "complete": bool(value.get("complete"))}


def _candidate(
    *,
    document: Mapping[str, Any],
    original_primary: ItemBinding,
    prepared: Mapping[str, Any],
    bbox: Sequence[float],
    transform_bounds: Callable[..., Sequence[float]],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    item_id = prepared.get("id")
    digest = prepared.get("stac_item_sha256")
    role = prepared.get("role")
    if role not in {"primary", "companion"}:
        raise SatelliteChangeSingletonPreparationV2Error(
            "prepared candidate role changed"
        )
    try:
        binding = ItemBinding(item_id, digest)
        if binding != original_primary:
            select_bound_items(document, original_primary, (binding,))
        item, singleton = select_bound_items(document, binding, ())
    except (SentinelMosaicContractError, TypeError) as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"prepared candidate binding or acquisition is invalid: {item_id}"
        ) from error
    if len(singleton) != 1 or canonical_sha256(item) != digest:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"prepared candidate hash changed: {item_id}"
        )
    try:
        coverage = epoch_metadata_coverage(item, singleton, bbox, transform_bounds)
    except SentinelMosaicContractError as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"prepared candidate grid is invalid: {item_id}"
        ) from error
    acquisition = item["properties"]
    record = {
        "binding": binding.as_dict(),
        "complete": bool(coverage["complete"]),
        "coverage": _coverage_summary(coverage),
        "datetime_utc": parse_rfc3339_instant(
            acquisition.get("datetime"), f"{item_id} datetime"
        ).isoformat().replace("+00:00", "Z"),
        "mgrs_tile": mgrs_tile(item),
        "prior_prepared_role": role,
        "same_acquisition_as_original_primary": True,
    }
    return record, item


def derive_singleton_row_v2(
    source_row: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    *,
    transform_bounds: Callable[..., Sequence[float]],
    processor: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive one row from only its two already prepared item bindings per epoch."""

    queue_id = source_row.get("queue_id")
    bbox = source_row.get("aoi_bbox_wgs84")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{queue_id} AOI changed"
        )
    epoch_records: dict[str, dict[str, Any]] = {}
    epoch_items: dict[str, dict[str, Mapping[str, Any]]] = {}
    for epoch in ("baseline", "current"):
        source_epoch = source_row["epochs"][epoch]
        prepared_items = source_epoch.get("selected_item_asset_bindings")
        if (
            not isinstance(prepared_items, list)
            or len(prepared_items) != 2
            or {row.get("role") for row in prepared_items}
            != {"primary", "companion"}
        ):
            raise SatelliteChangeSingletonPreparationV2Error(
                f"{queue_id} {epoch} prepared binding inventory changed"
            )
        original = next(row for row in prepared_items if row["role"] == "primary")
        original_binding = ItemBinding(
            original["id"], original["stac_item_sha256"]
        )
        candidates: list[dict[str, Any]] = []
        items: dict[str, Mapping[str, Any]] = {}
        for prepared in prepared_items:
            record, item = _candidate(
                document=documents[epoch],
                original_primary=original_binding,
                prepared=prepared,
                bbox=bbox,
                transform_bounds=transform_bounds,
            )
            candidates.append(record)
            items[record["binding"]["id"]] = item
        candidates.sort(key=lambda row: row["binding"]["id"])
        epoch_records[epoch] = {
            "archived_stac_response": dict(
                source_epoch["archived_stac_response"]
            ),
            "candidate_scope": "v1_prepared_selected_item_bindings_only",
            "original_primary": dict(source_epoch["primary"]),
            "prepared_binding_count": len(prepared_items),
            "singleton_candidates": candidates,
        }
        epoch_items[epoch] = items

    pairs: list[dict[str, Any]] = []
    for baseline in epoch_records["baseline"]["singleton_candidates"]:
        if not baseline["complete"]:
            continue
        baseline_item = epoch_items["baseline"][baseline["binding"]["id"]]
        for current in epoch_records["current"]["singleton_candidates"]:
            if not current["complete"]:
                continue
            current_item = epoch_items["current"][current["binding"]["id"]]
            same_tile = baseline["mgrs_tile"] == current["mgrs_tile"]
            equal_assets = {
                asset_name: grid_from_item(baseline_item, asset_name)
                == grid_from_item(current_item, asset_name)
                for asset_name in REQUIRED_ASSETS
            }
            ordered = parse_rfc3339_instant(
                baseline_item["properties"].get("datetime"),
                "baseline singleton datetime",
            ) < parse_rfc3339_instant(
                current_item["properties"].get("datetime"),
                "current singleton datetime",
            )
            pairs.append(
                {
                    "baseline": dict(baseline["binding"]),
                    "baseline_prior_prepared_role": baseline[
                        "prior_prepared_role"
                    ],
                    "baseline_precedes_current": ordered,
                    "current": dict(current["binding"]),
                    "current_prior_prepared_role": current[
                        "prior_prepared_role"
                    ],
                    "equal_grids_by_asset": equal_assets,
                    "mgrs_tile": baseline["mgrs_tile"] if same_tile else None,
                    "same_mgrs_tile": same_tile,
                    "valid": ordered and same_tile and all(equal_assets.values()),
                }
            )
    valid_pairs = [pair for pair in pairs if pair["valid"]]
    if len(valid_pairs) != 1:
        reason = "ambiguous" if len(valid_pairs) > 1 else "missing"
        raise SatelliteChangeSingletonPreparationV2Error(
            f"{queue_id} unique cross-epoch complete singleton pair is {reason}"
        )
    selected = valid_pairs[0]
    for epoch in ("baseline", "current"):
        binding = selected[epoch]
        candidate = next(
            row
            for row in epoch_records[epoch]["singleton_candidates"]
            if row["binding"] == binding
        )
        epoch_records[epoch].update(
            {
                "selected_companions": [],
                "selected_coverage": candidate["coverage"],
                "selected_primary": {
                    **dict(binding),
                    "mgrs_tile": candidate["mgrs_tile"],
                    "prior_prepared_role": candidate["prior_prepared_role"],
                },
            }
        )
    arguments: list[str] = []
    for epoch in ("baseline", "current"):
        record = epoch_records[epoch]
        arguments.extend(
            [
                f"--{epoch}-stac",
                record["archived_stac_response"]["path"],
                f"--{epoch}-stac-sha256",
                record["archived_stac_response"]["sha256"],
                f"--{epoch}-primary",
                (
                    f"{record['selected_primary']['id']}="
                    f"{record['selected_primary']['stac_item_sha256']}"
                ),
            ]
        )
    arguments.extend(
        [
            "--bbox",
            ",".join(predecessor._number_text(value) for value in bbox),
            "--entity-id",
            source_row["entity"]["id"],
            "--entity-name",
            source_row["entity"]["name"],
            "--output-dir",
            "{job_output_dir}",
            "--minimum-component-area-m2",
            "5000",
        ]
    )
    source_row_hash = _sha(
        (
            json.dumps(
                source_row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    return {
        "aoi_bbox_wgs84": list(bbox),
        "catalog_artifacts": dict(source_row["catalog_artifacts"]),
        "claim_constraints": dict(source_row["claim_constraints"]),
        "cross_epoch_singleton_pairs": pairs,
        "entity": dict(source_row["entity"]),
        "epochs": epoch_records,
        "execution": {
            "arguments": arguments,
            "cli": processor["cli"]["path"],
            "runtime": dict(source_row["execution"]["runtime"]),
        },
        "network_requests": 0,
        "preparation_only": True,
        "processor": dict(processor),
        "queue_id": queue_id,
        "queue_position": source_row["queue_position"],
        "raster_analysis_executed": False,
        "schema_version": SCHEMA_VERSION,
        "selected_pair": selected,
        "selection_scope": "v1_prepared_selected_item_bindings_only",
        "source_prepared_row_sha256": source_row_hash,
        "state": "singleton_ready",
    }


def _technical_incident(definition: Mapping[str, Any]) -> dict[str, Any]:
    value = definition["technical_incident"]
    if not isinstance(value, Mapping) or set(value) != {
        "classification",
        "directory",
        "manifest",
        "retention",
    }:
        raise SatelliteChangeSingletonPreparationV2Error(
            "technical incident definition is invalid"
        )
    manifest_path = _validate_pin(value["manifest"], "technical incident manifest")
    directory = _path(value["directory"], "technical incident directory")
    if manifest_path.parent != directory:
        raise SatelliteChangeSingletonPreparationV2Error(
            "technical incident path changed"
        )
    document = _strict_json(manifest_path.read_bytes(), "technical incident manifest")
    if (
        not isinstance(document, Mapping)
        or document.get("pipeline") != "satellite_review_change_mosaic_batch_v1"
        or document.get("state") != "incomplete"
        or document.get("summary", {}).get("jobs_failed") != 6
        or document.get("summary", {}).get("jobs_completed") != 0
    ):
        raise SatelliteChangeSingletonPreparationV2Error(
            "technical incident terminal facts changed"
        )
    errors = {
        str(job["failures"][0]["error"])
        for job in document["jobs"].values()
        if job.get("failures")
    }
    if len(errors) != 6 or any(
        "mosaic has conflicting nonzero overlap" not in error for error in errors
    ):
        raise SatelliteChangeSingletonPreparationV2Error(
            "technical incident failure class changed"
        )
    return {
        "classification": value["classification"],
        "directory": value["directory"],
        "failure_kind": "native_nonzero_overlap_disagreement",
        "jobs_completed": 0,
        "jobs_failed": 6,
        "manifest": dict(value["manifest"]),
        "retention": value["retention"],
        "retry_semantics": "successor_selection_not_retry",
    }


def _payloads(definition_path: str | Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    definition, resolved_definition = _definition(definition_path)
    source_rows, source_manifest, source_directory = _predecessor_rows(definition)
    incident = _technical_incident(definition)
    try:
        from rasterio.warp import transform_bounds
    except ImportError as error:
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation requires the pinned rasterio runtime"
        ) from error
    rows = [
        derive_singleton_row_v2(
            row,
            {epoch: _response(row, epoch) for epoch in ("baseline", "current")},
            transform_bounds=transform_bounds,
            processor=definition["processor"],
        )
        for row in source_rows
    ]
    expected = definition["expected_rebindings"]
    actual = [
        {
            "baseline": row["epochs"]["baseline"]["selected_primary"],
            "current": row["epochs"]["current"]["selected_primary"],
            "queue_id": row["queue_id"],
            "queue_position": row["queue_position"],
        }
        for row in rows
    ]
    if actual != expected:
        raise SatelliteChangeSingletonPreparationV2Error(
            "derived singleton rebindings differ from the explicit definition pins"
        )
    ready_raw = _canonical_jsonl(rows)
    summary = {
        "candidate_bindings_assessed": sum(
            len(epoch["singleton_candidates"])
            for row in rows
            for epoch in row["epochs"].values()
        ),
        "catalog_rediscoveries": 0,
        "catalog_rerankings": 0,
        "jobs_ready": len(rows),
        "prior_companions_rebound_as_primary": sum(
            row["epochs"][epoch]["selected_primary"]["prior_prepared_role"]
            == "companion"
            for row in rows
            for epoch in ("baseline", "current")
        ),
        "source_multi_tile_rows": len(source_rows),
        "unique_singleton_pairs": len(rows),
    }
    source_inventory = {
        "definition": {
            "path": resolved_definition.relative_to(ROOT).as_posix(),
            **_pin(resolved_definition),
        },
        "preserved_lineage": definition["preserved_lineage"],
        "source_preparation": {
            "directory": source_directory.relative_to(ROOT).as_posix(),
            "manifest": {
                "path": (
                    source_directory / "manifest.json"
                ).relative_to(ROOT).as_posix(),
                **_pin(source_directory / "manifest.json"),
            },
            "preparation_id": source_manifest["preparation_id"],
            "ready_partition": definition["source_preparation"]["ready_partition"],
        },
        "technical_incident": incident,
    }
    readme = (
        "# Frozen singleton reselection for six v57 boundary jobs\n\n"
        "This immutable metadata-only successor chooses only among each v1 row's "
        "two already selected and canonical-hash-bound same-acquisition items. It "
        "does not reopen the archived candidate set, discover another item, or "
        "rerank catalog candidates. A unique companion-tile pair covers both epochs "
        "for all six required assets, including the one-pixel SWIR interpolation "
        "halo, and is rebound as the primary with no companion flags.\n\n"
        "The failed v1 run is retained as a technical incident. This preparation "
        "opens no imagery and creates no data-centre identity, lifecycle, status, "
        "capacity, power, energy, PUE, workload, or parity claim.\n"
    ).encode("utf-8")
    payloads = {
        "README.md": readme,
        READY_FILENAME: ready_raw,
        "source-inventory.json": _canonical_json(source_inventory),
        "summary.json": _canonical_json(summary),
        "technical-incident.json": _canonical_json(incident),
    }
    manifest = {
        "claim_constraints": definition["claim_constraints"],
        "definition": source_inventory["definition"],
        "files": {
            name: {"bytes": len(raw), "sha256": _sha(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": RELEASE_FORMAT,
        "generated_at": definition["generated_at"],
        "preparation_id": PREPARATION_ID,
        "processor": definition["processor"],
        "runtime": definition["runtime"],
        "schema_version": SCHEMA_VERSION,
        "selection_policy": definition["selection_policy"],
        "source_preparation": source_inventory["source_preparation"],
        "summary": summary,
        "technical_incident": incident,
    }
    manifest_raw = _canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return payloads, manifest


def validate_satellite_change_singleton_preparation_v2(
    output_directory: str | Path,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    output = Path(output_directory)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangeSingletonPreparationV2Error(
            f"singleton preparation output is not a regular directory: {output}"
        )
    if {path.name for path in output.iterdir()} != RELEASE_FILES:
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation output inventory drift"
        )
    expected, manifest = _payloads(definition_path)
    for filename in sorted(RELEASE_FILES):
        path = output / filename
        if _regular(path, f"singleton preparation artifact {filename}") != expected[
            filename
        ]:
            raise SatelliteChangeSingletonPreparationV2Error(
                f"singleton preparation artifact differs: {filename}"
            )
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation directory is not frozen"
        )
    for path in output.iterdir():
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise SatelliteChangeSingletonPreparationV2Error(
                f"singleton preparation artifact is not frozen: {path.name}"
            )
    return manifest


def write_satellite_change_singleton_preparation_v2(
    output_directory: str | Path = ROOT / OUTPUT_PATH,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise SatelliteChangeSingletonPreparationV2Error(
            f"refusing to replace singleton preparation output: {output}"
        )
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteChangeSingletonPreparationV2Error(
            "singleton preparation output parent is not a regular directory"
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
        validate_satellite_change_singleton_preparation_v2(
            stage, definition_path=definition_path
        )
        if output.exists() or output.is_symlink():
            raise SatelliteChangeSingletonPreparationV2Error(
                "singleton preparation output appeared during publication"
            )
        os.rename(stage, output)
        descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if stage.exists() and not stage.is_symlink():
            for child in stage.iterdir():
                child.chmod(0o600)
            stage.chmod(0o700)
            shutil.rmtree(stage)
    return validate_satellite_change_singleton_preparation_v2(
        output, definition_path=definition_path
    )
