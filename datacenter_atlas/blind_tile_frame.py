"""Candidate-independent equal-area blind-tile frame and sample contract.

The checked-in release is deliberately a synthetic preflight, not the global
frame.  It exercises the deterministic grid, overlap assignment, four-stratum
classification, seeded draw, and exact inclusion-probability rules while the
required frozen GHSL and OSM auxiliary inputs remain unavailable.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import zlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .natural_earth import (
    NATURAL_EARTH_EXPECTED_BYTES,
    NATURAL_EARTH_SHA256,
    NATURAL_EARTH_VERSION,
)


SCHEMA_VERSION = 1
RELEASE_ID = "blind-tile-frame-preflight-2026-07-19-v1"
RELEASE_FORMAT = "datacenter-atlas-blind-tile-frame-bundle-v1"
DEFINITION_FORMAT = "datacenter-atlas-blind-tile-frame-definition-v1"
FIXTURE_INPUT_FORMAT = "datacenter-atlas-blind-tile-frame-preflight-input-v1"

DEFINITION_FILENAME = "definition.json"
FRAME_FILENAME = "frame-cells.jsonl.gz"
STRATA_FILENAME = "strata.json"
SAMPLE_FILENAME = "sample.jsonl"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_PAYLOAD_FILES = frozenset(
    {
        DEFINITION_FILENAME,
        FRAME_FILENAME,
        STRATA_FILENAME,
        SAMPLE_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)
BUNDLE_FILES = BUNDLE_PAYLOAD_FILES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}

CRS_EPSG = 6933
TILE_SIZE_M = 4_000
TILE_AREA_M2 = TILE_SIZE_M * TILE_SIZE_M
GRID_ORIGIN_M = (0, 0)
MACROREGIONS = (
    "Africa",
    "Asia",
    "Europe",
    "North America",
    "South America",
    "Oceania",
)
STRATA = (
    "background",
    "urban_built",
    "industrial_xor_grid",
    "industrial_and_grid",
)
QUOTAS = {
    "background": 16,
    "urban_built": 24,
    "industrial_xor_grid": 40,
    "industrial_and_grid": 80,
}
SEED_STRING = "datacenter-atlas-blind-tile-audit-v1|frame-2026-07-19"
SEED_SHA256 = "8dfad5fa219214e8031b70e831b9ccf45d881b32066051775417f0651f651e3f"
DRAW_KEY_METHOD = "SHA256(ASCII(seed_sha256) || NUL || ASCII(tile_id))"

COUNTRY_ASSIGNMENT_METHOD = (
    "greatest_projected_overlap_then_lexicographic_country_key"
)
MACROREGION_ASSIGNMENT_METHOD = (
    "greatest_projected_overlap_then_lexicographic_macroregion"
)
SEMANTIC_POLICY = {
    "annual_energy_consumption_inferred": False,
    "automatic_atlas_import_performed": False,
    "construction_activity_inferred": False,
    "data_centre_identity_inferred": False,
    "data_centre_presence_inferred": False,
    "data_centre_type_inferred": False,
    "gross_facility_power_inferred": False,
    "it_capacity_inferred": False,
    "lifecycle_status_inferred": False,
    "operating_status_inferred": False,
    "operator_inferred": False,
    "owner_inferred": False,
    "pue_inferred": False,
    "selection_is_data_centre_evidence": False,
    "workload_inferred": False,
}
PRODUCTION_BLOCKERS = (
    "production EPSG:6933 intersections have not been computed from the pinned Natural Earth geometry",
    "frozen GHS-BUILT-S 2020 and GHS-SMOD auxiliary artifacts are absent",
    "a frozen source-policy-compliant OSM industrial/grid auxiliary artifact is absent",
)

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_COUNTRY_KEY_RE = re.compile(r"[A-Z0-9][A-Z0-9:._-]{1,63}")
_TILE_ID_RE = re.compile(r"e6933-4km-x(?P<x>[+-][0-9]{6})-y(?P<y>[+-][0-9]{6})")
_FORBIDDEN_REFERENCE_PATTERNS = (
    re.compile(r"(?<!datacenter-)\batlas\b", re.IGNORECASE),
    re.compile(r"construction[-_ /]master", re.IGNORECASE),
    re.compile(r"construction[-_ /]map", re.IGNORECASE),
    re.compile(r"satellite[-_ /](?:review[-_ /])?queue", re.IGNORECASE),
    re.compile(r"osm[-_ /]structural[-_ /]shortlist", re.IGNORECASE),
    re.compile(r"candidate[-_ /]fusion", re.IGNORECASE),
    re.compile(
        r"(?:^|[/\\])atlas\.(?:geojson|sqlite|html|csv|jsonl?|parquet)(?:$|[?#])",
        re.IGNORECASE,
    ),
)


class BlindTileFrameError(ValueError):
    """Raised when a frame definition, input, or bundle fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint_bytes(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": sha256_bytes(raw)}


def _checkpoint_file(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise BlindTileFrameError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BlindTileFrameError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise BlindTileFrameError(f"{label} must be a JSON object")
    return value, raw


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise BlindTileFrameError(f"{label} schema changed")


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise BlindTileFrameError(f"{label} must be lowercase SHA-256")
    return value


def _require_positive_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BlindTileFrameError(f"{label} must be a positive integer")
    return value


def _require_nonnegative_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BlindTileFrameError(f"{label} must be a non-negative integer")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BlindTileFrameError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BlindTileFrameError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BlindTileFrameError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise BlindTileFrameError(f"{label} must be canonical UTC whole seconds")
    return value


def _reject_forbidden_references(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_forbidden_references(str(key), label)
            _reject_forbidden_references(child, label)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _reject_forbidden_references(child, label)
        return
    if not isinstance(value, str):
        return
    for pattern in _FORBIDDEN_REFERENCE_PATTERNS:
        if pattern.search(value):
            raise BlindTileFrameError(
                f"{label} contains a forbidden candidate-derived reference"
            )


def _checkpoint_spec(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BlindTileFrameError(f"{label} must be a checkpoint object")
    _require_exact_keys(value, {"bytes", "path", "sha256"}, label)
    if not isinstance(value["path"], str) or not value["path"]:
        raise BlindTileFrameError(f"{label} path must be non-empty text")
    _require_positive_integer(value["bytes"], f"{label} bytes")
    _require_hash(value["sha256"], f"{label} sha256")
    _reject_forbidden_references(value["path"], label)
    return value


def _load_definition(path: str | Path) -> tuple[dict[str, Any], bytes, Path]:
    source = Path(path)
    definition, raw = _json_object(source, "blind-tile definition")
    if raw != canonical_json(definition):
        raise BlindTileFrameError("blind-tile definition must be canonical pretty JSON")
    _require_exact_keys(
        definition,
        {
            "assignment_contract",
            "blockers",
            "eligibility_contract",
            "fixture_only",
            "format",
            "generated_at",
            "grid_contract",
            "implementation_contract",
            "input_contract",
            "production_frame_built",
            "release_id",
            "sampling_contract",
            "schema_version",
            "semantic_policy",
            "stratum_contract",
        },
        "blind-tile definition",
    )
    if (
        definition["schema_version"] != SCHEMA_VERSION
        or definition["format"] != DEFINITION_FORMAT
        or definition["release_id"] != RELEASE_ID
        or definition["fixture_only"] is not True
        or definition["production_frame_built"] is not False
    ):
        raise BlindTileFrameError("blind-tile definition identity changed")
    _timestamp(definition["generated_at"], "definition generated_at")
    expected_grid = {
        "crs": "EPSG:6933",
        "crs_epsg": CRS_EPSG,
        "integer_indexed": True,
        "origin_m": [0, 0],
        "tile_area_m2": TILE_AREA_M2,
        "tile_size_m": TILE_SIZE_M,
        "tile_id_format": "e6933-4km-x{signed_zero_padded_x_index}-y{signed_zero_padded_y_index}",
    }
    if definition["grid_contract"] != expected_grid:
        raise BlindTileFrameError("EPSG:6933 4 km grid contract changed")
    expected_eligibility = {
        "antarctica_excluded": True,
        "eligible_when": "positive projected-area intersection with the union of non-Antarctic Natural Earth land",
        "natural_earth_artifact_bytes": NATURAL_EARTH_EXPECTED_BYTES,
        "natural_earth_artifact_sha256": NATURAL_EARTH_SHA256,
        "natural_earth_version": NATURAL_EARTH_VERSION,
        "positive_land_intersection_required": True,
        "projected_area_crs": "EPSG:6933",
    }
    if definition["eligibility_contract"] != expected_eligibility:
        raise BlindTileFrameError("land eligibility contract changed")
    expected_assignment = {
        "all_positive_country_overlaps_retained": True,
        "country_assignment_method": COUNTRY_ASSIGNMENT_METHOD,
        "country_tie_break": "lexicographically smallest country_key",
        "macroregion_assignment_method": MACROREGION_ASSIGNMENT_METHOD,
        "macroregion_order": list(MACROREGIONS),
        "macroregion_tie_break": "lexicographically smallest macroregion",
        "macroregions": list(MACROREGIONS),
    }
    if definition["assignment_contract"] != expected_assignment:
        raise BlindTileFrameError("country or macroregion assignment contract changed")
    expected_strata = {
        "classification_precedence": list(reversed(STRATA)),
        "definitions": {
            "background": "no urban, industrial, or grid signal",
            "industrial_and_grid": "industrial and grid signals are both true; urban may coexist",
            "industrial_xor_grid": "exactly one of industrial or grid is true; urban may coexist",
            "urban_built": "urban is true and industrial and grid are both false",
        },
        "ghsl_built_surface_threshold_fraction_of_tile_land": {
            "denominator": 200,
            "numerator": 1,
        },
        "ghsl_smod_urban_cluster_is_urban": True,
        "industrial_minimum_intersection_m2": 10_000,
        "osm_grid_maximum_distance_m": 5_000,
        "osm_grid_minimum_parsed_voltage_kv": 110,
        "strata": list(STRATA),
        "unknown_signal_policy": "unknown is false for classification and remains in the lower stratum",
    }
    if definition["stratum_contract"] != expected_strata:
        raise BlindTileFrameError("four-stratum contract changed")
    expected_sampling = {
        "draw_key_method": DRAW_KEY_METHOD,
        "global_quota_ceiling": sum(QUOTAS.values()) * len(MACROREGIONS),
        "inclusion_probability": "n_h/N_h stored as exact unreduced integer numerator and denominator",
        "macroregion_order": list(MACROREGIONS),
        "no_reallocation_when_stratum_is_smaller": True,
        "quota_per_macroregion_and_stratum": QUOTAS,
        "rank_order": ["draw_key", "tile_id"],
        "seed_sha256": SEED_SHA256,
        "seed_string": SEED_STRING,
        "small_stratum_policy": "census",
        "stratum_order": list(STRATA),
        "weight": "N_h/n_h stored as exact unreduced integer numerator and denominator",
    }
    if definition["sampling_contract"] != expected_sampling:
        raise BlindTileFrameError("sampling contract changed")
    if definition["semantic_policy"] != SEMANTIC_POLICY:
        raise BlindTileFrameError("no-inference policy changed")
    if definition["blockers"] != list(PRODUCTION_BLOCKERS):
        raise BlindTileFrameError("production blocker record changed")

    implementation = definition["implementation_contract"]
    if not isinstance(implementation, Mapping):
        raise BlindTileFrameError("implementation_contract must be an object")
    _require_exact_keys(
        implementation,
        {"algorithm_id", "module"},
        "implementation_contract",
    )
    if implementation["algorithm_id"] != "blind-tile-frame-preflight-v1":
        raise BlindTileFrameError("implementation algorithm identity changed")
    _checkpoint_spec(implementation["module"], "implementation module")
    _reject_forbidden_references(implementation, "implementation contract")

    inputs = definition["input_contract"]
    if not isinstance(inputs, Mapping):
        raise BlindTileFrameError("input_contract must be an object")
    _require_exact_keys(
        inputs,
        {"ghsl", "natural_earth", "normalized_fixture", "osm_auxiliary"},
        "input_contract",
    )
    natural_earth = inputs["natural_earth"]
    if not isinstance(natural_earth, Mapping):
        raise BlindTileFrameError("Natural Earth input must be an object")
    _require_exact_keys(
        natural_earth,
        {"artifact", "geometry_applied_to_fixture", "version"},
        "Natural Earth input",
    )
    checkpoint = _checkpoint_spec(natural_earth["artifact"], "Natural Earth artifact")
    if (
        natural_earth["version"] != NATURAL_EARTH_VERSION
        or natural_earth["geometry_applied_to_fixture"] is not False
        or checkpoint["bytes"] != NATURAL_EARTH_EXPECTED_BYTES
        or checkpoint["sha256"] != NATURAL_EARTH_SHA256
    ):
        raise BlindTileFrameError("Natural Earth input pin changed")
    _checkpoint_spec(inputs["normalized_fixture"], "normalized fixture input")
    for name in ("ghsl", "osm_auxiliary"):
        source_input = inputs[name]
        if not isinstance(source_input, Mapping):
            raise BlindTileFrameError(f"{name} input must be an object")
        _require_exact_keys(
            source_input,
            {"available", "artifacts", "derived_values_in_fixture"},
            f"{name} input",
        )
        if (
            source_input["available"] is not False
            or source_input["artifacts"] != []
            or source_input["derived_values_in_fixture"] is not False
        ):
            raise BlindTileFrameError(f"{name} must remain absent in this preflight")
    _reject_forbidden_references(inputs, "input contract")
    return definition, raw, source


def _resolve_input(definition_path: Path, spec: Mapping[str, Any], label: str) -> Path:
    raw_path = spec["path"]
    supplied = Path(raw_path)
    if supplied.is_absolute():
        raise BlindTileFrameError(f"{label} path must be relative")
    project_root = definition_path.parent.parent.resolve()
    resolved = (definition_path.parent / supplied).resolve()
    if resolved != project_root and project_root not in resolved.parents:
        raise BlindTileFrameError(f"{label} path escapes the project root")
    _reject_forbidden_references(str(resolved), label)
    if resolved.is_symlink() or not resolved.is_file():
        raise BlindTileFrameError(f"{label} must be a regular file")
    actual = _checkpoint_file(resolved)
    if actual != {"bytes": spec["bytes"], "sha256": spec["sha256"]}:
        raise BlindTileFrameError(f"{label} hash or byte count changed")
    return resolved


def tile_id(x_index: int, y_index: int) -> str:
    if (
        not isinstance(x_index, int)
        or isinstance(x_index, bool)
        or not isinstance(y_index, int)
        or isinstance(y_index, bool)
        or not (-999_999 <= x_index <= 999_999)
        or not (-999_999 <= y_index <= 999_999)
    ):
        raise BlindTileFrameError("tile indices must be six-digit signed integers")
    return f"e6933-4km-x{x_index:+07d}-y{y_index:+07d}"


def draw_key(tile_identifier: str) -> str:
    if not isinstance(tile_identifier, str) or _TILE_ID_RE.fullmatch(tile_identifier) is None:
        raise BlindTileFrameError("draw-key tile_id is invalid")
    return hashlib.sha256(
        SEED_SHA256.encode("ascii") + b"\0" + tile_identifier.encode("ascii")
    ).hexdigest()


def classify_stratum(
    *,
    land_intersection_area_m2: int,
    ghsl_built_surface_2020_m2: int | None,
    ghsl_smod_urban_cluster: bool | None,
    osm_stable_industrial_intersection_m2_after_exclusions: int | None,
    osm_stable_grid_min_distance_m: int | None,
    osm_stable_grid_max_parsed_voltage_kv: int | None,
) -> tuple[str, dict[str, Any]]:
    land_area = _require_positive_integer(
        land_intersection_area_m2, "land intersection area"
    )
    nullable_nonnegative = {
        "ghsl_built_surface_2020_m2": ghsl_built_surface_2020_m2,
        "osm_stable_industrial_intersection_m2_after_exclusions": (
            osm_stable_industrial_intersection_m2_after_exclusions
        ),
        "osm_stable_grid_min_distance_m": osm_stable_grid_min_distance_m,
        "osm_stable_grid_max_parsed_voltage_kv": (
            osm_stable_grid_max_parsed_voltage_kv
        ),
    }
    for label, value in nullable_nonnegative.items():
        if value is not None:
            _require_nonnegative_integer(value, label)
    if ghsl_built_surface_2020_m2 is not None and ghsl_built_surface_2020_m2 > land_area:
        raise BlindTileFrameError("GHSL built surface exceeds tile land area")
    if (
        osm_stable_industrial_intersection_m2_after_exclusions is not None
        and osm_stable_industrial_intersection_m2_after_exclusions > land_area
    ):
        raise BlindTileFrameError("OSM industrial intersection exceeds tile land area")
    if ghsl_smod_urban_cluster not in {None, False, True}:
        raise BlindTileFrameError("GHS-SMOD urban-cluster value must be boolean or null")
    if (osm_stable_grid_min_distance_m is None) != (
        osm_stable_grid_max_parsed_voltage_kv is None
    ):
        raise BlindTileFrameError("OSM grid distance and voltage must be known together")

    built_urban = (
        ghsl_built_surface_2020_m2 is not None
        and ghsl_built_surface_2020_m2 * 200 >= land_area
    )
    urban = built_urban or ghsl_smod_urban_cluster is True
    industrial = (
        osm_stable_industrial_intersection_m2_after_exclusions is not None
        and osm_stable_industrial_intersection_m2_after_exclusions >= 10_000
    )
    grid = (
        osm_stable_grid_min_distance_m is not None
        and osm_stable_grid_max_parsed_voltage_kv is not None
        and osm_stable_grid_min_distance_m <= 5_000
        and osm_stable_grid_max_parsed_voltage_kv >= 110
    )
    if industrial and grid:
        stratum = "industrial_and_grid"
    elif industrial != grid:
        stratum = "industrial_xor_grid"
    elif urban:
        stratum = "urban_built"
    else:
        stratum = "background"
    unknown = sorted(
        label for label, value in nullable_nonnegative.items() if value is None
    )
    if ghsl_smod_urban_cluster is None:
        unknown.append("ghsl_smod_urban_cluster")
        unknown.sort()
    return stratum, {
        "built_surface_threshold_met": built_urban,
        "grid": grid,
        "industrial": industrial,
        "unknown_signal_fields": unknown,
        "urban": urban,
    }


def _normalize_country_overlaps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise BlindTileFrameError("eligible cell must retain positive country overlaps")
    overlaps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise BlindTileFrameError("country overlap must be an object")
        _require_exact_keys(
            item,
            {
                "area_m2",
                "country_iso_a3",
                "country_key",
                "country_name",
                "macroregion",
                "natural_earth_feature_id",
            },
            f"country overlap {index}",
        )
        key = item["country_key"]
        if not isinstance(key, str) or _COUNTRY_KEY_RE.fullmatch(key) is None:
            raise BlindTileFrameError("country_key is invalid")
        if key in seen:
            raise BlindTileFrameError("country overlaps contain a duplicate key")
        seen.add(key)
        iso = item["country_iso_a3"]
        if not isinstance(iso, str) or re.fullmatch(r"[A-Z]{3}", iso) is None:
            raise BlindTileFrameError("fixture country ISO A3 is invalid")
        if key != iso:
            raise BlindTileFrameError("fixture country_key must equal ISO A3")
        if not isinstance(item["country_name"], str) or not item["country_name"]:
            raise BlindTileFrameError("country name is required")
        if item["macroregion"] not in MACROREGIONS:
            raise BlindTileFrameError("country overlap macroregion is unsupported")
        if (
            not isinstance(item["natural_earth_feature_id"], str)
            or not item["natural_earth_feature_id"]
        ):
            raise BlindTileFrameError("Natural Earth feature ID is required")
        _require_positive_integer(item["area_m2"], "country overlap area")
        overlaps.append(dict(item))
    overlaps.sort(key=lambda row: row["country_key"])
    return overlaps


def _assigned_country(overlaps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    winner = min(overlaps, key=lambda row: (-row["area_m2"], row["country_key"]))
    return {
        "area_m2": winner["area_m2"],
        "country_iso_a3": winner["country_iso_a3"],
        "country_key": winner["country_key"],
        "country_name": winner["country_name"],
        "macroregion": winner["macroregion"],
        "natural_earth_feature_id": winner["natural_earth_feature_id"],
    }


def _macroregion_overlaps(
    overlaps: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    for overlap in overlaps:
        totals[overlap["macroregion"]] += overlap["area_m2"]
    return [
        {"area_m2": totals[macroregion], "macroregion": macroregion}
        for macroregion in sorted(totals)
    ]


def _fixture_auxiliary(stratum: str, sequence: int) -> dict[str, Any]:
    if stratum == "background" and sequence == 0:
        return {
            "ghsl_built_surface_2020_m2": None,
            "ghsl_smod_urban_cluster": None,
            "osm_stable_grid_max_parsed_voltage_kv": None,
            "osm_stable_grid_min_distance_m": None,
            "osm_stable_industrial_intersection_m2_after_exclusions": None,
        }
    if stratum == "background":
        return {
            "ghsl_built_surface_2020_m2": 0,
            "ghsl_smod_urban_cluster": False,
            "osm_stable_grid_max_parsed_voltage_kv": 110,
            "osm_stable_grid_min_distance_m": 6_000,
            "osm_stable_industrial_intersection_m2_after_exclusions": 0,
        }
    if stratum == "urban_built":
        return {
            "ghsl_built_surface_2020_m2": 80_000,
            "ghsl_smod_urban_cluster": False,
            "osm_stable_grid_max_parsed_voltage_kv": 110,
            "osm_stable_grid_min_distance_m": 6_000,
            "osm_stable_industrial_intersection_m2_after_exclusions": 0,
        }
    if stratum == "industrial_xor_grid":
        return {
            "ghsl_built_surface_2020_m2": 80_000 if sequence % 3 == 0 else 0,
            "ghsl_smod_urban_cluster": False,
            "osm_stable_grid_max_parsed_voltage_kv": 110,
            "osm_stable_grid_min_distance_m": 6_000 if sequence % 2 == 0 else 4_000,
            "osm_stable_industrial_intersection_m2_after_exclusions": (
                12_000 if sequence % 2 == 0 else 0
            ),
        }
    if stratum == "industrial_and_grid":
        return {
            "ghsl_built_surface_2020_m2": 0,
            "ghsl_smod_urban_cluster": False,
            "osm_stable_grid_max_parsed_voltage_kv": 220,
            "osm_stable_grid_min_distance_m": 4_000,
            "osm_stable_industrial_intersection_m2_after_exclusions": 12_000,
        }
    raise BlindTileFrameError("fixture requested an unsupported stratum")


def _fixture_country_overlaps(
    countries: Sequence[Mapping[str, Any]], macroregion: str, sequence: int
) -> list[dict[str, Any]]:
    if len(countries) != 2:
        raise BlindTileFrameError("fixture country profile must contain exactly two rows")
    areas = (6_000_000, 6_000_000) if sequence == 0 else (
        (9_000_000, 3_000_000) if sequence % 2 == 0 else (12_000_000, 0)
    )
    overlaps = []
    for country, area in zip(countries, areas, strict=True):
        if area == 0:
            continue
        overlaps.append(
            {
                "area_m2": area,
                "country_iso_a3": country["country_iso_a3"],
                "country_key": country["country_iso_a3"],
                "country_name": country["country_name"],
                "macroregion": macroregion,
                "natural_earth_feature_id": (
                    f"synthetic-fixture-{country['country_iso_a3'].lower()}"
                ),
            }
        )
    return _normalize_country_overlaps(overlaps)


def _frame_row(
    *,
    x_index: int,
    y_index: int,
    country_overlaps: Sequence[Mapping[str, Any]],
    auxiliary_raw: Mapping[str, Any],
) -> dict[str, Any]:
    identifier = tile_id(x_index, y_index)
    overlaps = _normalize_country_overlaps(list(country_overlaps))
    macroregion_overlaps = _macroregion_overlaps(overlaps)
    macroregion_winner = min(
        macroregion_overlaps, key=lambda row: (-row["area_m2"], row["macroregion"])
    )["macroregion"]
    land_area = 12_000_000
    stratum, derived = classify_stratum(
        land_intersection_area_m2=land_area,
        **auxiliary_raw,
    )
    auxiliary = {**dict(auxiliary_raw), **derived}
    return {
        "assigned_country": _assigned_country(overlaps),
        "assigned_macroregion": macroregion_winner,
        "auxiliary": auxiliary,
        "bounds_m": [
            x_index * TILE_SIZE_M,
            y_index * TILE_SIZE_M,
            (x_index + 1) * TILE_SIZE_M,
            (y_index + 1) * TILE_SIZE_M,
        ],
        "country_assignment_method": COUNTRY_ASSIGNMENT_METHOD,
        "country_overlaps": overlaps,
        "crs_epsg": CRS_EPSG,
        "eligible": True,
        "fixture_only": True,
        "macroregion_assignment_method": MACROREGION_ASSIGNMENT_METHOD,
        "macroregion_overlaps": macroregion_overlaps,
        "non_antarctic_land_intersection_area_m2": land_area,
        "schema_version": SCHEMA_VERSION,
        "selection_is_data_centre_evidence": False,
        "stratum": stratum,
        "tile_area_m2": TILE_AREA_M2,
        "tile_id": identifier,
        "tile_size_m": TILE_SIZE_M,
        "x_index": x_index,
        "y_index": y_index,
    }


def _load_fixture(path: Path) -> dict[str, Any]:
    fixture, raw = _json_object(path, "blind-tile preflight fixture")
    if raw != canonical_json(fixture):
        raise BlindTileFrameError("preflight fixture must be canonical pretty JSON")
    _reject_forbidden_references(fixture, "preflight fixture")
    _require_exact_keys(
        fixture,
        {
            "country_profiles",
            "fixture_id",
            "fixture_only",
            "format",
            "generation_contract",
            "macroregion_profiles",
            "schema_version",
        },
        "preflight fixture",
    )
    if (
        fixture["schema_version"] != SCHEMA_VERSION
        or fixture["format"] != FIXTURE_INPUT_FORMAT
        or fixture["fixture_only"] is not True
        or fixture["fixture_id"]
        != "blind-tile-frame-preflight-fixture-2026-07-19-v1"
    ):
        raise BlindTileFrameError("preflight fixture identity changed")
    expected_generation_contract = {
        "country_overlap_pattern": "sequence 0 has an equal-area two-country tie; other even sequences retain 9000000/3000000 m2 overlaps; odd sequences retain one 12000000 m2 overlap",
        "not_derived_from_ghsl": True,
        "not_derived_from_natural_earth_geometry": True,
        "not_derived_from_osm": True,
        "purpose": "exercise deterministic frame, stratum, assignment, ranking, and inclusion-probability contracts only",
        "tile_ids_have_no_geographic_meaning": True,
    }
    if fixture["generation_contract"] != expected_generation_contract:
        raise BlindTileFrameError("fixture generation disclosure changed")
    countries = fixture["country_profiles"]
    if not isinstance(countries, Mapping) or set(countries) != set(MACROREGIONS):
        raise BlindTileFrameError("fixture country profiles changed")
    for macroregion, rows in countries.items():
        if not isinstance(rows, list) or len(rows) != 2:
            raise BlindTileFrameError("fixture country profile must have two rows")
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise BlindTileFrameError("fixture country row must be an object")
            _require_exact_keys(
                row, {"country_iso_a3", "country_name"}, "fixture country row"
            )
            iso = row["country_iso_a3"]
            if not isinstance(iso, str) or re.fullmatch(r"[A-Z]{3}", iso) is None:
                raise BlindTileFrameError("fixture country ISO is invalid")
            if iso in seen:
                raise BlindTileFrameError("fixture country ISO is duplicated")
            seen.add(iso)
            if not isinstance(row["country_name"], str) or not row["country_name"]:
                raise BlindTileFrameError("fixture country name is required")
    profiles = fixture["macroregion_profiles"]
    if not isinstance(profiles, list) or len(profiles) != len(MACROREGIONS):
        raise BlindTileFrameError("fixture macroregion profile count changed")
    if [profile.get("macroregion") for profile in profiles] != list(MACROREGIONS):
        raise BlindTileFrameError("fixture macroregion order changed")
    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise BlindTileFrameError("fixture macroregion profile must be an object")
        _require_exact_keys(
            profile,
            {"macroregion", "stratum_counts", "x_index_origin", "y_index"},
            "fixture macroregion profile",
        )
        counts = profile["stratum_counts"]
        if not isinstance(counts, Mapping) or set(counts) != set(STRATA):
            raise BlindTileFrameError("fixture stratum-count schema changed")
        for stratum, count in counts.items():
            _require_positive_integer(count, f"fixture {stratum} count")
        for key in ("x_index_origin", "y_index"):
            if not isinstance(profile[key], int) or isinstance(profile[key], bool):
                raise BlindTileFrameError(f"fixture {key} must be an integer")
    return fixture


def _fixture_frame(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    countries = fixture["country_profiles"]
    for profile in fixture["macroregion_profiles"]:
        macroregion = profile["macroregion"]
        x_index = profile["x_index_origin"]
        for stratum in STRATA:
            count = profile["stratum_counts"][stratum]
            for sequence in range(count):
                cell = _frame_row(
                    x_index=x_index,
                    y_index=profile["y_index"],
                    country_overlaps=_fixture_country_overlaps(
                        countries[macroregion], macroregion, sequence
                    ),
                    auxiliary_raw=_fixture_auxiliary(stratum, sequence),
                )
                if cell["stratum"] != stratum:
                    raise BlindTileFrameError("fixture signal profile classified unexpectedly")
                cells.append(cell)
                x_index += 1
    cells.sort(key=lambda row: row["tile_id"])
    identifiers = [row["tile_id"] for row in cells]
    if len(identifiers) != len(set(identifiers)):
        raise BlindTileFrameError("fixture produced duplicate tile IDs")
    return cells


def _validate_frame_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise BlindTileFrameError("frame row must be an object")
    _require_exact_keys(
        row,
        {
            "assigned_country",
            "assigned_macroregion",
            "auxiliary",
            "bounds_m",
            "country_assignment_method",
            "country_overlaps",
            "crs_epsg",
            "eligible",
            "fixture_only",
            "macroregion_assignment_method",
            "macroregion_overlaps",
            "non_antarctic_land_intersection_area_m2",
            "schema_version",
            "selection_is_data_centre_evidence",
            "stratum",
            "tile_area_m2",
            "tile_id",
            "tile_size_m",
            "x_index",
            "y_index",
        },
        "frame row",
    )
    if (
        row["schema_version"] != SCHEMA_VERSION
        or row["crs_epsg"] != CRS_EPSG
        or row["tile_size_m"] != TILE_SIZE_M
        or row["tile_area_m2"] != TILE_AREA_M2
        or row["eligible"] is not True
        or row["fixture_only"] is not True
        or row["selection_is_data_centre_evidence"] is not False
        or row["country_assignment_method"] != COUNTRY_ASSIGNMENT_METHOD
        or row["macroregion_assignment_method"] != MACROREGION_ASSIGNMENT_METHOD
    ):
        raise BlindTileFrameError("frame row fixed semantics changed")
    x_index = row["x_index"]
    y_index = row["y_index"]
    if tile_id(x_index, y_index) != row["tile_id"]:
        raise BlindTileFrameError("frame tile ID does not match integer indices")
    expected_bounds = [
        x_index * TILE_SIZE_M,
        y_index * TILE_SIZE_M,
        (x_index + 1) * TILE_SIZE_M,
        (y_index + 1) * TILE_SIZE_M,
    ]
    if row["bounds_m"] != expected_bounds:
        raise BlindTileFrameError("frame bounds do not match integer grid indices")
    land_area = _require_positive_integer(
        row["non_antarctic_land_intersection_area_m2"], "frame land area"
    )
    if land_area > TILE_AREA_M2:
        raise BlindTileFrameError("frame land intersection exceeds cell area")
    overlaps = _normalize_country_overlaps(row["country_overlaps"])
    if row["country_overlaps"] != overlaps:
        raise BlindTileFrameError("country overlaps must be sorted by country_key")
    if row["assigned_country"] != _assigned_country(overlaps):
        raise BlindTileFrameError("country greatest-overlap assignment changed")
    macroregion_overlaps = _macroregion_overlaps(overlaps)
    if row["macroregion_overlaps"] != macroregion_overlaps:
        raise BlindTileFrameError("macroregion overlaps were not retained exactly")
    macroregion = min(
        macroregion_overlaps, key=lambda item: (-item["area_m2"], item["macroregion"])
    )["macroregion"]
    if row["assigned_macroregion"] != macroregion:
        raise BlindTileFrameError("macroregion greatest-overlap assignment changed")
    auxiliary = row["auxiliary"]
    if not isinstance(auxiliary, Mapping):
        raise BlindTileFrameError("frame auxiliary must be an object")
    raw_names = {
        "ghsl_built_surface_2020_m2",
        "ghsl_smod_urban_cluster",
        "osm_stable_grid_max_parsed_voltage_kv",
        "osm_stable_grid_min_distance_m",
        "osm_stable_industrial_intersection_m2_after_exclusions",
    }
    derived_names = {
        "built_surface_threshold_met",
        "grid",
        "industrial",
        "unknown_signal_fields",
        "urban",
    }
    _require_exact_keys(auxiliary, raw_names | derived_names, "frame auxiliary")
    stratum, derived = classify_stratum(
        land_intersection_area_m2=land_area,
        **{name: auxiliary[name] for name in raw_names},
    )
    if {name: auxiliary[name] for name in derived_names} != derived:
        raise BlindTileFrameError("frame derived signal flags changed")
    if row["stratum"] != stratum:
        raise BlindTileFrameError("frame stratum does not match auxiliary signals")
    return dict(row)


def _grouped_cells(
    cells: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {
        (macroregion, stratum): []
        for macroregion in MACROREGIONS
        for stratum in STRATA
    }
    for cell in cells:
        key = (cell["assigned_macroregion"], cell["stratum"])
        if key not in grouped:
            raise BlindTileFrameError("cell has unsupported macroregion or stratum")
        grouped[key].append(cell)
    return grouped


def _sample_rows(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped = _grouped_cells(cells)
    for macroregion in MACROREGIONS:
        for stratum in STRATA:
            population = grouped[(macroregion, stratum)]
            population_size = len(population)
            sample_size = min(population_size, QUOTAS[stratum])
            ranked = sorted(
                population, key=lambda cell: (draw_key(cell["tile_id"]), cell["tile_id"])
            )
            for rank, cell in enumerate(ranked[:sample_size], start=1):
                rows.append(
                    {
                        "design_weight": {
                            "denominator": sample_size,
                            "numerator": population_size,
                        },
                        "draw_key": draw_key(cell["tile_id"]),
                        "inclusion_probability": {
                            "denominator": population_size,
                            "numerator": sample_size,
                        },
                        "macroregion": macroregion,
                        "population_size": population_size,
                        "quota": QUOTAS[stratum],
                        "rank_within_stratum": rank,
                        "sample_size": sample_size,
                        "schema_version": SCHEMA_VERSION,
                        "selection_is_data_centre_evidence": False,
                        "stratum": stratum,
                        "tile_id": cell["tile_id"],
                    }
                )
    return rows


def _strata_document(
    cells: Sequence[Mapping[str, Any]], sample_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    grouped = _grouped_cells(cells)
    selected = defaultdict(int)
    for row in sample_rows:
        selected[(row["macroregion"], row["stratum"])] += 1
    groups = []
    for macroregion in MACROREGIONS:
        for stratum in STRATA:
            population_size = len(grouped[(macroregion, stratum)])
            sample_size = selected[(macroregion, stratum)]
            groups.append(
                {
                    "census": sample_size == population_size,
                    "macroregion": macroregion,
                    "population_size": population_size,
                    "quota": QUOTAS[stratum],
                    "sample_size": sample_size,
                    "shortfall_from_quota": QUOTAS[stratum] - sample_size,
                    "stratum": stratum,
                }
            )
    return {
        "fixture_only": True,
        "global_quota_ceiling": sum(QUOTAS.values()) * len(MACROREGIONS),
        "groups": groups,
        "macroregion_order": list(MACROREGIONS),
        "no_reallocation": True,
        "quota_per_macroregion_and_stratum": QUOTAS,
        "schema_version": SCHEMA_VERSION,
        "selected_cell_count": len(sample_rows),
        "stratum_order": list(STRATA),
        "total_eligible_cell_count": len(cells),
    }


def _coverage_document(
    cells: Sequence[Mapping[str, Any]], sample_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "blockers": list(PRODUCTION_BLOCKERS),
        "candidate_independent": True,
        "claims": {
            "complete_global_land_frame": False,
            "data_centre_recall_measured": False,
            "production_960_tile_sample_built": False,
            "semi_analysis_parity_claimed": False,
        },
        "eligible_frame_cell_count": len(cells),
        "fixture_only": True,
        "input_status": {
            "ghsl_auxiliary_available": False,
            "natural_earth_artifact_hash_verified_at_build": True,
            "natural_earth_geometry_applied": False,
            "osm_auxiliary_available": False,
            "synthetic_fixture_values_used": True,
        },
        "macroregions_represented": list(MACROREGIONS),
        "production_frame_built": False,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "selected_cell_count": len(sample_rows),
        "semantic_policy": SEMANTIC_POLICY,
        "strata_represented": list(STRATA),
        "target_quota_ceiling": sum(QUOTAS.values()) * len(MACROREGIONS),
    }


def _readme_document(
    cells: Sequence[Mapping[str, Any]], sample_rows: Sequence[Mapping[str, Any]]
) -> bytes:
    text = f"""# Blind global tile frame preflight

This immutable bundle is a **synthetic contract preflight**, not a production global frame and not a list of data centres. It contains {len(cells)} eligible fixture cells and {len(sample_rows)} selected fixture cells solely to exercise deterministic release behavior.

The production design uses an integer-indexed 4 km grid in EPSG:6933. A cell is eligible only when its projected intersection with the union of Natural Earth v5.1.1 non-Antarctic land has positive area. All positive country overlaps are retained; country and six-macroregion labels use greatest projected overlap with the declared lexical tie-breaks.

Within every macroregion, the mutually exclusive quotas are background 16, urban_built 24, industrial_xor_grid 40, and industrial_and_grid 80. A smaller stratum is a census and its unused quota is not reallocated. Ranking is `{DRAW_KEY_METHOD}` using seed hash `{SEED_SHA256}`. Every sampled row stores exact unreduced `n_h/N_h` inclusion-probability and `N_h/n_h` weight integers.

The four strata require frozen GHS-BUILT-S 2020, GHS-SMOD, and source-policy-compliant stable OSM industrial/grid auxiliaries. Those auxiliary artifacts are absent here. The fixture values are synthetic and are explicitly not derived from GHSL, OSM, or Natural Earth geometry. The pinned Natural Earth artifact was hash-verified, but its geometry was not used to make these fixture cells.

No Atlas ledger, construction master/map, satellite queue, OSM structural shortlist, or candidate-fusion artifact is an input. Selection does not infer data-centre presence, identity, lifecycle, type, operator, workload, power, energy, capacity, or PUE, and this bundle is not eligible for automatic downstream import.

Production remains blocked until the three blockers in `coverage.json` are resolved and a separate production frame definition is frozen before imagery review begins.
"""
    return text.encode("utf-8")


def _attribution_document() -> bytes:
    return (
        "Natural Earth 1:10m Admin-0 Countries v5.1.1 is public domain. The exact "
        f"artifact pin is SHA-256 {NATURAL_EARTH_SHA256}. Its bytes were verified "
        "during this preflight build, but its geometry was not applied to the synthetic "
        "fixture cells. No GHSL or OSM-derived values are included. All cell values are "
        "synthetic contract-test data with no geographic or data-centre meaning.\n"
    ).encode("utf-8")


def _deterministic_gzip(raw: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    body = compressor.compress(raw) + compressor.flush()
    header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    trailer = struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)
    return header + body + trailer


def _frame_bytes(cells: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(cell) for cell in cells)


def _sample_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


def _payload_documents(
    definition_raw: bytes, cells: Sequence[Mapping[str, Any]]
) -> dict[str, bytes]:
    sample_rows = _sample_rows(cells)
    return {
        ATTRIBUTION_FILENAME: _attribution_document(),
        COVERAGE_FILENAME: canonical_json(_coverage_document(cells, sample_rows)),
        DEFINITION_FILENAME: definition_raw,
        FRAME_FILENAME: _deterministic_gzip(_frame_bytes(cells)),
        README_FILENAME: _readme_document(cells, sample_rows),
        SAMPLE_FILENAME: _sample_bytes(sample_rows),
        STRATA_FILENAME: canonical_json(_strata_document(cells, sample_rows)),
    }


def _manifest_document(payloads: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "file_count": len(payloads),
        "files": {
            name: _checkpoint_bytes(payloads[name]) for name in sorted(payloads)
        },
        "fixture_only": True,
        "format": RELEASE_FORMAT,
        "production_frame_built": False,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _write_new_file(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(raw)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _freeze_bundle(path: Path) -> None:
    for child in path.iterdir():
        child.chmod(0o444)
    path.chmod(0o555)


def is_frozen_release(path: str | Path) -> bool:
    root = Path(path)
    if not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    return all(
        child.is_file()
        and not child.is_symlink()
        and stat.S_IMODE(child.stat().st_mode) == 0o444
        for child in root.iterdir()
    )


def build_preflight_bundle(
    output: str | Path,
    *,
    definition_path: str | Path,
    freeze: bool = True,
) -> dict[str, Any]:
    definition, definition_raw, source_definition_path = _load_definition(
        definition_path
    )
    inputs = definition["input_contract"]
    _resolve_input(
        source_definition_path,
        definition["implementation_contract"]["module"],
        "implementation module",
    )
    _resolve_input(
        source_definition_path,
        inputs["natural_earth"]["artifact"],
        "Natural Earth artifact",
    )
    fixture_path = _resolve_input(
        source_definition_path,
        inputs["normalized_fixture"],
        "normalized fixture input",
    )
    fixture = _load_fixture(fixture_path)
    cells = _fixture_frame(fixture)
    payloads = _payload_documents(definition_raw, cells)
    manifest_raw = canonical_json(_manifest_document(payloads))
    sidecar = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    destination = Path(output)
    if destination.exists() or destination.is_symlink():
        raise BlindTileFrameError("output path already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise BlindTileFrameError("temporary output path already exists")
    temporary.mkdir(mode=0o755)
    try:
        for name, raw in payloads.items():
            _write_new_file(temporary / name, raw)
        _write_new_file(temporary / MANIFEST_FILENAME, manifest_raw)
        _write_new_file(temporary / MANIFEST_HASH_FILENAME, sidecar)
        temporary.replace(destination)
        if freeze:
            _freeze_bundle(destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return validate_release_bundle(
        destination,
        definition_path=source_definition_path,
        require_frozen=freeze,
    )


def _load_jsonl(raw: bytes, label: str, *, maximum_rows: int = 1_000_000) -> list[Any]:
    if raw and not raw.endswith(b"\n"):
        raise BlindTileFrameError(f"{label} must end with a newline")
    rows = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if number > maximum_rows:
            raise BlindTileFrameError(f"{label} exceeds the row cap")
        if len(line) > 1_000_000:
            raise BlindTileFrameError(f"{label} line exceeds the byte cap")
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BlindTileFrameError(f"{label} line {number} is invalid JSON") from error
        if canonical_line(row).rstrip(b"\n") != line:
            raise BlindTileFrameError(f"{label} line {number} is not canonical JSON")
        rows.append(row)
    return rows


def _decompress_frame(raw: bytes) -> bytes:
    if len(raw) < 18 or raw[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff":
        raise BlindTileFrameError("frame gzip header is not deterministic")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as source:
            decompressed = source.read(16 * 1024 * 1024 + 1)
    except (EOFError, OSError) as error:
        raise BlindTileFrameError("frame gzip payload is invalid") from error
    if len(decompressed) > 16 * 1024 * 1024:
        raise BlindTileFrameError("frame gzip payload exceeds the uncompressed cap")
    return decompressed


def _regular_bundle_files(root: Path) -> set[str]:
    names: set[str] = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise BlindTileFrameError("bundle entries must be regular files")
        names.add(child.name)
    return names


def validate_release_bundle(
    path: str | Path,
    *,
    definition_path: str | Path | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise BlindTileFrameError("blind-tile bundle must be a directory")
    if _regular_bundle_files(root) != BUNDLE_FILES:
        raise BlindTileFrameError("blind-tile bundle file set changed")
    if require_frozen and not is_frozen_release(root):
        raise BlindTileFrameError("blind-tile bundle is not immutable 0555/0444")
    internal_definition, definition_raw, _ = _load_definition(
        root / DEFINITION_FILENAME
    )
    if definition_path is not None:
        external_definition, external_raw, _ = _load_definition(definition_path)
        if external_definition != internal_definition or external_raw != definition_raw:
            raise BlindTileFrameError("external and bundled definitions differ")

    manifest, manifest_raw = _json_object(root / MANIFEST_FILENAME, "manifest")
    if manifest_raw != canonical_json(manifest):
        raise BlindTileFrameError("manifest must be canonical pretty JSON")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("fixture_only") is not True
        or manifest.get("production_frame_built") is not False
        or manifest.get("file_count") != len(BUNDLE_PAYLOAD_FILES)
        or set(manifest.get("files", {})) != BUNDLE_PAYLOAD_FILES
    ):
        raise BlindTileFrameError("manifest identity or file inventory changed")
    for name in BUNDLE_PAYLOAD_FILES:
        checkpoint = manifest["files"].get(name)
        if not isinstance(checkpoint, Mapping):
            raise BlindTileFrameError("manifest file checkpoint is missing")
        _require_exact_keys(checkpoint, {"bytes", "sha256"}, "manifest checkpoint")
        if _checkpoint_file(root / name) != checkpoint:
            raise BlindTileFrameError(f"bundle payload changed: {name}")
    expected_sidecar = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if (root / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise BlindTileFrameError("manifest SHA-256 sidecar changed")

    frame_raw = _decompress_frame((root / FRAME_FILENAME).read_bytes())
    raw_frame_rows = _load_jsonl(frame_raw, "frame cells")
    cells = [_validate_frame_row(row) for row in raw_frame_rows]
    identifiers = [cell["tile_id"] for cell in cells]
    if identifiers != sorted(identifiers) or len(identifiers) != len(set(identifiers)):
        raise BlindTileFrameError("frame cells must have unique sorted tile IDs")
    sample_raw = (root / SAMPLE_FILENAME).read_bytes()
    sample_rows = _load_jsonl(sample_raw, "sample rows")
    expected_sample_rows = _sample_rows(cells)
    if sample_rows != expected_sample_rows:
        raise BlindTileFrameError("sample rows do not reproduce from the frozen seed")
    expected_strata = canonical_json(_strata_document(cells, expected_sample_rows))
    if (root / STRATA_FILENAME).read_bytes() != expected_strata:
        raise BlindTileFrameError("strata summary does not reproduce")
    expected_coverage = canonical_json(_coverage_document(cells, expected_sample_rows))
    if (root / COVERAGE_FILENAME).read_bytes() != expected_coverage:
        raise BlindTileFrameError("coverage disclosure does not reproduce")
    if (root / README_FILENAME).read_bytes() != _readme_document(
        cells, expected_sample_rows
    ):
        raise BlindTileFrameError("README does not reproduce")
    if (root / ATTRIBUTION_FILENAME).read_bytes() != _attribution_document():
        raise BlindTileFrameError("attribution does not reproduce")
    return {
        "coverage": json.loads(expected_coverage),
        "definition": internal_definition,
        "frame_cell_count": len(cells),
        "manifest": manifest,
        "manifest_sha256": sha256_bytes(manifest_raw),
        "sample_cell_count": len(sample_rows),
        "strata": json.loads(expected_strata),
    }


__all__ = [
    "BlindTileFrameError",
    "MACROREGIONS",
    "QUOTAS",
    "RELEASE_ID",
    "SEED_SHA256",
    "STRATA",
    "build_preflight_bundle",
    "canonical_json",
    "classify_stratum",
    "draw_key",
    "is_frozen_release",
    "sha256_bytes",
    "tile_id",
    "validate_release_bundle",
]
