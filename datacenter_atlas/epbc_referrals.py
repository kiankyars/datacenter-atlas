"""Bounded EPBC Act Public Portal data-centre source assessment.

The portal exposes an anonymous Power Pages entity-grid request, but its linked
portal terms do not grant redistribution rights for portal material.  Raw pages,
query results, and proposer-supplied descriptions therefore stay in an
operator-provided quarantine.  The frozen release is metadata-only: it records
the bounded search contract, result/classification arithmetic, rights decision,
and tamper-evident hashes without publishing referral rows.

Portal workflow status is process metadata, never physical construction or
operation evidence.  Supporting generation and storage values are never mapped
to data-centre IT load or annual energy consumption.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import base64
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "epbc-public-portal-data-centre-search-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-epbc-referrals-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-epbc-referrals-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-epbc-referrals-assessment-v1"
QUERY_SUMMARY_FORMAT = "datacenter-atlas-epbc-referrals-query-summary-v1"
INVENTORY_FORMAT = "datacenter-atlas-epbc-referrals-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-epbc-referrals-schema-v1"

PORTAL_ORIGIN = "https://epbcpublicportal.environment.gov.au"
ALL_REFERRALS_URL = f"{PORTAL_ORIGIN}/all-referrals/"
GRID_ENDPOINT = (
    f"{PORTAL_ORIGIN}/_services/entity-grid-data.json/"
    "2ab10dab-d681-4911-b881-cc99413f07b6"
)
TOKEN_URL = f"{PORTAL_ORIGIN}/_layout/tokenhtml"
DETAIL_URL_TEMPLATE = (
    f"{PORTAL_ORIGIN}/all-referrals/project-referral-summary/?id={{record_id}}"
)
PORTAL_TERMS_URL = "https://onlineservices.environment.gov.au/terms-and-conditions"
DCCEEW_COPYRIGHT_URL = "https://www.dcceew.gov.au/about/copyright"
PUBLIC_COMMENTS_URL = "https://www.dcceew.gov.au/environment/epbc/public-comments"

WEBSITE_ID = "2ab10dab-d681-4911-b881-cc99413f07b6"
ENTITY_LIST_ID = "18b9d47d-a12d-ec11-b6e6-0022481565ec"
VIEW_ID = "db1851f8-9f2d-ec11-b6e6-002248156b35"
ENTITY_NAME = "incident"
PRIMARY_KEY = "incidentid"
PAGE_SIZE = 10
SORT_EXPRESSION = "mara_validdate DESC"

SEARCH_PHRASES = ("data centre", "data center", "datacentre")
EXPECTED_QUERY_COUNTS = {
    "data centre": 2,
    "data center": 0,
    "datacentre": 0,
}
EXPECTED_RAW_HITS = 2
EXPECTED_UNIQUE_REFERRALS = 2
EXPECTED_CLASSIFICATION_COUNTS = {
    "ancillary_existing_data_centre_work": 0,
    "context_only": 0,
    "direct_data_centre_project": 2,
    "word_collision": 0,
}
EXPECTED_NETWORK_REQUESTS = 8
EXPECTED_QUARANTINED_RAW_ARTIFACTS = 7
MAX_NETWORK_REQUESTS = 15
MIN_REQUEST_INTERVAL_SECONDS = 1.0

# Filled from the exact, canonical closed set.  It detects changed IDs, titles,
# process fields, classifications, or scoped numeric statements without
# publishing those restricted values in the metadata-only release.
EXPECTED_CLOSED_SET_SHA256 = (
    "560ef608b4f0c9d24c230c84e29645aad4176e38573cd737a3fea288f066040e"
)
EXPECTED_POWER_SCOPE_SHA256 = (
    "b5611df1ba83e7935a40776c21e560bdfee69f5f205afc896dc3c5b372830f2d"
)

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
EPBC_NUMBER_RE = re.compile(r"^\d{4}/\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
POWER_RE = re.compile(
    r"(?<![\w.])(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>GWh|MWp|MVA|MW|GW)\b",
    flags=re.IGNORECASE,
)
DATA_CENTRE_RE = re.compile(r"\b(?:data\s+centre|data\s+center|datacentre)s?\b", re.I)
DIRECT_ACTION_RE = re.compile(
    r"\b(?:construct(?:ion)?|develop(?:ment)?|operation|use|campus|facility|data hall)s?\b",
    re.I,
)
CONTEXT_MARKER_RE = re.compile(
    r"\b(?:cable|fibre|fiber|substation|transmission|road|pipeline|chiller|cooler|"
    r"generator replacement|maintenance|demolition)\b",
    re.I,
)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
RELEASE_FILENAMES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "assessment.json",
        "definition.json",
        "query-summary.json",
        "retrieval-inventory.json",
        "schema.json",
        "source-inventory.json",
    }
)
EXPECTED_BUNDLE_FILES = RELEASE_FILENAMES | {
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}

OFFICIAL_HOSTS = frozenset(
    {
        "epbcpublicportal.environment.gov.au",
        "onlineservices.environment.gov.au",
        "www.dcceew.gov.au",
    }
)

RIGHTS_POLICY = {
    "assessment_status": "release_blocked_by_portal_terms",
    "commercial_reuse_permission_clear": False,
    "dccEEw_general_cc_by_4_notice_can_override_portal_terms": False,
    "dccEEw_general_notice_excludes_third_party_or_other_terms": True,
    "legal_conclusion_claimed": False,
    "portal_material_commercial_redistribution_permitted": False,
    "portal_material_reproduction_or_distribution_permission_clear": False,
    "portal_terms_access_and_download_limited_to_own_use": True,
    "portal_terms_prohibit_reproduction_distribution_retransmission_and_reposting": True,
    "proposer_supplied_description_rights_clear_for_release": False,
    "raw_artifacts_released": False,
    "raw_artifacts_retained_only_in_operator_quarantine": True,
    "referral_rows_released": False,
    "release_is_metadata_only": True,
    "rights_urls": [PORTAL_TERMS_URL, DCCEEW_COPYRIGHT_URL],
    "verified_local_date": "2026-07-18",
}

EVIDENCE_BOUNDARY = {
    "annual_energy_consumption_mwh": None,
    "atlas_lifecycle_status": None,
    "construction_verified": False,
    "data_centre_it_capacity_mw_released": False,
    "facility_identity_merge_performed": False,
    "gross_facility_power_mw": None,
    "operating_model": None,
    "operation_verified": False,
    "portal_status_is_process_only": True,
    "pue": None,
    "supporting_generation_or_storage_mapped_to_it_load": False,
    "unique_physical_site_count": None,
}


class EPBCReferralsError(ValueError):
    """Raised when retrieval, derivation, or validation fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_capture_state_hash(capture: Mapping[str, Any]) -> str:
    """Verify that a quarantine capture's self-hash binds every other field."""

    supplied = capture.get("capture_state_sha256")
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        raise EPBCReferralsError("quarantine capture-state hash is invalid")
    unhashed = dict(capture)
    del unhashed["capture_state_sha256"]
    if sha256_bytes(canonical_json(unhashed)) != supplied:
        raise EPBCReferralsError("quarantine capture-state hash mismatch")
    return supplied


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EPBCReferralsError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EPBCReferralsError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EPBCReferralsError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EPBCReferralsError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EPBCReferralsError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EPBCReferralsError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise EPBCReferralsError(f"{label} must contain an object")
    if path.read_bytes() != canonical_json(value):
        raise EPBCReferralsError(f"{label} is not canonical JSON")
    return value


def transport_expression(phrase: str) -> str:
    """Encode one exact phrase using the portal's documented substring syntax."""

    if phrase not in SEARCH_PHRASES:
        raise EPBCReferralsError(f"unapproved EPBC search phrase: {phrase!r}")
    return f"*{phrase}*"


def _tag_attributes(tag: str) -> dict[str, str]:
    return {
        name.lower(): unescape(double or single)
        for name, double, single in re.findall(
            r"([\w-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", tag
        )
    }


def parse_all_referrals_contract(body: bytes) -> dict[str, Any]:
    """Extract and fail closed on the current anonymous entity-grid contract."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EPBCReferralsError("all-referrals page is not UTF-8") from error
    match = re.search(r'<div class="entity-grid[^>]+>', text)
    if not match:
        raise EPBCReferralsError("all-referrals entity-grid was not found")
    attributes = _tag_attributes(match.group(0))
    required = {
        "data-get-url",
        "data-selected-view",
        "data-view-layouts",
    }
    if not required.issubset(attributes):
        raise EPBCReferralsError("all-referrals entity-grid contract is incomplete")
    endpoint = attributes["data-get-url"]
    if endpoint != urlsplit(GRID_ENDPOINT).path:
        raise EPBCReferralsError("entity-grid endpoint changed")
    if attributes["data-selected-view"] != VIEW_ID:
        raise EPBCReferralsError("entity-grid selected view changed")
    try:
        decoded = base64.b64decode(
            attributes["data-view-layouts"], validate=True
        )
        layouts = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as error:
        raise EPBCReferralsError("entity-grid layout is invalid") from error
    if not isinstance(layouts, list) or len(layouts) != 1:
        raise EPBCReferralsError("entity-grid layout count changed")
    layout = _object(layouts[0], "entity-grid layout")
    configuration = _object(layout.get("Configuration"), "grid configuration")
    search = _object(configuration.get("Search"), "grid search configuration")
    exact = {
        "EntityName": ENTITY_NAME,
        "PrimaryKeyName": PRIMARY_KEY,
        "ViewId": VIEW_ID,
        "PageSize": PAGE_SIZE,
        "FilterQueryStringParameterName": "filter",
        "SortQueryStringParameterName": "sort",
        "PageQueryStringParameterName": "page",
    }
    if any(configuration.get(key) != value for key, value in exact.items()):
        raise EPBCReferralsError("entity-grid configuration changed")
    if (
        search.get("Enabled") is not True
        or search.get("SearchQueryStringParameterName") != "query"
        or "asterisk" not in str(search.get("TooltipText", "")).lower()
        or "wildcard" not in str(search.get("TooltipText", "")).lower()
    ):
        raise EPBCReferralsError("entity-grid wildcard search contract changed")
    if layout.get("SortExpression") != SORT_EXPRESSION:
        raise EPBCReferralsError("entity-grid sort expression changed")
    secure_configuration = layout.get("Base64SecureConfiguration")
    if not isinstance(secure_configuration, str) or len(secure_configuration) < 100:
        raise EPBCReferralsError("secure grid configuration is missing")
    entity_list_match = re.search(
        r'id="EntityList(?P<id>[0-9a-f-]{36})"', text, flags=re.I
    )
    if not entity_list_match or entity_list_match.group("id").lower() != ENTITY_LIST_ID:
        raise EPBCReferralsError("entity-list identifier changed")
    return {
        "base64_secure_configuration": secure_configuration,
        "entity_list_id": ENTITY_LIST_ID,
        "entity_name": ENTITY_NAME,
        "endpoint": GRID_ENDPOINT,
        "page_size": PAGE_SIZE,
        "primary_key": PRIMARY_KEY,
        "search_query_parameter": "query",
        "sort_expression": SORT_EXPRESSION,
        "transport_rule": "literal phrase wrapped once with leading and trailing asterisks",
        "view_id": VIEW_ID,
        "website_id": WEBSITE_ID,
    }


def parse_antiforgery_token(body: bytes) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EPBCReferralsError("token response is not UTF-8") from error
    matches = re.findall(
        r'<input\s+name="__RequestVerificationToken"\s+type="hidden"\s+'
        r'value="([^"]+)"\s*/?>',
        text,
    )
    if len(matches) != 1 or len(matches[0]) < 40:
        raise EPBCReferralsError("anti-forgery token response changed")
    return matches[0]


def grid_request_document(
    contract: Mapping[str, Any],
    *,
    phrase: str,
    page: int,
    paging_cookie: str = "",
) -> dict[str, Any]:
    if page < 1 or not isinstance(paging_cookie, str):
        raise EPBCReferralsError("invalid grid pagination request")
    secure = contract.get("base64_secure_configuration")
    if not isinstance(secure, str) or not secure:
        raise EPBCReferralsError("grid contract lacks secure configuration")
    return {
        "base64SecureConfiguration": secure,
        "customParameters": [],
        "filter": None,
        "metaFilter": None,
        "nlSearchFilter": "",
        "page": page,
        "pageSize": PAGE_SIZE,
        "pagingCookie": paging_cookie,
        "search": transport_expression(phrase),
        "sortExpression": SORT_EXPRESSION,
        "timezoneOffset": 0,
    }


def parse_grid_response(
    body: bytes, *, phrase: str, expected_page: int
) -> dict[str, Any]:
    """Parse every returned row while keeping portal process fields distinct."""

    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EPBCReferralsError("entity-grid response is not valid JSON") from error
    if not isinstance(document, dict):
        raise EPBCReferralsError("entity-grid response must be an object")
    if document.get("AccessDenied") is True:
        raise EPBCReferralsError("entity-grid response denied anonymous access")
    numeric = {
        "ItemCount": document.get("ItemCount"),
        "PageCount": document.get("PageCount"),
        "PageNumber": document.get("PageNumber"),
        "PageSize": document.get("PageSize"),
    }
    if any(isinstance(value, bool) or not isinstance(value, int) for value in numeric.values()):
        raise EPBCReferralsError("entity-grid pagination metadata is invalid")
    if numeric["PageNumber"] != expected_page or numeric["PageSize"] != PAGE_SIZE:
        raise EPBCReferralsError("entity-grid page metadata changed")
    records = document.get("Records")
    if not isinstance(records, list) or len(records) > PAGE_SIZE:
        raise EPBCReferralsError("entity-grid records are invalid")
    parsed_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(records):
        record = _object(raw, f"Records[{index}]")
        record_id = record.get("Id")
        if not isinstance(record_id, str) or not UUID_RE.fullmatch(record_id):
            raise EPBCReferralsError("entity-grid record ID is invalid")
        attributes = record.get("Attributes")
        if not isinstance(attributes, list):
            raise EPBCReferralsError("entity-grid attributes are invalid")
        values: dict[str, Any] = {}
        for raw_attribute in attributes:
            attribute = _object(raw_attribute, "grid attribute")
            name = attribute.get("Name")
            if not isinstance(name, str) or not name or name in values:
                raise EPBCReferralsError("grid attribute name is invalid or duplicated")
            values[name] = attribute.get("DisplayValue")
        required = {
            "incidentid",
            "mara_industrytype",
            "mara_location",
            "mara_primarymarajurisdiction",
            "mara_proposerapprovalholdername",
            "mara_validdate",
            "statecode",
            "statuscode",
            "ticketnumber",
            "title",
        }
        if not required.issubset(values):
            raise EPBCReferralsError("entity-grid row fields changed")
        if values["incidentid"] != record_id:
            raise EPBCReferralsError("entity-grid record ID fields disagree")
        epbc_number = values["ticketnumber"]
        title = values["title"]
        if not isinstance(epbc_number, str) or not EPBC_NUMBER_RE.fullmatch(epbc_number):
            raise EPBCReferralsError("EPBC number is invalid")
        if not isinstance(title, str) or not title.strip():
            raise EPBCReferralsError("project title is missing")
        parsed_rows.append(
            {
                "epbc_number": epbc_number,
                "industry_type": values["mara_industrytype"],
                "location": values["mara_location"],
                "matched_queries": [phrase],
                "primary_jurisdiction": values["mara_primarymarajurisdiction"],
                "process_status": values["statuscode"],
                "proposer_or_approval_holder": values[
                    "mara_proposerapprovalholdername"
                ],
                "record_id": record_id,
                "record_state": values["statecode"],
                "title": title,
                "valid_date_display": values["mara_validdate"],
            }
        )
    if numeric["ItemCount"] == 0:
        if records or numeric["PageCount"] != 0:
            raise EPBCReferralsError("empty entity-grid arithmetic is inconsistent")
    elif numeric["PageCount"] < 1:
        raise EPBCReferralsError("entity-grid page count is inconsistent")
    more_records = document.get("MoreRecords")
    if not isinstance(more_records, bool):
        raise EPBCReferralsError("entity-grid MoreRecords flag is invalid")
    cookie = document.get("NextPagePagingCookie")
    if cookie is not None and not isinstance(cookie, str):
        raise EPBCReferralsError("entity-grid paging cookie is invalid")
    return {
        "item_count": numeric["ItemCount"],
        "more_records": more_records,
        "next_page_paging_cookie": cookie,
        "page_count": numeric["PageCount"],
        "page_number": numeric["PageNumber"],
        "records": parsed_rows,
    }


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.title: str | None = None
        self.labels: list[str] = []
        self.values: list[str] = []
        self.inputs: dict[str, str | None] = {}
        self.textareas: dict[str, str] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {name: value for name, value in attrs}
        classes = set((attributes.get("class") or "").split())
        if tag == "div" and "applicationTitle" in classes:
            self.capture = "title"
            self.buffer = []
        elif tag == "span" and "fieldLabel" in classes:
            self.capture = "label"
            self.buffer = []
        elif tag == "span" and "fieldtext" in classes:
            self.capture = "value"
            self.buffer = []
        elif tag == "textarea" and (attributes.get("id") or "").startswith("mara_"):
            self.capture = f"textarea:{attributes['id']}"
            self.buffer = []
        elif tag == "input" and (attributes.get("id") or "").startswith("mara_"):
            self.inputs[attributes["id"]] = attributes.get("value")

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture == "title" and tag == "div":
            self.title = " ".join("".join(self.buffer).split())
            self.capture = None
        elif self.capture == "label" and tag == "span":
            self.labels.append(" ".join("".join(self.buffer).split()).rstrip(":"))
            self.capture = None
        elif self.capture == "value" and tag == "span":
            self.values.append(" ".join("".join(self.buffer).split()))
            self.capture = None
        elif self.capture and self.capture.startswith("textarea:") and tag == "textarea":
            self.textareas[self.capture.split(":", 1)[1]] = "".join(self.buffer).strip()
            self.capture = None


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.fragments.append(data)


def _plain_text(markup: str) -> str:
    parser = _PlainTextParser()
    parser.feed(markup)
    parser.close()
    return " ".join(" ".join(parser.fragments).split())


def parse_detail_page(body: bytes, *, expected_record_id: str) -> dict[str, Any]:
    """Parse only the public referral-summary metadata and description field."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EPBCReferralsError("referral detail page is not UTF-8") from error
    parser = _DetailParser()
    parser.feed(text)
    parser.close()
    if not parser.title or len(parser.labels) != len(parser.values):
        raise EPBCReferralsError("referral detail header changed")
    header = dict(zip(parser.labels, parser.values, strict=True))
    if set(header) != {"EPBC Number", "Project Status"}:
        raise EPBCReferralsError("referral detail header fields changed")
    if not EPBC_NUMBER_RE.fullmatch(header["EPBC Number"]):
        raise EPBCReferralsError("referral detail EPBC number is invalid")
    if expected_record_id not in text:
        raise EPBCReferralsError("referral detail record ID mismatch")
    description_markup = parser.textareas.get("mara_proposedactionoverview")
    if not isinstance(description_markup, str) or not description_markup:
        raise EPBCReferralsError("referral detail project description is missing")
    required_inputs = {
        "mara_industrytype_name",
        "mara_location",
        "mara_personproposingaction_name",
        "mara_primarymarajurisdiction_name",
    }
    if not required_inputs.issubset(parser.inputs):
        raise EPBCReferralsError("referral detail fields changed")
    return {
        "description_markup": description_markup,
        "description_plain_text": _plain_text(description_markup),
        "epbc_number": header["EPBC Number"],
        "industry_type": parser.inputs["mara_industrytype_name"],
        "location": parser.inputs["mara_location"],
        "primary_jurisdiction": parser.inputs["mara_primarymarajurisdiction_name"],
        "process_status": header["Project Status"],
        "proposer": parser.inputs["mara_personproposingaction_name"],
        "title": parser.title,
    }


def classify_result(title: str, description: str) -> str:
    combined = f"{title} {description}"
    if not DATA_CENTRE_RE.search(combined):
        return "word_collision"
    title_has_phrase = bool(DATA_CENTRE_RE.search(title))
    direct_action = bool(DIRECT_ACTION_RE.search(description))
    context_marker = bool(CONTEXT_MARKER_RE.search(title))
    if title_has_phrase and direct_action and not context_marker:
        return "direct_data_centre_project"
    if re.search(r"\bexisting\b", combined, re.I) and CONTEXT_MARKER_RE.search(combined):
        return "ancillary_existing_data_centre_work"
    if title_has_phrase or DATA_CENTRE_RE.search(description):
        return "context_only"
    return "word_collision"


def _sentence_context(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start))
    right_candidates = [
        position
        for position in (text.find(".", end), text.find(";", end))
        if position >= 0
    ]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right + 1].strip()


def _power_role_context(
    text: str,
    matches: Sequence[re.Match[str]],
    index: int,
) -> str:
    """Return the local clause that owns one numeric power statement.

    Referral descriptions sometimes put facility, IT, generation, and storage
    capacities in a single sentence.  Looking at the whole sentence would let
    one ``IT capacity`` qualifier relabel every number in it.  Boundaries
    between adjacent numbers are therefore taken from explicit clause
    separators when present, and otherwise from the midpoint between them.
    """

    match = matches[index]
    sentence_left = max(text.rfind(".", 0, match.start()), text.rfind(";", 0, match.start())) + 1
    right_candidates = [
        position
        for position in (text.find(".", match.end()), text.find(";", match.end()))
        if position >= 0
    ]
    sentence_right = min(right_candidates) + 1 if right_candidates else len(text)

    def boundary(left_match: re.Match[str], right_match: re.Match[str]) -> int:
        between = text[left_match.end() : right_match.start()]
        separator = re.search(
            r"[,;]|\b(?:and|with|plus|while|alongside|whereas)\b",
            between,
            flags=re.IGNORECASE,
        )
        if separator:
            return left_match.end() + separator.end()
        return (left_match.end() + right_match.start()) // 2

    role_left = sentence_left
    if index > 0 and matches[index - 1].end() > sentence_left:
        role_left = boundary(matches[index - 1], match)
    role_right = sentence_right
    if index + 1 < len(matches) and matches[index + 1].start() < sentence_right:
        role_right = boundary(match, matches[index + 1])
    return text[role_left:role_right].strip()


def extract_scoped_power_statements(text: str) -> list[dict[str, Any]]:
    """Retain numeric wording and scope without unsafe capacity conversions."""

    statements: list[dict[str, Any]] = []
    matches = list(POWER_RE.finditer(text))
    for ordinal, match in enumerate(matches, start=1):
        context = _sentence_context(text, match.start(), match.end())
        role_context = _power_role_context(text, matches, ordinal - 1)
        lowered = role_context.lower()
        unit = match.group("unit")
        role: str
        is_data_centre_it_capacity = False
        is_annual_energy_consumption = False
        if re.search(r"\b(?:it|information technology)\s+capacity\b", lowered):
            role = "data_centre_it_capacity"
            is_data_centre_it_capacity = True
        elif re.search(r"\bsolar(?:\s+pv|\s+generation)?\b", lowered):
            role = "supporting_solar_generation_capacity"
        elif "battery" in lowered or "bess" in lowered:
            role = "battery_storage_energy_capacity"
        elif "gas-fired generation" in lowered:
            role = "supporting_gas_generation_capacity"
        elif DATA_CENTRE_RE.search(role_context):
            role = "data_centre_facility_capacity_scope_unspecified"
        else:
            role = "untyped_power_or_energy_statement"
        statements.append(
            {
                "annual_energy_consumption": is_annual_energy_consumption,
                "context": context,
                "is_data_centre_it_capacity": is_data_centre_it_capacity,
                "matched_text": match.group(0),
                "ordinal": ordinal,
                "role": role,
                "source_unit": unit,
                "source_value": match.group("value"),
            }
        )
    return statements


def verify_portal_terms(body: bytes) -> dict[str, bool]:
    text = _plain_text(body.decode("utf-8"))
    lowered = text.lower()
    checks = {
        "commercial_terms_restriction_found": "commercial terms" in lowered,
        "distribution_prohibition_found": "reselling or distributing our material" in lowered,
        "own_use_limit_found": "solely for your own use" in lowered,
        "reproduction_prohibition_found": "reproducing our material" in lowered,
        "retransmission_prohibition_found": "re-transmitting the our material" in lowered,
    }
    if not all(checks.values()):
        raise EPBCReferralsError("portal terms rights language changed")
    return checks


def verify_dcceew_copyright(body: bytes) -> dict[str, bool]:
    text = _plain_text(body.decode("utf-8"))
    lowered = text.lower()
    checks = {
        "cc_by_4_default_found": "creative commons attribution (cc-by) 4.0" in lowered,
        "other_terms_exclusion_found": "some other licence terms" in lowered,
        "third_party_permission_warning_found": "their permission may be required" in lowered,
    }
    if not all(checks.values()):
        raise EPBCReferralsError("DCCEEW copyright language changed")
    return checks


def verify_public_comments_page(body: bytes) -> dict[str, bool]:
    text = _plain_text(body.decode("utf-8"))
    lowered = text.lower()
    checks = {
        "all_projects_claim_found": "we list all projects referred to us" in lowered,
        "all_referrals_instruction_found": "all referrals" in lowered,
        "portal_identity_found": "epbc act public portal" in lowered,
    }
    if not all(checks.values()):
        raise EPBCReferralsError("DCCEEW EPBC portal guidance changed")
    return checks


def merge_query_rows(
    rows_by_phrase: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for phrase in SEARCH_PHRASES:
        rows = rows_by_phrase.get(phrase)
        if not isinstance(rows, Sequence):
            raise EPBCReferralsError(f"missing rows for query {phrase!r}")
        for raw in rows:
            row = dict(raw)
            record_id = row.get("record_id")
            if not isinstance(record_id, str) or not UUID_RE.fullmatch(record_id):
                raise EPBCReferralsError("query row record ID is invalid")
            queries = row.pop("matched_queries", None)
            if queries != [phrase]:
                raise EPBCReferralsError("query row provenance is invalid")
            if record_id in merged:
                existing = merged[record_id]
                existing_without_queries = {
                    key: value for key, value in existing.items() if key != "matched_queries"
                }
                if existing_without_queries != row:
                    raise EPBCReferralsError("same referral differs across queries")
                existing["matched_queries"].append(phrase)
            else:
                merged[record_id] = row | {"matched_queries": [phrase]}
    return sorted(merged.values(), key=lambda row: (row["epbc_number"], row["record_id"]))


def _stable_closed_set(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    stable: list[dict[str, Any]] = []
    for result in results:
        detail = _object(result.get("detail"), "result detail")
        stable.append(
            {
                "classification": result.get("classification"),
                "epbc_number": result.get("epbc_number"),
                "industry_type": result.get("industry_type"),
                "location": result.get("location"),
                "matched_queries": result.get("matched_queries"),
                "primary_jurisdiction": result.get("primary_jurisdiction"),
                "process_status": result.get("process_status"),
                "proposer_or_approval_holder": result.get("proposer_or_approval_holder"),
                "record_id": result.get("record_id"),
                "record_state": result.get("record_state"),
                "title": result.get("title"),
                "valid_date_display": result.get("valid_date_display"),
                "detail_description_sha256": sha256_bytes(
                    str(detail.get("description_markup", "")).encode("utf-8")
                ),
            }
        )
    return stable


def _stable_power_scope(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    stable: list[dict[str, Any]] = []
    for result in results:
        for statement in result.get("power_statements", []):
            stable.append(
                {
                    "epbc_number": result.get("epbc_number"),
                    **dict(statement),
                }
            )
    return stable


def source_definition() -> dict[str, Any]:
    return {
        "format": DEFINITION_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "country": "Australia",
            "name": "EPBC Act Public Portal - All referrals",
            "publisher": "Australian Government environment portfolio",
            "url": ALL_REFERRALS_URL,
        },
        "scope": {
            "claim_supported": "bounded title-keyword observation inventory only",
            "global_or_australia_completeness_claim_supported": False,
            "search_phrases_exact": list(SEARCH_PHRASES),
            "transport_expressions": [
                transport_expression(phrase) for phrase in SEARCH_PHRASES
            ],
            "transport_note": (
                "The portal tooltip requires the asterisk wildcard for partial text. "
                "Each fixed phrase is therefore wrapped once to implement an exact "
                "bounded substring probe."
            ),
        },
        "access_contract": {
            "all_referrals_url": ALL_REFERRALS_URL,
            "anti_forgery_token_url": TOKEN_URL,
            "anonymous_grid_post_reproducible": True,
            "entity_list_id": ENTITY_LIST_ID,
            "entity_name": ENTITY_NAME,
            "grid_endpoint": GRID_ENDPOINT,
            "page_size": PAGE_SIZE,
            "primary_key": PRIMARY_KEY,
            "sort_expression": SORT_EXPRESSION,
            "view_id": VIEW_ID,
            "website_id": WEBSITE_ID,
        },
        "retrieval_policy": {
            "allowed_hosts": sorted(OFFICIAL_HOSTS),
            "attachments_or_documents_fetched": False,
            "detail_pages": "only direct or boundary search matches",
            "max_network_requests": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "plans_images_maps_or_pdfs_fetched": False,
            "public_comments_or_submissions_fetched": False,
            "raw_destination": "operator-supplied quarantine outside release",
            "retries": "bounded exponential backoff; every attempt counts toward cap",
        },
        "rights_policy": RIGHTS_POLICY,
        "release_policy": {
            "atlas_merge_permitted": False,
            "metadata_only": True,
            "raw_or_row_level_portal_material_released": False,
            "status": "rights_blocked_metadata_only",
        },
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "update_policy": {
            "immutable_release": True,
            "recommended_refresh": "monthly with a new dated release ID",
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:datacenter-atlas:{RELEASE_ID}:assessment",
        "additionalProperties": True,
        "format": SCHEMA_FORMAT,
        "properties": {
            "assessment_id": {"const": RELEASE_ID},
            "format": {"const": ASSESSMENT_FORMAT},
            "rights_assessment": {"type": "object"},
            "schema_version": {"const": SCHEMA_VERSION},
        },
        "required": [
            "assessment_id",
            "format",
            "rights_assessment",
            "schema_version",
        ],
        "schema_version": SCHEMA_VERSION,
        "title": "EPBC rights-blocked metadata-only source assessment",
        "type": "object",
    }


def readme_text() -> str:
    return f"""# EPBC Act Public Portal bounded data-centre search

This frozen source assessment records a reproducible, anonymous query contract
for the official EPBC Act Public Portal.  The three fixed phrases are
`data centre`, `data center`, and `datacentre`; the transport adds one leading
and trailing `*` because the portal itself documents that wildcard syntax for
partial-text searches.

The capture found {EXPECTED_RAW_HITS} raw hits and {EXPECTED_UNIQUE_REFERRALS}
exact-ID-deduplicated referrals.  Both were classified as direct data-centre
project observations.  These counts are not a facility census: physical site
count remains null, Australia coverage is incomplete, and portal status is an
EPBC workflow field rather than construction or operation evidence.

No referral rows or raw portal pages are in this release.  The portal's linked
terms limit downloaded material to the user's own use and prohibit several
forms of reproduction and distribution.  The more general DCCEEW CC-BY notice
also excludes material governed by other terms and warns that third-party
permission may be required.  Raw HTML/JSON and proposer descriptions therefore
remain only in the operator-provided quarantine; the release contains counts,
scope decisions, retrieval metadata, and hashes.  This is a conservative source
governance decision, not legal advice.

The bounded live build fetches only the all-referrals page, its linked portal
terms, the anti-forgery token, the three grid result sets, and the two
direct/boundary detail pages.  It does not fetch submissions, comments,
consultant attachments, referral documents, plans, maps, images, or PDFs.

Validate offline:

```bash
python datacenter_atlas/scripts/validate_epbc_referrals.py \\
  datacenter_atlas/source_assessments/{RELEASE_ID}
```
"""


def attribution_text() -> str:
    return f"""Source identity: EPBC Act Public Portal, Australian Government environment portfolio
Portal: {ALL_REFERRALS_URL}
Portal terms: {PORTAL_TERMS_URL}
DCCEEW copyright notice: {DCCEEW_COPYRIGHT_URL}

This release republishes no raw portal material and no referral rows.  It is a
metadata-only audit of query accessibility, counts, classifications, rights,
and hashes.  No CC-BY licence is asserted for portal or proposer-supplied
material.  Australian Government logos and the Commonwealth Coat of Arms are
not included.
"""


def build_release_documents(capture: Mapping[str, Any]) -> dict[str, bytes]:
    """Build the rights-blocked release from a completed quarantine capture."""

    if capture.get("format") != "datacenter-atlas-epbc-quarantine-capture-v1":
        raise EPBCReferralsError("quarantine capture format is invalid")
    captured_at = _timestamp(capture.get("captured_at"), "captured_at")
    retrievals = capture.get("retrievals")
    results = capture.get("results")
    queries = capture.get("queries")
    if (
        not isinstance(retrievals, list)
        or not isinstance(results, list)
        or not isinstance(queries, list)
    ):
        raise EPBCReferralsError("quarantine capture collections are invalid")
    if len(retrievals) != EXPECTED_NETWORK_REQUESTS:
        raise EPBCReferralsError("quarantine retrieval count changed")
    query_by_phrase = {
        query.get("phrase"): query
        for query in queries
        if isinstance(query, Mapping)
    }
    if set(query_by_phrase) != set(SEARCH_PHRASES):
        raise EPBCReferralsError("quarantine query set changed")
    for phrase, expected in EXPECTED_QUERY_COUNTS.items():
        if query_by_phrase[phrase].get("item_count") != expected:
            raise EPBCReferralsError(f"EPBC result count changed for {phrase!r}")
    if sum(EXPECTED_QUERY_COUNTS.values()) != EXPECTED_RAW_HITS:
        raise EPBCReferralsError("expected query arithmetic is invalid")
    if len(results) != EXPECTED_UNIQUE_REFERRALS:
        raise EPBCReferralsError("deduplicated EPBC result count changed")
    classifications: dict[str, int] = {
        key: 0 for key in EXPECTED_CLASSIFICATION_COUNTS
    }
    for result in results:
        classification = result.get("classification")
        if classification not in classifications:
            raise EPBCReferralsError("unknown EPBC classification")
        classifications[classification] += 1
    if classifications != EXPECTED_CLASSIFICATION_COUNTS:
        raise EPBCReferralsError("EPBC classification arithmetic changed")

    closed_set_sha256 = sha256_bytes(canonical_json(_stable_closed_set(results)))
    power_scope_rows = _stable_power_scope(results)
    power_scope_sha256 = sha256_bytes(canonical_json(power_scope_rows))
    if (
        EXPECTED_CLOSED_SET_SHA256 != "TO_BE_PINNED"
        and closed_set_sha256 != EXPECTED_CLOSED_SET_SHA256
    ):
        raise EPBCReferralsError("EPBC closed set changed")
    if (
        EXPECTED_POWER_SCOPE_SHA256 != "TO_BE_PINNED"
        and power_scope_sha256 != EXPECTED_POWER_SCOPE_SHA256
    ):
        raise EPBCReferralsError("EPBC scoped power statements changed")

    role_counts: dict[str, int] = {}
    for row in power_scope_rows:
        role = row.get("role")
        if not isinstance(role, str):
            raise EPBCReferralsError("scoped power role is invalid")
        role_counts[role] = role_counts.get(role, 0) + 1
    if any(
        row.get("annual_energy_consumption") is not False
        for row in power_scope_rows
    ):
        raise EPBCReferralsError("annual energy consumption was inferred")
    for row in power_scope_rows:
        if row.get("role", "").startswith("supporting_") and row.get(
            "is_data_centre_it_capacity"
        ) is not False:
            raise EPBCReferralsError("supporting capacity was mapped to IT load")

    public_retrievals: list[dict[str, Any]] = []
    retained_raw = []
    for index, raw in enumerate(retrievals):
        retrieval = _object(raw, f"retrievals[{index}]")
        url = retrieval.get("url")
        if not isinstance(url, str):
            raise EPBCReferralsError("retrieval URL is invalid")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise EPBCReferralsError("retrieval used a non-official host")
        request_id = retrieval.get("request_id")
        endpoint_kind = retrieval.get("endpoint_kind")
        retained = retrieval.get("raw_artifact_retained") is True
        public_url = url
        if endpoint_kind == "referral_detail":
            public_url = DETAIL_URL_TEMPLATE.format(record_id="<quarantined>")
        entry = {
            "bytes": retrieval.get("bytes"),
            "content_type": retrieval.get("content_type"),
            "endpoint_kind": endpoint_kind,
            "http_status": retrieval.get("http_status"),
            "method": retrieval.get("method"),
            "raw_artifact_released": False,
            "raw_artifact_retained_in_operator_quarantine": retained,
            "request_body_sha256": retrieval.get("request_body_sha256"),
            "request_id": request_id,
            "retrieved_at": retrieval.get("retrieved_at"),
            "sha256": retrieval.get("sha256"),
            "url": public_url,
            "url_sha256": sha256_bytes(url.encode("utf-8")),
        }
        public_retrievals.append(entry)
        if retained:
            retained_raw.append(
                {
                    "bytes": retrieval.get("bytes"),
                    "request_id": request_id,
                    "sha256": retrieval.get("sha256"),
                }
            )
    if len(retained_raw) != EXPECTED_QUARANTINED_RAW_ARTIFACTS:
        raise EPBCReferralsError("quarantined raw artifact count changed")
    raw_bytes = sum(int(row["bytes"]) for row in retained_raw)
    raw_inventory_sha256 = sha256_bytes(canonical_json(retained_raw))
    capture_state_sha256 = validate_capture_state_hash(capture)

    query_summary = {
        "classification_counts": classifications,
        "closed_set_sha256": closed_set_sha256,
        "deduplication_key": "exact portal incident UUID",
        "format": QUERY_SUMMARY_FORMAT,
        "physical_unique_site_count": None,
        "power_scope_assessment": {
            "annual_energy_consumption_statement_count": 0,
            "raw_statement_occurrences": len(power_scope_rows),
            "role_counts": dict(sorted(role_counts.items())),
            "scoped_statement_set_sha256": power_scope_sha256,
            "supporting_generation_or_storage_promoted_to_it_or_energy_use": False,
            "values_released": False,
        },
        "queries": [
            {
                "item_count": query_by_phrase[phrase]["item_count"],
                "page_count": query_by_phrase[phrase]["page_count"],
                "phrase": phrase,
                "raw_response_sha256": query_by_phrase[phrase]["raw_response_sha256"],
                "result_rows_released": 0,
                "transport_expression": transport_expression(phrase),
            }
            for phrase in SEARCH_PHRASES
        ],
        "raw_hit_count": EXPECTED_RAW_HITS,
        "referral_rows_released": 0,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "unique_referral_count": EXPECTED_UNIQUE_REFERRALS,
    }
    retrieval_inventory = {
        "format": INVENTORY_FORMAT,
        "network_request_count": len(public_retrievals),
        "release_id": RELEASE_ID,
        "retrievals": public_retrievals,
        "schema_version": SCHEMA_VERSION,
    }
    source_inventory = {
        "capture_state_released": False,
        "capture_state_sha256": capture_state_sha256,
        "format": INVENTORY_FORMAT,
        "quarantined_raw_artifact_count": len(retained_raw),
        "quarantined_raw_bytes": raw_bytes,
        "quarantined_raw_inventory_sha256": raw_inventory_sha256,
        "raw_artifact_count_in_release": 0,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }
    assessment = {
        "assessed_at": captured_at,
        "assessment_id": RELEASE_ID,
        "coverage_assessment": {
            "australia_complete": False,
            "bounded_query_result_referrals": EXPECTED_UNIQUE_REFERRALS,
            "construction_verified_rows": 0,
            "country": "Australia",
            "facility_count": None,
            "geographic_scope": "incomplete bounded title-keyword search",
            "operation_verified_rows": 0,
            "physical_unique_site_count": None,
        },
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "format": ASSESSMENT_FORMAT,
        "portal_access_assessment": {
            "anonymous_entity_grid_post_reproducible": True,
            "anti_forgery_token_required": True,
            "attachment_or_document_endpoints_used": False,
            "expected_network_requests": EXPECTED_NETWORK_REQUESTS,
            "search_contract": "three fixed phrases with portal-documented outer wildcard",
        },
        "release_decision": {
            "atlas_merge_permitted": False,
            "reason": "portal-specific terms do not grant row or raw redistribution rights",
            "referral_rows_released": 0,
            "status": "rights_blocked_metadata_only",
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_context": {
            "dccEEw_says_all_referred_projects_are_listed_on_portal": True,
            "portal_search_is_a_facility_census": False,
            "portal_status_is_process_metadata": True,
        },
    }
    documents = {
        "ATTRIBUTION.txt": attribution_text().encode("utf-8"),
        "README.md": readme_text().encode("utf-8"),
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(source_definition()),
        "query-summary.json": canonical_json(query_summary),
        "retrieval-inventory.json": canonical_json(retrieval_inventory),
        "schema.json": canonical_json(schema_document()),
        "source-inventory.json": canonical_json(source_inventory),
    }
    return documents


def _manifest(documents: Mapping[str, bytes], generated_at: str) -> dict[str, Any]:
    return {
        "files": [
            {
                "bytes": len(documents[name]),
                "filename": name,
                "sha256": sha256_bytes(documents[name]),
            }
            for name in sorted(documents)
        ],
        "format": RELEASE_FORMAT,
        "generated_at": generated_at,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _freeze_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_symlink():
            raise EPBCReferralsError("release cannot contain symlinks")
        if child.is_dir():
            _freeze_tree(child)
        elif child.is_file():
            child.chmod(0o444)
        else:
            raise EPBCReferralsError("release contains a non-regular artifact")
    path.chmod(0o555)


def write_release_bundle(output: str | Path, documents: Mapping[str, bytes]) -> None:
    destination = Path(output)
    if destination.exists() or destination.is_symlink():
        raise EPBCReferralsError("output release already exists")
    if set(documents) != RELEASE_FILENAMES:
        raise EPBCReferralsError("release document set is invalid")
    assessment = json.loads(documents["assessment.json"])
    generated_at = _timestamp(assessment.get("assessed_at"), "assessed_at")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        for name, body in documents.items():
            if not isinstance(body, bytes) or not body:
                raise EPBCReferralsError(f"release body is invalid: {name}")
            (temporary / name).write_bytes(body)
        manifest = canonical_json(_manifest(documents, generated_at))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n", encoding="ascii"
        )
        _freeze_tree(temporary)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            for child in temporary.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    child.chmod(0o600)
            temporary.chmod(0o700)
            shutil.rmtree(temporary)
        raise


def _validate_query_summary(document: Mapping[str, Any]) -> None:
    if (
        document.get("format") != QUERY_SUMMARY_FORMAT
        or document.get("release_id") != RELEASE_ID
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise EPBCReferralsError("query summary identity is invalid")
    if (
        document.get("raw_hit_count") != EXPECTED_RAW_HITS
        or document.get("unique_referral_count") != EXPECTED_UNIQUE_REFERRALS
    ):
        raise EPBCReferralsError("query summary arithmetic changed")
    if document.get("classification_counts") != EXPECTED_CLASSIFICATION_COUNTS:
        raise EPBCReferralsError("classification counts changed")
    if (
        document.get("physical_unique_site_count") is not None
        or document.get("referral_rows_released") != 0
    ):
        raise EPBCReferralsError("query summary overclaims sites or releases rows")
    digest = document.get("closed_set_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise EPBCReferralsError("closed-set hash is invalid")
    if EXPECTED_CLOSED_SET_SHA256 != "TO_BE_PINNED" and digest != EXPECTED_CLOSED_SET_SHA256:
        raise EPBCReferralsError("closed-set hash changed")
    queries = document.get("queries")
    if not isinstance(queries, list) or len(queries) != len(SEARCH_PHRASES):
        raise EPBCReferralsError("query summary set is invalid")
    for row, phrase in zip(queries, SEARCH_PHRASES, strict=True):
        query = _object(row, "query summary row")
        if (
            query.get("phrase") != phrase
            or query.get("transport_expression") != transport_expression(phrase)
            or query.get("item_count") != EXPECTED_QUERY_COUNTS[phrase]
            or query.get("page_count") != (1 if EXPECTED_QUERY_COUNTS[phrase] else 0)
            or query.get("result_rows_released") != 0
        ):
            raise EPBCReferralsError("query summary row changed")
        raw_digest = query.get("raw_response_sha256")
        if not isinstance(raw_digest, str) or not SHA256_RE.fullmatch(raw_digest):
            raise EPBCReferralsError("query response hash is invalid")
    power = _object(document.get("power_scope_assessment"), "power scope assessment")
    if (
        power.get("annual_energy_consumption_statement_count") != 0
        or power.get("supporting_generation_or_storage_promoted_to_it_or_energy_use") is not False
        or power.get("values_released") is not False
    ):
        raise EPBCReferralsError("unsafe EPBC power mapping or release")
    power_digest = power.get("scoped_statement_set_sha256")
    if not isinstance(power_digest, str) or not SHA256_RE.fullmatch(power_digest):
        raise EPBCReferralsError("scoped power hash is invalid")
    if (
        EXPECTED_POWER_SCOPE_SHA256 != "TO_BE_PINNED"
        and power_digest != EXPECTED_POWER_SCOPE_SHA256
    ):
        raise EPBCReferralsError("scoped power hash changed")


def _validate_retrieval_inventory(document: Mapping[str, Any]) -> None:
    if (
        document.get("format") != INVENTORY_FORMAT
        or document.get("release_id") != RELEASE_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("network_request_count") != EXPECTED_NETWORK_REQUESTS
    ):
        raise EPBCReferralsError("retrieval inventory identity is invalid")
    retrievals = document.get("retrievals")
    if not isinstance(retrievals, list) or len(retrievals) != EXPECTED_NETWORK_REQUESTS:
        raise EPBCReferralsError("retrieval inventory count changed")
    request_ids: set[str] = set()
    retained = 0
    for raw in retrievals:
        row = _object(raw, "retrieval row")
        request_id = row.get("request_id")
        if not isinstance(request_id, str) or not request_id or request_id in request_ids:
            raise EPBCReferralsError("retrieval request ID is invalid or duplicated")
        request_ids.add(request_id)
        url = row.get("url")
        if not isinstance(url, str):
            raise EPBCReferralsError("retrieval URL is invalid")
        parsed = urlsplit(url.replace("<quarantined>", "00000000-0000-0000-0000-000000000000"))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise EPBCReferralsError("retrieval URL host is not official")
        if row.get("http_status") != 200 or row.get("raw_artifact_released") is not False:
            raise EPBCReferralsError("retrieval status or release boundary changed")
        byte_count = row.get("bytes")
        digest = row.get("sha256")
        url_digest = row.get("url_sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
            or not isinstance(url_digest, str)
            or not SHA256_RE.fullmatch(url_digest)
        ):
            raise EPBCReferralsError("retrieval size or hash is invalid")
        _timestamp(row.get("retrieved_at"), "retrieval retrieved_at")
        if row.get("raw_artifact_retained_in_operator_quarantine") is True:
            retained += 1
    if retained != EXPECTED_QUARANTINED_RAW_ARTIFACTS:
        raise EPBCReferralsError("quarantined retrieval count changed")
    expected_ids = {
        "all_referrals",
        "detail_001",
        "detail_002",
        "portal_terms",
        "query_data_center_page_001",
        "query_data_centre_page_001",
        "query_datacentre_page_001",
        "token",
    }
    if request_ids != expected_ids:
        raise EPBCReferralsError("retrieval request set changed")


def _validate_source_inventory(
    document: Mapping[str, Any], retrieval_inventory: Mapping[str, Any]
) -> None:
    if (
        document.get("format") != INVENTORY_FORMAT
        or document.get("release_id") != RELEASE_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("quarantined_raw_artifact_count") != EXPECTED_QUARANTINED_RAW_ARTIFACTS
        or document.get("raw_artifact_count_in_release") != 0
        or document.get("capture_state_released") is not False
    ):
        raise EPBCReferralsError("source inventory identity or boundary changed")
    for field in ("capture_state_sha256", "quarantined_raw_inventory_sha256"):
        digest = document.get(field)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise EPBCReferralsError(f"{field} is invalid")
    rows = [
        {
            "bytes": row["bytes"],
            "request_id": row["request_id"],
            "sha256": row["sha256"],
        }
        for row in retrieval_inventory["retrievals"]
        if row["raw_artifact_retained_in_operator_quarantine"]
    ]
    if document.get("quarantined_raw_bytes") != sum(row["bytes"] for row in rows):
        raise EPBCReferralsError("quarantined raw byte arithmetic changed")
    if document.get("quarantined_raw_inventory_sha256") != sha256_bytes(canonical_json(rows)):
        raise EPBCReferralsError("quarantined raw inventory hash changed")


def _validate_assessment(document: Mapping[str, Any]) -> None:
    if (
        document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != RELEASE_ID
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise EPBCReferralsError("assessment identity is invalid")
    _timestamp(document.get("assessed_at"), "assessed_at")
    if (
        document.get("rights_assessment") != RIGHTS_POLICY
        or document.get("evidence_boundary") != EVIDENCE_BOUNDARY
    ):
        raise EPBCReferralsError("assessment rights or evidence boundary changed")
    coverage = _object(document.get("coverage_assessment"), "coverage assessment")
    expected = {
        "australia_complete": False,
        "bounded_query_result_referrals": EXPECTED_UNIQUE_REFERRALS,
        "construction_verified_rows": 0,
        "country": "Australia",
        "facility_count": None,
        "geographic_scope": "incomplete bounded title-keyword search",
        "operation_verified_rows": 0,
        "physical_unique_site_count": None,
    }
    if dict(coverage) != expected:
        raise EPBCReferralsError("coverage assessment changed")
    decision = _object(document.get("release_decision"), "release decision")
    if (
        decision.get("status") != "rights_blocked_metadata_only"
        or decision.get("atlas_merge_permitted") is not False
        or decision.get("referral_rows_released") != 0
    ):
        raise EPBCReferralsError("release decision changed")


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise EPBCReferralsError("release path must be a directory")
    names = {child.name for child in root.iterdir()}
    if names != EXPECTED_BUNDLE_FILES:
        raise EPBCReferralsError("release file set changed")
    if any(child.is_symlink() or not child.is_file() for child in root.iterdir()):
        raise EPBCReferralsError("release must contain only regular files")
    definition = _load_json(root / "definition.json", "definition")
    assessment = _load_json(root / "assessment.json", "assessment")
    query_summary = _load_json(root / "query-summary.json", "query summary")
    retrieval_inventory = _load_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    source_inventory = _load_json(root / "source-inventory.json", "source inventory")
    schema = _load_json(root / "schema.json", "schema")
    if definition != source_definition():
        raise EPBCReferralsError("source definition changed")
    if schema != schema_document():
        raise EPBCReferralsError("schema changed")
    if (root / "README.md").read_text(encoding="utf-8") != readme_text():
        raise EPBCReferralsError("release README changed")
    if (root / "ATTRIBUTION.txt").read_text(encoding="utf-8") != attribution_text():
        raise EPBCReferralsError("release attribution changed")
    _validate_assessment(assessment)
    _validate_query_summary(query_summary)
    _validate_retrieval_inventory(retrieval_inventory)
    _validate_source_inventory(source_inventory, retrieval_inventory)
    manifest = _load_json(root / MANIFEST_FILENAME, "manifest")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise EPBCReferralsError("manifest identity is invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(RELEASE_FILENAMES):
        raise EPBCReferralsError("manifest file inventory is invalid")
    seen: set[str] = set()
    for raw in files:
        entry = _object(raw, "manifest file")
        filename = entry.get("filename")
        if filename not in RELEASE_FILENAMES or filename in seen:
            raise EPBCReferralsError("manifest filename is invalid or duplicated")
        seen.add(filename)
        artifact = root / str(filename)
        if entry.get("bytes") != artifact.stat().st_size or entry.get(
            "sha256"
        ) != sha256_file(artifact):
            raise EPBCReferralsError(f"manifest mismatch for {filename}")
    if seen != RELEASE_FILENAMES:
        raise EPBCReferralsError("manifest file set changed")
    expected_hash_line = f"{sha256_file(root / MANIFEST_FILENAME)}  {MANIFEST_FILENAME}\n"
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="ascii") != expected_hash_line:
        raise EPBCReferralsError("manifest sidecar hash mismatch")
    if not is_frozen_release(root):
        raise EPBCReferralsError("release is not frozen read-only")
    return {
        "assessment": assessment,
        "definition": definition,
        "manifest": manifest,
        "query_summary": query_summary,
        "retrieval_inventory": retrieval_inventory,
        "schema": schema,
        "source_inventory": source_inventory,
    }


def is_frozen_release(path: str | Path) -> bool:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            return False
        if stat.S_IMODE(child.stat().st_mode) != 0o444:
            return False
    return True


def thaw_for_test(path: str | Path) -> None:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise EPBCReferralsError("test release must be a directory")
    root.chmod(0o755)
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise EPBCReferralsError("test release must contain regular files")
        child.chmod(0o644)
