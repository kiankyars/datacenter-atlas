"""Static public-site builder for the Data Center Atlas.

``build_site`` turns the frozen dataset versions under ``verified_construction_core/`` into a
self-contained static site: HTML pages that work without JavaScript, a versioned static JSON
API under ``api/v1/`` with an OpenAPI description and JSON Schemas, bulk downloads (original
files plus JSON, NDJSON, SQLite, Excel, KML, a Frictionless Data Package, checksums and a zip
archive), a landing page for every download directory, Atom feeds, ``llms.txt`` and a sitemap.

The builder is standard-library only, makes no network requests and is deterministic: the
same inputs produce byte-identical output. ``atlas.sqlite`` is written with
``PRAGMA secure_delete = ON``, a fixed page size and the writer-version header field zeroed,
so it does not depend on the defaults a particular SQLite build was compiled with; a future
SQLite (or zlib, for the zip archives) whose file layout differs could still change those
bytes. Before anything is written the builder validates every dataset version against its
``manifest.json`` and ``manifest.sha256``, reads every input only from manifest-listed,
regular (non-symlink) files whose size and SHA-256 are re-checked on each read, and fails
closed on any mismatch.

Every dataset value is untrusted text. HTML output is escaped, only ``http``/``https`` URLs
become links, JSON embedded in ``<script>`` blocks escapes ``<``, ``>``, ``&``, U+2028 and
U+2029, KML descriptions are escaped twice (HTML, then XML), lone UTF-16 surrogates are
rejected, and identifiers used in output paths must match a conservative pattern. Original
files that a browser would run as active content (HTML, SVG, XML, JavaScript) are published
only when their SHA-256 is on a reviewed allowlist.

Typed records follow the checkpoint's own ``schema.json``: empty CSV values become ``null``,
``number`` becomes a float, ``integer`` an int, ``boolean`` a bool, ``json_array`` and
``geojson_geometry`` parsed JSON, and everything else stays a string. Typed field names drop
a trailing ``_json``; CSV and SQLite keep the original column names.

Download directories: ``downloads/<id>/`` holds every version's original files verbatim plus
``SHA256SUMS``. Every version from the first one published as current (``FIRST_PUBLISHED_DATASET``
or ``first_published_dataset`` in the config) up to the current one also keeps its derived
formats and its zip, built from that version alone, so a directory's files never disappear when
a newer checkpoint becomes current. ``downloads/latest/`` mirrors the current version.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, urlsplit
import uuid
import zipfile
import zlib


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
FEED_TITLE = "Data Center Atlas updates"
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
EXAMPLE_LIMIT = 80
JSON_EXAMPLE_LIMIT = 400
API_EXAMPLE_LINES = 60
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: https://*.basemaps.cartocdn.com "
    "https://tile.openstreetmap.org https://tiles.maps.eox.at; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'"
)
NAVIGATION = (
    ("explore", "", "Explore"),
    ("sites", "sites/", "Sites"),
    ("countries", "countries/", "Countries"),
    ("data", "data/", "Downloads"),
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
# Optional social preview image (site/static); pages reference it only when it exists.
OG_IMAGE = "og-image.png"
OG_IMAGE_ALT = "Data Center Atlas: map of data-centre construction sites"

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
XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
LONE_SURROGATE = re.compile("[\ud800-\udfff]")
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'`]+")
TRAILING_URL_PUNCTUATION = ".,;:!?)]}"
RETRIEVED_AT = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")
# csv's default per-field limit is 131,072 characters; a detailed boundary in geometry_json can
# exceed it. 64 MiB keeps a bound while leaving ample room.
CSV_FIELD_LIMIT = 64 * 1024 * 1024
# The site first went live with this checkpoint as current. It and every later version up to the
# current one keep their derived formats and zip; config key first_published_dataset overrides it.
FIRST_PUBLISHED_DATASET = "2026-08-20-v0.18-draft-thirty-fifth-reviewed"
# Original files a browser would run as active content on the site's origin. They are published
# verbatim (and without a Content-Security-Policy) only when their SHA-256 is listed here after
# review: the 17 preview map.html files load nothing external and write data with textContent only.
ACTIVE_CONTENT_SUFFIXES = (".html", ".htm", ".xhtml", ".shtml", ".svg", ".svgz", ".xml", ".xsl", ".xslt", ".js", ".mjs")
REVIEWED_ACTIVE_ORIGINALS = frozenset({
    "32d4da7cf6d3a38655a83fce5deafd0221eab1ba91de0b1bca95cb991220a717",  # 2026-08-19-preview-v0.1/map.html
    "2ba33d3abae67db389de12d6097ba385d526a8390c3a18228abbb5ab7735f7a4",  # 2026-08-20-preview-v0.2/map.html
    "5a1efaaea84c823c5bc1b53232456c83e7a4bd504397bde3734fad68ca59c0e4",  # 2026-08-20-preview-v0.3/map.html
    "ffc04e3365fae73cdf7ac3752b0df904cbc86e415338722e647a26ddb036adc1",  # 2026-08-20-preview-v0.4/map.html
    "8a1da8065a1606e857094f2b923ca9feb0d97f9659156929432202c94945b408",  # 2026-08-20-preview-v0.5/map.html
    "3eac962444c883889b113ee1633684ec0d5c89d431366a1586642e8f7d71aed7",  # 2026-08-20-preview-v0.6/map.html
    "95d8e2c1937bf709af75e9a28ab459475a1c35ab082addeff61e2dcdfb99ceee",  # 2026-08-20-preview-v0.7/map.html
    "4a2fcfeb4447917ce91885c0643c33d424c7c50c40d868cd9747cd30bf7fe3d7",  # 2026-08-20-preview-v0.8/map.html
    "feb2f104f87a4bc34f056016ccda2b303f9a5f5b2444bc980b61f76c596c0501",  # 2026-08-20-preview-v0.9/map.html
    "c758a3354f2b947a0caf75a11657e6c4c04e04f30dfe0443da580ac85da4da7e",  # 2026-08-20-preview-v0.10/map.html
    "c92d6c76ec64808b67e594a196583fc2fee0f15fefbc2f256b27c2ab3d66fb8f",  # 2026-08-20-preview-v0.11/map.html
    "fdbee3ebd20ddf82b9d6be690ad3a1653e19d1e531ca8366d739e8986a37497a",  # 2026-08-20-preview-v0.12/map.html
    "0cabe44034279315547b1a8f20fb7464bf68403da640ae87ef4a0d9a47b078f2",  # 2026-08-20-preview-v0.13/map.html
    "c16ce08cc679108392e6d675139c01e830a2c6aaf104cc485f078e672e649afe",  # 2026-08-20-preview-v0.14/map.html
    "08184b8e714cb22faa9bad76a0dd7327772c0f5144da4fefd0ca4915e1bf6e4c",  # 2026-08-20-preview-v0.15/map.html
    "ee2cb9a31ac9a920c2e7892a537418c095e5209e14deaf8bc61f385310590101",  # 2026-08-20-preview-v0.16/map.html
    "2897a779090bae5aff558851c7312d62d8a5523ad2d7a865d1adf9ef5ea758ce",  # 2026-08-20-preview-v0.17/map.html
})
ODBL = {
    "id": "ODbL-1.0",
    "name": "Open Data Commons Open Database License 1.0",
    "url": "https://opendatacommons.org/licenses/odbl/1-0/",
    "attribution": "\u00a9 OpenStreetMap contributors",
    "attribution_url": "https://www.openstreetmap.org/copyright",
    "scope": "Geometries whose geometry evidence row has license ODbL-1.0 (derived from OpenStreetMap).",
}
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
THIRD_PARTY_TERMS = (
    "Third-party facts, titles, URLs and geometries keep their source terms (each evidence record's license "
    "and attribution)."
)
# The four rules every reader of the data needs; repeated in llms.txt, the workbook and the API description.
DATA_CAVEATS = (
    "Each status is the last observed physical status as of a dated source (status_as_of), not the status today.",
    "Locators place a site on the map; they are not building footprints or construction extents.",
    "Empty or null values are unknown, never zero.",
    "Coverage is incomplete and varies by country.",
)
DATASET_KEYWORDS = ("data centres", "data centers", "construction", "infrastructure", "geospatial", "open data")
SITES_FEED_TITLE = "Data Center Atlas sites"
WAYBACK_PREFIX = "https://web.archive.org/web/"
# Licence codes recorded on evidence rows that have a canonical terms page.
LICENSE_URLS = {
    "ODbL-1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC-BY-SA-2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "Public-Domain-Mark-1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
    "etalab-2.0": "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
    "dl-de/by-2-0": "https://www.govdata.de/dl-de/by-2-0",
    "Open-Government-Licence-Alberta": "https://open.alberta.ca/licence",
    "Open Government Licence - Toronto": "https://open.toronto.ca/open-data-licence/",
    "Open Government Licence v3.0, except where otherwise stated": (
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
    ),
    "Hong-Kong-DATA.GOV.HK-Terms-of-Use": "https://data.gov.hk/en/terms-and-conditions",
    "e-stat-terms-compatible-with-CC-BY-4.0": "https://www.e-stat.go.jp/terms-of-use",
}
# Attribution statements some licences require of anyone who reuses material under them.
LICENSE_STATEMENTS = {
    "Open Government Licence - Toronto": (
        "Contains information licensed under the Open Government Licence \u2013 Toronto.",
        "https://open.toronto.ca/open-data-licence/",
    ),
    "Open Government Licence v3.0, except where otherwise stated": (
        "Contains public sector information licensed under the Open Government Licence v3.0.",
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    ),
}
# Publishers whose terms require their disclaimer wherever an application using their data is
# offered; the text is the "## Legal notice" section of the last preview's README.md.
LEGAL_NOTICE_PUBLISHERS = ("City of Chicago",)
CHICAGO_TERMS_URL = "https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html"

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
    "sites.csv": (
        "official_boundary", "country_slug", "url", "api_url", "geometry_licenses", "geometry_attributions",
    ),
    "projects.csv": ("evidence_ids", "status_source", "url", "api_url", "geometry_source"),
    "evidence.csv": ("site_ids", "url", "api_url", "archive_url"),
}
STATUS_SOURCE_FIELDS = (
    "evidence_id", "title", "publisher", "kind", "published_at", "source_url", "license", "attribution",
)
SITE_SUMMARY_FIELDS = (
    "site_id", "name", "country", "country_iso_a2", "latitude", "longitude", "geometry_type",
    "official_boundary", "locator_scopes", "statuses", "newest_status_as_of", "oldest_status_as_of",
    "project_count", "projects", "status_publishers", "power_observations", "verification_posture",
    "independent_imagery_verification", "url", "api_url", "geometry_licenses", "geometry_attributions",
)
# Unit of every by_* map in stats.json.
STATS_UNITS = {
    "by_status": "projects",
    "by_country": "sites",
    "by_status_month": "projects",
    "by_geometry_type": "sites",
    "by_locator_scope": "projects",
    "by_verification_posture": "projects",
    "by_evidence_kind": "evidence_rows",
    "by_evidence_license": "evidence_rows",
    "by_power_metric": "observations",
}
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
    "imagery_review_outcomes",
)
OBSERVATION_FIELDS = (
    ("power_observations", "power_unknown_reason", "Power"),
    ("efficiency_observations", "efficiency_unknown_reason", "Efficiency"),
    ("annual_energy_observations", "annual_energy_unknown_reason", "Annual energy"),
)
OBSERVATION_COLUMNS = (
    "metric", "stage", "low", "base", "high", "unit", "as_of_date", "target_date", "method", "confidence",
    "evidence_id", "notes",
)
DOWNLOAD_ORDER = (
    "sites.csv", "projects.csv", "evidence.csv", "sites.geojson", "atlas.xlsx", "atlas.json", "atlas.sqlite",
    "sites.kml", "sites.ndjson", "projects.ndjson", "evidence.ndjson", "datapackage.json",
    "schema.json", "selection-report.json", "review-provenance.json", "README.md",
    "ATTRIBUTION.txt", "manifest.json", "manifest.sha256", "map.html",
)
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOWNLOAD_INFO = {
    "sites.csv": ("CSV", "text/csv", "One row per physical site."),
    "projects.csv": (
        "CSV", "text/csv",
        "One row per construction project: last observed status, locator semantics and typed observations.",
    ),
    "evidence.csv": (
        "CSV", "text/csv", "Sources for site records, with URLs, usage terms and content hashes.",
    ),
    "sites.geojson": ("GeoJSON", "application/geo+json", "Site locators and boundaries as a GeoJSON FeatureCollection."),
    "atlas.xlsx": (
        "Excel", XLSX_MEDIA_TYPE,
        "Excel workbook: a README sheet plus sites, projects and evidence (UTF-8 safe; geometry omitted).",
    ),
    "atlas.json": ("JSON", "application/json", "Every typed site, project and evidence record in one JSON document."),
    "atlas.sqlite": (
        "SQLite", "application/vnd.sqlite3",
        "SQLite database: the three tables, link and observation tables and a site_overview view.",
    ),
    "sites.kml": ("KML", "application/vnd.google-earth.kml+xml", "Sites for Google Earth and other KML viewers."),
    "sites.ndjson": ("NDJSON", "application/x-ndjson", "One typed site record per line."),
    "projects.ndjson": ("NDJSON", "application/x-ndjson", "One typed project record per line."),
    "evidence.ndjson": ("NDJSON", "application/x-ndjson", "One typed evidence record per line."),
    "datapackage.json": (
        "Data Package", "application/json", "Frictionless Data Package descriptor: table schemas, sizes and hashes.",
    ),
    "schema.json": ("JSON", "application/json", "Field definitions for the source files."),
    "selection-report.json": ("JSON", "application/json", "Research and selection audit."),
    "review-provenance.json": ("JSON", "application/json", "Source and review records for additions."),
    "README.md": (
        "Markdown", "text/markdown",
        "Original research notes retained with the archived data.",
    ),
    "ATTRIBUTION.txt": ("Text", "text/plain", "Source attribution and third-party terms."),
    "manifest.json": ("JSON", "application/json", "File sizes and SHA-256 hashes of the source files."),
    "manifest.sha256": ("Text", "text/plain", "SHA-256 of manifest.json."),
    "map.html": ("HTML", "text/html", "Archived offline map."),
    "SHA256SUMS": ("Text", "text/plain", "SHA-256 of every file in this directory (sha256sum -c format)."),
}
DERIVED_DOWNLOADS = frozenset({
    "atlas.json", "atlas.sqlite", "atlas.xlsx", "sites.kml", "sites.ndjson", "projects.ndjson",
    "evidence.ndjson", "datapackage.json",
})
# Names the builder writes into a download directory; an original file may not use them.
RESERVED_DOWNLOAD_NAMES = DERIVED_DOWNLOADS | {"SHA256SUMS", "index.html"}
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
    # Optional: the first dataset the live site published as current (default FIRST_PUBLISHED_DATASET).
    first_published_dataset: str | None = None
    # Optional: the dataset title used in citations (default "<site_name>: <versions_root as words>").
    dataset_title: str | None = None

    @property
    def title(self) -> str:
        if self.dataset_title:
            return self.dataset_title
        words = " ".join(part.capitalize() for part in re.split(r"[_\-\s]+", self.versions_root.strip("/")) if part)
        return f"{self.site_name}: {words}" if words else self.site_name


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
    for key in ("first_published_dataset", "dataset_title"):
        if key in raw and (not isinstance(raw[key], str) or not raw[key].strip()):
            raise PublicSiteError(f"{path}: '{key}' must be a non-empty string when present")
    window = raw.get("status_window_days")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        raise PublicSiteError(f"{path}: 'status_window_days' must be a positive integer")
    for key in ("author", "data_license", "code_license"):
        if not isinstance(raw.get(key), dict):
            raise PublicSiteError(f"{path}: '{key}' must be an object")
    if not isinstance(raw["author"].get("name"), str) or not raw["author"]["name"].strip():
        raise PublicSiteError(f"{path}: 'author.name' must be a non-empty string")
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
        first_published_dataset=raw.get("first_published_dataset"),
        dataset_title=raw.get("dataset_title"),
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
    manifest = _parse_json_bytes(manifest_bytes, str(manifest_path))
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
    listed = {record.name for record in files}
    missing = [name for name in (*TABLE_FILES, "schema.json") if name not in listed]
    if missing:
        raise PublicSiteError(
            f"{identifier}/manifest.json does not list {missing}; the builder reads only hash-checked files"
        )
    report_listed = "selection-report.json" in listed
    if not report_listed and os.path.lexists(path / "selection-report.json"):
        raise PublicSiteError(
            f"{identifier}/selection-report.json exists but manifest.json does not list it; "
            "the builder reads only hash-checked files"
        )
    report = _parse_json_bytes(
        _checked_bytes(path, files, "selection-report.json"), f"{identifier}/selection-report.json"
    ) if report_listed else {}
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
    site_count = counts.get("physical_sites", 0)
    label = f"{checkpoint} · {site_count} {'site' if site_count == 1 else 'sites'}"
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
    _reject_surrogates(parsed, field_name)
    if logical_type == "json_array" and not isinstance(parsed, list):
        raise PublicSiteError(f"{field_name}: expected a JSON array")
    if logical_type == "geojson_geometry" and not (
        isinstance(parsed, dict) and isinstance(parsed.get("type"), str)
    ):
        raise PublicSiteError(f"{field_name}: expected a GeoJSON geometry object")
    return parsed


def _reject_json_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def convert_row(
    row: Mapping[str, str], fields: Sequence[Mapping[str, Any]], *, where: str | None = None
) -> dict[str, Any]:
    """Typed record for one CSV row, in schema column order."""
    record: dict[str, Any] = {}
    key = row.get(fields[0]["name"], "") if fields else ""
    for spec in fields:
        name = spec["name"]
        label = f"{where} {key}: {name}" if where else name
        record[typed_field_name(name)] = convert_value(
            row[name], str(spec.get("logical_type", "string")), field_name=label
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
    """Read, type, validate and cross-link the three tables of one dataset version.

    Every input is read from its manifest-listed file and re-checked against the size and
    SHA-256 recorded at validation, so the records are built from exactly the hashed bytes.
    """
    schema = _verified_json(version, "schema.json")
    fields = _schema_fields(schema, version.id)
    raw = {name: _read_csv_table(version, name, fields[name]) for name in TABLE_FILES}
    typed = {
        name: [convert_row(row, fields[name], where=f"{version.id}/{name}") for row in raw[name]]
        for name in TABLE_FILES
    }
    listed = {record.name for record in version.files}
    report = _verified_json(version, "selection-report.json") if "selection-report.json" in listed else {}
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


def _csv_records(text: str, where: str) -> Iterator[tuple[int, list[str]]]:
    """(line number, values) for every CSV record; csv errors become PublicSiteError."""
    if csv.field_size_limit() < CSV_FIELD_LIMIT:
        csv.field_size_limit(CSV_FIELD_LIMIT)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        for values in reader:
            yield reader.line_num, values
    except csv.Error as error:
        raise PublicSiteError(f"{where}: line {reader.line_num}: {error}") from error


def _read_csv_table(version: DatasetVersion, name: str, fields: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    where = f"{version.id}/{name}"
    names = [spec["name"] for spec in fields]
    records = _csv_records(_verified_text(version, name), where)
    header = next(records, (0, []))[1]
    if header != names:
        position = next(
            (index for index, pair in enumerate(zip(header, names)) if pair[0] != pair[1]),
            min(len(header), len(names)),
        )
        found = header[position] if position < len(header) else "end of header"
        wanted = names[position] if position < len(names) else "end of header"
        raise PublicSiteError(
            f"{where}: header does not match schema.json (column {position + 1}: found {found!r}, expected {wanted!r})"
        )
    rows = []
    for line, values in records:
        if len(values) != len(names):
            raise PublicSiteError(f"{where}: line {line} has {len(values)} values, expected {len(names)}")
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
        geometry_rows = [
            atlas.evidence_by_id[evidence_id]
            for evidence_id in dict.fromkeys(site.get("geometry_evidence_ids") or [])
            if isinstance(evidence_id, str) and evidence_id in atlas.evidence_by_id
        ]
        site["geometry_licenses"] = sorted({row["license"] for row in geometry_rows if row.get("license")})
        site["geometry_attributions"] = sorted({row["attribution"] for row in geometry_rows if row.get("attribution")})
    for project in atlas.projects:
        project_id = project["project_id"]
        status = atlas.evidence_by_id[project["status_evidence_id"]]
        project["evidence_ids"] = sorted(evidence_ids[project_id])
        project["status_source"] = {key: status.get(key) for key in STATUS_SOURCE_FIELDS}
        project["url"] = f"{base_url}sites/{project['site_id']}/#project-{project_id}"
        project["api_url"] = f"{base_url}api/v1/projects/{project_id}.json"
        geometry = atlas.evidence_by_id.get(project.get("geometry_evidence_id") or "")
        project["geometry_source"] = {key: geometry.get(key) for key in STATUS_SOURCE_FIELDS} if geometry else None
    for evidence in atlas.evidence:
        evidence["site_ids"] = sorted(
            {atlas.project_by_id[project_id]["site_id"] for project_id in evidence.get("project_ids") or []}
        )
        evidence["url"] = f"{base_url}api/v1/evidence/{evidence['evidence_id']}.json"
        evidence["api_url"] = evidence["url"]
        evidence["archive_url"] = _archive_url(evidence.get("source_url"), evidence.get("retrieved_at"))


def _archive_url(source_url: Any, retrieved_at: Any) -> str | None:
    """Wayback Machine URL of the capture nearest the retrieval time (the capture may not exist)."""
    if _safe_http_url(source_url) is None or not isinstance(retrieved_at, str):
        return None
    match = RETRIEVED_AT.match(retrieved_at)
    if match is None:
        return None
    timestamp = "".join(part for part in match.groups() if part)
    return f"{WAYBACK_PREFIX}{timestamp}/{source_url}"


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
        "geometry_licenses": site["geometry_licenses"],
        "geometry_attributions": site["geometry_attributions"],
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
            "geojson_url": f"{base_url}api/v1/countries/{iso}.geojson",
            "csv_url": f"{base_url}api/v1/countries/{iso}.csv",
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
        for value in site.get("imagery_review_outcomes") or []:
            add("imagery_review_outcomes", value)
        add("verification_postures", site.get("verification_posture"))
    for project in atlas.projects:
        add("statuses", project.get("last_observed_physical_status"))
        add("status_methods", project.get("status_method"))
        add("imagery_review_outcomes", project.get("imagery_review_outcome"))
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
    derived: bool = False


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
    history: Mapping[str, _VersionChange]
    derived_versions: tuple[DatasetVersion, ...]
    static_files: frozenset[str]
    attribution_text: str
    legal_notice_html: str
    downloads: tuple[DownloadFile, ...] = ()
    download_dirs: Mapping[str, tuple[DownloadFile, ...]] = field(default_factory=dict)
    og_image_size: tuple[int, int] | None = None

    @property
    def site_dir(self) -> Path:
        return self.root / "site"

    @property
    def window_start(self) -> str:
        return _window_start(self.config, self.current)

    @property
    def commit_short(self) -> str:
        return self.commit[:7] if self.commit else "local build"

    @property
    def zip_name(self) -> str:
        return _zip_name(self.current)

    def has_derived(self, version: DatasetVersion) -> bool:
        return any(item.id == version.id for item in self.derived_versions)


def _window_start(config: SiteConfig, version: DatasetVersion) -> str:
    reference = date.fromisoformat(version.lifecycle_reference_date)
    return (reference - timedelta(days=config.status_window_days)).isoformat()


def _zip_name(version: DatasetVersion) -> str:
    return f"datacenter-atlas-{version.id}.zip"


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
        context = _write_downloads(writer, context)
        _write_api(writer, context)
        _write_pages(writer, context)
        _write_feed(writer, context)
        _write_sites_feed(writer, context)
        _write_llms_txt(writer, context)
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
    if config.first_published_dataset:
        first = _find_version(versions, config.first_published_dataset, root, "first_published_dataset")
    else:
        first = next((version for version in versions if version.id == FIRST_PUBLISHED_DATASET), current)
    if first.sort_key > current.sort_key:
        raise PublicSiteError(
            f"first published dataset {first.id} is newer than the current dataset {current.id}: the published "
            "derived files of the newer versions would disappear; set first_published_dataset in the config "
            "to an older version deliberately if that is intended"
        )
    derived_versions = tuple(version for version in versions if first.sort_key <= version.sort_key <= current.sort_key)
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
        history=_version_history(versions),
        derived_versions=derived_versions,
        static_files=frozenset(relative for relative, _ in _static_files(root / "site" / "static")),
        attribution_text=_verified_text(current, "ATTRIBUTION.txt"),
        legal_notice_html=_legal_notice(last_preview),
        og_image_size=_png_size(root / "site" / "static" / OG_IMAGE),
    )


def _png_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of a PNG file, or None when there is no such regular file."""
    if path.is_symlink() or not path.is_file():
        return None
    header = path.read_bytes()[:24]
    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
        raise PublicSiteError(f"{path}: not a PNG image")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


# Version history -----------------------------------------------------------------------------

TABLE_KEYS = {"sites.csv": "site_id", "projects.csv": "project_id", "evidence.csv": "evidence_id"}
TABLE_LABEL_COLUMNS = {"sites.csv": "name", "projects.csv": "name", "evidence.csv": "title"}
CHANGE_VALUE_LIMIT = 120


@dataclass(frozen=True)
class _TableSnapshot:
    columns: tuple[str, ...]
    rows: dict[str, dict[str, str]]


@dataclass(frozen=True)
class _FieldChange:
    table: str
    record_id: str
    label: str
    field: str
    before: str
    after: str


@dataclass(frozen=True)
class _VersionChange:
    """What one version changed relative to the version before it (raw CSV strings compared)."""

    previous: str | None
    document: Mapping[str, Any]
    labels: Mapping[str, Mapping[str, str]]
    removed_labels: Mapping[str, Mapping[str, str]]
    field_changes: tuple[_FieldChange, ...]
    added_sites: Mapping[str, Mapping[str, str]]

    def ids(self, table: str, kind: str) -> list[str]:
        section = self.document[TABLE_NAMES[table]]
        if kind == "changed":
            return [item["id"] for item in section["changed"]]
        return list(section[kind])


def _table_snapshot(version: DatasetVersion, name: str) -> _TableSnapshot:
    where = f"{version.id}/{name}"
    records = _csv_records(_verified_text(version, name), where)
    header = tuple(next(records, (0, []))[1])
    key = TABLE_KEYS[name]
    if key not in header:
        raise PublicSiteError(f"{where}: needs a {key} column")
    rows: dict[str, dict[str, str]] = {}
    for line, values in records:
        if len(values) != len(header):
            raise PublicSiteError(f"{where}: line {line} has {len(values)} values, expected {len(header)}")
        row = dict(zip(header, values))
        if row[key] in rows:
            raise PublicSiteError(f"{where}: duplicate {key} {row[key]!r}")
        rows[row[key]] = row
    return _TableSnapshot(header, rows)


def _version_history(versions: Sequence[DatasetVersion]) -> dict[str, _VersionChange]:
    """Record-level changes of every version against its predecessor, oldest first."""
    history: dict[str, _VersionChange] = {}
    previous: DatasetVersion | None = None
    before: dict[str, _TableSnapshot] = {}
    for version in versions:
        after = {name: _table_snapshot(version, name) for name in TABLE_FILES}
        history[version.id] = _compare_versions(previous, before, after)
        previous, before = version, after
    return history


def _compare_versions(
    previous: DatasetVersion | None, before: Mapping[str, _TableSnapshot], after: Mapping[str, _TableSnapshot]
) -> _VersionChange:
    document: dict[str, Any] = {"previous": previous.id if previous else None, "schema": {}}
    labels: dict[str, dict[str, str]] = {}
    removed_labels: dict[str, dict[str, str]] = {}
    field_changes: list[_FieldChange] = []
    for name in TABLE_FILES:
        table = TABLE_NAMES[name]
        new, old = after[name], before.get(name)
        label_column = TABLE_LABEL_COLUMNS[name]
        labels[table] = {key: row.get(label_column, "") for key, row in new.rows.items()}
        if old is None:
            document["schema"][table] = {"added_columns": [], "removed_columns": []}
            document[table] = {"added": sorted(new.rows), "removed": [], "changed": []}
            removed_labels[table] = {}
            continue
        common = [column for column in new.columns if column in old.columns]
        changed = []
        for key in sorted(set(new.rows) & set(old.rows)):
            fields = [column for column in common if new.rows[key][column] != old.rows[key][column]]
            if fields:
                changed.append({"id": key, "fields": fields})
                field_changes.extend(
                    _FieldChange(table, key, labels[table][key], column, old.rows[key][column], new.rows[key][column])
                    for column in fields
                )
        removed = sorted(set(old.rows) - set(new.rows))
        document["schema"][table] = {
            "added_columns": [column for column in new.columns if column not in old.columns],
            "removed_columns": [column for column in old.columns if column not in new.columns],
        }
        document[table] = {"added": sorted(set(new.rows) - set(old.rows)), "removed": removed, "changed": changed}
        removed_labels[table] = {key: old.rows[key].get(label_column, "") for key in removed}
    sites = after["sites.csv"].rows
    added_sites = {
        key: {column: sites[key].get(column, "") for column in ("name", "country", "statuses_json", "newest_status_as_of")}
        for key in document["sites"]["added"]
    }
    return _VersionChange(
        previous=document["previous"],
        document=document,
        labels=labels,
        removed_labels=removed_labels,
        field_changes=tuple(field_changes),
        added_sites=added_sites,
    )


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
        "derived_download_versions": [version.id for version in context.derived_versions],
        # atlas.sqlite and the zip archives also depend on these libraries (see the module docstring).
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "zlib_version": zlib.ZLIB_RUNTIME_VERSION,
    }


# --------------------------------------------------------------------------------------------
# Shared API objects


def _dataset_ref(context: _Context, version: DatasetVersion | None = None) -> dict[str, Any]:
    version = version or context.current
    return {
        "id": version.id,
        "label": version.label,
        "release_status": version.release_status,
        "publishable_as_final": version.publishable_as_final,
        "checkpoint_date": version.checkpoint_date,
        "lifecycle_reference_date": version.lifecycle_reference_date,
    }


def _dataset_full(context: _Context, atlas: Atlas | None = None) -> dict[str, Any]:
    atlas = atlas or context.atlas
    version = atlas.version
    return {
        **_dataset_ref(context, version),
        "status_window_days": context.config.status_window_days,
        "counts": atlas.counts,
        "manifest_sha256": version.manifest_sha256,
        "repository_path": f"{context.config.versions_root}/{version.id}",
        "window_start": _window_start(context.config, version),
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
        "site_geojson": "api/v1/sites/{site_id}.geojson",
        "country_geojson": "api/v1/countries/{iso2}.geojson",
        "country_csv": "api/v1/countries/{iso2}.csv",
        "citation": "api/v1/citation.json",
        "openapi": "api/v1/openapi.json",
        "schemas": "api/v1/schemas/index.json",
    }


def _download_objects(context: _Context, prefix: str) -> list[dict[str, Any]]:
    pinned = f"{prefix}downloads/{context.current.id}/"
    return [
        {
            "name": item.name,
            "format": item.format,
            "media_type": item.media_type,
            "url": f"{prefix}downloads/{LATEST}/{item.name}",
            "bytes": item.size,
            "sha256": item.sha256,
            "pinned_url": pinned + (context.zip_name if item.name == f"datacenter-atlas-{LATEST}.zip" else item.name),
        }
        for item in context.downloads
    ]


def _license_block(context: _Context) -> dict[str, Any]:
    """The licence layering of the data, in one object reused by every machine-readable output."""
    config = context.config
    return {
        "data": dict(config.data_license),
        "code": dict(config.code_license),
        "openstreetmap_geometries": dict(ODBL),
        "third_party": THIRD_PARTY_TERMS,
    }


def _attribution_statement(context: _Context, version: DatasetVersion | None = None) -> str:
    version = version or context.current
    return (
        f"{context.config.title} ({context.config.author.get('name')}), {context.base_url} "
        f"(dataset {version.id}), {context.config.data_license.get('id', '')}. Includes data "
        f"{ODBL['attribution']} ({ODBL['id']}); other third-party facts and geometries keep their source terms: "
        f"{context.base_url}about/attribution/"
    )


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
    base = context.base_url
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "site": site,
        "projects": atlas.projects_by_site[site_id],
        "evidence": atlas.evidence_by_site[site_id],
        "links": {
            "html": site["url"],
            "sites": f"{base}api/v1/sites.json",
            "dataset_download": f"{base}downloads/{context.current.id}/{context.zip_name}",
            "geojson": f"{base}api/v1/sites/{site_id}.geojson",
            "explorer": f"{base}#site={site_id}",
            "dataset_files": f"{base}downloads/{context.current.id}/",
            "latest_download": f"{base}downloads/{LATEST}/datacenter-atlas-{LATEST}.zip",
            "citation": f"{base}api/v1/citation.json",
        },
    }


def _feature(summary: Mapping[str, Any], geometry: Any) -> dict[str, Any]:
    """A GeoJSON Feature whose rings are oriented as RFC 7946 requires (typed records stay verbatim)."""
    return {"type": "Feature", "id": summary["site_id"], "geometry": _rfc7946_geometry(geometry), "properties": summary}


def _rfc7946_geometry(geometry: Any) -> Any:
    """A copy of a (Multi)Polygon with counterclockwise exterior rings and clockwise holes.

    RFC 7946 section 3.1.6 requires this of GeoJSON generators. Orientation is the sign of the
    planar shoelace area in longitude/latitude, which is exact for these small, non-antimeridian
    rings; a degenerate ring (zero area) is left as it is. Other geometry types are returned as is.
    """
    if not isinstance(geometry, dict):
        return geometry
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon" and isinstance(coordinates, list):
        return {**geometry, "coordinates": _oriented_polygon(coordinates)}
    if kind == "MultiPolygon" and isinstance(coordinates, list):
        return {**geometry, "coordinates": [_oriented_polygon(polygon) for polygon in coordinates]}
    return geometry


def _oriented_polygon(rings: Any) -> Any:
    if not isinstance(rings, list):
        return rings
    oriented = []
    for index, ring in enumerate(rings):
        area = _signed_area(ring)
        if area != 0 and (area > 0) != (index == 0):
            ring = list(reversed(ring))
        oriented.append(ring)
    return oriented


def _signed_area(ring: Any) -> float:
    """Twice the signed planar area of a ring (positive = counterclockwise); 0 when not computable."""
    if not isinstance(ring, list) or len(ring) < 3:
        return 0.0
    points = []
    for position in ring:
        if not (isinstance(position, list) and len(position) >= 2 and _is_number(position[0]) and _is_number(position[1])):
            return 0.0
        points.append((float(position[0]), float(position[1])))
    if points[0] != points[-1]:
        points.append(points[0])
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:]))


def _geometry_positions(geometry: Any) -> Iterator[tuple[float, float]]:
    """Every (longitude, latitude) position of a GeoJSON geometry."""
    stack = [geometry.get("coordinates") if isinstance(geometry, dict) else None]
    while stack:
        item = stack.pop()
        if isinstance(item, list) and len(item) >= 2 and _is_number(item[0]) and _is_number(item[1]):
            yield float(item[0]), float(item[1])
        elif isinstance(item, list):
            stack.extend(item)


def _bounding_box(atlas: Atlas) -> tuple[float, float, float, float] | None:
    """(south, west, north, east) of every geometry position and display anchor, rounded outwards."""
    positions = [position for site in atlas.sites for position in _geometry_positions(site.get("geometry"))]
    positions += [(site["longitude"], site["latitude"]) for site in atlas.sites]
    if not positions:
        return None
    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    down = lambda value: math.floor(value * 10_000) / 10_000  # noqa: E731
    up = lambda value: math.ceil(value * 10_000) / 10_000  # noqa: E731
    return down(min(latitudes)), down(min(longitudes)), up(max(latitudes)), up(max(longitudes))


# --------------------------------------------------------------------------------------------
# JSON API

ENDPOINT_DESCRIPTIONS = {
    "index": "API root: dataset metadata, endpoint templates, downloads, licences and the citation.",
    "sites": "Array of site summaries, sorted by name.",
    "sites_geojson": "GeoJSON FeatureCollection of every site; feature properties are site summaries.",
    "site": "One site: typed site record, its projects and every evidence row.",
    "projects": "Array of typed project records (CSV order).",
    "project": "One project with its site summary and evidence.",
    "evidence": "Array of typed evidence records (CSV order).",
    "evidence_item": "One evidence record with the projects and sites it supports.",
    "countries": "Country summaries, by site count.",
    "country": "One country (upper-case ISO code) with its site summaries.",
    "stats": "Counts by status, month, country, location type and source, with units and research audit metadata.",
    "versions": "Every dataset version with counts, files, checksums and record-level changes from the previous version.",
    "vocabularies": "Labels and descriptions for coded values.",
    "site_geojson": "One site as a GeoJSON FeatureCollection (one feature), for GIS tools.",
    "country_geojson": "The sites of one country as a GeoJSON FeatureCollection.",
    "country_csv": "The sites of one country as CSV (RFC 4180, CRLF, list columns as JSON arrays).",
    "citation": "How to cite the current version: APA text, BibTeX, biblatex, RIS and CSL-JSON.",
    "openapi": "OpenAPI 3.1 description of every endpoint, with JSON Schemas of each response.",
    "schemas": "Index of the JSON Schemas (2020-12) of every API response and record type.",
}
OPERATION_IDS = {
    "index": "getIndex", "sites": "listSites", "sites_geojson": "getSitesGeoJSON", "site": "getSite",
    "projects": "listProjects", "project": "getProject", "evidence": "listEvidence", "evidence_item": "getEvidence",
    "countries": "listCountries", "country": "getCountry", "stats": "getStats", "versions": "listVersions",
    "vocabularies": "getVocabularies", "site_geojson": "getSiteGeoJSON", "country_geojson": "getCountryGeoJSON",
    "country_csv": "getCountryCSV", "citation": "getCitation", "openapi": "getOpenAPI", "schemas": "listSchemas",
}
# Response schema of every endpoint (a schema name, or ("array", name) for arrays of records).
ENDPOINT_SCHEMAS: dict[str, Any] = {
    "index": "index", "sites": ("array", "site-summary"), "sites_geojson": "feature-collection",
    "site": "site-document", "projects": ("array", "project"), "project": "project-document",
    "evidence": ("array", "evidence"), "evidence_item": "evidence-document",
    "countries": ("array", "country-summary"), "country": "country-document", "stats": "stats",
    "versions": "versions", "vocabularies": "vocabularies", "site_geojson": "feature-collection",
    "country_geojson": "feature-collection", "country_csv": None, "citation": "citation", "openapi": None,
    "schemas": "schema-index",
}
CSV_EXPORT_COLUMNS = (
    "site_id", "name", "country", "country_iso_a2", "latitude", "longitude", "statuses_json",
    "newest_status_as_of", "oldest_status_as_of", "project_count", "official_boundary", "geometry_type",
    "status_publishers_json", "geometry_licenses_json", "url", "api_url",
)
FORMULA_PREFIX = re.compile(r"^[=+\-@\t\r]")


def _write_api(writer: _Writer, context: _Context) -> None:
    atlas = context.atlas
    writer.write_json("api/v1/index.json", _api_index(context))
    writer.write_json("api/v1/sites.json", atlas.summaries)
    writer.write_json("api/v1/sites.geojson", _sites_geojson(context))
    for site in atlas.sites:
        site_id = site["site_id"]
        writer.write_json(f"api/v1/sites/{site_id}.json", _site_document(context, site))
        writer.write_json(f"api/v1/sites/{site_id}.geojson", _feature_collection(
            context, [_feature(atlas.summary_by_id[site_id], site["geometry"])], name=f"{GEOJSON_LAYER_NAME}-{site_id}",
        ))
    writer.write_json("api/v1/projects.json", atlas.projects)
    for project in atlas.projects:
        writer.write_json(f"api/v1/projects/{project['project_id']}.json", _project_document(context, project))
    writer.write_json("api/v1/evidence.json", atlas.evidence)
    for evidence in atlas.evidence:
        writer.write_json(f"api/v1/evidence/{evidence['evidence_id']}.json", _evidence_document(context, evidence))
    writer.write_json("api/v1/countries.json", atlas.countries)
    for country in atlas.countries:
        iso = country["country_iso_a2"]
        summaries = [atlas.summary_by_id[site_id] for site_id in _sorted_site_ids(atlas, country["site_ids"])]
        writer.write_json(f"api/v1/countries/{iso}.json", {
            "api_version": API_VERSION,
            "dataset": _dataset_ref(context),
            "country": country,
            "sites": summaries,
        })
        writer.write_json(f"api/v1/countries/{iso}.geojson", _feature_collection(
            context,
            [_feature(summary, atlas.site_by_id[summary["site_id"]]["geometry"]) for summary in summaries],
            name=f"{GEOJSON_LAYER_NAME}-{iso.lower()}",
        ))
        writer.write_text(f"api/v1/countries/{iso}.csv", _sites_csv(summaries))
    writer.write_json("api/v1/stats.json", _stats(context))
    writer.write_json("api/v1/versions.json", _versions_document(context))
    writer.write_json("api/v1/vocabularies.json", {"api_version": API_VERSION, **context.vocabularies})
    citations = _citations(context)
    writer.write_json("api/v1/citation.json", {
        "api_version": API_VERSION, "dataset": _dataset_ref(context), **citations,
    })
    writer.write_text("api/v1/citation.bib", citations["bibtex"] + "\n")
    writer.write_text("api/v1/citation.ris", citations["ris"])
    _write_contract(writer, context)


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
        "license": _license_block(context),
        "attribution_url": f"{base}about/attribution/",
        "docs_url": f"{base}api/",
        "build": {"source_commit": context.commit},
        "title": config.title,
        "caveats": list(DATA_CAVEATS),
        "attribution": _attribution_statement(context),
        "citation": _citations(context)["apa"],
        "citation_url": f"{base}api/v1/citation.json",
        "openapi_url": f"{base}api/v1/openapi.json",
        "schemas_url": f"{base}api/v1/schemas/index.json",
        "llms_txt_url": f"{base}llms.txt",
        "versions_url": f"{base}versions/",
        "downloads_url": f"{base}downloads/",
        "dataset_files_url": f"{base}downloads/{context.current.id}/",
        "feeds": {"releases": f"{base}feed.xml", "sites": f"{base}sites-feed.xml"},
        "media_type_note": MEDIA_TYPE_NOTE,
    }


MEDIA_TYPE_NOTE = (
    "GitHub Pages serves .ndjson, .sqlite and SHA256SUMS as application/octet-stream and .zip as "
    "application/x-zip-compressed; identify formats by file extension or by media_type here, not by Content-Type."
)


def _feature_collection(context: _Context, features: list[dict[str, Any]], *, name: str = GEOJSON_LAYER_NAME) -> dict[str, Any]:
    base = context.base_url
    return {
        "type": "FeatureCollection",
        "name": name,
        "dataset": {
            "id": context.current.id,
            "label": context.current.label,
            "release_status": context.current.release_status,
        },
        "license": _license_block(context),
        "attribution": _attribution_statement(context),
        "attribution_url": f"{base}about/attribution/",
        "features": features,
    }


def _sites_geojson(context: _Context) -> dict[str, Any]:
    atlas = context.atlas
    return _feature_collection(context, [
        _feature(summary, atlas.site_by_id[summary["site_id"]]["geometry"]) for summary in atlas.summaries
    ])


def _csv_cell(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif _is_number(value):
        text = _number_text(value)
    elif isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
        if FORMULA_PREFIX.match(text):
            text = "'" + text  # a spreadsheet would otherwise evaluate it as a formula
    if any(char in text for char in ',"\r\n'):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _sites_csv(summaries: Sequence[Mapping[str, Any]]) -> str:
    """Site summaries as RFC 4180 CSV (CRLF, header first); list columns are JSON arrays."""
    sources = {
        "statuses_json": "statuses", "status_publishers_json": "status_publishers",
        "geometry_licenses_json": "geometry_licenses",
    }
    lines = [",".join(CSV_EXPORT_COLUMNS)]
    for summary in summaries:
        lines.append(",".join(_csv_cell(summary.get(sources.get(column, column))) for column in CSV_EXPORT_COLUMNS))
    return "\r\n".join(lines) + "\r\n"


def _project_document(context: _Context, project: Mapping[str, Any]) -> dict[str, Any]:
    atlas = context.atlas
    base = context.base_url
    return {
        "api_version": API_VERSION,
        "dataset": _dataset_ref(context),
        "project": project,
        "site": atlas.summary_by_id[project["site_id"]],
        "evidence": atlas.evidence_by_project[project["project_id"]],
        "links": {
            "html": project["url"],
            "site": atlas.site_by_id[project["site_id"]]["api_url"],
            "dataset_download": f"{base}downloads/{context.current.id}/{context.zip_name}",
            "dataset_files": f"{base}downloads/{context.current.id}/",
            "latest_download": f"{base}downloads/{LATEST}/datacenter-atlas-{LATEST}.zip",
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
        "units": dict(STATS_UNITS),
    }


def _versions_document(context: _Context) -> dict[str, Any]:
    base = context.base_url
    versions = []
    for version in context.versions:
        change = context.history[version.id]
        listing = context.download_dirs.get(version.id, ())
        listed = {item.name for item in listing}
        files = [
            {
                "name": item.name,
                "bytes": item.size,
                "sha256": item.sha256,
                "url": f"{base}downloads/{version.id}/{item.name}",
                "derived": False,
            }
            for item in version.files
        ]
        files += [
            {
                "name": item.name,
                "bytes": item.size,
                "sha256": item.sha256,
                "url": f"{base}downloads/{version.id}/{item.name}",
                "derived": True,
            }
            for item in sorted(listing, key=lambda value: value.name)
            if item.derived
        ]
        if listing and not listed >= {record.name for record in version.files}:
            raise PublicSiteError(f"downloads/{version.id}: original files missing from the listing")
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
            "files": files,
            "download_base_url": f"{base}downloads/{version.id}/",
            "repository_url": _tree_url(context, version),
            "added_site_ids": change.ids("sites.csv", "added"),
            "removed_site_ids": change.ids("sites.csv", "removed"),
            "page_url": f"{base}versions/{version.id}/",
            "derived_downloads": context.has_derived(version),
            "changes": change.document,
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


# Citation ----------------------------------------------------------------------------------


def _citation_author(config: SiteConfig) -> tuple[str, str]:
    """(family, given) names of the author: config author.family/author.given, else split author.name."""
    author = config.author
    family, given = author.get("family"), author.get("given")
    if isinstance(family, str) and family.strip():
        return family.strip(), str(given or "").strip()
    parts = str(author.get("name", "")).split()
    return (parts[-1], " ".join(parts[:-1])) if parts else ("", "")


def _citation_names(config: SiteConfig, version: DatasetVersion) -> tuple[str, str, str]:
    """(APA author such as "Kyars, K.", full author such as "Kyars, Kian", year) of a version."""
    family, given = _citation_author(config)
    initials = " ".join(f"{part[0]}." for part in re.split(r"[\s-]+", given) if part)
    apa_author = f"{family}, {initials}" if initials else family
    full_author = f"{family}, {given}" if given else family
    return apa_author, full_author, version.checkpoint_date[:4]


def _bibtex_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "''").replace("{", "(").replace("}", ")")


def _citations(context: _Context, version: DatasetVersion | None = None) -> dict[str, Any]:
    """Every citation format of one version, from one set of facts (title, author, version, date, URL)."""
    version = version or context.current
    config = context.config
    family, given = _citation_author(config)
    apa_author, full_author, year = _citation_names(config, version)
    title = config.title
    url = f"{context.base_url}downloads/{version.id}/"
    key = re.sub(r"[^a-z0-9]", "", family.lower()) + year + re.sub(r"[^a-z0-9]", "", config.site_name.lower())
    note = f"Data as published {version.checkpoint_date}"
    bibtex = "\n".join([
        f"@misc{{{key},",
        f'  author = "{_bibtex_value(full_author)}",',
        f'  title  = "{_bibtex_value(title)}",',
        f'  year   = "{year}",',
        f'  note   = "{_bibtex_value(note)}",',
        f'  url    = "{_bibtex_value(url)}"',
        "}",
    ])
    biblatex = "\n".join([
        f"@dataset{{{key},",
        f"  author  = {{{_bibtex_value(full_author)}}},",
        f"  title   = {{{_bibtex_value(title)}}},",
        f"  date    = {{{version.checkpoint_date}}},",
        f"  version = {{{_bibtex_value(version.id)}}},",
        f"  url     = {{{_bibtex_value(url)}}},",
        f"  note    = {{{_bibtex_value(version.label)}}}",
        "}",
    ])
    ris_lines = [
        "TY  - DATA",
        f"AU  - {full_author}",
        f"TI  - {title}",
        f"PY  - {year}",
        f"DA  - {version.checkpoint_date.replace('-', '/')}",
        f"ET  - {version.id}",
        f"UR  - {url}",
        f"PB  - {config.site_name}",
        f"N1  - {note}. {version.label}.",
        "ER  - ",
    ]
    year_number, month, day = (int(part) for part in version.checkpoint_date.split("-"))
    csl = {
        "id": key,
        "type": "dataset",
        "title": title,
        "author": [{"family": family, "given": given}] if given else [{"literal": family}],
        "issued": {"date-parts": [[year_number, month, day]]},
        "version": version.id,
        "URL": url,
        "publisher": config.site_name,
        "note": f"{version.label}; {note}",
    }
    return {
        "apa": f"{apa_author} ({year}). {title} ({version.checkpoint_date}) [Data set]. {url}",
        "bibtex": bibtex,
        "biblatex": biblatex,
        "ris": "\r\n".join(ris_lines) + "\r\n",
        "csl_json": [csl],
        "citation_cff_url": f"{config.repository_url}/blob/main/CITATION.cff",
        "version_url": f"{context.base_url}versions/{version.id}/",
        "files_url": url,
    }


def _site_citation(context: _Context, site: Mapping[str, Any]) -> str:
    apa_author, _, year = _citation_names(context.config, context.current)
    return (
        f"{apa_author} ({year}). {site.get('name')} [site {site['site_id']}]. In {context.config.title} "
        f"({context.current.checkpoint_date}) [Data set]. {site['url']} "
        f"Source files: {context.base_url}downloads/{context.current.id}/"
    )


# Machine-readable contract (OpenAPI 3.1 and JSON Schema 2020-12) -----------------------------

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_COMPONENTS = {
    "geometry": "Geometry", "source-ref": "SourceRef", "typed-metric-observation": "TypedMetricObservation",
    "role-claim": "RoleClaim", "workload-observation": "WorkloadObservation", "site": "Site", "project": "Project",
    "evidence": "Evidence", "site-summary": "SiteSummary", "dataset-ref": "DatasetRef", "dataset": "Dataset",
    "license": "License", "download": "Download", "site-document": "SiteDocument",
    "project-document": "ProjectDocument", "evidence-document": "EvidenceDocument",
    "feature-collection": "FeatureCollection", "country-summary": "CountrySummary",
    "country-document": "CountryDocument", "stats": "Stats", "version": "Version", "versions": "Versions",
    "vocabularies": "Vocabularies", "index": "Index", "citation": "Citation", "schema-index": "SchemaIndex",
}
EMBEDDED_ITEM_SCHEMAS = {
    "typed_metric_observation": "typed-metric-observation",
    "role_claim": "role-claim",
    "workload_observation": "workload-observation",
}
EMBEDDED_FIELD_TYPES = {
    "evidence_id": {"type": "string"},
    "low": {"type": ["number", "null"]},
    "base": {"type": ["number", "null"]},
    "high": {"type": ["number", "null"]},
    "confidence": {"type": ["number", "null"]},
    "as_of_date": {"type": ["string", "null"]},
    "target_date": {"type": ["string", "null"]},
    "notes": {"type": ["string", "null"]},
}
LOGICAL_JSON_TYPES = {
    "number": {"type": "number"},
    "integer": {"type": "integer"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "uri": {"type": "string", "format": "uri"},
    "sha256": {"type": "string"},
}


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"{name}.schema.json"}


def _nullable(schema: Mapping[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return {"anyOf": [dict(schema), {"type": "null"}]}
    result = dict(schema)
    kind = result.get("type")
    if isinstance(kind, str):
        result["type"] = [kind, "null"]
    elif isinstance(kind, list) and "null" not in kind:
        result["type"] = [*kind, "null"]
    return result


def _described(schema: Mapping[str, Any], description: Any) -> dict[str, Any]:
    result = dict(schema)
    if isinstance(description, str) and description.strip():
        if "$ref" in result:
            return {"description": description, "allOf": [result]}
        result["description"] = description
    return result


def _string_array(description: str = "") -> dict[str, Any]:
    return _described({"type": "array", "items": {"type": "string"}}, description)


def _object(properties: Mapping[str, Any], *, title: str = "", description: str = "", required: Iterable[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    if title:
        schema["title"] = title
    if description:
        schema["description"] = description
    schema["type"] = "object"
    schema["required"] = list(properties if required is None else required)
    schema["properties"] = dict(properties)
    return schema


def _count_map(description: str = "") -> dict[str, Any]:
    return _described({"type": "object", "additionalProperties": {"type": "integer"}}, description)


def _json_schemas(context: _Context) -> dict[str, dict[str, Any]]:
    """Every response and record schema, keyed by file stem; ``$ref`` values name sibling files."""
    atlas = context.atlas
    descriptions = context.descriptions
    derived_descriptions = descriptions.get("derived") or {}
    url = {"type": "string", "format": "uri"}
    schemas: dict[str, dict[str, Any]] = {}
    geometry_types = (atlas.schema.get("geojson") or {}).get("allowed_geometry_types")
    geometry_type: dict[str, Any] = {"type": "string"}
    if isinstance(geometry_types, list) and geometry_types:
        geometry_type["enum"] = sorted(str(value) for value in geometry_types)
    schemas["geometry"] = _object(
        {"type": geometry_type, "coordinates": {"type": "array"}},
        title="GeoJSON geometry", description="A GeoJSON geometry object (RFC 7946) in WGS 84 longitude/latitude.",
    )
    schemas["source-ref"] = _object(
        {name: {"type": ["string", "null"]} for name in STATUS_SOURCE_FIELDS},
        title="Evidence summary",
        description="Summary of one evidence row: who published it, when, where and under which licence.",
    )
    embedded = atlas.schema.get("embedded_types") if isinstance(atlas.schema.get("embedded_types"), dict) else {}
    for kind, name in EMBEDDED_ITEM_SCHEMAS.items():
        spec = embedded.get(kind) if isinstance(embedded.get(kind), dict) else {}
        required = [str(field) for field in spec.get("required_fields") or []]
        properties = {field: EMBEDDED_FIELD_TYPES.get(field, {"type": ["string", "null"]}) for field in required}
        schemas[name] = _object(
            properties, title=kind.replace("_", " ").capitalize(),
            description=f"One item of an embedded JSON array (schema.json embedded_types.{kind}).",
        )
    array_items = atlas.schema.get("embedded_array_items") if isinstance(atlas.schema.get("embedded_array_items"), dict) else {}
    titles = {"sites.csv": "Site record", "projects.csv": "Project record", "evidence.csv": "Evidence record"}
    derived_schemas = {
        "sites.csv": {
            "official_boundary": {"type": "boolean"}, "country_slug": {"type": "string"}, "url": url, "api_url": url,
            "geometry_licenses": _string_array(), "geometry_attributions": _string_array(),
        },
        "projects.csv": {
            "evidence_ids": _string_array(), "status_source": _ref("source-ref"), "url": url, "api_url": url,
            "geometry_source": _nullable(_ref("source-ref")),
        },
        "evidence.csv": {
            "site_ids": _string_array(), "url": url, "api_url": url, "archive_url": _nullable(url),
        },
    }
    for file_name in TABLE_FILES:
        table = TABLE_NAMES[file_name]
        column_descriptions = descriptions.get("tables", {}).get(file_name, {})
        properties: dict[str, Any] = {}
        for spec in atlas.fields[file_name]:
            column = spec["name"]
            logical = str(spec.get("logical_type", "string"))
            if logical == "json_array":
                item_type = (array_items.get(f"{file_name}:{column}") or {}).get("item_type")
                if item_type in EMBEDDED_ITEM_SCHEMAS:
                    schema: dict[str, Any] = {"type": "array", "items": _ref(EMBEDDED_ITEM_SCHEMAS[item_type])}
                elif all(isinstance(item, str) for row in atlas.raw[file_name] for item in _json_items(row[column])):
                    schema = {"type": "array", "items": {"type": "string"}}
                else:
                    schema = {"type": "array"}
            elif logical == "geojson_geometry":
                schema = _ref("geometry")
            else:
                schema = dict(LOGICAL_JSON_TYPES.get(logical, {"type": "string"}))
            if spec.get("allows_empty_string") is not False:
                schema = _nullable(schema)
            properties[typed_field_name(column)] = _described(schema, column_descriptions.get(column))
        for name, schema in derived_schemas[file_name].items():
            properties[name] = _described(schema, (derived_descriptions.get(table) or {}).get(name))
        schemas[table if table != "sites" else "site"] = _object(
            properties, title=titles[file_name],
            description=(
                f"A typed {file_name} row: empty CSV values are null, *_json columns are parsed and lose the suffix, "
                "then the derived fields follow."
            ),
        )
    schemas["project"] = schemas.pop("projects")
    summary_descriptions = descriptions.get("site_summary") or {}
    summary_properties = {
        "site_id": {"type": "string"},
        "name": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "country_iso_a2": {"type": "string", "pattern": "^[A-Z]{2}$"},
        "latitude": {"type": "number"},
        "longitude": {"type": "number"},
        "geometry_type": {"type": ["string", "null"]},
        "official_boundary": {"type": "boolean"},
        "locator_scopes": _nullable(_string_array()),
        "statuses": _nullable(_string_array()),
        "newest_status_as_of": {"type": ["string", "null"], "format": "date"},
        "oldest_status_as_of": {"type": ["string", "null"], "format": "date"},
        "project_count": {"type": ["integer", "null"]},
        "projects": {"type": "array", "items": _object({
            "project_id": {"type": "string"}, "name": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]}, "status_as_of": {"type": ["string", "null"], "format": "date"},
        })},
        "status_publishers": _string_array(),
        "power_observations": {"type": "array", "items": _object({
            "project_id": {"type": "string"}, "metric": {"type": ["string", "null"]}, "stage": {"type": ["string", "null"]},
            "low": {"type": ["number", "null"]}, "base": {"type": ["number", "null"]}, "high": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]}, "as_of_date": {"type": ["string", "null"]},
        })},
        "verification_posture": {"type": ["string", "null"]},
        "independent_imagery_verification": {"type": ["boolean", "null"]},
        "url": url,
        "api_url": url,
        "geometry_licenses": _string_array(),
        "geometry_attributions": _string_array(),
    }
    schemas["site-summary"] = _object(
        {name: _described(schema, summary_descriptions.get(name)) for name, schema in summary_properties.items()},
        title="Site summary", description="One site in sites.json, sites.geojson properties and country files.",
    )
    schemas["dataset-ref"] = _object({
        "id": {"type": "string"}, "label": {"type": "string"}, "release_status": {"type": "string"},
        "publishable_as_final": {"type": "boolean"}, "checkpoint_date": {"type": "string", "format": "date"},
        "lifecycle_reference_date": {"type": "string", "format": "date"},
    }, title="Dataset reference", description="The dataset version a document belongs to.")
    index_descriptions = descriptions.get("index") or {}
    schemas["dataset"] = _object({
        **schemas["dataset-ref"]["properties"],
        "status_window_days": {"type": "integer"},
        "counts": _count_map("Record counts; see stats.json for the meaning of each key."),
        "manifest_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "repository_path": {"type": "string"},
        "window_start": {"type": "string", "format": "date"},
    }, title="Dataset", description="Dataset version metadata with counts and the status window.")
    schemas["license"] = _object({
        "data": {"type": "object"}, "code": {"type": "object"}, "openstreetmap_geometries": {"type": "object"},
        "third_party": {"type": "string"},
    }, title="Licences", description="The licence layering: Atlas data, code, OpenStreetMap-derived geometries, third parties.")
    schemas["download"] = _object({
        "name": {"type": "string"}, "format": {"type": "string"}, "media_type": {"type": "string"}, "url": url,
        "bytes": {"type": "integer"}, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "pinned_url": url,
    }, title="Download", description="One file of downloads/latest/ with its pinned URL under downloads/<id>/.")
    dataset_ref = _ref("dataset-ref")
    schemas["site-document"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref, "site": _ref("site"),
        "projects": {"type": "array", "items": _ref("project")}, "evidence": {"type": "array", "items": _ref("evidence")},
        "links": _object({name: url for name in (
            "html", "sites", "dataset_download", "geojson", "explorer", "dataset_files", "latest_download", "citation",
        )}),
    }, title="Site document", description="api/v1/sites/{site_id}.json")
    schemas["project-document"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref, "project": _ref("project"),
        "site": _ref("site-summary"), "evidence": {"type": "array", "items": _ref("evidence")},
        "links": _object({name: url for name in ("html", "site", "dataset_download", "dataset_files", "latest_download")}),
    }, title="Project document", description="api/v1/projects/{project_id}.json")
    schemas["evidence-document"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref, "evidence": _ref("evidence"),
        "projects": {"type": "array", "items": _object({
            "project_id": {"type": "string"}, "name": {"type": ["string", "null"]}, "site_id": {"type": "string"},
            "status": {"type": ["string", "null"]}, "status_as_of": {"type": ["string", "null"]}, "url": url, "api_url": url,
        })},
        "sites": {"type": "array", "items": _object({
            "site_id": {"type": "string"}, "name": {"type": ["string", "null"]}, "url": url, "api_url": url,
        })},
    }, title="Evidence document", description="api/v1/evidence/{evidence_id}.json")
    schemas["feature-collection"] = _object({
        "type": {"type": "string", "const": "FeatureCollection"},
        "name": {"type": "string"},
        "dataset": _object({"id": {"type": "string"}, "label": {"type": "string"}, "release_status": {"type": "string"}}),
        "license": _ref("license"),
        "attribution": {"type": "string"},
        "attribution_url": url,
        "features": {"type": "array", "items": _object({
            "type": {"type": "string", "const": "Feature"}, "id": {"type": "string"}, "geometry": _ref("geometry"),
            "properties": _ref("site-summary"),
        })},
    }, title="Sites GeoJSON", description=(
        "A GeoJSON FeatureCollection (RFC 7946, rings oriented counterclockwise) whose feature properties are site "
        "summaries; dataset, license and attribution are foreign members."
    ))
    country_descriptions = descriptions.get("country_summary") or {}
    schemas["country-summary"] = _object({
        name: _described(schema, country_descriptions.get(name)) for name, schema in {
            "country_iso_a2": {"type": "string", "pattern": "^[A-Z]{2}$"}, "country": {"type": "string"},
            "slug": {"type": "string"}, "site_count": {"type": "integer"}, "project_count": {"type": "integer"},
            "statuses": _count_map(), "site_ids": _string_array(), "url": url, "api_url": url,
            "geojson_url": url, "csv_url": url,
        }.items()
    }, title="Country summary", description="One entry of countries.json.")
    schemas["country-document"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref,
        "country": _ref("country-summary"), "sites": {"type": "array", "items": _ref("site-summary")},
    }, title="Country document", description="api/v1/countries/{iso2}.json")
    stats_descriptions = descriptions.get("stats") or {}
    stats_properties: dict[str, Any] = {
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref,
        "counts": _count_map(stats_descriptions.get("counts", "")),
    }
    for key in STATS_UNITS:
        stats_properties[key] = _count_map(stats_descriptions.get(key, ""))
    stats_properties["release_gates"] = _described({"type": "object"}, stats_descriptions.get("release_gates", ""))
    stats_properties["units"] = _described(
        {"type": "object", "additionalProperties": {"type": "string"}}, stats_descriptions.get("units", "")
    )
    schemas["stats"] = _object(stats_properties, title="Statistics", description="api/v1/stats.json")
    version_descriptions = descriptions.get("version") or {}
    change_section = _object({
        "added": _string_array(), "removed": _string_array(),
        "changed": {"type": "array", "items": _object({"id": {"type": "string"}, "fields": _string_array()})},
    })
    version_properties = {
        "id": {"type": "string"}, "kind": {"type": "string"}, "label": {"type": "string"},
        "checkpoint_date": {"type": "string", "format": "date"},
        "lifecycle_reference_date": {"type": "string", "format": "date"},
        "release_status": {"type": "string"}, "publishable_as_final": {"type": "boolean"},
        "counts": _count_map(), "manifest_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "files": {"type": "array", "items": _object({
            "name": {"type": "string"}, "bytes": {"type": "integer"},
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "url": url, "derived": {"type": "boolean"},
        })},
        "download_base_url": url, "repository_url": url, "added_site_ids": _string_array(),
        "removed_site_ids": _string_array(), "page_url": url, "derived_downloads": {"type": "boolean"},
        "changes": _object({
            "previous": {"type": ["string", "null"]},
            "schema": {"type": "object", "additionalProperties": _object({
                "added_columns": _string_array(), "removed_columns": _string_array(),
            })},
            "sites": change_section, "projects": change_section, "evidence": change_section,
        }),
    }
    schemas["version"] = _object(
        {name: _described(schema, version_descriptions.get(name)) for name, schema in version_properties.items()},
        title="Dataset version", description="One entry of versions.json.",
    )
    schemas["versions"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "current": {"type": "string"},
        "last_preview": {"type": "string"}, "versions": {"type": "array", "items": _ref("version")},
    }, title="Versions", description="api/v1/versions.json")
    vocabulary_entry = _object(
        {"label": {"type": "string"}, "unit": {"type": "string"}, "description": {"type": "string"}},
        required=("label", "description"),
    )
    schemas["vocabularies"] = {
        "title": "Vocabularies",
        "description": "api/v1/vocabularies.json: for each vocabulary, code -> {label, description} (power_metrics add unit).",
        "type": "object",
        "required": ["api_version", *VOCABULARY_KEYS],
        "properties": {
            "api_version": {"type": "string", "const": API_VERSION},
            **{key: {"type": "object", "additionalProperties": vocabulary_entry} for key in VOCABULARY_KEYS},
        },
    }
    index_properties = {
        "api_version": {"type": "string", "const": API_VERSION}, "name": {"type": "string"},
        "description": {"type": "string"}, "base_url": url, "repository_url": url, "dataset": _ref("dataset"),
        "endpoints": {"type": "object", "additionalProperties": {"type": "string"}},
        "downloads": {"type": "array", "items": _ref("download")}, "license": _ref("license"),
        "attribution_url": url, "docs_url": url,
        "build": _object({"source_commit": {"type": ["string", "null"]}}),
        "title": {"type": "string"}, "caveats": _string_array(), "attribution": {"type": "string"},
        "citation": {"type": "string"}, "citation_url": url, "openapi_url": url, "schemas_url": url,
        "llms_txt_url": url, "versions_url": url, "downloads_url": url, "dataset_files_url": url,
        "feeds": {"type": "object", "additionalProperties": url}, "media_type_note": {"type": "string"},
    }
    schemas["index"] = _object(
        {name: _described(schema, index_descriptions.get(name)) for name, schema in index_properties.items()},
        title="API index", description="api/v1/index.json",
    )
    schemas["citation"] = _object({
        "api_version": {"type": "string", "const": API_VERSION}, "dataset": dataset_ref, "apa": {"type": "string"},
        "bibtex": {"type": "string"}, "biblatex": {"type": "string"}, "ris": {"type": "string"},
        "csl_json": {"type": "array", "items": {"type": "object"}}, "citation_cff_url": url, "version_url": url,
        "files_url": url,
    }, title="Citation", description="api/v1/citation.json")
    schemas["schema-index"] = _object({
        "api_version": {"type": "string", "const": API_VERSION},
        "schemas": {"type": "object", "additionalProperties": url},
        "openapi_url": url,
    }, title="Schema index", description="api/v1/schemas/index.json")
    base = context.base_url
    return {
        name: {"$schema": JSON_SCHEMA_DIALECT, "$id": f"{base}api/v1/schemas/{name}.schema.json", **schema}
        for name, schema in schemas.items()
    }


def _json_items(value: str) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except ValueError:
        return []
    return parsed if isinstance(parsed, list) else []


def _component_refs(value: Any) -> Any:
    """A schema with file references rewritten to OpenAPI components, and $schema/$id dropped."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"$schema", "$id"}:
                continue
            if key == "$ref" and isinstance(item, str) and item.endswith(".schema.json"):
                result[key] = f"#/components/schemas/{SCHEMA_COMPONENTS[item.removesuffix('.schema.json')]}"
            else:
                result[key] = _component_refs(item)
        return result
    if isinstance(value, list):
        return [_component_refs(item) for item in value]
    return value


def _openapi(context: _Context, schemas: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    config, atlas = context.config, context.atlas
    base = context.base_url
    examples = {
        "site_id": atlas.summaries[0]["site_id"] if atlas.summaries else "",
        "project_id": atlas.projects[0]["project_id"] if atlas.projects else "",
        "evidence_id": atlas.evidence[0]["evidence_id"] if atlas.evidence else "",
        "iso2": atlas.countries[0]["country_iso_a2"] if atlas.countries else "",
    }
    parameter_descriptions = {
        "site_id": "Site identifier (site_id), as in api/v1/sites.json.",
        "project_id": "Project identifier (project_id), as in api/v1/projects.json.",
        "evidence_id": "Evidence identifier (evidence_id), as in api/v1/evidence.json.",
        "iso2": "Upper-case ISO 3166-1 alpha-2 country code, as in api/v1/countries.json.",
    }
    paths: dict[str, Any] = {}
    for key, path in _endpoint_paths().items():
        parameters = []
        for name in re.findall(r"\{([a-z0-9_]+)\}", path):
            pattern = "^[A-Z]{2}$" if name == "iso2" else "^" + SAFE_ID.pattern + "$"
            parameters.append({
                "name": name, "in": "path", "required": True, "description": parameter_descriptions[name],
                "schema": {"type": "string", "pattern": pattern}, "example": examples[name],
            })
        target = ENDPOINT_SCHEMAS.get(key)
        if path.endswith(".csv"):
            content = {"text/csv": {"schema": {"type": "string"}}}
        elif key == "openapi":
            content = {"application/json": {"schema": {"type": "object"}}}
        else:
            if isinstance(target, tuple):
                schema: dict[str, Any] = {"type": "array", "items": {"$ref": f"#/components/schemas/{SCHEMA_COMPONENTS[target[1]]}"}}
            else:
                schema = {"$ref": f"#/components/schemas/{SCHEMA_COMPONENTS[target]}"}
            media = "application/geo+json" if path.endswith(".geojson") else "application/json"
            content = {media: {"schema": schema}}
        operation: dict[str, Any] = {
            "operationId": OPERATION_IDS[key],
            "summary": ENDPOINT_DESCRIPTIONS[key],
            "tags": [_endpoint_tag(key)],
            "responses": {"200": {"description": ENDPOINT_DESCRIPTIONS[key], "content": content}},
        }
        if parameters:
            operation["parameters"] = parameters
            operation["responses"]["404"] = {"$ref": "#/components/responses/NotFound"}
        paths["/" + path] = {"get": operation}
    description = "\n\n".join([
        f"{config.tagline}. A static, read-only JSON API served by GitHub Pages: plain files over HTTPS with "
        "no key, no sign-up and CORS enabled. Within v1 changes are additive only.",
        "Read before using:\n" + "\n".join(f"- {caveat}" for caveat in DATA_CAVEATS),
        MEDIA_TYPE_NOTE,
        f"Licences: {config.data_license.get('name')} for Atlas-authored data; geometries derived from "
        f"OpenStreetMap are {ODBL['attribution']} under {ODBL['name']}; other third-party facts keep their "
        f"source terms ({base}about/attribution/). Cite as: {_citations(context)['apa']}",
    ])
    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": JSON_SCHEMA_DIALECT,
        "info": {
            "title": f"{config.site_name} API",
            "summary": f"Static JSON API of {config.title}.",
            "description": description,
            "version": API_VERSION,
            "contact": {"name": str(config.author.get("name", "")), "url": config.issues_url},
            "license": {"name": "CC BY 4.0 (Atlas data) and ODbL 1.0 (OpenStreetMap-derived geometries)",
                        "identifier": f"{config.data_license.get('id', 'CC-BY-4.0')} AND {ODBL['id']}"},
        },
        "externalDocs": {"description": "API guide", "url": f"{base}api/"},
        "servers": [{"url": base.rstrip("/"), "description": "GitHub Pages (static files)"}],
        "tags": [
            {"name": "sites", "description": "Physical sites and their GeoJSON."},
            {"name": "projects", "description": "Construction projects."},
            {"name": "evidence", "description": "Evidence rows."},
            {"name": "countries", "description": "Sites by country."},
            {"name": "metadata", "description": "Index, statistics, versions, vocabularies, citation and contract."},
        ],
        "paths": paths,
        "components": {
            "schemas": {SCHEMA_COMPONENTS[name]: _component_refs(schema) for name, schema in schemas.items()},
            "responses": {"NotFound": {
                "description": "No such record: GitHub Pages answers with its HTML 404 page.",
                "content": {"text/html": {"schema": {"type": "string"}}},
            }},
        },
    }


def _endpoint_tag(key: str) -> str:
    if key.startswith("site"):
        return "sites"
    if key.startswith("project"):
        return "projects"
    if key.startswith("evidence"):
        return "evidence"
    if key.startswith("countr"):
        return "countries"
    return "metadata"


def _write_contract(writer: _Writer, context: _Context) -> None:
    schemas = _json_schemas(context)
    base = context.base_url
    for name, schema in schemas.items():
        writer.write_json(f"api/v1/schemas/{name}.schema.json", schema, pretty=True)
    writer.write_json("api/v1/schemas/index.json", {
        "api_version": API_VERSION,
        "schemas": {name: f"{base}api/v1/schemas/{name}.schema.json" for name in schemas},
        "openapi_url": f"{base}api/v1/openapi.json",
    }, pretty=True)
    writer.write_json("api/v1/openapi.json", _openapi(context, schemas), pretty=True)


# --------------------------------------------------------------------------------------------
# Downloads


def _write_downloads(writer: _Writer, context: _Context) -> _Context:
    """Write every download directory; return the context with their file listings.

    ``downloads/<id>/`` gets the version's originals and ``SHA256SUMS``. Versions from the first
    one published as current up to the current one also get the derived formats and the zip,
    built from that version alone, so the files of a formerly current version stay where they
    were. ``downloads/latest/`` repeats the current version with a stable zip name.
    """
    current = context.current
    directories: dict[str, tuple[DownloadFile, ...]] = {}
    current_derived: dict[str, bytes] = {}
    for version in context.versions:
        directory = f"downloads/{version.id}"
        files = _copy_originals(writer, version, directory)
        if context.has_derived(version):
            atlas = context.atlas if version.id == current.id else load_atlas(version, context.base_url)
            derived = _derived_downloads(context, atlas)
            if version.id == current.id:
                current_derived = derived
            files.update(_write_named(writer, directory, derived))
            zip_name = _zip_name(version)
            files.update(_write_named(writer, directory, {zip_name: _zip_archive(writer, directory, files)}))
        files["SHA256SUMS"] = _write_checksums(writer, directory, files)
        directories[version.id] = _download_listing(version, files)
    latest = f"downloads/{LATEST}"
    files = _copy_originals(writer, current, latest)
    files.update(_write_named(writer, latest, current_derived))
    latest_zip = f"datacenter-atlas-{LATEST}.zip"
    files.update(_write_named(writer, latest, {latest_zip: _zip_archive(writer, latest, files)}))
    files["SHA256SUMS"] = _write_checksums(writer, latest, files)
    directories[LATEST] = _download_listing(current, files)
    return replace(context, downloads=directories[LATEST], download_dirs=directories)


def _download_listing(version: DatasetVersion, files: Mapping[str, tuple[int, str]]) -> tuple[DownloadFile, ...]:
    originals = {record.name for record in version.files}
    return tuple(
        _download_file(name, files[name], derived=name not in originals) for name in _download_display_order(files)
    )


def _copy_originals(writer: _Writer, version: DatasetVersion, directory: str) -> dict[str, tuple[int, str]]:
    files = {}
    for record in version.files:
        name = record.name
        if name in RESERVED_DOWNLOAD_NAMES or (name.startswith("datacenter-atlas-") and name.endswith(".zip")):
            raise PublicSiteError(f"{version.id}/{name}: this name is reserved for a file the site builder writes")
        if name.lower().endswith(ACTIVE_CONTENT_SUFFIXES) and record.sha256 not in REVIEWED_ACTIVE_ORIGINALS:
            raise PublicSiteError(
                f"{version.id}/{name}: an original file a browser would run as active content is published verbatim "
                "on the site's origin without a Content-Security-Policy. Review it (no external resources, no HTML "
                f"sinks for data) and add its SHA-256 {record.sha256} to REVIEWED_ACTIVE_ORIGINALS"
            )
        writer.write_bytes(f"{directory}/{name}", _verified_bytes(version, name))
        files[name] = (record.size, record.sha256)
    return files


def _write_named(writer: _Writer, directory: str, items: Mapping[str, bytes]) -> dict[str, tuple[int, str]]:
    written = {}
    for name, data in items.items():
        writer.write_bytes(f"{directory}/{name}", data)
        written[name] = (len(data), _sha256(data))
    return written


def _zip_archive(writer: _Writer, directory: str, files: Mapping[str, tuple[int, str]]) -> bytes:
    return _deterministic_zip((name, (writer.base / directory / name).read_bytes()) for name in sorted(files))


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


def _download_file(name: str, meta: tuple[int, str], *, derived: bool = False) -> DownloadFile:
    if name in DOWNLOAD_INFO:
        file_format, media_type, description = DOWNLOAD_INFO[name]
    elif name.endswith(".zip"):
        file_format, media_type, description = (
            "ZIP", "application/zip", "Every file listed here except SHA256SUMS, in one archive.",
        )
    else:
        file_format, media_type = EXTENSION_INFO.get(Path(name).suffix, ("File", "application/octet-stream"))
        description = "Original checkpoint file."
    return DownloadFile(name, meta[0], meta[1], file_format, media_type, description, derived)


def _derived_downloads(context: _Context, atlas: Atlas) -> dict[str, bytes]:
    """The derived formats of one version; they depend on that version only, never on which is current."""
    sqlite_bytes = _sqlite_database(context, atlas)
    xlsx_bytes = _xlsx_workbook(context, atlas)
    items = {
        "atlas.json": _json_text({
            "dataset": {
                **_dataset_full(context, atlas),
                "license": _license_block(context),
                "attribution": _attribution_statement(context, atlas.version),
                "caveats": list(DATA_CAVEATS),
            },
            "sites": atlas.sites,
            "projects": atlas.projects,
            "evidence": atlas.evidence,
        }, pretty=True).encode("utf-8"),
        "sites.ndjson": _ndjson(atlas.sites),
        "projects.ndjson": _ndjson(atlas.projects),
        "evidence.ndjson": _ndjson(atlas.evidence),
        "atlas.sqlite": sqlite_bytes,
        "atlas.xlsx": xlsx_bytes,
        "sites.kml": _kml(context, atlas),
    }
    items["datapackage.json"] = _datapackage(context, atlas, {"atlas.sqlite": sqlite_bytes, "atlas.xlsx": xlsx_bytes})
    return dict(sorted(items.items()))


def _ndjson(records: Iterable[Any]) -> bytes:
    return "".join(_json_text(record) for record in records).encode("utf-8")


# SQLite ------------------------------------------------------------------------------------


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


SQLITE_PAGE_SIZE = 4096
# Typed observation arrays of projects.csv that get their own table: (JSON field, table).
SQLITE_OBSERVATION_TABLES = (
    ("power_observations", "power_observations"),
    ("efficiency_observations", "efficiency_observations"),
    ("annual_energy_observations", "annual_energy_observations"),
)
SQLITE_TABLE_NOTES = {
    "sites": "One row per physical site; the columns of sites.csv.",
    "projects": "One row per construction project; the columns of projects.csv.",
    "evidence": "One row per evidence item; the columns of evidence.csv.",
    "project_evidence": "Which evidence rows support which project (from evidence.project_ids_json).",
    "evidence_roles": "The roles each evidence row plays (from evidence.roles_json).",
    "power_observations": "Typed power observations (projects.power_observations_json), one row per array item.",
    "efficiency_observations": "Typed efficiency observations such as PUE (projects.efficiency_observations_json).",
    "annual_energy_observations": "Typed annual-energy observations (projects.annual_energy_observations_json).",
    "role_claims": "Evidence-linked owner, operator, customer, tenant or user claims (projects.role_claims_json).",
    "workload_observations": "Evidence-linked workload observations (projects.workloads_json).",
    "site_overview": "View: one row per site with name, country, location, statuses and newest status date.",
}


def _sqlite_database(context: _Context, atlas: Atlas) -> bytes:
    """atlas.sqlite of one version, written so that its bytes depend only on the data.

    ``secure_delete`` zeroes freed space (Debian and Ubuntu compile SQLite with it on, macOS
    does not), the page size is fixed and the writer-version header field is zeroed.
    """
    with tempfile.TemporaryDirectory(prefix="atlas-sqlite-") as directory:
        path = Path(directory) / "atlas.sqlite"
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute(f"PRAGMA page_size = {SQLITE_PAGE_SIZE}")
            connection.execute("PRAGMA foreign_keys = ON")
            _sqlite_schema(connection, atlas)
            _sqlite_rows(connection, context, atlas)
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


def _sqlite_foreign_keys(atlas: Atlas) -> dict[str, list[tuple[str, str, str]]]:
    keys: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    declared = atlas.schema.get("foreign_keys") or []
    for item in declared if isinstance(declared, list) else []:
        source, target = (item.get("from"), item.get("to")) if isinstance(item, dict) else (None, None)
        if not (isinstance(source, list) and isinstance(target, list) and len(source) == 2 and len(target) == 2):
            continue
        if source[0] in TABLE_NAMES and target[0] in TABLE_NAMES:
            keys[TABLE_NAMES[source[0]]].append((source[1], TABLE_NAMES[target[0]], target[1]))
    if ("site_id", "sites", "site_id") not in keys["projects"]:
        keys["projects"].insert(0, ("site_id", "sites", "site_id"))
    return keys


def _sqlite_observation_table(table: str) -> str:
    return f"""
CREATE TABLE "{table}" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "ordinal" INTEGER NOT NULL,
  "metric" TEXT, "stage" TEXT, "low" REAL, "base" REAL, "high" REAL, "unit" TEXT,
  "as_of_date" TEXT, "target_date" TEXT, "method" TEXT, "confidence" REAL,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id"),
  "notes" TEXT,
  PRIMARY KEY ("project_id", "ordinal")
);"""


def _sqlite_schema(connection: sqlite3.Connection, atlas: Atlas) -> None:
    foreign = _sqlite_foreign_keys(atlas)
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
    observation_tables = "".join(_sqlite_observation_table(table) for _, table in SQLITE_OBSERVATION_TABLES)
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
);"""
        + observation_tables
        + """
CREATE TABLE "role_claims" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "ordinal" INTEGER NOT NULL,
  "role" TEXT, "party" TEXT, "relationship_scope" TEXT,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id"),
  PRIMARY KEY ("project_id", "ordinal")
);
CREATE TABLE "workload_observations" (
  "project_id" TEXT NOT NULL REFERENCES "projects" ("project_id"),
  "ordinal" INTEGER NOT NULL,
  "workload" TEXT, "deployment_scope" TEXT, "method" TEXT, "confidence" REAL, "as_of_date" TEXT,
  "evidence_id" TEXT REFERENCES "evidence" ("evidence_id"),
  PRIMARY KEY ("project_id", "ordinal")
);
CREATE TABLE "metadata" ("key" TEXT PRIMARY KEY, "value" TEXT);
CREATE VIEW "site_overview" AS
  SELECT "site_id", "name", "country", "country_iso_a2", "latitude", "longitude",
         "statuses_json", "newest_status_as_of", "project_count"
  FROM "sites";
"""
    )
    indexes.append(("project_evidence", "evidence_id"))
    for table in (*(table for _, table in SQLITE_OBSERVATION_TABLES), "role_claims", "workload_observations"):
        indexes.append((table, "evidence_id"))
    for table, column in indexes:
        name = _quote_identifier(f"idx_{table}_{column}")
        connection.execute(
            f"CREATE INDEX {name} ON {_quote_identifier(table)} ({_quote_identifier(column)})"
        )


def _sqlite_rows(connection: sqlite3.Connection, context: _Context, atlas: Atlas) -> None:
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
    observations: dict[str, list[tuple[Any, ...]]] = {table: [] for _, table in SQLITE_OBSERVATION_TABLES}
    claims, workloads = [], []
    for project in atlas.projects:
        project_id = project["project_id"]
        for key, table in SQLITE_OBSERVATION_TABLES:
            for ordinal, item in enumerate(_dict_items(project.get(key))):
                observations[table].append((project_id, ordinal, *(item.get(name) for name in OBSERVATION_COLUMNS)))
        for ordinal, item in enumerate(_dict_items(project.get("role_claims"))):
            claims.append((project_id, ordinal, *(item.get(key) for key in ("role", "party", "relationship_scope", "evidence_id"))))
        for ordinal, item in enumerate(_dict_items(project.get("workloads"))):
            workloads.append((project_id, ordinal, *(item.get(key) for key in (
                "workload", "deployment_scope", "method", "confidence", "as_of_date", "evidence_id",
            ))))
    width = 2 + len(OBSERVATION_COLUMNS)
    for table, rows in observations.items():
        connection.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" * width)})', [_sql_row(row) for row in rows])
    connection.executemany('INSERT INTO "role_claims" VALUES (?, ?, ?, ?, ?, ?)', [_sql_row(row) for row in claims])
    connection.executemany('INSERT INTO "workload_observations" VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [_sql_row(row) for row in workloads])
    connection.executemany('INSERT INTO "metadata" VALUES (?, ?)', _sqlite_metadata(context, atlas))


def _sql_row(row: Sequence[Any]) -> tuple[Any, ...]:
    """Embedded JSON values bound as SQL parameters: scalars as they are, anything else as JSON text."""
    return tuple(
        value if value is None or isinstance(value, (str, int, float)) else _json_text(value).rstrip("\n")
        for value in row
    )


def _sqlite_metadata(context: _Context, atlas: Atlas) -> list[tuple[str, str]]:
    version, config = atlas.version, context.config
    rows = [
        ("dataset_id", version.id),
        ("dataset_label", version.label),
        ("dataset_title", config.title),
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
        ("odbl_license", ODBL["id"]),
        ("odbl_license_url", ODBL["url"]),
        ("odbl_attribution", f"{ODBL['attribution']} ({ODBL['attribution_url']})"),
        ("odbl_scope", ODBL["scope"]),
        ("attribution", "Third-party facts and geometries keep their source terms; see ATTRIBUTION.txt and evidence.license."),
        ("attribution_url", f"{context.base_url}about/attribution/"),
        ("citation", _citations(context, version)["apa"]),
        ("api_version", API_VERSION),
        ("schema_note", (
            "Tables sites, projects and evidence keep the CSV column names; empty CSV values are NULL; "
            "booleans are 0/1; *_json columns hold JSON text. Observation and claim tables keep each "
            "array item's position in 'ordinal' (0-based)."
        )),
        ("semantics", (
            "Statuses are the last observed physical status as of status_as_of, not the current status; "
            "locators are not footprints; NULL means unknown, never zero; a reviewed preview, not a census."
        )),
    ]
    rows += [(f"table:{name}", note) for name, note in SQLITE_TABLE_NOTES.items()]
    return rows


# Excel -------------------------------------------------------------------------------------

XLSX_CELL_LIMIT = 32767
XLSX_TRUNCATION_MARK = " … [truncated: see the CSV file for the full value]"
XLSX_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XLSX_WORKSHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
# Columns too large or structural for a spreadsheet cell; every table links to the full record instead.
XLSX_OMITTED_COLUMNS = frozenset({"geometry_json"})


def _xlsx_workbook(context: _Context, atlas: Atlas) -> bytes:
    """atlas.xlsx: a README sheet plus one sheet per table, written with the standard library only.

    Numbers stay numbers, booleans become TRUE/FALSE, unknown values are empty cells (never 0),
    every text is an inline string (so no cell is ever evaluated as a formula) and cells longer
    than Excel's 32,767-character limit are truncated with a marker. The zip entries carry a
    fixed timestamp, so the bytes depend only on the data.
    """
    base = context.base_url
    sheets: list[tuple[str, list[list[Any]]]] = [("README", _xlsx_readme_rows(context, atlas))]
    extras = {
        "sites.csv": (
            ("url", lambda record: record["url"]),
            ("api_url", lambda record: record["api_url"]),
            ("geojson_url", lambda record: f"{base}api/v1/sites/{record['site_id']}.geojson"),
            ("geometry_licenses", lambda record: "; ".join(record.get("geometry_licenses") or [])),
        ),
        "projects.csv": (
            ("url", lambda record: record["url"]),
            ("api_url", lambda record: record["api_url"]),
        ),
        "evidence.csv": (
            ("api_url", lambda record: record["api_url"]),
            ("archive_url", lambda record: record.get("archive_url")),
        ),
    }
    for file_name in TABLE_FILES:
        fields = [spec for spec in atlas.fields[file_name] if spec["name"] not in XLSX_OMITTED_COLUMNS]
        records = {"sites.csv": atlas.sites, "projects.csv": atlas.projects, "evidence.csv": atlas.evidence}[file_name]
        header = [spec["name"] for spec in fields] + [name for name, _ in extras[file_name]]
        rows: list[list[Any]] = [header]
        for raw, record in zip(atlas.raw[file_name], records, strict=True):
            row = [_xlsx_value(raw[spec["name"]], str(spec.get("logical_type", "string")), spec["name"]) for spec in fields]
            row += [function(record) for _, function in extras[file_name]]
            rows.append(row)
        sheets.append((TABLE_NAMES[file_name], rows))
    return _xlsx_package(sheets)


def _xlsx_value(value: str, logical_type: str, field_name: str) -> Any:
    if value == "":
        return None
    if logical_type in {"number", "integer", "boolean"}:
        return convert_value(value, logical_type, field_name=field_name)
    return value


def _xlsx_readme_rows(context: _Context, atlas: Atlas) -> list[list[Any]]:
    config, version = context.config, atlas.version
    base = context.base_url
    counts = atlas.counts
    window = _window_start(config, version)
    rows: list[list[Any]] = [
        ["Data Center Atlas workbook", ""],
        ["Dataset", config.title],
        ["Updated", version.checkpoint_date],
        ["Status window", f"{window} to {version.lifecycle_reference_date}"],
        ["Sites", counts.get("physical_sites")],
        ["Projects", counts.get("projects")],
        ["Countries", counts.get("countries")],
        ["Evidence rows", counts.get("evidence")],
        ["", ""],
        ["Read before using", ""],
    ]
    rows += [["", caveat] for caveat in DATA_CAVEATS]
    rows += [
        ["", ""],
        ["Sheets", "sites, projects and evidence hold the CSV columns (geometry_json is omitted: use the GeoJSON "
                   "link in each row), followed by link columns added by the site builder."],
        ["Cells", "Empty cells are unknown values, never zero. *_json columns hold JSON text. A cell longer than "
                  "Excel's limit ends with a truncation note; the CSV files hold the full value."],
        ["Licence", f"{config.data_license.get('name')} ({config.data_license.get('url')}) for Atlas-authored data. "
                    f"Geometries derived from OpenStreetMap: {ODBL['attribution']}, {ODBL['id']} ({ODBL['url']}). "
                    "Other third-party facts and geometries keep their source terms: see each evidence row and "
                    f"{base}about/attribution/"],
        ["Cite as", _citations(context, version)["apa"]],
        ["Field dictionary", f"{base}data/dictionary/"],
        ["Downloads", f"{base}downloads/{version.id}/"],
        ["API", f"{base}api/"],
    ]
    return rows


def _xlsx_column(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xlsx_cell(reference: str, value: Any, *, header: bool = False) -> str:
    style = ' s="1"' if header else ""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return f'<c r="{reference}"{style} t="b"><v>{1 if value else 0}</v></c>'
    if _is_number(value):
        return f'<c r="{reference}"{style}><v>{_number_text(value)}</v></c>'
    text = XML_INVALID.sub("�", str(value))
    if len(text) > XLSX_CELL_LIMIT:
        text = text[: XLSX_CELL_LIMIT - len(XLSX_TRUNCATION_MARK)] + XLSX_TRUNCATION_MARK
    escaped = html.escape(text, quote=False)
    return f'<c r="{reference}"{style} t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'


def _xlsx_sheet(rows: Sequence[Sequence[Any]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{XLSX_MAIN}">',
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
        'state="frozen"/></sheetView></sheetViews>',
        "<sheetData>",
    ]
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(f"{_xlsx_column(column)}{row_index}", value, header=row_index == 1)
            for column, value in enumerate(row)
        )
        parts.append(f'<row r="{row_index}">{cells}</row>')
    parts += ["</sheetData>", "</worksheet>"]
    return "".join(parts)


def _xlsx_package(sheets: Sequence[tuple[str, Sequence[Sequence[Any]]]]) -> bytes:
    count = len(sheets)
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="{XLSX_WORKSHEET_TYPE}"/>'
        for index in range(1, count + 1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{overrides}</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{XLSX_PACKAGE_REL}">'
        f'<Relationship Id="rId1" Type="{XLSX_REL}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{XLSX_MAIN}" xmlns:r="{XLSX_REL}"><sheets>'
        + "".join(
            f'<sheet name="{_x(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _) in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{XLSX_PACKAGE_REL}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="{XLSX_REL}/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, count + 1)
        )
        + f'<Relationship Id="rId{count + 1}" Type="{XLSX_REL}/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{XLSX_MAIN}">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    parts = [
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", root_rels),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", workbook_rels),
        ("xl/styles.xml", styles),
    ]
    parts += [(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet(rows)) for index, (_, rows) in enumerate(sheets, start=1)]
    return _deterministic_zip((name, text.encode("utf-8")) for name, text in parts)


def _deterministic_zip(members: Iterable[tuple[str, bytes]]) -> bytes:
    """A deflated zip whose bytes depend only on the member names, order and contents."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    return buffer.getvalue()


# KML ---------------------------------------------------------------------------------------

KML_STYLE_ID = "atlas-site"
# KML colours are aabbggrr: an opaque orange outline (#ff7f0e) and a 25 % fill, visible on imagery.
KML_LINE_COLOR = "ff0e7fff"
KML_FILL_COLOR = "400e7fff"


def _kml(context: _Context, atlas: Atlas) -> bytes:
    version = atlas.version
    title = f"{context.config.site_name} — {version.label}"
    description = (
        f"<p>{_e(version.label)} (checkpoint {_e(version.checkpoint_date)}). "
        "Statuses are the last observed physical status on the status date, not today; locators are not "
        "footprints; empty values are unknown. Each polygon site also has a point at its display anchor.</p>"
        f"<p>Atlas data: {_e(context.config.data_license.get('id'))} ({_e(context.config.data_license.get('url'))}). "
        f"Includes geometries {_e(ODBL['attribution'])}, {_e(ODBL['id'])} ({_e(ODBL['url'])}). "
        f"Other source terms: {_e(context.base_url)}about/attribution/</p>"
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        f"<name>{_x(title)}</name>",
        f"<description>{_x(description)}</description>",
        f'<Style id="{KML_STYLE_ID}">'
        "<IconStyle><scale>1.0</scale></IconStyle>"
        f"<LineStyle><color>{KML_LINE_COLOR}</color><width>2</width></LineStyle>"
        f"<PolyStyle><color>{KML_FILL_COLOR}</color><fill>1</fill><outline>1</outline></PolyStyle>"
        "</Style>",
    ]
    for summary in atlas.summaries:
        lines.extend(_kml_placemark(context, atlas, summary))
    lines += ["</Document>", "</kml>"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _kml_placemark(context: _Context, atlas: Atlas, summary: Mapping[str, Any]) -> list[str]:
    site = atlas.site_by_id[summary["site_id"]]
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
        ("geometry_licenses", ";".join(summary.get("geometry_licenses") or [])),
        ("url", summary["url"]),
    )
    return [
        f'<Placemark id="{_x("site-" + summary["site_id"])}">',
        f"<name>{_x(summary.get('name'))}</name>",
        f"<description>{_x(description)}</description>",
        f"<styleUrl>#{KML_STYLE_ID}</styleUrl>",
        "<ExtendedData>",
        *(f'<Data name="{_x(name)}"><value>{_x(value)}</value></Data>' for name, value in data),
        "</ExtendedData>",
        _kml_geometry(site["geometry"], summary["site_id"], (site["longitude"], site["latitude"])),
        "</Placemark>",
    ]


def _kml_geometry(geometry: Mapping[str, Any], site_id: str, anchor: tuple[Any, Any]) -> str:
    """KML geometry; polygons are wrapped with a Point at the display anchor so they show at every zoom."""
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Point":
        return f"<Point><coordinates>{_kml_position(coordinates, site_id)}</coordinates></Point>"
    point = f"<Point><coordinates>{_kml_position(list(anchor), site_id)}</coordinates></Point>"
    if kind == "Polygon":
        return f"<MultiGeometry>{point}{_kml_polygon(coordinates, site_id)}</MultiGeometry>"
    if kind == "MultiPolygon" and isinstance(coordinates, list):
        return "<MultiGeometry>" + point + "".join(_kml_polygon(polygon, site_id) for polygon in coordinates) + "</MultiGeometry>"
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


def _package_licenses(context: _Context) -> list[dict[str, str]]:
    license_info = context.config.data_license
    return [
        {
            "name": str(license_info.get("id", "")),
            "path": str(license_info.get("url", "")),
            "title": f"{license_info.get('name', '')}: Atlas-authored data and structure (see DATA_LICENSE.md)",
        },
        {
            "name": ODBL["id"],
            "path": ODBL["url"],
            "title": f"{ODBL['name']}: geometries derived from OpenStreetMap ({ODBL['attribution']})",
        },
    ]


def _datapackage(context: _Context, atlas: Atlas, blobs: Mapping[str, bytes]) -> bytes:
    config, version = context.config, atlas.version
    files = {record.name: record for record in version.files}
    licenses = _package_licenses(context)
    resources = [
        _table_resource(context, atlas, file_name, files[file_name], licenses)
        for file_name in TABLE_FILES if file_name in files
    ]
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
            "licenses": licenses,
        })
    derived = (
        ("atlas-sqlite", "atlas.sqlite", "SQLite database of the checkpoint", "sqlite", "application/vnd.sqlite3"),
        ("atlas-xlsx", "atlas.xlsx", "Excel workbook of the checkpoint (geometry omitted)", "xlsx", XLSX_MEDIA_TYPE),
    )
    for name, path, title, file_format, media_type in derived:
        if path not in blobs:
            continue
        data = blobs[path]
        resource = {
            "name": name,
            "path": path,
            "profile": "data-resource",
            "title": title,
            "format": file_format,
            "mediatype": media_type,
            "bytes": len(data),
            "hash": f"sha256:{_sha256(data)}",
        }
        if path == "atlas.sqlite":
            resource["licenses"] = licenses
        resources.append(resource)
    package = {
        "profile": "data-package",
        "name": "datacenter-atlas",
        "title": f"{config.title} — {version.label}",
        "description": (
            f"{config.tagline}. {version.label}, checkpoint {version.checkpoint_date}, "
            f"lifecycle reference date {version.lifecycle_reference_date}. "
            f"Release status: {version.release_status}; not a final release unless publishable_as_final is true. "
            "Statuses are the last observed physical status on the status date, not the current status; "
            "locators are not footprints; empty values are unknown, never zero; a reviewed preview, not a census."
        ),
        "version": version.id,
        "homepage": context.base_url,
        "keywords": list(DATASET_KEYWORDS),
        "licenses": licenses,
        "sources": [
            {"title": f"{config.site_name} repository: {config.versions_root}/{version.id}", "path": _tree_url(context, version)},
            {"title": "Per-row third-party sources and terms (see evidence.csv and ATTRIBUTION.txt)", "path": "ATTRIBUTION.txt"},
            {"title": f"OpenStreetMap contributors ({ODBL['id']})", "path": ODBL["attribution_url"]},
        ],
        "contributors": [{
            "title": str(config.author.get("name", "")),
            "path": str(config.author.get("url", "")),
            "role": "author",
        }],
        "resources": resources,
    }
    return _json_text(package, pretty=True).encode("utf-8")


def _table_resource(
    context: _Context, atlas: Atlas, file_name: str, record: FileRecord, licenses: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
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
        constraints: dict[str, Any] = {}
        if spec.get("allows_empty_string") is False:
            constraints["required"] = True
        allowed = spec.get("allowed_values")
        if isinstance(allowed, list) and allowed and field_type in {"string", "boolean", "integer", "number"}:
            constraints["enum"] = list(allowed)
        if constraints:
            item["constraints"] = constraints
        fields.append(item)
    schema: dict[str, Any] = {"fields": fields}
    primary = atlas.schema["tables"][file_name].get("primary_key")
    if primary:
        schema["primaryKey"] = list(primary)
    foreign = [
        {"fields": [column], "reference": {"resource": target_table, "fields": [target_column]}}
        for column, target_table, target_column in _sqlite_foreign_keys(atlas).get(table, [])
    ]
    if foreign:
        schema["foreignKeys"] = foreign
    schema["missingValues"] = [""]
    resource = {
        "name": table,
        "path": file_name,
        "profile": "tabular-data-resource",
        "title": f"{file_name} of {atlas.version.id}",
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": "utf-8",
        "bytes": record.size,
        "hash": f"sha256:{record.sha256}",
        "dialect": {"delimiter": ",", "lineTerminator": "\n", "quoteChar": "\"", "doubleQuote": True, "header": True},
        "schema": schema,
    }
    if file_name in {"sites.csv", "projects.csv"}:
        resource["licenses"] = list(licenses)
    return resource


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
    if reason:
        return f'<details><summary>Not reported</summary><p class="small muted">{_e(reason)}</p></details>'
    return '<span class="muted">Not reported</span>'


def _copy_button(text: str, label: str = "Copy", aria_label: str | None = None) -> str:
    """A copy button; ``aria_label`` names what it copies and starts with the visible label (WCAG 2.5.3)."""
    name = f' aria-label="{_e(aria_label)}"' if aria_label else ""
    return (
        f'<button type="button" class="btn btn-small copy-btn hidden-noscript" data-copy="{_e(text)}"{name}>'
        f"{_e(label)}</button>"
    )


def _code_block(code: str, *, copy: bool = True, title: str | None = None) -> str:
    button = _copy_button(code, "Copy code", f"Copy code: {title}" if title else None) if copy else ""
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


def _methodology_link(context: _Context, anchor: str) -> str:
    """methodology/#<anchor> when site/content/methodology.html has that id, else methodology/."""
    text = _load_fragment(context, "content/methodology.html")
    return f"methodology/#{anchor}" if f'id="{anchor}"' in text else "methodology/"


def _token_values(context: _Context, root: str) -> tuple[dict[str, str], dict[str, str]]:
    config, current, preview = context.config, context.current, context.last_preview
    citations = _citations(context)
    text = {
        "root": root,
        "site_name": config.site_name,
        "tagline": config.tagline,
        "base_url": context.base_url,
        "repository_url": config.repository_url,
        "issues_url": config.issues_url,
        "dataset.id": current.id,
        "dataset.label": current.label,
        "dataset.title": config.title,
        "dataset.release_status": current.release_status,
        "dataset.checkpoint_date": current.checkpoint_date,
        "dataset.checkpoint_year": current.checkpoint_date[:4],
        "dataset.lifecycle_reference_date": current.lifecycle_reference_date,
        "dataset.status_window_days": str(config.status_window_days),
        "dataset.window_start": context.window_start,
        "last_preview.label": preview.label,
        "versions.count": str(len(context.versions)),
        "build.commit_short": context.commit_short,
        "citation.apa": citations["apa"],
        "citation.bibtex": citations["bibtex"],
    }
    text.update({f"counts.{key}": str(value) for key, value in context.atlas.counts.items()})
    text.update({f"last_preview.counts.{key}": str(value) for key, value in preview.counts.items()})
    markup = {
        "gates_table": _gates_table(context),
        "status_legend": _status_legend(context),
        "citation_block": _citation_html(context, root, citations),
        "legal_notice": context.legal_notice_html,
    }
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
    # Extra <link> elements in <head>: (rel, media type, path relative to the site root).
    head_links: tuple[tuple[str, str, str], ...] = ()


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
        # Pages left out of the sitemap (the 404 page) are not for search results either.
        *(() if page.in_sitemap else ('<meta name="robots" content="noindex">',)),
        f'<link rel="canonical" href="{_e(canonical)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{_e(title)}">',
        f'<meta property="og:description" content="{_e(page.description)}">',
        f'<meta property="og:url" content="{_e(canonical)}">',
        f'<meta property="og:site_name" content="{_e(config.site_name)}">',
        *_og_image_meta(context),
        f'<meta http-equiv="Content-Security-Policy" content="{CONTENT_SECURITY_POLICY}">',
        '<meta name="color-scheme" content="light dark">',
        f'<link rel="icon" href="{_e(_asset_url(context, root, FAVICON))}" type="image/svg+xml">',
        *(f'<link rel="stylesheet" href="{_e(_asset_url(context, root, style))}">' for style in page.styles),
        f'<link rel="stylesheet" href="{_e(_asset_url(context, root, SITE_CSS))}">',
        f'<link rel="alternate" type="application/atom+xml" title="{_e(FEED_TITLE)}" href="{_e(root)}feed.xml">',
        f'<link rel="alternate" type="application/atom+xml" title="{_e(SITES_FEED_TITLE)}" href="{_e(root)}sites-feed.xml">',
        *(
            f'<link rel="{_e(rel)}" type="{_e(media_type)}" href="{_e(root + path)}">'
            for rel, media_type, path in page.head_links
        ),
    ]
    if page.json_ld is not None:
        head.append(f'<script type="application/ld+json">{_script_json(page.json_ld)}</script>')
    head.append("</head>")
    body = [
        f'<body class="page-{_class_token(page.slug).replace("_", "-")}">',
        '<a class="skip-link" href="#main">Skip to content</a>',
        _render_header(context, root, page.section),
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


def _og_image_meta(context: _Context) -> list[str]:
    if context.og_image_size is None:
        return ['<meta name="twitter:card" content="summary">']
    width, height = context.og_image_size
    url = context.base_url + OG_IMAGE
    return [
        f'<meta property="og:image" content="{_e(url)}">',
        f'<meta property="og:image:width" content="{width}">',
        f'<meta property="og:image:height" content="{height}">',
        f'<meta property="og:image:alt" content="{_e(OG_IMAGE_ALT)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{_e(url)}">',
    ]


def _render_footer(context: _Context, root: str) -> str:
    config = context.config
    data_license = str(config.data_license.get("id", "")).replace("-", " ")
    code_license = str(config.code_license.get("id", "")).replace("-", " ")
    if context.commit:
        commit_url = f"{config.repository_url}/commit/{context.commit}"
        built = f'<a class="external" rel="noopener" href="{_e(commit_url)}"><code>{_e(context.commit_short)}</code></a>'
    else:
        built = f"<code>{_e(context.commit_short)}</code>"
    data_link = _external_link(config.data_license.get("url"), data_license)
    if _safe_http_url(config.data_license.get("url")):
        data_link = data_link.replace('rel="noopener"', 'rel="noopener license"', 1)
    code_link = _external_link(f"{config.repository_url}/blob/main/LICENSE", code_license)
    return (
        '<footer class="site-footer">\n'
        f"  <p>Data: {data_link} for Atlas-authored content; geometries from OpenStreetMap © "
        f'{_external_link(OSM_COPYRIGHT_URL, "OpenStreetMap contributors")}, {_external_link(ODBL["url"], "ODbL 1.0")}; '
        "other third-party facts and geometries keep their source terms "
        f'(<a href="{_e(root)}about/attribution/">attribution</a> &amp; '
        f'<a href="{_e(root)}about/attribution/#legal-notice">legal notices</a>). Code: {code_link}.</p>\n'
        f'  <p><a class="external" rel="noopener" href="{_e(config.repository_url)}">Source on GitHub</a> · '
        f'<a href="{_e(root)}methodology/">Methodology</a> · <a href="{_e(root)}api/">API</a> · '
        f'<a href="{_e(root)}versions/">Data history</a> · <a href="{_e(root)}feed.xml">Updates</a> · '
        f"Updated {_e(context.current.checkpoint_date)} · {built}</p>\n"
        "</footer>"
    )


def _write_page(writer: _Writer, context: _Context, page: _Page) -> None:
    writer.write_text(page.path, _render_page(context, page))
    if page.in_sitemap:
        writer.pages.append(page.path)


# --------------------------------------------------------------------------------------------
# JSON-LD


def _dataset_json_ld(context: _Context) -> dict[str, Any]:
    """The schema.org Dataset of the current version, published once, on the data page."""
    config, current = context.config, context.current
    base = context.base_url
    counts = context.atlas.counts
    data_url = f"{base}data/"
    descriptions = context.descriptions.get("tables", {})
    variables = [
        ("last_observed_physical_status", "projects.csv", None),
        ("status_as_of", "projects.csv", None),
        ("geometry_json", "sites.csv", None),
        ("geometry_use_scope", "projects.csv", None),
        ("power_observations_json", "projects.csv", "MW"),
    ]
    variable_measured = []
    for name, table, unit in variables:
        description = str(descriptions.get(table, {}).get(name, ""))
        if not description:
            continue
        item: dict[str, Any] = {"@type": "PropertyValue", "name": name, "description": description}
        if unit:
            item["unitText"] = unit
        variable_measured.append(item)
    document: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "@id": f"{data_url}#dataset",
        "name": config.title,
        "alternateName": [current.label, f"{config.site_name}: {current.label}"],
        "description": (
            f"{config.tagline}. Evidence-linked records of {counts.get('physical_sites')} physical data-centre sites "
            f"and {counts.get('projects')} construction projects in {counts.get('countries')} countries, each with a "
            "dated last observed physical status from an authoritative source and a reviewed locator. "
            "Statuses describe their "
            "status date, not today; locators are not footprints; empty values are unknown."
        ),
        "url": data_url,
        "sameAs": config.repository_url,
        "identifier": current.id,
        "version": current.id,
        "isAccessibleForFree": True,
        "license": [str(config.data_license.get("url", "")), ODBL["url"]],
        "usageInfo": f"{base}about/attribution/",
        "creditText": (
            f"{config.site_name} ({config.author.get('name', '')}); includes data {ODBL['attribution']} ({ODBL['id']})"
        ),
        "creator": {
            "@type": "Person",
            "name": str(config.author.get("name", "")),
            "url": str(config.author.get("url", "")),
            "sameAs": str(config.author.get("url", "")),
        },
        "keywords": list(DATASET_KEYWORDS),
        "temporalCoverage": f"{context.window_start}/{current.lifecycle_reference_date}",
        "datePublished": context.versions[0].checkpoint_date,
        "dateModified": current.checkpoint_date,
        "measurementTechnique": (
            "Review of dated authoritative sources (company disclosures, government records and filings) for "
            "physical construction status, with reviewed locators; no independent imagery verification."
        ),
        "variableMeasured": variable_measured,
        "citation": _citations(context)["apa"],
        "includedInDataCatalog": {"@type": "DataCatalog", "name": f"{config.site_name} versions", "url": f"{base}versions/"},
        "distribution": [
            {
                "@type": "DataDownload",
                "name": item.name,
                "encodingFormat": item.media_type,
                "contentUrl": f"{base}downloads/{LATEST}/{item.name}",
                "contentSize": f"{item.size} B",
            }
            for item in context.downloads
        ],
    }
    box = _bounding_box(context.atlas)
    if box is not None:
        document["spatialCoverage"] = {
            "@type": "Place",
            "name": f"{len(context.atlas.countries)} countries and territories",
            "geo": {"@type": "GeoShape", "box": " ".join(_number_text(value) for value in box)},
            "containsPlace": [{"@type": "Country", "name": country["country"]} for country in context.atlas.countries],
        }
    return document


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
    for version in context.versions:
        _write_page(writer, context, _version_page(context, version))
    _write_page(writer, context, _downloads_index_page(context))
    for directory in [*(version.id for version in context.versions), LATEST]:
        _write_page(writer, context, _download_directory_page(context, directory))
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
        json_ld=_website_json_ld(context),
        data_blocks=(("atlas-bootstrap", _bootstrap(context)),),
        head_links=(
            ("alternate", "application/geo+json", "api/v1/sites.geojson"),
            ("alternate", "application/json", "api/v1/index.json"),
            ("service-desc", "application/openapi+json", "api/v1/openapi.json"),
        ),
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
            "versions": "versions/",
            "downloads": "downloads/",
            "attribution": "about/attribution/",
        },
        "license": _license_block(context),
        "attribution": _attribution_statement(context),
        "attribution_url": f"{context.base_url}about/attribution/",
        "citation": _citations(context)["apa"],
        "caveats": list(DATA_CAVEATS),
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
            f"<td>{_time(summary.get('newest_status_as_of'))}</td>"
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
        f'<p class="lede">Browse {len(atlas.summaries)} data-centre sites by name, country and construction stage.</p>\n'
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
        f'<a class="btn" href="{root}#site={_e(quote(site_id, safe=""))}">Show on the map explorer</a>',
        f'<a class="btn" href="{root}api/v1/sites/{_e(site_id)}.json">JSON for this site</a>',
        f'<a class="btn" href="{root}api/v1/sites/{_e(site_id)}.geojson">GeoJSON for this site</a>',
        f'<a class="btn" href="{root}data/">Download dataset</a>',
        _external_link(_correction_url(context, site), "Report a correction", classes="btn btn-primary"),
    ])
    evidence_rows = atlas.evidence_by_site[site_id]
    notices = []
    if any(row.get("publisher") in LEGAL_NOTICE_PUBLISHERS for row in evidence_rows):
        notices.append(_legal_notice_callout(context))
    notices.append(_license_statements_html(_license_statements(row.get("license") for row in evidence_rows)))
    citation = _site_citation(context, site)
    body = "\n".join([
        _breadcrumbs(root, (("sites/", "Sites"), (f"countries/{slug}/", str(site.get("country")))), str(site.get("name"))),
        f"<h1>{_e(site.get('name'))}</h1>",
        f"<p>{_badges(vocabulary, statuses)}{boundary_tag}</p>",
        f'<p class="lede">{_e(site.get("country"))} · {len(projects)} {noun} · '
        f'Last reported {_time(site.get("newest_status_as_of"))}</p>',
        '<div class="grid-2">',
        '<section aria-labelledby="summary-heading"><h2 id="summary-heading">Summary</h2>'
        f"{_site_summary_kv(context, site, coordinates, root)}</section>",
        '<section aria-labelledby="location-heading"><h2 id="location-heading">Location</h2>'
        f"{_site_location(site, latitude, longitude, coordinates)}</section>",
        "</div>",
        f'<section aria-labelledby="projects-heading"><h2 id="projects-heading">Projects ({len(projects)})</h2>',
        *(_project_section(context, project, anchors) for project in projects),
        "</section>",
        '<details id="locator"><summary>Location details</summary>'
        f"{_locator_section(context, site, anchors)}</details>",
        '<section id="evidence" aria-labelledby="evidence-heading"><h2 id="evidence-heading">Evidence</h2>'
        f"{_evidence_table(context, site)}{''.join(notices)}</section>",
        '<details id="cite"><summary>Cite this site</summary>'
        f'<p>{_e(citation.split("Source files:", 1)[0])}</p>'
        f'<p>{_copy_button(citation, "Copy citation", "Copy citation for this site")}</p></details>',
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
        json_ld=_place_json_ld(context, site),
        data_blocks=(("site-geometry", _feature(summary, site["geometry"])),),
        head_links=(
            ("alternate", "application/json", f"api/v1/sites/{site_id}.json"),
            ("alternate", "application/geo+json", f"api/v1/sites/{site_id}.geojson"),
        ),
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
    licenses = ", ".join(_license_link(code) for code in site.get("geometry_licenses") or [])
    precision = " ".join(str(value) for value in site.get("geometry_precision_scopes") or [] if value)
    if "host_estate_context" in (site.get("geometry_use_scopes") or []):
        precision = "Surrounding industrial estate; the project's position within it is not established."
    return _kv([
        ("Country", country),
        ("Coordinates", f'<span class="mono">{_e(coordinates)}</span> '
                        f'{_copy_button(coordinates, "Copy", f"Copy coordinates {coordinates}")}'),
        ("Geometry type", _e(site.get("geometry_type"))),
        ("Locator scope", _e(scopes) or _muted_unknown(None)),
        ("Location precision", _e(precision) or _muted_unknown(None)),
        ("Geometry licence", licenses or _muted_unknown(None)),
        ("Source checks", f'<details><summary>Review details</summary>{posture_html}'
         f'<p>Independent imagery verification: {_e(imagery_text)}</p></details>'),
        ("Newest status as of", _time(site.get("newest_status_as_of")) or _muted_unknown(None)),
        ("Oldest status as of", _time(site.get("oldest_status_as_of")) or _muted_unknown(None)),
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
        ("Operating model", _coded_or_unknown(
            vocabulary, "operating_models", project.get("operating_model"), project.get("operating_model_unknown_reason")
        ) + anchors(project.get("operating_model_evidence_id"))),
        ("Development type", _coded_or_unknown(
            vocabulary, "development_types", project.get("development_type"), project.get("development_type_unknown_reason")
        )),
        ("Companies", _role_claims_html(context, project, anchors)),
        ("Workloads", _workloads_html(context, project, anchors)),
    ]
    for key, reason_key, title in OBSERVATION_FIELDS:
        count = len(_dict_items(project.get(key)))
        if count:
            facts.append((title, _e(f"{count} reported value{'s' if count != 1 else ''} (below)")))
        else:
            facts.append((title, _muted_unknown(project.get(reason_key))))
    facts.append(("Locator", _project_locator_html(context, project, anchors)))
    review = project.get("imagery_review_outcome")
    if review:
        outcome = (
            f"{_e(vocabulary.label('imagery_review_outcomes', review))} "
            f'<span class="mono small">{_breakable(review)}</span>'
        )
        description = vocabulary.description("imagery_review_outcomes", review)
        if description:
            outcome += f'<br><span class="small muted">{_e(description)}</span>'
    else:
        outcome = _muted_unknown(None)
    if project.get("independent_imagery_verification") is not True:
        outcome += " · no independent imagery verification"
    facts.append(("Source checks", f'<details><summary>Review details</summary><p>{outcome}</p>'
                  f'<p>Status age at review: {age_html}</p></details>'))
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
            f"<td>{_time(item.get('as_of_date'))}</td>"
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


def _evidence_table(context: _Context, site: Mapping[str, Any]) -> str:
    vocabulary = context.vocabulary
    rows = []
    not_stated = '<span class="muted">not stated</span>'
    for evidence in context.atlas.evidence_by_site[site["site_id"]]:
        url = evidence.get("source_url")
        link = _external_link(url, evidence.get("title") or url)
        if _safe_http_url(url) is None:
            link += f' <span class="small muted">(not linked: <span class="mono">{_e(url)}</span>)</span>'
        archive = _safe_http_url(evidence.get("archive_url"))
        if archive:
            label = f"Archived copy of {evidence.get('title') or url}"
            link += (
                f'<br><span class="small"><a class="external" rel="noopener" href="{_e(archive)}" '
                f'aria-label="{_e(label)}">Archived copy</a></span>'
            )
        roles = ", ".join(vocabulary.label("evidence_roles", role) for role in evidence.get("roles") or [])
        digest = str(evidence.get("content_hash") or "")
        kind = vocabulary.label("evidence_kinds", evidence.get("kind"))
        rows.append(
            f'<tr id="evidence-{_e(evidence["evidence_id"])}">'
            f"<td>{link}</td>"
            f'<td>{_e(evidence.get("publisher"))}<br><span class="small muted">{_e(kind)}</span></td>'
            f"<td>{_e(roles)}</td>"
            f"<td>{_time(evidence.get('published_at')) or not_stated}</td>"
            f"<td>{_time(evidence.get('retrieved_at'))}</td>"
            f"<td>{_license_link(evidence.get('license'), evidence.get('publisher'))}</td>"
            f"<td>{_attribution_html(evidence.get('attribution'))}</td>"
            f'<td><code class="checksum">{_e(digest)}</code></td>'
            "</tr>"
        )
    headers = (
        ("Title", ""), ("Publisher", ""), ("Roles", ""), ("Published", ""), ("Retrieved", ""),
        ("Licence", ""), ("Attribution", ""), ("Content hash (SHA-256)", ""),
    )
    note = (
        '<p class="small muted">Sources are linked, not redistributed; each keeps its own terms. An archived copy is '
        "the Wayback Machine capture nearest the retrieval time and may differ from what was reviewed; the content "
        "hash identifies the reviewed capture.</p>"
    )
    return note + _table("evidence-table", headers, rows, caption=f"Evidence for {site.get('name')}")


def _place_json_ld(context: _Context, site: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": site.get("name"),
        "identifier": site["site_id"],
        "url": site["url"],
        "geo": {"@type": "GeoCoordinates", "latitude": site["latitude"], "longitude": site["longitude"]},
        "address": {"@type": "PostalAddress", "addressCountry": site.get("country_iso_a2")},
        "containedInPlace": {"@type": "Country", "name": site.get("country")},
        "subjectOf": {"@id": f"{context.base_url}data/#dataset"},
    }


def _breakable(code: Any) -> str:
    """Escape an identifier and allow line breaks after _ / . - so it wraps between words, not mid-word.

    A hyphen followed by a digit (dates, UUIDs) is not a line-break opportunity on its own, so it
    gets an explicit one too; site.css sets overflow-wrap: normal on identifier cells.
    """
    return re.sub(r"([_/.-])", r"\1<wbr>", _e(code))


def _breadcrumbs(root: str, trail: Sequence[tuple[str, str]], current: str) -> str:
    """Breadcrumb list; the separators come from CSS, so screen readers do not read them."""
    items = "".join(f'<li><a href="{_e(root + path)}">{_e(text)}</a></li>' for path, text in trail)
    return (
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>{items}'
        f'<li><span aria-current="page">{_e(current)}</span></li></ol></nav>'
    )


def _time(value: Any, *, date_only: bool = True) -> str:
    """A <time> element; the visible text is the date (YYYY-MM-DD), the attribute keeps the full value."""
    if value in (None, ""):
        return ""
    text = str(value)
    shown = text[:10] if date_only and ISO_DATE.match(text) else text
    title = f' title="{_e(text)}"' if shown != text else ""
    return f'<time datetime="{_e(text)}"{title}>{_e(shown)}</time>'


def _license_link(code: Any, publisher: Any = None) -> str:
    """A licence code, linked to its terms when the code (or the publisher's terms page) is known."""
    if not code:
        return ""
    url = LICENSE_URLS.get(str(code))
    if url is None and str(code) == "SEE_TERMS_OF_USE" and publisher in LEGAL_NOTICE_PUBLISHERS:
        url = CHICAGO_TERMS_URL
    if url is None:
        return _e(code)
    # Not rel="license": that would claim the page itself is under the source's licence.
    return f'<a class="external" rel="noopener" href="{_e(url)}">{_e(code)}</a>'


def _attribution_html(text: Any) -> str:
    """Escaped attribution text; the first "OpenStreetMap" links to its copyright page."""
    escaped = _e(text)
    if "OpenStreetMap" not in escaped:
        return escaped
    link = f'<a class="external" rel="noopener" href="{_e(OSM_COPYRIGHT_URL)}">OpenStreetMap</a>'
    return escaped.replace("OpenStreetMap", link, 1)


def _license_statements(licenses: Iterable[Any]) -> list[tuple[str, str]]:
    """(statement, terms URL) required by the licences among ``licenses``, in a fixed order."""
    present = {str(code) for code in licenses if code}
    return [LICENSE_STATEMENTS[code] for code in LICENSE_STATEMENTS if code in present]


def _license_statements_html(statements: Sequence[tuple[str, str]]) -> str:
    if not statements:
        return ""
    items = "".join(
        f'<li>{_e(statement)} {_external_link(url, "Licence terms")}</li>' for statement, url in statements
    )
    return f'<p class="small">Required licence statements:</p><ul class="small">{items}</ul>'


def _legal_notice_callout(context: _Context, heading_id: str | None = None) -> str:
    identifier = f' id="{_e(heading_id)}"' if heading_id else ""
    return (
        f'<div class="callout" role="note"><p><strong{identifier}>Source terms</strong></p>'
        f"{context.legal_notice_html}</div>"
    )


def _website_json_ld(context: _Context) -> dict[str, Any]:
    config = context.config
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": config.site_name,
        "description": config.tagline,
        "url": context.base_url,
        "about": {"@id": f"{context.base_url}data/#dataset"},
    }


def _data_catalog_json_ld(context: _Context) -> dict[str, Any]:
    config, base = context.config, context.base_url
    datasets = []
    for version in reversed(context.versions):
        names = {record.name for record in version.files}
        wanted = [name for name in ("sites.csv", "projects.csv", "evidence.csv", "sites.geojson") if name in names]
        datasets.append({
            "@type": "Dataset",
            "name": f"{config.title} ({version.label})",
            "version": version.id,
            "datePublished": version.checkpoint_date,
            "url": f"{base}versions/{version.id}/",
            "license": str(config.data_license.get("url", "")),
            "distribution": [
                {
                    "@type": "DataDownload",
                    "name": name,
                    "encodingFormat": EXTENSION_INFO.get(Path(name).suffix, ("", "application/octet-stream"))[1],
                    "contentUrl": f"{base}downloads/{version.id}/{name}",
                }
                for name in wanted
            ],
        })
    return {
        "@context": "https://schema.org",
        "@type": "DataCatalog",
        "name": f"{config.site_name} versions",
        "description": "Archived data with additions, corrections and source files.",
        "url": f"{base}versions/",
        "dataset": datasets,
    }


def _citation_html(context: _Context, root: str, citations: Mapping[str, Any] | None = None) -> str:
    """The citation of the current version with copy buttons and links to the citation files."""
    citations = citations or _citations(context)
    root_files = f"{_e(root)}api/v1/"
    apa = str(citations["apa"])
    files_url = str(citations["files_url"])
    visible = _e(apa.removesuffix(files_url)) + _external_link(files_url, "Source files")
    return "\n".join([
        f"<p>{visible}</p>",
        f'<p>{_copy_button(citations["apa"], "Copy citation", "Copy citation (APA)")}</p>',
        _code_block(citations["bibtex"], title="BibTeX"),
        f'<p class="small">Also as <a href="{root_files}citation.bib">BibTeX file</a>, '
        f'<a href="{root_files}citation.ris">RIS</a> (EndNote, Zotero, Mendeley) and '
        f'<a href="{root_files}citation.json">JSON with CSL-JSON and biblatex</a>.</p>',
    ])


def _dictionary_example(raw_rows: Sequence[Mapping[str, str]], name: str, logical_type: str) -> str:
    """First informative value of a column: for JSON arrays, the first non-empty array."""
    if logical_type == "json_array":
        value = next((row[name] for row in raw_rows if _json_items(row[name])), None)
        if value is not None:
            return value if len(value) <= JSON_EXAMPLE_LIMIT else value[: JSON_EXAMPLE_LIMIT - 1] + "…"
    value = next((row[name] for row in raw_rows if row[name] != ""), "")
    return value if len(value) <= EXAMPLE_LIMIT else value[: EXAMPLE_LIMIT - 1] + "…"


def _embedded_types_table(atlas: Atlas) -> str:
    """schema.json embedded_types: the objects inside the *_json array columns of projects.csv."""
    embedded = atlas.schema.get("embedded_types")
    items = atlas.schema.get("embedded_array_items")
    if not isinstance(embedded, dict) or not embedded:
        return ""
    used: dict[str, list[str]] = defaultdict(list)
    for column, spec in (items.items() if isinstance(items, dict) else []):
        if isinstance(spec, dict) and isinstance(spec.get("item_type"), str):
            used[spec["item_type"]].append(column.split(":", 1)[-1])
    rows = []
    for name, spec in embedded.items():
        if not isinstance(spec, dict):
            continue
        parts = []
        for key, value in spec.items():
            label = key.replace("_", " ")
            if isinstance(value, list):
                text = ", ".join(str(item) for item in value)
            elif isinstance(value, dict):
                text = "; ".join(f"{item} = {unit}" for item, unit in value.items())
            else:
                text = str(value)
            parts.append(f"<strong>{_e(label)}</strong>: <span class=\"mono small\">{_e(text)}</span>")
        columns = ", ".join(f'<span class="mono">{_breakable(column)}</span>' for column in used.get(name, []))
        rows.append(
            f'<tr><td class="mono">{_breakable(name)}</td><td>{columns or "—"}</td><td>{"<br>".join(parts)}</td></tr>'
        )
    if not rows:
        return ""
    note = (
        "<p>Each item of these JSON array columns is an object with the fields below. Values the source does not "
        "state are <code>null</code>; units follow the metric.</p>"
    )
    return note + _table("dictionary-embedded", (("Object", ""), ("Columns", ""), ("Contract", "")), rows)


def _field_notes(entries: Mapping[str, Any] | None) -> str:
    items = "".join(
        f"<dt><code>{_breakable(name)}</code></dt><dd>{_e(description)}</dd>"
        for name, description in (entries or {}).items()
        if isinstance(description, str)
    )
    return f'<dl class="kv">{items}</dl>'


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
        f'<p class="lede">Explore data-centre construction in {count} countries and territories.</p>\n'
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
    iso = country["country_iso_a2"]
    summaries = [atlas.summary_by_id[site_id] for site_id in _sorted_site_ids(atlas, country["site_ids"])]
    table_id = "country-sites-table"
    stats = '<div class="stats">' + "".join(
        f'<div class="stat"><span class="stat-value">{value}</span> <span class="stat-label">{label}</span></div>'
        for value, label in ((country["site_count"], "sites"), (country["project_count"], "projects"))
    ) + "</div>"
    actions = " ".join([
        f'<a class="btn btn-small" href="{root}?country={_e(quote(iso, safe=""))}">Open in the map explorer</a>',
        f'<a class="btn btn-small" href="{root}api/v1/countries/{_e(iso)}.json">JSON for this country</a>',
        f'<a class="btn btn-small" href="{root}api/v1/countries/{_e(iso)}.geojson">GeoJSON</a>',
        f'<a class="btn btn-small" href="{root}api/v1/countries/{_e(iso)}.csv">CSV</a>',
    ])
    body = "\n".join([
        _breadcrumbs(root, (("countries/", "Countries"),), str(country["country"])),
        f"<h1>{_e(country['country'])}</h1>",
        stats,
        f'<p class="lede">Construction sites in {_e(country["country"])}, with reported stages and sources.</p>',
        _filter_controls(table_id, len(summaries), "sites"),
        _sites_table(context, summaries, root, table_id),
        f'<p class="small">{actions}</p>',
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
        head_links=(
            ("alternate", "application/json", f"api/v1/countries/{iso}.json"),
            ("alternate", "application/geo+json", f"api/v1/countries/{iso}.geojson"),
            ("alternate", "text/csv", f"api/v1/countries/{iso}.csv"),
        ),
    )


def _download_rows(context: _Context, root: str, directory: str = LATEST, items: Sequence[DownloadFile] | None = None) -> list[str]:
    rows = []
    for item in context.downloads if items is None else items:
        kind = '<br><span class="small muted">derived</span>' if item.derived else ""
        rows.append(
            "<tr>"
            f'<td><a href="{root}downloads/{_e(directory)}/{_e(item.name)}">{_e(item.name)}</a>{kind}</td>'
            f"<td>{_e(item.format)}</td>"
            f"<td>{_e(item.description)}</td>"
            f'<td class="num">{_e(_human_size(item.size))}</td>'
            f'<td><code class="checksum">{_e(item.sha256)}</code> '
            f'{_copy_button(item.sha256, "Copy", f"Copy SHA-256 of {item.name}")}</td>'
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
            '# keep_default_na=False keeps codes such as "NA" (Namibia); only empty cells are missing.',
            'options = {"keep_default_na": False, "na_values": [""]}',
            'sites = pd.read_csv(base + "sites.csv", **options)',
            'projects = pd.read_csv(base + "projects.csv", **options)',
            'evidence = pd.read_csv(base + "evidence.csv", **options)',
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
            f'sites = gpd.read_file("{base}api/v1/sites.geojson")',
            'print(sites[["name", "country", "geometry_type", "url"]].head())',
        ])),
        ("r", "R (readr and sf)", "\n".join([
            "library(readr)",
            "library(sf)",
            "",
            f'base <- "{latest}"',
            '# na = "" keeps codes such as "NA" (Namibia); only empty cells are missing.',
            'sites <- read_csv(paste0(base, "sites.csv"), na = "")',
            'projects <- read_csv(paste0(base, "projects.csv"), na = "")',
            'evidence <- read_csv(paste0(base, "evidence.csv"), na = "")',
            f'geometry <- st_read("{base}api/v1/sites.geojson")',
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
        ("spreadsheets", "Excel and Google Sheets", "\n".join([
            f"Excel: open {latest}atlas.xlsx (one sheet per table, plus a README sheet).",
            "Excel with a CSV: Data > From Text/CSV, File origin 65001: Unicode (UTF-8).",
            f'Google Sheets: =IMPORTDATA("{latest}sites.csv")',
        ])),
    ]


def _data_page(context: _Context) -> _Page:
    path = "data/index.html"
    root = _relative_root(path)
    current, counts = context.current, context.atlas.counts
    config = context.config
    latest = f"{context.base_url}downloads/{LATEST}/"
    zip_item = next((item for item in context.downloads if item.name.endswith(".zip")), None)
    zip_button = (
        f'<p><a class="btn btn-primary" href="{root}downloads/{LATEST}/{_e(zip_item.name)}">All files (zip, '
        f"{_e(_human_size(zip_item.size))})</a></p>" if zip_item else ""
    )
    snippets = "\n".join(
        f'{_heading(3, "use-" + anchor, title)}\n{_code_block(code, title=title)}'
        for anchor, title, code in _usage_snippets(context)
    )
    datasette = f"https://lite.datasette.io/?url={quote(latest + 'atlas.sqlite', safe=':/')}"
    toc_items = (
        ("files", "Files"), ("pinned", "Pinned URLs"), ("use", "Use the data"), ("gis", "QGIS and Google Earth"),
        ("more", "Dictionary and API"), ("cite", "Licence and citation"), ("legal-notice", "Data notices"),
    )
    toc = '<nav class="toc" aria-label="On this page"><ul>' + "".join(
        f'<li><a href="#{anchor}">{_e(text)}</a></li>' for anchor, text in toc_items
    ) + "</ul></nav>"
    citations = _citations(context)
    body = "\n".join([
        "<h1>Download the data</h1>",
        f'<p class="lede">{counts.get("physical_sites")} sites in {counts.get("countries")} countries. '
        'Download a spreadsheet, map file or database.</p>',
        f'<p class="small muted">Updated {_e(current.checkpoint_date)}. Construction observations: '
        f'{_e(context.window_start)} to {_e(current.lifecycle_reference_date)}.</p>',
        f'<p><a class="btn btn-primary" href="{root}downloads/{LATEST}/atlas.xlsx">Excel workbook</a> '
        f'<a class="btn" href="{root}downloads/{LATEST}/sites.csv">Sites CSV</a> '
        f'<a class="btn" href="{root}downloads/{LATEST}/sites.geojson">GeoJSON</a> '
        f'<a class="btn" href="{root}downloads/{LATEST}/atlas.sqlite">SQLite</a></p>',
        toc,
        _heading(2, "files", "Files"),
        zip_button,
        _table("downloads-table", (("File", ""), ("Format", ""), ("Description", ""), ("Size", "num"), ("SHA-256", "")),
               _download_rows(context, root), classes="data-table download-list"),
        f'<p class="small muted">{_e(MEDIA_TYPE_NOTE)}</p>',
        _heading(2, "pinned", "Pinned URLs"),
        f'<p>The <a href="{root}downloads/{LATEST}/">current downloads</a> update as records are added or corrected. '
        f'For reproducible analysis, use the <a href="{root}downloads/{_e(current.id)}/">archived source files '
        f'from {_e(current.checkpoint_date)}</a>. Their original bytes are fixed; generated formats can change '
        'with the site builder. Check files against the SHA256SUMS in their directory.</p>',
        _heading(2, "use", "Use the data"),
        snippets,
        _heading(2, "gis", "QGIS and Google Earth"),
        f"<p>In QGIS choose <em>Layer → Add Layer → Add Vector Layer</em> and paste "
        f"<code>{_e(context.base_url)}api/v1/sites.geojson</code> (its features carry each site's page URL, API URL and "
        "geometry licence). "
        f'In Google Earth open <a href="{root}downloads/{LATEST}/sites.kml">sites.kml</a>. To browse the SQLite database in '
        f"the browser, open it in {_external_link(datasette, 'Datasette Lite')}.</p>",
        _heading(2, "more", "Dictionary and API"),
        f'<ul><li><a href="{root}data/dictionary/">Field dictionary</a>: every column, type and coded value.</li>'
        f'<li><a href="{root}api/">JSON API</a>: per-site documents, GeoJSON, aggregates, an '
        f'<a href="{root}api/v1/openapi.json">OpenAPI description</a> and JSON Schemas.</li>'
        f'<li><a href="{root}versions/">Data history</a>: additions, corrections and archived files.</li>'
        f'<li><a href="{root}llms.txt">llms.txt</a>: a plain-text guide for language models and agents.</li></ul>',
        _heading(2, "cite", "Licence and citation"),
        f'<p>{_external_link(config.data_license.get("url"), config.data_license.get("name"))} for Atlas-authored '
        f"content. Geometries derived from OpenStreetMap are © "
        f'{_external_link(OSM_COPYRIGHT_URL, "OpenStreetMap contributors")} and available under the '
        f'{_external_link(ODBL["url"], ODBL["name"])}. Other third-party facts, titles, URLs and geometries keep '
        "their source terms, recorded per evidence row (each site record lists its geometry_licenses) and in "
        f'<a href="{root}about/attribution/">the attribution file</a>. '
        f'Details on the <a href="{root}about/">about page</a>.</p>',
        _citation_html(context, root, citations),
        _heading(2, "legal-notice", "Data notices"),
        _legal_notice_callout(context),
    ])
    return _Page(
        path=path,
        slug="data",
        section="data",
        title="Download the data",
        description=(
            "Download Data Center Atlas: Excel, CSV, GeoJSON, SQLite, JSON, NDJSON, KML and a Frictionless Data Package "
            "with checksums."
        ),
        body=body,
        scripts=(SITE_JS,),
        json_ld=_dataset_json_ld(context),
    )


def _dictionary_page(context: _Context) -> _Page:
    path = "data/dictionary/index.html"
    root = _relative_root(path)
    atlas = context.atlas
    descriptions = context.descriptions
    sections = []
    for file_name in TABLE_FILES:
        table_descriptions = descriptions.get("tables", {}).get(file_name, {})
        rows = []
        for spec in atlas.fields[file_name]:
            name = spec["name"]
            logical = str(spec.get("logical_type", "string"))
            example = _dictionary_example(atlas.raw[file_name], name, logical)
            nullable = "yes" if spec.get("allows_empty_string") else "no"
            description = table_descriptions.get(name) or "Not yet documented."
            rows.append(
                "<tr>"
                f'<td class="mono">{_breakable(name)}</td>'
                f'<td class="mono">{_breakable(typed_field_name(name))}</td>'
                f'<td class="mono">{_breakable(logical)}</td>'
                f"<td>{nullable}</td>"
                f"<td>{_e(description)}</td>"
                f'<td class="mono small">{_e(example)}</td>'
                "</tr>"
            )
        anchor = file_name.replace(".", "-")
        headers = (("Column", ""), ("JSON name", ""), ("Type", ""), ("Empty allowed", ""), ("Description", ""), ("Example", ""))
        sections.append(_heading(2, anchor, file_name) + "\n" + _table(f"dictionary-{anchor}", headers, rows))
    embedded = _embedded_types_table(atlas)
    if embedded:
        sections.append(_heading(2, "embedded", "Embedded objects") + "\n" + embedded)
    derived_rows = []
    for table, items in (descriptions.get("derived") or {}).items():
        for name, description in items.items():
            derived_rows.append(
                f'<tr><td class="mono">{_e(table)}</td><td class="mono">{_breakable(name)}</td><td>{_e(description)}</td></tr>'
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
    if embedded:
        toc_items.append(("embedded", "Embedded objects"))
    toc_items += [("derived", "Derived API fields"), ("coded-values", "Coded values")]
    toc = '<nav class="toc" aria-label="On this page"><ul>' + "".join(
        f'<li><a href="#{_e(anchor)}">{_e(text)}</a></li>' for anchor, text in toc_items
    ) + "</ul></nav>"
    body = "\n".join([
        _breadcrumbs(root, (("data/", "Data"),), "Dictionary"),
        "<h1>Field dictionary</h1>",
        f'<p class="lede">Every column of the three CSV files of {_e(context.current.label)}, from its schema.json, with '
        "plain-language descriptions and an example value. Empty values mean unknown, never zero. The same "
        f'contract is machine-readable as <a href="{root}api/v1/schemas/index.json">JSON Schemas</a> and in '
        f'<a href="{root}downloads/{LATEST}/datapackage.json">datapackage.json</a>. How the identifiers '
        "(<code>site_id</code>, <code>project_id</code>, <code>evidence_id</code>) are formed and how long they stay "
        f'valid is explained in the <a href="{root}{_methodology_link(context, "identifiers")}">methodology</a>.</p>',
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
        if name == "release_gates":
            continue  # Historical workflow metadata remains in the machine-readable vocabulary.
        rows = []
        for code, entry in entries.items():
            unit = f'<td class="mono">{_e(entry.get("unit"))}</td>' if name == "power_metrics" else ""
            rows.append(
                f'<tr><td class="mono">{_breakable(code)}</td><td>{_e(entry.get("label"))}</td>{unit}'
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
    replacements = {
        "{site_id}": first_site, "{project_id}": first_project, "{evidence_id}": first_evidence, "{iso2}": first_country,
    }
    rows = []
    for key, path in _endpoint_paths().items():
        example = path
        for token, value in replacements.items():
            example = example.replace(token, value)
        rows.append(
            f'<tr><td class="mono">{_breakable(path)}</td><td>{_e(ENDPOINT_DESCRIPTIONS[key])}</td>'
            f'<td><a href="{root}{_e(example)}">example</a></td></tr>'
        )
    return rows


def _api_page(context: _Context) -> _Page:
    path = "api/index.html"
    root = _relative_root(path)
    base = context.base_url
    atlas = context.atlas
    descriptions = context.descriptions
    example = ""
    first_site = atlas.summaries[0]["site_id"] if atlas.summaries else ""
    first_country = atlas.countries[0]["country_iso_a2"] if atlas.countries else ""
    if atlas.summaries:
        document = _site_document(context, atlas.site_by_id[atlas.summaries[0]["site_id"]])
        lines = _json_text(document, pretty=True).splitlines()
        example = "\n".join(lines[:API_EXAMPLE_LINES] + (["…"] if len(lines) > API_EXAMPLE_LINES else []))
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
    sections = (
        ("fields-site-summary", "Site summaries", "sites.json, sites.geojson properties and country files.", "site_summary"),
        ("fields-country-summary", "Country summaries", "countries.json and each country document.", "country_summary"),
        ("fields-stats", "Statistics", "stats.json: every map with its unit.", "stats"),
        ("fields-counts", "Counts", "The counts object of index.json, stats.json and atlas.json.", "counts"),
        ("fields-version", "Versions", "Each entry of versions.json.", "version"),
        ("fields-index", "Index", "api/v1/index.json.", "index"),
    )
    field_sections = []
    for anchor, title, scope, key in sections:
        field_sections.append(
            f"{_heading(3, anchor, title)}\n<p>{_e(scope)}</p>\n{_field_notes(descriptions.get(key))}"
        )
    body = "\n".join([
        "<h1>API</h1>",
        f'<p class="lede">A static, read-only JSON API at <code>{_e(base)}api/v1/</code>. Plain files over HTTPS: no key, '
        "no sign-up and no rate limit beyond GitHub Pages fair use. GitHub Pages sends CORS headers, so browsers can "
        "fetch it from any origin.</p>",
        '<div class="callout" role="note"><p>The path is versioned. Within <code>v1</code>, changes are additive only: '
        "new fields or endpoints may appear, existing ones keep their meaning. A breaking change would get a new "
        f"path. <code>api/v1/index.json</code> names the dataset version it serves; every version has its own "
        f'<a href="{root}downloads/">download directory</a> and <a href="{root}versions/">version page</a>.</p></div>',
        _heading(2, "read-first", "Read before using"),
        "<ul>" + "".join(f"<li>{_e(caveat)}</li>" for caveat in DATA_CAVEATS) + "</ul>",
        _heading(2, "endpoints", "Endpoints"),
        _table("api-endpoints", (("Path", ""), ("Description", ""), ("Example", "")), _api_endpoint_rows(context, root)),
        f'<p class="small muted">{_e(MEDIA_TYPE_NOTE)}</p>',
        _heading(2, "contract", "Machine-readable contract"),
        f'<p><a href="{root}api/v1/openapi.json">api/v1/openapi.json</a> is an OpenAPI 3.1 description of every '
        "endpoint; import it into Swagger UI, Postman or a code generator. Each response and record type also has a "
        f'JSON Schema (2020-12), listed in <a href="{root}api/v1/schemas/index.json">api/v1/schemas/index.json</a>. '
        "The schemas are generated from the dataset's schema.json and the descriptions on this page; "
        "new optional fields may appear within v1. Language models and agents can start from "
        f'<a href="{root}llms.txt">llms.txt</a>.</p>',
        _heading(2, "explorer-links", "Explorer links"),
        f'<p>The <a href="{root}">map explorer</a> keeps its view in the URL (<code>q</code>, <code>country</code>, '
        "<code>status</code>, <code>locator</code>, <code>power</code>, <code>from</code>, <code>to</code>, "
        "<code>sort</code> and <code>#site=&lt;site_id&gt;</code>), so a link reproduces a filtered view"
        + (
            f', for example <a href="{root}?country={_e(first_country)}"><code>?country={_e(first_country)}</code></a>'
            if first_country else ""
        )
        + ". The parameters, the columns of the explorer's CSV and GeoJSON exports and its optional WebMCP tools for "
        "browser agents are documented in the "
        f'<a class="external" rel="noopener" href="{_e(context.config.repository_url)}/blob/main/docs/public_site.md'
        '#explorer-links-and-exports">maintainer notes</a>.</p>',
        _heading(2, "fields", "Response fields"),
        "<p>Records are typed from the source schema.json: empty CSV values become <code>null</code>; "
        "<code>*_json</code> columns become parsed JSON without the suffix; numbers, integers and booleans are JSON "
        "types. Statuses are the last observed physical status on the status date. Absolute URLs in responses "
        "start with the <code>base_url</code> given in <code>api/v1/index.json</code>. The "
        f'<a href="{root}data/dictionary/">field dictionary</a> describes every column and coded value, and the '
        f'<a href="{root}{_methodology_link(context, "identifiers")}">methodology</a> explains how identifiers are '
        "formed and how long they stay valid. GeoJSON responses orient polygon rings as RFC 7946 requires (exterior "
        "rings counterclockwise); the CSV files and typed records keep the original ring order.</p>",
        *field_sections,
        _heading(2, "examples", "Examples"),
        *(f"<h3>{_e(title)}</h3>\n{_code_block(code, title=title)}" for title, code in examples),
        _heading(2, "citation", "Citation"),
        _citation_html(context, root),
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
        description="Static JSON API for the Data Center Atlas: endpoints, OpenAPI description, fields and examples.",
        body=body,
        scripts=(SITE_JS,),
        head_links=(
            ("service-desc", "application/openapi+json", "api/v1/openapi.json"),
            ("alternate", "application/json", "api/v1/index.json"),
        ),
    )


def _content_page(context: _Context, name: str) -> _Page:
    path = f"{name}/index.html"
    body = _render_fragment(context, f"content/{name}.html", _relative_root(path))
    titles = {
        "methodology": ("Methodology", "How sites are researched, and how to read construction stages, locations and sources."),
        "about": ("About", "About the Data Center Atlas: license, citation, corrections and legal notices."),
    }
    title, description = titles[name]
    return _Page(path=path, slug=name, section=name, title=title, description=description, body=body, scripts=(SITE_JS,))


def _version_files_html(context: _Context, version: DatasetVersion, root: str) -> str:
    names = [record.name for record in version.files]
    wanted = [name for name in ("sites.csv", "projects.csv", "evidence.csv", "sites.geojson", "manifest.json") if name in names]
    if context.has_derived(version):
        wanted.append(_zip_name(version))
    wanted.append("SHA256SUMS")
    links = " ".join(
        f'<a href="{root}downloads/{_e(version.id)}/{_e(name)}">{_e("All files (ZIP)" if name.endswith(".zip") else name)}</a>'
        for name in wanted
    )
    return f'{links} <a href="{root}downloads/{_e(version.id)}/">all files</a>'


def _versions_page(context: _Context) -> _Page:
    path = "versions/index.html"
    root = _relative_root(path)
    current_sites = context.atlas.site_by_id
    rows = []
    for version in reversed(context.versions):
        change = context.history[version.id]
        added = change.ids("sites.csv", "added")
        names = change.labels["sites"]
        items = []
        for site_id in sorted(added, key=lambda value: (names.get(value, "").casefold(), value)):
            label = _e(names.get(site_id, site_id))
            if site_id in current_sites:
                label = f'<a href="{root}sites/{_e(site_id)}/">{label}</a>'
            items.append(f"<li>{label}</li>")
        added_html = (
            f"<details><summary>{len(added)} added</summary><ul>{''.join(items)}</ul></details>" if added else "0"
        )
        removed = change.ids("sites.csv", "removed")
        if removed:
            added_html += f'<br><span class="small muted">{len(removed)} removed</span>'
        counts = version.counts
        marker = ' <span class="tag">current</span>' if version.id == context.current.id else ""
        rows.append(
            f'<tr id="version-{_e(version.id)}">'
            f'<td><a href="{root}versions/{_e(version.id)}/">{_e(version.label)}</a>{marker}</td>'
            f'<td class="num">{_e(counts.get("physical_sites"))}</td>'
            f'<td class="num">{_e(counts.get("projects"))}</td>'
            f'<td class="num">{_e(counts.get("countries"))}</td>'
            f'<td class="num">{_e(counts.get("evidence"))}</td>'
            f"<td>{added_html}</td>"
            f'<td class="small">{_e(_change_summary(change))}</td>'
            f'<td class="small">{_version_files_html(context, version, root)}</td>'
            f"<td>{_external_link(_tree_url(context, version), 'GitHub')}</td>"
            "</tr>"
        )
    headers = (
        ("Snapshot", ""), ("Sites", "num"), ("Projects", "num"),
        ("Countries", "num"), ("Evidence", "num"), ("Added sites", ""), ("Changes", ""), ("Files", ""), ("Source", ""),
    )
    body = "\n".join([
        "<h1>Data history</h1>",
        '<p class="lede">Additions and corrections to the Atlas, newest first. Open a snapshot to see '
        "what changed or download its data.</p>",
        f'<p>Subscribe to <a href="{root}feed.xml">data updates</a> or the '
        f'<a href="{root}sites-feed.xml">new sites feed</a>. '
        f'<a href="{root}api/v1/versions.json">Download this history as JSON</a>.</p>',
        _table("versions-table", headers, rows, classes="data-table"),
    ])
    return _Page(
        path=path,
        slug="versions",
        section="versions",
        title="Data history",
        description="Additions, corrections and dated snapshots of the Data Center Atlas, with downloads.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
        json_ld=_data_catalog_json_ld(context),
        head_links=(("alternate", "application/json", "api/v1/versions.json"),),
    )


def _legal_notice(version: DatasetVersion) -> str:
    """The "## Legal notice" section of a version's README.md as HTML paragraphs (hash-checked read)."""
    text = _verified_text(version, "README.md")
    match = re.search(r"^## Legal notice[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if match is None or not match.group(1).strip():
        raise PublicSiteError(f"{version.id}/README.md: no '## Legal notice' section")
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", match.group(1)) if block.strip()]
    # This Atlas-authored product description is not part of the source's required notice.
    paragraphs = [block for block in paragraphs if not block.startswith("This preview is an evidence product,")]
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
    statements = _license_statements(item.get("license") for item in context.atlas.evidence)
    statements_html = ""
    if statements:
        statements_html = (
            '<h2 id="licence-statements">Licence statements</h2>'
            "<p>Some sources' licences require a statement from anyone who reuses their material:</p><ul>"
            + "".join(f"<li>{_e(statement)} {_external_link(url, 'Licence terms')}</li>" for statement, url in statements)
            + "</ul>"
        )
    body = "\n".join([
        _breadcrumbs(root, (("about/", "About"),), "Attribution"),
        "<h1>Attribution and legal notices</h1>",
        '<p class="lede">Third-party facts, titles, URLs and geometries keep their source terms. '
        "Below is the dataset's full attribution file; every evidence row also records its own license and "
        "attribution. The Atlas links to sources and does not redistribute third-party documents or imagery.</p>",
        f'<p>Geometries derived from OpenStreetMap are © {_external_link(OSM_COPYRIGHT_URL, "OpenStreetMap contributors")}, '
        f'available under the {_external_link(ODBL["url"], ODBL["name"])}.</p>',
        '<section class="callout" aria-labelledby="legal-notice"><h2 id="legal-notice">Legal notice</h2>'
        f'{context.legal_notice_html}</section>',
        statements_html,
        '<h2 id="attribution-file">Source attribution</h2>',
        f'<p class="small"><a href="{root}downloads/{_e(current.id)}/ATTRIBUTION.txt">Download the file</a></p>',
        f'<details><summary>Full source attribution</summary><pre class="code">{_linkify(context.attribution_text)}</pre></details>',
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


def _change_summary(change: _VersionChange) -> str:
    """'8 sites added; 2 projects changed …' for one version (empty sections are left out)."""
    parts = []
    for table in ("sites", "projects", "evidence"):
        section = change.document[table]
        for kind in ("added", "removed", "changed"):
            count = len(section[kind])
            if count:
                noun = table if count != 1 else {"sites": "site", "projects": "project", "evidence": "evidence row"}[table]
                if table == "evidence" and count != 1:
                    noun = "evidence rows"
                parts.append(f"{count} {noun} {kind}")
    columns = sum(
        len(item["added_columns"]) + len(item["removed_columns"]) for item in change.document["schema"].values()
    )
    if columns:
        parts.append(f"{columns} column{'s' if columns != 1 else ''} added or removed")
    return "; ".join(parts) or "no record changes"


def _change_value(value: str) -> str:
    if len(value) > CHANGE_VALUE_LIMIT:
        return value[: CHANGE_VALUE_LIMIT - 1] + "…"
    return value


def _version_page(context: _Context, version: DatasetVersion) -> _Page:
    path = f"versions/{version.id}/index.html"
    root = _relative_root(path)
    change = context.history[version.id]
    document = change.document
    previous = change.previous
    current_sites = context.atlas.site_by_id
    counts = version.counts
    previous_version = next((item for item in context.versions if item.id == previous), None)
    facts = [
        ("Added to the archive", _time(version.checkpoint_date)),
        ("Construction as of", _time(version.lifecycle_reference_date)),
        ("Observation dates", f"{_time(_window_start(context.config, version))} to {_time(version.lifecycle_reference_date)}"),
        ("Counts", _e(
            f"{counts.get('physical_sites')} sites, {counts.get('projects')} projects, "
            f"{counts.get('countries')} countries, {counts.get('evidence')} evidence rows"
        )),
        ("Previous snapshot", (
            f'<a href="{root}versions/{_e(previous)}/">{_e(previous_version.label)}</a>'
            if previous_version else "none (first snapshot)"
        )),
        ("Manifest SHA-256", f'<code class="checksum">{_e(version.manifest_sha256)}</code>'),
        ("Files", f'<a href="{root}downloads/{_e(version.id)}/">Download this snapshot</a> · '
                  f"{_external_link(_tree_url(context, version), 'GitHub')}"),
    ]
    if version.id == context.current.id:
        facts.insert(0, ("Current", '<span class="tag">latest data</span>'))
    sections = [
        _heading(2, "summary", "Summary"),
        _kv(facts),
        _heading(2, "changes", "Changes from the previous snapshot"),
        f"<p>{_e(_change_summary(change))}.</p>" if previous else
        "<p>The first snapshot: every record is new.</p>",
    ]
    schema_rows = []
    for table, item in document["schema"].items():
        for kind in ("added_columns", "removed_columns"):
            for column in item[kind]:
                schema_rows.append(
                    f'<tr><td>{_e(table)}</td><td class="mono">{_breakable(column)}</td>'
                    f"<td>{'added' if kind == 'added_columns' else 'removed'}</td></tr>"
                )
    if schema_rows:
        sections += [
            _heading(3, "schema-changes", "Columns"),
            _table("schema-changes-table", (("Table", ""), ("Column", ""), ("Change", "")), schema_rows),
        ]
    added_sites = change.ids("sites.csv", "added")
    if added_sites:
        items = []
        for site_id in sorted(added_sites, key=lambda value: (change.labels["sites"].get(value, "").casefold(), value)):
            label = _e(change.labels["sites"].get(site_id, site_id))
            if site_id in current_sites:
                label = f'<a href="{root}sites/{_e(site_id)}/">{label}</a>'
            items.append(f'<li>{label} <span class="mono small muted">{_e(site_id)}</span></li>')
        sections += [_heading(3, "added-sites", f"Sites added ({len(added_sites)})"), "<ul>" + "".join(items) + "</ul>"]
    removed_rows = []
    for table in ("sites", "projects", "evidence"):
        for record_id in document[table]["removed"]:
            removed_rows.append(
                f"<tr><td>{_e(table)}</td><td>{_e(change.removed_labels[table].get(record_id, ''))}</td>"
                f'<td class="mono">{_breakable(record_id)}</td></tr>'
            )
    if removed_rows:
        sections += [
            _heading(3, "removed", f"Records removed ({len(removed_rows)})"),
            "<p>These records were removed from this snapshot. Their identifiers resolve in the current API "
            "only if the records were subsequently restored.</p>",
            _table("removed-table", (("Table", ""), ("Name or title", ""), ("ID", "")), removed_rows),
        ]
    if change.field_changes:
        rows = []
        for item in change.field_changes:
            empty = '<span class="muted">empty</span>'
            if item.field.endswith("_json"):
                values = '<span class="muted">JSON value changed (see the CSV files of both snapshots)</span>'
            else:
                before = _e(_change_value(item.before)) or empty
                after = _e(_change_value(item.after)) or empty
                values = f"{before} → {after}"
            link = _e(item.label or item.record_id)
            if item.table == "sites" and item.record_id in current_sites:
                link = f'<a href="{root}sites/{_e(item.record_id)}/">{link}</a>'
            rows.append(
                f"<tr><td>{_e(item.table)}</td><td>{link}<br>"
                f'<span class="mono small muted">{_breakable(item.record_id)}</span></td>'
                f'<td class="mono">{_breakable(item.field)}</td><td>{values}</td></tr>'
            )
        sections += [
            _heading(3, "changed", f"Fields changed ({len(change.field_changes)})"),
            "<p>Values that changed between the two snapshots. The earlier data remains available.</p>",
            _table("changed-table", (("Table", ""), ("Record", ""), ("Field", ""), ("Before → after", "")), rows),
        ]
    citation = _citations(context, version)
    sections += [
        _heading(2, "cite", "Cite this snapshot"),
        f"<p>{_e(citation['apa'])}</p>",
        f'<p>{_copy_button(citation["apa"], "Copy citation", f"Copy citation for {version.label}")}</p>',
    ]
    body = "\n".join([
        _breadcrumbs(root, (("versions/", "Data history"),), version.label),
        f"<h1>{_e(version.label)}</h1>",
        f'<p class="lede">Atlas data archived on {_e(version.checkpoint_date)}, with additions and corrections '
        "listed below.</p>",
        *sections,
    ])
    return _Page(
        path=path,
        slug="version",
        section="versions",
        title=version.label,
        description=(
            f"{version.label} of the Data Center Atlas: {counts.get('physical_sites')} sites, what changed from the "
            "previous snapshot, files and citation."
        ),
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _downloads_index_page(context: _Context) -> _Page:
    path = "downloads/index.html"
    root = _relative_root(path)
    rows = [
        f'<tr><td><a href="{root}downloads/{LATEST}/">Latest data</a></td><td>Always the latest Atlas data.</td>'
        f"<td>{_time(context.current.checkpoint_date)}</td><td>{len(context.download_dirs.get(LATEST, ()))}</td></tr>"
    ]
    for version in reversed(context.versions):
        marker = ' <span class="tag">current</span>' if version.id == context.current.id else ""
        rows.append(
            f'<tr><td><a href="{root}downloads/{_e(version.id)}/">{_e(version.label)}</a>{marker}</td>'
            f"<td>Archived data</td><td>{_time(version.checkpoint_date)}</td>"
            f"<td>{len(context.download_dirs.get(version.id, ()))}</td></tr>"
        )
    body = "\n".join([
        _breadcrumbs(root, (("data/", "Data"),), "Downloads"),
        "<h1>Download archive</h1>",
        '<p class="lede">Download the latest data or an earlier snapshot. Each directory lists its files, '
        "sizes and checksums.</p>",
        _table("download-directories", (("Data", ""), ("Contents", ""), ("Date", ""), ("Files", "")), rows),
    ])
    return _Page(
        path=path,
        slug="downloads",
        section="data",
        title="Download archive",
        description="Download the latest Data Center Atlas data or an earlier dated snapshot.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _download_directory_page(context: _Context, directory: str) -> _Page:
    path = f"downloads/{directory}/index.html"
    root = _relative_root(path)
    version = context.current if directory == LATEST else next(item for item in context.versions if item.id == directory)
    items = context.download_dirs.get(directory, ())
    url = f"{context.base_url}downloads/{directory}/"
    counts = version.counts
    if directory == LATEST:
        title = "Latest downloads"
        intro = (
            "The latest Atlas data in CSV, GeoJSON, Excel and other formats. For a reproducible reference, use "
            f'<a href="{root}downloads/{_e(version.id)}/">the {_e(version.checkpoint_date)} snapshot</a>.'
        )
    else:
        title = f"{version.label} downloads"
        intro = (
            f"Atlas data archived on {_e(version.checkpoint_date)}. The original data files remain unchanged."
        )
    derived = any(item.derived for item in items)
    derived_note = (
        " Files marked derived are rebuilt from the originals by each site build and may gain additive fields; "
        "SHA256SUMS lists the files as currently published." if derived else ""
    )
    verify = f"curl -LO {url}SHA256SUMS\nsha256sum --check --ignore-missing SHA256SUMS"
    body = "\n".join([
        _breadcrumbs(root, (("data/", "Data"), ("downloads/", "Downloads")), title),
        f"<h1>{_e(title)}</h1>",
        f'<p class="lede">{intro}</p>',
        _kv([
            ("Data history", f'<a href="{root}versions/{_e(version.id)}/">View additions and corrections</a>'),
            ("Archive date", _time(version.checkpoint_date)),
            ("Construction as of", _time(version.lifecycle_reference_date)),
            ("Counts", _e(
                f"{counts.get('physical_sites')} sites, {counts.get('projects')} projects, "
                f"{counts.get('countries')} countries, {counts.get('evidence')} evidence rows"
            )),
            ("Source", _external_link(_tree_url(context, version), "GitHub")),
        ]),
        f'<p class="small">manifest.json lists the size and SHA-256 hash of every original file.{_e(derived_note)} '
        "This page itself is not in SHA256SUMS or the zip.</p>",
        _table("downloads-table", (("File", ""), ("Format", ""), ("Description", ""), ("Size", "num"), ("SHA-256", "")),
               _download_rows(context, root, directory, items), classes="data-table download-list"),
        _heading(2, "verify", "Verify the files"),
        _code_block(verify, title="verify checksums"),
        f'<p class="small muted">{_e(MEDIA_TYPE_NOTE)}</p>',
    ])
    return _Page(
        path=path,
        slug="download-directory",
        section="data",
        title=title,
        description=f"Files of {version.label} of the Data Center Atlas with sizes and SHA-256 checksums.",
        body=body,
        main_class="page page-wide",
        scripts=(SITE_JS,),
    )


def _write_sites_feed(writer: _Writer, context: _Context) -> None:
    """One Atom entry per current site, dated by the snapshot that first added it."""
    base = context.base_url
    atlas, vocabulary = context.atlas, context.vocabulary
    first_seen: dict[str, DatasetVersion] = {}
    for version in context.versions:
        for site_id in context.history[version.id].ids("sites.csv", "added"):
            first_seen.setdefault(site_id, version)
    entries = sorted(
        atlas.summaries,
        key=lambda item: (
            first_seen[item["site_id"]].checkpoint_date if item["site_id"] in first_seen else "",
            first_seen[item["site_id"]].sort_key if item["site_id"] in first_seen else (),
            item["site_id"],
        ),
        reverse=True,
    )
    updated = max((version.checkpoint_date for version in first_seen.values()), default=context.current.checkpoint_date)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{_x(SITES_FEED_TITLE)}</title>",
        f"<subtitle>{_x('New sites added to the Atlas, newest first.')}</subtitle>",
        f"<id>{_x(_feed_id(context, '#sites'))}</id>",
        f"<updated>{updated}T00:00:00Z</updated>",
        f'<link rel="self" type="application/atom+xml" href="{_x(base)}sites-feed.xml"/>',
        f'<link rel="alternate" type="text/html" href="{_x(base)}sites/"/>',
        f"<author><name>{_x(context.config.author.get('name'))}</name><uri>{_x(context.config.author.get('url'))}</uri></author>",
    ]
    for summary in entries:
        version = first_seen.get(summary["site_id"], context.current)
        statuses = ", ".join(vocabulary.label("statuses", code) for code in summary.get("statuses") or []) or "unknown"
        text = (
            f"{summary.get('name')} ({summary.get('country')}): {statuses} as of "
            f"{summary.get('newest_status_as_of')}; source: {'; '.join(summary.get('status_publishers') or []) or 'not stated'}. "
            f"Added to the Atlas on {version.checkpoint_date}."
        )
        lines += [
            "<entry>",
            f"<title>{_x(summary.get('name'))}</title>",
            f"<id>{_x(_feed_id(context, '#site/' + summary['site_id']))}</id>",
            f"<updated>{version.checkpoint_date}T00:00:00Z</updated>",
            f'<link rel="alternate" type="text/html" href="{_x(summary["url"])}"/>',
            f'<link rel="related" type="application/json" href="{_x(summary["api_url"])}"/>',
            f"<summary>{_x(text)}</summary>",
            "</entry>",
        ]
    lines.append("</feed>")
    writer.write_text("sites-feed.xml", "\n".join(lines) + "\n")


def _write_llms_txt(writer: _Writer, context: _Context) -> None:
    writer.write_text("llms.txt", _llms_txt(context))
    writer.write_text("llms-full.txt", _llms_full_txt(context))


def _llms_txt(context: _Context) -> str:
    """llms.txt (llmstxt.org): data and documentation for language models, Atlas-authored text only."""
    config, current, atlas = context.config, context.current, context.atlas
    base = context.base_url
    counts = atlas.counts
    latest = f"{base}downloads/{LATEST}/"
    citation = _citations(context)["apa"]
    lines = [
        f"# {config.site_name}",
        "",
        f"> {config.tagline}. Updated {current.checkpoint_date}: "
        f"{counts.get('physical_sites')} physical sites, {counts.get('projects')} "
        f"construction projects in {counts.get('countries')} countries, {counts.get('evidence')} evidence rows. "
        f"Statuses were observed from {context.window_start} to {current.lifecycle_reference_date}.",
        "",
        "## About the data",
        "",
        *(f"- {caveat}" for caveat in DATA_CAVEATS),
        "- Every status, locator and metric is backed by an evidence row with a source URL, retrieval time, "
        "content hash and licence; follow those links rather than trusting summaries.",
        f"- Licence: {config.data_license.get('name')} for Atlas-authored data; geometries derived from OpenStreetMap "
        f"are {ODBL['attribution']} under {ODBL['name']}; other third-party facts keep their source terms "
        f"({base}about/attribution/).",
        f"- Cite as: {citation}",
        "",
        "## API",
        "",
        f"- [API index]({base}api/v1/index.json): dataset metadata, endpoint templates, downloads, licences",
        f"- [OpenAPI 3.1 description]({base}api/v1/openapi.json): every endpoint with JSON Schemas",
        f"- [JSON Schemas]({base}api/v1/schemas/index.json): one per response and record type",
        f"- [Site summaries]({base}api/v1/sites.json): one entry per site, sorted by name",
        f"- [Sites GeoJSON]({base}api/v1/sites.geojson): every site as a GeoJSON feature",
        f"- One site: {base}api/v1/sites/{{site_id}}.json (also .geojson); one project: "
        f"{base}api/v1/projects/{{project_id}}.json; one evidence row: {base}api/v1/evidence/{{evidence_id}}.json",
        f"- [Countries]({base}api/v1/countries.json): per country {base}api/v1/countries/{{iso2}}.json, .geojson and .csv",
        f"- [Statistics]({base}api/v1/stats.json): counts by status, month, country and more, with units",
        f"- [Vocabularies]({base}api/v1/vocabularies.json): labels and meanings of every coded value",
        f"- [Data history]({base}api/v1/versions.json): snapshots with files, checksums and record-level changes",
        f"- [Citation]({base}api/v1/citation.json): APA, BibTeX, RIS and CSL-JSON",
        "",
        "## Downloads",
        "",
        f"- [All files (zip)]({latest}datacenter-atlas-{LATEST}.zip): every file below in one archive",
        f"- [sites.csv]({latest}sites.csv), [projects.csv]({latest}projects.csv), [evidence.csv]({latest}evidence.csv): "
        "the three tables (UTF-8; empty cells are unknown)",
        f"- [atlas.sqlite]({latest}atlas.sqlite): SQLite database with link and observation tables",
        f"- [atlas.json]({latest}atlas.json): every typed record in one JSON document",
        f"- [atlas.xlsx]({latest}atlas.xlsx): Excel workbook",
        f"- [datapackage.json]({latest}datapackage.json): Frictionless Data Package with table schemas",
        f"- [SHA256SUMS]({latest}SHA256SUMS): checksums of every file",
        f"- [Current archived snapshot]({base}downloads/{current.id}/): original data files remain unchanged",
        "",
        "## Docs",
        "",
        f"- [Methodology]({base}methodology/): sources, construction statuses and location precision",
        f"- [Field dictionary]({base}data/dictionary/): every column, type and coded value",
        f"- [API guide]({base}api/): endpoints, fields and examples",
        f"- [Data history]({base}versions/): additions, corrections and earlier snapshots",
        f"- [Attribution and legal notices]({base}about/attribution/): source terms and required notices",
        f"- [About and citation]({base}about/#cite)",
        "",
        "## Optional",
        "",
        f"- [Full guide for language models]({base}llms-full.txt): methodology, field dictionary and vocabularies "
        "in one text file",
        f"- [Data updates feed]({base}feed.xml) and [new sites feed]({base}sites-feed.xml)",
        f"- [Source repository]({config.repository_url})",
    ]
    return "\n".join(lines) + "\n"


class _TextExtractor(HTMLParser):
    """Plain text of builder or content HTML: headings become Markdown headings, list items bullets."""

    BLOCKS = {"p", "div", "section", "dl", "ul", "ol", "table", "tr", "pre", "details", "summary"}
    SKIPPED = {"script", "style", "button", "nav"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIPPED:
            self.skip += 1
        elif self.skip:
            return
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in {"li", "dt"}:
            self.parts.append("\n- ")
        elif tag == "dd":
            self.parts.append(": ")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIPPED:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and (tag in self.BLOCKS or tag in {"h1", "h2", "h3", "h4"}):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in joined.splitlines()]
        lines = [re.sub(r"^#+ (.*?) #$", lambda match: match.group(0)[:-2], line) for line in lines]
        text = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _html_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return parser.text()


def _llms_full_txt(context: _Context) -> str:
    """llms-full.txt: methodology, field dictionary, vocabularies and endpoints as plain text.

    Only Atlas-authored text is included (site content, field descriptions, vocabularies); no
    third-party evidence titles or site names, so untrusted text never reaches an agent this way.
    """
    atlas = context.atlas
    descriptions = context.descriptions
    sections = [_llms_txt(context).rstrip("\n"), "",
                _html_text(_render_fragment(context, "content/methodology.html", context.base_url)).rstrip("\n")]
    sections += ["", "# Field dictionary", ""]
    for file_name in TABLE_FILES:
        sections.append(f"## {file_name}")
        sections.append("")
        table_descriptions = descriptions.get("tables", {}).get(file_name, {})
        for spec in atlas.fields[file_name]:
            name = spec["name"]
            empty = "may be empty (unknown)" if spec.get("allows_empty_string") else "always present"
            sections.append(
                f"- {name} (JSON: {typed_field_name(name)}; {spec.get('logical_type', 'string')}; {empty}): "
                f"{table_descriptions.get(name, '')}"
            )
        sections.append("")
    sections += ["## Derived API fields", ""]
    for table, items in (descriptions.get("derived") or {}).items():
        for name, description in items.items():
            sections.append(f"- {table}.{name}: {description}")
    for key, title in (("site_summary", "Site summary fields"), ("stats", "stats.json"), ("counts", "Counts")):
        sections += ["", f"## {title}", ""]
        sections += [f"- {name}: {text}" for name, text in (descriptions.get(key) or {}).items() if isinstance(text, str)]
    sections += ["", "# Coded values", ""]
    for name, entries in context.vocabularies.items():
        sections.append(f"## {name}")
        sections.append("")
        for code, entry in entries.items():
            unit = f" [{entry['unit']}]" if entry.get("unit") else ""
            sections.append(f"- {code}: {entry.get('label')}{unit}. {entry.get('description', '')}".rstrip())
        sections.append("")
    sections += ["# Endpoints", ""]
    sections += [f"- {context.base_url}{path}: {ENDPOINT_DESCRIPTIONS[key]}" for key, path in _endpoint_paths().items()]
    citations = _citations(context)
    sections += ["", "# Citation", "", citations["apa"], "", citations["bibtex"], ""]
    return "\n".join(sections).rstrip("\n") + "\n"


# --------------------------------------------------------------------------------------------
# Feed, sitemap, robots


def _feed_id(context: _Context, suffix: str) -> str:
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, context.config.repository_url + suffix)}"


def _write_feed(writer: _Writer, context: _Context) -> None:
    base = context.base_url
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
        change = context.history[version.id]
        added, removed = change.ids("sites.csv", "added"), change.ids("sites.csv", "removed")
        counts = version.counts
        summary = (
            f"{counts.get('physical_sites')} sites, {counts.get('projects')} projects, {counts.get('countries')} countries, "
            f"{counts.get('evidence')} evidence rows; {len(added)} sites added, {len(removed)} removed. "
            f"Data archived on {version.checkpoint_date}."
        )
        names = change.labels["sites"]
        added_items = "".join(f"<li>{_e(names.get(site_id, site_id))}</li>" for site_id in added[:50])
        more = f"<p>…and {len(added) - 50} more.</p>" if len(added) > 50 else ""
        content = (
            f"<p>{_e(summary)}</p><p>Changes: {_e(_change_summary(change))}.</p>"
            + (f"<p>Sites added:</p><ul>{added_items}</ul>{more}" if added else "")
        )
        lines += [
            "<entry>",
            f"<title>{_x(version.label)}</title>",
            f"<id>{_x(_feed_id(context, '#dataset/' + version.id))}</id>",
            f"<updated>{version.checkpoint_date}T00:00:00Z</updated>",
            f'<link rel="alternate" type="text/html" href="{_x(base)}versions/{_x(version.id)}/"/>',
            f'<link rel="related" type="application/json" href="{_x(base)}downloads/{_x(version.id)}/manifest.json"/>',
            f"<summary>{_x(summary)}</summary>",
            f'<content type="html">{_x(content)}</content>',
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
    return _parse_json_bytes(_read_regular_bytes(path), str(path))


def _parse_json_bytes(data: bytes, where: str) -> Any:
    """Strict JSON: UTF-8, no NaN/Infinity constants and no lone UTF-16 surrogates."""
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=_reject_json_constant)
    except ValueError as error:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise PublicSiteError(f"{where}: invalid JSON ({error})") from error
    _reject_surrogates(value, where)
    return value


def _reject_surrogates(value: Any, where: str) -> None:
    """JSON escapes such as \\ud800 decode to lone surrogates, which no UTF-8 output can encode."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if LONE_SURROGATE.search(item):
                raise PublicSiteError(f"{where}: lone UTF-16 surrogate in {item[:40]!r}")
        elif isinstance(item, dict):
            for key, child in item.items():
                stack.append(key)
                stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)


def _checked_bytes(directory: Path, files: Sequence[FileRecord], name: str) -> bytes:
    """Bytes of a manifest-listed regular file, re-checked against its recorded size and SHA-256."""
    record = next((item for item in files if item.name == name), None)
    if record is None:
        raise PublicSiteError(
            f"{directory.name}/{name} is not listed in manifest.json; the builder reads only hash-checked files"
        )
    data = _read_regular_bytes(directory / name)
    if len(data) != record.size or _sha256(data) != record.sha256:
        raise PublicSiteError(f"{directory / name} changed after validation (size or SHA-256 differs)")
    return data


def _verified_bytes(version: DatasetVersion, name: str) -> bytes:
    return _checked_bytes(version.path, version.files, name)


def _verified_text(version: DatasetVersion, name: str) -> str:
    try:
        return _verified_bytes(version, name).decode("utf-8")
    except UnicodeDecodeError as error:
        raise PublicSiteError(f"{version.id}/{name}: not valid UTF-8 ({error})") from error


def _verified_json(version: DatasetVersion, name: str) -> Any:
    return _parse_json_bytes(_verified_bytes(version, name), f"{version.id}/{name}")
