"""Conservative NSW Major Projects Data Storage source lane.

The NSW Major Projects portal reports planning-workflow observations.  Portal
stages are not physical construction or operation evidence, and modifications
remain separate observations linked advisorially to their base application.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable
from urllib.parse import urlencode, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "nsw-major-projects-data-storage-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-nsw-major-projects-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-nsw-major-projects-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-nsw-major-projects-assessment-v1"
INVENTORY_FORMAT = "datacenter-atlas-nsw-major-projects-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-nsw-major-projects-schema-v1"

LIST_ENDPOINT = "https://www.planningportal.nsw.gov.au/major-projects/projects"
COPYRIGHT_URL = "https://www.planning.nsw.gov.au/copyright-and-disclaimer"
DEVELOPMENT_TYPE = "Data Storage"
LIST_PAGE_SIZE = 9
MAX_NETWORK_REQUESTS = 50
MIN_REQUEST_INTERVAL_SECONDS = 1.0
EXPECTED_RESULT_COUNT = 44
EXPECTED_LIST_PAGES = 5
EXPECTED_BASE_ROWS = 35
EXPECTED_MODIFICATION_ROWS = 9
EXPECTED_ACTIVE_ROWS = 22
EXPECTED_ACTIVE_BASE_ROWS = 19
EXPECTED_ACTIVE_MODIFICATION_ROWS = 3
EXPECTED_NETWORK_REQUESTS = 27
EXPECTED_POWER_STATEMENT_ROWS = 10
EXPECTED_LIST_DETAIL_LGA_TEXT_MISMATCH_ROWS = 2
EXPECTED_RAW_BYTES = 1_494_278
EXPECTED_RAW_INVENTORY_SHA256 = (
    "dd7993ee3c17f6fd4c6e55faa434df439e38f9d6ed33dd094e9efa11f8096e81"
)
EXPECTED_STAGE_COUNTS = {
    "Assessment": 11,
    "Determination": 19,
    "Exhibition": 1,
    "Prepare EIS": 7,
    "Response to Submissions": 3,
    "Withdrawn": 2,
    "stage_missing": 1,
}

NONTERMINAL_STAGES = frozenset(
    {
        "Assessment",
        "Exhibition",
        "Prepare EIS",
        "Response to Submissions",
    }
)

CASE_ID_RE = re.compile(r"^SSD-\d+(?:-Mod-\d+)?$")
MODIFICATION_ID_RE = re.compile(r"^(SSD-\d+)-Mod-(\d+)$")
PROJECT_PATH_RE = re.compile(r"^/major-projects/projects/[a-z0-9-]+$")
POWER_STATEMENT_RE = re.compile(
    r"(?<![\w.])(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>GW|MW|MVA)\b",
    flags=re.IGNORECASE,
)
ATTACHMENT_SECTION_RE = re.compile(r"^(?P<label>.+?)\s*\((?P<count>\d+)\)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "active-planning-observations.jsonl",
        "assessment.json",
        "definition.json",
        "list-observations.jsonl",
        "modification-relationships.jsonl",
        "retrieval-inventory.json",
        "schema.json",
        "source-inventory.json",
    }
)

RIGHTS_POLICY = {
    "attribution_required": True,
    "attribution_text": (
        "© State of New South Wales and Department of Planning, Housing and "
        "Infrastructure 2026"
    ),
    "cc_by_4_default_applies_only_to_department_material": True,
    "copyright_statement_url": COPYRIGHT_URL,
    "department_metadata_and_unmarked_department_description_release_permitted": (
        True
    ),
    "excluded_material": [
        "NSW coats of arms, government and department logos, trademarks, "
        "symbols and brands",
        "third-party intellectual property including photographs, illustrations, "
        "drawings, plans, artwork and maps, which may not be expressly identified",
        "court judgments",
        "legislation",
    ],
    "license_id": "CC-BY-4.0",
    "license_name": "Creative Commons Attribution 4.0 International",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "legal_conclusion_claimed": False,
    "raw_detail_html_contains_mixed_rights_and_is_audit_evidence_only": True,
    "raw_html_redistribution_eligible": False,
    "source_document_bodies_fetched": False,
    "source_document_images_or_maps_fetched": False,
    "source_page_attachment_urls_requested": False,
    "verified_local_date": "2026-07-18",
}

REVIEW_POLICY = {
    "annual_energy_mwh": None,
    "atlas_facility_identity": None,
    "atlas_lifecycle_status": None,
    "auto_identity_merge_permitted": False,
    "construction_verified": False,
    "data_centre_type": None,
    "detail_current_status_is_physical_lifecycle": False,
    "facility_or_unique_site_count": None,
    "gross_facility_power_mw": None,
    "identity_merge_performed": False,
    "it_capacity_mw": None,
    "modification_relationship_is_advisory_only": True,
    "operating_model": None,
    "operational_workload": None,
    "operation_verified": False,
    "portal_workflow_stage_is_physical_lifecycle": False,
    "power_statements_are_untyped_source_text": True,
    "pue": None,
    "review_only": True,
}


class NSWMajorProjectsError(ValueError):
    """Raised when NSW retrieval or validation fails closed."""


@dataclass
class _Node:
    tag: str
    attributes: dict[str, str]
    parent: "_Node | None" = None
    children: list["_Node"] = field(default_factory=list)
    text_fragments: list[str] = field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attributes.get("class", "").split())

    def text(self) -> str:
        fragments: list[str] = []

        def visit(node: _Node) -> None:
            fragments.extend(node.text_fragments)
            for child in node.children:
                visit(child)

        visit(self)
        return " ".join(" ".join(fragments).split())

    def descendants(self) -> Iterable["_Node"]:
        for child in self.children:
            yield child
            yield from child.descendants()


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack = [self.root]

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        node = _Node(
            tag.lower(),
            {name.lower(): value or "" for name, value in attrs},
            parent=self.stack[-1],
        )
        self.stack[-1].children.append(node)
        if node.tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        target = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == target:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_fragments.append(data)


def _html_tree(body: bytes, context: str) -> _Node:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NSWMajorProjectsError(f"{context} is not UTF-8") from error
    parser = _TreeParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:  # HTMLParser can surface malformed declarations.
        raise NSWMajorProjectsError(f"could not parse {context}") from error
    return parser.root


def _nodes_with_class(root: _Node, class_name: str) -> list[_Node]:
    return [node for node in root.descendants() if class_name in node.classes]


def _one_text(root: _Node, class_name: str, *, required: bool = True) -> str | None:
    nodes = _nodes_with_class(root, class_name)
    values = [node.text() for node in nodes if node.text()]
    if len(values) == 1:
        return values[0]
    if not values and not required:
        return None
    raise NSWMajorProjectsError(
        f"expected one {class_name!r} value, found {len(values)}"
    )


def parse_list_rows(body: bytes, *, page: int) -> list[dict[str, Any]]:
    """Parse every displayed card without inferring facility identity/status."""

    root = _html_tree(body, f"list page {page}")
    cards = _nodes_with_class(root, "card")
    rows: list[dict[str, Any]] = []
    for position, card in enumerate(cards, start=1):
        case_id = _one_text(card, "field-field-case-id")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise NSWMajorProjectsError(f"invalid case id on list page {page}")
        case_type = _one_text(card, "field-field-case-type")
        title = _one_text(card, "card__title")
        lga = _one_text(card, "card__sub")

        tag_values = []
        for tag in _nodes_with_class(card, "tag"):
            value = tag.text()
            if value and value != case_type and value not in tag_values:
                tag_values.append(value)
        if len(tag_values) > 1:
            raise NSWMajorProjectsError(
                f"multiple workflow stages for {case_id}: {tag_values}"
            )
        stage = tag_values[0] if tag_values else None

        address_nodes = []
        for icon in _nodes_with_class(card, "icon--pin"):
            if icon.parent is not None:
                address_nodes.append(icon.parent.text())
        addresses = list(dict.fromkeys(value for value in address_nodes if value))
        if len(addresses) != 1:
            raise NSWMajorProjectsError(
                f"expected one address for {case_id}, found {len(addresses)}"
            )

        links = []
        for node in card.descendants():
            href = node.attributes.get("href")
            if node.tag == "a" and href and PROJECT_PATH_RE.fullmatch(href):
                links.append(href)
        links = list(dict.fromkeys(links))
        if len(links) != 1:
            raise NSWMajorProjectsError(
                f"expected one project link for {case_id}, found {len(links)}"
            )

        modification = MODIFICATION_ID_RE.fullmatch(case_id)
        rows.append(
            {
                "address": addresses[0],
                "base_case_id": modification.group(1) if modification else case_id,
                "case_id": case_id,
                "case_type": case_type,
                "detail_path": links[0],
                "is_modification": modification is not None,
                "list_page": page,
                "list_position": position,
                "local_government_area_text": lga,
                "modification_number": (
                    int(modification.group(2)) if modification else None
                ),
                "title": title,
                "workflow_stage": stage,
            }
        )
    return rows


def _one_node(
    root: _Node, class_name: str, *, required: bool = True
) -> _Node | None:
    nodes = _nodes_with_class(root, class_name)
    if len(nodes) == 1:
        return nodes[0]
    if not nodes and not required:
        return None
    raise NSWMajorProjectsError(
        f"expected one {class_name!r} node, found {len(nodes)}"
    )


def _one_tag_text(root: _Node, tag: str) -> str:
    values = [node.text() for node in root.descendants() if node.tag == tag]
    values = [value for value in values if value]
    if len(values) != 1:
        raise NSWMajorProjectsError(
            f"expected one {tag!r} value, found {len(values)}"
        )
    return values[0]


def _project_detail_pairs(root: _Node) -> dict[str, str]:
    details = _one_node(root, "project__details")
    assert details is not None
    pairs: dict[str, str] = {}
    for row in _nodes_with_class(details, "row"):
        labels = [node.text() for node in row.descendants() if node.tag == "b"]
        labels = [label for label in labels if label]
        if len(labels) != 1:
            continue
        label = labels[0]
        if label in {"Name", "Phone"}:
            continue
        value = row.text()
        if not value.startswith(label):
            raise NSWMajorProjectsError(f"could not parse project detail {label!r}")
        value = value[len(label) :].strip()
        if not value or label in pairs:
            raise NSWMajorProjectsError(f"invalid project detail {label!r}")
        pairs[label] = value
    required = {
        "Application Number",
        "Assessment Type",
        "Development Type",
        "Local Government Areas",
    }
    if not required.issubset(pairs):
        missing = sorted(required - pairs.keys())
        raise NSWMajorProjectsError(f"missing project details: {missing}")
    return pairs


def _drupal_coordinates(root: _Node) -> dict[str, Any]:
    scripts = [
        node
        for node in root.descendants()
        if node.tag == "script"
        and node.attributes.get("data-drupal-selector") == "drupal-settings-json"
    ]
    if len(scripts) != 1:
        raise NSWMajorProjectsError(
            f"expected one Drupal settings script, found {len(scripts)}"
        )
    try:
        settings = json.loads("".join(scripts[0].text_fragments))
    except json.JSONDecodeError as error:
        raise NSWMajorProjectsError("invalid Drupal settings JSON") from error
    maps = settings.get("geofield_google_map")
    if not isinstance(maps, dict) or len(maps) != 1:
        raise NSWMajorProjectsError("expected one official project map")
    map_value = next(iter(maps.values()))
    try:
        features = map_value["data"]["features"]
    except (KeyError, TypeError) as error:
        raise NSWMajorProjectsError("official project map has no features") from error
    if not isinstance(features, list) or len(features) != 1:
        raise NSWMajorProjectsError("expected one official project map feature")
    geometry = features[0].get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise NSWMajorProjectsError("official project geometry is not a point")
    coordinates = geometry.get("coordinates")
    if (
        not isinstance(coordinates, list)
        or len(coordinates) != 2
        or not all(isinstance(value, (int, float)) for value in coordinates)
    ):
        raise NSWMajorProjectsError("official project point is invalid")
    longitude, latitude = coordinates
    if not 140 <= longitude <= 154 or not -38 <= latitude <= -28:
        raise NSWMajorProjectsError("official project point is outside NSW bounds")
    return {
        "coordinate_order": "longitude_latitude",
        "crs": "EPSG:4326",
        "geometry_type": "Point",
        "latitude": latitude,
        "longitude": longitude,
        "source": "detail_page_drupal_settings_geofield",
    }


def _milestones(root: _Node) -> list[dict[str, Any]]:
    milestones: list[dict[str, Any]] = []
    for sequence, item in enumerate(
        _nodes_with_class(root, "project-milestones__item"), start=1
    ):
        name = _one_text(item, "project-milestones__state-inner")
        state_node = _one_node(item, "project-milestones__state")
        assert isinstance(name, str) and state_node is not None
        states = [
            value
            for value in ("completed", "current", "future")
            if f"project-milestones__state--{value}" in state_node.classes
        ]
        if len(states) != 1:
            raise NSWMajorProjectsError(f"invalid milestone state for {name}")
        milestones.append(
            {"name": name, "sequence": sequence, "state": states[0]}
        )
    if (
        not milestones
        or sum(row["state"] == "current" for row in milestones) != 1
    ):
        raise NSWMajorProjectsError(
            "detail page must have exactly one current milestone"
        )
    return milestones


def _attachment_sections(root: _Node) -> list[dict[str, Any]]:
    container = _one_node(root, "field-major-project-attachments", required=False)
    if container is None:
        return []
    sections: list[dict[str, Any]] = []
    for summary in _nodes_with_class(container, "accordion__title"):
        text = summary.text()
        match = ATTACHMENT_SECTION_RE.fullmatch(text)
        sections.append(
            {
                "displayed_count": int(match.group("count")) if match else None,
                "displayed_label": match.group("label") if match else text,
                "displayed_text": text,
                "document_bodies_fetched": False,
                "document_urls_fetched": False,
            }
        )
    return sections


def _power_statements(description: str) -> list[dict[str, Any]]:
    """Preserve power-like phrases without converting or typing their meaning."""

    statements: list[dict[str, Any]] = []
    for match in POWER_STATEMENT_RE.finditer(description):
        statements.append(
            {
                "context": description,
                "matched_text": match.group(0),
                "metric_type": None,
                "source_field": "department_project_description",
                "unit_text": match.group("unit"),
                "value_text": match.group("value"),
            }
        )
    return statements


def parse_detail_page(body: bytes, *, expected_case_id: str) -> dict[str, Any]:
    """Parse Department-authored detail metadata from a retained portal page."""

    if not CASE_ID_RE.fullmatch(expected_case_id):
        raise NSWMajorProjectsError("expected detail case id is invalid")
    root = _html_tree(body, f"detail page {expected_case_id}")
    details = _project_detail_pairs(root)
    if details["Application Number"] != expected_case_id:
        raise NSWMajorProjectsError("detail page application number mismatch")

    heading = _one_node(root, "content-heading")
    assert heading is not None
    title = _one_tag_text(heading, "h1")
    heading_type = _one_text(heading, "content-heading__sub")
    description = _one_text(root, "field-field-project-description")
    if not isinstance(description, str):
        raise NSWMajorProjectsError("project description is missing")

    status_heading = _one_text(root, "project__status-heading")
    if not isinstance(status_heading, str) or not status_heading.startswith(
        "Current Status:"
    ):
        raise NSWMajorProjectsError("detail current status is missing")
    current_status_text = status_heading.removeprefix("Current Status:").strip()
    milestones = _milestones(root)

    return {
        "application_number": details["Application Number"],
        "assessment_type": details["Assessment Type"],
        "attachment_sections": _attachment_sections(root),
        "coordinates": _drupal_coordinates(root),
        "current_milestone": next(
            row["name"] for row in milestones if row["state"] == "current"
        ),
        "current_status_text": current_status_text,
        "department_project_description": description,
        "development_type": details["Development Type"],
        "heading_application_type": heading_type,
        "local_government_areas": details["Local Government Areas"],
        "main_project_case_id": details.get("Main Project"),
        "milestones": milestones,
        "other_department_project_details": {
            key: value
            for key, value in details.items()
            if key
            not in {
                "Application Number",
                "Assessment Type",
                "Development Type",
                "Local Government Areas",
                "Main Project",
            }
        },
        "power_statements": _power_statements(description),
        "title": title,
    }


def _raw_inventory(
    retrievals: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    inventory = [
        {
            "artifact_id": artifact_id,
            "bytes": retrieval["bytes"],
            "case_id": retrieval.get("case_id"),
            "content_type": retrieval["content_type"],
            "effective_url": retrieval["effective_url"],
            "fetched_at": retrieval["fetched_at"],
            "filename": retrieval["filename"],
            "headers": retrieval["headers"],
            "http_status": retrieval["http_status"],
            "sha256": retrieval["sha256"],
            "url": retrieval["url"],
        }
        for artifact_id, retrieval in retrievals.items()
    ]
    return sorted(inventory, key=lambda row: row["filename"])


def _raw_inventory_digest(inventory: Iterable[Mapping[str, Any]]) -> str:
    compact = [
        {"filename": row["filename"], "sha256": row["sha256"]}
        for row in inventory
    ]
    return sha256_bytes(canonical_json(compact))


def _validate_capture(
    capture: Mapping[str, Any], raw_bodies: Mapping[str, bytes]
) -> dict[str, Any]:
    if capture.get("result_count") != EXPECTED_RESULT_COUNT:
        raise NSWMajorProjectsError("captured list result count changed")
    if capture.get("list_pages") != EXPECTED_LIST_PAGES:
        raise NSWMajorProjectsError("captured list page count changed")
    if capture.get("list_page_size") != LIST_PAGE_SIZE:
        raise NSWMajorProjectsError("captured list page size changed")
    if capture.get("network_requests") != EXPECTED_NETWORK_REQUESTS:
        raise NSWMajorProjectsError("captured network request count changed")
    if capture.get("active_detail_pages") != EXPECTED_ACTIVE_ROWS:
        raise NSWMajorProjectsError("captured active detail count changed")
    if capture.get("base_rows") != EXPECTED_BASE_ROWS:
        raise NSWMajorProjectsError("captured base count changed")
    if capture.get("modification_rows") != EXPECTED_MODIFICATION_ROWS:
        raise NSWMajorProjectsError("captured modification count changed")
    _timestamp(capture.get("captured_at"), "capture.captured_at")

    retrievals_value = capture.get("retrievals")
    if not isinstance(retrievals_value, Mapping):
        raise NSWMajorProjectsError("capture retrievals must be an object")
    retrievals: dict[str, Mapping[str, Any]] = {}
    for artifact_id, value in retrievals_value.items():
        if not isinstance(artifact_id, str) or not isinstance(value, Mapping):
            raise NSWMajorProjectsError("capture retrieval record is invalid")
        retrievals[artifact_id] = value
    if len(retrievals) != EXPECTED_NETWORK_REQUESTS:
        raise NSWMajorProjectsError("capture retrieval inventory count changed")

    filenames: set[str] = set()
    for artifact_id, retrieval in retrievals.items():
        filename = retrieval.get("filename")
        url = retrieval.get("url")
        effective_url = retrieval.get("effective_url")
        digest = retrieval.get("sha256")
        fetched_at = retrieval.get("fetched_at")
        if (
            not isinstance(filename, str)
            or not filename.startswith("raw/")
            or not filename.endswith(".html")
            or filename in filenames
        ):
            raise NSWMajorProjectsError("capture raw filename is invalid")
        filenames.add(filename)
        if not isinstance(url, str) or not isinstance(effective_url, str):
            raise NSWMajorProjectsError("capture URL is invalid")
        for candidate in (url, effective_url):
            parsed = urlsplit(candidate)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.planningportal.nsw.gov.au"
                or not parsed.path.startswith("/major-projects/projects")
            ):
                raise NSWMajorProjectsError("capture contains a non-portal URL")
        if (
            retrieval.get("attempt") != 1
            or retrieval.get("http_status") != 200
            or retrieval.get("content_type") != "text/html"
            or not isinstance(retrieval.get("bytes"), int)
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            raise NSWMajorProjectsError("capture response metadata changed")
        _timestamp(fetched_at, f"retrievals.{artifact_id}.fetched_at")
        body = raw_bodies.get(filename)
        if (
            not isinstance(body, bytes)
            or len(body) != retrieval["bytes"]
            or sha256_bytes(body) != digest
        ):
            raise NSWMajorProjectsError(f"raw artifact mismatch: {filename}")
    if set(raw_bodies) != filenames:
        raise NSWMajorProjectsError("raw body inventory changed")

    inventory = _raw_inventory(retrievals)
    if sum(row["bytes"] for row in inventory) != EXPECTED_RAW_BYTES:
        raise NSWMajorProjectsError("raw byte total changed")
    if _raw_inventory_digest(inventory) != EXPECTED_RAW_INVENTORY_SHA256:
        raise NSWMajorProjectsError("raw HTML inventory hash changed")

    list_rows: list[dict[str, Any]] = []
    for page in range(EXPECTED_LIST_PAGES):
        filename = f"raw/list-page-{page:05d}.html"
        list_rows.extend(parse_list_rows(raw_bodies[filename], page=page))
    if len(list_rows) != EXPECTED_RESULT_COUNT:
        raise NSWMajorProjectsError("parsed list row count changed")
    if len({row["case_id"] for row in list_rows}) != len(list_rows):
        raise NSWMajorProjectsError("list case ids are not unique")
    if (
        sum(not row["is_modification"] for row in list_rows)
        != EXPECTED_BASE_ROWS
    ):
        raise NSWMajorProjectsError("parsed base row count changed")
    if (
        sum(row["is_modification"] for row in list_rows)
        != EXPECTED_MODIFICATION_ROWS
    ):
        raise NSWMajorProjectsError("parsed modification row count changed")
    stage_counts = Counter(
        row["workflow_stage"] or "stage_missing" for row in list_rows
    )
    if dict(sorted(stage_counts.items())) != EXPECTED_STAGE_COUNTS:
        raise NSWMajorProjectsError("exact workflow-stage arithmetic changed")

    active_rows = [
        row for row in list_rows if row["workflow_stage"] in NONTERMINAL_STAGES
    ]
    if len(active_rows) != EXPECTED_ACTIVE_ROWS:
        raise NSWMajorProjectsError("nonterminal active selection changed")
    if (
        sum(not row["is_modification"] for row in active_rows)
        != EXPECTED_ACTIVE_BASE_ROWS
    ):
        raise NSWMajorProjectsError("active base row count changed")
    if (
        sum(row["is_modification"] for row in active_rows)
        != EXPECTED_ACTIVE_MODIFICATION_ROWS
    ):
        raise NSWMajorProjectsError("active modification row count changed")

    retrieval_by_case = {
        retrieval.get("case_id"): (artifact_id, retrieval)
        for artifact_id, retrieval in retrievals.items()
        if retrieval.get("case_id") is not None
    }
    if set(retrieval_by_case) != {row["case_id"] for row in active_rows}:
        raise NSWMajorProjectsError("detail retrieval selection changed")

    details: dict[str, dict[str, Any]] = {}
    for row in active_rows:
        artifact_id, retrieval = retrieval_by_case[row["case_id"]]
        detail = parse_detail_page(
            raw_bodies[retrieval["filename"]], expected_case_id=row["case_id"]
        )
        if (
            detail["title"] != row["title"]
            or detail["heading_application_type"] != row["case_type"]
            or detail["assessment_type"] != row["case_type"]
            or detail["development_type"] != DEVELOPMENT_TYPE
            or detail["current_milestone"] != row["workflow_stage"]
        ):
            raise NSWMajorProjectsError(
                f"list/detail metadata mismatch for {row['case_id']}"
            )
        expected_main = row["base_case_id"] if row["is_modification"] else None
        if detail["main_project_case_id"] != expected_main:
            raise NSWMajorProjectsError(
                f"main-project relationship mismatch for {row['case_id']}"
            )
        details[row["case_id"]] = detail | {"artifact_id": artifact_id}

    if (
        sum(bool(detail["power_statements"]) for detail in details.values())
        != EXPECTED_POWER_STATEMENT_ROWS
    ):
        raise NSWMajorProjectsError("power statement row count changed")
    if any(len(detail["power_statements"]) > 1 for detail in details.values()):
        raise NSWMajorProjectsError(
            "unexpected multiple power statements in a description"
        )
    if (
        sum(
            details[row["case_id"]]["local_government_areas"]
            != row["local_government_area_text"]
            for row in active_rows
        )
        != EXPECTED_LIST_DETAIL_LGA_TEXT_MISMATCH_ROWS
    ):
        raise NSWMajorProjectsError("list/detail LGA text reconciliation changed")

    fetched_at = [row["fetched_at"] for row in inventory]
    return {
        "active_rows": active_rows,
        "assessed_at": max(fetched_at),
        "batch_started_at": min(fetched_at),
        "details": details,
        "inventory": inventory,
        "list_rows": list_rows,
        "retrievals": retrievals,
        "stage_counts": dict(sorted(stage_counts.items())),
    }


def _list_observations(validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    retrievals = validated["retrievals"]
    records: list[dict[str, Any]] = []
    for row in validated["list_rows"]:
        artifact_id = f"list_page_{row['list_page']:05d}"
        retrieval = retrievals[artifact_id]
        records.append(
            {
                "address": row["address"],
                "application_type_source_text": row["case_type"],
                "base_case_id": row["base_case_id"],
                "case_id": row["case_id"],
                "detail_url": retrieval["url"].split("?")[0].rstrip("/")
                + row["detail_path"].removeprefix("/major-projects/projects"),
                "evidence_scope": REVIEW_POLICY,
                "is_modification": row["is_modification"],
                "list_page": row["list_page"],
                "list_position": row["list_position"],
                "local_government_area_text": row["local_government_area_text"],
                "modification_number": row["modification_number"],
                "observation_id": f"nsw-major-projects:list:{row['case_id']}",
                "portal_nonterminal_subset_selected": row["workflow_stage"]
                in NONTERMINAL_STAGES,
                "record_type": "nsw_major_project_list_observation",
                "source": {
                    "fetched_at": retrieval["fetched_at"],
                    "raw_filename": retrieval["filename"],
                    "raw_sha256": retrieval["sha256"],
                    "url": retrieval["url"],
                },
                "title": row["title"],
                "workflow_stage": row["workflow_stage"],
            }
        )
    return records


def _active_observations(validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    retrievals = validated["retrievals"]
    details = validated["details"]
    records: list[dict[str, Any]] = []
    for row in validated["active_rows"]:
        detail = details[row["case_id"]]
        retrieval = retrievals[detail["artifact_id"]]
        records.append(
            {
                "address": row["address"],
                "application_type_source_text": row["case_type"],
                "base_case_id": row["base_case_id"],
                "case_id": row["case_id"],
                "detail_metadata": {
                    key: value for key, value in detail.items() if key != "artifact_id"
                },
                "detail_url": retrieval["url"],
                "evidence_scope": REVIEW_POLICY,
                "is_modification": row["is_modification"],
                "list_observation_id": f"nsw-major-projects:list:{row['case_id']}",
                "local_government_area_text": row["local_government_area_text"],
                "modification_number": row["modification_number"],
                "observation_id": f"nsw-major-projects:active-detail:{row['case_id']}",
                "priority": "high",
                "priority_basis": (
                    "exact portal list workflow stage is in the pinned nonterminal set"
                ),
                "record_type": "nsw_major_project_nonterminal_detail_observation",
                "reconciliation": {
                    "detail_lga_text_matches_list": detail[
                        "local_government_areas"
                    ]
                    == row["local_government_area_text"],
                    "detail_title_matches_list": True,
                    "detail_type_matches_list": True,
                    "detail_current_milestone_matches_list_stage": True,
                },
                "selection_workflow_stage_exact": row["workflow_stage"],
                "source": {
                    "fetched_at": retrieval["fetched_at"],
                    "raw_filename": retrieval["filename"],
                    "raw_sha256": retrieval["sha256"],
                    "url": retrieval["url"],
                },
                "title": row["title"],
            }
        )
    return records


def _modification_relationships(
    validated: Mapping[str, Any],
) -> list[dict[str, Any]]:
    case_ids = {row["case_id"] for row in validated["list_rows"]}
    details = validated["details"]
    return [
        {
            "auto_merge_permitted": False,
            "base_case_id": row["base_case_id"],
            "base_row_present": row["base_case_id"] in case_ids,
            "detail_main_project_field_confirmed": (
                details[row["case_id"]]["main_project_case_id"] == row["base_case_id"]
                if row["case_id"] in details
                else None
            ),
            "modification_case_id": row["case_id"],
            "relationship_type": "portal_modification_of_case_id",
            "review_only": True,
        }
        for row in validated["list_rows"]
        if row["is_modification"]
    ]


def derive_release_files(
    capture: Mapping[str, Any], raw_bodies: Mapping[str, bytes]
) -> dict[str, bytes]:
    """Derive the complete offline-reproducible release from captured HTML."""

    validated = _validate_capture(capture, raw_bodies)
    list_observations = _list_observations(validated)
    active_observations = _active_observations(validated)
    relationships = _modification_relationships(validated)
    attachment_sections = sum(
        len(row["detail_metadata"]["attachment_sections"])
        for row in active_observations
    )
    assessment = {
        "assessed_at": validated["assessed_at"],
        "atlas_decision": {
            "construction_status_promotion_permitted": False,
            "planning_observations_publication_eligible": True,
            "raw_html_publication_eligible": False,
            "status": "cc_by_4_department_metadata_planning_review_lane",
            "typed_power_or_energy_promotion_permitted": False,
            "unique_site_count_published": False,
        },
        "coverage_assessment": {
            "active_base_rows": EXPECTED_ACTIVE_BASE_ROWS,
            "active_detail_rows": EXPECTED_ACTIVE_ROWS,
            "active_modification_rows": EXPECTED_ACTIVE_MODIFICATION_ROWS,
            "attachment_category_sections_inventoried": attachment_sections,
            "base_rows": EXPECTED_BASE_ROWS,
            "construction_verified_rows": 0,
            "coordinates_retained_rows": EXPECTED_ACTIVE_ROWS,
            "detail_pages_not_fetched_for_terminal_or_missing_stage_rows": (
                EXPECTED_RESULT_COUNT - EXPECTED_ACTIVE_ROWS
            ),
            "list_detail_lga_text_mismatch_rows": sum(
                not row["reconciliation"]["detail_lga_text_matches_list"]
                for row in active_observations
            ),
            "list_rows": EXPECTED_RESULT_COUNT,
            "modification_rows": EXPECTED_MODIFICATION_ROWS,
            "nsw_local_da_coverage": False,
            "power_statement_rows": EXPECTED_POWER_STATEMENT_ROWS,
            "state_significant_only": True,
            "unique_physical_site_count": None,
        },
        "format": ASSESSMENT_FORMAT,
        "inference_policy": REVIEW_POLICY,
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "attempts_requiring_retry": 0,
            "batch_completed_at": validated["assessed_at"],
            "batch_started_at": validated["batch_started_at"],
            "detail_page_requests": EXPECTED_ACTIVE_ROWS,
            "list_page_requests": EXPECTED_LIST_PAGES,
            "maximum_request_cap": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": 1.05,
            "network_requests": EXPECTED_NETWORK_REQUESTS,
            "raw_bytes": EXPECTED_RAW_BYTES,
            "raw_inventory_sha256": EXPECTED_RAW_INVENTORY_SHA256,
            "retrieval_mode": "bounded_live_fetch_then_offline_derivation",
            "validator_network_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "selection_assessment": {
            "blank_stage_rows_retained": 1,
            "exact_nonterminal_workflow_stages": sorted(NONTERMINAL_STAGES),
            "selection_uses_detail_current_status_text": False,
            "selection_uses_list_workflow_stage_exact": True,
            "stage_counts": validated["stage_counts"],
        },
        "source_definition": source_definition(),
    }
    source_inventory = {
        "artifact_count": len(validated["inventory"]),
        "artifacts": validated["inventory"],
        "format": INVENTORY_FORMAT,
        "raw_bytes": EXPECTED_RAW_BYTES,
        "raw_inventory_sha256": EXPECTED_RAW_INVENTORY_SHA256,
        "release_id": RELEASE_ID,
    }
    schema = {
        "field_semantics": {
            "application_type_source_text": "exact portal case/assessment type text",
            "coordinates": (
                "portal detail-page point in EPSG:4326; not a site boundary"
            ),
            "detail_current_status_text": (
                "portal process display text; not physical lifecycle"
            ),
            "modification_relationship": (
                "advisory portal case relationship; never an identity merge"
            ),
            "power_statements": (
                "untyped verbatim phrases plus full description context"
            ),
            "workflow_stage": "exact filtered-list planning workflow stage or null",
        },
        "format": SCHEMA_FORMAT,
        "inference_policy": REVIEW_POLICY,
        "record_types": {
            "active": "nsw_major_project_nonterminal_detail_observation",
            "list": "nsw_major_project_list_observation",
            "relationship": "portal_modification_of_case_id",
        },
        "schema_version": SCHEMA_VERSION,
    }
    attribution = (
        "NSW Major Projects Data Storage planning metadata\n"
        f"{RIGHTS_POLICY['attribution_text']}\n"
        "Source: https://www.planningportal.nsw.gov.au/major-projects/"
        "projects?development_type=Data%20Storage\n"
        f"Licence: {RIGHTS_POLICY['license_url']}\n"
        f"Copyright statement: {COPYRIGHT_URL}\n\n"
        "Only Department material is treated as CC BY 4.0. Raw HTML is retained "
        "as mixed-rights audit evidence and is not redistribution-eligible. "
        "Third-party attachments, plans, photographs, artwork, maps, submissions "
        "and document bodies "
        "were not requested.\n"
    ).encode("utf-8")
    readme = (
        "# NSW Major Projects Data Storage planning observations\n\n"
        "This frozen source assessment preserves all 44 filtered register cards and "
        "22 detail pages selected only by the exact nonterminal list-stage contract. "
        "The 22-record high-priority subset contains 19 base applications and 3 "
        "modifications. A portal stage describes the planning workflow; it does not "
        "verify physical construction or operation.\n\n"
        "The register is limited to NSW state-significant applications and is not a "
        "complete NSW, Australian, facility, or unique-site inventory. Modifications "
        "remain separate observations with advisory links. Coordinates are portal "
        "points, not site boundaries. MW, GW and MVA phrases remain untyped source "
        "statements in their full description context.\n\n"
        "No attachment, EIS, plan, photograph, map, submission document, or applicant "
        "document was fetched. Exact raw list/detail HTML is retained only for offline "
        "audit and reproducibility because detail pages can contain mixed-rights "
        "material.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "active-planning-observations.jsonl": _jsonl(active_observations),
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(source_definition()),
        "list-observations.jsonl": _jsonl(list_observations),
        "modification-relationships.jsonl": _jsonl(relationships),
        "retrieval-inventory.json": canonical_json(dict(capture)),
        "schema.json": canonical_json(schema),
        "source-inventory.json": canonical_json(source_inventory),
    }


def _artifact_role(filename: str) -> str:
    if filename.startswith("raw/list-page-"):
        return "exact_filtered_register_html_audit_evidence"
    if filename.startswith("raw/detail-"):
        return "exact_nonterminal_detail_html_mixed_rights_audit_evidence"
    if filename.endswith("observations.jsonl"):
        return "derived_planning_observations"
    if filename == "modification-relationships.jsonl":
        return "advisory_relationship_suggestions"
    return "release_metadata"


def _license_scope(filename: str) -> str:
    if filename.startswith("raw/"):
        return "mixed_rights_local_audit_evidence_not_redistribution_eligible"
    if filename in {
        "active-planning-observations.jsonl",
        "list-observations.jsonl",
    }:
        return "CC-BY-4.0_department_material_with_attribution"
    return "derived_by_datacenter_atlas_with_source_attribution"


def _manifest_for_directory(path: Path, assessed_at: str) -> bytes:
    files: dict[str, dict[str, Any]] = {}
    for entry in sorted(path.rglob("*")):
        if not entry.is_file():
            continue
        relative = entry.relative_to(path).as_posix()
        if relative in {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}:
            continue
        body = entry.read_bytes()
        files[relative] = {
            "bytes": len(body),
            "license_scope": _license_scope(relative),
            "role": _artifact_role(relative),
            "sha256": sha256_bytes(body),
        }
    return canonical_json(
        {
            "assessed_at": assessed_at,
            "files": files,
            "format": RELEASE_FORMAT,
            "release_id": RELEASE_ID,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _freeze_tree(path: Path) -> None:
    for entry in path.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    path.chmod(0o555)


def write_release_bundle(
    output: str | Path,
    capture: Mapping[str, Any],
    raw_bodies: Mapping[str, bytes],
    *,
    freeze: bool = True,
) -> Path:
    """Write a new release atomically without overwriting an existing path."""

    output_path = Path(output)
    if output_path.exists() or output_path.is_symlink():
        raise NSWMajorProjectsError("output release already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validated = _validate_capture(capture, raw_bodies)
    derived = derive_release_files(capture, raw_bodies)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    )
    try:
        for filename, body in raw_bodies.items():
            destination = temporary / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        for filename, body in derived.items():
            (temporary / filename).write_bytes(body)
        manifest_body = _manifest_for_directory(
            temporary, validated["assessed_at"]
        )
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_path)
        if freeze:
            _freeze_tree(output_path)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_path


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NSWMajorProjectsError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise NSWMajorProjectsError(f"{label} is not canonical JSON")
    return value


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NSWMajorProjectsError(f"{label} is not valid JSONL") from error
    if any(not isinstance(value, dict) for value in values):
        raise NSWMajorProjectsError(f"{label} rows must be objects")
    if path.read_bytes() != _jsonl(values):
        raise NSWMajorProjectsError(f"{label} is not canonical JSONL")
    return values


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the frozen source assessment entirely offline."""

    release = Path(path)
    if not release.is_dir() or release.is_symlink():
        raise NSWMajorProjectsError("release must be a non-symlink directory")
    capture = _load_canonical_json(
        release / "retrieval-inventory.json", "retrieval inventory"
    )
    retrievals = capture.get("retrievals")
    if not isinstance(retrievals, Mapping):
        raise NSWMajorProjectsError("retrieval inventory has no retrievals")
    raw_filenames = {
        value.get("filename")
        for value in retrievals.values()
        if isinstance(value, Mapping)
    }
    if any(not isinstance(filename, str) for filename in raw_filenames):
        raise NSWMajorProjectsError("retrieval raw filename inventory is invalid")
    expected_files = (
        set(raw_filenames)
        | set(DERIVED_FILENAMES)
        | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    )
    actual_files = {
        entry.relative_to(release).as_posix()
        for entry in release.rglob("*")
        if entry.is_file()
    }
    if actual_files != expected_files:
        raise NSWMajorProjectsError("release file set changed")
    raw_bodies = {
        filename: (release / filename).read_bytes() for filename in raw_filenames
    }
    validated = _validate_capture(capture, raw_bodies)

    manifest = _load_canonical_json(release / MANIFEST_FILENAME, "manifest")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("assessed_at") != validated["assessed_at"]
    ):
        raise NSWMajorProjectsError("manifest identity changed")
    expected_manifest = _manifest_for_directory(release, validated["assessed_at"])
    if (release / MANIFEST_FILENAME).read_bytes() != expected_manifest:
        raise NSWMajorProjectsError("manifest does not bind the release files")
    sidecar = (
        f"{sha256_bytes(expected_manifest)}  {MANIFEST_FILENAME}\n".encode("utf-8")
    )
    if (release / MANIFEST_HASH_FILENAME).read_bytes() != sidecar:
        raise NSWMajorProjectsError("manifest SHA-256 sidecar changed")

    reproduced = derive_release_files(capture, raw_bodies)
    for filename, expected in reproduced.items():
        if (release / filename).read_bytes() != expected:
            raise NSWMajorProjectsError(f"offline reproduction mismatch: {filename}")

    assessment = _load_canonical_json(release / "assessment.json", "assessment")
    if assessment.get("rights_assessment") != RIGHTS_POLICY:
        raise NSWMajorProjectsError("rights boundary changed")
    if assessment.get("inference_policy") != REVIEW_POLICY:
        raise NSWMajorProjectsError("inference boundary changed")
    list_observations = _load_jsonl(
        release / "list-observations.jsonl", "list observations"
    )
    active_observations = _load_jsonl(
        release / "active-planning-observations.jsonl", "active observations"
    )
    relationships = _load_jsonl(
        release / "modification-relationships.jsonl", "modification relationships"
    )
    return {
        "active_observations": active_observations,
        "assessment": assessment,
        "definition": _load_canonical_json(release / "definition.json", "definition"),
        "list_observations": list_observations,
        "manifest": manifest,
        "relationships": relationships,
        "schema": _load_canonical_json(release / "schema.json", "schema"),
        "source_inventory": _load_canonical_json(
            release / "source-inventory.json", "source inventory"
        ),
    }


def is_frozen_release(path: str | Path) -> bool:
    release = Path(path)
    if not release.is_dir() or release.stat().st_mode & 0o777 != 0o555:
        return False
    return all(
        entry.stat().st_mode & 0o777 == (0o555 if entry.is_dir() else 0o444)
        for entry in release.rglob("*")
    )


def thaw_for_test(path: str | Path) -> None:
    release = Path(path)
    release.chmod(stat.S_IRWXU)
    for entry in release.rglob("*"):
        entry.chmod(stat.S_IRWXU if entry.is_dir() else stat.S_IRUSR | stat.S_IWUSR)


def canonical_json(value: Any) -> bytes:
    """Return deterministic pretty JSON with one trailing newline."""

    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest of *value*."""

    return hashlib.sha256(value).hexdigest()


def _timestamp(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise NSWMajorProjectsError(f"{field_name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NSWMajorProjectsError(f"{field_name} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NSWMajorProjectsError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _jsonl(records: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
        for record in records
    ).encode("utf-8")


def source_definition() -> dict[str, Any]:
    """Return the fail-closed definition for this source lane."""

    return {
        "coverage": {
            "complete_for_australia": False,
            "complete_for_nsw_local_development_applications": False,
            "geography": "New South Wales, Australia",
            "scope": (
                "NSW Major Projects portal State Significant Applications and "
                "modifications classified by the portal as Data Storage"
            ),
            "state_significant_only": True,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": REVIEW_POLICY,
        "network_policy": {
            "backoff_seconds_by_retry": [2, 4],
            "detail_selection": "exact membership in nonterminal_workflow_stages",
            "list_page_size": LIST_PAGE_SIZE,
            "maximum_attempts_per_url": 3,
            "maximum_network_requests_per_run": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "published_numeric_server_rate_limit_found": False,
        },
        "publisher": (
            "State of New South Wales, Department of Planning, Housing and "
            "Infrastructure"
        ),
        "query": {
            "development_type_exact": DEVELOPMENT_TYPE,
            "list_page_zero_url": list_page_url(0),
            "nonterminal_workflow_stages": sorted(NONTERMINAL_STAGES),
        },
        "release_id": RELEASE_ID,
        "retention": {
            "attachment_documents_fetched": False,
            "detail_html_for_nonterminal_rows_only": True,
            "exact_raw_html_retained_for_audit": True,
            "list_html_all_pages_retained": True,
            "raw_html_publication_eligible": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "nsw-major-projects-data-storage",
        "source_urls": {
            "copyright_statement": COPYRIGHT_URL,
            "filtered_register": list_page_url(0),
        },
        "title": "NSW Major Projects Data Storage planning observations",
    }


def list_page_url(page: int) -> str:
    """Return the stable filtered portal URL for a zero-indexed list page."""

    if page < 0:
        raise NSWMajorProjectsError("list page must be non-negative")
    parameters: list[tuple[str, str]] = [("development_type", DEVELOPMENT_TYPE)]
    if page:
        parameters.append(("page", str(page)))
    return f"{LIST_ENDPOINT}?{urlencode(parameters)}"


def parse_list_result_count(body: bytes) -> int:
    """Parse the portal's displayed filtered result count."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NSWMajorProjectsError("list page is not UTF-8") from error
    patterns = (
        r"Showing\s*(?:<[^>]+>|\s|&nbsp;)*\d[\d,]*\s*(?:-|to)\s*"
        r"\d[\d,]*\s*(?:<[^>]+>|\s|&nbsp;)*(?:of\s*)?"
        r"([\d,]+)\s*(?:results?|projects?)",
        r"Showing:\s*(?:<[^>]+>|\s|&nbsp;)*([\d,]+)\s*results?",
        r"([\d,]+)\s+results?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
    raise NSWMajorProjectsError("could not parse list result count")


def list_page_count(result_count: int) -> int:
    """Return the number of list pages for the portal's nine-card pages."""

    if result_count <= 0:
        raise NSWMajorProjectsError("result count must be positive")
    return math.ceil(result_count / LIST_PAGE_SIZE)
