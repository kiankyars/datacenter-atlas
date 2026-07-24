"""Build a compact, auditable browser map from a construction-master bundle.

The map is a presentation artifact, not a new evidence or entity-resolution
layer.  It carries only a compact projection of master rows and preserves the
master's tier, review-only, and construction-verification boundaries.
"""

from __future__ import annotations

from collections import Counter
import base64
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .construction_master import validate_construction_master


SCHEMA_VERSION = 1
FORMAT = "datacenter-atlas-construction-map-index-v1"
BUNDLE_FORMAT = "datacenter-atlas-construction-map-bundle-v1"
DEFINITION_FORMAT = "datacenter-atlas-construction-map-definition-v1"
STRICT_DEFINITION_ROLE = "strict_projection_contract_consumed_by_map_builder_and_validator"
INDEX_FILENAME = "construction-map-index.json.gz"
HTML_FILENAME = "construction-map.html"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
TEMPLATE_FILENAME = "construction-map-template.html"
DATA_PLACEHOLDER = "__CONSTRUCTION_MAP_GZIP_BASE64__"
DEFAULT_VISIBLE_TIERS = ("A", "B")
BUNDLE_FILES = frozenset(
    {
        INDEX_FILENAME,
        HTML_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)
MAP_SCOPE = {
    "atlas_claims_created": False,
    "construction_arithmetic_recomputed": False,
    "entity_merges_created": False,
    "global_completeness_claimed": False,
    "map_rows_are_observations_not_unique_sites": True,
    "review_and_discovery_rows_remain_unpromoted": True,
    "unique_physical_site_count": None,
}
FIELDS = (
    "row_id",
    "tier",
    "observation_kind",
    "name",
    "address",
    "longitude",
    "latitude",
    "country",
    "country_iso_a3",
    "normalized_status",
    "reported_status",
    "reported_status_date",
    "entity_kind",
    "review_only",
    "construction_source_supported",
    "construction_verified",
    "construction_confidence",
    "construction_verification_status",
    "identity_status",
    "source_artifact_id",
    "source_release_id",
    "source_record_id",
    "source_license",
    "source_url",
    "source_publisher",
    "capacity_observations",
    "annual_energy_observations",
    "pue_observations",
    "untyped_capacity_statements",
    "operating_model",
    "workloads",
    "first_evidence_date",
    "last_evidence_date",
    "disposition_label",
    "evidence_scope",
    "satellite_link_count",
    "resolution_advisory_count",
)


class ConstructionMapError(ValueError):
    """Raised when map inputs, projections, or frozen outputs differ."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _compact_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _relative_path(path: Path, start: Path) -> str:
    return os.path.relpath(path, start=start).replace(os.sep, "/")


def _json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMapError(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionMapError(f"{label} must be a JSON object")
    return value, raw


def _canonical_json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    value, raw = _json_file(path, label)
    if raw != _canonical_json(value):
        raise ConstructionMapError(f"{label} must be canonical JSON")
    return value, raw


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConstructionMapError(f"{label} must be text or null")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConstructionMapError(f"{label} must be boolean")
    return value


def _number_or_none(value: Any, label: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConstructionMapError(f"{label} must be numeric or null")
    if not math.isfinite(float(value)):
        raise ConstructionMapError(f"{label} must be finite")
    return value


def _metric_rows(value: Any, label: str) -> list[list[Any]]:
    if not isinstance(value, list):
        raise ConstructionMapError(f"{label} must be a list")
    result: list[list[Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ConstructionMapError(f"{label}[{index}] must be an object")
        result.append(
            [
                _optional_text(item.get("metric"), f"{label}[{index}].metric"),
                _number_or_none(item.get("value"), f"{label}[{index}].value"),
                _number_or_none(item.get("low"), f"{label}[{index}].low"),
                _number_or_none(item.get("high"), f"{label}[{index}].high"),
                _optional_text(item.get("unit"), f"{label}[{index}].unit"),
                _optional_text(item.get("stage"), f"{label}[{index}].stage"),
                _optional_text(
                    item.get("target_date"), f"{label}[{index}].target_date"
                ),
                _optional_text(item.get("method"), f"{label}[{index}].method"),
                _number_or_none(
                    item.get("confidence"), f"{label}[{index}].confidence"
                ),
            ]
        )
    return result


def _workloads(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ConstructionMapError("workload_observations must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or not isinstance(item.get("workload"), str):
            raise ConstructionMapError(
                f"workload_observations[{index}] must contain workload text"
            )
        result.append(str(item["workload"]))
    return result


def _operating_model(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConstructionMapError("operating_model_observation must be an object or null")
    candidate = value.get(
        "value", value.get("operating_model", value.get("model"))
    )
    return _optional_text(candidate, "operating_model")


def _source_publisher(row: Mapping[str, Any]) -> str | None:
    evidence = row.get("source_evidence")
    if not isinstance(evidence, list):
        raise ConstructionMapError("source_evidence must be a list")
    for item in evidence:
        if isinstance(item, Mapping) and isinstance(item.get("publisher"), str):
            return str(item["publisher"])
    return None


def _project_row(row: Mapping[str, Any], line_number: int) -> list[Any] | None:
    required_objects = ("entity", "lifecycle", "construction", "identity", "source", "disposition")
    for key in required_objects:
        if not isinstance(row.get(key), Mapping):
            raise ConstructionMapError(f"master line {line_number} {key} must be an object")
    entity = row["entity"]
    latitude = entity.get("latitude")
    longitude = entity.get("longitude")
    if latitude is None or longitude is None:
        if latitude is not None or longitude is not None:
            raise ConstructionMapError(
                f"master line {line_number} has a partial coordinate"
            )
        return None
    latitude = _number_or_none(latitude, f"master line {line_number} latitude")
    longitude = _number_or_none(longitude, f"master line {line_number} longitude")
    assert latitude is not None and longitude is not None
    if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
        raise ConstructionMapError(f"master line {line_number} coordinate is out of range")
    tier = row.get("tier")
    if tier not in {"A", "B", "C"}:
        raise ConstructionMapError(f"master line {line_number} has an invalid tier")
    row_id = row.get("row_id")
    if not isinstance(row_id, str) or not row_id:
        raise ConstructionMapError(f"master line {line_number} has no row_id")
    source = row["source"]
    construction = row["construction"]
    identity = row["identity"]
    lifecycle = row["lifecycle"]
    disposition = row["disposition"]
    return [
        row_id,
        tier,
        _optional_text(row.get("observation_kind"), "observation_kind"),
        _optional_text(entity.get("name"), "entity.name"),
        _optional_text(entity.get("address"), "entity.address"),
        longitude,
        latitude,
        _optional_text(entity.get("country"), "entity.country"),
        _optional_text(entity.get("country_iso_a3"), "entity.country_iso_a3"),
        _optional_text(lifecycle.get("normalized_status"), "normalized_status"),
        _optional_text(lifecycle.get("reported_status"), "reported_status"),
        _optional_text(lifecycle.get("reported_status_date"), "reported_status_date"),
        _optional_text(entity.get("kind"), "entity.kind"),
        _boolean(row.get("review_only"), "review_only"),
        _boolean(construction.get("source_supported"), "construction.source_supported"),
        _boolean(construction.get("verified"), "construction.verified"),
        _number_or_none(construction.get("confidence"), "construction.confidence"),
        _optional_text(
            construction.get("verification_status"), "construction.verification_status"
        ),
        _optional_text(identity.get("status"), "identity.status"),
        _optional_text(source.get("artifact_id"), "source.artifact_id"),
        _optional_text(source.get("release_id"), "source.release_id"),
        _optional_text(source.get("record_id"), "source.record_id"),
        _optional_text(source.get("source_license"), "source.source_license"),
        _optional_text(source.get("source_url"), "source.source_url"),
        _source_publisher(row),
        _metric_rows(row.get("capacity_observations"), "capacity_observations"),
        _metric_rows(
            row.get("annual_energy_observations"), "annual_energy_observations"
        ),
        _metric_rows(row.get("pue_observations"), "pue_observations"),
        row.get("untyped_capacity_statements"),
        _operating_model(row.get("operating_model_observation")),
        _workloads(row.get("workload_observations")),
        _optional_text(row.get("first_evidence_date"), "first_evidence_date"),
        _optional_text(row.get("last_evidence_date"), "last_evidence_date"),
        _optional_text(disposition.get("label"), "disposition.label"),
        _optional_text(row.get("evidence_scope"), "evidence_scope"),
        len(row.get("satellite_links", [])),
        len(row.get("resolution_advisories", [])),
    ]


def _build_index_details(
    rows: Iterable[Mapping[str, Any]],
    *,
    master_manifest: Mapping[str, Any],
    master_manifest_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    mapped: list[list[Any]] = []
    total = 0
    unmapped = 0
    unmapped_source_record_ids: list[str] = []
    tiers: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ConstructionMapError(f"master line {line_number} must be an object")
        total += 1
        projected = _project_row(row, line_number)
        if projected is None:
            unmapped += 1
            source_record_id = row["source"].get("record_id")
            if not isinstance(source_record_id, str) or not source_record_id:
                raise ConstructionMapError(
                    f"master line {line_number} missing source record ID"
                )
            unmapped_source_record_ids.append(source_record_id)
            continue
        mapped.append(projected)
        by_name = dict(zip(FIELDS, projected, strict=True))
        tiers[str(by_name["tier"])] += 1
        statuses[str(by_name["normalized_status"] or "unknown")] += 1
        kinds[str(by_name["observation_kind"] or "unknown")] += 1
        countries[str(by_name["country"] or by_name["country_iso_a3"] or "Unknown")] += 1
        sources[str(by_name["source_artifact_id"] or "unknown")] += 1
    declared_total = master_manifest.get("row_counts", {}).get("total")
    if declared_total != total:
        raise ConstructionMapError(
            f"master manifest declares {declared_total} rows but JSONL has {total}"
        )
    coverage = {
        "counts": {
            "mapped_observation_rows": len(mapped),
            "master_observation_rows": total,
            "unmapped_observation_rows": unmapped,
            "unique_physical_site_count": None,
        },
        "mapped_counts": {
            "by_country": dict(sorted(countries.items())),
            "by_normalized_status": dict(sorted(statuses.items())),
            "by_observation_kind": dict(sorted(kinds.items())),
            "by_source_artifact": dict(sorted(sources.items())),
            "by_tier": dict(sorted(tiers.items())),
        },
        "scope": MAP_SCOPE,
        "schema_version": SCHEMA_VERSION,
    }
    index = {
        "attribution": [
            "Source attribution and license are retained per observation",
            "OpenStreetMap contributors where source rows identify OpenStreetMap",
            "Contains modified Copernicus Sentinel data for linked imagery reviews",
        ],
        "fields": list(FIELDS),
        "format": FORMAT,
        "generated_at": master_manifest.get("generated_at"),
        "master_id": master_manifest.get("master_id"),
        "master_manifest_sha256": master_manifest_sha256,
        "rows": mapped,
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
    }
    return index, coverage, sorted(unmapped_source_record_ids)


def _projection_summary(
    coverage: Mapping[str, Any], unmapped_source_record_ids: Sequence[str]
) -> dict[str, Any]:
    counts = coverage["counts"]
    tiers = coverage["mapped_counts"]["by_tier"]
    mapped_by_tier = {tier: int(tiers.get(tier, 0)) for tier in ("A", "B", "C")}
    return {
        "default_visible_rows": sum(
            mapped_by_tier[tier] for tier in DEFAULT_VISIBLE_TIERS
        ),
        "default_visible_tiers": list(DEFAULT_VISIBLE_TIERS),
        "mapped_by_tier": mapped_by_tier,
        "mapped_rows": counts["mapped_observation_rows"],
        "master_rows": counts["master_observation_rows"],
        "unmapped_rows": counts["unmapped_observation_rows"],
        "unmapped_source_record_ids": list(unmapped_source_record_ids),
    }


def _validate_expected_projection(
    expected: Mapping[str, Any], observed: Mapping[str, Any]
) -> None:
    if set(expected) != {
        "default_visible_rows",
        "default_visible_tiers",
        "mapped_by_tier",
        "mapped_rows",
        "master_rows",
        "unmapped_rows",
        "unmapped_source_record_ids",
    }:
        raise ConstructionMapError("map definition projection schema changed")
    for field in (
        "default_visible_rows",
        "mapped_rows",
        "master_rows",
        "unmapped_rows",
    ):
        value = expected.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConstructionMapError(f"map definition {field} must be nonnegative")
    if expected.get("default_visible_tiers") != list(DEFAULT_VISIBLE_TIERS):
        raise ConstructionMapError("map definition default tiers changed")
    mapped_by_tier = expected.get("mapped_by_tier")
    if not isinstance(mapped_by_tier, Mapping) or set(mapped_by_tier) != {
        "A",
        "B",
        "C",
    }:
        raise ConstructionMapError("map definition tier counts changed")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in mapped_by_tier.values()
    ):
        raise ConstructionMapError("map definition tier count is invalid")
    unmapped_ids = expected.get("unmapped_source_record_ids")
    if (
        not isinstance(unmapped_ids, list)
        or any(not isinstance(value, str) or not value for value in unmapped_ids)
        or unmapped_ids != sorted(set(unmapped_ids))
    ):
        raise ConstructionMapError("map definition unmapped IDs are invalid")
    if (
        expected["mapped_rows"] + expected["unmapped_rows"]
        != expected["master_rows"]
        or sum(mapped_by_tier.values()) != expected["mapped_rows"]
        or sum(mapped_by_tier[tier] for tier in DEFAULT_VISIBLE_TIERS)
        != expected["default_visible_rows"]
        or len(unmapped_ids) != expected["unmapped_rows"]
    ):
        raise ConstructionMapError("map definition projection arithmetic differs")
    if dict(expected) != dict(observed):
        raise ConstructionMapError("map projection differs from strict definition")


def build_index(
    rows: Iterable[Mapping[str, Any]],
    *,
    master_manifest: Mapping[str, Any],
    master_manifest_sha256: str,
    expected_projection: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project validated master rows into compact arrays plus checked coverage."""

    index, coverage, unmapped_source_record_ids = _build_index_details(
        rows,
        master_manifest=master_manifest,
        master_manifest_sha256=master_manifest_sha256,
    )
    if expected_projection is not None:
        observed = _projection_summary(coverage, unmapped_source_record_ids)
        _validate_expected_projection(expected_projection, observed)
    return index, coverage


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConstructionMapError(
                    f"master JSONL line {line_number} is invalid"
                ) from error
            if not isinstance(value, dict):
                raise ConstructionMapError(
                    f"master JSONL line {line_number} must be an object"
                )
            yield value


def _derive_projection_only(
    rows: Iterable[Mapping[str, Any]], master_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    total = 0
    mapped = 0
    tiers: Counter[str] = Counter()
    unmapped_source_record_ids: list[str] = []
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ConstructionMapError(f"master line {line_number} must be an object")
        total += 1
        projected = _project_row(row, line_number)
        if projected is None:
            source_record_id = row["source"].get("record_id")
            if not isinstance(source_record_id, str) or not source_record_id:
                raise ConstructionMapError(
                    f"master line {line_number} missing source record ID"
                )
            unmapped_source_record_ids.append(source_record_id)
            continue
        mapped += 1
        tier = projected[FIELDS.index("tier")]
        tiers[str(tier)] += 1
    declared_total = master_manifest.get("row_counts", {}).get("total")
    if declared_total != total:
        raise ConstructionMapError(
            f"master manifest declares {declared_total} rows but JSONL has {total}"
        )
    mapped_by_tier = {tier: tiers[tier] for tier in ("A", "B", "C")}
    return {
        "default_visible_rows": sum(
            mapped_by_tier[tier] for tier in DEFAULT_VISIBLE_TIERS
        ),
        "default_visible_tiers": list(DEFAULT_VISIBLE_TIERS),
        "mapped_by_tier": mapped_by_tier,
        "mapped_rows": mapped,
        "master_rows": total,
        "unmapped_rows": total - mapped,
        "unmapped_source_record_ids": sorted(unmapped_source_record_ids),
    }


def derive_map_definition(
    master_directory: str | Path,
    master_definition_path: str | Path,
    *,
    definition_directory: str | Path,
) -> dict[str, Any]:
    """Derive a strict map contract from one validated frozen master."""

    master = Path(master_directory).resolve()
    master_definition = Path(master_definition_path).resolve()
    definition_parent = Path(definition_directory).resolve()
    validate_construction_master(master, definition_path=master_definition)
    master_manifest, master_manifest_raw = _canonical_json_file(
        master / MANIFEST_FILENAME, "construction-master manifest"
    )
    master_jsonl = master / "construction-master.jsonl"
    projection = _derive_projection_only(
        _read_jsonl(master_jsonl), master_manifest
    )
    _validate_expected_projection(projection, projection)
    template_path = Path(__file__).resolve().parents[1] / "web" / TEMPLATE_FILENAME
    master_id = master_manifest.get("master_id")
    generated_at = master_manifest.get("generated_at")
    if not isinstance(master_id, str) or not master_id:
        raise ConstructionMapError("construction-master ID is invalid")
    if not isinstance(generated_at, str) or not generated_at:
        raise ConstructionMapError("construction-master generated_at is invalid")
    return {
        "definition_role": STRICT_DEFINITION_ROLE,
        "expected_projection": projection,
        "format": DEFINITION_FORMAT,
        "generated_at": generated_at,
        "map_id": f"{master_id}-construction-map-v1",
        "master": {
            "definition": {
                **_checkpoint(master_definition),
                "path": _relative_path(master_definition, definition_parent),
            },
            "directory": _relative_path(master, definition_parent),
            "jsonl": {
                **_checkpoint(master_jsonl),
                "path": _relative_path(master_jsonl, definition_parent),
            },
            "manifest": {
                "bytes": len(master_manifest_raw),
                "path": _relative_path(
                    master / MANIFEST_FILENAME, definition_parent
                ),
                "sha256": _sha256(master_manifest_raw),
            },
            "master_id": master_id,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
        "template": {
            **_checkpoint(template_path),
            "path": _relative_path(template_path, definition_parent),
        },
    }


def _validate_definition_checkpoint(
    definition_parent: Path,
    record: Any,
    expected_path: Path,
    label: str,
) -> None:
    if not isinstance(record, Mapping) or set(record) != {
        "bytes",
        "path",
        "sha256",
    }:
        raise ConstructionMapError(f"{label} checkpoint schema changed")
    pinned_path = record.get("path")
    if not isinstance(pinned_path, str) or not pinned_path:
        raise ConstructionMapError(f"{label} checkpoint path is invalid")
    if expected_path.is_symlink() or not expected_path.is_file():
        raise ConstructionMapError(f"{label} must be a regular file")
    resolved = (definition_parent / pinned_path).resolve()
    if resolved != expected_path.resolve():
        raise ConstructionMapError(f"{label} checkpoint path changed")
    if _checkpoint(expected_path) != {
        "bytes": record.get("bytes"),
        "sha256": record.get("sha256"),
    }:
        raise ConstructionMapError(f"{label} checkpoint differs")


def validate_map_definition(
    definition_path: str | Path,
    *,
    master_directory: str | Path,
    master_definition_path: str | Path,
) -> dict[str, Any]:
    """Validate a strict map definition and all pinned source paths."""

    definition_input = Path(definition_path)
    definition, _raw = _canonical_json_file(
        definition_input, "construction-map definition"
    )
    definition_file = definition_input.resolve()
    if set(definition) != {
        "definition_role",
        "expected_projection",
        "format",
        "generated_at",
        "map_id",
        "master",
        "schema_version",
        "scope",
        "template",
    }:
        raise ConstructionMapError("map definition schema changed")
    if (
        definition.get("definition_role") != STRICT_DEFINITION_ROLE
        or definition.get("format") != DEFINITION_FORMAT
        or definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("scope") != MAP_SCOPE
    ):
        raise ConstructionMapError("map definition identity or scope changed")
    expected_projection = definition.get("expected_projection")
    if not isinstance(expected_projection, Mapping):
        raise ConstructionMapError("map definition projection must be an object")
    _validate_expected_projection(expected_projection, expected_projection)

    master = Path(master_directory).resolve()
    master_definition = Path(master_definition_path).resolve()
    master_manifest, master_manifest_raw = _canonical_json_file(
        master / MANIFEST_FILENAME, "construction-master manifest"
    )
    master_record = definition.get("master")
    if not isinstance(master_record, Mapping) or set(master_record) != {
        "definition",
        "directory",
        "jsonl",
        "manifest",
        "master_id",
    }:
        raise ConstructionMapError("map definition master schema changed")
    pinned_directory = master_record.get("directory")
    if (
        not isinstance(pinned_directory, str)
        or (definition_file.parent / pinned_directory).resolve() != master
    ):
        raise ConstructionMapError("map definition master directory changed")
    _validate_definition_checkpoint(
        definition_file.parent,
        master_record.get("definition"),
        master_definition,
        "master definition",
    )
    _validate_definition_checkpoint(
        definition_file.parent,
        master_record.get("jsonl"),
        master / "construction-master.jsonl",
        "master JSONL",
    )
    _validate_definition_checkpoint(
        definition_file.parent,
        master_record.get("manifest"),
        master / MANIFEST_FILENAME,
        "master manifest",
    )
    master_id = master_manifest.get("master_id")
    generated_at = master_manifest.get("generated_at")
    if (
        master_record.get("master_id") != master_id
        or definition.get("generated_at") != generated_at
        or definition.get("map_id") != f"{master_id}-construction-map-v1"
        or _sha256(master_manifest_raw)
        != master_record["manifest"].get("sha256")
    ):
        raise ConstructionMapError("map definition master identity changed")
    template_path = Path(__file__).resolve().parents[1] / "web" / TEMPLATE_FILENAME
    _validate_definition_checkpoint(
        definition_file.parent,
        definition.get("template"),
        template_path,
        "map template",
    )
    return definition


def _gzip(raw: bytes) -> bytes:
    compressed = bytearray(gzip.compress(raw, compresslevel=9, mtime=0))
    # Python versions disagree on whether gzip.compress(..., mtime=0) should
    # expose the zlib platform code or the RFC 1952 unknown-platform value.
    # The payload is identical, so pin the header byte explicitly.
    compressed[9] = 255
    return bytes(compressed)


def _template() -> tuple[str, dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "web" / TEMPLATE_FILENAME
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConstructionMapError("construction map template is not UTF-8") from error
    if text.count(DATA_PLACEHOLDER) != 1:
        raise ConstructionMapError("construction map template placeholder count differs")
    return text, {"bytes": len(raw), "path": f"web/{TEMPLATE_FILENAME}", "sha256": _sha256(raw)}


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)


def _build_into(
    master_directory: Path,
    destination: Path,
    *,
    map_definition: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    master_manifest, master_manifest_raw = _json_file(
        master_directory / "manifest.json", "construction-master manifest"
    )
    master_jsonl = master_directory / "construction-master.jsonl"
    expected_jsonl = master_manifest.get("outputs", {}).get("construction-master.jsonl")
    if not isinstance(expected_jsonl, Mapping) or _checkpoint(master_jsonl) != {
        "bytes": expected_jsonl.get("bytes"),
        "sha256": expected_jsonl.get("sha256"),
    }:
        raise ConstructionMapError("construction-master JSONL checkpoint differs")
    manifest_sha = _sha256(master_manifest_raw)
    index, coverage = build_index(
        _read_jsonl(master_jsonl),
        master_manifest=master_manifest,
        master_manifest_sha256=manifest_sha,
        expected_projection=(
            map_definition["expected_projection"]
            if map_definition is not None
            else None
        ),
    )
    index_raw = _compact_json(index)
    compressed = _gzip(index_raw)
    template, template_checkpoint = _template()
    encoded = base64.b64encode(compressed).decode("ascii")
    html_raw = template.replace(DATA_PLACEHOLDER, encoded).encode("utf-8")
    coverage_raw = _canonical_json(coverage)
    mapped = coverage["counts"]["mapped_observation_rows"]
    total = coverage["counts"]["master_observation_rows"]
    readme_raw = (
        f"# Construction map: {master_manifest['master_id']}\n\n"
        f"This browser map projects {mapped:,} coordinate-bearing rows from {total:,} "
        "construction-master observation rows. It does not deduplicate physical sites, "
        "promote review/discovery rows, or create new construction claims. Tier C is hidden "
        "by default and consists of discovery observations, not confirmed data centres.\n"
    ).encode("utf-8")
    attribution_raw = (
        "Data Center Atlas source attribution and licenses are retained per mapped row.\n"
        "OpenStreetMap-derived rows: © OpenStreetMap contributors, ODbL 1.0.\n"
        "Sentinel-linked review rows: Contains modified Copernicus Sentinel data.\n"
        "Basemap at runtime: @d3-maps/atlas / Natural Earth.\n"
    ).encode("utf-8")
    _write(destination / INDEX_FILENAME, compressed)
    _write(destination / HTML_FILENAME, html_raw)
    _write(destination / COVERAGE_FILENAME, coverage_raw)
    _write(destination / README_FILENAME, readme_raw)
    _write(destination / ATTRIBUTION_FILENAME, attribution_raw)
    outputs = {}
    for name in sorted(
        BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    ):
        outputs[name] = _checkpoint(destination / name)
    outputs[INDEX_FILENAME].update(
        {
            "records": mapped,
            "uncompressed_bytes": len(index_raw),
            "uncompressed_sha256": _sha256(index_raw),
        }
    )
    manifest = {
        "format": BUNDLE_FORMAT,
        "generated_at": master_manifest.get("generated_at"),
        "map_id": f"{master_manifest['master_id']}-construction-map-v1",
        "master": {
            "directory_name": master_directory.name,
            "jsonl": _checkpoint(master_jsonl),
            "manifest": {
                "bytes": len(master_manifest_raw),
                "sha256": manifest_sha,
            },
            "master_id": master_manifest.get("master_id"),
            "rows": total,
        },
        "outputs": outputs,
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
        "template": template_checkpoint,
    }
    if map_definition is not None and (
        manifest["map_id"] != map_definition.get("map_id")
        or manifest["generated_at"] != map_definition.get("generated_at")
        or manifest["scope"] != map_definition.get("scope")
        or {
            "bytes": manifest["template"]["bytes"],
            "sha256": manifest["template"]["sha256"],
        }
        != {
            "bytes": map_definition["template"].get("bytes"),
            "sha256": map_definition["template"].get("sha256"),
        }
    ):
        raise ConstructionMapError("map output identity differs from strict definition")
    manifest_raw = _canonical_json(manifest)
    _write(destination / MANIFEST_FILENAME, manifest_raw)
    _write(
        destination / MANIFEST_HASH_FILENAME,
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    return manifest


def write_construction_map(
    master_directory: str | Path,
    output_directory: str | Path,
    *,
    master_definition_path: str | Path | None = None,
    map_definition_path: str | Path | None = None,
    validate_master: bool = True,
    freeze: bool = False,
) -> dict[str, Any]:
    """Atomically build a construction-map bundle from a frozen master."""

    master = Path(master_directory)
    if validate_master:
        if master_definition_path is None:
            raise ConstructionMapError("master_definition_path is required")
        validate_construction_master(master, definition_path=master_definition_path)
    map_definition = None
    if map_definition_path is not None:
        if master_definition_path is None:
            raise ConstructionMapError(
                "master_definition_path is required with a map definition"
            )
        map_definition = validate_map_definition(
            map_definition_path,
            master_directory=master,
            master_definition_path=master_definition_path,
        )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ConstructionMapError(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        manifest = _build_into(
            master,
            stage,
            map_definition=map_definition,
        )
        _validate_static(stage)
        if freeze:
            for entry in stage.iterdir():
                entry.chmod(0o444)
            stage.chmod(0o555)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            stage.chmod(0o755)
            for entry in stage.iterdir():
                if not entry.is_symlink():
                    entry.chmod(0o644)
            shutil.rmtree(stage)
        raise
    return manifest


def is_frozen_map(directory: str | Path) -> bool:
    root = Path(directory)
    return (
        not root.is_symlink()
        and root.is_dir()
        and root.stat().st_mode & 0o777 == 0o555
        and all(
            not entry.is_symlink()
            and entry.is_file()
            and entry.stat().st_mode & 0o777 == 0o444
            for entry in root.iterdir()
        )
    )


def _validate_static(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionMapError("map bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ConstructionMapError("map bundle closed file set changed")
    manifest, manifest_raw = _json_file(directory / MANIFEST_FILENAME, "map manifest")
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionMapError("map manifest is not canonical")
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ConstructionMapError("map manifest sidecar changed")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("scope") != MAP_SCOPE
    ):
        raise ConstructionMapError("map manifest identity or scope changed")
    output_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != output_names:
        raise ConstructionMapError("map output inventory changed")
    for name in output_names:
        expected = manifest["outputs"][name]
        if _checkpoint(directory / name) != {
            "bytes": expected.get("bytes"),
            "sha256": expected.get("sha256"),
        }:
            raise ConstructionMapError(f"map output changed: {name}")
    compressed = (directory / INDEX_FILENAME).read_bytes()
    if len(compressed) < 10 or compressed[9] != 255:
        raise ConstructionMapError("map index gzip platform byte changed")
    try:
        index_raw = gzip.decompress(compressed)
        index = json.loads(index_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapError("map index gzip or JSON is invalid") from error
    expected_index = manifest["outputs"][INDEX_FILENAME]
    if (
        len(index_raw) != expected_index.get("uncompressed_bytes")
        or _sha256(index_raw) != expected_index.get("uncompressed_sha256")
        or not isinstance(index, dict)
        or index.get("format") != FORMAT
        or index.get("fields") != list(FIELDS)
        or index.get("scope") != MAP_SCOPE
        or not isinstance(index.get("rows"), list)
        or len(index["rows"]) != expected_index.get("records")
        or any(not isinstance(row, list) or len(row) != len(FIELDS) for row in index["rows"])
    ):
        raise ConstructionMapError("map index content differs from manifest contract")
    coverage, coverage_raw = _json_file(directory / COVERAGE_FILENAME, "map coverage")
    if coverage_raw != _canonical_json(coverage) or coverage.get("scope") != MAP_SCOPE:
        raise ConstructionMapError("map coverage changed")
    if coverage.get("counts", {}).get("mapped_observation_rows") != len(index["rows"]):
        raise ConstructionMapError("map coverage does not reconcile to index")
    template, template_checkpoint = _template()
    if manifest.get("template") != template_checkpoint:
        raise ConstructionMapError("map template checkpoint changed")
    encoded = base64.b64encode((directory / INDEX_FILENAME).read_bytes()).decode("ascii")
    expected_html = template.replace(DATA_PLACEHOLDER, encoded).encode("utf-8")
    if (directory / HTML_FILENAME).read_bytes() != expected_html:
        raise ConstructionMapError("map HTML does not embed the pinned index")
    return manifest


def _validate_strict_bundle(
    directory: Path,
    manifest: Mapping[str, Any],
    definition: Mapping[str, Any],
) -> None:
    if not is_frozen_map(directory):
        raise ConstructionMapError("strict map bundle modes changed")
    expected = definition["expected_projection"]
    coverage, _raw = _canonical_json_file(
        directory / COVERAGE_FILENAME, "map coverage"
    )
    if coverage.get("counts") != {
        "mapped_observation_rows": expected["mapped_rows"],
        "master_observation_rows": expected["master_rows"],
        "unique_physical_site_count": None,
        "unmapped_observation_rows": expected["unmapped_rows"],
    } or coverage.get("mapped_counts", {}).get("by_tier") != expected[
        "mapped_by_tier"
    ]:
        raise ConstructionMapError("map coverage differs from strict definition")
    master_definition = definition["master"]
    if (
        manifest.get("map_id") != definition.get("map_id")
        or manifest.get("generated_at") != definition.get("generated_at")
        or manifest.get("scope") != definition.get("scope")
        or manifest.get("master", {}).get("master_id")
        != master_definition.get("master_id")
        or manifest.get("master", {}).get("rows") != expected["master_rows"]
        or manifest.get("master", {}).get("jsonl")
        != {
            "bytes": master_definition["jsonl"].get("bytes"),
            "sha256": master_definition["jsonl"].get("sha256"),
        }
        or manifest.get("master", {}).get("manifest")
        != {
            "bytes": master_definition["manifest"].get("bytes"),
            "sha256": master_definition["manifest"].get("sha256"),
        }
        or {
            "bytes": manifest.get("template", {}).get("bytes"),
            "sha256": manifest.get("template", {}).get("sha256"),
        }
        != {
            "bytes": definition["template"].get("bytes"),
            "sha256": definition["template"].get("sha256"),
        }
    ):
        raise ConstructionMapError("map manifest differs from strict definition")


def validate_construction_map(
    directory: str | Path,
    *,
    master_directory: str | Path | None = None,
    master_definition_path: str | Path | None = None,
    map_definition_path: str | Path | None = None,
    reproduce: bool = True,
) -> dict[str, Any]:
    """Validate a frozen map and optionally reconstruct every byte offline."""

    root = Path(directory)
    manifest = _validate_static(root)
    map_definition = None
    if map_definition_path is not None:
        if master_directory is None or master_definition_path is None:
            raise ConstructionMapError(
                "master paths are required with a map definition"
            )
        validate_construction_master(
            master_directory, definition_path=master_definition_path
        )
        map_definition = validate_map_definition(
            map_definition_path,
            master_directory=master_directory,
            master_definition_path=master_definition_path,
        )
        _validate_strict_bundle(root, manifest, map_definition)
    if reproduce:
        if master_directory is None or master_definition_path is None:
            raise ConstructionMapError(
                "master_directory and master_definition_path are required for reproduction"
            )
        with tempfile.TemporaryDirectory(prefix="construction-map-reproduce-") as temporary:
            rebuilt = Path(temporary) / "map"
            write_construction_map(
                master_directory,
                rebuilt,
                master_definition_path=master_definition_path,
                map_definition_path=map_definition_path,
                validate_master=map_definition is None,
                freeze=False,
            )
            for name in sorted(BUNDLE_FILES):
                if _checkpoint(root / name) != _checkpoint(rebuilt / name):
                    raise ConstructionMapError(
                        f"map differs from offline reproduction: {name}"
                    )
    return manifest


__all__ = [
    "ConstructionMapError",
    "DEFAULT_VISIBLE_TIERS",
    "DEFINITION_FORMAT",
    "FIELDS",
    "MAP_SCOPE",
    "STRICT_DEFINITION_ROLE",
    "build_index",
    "derive_map_definition",
    "is_frozen_map",
    "validate_construction_map",
    "validate_map_definition",
    "write_construction_map",
]
