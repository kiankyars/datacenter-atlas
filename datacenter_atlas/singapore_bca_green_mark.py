"""Bounded Singapore BCA Green Mark data-centre certification assessment.

The source unit is one Green Mark certification observation identified by the
data.gov.sg ``_id`` field.  A certification record, provisional letter,
electronic-certificate date, expiry date, or re-certification flag is not a
physical construction, commissioning, completion, or operation milestone.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any
import unicodedata
from urllib.parse import urlencode, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = (
    "singapore-bca-green-mark-data-centre-certifications-"
    "2005-2026-2026-07-18-v1"
)
RELEASE_FORMAT = "datacenter-atlas-singapore-bca-green-mark-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-singapore-bca-green-mark-definition-v1"
CAPTURE_FORMAT = "datacenter-atlas-singapore-bca-green-mark-capture-v1"
OBSERVATION_FORMAT = "datacenter-atlas-singapore-bca-green-mark-observation-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-singapore-bca-green-mark-assessment-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-singapore-bca-green-mark-retrieval-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-singapore-bca-green-mark-source-inventory-v1"
)
SCHEMA_FORMAT = "datacenter-atlas-singapore-bca-green-mark-schema-v1"

DATASET_ID = "d_c4bd082b48fa7611713f39e23d250c27"
DATASET_URL = f"https://data.gov.sg/datasets/{DATASET_ID}/view"
DATASTORE_ENDPOINT = "https://data.gov.sg/api/action/datastore_search"
LICENCE_URL = "https://data.gov.sg/open-data-licence"
PUBLISHER = "Building and Construction Authority (BCA), Singapore"
DATASET_TITLE = "Green Mark Buildings"
CAPTURE_DATE_LOCAL = "2026-07-18"
ACCESS_DATE_DISPLAY = "18 July 2026"

PAGE_SIZE = 1000
PAGE_OFFSETS = (0, 1000, 2000, 3000, 4000)
PAGE_COUNTS = (1000, 1000, 1000, 1000, 793)
EXPECTED_TOTAL = 4793
EXPECTED_UNIQUE_REFERENCE_COUNT = 4786
EXPECTED_LOGICAL_REQUESTS = 7
MAX_LOGICAL_REQUESTS = 7
MAX_ATTEMPTS_PER_REQUEST = 1

EXPECTED_FIELDS = (
    ("Reference_No", "text"),
    ("Project_Name", "text"),
    ("Actual_Project_Name", "text"),
    ("Postal_Code", "text"),
    ("Rating", "text"),
    ("SLE_ZE_PE", "text"),
    ("CN", "text"),
    ("HW", "text"),
    ("IN", "text"),
    ("MT", "text"),
    ("RE", "text"),
    ("Prov_Letter", "text"),
    ("e_cert", "text"),
    ("Expiry", "text"),
    ("Project_Type", "text"),
    ("GFA", "text"),
    ("Re_Certification", "text"),
    ("Previous_GM_Cert_Reference_No", "text"),
    ("GM_Version", "text"),
    ("_id", "int4"),
)
EXPECTED_ROW_KEYS = frozenset(name for name, _ in EXPECTED_FIELDS)

MATCH_CLASSES = (
    "green_mark_data_centre_scheme",
    "additional_project_type_match",
    "name_only_review",
)
EXPECTED_MATCH_COUNTS = {
    "scheme": 94,
    "project_type": 13,
    "name": 51,
    "union": 101,
}
EXPECTED_EXCLUSIVE_COUNTS = {
    "green_mark_data_centre_scheme": 94,
    "additional_project_type_match": 2,
    "name_only_review": 5,
}
EXPECTED_INTERSECTION_COUNTS = {
    "all_three": 10,
    "scheme_and_name": 45,
    "scheme_and_project_type": 11,
    "project_type_and_name": 11,
}
EXPECTED_MEMBERSHIP_COUNT = 158
EXPECTED_LEAD_IDS = (2, 205, 2439, 3908)

DATA_CENTRE_RE = re.compile(
    r"(?<![a-z0-9])data(?:[\s-]*centre|[\s-]*center)s?(?![a-z0-9])"
)
NEW_DATA_CENTRE_SCHEME_RE = re.compile(
    r"^new[\s-]+data(?:[\s-]*centre|[\s-]*center)s?(?:\b|\s|\()"
)
EMAIL_RE = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"(?![a-z0-9.-])"
)
NRIC_FIN_RE = re.compile(r"(?i)(?<![a-z0-9])[stfgm]\d{7}[a-z](?![a-z0-9])")
SG_PHONE_RE = re.compile(r"(?<!\d)(?:\+65[ -]?)?[689]\d{3}[ -]?\d{4}(?!\d)")
PERSON_CONTACT_FIELD_RE = re.compile(
    r"(?i)(?:^|_)(?:email|e_mail|phone|telephone|mobile|contact|nric|fin|person|"
    r"individual|owner_name)(?:$|_)"
)

RIGHTS_POLICY = {
    "attribution_required": True,
    "dataset_and_derived_data_public_review_release_permitted": True,
    "licence_name": "Singapore Open Data Licence version 1.0",
    "licence_url": LICENCE_URL,
    "legal_conclusion_claimed": False,
    "limitations": {
        "agency_names_logos_and_trademarks_not_licensed_as_dataset_content": True,
        "no_endorsement_implied": True,
        "personal_data_not_licensed": True,
        "third_party_rights_not_licensed_without_agency_authority": True,
    },
    "raw_dataset_response_bodies_released": False,
    "source_dataset_snapshot_released": True,
    "verified_local_date": CAPTURE_DATE_LOCAL,
}

DOWNSTREAM_IMPORT_POLICY = {
    "automatic_construction_master_import_permitted": False,
    "construction_map_import_permitted": False,
    "future_construction_master_tier_b_review_observation_import_permitted": True,
    "future_master_requirements": {
        "explicit_human_review_required": True,
        "physical_lifecycle_status_must_be_null": True,
        "tier": "B",
    },
    "map_blocker": "source has no coordinates and no exact documented geospatial join",
    "no_fuzzy_green_mark_geospatial_join": True,
}

PHYSICAL_LIFECYCLE_BOUNDARY = {
    "commissioning_date": None,
    "completion_date": None,
    "construction_start_date": None,
    "construction_status": None,
    "operation_date": None,
    "operation_status": None,
    "certification_dates_are_physical_dates": False,
    "expiry_is_completion_or_closure": False,
    "provisional_letter_is_construction_evidence": False,
    "recertification_is_physical_status": False,
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "dataset-snapshot.jsonl",
    "definition.json",
    "match-membership.jsonl",
    "observations.jsonl",
    "provisional-new-scheme-leads.jsonl",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
}
EXPECTED_FILES = DERIVED_FILENAMES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SingaporeBCAGreenMarkError(ValueError):
    """Raised when the BCA capture or frozen release fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(dict(row)) for row in rows)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _require_regular_file(path: Path, *, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise SingaporeBCAGreenMarkError(f"{label} missing: {path}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SingaporeBCAGreenMarkError(f"{label} must be a regular non-symlink file")


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    _require_regular_file(path, label=label)
    return path.read_bytes()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SingaporeBCAGreenMarkError("text normalization received a non-string")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def data_centre_phrase_match(value: str | None) -> bool:
    return bool(DATA_CENTRE_RE.search(normalize_text(value)))


def data_centre_name_match(row: Mapping[str, Any]) -> bool:
    joined = f"{row.get('Project_Name') or ''} {row.get('Actual_Project_Name') or ''}"
    return data_centre_phrase_match(joined)


def new_data_centre_scheme_match(value: str | None) -> bool:
    return bool(NEW_DATA_CENTRE_SCHEME_RE.search(normalize_text(value)))


def page_url(offset: int) -> str:
    if offset not in PAGE_OFFSETS:
        raise SingaporeBCAGreenMarkError("offset outside closed page plan")
    parameters = {
        "resource_id": DATASET_ID,
        "limit": str(PAGE_SIZE),
        "offset": str(offset),
    }
    return f"{DATASTORE_ENDPOINT}?{urlencode(parameters)}"


def _official_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "data.gov.sg":
        raise SingaporeBCAGreenMarkError(f"non-official URL outside capture policy: {url}")
    return url


def source_definition() -> dict[str, Any]:
    return {
        "classification_contract": {
            "exclusive_precedence": [
                "green_mark_data_centre_scheme",
                "additional_project_type_match",
                "name_only_review",
            ],
            "name_fields": ["Project_Name", "Actual_Project_Name"],
            "normalization": ["NFKC", "casefold", "collapse_whitespace"],
            "phrase_pattern": DATA_CENTRE_RE.pattern,
            "project_type_field": "Project_Type",
            "scheme_field": "GM_Version",
        },
        "coverage_contract": {
            "certification_observation_count": EXPECTED_TOTAL,
            "coverage_end": "2026-02",
            "coverage_start": "2005-01",
            "dataset_last_updated": "2026-05-19",
            "legislated_projects_excluded": True,
            "national_data_centre_completeness_claimed": False,
            "opted_out_public_disclosure_projects_excluded": True,
            "project_count": None,
            "site_count": None,
            "voluntary_green_mark_listing_only": True,
        },
        "dataset_id": DATASET_ID,
        "dataset_title": DATASET_TITLE,
        "dataset_url": DATASET_URL,
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_consumption": None,
            "coordinates": None,
            "data_centre_type": None,
            "gfa_field_is_untyped_raw_text": True,
            "gfa_unit": None,
            "it_capacity": None,
            "operator": None,
            "physical_lifecycle": PHYSICAL_LIFECYCLE_BOUNDARY,
            "power": None,
            "pue": None,
        },
        "network_policy": {
            "logical_request_count": EXPECTED_LOGICAL_REQUESTS,
            "maximum_attempts_per_request": MAX_ATTEMPTS_PER_REQUEST,
            "maximum_logical_requests": MAX_LOGICAL_REQUESTS,
            "page_offsets": list(PAGE_OFFSETS),
            "page_size": PAGE_SIZE,
            "redirects_permitted": False,
        },
        "publisher": PUBLISHER,
        "release_id": RELEASE_ID,
        "rights_policy": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": "data.gov.sg Datastore API",
        "source_unit": "one Green Mark certification observation keyed by _id",
    }


def _validate_source_row(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != EXPECTED_ROW_KEYS:
        raise SingaporeBCAGreenMarkError("source row schema changed")
    identifier = value.get("_id")
    if not isinstance(identifier, int) or isinstance(identifier, bool):
        raise SingaporeBCAGreenMarkError("source _id must be an integer")
    for field in EXPECTED_ROW_KEYS - {"_id"}:
        field_value = value[field]
        if field_value is not None and not isinstance(field_value, str):
            raise SingaporeBCAGreenMarkError(f"source field is not text/null: {field}")
    return dict(value)


def _validate_dataset_page(body: bytes) -> None:
    folded = body.decode("utf-8", errors="strict").casefold()
    required = (
        DATASET_ID,
        "green mark buildings",
        "jan 2005 to feb 2026",
        "19 may 2026",
        "listing is based on voluntary green mark certification",
        "excluding legislated projects",
        "projects that have opted out of public disclosure",
        "building and construction authority",
    )
    if any(phrase not in folded for phrase in required):
        raise SingaporeBCAGreenMarkError("official dataset metadata evidence changed")


def _validate_licence_page(body: bytes) -> None:
    folded = body.decode("utf-8", errors="strict").casefold()
    required = (
        "singapore open data licence",
        "version 1.0",
        "use, access, download, copy, distribute, transmit, modify and adapt",
        "whether commercially or non-commercially",
        "any personal data in the dataset",
        "third party rights that the agency is not authorised to license",
        "patents, trademarks and design rights",
        "conspicuous notice acknowledging the source of the datasets",
    )
    if any(phrase not in folded for phrase in required):
        raise SingaporeBCAGreenMarkError("official licence evidence changed")


def load_capture(capture_directory: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if capture_directory.is_symlink() or not capture_directory.is_dir():
        raise SingaporeBCAGreenMarkError("capture directory must be a non-symlink directory")
    capture_path = capture_directory / "capture.json"
    capture_raw = _read_regular_bytes(capture_path, label="capture manifest")
    try:
        capture = json.loads(capture_raw)
    except json.JSONDecodeError as error:
        raise SingaporeBCAGreenMarkError("capture manifest is invalid JSON") from error
    if capture_raw != canonical_json(capture):
        raise SingaporeBCAGreenMarkError("capture manifest is not canonical JSON")
    if capture.get("format") != CAPTURE_FORMAT:
        raise SingaporeBCAGreenMarkError("unexpected capture format")
    requests = capture.get("requests")
    if not isinstance(requests, list) or len(requests) != EXPECTED_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("capture logical request count changed")
    if not all(isinstance(row, dict) for row in requests):
        raise SingaporeBCAGreenMarkError("capture request must be an object")
    if capture.get("planned_logical_request_count") != EXPECTED_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("planned logical request count mismatch")
    if capture.get("completed_logical_response_count") != EXPECTED_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("completed logical response count mismatch")
    if capture.get("http_request_count") != EXPECTED_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("capture HTTP request count mismatch")
    if capture.get("http_requests_this_invocation") != EXPECTED_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("capture invocation HTTP count mismatch")
    if capture.get("redirect_count") != 0 or capture.get("resumed_body_count") != 0:
        raise SingaporeBCAGreenMarkError("capture must contain seven direct fresh responses")

    expected_plan = [
        *(f"page-{offset}" for offset in PAGE_OFFSETS),
        "dataset-metadata",
        "open-data-licence",
    ]
    if [row.get("request_id") for row in requests] != expected_plan:
        raise SingaporeBCAGreenMarkError("capture request order/identity changed")
    raw_directory = capture_directory / "raw"
    if raw_directory.is_symlink() or not raw_directory.is_dir():
        raise SingaporeBCAGreenMarkError("capture raw directory invalid")
    expected_raw = {f"{request_id}.bin" for request_id in expected_plan}
    actual_raw = {child.name for child in raw_directory.iterdir()}
    if actual_raw != expected_raw:
        raise SingaporeBCAGreenMarkError("capture raw file set changed")

    bodies: dict[str, bytes] = {}
    for row in requests:
        request_id = row["request_id"]
        expected_url = (
            page_url(int(request_id.removeprefix("page-")))
            if request_id.startswith("page-")
            else DATASET_URL if request_id == "dataset-metadata" else LICENCE_URL
        )
        if row.get("url") != expected_url:
            raise SingaporeBCAGreenMarkError(f"capture URL mismatch: {request_id}")
        _official_url(expected_url)
        if row.get("status") != 200 or row.get("redirect_count") != 0:
            raise SingaporeBCAGreenMarkError(f"capture response not direct HTTP 200: {request_id}")
        if row.get("http_request_count") != 1:
            raise SingaporeBCAGreenMarkError(f"ambiguous HTTP count: {request_id}")
        content_type = row.get("content_type")
        expected_content_prefix = (
            "application/json" if request_id.startswith("page-") else "text/html"
        )
        if (
            not isinstance(content_type, str)
            or not content_type.casefold().startswith(expected_content_prefix)
        ):
            raise SingaporeBCAGreenMarkError(
                f"capture content type mismatch: {request_id}"
            )
        body_path = capture_directory / str(row.get("body_file"))
        if body_path.parent != raw_directory:
            raise SingaporeBCAGreenMarkError("capture body path escaped raw directory")
        body = _read_regular_bytes(body_path, label=f"capture body {request_id}")
        if row.get("bytes") != len(body) or row.get("sha256") != sha256_bytes(body):
            raise SingaporeBCAGreenMarkError(f"capture checkpoint mismatch: {request_id}")
        bodies[request_id] = body
    _validate_dataset_page(bodies["dataset-metadata"])
    _validate_licence_page(bodies["open-data-licence"])
    return capture, bodies


def _parse_snapshot_pages(bodies: Mapping[str, bytes]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset, expected_count in zip(PAGE_OFFSETS, PAGE_COUNTS, strict=True):
        request_id = f"page-{offset}"
        try:
            payload = json.loads(bodies[request_id])
        except (KeyError, json.JSONDecodeError) as error:
            raise SingaporeBCAGreenMarkError(f"invalid API JSON: {request_id}") from error
        if not isinstance(payload, dict):
            raise SingaporeBCAGreenMarkError(f"API envelope must be an object: {request_id}")
        if payload.get("success") is not True or set(payload) != {"success", "result"}:
            raise SingaporeBCAGreenMarkError(f"API success envelope changed: {request_id}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise SingaporeBCAGreenMarkError(f"API result envelope changed: {request_id}")
        fields = result.get("fields")
        actual_fields = (
            tuple((field.get("id"), field.get("type")) for field in fields)
            if isinstance(fields, list) and all(isinstance(field, dict) for field in fields)
            else ()
        )
        if actual_fields != EXPECTED_FIELDS:
            raise SingaporeBCAGreenMarkError(f"API field schema changed: {request_id}")
        if (
            result.get("resource_id") != DATASET_ID
            or result.get("total") != EXPECTED_TOTAL
            or result.get("limit") != PAGE_SIZE
            or result.get("offset") != offset
        ):
            raise SingaporeBCAGreenMarkError(f"API pagination metadata changed: {request_id}")
        records = result.get("records")
        if not isinstance(records, list) or len(records) != expected_count:
            raise SingaporeBCAGreenMarkError(f"API page row count changed: {request_id}")
        page_rows = [_validate_source_row(row) for row in records]
        expected_ids = list(range(offset + 1, offset + expected_count + 1))
        if [row["_id"] for row in page_rows] != expected_ids:
            raise SingaporeBCAGreenMarkError(f"API page ID arithmetic changed: {request_id}")
        rows.extend(page_rows)
    _validate_snapshot_rows(rows)
    return rows


def _validate_snapshot_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise SingaporeBCAGreenMarkError("snapshot row count changed")
    identifiers = [row["_id"] for row in rows]
    if identifiers != list(range(1, EXPECTED_TOTAL + 1)):
        raise SingaporeBCAGreenMarkError("snapshot IDs must be unique contiguous 1..4793")
    references = [row["Reference_No"] for row in rows]
    if any(not isinstance(value, str) or not value for value in references):
        raise SingaporeBCAGreenMarkError("Reference_No missing")
    if len(set(references)) != EXPECTED_UNIQUE_REFERENCE_COUNT:
        raise SingaporeBCAGreenMarkError("Reference_No uniqueness arithmetic changed")


def _match_sets(rows: list[dict[str, Any]]) -> dict[str, set[int]]:
    result = {
        "scheme": {
            row["_id"] for row in rows if data_centre_phrase_match(row["GM_Version"])
        },
        "project_type": {
            row["_id"] for row in rows if data_centre_phrase_match(row["Project_Type"])
        },
        "name": {row["_id"] for row in rows if data_centre_name_match(row)},
    }
    counts = {key: len(value) for key, value in result.items()}
    counts["union"] = len(set().union(*result.values()))
    if counts != EXPECTED_MATCH_COUNTS:
        raise SingaporeBCAGreenMarkError("closed match-union arithmetic changed")
    return result


def _exclusive_class(identifier: int, matches: Mapping[str, set[int]]) -> str:
    if identifier in matches["scheme"]:
        return "green_mark_data_centre_scheme"
    if identifier in matches["project_type"]:
        return "additional_project_type_match"
    if identifier in matches["name"]:
        return "name_only_review"
    raise SingaporeBCAGreenMarkError("unmatched ID entered the closed union")


def _pii_scan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [
        normalize_text(value)
        for row in rows
        for value in row.values()
        if isinstance(value, str)
    ]
    schema_person_contact_fields = sorted(
        field for field in EXPECTED_ROW_KEYS if PERSON_CONTACT_FIELD_RE.search(field)
    )
    result = {
        "email_pattern_match_count": sum(bool(EMAIL_RE.search(value)) for value in texts),
        "nric_fin_pattern_match_count": sum(
            bool(NRIC_FIN_RE.search(value)) for value in texts
        ),
        "personal_data_absence_claimed": False,
        "scan_scope": "all string cells in all 4,793 source rows",
        "schema_fields": sorted(EXPECTED_ROW_KEYS),
        "schema_person_or_contact_fields": schema_person_contact_fields,
        "singapore_phone_pattern_match_count": sum(
            bool(SG_PHONE_RE.search(value)) for value in texts
        ),
    }
    if (
        result["email_pattern_match_count"]
        or result["nric_fin_pattern_match_count"]
        or result["singapore_phone_pattern_match_count"]
        or schema_person_contact_fields
    ):
        raise SingaporeBCAGreenMarkError("PII/schema scan no longer has zero matches")
    return result


def _observation(row: Mapping[str, Any], matches: Mapping[str, set[int]]) -> dict[str, Any]:
    identifier = row["_id"]
    match_flags = {
        "name": identifier in matches["name"],
        "project_type": identifier in matches["project_type"],
        "scheme": identifier in matches["scheme"],
    }
    return {
        "actual_project_name": row["Actual_Project_Name"],
        "annual_energy_consumption": None,
        "certification_observation_count_contribution": 1,
        "coordinates": None,
        "data_centre_type": None,
        "e_certificate_date_raw": row["e_cert"],
        "exclusive_classification": _exclusive_class(identifier, matches),
        "expiry_date_raw": row["Expiry"],
        "format": OBSERVATION_FORMAT,
        "gfa_raw": row["GFA"],
        "gfa_unit": None,
        "green_mark_version": row["GM_Version"],
        "it_capacity": None,
        "match_memberships": match_flags,
        "observation_id": f"bca-green-mark-certification:{identifier}",
        "operator": None,
        "physical_lifecycle": PHYSICAL_LIFECYCLE_BOUNDARY,
        "postal_code_raw": row["Postal_Code"],
        "power": None,
        "previous_green_mark_reference_no": row["Previous_GM_Cert_Reference_No"],
        "project_count_contribution": None,
        "project_name": row["Project_Name"],
        "project_type_raw": row["Project_Type"],
        "provisional_letter_date_raw": row["Prov_Letter"],
        "pue": None,
        "rating": row["Rating"],
        "recertification_raw": row["Re_Certification"],
        "reference_no": row["Reference_No"],
        "site_id": None,
        "source_record_id": identifier,
        "source_url": DATASET_URL,
        "unique_site_count_contribution": None,
    }


def derive_rows(
    snapshot_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _validate_snapshot_rows(snapshot_rows)
    matches = _match_sets(snapshot_rows)
    union = set().union(*matches.values())
    observations = [
        _observation(row, matches) for row in snapshot_rows if row["_id"] in union
    ]
    memberships = [
        {
            "match_field_family": family,
            "normalization": "NFKC+casefold+collapsed-whitespace",
            "phrase_pattern": DATA_CENTRE_RE.pattern,
            "source_record_id": identifier,
        }
        for family in ("scheme", "project_type", "name")
        for identifier in sorted(matches[family])
    ]
    leads = [
        observation
        for observation in observations
        if observation["match_memberships"]["scheme"]
        and new_data_centre_scheme_match(observation["green_mark_version"])
        and observation["recertification_raw"] == "No"
        and observation["provisional_letter_date_raw"] is not None
        and observation["e_certificate_date_raw"] is None
    ]
    if [row["source_record_id"] for row in leads] != list(EXPECTED_LEAD_IDS):
        raise SingaporeBCAGreenMarkError("provisional new-scheme lead subset changed")
    if len(memberships) != EXPECTED_MEMBERSHIP_COUNT:
        raise SingaporeBCAGreenMarkError("match membership arithmetic changed")
    exclusive = Counter(row["exclusive_classification"] for row in observations)
    if dict(exclusive) != EXPECTED_EXCLUSIVE_COUNTS:
        raise SingaporeBCAGreenMarkError("exclusive classification arithmetic changed")
    intersections = {
        "all_three": len(matches["scheme"] & matches["project_type"] & matches["name"]),
        "scheme_and_name": len(matches["scheme"] & matches["name"]),
        "scheme_and_project_type": len(matches["scheme"] & matches["project_type"]),
        "project_type_and_name": len(matches["project_type"] & matches["name"]),
    }
    if intersections != EXPECTED_INTERSECTION_COUNTS:
        raise SingaporeBCAGreenMarkError("match intersection arithmetic changed")
    return observations, memberships, leads, _pii_scan(snapshot_rows)


def _retrieval_inventory(
    capture: Mapping[str, Any], bodies: Mapping[str, bytes]
) -> dict[str, Any]:
    responses: list[dict[str, Any]] = []
    for row in capture["requests"]:
        request_id = row["request_id"]
        response = {
            "bytes": len(bodies[request_id]),
            "content_type": row["content_type"],
            "http_request_count": row["http_request_count"],
            "redirect_count": row["redirect_count"],
            "request_id": request_id,
            "sha256": sha256_bytes(bodies[request_id]),
            "status": row["status"],
            "url": row["url"],
        }
        if request_id.startswith("page-"):
            result = json.loads(bodies[request_id])["result"]
            response.update(
                {
                    "api_total": result["total"],
                    "field_schema_sha256": sha256_bytes(
                        canonical_json(result["fields"])
                    ),
                    "limit": result["limit"],
                    "offset": result["offset"],
                    "record_count": len(result["records"]),
                }
            )
        responses.append(response)
    return {
        "capture_created_at": capture["created_at"],
        "capture_http_request_count": capture["http_request_count"],
        "capture_http_requests_this_invocation": capture[
            "http_requests_this_invocation"
        ],
        "capture_logical_request_count": capture["planned_logical_request_count"],
        "capture_redirect_count": capture["redirect_count"],
        "capture_resumed_body_count": capture["resumed_body_count"],
        "format": RETRIEVAL_FORMAT,
        "network_responses": responses,
        "offline_validation_http_request_count": 0,
        "raw_response_bodies_released": False,
        "release_build_http_request_count": 0,
    }


def _validate_retrieval_inventory(retrieval: Mapping[str, Any]) -> None:
    expected_keys = {
        "capture_created_at",
        "capture_http_request_count",
        "capture_http_requests_this_invocation",
        "capture_logical_request_count",
        "capture_redirect_count",
        "capture_resumed_body_count",
        "format",
        "network_responses",
        "offline_validation_http_request_count",
        "raw_response_bodies_released",
        "release_build_http_request_count",
    }
    if set(retrieval) != expected_keys or retrieval.get("format") != RETRIEVAL_FORMAT:
        raise SingaporeBCAGreenMarkError("retrieval inventory identity/schema changed")
    if (
        retrieval.get("capture_http_request_count") != EXPECTED_LOGICAL_REQUESTS
        or retrieval.get("capture_http_requests_this_invocation")
        != EXPECTED_LOGICAL_REQUESTS
        or retrieval.get("capture_logical_request_count") != EXPECTED_LOGICAL_REQUESTS
        or retrieval.get("capture_redirect_count") != 0
        or retrieval.get("capture_resumed_body_count") != 0
        or retrieval.get("offline_validation_http_request_count") != 0
        or retrieval.get("release_build_http_request_count") != 0
        or retrieval.get("raw_response_bodies_released") is not False
    ):
        raise SingaporeBCAGreenMarkError("retrieval network-counter boundary changed")
    created_at = retrieval.get("capture_created_at")
    if not isinstance(created_at, str) or not created_at.endswith("Z"):
        raise SingaporeBCAGreenMarkError("retrieval capture timestamp invalid")
    responses = retrieval.get("network_responses")
    expected_ids = [
        *(f"page-{offset}" for offset in PAGE_OFFSETS),
        "dataset-metadata",
        "open-data-licence",
    ]
    if not isinstance(responses, list) or not all(
        isinstance(row, dict) for row in responses
    ):
        raise SingaporeBCAGreenMarkError("retrieval response must be an object")
    if [row.get("request_id") for row in responses] != expected_ids:
        raise SingaporeBCAGreenMarkError("retrieval response identity/order changed")
    field_schema_hashes: set[str] = set()
    for index, response in enumerate(responses):
        request_id = response["request_id"]
        expected_url = (
            page_url(int(request_id.removeprefix("page-")))
            if request_id.startswith("page-")
            else DATASET_URL if request_id == "dataset-metadata" else LICENCE_URL
        )
        if (
            response.get("url") != expected_url
            or response.get("status") != 200
            or response.get("http_request_count") != 1
            or response.get("redirect_count") != 0
            or not isinstance(response.get("bytes"), int)
            or response["bytes"] <= 0
            or not isinstance(response.get("sha256"), str)
            or not _SHA256_RE.fullmatch(response["sha256"])
        ):
            raise SingaporeBCAGreenMarkError(
                f"retrieval response checkpoint invalid: {request_id}"
            )
        content_type = response.get("content_type")
        if request_id.startswith("page-"):
            offset = PAGE_OFFSETS[index]
            expected_count = PAGE_COUNTS[index]
            expected_page_keys = {
                "api_total",
                "bytes",
                "content_type",
                "field_schema_sha256",
                "http_request_count",
                "limit",
                "offset",
                "record_count",
                "redirect_count",
                "request_id",
                "sha256",
                "status",
                "url",
            }
            if (
                set(response) != expected_page_keys
                or not isinstance(content_type, str)
                or not content_type.casefold().startswith("application/json")
                or response.get("api_total") != EXPECTED_TOTAL
                or response.get("limit") != PAGE_SIZE
                or response.get("offset") != offset
                or response.get("record_count") != expected_count
                or not _SHA256_RE.fullmatch(
                    str(response.get("field_schema_sha256", ""))
                )
            ):
                raise SingaporeBCAGreenMarkError(
                    f"retrieval page arithmetic invalid: {request_id}"
                )
            field_schema_hashes.add(response["field_schema_sha256"])
        else:
            expected_html_keys = {
                "bytes",
                "content_type",
                "http_request_count",
                "redirect_count",
                "request_id",
                "sha256",
                "status",
                "url",
            }
            if (
                set(response) != expected_html_keys
                or not isinstance(content_type, str)
                or not content_type.casefold().startswith("text/html")
            ):
                raise SingaporeBCAGreenMarkError(
                    f"retrieval HTML evidence invalid: {request_id}"
                )
    if len(field_schema_hashes) != 1:
        raise SingaporeBCAGreenMarkError("API field schema hashes differ across pages")


def build_release_documents_from_snapshot(
    definition: Mapping[str, Any],
    snapshot_rows: list[dict[str, Any]],
    retrieval: Mapping[str, Any],
) -> dict[str, bytes]:
    if definition != source_definition():
        raise SingaporeBCAGreenMarkError("checked-in definition differs from module contract")
    _validate_retrieval_inventory(retrieval)
    observations, memberships, leads, pii_scan = derive_rows(snapshot_rows)
    exclusive = Counter(row["exclusive_classification"] for row in observations)
    scheme_count = sum(row["match_memberships"]["scheme"] for row in observations)
    type_count = sum(row["match_memberships"]["project_type"] for row in observations)
    name_count = sum(row["match_memberships"]["name"] for row in observations)
    assessment = {
        "certification_observation_count": EXPECTED_TOTAL,
        "classification_counts": {
            key: exclusive.get(key, 0) for key in MATCH_CLASSES
        },
        "coverage": definition["coverage_contract"],
        "data_centre_match_union_count": len(observations),
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": ASSESSMENT_FORMAT,
        "intersection_counts": EXPECTED_INTERSECTION_COUNTS,
        "lead_count": len(leads),
        "match_membership_count": len(memberships),
        "match_set_counts": {
            "name": name_count,
            "project_type": type_count,
            "scheme": scheme_count,
            "union": len(observations),
        },
        "physical_lifecycle_boundary": PHYSICAL_LIFECYCLE_BOUNDARY,
        "pii_and_schema_scan": pii_scan,
        "project_count": None,
        "public_review_release_permitted": True,
        "reference_no_distinct_count": EXPECTED_UNIQUE_REFERENCE_COUNT,
        "release_id": RELEASE_ID,
        "rights_policy": RIGHTS_POLICY,
        "source_record_id_count": EXPECTED_TOTAL,
        "unique_site_count": None,
    }
    source_inventory = {
        "dataset_description": (
            "Green Mark certified buildings; voluntary listing only, excluding "
            "legislated projects and projects opted out of public disclosure"
        ),
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {"role": "dataset_metadata", "url": DATASET_URL},
            {"role": "dataset_rows", "url": DATASTORE_ENDPOINT},
            {"role": "licence", "url": LICENCE_URL},
        ],
        "publisher": PUBLISHER,
    }
    schema = {
        "format": SCHEMA_FORMAT,
        "invariants": {
            "certification_observation_is_project": False,
            "certification_observation_is_site": False,
            "coordinates_are_null": True,
            "gfa_has_inferred_unit": False,
            "physical_lifecycle_is_null": True,
            "power_energy_capacity_and_pue_are_null": True,
            "reference_no_is_unique": False,
            "source_record_id_is_unique": True,
        },
        "observation_format": OBSERVATION_FORMAT,
        "source_fields": [
            {"id": identifier, "type": field_type}
            for identifier, field_type in EXPECTED_FIELDS
        ],
    }
    readme = f"""# Singapore BCA Green Mark data-centre certification assessment

This frozen public-review release reproduces the complete **{EXPECTED_TOTAL:,}-row**
`Green Mark Buildings` dataset snapshot and derives a closed **{len(observations)}-row**
data-centre certification-observation union. The exact NFKC, casefold, and
whitespace-normalized phrase predicate matches data centre/center spelling,
plural, hyphenated, and concatenated variants. It yields {scheme_count} scheme
matches, {type_count} project-type matches, and {name_count} name matches. With
scheme-first precedence the exclusive classes are {exclusive['green_mark_data_centre_scheme']}
scheme observations, {exclusive['additional_project_type_match']} additional
project-type observations, and {exclusive['name_only_review']} name-only review
observations. Match memberships are retained separately.

The four-row lead subset contains source `_id` values {', '.join(map(str, EXPECTED_LEAD_IDS))}.
Each has a new-data-centre Green Mark scheme, `Re_Certification=No`, a non-null
`Prov_Letter`, and null `e_cert`. `Prov_Letter` is a design/commitment-stage
certification field, not evidence of physical construction. Certification,
electronic-certificate, expiry, and re-certification fields are retained only as
raw source values. They are never converted into construction, commissioning,
completion, or operation dates or status.

The source unit is one certification observation keyed by `_id`; `_id` is unique
across all {EXPECTED_TOTAL:,} rows, while `Reference_No` has
{EXPECTED_UNIQUE_REFERENCE_COUNT:,} distinct values and is not a safe unique key.
Project and unique-site counts remain null. Operator, data-centre type,
coordinates, power, IT capacity, PUE, and annual energy remain null. `GFA` is
preserved as untyped raw text with no inferred unit.

Coverage is Jan 2005 through Feb 2026, last updated 19 May 2026. The listing is
voluntary only and excludes legislated projects and projects that opted out of
public disclosure; it is not a complete Singapore data-centre inventory. A
complete schema scan found no person/contact fields, and limited pattern scans
found no email, NRIC/FIN, or Singapore-phone strings. This does not assert that
the dataset is free of all personal data.

The dataset snapshot and derived factual data are released under the Singapore
Open Data Licence version 1.0 with required attribution. That licence excludes
personal data, unlicensed third-party rights, and patents/trademarks/design
rights; no agency name, logo, or mark is treated as licensed dataset content and
no endorsement is implied. Raw API and HTML response bodies remain outside the
release; their exact hashes, sizes, URLs, response types, and status codes are
bound in `retrieval-inventory.json`.

No automatic construction-master import is allowed. A future explicit Tier-B
review-observation import may retain these records only with physical lifecycle
status null. Map import is false because the source has no coordinates; no fuzzy
join to a Green Mark geospatial dataset is authorized.
""".encode("utf-8")
    attribution = (
        "Contains information from Green Mark Buildings accessed on "
        f"{ACCESS_DATE_DISPLAY} from {DATASET_URL}, which is made available "
        "under the terms of the Singapore Open Data Licence version 1.0 "
        f"{LICENCE_URL}.\n"
        "Publisher: Building and Construction Authority (BCA), Singapore.\n"
        "No endorsement by the Singapore Government or BCA is implied. Agency "
        "names, logos, and trademarks are not reused as licensed dataset content.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "assessment.json": canonical_json(assessment),
        "dataset-snapshot.jsonl": jsonl(snapshot_rows),
        "definition.json": canonical_json(definition),
        "match-membership.jsonl": jsonl(memberships),
        "observations.jsonl": jsonl(observations),
        "provisional-new-scheme-leads.jsonl": jsonl(leads),
        "retrieval-inventory.json": canonical_json(dict(retrieval)),
        "schema.json": canonical_json(schema),
        "source-inventory.json": canonical_json(source_inventory),
    }


def build_release_documents(
    definition: Mapping[str, Any], capture: Mapping[str, Any], bodies: Mapping[str, bytes]
) -> dict[str, bytes]:
    snapshot_rows = _parse_snapshot_pages(bodies)
    retrieval = _retrieval_inventory(capture, bodies)
    return build_release_documents_from_snapshot(definition, snapshot_rows, retrieval)


def _manifest(documents: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "files": {
            name: {"bytes": len(body), "sha256": sha256_bytes(body)}
            for name, body in sorted(documents.items())
        },
        "format": RELEASE_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def freeze_release(path: Path) -> None:
    for child in path.rglob("*"):
        child.chmod(0o555 if child.is_dir() else 0o444)
    path.chmod(0o555)


def thaw_for_test(path: Path) -> None:
    path.chmod(0o755)
    for child in path.rglob("*"):
        child.chmod(0o755 if child.is_dir() else 0o644)


def is_frozen_release(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o555:
        return False
    for child in path.rglob("*"):
        if child.is_symlink():
            return False
        expected = 0o555 if child.is_dir() else 0o444
        if stat.S_IMODE(child.stat().st_mode) != expected:
            return False
    return True


def write_release_bundle(
    definition_path: Path,
    capture_directory: Path,
    output: Path,
    *,
    freeze: bool = True,
) -> Path:
    definition_raw = _read_regular_bytes(definition_path, label="source definition")
    definition = json.loads(definition_raw)
    if definition_raw != canonical_json(definition):
        raise SingaporeBCAGreenMarkError("source definition is not canonical JSON")
    capture, bodies = load_capture(capture_directory)
    documents = build_release_documents(definition, capture, bodies)
    manifest = _manifest(documents)
    documents[MANIFEST_FILENAME] = canonical_json(manifest)
    documents[MANIFEST_HASH_FILENAME] = (
        f"{sha256_bytes(documents[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise SingaporeBCAGreenMarkError(f"refusing to overwrite output: {output}")
    staging = Path(tempfile.mkdtemp(prefix=f".{RELEASE_ID}-", dir=output.parent))
    try:
        for name, body in documents.items():
            destination = staging / name
            destination.write_bytes(body)
            destination.chmod(0o644)
        validate_release_bundle(staging, definition_path=definition_path)
        os.replace(staging, output)
        if freeze:
            freeze_release(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return output


def _load_jsonl_regular(path: Path, *, label: str) -> list[dict[str, Any]]:
    raw = _read_regular_bytes(path, label=label)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        if not line.endswith(b"\n"):
            raise SingaporeBCAGreenMarkError(f"{label} line lacks newline: {line_number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SingaporeBCAGreenMarkError(
                f"{label} invalid JSON line: {line_number}"
            ) from error
        if not isinstance(row, dict) or canonical_line(row) != line:
            raise SingaporeBCAGreenMarkError(f"{label} is not canonical JSONL")
        rows.append(row)
    return rows


def validate_release_bundle(
    path: Path, *, definition_path: Path | None = None
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_dir():
        raise SingaporeBCAGreenMarkError("release directory must be a non-symlink directory")
    children = list(path.iterdir())
    if any(child.is_symlink() or not child.is_file() for child in children):
        raise SingaporeBCAGreenMarkError("release may contain regular files only")
    actual_files = {child.name for child in children}
    if actual_files != EXPECTED_FILES:
        raise SingaporeBCAGreenMarkError(
            f"release file set mismatch: {sorted(actual_files ^ EXPECTED_FILES)}"
        )
    manifest_raw = _read_regular_bytes(path / MANIFEST_FILENAME, label="manifest")
    manifest = json.loads(manifest_raw)
    if manifest_raw != canonical_json(manifest):
        raise SingaporeBCAGreenMarkError("manifest is not canonical JSON")
    if manifest.get("format") != RELEASE_FORMAT or manifest.get("release_id") != RELEASE_ID:
        raise SingaporeBCAGreenMarkError("manifest identity mismatch")
    expected_hash_line = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    manifest_hash_raw = _read_regular_bytes(
        path / MANIFEST_HASH_FILENAME, label="manifest hash"
    )
    if manifest_hash_raw.decode("ascii") != expected_hash_line:
        raise SingaporeBCAGreenMarkError("manifest hash mismatch")
    if set(manifest.get("files", {})) != DERIVED_FILENAMES:
        raise SingaporeBCAGreenMarkError("manifest file inventory mismatch")
    for name, expected in manifest["files"].items():
        _require_regular_file(path / name, label=name)
        actual = checkpoint(path / name)
        if actual != expected or not _SHA256_RE.fullmatch(actual["sha256"]):
            raise SingaporeBCAGreenMarkError(f"file checkpoint mismatch: {name}")

    definition_raw = _read_regular_bytes(path / "definition.json", label="definition")
    definition = json.loads(definition_raw)
    if definition_raw != canonical_json(definition) or definition != source_definition():
        raise SingaporeBCAGreenMarkError("release definition differs from module contract")
    if definition_path is not None:
        checked_raw = _read_regular_bytes(definition_path, label="checked-in definition")
        checked = json.loads(checked_raw)
        if checked_raw != canonical_json(checked) or checked != definition:
            raise SingaporeBCAGreenMarkError(
                "release definition differs from checked-in definition"
            )
    snapshot = _load_jsonl_regular(path / "dataset-snapshot.jsonl", label="snapshot")
    snapshot_rows = [_validate_source_row(row) for row in snapshot]
    retrieval_raw = _read_regular_bytes(
        path / "retrieval-inventory.json", label="retrieval inventory"
    )
    retrieval = json.loads(retrieval_raw)
    if retrieval_raw != canonical_json(retrieval):
        raise SingaporeBCAGreenMarkError("retrieval inventory is not canonical JSON")
    reproduced = build_release_documents_from_snapshot(
        definition, snapshot_rows, retrieval
    )
    for name, body in reproduced.items():
        if _read_regular_bytes(path / name, label=name) != body:
            raise SingaporeBCAGreenMarkError(f"offline byte reproduction mismatch: {name}")
    if canonical_json(_manifest(reproduced)) != manifest_raw:
        raise SingaporeBCAGreenMarkError("manifest offline reproduction mismatch")

    observations = _load_jsonl_regular(path / "observations.jsonl", label="observations")
    memberships = _load_jsonl_regular(
        path / "match-membership.jsonl", label="match memberships"
    )
    leads = _load_jsonl_regular(
        path / "provisional-new-scheme-leads.jsonl", label="lead subset"
    )
    assessment = json.loads(
        _read_regular_bytes(path / "assessment.json", label="assessment")
    )
    return {
        "assessment": assessment,
        "definition": definition,
        "leads": leads,
        "manifest": manifest,
        "memberships": memberships,
        "observations": observations,
        "retrieval": retrieval,
        "snapshot": snapshot_rows,
    }


def _capture_request(url: str, *, timeout: float) -> tuple[int, str, int, bytes]:
    _official_url(url)
    with tempfile.TemporaryDirectory(prefix="singapore-bca-request-") as temporary:
        output = Path(temporary) / "body.bin"
        command = [
            "curl",
            "--http1.1",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            str(timeout),
            "--user-agent",
            "datacenter-atlas-official-source-audit/1.0",
            "--header",
            "Accept: application/json,text/html,*/*",
            "--output",
            str(output),
            "--write-out",
            "%{http_code}\n%{content_type}\n%{num_redirects}",
            url,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout + 10,
        )
        if completed.returncode != 0 or not output.is_file():
            detail = completed.stderr.strip() or f"curl exit {completed.returncode}"
            raise SingaporeBCAGreenMarkError(f"request failed: {url}: {detail}")
        metadata = completed.stdout.splitlines()
        if len(metadata) != 3 or not metadata[0].isdigit() or not metadata[2].isdigit():
            raise SingaporeBCAGreenMarkError(f"invalid curl response metadata: {url}")
        return int(metadata[0]), metadata[1], int(metadata[2]), output.read_bytes()


def capture_live_sources(capture_directory: Path, *, timeout: float = 120.0) -> Path:
    if timeout <= 0:
        raise SingaporeBCAGreenMarkError("timeout must be positive")
    if capture_directory.exists() or capture_directory.is_symlink():
        raise SingaporeBCAGreenMarkError("capture output must not already exist")
    capture_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{capture_directory.name}-", dir=capture_directory.parent)
    )
    staging.chmod(0o700)
    raw = staging / "raw"
    raw.mkdir(mode=0o700)
    plan = [
        *((f"page-{offset}", page_url(offset)) for offset in PAGE_OFFSETS),
        ("dataset-metadata", DATASET_URL),
        ("open-data-licence", LICENCE_URL),
    ]
    if len(plan) != EXPECTED_LOGICAL_REQUESTS or len(plan) > MAX_LOGICAL_REQUESTS:
        raise SingaporeBCAGreenMarkError("closed request plan arithmetic changed")
    rows: list[dict[str, Any]] = []
    try:
        for request_id, url in plan:
            started_at = datetime.now(UTC).isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
            status, content_type, redirects, body = _capture_request(url, timeout=timeout)
            if status != 200 or redirects != 0:
                raise SingaporeBCAGreenMarkError(
                    f"expected direct HTTP 200 response: {request_id}"
                )
            body_file = f"raw/{request_id}.bin"
            destination = staging / body_file
            destination.write_bytes(body)
            destination.chmod(0o600)
            rows.append(
                {
                    "body_file": body_file,
                    "bytes": len(body),
                    "content_type": content_type,
                    "finished_at": datetime.now(UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                    "http_request_count": 1,
                    "redirect_count": redirects,
                    "request_id": request_id,
                    "sha256": sha256_bytes(body),
                    "started_at": started_at,
                    "status": status,
                    "url": url,
                }
            )
        capture = {
            "completed_logical_response_count": len(rows),
            "created_at": datetime.now(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "format": CAPTURE_FORMAT,
            "http_request_count": sum(row["http_request_count"] for row in rows),
            "http_requests_this_invocation": sum(
                row["http_request_count"] for row in rows
            ),
            "planned_logical_request_count": len(plan),
            "redirect_count": sum(row["redirect_count"] for row in rows),
            "requests": rows,
            "resumed_body_count": 0,
        }
        capture_path = staging / "capture.json"
        capture_path.write_bytes(canonical_json(capture))
        capture_path.chmod(0o600)
        loaded, bodies = load_capture(staging)
        _parse_snapshot_pages(bodies)
        build_release_documents(source_definition(), loaded, bodies)
        os.replace(staging, capture_directory)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return capture_directory
