"""Deterministic browser-map projection for construction-master schema v2."""

from __future__ import annotations

from collections import Counter
import base64
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable, Iterator, Mapping

from . import construction_map as legacy
from .construction_master_v2 import (
    CORE_ROLE_KEYS,
    MASTER_ID,
    ROLE_KEYS,
    ConstructionMasterV2Error,
    validate_definition as validate_master_definition,
    validate_construction_master_v2,
)


SCHEMA_VERSION = 2
DEFINITION_FORMAT = "datacenter-atlas-construction-map-definition-v2"
FORMAT = "datacenter-atlas-construction-map-index-v2"
BUNDLE_FORMAT = "datacenter-atlas-construction-map-bundle-v2"
MAP_ID = f"{MASTER_ID}-construction-map-v2"
GENERATED_AT = "2026-07-20T06:15:00Z"
STRICT_DEFINITION_ROLE = (
    "strict_role_preserving_projection_contract_consumed_by_v2_map_builder_and_validator"
)
INDEX_FILENAME = "construction-map-index.json.gz"
HTML_FILENAME = "construction-map.html"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
TEMPLATE_FILENAME = "construction-map-template-v2.html"
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

FIELDS = legacy.FIELDS + (
    "source_publication_contract_version",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "source_role_tags",
)

MAP_SCOPE = {
    **legacy.MAP_SCOPE,
    "historical_status_is_not_current_status_claim": True,
    "role_values_copied_from_master_without_inference": True,
    "role_values_rendered_as_text_not_markup": True,
    "source_role_tags_preserved_opaquely": True,
}

EXPECTED_FIXED = {
    "added_replacement_rows_unmapped": 63,
    "default_visible_rows": 6479,
    "mapped_by_tier": {"A": 199, "B": 6280, "C": 102494},
    "mapped_replacement_rows": 80,
    "mapped_rows": 108973,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109174,
    "unmapped_rows": 201,
}
EXPECTED_DIGEST_KEYS = {
    "added_replacement_unmapped_source_record_ids_sha256",
    "unmapped_source_record_ids_sha256",
}
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ConstructionMapV2Error(ValueError):
    """Raised when the role-preserving map contract or output drifts."""


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


def _json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMapV2Error(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapV2Error(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionMapV2Error(f"{label} must be a JSON object")
    return value, raw


def _safe_definition_path(base: Path, supplied: Any, label: str) -> Path:
    if not isinstance(supplied, str) or not supplied or "\\" in supplied:
        raise ConstructionMapV2Error(f"{label} path is invalid")
    relative = Path(supplied)
    if relative.is_absolute():
        raise ConstructionMapV2Error(f"{label} path must be relative")
    package_root = base.parent.resolve()
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as error:
        raise ConstructionMapV2Error(f"{label} path escapes package") from error
    return resolved


def _validate_checkpoint(
    definition_directory: Path,
    spec: Any,
    actual_path: Path,
    label: str,
) -> None:
    if not isinstance(spec, Mapping) or set(spec) != {"bytes", "path", "sha256"}:
        raise ConstructionMapV2Error(f"{label} checkpoint schema changed")
    digest = spec.get("sha256")
    size = spec.get("bytes")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
        or not isinstance(digest, str)
        or not _SHA_RE.fullmatch(digest)
    ):
        raise ConstructionMapV2Error(f"{label} checkpoint is invalid")
    resolved = _safe_definition_path(definition_directory, spec.get("path"), label)
    if resolved != actual_path.resolve():
        raise ConstructionMapV2Error(f"{label} path changed")
    if resolved.is_symlink() or not resolved.is_file():
        raise ConstructionMapV2Error(f"{label} must be a regular file")
    if _checkpoint(resolved) != {"bytes": size, "sha256": digest}:
        raise ConstructionMapV2Error(f"{label} checkpoint changed")


def _expected_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        *EXPECTED_FIXED,
        *EXPECTED_DIGEST_KEYS,
        "default_visible_tiers",
    }:
        raise ConstructionMapV2Error("map expected projection schema changed")
    if value.get("default_visible_tiers") != list(DEFAULT_VISIBLE_TIERS):
        raise ConstructionMapV2Error("map default tiers changed")
    for key, expected in EXPECTED_FIXED.items():
        if value.get(key) != expected:
            raise ConstructionMapV2Error(f"map fixed projection changed: {key}")
    for key in EXPECTED_DIGEST_KEYS:
        digest = value.get(key)
        if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
            raise ConstructionMapV2Error(f"map projection digest is invalid: {key}")
    return dict(value)


def validate_map_definition_v2(
    definition_path: str | Path,
    *,
    master_directory: str | Path,
    master_definition_path: str | Path,
) -> dict[str, Any]:
    path = Path(definition_path)
    definition, raw = _json_file(path, "map v2 definition")
    if raw != _canonical_json(definition):
        raise ConstructionMapV2Error("map definition must be canonical JSON")
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
        raise ConstructionMapV2Error("map definition keys differ from v2 contract")
    if (
        definition.get("definition_role") != STRICT_DEFINITION_ROLE
        or definition.get("format") != DEFINITION_FORMAT
        or definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("map_id") != MAP_ID
        or definition.get("generated_at") != GENERATED_AT
        or definition.get("scope") != MAP_SCOPE
    ):
        raise ConstructionMapV2Error("map definition identity or scope changed")
    _expected_projection(definition.get("expected_projection"))

    master = Path(master_directory).resolve()
    master_definition = Path(master_definition_path).resolve()
    record = definition.get("master")
    if not isinstance(record, Mapping) or set(record) != {
        "definition",
        "directory",
        "jsonl",
        "manifest",
        "master_id",
    }:
        raise ConstructionMapV2Error("map master checkpoint schema changed")
    pinned_directory = record.get("directory")
    if (
        not isinstance(pinned_directory, str)
        or (path.parent / pinned_directory).resolve() != master
        or record.get("master_id") != MASTER_ID
    ):
        raise ConstructionMapV2Error("map master identity changed")
    _validate_checkpoint(
        path.parent, record["definition"], master_definition, "master definition"
    )
    _validate_checkpoint(
        path.parent,
        record["jsonl"],
        master / "construction-master.jsonl",
        "master JSONL",
    )
    _validate_checkpoint(
        path.parent,
        record["manifest"],
        master / "manifest.json",
        "master manifest",
    )
    template = Path(__file__).resolve().parents[1] / "web" / TEMPLATE_FILENAME
    _validate_checkpoint(path.parent, definition["template"], template, "map template")
    master_manifest, master_manifest_raw = _json_file(
        master / "manifest.json", "master manifest"
    )
    if (
        master_manifest.get("master_id") != MASTER_ID
        or master_manifest.get("row_counts", {}).get("total") != 109_174
        or _sha256(master_manifest_raw) != record["manifest"]["sha256"]
    ):
        raise ConstructionMapV2Error("map master manifest binding changed")
    return definition


def _master_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as source:
        for line_number, raw in enumerate(source, start=1):
            try:
                row = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ConstructionMapV2Error(
                    f"master line {line_number} is invalid"
                ) from error
            if not isinstance(row, dict) or (
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                + "\n"
            ).encode("utf-8") != raw:
                raise ConstructionMapV2Error(
                    f"master line {line_number} is not canonical"
                )
            yield row


def _project_row(row: Mapping[str, Any], line_number: int) -> list[Any] | None:
    try:
        projected = legacy._project_row(row, line_number)
    except legacy.ConstructionMapError as error:
        raise ConstructionMapV2Error(str(error)) from error
    roles = row.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != set(ROLE_KEYS):
        raise ConstructionMapV2Error(f"master line {line_number} roles changed")
    marker = roles.get("source_publication_contract_version")
    if marker is not None and (
        isinstance(marker, bool) or not isinstance(marker, int) or marker != 4
    ):
        raise ConstructionMapV2Error(f"master line {line_number} marker changed")
    for key in CORE_ROLE_KEYS:
        if roles.get(key) is not None and not isinstance(roles.get(key), str):
            raise ConstructionMapV2Error(
                f"master line {line_number} {key} must be text or null"
            )
    tags = roles.get("source_role_tags")
    if not isinstance(tags, dict) or any(
        not isinstance(key, str) or not key.startswith("role:") for key in tags
    ):
        raise ConstructionMapV2Error(
            f"master line {line_number} source_role_tags changed"
        )
    if projected is None:
        return None
    return [
        *projected,
        marker,
        *(roles[key] for key in CORE_ROLE_KEYS),
        dict(tags),
    ]


def _id_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _added_source_record_ids(
    master_definition_path: str | Path,
) -> set[str]:
    definition, _raw, _root, resolved, _context = validate_master_definition(
        master_definition_path
    )
    inputs = definition["inputs"]
    base_path = resolved[str(inputs["base_master"]["jsonl"]["path"])]
    old_ids: set[str] = set()
    with base_path.open("rb") as source:
        for raw in source:
            row = json.loads(raw)
            artifact_id = row.get("source", {}).get("artifact_id")
            if artifact_id != "epoch-official-open-seed-v33":
                break
            record_id = row.get("source", {}).get("record_id")
            if not isinstance(record_id, str) or record_id in old_ids:
                raise ConstructionMapV2Error("v14 base record ID boundary changed")
            old_ids.add(record_id)
    replacement = inputs["replacement_release"]
    data_path = resolved[str(replacement["data"]["path"])]
    with data_path.open(newline="", encoding="utf-8") as source:
        replacement_ids = {
            str(row["entity_id"]) for row in csv.DictReader(source)
        }
    added = replacement_ids - old_ids
    if (
        len(old_ids) != 199
        or len(replacement_ids) != 262
        or len(added) != 63
        or _id_digest(added)
        != definition["expected"]["added_source_record_ids_sha256"]
    ):
        raise ConstructionMapV2Error("v16 additive source-record boundary changed")
    return added


def build_index_v2(
    rows: Iterable[Mapping[str, Any]],
    *,
    master_manifest: Mapping[str, Any],
    master_manifest_sha256: str,
    added_source_record_ids: set[str],
    expected_projection: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mapped: list[list[Any]] = []
    unmapped_ids: list[str] = []
    added_unmapped_ids: list[str] = []
    tiers: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    mapped_rows_with_any_role = 0
    mapped_replacement_rows = 0
    total = 0
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ConstructionMapV2Error(f"master line {line_number} must be an object")
        total += 1
        projected = _project_row(row, line_number)
        source = row.get("source")
        if not isinstance(source, Mapping):
            raise ConstructionMapV2Error(f"master line {line_number} source is absent")
        record_id = source.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ConstructionMapV2Error(f"master line {line_number} record ID is absent")
        if projected is None:
            unmapped_ids.append(record_id)
            if record_id in added_source_record_ids:
                added_unmapped_ids.append(record_id)
            continue
        if record_id in added_source_record_ids:
            raise ConstructionMapV2Error("an additive v42 row unexpectedly became mapped")
        mapped.append(projected)
        values = dict(zip(FIELDS, projected, strict=True))
        tiers[str(values["tier"])] += 1
        statuses[str(values["normalized_status"] or "unknown")] += 1
        kinds[str(values["observation_kind"] or "unknown")] += 1
        countries[
            str(values["country"] or values["country_iso_a3"] or "Unknown")
        ] += 1
        sources[str(values["source_artifact_id"] or "unknown")] += 1
        any_role = any(values[key] is not None for key in CORE_ROLE_KEYS) or bool(
            values["source_role_tags"]
        )
        mapped_rows_with_any_role += any_role
        mapped_replacement_rows += (
            values["source_artifact_id"] == "epoch-official-open-seed-v42"
        )
    declared = master_manifest.get("row_counts", {}).get("total")
    if total != declared:
        raise ConstructionMapV2Error(
            f"master manifest declares {declared} rows but JSONL has {total}"
        )

    if set(added_unmapped_ids) != added_source_record_ids:
        raise ConstructionMapV2Error("not all 63 additive v42 rows remain unmapped")
    summary = {
        "added_replacement_rows_unmapped": len(added_unmapped_ids),
        "added_replacement_unmapped_source_record_ids_sha256": _id_digest(
            added_unmapped_ids
        ),
        "default_visible_rows": sum(tiers[tier] for tier in DEFAULT_VISIBLE_TIERS),
        "default_visible_tiers": list(DEFAULT_VISIBLE_TIERS),
        "mapped_by_tier": {tier: tiers[tier] for tier in ("A", "B", "C")},
        "mapped_replacement_rows": mapped_replacement_rows,
        "mapped_rows": len(mapped),
        "mapped_rows_with_any_role": mapped_rows_with_any_role,
        "master_rows": total,
        "unmapped_rows": len(unmapped_ids),
        "unmapped_source_record_ids_sha256": _id_digest(unmapped_ids),
    }
    if expected_projection is not None and summary != dict(expected_projection):
        raise ConstructionMapV2Error(
            f"map projection differs from strict definition: {summary!r}"
        )
    coverage = {
        "counts": {
            "mapped_observation_rows": len(mapped),
            "mapped_replacement_rows": mapped_replacement_rows,
            "mapped_rows_with_any_role": mapped_rows_with_any_role,
            "master_observation_rows": total,
            "unique_physical_site_count": None,
            "unmapped_observation_rows": len(unmapped_ids),
        },
        "freshness": {
            "historical_status_warning": (
                "Statuses are historical source observations; inclusion does not prove "
                "that construction persisted after reported_status_date."
            )
        },
        "mapped_counts": {
            "by_country": dict(sorted(countries.items())),
            "by_normalized_status": dict(sorted(statuses.items())),
            "by_observation_kind": dict(sorted(kinds.items())),
            "by_source_artifact": dict(sorted(sources.items())),
            "by_tier": dict(sorted(tiers.items())),
        },
        "projection": summary,
        "scope": MAP_SCOPE,
        "schema_version": SCHEMA_VERSION,
    }
    index = {
        "attribution": [
            "Source attribution and license are retained per observation",
            "Role fields are exact source strings, not inferred relationships",
            "OpenStreetMap contributors where source rows identify OpenStreetMap",
            "Contains modified Copernicus Sentinel data for linked imagery reviews",
        ],
        "fields": list(FIELDS),
        "format": FORMAT,
        "generated_at": GENERATED_AT,
        "master_id": master_manifest.get("master_id"),
        "master_manifest_sha256": master_manifest_sha256,
        "rows": mapped,
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
    }
    return index, coverage


def _gzip(raw: bytes) -> bytes:
    compressed = bytearray(gzip.compress(raw, compresslevel=9, mtime=0))
    compressed[9] = 255
    return bytes(compressed)


def _template() -> tuple[str, dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "web" / TEMPLATE_FILENAME
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConstructionMapV2Error("map template must be UTF-8") from error
    if text.count(DATA_PLACEHOLDER) != 1 or "innerHTML" in text:
        raise ConstructionMapV2Error("map template placeholder or escaping contract changed")
    return text, {
        "bytes": len(raw),
        "path": f"web/{TEMPLATE_FILENAME}",
        "sha256": _sha256(raw),
    }


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)


def _build_into(
    master_directory: Path,
    destination: Path,
    *,
    definition: Mapping[str, Any],
    added_source_record_ids: set[str],
) -> dict[str, Any]:
    master_manifest, master_manifest_raw = _json_file(
        master_directory / "manifest.json", "master manifest"
    )
    master_jsonl = master_directory / "construction-master.jsonl"
    expected_jsonl = master_manifest.get("outputs", {}).get(
        "construction-master.jsonl"
    )
    if not isinstance(expected_jsonl, Mapping) or _checkpoint(master_jsonl) != {
        "bytes": expected_jsonl.get("bytes"),
        "sha256": expected_jsonl.get("sha256"),
    }:
        raise ConstructionMapV2Error("master JSONL checkpoint differs")
    index, coverage = build_index_v2(
        _master_rows(master_jsonl),
        master_manifest=master_manifest,
        master_manifest_sha256=_sha256(master_manifest_raw),
        added_source_record_ids=added_source_record_ids,
        expected_projection=definition["expected_projection"],
    )
    index_raw = _compact_json(index)
    compressed = _gzip(index_raw)
    template, template_checkpoint = _template()
    html_raw = template.replace(
        DATA_PLACEHOLDER, base64.b64encode(compressed).decode("ascii")
    ).encode("utf-8")
    _write(destination / INDEX_FILENAME, compressed)
    _write(destination / HTML_FILENAME, html_raw)
    _write(destination / COVERAGE_FILENAME, _canonical_json(coverage))
    _write(
        destination / README_FILENAME,
        (
            "# Construction evidence map v16 (schema v2)\n\n"
            "This map projects 108,973 coordinate-bearing source observations from "
            "109,174 master rows. It does not deduplicate physical sites or claim global "
            "completeness. Tier B and C rows remain unpromoted; Tier C is hidden by "
            "default.\n\nRole strings and opaque role:* tags are exact values from the "
            "marked v42 source release and are rendered as text, never executable markup. "
            "Statuses are historical observations and do not prove that construction "
            "persisted after the reported date.\n"
        ).encode("utf-8"),
    )
    _write(
        destination / ATTRIBUTION_FILENAME,
        (
            "Data Center Atlas source attribution and licenses are retained per mapped row.\n"
            "Role fields are exact source strings and do not imply independently verified relationships.\n"
            "OpenStreetMap-derived rows: © OpenStreetMap contributors, ODbL 1.0.\n"
            "Sentinel-linked review rows: Contains modified Copernicus Sentinel data.\n"
            "Basemap at runtime: @d3-maps/atlas / Natural Earth.\n"
        ).encode("utf-8"),
    )
    output_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    outputs = {
        name: _checkpoint(destination / name) for name in sorted(output_names)
    }
    outputs[INDEX_FILENAME].update(
        {
            "records": len(index["rows"]),
            "uncompressed_bytes": len(index_raw),
            "uncompressed_sha256": _sha256(index_raw),
        }
    )
    manifest = {
        "format": BUNDLE_FORMAT,
        "generated_at": GENERATED_AT,
        "map_id": MAP_ID,
        "master": {
            "directory_name": master_directory.name,
            "jsonl": _checkpoint(master_jsonl),
            "manifest": {
                "bytes": len(master_manifest_raw),
                "sha256": _sha256(master_manifest_raw),
            },
            "master_id": master_manifest.get("master_id"),
            "rows": coverage["counts"]["master_observation_rows"],
        },
        "outputs": outputs,
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
        "template": template_checkpoint,
    }
    manifest_raw = _canonical_json(manifest)
    _write(destination / MANIFEST_FILENAME, manifest_raw)
    _write(
        destination / MANIFEST_HASH_FILENAME,
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    return manifest


def write_construction_map_v2(
    master_directory: str | Path,
    output_directory: str | Path,
    *,
    master_definition_path: str | Path,
    map_definition_path: str | Path,
    freeze: bool = False,
) -> dict[str, Any]:
    master = Path(master_directory)
    try:
        validate_construction_master_v2(
            master,
            definition_path=master_definition_path,
            reproduce=False,
        )
    except ConstructionMasterV2Error as error:
        raise ConstructionMapV2Error(str(error)) from error
    definition = validate_map_definition_v2(
        map_definition_path,
        master_directory=master,
        master_definition_path=master_definition_path,
    )
    added_source_record_ids = _added_source_record_ids(master_definition_path)
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ConstructionMapV2Error(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        manifest = _build_into(
            master,
            stage,
            definition=definition,
            added_source_record_ids=added_source_record_ids,
        )
        _validate_static(stage, frozen=False)
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


def is_frozen_map_v2(directory: str | Path) -> bool:
    root = Path(directory)
    return (
        not root.is_symlink()
        and root.is_dir()
        and stat.S_IMODE(root.stat().st_mode) == 0o555
        and all(
            entry.is_file()
            and not entry.is_symlink()
            and stat.S_IMODE(entry.stat().st_mode) == 0o444
            for entry in root.iterdir()
        )
    )


def _validate_static(directory: Path, *, frozen: bool) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionMapV2Error("map bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ConstructionMapV2Error("map closed file set changed")
    manifest, manifest_raw = _json_file(directory / MANIFEST_FILENAME, "map manifest")
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionMapV2Error("map manifest is not canonical")
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ConstructionMapV2Error("map manifest sidecar changed")
    if (
        manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("map_id") != MAP_ID
        or manifest.get("generated_at") != GENERATED_AT
        or manifest.get("scope") != MAP_SCOPE
    ):
        raise ConstructionMapV2Error("map manifest identity changed")
    expected_outputs = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != expected_outputs:
        raise ConstructionMapV2Error("map output inventory changed")
    for name in expected_outputs:
        expected = manifest["outputs"][name]
        if _checkpoint(directory / name) != {
            "bytes": expected.get("bytes"),
            "sha256": expected.get("sha256"),
        }:
            raise ConstructionMapV2Error(f"map output changed: {name}")
    compressed = (directory / INDEX_FILENAME).read_bytes()
    if len(compressed) < 10 or compressed[9] != 255:
        raise ConstructionMapV2Error("map gzip header changed")
    try:
        index_raw = gzip.decompress(compressed)
        index = json.loads(index_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapV2Error("map index is invalid") from error
    index_checkpoint = manifest["outputs"][INDEX_FILENAME]
    if (
        len(index_raw) != index_checkpoint.get("uncompressed_bytes")
        or _sha256(index_raw) != index_checkpoint.get("uncompressed_sha256")
        or index.get("format") != FORMAT
        or index.get("fields") != list(FIELDS)
        or index.get("scope") != MAP_SCOPE
        or not isinstance(index.get("rows"), list)
        or len(index["rows"]) != index_checkpoint.get("records")
        or any(
            not isinstance(row, list) or len(row) != len(FIELDS)
            for row in index["rows"]
        )
    ):
        raise ConstructionMapV2Error("map index content changed")
    coverage, coverage_raw = _json_file(directory / COVERAGE_FILENAME, "map coverage")
    if (
        coverage_raw != _canonical_json(coverage)
        or coverage.get("scope") != MAP_SCOPE
        or coverage.get("counts", {}).get("mapped_observation_rows")
        != len(index["rows"])
    ):
        raise ConstructionMapV2Error("map coverage changed")
    template, template_checkpoint = _template()
    if manifest.get("template") != template_checkpoint:
        raise ConstructionMapV2Error("map template checkpoint changed")
    expected_html = template.replace(
        DATA_PLACEHOLDER,
        base64.b64encode((directory / INDEX_FILENAME).read_bytes()).decode("ascii"),
    ).encode("utf-8")
    if (directory / HTML_FILENAME).read_bytes() != expected_html:
        raise ConstructionMapV2Error("map HTML embed changed")
    if frozen and not is_frozen_map_v2(directory):
        raise ConstructionMapV2Error("map must be frozen 0555/0444")
    return manifest


def validate_construction_map_v2(
    directory: str | Path,
    *,
    master_directory: str | Path,
    master_definition_path: str | Path,
    map_definition_path: str | Path,
    reproduce: bool = True,
) -> dict[str, Any]:
    root = Path(directory)
    manifest = _validate_static(root, frozen=True)
    definition = validate_map_definition_v2(
        map_definition_path,
        master_directory=master_directory,
        master_definition_path=master_definition_path,
    )
    coverage, _raw = _json_file(root / COVERAGE_FILENAME, "map coverage")
    if coverage.get("projection") != definition["expected_projection"]:
        raise ConstructionMapV2Error("map strict projection changed")
    if reproduce:
        with tempfile.TemporaryDirectory(prefix="construction-map-v2-reproduce-") as temporary:
            rebuilt = Path(temporary) / "map"
            write_construction_map_v2(
                master_directory,
                rebuilt,
                master_definition_path=master_definition_path,
                map_definition_path=map_definition_path,
            )
            for name in sorted(BUNDLE_FILES):
                if _checkpoint(root / name) != _checkpoint(rebuilt / name):
                    raise ConstructionMapV2Error(
                        f"map differs from offline reproduction: {name}"
                    )
    return manifest


__all__ = [
    "ConstructionMapV2Error",
    "FIELDS",
    "MAP_SCOPE",
    "build_index_v2",
    "is_frozen_map_v2",
    "validate_construction_map_v2",
    "validate_map_definition_v2",
    "write_construction_map_v2",
]
