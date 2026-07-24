"""Resumable candidate-independent integration of blind-frame auxiliaries.

The production geometry adapter emits four canonical, hash-pinned JSONL streams
in EPSG:6933. This module aggregates those streams without loading them into
memory, conserves every extensive GHS-BUILT-S source-cell total exactly at one
square-millimetre resolution, preserves tri-state unknowns, and publishes an
immutable tile-signal bundle. Production mode validates the frozen GHSL cache
and frozen OSM derivative before touching the work database.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).resolve()
CLI_PATH = PROJECT_ROOT / "scripts" / "build_blind_tile_auxiliary_integration.py"

SCHEMA_VERSION = 1
DEFINITION_FORMAT = "datacenter-atlas-blind-tile-auxiliary-integration-definition-v1"
BUNDLE_FORMAT = "datacenter-atlas-blind-tile-auxiliary-integration-bundle-v1"
PIPELINE = "blind_tile_auxiliary_integration"
OUTPUT_FILENAME = "tile-auxiliary.jsonl"
COVERAGE_FILENAME = "coverage.json"
DEFINITION_FILENAME = "definition.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_SHA_FILENAME = "manifest.sha256"
BUNDLE_PAYLOAD_FILES = frozenset(
    {
        OUTPUT_FILENAME,
        COVERAGE_FILENAME,
        DEFINITION_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)
BUNDLE_FILES = BUNDLE_PAYLOAD_FILES | {MANIFEST_FILENAME, MANIFEST_SHA_FILENAME}

INPUT_ROLES = ("tiles", "built_cells", "smod_cells", "osm_tiles")
CRS = "EPSG:6933"
AREA_UNIT = "square_millimetre"
AREA_UNITS_PER_M2 = 1_000_000
BUILT_THRESHOLD_NUMERATOR = 1
BUILT_THRESHOLD_DENOMINATOR = 200
INDUSTRIAL_THRESHOLD_AREA_MM2 = 10_000 * AREA_UNITS_PER_M2
GRID_THRESHOLD_DISTANCE_MM = 5_000 * 1_000
GRID_THRESHOLD_VOLTAGE_V = 110_000
SMOD_VALID_CODES = frozenset({10, 11, 12, 13, 21, 22, 23, 30})
SMOD_URBAN_CODES = frozenset({21, 22, 23, 30})

GHSL_CACHE_BASENAME = "ghsl-r2023a-2020-1km"
GHSL_FROZEN_FILES = {
    "GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000.copyright.txt": (
        540,
        "f20723519a580fb35b3499870f0b1baea54f483195105416e547f0014f1610d2",
    ),
    "GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000_V1_0.zip": (
        152_527_564,
        "5ab899936b560f1b803778fffe6912a28de50036e2bfa0338d55ed34e502d8a2",
    ),
    "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000.copyright.txt": (
        540,
        "f20723519a580fb35b3499870f0b1baea54f483195105416e547f0014f1610d2",
    ),
    "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip": (
        35_853_870,
        "5a81c3827c9bbc9109159b4c3f92ac7722705944e43038219f142b410431a852",
    ),
    "README.md": (
        1_753,
        "54390f19dd4f28135f534fcc11d3500e4e0773f220441f5cf7597452bcc91610",
    ),
    "fetch-manifest.json": (
        10_544,
        "07bfcabcae06aa14e5b53e5cf9f73c4430e1d7902463df1f6ca6f8c8c2fd7b31",
    ),
    "raster-metadata.json": (
        3_532,
        "1343f3199e1ee42d29be326bc2e593ee600b1c53e67875c8675880efacf5cf99",
    ),
}
OSM_DERIVATIVE_BASENAME = "osm-blind-tile-auxiliary-260713-v3"
PRODUCTION_GEOMETRY_PRODUCER_IMPLEMENTED = False
PRODUCTION_GEOMETRY_PRODUCER_BLOCKER = (
    "production normalized geometry producer bytes and independent source-to-stream "
    "validation are not implemented; production auxiliary builds remain disabled"
)

NORMALIZED_INPUT_SOURCE_BINDINGS = {
    "tiles": {
        "allowed_raw_sources": ["natural_earth_non_antarctic_land"],
        "candidate_derived_sources_allowed": False,
        "role": "positive tile-land intersections and land denominators",
    },
    "built_cells": {
        "allowed_raw_sources": [
            "ghsl_r2023a_2020_1km_built_s",
            "natural_earth_non_antarctic_land",
        ],
        "candidate_derived_sources_allowed": False,
        "role": "extensive BUILT source values and exact tile-land fragments",
    },
    "smod_cells": {
        "allowed_raw_sources": [
            "ghsl_r2023a_2020_1km_smod_l2",
            "natural_earth_non_antarctic_land",
        ],
        "candidate_derived_sources_allowed": False,
        "role": "categorical SMOD source values and exact tile-land fragments",
    },
    "osm_tiles": {
        "allowed_raw_sources": [
            "frozen_stable_osm_blind_tile_derivative",
            "natural_earth_non_antarctic_land",
        ],
        "candidate_derived_sources_allowed": False,
        "role": "stable industrial union and >=110 kV grid tile observations",
    },
}

SEMANTIC_CONTRACT = {
    "area_crs": CRS,
    "area_unit": AREA_UNIT,
    "built": {
        "allocation": "source built m2 converted to integer square-mm and allocated by source-cell-land fragment area using deterministic largest remainder",
        "bilinear_interpolation_allowed": False,
        "extensive_quantity": True,
        "false_requires_full_valid_tile_land_coverage": True,
        "nodata_or_missing_coverage": "unknown_not_zero",
        "per_source_cell_conservation": "exact_integer_square_mm",
        "threshold_fraction_of_non_antarctic_tile_land": {
            "denominator": BUILT_THRESHOLD_DENOMINATOR,
            "numerator": BUILT_THRESHOLD_NUMERATOR,
        },
    },
    "grid": {
        "false_requires_complete_osm_tile_processing": True,
        "maximum_distance_mm": GRID_THRESHOLD_DISTANCE_MM,
        "minimum_voltage_v": GRID_THRESHOLD_VOLTAGE_V,
        "unknown_when_processing_incomplete_without_positive_lower_bound": True,
    },
    "industrial": {
        "false_requires_complete_osm_tile_processing": True,
        "minimum_union_intersection_area_mm2": INDUSTRIAL_THRESHOLD_AREA_MM2,
        "union_required_before_tile_intersection": True,
        "unknown_when_processing_incomplete_below_threshold": True,
    },
    "land_denominator": "positive tile intersection with pinned non-Antarctic Natural Earth land union",
    "smod": {
        "categorical": True,
        "false_requires_full_valid_tile_land_coverage": True,
        "nodata_or_missing_coverage": "unknown_not_zero",
        "resampling": "none_for_intersections_or_nearest_neighbour_only",
        "true_rule": "positive urban-coded tile-land intersection area",
        "urban_codes": sorted(SMOD_URBAN_CODES),
    },
    "unknown_signal_classification_policy": "unknown_is_false_only_for_lower-stratum_assignment_and_remains_explicit",
}

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_TILE_ID_RE = re.compile(r"e6933-4km-x[+-][0-9]{6}-y[+-][0-9]{6}")
_SOURCE_CELL_ID_RE = re.compile(r"[a-z0-9][a-z0-9:._+-]{0,127}")
_FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"construction[-_ /]master", re.IGNORECASE),
    re.compile(r"construction[-_ /]map", re.IGNORECASE),
    re.compile(r"candidate[-_ /]fusion", re.IGNORECASE),
    re.compile(r"satellite[-_ /](?:review[-_ /])?queue", re.IGNORECASE),
    re.compile(r"osm[-_ /]structural[-_ /]shortlist", re.IGNORECASE),
    re.compile(r"(?:^|[/\\])releases(?:$|[/\\])", re.IGNORECASE),
)


class BlindTileAuxiliaryIntegrationError(ValueError):
    """Raised when normalized geometry, lineage, or state fails closed."""


Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _hash_file(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(16 * 1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _regular_file(path: Path, label: str) -> os.stat_result:
    if path.is_symlink():
        raise BlindTileAuxiliaryIntegrationError(f"{label} must not be a symlink")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise BlindTileAuxiliaryIntegrationError(f"{label} is missing: {path}") from error
    if not stat.S_ISREG(status.st_mode):
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be a regular file")
    return status


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BlindTileAuxiliaryIntegrationError(
            f"{label} must be a non-negative integer"
        )
    return value


def _exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise BlindTileAuxiliaryIntegrationError(f"{label} schema changed")


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BlindTileAuxiliaryIntegrationError(f"{label} is invalid") from error
    if parsed.tzinfo is None:
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be canonical UTC")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be canonical UTC")
    return value


def _checkpoint(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be a checkpoint")
    _exact_keys(value, {"bytes", "path", "sha256"}, label)
    if not isinstance(value["path"], str) or not value["path"]:
        raise BlindTileAuxiliaryIntegrationError(f"{label} path is invalid")
    _positive_integer(value["bytes"], f"{label} bytes")
    if not isinstance(value["sha256"], str) or _HASH_RE.fullmatch(value["sha256"]) is None:
        raise BlindTileAuxiliaryIntegrationError(f"{label} SHA-256 is invalid")
    _reject_forbidden_path(value["path"], label)
    return dict(value)


def _reject_forbidden_path(value: str, label: str) -> None:
    for pattern in _FORBIDDEN_PATH_PATTERNS:
        if pattern.search(value):
            raise BlindTileAuxiliaryIntegrationError(
                f"{label} contains a forbidden candidate-derived path"
            )


def _reject_existing_symlink_components(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            status = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(status.st_mode):
            raise BlindTileAuxiliaryIntegrationError(
                f"{label} contains a symlink component: {current}"
            )


def _reject_bound_path_symlinks(
    definition_path: Path, candidate: Path, label: str
) -> None:
    base = Path(os.path.abspath(definition_path.parent))
    _reject_existing_symlink_components(base, label)
    current = base
    for component in candidate.parts:
        if component in {"", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            status = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(status.st_mode):
            raise BlindTileAuxiliaryIntegrationError(
                f"{label} contains a symlink component: {current}"
            )


def _resolve_relative(definition_path: Path, raw_path: str, label: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be relative")
    _reject_bound_path_symlinks(definition_path, candidate, label)
    root = definition_path.parent.parent.resolve()
    resolved = (definition_path.parent / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise BlindTileAuxiliaryIntegrationError(f"{label} escapes the project root")
    _reject_forbidden_path(str(resolved), label)
    return resolved


def _code_checkpoint(path: Path) -> dict[str, Any]:
    return {"path": path.name, **_hash_file(path)}


def current_algorithm_checkpoints() -> dict[str, dict[str, Any]]:
    return {
        "cli": _code_checkpoint(CLI_PATH),
        "module": _code_checkpoint(MODULE_PATH),
    }


def runtime_record() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }


def _load_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _regular_file(path, label)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BlindTileAuxiliaryIntegrationError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be canonical JSON")
    return value, raw


def _validate_frozen_ghsl_cache(path: Path) -> dict[str, Any]:
    if path.name != GHSL_CACHE_BASENAME or path.is_symlink() or not path.is_dir():
        raise BlindTileAuxiliaryIntegrationError("GHSL cache path is not the pinned cache")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise BlindTileAuxiliaryIntegrationError("GHSL cache directory must be mode 0555")
    if {entry.name for entry in path.iterdir()} != set(GHSL_FROZEN_FILES):
        raise BlindTileAuxiliaryIntegrationError("GHSL cache inventory changed")
    files: dict[str, Any] = {}
    for name, (expected_bytes, expected_sha256) in GHSL_FROZEN_FILES.items():
        child = path / name
        status = _regular_file(child, f"GHSL {name}")
        if stat.S_IMODE(status.st_mode) != 0o444:
            raise BlindTileAuxiliaryIntegrationError("GHSL cache file mode changed")
        checkpoint = _hash_file(child)
        if checkpoint != {"bytes": expected_bytes, "sha256": expected_sha256}:
            raise BlindTileAuxiliaryIntegrationError(f"GHSL cache file changed: {name}")
        files[name] = checkpoint
    return {"directory": path.name, "files": files, "frozen": True}


def _validate_frozen_osm_derivative(path: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    if path.name != OSM_DERIVATIVE_BASENAME:
        raise BlindTileAuxiliaryIntegrationError("OSM derivative path is not the pinned lane")
    try:
        from . import osm_blind_tile_auxiliary_v3

        document = osm_blind_tile_auxiliary_v3.validate_bundle(
            path, deep_source_hash=False
        )
    except Exception as error:
        raise BlindTileAuxiliaryIntegrationError(
            f"OSM derivative did not pass frozen validation: {error}"
        ) from error
    manifest_path = path / osm_blind_tile_auxiliary_v3.MANIFEST_FILENAME
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if actual != expected_manifest_sha256:
        raise BlindTileAuxiliaryIntegrationError("OSM derivative manifest pin changed")
    final_statistics = document["selection_statistics"]["final"]
    return {
        "directory": path.name,
        "downstream_contract": document["downstream_contract"],
        "manifest_sha256": actual,
        "selected_objects": final_statistics["selected_objects"],
        "unresolved_geometry_objects": final_statistics[
            "unresolved_geometry_objects"
        ],
        "unresolved_with_bounds": final_statistics["unresolved_with_bounds"],
        "unresolved_without_bounds": final_statistics["unresolved_without_bounds"],
    }


def load_definition(
    path: str | Path, *, verify_external_sources: bool = True
) -> tuple[dict[str, Any], bytes, dict[str, Path]]:
    definition_path = Path(path)
    _reject_existing_symlink_components(
        definition_path, "integration definition path"
    )
    definition, raw = _load_json_object(definition_path, "integration definition")
    _exact_keys(
        definition,
        {
            "algorithm",
            "candidate_independent",
            "fixture_only",
            "format",
            "generated_at",
            "input_contract",
            "production_frame_built",
            "release_id",
            "schema_version",
            "semantic_contract",
            "source_lineage",
        },
        "integration definition",
    )
    if (
        definition["schema_version"] != SCHEMA_VERSION
        or definition["format"] != DEFINITION_FORMAT
        or definition["candidate_independent"] is not True
        or definition["production_frame_built"] is not False
        or not isinstance(definition["fixture_only"], bool)
        or not isinstance(definition["release_id"], str)
        or not definition["release_id"]
        or definition["semantic_contract"] != SEMANTIC_CONTRACT
    ):
        raise BlindTileAuxiliaryIntegrationError("integration definition identity changed")
    _timestamp(definition["generated_at"], "definition generated_at")
    if definition["algorithm"] != current_algorithm_checkpoints():
        raise BlindTileAuxiliaryIntegrationError("integration algorithm bytes changed")
    contract = definition["input_contract"]
    if not isinstance(contract, Mapping):
        raise BlindTileAuxiliaryIntegrationError("input_contract must be an object")
    _exact_keys(
        contract,
        {
            "area_crs",
            "area_unit",
            "canonical_jsonl",
            "inputs",
            "source_role_bindings",
            "stream_order",
        },
        "input_contract",
    )
    if (
        contract["area_crs"] != CRS
        or contract["area_unit"] != AREA_UNIT
        or contract["canonical_jsonl"] is not True
        or contract["stream_order"] != list(INPUT_ROLES)
        or contract["source_role_bindings"] != NORMALIZED_INPUT_SOURCE_BINDINGS
        or not isinstance(contract["inputs"], Mapping)
        or set(contract["inputs"]) != set(INPUT_ROLES)
    ):
        raise BlindTileAuxiliaryIntegrationError("normalized input contract changed")
    inputs: dict[str, Path] = {}
    for role in INPUT_ROLES:
        spec = _checkpoint(contract["inputs"][role], f"{role} input")
        if Path(spec["path"]).is_absolute():
            raise BlindTileAuxiliaryIntegrationError(f"{role} input must be relative")
        if verify_external_sources:
            resolved = _resolve_relative(
                definition_path, spec["path"], f"{role} input"
            )
            _regular_file(resolved, f"{role} input")
            if _hash_file(resolved) != {
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
            }:
                raise BlindTileAuxiliaryIntegrationError(
                    f"{role} input checkpoint changed"
                )
            inputs[role] = resolved
    lineage = definition["source_lineage"]
    if not isinstance(lineage, Mapping):
        raise BlindTileAuxiliaryIntegrationError("source_lineage must be an object")
    if definition["fixture_only"]:
        if lineage != {
            "mode": "synthetic_fixture",
            "production_sources_used": False,
        }:
            raise BlindTileAuxiliaryIntegrationError("fixture lineage changed")
    else:
        _exact_keys(
            lineage,
            {
                "ghsl_cache_path",
                "mode",
                "natural_earth_artifact",
                "osm_derivative_manifest_sha256",
                "osm_derivative_path",
                "production_sources_used",
            },
            "production source_lineage",
        )
        if lineage["mode"] != "frozen_production" or lineage["production_sources_used"] is not True:
            raise BlindTileAuxiliaryIntegrationError("production lineage mode changed")
        for key, label in (
            ("ghsl_cache_path", "GHSL cache"),
            ("osm_derivative_path", "OSM derivative"),
        ):
            raw_path = lineage[key]
            if not isinstance(raw_path, str) or not raw_path:
                raise BlindTileAuxiliaryIntegrationError(f"{label} path is invalid")
            if Path(raw_path).is_absolute():
                raise BlindTileAuxiliaryIntegrationError(f"{label} must be relative")
            _reject_forbidden_path(raw_path, label)
        osm_hash = lineage["osm_derivative_manifest_sha256"]
        if not isinstance(osm_hash, str) or _HASH_RE.fullmatch(osm_hash) is None:
            raise BlindTileAuxiliaryIntegrationError("OSM manifest SHA-256 is invalid")
        natural_earth = _checkpoint(
            lineage["natural_earth_artifact"], "Natural Earth artifact"
        )
        if Path(natural_earth["path"]).is_absolute():
            raise BlindTileAuxiliaryIntegrationError(
                "Natural Earth artifact must be relative"
            )
        if verify_external_sources:
            ghsl_path = _resolve_relative(
                definition_path, lineage["ghsl_cache_path"], "GHSL cache"
            )
            _validate_frozen_ghsl_cache(ghsl_path)
            osm_path = _resolve_relative(
                definition_path, lineage["osm_derivative_path"], "OSM derivative"
            )
            _validate_frozen_osm_derivative(osm_path, osm_hash)
            natural_path = _resolve_relative(
                definition_path, natural_earth["path"], "Natural Earth artifact"
            )
            if _hash_file(natural_path) != {
                "bytes": natural_earth["bytes"],
                "sha256": natural_earth["sha256"],
            }:
                raise BlindTileAuxiliaryIntegrationError(
                    "Natural Earth checkpoint changed"
                )
            if not PRODUCTION_GEOMETRY_PRODUCER_IMPLEMENTED:
                raise BlindTileAuxiliaryIntegrationError(
                    PRODUCTION_GEOMETRY_PRODUCER_BLOCKER
                )
    return definition, raw, inputs


def _connect_state(path: Path, definition_sha256: str) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise BlindTileAuxiliaryIntegrationError("work database path is unsafe")
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress (
            role TEXT PRIMARY KEY,
            input_bytes INTEGER NOT NULL,
            input_sha256 TEXT NOT NULL,
            byte_offset INTEGER NOT NULL,
            row_count INTEGER NOT NULL,
            completed INTEGER NOT NULL CHECK (completed IN (0, 1))
        );
        CREATE TABLE IF NOT EXISTS tiles (
            tile_id TEXT PRIMARY KEY,
            land_area_mm2 INTEGER NOT NULL,
            built_allocated_mm2 INTEGER NOT NULL DEFAULT 0,
            built_valid_area_mm2 INTEGER NOT NULL DEFAULT 0,
            built_nodata_area_mm2 INTEGER NOT NULL DEFAULT 0,
            smod_valid_area_mm2 INTEGER NOT NULL DEFAULT 0,
            smod_urban_area_mm2 INTEGER NOT NULL DEFAULT 0,
            smod_nodata_area_mm2 INTEGER NOT NULL DEFAULT 0,
            osm_seen INTEGER NOT NULL DEFAULT 0,
            osm_complete INTEGER,
            industrial_union_area_mm2 INTEGER,
            grid_min_distance_mm INTEGER,
            grid_max_voltage_v INTEGER
        );
        CREATE TABLE IF NOT EXISTS source_cells (
            role TEXT NOT NULL,
            source_cell_id TEXT NOT NULL,
            PRIMARY KEY (role, source_cell_id)
        );
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    existing = connection.execute(
        "SELECT value FROM metadata WHERE key='definition_sha256'"
    ).fetchone()
    if existing is None:
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('definition_sha256',?)",
            (definition_sha256,),
        )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
    elif existing[0] != definition_sha256:
        connection.close()
        raise BlindTileAuxiliaryIntegrationError(
            "work database belongs to another definition"
        )
    return connection


def _counter_add(connection: sqlite3.Connection, key: str, delta: int) -> None:
    row = connection.execute("SELECT value FROM counters WHERE key=?", (key,)).fetchone()
    value = (int(row[0]) if row else 0) + delta
    if row:
        connection.execute("UPDATE counters SET value=? WHERE key=?", (str(value), key))
    else:
        connection.execute("INSERT INTO counters(key,value) VALUES(?,?)", (key, str(value)))


def _parse_line(raw: bytes, role: str, row_number: int) -> dict[str, Any]:
    if len(raw) > 4 * 1024 * 1024 or not raw.endswith(b"\n"):
        raise BlindTileAuxiliaryIntegrationError(f"{role} row {row_number} framing changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BlindTileAuxiliaryIntegrationError(
            f"{role} row {row_number} is invalid JSON"
        ) from error
    if not isinstance(value, dict) or raw != canonical_line(value):
        raise BlindTileAuxiliaryIntegrationError(
            f"{role} row {row_number} must be canonical JSONL"
        )
    return value


def _tile_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _TILE_ID_RE.fullmatch(value) is None:
        raise BlindTileAuxiliaryIntegrationError(f"{label} tile_id is invalid")
    return value


def _fragments(value: Any, source_land_area_mm2: int, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise BlindTileAuxiliaryIntegrationError(f"{label} fragments must be non-empty")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, fragment in enumerate(value):
        if not isinstance(fragment, Mapping):
            raise BlindTileAuxiliaryIntegrationError(f"{label} fragment is invalid")
        _exact_keys(fragment, {"area_mm2", "tile_id"}, f"{label} fragment")
        tile = _tile_id(fragment["tile_id"], f"{label} fragment")
        area = _positive_integer(fragment["area_mm2"], f"{label} fragment area")
        if tile in seen:
            raise BlindTileAuxiliaryIntegrationError(f"{label} repeats a tile")
        seen.add(tile)
        result.append({"area_mm2": area, "tile_id": tile})
    if result != sorted(result, key=lambda row: row["tile_id"]):
        raise BlindTileAuxiliaryIntegrationError(f"{label} fragments must be sorted")
    if sum(row["area_mm2"] for row in result) != source_land_area_mm2:
        raise BlindTileAuxiliaryIntegrationError(
            f"{label} fragments do not exactly close the source-cell land area"
        )
    return result


def allocate_extensive_built_area(
    built_surface_m2: int, source_land_area_mm2: int, fragments: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Allocate one integer-m² source total exactly in integer square millimetres."""
    _nonnegative_integer(built_surface_m2, "built surface")
    denominator = _positive_integer(source_land_area_mm2, "source land area")
    if not fragments:
        raise BlindTileAuxiliaryIntegrationError(
            "built allocation fragments must be non-empty"
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fragment in fragments:
        if not isinstance(fragment, Mapping):
            raise BlindTileAuxiliaryIntegrationError(
                "built allocation fragment is invalid"
            )
        _exact_keys(
            fragment,
            {"area_mm2", "tile_id"},
            "built allocation fragment",
        )
        tile = _tile_id(fragment["tile_id"], "built allocation fragment")
        area = _positive_integer(
            fragment["area_mm2"], "built allocation fragment area"
        )
        if tile in seen:
            raise BlindTileAuxiliaryIntegrationError(
                "built allocation repeats a tile"
            )
        seen.add(tile)
        normalized.append({"area_mm2": area, "tile_id": tile})
    if normalized != sorted(normalized, key=lambda row: row["tile_id"]):
        raise BlindTileAuxiliaryIntegrationError(
            "built allocation fragments must be sorted"
        )
    if sum(row["area_mm2"] for row in normalized) != denominator:
        raise BlindTileAuxiliaryIntegrationError("built allocation fragments do not conserve area")
    total = built_surface_m2 * AREA_UNITS_PER_M2
    if total > denominator:
        raise BlindTileAuxiliaryIntegrationError(
            "built surface exceeds source-cell land area"
        )
    allocations: list[dict[str, Any]] = []
    for fragment in normalized:
        product = total * fragment["area_mm2"]
        quotient, remainder = divmod(product, denominator)
        allocations.append(
            {
                "allocated_area_mm2": quotient,
                "remainder": remainder,
                "tile_id": fragment["tile_id"],
            }
        )
    leftover = total - sum(row["allocated_area_mm2"] for row in allocations)
    if not 0 <= leftover < len(allocations):
        raise BlindTileAuxiliaryIntegrationError("built largest-remainder closure failed")
    ranked = sorted(
        range(len(allocations)),
        key=lambda index: (-allocations[index]["remainder"], allocations[index]["tile_id"]),
    )
    for index in ranked[:leftover]:
        allocations[index]["allocated_area_mm2"] += 1
    if sum(row["allocated_area_mm2"] for row in allocations) != total:
        raise BlindTileAuxiliaryIntegrationError("built allocation is not exactly conservative")
    return [
        {
            "allocated_area_mm2": row["allocated_area_mm2"],
            "tile_id": row["tile_id"],
        }
        for row in allocations
    ]


def _require_tile(connection: sqlite3.Connection, tile: str) -> int:
    row = connection.execute(
        "SELECT land_area_mm2 FROM tiles WHERE tile_id=?", (tile,)
    ).fetchone()
    if row is None:
        raise BlindTileAuxiliaryIntegrationError(f"fragment references unknown tile {tile}")
    return int(row[0])


def _ingest_tiles(connection: sqlite3.Connection, value: Mapping[str, Any]) -> None:
    _exact_keys(value, {"land_area_mm2", "tile_id"}, "tile row")
    tile = _tile_id(value["tile_id"], "tile row")
    area = _positive_integer(value["land_area_mm2"], "tile land area")
    if area > 16_000_000 * AREA_UNITS_PER_M2:
        raise BlindTileAuxiliaryIntegrationError("tile land area exceeds a 4 km tile")
    try:
        connection.execute(
            "INSERT INTO tiles(tile_id,land_area_mm2) VALUES(?,?)", (tile, area)
        )
    except sqlite3.IntegrityError as error:
        raise BlindTileAuxiliaryIntegrationError("tiles contain a duplicate tile_id") from error


def _source_cell_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SOURCE_CELL_ID_RE.fullmatch(value) is None:
        raise BlindTileAuxiliaryIntegrationError(f"{label} source_cell_id is invalid")
    return value


def _mark_source_cell(
    connection: sqlite3.Connection, role: str, source_cell_id: str
) -> None:
    try:
        connection.execute(
            "INSERT INTO source_cells(role,source_cell_id) VALUES(?,?)",
            (role, source_cell_id),
        )
    except sqlite3.IntegrityError as error:
        raise BlindTileAuxiliaryIntegrationError(
            f"{role} repeats source cell {source_cell_id}"
        ) from error


def _ingest_built(connection: sqlite3.Connection, value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {"built_surface_m2", "fragments", "source_cell_id", "source_land_area_mm2"},
        "BUILT row",
    )
    source_id = _source_cell_id(value["source_cell_id"], "BUILT row")
    source_area = _positive_integer(value["source_land_area_mm2"], "BUILT source land area")
    fragments = _fragments(value["fragments"], source_area, "BUILT row")
    _mark_source_cell(connection, "built_cells", source_id)
    built = value["built_surface_m2"]
    if built is None:
        for fragment in fragments:
            _require_tile(connection, fragment["tile_id"])
            connection.execute(
                "UPDATE tiles SET built_nodata_area_mm2=built_nodata_area_mm2+? WHERE tile_id=?",
                (fragment["area_mm2"], fragment["tile_id"]),
            )
        _counter_add(connection, "built_nodata_source_cells", 1)
        return
    _nonnegative_integer(built, "BUILT source value")
    if built > 1_000_000:
        raise BlindTileAuxiliaryIntegrationError("BUILT value exceeds one 1 km cell")
    if built * AREA_UNITS_PER_M2 > source_area:
        raise BlindTileAuxiliaryIntegrationError(
            "BUILT value exceeds source-cell land area"
        )
    allocations = allocate_extensive_built_area(built, source_area, fragments)
    allocation_by_tile = {row["tile_id"]: row["allocated_area_mm2"] for row in allocations}
    for fragment in fragments:
        _require_tile(connection, fragment["tile_id"])
        connection.execute(
            """
            UPDATE tiles
            SET built_allocated_mm2=built_allocated_mm2+?,
                built_valid_area_mm2=built_valid_area_mm2+?
            WHERE tile_id=?
            """,
            (
                allocation_by_tile[fragment["tile_id"]],
                fragment["area_mm2"],
                fragment["tile_id"],
            ),
        )
    total = built * AREA_UNITS_PER_M2
    _counter_add(connection, "built_source_total_mm2", total)
    _counter_add(connection, "built_allocated_total_mm2", sum(allocation_by_tile.values()))
    _counter_add(connection, "built_valid_source_cells", 1)


def _ingest_smod(connection: sqlite3.Connection, value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {"code", "fragments", "source_cell_id", "source_land_area_mm2"},
        "SMOD row",
    )
    source_id = _source_cell_id(value["source_cell_id"], "SMOD row")
    source_area = _positive_integer(value["source_land_area_mm2"], "SMOD source land area")
    fragments = _fragments(value["fragments"], source_area, "SMOD row")
    _mark_source_cell(connection, "smod_cells", source_id)
    code = value["code"]
    if code is not None and (isinstance(code, bool) or code not in SMOD_VALID_CODES):
        raise BlindTileAuxiliaryIntegrationError("SMOD code is outside the pinned L2 set")
    for fragment in fragments:
        _require_tile(connection, fragment["tile_id"])
        if code is None:
            connection.execute(
                "UPDATE tiles SET smod_nodata_area_mm2=smod_nodata_area_mm2+? WHERE tile_id=?",
                (fragment["area_mm2"], fragment["tile_id"]),
            )
        else:
            connection.execute(
                """
                UPDATE tiles
                SET smod_valid_area_mm2=smod_valid_area_mm2+?,
                    smod_urban_area_mm2=smod_urban_area_mm2+?
                WHERE tile_id=?
                """,
                (
                    fragment["area_mm2"],
                    fragment["area_mm2"] if code in SMOD_URBAN_CODES else 0,
                    fragment["tile_id"],
                ),
            )
    _counter_add(connection, "smod_nodata_source_cells" if code is None else "smod_valid_source_cells", 1)


def _ingest_osm(connection: sqlite3.Connection, value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "coverage_complete",
            "grid_max_voltage_v",
            "grid_min_distance_mm",
            "industrial_union_area_mm2",
            "tile_id",
        },
        "OSM tile row",
    )
    tile = _tile_id(value["tile_id"], "OSM tile row")
    land_area = _require_tile(connection, tile)
    complete = value["coverage_complete"]
    if not isinstance(complete, bool):
        raise BlindTileAuxiliaryIntegrationError("OSM coverage_complete must be boolean")
    industrial = _nonnegative_integer(
        value["industrial_union_area_mm2"], "OSM industrial union area"
    )
    if industrial > land_area:
        raise BlindTileAuxiliaryIntegrationError("OSM industrial union exceeds tile land")
    distance = value["grid_min_distance_mm"]
    voltage = value["grid_max_voltage_v"]
    if (distance is None) != (voltage is None):
        raise BlindTileAuxiliaryIntegrationError("OSM grid distance and voltage must be paired")
    if distance is not None:
        _nonnegative_integer(distance, "OSM grid distance")
        _nonnegative_integer(voltage, "OSM grid voltage")
        if voltage < GRID_THRESHOLD_VOLTAGE_V:
            raise BlindTileAuxiliaryIntegrationError(
                "OSM derivative contains grid voltage below its 110 kV contract"
            )
    cursor = connection.execute(
        """
        UPDATE tiles
        SET osm_seen=1, osm_complete=?, industrial_union_area_mm2=?,
            grid_min_distance_mm=?, grid_max_voltage_v=?
        WHERE tile_id=? AND osm_seen=0
        """,
        (int(complete), industrial, distance, voltage, tile),
    )
    if cursor.rowcount != 1:
        raise BlindTileAuxiliaryIntegrationError("OSM stream repeats a tile")


_INGESTERS = {
    "tiles": _ingest_tiles,
    "built_cells": _ingest_built,
    "smod_cells": _ingest_smod,
    "osm_tiles": _ingest_osm,
}


def _ensure_progress(
    connection: sqlite3.Connection, role: str, checkpoint: Mapping[str, Any]
) -> tuple[int, int, bool]:
    row = connection.execute(
        "SELECT input_bytes,input_sha256,byte_offset,row_count,completed FROM progress WHERE role=?",
        (role,),
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO progress VALUES(?,?,?,?,?,0)",
            (role, checkpoint["bytes"], checkpoint["sha256"], 0, 0),
        )
        return 0, 0, False
    if row[0] != checkpoint["bytes"] or row[1] != checkpoint["sha256"]:
        raise BlindTileAuxiliaryIntegrationError(f"{role} input changed during resume")
    return int(row[2]), int(row[3]), bool(row[4])


def _ingest_one_batch(
    connection: sqlite3.Connection,
    role: str,
    path: Path,
    checkpoint: Mapping[str, Any],
    batch_size: int,
) -> tuple[bool, int]:
    offset, row_count, completed = _ensure_progress(connection, role, checkpoint)
    if completed:
        return True, 0
    records: list[tuple[bytes, int]] = []
    with path.open("rb") as source:
        source.seek(offset)
        for _ in range(batch_size):
            raw = source.readline(4 * 1024 * 1024 + 1)
            if not raw:
                break
            records.append((raw, source.tell()))
        next_byte = source.read(1)
        eof = not next_byte
    connection.execute("BEGIN IMMEDIATE")
    try:
        for index, (raw, _) in enumerate(records, start=row_count + 1):
            _INGESTERS[role](connection, _parse_line(raw, role, index))
        new_offset = records[-1][1] if records else offset
        connection.execute(
            """
            UPDATE progress SET byte_offset=?,row_count=?,completed=? WHERE role=?
            """,
            (new_offset, row_count + len(records), int(eof), role),
        )
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return eof, len(records)


def _signal_or(first: str, second: str) -> str:
    if "true" in {first, second}:
        return "true"
    if first == second == "false":
        return "false"
    return "unknown"


def _lower_bound_stratum(signals: Mapping[str, str]) -> str:
    industrial = signals["industrial"] == "true"
    grid = signals["grid"] == "true"
    urban = signals["urban"] == "true"
    if industrial and grid:
        return "industrial_and_grid"
    if industrial != grid:
        return "industrial_xor_grid"
    if urban:
        return "urban_built"
    return "background"


def _tile_output(row: sqlite3.Row) -> dict[str, Any]:
    land = int(row["land_area_mm2"])
    built_allocated = int(row["built_allocated_mm2"])
    built_valid = int(row["built_valid_area_mm2"])
    built_nodata = int(row["built_nodata_area_mm2"])
    smod_valid = int(row["smod_valid_area_mm2"])
    smod_urban = int(row["smod_urban_area_mm2"])
    smod_nodata = int(row["smod_nodata_area_mm2"])
    if built_valid + built_nodata > land or smod_valid + smod_nodata > land:
        raise BlindTileAuxiliaryIntegrationError("auxiliary coverage exceeds tile land area")
    if built_allocated > built_valid or smod_urban > smod_valid:
        raise BlindTileAuxiliaryIntegrationError(
            "auxiliary positive area exceeds its valid coverage"
        )
    built_true = built_allocated * BUILT_THRESHOLD_DENOMINATOR >= land
    built_signal = "true" if built_true else ("false" if built_valid == land else "unknown")
    smod_signal = "true" if smod_urban > 0 else ("false" if smod_valid == land else "unknown")
    urban_signal = _signal_or(built_signal, smod_signal)
    osm_seen = bool(row["osm_seen"])
    osm_complete = bool(row["osm_complete"]) if osm_seen else False
    industrial_area = (
        int(row["industrial_union_area_mm2"])
        if row["industrial_union_area_mm2"] is not None
        else 0
    )
    industrial_signal = (
        "true"
        if industrial_area >= INDUSTRIAL_THRESHOLD_AREA_MM2
        else ("false" if osm_seen and osm_complete else "unknown")
    )
    distance = row["grid_min_distance_mm"]
    voltage = row["grid_max_voltage_v"]
    grid_true = (
        distance is not None
        and voltage is not None
        and int(distance) <= GRID_THRESHOLD_DISTANCE_MM
        and int(voltage) >= GRID_THRESHOLD_VOLTAGE_V
    )
    grid_signal = "true" if grid_true else ("false" if osm_seen and osm_complete else "unknown")
    signal_map = {
        "built": built_signal,
        "grid": grid_signal,
        "industrial": industrial_signal,
        "smod": smod_signal,
        "urban": urban_signal,
    }
    stratum = _lower_bound_stratum(signal_map)
    return {
        "candidate_independent": True,
        "ghsl": {
            "built": {
                "allocated_area_mm2": built_allocated,
                "coverage": {
                    "missing_area_mm2": land - built_valid - built_nodata,
                    "nodata_area_mm2": built_nodata,
                    "valid_area_mm2": built_valid,
                },
                "signal": built_signal,
                "threshold_denominator_land_area_mm2": land,
            },
            "smod": {
                "coverage": {
                    "missing_area_mm2": land - smod_valid - smod_nodata,
                    "nodata_area_mm2": smod_nodata,
                    "valid_area_mm2": smod_valid,
                },
                "signal": smod_signal,
                "urban_intersection_area_mm2": smod_urban,
            },
        },
        "land_area_mm2": land,
        "osm": {
            "coverage_complete": osm_complete if osm_seen else False,
            "grid": {
                "max_voltage_v": int(voltage) if voltage is not None else None,
                "min_distance_mm": int(distance) if distance is not None else None,
                "signal": grid_signal,
            },
            "industrial": {
                "signal": industrial_signal,
                "union_intersection_area_mm2": industrial_area if osm_seen else None,
            },
            "row_present": osm_seen,
        },
        "schema_version": SCHEMA_VERSION,
        "signals": signal_map,
        "stratum_lower_bound": stratum,
        "tile_id": row["tile_id"],
        "unknown_signal_fields": sorted(
            key for key, value in signal_map.items() if value == "unknown"
        ),
    }


def _validated_coverage(
    value: Any, land_area_mm2: int, label: str
) -> tuple[int, int, int]:
    if not isinstance(value, Mapping):
        raise BlindTileAuxiliaryIntegrationError(f"{label} must be an object")
    _exact_keys(
        value,
        {"missing_area_mm2", "nodata_area_mm2", "valid_area_mm2"},
        label,
    )
    missing = _nonnegative_integer(value["missing_area_mm2"], f"{label} missing")
    nodata = _nonnegative_integer(value["nodata_area_mm2"], f"{label} nodata")
    valid = _nonnegative_integer(value["valid_area_mm2"], f"{label} valid")
    if missing + nodata + valid != land_area_mm2:
        raise BlindTileAuxiliaryIntegrationError(
            f"{label} does not exactly partition tile land"
        )
    return valid, nodata, missing


def _validate_tile_output_document(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output row must be an object")
    _exact_keys(
        value,
        {
            "candidate_independent",
            "ghsl",
            "land_area_mm2",
            "osm",
            "schema_version",
            "signals",
            "stratum_lower_bound",
            "tile_id",
            "unknown_signal_fields",
        },
        "output row",
    )
    _tile_id(value["tile_id"], "output row")
    if (
        value["candidate_independent"] is not True
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise BlindTileAuxiliaryIntegrationError("output row identity changed")
    land = _positive_integer(value["land_area_mm2"], "output tile land area")
    if land > 16_000_000 * AREA_UNITS_PER_M2:
        raise BlindTileAuxiliaryIntegrationError("output tile land area exceeds 4 km tile")

    ghsl = value["ghsl"]
    if not isinstance(ghsl, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output GHSL must be an object")
    _exact_keys(ghsl, {"built", "smod"}, "output GHSL")
    built = ghsl["built"]
    if not isinstance(built, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output BUILT must be an object")
    _exact_keys(
        built,
        {
            "allocated_area_mm2",
            "coverage",
            "signal",
            "threshold_denominator_land_area_mm2",
        },
        "output BUILT",
    )
    allocated = _nonnegative_integer(
        built["allocated_area_mm2"], "output BUILT allocated area"
    )
    built_valid, _, _ = _validated_coverage(
        built["coverage"], land, "output BUILT coverage"
    )
    if allocated > built_valid:
        raise BlindTileAuxiliaryIntegrationError(
            "output BUILT allocated area exceeds valid coverage"
        )
    if built["threshold_denominator_land_area_mm2"] != land:
        raise BlindTileAuxiliaryIntegrationError(
            "output BUILT denominator is not tile land"
        )
    expected_built = (
        "true"
        if allocated * BUILT_THRESHOLD_DENOMINATOR >= land
        else ("false" if built_valid == land else "unknown")
    )
    if built["signal"] != expected_built:
        raise BlindTileAuxiliaryIntegrationError("output BUILT signal changed")

    smod = ghsl["smod"]
    if not isinstance(smod, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output SMOD must be an object")
    _exact_keys(
        smod,
        {"coverage", "signal", "urban_intersection_area_mm2"},
        "output SMOD",
    )
    smod_valid, _, _ = _validated_coverage(
        smod["coverage"], land, "output SMOD coverage"
    )
    urban_area = _nonnegative_integer(
        smod["urban_intersection_area_mm2"], "output SMOD urban area"
    )
    if urban_area > smod_valid:
        raise BlindTileAuxiliaryIntegrationError(
            "output SMOD urban area exceeds valid coverage"
        )
    expected_smod = (
        "true" if urban_area > 0 else ("false" if smod_valid == land else "unknown")
    )
    if smod["signal"] != expected_smod:
        raise BlindTileAuxiliaryIntegrationError("output SMOD signal changed")

    osm = value["osm"]
    if not isinstance(osm, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output OSM must be an object")
    _exact_keys(
        osm,
        {"coverage_complete", "grid", "industrial", "row_present"},
        "output OSM",
    )
    if not isinstance(osm["row_present"], bool) or not isinstance(
        osm["coverage_complete"], bool
    ):
        raise BlindTileAuxiliaryIntegrationError("output OSM coverage flags changed")
    seen = osm["row_present"]
    complete = osm["coverage_complete"]
    if not seen and complete:
        raise BlindTileAuxiliaryIntegrationError(
            "output OSM cannot be complete without a row"
        )
    industrial = osm["industrial"]
    if not isinstance(industrial, Mapping):
        raise BlindTileAuxiliaryIntegrationError(
            "output OSM industrial must be an object"
        )
    _exact_keys(
        industrial,
        {"signal", "union_intersection_area_mm2"},
        "output OSM industrial",
    )
    industrial_area = industrial["union_intersection_area_mm2"]
    if seen:
        industrial_area = _nonnegative_integer(
            industrial_area, "output OSM industrial area"
        )
        if industrial_area > land:
            raise BlindTileAuxiliaryIntegrationError(
                "output OSM industrial area exceeds tile land"
            )
    elif industrial_area is not None:
        raise BlindTileAuxiliaryIntegrationError(
            "output OSM industrial area exists without a row"
        )
    expected_industrial = (
        "true"
        if seen and industrial_area >= INDUSTRIAL_THRESHOLD_AREA_MM2
        else ("false" if seen and complete else "unknown")
    )
    if industrial["signal"] != expected_industrial:
        raise BlindTileAuxiliaryIntegrationError("output OSM industrial signal changed")

    grid = osm["grid"]
    if not isinstance(grid, Mapping):
        raise BlindTileAuxiliaryIntegrationError("output OSM grid must be an object")
    _exact_keys(
        grid,
        {"max_voltage_v", "min_distance_mm", "signal"},
        "output OSM grid",
    )
    distance = grid["min_distance_mm"]
    voltage = grid["max_voltage_v"]
    if (distance is None) != (voltage is None):
        raise BlindTileAuxiliaryIntegrationError(
            "output OSM grid distance and voltage must be paired"
        )
    if not seen and distance is not None:
        raise BlindTileAuxiliaryIntegrationError(
            "output OSM grid values exist without a row"
        )
    if distance is not None:
        distance = _nonnegative_integer(distance, "output OSM grid distance")
        voltage = _nonnegative_integer(voltage, "output OSM grid voltage")
        if voltage < GRID_THRESHOLD_VOLTAGE_V:
            raise BlindTileAuxiliaryIntegrationError(
                "output OSM grid voltage is below 110 kV"
            )
    grid_true = (
        seen
        and distance is not None
        and distance <= GRID_THRESHOLD_DISTANCE_MM
        and voltage >= GRID_THRESHOLD_VOLTAGE_V
    )
    expected_grid = "true" if grid_true else ("false" if seen and complete else "unknown")
    if grid["signal"] != expected_grid:
        raise BlindTileAuxiliaryIntegrationError("output OSM grid signal changed")

    expected_signals = {
        "built": expected_built,
        "grid": expected_grid,
        "industrial": expected_industrial,
        "smod": expected_smod,
        "urban": _signal_or(expected_built, expected_smod),
    }
    if value["signals"] != expected_signals:
        raise BlindTileAuxiliaryIntegrationError("output signal map changed")
    if value["stratum_lower_bound"] != _lower_bound_stratum(expected_signals):
        raise BlindTileAuxiliaryIntegrationError("output lower-bound stratum changed")
    expected_unknown = sorted(
        key for key, signal in expected_signals.items() if signal == "unknown"
    )
    if value["unknown_signal_fields"] != expected_unknown:
        raise BlindTileAuxiliaryIntegrationError("output unknown fields changed")


def _stream_outputs(
    connection: sqlite3.Connection, output_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    size = 0
    with output_path.open("xb") as destination:
        cursor = connection.execute("SELECT * FROM tiles ORDER BY tile_id")
        for row in cursor:
            document = _tile_output(row)
            raw = canonical_line(document)
            destination.write(raw)
            digest.update(raw)
            size += len(raw)
            counts["tiles"] += 1
            counts[f"stratum:{document['stratum_lower_bound']}"] += 1
            for signal, value in document["signals"].items():
                counts[f"signal:{signal}:{value}"] += 1
        destination.flush()
        os.fsync(destination.fileno())
    if counts["tiles"] <= 0:
        raise BlindTileAuxiliaryIntegrationError("integration output has no tiles")
    source_total_row = connection.execute(
        "SELECT value FROM counters WHERE key='built_source_total_mm2'"
    ).fetchone()
    allocated_total_row = connection.execute(
        "SELECT value FROM counters WHERE key='built_allocated_total_mm2'"
    ).fetchone()
    source_total = int(source_total_row[0]) if source_total_row else 0
    allocated_total = int(allocated_total_row[0]) if allocated_total_row else 0
    if source_total != allocated_total:
        raise BlindTileAuxiliaryIntegrationError("global BUILT allocation is not conservative")
    coverage = {
        "candidate_independent": True,
        "claims": {
            "production_frame_built": False,
            "production_sample_built": False,
            "selection_is_data_centre_evidence": False,
        },
        "counts": dict(sorted(counts.items())),
        "production_frame_built": False,
        "schema_version": SCHEMA_VERSION,
        "source_built_area_mm2": source_total,
        "allocated_built_area_mm2": allocated_total,
        "source_to_tile_built_conservation_exact": True,
    }
    return {"bytes": size, "sha256": digest.hexdigest()}, coverage


def _readme(definition: Mapping[str, Any], coverage: Mapping[str, Any]) -> bytes:
    fixture = definition["fixture_only"]
    text = f"""# Blind-tile auxiliary integration {'fixture' if fixture else 'production signals'}

This bundle contains {coverage['counts']['tiles']} candidate-independent tile-signal rows. It is {'a synthetic fixture only' if fixture else 'derived only from the pinned Natural Earth land frame, frozen GHSL cache, and frozen full-Planet stable OSM derivative'}.

GHS-BUILT-S is treated as an extensive quantity. Every source-cell integer-square-metre total is converted to square millimetres and distributed by source-cell-land intersection area using deterministic largest remainder; source and allocated totals are exactly equal. Bilinear interpolation is forbidden. GHS-SMOD remains categorical and is true on any positive urban-coded intersection. Nodata and missing coverage remain explicit unknowns.

OSM industrial area is the union intersection and requires at least 10,000 m2. Grid requires a frozen >=110 kV feature within 5 km. Negative OSM signals require complete tile processing. Unknown signals are treated as false only for the recorded lower-bound stratum and remain listed explicitly.

This is not a data-centre list, does not establish data-centre presence, and did not build a production frame or sample.
"""
    return text.encode("utf-8")


def _attribution(definition: Mapping[str, Any]) -> bytes:
    if definition["fixture_only"]:
        return b"Synthetic integration fixture; no GHSL or OSM-derived values.\n"
    return (
        "GHSL: European Union / European Commission, Joint Research Centre (JRC), "
        "CC BY 4.0; changes indicated. OpenStreetMap: © OpenStreetMap contributors, "
        "ODbL 1.0. Natural Earth is public domain.\n"
    ).encode("utf-8")


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


def _freeze(path: Path) -> None:
    for child in path.iterdir():
        child.chmod(0o444)
    path.chmod(0o555)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _discard_temporary_bundle(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    if path.is_dir():
        path.chmod(0o755)
        for child in path.iterdir():
            if not child.is_symlink():
                child.chmod(0o644)
        shutil.rmtree(path)


def _bundle_frozen(path: Path) -> bool:
    return (
        stat.S_IMODE(path.stat().st_mode) == 0o555
        and all(
            child.is_file()
            and not child.is_symlink()
            and stat.S_IMODE(child.stat().st_mode) == 0o444
            for child in path.iterdir()
        )
    )


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _validate_storage_paths(
    output_path: str | Path,
    work_database_path: str | Path,
    definition_path: str | Path,
    inputs: Mapping[str, Path],
) -> tuple[Path, Path, Path]:
    lexical_output = Path(output_path)
    lexical_work_database = Path(work_database_path)
    if not lexical_output.name:
        raise BlindTileAuxiliaryIntegrationError(
            "integration output must name a non-root directory"
        )
    lexical_temporary = lexical_output.with_name(f".{lexical_output.name}.tmp")
    lexical_sqlite_companions = {
        "SQLite rollback journal": Path(f"{lexical_work_database}-journal"),
        "SQLite shared memory": Path(f"{lexical_work_database}-shm"),
        "SQLite WAL": Path(f"{lexical_work_database}-wal"),
    }
    lexical_storage_paths = {
        "output": lexical_output,
        "sibling temporary bundle": lexical_temporary,
        "work database": lexical_work_database,
        **lexical_sqlite_companions,
    }
    for label, candidate in lexical_storage_paths.items():
        _reject_existing_symlink_components(candidate, f"integration {label}")
    output = lexical_output.resolve()
    work_database = lexical_work_database.resolve()
    temporary = lexical_temporary.resolve()
    storage_paths = {
        label: candidate.resolve()
        for label, candidate in lexical_storage_paths.items()
    }
    for label, candidate in storage_paths.items():
        _reject_forbidden_path(str(candidate), f"integration {label}")
    labels = list(storage_paths)
    for index, first_label in enumerate(labels):
        for second_label in labels[index + 1 :]:
            if _paths_overlap(
                storage_paths[first_label], storage_paths[second_label]
            ):
                raise BlindTileAuxiliaryIntegrationError(
                    f"integration {first_label} and {second_label} paths overlap"
                )
    protected_paths = {
        "definition": Path(definition_path).resolve(),
        **{f"{role} input": path.resolve() for role, path in inputs.items()},
    }
    for storage_label, storage_path in storage_paths.items():
        for protected_label, protected_path in protected_paths.items():
            if _paths_overlap(storage_path, protected_path):
                raise BlindTileAuxiliaryIntegrationError(
                    f"integration {storage_label} overlaps the bound {protected_label}"
                )
    if temporary.exists() or temporary.is_symlink():
        raise BlindTileAuxiliaryIntegrationError(
            "temporary bundle path already exists before SQLite open"
        )
    return output, work_database, temporary


def build_integration_bundle(
    output_path: str | Path,
    *,
    definition_path: str | Path,
    work_database_path: str | Path,
    batch_size: int = 10_000,
    maximum_batches: int | None = None,
    freeze: bool = True,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    if batch_size <= 0 or (maximum_batches is not None and maximum_batches <= 0):
        raise ValueError("batch_size and maximum_batches must be positive")
    definition, definition_raw, inputs = load_definition(definition_path)
    if not definition["fixture_only"] and not freeze:
        raise BlindTileAuxiliaryIntegrationError(
            "production auxiliary bundles must be frozen"
        )
    algorithm_before = current_algorithm_checkpoints()
    definition_sha256 = hashlib.sha256(definition_raw).hexdigest()
    output, work_database, temporary = _validate_storage_paths(
        output_path, work_database_path, definition_path, inputs
    )
    if output.exists() or output.is_symlink():
        return validate_integration_bundle(
            output, definition_path=definition_path, require_frozen=freeze
        )
    connection = _connect_state(work_database, definition_sha256)
    batches = 0
    try:
        for role in INPUT_ROLES:
            checkpoint = _hash_file(inputs[role])
            while True:
                completed, rows = _ingest_one_batch(
                    connection, role, inputs[role], checkpoint, batch_size
                )
                if rows:
                    batches += 1
                if completed:
                    break
                if maximum_batches is not None and batches >= maximum_batches:
                    return {
                        "batches_committed_this_run": batches,
                        "production_frame_built": False,
                        "release_id": definition["release_id"],
                        "state": "in_progress",
                    }
            if maximum_batches is not None and batches >= maximum_batches and role != INPUT_ROLES[-1]:
                return {
                    "batches_committed_this_run": batches,
                    "production_frame_built": False,
                    "release_id": definition["release_id"],
                    "state": "in_progress",
                }
        if current_algorithm_checkpoints() != algorithm_before:
            raise BlindTileAuxiliaryIntegrationError("integration code changed during build")
        expected_input_checkpoints = {
            role: {
                "bytes": definition["input_contract"]["inputs"][role]["bytes"],
                "sha256": definition["input_contract"]["inputs"][role]["sha256"],
            }
            for role in INPUT_ROLES
        }
        actual_input_checkpoints = {
            role: _hash_file(inputs[role]) for role in INPUT_ROLES
        }
        if actual_input_checkpoints != expected_input_checkpoints:
            raise BlindTileAuxiliaryIntegrationError(
                "normalized input changed before publication"
            )
        if temporary.exists() or temporary.is_symlink():
            raise BlindTileAuxiliaryIntegrationError("temporary bundle path already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.mkdir()
        started = clock()
        try:
            output_checkpoint, coverage = _stream_outputs(
                connection, temporary / OUTPUT_FILENAME
            )
            payloads = {
                ATTRIBUTION_FILENAME: _attribution(definition),
                COVERAGE_FILENAME: canonical_json(coverage),
                DEFINITION_FILENAME: definition_raw,
                README_FILENAME: _readme(definition, coverage),
            }
            for name, raw in payloads.items():
                _write_new(temporary / name, raw)
            manifest = {
                "algorithm": algorithm_before,
                "candidate_independent": True,
                "file_count": len(BUNDLE_PAYLOAD_FILES),
                "files": {
                    name: _hash_file(temporary / name)
                    for name in sorted(BUNDLE_PAYLOAD_FILES)
                },
                "finished_at": clock(),
                "fixture_only": definition["fixture_only"],
                "format": BUNDLE_FORMAT,
                "input_checkpoints": actual_input_checkpoints,
                "pipeline": PIPELINE,
                "production_frame_built": False,
                "release_id": definition["release_id"],
                "runtime": runtime_record(),
                "schema_version": SCHEMA_VERSION,
                "semantic_contract": SEMANTIC_CONTRACT,
                "started_at": started,
                "state": "completed",
            }
            if manifest["files"][OUTPUT_FILENAME] != output_checkpoint:
                raise BlindTileAuxiliaryIntegrationError("streamed output checkpoint changed")
            manifest_raw = canonical_json(manifest)
            _write_new(temporary / MANIFEST_FILENAME, manifest_raw)
            _write_new(
                temporary / MANIFEST_SHA_FILENAME,
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n".encode(
                    "ascii"
                ),
            )
            if current_algorithm_checkpoints() != algorithm_before:
                raise BlindTileAuxiliaryIntegrationError("integration code changed before publish")
            validate_integration_bundle(
                temporary,
                definition_path=definition_path,
                require_frozen=False,
            )
            if current_algorithm_checkpoints() != algorithm_before:
                raise BlindTileAuxiliaryIntegrationError(
                    "integration code changed during prepublication replay"
                )
            if {
                role: _hash_file(inputs[role]) for role in INPUT_ROLES
            } != expected_input_checkpoints:
                raise BlindTileAuxiliaryIntegrationError(
                    "normalized input changed after prepublication replay"
                )
            if freeze:
                _freeze(temporary)
                if not _bundle_frozen(temporary):
                    raise BlindTileAuxiliaryIntegrationError(
                        "temporary integration bundle did not freeze"
                    )
            _fsync_directory(temporary)
            _fsync_directory(output.parent)
            temporary.replace(output)
            _fsync_directory(output.parent)
        except BaseException:
            _discard_temporary_bundle(temporary)
            raise
    finally:
        connection.close()
    return validate_integration_bundle(
        output, definition_path=definition_path, require_frozen=freeze
    )


def _iter_canonical_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("rb") as source:
        for row_number, raw in enumerate(source, start=1):
            yield _parse_line(raw, OUTPUT_FILENAME, row_number)


def _source_built_area_total(path: Path) -> int:
    total = 0
    with path.open("rb") as source:
        for row_number, raw in enumerate(source, start=1):
            value = _parse_line(raw, "built_cells", row_number)
            if set(value) != {
                "built_surface_m2",
                "fragments",
                "source_cell_id",
                "source_land_area_mm2",
            }:
                raise BlindTileAuxiliaryIntegrationError(
                    "BUILT source row schema changed during validation"
                )
            built = value["built_surface_m2"]
            if built is not None:
                total += _nonnegative_integer(
                    built, "BUILT source value during validation"
                ) * AREA_UNITS_PER_M2
    return total


def _compare_output_lockstep(expected_path: Path, actual_path: Path) -> None:
    with expected_path.open("rb") as expected, actual_path.open("rb") as actual:
        row_number = 0
        while True:
            expected_row = expected.readline(4 * 1024 * 1024 + 1)
            actual_row = actual.readline(4 * 1024 * 1024 + 1)
            if not expected_row and not actual_row:
                return
            row_number += 1
            if expected_row != actual_row:
                raise BlindTileAuxiliaryIntegrationError(
                    "published auxiliary output differs from fresh normalized-stream "
                    f"replay at row {row_number}"
                )


def _replay_and_compare_normalized_streams(
    root: Path,
    inputs: Mapping[str, Path],
    definition_sha256: str,
    expected_checkpoints: Mapping[str, Mapping[str, Any]],
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="blind-tile-auxiliary-validation-"
    ) as temporary_name:
        temporary = Path(temporary_name)
        connection = _connect_state(
            temporary / "fresh-validation.sqlite3", definition_sha256
        )
        try:
            for role in INPUT_ROLES:
                checkpoint = _hash_file(inputs[role])
                if checkpoint != expected_checkpoints[role]:
                    raise BlindTileAuxiliaryIntegrationError(
                        f"{role} input changed before fresh validation replay"
                    )
                completed = False
                while not completed:
                    completed, _ = _ingest_one_batch(
                        connection,
                        role,
                        inputs[role],
                        checkpoint,
                        10_000,
                    )
            expected_output = temporary / OUTPUT_FILENAME
            _, expected_coverage = _stream_outputs(connection, expected_output)
        finally:
            connection.close()
        for role in INPUT_ROLES:
            if _hash_file(inputs[role]) != expected_checkpoints[role]:
                raise BlindTileAuxiliaryIntegrationError(
                    f"{role} input changed during fresh validation replay"
                )
        _compare_output_lockstep(expected_output, root / OUTPUT_FILENAME)
        if (root / COVERAGE_FILENAME).read_bytes() != canonical_json(
            expected_coverage
        ):
            raise BlindTileAuxiliaryIntegrationError(
                "published coverage differs from fresh normalized-stream replay"
            )


def validate_integration_bundle(
    path: str | Path,
    *,
    definition_path: str | Path | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise BlindTileAuxiliaryIntegrationError("integration bundle must be a directory")
    entries = {entry.name for entry in root.iterdir()}
    if entries != BUNDLE_FILES or any(entry.is_symlink() or not entry.is_file() for entry in root.iterdir()):
        raise BlindTileAuxiliaryIntegrationError("integration bundle inventory changed")
    if require_frozen and not _bundle_frozen(root):
        raise BlindTileAuxiliaryIntegrationError("integration bundle is not frozen 0555/0444")
    bundled_definition, definition_raw, _ = load_definition(
        root / DEFINITION_FILENAME, verify_external_sources=False
    )
    if not bundled_definition["fixture_only"] and definition_path is None:
        raise BlindTileAuxiliaryIntegrationError(
            "production bundle validation requires the external definition for source lineage"
        )
    external_inputs: dict[str, Path] | None = None
    external_definition_sha256: str | None = None
    if definition_path is not None:
        external, external_raw, external_inputs = load_definition(definition_path)
        external_definition_sha256 = hashlib.sha256(external_raw).hexdigest()
        if external != bundled_definition or external_raw != definition_raw:
            raise BlindTileAuxiliaryIntegrationError("external definition differs")
    manifest, manifest_raw = _load_json_object(root / MANIFEST_FILENAME, "integration manifest")
    expected_manifest_keys = {
        "algorithm",
        "candidate_independent",
        "file_count",
        "files",
        "finished_at",
        "fixture_only",
        "format",
        "input_checkpoints",
        "pipeline",
        "production_frame_built",
        "release_id",
        "runtime",
        "schema_version",
        "semantic_contract",
        "started_at",
        "state",
    }
    if set(manifest) != expected_manifest_keys or (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("pipeline") != PIPELINE
        or manifest.get("state") != "completed"
        or manifest.get("candidate_independent") is not True
        or manifest.get("production_frame_built") is not False
        or manifest.get("semantic_contract") != SEMANTIC_CONTRACT
        or manifest.get("algorithm") != current_algorithm_checkpoints()
        or manifest.get("fixture_only") != bundled_definition["fixture_only"]
        or manifest.get("release_id") != bundled_definition["release_id"]
        or manifest.get("file_count") != len(BUNDLE_PAYLOAD_FILES)
        or not isinstance(manifest.get("files"), Mapping)
        or set(manifest["files"]) != BUNDLE_PAYLOAD_FILES
    ):
        raise BlindTileAuxiliaryIntegrationError("integration manifest identity changed")
    _timestamp(manifest["started_at"], "manifest started_at")
    _timestamp(manifest["finished_at"], "manifest finished_at")
    if manifest["finished_at"] < manifest["started_at"]:
        raise BlindTileAuxiliaryIntegrationError("integration manifest time moved backward")
    runtime = manifest["runtime"]
    if (
        not isinstance(runtime, Mapping)
        or set(runtime) != {"implementation", "platform", "python_version"}
        or any(not isinstance(value, str) or not value for value in runtime.values())
    ):
        raise BlindTileAuxiliaryIntegrationError("integration runtime record changed")
    expected_inputs = {
        role: {
            "bytes": bundled_definition["input_contract"]["inputs"][role]["bytes"],
            "sha256": bundled_definition["input_contract"]["inputs"][role]["sha256"],
        }
        for role in INPUT_ROLES
    }
    if manifest["input_checkpoints"] != expected_inputs:
        raise BlindTileAuxiliaryIntegrationError(
            "integration input checkpoints changed"
        )
    sidecar = f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if (root / MANIFEST_SHA_FILENAME).read_bytes() != sidecar:
        raise BlindTileAuxiliaryIntegrationError("integration manifest sidecar changed")
    for name in BUNDLE_PAYLOAD_FILES:
        if _hash_file(root / name) != manifest["files"][name]:
            raise BlindTileAuxiliaryIntegrationError(f"integration payload changed: {name}")
    counts: Counter[str] = Counter()
    output_allocated_built_area_mm2 = 0
    previous: str | None = None
    for row in _iter_canonical_jsonl(root / OUTPUT_FILENAME):
        _validate_tile_output_document(row)
        tile = row["tile_id"]
        if previous is not None and tile <= previous:
            raise BlindTileAuxiliaryIntegrationError("output tiles are duplicate or unsorted")
        previous = tile
        signals = row["signals"]
        output_allocated_built_area_mm2 += row["ghsl"]["built"][
            "allocated_area_mm2"
        ]
        counts["tiles"] += 1
        counts[f"stratum:{row.get('stratum_lower_bound')}"] += 1
        for signal, value in signals.items():
            counts[f"signal:{signal}:{value}"] += 1
    if counts["tiles"] <= 0:
        raise BlindTileAuxiliaryIntegrationError("integration output has no tiles")
    coverage, _ = _load_json_object(root / COVERAGE_FILENAME, "coverage")
    _exact_keys(
        coverage,
        {
            "allocated_built_area_mm2",
            "candidate_independent",
            "claims",
            "counts",
            "production_frame_built",
            "schema_version",
            "source_built_area_mm2",
            "source_to_tile_built_conservation_exact",
        },
        "coverage",
    )
    if (
        coverage["schema_version"] != SCHEMA_VERSION
        or coverage["candidate_independent"] is not True
        or coverage["production_frame_built"] is not False
        or coverage["claims"]
        != {
            "production_frame_built": False,
            "production_sample_built": False,
            "selection_is_data_centre_evidence": False,
        }
        or coverage["counts"] != dict(sorted(counts.items()))
        or coverage["source_to_tile_built_conservation_exact"] is not True
    ):
        raise BlindTileAuxiliaryIntegrationError("coverage summary changed")
    source_total = _nonnegative_integer(
        coverage["source_built_area_mm2"], "coverage source BUILT area"
    )
    allocated_total = _nonnegative_integer(
        coverage["allocated_built_area_mm2"], "coverage allocated BUILT area"
    )
    if (
        source_total != allocated_total
        or allocated_total != output_allocated_built_area_mm2
    ):
        raise BlindTileAuxiliaryIntegrationError("coverage conservation changed")
    if (
        external_inputs is not None
        and source_total != _source_built_area_total(external_inputs["built_cells"])
    ):
        raise BlindTileAuxiliaryIntegrationError(
            "coverage source BUILT total changed"
        )
    if (root / README_FILENAME).read_bytes() != _readme(bundled_definition, coverage):
        raise BlindTileAuxiliaryIntegrationError("integration README changed")
    if (root / ATTRIBUTION_FILENAME).read_bytes() != _attribution(bundled_definition):
        raise BlindTileAuxiliaryIntegrationError("integration attribution changed")
    if external_inputs is not None and external_definition_sha256 is not None:
        _replay_and_compare_normalized_streams(
            root,
            external_inputs,
            external_definition_sha256,
            expected_inputs,
        )
    return {
        "coverage": coverage,
        "fixture_only": bundled_definition["fixture_only"],
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "production_frame_built": False,
        "release_id": bundled_definition["release_id"],
        "tile_count": counts["tiles"],
    }


__all__ = [
    "AREA_UNITS_PER_M2",
    "BlindTileAuxiliaryIntegrationError",
    "DEFINITION_FORMAT",
    "INPUT_ROLES",
    "NORMALIZED_INPUT_SOURCE_BINDINGS",
    "PRODUCTION_GEOMETRY_PRODUCER_BLOCKER",
    "PRODUCTION_GEOMETRY_PRODUCER_IMPLEMENTED",
    "SEMANTIC_CONTRACT",
    "allocate_extensive_built_area",
    "build_integration_bundle",
    "canonical_json",
    "canonical_line",
    "current_algorithm_checkpoints",
    "load_definition",
    "validate_integration_bundle",
]
