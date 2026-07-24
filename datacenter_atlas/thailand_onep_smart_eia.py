"""Bounded Thailand ONEP Smart EIA approved-report source assessment.

The official CKAN record links one JSON resource and carries the literal
licence label ``Creative Commons Attributions``.  The single permitted resource
request returned only page 1 of 138, so this lane fails closed: it records audit
metadata and hashes but emits no ONEP report observations or review shards.

An approved IEE/EIA/EHIA-family report is an administrative report observation,
not evidence that a project is announced, permitted for construction, being
built, complete, commissioned, or operating.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
import unicodedata
from urllib.parse import urlsplit
import uuid


SCHEMA_VERSION = 1
RELEASE_ID = (
    "thailand-onep-smart-eia-approved-reports-data-centre-"
    "snapshot-audit-2026-07-18-v1"
)
SOURCE_ID = RELEASE_ID
RELEASE_FORMAT = "datacenter-atlas-thailand-onep-smart-eia-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-thailand-onep-smart-eia-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-thailand-onep-smart-eia-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-thailand-onep-smart-eia-retrieval-v1"
SNAPSHOT_AUDIT_FORMAT = (
    "datacenter-atlas-thailand-onep-smart-eia-snapshot-audit-v1"
)
SCHEMA_FORMAT = "datacenter-atlas-thailand-onep-smart-eia-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-thailand-onep-smart-eia-source-inventory-v1"
)

ASSESSMENT_DATE = date(2026, 7, 18)
PUBLISHER = (
    "Office of Natural Resources and Environmental Policy and Planning "
    "(ONEP), Thailand"
)
DATASET_NAME = "database1"
DATASET_TITLE = "รายงานการประเมินผลกระทบสิ่งแวดล้อมที่ได้รับความเห็นชอบ"
PUBLIC_LIST_URL = "https://eia.onep.go.th/site/eia"
DATASET_URL = "https://onep.gdcatalog.go.th/en/dataset/database1"
PACKAGE_SHOW_URL = (
    "https://onep.gdcatalog.go.th/api/3/action/package_show?id=database1"
)
RESOURCE_URL = "https://eia.onep.go.th/services/web/open-api/eia-list"
PRIVACY_URL = "https://eia.onep.go.th/site/policy"
ROBOTS_URL = "https://eia.onep.go.th/robots.txt"
LICENCE_LABEL = "Creative Commons Attributions"

REQUEST_TIMEOUT_SECONDS = 60
MAX_REDIRECTS = 3
MAX_BODY_BYTES = 100 * 1024 * 1024
MAX_RECORDS = 25_000
MAX_CANDIDATE_UNION = 500
MAX_REVIEW_SHARD = 250

THAI_DIRECT_TERMS = (
    "ดาต้าเซ็นเตอร์",
    "ดาต้า เซ็นเตอร์",
    "ศูนย์ข้อมูลคอมพิวเตอร์",
    "ศูนย์ประมวลผลข้อมูล",
)
ENGLISH_DIRECT_TERMS = (
    "internet data center",
    "internet data centre",
    "data center",
    "data centre",
)
IDC_TERM = "IDC"
THAI_GENERIC_TERM = "ศูนย์ข้อมูล"
THAI_GENERIC_CONTEXT_TERMS = (
    "คอมพิวเตอร์",
    "คลาวด์",
    "อินเทอร์เน็ต",
    "เซิร์ฟเวอร์",
)
MATCH_FIELDS = ("name",)

EXPECTED_ROW_KEYS = frozenset(
    {
        "approve_date",
        "approve_number",
        "category",
        "code",
        "name",
        "owner",
        "province",
        "reporter",
        "year",
        "zone",
    }
)
DOCUMENTED_PROJECT_STATUS_FIELDS = frozenset()

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "definition.json",
    "observations.jsonl",
    "query-plan.json",
    "retrieval-inventory.json",
    "review-shards.jsonl",
    "schema.json",
    "snapshot-audit.json",
    "source-inventory.json",
}
EXPECTED_FILES = DERIVED_FILENAMES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENGLISH_TERM_PATTERNS = tuple(
    (
        term,
        re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"),
    )
    for term in ENGLISH_DIRECT_TERMS
)
_IDC_PATTERN = re.compile(r"(?<![a-z0-9])idc(?![a-z0-9])")
_ONEP_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, RESOURCE_URL)


class ThailandONEPSmartEIAError(ValueError):
    """Raised when the ONEP assessment fails its closed contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(dict(row)) for row in rows)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ThailandONEPSmartEIAError("text normalization requires text or null")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def matched_terms(value: str | None) -> tuple[str, ...]:
    """Return exact high-precision term memberships in declared order."""

    normalized = normalize_text(value)
    hits: list[str] = []
    for term in THAI_DIRECT_TERMS:
        if term in normalized:
            hits.append(term)
    for term, pattern in _ENGLISH_TERM_PATTERNS:
        if pattern.search(normalized):
            hits.append(term)
    if _IDC_PATTERN.search(normalized):
        hits.append(IDC_TERM)
    if THAI_GENERIC_TERM in normalized and any(
        context in normalized for context in THAI_GENERIC_CONTEXT_TERMS
    ):
        hits.append(f"{THAI_GENERIC_TERM}+context")
    return tuple(hits)


def _strict_json(body: bytes, *, label: str) -> Any:
    if not isinstance(body, bytes):
        raise ThailandONEPSmartEIAError(f"{label} must be bytes")
    if len(body) > MAX_BODY_BYTES:
        raise ThailandONEPSmartEIAError(f"{label} exceeds the body cap")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ThailandONEPSmartEIAError(f"{label} is not UTF-8") from error

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ThailandONEPSmartEIAError(
                    f"{label} contains a duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
    except json.JSONDecodeError as error:
        raise ThailandONEPSmartEIAError(f"{label} is invalid JSON") from error


def _official_url(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise ThailandONEPSmartEIAError(f"{label} must be a URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.fragment
        or parsed.hostname not in {"eia.onep.go.th", "onep.gdcatalog.go.th"}
    ):
        raise ThailandONEPSmartEIAError(f"{label} is outside official hosts")
    return value


def _utc_timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ThailandONEPSmartEIAError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ThailandONEPSmartEIAError(f"{label} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ThailandONEPSmartEIAError(f"{label} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _validate_package_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"help", "result", "success"}:
        raise ThailandONEPSmartEIAError("CKAN package envelope schema changed")
    if value.get("success") is not True or not isinstance(value.get("result"), dict):
        raise ThailandONEPSmartEIAError("CKAN package_show did not succeed")
    result = value["result"]
    expected = {
        "data_category": "ข้อมูลสาธารณะ",
        "license_id": LICENCE_LABEL,
        "license_title": LICENCE_LABEL,
        "name": DATASET_NAME,
        "private": False,
        "title": DATASET_TITLE,
    }
    if any(result.get(key) != expected_value for key, expected_value in expected.items()):
        raise ThailandONEPSmartEIAError("CKAN dataset identity or licence changed")
    if result.get("license_url") is not None:
        raise ThailandONEPSmartEIAError(
            "licence URL unexpectedly appeared; review rather than inferring a version"
        )
    if result.get("accessible_condition") != "ไม่มี":
        raise ThailandONEPSmartEIAError("CKAN access condition changed")
    resources = result.get("resources")
    if not isinstance(resources, list) or len(resources) != 1:
        raise ThailandONEPSmartEIAError("CKAN resource inventory changed")
    resource = resources[0]
    if (
        not isinstance(resource, dict)
        or resource.get("format") != "JSON"
        or resource.get("url") != RESOURCE_URL
        or resource.get("datastore_active") is not False
        or resource.get("datastore_contains_all_records_of_source_file") is not False
    ):
        raise ThailandONEPSmartEIAError("CKAN JSON resource contract changed")
    return result


def _validate_source_row(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or frozenset(value) != EXPECTED_ROW_KEYS:
        raise ThailandONEPSmartEIAError("ONEP row schema changed")
    result: dict[str, str] = {}
    for field in sorted(EXPECTED_ROW_KEYS):
        field_value = value[field]
        if not isinstance(field_value, str) or not field_value.strip():
            raise ThailandONEPSmartEIAError(
                f"ONEP row field must be non-empty text: {field}"
            )
        result[field] = field_value
    return result


def approval_date_gregorian(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise ThailandONEPSmartEIAError("approval date is not DD/MM/BBBB")
    day_value, month_value, buddhist_year = (int(part) for part in value.split("/"))
    gregorian_year = buddhist_year - 543
    if gregorian_year < 1900 or gregorian_year > 2200:
        raise ThailandONEPSmartEIAError("approval date Buddhist year is implausible")
    try:
        parsed = date(gregorian_year, month_value, day_value)
    except ValueError as error:
        raise ThailandONEPSmartEIAError("approval date is invalid") from error
    return parsed.isoformat()


def approval_year_gregorian(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}", value):
        raise ThailandONEPSmartEIAError("approval year is not four digits")
    result = int(value) - 543
    if result < 1900 or result > 2200:
        raise ThailandONEPSmartEIAError("approval year Buddhist value is implausible")
    return result


def stable_observation_id(row: Mapping[str, Any]) -> str:
    validated = _validate_source_row(dict(row))
    return str(uuid.uuid5(_ONEP_NAMESPACE, validated["code"]))


def _deduplicate_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, str]], int]:
    by_code: dict[str, dict[str, str]] = {}
    exact_duplicates = 0
    for value in rows:
        row = _validate_source_row(dict(value))
        prior = by_code.get(row["code"])
        if prior is None:
            by_code[row["code"]] = row
        elif prior == row:
            exact_duplicates += 1
        else:
            raise ThailandONEPSmartEIAError(
                f"conflicting ONEP source-key collision: {row['code']}"
            )
    return list(by_code.values()), exact_duplicates


def validate_snapshot_payload(value: Any, *, require_complete: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "currentPage",
        "dataList",
        "totalCount",
        "totalPage",
    }:
        raise ThailandONEPSmartEIAError("ONEP snapshot envelope schema changed")
    rows_value = value.get("dataList")
    if not isinstance(rows_value, list):
        raise ThailandONEPSmartEIAError("ONEP dataList must be an array")
    counts = (value.get("totalCount"), value.get("currentPage"), value.get("totalPage"))
    if any(isinstance(item, bool) or not isinstance(item, int) for item in counts):
        raise ThailandONEPSmartEIAError("ONEP snapshot counts must be integers")
    total_count, current_page, total_page = counts
    if total_count < 0 or current_page < 1 or total_page < 1:
        raise ThailandONEPSmartEIAError("ONEP snapshot counts are invalid")
    if len(rows_value) > MAX_RECORDS or total_count > MAX_RECORDS:
        raise ThailandONEPSmartEIAError("ONEP snapshot exceeds the record cap")
    rows, exact_duplicates = _deduplicate_rows(rows_value)
    if total_count < len(rows_value):
        raise ThailandONEPSmartEIAError("ONEP totalCount is smaller than dataList")
    complete = current_page == 1 and total_page == 1 and total_count == len(rows_value)
    if require_complete and not complete:
        raise ThailandONEPSmartEIAError(
            "ONEP snapshot is paginated or truncated; no rows may be derived"
        )
    years = sorted({row["year"] for row in rows})
    gregorian_dates = sorted(approval_date_gregorian(row["approve_date"]) for row in rows)
    for row in rows:
        if approval_year_gregorian(row["year"]) != int(
            approval_date_gregorian(row["approve_date"])[:4]
        ):
            raise ThailandONEPSmartEIAError("ONEP year and approval date disagree")
    future_dated_row_count = sum(
        value > ASSESSMENT_DATE.isoformat() for value in gregorian_dates
    )
    if require_complete and future_dated_row_count:
        raise ThailandONEPSmartEIAError(
            "ONEP snapshot contains approval dates after the assessment date; "
            "no rows may be derived"
        )
    code_count = len({row["code"] for row in rows})
    return {
        "complete": complete,
        "current_page": current_page,
        "documented_project_status_field_present": bool(
            EXPECTED_ROW_KEYS & DOCUMENTED_PROJECT_STATUS_FIELDS
        ),
        "exact_duplicate_row_count": exact_duplicates,
        "future_dated_row_count_at_assessment_date": future_dated_row_count,
        "maximum_approval_date_gregorian": gregorian_dates[-1] if gregorian_dates else None,
        "minimum_approval_date_gregorian": gregorian_dates[0] if gregorian_dates else None,
        "returned_code_collision_count": len(rows) - code_count,
        "returned_code_unique_count": code_count,
        "returned_row_count": len(rows_value),
        "returned_unique_row_count": len(rows),
        "returned_year_values_buddhist": years,
        "total_count": total_count,
        "total_page": total_page,
    }


def _observation(row: Mapping[str, Any]) -> dict[str, Any]:
    source = _validate_source_row(dict(row))
    terms = matched_terms(source["name"])
    if not terms:
        raise ThailandONEPSmartEIAError("nonmatching row cannot become a lead")
    return {
        "annual_energy_consumption_mwh": None,
        "approval_date_gregorian": approval_date_gregorian(source["approve_date"]),
        "approval_date_raw": source["approve_date"],
        "approval_number": source["approve_number"],
        "category_raw": source["category"],
        "coordinates": None,
        "data_centre_type": None,
        "gross_facility_power_mw": None,
        "it_capacity_mw": None,
        "lifecycle_status": None,
        "match_fields": list(MATCH_FIELDS),
        "matched_terms": list(terms),
        "observation_id": stable_observation_id(source),
        "operator": None,
        "owner_is_operator": False,
        "owner_raw": source["owner"],
        "project_name": source["name"],
        "project_status": None,
        "province": source["province"],
        "pue": None,
        "report_family": "IEE/EIA/EHIA family; unresolved per row",
        "reporter_raw": source["reporter"],
        "source_record_id": source["code"],
        "source_tier": "C",
        "source_unit": "ONEP-approved environmental-assessment report observation",
        "source_url": PUBLIC_LIST_URL,
        "zone": source["zone"],
    }


def derive_complete_candidates(value: Any) -> list[dict[str, Any]]:
    validate_snapshot_payload(value, require_complete=True)
    rows, _ = _deduplicate_rows(value["dataList"])
    candidates = [_observation(row) for row in rows if matched_terms(row["name"])]
    if len(candidates) > MAX_CANDIDATE_UNION:
        raise ThailandONEPSmartEIAError("candidate union exceeds the review cap")
    identifiers = [row["observation_id"] for row in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ThailandONEPSmartEIAError("deterministic observation ID collision")
    return sorted(candidates, key=lambda row: (row["source_record_id"], row["observation_id"]))


def build_review_shards(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in candidates]
    if len(rows) > MAX_CANDIDATE_UNION:
        raise ThailandONEPSmartEIAError("candidate union exceeds the review cap")
    memberships: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        identifier = row.get("observation_id")
        province = row.get("province")
        approval_date = row.get("approval_date_gregorian")
        terms = row.get("matched_terms")
        if (
            not isinstance(identifier, str)
            or not isinstance(province, str)
            or not isinstance(approval_date, str)
            or not isinstance(terms, list)
            or not all(isinstance(term, str) for term in terms)
        ):
            raise ThailandONEPSmartEIAError("candidate shard fields are invalid")
        year = approval_date[:4]
        for term in terms:
            memberships.setdefault((term, year, province), []).append(identifier)
    shards: list[dict[str, Any]] = []
    for index, ((term, year, province), identifiers) in enumerate(
        sorted(memberships.items()), 1
    ):
        unique_ids = sorted(set(identifiers))
        if len(unique_ids) > MAX_REVIEW_SHARD:
            raise ThailandONEPSmartEIAError(
                "review shard exceeds cap; split contract must be extended explicitly"
            )
        shards.append(
            {
                "approval_year_gregorian": year,
                "candidate_count": len(unique_ids),
                "candidate_observation_ids": unique_ids,
                "exact_match_term": term,
                "province": province,
                "shard_id": f"onep-review-{index:04d}",
            }
        )
    return shards


RIGHTS_POLICY: dict[str, Any] = {
    "affirmative_dataset_specific_label_present": True,
    "attribution_required": True,
    "catalog_access_condition_literal": "ไม่มี",
    "catalog_data_category_literal": "ข้อมูลสาธารณะ",
    "catalog_isopen_flag": False,
    "dataset_record_reuse_label_literal": LICENCE_LABEL,
    "licence_url": None,
    "licence_version": None,
    "legal_conclusion_claimed": False,
    "linked_pdf_excel_or_document_rights_inferred": False,
    "privacy_policy_is_dataset_licence": False,
    "robots_absence_is_permission": False,
    "source_attribution": PUBLISHER,
    "verified_local_date": ASSESSMENT_DATE.isoformat(),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "reason": (
        "single resource response was paginated/truncated; no report lead was "
        "retained, and report approval is not physical lifecycle evidence"
    ),
}

PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": ASSESSMENT_DATE.isoformat(),
    "capture_completed_at": "2026-07-19T05:30:00Z",
    "controlled_http_requests": 4,
    "curl_content_decoding_enabled": True,
    "controlled_requests": [
        {
            "body_retained": False,
            "bytes": 13432,
            "canonical_sha256": "b7b571fa0a02c7bc96f29c0686c2f14f22d0e5c5a9ac4fe2f9cd49f168ca7b9d",
            "content_type": "application/json;charset=utf-8",
            "data_bearing": False,
            "http_content_encoding": None,
            "http_request_count": 1,
            "http_status": 200,
            "method": "GET",
            "raw_sha256": "d27e73ab44c877edb891a2f5a3d888e7d6967c9728c48f38bf7e379a251f7144",
            "redirect_count": 0,
            "request_id": "ckan-package-show",
            "response_date": "2026-07-19T05:29:40Z",
            "transfer_bytes": 13432,
            "url": PACKAGE_SHOW_URL,
        },
        {
            "body_retained": False,
            "bytes": 86108,
            "canonical_sha256": None,
            "content_type": "text/html; charset=UTF-8",
            "data_bearing": False,
            "http_content_encoding": "gzip",
            "http_request_count": 1,
            "http_status": 200,
            "method": "GET",
            "raw_sha256": "4cd20c37433239b665412b9b5a5170d6827479f6ef48b1231e18834c36d58030",
            "redirect_count": 0,
            "request_id": "privacy-policy",
            "response_date": "2026-07-19T05:29:41Z",
            "transfer_bytes": 15488,
            "url": PRIVACY_URL,
        },
        {
            "body_retained": False,
            "bytes": 24877,
            "canonical_sha256": None,
            "content_type": "text/html; charset=UTF-8",
            "data_bearing": False,
            "http_content_encoding": None,
            "http_request_count": 1,
            "http_status": 404,
            "method": "GET",
            "raw_sha256": "d28aad79dccd2af221a407ef60d246438e9a346240c5af8c5e99867b59c7bf9c",
            "redirect_count": 0,
            "request_id": "robots",
            "response_date": "2026-07-19T05:29:43Z",
            "transfer_bytes": 24877,
            "url": ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 60783,
            "canonical_sha256": "5926ac673c653de85fdc85cf0befdf6bc1dee358b816025c7b2fefac9c45d345",
            "content_type": "application/json; charset=UTF-8",
            "data_bearing": True,
            "http_content_encoding": None,
            "http_request_count": 1,
            "http_status": 200,
            "method": "GET",
            "raw_sha256": "775e24d2e31bb2f192129422cf1d2aac498c61cf1d3d13570ee10e418a5abe36",
            "redirect_count": 0,
            "request_id": "json-resource-snapshot",
            "response_date": "2026-07-19T05:30:00Z",
            "transfer_bytes": 60783,
            "url": RESOURCE_URL,
        },
    ],
    "detail_requests": 0,
    "document_requests": 0,
    "excel_requests": 0,
    "format": RETRIEVAL_FORMAT,
    "login_or_captcha_requests": 0,
    "maximum_body_bytes": MAX_BODY_BYTES,
    "maximum_redirects_per_request": MAX_REDIRECTS,
    "maximum_records": MAX_RECORDS,
    "package_show_requests": 1,
    "pagination_requests": 0,
    "pdf_requests": 0,
    "privacy_policy_requests": 1,
    "raw_response_bodies_retained": False,
    "release_build_http_requests": 0,
    "resource_snapshot_requests": 1,
    "robots_requests": 1,
    "timeout_seconds_per_request": REQUEST_TIMEOUT_SECONDS,
    "ui_crawl_requests": 0,
}

PINNED_SNAPSHOT_AUDIT: dict[str, Any] = {
    "format": SNAPSHOT_AUDIT_FORMAT,
    "matching_diagnostic": {
        "global_candidate_count": None,
        "global_match_scan_executed": False,
        "returned_page_diagnostic_match_count": 0,
        "returned_page_diagnostic_is_coverage_result": False,
    },
    "package": {
        "canonical_bytes": 9973,
        "canonical_sha256": "b7b571fa0a02c7bc96f29c0686c2f14f22d0e5c5a9ac4fe2f9cd49f168ca7b9d",
        "catalog_claimed_first_year_buddhist": 2535,
        "catalog_claimed_first_year_gregorian": 1992,
        "catalog_last_updated_date": "2024-07-01",
        "data_category_literal": "ข้อมูลสาธารณะ",
        "dataset_name": DATASET_NAME,
        "dataset_title": DATASET_TITLE,
        "licence_id_literal": LICENCE_LABEL,
        "licence_title_literal": LICENCE_LABEL,
        "licence_url": None,
        "licence_version": None,
        "metadata_created": "2022-06-10T02:49:03.704117",
        "metadata_modified": "2024-07-08T07:52:31.733119",
        "raw_bytes": 13432,
        "raw_sha256": "d27e73ab44c877edb891a2f5a3d888e7d6967c9728c48f38bf7e379a251f7144",
        "resource_last_updated_date": "2024-01-30",
        "resource_url": RESOURCE_URL,
        "update_frequency_literal": "1 เดือน",
    },
    "release_id": RELEASE_ID,
    "snapshot": {
        "canonical_bytes": 69264,
        "canonical_sha256": "5926ac673c653de85fdc85cf0befdf6bc1dee358b816025c7b2fefac9c45d345",
        "complete": False,
        "current_page": 1,
        "documented_project_status_field_present": False,
        "exact_duplicate_row_count": 0,
        "freshness_reliable": False,
        "future_dated_row_count_at_assessment_date": 3,
        "maximum_approval_date_gregorian": "2026-12-30",
        "minimum_approval_date_gregorian": "2026-03-02",
        "raw_bytes": 60783,
        "raw_sha256": "775e24d2e31bb2f192129422cf1d2aac498c61cf1d3d13570ee10e418a5abe36",
        "rejection_reasons": [
            "totalPage is 138 rather than 1",
            "totalCount is 13793 while dataList contains 94 rows",
            "three returned approval dates are after the assessment date",
        ],
        "returned_code_collision_count": 0,
        "returned_code_unique_count": 94,
        "returned_row_count": 94,
        "returned_rows_jsonl_bytes": 60718,
        "returned_rows_jsonl_sha256": "1d74c5661304d3a07f4197a7c3c4351dfe874b8d7d209d5db131104038b56ea4",
        "returned_unique_row_count": 94,
        "returned_year_values_buddhist": ["2569"],
        "row_keys": sorted(EXPECTED_ROW_KEYS),
        "source_report_total_count": 13793,
        "total_page": 138,
    },
}


def source_definition() -> dict[str, Any]:
    return {
        "coverage_contract": {
            "catalog_claimed_start_year_gregorian": 1992,
            "complete_for_thailand_claimed": False,
            "coverage_end_observed": None,
            "coverage_start_observed": None,
            "future_dated_approval_rows_fail_complete_derivation": True,
            "scope": "ONEP-listed approved environmental-assessment reports only",
            "source_report_total_count_observed": 13793,
            "source_snapshot_complete": False,
        },
        "deterministic_identity_contract": {
            "conflicting_duplicate_code_fails_closed": True,
            "exact_duplicate_rows_deduplicated": True,
            "namespace": str(_ONEP_NAMESPACE),
            "observation_id_method": "UUIDv5(namespace, exact source code)",
            "source_key": "code",
        },
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "approval_is_construction_or_operation": False,
            "coordinates": None,
            "data_centre_type": None,
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "lifecycle_status": None,
            "operator": None,
            "owner_field_is_operator": False,
            "project_status": None,
            "pue": None,
            "annual_energy_consumption_mwh": None,
        },
        "matching_contract": {
            "english_direct_terms": list(ENGLISH_DIRECT_TERMS),
            "generic_thai_context_terms": list(THAI_GENERIC_CONTEXT_TERMS),
            "generic_thai_term": THAI_GENERIC_TERM,
            "generic_thai_term_requires_context": True,
            "idc_is_ascii_token_bounded": True,
            "idc_term": IDC_TERM,
            "match_fields": list(MATCH_FIELDS),
            "normalization": ["Unicode NFKC", "casefold", "collapse whitespace"],
            "thai_direct_terms": list(THAI_DIRECT_TERMS),
        },
        "network_policy": {
            "detail_or_document_requests_permitted": False,
            "maximum_body_bytes": MAX_BODY_BYTES,
            "maximum_ckan_package_show_requests": 1,
            "maximum_json_resource_snapshot_requests": 1,
            "maximum_records": MAX_RECORDS,
            "maximum_redirects": MAX_REDIRECTS,
            "pagination_guessing_permitted": False,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "ui_crawling_permitted": False,
        },
        "publisher": PUBLISHER,
        "release_id": RELEASE_ID,
        "review_contract": {
            "candidate_union_cap": MAX_CANDIDATE_UNION,
            "local_shard_dimensions": [
                "exact match term",
                "approval Gregorian year",
                "province",
            ],
            "review_shard_cap": MAX_REVIEW_SHARD,
            "split_or_fail_never_truncate": True,
            "tier": "C",
        },
        "rights_policy": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_unit": "ONEP-approved IEE/EIA/EHIA-family report observation",
        "source_urls": {
            "dataset": DATASET_URL,
            "package_show": PACKAGE_SHOW_URL,
            "privacy": PRIVACY_URL,
            "public_list": PUBLIC_LIST_URL,
            "resource": RESOURCE_URL,
            "robots": ROBOTS_URL,
        },
        "title": "Thailand ONEP Smart EIA approved-report data-centre assessment",
    }


def query_plan() -> dict[str, Any]:
    return {
        "candidate_union": {
            "candidate_count": None,
            "cap": MAX_CANDIDATE_UNION,
            "status": "not_built_incomplete_resource_snapshot",
        },
        "deduplication": {
            "conflicting_duplicate_code": "fail_closed",
            "exact_duplicate_row": "deduplicate",
            "source_key": "code",
        },
        "format": QUERY_PLAN_FORMAT,
        "local_review_shards": {
            "dimensions": [
                "exact match term",
                "approval Gregorian year",
                "province",
            ],
            "network_requests": 0,
            "per_shard_cap": MAX_REVIEW_SHARD,
            "split_or_fail_never_truncate": True,
            "status": "not_built_incomplete_resource_snapshot",
        },
        "matching_contract": source_definition()["matching_contract"],
        "release_id": RELEASE_ID,
        "source_snapshot": {
            "complete": False,
            "current_page": 1,
            "pagination_requests": 0,
            "returned_row_count": 94,
            "total_count": 13793,
            "total_page": 138,
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "format": SCHEMA_FORMAT,
        "invariants": {
            "annual_energy_is_null": True,
            "approval_is_physical_lifecycle": False,
            "coordinates_are_null": True,
            "data_centre_type_is_null": True,
            "lifecycle_is_null": True,
            "operator_is_null": True,
            "owner_is_operator": False,
            "power_it_capacity_and_pue_are_null": True,
            "report_observation_is_atlas_project": False,
            "report_observation_is_atlas_site": False,
        },
        "release_id": RELEASE_ID,
        "retained_candidate_rows": 0,
        "retained_review_shards": 0,
        "retained_source_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "candidate_count": None,
            "project_count": None,
            "retained_report_observation_count": 0,
            "site_count": None,
            "source_report_total_count_observed": 13793,
        },
        "source_row_fields": sorted(EXPECTED_ROW_KEYS),
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "coverage_boundary": {
            "catalog_claimed_start_year_gregorian": 1992,
            "complete_for_thailand": False,
            "observed_complete_snapshot": False,
            "scope": "ONEP-listed approved environmental-assessment reports only",
        },
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {"role": "public report list; not crawled", "url": PUBLIC_LIST_URL},
            {"role": "official CKAN dataset landing; not requested", "url": DATASET_URL},
            {"role": "single CKAN package_show request", "url": PACKAGE_SHOW_URL},
            {"role": "single incomplete JSON resource snapshot", "url": RESOURCE_URL},
            {"role": "privacy policy inspection", "url": PRIVACY_URL},
            {"role": "robots inspection; returned HTTP 404", "url": ROBOTS_URL},
        ],
        "publisher": PUBLISHER,
        "release_id": RELEASE_ID,
        "rights_boundary": RIGHTS_POLICY,
    }


def assessment_document() -> dict[str, Any]:
    return {
        "assessed_at": PINNED_RETRIEVAL_INVENTORY["capture_completed_at"],
        "atlas_decision": {
            **DOWNSTREAM_IMPORT_POLICY,
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            "retained_source_rows": 0,
            "status": "snapshot_rejected_incomplete_page_metadata_only",
        },
        "coverage": {
            "candidate_count": None,
            "catalog_claimed_start_year_gregorian": 1992,
            "complete_for_thailand": False,
            "current_page": 1,
            "observed_coverage_end": None,
            "observed_coverage_start": None,
            "project_count": None,
            "retained_report_observation_count": 0,
            "site_count": None,
            "source_report_total_count_observed": 13793,
            "total_page": 138,
        },
        "format": RELEASE_FORMAT,
        "inference_boundary": source_definition()["inference_policy"],
        "matching_assessment": PINNED_SNAPSHOT_AUDIT["matching_diagnostic"],
        "query_plan": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval": {
            "controlled_http_requests": 4,
            "curl_content_decoding_enabled": True,
            "package_show_requests": 1,
            "pagination_requests": 0,
            "resource_snapshot_requests": 1,
            "snapshot_raw_sha256": PINNED_SNAPSHOT_AUDIT["snapshot"]["raw_sha256"],
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "snapshot_decision": {
            "complete": False,
            "freshness_reliable": False,
            "rejection_reasons": PINNED_SNAPSHOT_AUDIT["snapshot"]["rejection_reasons"],
            "returned_row_count": 94,
            "rows_released": False,
        },
        "source": {
            "dataset_title": DATASET_TITLE,
            "name": "ONEP Smart EIA Plus",
            "publisher": PUBLISHER,
            "resource_url": RESOURCE_URL,
        },
    }


def attribution_bytes() -> bytes:
    return f"""Thailand ONEP Smart EIA approved-report source assessment

Source attribution: {PUBLISHER}
Official dataset: {DATASET_URL}
Official JSON resource: {RESOURCE_URL}

The CKAN metadata carries the literal licence label "{LICENCE_LABEL}". This
assessment does not invent a licence version or URL and does not extend the
catalog label to linked PDFs, spreadsheets, reports, or other documents. The
bundle republishes no ONEP source rows or document content; it retains only
request metadata, response hashes, source counts, schema diagnostics, and the
atlas project's fail-closed assessment.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Thailand ONEP Smart EIA approved-report assessment

This frozen release records a bounded audit of ONEP's approved environmental-
assessment report dataset. Exactly one official CKAN `package_show` request,
one privacy-policy request, one robots request, and one catalog-linked JSON
resource request were made. There were no redirects. No UI pages, pagination,
detail pages, PDFs, spreadsheets, documents, login, or CAPTCHA flows were
requested.

The CKAN record identifies `{DATASET_TITLE}`, attributes it to ONEP, labels the
data public with no access condition, and carries the exact licence label
`{LICENCE_LABEL}`. No licence version or licence URL is present, so none is
asserted. The label is not extended to linked report documents. Robots returned
HTTP 404; the absence of a robots file is not treated as permission.

The JSON response was **not a complete snapshot**. It declared `totalCount=13793`,
`currentPage=1`, and `totalPage=138`, but contained only 94 rows. Three returned
approval dates converted from Buddhist Era dates fall after the assessment
date. The response therefore failed both completeness and freshness gates. The
94-row page is represented only by counts and cryptographic hashes; its rows
are not released, searched into a global result, or promoted. The diagnostic
match count on that page was zero, which is explicitly not a Thailand-wide
zero-result claim.

Audit mode may count future-dated rows without retaining them. Any structurally
complete future snapshot that contains even one approval date after the
assessment date is rejected before candidate or review-shard derivation.

The future local matching contract uses Unicode NFKC, casefolding, and collapsed
whitespace. Direct Thai terms are `{THAI_DIRECT_TERMS[0]}`,
`{THAI_DIRECT_TERMS[1]}`, `{THAI_DIRECT_TERMS[2]}`, and
`{THAI_DIRECT_TERMS[3]}`. English terms are `data center`, `data centre`,
`internet data center`, and `internet data centre`; `IDC` must be an ASCII-
token-bounded match. Generic `{THAI_GENERIC_TERM}` is accepted only with
`คอมพิวเตอร์`, `คลาวด์`, `อินเทอร์เน็ต`, or `เซิร์ฟเวอร์` in the same normalized
project name. A complete future snapshot would be deduplicated by exact source
`code`, assigned deterministic UUIDv5 observation IDs, capped at 500 candidates,
and locally sharded by exact term × Gregorian approval year × province with a
250-row cap. Oversize inputs split only under an explicit contract or fail;
they are never truncated.

Even after a complete capture, a matching row is only a Tier-C ONEP-approved
IEE/EIA/EHIA-family report observation. Report approval is not construction,
completion, commissioning, or operation. The returned schema has no documented
project-status field. Owner is not operator. Lifecycle, data-centre type,
coordinates, power, IT capacity, PUE, and annual energy remain null.

This release cannot feed the construction master, map, or current-coverage
ledger. Validate it offline with:

```bash
python3 scripts/validate_thailand_onep_smart_eia.py
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise ThailandONEPSmartEIAError("retrieval inventory differs from pinned capture")
    requests = inventory.get("controlled_requests")
    if not isinstance(requests, list) or len(requests) != 4:
        raise ThailandONEPSmartEIAError("controlled request inventory must contain four rows")
    if inventory.get("controlled_http_requests") != sum(
        row.get("http_request_count", 0) for row in requests
    ):
        raise ThailandONEPSmartEIAError("controlled request arithmetic changed")
    expected_ids = [
        "ckan-package-show",
        "privacy-policy",
        "robots",
        "json-resource-snapshot",
    ]
    expected_urls = [PACKAGE_SHOW_URL, PRIVACY_URL, ROBOTS_URL, RESOURCE_URL]
    expected_statuses = [200, 200, 404, 200]
    for index, row in enumerate(requests):
        _official_url(row.get("url"), label=f"request[{index}].url")
        _utc_timestamp(row.get("response_date"), label=f"request[{index}].response_date")
        if (
            row.get("request_id") != expected_ids[index]
            or row.get("url") != expected_urls[index]
            or row.get("http_status") != expected_statuses[index]
            or row.get("method") != "GET"
            or row.get("http_request_count") != 1
            or row.get("redirect_count") != 0
            or row.get("body_retained") is not False
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or isinstance(row.get("transfer_bytes"), bool)
            or not isinstance(row.get("transfer_bytes"), int)
            or row["transfer_bytes"] < 1
            or row.get("http_content_encoding") not in {None, "gzip"}
            or not _SHA256_RE.fullmatch(str(row.get("raw_sha256", "")))
            or (
                row.get("canonical_sha256") is not None
                and not _SHA256_RE.fullmatch(str(row["canonical_sha256"]))
            )
        ):
            raise ThailandONEPSmartEIAError(f"controlled request row invalid: {index}")
    zero_request_fields = (
        "detail_requests",
        "document_requests",
        "excel_requests",
        "login_or_captcha_requests",
        "pagination_requests",
        "pdf_requests",
        "release_build_http_requests",
        "ui_crawl_requests",
    )
    if any(inventory[field] != 0 for field in zero_request_fields):
        raise ThailandONEPSmartEIAError("forbidden request counter is nonzero")
    if (
        inventory.get("package_show_requests") != 1
        or inventory.get("resource_snapshot_requests") != 1
        or inventory.get("privacy_policy_requests") != 1
        or inventory.get("robots_requests") != 1
        or inventory.get("curl_content_decoding_enabled") is not True
        or inventory.get("raw_response_bodies_retained") is not False
    ):
        raise ThailandONEPSmartEIAError("bounded capture counters changed")


def validate_snapshot_audit(audit: Mapping[str, Any]) -> None:
    if dict(audit) != PINNED_SNAPSHOT_AUDIT:
        raise ThailandONEPSmartEIAError("snapshot audit differs from pinned evidence")
    package = audit["package"]
    snapshot = audit["snapshot"]
    for row in (package, snapshot):
        if not _SHA256_RE.fullmatch(row["raw_sha256"]):
            raise ThailandONEPSmartEIAError("raw snapshot hash is invalid")
        if not _SHA256_RE.fullmatch(row["canonical_sha256"]):
            raise ThailandONEPSmartEIAError("canonical snapshot hash is invalid")
    if (
        snapshot["complete"] is not False
        or snapshot["source_report_total_count"] != 13793
        or snapshot["returned_row_count"] != 94
        or snapshot["current_page"] != 1
        or snapshot["total_page"] != 138
        or snapshot["returned_code_collision_count"] != 0
        or snapshot["freshness_reliable"] is not False
    ):
        raise ThailandONEPSmartEIAError("snapshot completeness/count contract changed")


def audit_capture_bodies(
    package_body: bytes,
    snapshot_body: bytes,
    policy_body: bytes,
    robots_body: bytes,
) -> dict[str, Any]:
    """Validate captured bodies offline and return reproducible diagnostics.

    This function performs no network I/O. It is retained so future captures
    must pass the same raw/canonical, schema, count, freshness, and matching
    gates before any row can be derived.
    """

    package_payload = _strict_json(package_body, label="CKAN package body")
    package = _validate_package_payload(package_payload)
    snapshot_payload = _strict_json(snapshot_body, label="ONEP snapshot body")
    snapshot_summary = validate_snapshot_payload(snapshot_payload, require_complete=False)
    try:
        policy_text = policy_body.decode("utf-8")
        robots_text = robots_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ThailandONEPSmartEIAError("policy/robots evidence is not UTF-8") from error
    if "นโยบายการคุ้มครองข้อมูลส่วนบุคคล" not in policy_text:
        raise ThailandONEPSmartEIAError("ONEP privacy-policy identity changed")
    if "ไม่พบข้อมูล" not in robots_text:
        raise ThailandONEPSmartEIAError("ONEP robots 404 body identity changed")
    rows, _ = _deduplicate_rows(snapshot_payload["dataList"])
    diagnostic_matches = sum(bool(matched_terms(row["name"])) for row in rows)
    resource = package["resources"][0]
    return {
        "matching_diagnostic": {
            "global_candidate_count": (
                diagnostic_matches if snapshot_summary["complete"] else None
            ),
            "global_match_scan_executed": snapshot_summary["complete"],
            "returned_page_diagnostic_match_count": diagnostic_matches,
            "returned_page_diagnostic_is_coverage_result": False,
        },
        "package": {
            "canonical_bytes": len(canonical_json(package_payload)),
            "canonical_sha256": sha256_bytes(canonical_json(package_payload)),
            "catalog_last_updated_date": package["last_updated_date"],
            "dataset_name": package["name"],
            "licence_title_literal": package["license_title"],
            "licence_url": package.get("license_url"),
            "metadata_modified": package["metadata_modified"],
            "raw_bytes": len(package_body),
            "raw_sha256": sha256_bytes(package_body),
            "resource_last_updated_date": resource["resource_last_updated_date"],
            "resource_url": resource["url"],
        },
        "snapshot": {
            **snapshot_summary,
            "canonical_bytes": len(canonical_json(snapshot_payload)),
            "canonical_sha256": sha256_bytes(canonical_json(snapshot_payload)),
            "raw_bytes": len(snapshot_body),
            "raw_sha256": sha256_bytes(snapshot_body),
            "returned_rows_jsonl_bytes": len(jsonl(rows)),
            "returned_rows_jsonl_sha256": sha256_bytes(jsonl(rows)),
            "row_keys": sorted(EXPECTED_ROW_KEYS),
        },
    }


def derive_release_files() -> dict[str, bytes]:
    validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
    validate_snapshot_audit(PINNED_SNAPSHOT_AUDIT)
    return {
        "ATTRIBUTION.txt": attribution_bytes(),
        "README.md": readme_bytes(),
        "assessment.json": canonical_json(assessment_document()),
        "definition.json": canonical_json(source_definition()),
        "observations.jsonl": b"",
        "query-plan.json": canonical_json(query_plan()),
        "retrieval-inventory.json": canonical_json(PINNED_RETRIEVAL_INVENTORY),
        "review-shards.jsonl": b"",
        "schema.json": canonical_json(schema_document()),
        "snapshot-audit.json": canonical_json(PINNED_SNAPSHOT_AUDIT),
        "source-inventory.json": canonical_json(source_inventory_document()),
    }


def _manifest(files: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "files": {
            name: {"bytes": len(body), "sha256": sha256_bytes(body)}
            for name, body in sorted(files.items())
        },
        "format": "datacenter-atlas-manifest-v1",
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def freeze_release(root: Path) -> None:
    for entry in sorted(root.rglob("*"), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def is_frozen_release(root: Path) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    return all(
        not entry.is_symlink()
        and entry.is_file()
        and stat.S_IMODE(entry.stat().st_mode) == 0o444
        for entry in root.rglob("*")
    )


def write_release_bundle(output: Path, *, freeze: bool = True) -> Path:
    if output.exists() or output.is_symlink():
        raise ThailandONEPSmartEIAError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        files = derive_release_files()
        for name, body in files.items():
            (temporary / name).write_bytes(body)
        manifest_body = canonical_json(_manifest(files))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        if freeze:
            freeze_release(temporary)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise
    return output


def _load_canonical_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ThailandONEPSmartEIAError(f"{label} must be a regular file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThailandONEPSmartEIAError(f"invalid {label}") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ThailandONEPSmartEIAError(f"{label} must be canonical JSON")
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ThailandONEPSmartEIAError("release must be a regular directory")
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise ThailandONEPSmartEIAError("release file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in root.rglob("*")):
        raise ThailandONEPSmartEIAError("release entries must be regular files")
    if require_frozen and not is_frozen_release(root):
        raise ThailandONEPSmartEIAError("release modes are not frozen")

    derived = derive_release_files()
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise ThailandONEPSmartEIAError(f"derived file differs: {name}")
    manifest = _load_canonical_json(root / MANIFEST_FILENAME, label="manifest")
    if manifest != _manifest(derived):
        raise ThailandONEPSmartEIAError("manifest inventory differs")
    manifest_raw = (root / MANIFEST_FILENAME).read_bytes()
    sidecar = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise ThailandONEPSmartEIAError("manifest sidecar differs")

    definition = _load_canonical_json(root / "definition.json", label="definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise ThailandONEPSmartEIAError("external definition must be a regular file")
        if definition_path.read_bytes() != canonical_json(definition):
            raise ThailandONEPSmartEIAError("external definition differs")
    assessment = _load_canonical_json(root / "assessment.json", label="assessment")
    schema = _load_canonical_json(root / "schema.json", label="schema")
    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", label="retrieval inventory"
    )
    audit = _load_canonical_json(root / "snapshot-audit.json", label="snapshot audit")
    validate_retrieval_inventory(inventory)
    validate_snapshot_audit(audit)
    if (
        assessment["atlas_decision"]["status"]
        != "snapshot_rejected_incomplete_page_metadata_only"
        or assessment["atlas_decision"]["retained_source_rows"] != 0
        or schema["retained_source_rows"] != 0
        or schema["retained_candidate_rows"] != 0
        or (root / "observations.jsonl").read_bytes()
        or (root / "review-shards.jsonl").read_bytes()
    ):
        raise ThailandONEPSmartEIAError("incomplete snapshot emitted rows")
    if any(DOWNSTREAM_IMPORT_POLICY[key] for key in (
        "construction_map_import_permitted",
        "construction_master_import_permitted",
        "current_coverage_ledger_import_permitted",
    )):
        raise ThailandONEPSmartEIAError("downstream import permission changed")
    return {
        "assessment": assessment,
        "definition": definition,
        "inventory": inventory,
        "manifest": manifest,
        "schema": schema,
        "snapshot_audit": audit,
    }
