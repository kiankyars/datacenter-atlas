"""Static public-site builder for the Data Center Atlas.

``build_site`` turns the frozen dataset versions under ``verified_construction_core/`` into a
self-contained static site: HTML pages that work without JavaScript, a versioned static JSON
API under ``api/v1/``, bulk downloads (original files plus JSON, NDJSON, SQLite, KML, a
Frictionless Data Package, checksums and a zip archive), an Atom feed and a sitemap.

The builder is standard-library only, makes no network requests and is deterministic: the
same inputs produce byte-identical output. Before anything is written it validates every
dataset version against its ``manifest.json`` and ``manifest.sha256`` and fails closed on
any mismatch.

Every dataset value is untrusted text. HTML output is escaped, only ``http``/``https`` URLs
become links, JSON embedded in ``<script>`` blocks escapes ``<``, ``>``, ``&``, U+2028 and
U+2029, KML descriptions are escaped twice (HTML, then XML), and identifiers used in output
paths must match a conservative pattern.

Typed records follow the checkpoint's own ``schema.json``: empty CSV values become ``null``,
``number`` becomes a float, ``integer`` an int, ``boolean`` a bool, ``json_array`` and
``geojson_geometry`` parsed JSON, and everything else stays a string. Typed field names drop
a trailing ``_json``; CSV and SQLite keep the original column names.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlsplit
import uuid
import zipfile


__all__ = [
    "API_VERSION",
    "PublicSiteError",
    "SiteConfig",
    "DatasetVersion",
    "Atlas",
    "build_site",
    "load_config",
    "normalize_base_url",
    "discover_versions",
    "validate_dataset",
    "load_atlas",
    "convert_value",
    "convert_row",
    "typed_field_name",
    "render_tokens",
    "collect_vocabulary_codes",
    "fallback_label",
]

API_VERSION = "1"
MARKER_NAME = ".atlas-site"
MARKER_TEXT = (
    "Output of datacenter_atlas.public_site. The --force flag only replaces "
    "directories that contain this marker.\n"
)
TABLE_FILES = ("sites.csv", "projects.csv", "evidence.csv")
TABLE_NAMES = {"sites.csv": "sites", "projects.csv": "projects", "evidence.csv": "evidence"}
LATEST = "latest"
GEOJSON_LAYER_NAME = "datacenter-atlas-sites"
FEED_TITLE = "Data Center Atlas releases"
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
EXAMPLE_LIMIT = 80
API_EXAMPLE_LINES = 60
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: https://*.basemaps.cartocdn.com "
    "https://tile.openstreetmap.org https://tiles.maps.eox.at; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self' https://github.com"
)
NAVIGATION = (
    ("explore", "", "Explore"),
    ("sites", "sites/", "Sites"),
    ("countries", "countries/", "Countries"),
    ("data", "data/", "Data"),
    ("api", "api/", "API"),
    ("methodology", "methodology/", "Methodology"),
    ("versions", "versions/", "Versions"),
    ("about", "about/", "About"),
)
LEAFLET_JS = "assets/vendor/leaflet/leaflet.js"
LEAFLET_CSS = "assets/vendor/leaflet/leaflet.css"
SITE_CSS = "assets/site.css"
SITE_JS = "assets/site.js"
SITE_MAP_JS = "assets/site-map.js"
APP_JS = "assets/app.js"
# Optional shared logic for app.js and site-map.js: both load it on demand when a page lacks
# it, so the layout includes it only when site/static provides it.
ATLAS_CORE_JS = "assets/atlas-core.js"
FAVICON = "favicon.svg"

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
COLUMN_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
ISO_A2 = re.compile(r"[A-Z]{2}")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{4,64}")
JSON_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
INTEGER = re.compile(r"-?(?:0|[1-9]\d*)")
PREVIEW_DIR = re.compile(r"\d{4}-\d{2}-\d{2}-preview-v(?P<major>\d+)\.(?P<minor>\d+)")
DRAFT_DIR = re.compile(
    r"\d{4}-\d{2}-\d{2}-v(?P<major>\d+)\.(?P<minor>\d+)-draft-(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)"
)
TOKEN = re.compile(r"\{\{\{\s*([A-Za-z0-9_.]+)\s*\}\}\}|\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'`]+")
TRAILING_URL_PUNCTUATION = ".,;:!?)]}"

REQUIRED_COLUMNS = {
    "sites.csv": (
        "site_id", "name", "country", "country_iso_a2", "latitude", "longitude",
        "geometry_json", "geometry_type", "project_ids_json", "statuses_json",
        "oldest_status_as_of", "newest_status_as_of", "project_count",
    ),
    "projects.csv": (
        "project_id", "site_id", "name", "country", "country_iso_a2",
        "last_observed_physical_status", "status_as_of", "status_evidence_id",
    ),
    "evidence.csv": ("evidence_id", "project_ids_json", "title", "source_url", "publisher"),
}
DERIVED_FIELDS = {
    "sites.csv": ("official_boundary", "country_slug", "url", "api_url"),
    "projects.csv": ("evidence_ids", "status_source", "url", "api_url"),
    "evidence.csv": ("site_ids", "url"),
}
STATUS_SOURCE_FIELDS = (
    "evidence_id", "title", "publisher", "kind", "published_at", "source_url", "license",
)
SQL_TYPES = {"number": "REAL", "integer": "INTEGER", "boolean": "INTEGER"}
DATAPACKAGE_TYPES = {
    "string": ("string", None),
    "uri": ("string", "uri"),
    "number": ("number", None),
    "integer": ("integer", None),
    "boolean": ("boolean", None),
    "date": ("date", None),
    "date_or_datetime": ("string", None),
    "sha256": ("string", None),
    "json_array": ("array", None),
    "geojson_geometry": ("geojson", None),
}
VOCABULARY_KEYS = (
    "statuses",
    "status_methods",
    "geometry_use_scopes",
    "geometry_authority_classes",
    "verification_postures",
    "power_metrics",
    "power_stages",
    "estimate_methods",
    "evidence_kinds",
    "evidence_roles",
    "relationship_scopes",
    "workload_deployment_scopes",
    "party_roles",
    "workloads",
    "workload_methods",
    "operating_models",
    "development_types",
    "geometry_source_entity_kinds",
    "release_gates",
)
OBSERVATION_FIELDS = (
    ("power_observations", "power_unknown_reason", "Power"),
    ("efficiency_observations", "efficiency_unknown_reason", "Efficiency"),
    ("annual_energy_observations", "annual_energy_unknown_reason", "Annual energy"),
)
DOWNLOAD_ORDER = (
    "sites.csv", "projects.csv", "evidence.csv", "sites.geojson", "atlas.json", "atlas.sqlite",
    "sites.kml", "sites.ndjson", "projects.ndjson", "evidence.ndjson", "datapackage.json",
    "schema.json", "selection-report.json", "review-provenance.json", "README.md",
    "ATTRIBUTION.txt", "manifest.json", "manifest.sha256", "map.html",
)
DOWNLOAD_INFO = {
    "sites.csv": ("CSV", "text/csv", "One row per physical site."),
    "projects.csv": (
        "CSV", "text/csv",
        "One row per construction project: last observed status, locator semantics and typed observations.",
    ),
    "evidence.csv": (
        "CSV", "text/csv", "Every evidence row the checkpoint references, with source URL, rights and content hash.",
    ),
    "sites.geojson": ("GeoJSON", "application/geo+json", "Site locators and boundaries as a GeoJSON FeatureCollection."),
    "atlas.json": ("JSON", "application/json", "Every typed site, project and evidence record in one JSON document."),
    "atlas.sqlite": (
        "SQLite", "application/vnd.sqlite3", "SQLite database: the three tables, link tables and a site_overview view.",
    ),
    "sites.kml": ("KML", "application/vnd.google-earth.kml+xml", "Sites for Google Earth and other KML viewers."),
    "sites.ndjson": ("NDJSON", "application/x-ndjson", "One typed site record per line."),
    "projects.ndjson": ("NDJSON", "application/x-ndjson", "One typed project record per line."),
    "evidence.ndjson": ("NDJSON", "application/x-ndjson", "One typed evidence record per line."),
    "datapackage.json": (
        "Data Package", "application/json", "Frictionless Data Package descriptor: table schemas, sizes and hashes.",
    ),
    "schema.json": ("JSON", "application/json", "Machine-readable schema of the checkpoint files."),
    "selection-report.json": ("JSON", "application/json", "Selection accounting and final-release gates."),
    "review-provenance.json": ("JSON", "application/json", "Review provenance of the draft additions."),
    "README.md": ("Markdown", "text/markdown", "Checkpoint readme."),
    "ATTRIBUTION.txt": ("Text", "text/plain", "Source attribution and third-party terms."),
    "manifest.json": ("JSON", "application/json", "Byte sizes and SHA-256 hashes of the original checkpoint files."),
    "manifest.sha256": ("Text", "text/plain", "SHA-256 of manifest.json."),
    "map.html": ("HTML", "text/html", "Offline map shipped with the preview."),
    "SHA256SUMS": ("Text", "text/plain", "SHA-256 of every file in this directory (sha256sum -c format)."),
}
EXTENSION_INFO = {
    ".csv": ("CSV", "text/csv"),
    ".json": ("JSON", "application/json"),
    ".geojson": ("GeoJSON", "application/geo+json"),
    ".md": ("Markdown", "text/markdown"),
    ".txt": ("Text", "text/plain"),
    ".html": ("HTML", "text/html"),
    ".zip": ("ZIP", "application/zip"),
}


class PublicSiteError(ValueError):
    """Raised when the inputs cannot produce a valid public site."""


# --------------------------------------------------------------------------------------------
# Configuration


@dataclass(frozen=True)
class SiteConfig:
    site_name: str
    tagline: str
    base_url: str
    repository_url: str
    issues_url: str
    versions_root: str
    current_dataset: str
    last_preview_dataset: str
    status_window_days: int
    author: Mapping[str, Any]
    data_license: Mapping[str, Any]
    code_license: Mapping[str, Any]


def load_config(path: Path) -> SiteConfig:
    """Read and validate ``site/config.json``."""
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise PublicSiteError(f"{path}: expected a JSON object")
    text_keys = (
        "site_name", "tagline", "base_url", "repository_url", "issues_url",
        "versions_root", "current_dataset", "last_preview_dataset",
    )
    for key in text_keys:
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise PublicSiteError(f"{path}: '{key}' must be a non-empty string")
    window = raw.get("status_window_days")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        raise PublicSiteError(f"{path}: 'status_window_days' must be a positive integer")
    for key in ("author", "data_license", "code_license"):
        if not isinstance(raw.get(key), dict):
            raise PublicSiteError(f"{path}: '{key}' must be an object")
    for key in ("repository_url", "issues_url"):
        if _safe_http_url(raw[key]) is None:
            raise PublicSiteError(f"{path}: '{key}' must be an http(s) URL")
    return SiteConfig(
        site_name=raw["site_name"],
        tagline=raw["tagline"],
        base_url=normalize_base_url(raw["base_url"]),
        repository_url=raw["repository_url"].rstrip("/"),
        issues_url=raw["issues_url"].rstrip("/"),
        versions_root=raw["versions_root"],
        current_dataset=raw["current_dataset"],
        last_preview_dataset=raw["last_preview_dataset"],
        status_window_days=window,
        author=raw["author"],
        data_license=raw["data_license"],
        code_license=raw["code_license"],
    )


def normalize_base_url(value: str) -> str:
    """Return an absolute http(s) base URL that ends with a slash."""
    url = value.strip()
    if _safe_http_url(url) is None:
        raise PublicSiteError(f"base URL must be an absolute http(s) URL: {value!r}")
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        raise PublicSiteError(f"base URL must not contain a query or fragment: {value!r}")
    return url if url.endswith("/") else url + "/"


def _normalize_commit(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    commit = value.strip().lower()
    if not COMMIT.fullmatch(commit):
        raise PublicSiteError(f"source commit must be a hexadecimal git object name: {value!r}")
    return commit


# --------------------------------------------------------------------------------------------
# Dataset versions and validation


@dataclass(frozen=True)
class FileRecord:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class DatasetVersion:
    id: str
    path: Path
    kind: str
    label: str
    checkpoint_date: str
    lifecycle_reference_date: str
    release_status: str
    publishable_as_final: bool
    counts: Mapping[str, Any]
    manifest: Mapping[str, Any]
    manifest_sha256: str
    files: tuple[FileRecord, ...]
    sort_key: tuple[Any, ...]


def validate_dataset(path: Path) -> tuple[dict[str, Any], str, tuple[FileRecord, ...]]:
    """Check ``manifest.sha256`` and every manifest-listed file of one dataset directory.

    Returns the parsed manifest, its SHA-256 and the original files (manifest-listed files
    plus ``manifest.json`` and ``manifest.sha256``) sorted by name.
    """
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    manifest_bytes = _read_regular_bytes(manifest_path)
    checksum_bytes = _read_regular_bytes(checksum_path)
    digest = _sha256(manifest_bytes)
    try:
        checksum_text = checksum_bytes.decode("ascii")
    except UnicodeDecodeError as error:
        raise PublicSiteError(f"{checksum_path}: not ASCII") from error
    lines = checksum_text.splitlines()
    match = re.fullmatch(r"([0-9a-f]{64})  manifest\.json", lines[0]) if len(lines) == 1 else None
    if match is None:
        raise PublicSiteError(f"{checksum_path}: expected one line '<sha256>  manifest.json'")
    if match.group(1) != digest:
        raise PublicSiteError(
            f"{checksum_path}: manifest.json has SHA-256 {digest}, manifest.sha256 says {match.group(1)}"
        )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicSiteError(f"{manifest_path}: invalid JSON ({error})") from error
    listed = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(listed, dict) or not listed:
        raise PublicSiteError(f"{manifest_path}: 'files' must be a non-empty object")
    records = [
        FileRecord("manifest.json", len(manifest_bytes), digest),
        FileRecord("manifest.sha256", len(checksum_bytes), _sha256(checksum_bytes)),
    ]
    for name in sorted(listed):
        records.append(_validate_listed_file(path, name, listed[name]))
    names = [record.name for record in records]
    if len(set(names)) != len(names):
        raise PublicSiteError(f"{manifest_path}: lists manifest.json or manifest.sha256 as a data file")
    return manifest, digest, tuple(sorted(records, key=lambda record: record.name))


def _validate_listed_file(directory: Path, name: str, entry: Any) -> FileRecord:
    if not SAFE_FILE_NAME.fullmatch(name):
        raise PublicSiteError(f"{directory}/manifest.json: unsafe file name {name!r}")
    if not isinstance(entry, dict):
        raise PublicSiteError(f"{directory}/manifest.json: entry for {name} must be an object")
    size, expected = entry.get("bytes"), entry.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or not isinstance(expected, str):
        raise PublicSiteError(f"{directory}/manifest.json: entry for {name} needs bytes and sha256")
    if not SHA256_HEX.fullmatch(expected):
        raise PublicSiteError(f"{directory}/manifest.json: sha256 for {name} is not 64 lower-case hex digits")
    data = _read_regular_bytes(directory / name)
    if len(data) != size:
        raise PublicSiteError(f"{directory / name}: {len(data)} bytes, manifest says {size}")
    digest = _sha256(data)
    if digest != expected:
        raise PublicSiteError(f"{directory / name}: SHA-256 {digest}, manifest says {expected}")
    return FileRecord(name, size, digest)


def discover_versions(versions_root: Path) -> tuple[DatasetVersion, ...]:
    """Validate and order every dataset directory (a direct child with ``manifest.json``)."""
    if not versions_root.is_dir():
        raise PublicSiteError(f"versions root {versions_root} is not a directory")
    versions = []
    for child in sorted(versions_root.iterdir(), key=lambda item: item.name):
        if child.is_symlink() or not child.is_dir() or not (child / "manifest.json").exists():
            continue
        versions.append(_load_version(child))
    if not versions:
        raise PublicSiteError(f"no dataset versions found under {versions_root}")
    versions.sort(key=lambda version: version.sort_key)
    for previous, current in zip(versions, versions[1:]):
        if previous.sort_key == current.sort_key:
            raise PublicSiteError(f"ambiguous version order: {previous.id} and {current.id}")
    return tuple(versions)


def _load_version(path: Path) -> DatasetVersion:
    identifier = path.name
    if not SAFE_ID.fullmatch(identifier):
        raise PublicSiteError(f"unsafe dataset directory name {identifier!r}")
    manifest, digest, files = validate_dataset(path)
    report = _read_json(path / "selection-report.json") if (path / "selection-report.json").is_file() else {}
    if not isinstance(report, dict):
        raise PublicSiteError(f"{identifier}/selection-report.json: expected a JSON object")
    kind = manifest.get("release_status")
    if kind not in {"preview", "draft"}:
        raise PublicSiteError(f"{identifier}: unsupported release_status {kind!r}")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise PublicSiteError(f"{identifier}: manifest has no counts object")
    for key in ("physical_sites", "projects", "evidence", "countries"):
        if not isinstance(counts.get(key), int):
            raise PublicSiteError(f"{identifier}: manifest counts.{key} must be an integer")
    label, sort_key = _version_label_and_order(identifier, kind, counts)
    checkpoint = _checkpoint_date(identifier, kind, manifest)
    lifecycle = (
        manifest.get("cohort_lifecycle_reference_date")
        or manifest.get("reviewed_at")
        or report.get("lifecycle_reference_date")
    )
    _require_date(lifecycle, f"{identifier}: lifecycle reference date")
    publishable = manifest.get("publishable_as_final", report.get("publishable_as_final", False))
    return DatasetVersion(
        id=identifier,
        path=path,
        kind=kind,
        label=label,
        checkpoint_date=checkpoint,
        lifecycle_reference_date=lifecycle,
        release_status=kind,
        publishable_as_final=publishable is True,
        counts=counts,
        manifest=manifest,
        manifest_sha256=digest,
        files=files,
        sort_key=sort_key,
    )


def _version_label_and_order(identifier: str, kind: str, counts: Mapping[str, int]) -> tuple[str, tuple[Any, ...]]:
    if kind == "preview":
        match = PREVIEW_DIR.fullmatch(identifier)
        if match is None:
            raise PublicSiteError(f"{identifier}: preview directory name must look like YYYY-MM-DD-preview-vX.Y")
        major, minor = int(match.group("major")), int(match.group("minor"))
        return f"v{major}.{minor} preview", (0, major, minor)
    match = DRAFT_DIR.fullmatch(identifier)
    if match is None:
        raise PublicSiteError(f"{identifier}: draft directory name must look like YYYY-MM-DD-vX.Y-draft-<name>")
    version = f"v{int(match.group('major'))}.{int(match.group('minor'))}"
    label = f"{version} draft — {_draft_phrase(match.group('name'))}"
    return label, (1, counts["physical_sites"], counts["projects"], counts["evidence"])


def _draft_phrase(name: str) -> str:
    if name.startswith("initial-") and name.count("-") == 1:
        return f"initial {name.removeprefix('initial-')}-site checkpoint"
    if name.endswith("-reviewed"):
        return f"{name.removesuffix('-reviewed')} reviewed checkpoint"
    return f"{name.replace('-', ' ')} checkpoint"


def _checkpoint_date(identifier: str, kind: str, manifest: Mapping[str, Any]) -> str:
    if kind == "preview":
        value = manifest.get("geometry_identity_reviewed_at") or manifest.get("reviewed_at")
        _require_date(value, f"{identifier}: checkpoint date")
        return value
    draft_id = manifest.get("draft_id")
    if not isinstance(draft_id, str):
        raise PublicSiteError(f"{identifier}: draft manifest has no draft_id")
    for match in ISO_DATE.finditer(draft_id):
        if match.start() == 0:
            continue
        _require_date(match.group(0), f"{identifier}: draft_id date")
        return match.group(0)
    raise PublicSiteError(f"{identifier}: draft_id {draft_id!r} has no checkpoint date")


def _require_date(value: Any, what: str) -> None:
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise PublicSiteError(f"{what} must be an ISO date, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise PublicSiteError(f"{what} is not a valid date: {value!r}") from error


def _find_version(versions: Sequence[DatasetVersion], configured: str, root: Path, key: str) -> DatasetVersion:
    target = (root / configured).resolve()
    for version in versions:
        if version.path.resolve() == target:
            return version
    raise PublicSiteError(f"config {key} {configured!r} is not a validated dataset version")


# --------------------------------------------------------------------------------------------
# Typed conversion


def typed_field_name(name: str) -> str:
    """Typed JSON field name for a CSV column: drop a trailing ``_json``."""
    return name.removesuffix("_json") if name.endswith("_json") and len(name) > 5 else name


def convert_value(value: str, logical_type: str, *, field_name: str = "value") -> Any:
    """Convert one CSV value by its schema logical type (empty string -> None)."""
    if value == "":
        return None
    if logical_type == "number":
        if not JSON_NUMBER.fullmatch(value):
            raise PublicSiteError(f"{field_name}: {value!r} is not a number")
        number = float(value)
        if not math.isfinite(number):
            raise PublicSiteError(f"{field_name}: {value!r} is not a finite number")
        return number
    if logical_type == "integer":
        if not INTEGER.fullmatch(value):
            raise PublicSiteError(f"{field_name}: {value!r} is not an integer")
        return int(value)
    if logical_type == "boolean":
        if value in {"true", "false"}:
            return value == "true"
        raise PublicSiteError(f"{field_name}: {value!r} is not 'true' or 'false'")
    if logical_type in {"json_array", "geojson_geometry"}:
        return _parse_embedded_json(value, logical_type, field_name)
    return value


def _parse_embedded_json(value: str, logical_type: str, field_name: str) -> Any:
    try:
        parsed = json.loads(value, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise PublicSiteError(f"{field_name}: invalid JSON ({error})") from error
    if logical_type == "json_array" and not isinstance(parsed, list):
        raise PublicSiteError(f"{field_name}: expected a JSON array")
    if logical_type == "geojson_geometry" and not (
        isinstance(parsed, dict) and isinstance(parsed.get("type"), str)
    ):
        raise PublicSiteError(f"{field_name}: expected a GeoJSON geometry object")
    return parsed


def _reject_json_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def convert_row(row: Mapping[str, str], fields: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Typed record for one CSV row, in schema column order."""
    record: dict[str, Any] = {}
    for spec in fields:
        name = spec["name"]
        record[typed_field_name(name)] = convert_value(
            row[name], str(spec.get("logical_type", "string")), field_name=name
        )
    return record


def _sql_value(value: str, logical_type: str, field_name: str) -> Any:
    converted = convert_value(value, logical_type, field_name=field_name)
    if converted is None:
        return None
    if logical_type == "boolean":
        return 1 if converted else 0
    if logical_type in {"number", "integer"}:
        return converted
    return value


# --------------------------------------------------------------------------------------------
# The current dataset as typed, cross-linked records


@dataclass
class Atlas:
    version: DatasetVersion
    schema: Mapping[str, Any]
    fields: dict[str, tuple[Mapping[str, Any], ...]]
    raw: dict[str, list[dict[str, str]]]
    sites: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    selection_report: Mapping[str, Any]
    site_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    project_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    projects_by_site: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    evidence_by_site: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    evidence_by_project: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    summary_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    countries: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)


def load_atlas(version: DatasetVersion, base_url: str) -> Atlas:
    """Read, type, validate and cross-link the three tables of one dataset version."""
    schema = _read_json(version.path / "schema.json")
    fields = _schema_fields(schema, version.id)
    raw = {name: _read_csv_table(version.path / name, fields[name]) for name in TABLE_FILES}
    typed = {name: [convert_row(row, fields[name]) for row in raw[name]] for name in TABLE_FILES}
    report_path = version.path / "selection-report.json"
    report = _read_json(report_path) if report_path.is_file() else {}
    if not isinstance(report, dict):
        raise PublicSiteError(f"{version.id}/selection-report.json: expected a JSON object")
    atlas = Atlas(
        version=version,
        schema=schema,
        fields=fields,
        raw=raw,
        sites=typed["sites.csv"],
        projects=typed["projects.csv"],
        evidence=typed["evidence.csv"],
        selection_report=report,
    )
    _index_records(atlas)
    _check_references(atlas)
    _derive_fields(atlas, base_url)
    _group_records(atlas)
    atlas.summaries = sorted(
        (_site_summary(atlas, site) for site in atlas.sites),
        key=lambda summary: _name_key(summary, "site_id"),
    )
    atlas.summary_by_id = {summary["site_id"]: summary for summary in atlas.summaries}
    atlas.countries = _country_summaries(atlas, base_url)
    atlas.counts = _merged_counts(atlas)
    return atlas


def _schema_fields(schema: Any, version_id: str) -> dict[str, tuple[Mapping[str, Any], ...]]:
    tables = schema.get("tables") if isinstance(schema, dict) else None
    if not isinstance(tables, dict):
        raise PublicSiteError(f"{version_id}/schema.json: missing 'tables'")
    result = {}
    for name in TABLE_FILES:
        spec = tables.get(name)
        fields = spec.get("fields") if isinstance(spec, dict) else None
        if not isinstance(fields, list) or not fields:
            raise PublicSiteError(f"{version_id}/schema.json: no fields for {name}")
        typed_names = set()
        for item in fields:
            column = item.get("name") if isinstance(item, dict) else None
            if not isinstance(column, str) or not COLUMN_NAME.fullmatch(column):
                raise PublicSiteError(f"{version_id}/schema.json: invalid column name {column!r} in {name}")
            if typed_field_name(column) in typed_names:
                raise PublicSiteError(f"{version_id}/schema.json: duplicate typed field {column!r} in {name}")
            typed_names.add(typed_field_name(column))
        missing = [column for column in REQUIRED_COLUMNS[name] if column not in {f["name"] for f in fields}]
        if missing:
            raise PublicSiteError(f"{version_id}/schema.json: {name} lacks required columns {missing}")
        clashes = typed_names & set(DERIVED_FIELDS[name])
        if clashes:
            raise PublicSiteError(f"{version_id}/schema.json: {name} columns clash with derived fields {sorted(clashes)}")
        result[name] = tuple(fields)
    return result


def _read_csv_table(path: Path, fields: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    names = [spec["name"] for spec in fields]
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None) or []
        if header != names:
            position = next(
                (index for index, pair in enumerate(zip(header, names)) if pair[0] != pair[1]),
                min(len(header), len(names)),
            )
            found = header[position] if position < len(header) else "end of header"
            wanted = names[position] if position < len(names) else "end of header"
            raise PublicSiteError(
                f"{path}: header does not match schema.json (column {position + 1}: found {found!r}, expected {wanted!r})"
            )
        rows = []
        for values in reader:
            if len(values) != len(names):
                raise PublicSiteError(f"{path}: line {reader.line_num} has {len(values)} values, expected {len(names)}")
            rows.append(dict(zip(names, values)))
    return rows


def _index_records(atlas: Atlas) -> None:
    atlas.site_by_id = _unique_index(atlas.sites, "site_id", "sites.csv")
    atlas.project_by_id = _unique_index(atlas.projects, "project_id", "projects.csv")
    atlas.evidence_by_id = _unique_index(atlas.evidence, "evidence_id", "evidence.csv")
    for site in atlas.sites:
        iso = site.get("country_iso_a2")
        if not isinstance(iso, str) or not ISO_A2.fullmatch(iso):
            raise PublicSiteError(f"sites.csv {site['site_id']}: invalid country_iso_a2 {iso!r}")
        for key in ("latitude", "longitude"):
            if not isinstance(site.get(key), float):
                raise PublicSiteError(f"sites.csv {site['site_id']}: {key} is required")
        if not isinstance(site.get("geometry"), dict):
            raise PublicSiteError(f"sites.csv {site['site_id']}: geometry_json is required")
    members: dict[str, set[str]] = defaultdict(set)
    for project in atlas.projects:
        site_id = project.get("site_id")
        if site_id not in atlas.site_by_id:
            raise PublicSiteError(f"projects.csv {project['project_id']}: unknown site_id {site_id!r}")
        if project.get("status_evidence_id") not in atlas.evidence_by_id:
            raise PublicSiteError(f"projects.csv {project['project_id']}: unknown status_evidence_id")
        members[site_id].add(project["project_id"])
    for site in atlas.sites:
        listed = site.get("project_ids") or []
        if set(listed) != members[site["site_id"]] or len(listed) != len(set(listed)):
            raise PublicSiteError(f"sites.csv {site['site_id']}: project_ids_json disagrees with projects.csv")
    for evidence in atlas.evidence:
        for project_id in evidence.get("project_ids") or []:
            if project_id not in atlas.project_by_id:
                raise PublicSiteError(f"evidence.csv {evidence['evidence_id']}: unknown project {project_id!r}")


def _check_references(atlas: Atlas) -> None:
    """Every schema foreign key and embedded evidence reference must resolve."""
    rows = {"sites.csv": atlas.sites, "projects.csv": atlas.projects, "evidence.csv": atlas.evidence}
    keys = {"sites.csv": "site_id", "projects.csv": "project_id", "evidence.csv": "evidence_id"}
    declared = atlas.schema.get("foreign_keys")
    for item in declared if isinstance(declared, list) else []:
        source, target = (item.get("from"), item.get("to")) if isinstance(item, dict) else (None, None)
        if not (isinstance(source, list) and isinstance(target, list) and source[0] in rows and target[0] in rows):
            continue
        targets = {record.get(typed_field_name(target[1])) for record in rows[target[0]]}
        for record in rows[source[0]]:
            value = record.get(typed_field_name(source[1]))
            if value is not None and value not in targets:
                raise PublicSiteError(
                    f"{source[0]} {record[keys[source[0]]]}: {source[1]} {value!r} is not a {target[0]} {target[1]}"
                )
    embedded = atlas.schema.get("json_embedded_evidence_fields")
    for item in embedded if isinstance(embedded, list) else []:
        if not (isinstance(item, list) and len(item) == 3 and item[0] in rows):
            continue
        table, column, key = item
        for record in rows[table]:
            for entry in _dict_items(record.get(typed_field_name(column))):
                if entry.get(key) not in atlas.evidence_by_id:
                    raise PublicSiteError(
                        f"{table} {record[keys[table]]}: {column} references unknown evidence {entry.get(key)!r}"
                    )


def _unique_index(records: Sequence[dict[str, Any]], key: str, table: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            raise PublicSiteError(f"{table}: unsafe or empty {key} {value!r}")
        if value in index:
            raise PublicSiteError(f"{table}: duplicate {key} {value!r}")
        index[value] = record
    return index


def _derive_fields(atlas: Atlas, base_url: str) -> None:
    evidence_ids: dict[str, set[str]] = defaultdict(set)
    for evidence in atlas.evidence:
        for project_id in evidence.get("project_ids") or []:
            evidence_ids[project_id].add(evidence["evidence_id"])
    site_projects: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in atlas.projects:
        site_projects[project["site_id"]].append(project)
    for site in atlas.sites:
        site_id = site["site_id"]
        site["official_boundary"] = any(
            project.get("geometry_use_scope") == "official_boundary" for project in site_projects[site_id]
        )
        site["country_slug"] = site["country_iso_a2"].lower()
        site["url"] = f"{base_url}sites/{site_id}/"
        site["api_url"] = f"{base_url}api/v1/sites/{site_id}.json"
    for project in atlas.projects:
        project_id = project["project_id"]
        status = atlas.evidence_by_id[project["status_evidence_id"]]
        project["evidence_ids"] = sorted(evidence_ids[project_id])
        project["status_source"] = {key: status.get(key) for key in STATUS_SOURCE_FIELDS}
        project["url"] = f"{base_url}sites/{project['site_id']}/#project-{project_id}"
        project["api_url"] = f"{base_url}api/v1/projects/{project_id}.json"
    for evidence in atlas.evidence:
        evidence["site_ids"] = sorted(
            {atlas.project_by_id[project_id]["site_id"] for project_id in evidence.get("project_ids") or []}
        )
        evidence["url"] = f"{base_url}api/v1/evidence/{evidence['evidence_id']}.json"


def _group_records(atlas: Atlas) -> None:
    projects_by_site: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in atlas.projects:
        projects_by_site[project["site_id"]].append(project)
    atlas.projects_by_site = {
        site_id: sorted(projects_by_site[site_id], key=lambda item: _name_key(item, "project_id"))
        for site_id in atlas.site_by_id
    }
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evidence in atlas.evidence:
        for project_id in dict.fromkeys(evidence.get("project_ids") or []):
            by_project[project_id].append(evidence)
    atlas.evidence_by_project = {
        project_id: sorted(by_project[project_id], key=_evidence_key) for project_id in atlas.project_by_id
    }
    atlas.evidence_by_site = {}
    for site_id, projects in atlas.projects_by_site.items():
        rows = {evidence["evidence_id"]: evidence for project in projects for evidence in by_project[project["project_id"]]}
        atlas.evidence_by_site[site_id] = sorted(rows.values(), key=_evidence_key)


def _name_key(record: Mapping[str, Any], id_field: str) -> tuple[str, str, str]:
    name = record.get("name") or ""
    return (name.casefold(), name, record.get(id_field) or "")


def _evidence_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    title = record.get("title") or ""
    return (title.casefold(), title, record["evidence_id"])


def _site_summary(atlas: Atlas, site: Mapping[str, Any]) -> dict[str, Any]:
    projects = atlas.projects_by_site[site["site_id"]]
    publishers = {
        atlas.evidence_by_id[project["status_evidence_id"]].get("publisher") for project in projects
    }
    power = []
    for project in projects:
        observations = [item for item in project.get("power_observations") or [] if isinstance(item, dict)]
        for item in sorted(observations, key=lambda value: str(value.get("metric") or "")):
            power.append({
                "project_id": project["project_id"],
                "metric": item.get("metric"),
                "stage": item.get("stage"),
                "low": item.get("low"),
                "base": item.get("base"),
                "high": item.get("high"),
                "unit": item.get("unit"),
                "as_of_date": item.get("as_of_date"),
            })
    return {
        "site_id": site["site_id"],
        "name": site.get("name"),
        "country": site.get("country"),
        "country_iso_a2": site.get("country_iso_a2"),
        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "geometry_type": site.get("geometry_type"),
        "official_boundary": site["official_boundary"],
        "locator_scopes": site.get("geometry_use_scopes") if "geometry_use_scopes" in site else [],
        "statuses": site.get("statuses"),
        "newest_status_as_of": site.get("newest_status_as_of"),
        "oldest_status_as_of": site.get("oldest_status_as_of"),
        "project_count": site.get("project_count"),
        "projects": [
            {
                "project_id": project["project_id"],
                "name": project.get("name"),
                "status": project.get("last_observed_physical_status"),
                "status_as_of": project.get("status_as_of"),
            }
            for project in projects
        ],
        "status_publishers": sorted(publisher for publisher in publishers if publisher),
        "power_observations": power,
        "verification_posture": site.get("verification_posture"),
        "independent_imagery_verification": site.get("independent_imagery_verification"),
        "url": site["url"],
        "api_url": site["api_url"],
    }


def _country_summaries(atlas: Atlas, base_url: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for site in atlas.sites:
        groups[site["country_iso_a2"]].append(site)
    countries = []
    for iso in sorted(groups):
        sites = groups[iso]
        names = {site.get("country") for site in sites}
        if len(names) != 1:
            raise PublicSiteError(f"sites.csv: country_iso_a2 {iso} has several country names {sorted(map(str, names))}")
        projects = [project for site in sites for project in atlas.projects_by_site[site["site_id"]]]
        statuses = Counter(str(project.get("last_observed_physical_status")) for project in projects)
        slug = iso.lower()
        countries.append({
            "country_iso_a2": iso,
            "country": names.pop(),
            "slug": slug,
            "site_count": len(sites),
            "project_count": len(projects),
            "statuses": _ordered_counts(statuses),
            "site_ids": sorted(site["site_id"] for site in sites),
            "url": f"{base_url}countries/{slug}/",
            "api_url": f"{base_url}api/v1/countries/{iso}.json",
        })
    countries.sort(key=lambda item: (-item["site_count"], str(item["country"]).casefold(), item["country_iso_a2"]))
    return countries


def _merged_counts(atlas: Atlas) -> dict[str, Any]:
    counts = dict(atlas.version.counts)
    derived = {
        "polygon_sites": sum(1 for site in atlas.sites if site.get("geometry_type") in {"Polygon", "MultiPolygon"}),
        "point_sites": sum(1 for site in atlas.sites if site.get("geometry_type") == "Point"),
        "power_observation_projects": sum(1 for project in atlas.projects if project.get("power_observations")),
        "multi_project_sites": sum(1 for site in atlas.sites if len(atlas.projects_by_site[site["site_id"]]) > 1),
    }
    for key, value in derived.items():
        counts.setdefault(key, value)
    return counts


def _ordered_counts(counter: Counter) -> dict[str, int]:
    return {key: count for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))}


def collect_vocabulary_codes(atlas: Atlas) -> dict[str, list[str]]:
    """Every coded value present in the dataset, grouped by vocabulary (sorted, distinct)."""
    codes: dict[str, set[str]] = {key: set() for key in VOCABULARY_KEYS}

    def add(key: str, value: Any) -> None:
        if isinstance(value, str) and value:
            codes[key].add(value)

    for site in atlas.sites:
        for value in site.get("statuses") or []:
            add("statuses", value)
        for value in site.get("geometry_use_scopes") or []:
            add("geometry_use_scopes", value)
        for value in site.get("geometry_authority_classes") or []:
            add("geometry_authority_classes", value)
        for value in site.get("geometry_source_entity_kinds") or []:
            add("geometry_source_entity_kinds", value)
        add("verification_postures", site.get("verification_posture"))
    for project in atlas.projects:
        add("statuses", project.get("last_observed_physical_status"))
        add("status_methods", project.get("status_method"))
        add("geometry_use_scopes", project.get("geometry_use_scope"))
        add("geometry_authority_classes", project.get("geometry_authority_class"))
        add("geometry_source_entity_kinds", project.get("geometry_source_entity_kind"))
        add("verification_postures", project.get("verification_posture"))
        add("operating_models", project.get("operating_model"))
        add("development_types", project.get("development_type"))
        for observation in _observations(project):
            add("power_metrics", observation.get("metric"))
            add("power_stages", observation.get("stage"))
            add("estimate_methods", observation.get("method"))
        for claim in _dict_items(project.get("role_claims")):
            add("party_roles", claim.get("role"))
            add("relationship_scopes", claim.get("relationship_scope"))
        for workload in _dict_items(project.get("workloads")):
            add("workloads", workload.get("workload"))
            add("workload_deployment_scopes", workload.get("deployment_scope"))
            add("workload_methods", workload.get("method"))
    for evidence in atlas.evidence:
        add("evidence_kinds", evidence.get("kind"))
        for role in evidence.get("roles") or []:
            add("evidence_roles", role)
    gates = atlas.selection_report.get("final_release_gates")
    for gate in gates if isinstance(gates, dict) else {}:
        add("release_gates", gate)
    return {key: sorted(values) for key, values in codes.items()}


def _observations(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = []
    for key, _, _ in OBSERVATION_FIELDS:
        items.extend(_dict_items(project.get(key)))
    return items


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


# --------------------------------------------------------------------------------------------
# Vocabularies


def fallback_label(code: Any) -> str:
    """Title-cased label for a code that has no vocabulary entry."""
    text = str(code or "").replace(":", ": ")
    words = [word for word in re.split(r"[_\s]+", text) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words) or "Unknown"


class Vocabulary:
    """Labels and descriptions from ``site/vocabulary.json`` with title-case fallbacks."""

    def __init__(self, source: Mapping[str, Any]) -> None:
        for key in VOCABULARY_KEYS:
            entries = source.get(key, {})
            if not isinstance(entries, dict) or not all(
                isinstance(entry, dict) and isinstance(entry.get("label"), str) for entry in entries.values()
            ):
                raise PublicSiteError(f"site/vocabulary.json: '{key}' must map codes to {{label, description}}")
        self._source = source

    def entry(self, vocabulary: str, code: Any) -> Mapping[str, Any] | None:
        return self._source.get(vocabulary, {}).get(code) if isinstance(code, str) else None

    def label(self, vocabulary: str, code: Any) -> str:
        entry = self.entry(vocabulary, code)
        return entry["label"] if entry else fallback_label(code)

    def description(self, vocabulary: str, code: Any) -> str:
        entry = self.entry(vocabulary, code)
        return str(entry.get("description", "")) if entry else ""

    def export(self, data_codes: Mapping[str, Sequence[str]]) -> dict[str, dict[str, dict[str, str]]]:
        """Every vocabulary: curated entries in file order, then data codes without an entry."""
        result = {}
        for key in VOCABULARY_KEYS:
            entries: dict[str, dict[str, str]] = {}
            for code, entry in self._source.get(key, {}).items():
                entries[code] = self._exported_entry(key, entry)
            for code in data_codes.get(key, ()):
                if code not in entries:
                    entries[code] = self._exported_entry(key, {"label": fallback_label(code)})
            result[key] = entries
        return result

    @staticmethod
    def _exported_entry(key: str, entry: Mapping[str, Any]) -> dict[str, str]:
        exported = {"label": str(entry.get("label", ""))}
        if key == "power_metrics":
            exported["unit"] = str(entry.get("unit", ""))
        exported["description"] = str(entry.get("description", ""))
        return exported


# --------------------------------------------------------------------------------------------
# Output tree


class _Writer:
    """Writes each output path exactly once, inside the staging directory."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.paths: set[str] = set()
        self.pages: list[str] = []

    def write_bytes(self, relative: str, data: bytes) -> None:
        if relative in self.paths or relative.startswith("/") or ".." in relative.split("/") or "\\" in relative:
            raise PublicSiteError(f"invalid or duplicate output path {relative!r}")
        target = self.base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise PublicSiteError(f"output path {relative!r} is written twice (static file collision?)")
        target.write_bytes(data)
        self.paths.add(relative)

    def write_text(self, relative: str, text: str) -> None:
        self.write_bytes(relative, text.encode("utf-8"))

    def write_json(self, relative: str, value: Any, *, pretty: bool = False) -> None:
        self.write_text(relative, _json_text(value, pretty=pretty))


def _json_text(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def _check_output_location(output: Path, root: Path, config: SiteConfig) -> None:
    if output == root or output in root.parents:
        raise PublicSiteError(f"refusing to build into {output}: it contains the repository")
    for path in (root / "site", root / config.versions_root, root / ".git"):
        protected = path.resolve()
        if output == protected or protected in output.parents:
            raise PublicSiteError(f"refusing to build into {output}: it is inside {protected}")


def _check_output_directory(output: Path, *, overwrite: bool) -> None:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise PublicSiteError(f"output path {output} exists and is not a directory")
    if not output.exists() or not any(output.iterdir()):
        return
    if not overwrite:
        raise PublicSiteError(
            f"refusing to write into non-empty directory {output}; pass --force to replace a previous build"
        )
    if not (output / MARKER_NAME).is_file():
        raise PublicSiteError(f"refusing to replace {output}: it has no {MARKER_NAME} marker written by this builder")


def _make_staging(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".building", dir=output.parent))
    staging.chmod(0o755)
    return staging


def _publish_staging(staging: Path, output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    staging.rename(output)


# --------------------------------------------------------------------------------------------
# Build orchestration


@dataclass(frozen=True)
class DownloadFile:
    name: str
    size: int
    sha256: str
    format: str
    media_type: str
    description: str


@dataclass(frozen=True)
class _Context:
    config: SiteConfig
    base_url: str
    commit: str | None
    root: Path
    versions: tuple[DatasetVersion, ...]
    current: DatasetVersion
    last_preview: DatasetVersion
    atlas: Atlas
    vocabulary: Vocabulary
    vocabularies: Mapping[str, Any]
    descriptions: Mapping[str, Any]
    version_sites: Mapping[str, Mapping[str, str]]
    static_files: frozenset[str]
    downloads: tuple[DownloadFile, ...] = ()

    @property
    def site_dir(self) -> Path:
        return self.root / "site"

    @property
    def window_start(self) -> str:
        reference = date.fromisoformat(self.current.lifecycle_reference_date)
        return (reference - timedelta(days=self.config.status_window_days)).isoformat()

    @property
    def commit_short(self) -> str:
        return self.commit[:7] if self.commit else "local build"

    @property
    def zip_name(self) -> str:
        return f"datacenter-atlas-{self.current.id}.zip"


def build_site(
    output_dir: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str],
    base_url: str | None = None,
    source_commit: str | None = None,
    config_path: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build the public site into ``output_dir`` and return a summary.

    ``root`` is the repository root (it holds ``site/`` and the dataset versions).
    ``base_url`` overrides ``config.base_url`` for absolute URLs in JSON, feeds and
    sitemaps; HTML links are always relative. An existing non-empty ``output_dir`` is
    replaced only when ``overwrite`` is true *and* it contains the builder's marker file.
    """
    root_path = Path(root).resolve()
    output = Path(output_dir).expanduser().absolute()
    config = load_config(Path(config_path) if config_path else root_path / "site" / "config.json")
    site_url = normalize_base_url(base_url) if base_url else config.base_url
    commit = _normalize_commit(source_commit)
    _check_output_location(output.resolve(), root_path, config)
    _check_output_directory(output, overwrite=overwrite)
    context = _prepare_context(root_path, config, site_url, commit)
    staging = _make_staging(output)
    try:
        writer = _Writer(staging)
        _copy_static(writer, context.site_dir / "static")
        context = replace(context, downloads=_write_downloads(writer, context))
        _write_api(writer, context)
        _write_pages(writer, context)
        _write_feed(writer, context)
        _write_sitemap_and_robots(writer, context)
        writer.write_bytes(".nojekyll", b"")
        writer.write_text(MARKER_NAME, MARKER_TEXT)
        summary = _summary(writer, context, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _publish_staging(staging, output)
    return summary


def _prepare_context(root: Path, config: SiteConfig, base_url: str, commit: str | None) -> _Context:
    versions = discover_versions(root / config.versions_root)
    current = _find_version(versions, config.current_dataset, root, "current_dataset")
    last_preview = _find_version(versions, config.last_preview_dataset, root, "last_preview_dataset")
    atlas = load_atlas(current, base_url)
    vocabulary = Vocabulary(_read_json(root / "site" / "vocabulary.json"))
    descriptions = _read_json(root / "site" / "field_descriptions.json")
    if not isinstance(descriptions, dict) or not isinstance(descriptions.get("tables"), dict):
        raise PublicSiteError("site/field_descriptions.json: expected an object with 'tables'")
    return _Context(
        config=config,
        base_url=base_url,
        commit=commit,
        root=root,
        versions=versions,
        current=current,
        last_preview=last_preview,
        atlas=atlas,
        vocabulary=vocabulary,
        vocabularies=vocabulary.export(collect_vocabulary_codes(atlas)),
        descriptions=descriptions,
        version_sites={version.id: _version_site_names(version) for version in versions},
        static_files=frozenset(relative for relative, _ in _static_files(root / "site" / "static")),
    )


def _version_site_names(version: DatasetVersion) -> dict[str, str]:
    with (version.path / "sites.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "site_id" not in reader.fieldnames or "name" not in reader.fieldnames:
            raise PublicSiteError(f"{version.id}/sites.csv: needs site_id and name columns")
        names = {}
        for row in reader:
            if row["site_id"] in names:
                raise PublicSiteError(f"{version.id}/sites.csv: duplicate site_id {row['site_id']!r}")
            names[row["site_id"]] = row["name"]
    return names


def _static_files(static_dir: Path) -> list[tuple[str, Path]]:
    if not static_dir.is_dir():
        raise PublicSiteError(f"static directory {static_dir} is missing")
    files = []
    for directory, subdirectories, names in os.walk(static_dir):
        subdirectories[:] = sorted(name for name in subdirectories if not name.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                raise PublicSiteError(f"static file {path} must be a regular file")
            files.append((path.relative_to(static_dir).as_posix(), path))
    return files


def _copy_static(writer: _Writer, static_dir: Path) -> None:
    for relative, path in _static_files(static_dir):
        writer.write_bytes(relative, path.read_bytes())


def _summary(writer: _Writer, context: _Context, output: Path) -> dict[str, Any]:
    total = sum((writer.base / path).stat().st_size for path in writer.paths)
    return {
        "output_dir": str(output),
        "base_url": context.base_url,
        "source_commit": context.commit,
        "dataset": context.current.id,
        "dataset_label": context.current.label,
        "versions": len(context.versions),
        "sites": len(context.atlas.sites),
        "projects": len(context.atlas.projects),
        "evidence": len(context.atlas.evidence),
        "countries": len(context.atlas.countries),
        "html_pages": len(writer.pages),
        "files": len(writer.paths),
        "bytes": total,
    }


# --------------------------------------------------------------------------------------------
# Shared API objects


def _dataset_ref(context: _Context) -> dict[str, Any]:
    version = context.current
    return {
        "id": version.id,
        "label": version.label,
        "release_status": version.release_status,
        "publishable_as_final": version.publishable_as_final,
        "checkpoint_date": version.checkpoint_date,
        "lifecycle_reference_date": version.lifecycle_reference_date,
    }


def _dataset_full(context: _Context) -> dict[str, Any]:
    version = context.current
    return {
        **_dataset_ref(context),
        "status_window_days": context.config.status_window_days,
        "counts": context.atlas.counts,
        "manifest_sha256": version.manifest_sha256,
        "repository_path": f"{context.config.versions_root}/{version.id}",
        "window_start": context.window_start,
    }


def _endpoint_paths() -> dict[str, str]:
    return {
        "index": "api/v1/index.json",
        "sites": "api/v1/sites.json",
        "sites_geojson": "api/v1/sites.geojson",
        "site": "api/v1/sites/{site_id}.json",
        "projects": "api/v1/projects.json",
        "project": "api/v1/projects/{project_id}.json",
        "evidence": "api/v1/evidence.json",
        "evidence_item": "api/v1/evidence/{evidence_id}.json",
        "countries": "api/v1/countries.json",
        "country": "api/v1/countries/{iso2}.json",
        "stats": "api/v1/stats.json",
        "versions": "api/v1/versions.json",
        "vocabularies": "api/v1/vocabularies.json",
    }


def _download_objects(context: _Context, prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "format": item.format,
            "media_type": item.media_type,
            "url": f"{prefix}downloads/{LATEST}/{item.name}",
            "bytes": item.size,
            "sha256": item.sha256,
        }
        for item in context.downloads
    ]


def _gates(context: _Context) -> dict[str, Any]:
    gates = context.atlas.selection_report.get("final_release_gates") or {}
    return gates if isinstance(gates, dict) else {}


def _gates_summary(context: _Context) -> dict[str, Any]:
    gates = _gates(context)
    failed = [name for name, gate in gates.items() if not (isinstance(gate, dict) and gate.get("passed") is True)]
    total = len(gates)
    if context.current.publishable_as_final:
        text = "Final release"
    elif total:
        text = f"{len(failed)} of {total} release gates are not met"
    else:
        text = "release gates are not recorded"
    return {"total": total, "passed": total - len(failed), "failed": len(failed), "failed_gates": failed, "text": text}


def _replace_lists_with_lengths(value: Any) -> Any:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return {key: _replace_lists_with_lengths(item) for key, item in value.items()}
    return value


def _site_document(context: _Context, site: Mapping[str, Any]) -> dict[str, Any]:
    atlas = context.atlas
    site_id = site["site_id"]
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "site": site,
        "projects": atlas.projects_by_site[site_id],
        "evidence": atlas.evidence_by_site[site_id],
        "links": {
            "html": site["url"],
            "sites": f"{context.base_url}api/v1/sites.json",
            "dataset_download": f"{context.base_url}downloads/{context.current.id}/{context.zip_name}",
        },
    }


def _feature(summary: Mapping[str, Any], geometry: Any) -> dict[str, Any]:
    return {"type": "Feature", "id": summary["site_id"], "geometry": geometry, "properties": summary}


# --------------------------------------------------------------------------------------------
# JSON API


def _write_api(writer: _Writer, context: _Context) -> None:
    atlas = context.atlas
    writer.write_json("api/v1/index.json", _api_index(context))
    writer.write_json("api/v1/sites.json", atlas.summaries)
    writer.write_json("api/v1/sites.geojson", _sites_geojson(context))
    for site in atlas.sites:
        writer.write_json(f"api/v1/sites/{site['site_id']}.json", _site_document(context, site))
    writer.write_json("api/v1/projects.json", atlas.projects)
    for project in atlas.projects:
        writer.write_json(f"api/v1/projects/{project['project_id']}.json", _project_document(context, project))
    writer.write_json("api/v1/evidence.json", atlas.evidence)
    for evidence in atlas.evidence:
        writer.write_json(f"api/v1/evidence/{evidence['evidence_id']}.json", _evidence_document(context, evidence))
    writer.write_json("api/v1/countries.json", atlas.countries)
    for country in atlas.countries:
        writer.write_json(f"api/v1/countries/{country['country_iso_a2']}.json", {
            "api_version": API_VERSION,
            "dataset": _dataset_ref(context),
            "country": country,
            "sites": [atlas.summary_by_id[site_id] for site_id in _sorted_site_ids(atlas, country["site_ids"])],
        })
    writer.write_json("api/v1/stats.json", _stats(context))
    writer.write_json("api/v1/versions.json", _versions_document(context))
    writer.write_json("api/v1/vocabularies.json", {"api_version": API_VERSION, **context.vocabularies})


def _sorted_site_ids(atlas: Atlas, site_ids: Iterable[str]) -> list[str]:
    return sorted(site_ids, key=lambda site_id: _name_key(atlas.summary_by_id[site_id], "site_id"))


def _api_index(context: _Context) -> dict[str, Any]:
    config = context.config
    base = context.base_url
    return {
        "api_version": API_VERSION,
        "name": config.site_name,
        "description": config.tagline,
        "base_url": base,
        "repository_url": config.repository_url,
        "dataset": _dataset_full(context),
        "endpoints": {key: base + path for key, path in _endpoint_paths().items()},
        "downloads": _download_objects(context, base),
        "license": {"data": dict(config.data_license), "code": dict(config.code_license)},
        "attribution_url": f"{base}about/attribution/",
        "docs_url": f"{base}api/",
        "build": {"source_commit": context.commit},
    }


def _sites_geojson(context: _Context) -> dict[str, Any]:
    atlas = context.atlas
    return {
        "type": "FeatureCollection",
        "name": GEOJSON_LAYER_NAME,
        "dataset": {
            "id": context.current.id,
            "label": context.current.label,
            "release_status": context.current.release_status,
        },
        "features": [
            _feature(summary, atlas.site_by_id[summary["site_id"]]["geometry"]) for summary in atlas.summaries
        ],
    }


def _project_document(context: _Context, project: Mapping[str, Any]) -> dict[str, Any]:
    atlas = context.atlas
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "project": project,
        "site": atlas.summary_by_id[project["site_id"]],
        "evidence": atlas.evidence_by_project[project["project_id"]],
        "links": {
            "html": project["url"],
            "site": atlas.site_by_id[project["site_id"]]["api_url"],
            "dataset_download": f"{context.base_url}downloads/{context.current.id}/{context.zip_name}",
        },
    }


def _evidence_document(context: _Context, evidence: Mapping[str, Any]) -> dict[str, Any]:
    atlas = context.atlas
    projects = sorted(
        (atlas.project_by_id[project_id] for project_id in dict.fromkeys(evidence.get("project_ids") or [])),
        key=lambda item: _name_key(item, "project_id"),
    )
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "evidence": evidence,
        "projects": [
            {
                "project_id": project["project_id"],
                "name": project.get("name"),
                "site_id": project["site_id"],
                "status": project.get("last_observed_physical_status"),
                "status_as_of": project.get("status_as_of"),
                "url": project["url"],
                "api_url": project["api_url"],
            }
            for project in projects
        ],
        "sites": [
            {
                "site_id": site_id,
                "name": atlas.site_by_id[site_id].get("name"),
                "url": atlas.site_by_id[site_id]["url"],
                "api_url": atlas.site_by_id[site_id]["api_url"],
            }
            for site_id in evidence["site_ids"]
        ],
    }


def _stats(context: _Context) -> dict[str, Any]:
    atlas = context.atlas
    projects, sites, evidence = atlas.projects, atlas.sites, atlas.evidence
    months = Counter(str(project.get("status_as_of") or "")[:7] for project in projects if project.get("status_as_of"))
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "counts": atlas.counts,
        "by_status": _ordered_counts(Counter(str(project.get("last_observed_physical_status")) for project in projects)),
        "by_country": _ordered_counts(Counter(str(site.get("country")) for site in sites)),
        "by_status_month": dict(sorted(months.items())),
        "by_geometry_type": _ordered_counts(Counter(str(site.get("geometry_type")) for site in sites)),
        "by_locator_scope": _ordered_counts(Counter(str(project.get("geometry_use_scope")) for project in projects)),
        "by_verification_posture": _ordered_counts(Counter(str(project.get("verification_posture")) for project in projects)),
        "by_evidence_kind": _ordered_counts(Counter(str(item.get("kind")) for item in evidence)),
        "by_evidence_license": _ordered_counts(Counter(item.get("license") or "unspecified" for item in evidence)),
        "by_power_metric": _ordered_counts(Counter(
            str(item.get("metric")) for project in projects for item in _dict_items(project.get("power_observations"))
        )),
        "release_gates": _replace_lists_with_lengths(_gates(context)),
    }


def _version_changes(context: _Context) -> dict[str, tuple[list[str], list[str]]]:
    changes = {}
    previous: set[str] = set()
    for version in context.versions:
        current = set(context.version_sites[version.id])
        changes[version.id] = (sorted(current - previous), sorted(previous - current))
        previous = current
    return changes


def _versions_document(context: _Context) -> dict[str, Any]:
    base = context.base_url
    changes = _version_changes(context)
    versions = []
    for version in context.versions:
        added, removed = changes[version.id]
        versions.append({
            "id": version.id,
            "kind": version.kind,
            "label": version.label,
            "checkpoint_date": version.checkpoint_date,
            "lifecycle_reference_date": version.lifecycle_reference_date,
            "release_status": version.release_status,
            "publishable_as_final": version.publishable_as_final,
            "counts": dict(version.counts),
            "manifest_sha256": version.manifest_sha256,
            "files": [
                {
                    "name": item.name,
                    "bytes": item.size,
                    "sha256": item.sha256,
                    "url": f"{base}downloads/{version.id}/{item.name}",
                }
                for item in version.files
            ],
            "download_base_url": f"{base}downloads/{version.id}/",
            "repository_url": _tree_url(context, version),
            "added_site_ids": added,
            "removed_site_ids": removed,
        })
    return {
        "api_version": API_VERSION,
        "current": context.current.id,
        "last_preview": context.last_preview.id,
        "versions": versions,
    }


def _tree_url(context: _Context, version: DatasetVersion) -> str:
    path = "/".join(quote(part) for part in f"{context.config.versions_root}/{version.id}".split("/"))
    return f"{context.config.repository_url}/tree/main/{path}"


# --------------------------------------------------------------------------------------------
# Downloads


def _write_downloads(writer: _Writer, context: _Context) -> tuple[DownloadFile, ...]:
    current = context.current
    derived = _derived_downloads(context)
    for version in context.versions:
        directory = f"downloads/{version.id}"
        files = _copy_originals(writer, version, directory)
        if version.id == current.id:
            files.update(_write_named(writer, directory, derived))
            zip_bytes = _zip_archive(writer, directory, files)
            files[context.zip_name] = _write_named(writer, directory, {context.zip_name: zip_bytes})[context.zip_name]
        _write_checksums(writer, directory, files)
    latest = f"downloads/{LATEST}"
    files = _copy_originals(writer, current, latest)
    files.update(_write_named(writer, latest, derived))
    zip_bytes = _zip_archive(writer, latest, files)
    latest_zip = f"datacenter-atlas-{LATEST}.zip"
    files.update(_write_named(writer, latest, {latest_zip: zip_bytes}))
    files["SHA256SUMS"] = _write_checksums(writer, latest, files)
    return tuple(_download_file(name, files[name]) for name in _download_display_order(files))


def _copy_originals(writer: _Writer, version: DatasetVersion, directory: str) -> dict[str, tuple[int, str]]:
    files = {}
    for record in version.files:
        data = _read_regular_bytes(version.path / record.name)
        if len(data) != record.size or _sha256(data) != record.sha256:
            raise PublicSiteError(f"{version.path / record.name} changed after validation")
        writer.write_bytes(f"{directory}/{record.name}", data)
        files[record.name] = (record.size, record.sha256)
    return files


def _write_named(writer: _Writer, directory: str, items: Mapping[str, bytes]) -> dict[str, tuple[int, str]]:
    written = {}
    for name, data in items.items():
        writer.write_bytes(f"{directory}/{name}", data)
        written[name] = (len(data), _sha256(data))
    return written


def _zip_archive(writer: _Writer, directory: str, files: Mapping[str, tuple[int, str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (writer.base / directory / name).read_bytes(), compresslevel=9)
    return buffer.getvalue()


def _write_checksums(writer: _Writer, directory: str, files: Mapping[str, tuple[int, str]]) -> tuple[int, str]:
    text = "".join(f"{files[name][1]}  {name}\n" for name in sorted(files))
    data = text.encode("ascii")
    writer.write_bytes(f"{directory}/SHA256SUMS", data)
    return len(data), _sha256(data)


def _download_display_order(files: Mapping[str, Any]) -> list[str]:
    order = {name: index for index, name in enumerate(DOWNLOAD_ORDER)}
    zips = sorted(name for name in files if name.endswith(".zip"))
    rest = [name for name in files if name not in zips and name != "SHA256SUMS"]
    rest.sort(key=lambda name: (order.get(name, len(order)), name))
    return zips + rest + (["SHA256SUMS"] if "SHA256SUMS" in files else [])


def _download_file(name: str, meta: tuple[int, str]) -> DownloadFile:
    if name in DOWNLOAD_INFO:
        file_format, media_type, description = DOWNLOAD_INFO[name]
    elif name.endswith(".zip"):
        file_format, media_type, description = "ZIP", "application/zip", "Every file in this directory except SHA256SUMS."
    else:
        file_format, media_type = EXTENSION_INFO.get(Path(name).suffix, ("File", "application/octet-stream"))
        description = "Original checkpoint file."
    return DownloadFile(name, meta[0], meta[1], file_format, media_type, description)


def _derived_downloads(context: _Context) -> dict[str, bytes]:
    atlas = context.atlas
    sqlite_bytes = _sqlite_database(context)
    items = {
        "atlas.json": _json_text({
            "dataset": _dataset_full(context),
            "sites": atlas.sites,
            "projects": atlas.projects,
            "evidence": atlas.evidence,
        }, pretty=True).encode("utf-8"),
        "sites.ndjson": _ndjson(atlas.sites),
        "projects.ndjson": _ndjson(atlas.projects),
        "evidence.ndjson": _ndjson(atlas.evidence),
        "atlas.sqlite": sqlite_bytes,
        "sites.kml": _kml(context),
    }
    items["datapackage.json"] = _datapackage(context, sqlite_bytes)
    return dict(sorted(items.items()))


def _ndjson(records: Iterable[Any]) -> bytes:
    return "".join(_json_text(record) for record in records).encode("utf-8")


# SQLite ------------------------------------------------------------------------------------


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_database(context: _Context) -> bytes:
    with tempfile.TemporaryDirectory(prefix="atlas-sqlite-") as directory:
        path = Path(directory) / "atlas.sqlite"
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            _sqlite_schema(connection, context)
            _sqlite_rows(connection, context)
            connection.commit()
            problems = connection.execute("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise PublicSiteError(f"atlas.sqlite: foreign key violations {problems[:5]}")
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
            connection.execute("VACUUM")
        except sqlite3.Error as error:
            raise PublicSiteError(f"atlas.sqlite: {error}") from error
        finally:
            connection.close()
        return _normalize_sqlite_header(path.read_bytes())


SQLITE_HEADER = b"SQLite format 3\x00"
SQLITE_WRITER_VERSION = slice(96, 100)


def _normalize_sqlite_header(data: bytes) -> bytes:
    """Zero the header field naming the SQLite library version that last wrote the file.

    Bytes 96-99 hold SQLITE_VERSION_NUMBER of the writing library. SQLite only reports it (for
    example in ``.dbinfo``) and never relies on it, but it changes whenever the runner's SQLite
    is upgraded, which would change the published checksum of identical data. Every other header
    field, including the version-valid-for number at offset 92, is left untouched.
    """
    if len(data) < 100 or not data.startswith(SQLITE_HEADER):
        raise PublicSiteError("atlas.sqlite: unexpected file header")
    normalized = bytearray(data)
    normalized[SQLITE_WRITER_VERSION] = bytes(4)
    return bytes(normalized)


def _sqlite_foreign_keys(context: _Context) -> dict[str, list[tuple[str, str, str]]]:
    keys: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    declared = context.atlas.schema.get("foreign_keys") or []
    for item in declared if isinstance(declared, list) else []:
        source, target = item.get("from"), item.get("to")
        if not (isinstance(source, list) and isinstance(target, list) and len(source) == 2 and len(target) == 2):
            continue
        if source[0] in TABLE_NAMES and target[0] in TABLE_NAMES:
            keys[TABLE_NAMES[source[0]]].append((source[1], TABLE_NAMES[target[0]], target[1]))
    if ("site_id", "sites", "site_id") not in keys["projects"]:
        keys["projects"].insert(0, ("site_id", "sites", "site_id"))
    return keys


def _sqlite_schema(connection: sqlite3.Connection, context: _Context) -> None:
    atlas = context.atlas
    foreign = _sqlite_foreign_keys(context)
    indexes = []
    for file_name in ("sites.csv", "evidence.csv", "projects.csv"):
        table = TABLE_NAMES[file_name]
        primary = (atlas.schema["tables"][file_name].get("primary_key") or [])
        lines = []
        for spec in atlas.fields[file_name]:
            logical = str(spec.get("logical_type", "string"))
            column = f"  {_quote_identifier(spec['name'])} {SQL_TYPES.get(logical, 'TEXT')}"
            if spec.get("allows_empty_string") is False:
                column += " NOT NULL"
            if logical == "boolean":
                column += f" CHECK ({_quote_identifier(spec['name'])} IN (0, 1))"
            lines.append(column)
        if primary:
            lines.append(f"  PRIMARY KEY ({', '.join(_quote_identifier(name) for name in primary)})")
        for column, target_table, target_column in foreign.get(table, []):
            lines.append(
                f"  FOREIGN KEY ({_quote_identifier(column)}) REFERENCES "
                f"{_quote_identifier(target_table)} ({_quote_identifier(target_column)})"
            )
            indexes.append((table, column))
        connection.execute(f"CREATE TABLE {_quote_identifier(table)} (\n" + ",\n".join(lines) + "\n)")
    connection.executescript(
        """
CREATE TABLE "project_evidence" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "evidence_id" TEXT NOT NULL REFERENCES "evidence" ("evidence_id"),
  PRIMARY KEY ("project_id", "evidence_id")
);
CREATE TABLE "evidence_roles" (
  "evidence_id" TEXT NOT NULL REFERENCES "evidence" ("evidence_id"),
  "role" TEXT NOT NULL,
  PRIMARY KEY ("evidence_id", "role")
);
CREATE TABLE "power_observations" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "metric" TEXT, "stage" TEXT, "low" REAL, "base" REAL, "high" REAL, "unit" TEXT,
  "as_of_date" TEXT, "target_date" TEXT, "method" TEXT, "confidence" REAL,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id"),
  "notes" TEXT
);
CREATE TABLE "role_claims" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "role" TEXT, "party" TEXT, "relationship_scope" TEXT,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id")
);
CREATE TABLE "workload_observations" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "workload" TEXT, "deployment_scope" TEXT, "method" TEXT, "confidence" REAL, "as_of_date" TEXT,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id")
);
CREATE TABLE "metadata" ("key" TEXT PRIMARY KEY, "value" TEXT);
CREATE VIEW "site_overview" AS
  SELECT "site_id", "name", "country", "country_iso_a2", "latitude", "longitude",
         "statuses_json", "newest_status_as_of", "project_count"
  FROM "sites";
"""
    )
    indexes += [
        ("project_evidence", "evidence_id"),
        ("power_observations", "project_id"), ("power_observations", "evidence_id"),
        ("role_claims", "project_id"), ("role_claims", "evidence_id"),
        ("workload_observations", "project_id"), ("workload_observations", "evidence_id"),
    ]
    for table, column in indexes:
        name = _quote_identifier(f"idx_{table}_{column}")
        connection.execute(
            f"CREATE INDEX {name} ON {_quote_identifier(table)} ({_quote_identifier(column)})"
        )


def _sqlite_rows(connection: sqlite3.Connection, context: _Context) -> None:
    atlas = context.atlas
    for file_name in ("sites.csv", "evidence.csv", "projects.csv"):
        fields = atlas.fields[file_name]
        placeholders = ", ".join("?" for _ in fields)
        connection.executemany(
            f"INSERT INTO {_quote_identifier(TABLE_NAMES[file_name])} VALUES ({placeholders})",
            [
                tuple(_sql_value(row[spec["name"]], str(spec.get("logical_type", "string")), spec["name"]) for spec in fields)
                for row in atlas.raw[file_name]
            ],
        )
    links = sorted({(project_id, item["evidence_id"]) for item in atlas.evidence for project_id in item.get("project_ids") or []})
    connection.executemany('INSERT INTO "project_evidence" VALUES (?, ?)', links)
    roles = sorted({(item["evidence_id"], str(role)) for item in atlas.evidence for role in item.get("roles") or []})
    connection.executemany('INSERT INTO "evidence_roles" VALUES (?, ?)', roles)
    power, claims, workloads = [], [], []
    for project in atlas.projects:
        project_id = project["project_id"]
        for item in _dict_items(project.get("power_observations")):
            power.append((project_id, *(item.get(key) for key in (
                "metric", "stage", "low", "base", "high", "unit", "as_of_date", "target_date",
                "method", "confidence", "evidence_id", "notes",
            ))))
        for item in _dict_items(project.get("role_claims")):
            claims.append((project_id, *(item.get(key) for key in ("role", "party", "relationship_scope", "evidence_id"))))
        for item in _dict_items(project.get("workloads")):
            workloads.append((project_id, *(item.get(key) for key in (
                "workload", "deployment_scope", "method", "confidence", "as_of_date", "evidence_id",
            ))))
    connection.executemany(f'INSERT INTO "power_observations" VALUES ({", ".join("?" * 13)})', power)
    connection.executemany('INSERT INTO "role_claims" VALUES (?, ?, ?, ?, ?)', claims)
    connection.executemany('INSERT INTO "workload_observations" VALUES (?, ?, ?, ?, ?, ?, ?)', workloads)
    connection.executemany('INSERT INTO "metadata" VALUES (?, ?)', _sqlite_metadata(context))


def _sqlite_metadata(context: _Context) -> list[tuple[str, str]]:
    version, config = context.current, context.config
    return [
        ("dataset_id", version.id),
        ("dataset_label", version.label),
        ("release_status", version.release_status),
        ("publishable_as_final", "true" if version.publishable_as_final else "false"),
        ("checkpoint_date", version.checkpoint_date),
        ("lifecycle_reference_date", version.lifecycle_reference_date),
        ("status_window_days", str(config.status_window_days)),
        ("manifest_sha256", version.manifest_sha256),
        ("repository_url", config.repository_url),
        ("repository_path", f"{config.versions_root}/{version.id}"),
        ("site_url", context.base_url),
        ("data_license", str(config.data_license.get("id", ""))),
        ("data_license_url", str(config.data_license.get("url", ""))),
        ("attribution", "Third-party facts and geometries keep their source terms; see ATTRIBUTION.txt and evidence.license."),
        ("api_version", API_VERSION),
        ("schema_note", (
            "Tables sites, projects and evidence keep the CSV column names; empty CSV values are NULL; "
            "booleans are 0/1; *_json columns hold JSON text."
        )),
    ]


# KML ---------------------------------------------------------------------------------------


def _kml(context: _Context) -> bytes:
    atlas = context.atlas
    title = f"{context.config.site_name} — {context.current.label}"
    description = (
        f"<p>{_e(context.current.label)} (checkpoint {_e(context.current.checkpoint_date)}). "
        "Statuses are the last observed physical status on the status date; locators are not "
        f"footprints. Source terms: {_e(context.base_url)}about/attribution/</p>"
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        f"<name>{_x(title)}</name>",
        f"<description>{_x(description)}</description>",
    ]
    for summary in atlas.summaries:
        lines.extend(_kml_placemark(context, summary))
    lines += ["</Document>", "</kml>"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _kml_placemark(context: _Context, summary: Mapping[str, Any]) -> list[str]:
    site = context.atlas.site_by_id[summary["site_id"]]
    statuses = [str(code) for code in summary.get("statuses") or []]
    status_text = ", ".join(context.vocabulary.label("statuses", code) for code in statuses) or "Unknown"
    description = (
        f"<p><strong>{_e(summary.get('name'))}</strong></p>"
        f"<p>Last observed physical status: {_e(status_text)} "
        f"(newest status date {_e(summary.get('newest_status_as_of'))}).</p>"
        f"<p>Projects: {_e(summary.get('project_count'))}. Country: {_e(summary.get('country'))}.</p>"
        f'<p><a href="{_e(summary["url"])}">Site page with evidence</a></p>'
    )
    data = (
        ("site_id", summary["site_id"]),
        ("country", summary.get("country")),
        ("country_iso_a2", summary.get("country_iso_a2")),
        ("statuses", ";".join(statuses)),
        ("newest_status_as_of", summary.get("newest_status_as_of")),
        ("project_count", summary.get("project_count")),
        ("official_boundary", "true" if summary.get("official_boundary") else "false"),
        ("url", summary["url"]),
    )
    return [
        f'<Placemark id="{_x("site-" + summary["site_id"])}">',
        f"<name>{_x(summary.get('name'))}</name>",
        f"<description>{_x(description)}</description>",
        "<ExtendedData>",
        *(f'<Data name="{_x(name)}"><value>{_x(value)}</value></Data>' for name, value in data),
        "</ExtendedData>",
        _kml_geometry(site["geometry"], summary["site_id"]),
        "</Placemark>",
    ]


def _kml_geometry(geometry: Mapping[str, Any], site_id: str) -> str:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Point":
        return f"<Point><coordinates>{_kml_position(coordinates, site_id)}</coordinates></Point>"
    if kind == "Polygon":
        return _kml_polygon(coordinates, site_id)
    if kind == "MultiPolygon" and isinstance(coordinates, list):
        return "<MultiGeometry>" + "".join(_kml_polygon(polygon, site_id) for polygon in coordinates) + "</MultiGeometry>"
    raise PublicSiteError(f"sites.csv {site_id}: unsupported geometry type {kind!r}")


def _kml_polygon(rings: Any, site_id: str) -> str:
    if not isinstance(rings, list) or not rings:
        raise PublicSiteError(f"sites.csv {site_id}: polygon has no rings")
    outer, *inner = rings
    parts = [_kml_boundary("outerBoundaryIs", outer, site_id)]
    parts += [_kml_boundary("innerBoundaryIs", ring, site_id) for ring in inner]
    return "<Polygon>" + "".join(parts) + "</Polygon>"


def _kml_boundary(tag: str, ring: Any, site_id: str) -> str:
    return f"<{tag}><LinearRing><coordinates>{_kml_ring(ring, site_id)}</coordinates></LinearRing></{tag}>"


def _kml_ring(ring: Any, site_id: str) -> str:
    if not isinstance(ring, list) or not ring:
        raise PublicSiteError(f"sites.csv {site_id}: empty polygon ring")
    return " ".join(_kml_position(position, site_id) for position in ring)


def _kml_position(position: Any, site_id: str) -> str:
    if not isinstance(position, list) or len(position) < 2 or not all(_is_number(value) for value in position):
        raise PublicSiteError(f"sites.csv {site_id}: invalid coordinate {position!r}")
    return ",".join(_number_text(value) for value in position)


# Data package ------------------------------------------------------------------------------


def _datapackage(context: _Context, sqlite_bytes: bytes) -> bytes:
    config, version = context.config, context.current
    files = {record.name: record for record in version.files}
    resources = [_table_resource(context, file_name, files[file_name]) for file_name in TABLE_FILES if file_name in files]
    if "sites.geojson" in files:
        record = files["sites.geojson"]
        resources.append({
            "name": "sites-geojson",
            "path": "sites.geojson",
            "profile": "data-resource",
            "title": "Site locators and boundaries",
            "format": "geojson",
            "mediatype": "application/geo+json",
            "encoding": "utf-8",
            "bytes": record.size,
            "hash": f"sha256:{record.sha256}",
        })
    resources.append({
        "name": "atlas-sqlite",
        "path": "atlas.sqlite",
        "profile": "data-resource",
        "title": "SQLite database of the checkpoint",
        "format": "sqlite",
        "mediatype": "application/vnd.sqlite3",
        "bytes": len(sqlite_bytes),
        "hash": f"sha256:{_sha256(sqlite_bytes)}",
    })
    license_info = config.data_license
    package = {
        "profile": "data-package",
        "name": "datacenter-atlas",
        "title": f"{config.site_name} — {version.label}",
        "description": (
            f"{config.tagline}. {version.label}, checkpoint {version.checkpoint_date}, "
            f"lifecycle reference date {version.lifecycle_reference_date}. "
            f"Release status: {version.release_status}; not a final release unless publishable_as_final is true. "
            "Statuses are the last observed physical status on the status date; locators are not footprints."
        ),
        "version": version.id,
        "homepage": context.base_url,
        "keywords": ["data centres", "data centers", "construction", "infrastructure", "geospatial", "open data"],
        "licenses": [{
            "name": str(license_info.get("id", "")),
            "title": str(license_info.get("name", "")),
            "path": str(license_info.get("url", "")),
        }],
        "sources": [
            {"title": f"{config.site_name} repository: {config.versions_root}/{version.id}", "path": _tree_url(context, version)},
            {"title": "Per-row third-party sources and terms (see evidence.csv and ATTRIBUTION.txt)", "path": "ATTRIBUTION.txt"},
        ],
        "contributors": [{
            "title": str(config.author.get("name", "")),
            "path": str(config.author.get("url", "")),
            "role": "author",
        }],
        "resources": resources,
    }
    return _json_text(package, pretty=True).encode("utf-8")


def _table_resource(context: _Context, file_name: str, record: FileRecord) -> dict[str, Any]:
    atlas = context.atlas
    table = TABLE_NAMES[file_name]
    descriptions = context.descriptions.get("tables", {}).get(file_name, {})
    fields = []
    for spec in atlas.fields[file_name]:
        logical = str(spec.get("logical_type", "string"))
        field_type, field_format = DATAPACKAGE_TYPES.get(logical, ("string", None))
        item: dict[str, Any] = {"name": spec["name"], "type": field_type}
        if field_format:
            item["format"] = field_format
        item["description"] = str(descriptions.get(spec["name"], ""))
        if logical == "boolean":
            item["trueValues"] = ["true"]
            item["falseValues"] = ["false"]
        if spec.get("allows_empty_string") is False:
            item["constraints"] = {"required": True}
        fields.append(item)
    schema: dict[str, Any] = {"fields": fields}
    primary = atlas.schema["tables"][file_name].get("primary_key")
    if primary:
        schema["primaryKey"] = list(primary)
    foreign = [
        {"fields": [column], "reference": {"resource": target_table, "fields": [target_column]}}
        for column, target_table, target_column in _sqlite_foreign_keys(context).get(table, [])
    ]
    if foreign:
        schema["foreignKeys"] = foreign
    schema["missingValues"] = [""]
    return {
        "name": table,
        "path": file_name,
        "profile": "tabular-data-resource",
        "title": f"{file_name} of {context.current.id}",
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": "utf-8",
        "bytes": record.size,
        "hash": f"sha256:{record.sha256}",
        "dialect": {"delimiter": ",", "lineTerminator": "\n", "quoteChar": "\"", "doubleQuote": True, "header": True},
        "schema": schema,
    }


# --------------------------------------------------------------------------------------------
# HTML helpers


def _e(value: Any) -> str:
    """HTML-escape any value (None -> empty string)."""
    return html.escape("" if value is None else str(value), quote=True)


def _x(value: Any) -> str:
    """XML-escape any value for element text or a double-quoted attribute.

    Characters XML 1.0 cannot represent (most C0 controls) become U+FFFD.
    """
    return html.escape(XML_INVALID.sub("\ufffd", "" if value is None else str(value)), quote=True)


def _safe_http_url(value: Any) -> str | None:
    """Return the URL unchanged when it is an absolute http(s) URL, else None."""
    if not isinstance(value, str) or not value or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    return value


def _external_link(url: Any, text: Any, *, classes: str = "") -> str:
    safe = _safe_http_url(url)
    if safe is None:
        return _e(text)
    class_names = " ".join(part for part in (classes, "external") if part)
    return f'<a class="{class_names}" rel="noopener" href="{_e(safe)}">{_e(text)}</a>'


def _linkify(text: str) -> str:
    """Escape text and turn http(s) URLs into external links."""
    parts, position = [], 0
    for match in URL_IN_TEXT.finditer(text):
        url = match.group(0)
        while url and url[-1] in TRAILING_URL_PUNCTUATION:
            if url[-1] == ")" and url.count("(") >= url.count(")"):
                break
            url = url[:-1]
        if not url or _safe_http_url(url) is None:
            continue
        parts.append(_e(text[position:match.start()]))
        parts.append(_external_link(url, url))
        position = match.start() + len(url)
    parts.append(_e(text[position:]))
    return "".join(parts)


def _script_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for raw, escaped in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(raw, escaped)
    return text


def _class_token(code: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(code or "unknown").lower())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number_text(value: Any) -> str:
    return str(value) if isinstance(value, int) else repr(float(value))


def _format_number(value: Any) -> str:
    if not _is_number(value):
        return "" if value is None else str(value)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,}"


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
    return f"{size} B"


def _relative_root(path: str) -> str:
    depth = path.count("/")
    return "./" if depth == 0 else "../" * depth


def _url_path(path: str) -> str:
    return path[: -len("index.html")] if path.endswith("index.html") else path


def _badge(vocabulary: Vocabulary, status: Any) -> str:
    return f'<span class="badge status-{_class_token(status)}">{_e(vocabulary.label("statuses", status))}</span>'


def _badges(vocabulary: Vocabulary, statuses: Iterable[Any]) -> str:
    return " ".join(_badge(vocabulary, status) for status in dict.fromkeys(statuses))


def _muted_unknown(reason: Any) -> str:
    text = str(reason).strip() if reason else "not established"
    return f'<span class="muted">Unknown: {_e(text)}</span>'


def _copy_button(text: str, label: str = "Copy") -> str:
    return f'<button type="button" class="btn btn-small copy-btn hidden-noscript" data-copy="{_e(text)}">{_e(label)}</button>'


def _code_block(code: str, *, copy: bool = True) -> str:
    button = _copy_button(code, "Copy code") if copy else ""
    return f'<pre class="code"><code>{_e(code)}</code></pre>{button}'


def _heading(level: int, anchor: str, text: str) -> str:
    return (
        f'<h{level} id="{_e(anchor)}">{_e(text)} '
        f'<a class="anchor" href="#{_e(anchor)}" aria-label="Link to this section">#</a></h{level}>'
    )


def _table(
    table_id: str | None,
    headers: Sequence[tuple[str, str]],
    rows: Iterable[str],
    *,
    classes: str = "data-table",
    caption: str | None = None,
    sorted_by: tuple[int, str] | None = None,
) -> str:
    """A wrapped data table; ``sorted_by`` = (column index, "ascending"|"descending") of the rows' order."""
    identifier = f' id="{_e(table_id)}"' if table_id else ""
    head = "".join(
        _header_cell(text, cell_class, sorted_by[1] if sorted_by and sorted_by[0] == index else None)
        for index, (text, cell_class) in enumerate(headers)
    )
    caption_html = f'<caption class="small muted">{_e(caption)}</caption>' if caption else ""
    body = "\n".join(rows)
    return (
        f'<div class="table-wrap"><table class="{classes}"{identifier}>{caption_html}'
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n{body}\n</tbody></table></div>"
    )


def _header_cell(text: str, cell_class: str, sort: str | None = None) -> str:
    class_attribute = f' class="{_e(cell_class)}"' if cell_class else ""
    sort_attribute = f' aria-sort="{_e(sort)}"' if sort else ""
    return f'<th scope="col"{class_attribute}{sort_attribute}>{_e(text)}</th>'


class _EvidenceAnchors:
    """Links to evidence rows of the current page; IDs not on the page produce no link."""

    def __init__(self, available: Iterable[str]) -> None:
        self.available = set(available)

    def __call__(self, evidence_id: Any, text: str = "evidence") -> str:
        if not isinstance(evidence_id, str) or evidence_id not in self.available:
            return ""
        return f' <a class="small" href="#evidence-{_e(evidence_id)}">{_e(text)}</a>'


def _kv(items: Iterable[tuple[str, str]]) -> str:
    return '<dl class="kv">' + "".join(f"<dt>{_e(term)}</dt><dd>{value}</dd>" for term, value in items) + "</dl>"


# --------------------------------------------------------------------------------------------
# Templates and tokens


def render_tokens(template: str, text_values: Mapping[str, str], html_values: Mapping[str, str], *, source: str) -> str:
    """Replace ``{{name}}`` (escaped text) and ``{{{name}}}`` (builder HTML) tokens.

    Unknown tokens, a text token in triple braces, an HTML token in double braces and any
    leftover ``{{`` are build errors.
    """

    def replace_token(match: re.Match[str]) -> str:
        html_name, text_name = match.group(1), match.group(2)
        if html_name is not None:
            if html_name in html_values:
                return html_values[html_name]
            if html_name in text_values:
                raise PublicSiteError(f"{source}: {{{{{{{html_name}}}}}}} is a text token; use {{{{{html_name}}}}}")
            raise PublicSiteError(f"{source}: unknown template token {{{{{{{html_name}}}}}}}")
        if text_name in text_values:
            return _e(text_values[text_name])
        if text_name in html_values:
            raise PublicSiteError(f"{source}: {{{{{text_name}}}}} inserts HTML; use {{{{{{{text_name}}}}}}}")
        raise PublicSiteError(f"{source}: unknown template token {{{{{text_name}}}}}")

    leftover = TOKEN.sub("", template)
    if "{{" in leftover:
        position = leftover.index("{{")
        raise PublicSiteError(f"{source}: malformed template token near {leftover[position:position + 40]!r}")
    return TOKEN.sub(replace_token, template)


def _load_fragment(context: _Context, relative: str) -> str:
    path = context.site_dir / relative
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PublicSiteError(f"missing template {path}") from error
    return HTML_COMMENT.sub("", text).strip()


def _token_values(context: _Context, root: str) -> tuple[dict[str, str], dict[str, str]]:
    config, current, preview = context.config, context.current, context.last_preview
    text = {
        "root": root,
        "site_name": config.site_name,
        "tagline": config.tagline,
        "base_url": context.base_url,
        "repository_url": config.repository_url,
        "issues_url": config.issues_url,
        "dataset.id": current.id,
        "dataset.label": current.label,
        "dataset.release_status": current.release_status,
        "dataset.checkpoint_date": current.checkpoint_date,
        "dataset.checkpoint_year": current.checkpoint_date[:4],
        "dataset.lifecycle_reference_date": current.lifecycle_reference_date,
        "dataset.status_window_days": str(config.status_window_days),
        "dataset.window_start": context.window_start,
        "last_preview.label": preview.label,
        "versions.count": str(len(context.versions)),
        "build.commit_short": context.commit_short,
    }
    text.update({f"counts.{key}": str(value) for key, value in context.atlas.counts.items()})
    text.update({f"last_preview.counts.{key}": str(value) for key, value in preview.counts.items()})
    markup = {"gates_table": _gates_table(context), "status_legend": _status_legend(context)}
    return text, markup


def _render_fragment(context: _Context, relative: str, root: str) -> str:
    text, markup = _token_values(context, root)
    return render_tokens(_load_fragment(context, relative), text, markup, source=f"site/{relative}")


def _status_legend(context: _Context) -> str:
    counts = Counter(str(project.get("last_observed_physical_status")) for project in context.atlas.projects)
    vocabulary = context.vocabularies["statuses"]
    ordered = [code for code in vocabulary if code in counts] + sorted(code for code in counts if code not in vocabulary)
    items = []
    for code in ordered:
        noun = "project" if counts[code] == 1 else "projects"
        description = context.vocabulary.description("statuses", code)
        items.append((
            _badge(context.vocabulary, code),
            f"{_e(description)} <span class=\"small muted\">{counts[code]} {noun}</span>",
        ))
    return '<dl class="kv">' + "".join(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in items) + "</dl>"


def _gates_table(context: _Context) -> str:
    rows = []
    for name, gate in _gates(context).items():
        gate = gate if isinstance(gate, dict) else {}
        passed = gate.get("passed") is True
        status = "Passed" if passed else "<strong>Not met</strong>"
        description = context.vocabulary.description("release_gates", name)
        label = context.vocabulary.label("release_gates", name)
        rows.append(
            f'<tr><th scope="row">{_e(label)}<br><span class="mono small muted">{_e(name)}</span></th>'
            f"<td>{status}</td><td>{_e(_gate_actual(name, gate))}</td><td>{_e(_gate_requirement(name, gate))}</td>"
            f"<td>{_e(_gate_notes(gate, description))}</td></tr>"
        )
    if not rows:
        return '<p class="muted">This checkpoint records no final-release gates.</p>'
    headers = (("Gate", ""), ("Status", ""), ("Actual", ""), ("Requirement", ""), ("Notes", ""))
    caption = f"Final-release gates recorded in selection-report.json of {context.current.id}"
    return _table("release-gates-table", headers, rows, caption=caption)


def _gate_value(name: str, value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and "share" in name:
        return f"{value * 100:.1f}%"
    if isinstance(value, list):
        return str(len(value))
    return _format_number(value)


def _gate_actual(name: str, gate: Mapping[str, Any]) -> str:
    if "actual" in gate:
        return _gate_value(name, gate["actual"])
    parts = []
    for key, value in gate.items():
        if f"required_{key}" in gate and _is_number(value):
            parts.append(f"{key.replace('_', ' ')} {_gate_value(name, value)}")
    return "; ".join(parts) or "—"


def _gate_requirement(name: str, gate: Mapping[str, Any]) -> str:
    parts = []
    if "required" in gate:
        parts.append(_gate_value(name, gate["required"]))
    if "required_minimum" in gate:
        parts.append(f"≥ {_gate_value(name, gate['required_minimum'])}")
    if "required_maximum" in gate:
        parts.append(f"≤ {_gate_value(name, gate['required_maximum'])}")
    for key, value in gate.items():
        if key.startswith("required_") and key not in {"required_minimum", "required_maximum"} and _is_number(value):
            parts.append(f"{key.removeprefix('required_').replace('_', ' ')} ≥ {_gate_value(name, value)}")
    return "; ".join(parts) or "—"


def _gate_notes(gate: Mapping[str, Any], description: str) -> str:
    notes = [description] if description else []
    for key in ("reason", "sample_scope", "population_scope"):
        if isinstance(gate.get(key), str):
            notes.append(gate[key])
    for key, value in gate.items():
        if isinstance(value, dict) and "passed" in value:
            outcome = "passed" if value.get("passed") is True else "not met"
            notes.append(f"{key.replace('_', ' ').capitalize()}: {outcome}.")
    sentences = (note.strip() for note in notes if note.strip())
    # Report strings are lower-case clauses; each becomes its own capitalised sentence.
    return " ".join(
        sentence[:1].upper() + sentence[1:] + ("" if sentence.endswith(".") else ".") for sentence in sentences
    )


# --------------------------------------------------------------------------------------------
# Page layout


@dataclass(frozen=True)
class _Page:
    path: str
    slug: str
    section: str | None
    title: str
    description: str
    body: str
    main_class: str = "page"
    scripts: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    json_ld: Mapping[str, Any] | None = None
    data_blocks: tuple[tuple[str, Any], ...] = ()
    absolute_root: bool = False
    in_sitemap: bool = True


def _asset_url(context: _Context, root: str, relative: str) -> str:
    if relative not in context.static_files:
        raise PublicSiteError(f"site/static/{relative} is missing (referenced by the page layout)")
    return f"{root}{relative}"


def _map_scripts(context: _Context, page_script: str) -> tuple[str, ...]:
    """Leaflet, then the optional shared logic module when present, then the page's map script."""
    core = (ATLAS_CORE_JS,) if ATLAS_CORE_JS in context.static_files else ()
    return (LEAFLET_JS, *core, page_script)


def _render_page(context: _Context, page: _Page) -> str:
    config = context.config
    root = context.base_url if page.absolute_root else _relative_root(page.path)
    canonical = context.base_url + _url_path(page.path)
    if page.slug == "home":
        title = f"{config.site_name} — {config.tagline}"
    else:
        title = f"{page.title} · {config.site_name}"
    head = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_e(title)}</title>",
        f'<meta name="description" content="{_e(page.description)}">',
        f'<link rel="canonical" href="{_e(canonical)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{_e(title)}">',
        f'<meta property="og:description" content="{_e(page.description)}">',
        f'<meta property="og:url" content="{_e(canonical)}">',
        f'<meta property="og:site_name" content="{_e(config.site_name)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta http-equiv="Content-Security-Policy" content="{CONTENT_SECURITY_POLICY}">',
        '<meta name="color-scheme" content="light dark">',
        f'<link rel="icon" href="{_e(_asset_url(context, root, FAVICON))}" type="image/svg+xml">',
        *(f'<link rel="stylesheet" href="{_e(_asset_url(context, root, style))}">' for style in page.styles),
        f'<link rel="stylesheet" href="{_e(_asset_url(context, root, SITE_CSS))}">',
        f'<link rel="alternate" type="application/atom+xml" title="{_e(FEED_TITLE)}" href="{_e(root)}feed.xml">',
    ]
    if page.json_ld is not None:
        head.append(f'<script type="application/ld+json">{_script_json(page.json_ld)}</script>')
    head.append("</head>")
    body = [
        f'<body class="page-{_class_token(page.slug).replace("_", "-")}">',
        '<a class="skip-link" href="#main">Skip to content</a>',
        _render_header(context, root, page.section),
        _render_banner(context, root),
        f'<main id="main" class="{_e(page.main_class)}">',
        page.body,
        "</main>",
        _render_footer(context, root),
        *(f'<script type="application/json" id="{_e(name)}">{_script_json(value)}</script>' for name, value in page.data_blocks),
        *(f'<script src="{_e(_asset_url(context, root, script))}" defer></script>' for script in page.scripts),
        "</body></html>",
    ]
    return "\n".join(line for line in head + body if line) + "\n"


def _render_header(context: _Context, root: str, section: str | None) -> str:
    links = []
    for key, path, label in NAVIGATION:
        current = ' aria-current="page"' if key == section else ""
        links.append(f'<a href="{_e(root + path)}"{current}>{_e(label)}</a>')
    return (
        '<header class="site-header">\n'
        f'  <a class="brand" href="{_e(root)}"><img src="{_e(root + FAVICON)}" alt="" width="24" height="24"> '
        f"{_e(context.config.site_name)}</a>\n"
        '  <nav class="site-nav" aria-label="Primary">\n    '
        + "\n    ".join(links)
        + "\n  </nav>\n</header>"
    )


def _render_banner(context: _Context, root: str) -> str:
    if context.current.publishable_as_final:
        return ""
    current = context.current
    return (
        '<div class="preview-banner" role="note"><strong>Preview data.</strong> '
        f"{_e(current.label)}, checkpoint {_e(current.checkpoint_date)}. "
        f"Not a final release: {_e(_gates_summary(context)['text'])}. "
        f'<a href="{_e(root)}methodology/#release-gates">Why</a></div>'
    )


def _render_footer(context: _Context, root: str) -> str:
    config = context.config
    data_license = str(config.data_license.get("id", "")).replace("-", " ")
    code_license = str(config.code_license.get("id", "")).replace("-", " ")
    if context.commit:
        commit_url = f"{config.repository_url}/commit/{context.commit}"
        built = f'<a class="external" rel="noopener" href="{_e(commit_url)}"><code>{_e(context.commit_short)}</code></a>'
    else:
        built = f"<code>{_e(context.commit_short)}</code>"
    return (
        '<footer class="site-footer">\n'
        f"  <p>Data: {_e(data_license)} for Atlas-authored content; third-party facts and geometries keep their "
        f'source terms (<a href="{_e(root)}about/attribution/">attribution &amp; legal notices</a>). '
        f"Code: {_e(code_license)}.</p>\n"
        f'  <p><a class="external" rel="noopener" href="{_e(config.repository_url)}">Source on GitHub</a> · '
        f'<a href="{_e(root)}api/v1/index.json">API</a> · <a href="{_e(root)}feed.xml">Releases feed</a> · '
        f"Built from {built} · Dataset {_e(context.current.id)}</p>\n"
        "</footer>"
    )


def _write_page(writer: _Writer, context: _Context, page: _Page) -> None:
    writer.write_text(page.path, _render_page(context, page))
    if page.in_sitemap:
        writer.pages.append(page.path)


# --------------------------------------------------------------------------------------------
# JSON-LD


def _dataset_json_ld(context: _Context) -> dict[str, Any]:
    config, current = context.config, context.current
    counts = context.atlas.counts
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"{config.site_name}: {current.label}",
        "description": (
            f"{config.tagline}. Evidence-linked records of {counts.get('physical_sites')} physical data-centre sites "
            f"and {counts.get('projects')} construction projects in {counts.get('countries')} countries, each with a "
            "dated last observed physical status from an authoritative source and a reviewed locator. "
            f"{current.label}; not a final release."
        ),
        "url": context.base_url,
        "sameAs": config.repository_url,
        "identifier": current.id,
        "version": current.id,
        "isAccessibleForFree": True,
        "license": str(config.data_license.get("url", "")),
        "creator": {
            "@type": "Person",
            "name": str(config.author.get("name", "")),
            "url": str(config.author.get("url", "")),
        },
        "keywords": ["data centres", "data centers", "construction", "infrastructure", "geospatial", "open data"],
        "temporalCoverage": f"{context.window_start}/{current.lifecycle_reference_date}",
        "dateModified": current.checkpoint_date,
        "distribution": [
            {
                "@type": "DataDownload",
                "name": item.name,
                "encodingFormat": item.media_type,
                "contentUrl": f"{context.base_url}downloads/{LATEST}/{item.name}",
                "contentSize": f"{item.size} B",
            }
            for item in context.downloads
        ],
    }


# --------------------------------------------------------------------------------------------
# Pages


def _write_pages(writer: _Writer, context: _Context) -> None:
    _write_page(writer, context, _explorer_page(context))
    _write_page(writer, context, _sites_index_page(context))
    for summary in context.atlas.summaries:
        _write_page(writer, context, _site_page(context, summary))
    _write_page(writer, context, _countries_page(context))
    for country in context.atlas.countries:
        _write_page(writer, context, _country_page(context, country))
    _write_page(writer, context, _data_page(context))
    _write_page(writer, context, _dictionary_page(context))
    _write_page(writer, context, _api_page(context))
    _write_page(writer, context, _content_page(context, "methodology"))
    _write_page(writer, context, _versions_page(context))
    _write_page(writer, context, _content_page(context, "about"))
    _write_page(writer, context, _attribution_page(context))
    _write_page(writer, context, _not_found_page(context))


def _explorer_page(context: _Context) -> _Page:
    path = "index.html"
    body = _render_fragment(context, "templates/explorer.html", _relative_root(path))
    counts = context.atlas.counts
    description = (
        f"Map and list of {counts.get('physical_sites')} data-centre construction sites in "
        f"{counts.get('countries')} countries, each with a dated, evidence-linked last observed physical status."
    )
    return _Page(
        path=path,
        slug="home",
        section="explore",
        title=context.config.site_name,
        description=description,
        body=body,
        main_class="explorer",
        scripts=_map_scripts(context, APP_JS),
        styles=(LEAFLET_CSS,),
        json_ld=_dataset_json_ld(context),
        data_blocks=(("atlas-bootstrap", _bootstrap(context)),),
    )


def _bootstrap(context: _Context) -> dict[str, Any]:
    config = context.config
    return {
        "api_version": API_VERSION,
        "site_name": config.site_name,
        "root": "./",
        "base_url": context.base_url,
        "repository_url": config.repository_url,
        "issues_url": config.issues_url,
        "dataset": {
            **_dataset_ref(context),
            "status_window_days": config.status_window_days,
            "counts": context.atlas.counts,
            "window_start": context.window_start,
        },
        "endpoints": _endpoint_paths(),
        "downloads": _download_objects(context, ""),
        "vocabularies": context.vocabularies,
        "gates_summary": _gates_summary(context),
        "pages": {
            "sites": "sites/",
            "site": "sites/{site_id}/",
            "countries": "countries/",
            "country": "countries/{country_slug}/",
            "data": "data/",
            "methodology": "methodology/",
        },
    }


def _sites_table(context: _Context, summaries: Sequence[Mapping[str, Any]], root: str, table_id: str) -> str:
    vocabulary = context.vocabulary
    rows = []
    for summary in summaries:
        site_id = summary["site_id"]
        country_slug = str(summary.get("country_iso_a2")).lower()
        locator = _e(summary.get("geometry_type"))
        if summary.get("official_boundary"):
            locator += ' <span class="tag">official boundary</span>'
        rows.append(
            "<tr>"
            f'<td><a href="{_e(root)}sites/{_e(site_id)}/">{_e(summary.get("name"))}</a></td>'
            f'<td><a href="{_e(root)}countries/{_e(country_slug)}/">{_e(summary.get("country"))}</a></td>'
            f"<td>{_badges(vocabulary, summary.get('statuses') or [])}</td>"
            f"<td>{_e(summary.get('newest_status_as_of'))}</td>"
            f'<td class="num">{_e(summary.get("project_count"))}</td>'
            f"<td>{locator}</td>"
            f"<td>{_e('; '.join(summary.get('status_publishers') or []))}</td>"
            "</tr>"
        )
    headers = (
        ("Site", ""), ("Country", ""), ("Status", ""), ("Status as of", ""), ("Projects", "num"),
        ("Locator", ""), ("Status source", ""),
    )
    # Callers pass summaries sorted by name, so the Site column is the initial sort order.
    return _table(table_id, headers, rows, classes="data-table sortable", sorted_by=(0, "ascending"))


def _filter_controls(table_id: str, total: int, noun: str) -> str:
    input_id = f"{table_id}-filter"
    return (
        f'<p class="hidden-noscript"><label for="{_e(input_id)}">Filter {_e(noun)}</label> '
        f'<input class="filter-input" type="search" id="{_e(input_id)}" data-filter-table="{_e(table_id)}" '
        f'autocomplete="off"> <span class="small muted" data-filter-count="{_e(table_id)}" aria-live="polite">'
        f"{total} of {total} shown</span></p>"
    )


def _sites_index_page(context: _Context) -> _Page:
    path = "sites/index.html"
    root = _relative_root(path)
    atlas = context.atlas
    counts = atlas.counts
    body = (
        "<h1>Sites</h1>\n"
        f'<p class="lede">All {len(atlas.summaries)} physical sites in {_e(context.current.label)}, with the last '
        "observed physical status of their projects. Statuses come from dated authoritative sources and describe "
        "the status date, not today; locators are not footprints.</p>\n"
        f"{_filter_controls('sites-table', len(atlas.summaries), 'sites')}\n"
        f"{_sites_table(context, atlas.summaries, root, 'sites-table')}\n"
        f'<p class="small muted">{counts.get("projects")} projects, {counts.get("countries")} countries. '
        f'Download everything from the <a href="{root}data/">data page</a>.</p>'
    )
    return _Page(
        path=path,
        slug="sites",
        section="sites",
        title="Sites",
        description=f"Table of all {len(atlas.summaries)} data-centre construction sites with status, date and source.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _coordinates_text(latitude: float, longitude: float) -> str:
    return f"{latitude:.5f}, {longitude:.5f}"


def _map_links(latitude: float, longitude: float) -> list[tuple[str, str]]:
    lat, lon = f"{latitude:.6f}", f"{longitude:.6f}"
    return [
        ("OpenStreetMap", f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"),
        ("Google Maps", f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"),
        ("Bing aerial", f"https://www.bing.com/maps?cp={lat}~{lon}&lvl=17&style=a"),
        ("Copernicus Browser", f"https://browser.dataspace.copernicus.eu/?zoom=15&lat={lat}&lng={lon}"),
    ]


def _correction_url(context: _Context, site: Mapping[str, Any]) -> str:
    title = quote(f"Correction: {site.get('name') or site['site_id']}", safe="")
    return f"{context.config.issues_url}/new?template=correction.yml&title={title}&site_id={quote(site['site_id'], safe='')}"


def _site_page(context: _Context, summary: Mapping[str, Any]) -> _Page:
    atlas, vocabulary = context.atlas, context.vocabulary
    site_id = summary["site_id"]
    site = atlas.site_by_id[site_id]
    path = f"sites/{site_id}/index.html"
    root = _relative_root(path)
    projects = atlas.projects_by_site[site_id]
    anchors = _EvidenceAnchors(evidence["evidence_id"] for evidence in atlas.evidence_by_site[site_id])
    latitude, longitude = float(site["latitude"]), float(site["longitude"])
    coordinates = _coordinates_text(latitude, longitude)
    slug = str(site["country_iso_a2"]).lower()
    statuses = summary.get("statuses") or []
    noun = "project" if len(projects) == 1 else "projects"
    boundary_tag = ' <span class="tag">official boundary</span>' if site.get("official_boundary") else ""
    actions = " ".join([
        f'<a class="btn" href="{root}api/v1/sites/{_e(site_id)}.json">JSON for this site</a>',
        f'<a class="btn" href="{root}data/">Download dataset</a>',
        _external_link(_correction_url(context, site), "Report a correction", classes="btn btn-primary"),
    ])
    body = "\n".join([
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="{root}sites/">Sites</a> › '
        f'<a href="{root}countries/{_e(slug)}/">{_e(site.get("country"))}</a> › '
        f'<span aria-current="page">{_e(site.get("name"))}</span></nav>',
        f"<h1>{_e(site.get('name'))}</h1>",
        f"<p>{_badges(vocabulary, statuses)}{boundary_tag}</p>",
        f'<p class="lede">Last observed physical status of {len(projects)} {noun} at this site, each from a dated '
        "authoritative source. A status describes its status date, not today. The locator shows where the site "
        "is; it is not a building footprint.</p>",
        '<div class="grid-2">',
        '<section aria-labelledby="summary-heading"><h2 id="summary-heading">Summary</h2>'
        f"{_site_summary_kv(context, site, coordinates, root)}</section>",
        '<section aria-labelledby="location-heading"><h2 id="location-heading">Location</h2>'
        f"{_site_location(site, latitude, longitude, coordinates)}</section>",
        "</div>",
        f'<section aria-labelledby="projects-heading"><h2 id="projects-heading">Projects ({len(projects)})</h2>',
        *(_project_section(context, project, anchors) for project in projects),
        "</section>",
        '<section id="locator" aria-labelledby="locator-heading"><h2 id="locator-heading">Locator semantics</h2>'
        f"{_locator_section(context, site, anchors)}</section>",
        '<section id="evidence" aria-labelledby="evidence-heading"><h2 id="evidence-heading">Evidence</h2>'
        f"{_evidence_table(context, site_id)}</section>",
        f'<p class="small">{actions}</p>',
    ])
    status_text = ", ".join(vocabulary.label("statuses", code) for code in statuses) or "unknown"
    description = (
        f"{site.get('name')}, {site.get('country')}: last observed physical status {status_text} as of "
        f"{site.get('newest_status_as_of')}, with locator semantics and source evidence."
    )
    return _Page(
        path=path,
        slug="site",
        section="sites",
        title=str(site.get("name")),
        description=description,
        body=body,
        scripts=(*_map_scripts(context, SITE_MAP_JS), SITE_JS),
        styles=(LEAFLET_CSS,),
        json_ld=_place_json_ld(site),
        data_blocks=(("site-geometry", _feature(summary, site["geometry"])),),
    )


def _site_summary_kv(context: _Context, site: Mapping[str, Any], coordinates: str, root: str) -> str:
    vocabulary = context.vocabulary
    slug = str(site["country_iso_a2"]).lower()
    scopes = ", ".join(vocabulary.label("geometry_use_scopes", code) for code in site.get("geometry_use_scopes") or [])
    posture = site.get("verification_posture")
    imagery = site.get("independent_imagery_verification")
    imagery_text = "Yes" if imagery is True else "No" if imagery is False else "Not stated"
    country = (
        f'<a href="{root}countries/{_e(slug)}/">{_e(site.get("country"))}</a> '
        f'<span class="mono small">{_e(site.get("country_iso_a2"))}</span>'
    )
    posture_html = (
        f"{_e(vocabulary.label('verification_postures', posture))}<br>"
        f'<span class="small muted">{_e(vocabulary.description("verification_postures", posture))}</span>'
    )
    return _kv([
        ("Country", country),
        ("Coordinates", f'<span class="mono">{_e(coordinates)}</span> {_copy_button(coordinates)}'),
        ("Geometry type", _e(site.get("geometry_type"))),
        ("Locator scope", _e(scopes) or _muted_unknown(None)),
        ("Verification posture", posture_html),
        ("Independent imagery verification", _e(imagery_text)),
        ("Newest status as of", _e(site.get("newest_status_as_of"))),
        ("Oldest status as of", _e(site.get("oldest_status_as_of"))),
        ("Projects", _e(site.get("project_count"))),
    ])


def _site_location(site: Mapping[str, Any], latitude: float, longitude: float, coordinates: str) -> str:
    links = " · ".join(_external_link(url, label) for label, url in _map_links(latitude, longitude))
    return (
        f'<div class="site-map" id="site-map" data-lat="{_e(_number_text(latitude))}" '
        f'data-lon="{_e(_number_text(longitude))}">'
        '<p class="muted small">The interactive map needs JavaScript. Display anchor: '
        f'<span class="mono">{_e(coordinates)}</span> ({_e(site.get("geometry_type"))} locator, WGS 84).</p></div>'
        f'<p class="small">View location: {links}</p>'
    )


def _project_section(context: _Context, project: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    vocabulary = context.vocabulary
    status = project.get("last_observed_physical_status")
    as_of = _e(project.get("status_as_of"))
    method = _e(vocabulary.label("status_methods", project.get("status_method")))
    parts = [
        f'<section class="project" id="project-{_e(project["project_id"])}">',
        f"<h3>{_e(project.get('name'))}</h3>",
        f'<p>{_badge(vocabulary, status)} last observed as of <time datetime="{as_of}">{as_of}</time> '
        f'· <span class="muted">{method}</span></p>',
        _kv(_project_facts(context, project, anchors)),
    ]
    for key, _, title in OBSERVATION_FIELDS:
        observations = _dict_items(project.get(key))
        if observations:
            parts.append(f"<h4>{_e(title)}</h4>")
            parts.append(_observation_table(context, observations, anchors))
    parts.append("</section>")
    return "\n".join(parts)


def _project_facts(context: _Context, project: Mapping[str, Any], anchors: _EvidenceAnchors) -> list[tuple[str, str]]:
    vocabulary = context.vocabulary
    age = project.get("status_age_days_at_review")
    age_html = (
        _e(f"{age} days before the lifecycle reference date {context.current.lifecycle_reference_date}")
        if age is not None else _muted_unknown(None)
    )
    facts = [
        ("Status source", _status_source_html(context, project.get("status_source") or {}, anchors)),
        ("Status age", age_html),
        ("Operating model", _coded_or_unknown(
            vocabulary, "operating_models", project.get("operating_model"), project.get("operating_model_unknown_reason")
        ) + anchors(project.get("operating_model_evidence_id"))),
        ("Development type", _coded_or_unknown(
            vocabulary, "development_types", project.get("development_type"), project.get("development_type_unknown_reason")
        )),
        ("Role claims", _role_claims_html(context, project, anchors)),
        ("Workloads", _workloads_html(context, project, anchors)),
    ]
    for key, reason_key, title in OBSERVATION_FIELDS:
        count = len(_dict_items(project.get(key)))
        if count:
            facts.append((title, _e(f"{count} typed observation{'s' if count != 1 else ''} (table below)")))
        else:
            facts.append((title, _muted_unknown(project.get(reason_key))))
    facts.append(("Locator", _project_locator_html(context, project, anchors)))
    review = project.get("imagery_review_outcome")
    outcome = f'<span class="mono">{_e(review)}</span>' if review else _muted_unknown(None)
    if project.get("independent_imagery_verification") is not True:
        outcome += " · no independent imagery verification"
    facts.append(("Imagery review", outcome))
    return facts


def _status_source_html(context: _Context, source: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    if not source:
        return _muted_unknown(None)
    published = source.get("published_at")
    details = [
        _e(source.get("publisher")),
        f"published {_e(published)}" if published else '<span class="muted">publication date not stated</span>',
        _e(context.vocabulary.label("evidence_kinds", source.get("kind"))),
    ]
    title = _external_link(source.get("source_url"), source.get("title") or source.get("source_url"))
    separator = " · "
    return (
        f"{title}{anchors(source.get('evidence_id'), 'evidence row')}<br>"
        f'<span class="small">{separator.join(details)}</span>'
    )


def _coded_or_unknown(vocabulary: Vocabulary, name: str, code: Any, reason: Any) -> str:
    if code in (None, "", "unknown"):
        return _muted_unknown(reason)
    return _e(vocabulary.label(name, code))


def _role_claims_html(context: _Context, project: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    claims = _dict_items(project.get("role_claims"))
    if not claims:
        return '<span class="muted">No evidence-linked role claims are published for this project.</span>'
    vocabulary = context.vocabulary
    items = []
    for claim in claims:
        scope = vocabulary.label("relationship_scopes", claim.get("relationship_scope")).lower()
        items.append(
            f"<li>{_e(vocabulary.label('party_roles', claim.get('role')))}: {_e(claim.get('party'))} "
            f"({_e(scope)}){anchors(claim.get('evidence_id'))}</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def _workloads_html(context: _Context, project: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    workloads = _dict_items(project.get("workloads"))
    if not workloads:
        return _muted_unknown(project.get("workload_unknown_reason"))
    vocabulary = context.vocabulary
    items = []
    for workload in workloads:
        scope = workload.get("deployment_scope")
        scope_text = vocabulary.label("workload_deployment_scopes", scope).lower() if scope else "scope not recorded"
        method = vocabulary.label("workload_methods", workload.get("method")).lower()
        items.append(
            f"<li>{_e(vocabulary.label('workloads', workload.get('workload')))} ({_e(scope_text)}; "
            f"{_e(method)}, as of {_e(workload.get('as_of_date'))}){anchors(workload.get('evidence_id'))}</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def _project_locator_html(context: _Context, project: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    vocabulary = context.vocabulary
    scope = project.get("geometry_use_scope")
    authority = project.get("geometry_authority_class")
    parts = [_e(vocabulary.label("geometry_use_scopes", scope)) if scope else _muted_unknown(None)]
    if authority:
        parts.append(_e(vocabulary.label("geometry_authority_classes", authority)))
    if project.get("geometry_scope_class"):
        parts.append(f'<span class="mono">{_e(project.get("geometry_scope_class"))}</span>')
    return " · ".join(parts) + anchors(project.get("geometry_evidence_id"))


def _observation_table(context: _Context, observations: Sequence[Mapping[str, Any]], anchors: _EvidenceAnchors) -> str:
    vocabulary = context.vocabulary
    rows = []
    for item in observations:
        evidence = anchors(item.get("evidence_id")).strip() or _muted_unknown(None)
        rows.append(
            "<tr>"
            f"<td>{_e(vocabulary.label('power_metrics', item.get('metric')))}</td>"
            f"<td>{_e(vocabulary.label('power_stages', item.get('stage')))}</td>"
            f'<td class="num">{_e(_observation_value(item))}</td>'
            f"<td>{_e(item.get('as_of_date'))}</td>"
            f"<td>{_e(vocabulary.label('estimate_methods', item.get('method')))}</td>"
            f"<td>{_e(item.get('notes'))}</td>"
            f"<td>{evidence}</td>"
            "</tr>"
        )
    headers = (
        ("Metric", ""), ("Stage", ""), ("Value", "num"), ("As of", ""), ("Method", ""), ("Notes", ""),
        ("Evidence", ""),
    )
    return _table(None, headers, rows)


def _observation_value(item: Mapping[str, Any]) -> str:
    low, base, high, unit = item.get("low"), item.get("base"), item.get("high"), item.get("unit") or ""
    if _is_number(low) and _is_number(high) and low != high:
        text = f"{_format_number(low)}–{_format_number(high)} {unit}".strip()
        if _is_number(base) and base not in (low, high):
            text += f" (base {_format_number(base)})"
        return text
    return f"{_format_number(base if base is not None else low)} {unit}".strip()


def _locator_section(context: _Context, site: Mapping[str, Any], anchors: _EvidenceAnchors) -> str:
    vocabulary = context.vocabulary

    def listed(key: str, vocabulary_name: str | None = None) -> str:
        values = [value for value in site.get(key) or [] if value not in (None, "")]
        if not values:
            return _muted_unknown(None)
        if vocabulary_name:
            return _e(", ".join(vocabulary.label(vocabulary_name, value) for value in values))
        return ", ".join(f'<span class="mono">{_e(value)}</span>' for value in values)

    uncertainty = site.get("horizontal_uncertainty_metres")
    if _is_number(uncertainty):
        uncertainty_html = f"{_e(_format_number(uncertainty))} m"
    else:
        uncertainty_html = _muted_unknown(site.get("horizontal_uncertainty_unknown_reason"))
    precision = [value for value in site.get("geometry_precision_scopes") or [] if value]
    evidence_links = "".join(
        anchors(evidence_id, str(evidence_id)[:8]) for evidence_id in site.get("geometry_evidence_ids") or []
    ).strip()
    items = [
        ("Use scope", listed("geometry_use_scopes", "geometry_use_scopes")),
        ("Scope class", listed("geometry_scope_classes")),
        ("Authority", listed("geometry_authority_classes", "geometry_authority_classes")),
        ("Source entity", listed("geometry_source_entity_kinds", "geometry_source_entity_kinds")),
        ("Method", listed("geometry_methods")),
        ("Derivation", listed("geometry_derivations")),
        ("Precision scope", "<br>".join(_e(value) for value in precision) or _muted_unknown(None)),
        ("Horizontal uncertainty", uncertainty_html),
        ("Geometry evidence", evidence_links or _muted_unknown(None)),
    ]
    note = (
        '<p class="small muted">A locator places the site on the map. It is not a building footprint, a '
        "construction extent or a surveyed boundary unless the use scope is an official boundary, and even then "
        "it is a parcel or permit boundary.</p>"
    )
    return _kv(items) + note


def _evidence_table(context: _Context, site_id: str) -> str:
    vocabulary = context.vocabulary
    rows = []
    not_stated = '<span class="muted">not stated</span>'
    for evidence in context.atlas.evidence_by_site[site_id]:
        url = evidence.get("source_url")
        link = _external_link(url, evidence.get("title") or url)
        if _safe_http_url(url) is None:
            link += f' <span class="small muted">(not linked: <span class="mono">{_e(url)}</span>)</span>'
        roles = ", ".join(vocabulary.label("evidence_roles", role) for role in evidence.get("roles") or [])
        digest = str(evidence.get("content_hash") or "")
        short_digest = digest[:12] + ("…" if len(digest) > 12 else "")
        rows.append(
            f'<tr id="evidence-{_e(evidence["evidence_id"])}">'
            f"<td>{link}</td>"
            f"<td>{_e(evidence.get('publisher'))}</td>"
            f"<td>{_e(vocabulary.label('evidence_kinds', evidence.get('kind')))}</td>"
            f"<td>{_e(roles)}</td>"
            f"<td>{_e(evidence.get('published_at')) or not_stated}</td>"
            f"<td>{_e(evidence.get('retrieved_at'))}</td>"
            f"<td>{_e(evidence.get('license'))}</td>"
            f"<td>{_e(evidence.get('attribution'))}</td>"
            f'<td><span class="mono" title="{_e(digest)}">{_e(short_digest)}</span></td>'
            "</tr>"
        )
    headers = (
        ("Title", ""), ("Publisher", ""), ("Kind", ""), ("Roles", ""), ("Published", ""), ("Retrieved", ""),
        ("License", ""), ("Attribution", ""), ("Content hash", ""),
    )
    caption = "Sources are linked, not redistributed; each keeps its own terms."
    return _table("evidence-table", headers, rows, caption=caption)


def _place_json_ld(site: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": site.get("name"),
        "url": site["url"],
        "geo": {"@type": "GeoCoordinates", "latitude": site["latitude"], "longitude": site["longitude"]},
        "address": {"@type": "PostalAddress", "addressCountry": site.get("country_iso_a2")},
        "containedInPlace": {"@type": "Country", "name": site.get("country")},
    }


def _countries_page(context: _Context) -> _Page:
    path = "countries/index.html"
    root = _relative_root(path)
    vocabulary = context.vocabulary
    rows = []
    for country in context.atlas.countries:
        breakdown = " ".join(
            f"{_badge(vocabulary, code)} <span class=\"small\">{count}</span>" for code, count in country["statuses"].items()
        )
        rows.append(
            "<tr>"
            f'<td><a href="{root}countries/{_e(country["slug"])}/">{_e(country["country"])}</a></td>'
            f'<td class="mono">{_e(country["country_iso_a2"])}</td>'
            f'<td class="num">{country["site_count"]}</td>'
            f'<td class="num">{country["project_count"]}</td>'
            f"<td>{breakdown}</td>"
            "</tr>"
        )
    headers = (("Country", ""), ("ISO", ""), ("Sites", "num"), ("Projects", "num"), ("Projects by last observed status", ""))
    count = len(context.atlas.countries)
    body = (
        "<h1>Countries</h1>\n"
        f'<p class="lede">{count} countries and territories with at least one site in {_e(context.current.label)}. '
        "Coverage reflects the selection rules, not the size of each market: this is not a census.</p>\n"
        # atlas.countries is ordered by site count (descending), then name.
        + _table("countries-table", headers, rows, classes="data-table sortable", sorted_by=(2, "descending"))
    )
    return _Page(
        path=path,
        slug="countries",
        section="countries",
        title="Countries",
        description=f"Data-centre construction sites by country: {count} countries with site and project counts.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _country_page(context: _Context, country: Mapping[str, Any]) -> _Page:
    path = f"countries/{country['slug']}/index.html"
    root = _relative_root(path)
    atlas = context.atlas
    summaries = [atlas.summary_by_id[site_id] for site_id in _sorted_site_ids(atlas, country["site_ids"])]
    table_id = "country-sites-table"
    stats = '<div class="stats">' + "".join(
        f'<div class="stat"><span class="stat-value">{value}</span> <span class="stat-label">{label}</span></div>'
        for value, label in ((country["site_count"], "sites"), (country["project_count"], "projects"))
    ) + "</div>"
    country_json = f'{root}api/v1/countries/{_e(country["country_iso_a2"])}.json'
    body = "\n".join([
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="{root}countries/">Countries</a> › '
        f'<span aria-current="page">{_e(country["country"])}</span></nav>',
        f"<h1>{_e(country['country'])}</h1>",
        stats,
        f'<p class="lede">Sites in {_e(country["country"])} in {_e(context.current.label)}, with the last observed '
        "physical status of their projects.</p>",
        _filter_controls(table_id, len(summaries), "sites"),
        _sites_table(context, summaries, root, table_id),
        f'<p class="small"><a class="btn btn-small" href="{country_json}">JSON for this country</a></p>',
    ])
    return _Page(
        path=path,
        slug="country",
        section="countries",
        title=str(country["country"]),
        description=f"{country['site_count']} data-centre construction sites in {country['country']} with status and sources.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _download_rows(context: _Context, root: str) -> list[str]:
    rows = []
    for item in context.downloads:
        rows.append(
            "<tr>"
            f'<td><a href="{root}downloads/{LATEST}/{_e(item.name)}">{_e(item.name)}</a></td>'
            f"<td>{_e(item.format)}</td>"
            f"<td>{_e(item.description)}</td>"
            f'<td class="num">{_e(_human_size(item.size))}</td>'
            f'<td><code class="checksum">{_e(item.sha256)}</code> {_copy_button(item.sha256)}</td>'
            "</tr>"
        )
    return rows


def _usage_snippets(context: _Context) -> list[tuple[str, str, str]]:
    base = context.base_url
    latest = f"{base}downloads/{LATEST}/"
    return [
        ("curl", "curl", "\n".join([
            f"curl -LO {latest}sites.csv",
            f"curl -LO {latest}datacenter-atlas-{LATEST}.zip",
            f"curl -LO {latest}SHA256SUMS",
            "sha256sum --check --ignore-missing SHA256SUMS",
        ])),
        ("python-pandas", "Python (pandas)", "\n".join([
            "import pandas as pd",
            "",
            f'base = "{latest}"',
            'sites = pd.read_csv(base + "sites.csv")',
            'projects = pd.read_csv(base + "projects.csv")',
            'evidence = pd.read_csv(base + "evidence.csv")',
            'print(projects.groupby("last_observed_physical_status").size())',
        ])),
        ("python-stdlib", "Python (standard library)", "\n".join([
            "import csv",
            "import io",
            "import json",
            "import urllib.request",
            "",
            f'with urllib.request.urlopen("{latest}projects.csv") as response:',
            '    projects = list(csv.DictReader(io.TextIOWrapper(response, encoding="utf-8", newline="")))',
            f'with urllib.request.urlopen("{base}api/v1/sites.json") as response:',
            "    sites = json.load(response)",
            'print(len(projects), "projects at", len(sites), "sites")',
        ])),
        ("python-geopandas", "Python (GeoPandas)", "\n".join([
            "import geopandas as gpd",
            "",
            f'sites = gpd.read_file("{latest}sites.geojson")',
            'print(sites[["name", "country", "geometry_type"]].head())',
        ])),
        ("r", "R (readr and sf)", "\n".join([
            "library(readr)",
            "library(sf)",
            "",
            f'base <- "{latest}"',
            'sites <- read_csv(paste0(base, "sites.csv"))',
            'projects <- read_csv(paste0(base, "projects.csv"))',
            'geometry <- st_read(paste0(base, "sites.geojson"))',
        ])),
        ("duckdb", "DuckDB", "\n".join([
            f"SELECT * FROM read_csv_auto('{latest}sites.csv');",
            "",
            "SELECT last_observed_physical_status, count(*) AS projects",
            f"FROM read_csv_auto('{latest}projects.csv')",
            "GROUP BY 1 ORDER BY 2 DESC;",
        ])),
        ("sqlite", "SQLite command line", "\n".join([
            f"curl -LO {latest}atlas.sqlite",
            'sqlite3 atlas.sqlite "SELECT name, country, newest_status_as_of FROM site_overview '
            'ORDER BY newest_status_as_of DESC LIMIT 10;"',
        ])),
        ("javascript", "JavaScript (fetch)", "\n".join([
            f'const response = await fetch("{base}api/v1/sites.json");',
            "const sites = await response.json();",
            "console.log(sites.length, sites[0].name, sites[0].statuses);",
        ])),
    ]


def _data_page(context: _Context) -> _Page:
    path = "data/index.html"
    root = _relative_root(path)
    current, counts = context.current, context.atlas.counts
    latest = f"{context.base_url}downloads/{LATEST}/"
    pinned = f"{context.base_url}downloads/{current.id}/"
    zip_item = next((item for item in context.downloads if item.name.endswith(".zip")), None)
    zip_button = (
        f'<p><a class="btn btn-primary" href="{root}downloads/{LATEST}/{_e(zip_item.name)}">All files (zip, '
        f"{_e(_human_size(zip_item.size))})</a></p>" if zip_item else ""
    )
    snippets = "\n".join(
        f'{_heading(3, "use-" + anchor, title)}\n{_code_block(code)}' for anchor, title, code in _usage_snippets(context)
    )
    datasette = f"https://lite.datasette.io/?url={quote(latest + 'atlas.sqlite', safe=':/')}"
    toc_items = (
        ("files", "Files"), ("pinned", "Pinned URLs"), ("use", "Use the data"), ("gis", "QGIS and Google Earth"),
        ("more", "Dictionary, API and versions"), ("cite", "License and citation"),
    )
    toc = '<nav class="toc" aria-label="On this page"><ul>' + "".join(
        f'<li><a href="#{anchor}">{_e(text)}</a></li>' for anchor, text in toc_items
    ) + "</ul></nav>"
    status_note = "preview, not final" if not current.publishable_as_final else "final release"
    citation = _citation_text(context)
    body = "\n".join([
        "<h1>Download the data</h1>",
        '<p class="lede">Every file is static, free to download and checksummed. Open the CSVs in a spreadsheet, '
        "load the GeoJSON in a GIS, query the SQLite database, or use the JSON API.</p>",
        f'<div class="callout callout-warning" role="note"><p><strong>{_e(current.label)}</strong> · checkpoint '
        f"{_e(current.checkpoint_date)} · release status {_e(current.release_status)} ({_e(status_note)}).</p>"
        f"<p>{counts.get('physical_sites')} sites, {counts.get('projects')} projects, {counts.get('countries')} countries, "
        f"{counts.get('evidence')} evidence rows. Statuses are the last observed physical status in the window "
        f"{_e(context.window_start)} to {_e(current.lifecycle_reference_date)}; locators are not footprints.</p></div>",
        toc,
        _heading(2, "files", "Files"),
        zip_button,
        _table("downloads-table", (("File", ""), ("Format", ""), ("Description", ""), ("Size", "num"), ("SHA-256", "")),
               _download_rows(context, root), classes="data-table download-list"),
        _heading(2, "pinned", "Pinned URLs"),
        f'<div class="callout" role="note"><p><code>{_e(pinned)}</code> is pinned to this checkpoint: its original '
        "files never change (manifest.json lists their sizes and SHA-256 hashes) and the derived formats are built "
        f"only from them. <code>{_e(latest)}</code> always points at the current checkpoint and moves when a new one "
        "is published. Cite or script against the pinned URL. Every earlier checkpoint stays available on the "
        f'<a href="{root}versions/">versions page</a>.</p></div>',
        _heading(2, "use", "Use the data"),
        snippets,
        _heading(2, "gis", "QGIS and Google Earth"),
        f"<p>In QGIS choose <em>Layer → Add Layer → Add Vector Layer</em> and paste <code>{_e(latest)}sites.geojson</code>. "
        f'In Google Earth open <a href="{root}downloads/{LATEST}/sites.kml">sites.kml</a>. To browse the SQLite database in '
        f"the browser, open it in {_external_link(datasette, 'Datasette Lite')}.</p>",
        _heading(2, "more", "Dictionary, API and versions"),
        f'<ul><li><a href="{root}data/dictionary/">Field dictionary</a>: every column, type and coded value.</li>'
        f'<li><a href="{root}api/">JSON API</a>: per-site documents, GeoJSON and aggregates.</li>'
        f'<li><a href="{root}versions/">All versions</a>: every checkpoint with its own files and checksums.</li></ul>',
        _heading(2, "cite", "License and citation"),
        f'<p>{_e(context.config.data_license.get("name"))} for Atlas-authored content; third-party facts, titles, URLs '
        "and geometries keep their source terms, recorded per evidence row and in "
        f'<a href="{root}about/attribution/">the attribution file</a>. '
        f'Details on the <a href="{root}about/">about page</a>.</p>',
        _code_block(citation),
    ])
    return _Page(
        path=path,
        slug="data",
        section="data",
        title="Download the data",
        description=(
            f"Download {current.label}: CSV, GeoJSON, SQLite, JSON, NDJSON, KML and a Frictionless Data Package "
            "with checksums."
        ),
        body=body,
        scripts=(SITE_JS,),
        json_ld=_dataset_json_ld(context),
    )


def _citation_text(context: _Context) -> str:
    config, current = context.config, context.current
    year = current.checkpoint_date[:4]
    return (
        f"{config.author.get('name', '')} ({year}). {config.site_name}: {current.label} "
        f"({current.id}) [Data set]. {context.base_url}downloads/{current.id}/"
    )


def _dictionary_page(context: _Context) -> _Page:
    path = "data/dictionary/index.html"
    atlas = context.atlas
    descriptions = context.descriptions
    sections = []
    for file_name in TABLE_FILES:
        table_descriptions = descriptions.get("tables", {}).get(file_name, {})
        rows = []
        for spec in atlas.fields[file_name]:
            name = spec["name"]
            example = next((row[name] for row in atlas.raw[file_name] if row[name] != ""), "")
            if len(example) > EXAMPLE_LIMIT:
                example = example[: EXAMPLE_LIMIT - 1] + "…"
            nullable = "yes" if spec.get("allows_empty_string") else "no"
            description = table_descriptions.get(name) or "Not yet documented."
            rows.append(
                "<tr>"
                f'<td class="mono">{_e(name)}</td>'
                f'<td class="mono">{_e(typed_field_name(name))}</td>'
                f'<td class="mono">{_e(spec.get("logical_type", "string"))}</td>'
                f"<td>{nullable}</td>"
                f"<td>{_e(description)}</td>"
                f'<td class="mono small">{_e(example)}</td>'
                "</tr>"
            )
        anchor = file_name.replace(".", "-")
        headers = (("Column", ""), ("JSON name", ""), ("Type", ""), ("Empty allowed", ""), ("Description", ""), ("Example", ""))
        sections.append(_heading(2, anchor, file_name) + "\n" + _table(f"dictionary-{anchor}", headers, rows))
    derived_rows = []
    for table, items in (descriptions.get("derived") or {}).items():
        for name, description in items.items():
            derived_rows.append(
                f'<tr><td class="mono">{_e(table)}</td><td class="mono">{_e(name)}</td><td>{_e(description)}</td></tr>'
            )
    sections.append(
        _heading(2, "derived", "Derived API fields")
        + '\n<p>The JSON API, NDJSON and atlas.json add these fields after the CSV columns. Typed records turn empty '
        "values into <code>null</code>, numbers into JSON numbers, booleans into <code>true</code>/<code>false</code> "
        "and <code>*_json</code> columns into parsed JSON under the name without the suffix.</p>\n"
        + _table("dictionary-derived", (("Record", ""), ("Field", ""), ("Description", "")), derived_rows)
    )
    sections.append(_heading(2, "coded-values", "Coded values") + "\n" + _vocabulary_tables(context))
    toc_items = [(file_name.replace(".", "-"), file_name) for file_name in TABLE_FILES]
    toc_items += [("derived", "Derived API fields"), ("coded-values", "Coded values")]
    toc = '<nav class="toc" aria-label="On this page"><ul>' + "".join(
        f'<li><a href="#{_e(anchor)}">{_e(text)}</a></li>' for anchor, text in toc_items
    ) + "</ul></nav>"
    body = "\n".join([
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="{_relative_root(path)}data/">Data</a> › '
        '<span aria-current="page">Dictionary</span></nav>',
        "<h1>Field dictionary</h1>",
        f'<p class="lede">Every column of the three CSV files of {_e(context.current.label)}, from its schema.json, with '
        "plain-language descriptions and an example value. Empty values mean unknown, never zero.</p>",
        toc,
        *sections,
    ])
    return _Page(
        path=path,
        slug="dictionary",
        section="data",
        title="Field dictionary",
        description="Columns, types, descriptions and coded values of the Data Center Atlas CSV files and API.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _vocabulary_tables(context: _Context) -> str:
    sections = []
    free_form = (
        '<p class="small muted">Free-form review codes such as <code>geometry_method</code>, '
        "<code>geometry_derivation</code> and <code>geometry_scope_class</code> are shown verbatim.</p>"
    )
    for name, entries in context.vocabularies.items():
        rows = []
        for code, entry in entries.items():
            unit = f'<td class="mono">{_e(entry.get("unit"))}</td>' if name == "power_metrics" else ""
            rows.append(
                f'<tr><td class="mono">{_e(code)}</td><td>{_e(entry.get("label"))}</td>{unit}'
                f'<td>{_e(entry.get("description"))}</td></tr>'
            )
        headers = [("Code", ""), ("Label", "")]
        if name == "power_metrics":
            headers.append(("Unit", ""))
        headers.append(("Description", ""))
        anchor = f"vocabulary-{name.replace('_', '-')}"
        title = name.replace("_", " ").capitalize()
        sections.append(_heading(3, anchor, title) + "\n" + _table(anchor + "-table", headers, rows))
    return free_form + "\n" + "\n".join(sections)


def _api_endpoint_rows(context: _Context, root: str) -> list[str]:
    atlas = context.atlas
    first_site = atlas.summaries[0]["site_id"] if atlas.summaries else ""
    first_project = atlas.projects[0]["project_id"] if atlas.projects else ""
    first_evidence = atlas.evidence[0]["evidence_id"] if atlas.evidence else ""
    first_country = atlas.countries[0]["country_iso_a2"] if atlas.countries else ""
    examples = {
        "site": f"api/v1/sites/{first_site}.json",
        "project": f"api/v1/projects/{first_project}.json",
        "evidence_item": f"api/v1/evidence/{first_evidence}.json",
        "country": f"api/v1/countries/{first_country}.json",
    }
    descriptions = {
        "index": "API root: dataset metadata, endpoint templates, downloads and licenses.",
        "sites": "Array of site summaries, sorted by name.",
        "sites_geojson": "GeoJSON FeatureCollection; feature properties are site summaries.",
        "site": "One site: typed site record, its projects and every evidence row.",
        "projects": "Array of typed project records (CSV order).",
        "project": "One project with its site summary and evidence.",
        "evidence": "Array of typed evidence records (CSV order).",
        "evidence_item": "One evidence record with the projects and sites it supports.",
        "countries": "Country summaries, by site count.",
        "country": "One country (upper-case ISO code) with its site summaries.",
        "stats": "Aggregate counts by status, month, country, locator, evidence kind and license; release gates.",
        "versions": "Every dataset version with counts, files, checksums and added or removed sites.",
        "vocabularies": "Labels and descriptions for coded values.",
    }
    return [
        f'<tr><td class="mono">{_e(path)}</td><td>{_e(descriptions[key])}</td>'
        f'<td><a href="{root}{_e(examples.get(key, path))}">example</a></td></tr>'
        for key, path in _endpoint_paths().items()
    ]


def _api_page(context: _Context) -> _Page:
    path = "api/index.html"
    root = _relative_root(path)
    base = context.base_url
    atlas = context.atlas
    example = ""
    first_site = atlas.summaries[0]["site_id"] if atlas.summaries else ""
    if atlas.summaries:
        document = _site_document(context, atlas.site_by_id[atlas.summaries[0]["site_id"]])
        lines = _json_text(document, pretty=True).splitlines()
        example = "\n".join(lines[:API_EXAMPLE_LINES] + (["…"] if len(lines) > API_EXAMPLE_LINES else []))
    notes = "".join(
        f"<dt><code>{_e(name)}</code></dt><dd>{_e(description)}</dd>"
        for name, description in (context.descriptions.get("site_summary") or {}).items()
    )
    examples = [
        ("curl and jq", "\n".join([
            f"curl -s {base}api/v1/sites.json | jq '.[] | {{name, country, statuses, newest_status_as_of}}'",
            f"curl -s {base}api/v1/stats.json | jq .by_status",
        ])),
        ("JavaScript", "\n".join([
            f'const index = await (await fetch("{base}api/v1/index.json")).json();',
            'const sites = await (await fetch(index.endpoints.sites)).json();',
            'const first = await (await fetch(index.endpoints.site.replace("{site_id}", sites[0].site_id))).json();',
            "console.log(first.site.name, first.projects.length, first.evidence.length);",
        ])),
        ("Python", "\n".join([
            "import json",
            "import urllib.request",
            "",
            f'with urllib.request.urlopen("{base}api/v1/sites.json") as response:',
            "    sites = json.load(response)",
            "for site in sites[:5]:",
            '    print(site["name"], site["statuses"], site["newest_status_as_of"])',
        ])),
    ]
    body = "\n".join([
        "<h1>API</h1>",
        f'<p class="lede">A static, read-only JSON API at <code>{_e(base)}api/v1/</code>. Plain files over HTTPS: no key, '
        "no sign-up and no rate limit beyond GitHub Pages fair use. GitHub Pages sends CORS headers, so browsers can "
        "fetch it from any origin.</p>",
        '<div class="callout" role="note"><p>The path is versioned. Within <code>v1</code>, changes are additive only: '
        "new fields or endpoints may appear, existing ones keep their meaning. A breaking change would get a new "
        f"path. <code>api/v1/index.json</code> names the dataset version it serves; pinned files for every version live on the "
        f'<a href="{root}versions/">versions page</a>.</p></div>',
        _heading(2, "endpoints", "Endpoints"),
        _table("api-endpoints", (("Path", ""), ("Description", ""), ("Example", "")), _api_endpoint_rows(context, root)),
        _heading(2, "fields", "Response fields"),
        "<p>Records are typed from each checkpoint's schema.json: empty CSV values become <code>null</code>; "
        "<code>*_json</code> columns become parsed JSON without the suffix; numbers, integers and booleans are JSON "
        "types. Statuses are the last observed physical status on the status date. Absolute URLs in responses "
        "start with the <code>base_url</code> given in <code>api/v1/index.json</code>. The "
        f'<a href="{root}data/dictionary/">field dictionary</a> describes every column and coded value.</p>',
        "<p>Site summaries (sites.json, sites.geojson and country files) contain:</p>",
        f'<dl class="kv">{notes}</dl>',
        _heading(2, "examples", "Examples"),
        *(f"<h3>{_e(title)}</h3>\n{_code_block(code)}" for title, code in examples),
        _heading(2, "example-response", "Example response"),
        f"<p>The first {API_EXAMPLE_LINES} lines of <code>api/v1/sites/{_e(first_site)}.json</code>, "
        "pretty-printed (the file itself is minified):</p>",
        _code_block(example, copy=False),
    ])
    return _Page(
        path=path,
        slug="api",
        section="api",
        title="API",
        description="Static JSON API for the Data Center Atlas: endpoints, fields and examples.",
        body=body,
        scripts=(SITE_JS,),
    )


def _content_page(context: _Context, name: str) -> _Page:
    path = f"{name}/index.html"
    body = _render_fragment(context, f"content/{name}.html", _relative_root(path))
    if name == "methodology":
        source = _load_fragment(context, "content/methodology.html")
        uses_gates = any(match.group(1) == "gates_table" for match in TOKEN.finditer(source))
        if 'id="release-gates"' not in body or not uses_gates:
            raise PublicSiteError(
                'site/content/methodology.html must contain id="release-gates" and insert {{{gates_table}}} there'
            )
    titles = {
        "methodology": ("Methodology", "How sites are selected, what statuses and locators mean, release gates and limits."),
        "about": ("About", "About the Data Center Atlas: license, citation, corrections and legal notices."),
    }
    title, description = titles[name]
    return _Page(path=path, slug=name, section=name, title=title, description=description, body=body, scripts=(SITE_JS,))


def _version_files_html(context: _Context, version: DatasetVersion, root: str) -> str:
    names = [record.name for record in version.files]
    wanted = [name for name in ("sites.csv", "projects.csv", "evidence.csv", "sites.geojson", "manifest.json") if name in names]
    if version.id == context.current.id:
        wanted.append(context.zip_name)
    wanted.append("SHA256SUMS")
    return " ".join(f'<a href="{root}downloads/{_e(version.id)}/{_e(name)}">{_e(name)}</a>' for name in wanted)


def _versions_page(context: _Context) -> _Page:
    path = "versions/index.html"
    root = _relative_root(path)
    changes = _version_changes(context)
    current_sites = context.atlas.site_by_id
    rows = []
    for version in reversed(context.versions):
        added, removed = changes[version.id]
        names = context.version_sites[version.id]
        items = []
        for site_id in sorted(added, key=lambda value: (names[value].casefold(), value)):
            label = _e(names[site_id])
            if site_id in current_sites:
                label = f'<a href="{root}sites/{_e(site_id)}/">{label}</a>'
            items.append(f"<li>{label}</li>")
        added_html = (
            f"<details><summary>{len(added)} added</summary><ul>{''.join(items)}</ul></details>" if added else "0"
        )
        if removed:
            added_html += f'<br><span class="small muted">{len(removed)} removed</span>'
        counts = version.counts
        marker = ' <span class="tag">current</span>' if version.id == context.current.id else ""
        rows.append(
            f'<tr id="version-{_e(version.id)}">'
            f'<td>{_e(version.label)}{marker}<br><span class="mono small muted">{_e(version.id)}</span></td>'
            f"<td>{_e(version.kind)}</td>"
            f"<td>{_e(version.checkpoint_date)}</td>"
            f'<td class="num">{_e(counts.get("physical_sites"))}</td>'
            f'<td class="num">{_e(counts.get("projects"))}</td>'
            f'<td class="num">{_e(counts.get("countries"))}</td>'
            f'<td class="num">{_e(counts.get("evidence"))}</td>'
            f"<td>{added_html}</td>"
            f'<td class="small">{_version_files_html(context, version, root)}</td>'
            f"<td>{_external_link(_tree_url(context, version), 'GitHub')}</td>"
            "</tr>"
        )
    headers = (
        ("Version", ""), ("Kind", ""), ("Checkpoint", ""), ("Sites", "num"), ("Projects", "num"),
        ("Countries", "num"), ("Evidence", "num"), ("Added sites", ""), ("Files", ""), ("Source", ""),
    )
    previews = [version for version in context.versions if version.kind == "preview"]
    drafts = [version for version in context.versions if version.kind == "draft"]
    body = "\n".join([
        "<h1>Versions</h1>",
        f'<p class="lede">All {len(context.versions)} dataset versions, newest first. Each is a frozen, hash-validated '
        "snapshot: later versions build on earlier ones instead of overwriting them, and every version stays "
        "downloadable byte for byte.</p>",
        f"<p><strong>Previews</strong> ({len(previews)}) are the frozen releases of the original cohort, up to "
        f"{_e(context.last_preview.label)} with {_e(context.last_preview.counts.get('physical_sites'))} sites. "
        f"<strong>Drafts</strong> ({len(drafts)}) are reviewed checkpoints of the expansion that follows; each adds "
        "independently reviewed sites. No version is a final release: see the "
        f'<a href="{root}methodology/#release-gates">release gates</a>. The '
        f'<a href="{root}feed.xml">releases feed</a> announces new versions.</p>',
        _table("versions-table", headers, rows, classes="data-table"),
    ])
    return _Page(
        path=path,
        slug="versions",
        section="versions",
        title="Versions",
        description=f"Every Data Center Atlas dataset version ({len(context.versions)}) with counts, files and sites added.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _legal_notice(context: _Context) -> str:
    readme = context.last_preview.path / "README.md"
    text = readme.read_text(encoding="utf-8")
    match = re.search(r"^## Legal notice[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if match is None or not match.group(1).strip():
        raise PublicSiteError(f"{readme}: no '## Legal notice' section")
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", match.group(1)) if block.strip()]
    return "\n".join(f"<p>{_join_notice_lines(block.splitlines())}</p>" for block in paragraphs)


def _join_notice_lines(lines: Sequence[str]) -> str:
    """Keep deliberate line breaks (short lines, lines ending in a colon) and unwrap hard-wrapped prose."""
    html_parts = []
    for index, line in enumerate(lines):
        html_parts.append(_linkify(line.strip()))
        if index < len(lines) - 1:
            deliberate = line.rstrip().endswith(":") or len(line.strip()) < 60
            html_parts.append("<br>" if deliberate else " ")
    return "".join(html_parts)


def _attribution_page(context: _Context) -> _Page:
    path = "about/attribution/index.html"
    root = _relative_root(path)
    current = context.current
    attribution = (current.path / "ATTRIBUTION.txt").read_text(encoding="utf-8")
    body = "\n".join([
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="{root}about/">About</a> › '
        '<span aria-current="page">Attribution</span></nav>',
        "<h1>Attribution and legal notices</h1>",
        f'<p class="lede">Third-party facts, titles, URLs and geometries in {_e(current.label)} keep their source terms. '
        "Below is the dataset's full attribution file; every evidence row also records its own license and "
        "attribution. The Atlas links to sources and does not redistribute third-party documents or imagery.</p>",
        '<section class="callout callout-warning" aria-labelledby="legal-notice"><h2 id="legal-notice">Legal notice</h2>'
        f'<p class="small muted">From the {_e(context.last_preview.label)} readme.</p>{_legal_notice(context)}</section>',
        f'<h2 id="attribution-file">ATTRIBUTION.txt of {_e(current.id)}</h2>',
        f'<p class="small"><a href="{root}downloads/{_e(current.id)}/ATTRIBUTION.txt">Download the file</a></p>',
        f'<pre class="code">{_linkify(attribution)}</pre>',
    ])
    return _Page(
        path=path,
        slug="attribution",
        section="about",
        title="Attribution and legal notices",
        description="Source attribution, third-party terms and required legal notices for the Data Center Atlas data.",
        body=body,
        main_class="page page-wide",
    )


def _not_found_page(context: _Context) -> _Page:
    base = context.base_url
    body = "\n".join([
        "<h1>Page not found</h1>",
        '<p class="lede">There is no page at this address. It may have moved, or the link may be mistyped.</p>',
        "<ul>",
        f'<li><a href="{_e(base)}">Explore the map</a></li>',
        f'<li><a href="{_e(base)}sites/">Browse all sites</a></li>',
        f'<li><a href="{_e(base)}data/">Download the data</a></li>',
        f'<li><a href="{_e(base)}api/">Use the API</a></li>',
        "</ul>",
    ])
    return _Page(
        path="404.html",
        slug="not-found",
        section=None,
        title="Page not found",
        description="The requested page does not exist.",
        body=body,
        absolute_root=True,
        in_sitemap=False,
    )


# --------------------------------------------------------------------------------------------
# Feed, sitemap, robots


def _feed_id(context: _Context, suffix: str) -> str:
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, context.config.repository_url + suffix)}"


def _write_feed(writer: _Writer, context: _Context) -> None:
    base = context.base_url
    changes = _version_changes(context)
    updated = max(version.checkpoint_date for version in context.versions)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{_x(FEED_TITLE)}</title>",
        f"<subtitle>{_x(context.config.tagline)}</subtitle>",
        f"<id>{_x(_feed_id(context, '#releases'))}</id>",
        f"<updated>{updated}T00:00:00Z</updated>",
        f'<link rel="self" type="application/atom+xml" href="{_x(base)}feed.xml"/>',
        f'<link rel="alternate" type="text/html" href="{_x(base)}versions/"/>',
        f"<author><name>{_x(context.config.author.get('name'))}</name><uri>{_x(context.config.author.get('url'))}</uri></author>",
    ]
    for version in reversed(context.versions):
        added, removed = changes[version.id]
        counts = version.counts
        status = "final release" if version.publishable_as_final else f"{version.kind}, not a final release"
        summary = (
            f"{counts.get('physical_sites')} sites, {counts.get('projects')} projects, {counts.get('countries')} countries, "
            f"{counts.get('evidence')} evidence rows; {len(added)} sites added, {len(removed)} removed. "
            f"Checkpoint {version.checkpoint_date} ({status})."
        )
        lines += [
            "<entry>",
            f"<title>{_x(version.label)}</title>",
            f"<id>{_x(_feed_id(context, '#dataset/' + version.id))}</id>",
            f"<updated>{version.checkpoint_date}T00:00:00Z</updated>",
            f'<link rel="alternate" type="text/html" href="{_x(base)}versions/#version-{_x(version.id)}"/>',
            f'<link rel="related" type="application/json" href="{_x(base)}downloads/{_x(version.id)}/manifest.json"/>',
            f"<summary>{_x(summary)}</summary>",
            "</entry>",
        ]
    lines.append("</feed>")
    writer.write_text("feed.xml", "\n".join(lines) + "\n")


def _write_sitemap_and_robots(writer: _Writer, context: _Context) -> None:
    urls = sorted(context.base_url + _url_path(path) for path in writer.pages)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f"<url><loc>{_x(url)}</loc></url>" for url in urls]
    lines.append("</urlset>")
    writer.write_text("sitemap.xml", "\n".join(lines) + "\n")
    writer.write_text("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {context.base_url}sitemap.xml\n")


# --------------------------------------------------------------------------------------------
# Small I/O helpers


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PublicSiteError(f"{path} is missing or is not a regular file")
    return path.read_bytes()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_regular_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicSiteError(f"{path}: invalid JSON ({error})") from error
