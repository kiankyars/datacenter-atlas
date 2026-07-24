"""Conservative IAAC official-registry source assessment lane.

The bounded search is an observation inventory, not a facility or site census.
IAAC assessment status is process metadata.  Supporting-generation capacity is
not data-centre load, and the Bell source wording is not IT capacity or energy.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit
from zipfile import BadZipFile, ZipFile


SCHEMA_VERSION = 1
RELEASE_ID = "iaac-data-center-search-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-iaac-registry-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-iaac-registry-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-iaac-registry-assessment-v1"
INVENTORY_FORMAT = "datacenter-atlas-iaac-registry-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-iaac-registry-schema-v1"

SEARCH_URL = (
    "https://iaac-aeic.gc.ca/050/evaluations/exploration?"
    "search=data%20center&document_type=project&culture=en-CA"
)
PROJECT_URL_TEMPLATE = "https://iaac-aeic.gc.ca/050/evaluations/proj/{reference_number}"
TERMS_URL = "https://www.canada.ca/en/transparency/terms.html"
OGL_URL = "https://open.canada.ca/en/open-government-licence-canada"

EXPECTED_SEARCH_RESULTS = 41
EXPECTED_DIRECT_RESULTS = 4
EXPECTED_EXCLUDED_RESULTS = 37
EXPECTED_NETWORK_REQUESTS = 11
EXPECTED_RAW_BYTES = 1_966_123
EXPECTED_RAW_INVENTORY_SHA256 = (
    "1ae2290754b00643840d7bf892e760a7598eccc7c813cb403d681330d3613a4d"
)
EXPECTED_CLOSED_SET_SHA256 = (
    "4e92a1ab7938c12c066fa300787dde167d82bbbb0103434f6c763b55b2afbdd3"
)
EXPECTED_SEARCH_INVENTORY_SHA256 = (
    "8241a72f7426920acc1dc2e24264cb60c2f6c21c49f4ad71f3de075bbe967958"
)
MAX_NETWORK_REQUESTS = 20
MIN_REQUEST_INTERVAL_SECONDS = 1.0

DIRECT_PROJECTS = {
    "90036": {
        "title": "Mihta Askiy Data Center Project",
        "geospatial_document_id": "164355",
    },
    "90121": {
        "title": "Beacon AI Centers Indus Project",
        "geospatial_document_id": "164503",
    },
    "90123": {
        "title": "Beacon AI Centers Heartland Project",
        "geospatial_document_id": "164351",
    },
    "90514": {
        "title": "Bell AI Fabric Data Centre Project",
        "geospatial_document_id": None,
    },
}

DIRECT_DECISIONS = {
    "90036": {
        "observation_role": "supporting_generation_project",
        "reason": "IAAC says the proposed 650 MW generation facility would support a new data centre.",
    },
    "90121": {
        "observation_role": "supporting_generation_project",
        "reason": "IAAC says the proposed 1,494 MW generation facility would support a new data centre.",
    },
    "90123": {
        "observation_role": "supporting_generation_project",
        "reason": "IAAC says the proposed 920 MW generation facility would support a new data centre.",
    },
    "90514": {
        "observation_role": "data_centre_project",
        "reason": "IAAC describes a proposed 300 MW industrial artificial-intelligence data centre.",
    },
}

EXCLUSION_DECISIONS = {
    "80468": {
        "title": "Regional Assessment in the Ring of Fire Area",
        "category": "generic_data_centre_token_collision",
        "reason": "Regional-assessment text uses data and geographic centred wording; it is not a data-centre project.",
    },
    "80780": {
        "title": "Environment and Climate Change Canada climate station relocation, Gros Morne National Park",
        "category": "generic_data_centre_token_collision",
        "reason": "Climate data and a site-center description caused the match; the project is a climate-station relocation.",
    },
    "80802": {
        "title": "Canadian Coast Guard Seal Cove Base Mid Shore Patrol Vessel Float Replacement",
        "category": "generic_data_centre_token_collision",
        "reason": "Chart datum text caused the data-like match; the project replaces a marine float.",
    },
    "80887": {
        "title": "Biigtigong Nishnaabeg Water Treatment System Project",
        "category": "generic_data_centre_token_collision",
        "reason": "SCADA and healing-centre text caused the match; the project is a water-treatment system.",
    },
    "81018": {
        "title": "Fire Hydrant Replacement",
        "category": "generic_data_centre_token_collision",
        "reason": "The Surrey Tax Centre name caused the centre match; the work replaces fire hydrants.",
    },
    "81092": {
        "title": "Removal of Pad-Mount Transformer and Switchgear",
        "category": "existing_data_centre_ancillary_work",
        "reason": "Removal of redundant transformer and switchgear outside an existing DND Data Centre is ancillary work, not a new data-centre build.",
    },
    "81344": {
        "title": "Design and Construct CJIRU - Geotechnical and Topographical Study at the 8 Wing Trenton Airfield",
        "category": "generic_data_centre_token_collision",
        "reason": "Training-centre and site-information text caused the match; the observation is a geotechnical/topographical study.",
    },
    "81737": {
        "title": "Exterior Perimeter Fencing Extension",
        "category": "existing_data_centre_ancillary_work",
        "reason": "A chain-link fence extension at the existing Surrey Taxation Data Center is ancillary work, not a new data-centre build.",
    },
    "83106": {
        "title": "Simpcw Community Centre - NEQWEYQWELSTEN SCHOOL",
        "category": "generic_data_centre_token_collision",
        "reason": "Community-centre and BC Conservation Data Centre references caused the match; it is not a data-centre project.",
    },
    "83223": {
        "title": "Deschambault Nursing Station",
        "category": "generic_data_centre_token_collision",
        "reason": "Health-centre wording caused the match; the project is a nursing station.",
    },
    "83307": {
        "title": "Submarine Fibre Optic Telecommunication Cables",
        "category": "generic_data_centre_token_collision",
        "reason": "Convention-centre and internet-exchange context caused the match; the project installs submarine fibre cables.",
    },
    "83490": {
        "title": "Canadian Coast Guard Telegraph Cove Radar and Communications Site",
        "category": "generic_data_centre_token_collision",
        "reason": "Communications-center wording caused the match; the project is a Coast Guard radar site.",
    },
    "83518": {
        "title": "Canadian Coast Guard Denny Island Radar and Communications Site",
        "category": "generic_data_centre_token_collision",
        "reason": "Communications-center wording caused the match; the project is a Coast Guard radar site.",
    },
    "83767": {
        "title": "Samahquam-Wastewater System and Sludge Management",
        "category": "generic_data_centre_token_collision",
        "reason": "Conservation Data Center text caused the match; the project is a wastewater system.",
    },
    "83853": {
        "title": "Esk'Etemc First Nation Road and Drainage Improvements (Alkali Lake)",
        "category": "generic_data_centre_token_collision",
        "reason": "BC Conservation Data Centre text caused the match; the project concerns roads and drainage.",
    },
    "83921": {
        "title": "Chiller and Dry-Cooler Replacement",
        "category": "existing_data_centre_ancillary_work",
        "reason": "Replacement of chillers and fluid coolers serving an existing data-center cooling plant is ancillary maintenance, not a new data-centre build.",
    },
    "83946": {
        "title": "Adams Lake-Sahhltkum IR#4 Water Treatment and Reservoir",
        "category": "generic_data_centre_token_collision",
        "reason": "Conservation Data Centre text caused the match; the project is a water-treatment and reservoir project.",
    },
    "84219": {
        "title": "Construct Combatant Training and Integration Centre - Canadian Forces Base Halifax",
        "category": "generic_data_centre_token_collision",
        "reason": "Training-centre text also mentions operational data; the facility is not a data centre.",
    },
    "84225": {
        "title": "Riprap rehabilitation at the Cap-aux-Meules terminal, Iles-de-la-Madeleine, Quebec.",
        "category": "generic_data_centre_token_collision",
        "reason": "Chart Datum text caused the data-like match; the project rehabilitates riprap.",
    },
    "84524": {
        "title": "Runway 18-36 Rehabilitation at YWG",
        "category": "generic_data_centre_token_collision",
        "reason": "Field Electrical Center wording caused the match; the project rehabilitates a runway.",
    },
    "85895": {
        "title": "Wharf Repair and Removal, New Haven Department of Fisheries and Oceans Canada Small Craft Harbour, Victoria County, Nova Scotia",
        "category": "generic_data_centre_token_collision",
        "reason": "Center-to-center and chart-datum measurement text caused the match; the project repairs a wharf.",
    },
    "85933": {
        "title": "Lílwat Nation: Xetólacw Village Road Resurfacing",
        "category": "generic_data_centre_token_collision",
        "reason": "Service-centre and centre-line wording caused the match; the project resurfaces roads.",
    },
    "85963": {
        "title": "Breakwater Reconstruction at Baileys Brook Small Craft Harbour, Pictou County, NS",
        "category": "generic_data_centre_token_collision",
        "reason": "Chart datum text caused the data-like match; the project reconstructs a breakwater.",
    },
    "86010": {
        "title": "Construct Combatant Training and Integration Centre - Canadian Forces Base Esquimalt",
        "category": "generic_data_centre_token_collision",
        "reason": "Training-centre text also mentions operational data; the facility is not a data centre.",
    },
    "87150": {
        "title": "Relocation of Cave Creek Collector Sewer - Phase 1",
        "category": "generic_data_centre_token_collision",
        "reason": "City Centre place-name wording caused the match; the project relocates a sewer.",
    },
    "87377": {
        "title": "Workplace Modernization at 80 Elgin Street",
        "category": "generic_data_centre_token_collision",
        "reason": "Office data systems and National Arts Centre context caused the match; it is workplace modernization.",
    },
    "87402": {
        "title": "VanPile maintenance dredging",
        "category": "generic_data_centre_token_collision",
        "reason": "Chart datum text caused the data-like match; the project is maintenance dredging.",
    },
    "88770": {
        "title": "Borden Satellite Hub",
        "category": "non_data_centre_data_processing_facility",
        "reason": "The source describes a seismic-data satellite reception and processing centre, not a general-purpose data-centre build.",
    },
    "89234": {
        "title": "Fostering Resilience in Iraq Through Sustainable Water Management and Climate-Smart Agriculture",
        "category": "generic_data_centre_token_collision",
        "reason": "Data-driven decision-making and community-centre context caused the match; it is an international water/agriculture program.",
    },
    "89309": {
        "title": "Integrated Emergency Response for El Niño Drought Affected Communities in Zimbabwe, Zambia, Mozambique, and Malawi",
        "category": "generic_data_centre_token_collision",
        "reason": "Health-centre and baseline-data text caused the match; it is an international emergency-response program.",
    },
    "89781": {
        "title": "Installation of new distance measuring equipment (DME) in Trois-Rivières",
        "category": "generic_data_centre_token_collision",
        "reason": "Property-center wording caused the match; the project installs aviation distance-measuring equipment.",
    },
    "89826": {
        "title": "Department of National Defence Quinte West Training Centre Project - 8 Wing Trenton, ON",
        "category": "generic_data_centre_token_collision",
        "reason": "Training-centre wording caused the match; the project builds military training facilities.",
    },
    "89997": {
        "title": "Fuel Facility Oil Water Separator Replacement – 5th Canadian Division Support Base Gagetown",
        "category": "generic_data_centre_token_collision",
        "reason": "Rainfall-data context caused the match; the project replaces an oil-water separator.",
    },
    "90532": {
        "title": "Red Pheasant Cree Nation Youth Centre",
        "category": "generic_data_centre_token_collision",
        "reason": "A youth centre with ordinary data/telephone utility lines is not a data centre.",
    },
    "90572": {
        "title": "Department of National Defence, Strategic Tanker Transport Capability Project Support Infrastructure at CFB Trenton - Expansion of the existing Air Mobility Training Centre (AMTC) WP4",
        "category": "generic_data_centre_token_collision",
        "reason": "Training-centre wording caused the match; the project expands military training infrastructure.",
    },
    "90599": {
        "title": "Department of National Defence (DND) NORAD A-OTHR (Arctic Over the Horizon Radar) Project at Military Aeronautical Communications System (MACS) Carrying Place",
        "category": "generic_data_centre_token_collision",
        "reason": "Property-center wording caused the match; the project is radar and communications infrastructure.",
    },
    "90623": {
        "title": "Leveraging climate-smart shrimp aquaculture as an inclusive nature-based climate solution for small-scale farmers in coastal Indonesia",
        "category": "generic_data_centre_token_collision",
        "reason": "International Development Research Centre and real-time data text caused the match; it is an aquaculture program.",
    },
}

GEOSPATIAL_DOCUMENTS = {
    "164351": "90123",
    "164355": "90036",
    "164503": "90121",
}

PROJECT_FACT_CONTRACTS = {
    "90036": {
        "assessment_status": "Completed",
        "assessment_type": "Early decision - No further assessment required",
        "construction_evidence": False,
        "data_centre_capacity_mw": None,
        "data_centre_capacity_metric": None,
        "location": "Approximately 40 km northeast of Peace River (Alberta)",
        "nature_of_activity": "Oil and Gas",
        "operation_evidence": False,
        "proponent": "Cree Ative Datacenter Corp GP",
        "source_power_mw": 650,
        "source_power_metric": "supporting_generation_production_capacity_mw",
        "start_date": "2025-12-29",
    },
    "90121": {
        "assessment_status": "Completed",
        "assessment_type": "Early decision - No further assessment required",
        "construction_evidence": False,
        "data_centre_capacity_mw": None,
        "data_centre_capacity_metric": None,
        "location": "Approximately 2 km northwest of Indus (Alberta)",
        "nature_of_activity": "Oil and Gas",
        "operation_evidence": False,
        "proponent": "Indus Power",
        "source_power_mw": 1494,
        "source_power_metric": "supporting_generation_production_capacity_mw",
        "start_date": "2025-12-29",
    },
    "90123": {
        "assessment_status": "Completed",
        "assessment_type": "Early decision - No further assessment required",
        "construction_evidence": False,
        "data_centre_capacity_mw": None,
        "data_centre_capacity_metric": None,
        "location": "Sturgeon County, about 7 kilometres east of Gibbons (Alberta)",
        "nature_of_activity": "Oil and Gas",
        "operation_evidence": False,
        "proponent": "Heartland Power",
        "source_power_mw": 920,
        "source_power_metric": "supporting_generation_production_capacity_mw",
        "start_date": "2025-12-29",
    },
    "90514": {
        "assessment_status": "Completed",
        "assessment_type": "Request for designation not applicable",
        "construction_evidence": True,
        "data_centre_capacity_mw": 300,
        "data_centre_capacity_metric": "source_wording_industrial_ai_data_centre_mw",
        "location": "Rural Municipality of Sherwood (Saskatchewan)",
        "nature_of_activity": "Other, not otherwise specified",
        "operation_evidence": False,
        "proponent": "Bell Canada",
        "source_power_mw": 300,
        "source_power_metric": "source_wording_industrial_ai_data_centre_mw",
        "start_date": "2026-06-05",
    },
}

RIGHTS_POLICY = {
    "attribution_required_for_noncommercial_reproduction": True,
    "commercial_redistribution_permission_required_unless_otherwise_specified": True,
    "general_terms_url": TERMS_URL,
    "geospatial_archives_license_id": "OGL-Canada",
    "geospatial_archives_license_name": "Open Government Licence - Canada",
    "geospatial_archives_license_url": OGL_URL,
    "geospatial_archives_publication_eligible": True,
    "geospatial_license_applies_only_where_the_iaac_landing_page_says_so": True,
    "legal_conclusion_claimed": False,
    "official_symbols_excluded": True,
    "project_and_search_html_publication_eligible": False,
    "project_and_search_html_retained_for_audit_only": True,
    "third_party_material_may_have_separate_copyright": True,
    "verified_local_date": "2026-07-18",
}

INFERENCE_POLICY = {
    "annual_energy_mwh": None,
    "assessment_status_is_physical_lifecycle": False,
    "atlas_facility_identity": None,
    "atlas_lifecycle_status": None,
    "bell_300_mw_is_annual_energy": False,
    "bell_300_mw_is_it_capacity": False,
    "bell_physical_activity_substantially_begun_is_construction_evidence": True,
    "bell_physical_activity_substantially_begun_is_operation_evidence": False,
    "data_centre_type": None,
    "generation_capacity_is_data_centre_load": False,
    "gross_facility_power_mw": None,
    "identity_merge_performed": False,
    "it_capacity_mw": None,
    "operation_verified": False,
    "pue": None,
    "review_only": True,
    "unique_physical_site_count": None,
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "assessment.json",
        "definition.json",
        "direct-observations.jsonl",
        "geospatial-inventory.jsonl",
        "retrieval-inventory.json",
        "schema.json",
        "search-inventory.jsonl",
        "source-inventory.json",
    }
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_PATH_RE = re.compile(r"^/050/evaluations/proj/(?P<reference>\d+)$")
DOCUMENT_PATH_RE = re.compile(r"^/050/evaluations/document/(?P<reference>\d+)$")
ZIP_PATH_RE = re.compile(r"^/050/documents/p\d+/[\w.-]+\.zip$", re.IGNORECASE)
_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)


class IAACRegistryError(ValueError):
    """Raised when IAAC capture, parsing, or validation fails closed."""


class _Node:
    def __init__(
        self,
        tag: str,
        attributes: dict[str, str],
        parent: "_Node | None" = None,
    ) -> None:
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.children: list[_Node] = []
        self.content: list[str | _Node] = []

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attributes.get("class", "").split())

    def text(self) -> str:
        values: list[str] = []

        def visit(node: _Node) -> None:
            for item in node.content:
                if isinstance(item, str):
                    values.append(item)
                else:
                    visit(item)

        visit(self)
        return " ".join(" ".join(values).split())

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
            self.stack[-1],
        )
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
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
            self.stack[-1].content.append(data)


def _html_tree(body: bytes, context: str) -> _Node:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IAACRegistryError(f"{context} is not UTF-8") from error
    parser = _TreeParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:
        raise IAACRegistryError(f"could not parse {context}") from error
    return parser.root


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def project_url(reference_number: str) -> str:
    if reference_number not in DIRECT_PROJECTS:
        raise IAACRegistryError("project reference is outside the closed direct set")
    return PROJECT_URL_TEMPLATE.format(reference_number=reference_number)


def geospatial_document_url(document_id: str) -> str:
    if document_id not in GEOSPATIAL_DOCUMENTS:
        raise IAACRegistryError("geospatial document is outside the closed set")
    return f"https://iaac-aeic.gc.ca/050/evaluations/document/{document_id}"


def parse_geospatial_download_url(body: bytes, *, document_id: str) -> str:
    """Return the sole IAAC ZIP linked by an explicitly licensed landing page."""

    root = _html_tree(body, f"geospatial document {document_id}")
    ogl_links = [
        node
        for node in root.descendants()
        if node.tag == "a"
        and node.attributes.get("href") == OGL_URL
        and "Open Government Licence" in node.text()
    ]
    if len(ogl_links) != 1 or document_id not in GEOSPATIAL_DOCUMENTS:
        raise IAACRegistryError("geospatial landing lacks the explicit OGL statement")
    links: list[str] = []
    for node in root.descendants():
        href = node.attributes.get("href")
        if node.tag != "a" or not href or not href.lower().endswith(".zip"):
            continue
        absolute = urljoin(geospatial_document_url(document_id), href)
        parsed = urlsplit(absolute)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "iaac-aeic.gc.ca"
            or not ZIP_PATH_RE.fullmatch(parsed.path)
            or parsed.query
            or parsed.fragment
        ):
            raise IAACRegistryError("geospatial landing links an unexpected ZIP")
        links.append(absolute)
    links = list(dict.fromkeys(links))
    if len(links) != 1:
        raise IAACRegistryError(
            f"expected one licensed ZIP on document {document_id}, found {len(links)}"
        )
    return links[0]


def _nodes_with_class(root: _Node, class_name: str) -> list[_Node]:
    return [node for node in root.descendants() if class_name in node.classes]


def _node_by_id(root: _Node, element_id: str) -> _Node:
    nodes = [
        node for node in root.descendants()
        if node.attributes.get("id") == element_id
    ]
    if len(nodes) != 1:
        raise IAACRegistryError(
            f"expected one element id {element_id!r}, found {len(nodes)}"
        )
    return nodes[0]


def _one_node_with_class(root: _Node, class_name: str) -> _Node:
    nodes = _nodes_with_class(root, class_name)
    if len(nodes) != 1:
        raise IAACRegistryError(
            f"expected one {class_name!r} element, found {len(nodes)}"
        )
    return nodes[0]


def _one_descendant_tag(root: _Node, tag: str) -> _Node:
    nodes = [node for node in root.descendants() if node.tag == tag]
    if len(nodes) != 1:
        raise IAACRegistryError(
            f"expected one {tag!r} element, found {len(nodes)}"
        )
    return nodes[0]


def _remove_prefix(value: str, prefix: str, context: str) -> str:
    if not value.startswith(prefix):
        raise IAACRegistryError(f"could not parse {context}")
    result = value[len(prefix):].strip()
    if not result:
        raise IAACRegistryError(f"empty {context}")
    return result


def parse_search_results(body: bytes) -> list[dict[str, Any]]:
    """Preserve every displayed project result from the exact bounded query."""

    root = _html_tree(body, "IAAC project search")
    count_text = _node_by_id(root, "projects-found").text()
    if count_text != str(EXPECTED_SEARCH_RESULTS):
        raise IAACRegistryError("displayed IAAC search count changed")
    wrapper = _node_by_id(root, "project_details_div")
    articles = [child for child in wrapper.children if child.tag == "article"]
    rows: list[dict[str, Any]] = []
    for position, article in enumerate(articles, start=1):
        result_link = _one_node_with_class(article, "resultJobItem")
        href = result_link.attributes.get("href")
        if not href:
            raise IAACRegistryError("search result lacks a project URL")
        parsed = urlsplit(href)
        match = PROJECT_PATH_RE.fullmatch(parsed.path)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "iaac-aeic.gc.ca"
            or match is None
            or parsed.query
            or parsed.fragment
        ):
            raise IAACRegistryError("search result has an unexpected project URL")
        reference = match.group("reference")
        title = _one_node_with_class(article, "noctitle").text()
        location_text = _one_node_with_class(article, "location").text()
        location = _remove_prefix(location_text, "Location", "search location")
        if not (location.startswith("(") and location.endswith(")")):
            raise IAACRegistryError("search location is not parenthesized")
        location = location[1:-1].strip()

        fields: dict[str, str] = {}
        for node in _nodes_with_class(article, "salary"):
            value = node.text()
            if ":" not in value:
                raise IAACRegistryError("search metadata row lacks a label")
            label, field_value = value.split(":", 1)
            label = label.strip()
            field_value = field_value.strip()
            if not label or not field_value or label in fields:
                raise IAACRegistryError("search metadata row is invalid")
            fields[label] = field_value
        required = {
            "Assessment Type", "Last Modified", "Reference Number", "Relevance",
            "Status",
        }
        if set(fields) != required or fields["Reference Number"] != reference:
            raise IAACRegistryError("search metadata field contract changed")
        snippets = _nodes_with_class(article, "business")
        if len(snippets) > 1:
            raise IAACRegistryError("search result has multiple snippets")
        rows.append(
            {
                "assessment_status": fields["Status"],
                "assessment_type": fields["Assessment Type"],
                "last_modified": fields["Last Modified"],
                "location": location,
                "project_url": href,
                "reference_number": reference,
                "relevance_score_text": fields["Relevance"],
                "result_position": position,
                "search_snippet": snippets[0].text() if snippets else None,
                "title": title,
            }
        )
    if len(rows) != EXPECTED_SEARCH_RESULTS:
        raise IAACRegistryError("parsed search row count changed")
    references = [row["reference_number"] for row in rows]
    if len(set(references)) != len(references):
        raise IAACRegistryError("search result references are not unique")
    return rows


def classify_search_results(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the pinned, explicit decision for each of the 41 observations."""

    values = [dict(row) for row in rows]
    observed = {row.get("reference_number") for row in values}
    expected = set(DIRECT_PROJECTS) | set(EXCLUSION_DECISIONS)
    if observed != expected or len(values) != len(expected):
        raise IAACRegistryError("search inventory is not the pinned closed set")
    classified: list[dict[str, Any]] = []
    for row in values:
        reference = row["reference_number"]
        if reference in DIRECT_PROJECTS:
            if row["title"] != DIRECT_PROJECTS[reference]["title"]:
                raise IAACRegistryError("direct-result title changed")
            decision = DIRECT_DECISIONS[reference]
            classification = {
                "classification": "direct",
                "exclusion_category": None,
                "observation_role": decision["observation_role"],
                "review_reason": decision["reason"],
            }
        else:
            decision = EXCLUSION_DECISIONS[reference]
            if row["title"] != decision["title"]:
                raise IAACRegistryError("excluded-result title changed")
            classification = {
                "classification": "excluded",
                "exclusion_category": decision["category"],
                "observation_role": None,
                "review_reason": decision["reason"],
            }
        classified.append(row | classification)
    if (
        sum(row["classification"] == "direct" for row in classified)
        != EXPECTED_DIRECT_RESULTS
        or sum(row["classification"] == "excluded" for row in classified)
        != EXPECTED_EXCLUDED_RESULTS
    ):
        raise IAACRegistryError("classification arithmetic changed")
    return classified


def _project_detail_pairs(root: _Node) -> dict[str, str]:
    details = _node_by_id(root, "projectDetails")
    pairs: dict[str, str] = {}
    for item in [child for child in details.children if child.tag == "li"]:
        headings = [
            node for node in item.descendants()
            if node.tag == "h3" and "h5" in node.classes
        ]
        if len(headings) != 1:
            raise IAACRegistryError("project detail row has no unique label")
        label = headings[0].text()
        value = _remove_prefix(item.text(), label, f"project detail {label}")
        if label in pairs:
            raise IAACRegistryError("duplicate project detail label")
        pairs[label] = value
    required = {
        "Assessment Status", "Assessment Type", "Authorities", "Location",
        "Nature of Activity", "Proponent", "Reference Number", "Start Date",
    }
    if set(pairs) != required:
        raise IAACRegistryError("project detail fields changed")
    return pairs


def _power_sentence(summary: str, reference_number: str) -> str:
    marker = "300-megawatt" if reference_number == "90514" else "production capacity"
    sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", summary)]
    matches = [sentence for sentence in sentences if marker in sentence]
    if len(matches) != 1:
        raise IAACRegistryError("project power statement is not unique")
    return matches[0]


def parse_project_page(body: bytes, *, expected_reference: str) -> dict[str, Any]:
    """Parse only IAAC-authored project-page facts in the closed direct set."""

    if expected_reference not in DIRECT_PROJECTS:
        raise IAACRegistryError("expected project is outside the closed direct set")
    root = _html_tree(body, f"IAAC project {expected_reference}")
    panels = _nodes_with_class(root, "project-panel")
    if len(panels) != 1:
        raise IAACRegistryError("project page has no unique project panel")
    panel = panels[0]
    title = _one_descendant_tag(panel, "h1").text()
    summary = _one_node_with_class(panel, "project-summary-content").text()
    latest_update = _node_by_id(panel, "latestUpdates").text()
    details = _project_detail_pairs(panel)
    if (
        title != DIRECT_PROJECTS[expected_reference]["title"]
        or details["Reference Number"] != expected_reference
    ):
        raise IAACRegistryError("project page identity changed")
    contract = PROJECT_FACT_CONTRACTS[expected_reference]
    exact_fields = {
        "assessment_status": details["Assessment Status"],
        "assessment_type": details["Assessment Type"],
        "location": details["Location"],
        "nature_of_activity": details["Nature of Activity"],
        "proponent": details["Proponent"],
        "start_date": details["Start Date"],
    }
    for field, value in exact_fields.items():
        if value != contract[field]:
            raise IAACRegistryError(
                f"project {expected_reference} exact field changed: {field}"
            )
    if "proposing" not in summary:
        raise IAACRegistryError("project summary no longer contains proposal wording")
    power_statement = _power_sentence(summary, expected_reference)
    normalized_statement = power_statement.replace(",", "")
    expected_power = str(contract["source_power_mw"])
    if expected_power not in normalized_statement:
        raise IAACRegistryError("project power statement changed")
    if expected_reference != "90514" and "to support a new data centre" not in power_statement:
        raise IAACRegistryError("supporting-generation context changed")
    if expected_reference == "90514":
        required = (
            "300-megawatt industrial artificial intelligence data centre on a "
            "65-hectare agricultural site"
        )
        if required not in summary:
            raise IAACRegistryError("Bell capacity/site-area wording changed")
        if "physical activity has substantially begun" not in latest_update:
            raise IAACRegistryError("Bell construction-evidence wording changed")
    else:
        if "physical activity has substantially begun" in latest_update:
            raise IAACRegistryError("unexpected physical-activity evidence")
    return {
        "assessment_process": {
            "assessment_status_exact": details["Assessment Status"],
            "assessment_type_exact": details["Assessment Type"],
            "assessment_status_is_physical_lifecycle": False,
            "start_date_exact": details["Start Date"],
        },
        "atlas_inference": INFERENCE_POLICY,
        "authorities": details["Authorities"],
        "construction_evidence": (
            {
                "as_of_date": "2026-06-05",
                "method": "iaac_latest_update_physical_activity_substantially_begun",
                "operation_evidence": False,
                "source_text": latest_update,
            }
            if expected_reference == "90514"
            else None
        ),
        "data_centre_capacity": (
            {
                "metric": "source_wording_industrial_ai_data_centre_mw",
                "source_text": power_statement,
                "unit": "MW",
                "value": 300,
                "is_annual_energy": False,
                "is_it_capacity": False,
            }
            if expected_reference == "90514"
            else None
        ),
        "geospatial_document_id": DIRECT_PROJECTS[expected_reference][
            "geospatial_document_id"
        ],
        "latest_update_exact": latest_update,
        "location_exact": details["Location"],
        "nature_of_activity_exact": details["Nature of Activity"],
        "project_summary_exact": summary,
        "proponent_exact": details["Proponent"],
        "proposal_wording_present": True,
        "reference_number": expected_reference,
        "site_area": (
            {
                "metric": "source_wording_agricultural_site_area",
                "unit": "ha",
                "value": 65,
            }
            if expected_reference == "90514"
            else None
        ),
        "source_power_statement": {
            "is_annual_energy": False,
            "is_data_centre_load": (
                None if expected_reference == "90514" else False
            ),
            "is_it_capacity": False,
            "metric": contract["source_power_metric"],
            "source_text": power_statement,
            "unit": "MW",
            "value": contract["source_power_mw"],
        },
        "standardized_data_centre_type": None,
        "title": title,
    }


def parse_geospatial_landing(
    body: bytes, *, document_id: str
) -> dict[str, Any]:
    """Parse the explicit licence statement and advertised layer inventory."""

    if document_id not in GEOSPATIAL_DOCUMENTS:
        raise IAACRegistryError("geospatial document is outside the closed set")
    root = _html_tree(body, f"geospatial document {document_id}")
    download_url = parse_geospatial_download_url(body, document_id=document_id)
    project_reference = GEOSPATIAL_DOCUMENTS[document_id]
    project_links = []
    for node in root.descendants():
        href = node.attributes.get("href")
        if node.tag != "a" or not href:
            continue
        parsed = urlsplit(urljoin(geospatial_document_url(document_id), href))
        match = PROJECT_PATH_RE.fullmatch(parsed.path)
        if match and match.group("reference") == project_reference:
            project_links.append(node)
    if len(project_links) != 1:
        raise IAACRegistryError("geospatial landing project link changed")
    project_title = project_links[0].text()
    if project_title != DIRECT_PROJECTS[project_reference]["title"]:
        raise IAACRegistryError("geospatial landing project title changed")
    tables = _nodes_with_class(root, "table-bordered")
    if len(tables) != 1:
        raise IAACRegistryError("geospatial landing layer table changed")
    body_nodes = [node for node in tables[0].descendants() if node.tag == "tbody"]
    if len(body_nodes) != 1:
        raise IAACRegistryError("geospatial layer table lacks one body")
    layers: list[dict[str, str]] = []
    for row in [child for child in body_nodes[0].children if child.tag == "tr"]:
        cells = [child.text() for child in row.children if child.tag == "td"]
        if len(cells) != 2 or not all(cells):
            raise IAACRegistryError("geospatial layer row changed")
        layers.append({"layer_name_exact": cells[0], "page_number_text": cells[1]})
    expected_count = 4 if project_reference == "90036" else 2
    if len(layers) != expected_count:
        raise IAACRegistryError("geospatial advertised layer count changed")
    return {
        "advertised_layers": layers,
        "document_id": document_id,
        "download_url": download_url,
        "license": {
            "explicit_on_landing": True,
            "id": "OGL-Canada",
            "name": "Open Government Licence - Canada",
            "url": OGL_URL,
        },
        "project_reference": project_reference,
        "project_title": project_title,
    }


def inspect_geospatial_archive(body: bytes) -> dict[str, Any]:
    """Inventory ZIP members without extracting or reading attachment bodies."""

    try:
        archive = ZipFile(io.BytesIO(body))
    except BadZipFile as error:
        raise IAACRegistryError("geospatial archive is not a ZIP") from error
    with archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= 500:
            raise IAACRegistryError("geospatial archive member count is unsafe")
        names: set[str] = set()
        members: list[dict[str, Any]] = []
        total = 0
        for info in infos:
            path = Path(info.filename)
            if (
                info.filename in names
                or path.is_absolute()
                or ".." in path.parts
                or info.flag_bits & 0x1
            ):
                raise IAACRegistryError("geospatial archive has an unsafe member")
            names.add(info.filename)
            total += info.file_size
            if total > 20_000_000:
                raise IAACRegistryError("geospatial archive expands beyond the cap")
            members.append(
                {
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "filename": info.filename,
                    "is_directory": info.is_dir(),
                    "uncompressed_bytes": info.file_size,
                }
            )
    return {
        "archive_member_count": len(members),
        "archive_members": members,
        "archive_uncompressed_bytes": total,
        "attachment_bodies_inspected": False,
        "nested_archives_extracted": False,
    }


def source_definition() -> dict[str, Any]:
    return {
        "coverage": {
            "complete_for_canada": False,
            "geography": "Canada",
            "scope": "one exact IAAC project-document search for data center",
            "unique_physical_site_count": None,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "network_policy": {
            "backoff_seconds_by_retry": [2, 4],
            "expected_successful_requests": EXPECTED_NETWORK_REQUESTS,
            "maximum_attempts_per_url": 3,
            "maximum_network_requests_per_run": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "published_numeric_server_rate_limit_found": False,
        },
        "publisher": "Impact Assessment Agency of Canada",
        "query": {
            "culture": "en-CA",
            "document_type": "project",
            "exact_url": SEARCH_URL,
            "search_text": "data center",
        },
        "release_id": RELEASE_ID,
        "retention": {
            "all_search_results_preserved": True,
            "direct_project_pages_fetched": sorted(DIRECT_PROJECTS),
            "geospatial_archives_fetched_only_after_explicit_ogl_statement": True,
            "initial_project_descriptions_fetched": False,
            "other_attachments_fetched": False,
            "public_comments_or_submissions_fetched": False,
            "raw_project_and_search_html_audit_only": True,
            "third_party_pdfs_fetched": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "iaac-data-center-search",
        "source_urls": {
            "general_terms": TERMS_URL,
            "open_government_licence": OGL_URL,
            "search": SEARCH_URL,
        },
        "title": "IAAC data center project-search observations",
    }


def _timestamp(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise IAACRegistryError(f"{field_name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IAACRegistryError(f"{field_name} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IAACRegistryError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _jsonl(records: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(dict(record)) for record in records)


def _raw_inventory(
    retrievals: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "artifact_id": artifact_id,
                "bytes": retrieval["bytes"],
                "content_type": retrieval["content_type"],
                "document_id": retrieval.get("document_id"),
                "effective_url": retrieval["effective_url"],
                "fetched_at": retrieval["fetched_at"],
                "filename": retrieval["filename"],
                "headers": retrieval["headers"],
                "http_status": retrieval["http_status"],
                "project_reference": retrieval.get("project_reference"),
                "sha256": retrieval["sha256"],
                "url": retrieval["url"],
            }
            for artifact_id, retrieval in retrievals.items()
        ],
        key=lambda row: row["filename"],
    )


def _raw_inventory_digest(inventory: Iterable[Mapping[str, Any]]) -> str:
    compact = [
        {"filename": row["filename"], "sha256": row["sha256"]}
        for row in inventory
    ]
    return sha256_bytes(canonical_json(compact))


def _closed_set_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    compact = [
        {
            "classification": row["classification"],
            "exclusion_category": row["exclusion_category"],
            "reference_number": row["reference_number"],
            "result_position": row["result_position"],
            "title": row["title"],
        }
        for row in rows
    ]
    return sha256_bytes(canonical_json(compact))


def _expected_retrieval_contract() -> dict[str, dict[str, Any]]:
    contract: dict[str, dict[str, Any]] = {
        "search": {
            "content_types": {"text/html"},
            "document_id": None,
            "filename": "raw/search.html",
            "project_reference": None,
            "url": SEARCH_URL,
        }
    }
    for reference in sorted(DIRECT_PROJECTS):
        contract[f"project_{reference}"] = {
            "content_types": {"text/html"},
            "document_id": None,
            "filename": f"raw/project-{reference}.html",
            "project_reference": reference,
            "url": project_url(reference),
        }
    for document_id, reference in sorted(GEOSPATIAL_DOCUMENTS.items()):
        contract[f"geospatial_landing_{document_id}"] = {
            "content_types": {"text/html"},
            "document_id": document_id,
            "filename": f"raw/geospatial-{document_id}.html",
            "project_reference": reference,
            "url": geospatial_document_url(document_id),
        }
    return contract


def _validate_capture(
    capture: Mapping[str, Any], raw_bodies: Mapping[str, bytes]
) -> dict[str, Any]:
    if capture.get("network_requests") != EXPECTED_NETWORK_REQUESTS:
        raise IAACRegistryError("capture request arithmetic changed")
    if capture.get("minimum_request_interval_seconds") != 1.0:
        raise IAACRegistryError("capture pacing contract changed")
    if capture.get("maximum_network_requests") != MAX_NETWORK_REQUESTS:
        raise IAACRegistryError("capture request cap changed")
    if capture.get("maximum_attempts_per_url") != 3:
        raise IAACRegistryError("capture retry contract changed")
    captured_at = _timestamp(capture.get("captured_at"), "capture.captured_at")
    retrievals_value = capture.get("retrievals")
    if not isinstance(retrievals_value, Mapping):
        raise IAACRegistryError("capture retrievals must be an object")
    retrievals: dict[str, Mapping[str, Any]] = {}
    for artifact_id, value in retrievals_value.items():
        if not isinstance(artifact_id, str) or not isinstance(value, Mapping):
            raise IAACRegistryError("capture retrieval record is invalid")
        retrievals[artifact_id] = value

    contract = _expected_retrieval_contract()
    if set(retrievals) != set(contract) | {
        f"geospatial_archive_{document_id}" for document_id in GEOSPATIAL_DOCUMENTS
    }:
        raise IAACRegistryError("capture retrieval closed set changed")
    filenames: set[str] = set()
    for artifact_id, retrieval in retrievals.items():
        if artifact_id.startswith("geospatial_archive_"):
            document_id = artifact_id.removeprefix("geospatial_archive_")
            reference = GEOSPATIAL_DOCUMENTS.get(document_id)
            if reference is None:
                raise IAACRegistryError("archive retrieval document changed")
            landing_filename = contract[f"geospatial_landing_{document_id}"][
                "filename"
            ]
            expected_url = parse_geospatial_download_url(
                raw_bodies[landing_filename], document_id=document_id
            )
            expected = {
                "content_types": {
                    "application/octet-stream",
                    "application/x-zip-compressed",
                    "application/zip",
                },
                "document_id": document_id,
                "filename": f"raw/geospatial-{document_id}.zip",
                "project_reference": reference,
                "url": expected_url,
            }
        else:
            expected = contract[artifact_id]
        filename = retrieval.get("filename")
        if (
            filename != expected["filename"]
            or not isinstance(filename, str)
            or filename in filenames
        ):
            raise IAACRegistryError("capture raw filename changed")
        filenames.add(filename)
        if (
            retrieval.get("url") != expected["url"]
            or retrieval.get("effective_url") != expected["url"]
            or retrieval.get("document_id") != expected["document_id"]
            or retrieval.get("project_reference") != expected["project_reference"]
            or retrieval.get("attempt") != 1
            or retrieval.get("http_status") != 200
            or retrieval.get("content_type") not in expected["content_types"]
        ):
            raise IAACRegistryError("capture request/response metadata changed")
        digest = retrieval.get("sha256")
        size = retrieval.get("bytes")
        headers = retrieval.get("headers")
        if (
            not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(headers, Mapping)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items())
        ):
            raise IAACRegistryError("capture response lineage is invalid")
        _timestamp(retrieval.get("fetched_at"), f"retrievals.{artifact_id}.fetched_at")
        body = raw_bodies.get(filename)
        if (
            not isinstance(body, bytes)
            or len(body) != size
            or sha256_bytes(body) != digest
        ):
            raise IAACRegistryError(f"raw artifact mismatch: {filename}")
    if set(raw_bodies) != filenames:
        raise IAACRegistryError("raw body inventory changed")

    inventory = _raw_inventory(retrievals)
    if sum(row["bytes"] for row in inventory) != EXPECTED_RAW_BYTES:
        raise IAACRegistryError("raw byte total changed")
    if _raw_inventory_digest(inventory) != EXPECTED_RAW_INVENTORY_SHA256:
        raise IAACRegistryError("raw inventory digest changed")

    search_rows = classify_search_results(parse_search_results(raw_bodies["raw/search.html"]))
    if _closed_set_digest(search_rows) != EXPECTED_CLOSED_SET_SHA256:
        raise IAACRegistryError("search closed-set digest changed")
    if sha256_bytes(_jsonl(search_rows)) != EXPECTED_SEARCH_INVENTORY_SHA256:
        raise IAACRegistryError("classified search inventory digest changed")

    projects: dict[str, dict[str, Any]] = {}
    search_by_reference = {row["reference_number"]: row for row in search_rows}
    for reference in sorted(DIRECT_PROJECTS):
        project = parse_project_page(
            raw_bodies[f"raw/project-{reference}.html"],
            expected_reference=reference,
        )
        search_row = search_by_reference[reference]
        if (
            project["title"] != search_row["title"]
            or project["assessment_process"]["assessment_status_exact"]
            != search_row["assessment_status"]
            or project["assessment_process"]["assessment_type_exact"]
            != search_row["assessment_type"]
        ):
            raise IAACRegistryError("direct search/project facts disagree")
        projects[reference] = project

    geospatial: dict[str, dict[str, Any]] = {}
    for document_id, reference in sorted(GEOSPATIAL_DOCUMENTS.items()):
        landing = parse_geospatial_landing(
            raw_bodies[f"raw/geospatial-{document_id}.html"],
            document_id=document_id,
        )
        archive = inspect_geospatial_archive(
            raw_bodies[f"raw/geospatial-{document_id}.zip"]
        )
        archive_retrieval = retrievals[f"geospatial_archive_{document_id}"]
        if (
            landing["project_reference"] != reference
            or landing["download_url"] != archive_retrieval["url"]
        ):
            raise IAACRegistryError("geospatial landing/archive lineage changed")
        geospatial[document_id] = landing | archive

    fetched_at = [row["fetched_at"] for row in inventory]
    return {
        "assessed_at": max(fetched_at),
        "batch_started_at": min(fetched_at),
        "capture_completed_at": captured_at,
        "geospatial": geospatial,
        "inventory": inventory,
        "projects": projects,
        "retrievals": retrievals,
        "search_rows": search_rows,
    }


def _search_inventory(validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    retrieval = validated["retrievals"]["search"]
    return [
        {
            **row,
            "observation_id": f"iaac:search:{row['reference_number']}",
            "record_type": "iaac_project_search_observation",
            "source": {
                "fetched_at": retrieval["fetched_at"],
                "raw_filename": retrieval["filename"],
                "raw_sha256": retrieval["sha256"],
                "url": retrieval["url"],
            },
        }
        for row in validated["search_rows"]
    ]


def _direct_observations(validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    search_by_reference = {
        row["reference_number"]: row for row in validated["search_rows"]
    }
    records: list[dict[str, Any]] = []
    for reference in sorted(DIRECT_PROJECTS):
        retrieval = validated["retrievals"][f"project_{reference}"]
        search_row = search_by_reference[reference]
        records.append(
            validated["projects"][reference]
            | {
                "observation_id": f"iaac:project:{reference}",
                "observation_role": search_row["observation_role"],
                "record_type": "iaac_direct_project_observation",
                "review_reason": search_row["review_reason"],
                "search_observation_id": f"iaac:search:{reference}",
                "source": {
                    "fetched_at": retrieval["fetched_at"],
                    "raw_filename": retrieval["filename"],
                    "raw_sha256": retrieval["sha256"],
                    "url": retrieval["url"],
                },
                "unique_physical_site_id": None,
            }
        )
    return records


def _geospatial_inventory(validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for document_id in sorted(GEOSPATIAL_DOCUMENTS):
        landing = validated["retrievals"][f"geospatial_landing_{document_id}"]
        archive = validated["retrievals"][f"geospatial_archive_{document_id}"]
        records.append(
            validated["geospatial"][document_id]
            | {
                "archive_source": {
                    "bytes": archive["bytes"],
                    "content_type": archive["content_type"],
                    "fetched_at": archive["fetched_at"],
                    "raw_filename": archive["filename"],
                    "raw_sha256": archive["sha256"],
                    "url": archive["url"],
                },
                "landing_source": {
                    "fetched_at": landing["fetched_at"],
                    "raw_filename": landing["filename"],
                    "raw_sha256": landing["sha256"],
                    "url": landing["url"],
                },
                "record_type": "iaac_ogl_geospatial_archive",
                "site_identity_resolved": False,
            }
        )
    return records


def derive_release_files(
    capture: Mapping[str, Any], raw_bodies: Mapping[str, bytes]
) -> dict[str, bytes]:
    """Derive every assessment artifact from the bounded retained capture."""

    validated = _validate_capture(capture, raw_bodies)
    search_rows = _search_inventory(validated)
    direct_rows = _direct_observations(validated)
    geospatial_rows = _geospatial_inventory(validated)
    exclusion_counts: dict[str, int] = {}
    for row in validated["search_rows"]:
        category = row["exclusion_category"]
        if category is not None:
            exclusion_counts[category] = exclusion_counts.get(category, 0) + 1
    assessment = {
        "assessed_at": validated["assessed_at"],
        "atlas_decision": {
            "master_or_ledger_import_permitted": False,
            "physical_site_identity_published": False,
            "raw_project_and_search_html_publication_eligible": False,
            "status": "isolated_official_registry_assessment_lane",
            "unique_site_count_published": False,
        },
        "capacity_assessment": {
            "annual_energy_mwh": None,
            "bell_source_wording": {
                "annual_energy_inference_permitted": False,
                "it_capacity_inference_permitted": False,
                "metric": "source_wording_industrial_ai_data_centre_mw",
                "value_mw": 300,
            },
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "pue": None,
            "supporting_generation_not_data_centre_load_mw": {
                "90036": 650,
                "90121": 1494,
                "90123": 920,
            },
        },
        "coverage_assessment": {
            "assessment_status_completed_rows": 4,
            "construction_evidence_rows": 1,
            "data_centre_project_observations": 1,
            "direct_observations": EXPECTED_DIRECT_RESULTS,
            "geospatial_archives": 3,
            "operation_evidence_rows": 0,
            "proposal_wording_rows": 4,
            "supporting_generation_observations": 3,
            "unique_physical_site_count": None,
        },
        "format": ASSESSMENT_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "attempts_requiring_retry": 0,
            "batch_completed_at": validated["assessed_at"],
            "batch_started_at": validated["batch_started_at"],
            "geospatial_archive_requests": 3,
            "geospatial_landing_requests": 3,
            "maximum_request_cap": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": 1.0,
            "network_requests": EXPECTED_NETWORK_REQUESTS,
            "project_page_requests": 4,
            "raw_bytes": EXPECTED_RAW_BYTES,
            "raw_inventory_sha256": EXPECTED_RAW_INVENTORY_SHA256,
            "retrieval_mode": "bounded_live_fetch_then_offline_derivation",
            "search_page_requests": 1,
            "validator_network_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "selection_assessment": {
            "closed_set_sha256": EXPECTED_CLOSED_SET_SHA256,
            "direct_rows": EXPECTED_DIRECT_RESULTS,
            "excluded_rows": EXPECTED_EXCLUDED_RESULTS,
            "exclusion_category_counts": dict(sorted(exclusion_counts.items())),
            "result_rows": EXPECTED_SEARCH_RESULTS,
            "search_inventory_sha256": EXPECTED_SEARCH_INVENTORY_SHA256,
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
            "assessment_status_exact": "IAAC process status, never physical lifecycle",
            "construction_evidence": "Bell-only dated IAAC latest-update statement that physical activity substantially began",
            "data_centre_capacity": "Bell source wording only; neither IT capacity nor annual energy",
            "geospatial_archive": "explicitly OGL-Canada IAAC file; inventoried without reading embedded attachment bodies",
            "source_power_statement": "typed as supporting generation for 90036, 90121 and 90123; Bell remains untyped source wording rather than inferred data-centre load",
            "unique_physical_site_id": "always null in this observation-only assessment",
        },
        "format": SCHEMA_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "record_types": {
            "direct": "iaac_direct_project_observation",
            "geospatial": "iaac_ogl_geospatial_archive",
            "search": "iaac_project_search_observation",
        },
        "schema_version": SCHEMA_VERSION,
    }
    attribution = (
        "IAAC data center project-search assessment\n"
        "Source: Impact Assessment Agency of Canada\n"
        f"Search: {SEARCH_URL}\n"
        f"General terms: {TERMS_URL}\n\n"
        "The search and project HTML is retained for internal audit only. Under the "
        "general Canada.ca terms, non-commercial reproduction requires the stated "
        "conditions and commercial redistribution requires prior written permission "
        "unless otherwise specified. Third-party material can have separate rights.\n\n"
        "The three retained geospatial archives only are available under the Open "
        "Government Licence - Canada, as stated on IAAC documents 164351, 164355, "
        f"and 164503. Licence: {OGL_URL}\n"
        "Contains information licensed under the Open Government Licence - Canada.\n"
    ).encode("utf-8")
    readme = (
        "# IAAC data center project-search assessment\n\n"
        "This frozen, isolated lane preserves every one of the 41 project results "
        "returned by the exact IAAC search on 2026-07-18 local time. Four are direct "
        "observations and 37 are explicit false-positive exclusions. The direct set "
        "contains one data-centre project (Bell) and three proposed power-generation "
        "projects whose source descriptions say they would support new data centres.\n\n"
        "The 650 MW, 920 MW and 1,494 MW values are generation production capacity, "
        "not data-centre load or consumption. Bell's 300 MW is preserved as source "
        "wording for an industrial artificial-intelligence data centre; it is not "
        "converted to IT capacity or annual energy. No PUE or operation is inferred.\n\n"
        "IAAC `Completed` is assessment-process status. Bell's June 5, 2026 latest "
        "update says physical activity had substantially begun, which is retained as "
        "dated construction evidence but not operation evidence. The four records are "
        "observations only; unique physical site count remains null.\n\n"
        "Only the exact search page, four project pages, three explicitly licensed "
        "geospatial landing pages and their three ZIP files were fetched. No comments, "
        "submissions, initial project descriptions, PDFs, images, or other linked "
        "attachments were requested. Embedded archive members were inventoried by ZIP "
        "metadata only and not opened or extracted.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(source_definition()),
        "direct-observations.jsonl": _jsonl(direct_rows),
        "geospatial-inventory.jsonl": _jsonl(geospatial_rows),
        "retrieval-inventory.json": canonical_json(dict(capture)),
        "schema.json": canonical_json(schema),
        "search-inventory.jsonl": _jsonl(search_rows),
        "source-inventory.json": canonical_json(source_inventory),
    }


def _artifact_role(filename: str) -> str:
    if filename.startswith("raw/geospatial-") and filename.endswith(".zip"):
        return "explicitly_ogl_canada_geospatial_archive"
    if filename.startswith("raw/geospatial-"):
        return "geospatial_license_landing_audit_evidence"
    if filename.startswith("raw/"):
        return "official_registry_html_internal_audit_evidence"
    if filename == "search-inventory.jsonl":
        return "complete_classified_search_inventory"
    if filename == "direct-observations.jsonl":
        return "direct_project_observations"
    if filename == "geospatial-inventory.jsonl":
        return "licensed_geospatial_archive_inventory"
    return "release_metadata"


def _license_scope(filename: str) -> str:
    if filename.startswith("raw/geospatial-") and filename.endswith(".zip"):
        return "OGL-Canada_as_explicitly_stated_by_IAAC"
    if filename.startswith("raw/"):
        return "internal_audit_only_general_canada_ca_terms"
    return "derived_internal_assessment_with_source_attribution"


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
    """Write a new immutable release atomically without overwriting a path."""

    output_path = Path(output)
    if output_path.exists() or output_path.is_symlink():
        raise IAACRegistryError("output release already exists")
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
        manifest_body = _manifest_for_directory(temporary, validated["assessed_at"])
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
        raise IAACRegistryError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise IAACRegistryError(f"{label} is not canonical JSON")
    return value


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IAACRegistryError(f"{label} is not valid JSONL") from error
    if any(not isinstance(value, dict) for value in values):
        raise IAACRegistryError(f"{label} rows must be objects")
    if path.read_bytes() != _jsonl(values):
        raise IAACRegistryError(f"{label} is not canonical JSONL")
    return values


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    """Validate and reproduce the frozen source assessment entirely offline."""

    release = Path(path)
    if not release.is_dir() or release.is_symlink():
        raise IAACRegistryError("release must be a non-symlink directory")
    if any(entry.is_symlink() for entry in release.rglob("*")):
        raise IAACRegistryError("release cannot contain symlinks")
    capture = _load_canonical_json(
        release / "retrieval-inventory.json", "retrieval inventory"
    )
    retrievals = capture.get("retrievals")
    if not isinstance(retrievals, Mapping):
        raise IAACRegistryError("retrieval inventory has no retrievals")
    raw_filenames = {
        value.get("filename")
        for value in retrievals.values()
        if isinstance(value, Mapping)
    }
    if any(not isinstance(filename, str) for filename in raw_filenames):
        raise IAACRegistryError("retrieval raw filename inventory is invalid")
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
        raise IAACRegistryError("release file set changed")
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
        raise IAACRegistryError("manifest identity changed")
    expected_manifest = _manifest_for_directory(release, validated["assessed_at"])
    if (release / MANIFEST_FILENAME).read_bytes() != expected_manifest:
        raise IAACRegistryError("manifest does not bind the release files")
    sidecar = (
        f"{sha256_bytes(expected_manifest)}  {MANIFEST_FILENAME}\n".encode("utf-8")
    )
    if (release / MANIFEST_HASH_FILENAME).read_bytes() != sidecar:
        raise IAACRegistryError("manifest SHA-256 sidecar changed")

    reproduced = derive_release_files(capture, raw_bodies)
    for filename, expected in reproduced.items():
        if (release / filename).read_bytes() != expected:
            raise IAACRegistryError(f"offline reproduction mismatch: {filename}")
    assessment = _load_canonical_json(release / "assessment.json", "assessment")
    if assessment.get("rights_assessment") != RIGHTS_POLICY:
        raise IAACRegistryError("rights boundary changed")
    if assessment.get("inference_policy") != INFERENCE_POLICY:
        raise IAACRegistryError("inference boundary changed")
    return {
        "assessment": assessment,
        "definition": _load_canonical_json(release / "definition.json", "definition"),
        "direct_observations": _load_jsonl(
            release / "direct-observations.jsonl", "direct observations"
        ),
        "geospatial_inventory": _load_jsonl(
            release / "geospatial-inventory.jsonl", "geospatial inventory"
        ),
        "manifest": manifest,
        "schema": _load_canonical_json(release / "schema.json", "schema"),
        "search_inventory": _load_jsonl(
            release / "search-inventory.jsonl", "search inventory"
        ),
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
