"""Static public site: full build of the real current dataset plus a hostile synthetic fixture."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
from html import escape as html_escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET
import zipfile

try:
    from datacenter_atlas import public_site
except ImportError:  # the repository used as a package without the editable install
    from datacenter_atlas.datacenter_atlas import public_site
from datacenter_atlas import models


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "0123456789abcdef0123456789abcdef01234567"
KML = "{http://www.opengis.net/kml/2.2}"
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
LOCAL = "https://local.invalid/"
LAYOUT_CLASSES = {
    "skip-link", "site-header", "brand", "site-nav", "site-footer", "explorer",
}
VOCABULARY_CLASSES = {
    "page", "page-wide", "lede", "muted", "small", "mono", "breadcrumbs", "stats", "stat", "stat-value",
    "stat-label", "badge", "tag", "btn", "btn-primary", "btn-small", "card", "cards", "grid-2", "kv",
    "table-wrap", "data-table", "num", "callout", "callout-warning", "code", "copy-btn", "toc",
    "download-list", "checksum", "site-map", "evidence-list", "project", "filter-input", "sortable",
    "hidden-noscript", "external", "anchor",
}
# Pages whose <main> content comes from the frontend and docs fragments (site/templates, site/content).
FRAGMENT_PAGES = {"index.html", "methodology/index.html", "about/index.html"}
DERIVED = {
    "sites.csv": ["official_boundary", "country_slug", "url", "api_url", "geometry_licenses", "geometry_attributions"],
    "projects.csv": ["evidence_ids", "status_source", "url", "api_url", "geometry_source"],
    "evidence.csv": ["site_ids", "url", "api_url", "archive_url"],
}
SITE_SUMMARY_KEYS = [
    "site_id", "name", "country", "country_iso_a2", "latitude", "longitude", "geometry_type",
    "official_boundary", "locator_scopes", "statuses", "newest_status_as_of", "oldest_status_as_of",
    "project_count", "projects", "status_publishers", "power_observations", "verification_posture",
    "independent_imagery_verification", "url", "api_url", "geometry_licenses", "geometry_attributions",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): sha256(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def ring_sets(geometry):
    """A geometry with every ring as a set of positions, so ring orientation does not matter."""
    kind = geometry.get("type")
    if kind == "Polygon":
        return kind, [frozenset(map(tuple, ring)) for ring in geometry["coordinates"]]
    if kind == "MultiPolygon":
        return kind, [[frozenset(map(tuple, ring)) for ring in polygon] for polygon in geometry["coordinates"]]
    return kind, geometry.get("coordinates")


def follows_right_hand_rule(geometry) -> bool:
    """RFC 7946: exterior rings counterclockwise, holes clockwise (planar shoelace sign)."""
    polygons = {"Polygon": [geometry.get("coordinates")], "MultiPolygon": geometry.get("coordinates")}.get(
        geometry.get("type"), []
    )
    for polygon in polygons:
        for index, ring in enumerate(polygon):
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
            if area and (area > 0) != (index == 0):
                return False
    return True


def version_dirs() -> list[Path]:
    config = read_json(ROOT / "site" / "config.json")
    return sorted(path for path in (ROOT / config["versions_root"]).iterdir() if (path / "manifest.json").is_file())


class PageScan(HTMLParser):
    """Collects links, ids, classes, meta tags, scripts and inline attributes of one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self.id_list: list[str] = []
        self.classes: set[str] = set()
        self.meta: list[dict[str, str | None]] = []
        self.scripts: list[dict[str, str | None]] = []
        self.stylesheets: list[str] = []
        self.inline_attributes: list[str] = []
        self.data_blocks: dict[str, str] = {}
        self._block: str | None = None
        self._text: list[str] = []

    @property
    def ids(self) -> set[str]:
        return set(self.id_list)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.id_list.append(attributes["id"])
        self.classes.update((attributes.get("class") or "").split())
        for name in ("href", "src"):
            if attributes.get(name) is not None:
                self.links.append((tag, name, attributes[name]))
        if tag == "meta":
            self.meta.append(attributes)
        if tag == "script":
            self.scripts.append(attributes)
            if attributes.get("type") in {"application/json", "application/ld+json"}:
                self._block = attributes.get("id") or attributes.get("type")
                self._text = []
        if tag == "link" and "stylesheet" in (attributes.get("rel") or "").split():
            self.stylesheets.append(attributes.get("href") or "")
        self.inline_attributes += [name for name in attributes if name == "style" or name.startswith("on")]

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        if self._block is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._block is not None:
            self.data_blocks[self._block] = "".join(self._text)
            self._block = None


def scan(path: Path) -> PageScan:
    parser = PageScan()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


class VisibleProse(HTMLParser):
    """Ordinary page text, excluding code, embedded data and technical file names."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "pre", "code"}:
            self.skipped.append(tag)

    def handle_endtag(self, tag):
        if self.skipped and tag == self.skipped[-1]:
            self.skipped.pop()

    def handle_data(self, data):
        if self.skipped:
            return
        text = data.strip()
        if text and not re.fullmatch(r"(?:https?://\S+|[\w.-]+\.(?:zip|json|csv|geojson|md|txt))", text):
            self.parts.append(text)


def builder_pages(site: Path) -> list[Path]:
    """Every HTML page the builder wrote: dataset originals under downloads/ (such as the preview
    map.html files) are excluded, the builder's index.html landing pages there are included."""
    return sorted(
        path for path in site.rglob("*.html")
        if path.relative_to(site).parts[0] != "downloads" or path.name == "index.html"
    )


def link_problems(site: Path, base_url: str) -> list[str]:
    """Internal href/src values that do not resolve to an output file (or a missing #fragment)."""
    problems: list[str] = []
    id_cache: dict[Path, set[str]] = {}

    def ids_of(path: Path) -> set[str]:
        if path not in id_cache:
            id_cache[path] = scan(path).ids
        return id_cache[path]

    for page in builder_pages(site):
        relative = page.relative_to(site).as_posix()
        for tag, attribute, value in scan(page).links:
            url = LOCAL + value[len(base_url):] if value.startswith(base_url) else value
            scheme = urlsplit(url).scheme.lower()
            if scheme and scheme not in {"http", "https"}:
                problems.append(f"{relative}: <{tag} {attribute}> has scheme {scheme!r}: {value}")
                continue
            resolved = urlsplit(urljoin(LOCAL + relative, url))
            if f"{resolved.scheme}://{resolved.netloc}/" != LOCAL:
                continue
            target = site / unquote(resolved.path.lstrip("/"))
            if resolved.path.endswith("/") or target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                problems.append(f"{relative}: <{tag} {attribute}> {value} -> missing {target.relative_to(site)}")
                continue
            fragment = unquote(resolved.fragment)
            # "#site=<id>" is explorer state read by app.js, not an element id.
            if fragment and "=" not in fragment and target.suffix == ".html" and fragment not in ids_of(target):
                problems.append(f"{relative}: {value} -> no element with id {fragment!r}")
    return problems


class SchemaCheck:
    """A small JSON Schema (2020-12) checker for the subset the builder emits, plus one strict rule:
    an object schema with "properties" and no "additionalProperties" must declare every key."""

    DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
    URI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")

    def __init__(self, directory: Path) -> None:
        self.schemas = {path.name: read_json(path) for path in directory.glob("*.schema.json")}

    def errors(self, instance, schema, where: str = "$") -> list[str]:
        if "$ref" in schema:
            return self.errors(instance, self.schemas[schema["$ref"]], where)
        problems: list[str] = []
        for part in schema.get("allOf", []):
            problems += self.errors(instance, part, where)
        if "anyOf" in schema and all(self.errors(instance, part, where) for part in schema["anyOf"]):
            problems.append(f"{where}: matches no anyOf branch")
        kinds = schema.get("type")
        if kinds is not None and not any(self._is(instance, kind) for kind in ([kinds] if isinstance(kinds, str) else kinds)):
            return problems + [f"{where}: {type(instance).__name__} is not {kinds}"]
        if "const" in schema and instance != schema["const"]:
            problems.append(f"{where}: {instance!r} != const {schema['const']!r}")
        if "enum" in schema and instance not in schema["enum"]:
            problems.append(f"{where}: {instance!r} not in enum")
        if isinstance(instance, str):
            if "pattern" in schema and not re.search(schema["pattern"], instance):
                problems.append(f"{where}: {instance!r} does not match {schema['pattern']}")
            if schema.get("format") == "date" and not self.DATE.fullmatch(instance):
                problems.append(f"{where}: {instance!r} is not a date")
            if schema.get("format") == "uri" and not self.URI.match(instance):
                problems.append(f"{where}: {instance!r} is not a URI")
        if isinstance(instance, dict):
            for key in schema.get("required", []):
                if key not in instance:
                    problems.append(f"{where}: missing {key}")
            properties = schema.get("properties", {})
            extra = schema.get("additionalProperties")
            for key, value in instance.items():
                if key in properties:
                    problems += self.errors(value, properties[key], f"{where}.{key}")
                elif isinstance(extra, dict):
                    problems += self.errors(value, extra, f"{where}.{key}")
                elif extra is False or ("properties" in schema and extra is None):
                    problems.append(f"{where}: undeclared key {key!r}")
        if isinstance(instance, list) and "items" in schema:
            for index, item in enumerate(instance):
                problems += self.errors(item, schema["items"], f"{where}[{index}]")
        return problems

    @staticmethod
    def _is(value, kind: str) -> bool:
        return {
            "null": value is None,
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "string": isinstance(value, str),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }[kind]


def api_schema_for(relative: str) -> tuple[str, bool] | None:
    """(schema file, is an array of that schema) of one api/v1 file, or None for non-JSON files."""
    fixed = {
        "index.json": ("index", False), "sites.json": ("site-summary", True), "sites.geojson": ("feature-collection", False),
        "projects.json": ("project", True), "evidence.json": ("evidence", True),
        "countries.json": ("country-summary", True), "stats.json": ("stats", False), "versions.json": ("versions", False),
        "vocabularies.json": ("vocabularies", False), "citation.json": ("citation", False),
        "schemas/index.json": ("schema-index", False),
    }
    if relative in fixed:
        name, many = fixed[relative]
        return f"{name}.schema.json", many
    folder, _, name = relative.partition("/")
    patterns = {
        ("sites", ".json"): "site-document", ("sites", ".geojson"): "feature-collection",
        ("projects", ".json"): "project-document", ("evidence", ".json"): "evidence-document",
        ("countries", ".json"): "country-document", ("countries", ".geojson"): "feature-collection",
    }
    schema = patterns.get((folder, Path(name).suffix))
    return (f"{schema}.schema.json", False) if schema and "/" not in name else None


# --------------------------------------------------------------------------------------------
# Synthetic fixture: 2 sites, 3 projects, 4 evidence rows, one earlier preview, hostile strings.

EVIL_NAME = 'Evil <script>alert(1)</script> & "Co" Campus'
EVIL_TITLE = "Status <img src=x onerror=alert(2)> report"
EVIL_TAGLINE = 'Fixture <b>bold</b> & "quoted" tagline'
FIXTURE_PREVIEW = "2026-01-01-preview-v0.1"
FIXTURE_DRAFT = "2026-01-01-v0.2-draft-initial-two"
SITE_A, SITE_B = "vcc-site-aaaa", "vcc-site-bbbb"
P1, P2, P3 = "p-0001", "p-0002", "p-0003"
E1, E2, E3, E4, E5 = "e-0001", "e-0002", "e-0003", "e-0004", "e-0005"
GEOMETRY_URL = "https://example.org/geometry?x=1&y=2"


def _field(name: str, logical_type: str = "string", allows_empty: bool = False) -> dict:
    return {"allows_empty_string": allows_empty, "logical_type": logical_type, "name": name}


SITE_FIELDS = [
    _field("site_id"), _field("name"), _field("country"), _field("country_iso_a2"),
    _field("latitude", "number"), _field("longitude", "number"),
    _field("geometry_json", "geojson_geometry"), _field("geometry_type"),
    _field("geometry_use_scopes_json", "json_array"),
    _field("horizontal_uncertainty_metres", "number", True),
    _field("horizontal_uncertainty_unknown_reason", allows_empty=True),
    _field("geometry_evidence_ids_json", "json_array"), _field("project_count", "integer"),
    _field("project_ids_json", "json_array"), _field("statuses_json", "json_array"),
    _field("oldest_status_as_of", "date"), _field("newest_status_as_of", "date"),
    _field("verification_posture"), _field("independent_imagery_verification", "boolean"),
    _field("local_note", "fixture_only_type", True),
]
PROJECT_FIELDS = [
    _field("project_id"), _field("site_id"), _field("name"), _field("country"), _field("country_iso_a2"),
    _field("latitude", "number"), _field("longitude", "number"), _field("geometry_json", "geojson_geometry"),
    _field("geometry_type"), _field("geometry_use_scope"), _field("geometry_authority_class"),
    _field("geometry_evidence_id"), _field("last_observed_physical_status"), _field("status_as_of", "date"),
    _field("status_age_days_at_review", "integer"), _field("status_method"), _field("status_evidence_id"),
    _field("verification_posture"), _field("independent_imagery_verification", "boolean"),
    _field("operating_model"), _field("operating_model_unknown_reason", allows_empty=True),
    _field("workloads_json", "json_array"), _field("workload_unknown_reason", allows_empty=True),
    _field("role_claims_json", "json_array"), _field("power_observations_json", "json_array"),
    _field("power_unknown_reason", allows_empty=True),
]
EVIDENCE_FIELDS = [
    _field("evidence_id"), _field("roles_json", "json_array"), _field("project_ids_json", "json_array"),
    _field("kind"), _field("title"), _field("source_url", "uri"), _field("publisher"), _field("source_family"),
    _field("license", allows_empty=True), _field("attribution", allows_empty=True),
    _field("published_at", "date_or_datetime", True), _field("retrieved_at", "date_or_datetime"),
    _field("content_hash", "sha256"),
]
POINT_A = {"coordinates": [10.5, 20.25], "type": "Point"}
POLYGON_B = {"coordinates": [[[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 1.0]]], "type": "Polygon"}
POWER = [{
    "as_of_date": "2025-12-01", "base": 15, "confidence": 0.9, "evidence_id": E3, "high": 20, "low": 10,
    "method": "reported", "metric": "critical_it_mw", "notes": "Planned <b>range</b>", "stage": "planned",
    "target_date": None, "unit": "MW",
}]
ROLE_CLAIMS = [{"evidence_id": E2, "party": "Operator <Ltd>", "relationship_scope": "intended", "role": "operator"}]
GATES = {
    "site_count": {"actual": 2, "passed": False, "reason": "fixture drafts never reach the target", "required": 100},
    "maximum_single_country_share": {"actual": 1.0, "passed": False, "required_maximum": 0.4},
    "blind_review": {
        "agreements": 0, "passed": False, "required_agreements": 19, "required_sample_size": 20,
        "sample_size": 0, "eligible_project_stable_keys": ["a", "b"],
    },
}
LEGAL_README = (
    "# Fixture preview\n\n## Legal notice\n\nFixture city notice\nTerms: https://example.org/disclaimer\n\n"
    "## Other\n\nIgnored.\n"
)


def _compact(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _site_row(site_id, name, geometry, anchor, projects, statuses, dates, uncertainty, note):
    latitude, longitude = anchor
    oldest, newest = dates
    return {
        "site_id": site_id, "name": name, "country": "Fixtureland", "country_iso_a2": "ZZ",
        "latitude": latitude, "longitude": longitude, "geometry_json": _compact(geometry),
        "geometry_type": geometry["type"], "geometry_use_scopes_json": _compact(["campus_locator"]),
        "horizontal_uncertainty_metres": uncertainty,
        "horizontal_uncertainty_unknown_reason": "" if uncertainty else "No accuracy stated.",
        "geometry_evidence_ids_json": _compact([E3]), "project_count": str(len(projects)),
        "project_ids_json": _compact(projects), "statuses_json": _compact(statuses),
        "oldest_status_as_of": oldest, "newest_status_as_of": newest,
        "verification_posture": "recent_authoritative_physical_observation_plus_reviewed_site_locator",
        "independent_imagery_verification": "false", "local_note": note,
    }


def _project_row(project_id, site_id, name, geometry, anchor, scope, status, evidence, power=(), roles=()):
    latitude, longitude = anchor
    status_code, as_of = status
    return {
        "project_id": project_id, "site_id": site_id, "name": name, "country": "Fixtureland",
        "country_iso_a2": "ZZ", "latitude": latitude, "longitude": longitude,
        "geometry_json": _compact(geometry), "geometry_type": geometry["type"], "geometry_use_scope": scope,
        "geometry_authority_class": "official_source", "geometry_evidence_id": E3,
        "last_observed_physical_status": status_code, "status_as_of": as_of, "status_age_days_at_review": "30",
        "status_method": "authoritative_physical_status_update", "status_evidence_id": evidence,
        "verification_posture": "recent_authoritative_physical_observation_plus_reviewed_site_locator",
        "independent_imagery_verification": "false", "operating_model": "unknown",
        "operating_model_unknown_reason": "not established by selected evidence", "workloads_json": "[]",
        "workload_unknown_reason": "not established", "role_claims_json": _compact(list(roles)),
        "power_observations_json": _compact(list(power)),
        "power_unknown_reason": "" if power else "no typed project power observation; not estimated",
    }


def _evidence_row(evidence_id, roles, projects, title, url, published):
    return {
        "evidence_id": evidence_id, "roles_json": _compact(roles), "project_ids_json": _compact(projects),
        "kind": "company_disclosure", "title": title, "source_url": url, "publisher": f"Publisher {evidence_id}",
        "source_family": "fixture", "license": "CC-BY-4.0", "attribution": "Fixture & Co",
        "published_at": published, "retrieved_at": "2026-01-02T00:00:00Z",
        "content_hash": hashlib.sha256(evidence_id.encode()).hexdigest(),
    }


def _write_csv(path: Path, fields: list[dict], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([field["name"] for field in fields])
        for row in rows:
            writer.writerow([row[field["name"]] for field in fields])


def _counts(sites: list[dict], projects: list[dict], evidence: list[dict]) -> dict:
    boundary = sum(1 for row in projects if row["geometry_use_scope"] == "official_boundary")
    return {
        "countries": len({row["country_iso_a2"] for row in sites}), "evidence": len(evidence),
        "non_us_sites": len(sites), "official_boundary_projects": boundary, "physical_sites": len(sites),
        "projects": len(projects), "reviewed_site_locator_projects": len(projects) - boundary,
    }


def _write_dataset(directory: Path, *, sites, projects, evidence, manifest: dict, report: dict, readme: str):
    directory.mkdir(parents=True)
    _write_csv(directory / "sites.csv", SITE_FIELDS, sites)
    _write_csv(directory / "projects.csv", PROJECT_FIELDS, projects)
    _write_csv(directory / "evidence.csv", EVIDENCE_FIELDS, evidence)
    features = [
        {"geometry": json.loads(row["geometry_json"]), "id": row["site_id"], "properties": {}, "type": "Feature"}
        for row in sites
    ]
    collection = _compact({"features": features, "type": "FeatureCollection"})
    (directory / "sites.geojson").write_text(collection + "\n", encoding="utf-8")
    schema = {
        "foreign_keys": [
            {"from": ["projects.csv", "site_id"], "to": ["sites.csv", "site_id"]},
            {"from": ["projects.csv", "status_evidence_id"], "to": ["evidence.csv", "evidence_id"]},
            {"from": ["projects.csv", "geometry_evidence_id"], "to": ["evidence.csv", "evidence_id"]},
        ],
        "json_embedded_evidence_fields": [
            ["projects.csv", "power_observations_json", "evidence_id"],
            ["projects.csv", "role_claims_json", "evidence_id"],
        ],
        "tables": {
            "sites.csv": {"fields": SITE_FIELDS, "primary_key": ["site_id"]},
            "projects.csv": {"fields": PROJECT_FIELDS, "primary_key": ["project_id"]},
            "evidence.csv": {"fields": EVIDENCE_FIELDS, "primary_key": ["evidence_id"]},
        },
    }
    (directory / "schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    (directory / "selection-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (directory / "README.md").write_text(readme, encoding="utf-8")
    (directory / "ATTRIBUTION.txt").write_text(
        "Fixture attribution\n- Publisher <x> | CC-BY-4.0 | https://example.org/terms?a=1&b=2.\n", encoding="utf-8"
    )
    files = {}
    for path in sorted(directory.iterdir()):
        data = path.read_bytes()
        files[path.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    document = {**manifest, "counts": _counts(sites, projects, evidence), "files": files, "publishable_as_final": False}
    manifest_bytes = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (directory / "manifest.json").write_bytes(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    (directory / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")


def _reseal(directory: Path, *, drop: tuple[str, ...] = (), add: tuple[str, ...] = ()) -> None:
    """Re-hash the manifest-listed files of a fixture version (minus ``drop``, plus ``add``)."""
    document = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    names = (set(document["files"]) - set(drop)) | set(add)
    files = {}
    for name in sorted(names):
        data = (directory / name).read_bytes()
        files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    document["files"] = files
    manifest_bytes = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (directory / "manifest.json").write_bytes(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    (directory / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")


def _write_site_inputs(site: Path, about: str | None) -> None:
    default_about = (
        "<h1>About {{site_name}}</h1><p>{{versions.count}} versions; built {{build.commit_short}}; "
        "cite as ({{dataset.checkpoint_year}}).</p>"
    )
    files = {
        "static/assets/site.css": "body{margin:0}\n",
        "static/assets/app.js": "'use strict';\n",
        "static/assets/site.js": "'use strict'; // site\n",
        "static/assets/site-map.js": "'use strict'; // map\n",
        "static/assets/vendor/leaflet/leaflet.js": "/* leaflet */\n",
        "static/assets/vendor/leaflet/leaflet.css": "/* leaflet */\n",
        "static/favicon.svg": '<svg xmlns="http://www.w3.org/2000/svg"/>\n',
        "templates/explorer.html": (
            "<!-- explorer fixture: {{not_a_token}} inside a comment is ignored -->\n"
            '<h1>{{site_name}}</h1><p class="lede">{{tagline}} — {{counts.physical_sites}} sites, window '
            '{{dataset.window_start}} to {{dataset.lifecycle_reference_date}}.</p><div id="atlas-map"></div>'
            '<p><a href="{{root}}sites/">Sites</a></p>'
        ),
        "content/methodology.html": (
            '<h1>Methodology</h1><section id="release-gates"><h2>Gates</h2>{{{gates_table}}}</section>'
            "{{{status_legend}}}<p>{{last_preview.label}}; sites: {{last_preview.counts.physical_sites}}.</p>"
        ),
        "content/about.html": default_about if about is None else about,
    }
    if about is None:
        files["content/about.html"] += "<section id=\"cite\">{{{citation_block}}}</section>"
    for relative, text in files.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    shutil.copyfile(ROOT / "site" / "vocabulary.json", site / "vocabulary.json")
    shutil.copyfile(ROOT / "site" / "field_descriptions.json", site / "field_descriptions.json")
    config = read_json(ROOT / "site" / "config.json")
    config.update({
        "tagline": EVIL_TAGLINE,
        "versions_root": "verified_construction_core",
        "current_dataset": f"verified_construction_core/{FIXTURE_DRAFT}",
        "last_preview_dataset": f"verified_construction_core/{FIXTURE_PREVIEW}",
    })
    (site / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def make_fixture_root(base: Path, *, about: str | None = None) -> Path:
    """Write a complete repository-shaped fixture (site/ inputs plus two dataset versions)."""
    root = base / "repo"
    _write_site_inputs(root / "site", about)
    versions = root / "verified_construction_core"
    site_a = _site_row(SITE_A, EVIL_NAME, POINT_A, ("20.25", "10.5"), [P1], ["under_construction"],
                       ("2025-12-01", "2025-12-01"), "", "free <note>")
    site_b = _site_row(SITE_B, "Beta Campus", POLYGON_B, ("1.5", "1.25"), [P2, P3], ["shell", "site_preparation"],
                       ("2025-11-15", "2025-12-10"), "25", "")
    project_1 = _project_row(P1, SITE_A, "Evil project", POINT_A, ("20.25", "10.5"), "campus_locator",
                             ("under_construction", "2025-12-01"), E1, power=POWER)
    project_2 = _project_row(P2, SITE_B, "Beta shell", POLYGON_B, ("1.5", "1.25"), "campus_locator",
                             ("shell", "2025-12-10"), E2, roles=ROLE_CLAIMS)
    project_3 = _project_row(P3, SITE_B, "Beta boundary", POLYGON_B, ("1.5", "1.25"), "official_boundary",
                             ("site_preparation", "2025-11-15"), E4)
    status_1 = _evidence_row(E1, ["physical_status"], [P1], "Status of the evil site", "javascript:alert(1)", "2025-12-01")
    geometry_roles = ["geometry", "typed_metric:critical_it_mw"]
    retired = _evidence_row(E5, ["context:project_context"], [P1], "Retired source", "https://example.org/retired", "")
    _write_dataset(
        versions / FIXTURE_PREVIEW,
        sites=[site_a],
        projects=[project_1],
        evidence=[status_1, _evidence_row(E3, geometry_roles, [P1], EVIL_TITLE, GEOMETRY_URL, ""), retired],
        manifest={"release_status": "preview", "reviewed_at": "2025-12-20", "preview_id": FIXTURE_PREVIEW},
        report={"final_release_gates": GATES, "publishable_as_final": False},
        readme=LEGAL_README,
    )
    # The draft corrects one field of P1 and drops the retired evidence row E5.
    corrected = {**project_1, "operating_model_unknown_reason": "not established by the selected evidence"}
    _write_dataset(
        versions / FIXTURE_DRAFT,
        sites=[site_a, site_b],
        projects=[corrected, project_2, project_3],
        evidence=[
            status_1,
            _evidence_row(E2, ["physical_status", "role:operator"], [P2, P3], "Beta status",
                          "https://example.org/beta", "2025-12-10"),
            _evidence_row(E3, geometry_roles, [P1, P2, P3], EVIL_TITLE, GEOMETRY_URL, ""),
            _evidence_row(E4, ["physical_status"], [P3], "Boundary status", "https://example.org/boundary", "2025-11-15"),
        ],
        manifest={"release_status": "draft", "draft_id": "2026-01-01-v0.2-draft-initial-two-2026-01-05"},
        report={"final_release_gates": GATES, "lifecycle_reference_date": "2025-12-31", "publishable_as_final": False},
        readme="# Fixture draft\n",
    )
    return root


# --------------------------------------------------------------------------------------------


class TypedConversionTests(unittest.TestCase):
    def test_values_follow_logical_types(self):
        convert = public_site.convert_value
        for logical in ("string", "number", "integer", "boolean", "json_array", "geojson_geometry", "date", "uri"):
            self.assertIsNone(convert("", logical))
        self.assertEqual(convert("12", "number"), 12.0)
        self.assertIsInstance(convert("12", "number"), float)
        self.assertEqual(convert("-1.5e3", "number"), -1500.0)
        self.assertEqual(convert("500", "integer"), 500)
        self.assertIsInstance(convert("500", "integer"), int)
        self.assertIs(convert("true", "boolean"), True)
        self.assertIs(convert("false", "boolean"), False)
        self.assertEqual(convert('["a",1]', "json_array"), ["a", 1])
        self.assertEqual(convert('{"type":"Point","coordinates":[1,2]}', "geojson_geometry")["coordinates"], [1, 2])
        self.assertEqual(convert("2026-08-20", "date"), "2026-08-20")
        self.assertEqual(convert(" keep  as is ", "some_future_type"), " keep  as is ")
        invalid = (
            ("abc", "number"), ("1_000", "number"), ("NaN", "number"), ("inf", "number"), ("1.0", "integer"),
            ("TRUE", "boolean"), ("yes", "boolean"), ("{}", "json_array"), ("[1]", "geojson_geometry"),
            ("[NaN]", "json_array"), ("[1,", "json_array"),
        )
        for value, logical in invalid:
            with self.subTest(value=value, logical=logical), self.assertRaises(public_site.PublicSiteError):
                convert(value, logical)

    def test_json_suffix_is_dropped_and_order_kept(self):
        self.assertEqual(public_site.typed_field_name("statuses_json"), "statuses")
        self.assertEqual(public_site.typed_field_name("geometry_json"), "geometry")
        self.assertEqual(public_site.typed_field_name("_json"), "_json")
        self.assertEqual(public_site.typed_field_name("json_count"), "json_count")
        fields = [_field("b_json", "json_array"), _field("a", "integer"), _field("c", "boolean"), _field("d", allows_empty=True)]
        record = public_site.convert_row({"b_json": "[]", "a": "3", "c": "false", "d": ""}, fields)
        self.assertEqual(list(record), ["b", "a", "c", "d"])
        self.assertEqual(record, {"b": [], "a": 3, "c": False, "d": None})


class TokenTests(unittest.TestCase):
    def test_text_is_escaped_and_html_is_inserted(self):
        rendered = public_site.render_tokens(
            "<p>{{name}} {{ name }}</p>{{{table}}}", {"name": "<b>&"}, {"table": "<table></table>"}, source="t"
        )
        self.assertEqual(rendered, "<p>&lt;b&gt;&amp; &lt;b&gt;&amp;</p><table></table>")

    def test_unknown_or_misused_tokens_fail(self):
        for template in ("{{missing}}", "{{{missing}}}", "{{{name}}}", "{{table}}", "{{ bad token }}", "{{name"):
            with self.subTest(template=template), self.assertRaises(public_site.PublicSiteError):
                public_site.render_tokens(template, {"name": "x"}, {"table": "<t>"}, source="t")
        self.assertEqual(public_site.render_tokens('{"a":{"b":1}}', {}, {}, source="t"), '{"a":{"b":1}}')

    def test_fallback_label_title_cases_codes(self):
        self.assertEqual(public_site.fallback_label("open_map_record"), "Open Map Record")
        self.assertEqual(public_site.fallback_label("context:new_kind"), "Context: New Kind")


class FixtureBuildTests(unittest.TestCase):
    base_url = "http://127.0.0.1:8000/sub/"

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="atlas-site-fixture-")
        cls.base = Path(cls.temp.name)
        cls.root = make_fixture_root(cls.base)
        cls.site = cls.base / "out"
        cls.summary = public_site.build_site(cls.site, root=cls.root, base_url=cls.base_url)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def page(self, relative: str) -> str:
        return (self.site / relative).read_text(encoding="utf-8")

    def test_counts_and_versions(self):
        self.assertEqual((self.summary["sites"], self.summary["projects"], self.summary["evidence"]), (2, 3, 4))
        versions = read_json(self.site / "api/v1/versions.json")
        self.assertEqual([item["id"] for item in versions["versions"]], [FIXTURE_PREVIEW, FIXTURE_DRAFT])
        preview, draft = versions["versions"]
        self.assertEqual(preview["label"], "2025-12-20 · 1 site")
        self.assertEqual(draft["label"], "2026-01-05 · 2 sites")
        self.assertEqual((preview["checkpoint_date"], draft["checkpoint_date"]), ("2025-12-20", "2026-01-05"))
        self.assertEqual(draft["lifecycle_reference_date"], "2025-12-31")
        self.assertEqual(preview["added_site_ids"], [SITE_A])
        self.assertEqual((draft["added_site_ids"], draft["removed_site_ids"]), ([SITE_B], []))
        changes = draft["changes"]
        self.assertEqual(changes["previous"], FIXTURE_PREVIEW)
        self.assertEqual(changes["projects"], {
            "added": [P2, P3], "removed": [], "changed": [{"id": P1, "fields": ["operating_model_unknown_reason"]}],
        })
        self.assertEqual(changes["evidence"]["removed"], [E5])
        self.assertEqual(changes["evidence"]["changed"], [{"id": E3, "fields": ["project_ids_json"]}])
        self.assertEqual(changes["schema"]["projects"], {"added_columns": [], "removed_columns": []})
        self.assertIsNone(preview["changes"]["previous"])
        page = self.page(f"versions/{FIXTURE_DRAFT}/index.html")
        self.assertIn("not established by selected evidence → not established by the selected evidence", page)
        self.assertIn("Retired source", page)
        self.assertIn(f'href="../../versions/{FIXTURE_PREVIEW}/"', page)
        feed = ET.parse(self.site / "feed.xml").getroot()
        links = [entry.find(f"{ATOM}link").get("href") for entry in feed.findall(f"{ATOM}entry")]
        self.assertEqual(links, [f"{self.base_url}versions/{FIXTURE_DRAFT}/", f"{self.base_url}versions/{FIXTURE_PREVIEW}/"])
        sites_feed = ET.parse(self.site / "sites-feed.xml").getroot()
        entries = sites_feed.findall(f"{ATOM}entry")
        self.assertEqual([entry.find(f"{ATOM}title").text for entry in entries], ["Beta Campus", EVIL_NAME])
        self.assertEqual(entries[0].find(f"{ATOM}updated").text, "2026-01-05T00:00:00Z")

    def test_hostile_text_is_escaped_everywhere(self):
        page = self.page(f"sites/{SITE_A}/index.html")
        self.assertIn("Evil &lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;Co&quot; Campus", page)
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("Status &lt;img src=x onerror=alert(2)&gt; report", page)
        self.assertNotIn('href="javascript:', page.lower())
        self.assertIn("javascript:alert(1)", page)  # shown as text, never linked
        self.assertIn("\\u003cscript\\u003e", page)  # inside the site-geometry JSON block
        for path in builder_pages(self.site):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", text, path)
            self.assertNotIn("<b>bold</b>", text, path)
        self.assertIn("Fixture &lt;b&gt;bold&lt;/b&gt; &amp; &quot;quoted&quot; tagline", self.page("index.html"))
        self.assertIn("Evil &lt;script&gt;", self.page("sites/index.html"))

    def test_json_blocks_are_script_safe_and_parse(self):
        block = scan(self.site / f"sites/{SITE_A}/index.html").data_blocks["site-geometry"]
        self.assertNotIn("<", block)
        feature = json.loads(block)
        self.assertEqual(feature["properties"]["name"], EVIL_NAME)
        self.assertEqual(feature["geometry"], POINT_A)
        bootstrap = json.loads(scan(self.site / "index.html").data_blocks["atlas-bootstrap"])
        self.assertEqual(bootstrap["root"], "./")
        self.assertEqual(bootstrap["endpoints"]["sites_geojson"], "api/v1/sites.geojson")
        self.assertEqual(bootstrap["dataset"]["window_start"], "2025-10-02")

    def test_typed_records_and_derived_fields(self):
        document = read_json(self.site / f"api/v1/sites/{SITE_B}.json")
        site = document["site"]
        self.assertIs(site["independent_imagery_verification"], False)
        self.assertEqual(site["horizontal_uncertainty_metres"], 25.0)
        self.assertIsNone(site["horizontal_uncertainty_unknown_reason"])
        self.assertIsNone(site["local_note"])
        self.assertIs(site["official_boundary"], True)
        self.assertNotIn("statuses_json", site)
        self.assertEqual(site["statuses"], ["shell", "site_preparation"])
        self.assertEqual(site["url"], f"{self.base_url}sites/{SITE_B}/")
        self.assertEqual([project["project_id"] for project in document["projects"]], [P3, P2])
        self.assertEqual([item["evidence_id"] for item in document["evidence"]], [E2, E4, E3])
        boundary = document["projects"][0]
        self.assertEqual(boundary["evidence_ids"], [E2, E3, E4])
        self.assertEqual(boundary["status_source"]["evidence_id"], E4)
        self.assertEqual(list(boundary["status_source"]), [
            "evidence_id", "title", "publisher", "kind", "published_at", "source_url", "license", "attribution",
        ])
        self.assertEqual(boundary["geometry_source"]["evidence_id"], E3)
        self.assertEqual(site["geometry_licenses"], ["CC-BY-4.0"])
        self.assertEqual(site["geometry_attributions"], ["Fixture & Co"])
        evil = read_json(self.site / f"api/v1/sites/{SITE_A}.json")["site"]
        self.assertEqual(evil["local_note"], "free <note>")
        self.assertIsNone(evil["horizontal_uncertainty_metres"])
        evidence = read_json(self.site / f"api/v1/evidence/{E3}.json")["evidence"]
        self.assertEqual(evidence["site_ids"], [SITE_A, SITE_B])
        self.assertIsNone(evidence["published_at"])
        self.assertEqual(evidence["url"], f"{self.base_url}api/v1/evidence/{E3}.json")
        self.assertEqual(evidence["api_url"], evidence["url"])
        self.assertEqual(evidence["archive_url"], f"https://web.archive.org/web/20260102000000/{GEOMETRY_URL}")
        unsafe = read_json(self.site / f"api/v1/evidence/{E1}.json")["evidence"]
        self.assertIsNone(unsafe["archive_url"])  # javascript: URLs get no archive link

    def test_summary_power_and_kml_escaping(self):
        summary = read_json(self.site / "api/v1/sites.json")
        self.assertEqual([item["site_id"] for item in summary], [SITE_B, SITE_A])
        self.assertEqual(summary[1]["power_observations"][0]["low"], 10)
        page = self.page(f"sites/{SITE_A}/index.html")
        self.assertIn("10–20 MW (base 15)", page)
        self.assertIn("Planned &lt;b&gt;range&lt;/b&gt;", page)
        tree = ET.parse(self.site / "downloads/latest/sites.kml")
        placemarks = tree.getroot().findall(f"{KML}Document/{KML}Placemark")
        self.assertEqual(len(placemarks), 2)
        evil = next(item for item in placemarks if item.get("id") == f"site-{SITE_A}")
        self.assertEqual(evil.find(f"{KML}name").text, EVIL_NAME)
        description = evil.find(f"{KML}description").text
        self.assertIn("&lt;script&gt;", description)  # HTML-escaped inside the XML-escaped balloon
        self.assertNotIn("<script>", description)

    def test_links_resolve_and_schemes_are_safe(self):
        self.assertEqual(link_problems(self.site, self.base_url), [])
        for path in builder_pages(self.site):
            for _, _, value in scan(path).links:
                self.assertFalse(value.lower().startswith(("javascript:", "data:", "vbscript:")), f"{path}: {value}")

    def test_tokens_render_on_content_pages(self):
        methodology = self.page("methodology/index.html")
        self.assertIn('id="release-gates-table"', methodology)
        self.assertIn("2025-12-20 · 1 site; sites: 1.", methodology)
        self.assertIn("100.0%", methodology)
        self.assertIn("agreements ≥ 19", methodology)
        self.assertIn('class="badge status-shell"', methodology)
        self.assertIn("2 versions; built local build; cite as (2026).", self.page("about/index.html"))
        self.assertNotIn("not_a_token", self.page("index.html"))
        self.assertIn("Fixture drafts never reach the target.", methodology)  # report clauses become sentences

    def test_optional_core_module_is_only_referenced_when_present(self):
        # The fixture's site/static has no assets/atlas-core.js: app.js and site-map.js load it on demand.
        for relative in ("index.html", f"sites/{SITE_A}/index.html"):
            sources = [script.get("src") for script in scan(self.site / relative).scripts if script.get("src")]
            self.assertTrue(sources, relative)
            self.assertFalse(any("atlas-core" in source for source in sources), (relative, sources))

    def test_attribution_page_linkifies_and_shows_legal_notice(self):
        page = self.page("about/attribution/index.html")
        self.assertIn("Fixture city notice", page)
        self.assertNotIn("Ignored.", page)
        self.assertIn('href="https://example.org/terms?a=1&amp;b=2"', page)
        self.assertIn("Publisher &lt;x&gt;", page)

    def test_rebuild_is_deterministic(self):
        again = self.base / "again"
        public_site.build_site(again, root=self.root, base_url=self.base_url)
        self.assertEqual(tree_hashes(again), tree_hashes(self.site))

    def test_tampered_dataset_fails_closed(self):
        def replace(name: str, old: bytes, new: bytes):
            return lambda directory: (directory / name).write_bytes((directory / name).read_bytes().replace(old, new))

        cases = {
            "content": (replace("sites.csv", b"Beta", b"Bete"), "SHA-256"),
            "size": (lambda directory: (directory / "evidence.csv").write_bytes(b"\n" * 3), "bytes"),
            "manifest": (replace("manifest.json", b'"draft"', b'"Draft"'), "manifest.sha256"),
            "missing": (lambda directory: (directory / "README.md").unlink(), "README.md"),
        }
        for name, (tamper, message) in cases.items():
            with self.subTest(name=name):
                base = Path(tempfile.mkdtemp(prefix=f"tamper-{name}-", dir=self.base))
                root = make_fixture_root(base)
                tamper(root / "verified_construction_core" / FIXTURE_DRAFT)
                with self.assertRaises(public_site.PublicSiteError) as caught:
                    public_site.build_site(base / "out", root=root)
                self.assertIn(message, str(caught.exception))
                self.assertFalse((base / "out").exists())

    def test_broken_references_and_headers_fail_with_clear_errors(self):
        base = Path(tempfile.mkdtemp(prefix="references-", dir=self.base))
        root = make_fixture_root(base)
        directory = root / "verified_construction_core" / FIXTURE_DRAFT
        projects = directory / "projects.csv"
        original = projects.read_bytes()
        cases = (  # projects.csv is written with minimal quoting: JSON cells double their quotes
            (b",e-0003,under_construction,", b",e-9999,under_construction,", "geometry_evidence_id 'e-9999'"),
            (b'""evidence_id"":""e-0003"",""high""', b'""evidence_id"":""e-9998"",""high""', "unknown evidence 'e-9998'"),
            (b"project_id,site_id,", b"project_id,site,", "found 'site', expected 'site_id'"),
        )
        for old, new, message in cases:
            with self.subTest(message=message):
                text = original.replace(old, new)
                self.assertNotEqual(text, original)
                projects.write_bytes(text)
                _reseal(directory)
                versions = public_site.discover_versions(root / "verified_construction_core")
                draft = next(version for version in versions if version.id == FIXTURE_DRAFT)
                with self.assertRaises(public_site.PublicSiteError) as caught:
                    public_site.load_atlas(draft, self.base_url)
                self.assertIn(message, str(caught.exception))

    def test_inputs_are_parsed_only_from_hash_checked_bytes(self):
        base = Path(tempfile.mkdtemp(prefix="reread-", dir=self.base))
        root = make_fixture_root(base)
        versions = public_site.discover_versions(root / "verified_construction_core")
        draft = next(version for version in versions if version.id == FIXTURE_DRAFT)
        projects = draft.path / "projects.csv"
        projects.write_bytes(projects.read_bytes().replace(b"Beta", b"Bete"))  # after validation
        with self.assertRaises(public_site.PublicSiteError) as caught:
            public_site.load_atlas(draft, self.base_url)
        self.assertIn("changed after validation", str(caught.exception))

    def test_unlisted_symlinked_and_active_originals_are_refused(self):
        def unlisted_symlink(directory: Path, base: Path) -> None:
            secret = base / "secret.txt"
            secret.write_text("SECRET-OUTSIDE-DATASET\n", encoding="utf-8")
            (directory / "ATTRIBUTION.txt").unlink()
            (directory / "ATTRIBUTION.txt").symlink_to(secret)
            _reseal(directory, drop=("ATTRIBUTION.txt",))

        def active(directory: Path, base: Path) -> None:
            (directory / "extra.html").write_text("<script>alert(1)</script>\n", encoding="utf-8")
            _reseal(directory, add=("extra.html",))

        def reserved(directory: Path, base: Path) -> None:
            (directory / "atlas.json").write_text("{}\n", encoding="utf-8")
            _reseal(directory, add=("atlas.json",))

        def unlisted_table(directory: Path, base: Path) -> None:
            _reseal(directory, drop=("schema.json",))

        cases = {
            "unlisted": (unlisted_symlink, "ATTRIBUTION.txt"),
            "active": (active, "REVIEWED_ACTIVE_ORIGINALS"),
            "reserved": (reserved, "reserved"),
            "table": (unlisted_table, "schema.json"),
        }
        for name, (tamper, message) in cases.items():
            with self.subTest(name=name):
                base = Path(tempfile.mkdtemp(prefix=f"inputs-{name}-", dir=self.base))
                root = make_fixture_root(base)
                tamper(root / "verified_construction_core" / FIXTURE_DRAFT, base)
                with self.assertRaises(public_site.PublicSiteError) as caught:
                    public_site.build_site(base / "out", root=root)
                self.assertIn(message, str(caught.exception))
                self.assertFalse((base / "out").exists())

    def test_lone_surrogates_and_long_csv_fields(self):
        with self.assertRaises(public_site.PublicSiteError):
            public_site.convert_value('["ok", "\\ud800"]', "json_array")
        self.assertEqual(public_site.convert_value('["\\ud83d\\ude00"]', "json_array"), ["\U0001f600"])
        self.assertEqual(public_site._x("a\ud800b"), "a\ufffdb")
        geometry = "x" * 200_000  # beyond the csv module's default 131,072-character field limit
        records = list(public_site._csv_records(f'site_id,geometry_json\ns-1,"{geometry}"\n', "fixture.csv"))
        self.assertEqual(len(records[1][1][1]), 200_000)

    def test_formerly_current_version_keeps_its_files(self):
        """downloads/<id>/ of a version published as current is the same whichever version is current."""
        base = Path(tempfile.mkdtemp(prefix="pinned-", dir=self.base))
        root = make_fixture_root(base)
        config = read_json(root / "site" / "config.json")
        first = f"verified_construction_core/{FIXTURE_PREVIEW}"
        builds = {}
        for current in (FIXTURE_PREVIEW, FIXTURE_DRAFT):
            path = base / f"config-{current}.json"
            path.write_text(json.dumps({
                **config, "current_dataset": f"verified_construction_core/{current}", "first_published_dataset": first,
            }), encoding="utf-8")
            builds[current] = base / f"out-{current}"
            public_site.build_site(builds[current], root=root, config_path=path, base_url=self.base_url)
        directories = [build / "downloads" / FIXTURE_PREVIEW for build in builds.values()]
        hashes = [
            {name: digest for name, digest in tree_hashes(directory).items() if name != "index.html"}
            for directory in directories
        ]
        self.assertEqual(hashes[0], hashes[1])
        for name in (f"datacenter-atlas-{FIXTURE_PREVIEW}.zip", "atlas.sqlite", "atlas.json", "datapackage.json"):
            self.assertIn(name, hashes[1])

    def test_xml_outputs_drop_invalid_control_characters(self):
        self.assertEqual(public_site._x("a\x01b<c>"), "a�b&lt;c&gt;")
        self.assertEqual(public_site._x("tab\tand\nnewline"), "tab\tand\nnewline")

    def test_unknown_template_token_is_a_build_error(self):
        base = Path(tempfile.mkdtemp(prefix="token-", dir=self.base))
        root = make_fixture_root(base, about="<h1>About</h1><p>{{no_such_token}}</p>")
        with self.assertRaises(public_site.PublicSiteError) as caught:
            public_site.build_site(base / "out", root=root)
        self.assertIn("no_such_token", str(caught.exception))
        self.assertEqual(list(base.glob(".out.*")), [])
        self.assertFalse((base / "out").exists())

    def test_methodology_does_not_require_internal_release_gates(self):
        base = Path(tempfile.mkdtemp(prefix="gates-", dir=self.base))
        root = make_fixture_root(base)
        (root / "site" / "content" / "methodology.html").write_text(
            '<h1>Methodology</h1><p>Construction stages come from dated sources.</p>', encoding="utf-8"
        )
        public_site.build_site(base / "out", root=root)
        text = (base / "out" / "methodology" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Construction stages come from dated sources.", text)
        self.assertNotIn('id="release-gates-table"', text)

    def test_output_directory_safety(self):
        base = Path(tempfile.mkdtemp(prefix="output-", dir=self.base))
        foreign = base / "foreign"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("mine", encoding="utf-8")
        for overwrite in (False, True):
            with self.assertRaises(public_site.PublicSiteError):
                public_site.build_site(foreign, root=self.root, overwrite=overwrite)
        self.assertEqual((foreign / "keep.txt").read_text(encoding="utf-8"), "mine")
        empty = base / "empty"
        empty.mkdir()
        public_site.build_site(empty, root=self.root)
        (empty / "stale.txt").write_text("old", encoding="utf-8")
        with self.assertRaises(public_site.PublicSiteError):
            public_site.build_site(empty, root=self.root)
        public_site.build_site(empty, root=self.root, overwrite=True)
        self.assertFalse((empty / "stale.txt").exists())
        self.assertTrue((empty / public_site.MARKER_NAME).is_file())
        for protected in (self.root, self.root / "site" / "out", self.root / "verified_construction_core" / "out"):
            with self.subTest(protected=protected), self.assertRaises(public_site.PublicSiteError):
                public_site.build_site(protected, root=self.root, overwrite=True)

    def test_no_duplicate_ids(self):
        for path in builder_pages(self.site):
            ids = scan(path).id_list
            self.assertEqual(len(ids), len(set(ids)), path)


class RealSiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="atlas-site-real-")
        cls.site = Path(cls.temp.name) / "site"
        cls.summary = public_site.build_site(cls.site, root=ROOT, source_commit=COMMIT)
        cls.config = read_json(ROOT / "site" / "config.json")
        cls.base_url = cls.config["base_url"]
        cls.dataset_dir = ROOT / cls.config["current_dataset"]
        cls.dataset_id = cls.dataset_dir.name
        cls.manifest = read_json(cls.dataset_dir / "manifest.json")
        cls.schema = read_json(cls.dataset_dir / "schema.json")
        cls.rows = {name: read_csv(cls.dataset_dir / name) for name in ("sites.csv", "projects.csv", "evidence.csv")}
        cls.api = cls.site / "api" / "v1"
        cls.pages = builder_pages(cls.site)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def typed_names(self, table: str) -> list[str]:
        return [public_site.typed_field_name(field["name"]) for field in self.schema["tables"][table]["fields"]]

    def json_list(self, table: str, column: str) -> list[list]:
        return [json.loads(row[column]) for row in self.rows[table]]

    def test_index_and_stats_counts_match_manifest(self):
        index = read_json(self.api / "index.json")
        stats = read_json(self.api / "stats.json")
        for key, value in self.manifest["counts"].items():
            self.assertEqual(index["dataset"]["counts"][key], value, key)
            self.assertEqual(stats["counts"][key], value, key)
        self.assertEqual(index["dataset"]["id"], self.dataset_id)
        self.assertEqual(index["dataset"]["manifest_sha256"], sha256(self.dataset_dir / "manifest.json"))
        self.assertEqual(index["build"], {"source_commit": COMMIT})
        self.assertEqual(list(index), [
            "api_version", "name", "description", "base_url", "repository_url", "dataset", "endpoints",
            "downloads", "license", "attribution_url", "docs_url", "build", "title", "caveats", "attribution",
            "citation", "citation_url", "openapi_url", "schemas_url", "llms_txt_url", "versions_url",
            "downloads_url", "dataset_files_url", "feeds", "media_type_note",
        ])
        self.assertEqual(index["license"]["openstreetmap_geometries"]["id"], "ODbL-1.0")
        self.assertEqual(set(stats["units"]), {key for key in stats if key.startswith("by_")})
        self.assertEqual(set(stats["units"].values()), {"projects", "sites", "evidence_rows", "observations"})
        for item in index["downloads"]:
            pinned = item["pinned_url"].removeprefix(self.base_url)
            self.assertTrue((self.site / pinned).is_file(), pinned)
        projects = self.rows["projects.csv"]
        self.assertEqual(Counter(stats["by_status"]), Counter(row["last_observed_physical_status"] for row in projects))
        self.assertEqual(Counter(stats["by_status_month"]), Counter(row["status_as_of"][:7] for row in projects))
        self.assertEqual(list(stats["by_status_month"]), sorted(stats["by_status_month"]))
        counts = stats["counts"]
        self.assertEqual(counts["polygon_sites"] + counts["point_sites"], counts["physical_sites"])
        powered = sum(1 for items in self.json_list("projects.csv", "power_observations_json") if items)
        self.assertEqual(counts["power_observation_projects"], powered)
        self.assertIsInstance(stats["release_gates"]["blind_review"]["eligible_project_stable_keys"], int)
        expected = tuple(self.manifest["counts"][key] for key in ("physical_sites", "projects", "evidence"))
        self.assertEqual((self.summary["sites"], self.summary["projects"], self.summary["evidence"]), expected)

    def test_every_record_has_its_page_and_json(self):
        for row in self.rows["sites.csv"]:
            self.assertTrue((self.site / "sites" / row["site_id"] / "index.html").is_file(), row["site_id"])
            self.assertTrue((self.api / "sites" / f"{row['site_id']}.json").is_file(), row["site_id"])
        for row in self.rows["projects.csv"]:
            self.assertTrue((self.api / "projects" / f"{row['project_id']}.json").is_file())
        for row in self.rows["evidence.csv"]:
            self.assertTrue((self.api / "evidence" / f"{row['evidence_id']}.json").is_file())
        countries = read_json(self.api / "countries.json")
        self.assertEqual(len(countries), self.manifest["counts"]["countries"])
        self.assertEqual({item["country_iso_a2"]: item["site_count"] for item in countries},
                         dict(Counter(row["country_iso_a2"] for row in self.rows["sites.csv"])))
        order = sorted(countries, key=lambda item: (-item["site_count"], item["country"].casefold(), item["country_iso_a2"]))
        self.assertEqual(countries, order)
        for country in countries:
            self.assertTrue((self.site / "countries" / country["slug"] / "index.html").is_file())
            document = read_json(self.api / "countries" / f"{country['country_iso_a2']}.json")
            self.assertEqual(sorted(site["site_id"] for site in document["sites"]), country["site_ids"])

    def test_typed_records_follow_schema(self):
        for row in self.rows["sites.csv"]:
            site = read_json(self.api / "sites" / f"{row['site_id']}.json")["site"]
            self.assertEqual(list(site), self.typed_names("sites.csv") + DERIVED["sites.csv"])
            self.assertIsInstance(site["latitude"], float)
            self.assertIsInstance(site["project_count"], int)
            self.assertIs(site["independent_imagery_verification"], row["independent_imagery_verification"] == "true")
            self.assertEqual(site["statuses"], json.loads(row["statuses_json"]))
            self.assertNotIn("statuses_json", site)
            uncertainty = row["horizontal_uncertainty_metres"]
            self.assertEqual(site["horizontal_uncertainty_metres"], float(uncertainty) if uncertainty else None)
        projects = read_json(self.api / "projects.json")
        self.assertEqual([item["project_id"] for item in projects], [row["project_id"] for row in self.rows["projects.csv"]])
        for project in projects:
            self.assertEqual(list(project), self.typed_names("projects.csv") + DERIVED["projects.csv"])
            self.assertIsInstance(project["status_age_days_at_review"], int)
            self.assertIsInstance(project["power_observations"], list)
        evidence = read_json(self.api / "evidence.json")
        for item, row in zip(evidence, self.rows["evidence.csv"], strict=True):
            self.assertEqual(list(item), self.typed_names("evidence.csv") + DERIVED["evidence.csv"])
            self.assertEqual(item["published_at"], row["published_at"] or None)
            self.assertEqual(item["roles"], json.loads(row["roles_json"]))

    def test_site_summary_shape(self):
        summaries = read_json(self.api / "sites.json")
        self.assertEqual(list(summaries[0]), SITE_SUMMARY_KEYS)
        order = sorted(summaries, key=lambda item: (item["name"].casefold(), item["name"], item["site_id"]))
        self.assertEqual(summaries, order)
        multi = read_json(self.api / "stats.json")["counts"]["multi_project_sites"]
        self.assertEqual(sum(1 for item in summaries if item["project_count"] > 1), multi)
        power = sum(len(items) for items in self.json_list("projects.csv", "power_observations_json"))
        self.assertEqual(sum(len(item["power_observations"]) for item in summaries), power)

    def test_geojson_ids_match_sites_csv(self):
        collection = read_json(self.api / "sites.geojson")
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertEqual(collection["dataset"]["id"], self.dataset_id)
        ids = [feature["id"] for feature in collection["features"]]
        self.assertEqual(sorted(ids), sorted(row["site_id"] for row in self.rows["sites.csv"]))
        original = read_json(self.dataset_dir / "sites.geojson")["features"]
        geometries = {feature["id"]: feature["geometry"] for feature in original}
        names = [feature["properties"]["name"] for feature in collection["features"]]
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertEqual(collection["license"]["openstreetmap_geometries"]["id"], "ODbL-1.0")
        self.assertIn("OpenStreetMap", collection["attribution"])
        rewound = 0
        for feature in collection["features"]:
            original_geometry = geometries[feature["id"]]
            self.assertEqual(ring_sets(feature["geometry"]), ring_sets(original_geometry), feature["id"])
            self.assertTrue(follows_right_hand_rule(feature["geometry"]), feature["id"])
            rewound += feature["geometry"] != original_geometry
            self.assertEqual(feature["properties"]["site_id"], feature["id"])
            single = read_json(self.api / "sites" / f"{feature['id']}.geojson")
            self.assertEqual(single["features"], [feature])
        self.assertGreater(rewound, 0)  # the checkpoint has clockwise rings; the API reorients them
        for country in read_json(self.api / "countries.json"):
            document = read_json(self.api / "countries" / f"{country['country_iso_a2']}.geojson")
            self.assertEqual(sorted(item["id"] for item in document["features"]), country["site_ids"])
            with (self.api / "countries" / f"{country['country_iso_a2']}.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(sorted(row["site_id"] for row in rows), country["site_ids"])
            self.assertTrue(all(json.loads(row["statuses_json"]) for row in rows))

    def test_sqlite_database(self):
        path = self.site / "downloads" / "latest" / "atlas.sqlite"
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

        def scalar(sql: str, *parameters):
            return connection.execute(sql, parameters).fetchone()[0]

        try:
            for table in ("sites", "projects", "evidence"):
                rows = self.rows[f"{table}.csv"]
                self.assertEqual(scalar(f"SELECT COUNT(*) FROM {table}"), len(rows))
                columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
                self.assertEqual(columns, list(rows[0]))
            connection.execute("PRAGMA foreign_keys = ON")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(scalar("PRAGMA integrity_check"), "ok")
            self.assertEqual(scalar("PRAGMA user_version"), 1)
            # The writer's SQLite version (header bytes 96-99) is zeroed so upgrades do not change the bytes.
            self.assertEqual(path.read_bytes()[96:100], bytes(4))
            foreign = {(row[3], row[2]) for row in connection.execute("PRAGMA foreign_key_list(projects)")}
            self.assertIn(("site_id", "sites"), foreign)
            self.assertEqual(scalar("SELECT COUNT(*) FROM site_overview"), len(self.rows["sites.csv"]))
            links = {
                (project, row["evidence_id"])
                for row in self.rows["evidence.csv"] for project in json.loads(row["project_ids_json"])
            }
            self.assertEqual(scalar("SELECT COUNT(*) FROM project_evidence"), len(links))
            power = sum(len(items) for items in self.json_list("projects.csv", "power_observations_json"))
            self.assertEqual(scalar("SELECT COUNT(*) FROM power_observations"), power)
            self.assertEqual(connection.execute("SELECT DISTINCT independent_imagery_verification FROM sites").fetchall(), [(0,)])
            empty = sum(1 for row in self.rows["sites.csv"] if row["horizontal_uncertainty_metres"] == "")
            self.assertEqual(scalar("SELECT COUNT(*) FROM sites WHERE horizontal_uncertainty_metres IS NULL"), empty)
            first = self.rows["sites.csv"][0]
            sample = connection.execute("SELECT name, latitude FROM sites WHERE site_id = ?", (first["site_id"],)).fetchone()
            self.assertEqual(sample, (first["name"], float(first["latitude"])))
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            self.assertEqual(metadata["dataset_id"], self.dataset_id)
            self.assertNotIn(COMMIT, metadata.values())
        finally:
            connection.close()

    def check_checksums(self, directory: Path) -> dict[str, str]:
        lines = (directory / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        sums = {name: digest for digest, name in (line.split("  ", 1) for line in lines)}
        self.assertEqual(list(sums), sorted(sums))
        # The builder's index.html landing page is not a data file: it is in neither SHA256SUMS nor the zip.
        self.assertTrue((directory / "index.html").is_file(), directory)
        listed = sorted(path.name for path in directory.iterdir() if path.name not in {"SHA256SUMS", "index.html"})
        self.assertEqual(sorted(sums), listed)
        for name, digest in sums.items():
            self.assertEqual(sha256(directory / name), digest, f"{directory.name}/{name}")
        return sums

    def test_checksums_cover_every_download_directory(self):
        downloads = self.site / "downloads"
        directories = sorted(path.name for path in downloads.iterdir() if path.is_dir())
        self.assertEqual(directories, sorted([*(path.name for path in version_dirs()), "latest"]))
        derived = set(self.summary["derived_download_versions"])
        self.assertIn(self.dataset_id, derived)
        self.assertIn(public_site.FIRST_PUBLISHED_DATASET, derived)
        for name in directories:
            sums = self.check_checksums(downloads / name)
            if name == "latest":
                continue
            manifest = read_json(ROOT / self.config["versions_root"] / name / "manifest.json")
            originals = sorted([*manifest["files"], "manifest.json", "manifest.sha256"])
            if name in derived:
                # Versions published as current keep their pinned derived formats and zip.
                self.assertTrue(set(originals) < set(sums), name)
                self.assertIn(f"datacenter-atlas-{name}.zip", sums)
            else:
                self.assertEqual(sorted(sums), originals)
            for file_name, meta in manifest["files"].items():
                self.assertEqual(sums[file_name], meta["sha256"])

    def test_zip_archives_are_complete_and_identical(self):
        pinned = self.site / "downloads" / self.dataset_id
        latest = self.site / "downloads" / "latest"
        latest_zip = latest / "datacenter-atlas-latest.zip"
        self.assertEqual((pinned / f"datacenter-atlas-{self.dataset_id}.zip").read_bytes(), latest_zip.read_bytes())
        expected = sorted(
            path.name for path in latest.iterdir() if path.name not in {"SHA256SUMS", "index.html", latest_zip.name}
        )
        with zipfile.ZipFile(latest_zip) as archive:
            self.assertEqual(archive.namelist(), expected)
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
                self.assertEqual(archive.read(info), (latest / info.filename).read_bytes())
        for name in expected:
            self.assertEqual((pinned / name).read_bytes(), (latest / name).read_bytes(), name)
        unzipped = {path.name for path in pinned.iterdir() if not path.name.endswith((".zip", ".html"))}
        self.assertEqual(unzipped, {path.name for path in latest.iterdir() if not path.name.endswith((".zip", ".html"))})

    def test_datapackage_resources(self):
        directory = self.site / "downloads" / "latest"
        package = read_json(directory / "datapackage.json")
        self.assertEqual((package["name"], package["version"]), ("datacenter-atlas", self.dataset_id))
        names = {resource["name"] for resource in package["resources"]}
        for resource in package["resources"]:
            path = directory / resource["path"]
            self.assertEqual(resource["bytes"], path.stat().st_size, resource["path"])
            self.assertEqual(resource["hash"], f"sha256:{sha256(path)}", resource["path"])
            if resource["path"].endswith(".csv"):
                schema = resource["schema"]
                self.assertEqual([field["name"] for field in schema["fields"]], list(self.rows[resource["path"]][0]))
                self.assertEqual(schema["missingValues"], [""])
                self.assertTrue(all(field["description"] for field in schema["fields"]))
                for key in schema.get("foreignKeys", []):
                    self.assertIn(key["reference"]["resource"], names)
        sites = next(resource for resource in package["resources"] if resource["name"] == "sites")
        types = {field["name"]: field for field in sites["schema"]["fields"]}
        self.assertEqual(types["geometry_json"]["type"], "geojson")
        self.assertEqual(types["statuses_json"]["type"], "array")
        self.assertEqual(types["independent_imagery_verification"]["trueValues"], ["true"])
        self.assertIn("atlas.sqlite", {resource["path"] for resource in package["resources"]})

    def test_ndjson_and_atlas_json(self):
        directory = self.site / "downloads" / "latest"
        atlas = read_json(directory / "atlas.json")
        self.assertEqual(list(atlas), ["dataset", "sites", "projects", "evidence"])
        for key in ("sites", "projects", "evidence"):
            lines = (directory / f"{key}.ndjson").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(self.rows[f"{key}.csv"]))
            self.assertEqual([json.loads(line) for line in lines], atlas[key])

    def test_kml_is_well_formed(self):
        tree = ET.parse(self.site / "downloads" / "latest" / "sites.kml")
        placemarks = tree.getroot().findall(f"{KML}Document/{KML}Placemark")
        self.assertEqual(len(placemarks), len(self.rows["sites.csv"]))
        names = [placemark.find(f"{KML}name").text for placemark in placemarks]
        self.assertEqual(names, sorted(names, key=str.casefold))
        geometry_tags = {"Point", "Polygon", "MultiGeometry"}
        kinds = Counter(
            next(child.tag.removeprefix(KML) for child in placemark if child.tag.removeprefix(KML) in geometry_tags)
            for placemark in placemarks
        )
        geometry = Counter(row["geometry_type"] for row in self.rows["sites.csv"])
        # Polygon sites are a MultiGeometry of a Point at the display anchor plus their polygons.
        expected = {"Point": geometry["Point"], "MultiGeometry": geometry["Polygon"] + geometry["MultiPolygon"]}
        self.assertEqual(kinds, Counter(expected))
        document = tree.getroot().find(f"{KML}Document")
        style = document.find(f"{KML}Style")
        self.assertEqual(style.get("id"), "atlas-site")
        self.assertEqual(style.find(f"{KML}PolyStyle/{KML}color").text[:2], "40")  # translucent fill
        polygons = Counter(row["geometry_type"] for row in self.rows["sites.csv"])
        self.assertEqual(
            sum(len(placemark.findall(f".//{KML}Polygon")) > 0 for placemark in placemarks),
            polygons["Polygon"] + polygons["MultiPolygon"],
        )
        for placemark in placemarks:
            self.assertEqual(placemark.find(f"{KML}styleUrl").text, "#atlas-site")
            self.assertEqual(len(placemark.findall(f".//{KML}Point")), 1, placemark.get("id"))
            children = [child.tag.removeprefix(KML) for child in placemark]
            self.assertLess(children.index("description"), children.index("styleUrl"))
            self.assertLess(children.index("styleUrl"), children.index("ExtendedData"))
        self.assertIn("ODbL", document.find(f"{KML}description").text)

    def test_versions_document(self):
        versions = read_json(self.api / "versions.json")
        self.assertEqual(sorted(item["id"] for item in versions["versions"]), [path.name for path in version_dirs()])
        self.assertEqual(versions["current"], self.dataset_id)
        self.assertEqual(versions["versions"][-1]["id"], self.dataset_id)
        kinds = [item["kind"] for item in versions["versions"]]
        self.assertEqual(kinds, sorted(kinds, key=lambda kind: kind != "preview"))
        for item in versions["versions"]:
            self.assertEqual(item["label"], f"{item['checkpoint_date']} · {item['counts']['physical_sites']} sites")
        drafts = [item["counts"] for item in versions["versions"] if item["kind"] == "draft"]
        keys = [(counts["physical_sites"], counts["projects"], counts["evidence"]) for counts in drafts]
        self.assertEqual(keys, sorted(set(keys)))
        by_id = {item["id"]: item for item in versions["versions"]}
        expectations = {
            self.dataset_id: ("2026-10-09 · 200 sites", "2026-10-09"),
            "2026-08-20-v0.18-draft-thirty-fifth-reviewed": ("2026-09-25 · 197 sites", "2026-09-25"),
            "2026-08-20-v0.18-draft-initial-five": ("2026-09-08 · 105 sites", "2026-09-08"),
            "2026-08-20-v0.18-draft-second-reviewed": ("2026-09-08 · 112 sites", "2026-09-08"),
            "2026-08-20-preview-v0.17": ("2026-09-06 · 100 sites", "2026-09-06"),
            "2026-08-19-preview-v0.1": ("2026-08-19 · 8 sites", "2026-08-19"),
        }
        for identifier, (label, checkpoint) in expectations.items():
            self.assertEqual((by_id[identifier]["label"], by_id[identifier]["checkpoint_date"]), (label, checkpoint))
        seen: set[str] = set()
        for item in versions["versions"]:
            directory = ROOT / self.config["versions_root"] / item["id"]
            current = {row["site_id"] for row in read_csv(directory / "sites.csv")}
            self.assertEqual(item["added_site_ids"], sorted(current - seen))
            self.assertEqual(item["removed_site_ids"], sorted(seen - current))
            self.assertEqual(item["counts"], read_json(directory / "manifest.json")["counts"])
            seen = current

    def test_vocabularies_cover_data_and_model_enums(self):
        vocabulary = read_json(ROOT / "site" / "vocabulary.json")
        exported = read_json(self.api / "vocabularies.json")
        self.assertEqual(list(exported)[:13], [
            "api_version", "statuses", "status_methods", "geometry_use_scopes", "geometry_authority_classes",
            "verification_postures", "power_metrics", "power_stages", "estimate_methods", "evidence_kinds",
            "evidence_roles", "relationship_scopes", "workload_deployment_scopes",
        ])
        versions = public_site.discover_versions(ROOT / self.config["versions_root"])
        version = next(item for item in versions if item.id == self.dataset_id)
        codes = public_site.collect_vocabulary_codes(public_site.load_atlas(version, self.base_url))
        for name, values in codes.items():
            for code in values:
                self.assertIn(code, vocabulary[name], f"{name}: {code} has no label in site/vocabulary.json")
        enums = {
            "statuses": models.LifecycleStatus, "power_metrics": models.CapacityMetric,
            "power_stages": models.CapacityStage, "estimate_methods": models.EstimateMethod,
            "evidence_kinds": models.EvidenceKind, "operating_models": models.OperatingModel,
            "workloads": models.Workload,
        }
        for name, enum in enums.items():
            self.assertEqual({item.value for item in enum} - set(vocabulary[name]), set(), name)
        for item in models.CapacityMetric:
            self.assertEqual(vocabulary["power_metrics"][item.value]["unit"], item.unit, item.value)
        for name in public_site.VOCABULARY_KEYS:
            for code, entry in vocabulary[name].items():
                self.assertTrue(entry["label"].strip() and entry["description"].strip(), f"{name}: {code}")

    def test_every_schema_column_has_a_description(self):
        descriptions = read_json(ROOT / "site" / "field_descriptions.json")
        dictionary = (self.site / "data" / "dictionary" / "index.html").read_text(encoding="utf-8").replace("<wbr>", "")
        for table, spec in self.schema["tables"].items():
            for field in spec["fields"]:
                text = descriptions["tables"].get(table, {}).get(field["name"], "")
                self.assertGreater(len(text.strip()), 20, f"{table}:{field['name']}")
                self.assertIn(f">{field['name']}<", dictionary)
            extra = set(descriptions["tables"].get(table, {})) - {field["name"] for field in spec["fields"]}
            self.assertEqual(extra, set(), f"{table} describes columns the current schema lacks")
        for table, names in DERIVED.items():
            self.assertEqual(list(descriptions["derived"][table.removesuffix(".csv")]), names)
        self.assertEqual(list(descriptions["site_summary"]), list(read_json(self.api / "sites.json")[0]))
        self.assertNotIn("Not yet documented.", dictionary)
        stats = read_json(self.api / "stats.json")
        for key in stats:
            if key not in {"api_version", "dataset"}:
                self.assertIn(key, descriptions["stats"], f"stats.json {key} is not described")
        for key in stats["counts"]:
            self.assertIn(key, descriptions["counts"], f"counts.{key} is not described")
        self.assertIn("host_estate_context_projects", descriptions["counts"])  # arrives with the next checkpoint
        self.assertEqual(list(descriptions["country_summary"]), list(read_json(self.api / "countries.json")[0]))
        self.assertEqual(set(descriptions["version"]), set(read_json(self.api / "versions.json")["versions"][0]))
        self.assertEqual(list(descriptions["index"]), list(read_json(self.api / "index.json")))
        api_page = (self.site / "api" / "index.html").read_text(encoding="utf-8").replace("<wbr>", "")
        for name in descriptions["stats"]:
            self.assertIn(f"<code>{name}</code>", api_page)
        # JSON array columns show a non-empty example of their objects, not "[]".
        powered = re.search(r'power_observations_json</td>.*?<td class="mono small">([^<]*)</td>', dictionary)
        self.assertTrue(powered and powered.group(1).startswith("[{"), powered and powered.group(1))
        self.assertIn('id="dictionary-embedded"', dictionary)

    def test_internal_links_resolve(self):
        self.assertEqual(link_problems(self.site, self.base_url), [])

    def test_pages_have_csp_and_only_local_assets(self):
        self.assertEqual(len(self.pages), self.summary["html_pages"] + 1)  # 404.html is not in the sitemap
        data_types = {"application/json", "application/ld+json"}
        for page in self.pages:
            relative = page.relative_to(self.site).as_posix()
            parsed = scan(page)
            policies = [
                meta.get("content") for meta in parsed.meta
                if (meta.get("http-equiv") or "").lower() == "content-security-policy"
            ]
            self.assertEqual(policies, [public_site.CONTENT_SECURITY_POLICY], relative)
            for source in [script.get("src") for script in parsed.scripts if script.get("src")] + parsed.stylesheets:
                parts = urlsplit(source)
                local = not parts.scheme and not parts.netloc
                self.assertTrue(local or source.startswith(self.base_url), f"{relative}: {source}")
            for script in parsed.scripts:
                self.assertTrue(script.get("src") or script.get("type") in data_types, f"{relative}: inline script")
            self.assertEqual(parsed.inline_attributes, [], relative)
            text = page.read_text(encoding="utf-8")
            self.assertNotIn("{{", text, relative)
            self.assertTrue(text.startswith('<!doctype html>\n<html lang="en">'), relative)

    def test_builder_markup_uses_only_the_class_vocabulary(self):
        allowed = VOCABULARY_CLASSES | LAYOUT_CLASSES
        for page in self.pages:
            relative = page.relative_to(self.site).as_posix()
            if relative in FRAGMENT_PAGES:
                continue
            classes = scan(page).classes
            unknown = {name for name in classes if name not in allowed and not name.startswith(("status-", "page-"))}
            self.assertEqual(unknown, set(), relative)

    def test_no_duplicate_ids_on_builder_pages(self):
        for page in self.pages:
            if page.relative_to(self.site).as_posix() in FRAGMENT_PAGES:
                continue
            ids = scan(page).id_list
            self.assertEqual(sorted(name for name, count in Counter(ids).items() if count > 1), [], page)

    def test_site_page_content(self):
        projects = {row["project_id"]: row for row in self.rows["projects.csv"]}
        powered = next(
            row for row in self.rows["sites.csv"]
            if any(projects[pid]["power_observations_json"] != "[]" for pid in json.loads(row["project_ids_json"]))
        )
        site_projects = set(json.loads(powered["project_ids_json"]))
        page = self.site / "sites" / powered["site_id"] / "index.html"
        parsed = scan(page)
        text = page.read_text(encoding="utf-8")
        self.assertIn("Critical IT load", text)
        self.assertEqual(json.loads(parsed.data_blocks["site-geometry"])["geometry"], json.loads(powered["geometry_json"]))
        place = json.loads(parsed.data_blocks["application/ld+json"])
        self.assertEqual((place["@type"], place["geo"]["latitude"]), ("Place", float(powered["latitude"])))
        wanted = {
            row["evidence_id"] for row in self.rows["evidence.csv"]
            if set(json.loads(row["project_ids_json"])) & site_projects
        }
        rows = {identifier.removeprefix("evidence-") for identifier in parsed.ids if identifier.startswith("evidence-")}
        self.assertEqual(rows - {"heading", "table"}, wanted)
        self.assertIn("template=correction.yml&amp;title=Correction%3A%20", text)
        self.assertIn(f"&amp;site_id={powered['site_id']}", text)
        self.assertIn(f'href="../../api/v1/sites/{powered["site_id"]}.json"', text)
        self.assertIn(f"/commit/{COMMIT}", text)
        for label in ("OpenStreetMap", "Google Maps", "Bing aerial", "Copernicus Browser"):
            self.assertIn(f">{label}</a>", text)

    def test_explorer_bootstrap_and_dataset_json_ld(self):
        parsed = scan(self.site / "index.html")
        bootstrap = json.loads(parsed.data_blocks["atlas-bootstrap"])
        self.assertEqual(bootstrap["root"], "./")
        self.assertEqual(bootstrap["dataset"]["counts"]["physical_sites"], self.manifest["counts"]["physical_sites"])
        self.assertEqual(bootstrap["dataset"]["window_start"], "2026-05-22")
        for path in bootstrap["endpoints"].values():
            self.assertFalse(urlsplit(path).scheme)
            if "{" not in path:
                self.assertTrue((self.site / path).is_file(), path)
        for item in bootstrap["downloads"]:
            self.assertEqual(sha256(self.site / item["url"]), item["sha256"])
        gates = read_json(self.dataset_dir / "selection-report.json")["final_release_gates"]
        self.assertEqual(bootstrap["gates_summary"]["total"], len(gates))
        self.assertEqual(bootstrap["gates_summary"]["passed"], sum(1 for gate in gates.values() if gate["passed"]))
        website = json.loads(parsed.data_blocks["application/ld+json"])
        self.assertEqual(website["@type"], "WebSite")
        self.assertEqual(website["about"], {"@id": f"{self.base_url}data/#dataset"})
        dataset = json.loads(scan(self.site / "data" / "index.html").data_blocks["application/ld+json"])
        self.assertEqual(dataset["@type"], "Dataset")
        self.assertEqual((dataset["@id"], dataset["url"]), (f"{self.base_url}data/#dataset", f"{self.base_url}data/"))
        self.assertEqual(dataset["name"], "Data Center Atlas")
        self.assertTrue(all(item["@type"] == "DataDownload" for item in dataset["distribution"]))
        self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", dataset["license"])
        south, west, north, east = map(float, dataset["spatialCoverage"]["geo"]["box"].split())
        self.assertTrue(-90 <= south < north <= 90 and -180 <= west < east <= 180)
        for row in self.rows["sites.csv"]:
            self.assertTrue(south <= float(row["latitude"]) <= north and west <= float(row["longitude"]) <= east)
        self.assertEqual(dataset["citation"], read_json(self.api / "citation.json")["apa"])
        self.assertTrue(dataset["variableMeasured"])
        catalog = json.loads(scan(self.site / "versions" / "index.html").data_blocks["application/ld+json"])
        self.assertEqual(catalog["@type"], "DataCatalog")
        self.assertEqual(len(catalog["dataset"]), len(version_dirs()))
        self.assertEqual(bootstrap["license"]["openstreetmap_geometries"]["id"], "ODbL-1.0")
        stylesheets = parsed.stylesheets
        leaflet = next(index for index, href in enumerate(stylesheets) if href.endswith("leaflet.css"))
        site_css = next(index for index, href in enumerate(stylesheets) if href.endswith("site.css"))
        self.assertLess(leaflet, site_css)
        sources = [script["src"] for script in parsed.scripts if script.get("src")]
        self.assertEqual(sources, ["./assets/vendor/leaflet/leaflet.js", "./assets/atlas-core.js", "./assets/app.js"])
        site_id = read_json(self.api / "sites.json")[0]["site_id"]
        site_scripts = [script["src"] for script in scan(self.site / "sites" / site_id / "index.html").scripts if script.get("src")]
        self.assertEqual(site_scripts, [
            "../../assets/vendor/leaflet/leaflet.js", "../../assets/atlas-core.js", "../../assets/site-map.js",
            "../../assets/site.js",
        ])

    def test_sortable_tables_announce_their_initial_order(self):
        country = read_json(self.api / "countries.json")[0]["slug"]
        expectations = {
            "sites/index.html": [("Site", "ascending")],
            f"countries/{country}/index.html": [("Site", "ascending")],
            "countries/index.html": [("Sites", "descending")],
        }
        for relative, expected in expectations.items():
            text = (self.site / relative).read_text(encoding="utf-8")
            found = [(label, sort) for sort, label in re.findall(r'<th scope="col"[^>]* aria-sort="([a-z]+)">([^<]+)</th>', text)]
            self.assertEqual(found, expected, relative)

    def test_methodology_attribution_and_not_found(self):
        methodology = scan(self.site / "methodology" / "index.html")
        self.assertNotIn("release-gates-table", methodology.ids)
        self.assertTrue({"selection", "statuses", "locators", "evidence"}.issubset(methodology.ids))
        attribution = (self.site / "about" / "attribution" / "index.html").read_text(encoding="utf-8")
        self.assertIn("City of Chicago", attribution)
        self.assertIn("makes no claims as to the content, accuracy, timeliness, or completeness", attribution)
        self.assertIn('id="legal-notice"', attribution)
        not_found = scan(self.site / "404.html")
        for tag, _, value in not_found.links:  # GitHub Pages serves 404.html at any depth: no relative links
            if not value.startswith("#"):
                self.assertTrue(value.startswith(("https://", "http://")), f"<{tag}> {value}")
        self.assertTrue(any(value == f"{self.base_url}sites/" for _, _, value in not_found.links))
        not_found_text = (self.site / "404.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex">', not_found_text)
        home = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('name="robots"', home)  # sitemap pages stay indexable
        api_page = (self.site / "api" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="explorer-links"', api_page)
        self.assertIn("../methodology/#identifiers", api_page)
        self.assertIn("../../methodology/#identifiers", (self.site / "data" / "dictionary" / "index.html").read_text(encoding="utf-8"))
        # Identifier cells break at - as well (a hyphen before a digit is not a break opportunity on its own).
        self.assertEqual(public_site._breakable("2026-08-20_a.b/c"), "2026-<wbr>08-<wbr>20_<wbr>a.<wbr>b/<wbr>c")

    def test_public_prose_does_not_present_the_atlas_as_an_unfinished_release(self):
        # Inspect ordinary product pages, not raw source evidence or archived record diffs.
        paths = (
            "index.html", "sites/index.html", "countries/index.html", "data/index.html",
            "about/index.html", "methodology/index.html", "api/index.html", "versions/index.html",
            "downloads/index.html", "downloads/latest/index.html",
        )
        forbidden = re.compile(r"\b(?:preview|draft|final[- ]release|guarded|checkpoint)s?\b", re.IGNORECASE)
        for relative in paths:
            with self.subTest(page=relative):
                page = self.site / relative
                self.assertNotIn("preview-banner", scan(page).classes)
                prose = VisibleProse()
                prose.feed(page.read_text(encoding="utf-8"))
                prose.close()
                text = " ".join(prose.parts)
                match = forbidden.search(text)
                context = text[max(0, match.start() - 80):match.end() + 80] if match else ""
                self.assertIsNone(match, f"Public process language in {relative}: {context}")

    def test_feed_and_sitemap(self):
        feed = ET.parse(self.site / "feed.xml").getroot()
        entries = feed.findall(f"{ATOM}entry")
        versions = read_json(self.api / "versions.json")["versions"]
        self.assertEqual(len(entries), len(versions))
        self.assertEqual(entries[0].find(f"{ATOM}title").text, versions[-1]["label"])
        newest = max(item["checkpoint_date"] for item in versions)
        self.assertEqual(feed.find(f"{ATOM}updated").text, f"{newest}T00:00:00Z")
        sitemap = ET.parse(self.site / "sitemap.xml").getroot()
        urls = [element.text for element in sitemap.findall(f"{SITEMAP}url/{SITEMAP}loc")]
        expected = sorted(
            self.base_url + page.relative_to(self.site).as_posix().removesuffix("index.html")
            for page in self.pages if page.name != "404.html"
        )
        self.assertEqual(urls, expected)
        self.assertIn(f"Sitemap: {self.base_url}sitemap.xml", (self.site / "robots.txt").read_text(encoding="utf-8"))
        self.assertTrue((self.site / ".nojekyll").is_file())

    def test_static_assets_are_copied_verbatim(self):
        static = ROOT / "site" / "static"
        for path in static.rglob("*"):
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(static).parts):
                self.assertEqual((self.site / path.relative_to(static)).read_bytes(), path.read_bytes(), path)

    def test_api_files_follow_their_json_schemas(self):
        checker = SchemaCheck(self.api / "schemas")
        index = read_json(self.api / "schemas" / "index.json")
        self.assertEqual(sorted(f"{name}.schema.json" for name in index["schemas"]), sorted(checker.schemas))
        for schema in checker.schemas.values():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        checked = Counter()
        for path in sorted(self.api.rglob("*")):
            relative = path.relative_to(self.api).as_posix()
            target = api_schema_for(relative)
            if target is None or relative.startswith("schemas/") and relative != "schemas/index.json":
                continue
            name, many = target
            schema = {"type": "array", "items": {"$ref": name}} if many else {"$ref": name}
            problems = checker.errors(read_json(path), schema)
            self.assertEqual(problems[:5], [], relative)
            checked[name] += 1
        self.assertEqual(checked["site-document.schema.json"], len(self.rows["sites.csv"]))
        self.assertEqual(checked["evidence-document.schema.json"], len(self.rows["evidence.csv"]))

    def test_openapi_describes_every_endpoint(self):
        document = read_json(self.api / "openapi.json")
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertEqual(document["servers"], [{"url": self.base_url.rstrip("/"), "description": "GitHub Pages (static files)"}])
        index = read_json(self.api / "index.json")
        self.assertEqual(index["openapi_url"], f"{self.base_url}api/v1/openapi.json")
        endpoints = {url.removeprefix(self.base_url) for url in index["endpoints"].values()}
        self.assertEqual({path.lstrip("/") for path in document["paths"]}, endpoints)
        components = document["components"]["schemas"]
        operation_ids = set()
        for path, item in document["paths"].items():
            operation = item["get"]
            operation_ids.add(operation["operationId"])
            concrete = path.lstrip("/")
            for parameter in operation.get("parameters", []):
                self.assertTrue(re.fullmatch(parameter["schema"]["pattern"].strip("^$"), parameter["example"]), path)
                concrete = concrete.replace("{" + parameter["name"] + "}", parameter["example"])
            self.assertTrue((self.site / concrete).is_file(), concrete)
            for content in operation["responses"]["200"]["content"].values():
                for ref in re.findall(r'"\$ref": "#/components/schemas/([A-Za-z]+)"', json.dumps(content)):
                    self.assertIn(ref, components)
        self.assertEqual(len(operation_ids), len(document["paths"]))
        for ref in re.findall(r'"\$ref": "([^"]+)"', json.dumps(components)):
            self.assertTrue(ref.startswith("#/components/schemas/") and ref.rsplit("/", 1)[1] in components, ref)
        self.assertIn('rel="service-desc"', (self.site / "api" / "index.html").read_text(encoding="utf-8"))

    def test_llms_txt_explains_data_and_links_to_documentation(self):
        text = (self.site / "llms.txt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Data Center Atlas\n\n> "))
        self.assertIn(self.dataset_id, text)
        for phrase in ("not the status today", "not building footprints", "unknown, never zero", "Coverage is incomplete"):
            self.assertIn(phrase, text)
        full = (self.site / "llms-full.txt").read_text(encoding="utf-8")
        self.assertTrue(full.startswith(text))
        for row in self.rows["sites.csv"][:20]:
            self.assertNotIn(row["name"], full)  # Atlas-authored text only: no site names or evidence titles
        for link in re.findall(r"\]\((https?://[^)]+)\)", text) + re.findall(r"https?://\S+", full):
            link = link.rstrip(".,;:)\"'")
            if not link.startswith(self.base_url) or "{" in link:
                continue
            relative = unquote(link.removeprefix(self.base_url).split("#")[0])
            target = self.site / relative / "index.html" if relative.endswith("/") or not relative else self.site / relative
            self.assertTrue(target.is_file(), link)

    def test_download_directories_have_landing_pages_and_urls_resolve(self):
        downloads = self.site / "downloads"
        self.assertTrue((downloads / "index.html").is_file())
        for directory in downloads.iterdir():
            if directory.is_dir():
                page = (directory / "index.html").read_text(encoding="utf-8")
                for name in (directory / "SHA256SUMS").read_text(encoding="ascii").split():
                    if not re.fullmatch(r"[0-9a-f]{64}", name):
                        self.assertIn(f'>{name}</a>', page)
        versions = read_json(self.api / "versions.json")
        current = next(item for item in versions["versions"] if item["id"] == self.dataset_id)
        self.assertTrue(current["derived_downloads"])
        derived = {item["name"] for item in current["files"] if item["derived"]}
        self.assertIn(f"datacenter-atlas-{self.dataset_id}.zip", derived)
        self.assertIn("SHA256SUMS", derived)
        self.assertEqual({item["name"] for item in current["files"] if not item["derived"]},
                         {*self.manifest["files"], "manifest.json", "manifest.sha256"})
        urls = []
        for item in versions["versions"]:
            urls += [item["download_base_url"], item["page_url"], *(entry["url"] for entry in item["files"])]
        citation = read_json(self.api / "citation.json")
        urls += [citation["version_url"], citation["files_url"]]
        for document in (self.site / "index.html", self.site / "data" / "index.html", self.site / "feed.xml",
                         self.site / "llms.txt", self.api / "index.json", self.api / "sites.json"):
            urls += re.findall(re.escape(self.base_url) + r"downloads/[^\s\"'<>)]*/(?=[\s\"'<>)])",
                               document.read_text(encoding="utf-8"))
        self.assertGreater(len(urls), 100)
        for url in set(urls):
            relative = unquote(url.removeprefix(self.base_url))
            target = self.site / relative / "index.html" if relative.endswith("/") else self.site / relative
            self.assertTrue(target.is_file(), url)

    def test_citations_agree_everywhere(self):
        citation = read_json(self.api / "citation.json")
        apa = citation["apa"]
        versions = read_json(self.api / "versions.json")["versions"]
        published = next(item for item in versions if item["id"] == self.dataset_id)["checkpoint_date"]
        self.assertEqual(apa, f"Kyars, K. ({published[:4]}). Data Center Atlas "
                              f"({published}) [Data set]. {self.base_url}downloads/{self.dataset_id}/")
        self.assertEqual(citation["csl_json"][0]["URL"], citation["files_url"])
        self.assertEqual(read_json(self.api / "index.json")["citation"], apa)
        escaped = html_escape(apa)
        for page in ("data/index.html", "api/index.html", "about/index.html"):
            self.assertIn(escaped, (self.site / page).read_text(encoding="utf-8"), page)
        self.assertTrue((self.api / "citation.bib").read_text(encoding="utf-8").startswith("@misc{kyars"))
        ris = (self.api / "citation.ris").read_bytes()
        self.assertTrue(ris.startswith(b"TY  - DATA\r\n") and ris.endswith(b"ER  - \r\n"))
        self.assertEqual(citation["csl_json"][0]["type"], "dataset")

    def test_excel_workbook(self):
        path = self.site / "downloads" / "latest" / "atlas.xlsx"
        main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist()[0], "[Content_Types].xml")
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            names = [sheet.get("name") for sheet in workbook.iter(f"{main}sheet")]
            self.assertEqual(names, ["README", "sites", "projects", "evidence"])
            sheets = {}
            for index, name in enumerate(names, start=1):
                rows = []
                for row in ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml")).iter(f"{main}row"):
                    cells = {}
                    for cell in row.iter(f"{main}c"):
                        text = "".join(cell.itertext())
                        self.assertLessEqual(len(text), 32767)
                        cells[re.sub(r"\d", "", cell.get("r"))] = (cell.get("t"), text)
                    rows.append(cells)
                sheets[name] = rows
        for table in ("sites", "projects", "evidence"):
            self.assertEqual(len(sheets[table]), len(self.rows[f"{table}.csv"]) + 1, table)
        header = [value for _, value in sheets["sites"][0].values()]
        self.assertNotIn("geometry_json", header)
        self.assertIn("geojson_url", header)
        latitude = header.index("latitude")
        column = list(sheets["sites"][0])[latitude]
        kind, value = sheets["sites"][1][column]
        self.assertIsNone(kind)  # a number cell, not text
        self.assertEqual(float(value), float(self.rows["sites.csv"][0]["latitude"]))
        names = {value for row in sheets["sites"][1:] for kind, value in row.values() if kind == "inlineStr"}
        lévis = next((row["name"] for row in self.rows["sites.csv"] if "é" in row["name"]), None)
        if lévis:
            self.assertIn(lévis, names)
        readme = " ".join(value for row in sheets["README"] for _, value in row.values())
        self.assertIn(self.dataset_id, readme)
        self.assertIn("Coverage is incomplete and varies by country.", readme)

    def test_sqlite_observation_tables_and_reproducible_bytes(self):
        path = self.site / "downloads" / "latest" / "atlas.sqlite"
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for table, column in (
                ("power_observations", "power_observations_json"), ("efficiency_observations", "efficiency_observations_json"),
                ("annual_energy_observations", "annual_energy_observations_json"), ("role_claims", "role_claims_json"),
                ("workload_observations", "workloads_json"),
            ):
                expected = sum(len(items) for items in self.json_list("projects.csv", column))
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], expected, table)
                columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
                self.assertEqual(columns[:2], ["project_id", "ordinal"], table)
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            self.assertEqual(metadata["odbl_license"], "ODbL-1.0")
            self.assertIn("table:efficiency_observations", metadata)
            self.assertEqual(connection.execute("PRAGMA page_size").fetchone()[0], 4096)
        finally:
            connection.close()
        # The bytes must not depend on the SQLite build's secure_delete default (on for Debian/Ubuntu, off on macOS).
        config = public_site.load_config(ROOT / "site" / "config.json")
        context = public_site._prepare_context(ROOT, config, self.base_url, COMMIT)
        connect = sqlite3.connect
        results = []
        for preset in ("OFF", "ON"):
            def preset_connect(*args, preset=preset, **kwargs):
                connection = connect(*args, **kwargs)
                connection.execute(f"PRAGMA secure_delete = {preset}")
                return connection
            with mock.patch.object(public_site.sqlite3, "connect", preset_connect):
                results.append(public_site._sqlite_database(context, context.atlas))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], path.read_bytes())

    def test_site_pages_are_accessible_and_link_onwards(self):
        site_id = read_json(self.api / "sites.json")[0]["site_id"]
        text = (self.site / "sites" / site_id / "index.html").read_text(encoding="utf-8")
        self.assertIn('<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>', text)
        self.assertNotIn("›", text)
        self.assertIn(f'href="../../#site={site_id}"', text)
        self.assertIn(f'href="../../api/v1/sites/{site_id}.geojson"', text)
        self.assertIn('aria-label="Copy coordinates ', text)
        self.assertIn('<caption class="small muted">Evidence for ', text)
        self.assertIn('<td><code class="checksum">', text)
        self.assertRegex(text, r'<time datetime="\d{4}-\d{2}-\d{2}T[^"]+" title="[^"]+">\d{4}-\d{2}-\d{2}</time>')
        self.assertIn('rel="alternate" type="application/geo+json"', text)
        self.assertIn("Cite this site", text)
        country = read_json(self.api / "countries.json")[0]
        page = (self.site / "countries" / country["slug"] / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'href="../../?country={country["country_iso_a2"]}"', page)
        data = (self.site / "data" / "index.html").read_text(encoding="utf-8")
        labels = re.findall(r'<button type="button" class="[^"]*copy-btn[^"]*"[^>]*?(?: aria-label="([^"]*)")?>', data)
        self.assertTrue(labels)
        self.assertEqual(len(labels), len(set(labels)), "copy buttons need distinct accessible names")
        self.assertIn("keep_default_na", data)
        self.assertIn('na = ""', data.replace("&quot;", '"'))
        chicago = next((row for row in self.rows["evidence.csv"] if row["publisher"] == "City of Chicago"), None)
        if chicago:
            projects = set(json.loads(chicago["project_ids_json"]))
            site_ids = {row["site_id"] for row in self.rows["projects.csv"] if row["project_id"] in projects}
            for chicago_site in site_ids:
                page = (self.site / "sites" / chicago_site / "index.html").read_text(encoding="utf-8")
                self.assertIn("makes no claims as to the content, accuracy, timeliness, or completeness", page)
            self.assertIn("makes no claims as to the content, accuracy, timeliness, or completeness", data)
        footer = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="noopener license"', footer)
        self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", footer)

    def test_rebuild_is_byte_identical(self):
        with tempfile.TemporaryDirectory(prefix="atlas-site-again-") as directory:
            again = Path(directory) / "site"
            public_site.build_site(again, root=ROOT, source_commit=COMMIT)
            self.assertEqual(tree_hashes(again), tree_hashes(self.site))

    def test_command_line_interface(self):
        script = ROOT / "scripts" / "build_public_site.py"
        with tempfile.TemporaryDirectory(prefix="atlas-site-cli-") as directory:
            output = Path(directory) / "site"
            command = [sys.executable, str(script), "--output", str(output), "--base-url", "http://127.0.0.1:8000/x"]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual((summary["base_url"], summary["dataset"]), ("http://127.0.0.1:8000/x/", self.dataset_id))
            self.assertEqual(read_json(output / "api/v1/index.json")["base_url"], "http://127.0.0.1:8000/x/")
            refused = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("--force", refused.stderr)
            forced = subprocess.run([*command, "--force", "--source-commit", COMMIT], capture_output=True, text=True, check=False)
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertEqual(read_json(output / "api/v1/index.json")["build"]["source_commit"], COMMIT)


if __name__ == "__main__":
    unittest.main()
