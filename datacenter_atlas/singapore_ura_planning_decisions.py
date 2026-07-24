"""Fail-closed Singapore URA Planning_Decision source assessment.

The official API documents annual and daily-delta access to planning decisions,
but access requires registration, an AccessKey, and a daily Token.  This module
records only a controlled documentation/access audit and a future retrieval
contract.  It never registers, requests credentials, sends credentials, or
retains planning-decision records or response bodies.
"""

from __future__ import annotations

from collections.abc import Mapping
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
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = (
    "singapore-ura-planning-decisions-data-centre-"
    "2001-2026-2026-07-18-v1"
)
SOURCE_ID = RELEASE_ID
RELEASE_FORMAT = "datacenter-atlas-singapore-ura-planning-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-singapore-ura-planning-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-singapore-ura-planning-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-singapore-ura-planning-audit-v1"
SCHEMA_FORMAT = "datacenter-atlas-singapore-ura-planning-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-singapore-ura-planning-source-inventory-v1"
)

ASSESSMENT_DATE = date(2026, 7, 18)
BOUNDARY_PROBE_YEAR = 2000
START_YEAR = 2001
END_YEAR = 2026
ANNUAL_YEARS = tuple(range(START_YEAR, END_YEAR + 1))

DIRECT_TERMS = (
    "data centre",
    "data center",
    "datacentre",
    "datacenter",
    "data-centre",
    "data-center",
    "data farm",
    "data-farm",
)
REVIEW_TERMS = (
    "server farm",
    "server-farm",
    "computer centre",
    "computer center",
    "server room",
    "co-location",
    "colocation",
)
FORBIDDEN_STANDALONE_TERMS = ("DC", "cloud", "data", "centre")

API_DOCS_URL = "https://eservice.ura.gov.sg/maps/api/"
REGISTRATION_URL = "https://eservice.ura.gov.sg/maps/api/reg.html"
TOKEN_ENDPOINT = (
    "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
)
PLANNING_ENDPOINT = (
    "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
    "?service=Planning_Decision"
)
PLANNING_ERROR_PROBE_URL = f"{PLANNING_ENDPOINT}&year=2025"
OPEN_DATA_LICENCE_URL = (
    "https://www.ura.gov.sg/eservices-info/maps/acceptance-grant-licence/"
)
API_TERMS_URL = (
    "https://www.ura.gov.sg/eservices-info/maps/api-terms-of-service/"
)
ROBOTS_URL = "https://eservice.ura.gov.sg/robots.txt"
DEVELOPMENT_REGISTER_URL = (
    "https://data.gov.sg/datasets/"
    "d_5fea232c6e60ea4a896e355e3c05141c/view"
)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
EXPECTED_FILES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "definition.json",
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    "observations.jsonl",
    "query-plan.json",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SingaporeURAPlanningDecisionError(ValueError):
    """Raised when the URA assessment fails its closed contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SingaporeURAPlanningDecisionError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SingaporeURAPlanningDecisionError(
            f"{field} must be RFC 3339"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SingaporeURAPlanningDecisionError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise SingaporeURAPlanningDecisionError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "data.gov.sg",
        "eservice.ura.gov.sg",
        "www.ura.gov.sg",
    }:
        raise SingaporeURAPlanningDecisionError(
            f"{field} must use an allowed official host"
        )
    return value


def annual_request_url(year: int) -> str:
    """Return one predeclared annual URL without performing a request."""

    if (
        isinstance(year, bool)
        or not isinstance(year, int)
        or year < BOUNDARY_PROBE_YEAR
        or year > END_YEAR
    ):
        raise SingaporeURAPlanningDecisionError(
            "year is outside the closed 2000-2026 plan"
        )
    return f"{PLANNING_ENDPOINT}&year={year}"


def delta_request_url(last_download_date: date) -> str:
    """Return the documented future delta URL without performing a request."""

    if not isinstance(last_download_date, date) or isinstance(
        last_download_date, datetime
    ):
        raise SingaporeURAPlanningDecisionError(
            "last download date must be a date"
        )
    return (
        f"{PLANNING_ENDPOINT}&last_dnload_date="
        f"{last_download_date.strftime('%d/%m/%Y')}"
    )


def require_success_result(
    payload: bytes | str | Mapping[str, Any],
    *,
    http_status: int = 200,
) -> list[Any]:
    """Return Result only for an HTTP-200 URA Success array envelope.

    A transport-level HTTP 200 with an application-level Error envelope is an
    error and can never be interpreted as a zero-row response.
    """

    if isinstance(http_status, bool) or not isinstance(http_status, int):
        raise SingaporeURAPlanningDecisionError("HTTP status must be an integer")
    if http_status != 200:
        raise SingaporeURAPlanningDecisionError(
            f"planning request HTTP status is not 200: {http_status}"
        )
    if isinstance(payload, Mapping):
        envelope: Any = dict(payload)
    else:
        if isinstance(payload, bytes):
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise SingaporeURAPlanningDecisionError(
                    "planning response is not UTF-8"
                ) from error
        elif isinstance(payload, str):
            text = payload
        else:
            raise SingaporeURAPlanningDecisionError(
                "planning response must be JSON bytes, text, or a mapping"
            )
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as error:
            raise SingaporeURAPlanningDecisionError(
                "planning response is not valid JSON"
            ) from error
    if not isinstance(envelope, dict):
        raise SingaporeURAPlanningDecisionError(
            "planning response must be a top-level object"
        )
    if envelope.get("Status") != "Success":
        raise SingaporeURAPlanningDecisionError(
            "planning response is an application error envelope; "
            "HTTP 200 does not mean zero rows"
        )
    result = envelope.get("Result")
    if not isinstance(result, list):
        raise SingaporeURAPlanningDecisionError(
            "successful planning response Result must be an array"
        )
    return result


RIGHTS_POLICY: dict[str, Any] = {
    "api_specific_open_data_licence_url": OPEN_DATA_LICENCE_URL,
    "api_terms_of_service_url": API_TERMS_URL,
    "api_terms_acceptance_required_at_registration": True,
    "attribution_required_for_future_authorized_use": True,
    "commercial_and_noncommercial_future_use_stated": True,
    "credential_confidentiality_controls_apply": True,
    "legal_conclusion_claimed": False,
    "licence_acceptance_required_at_registration": True,
    "licence_or_terms_body_retained": False,
    "raw_api_response_publication_asserted": False,
    "registration_page_links_both_terms": True,
    "source_record_capture_authorized_in_this_assessment": False,
    "terms_direct_get_http_status_during_audit": 403,
    "verified_local_date": ASSESSMENT_DATE.isoformat(),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "minimum_future_gate": (
        "an authorized Planning_Decision Success-array row capture must exist "
        "and each retained row must be classified and evidence-reviewed"
    ),
    "reason": (
        "credential-required metadata-only assessment with zero source rows, "
        "no physical-lifecycle evidence, and no project or site resolution"
    ),
}

PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": ASSESSMENT_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T04:19:50Z",
    "captcha_automation_requests": 0,
    "captured_success_envelopes": 0,
    "controlled_http_requests": [
        {
            "access_key_header_sent": False,
            "body_retained": False,
            "bytes": 89055,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "request_class": "documentation",
            "request_id": "api_documentation_audit",
            "server_date": "2026-07-19T04:19:46Z",
            "sha256": (
                "76b4ae10e7dc2dd6dfb5adc8371d7f9d2ed789a38708c8d36"
                "a181bbccfcbceed"
            ),
            "token_header_sent": False,
            "url": API_DOCS_URL,
        },
        {
            "access_key_header_sent": False,
            "body_retained": False,
            "bytes": 8441,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "request_class": "documentation",
            "request_id": "registration_page_audit",
            "server_date": "2026-06-30T23:50:29Z",
            "sha256": (
                "14a638e6a49c7309673535b0d314895757d645f58a167d2e67417"
                "ac6a753da60"
            ),
            "token_header_sent": False,
            "url": REGISTRATION_URL,
        },
        {
            "access_key_header_sent": False,
            "body_retained": False,
            "bytes": 919,
            "content_type": "text/html",
            "http_status": 403,
            "method": "GET",
            "request_class": "documentation",
            "request_id": "api_open_data_licence_audit",
            "server_date": "2026-07-19T04:19:48Z",
            "sha256": (
                "f79e59b0397840b82ab1c6f48eff8fcb4dd9935ea46c56af3d7"
                "efbc44cf01280"
            ),
            "token_header_sent": False,
            "url": OPEN_DATA_LICENCE_URL,
        },
        {
            "access_key_header_sent": False,
            "body_retained": False,
            "bytes": 919,
            "content_type": "text/html",
            "http_status": 403,
            "method": "GET",
            "request_class": "documentation",
            "request_id": "api_terms_of_service_audit",
            "server_date": "2026-07-19T04:19:48Z",
            "sha256": (
                "ee8b2ff54068bb33faab19c1493358fbe6ed7e9174bf2bb991442"
                "bdae8db5df4"
            ),
            "token_header_sent": False,
            "url": API_TERMS_URL,
        },
        {
            "access_key_header_sent": False,
            "body_retained": False,
            "bytes": 67,
            "content_type": "text/plain",
            "http_status": 200,
            "method": "GET",
            "request_class": "documentation",
            "request_id": "eservice_robots_audit",
            "server_date": "2026-07-19T04:19:49Z",
            "sha256": (
                "a56a687fa67a1f07ebc4d9d84172c358629ae296b6e08a89cd16"
                "feee55fc39cb"
            ),
            "token_header_sent": False,
            "url": ROBOTS_URL,
        },
        {
            "access_key_header_sent": False,
            "application_message": "Invalid Access Key",
            "application_status": "Error",
            "body_retained": False,
            "bytes": 61,
            "content_type": "application/json",
            "http_status": 200,
            "method": "GET",
            "request_class": "unauthenticated_error_probe",
            "request_id": "token_endpoint_no_access_key_probe",
            "result_is_array": False,
            "result_json_type": "string",
            "server_date": "2026-07-19T04:19:49Z",
            "sha256": (
                "3581ea5a3af2812d4e1d625cadd4d184f8e44fcb96fa9ed25fe9"
                "932818992b8d"
            ),
            "token_header_sent": False,
            "url": TOKEN_ENDPOINT,
        },
        {
            "access_key_header_sent": False,
            "application_message": "Invalid input.",
            "application_status": "Error",
            "body_retained": False,
            "bytes": 59,
            "content_type": "application/json",
            "http_status": 200,
            "method": "GET",
            "request_class": "unauthenticated_error_probe",
            "request_id": "planning_year_no_headers_probe",
            "result_is_array": False,
            "result_json_type": "string",
            "server_date": "2026-07-19T04:19:50Z",
            "sha256": (
                "f23c76f0434c3845d28084985d2d79410bb987071d78441a89e65"
                "0a31f61e982"
            ),
            "token_header_sent": False,
            "url": PLANNING_ERROR_PROBE_URL,
        },
    ],
    "credentialed_requests": 0,
    "documentation_requests": 5,
    "format": RETRIEVAL_FORMAT,
    "http_200_error_envelope_means_zero": False,
    "network_requests": 7,
    "planning_capture_started": False,
    "planning_error_probe_requests": 1,
    "raw_response_bodies_retained": False,
    "registration_submissions": 0,
    "release_id": RELEASE_ID,
    "result_bearing_requests": 0,
    "retained_source_rows": 0,
    "token_error_probe_requests": 1,
    "unauthenticated_error_probe_requests": 2,
}


def _null_counts() -> dict[str, None]:
    return {
        "classification_direct_count": None,
        "classification_excluded_count": None,
        "classification_review_count": None,
        "decision_count": None,
        "license_or_permit_count": None,
        "metric_statement_count": None,
        "project_count": None,
        "result_count": None,
        "search_count": None,
        "site_count": None,
    }


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "access_key_present_during_assessment": False,
            "access_key_required": True,
            "authorized_row_capture_exists": False,
            "captcha_automation_performed": False,
            "daily_token_present_during_assessment": False,
            "daily_token_required": True,
            "planning_capture_started": False,
            "registration_performed": False,
            "registration_required": True,
            "registration_submission_contains_personal_or_company_fields": True,
        },
        "application_success_contract": {
            "http_status_required": 200,
            "result_json_type_required": "array",
            "status_exact_value_required": "Success",
            "transport_success_alone_is_sufficient": False,
            "zero_count_permitted_only_after_valid_success_array": True,
        },
        "classification_contract": {
            "case_matching": "Unicode casefolded phrase matching",
            "direct_terms": list(DIRECT_TERMS),
            "forbidden_standalone_terms": list(FORBIDDEN_STANDALONE_TERMS),
            "review_terms": list(REVIEW_TERMS),
            "review_terms_are_direct_matches": False,
            "vocabulary_is_predeclared_before_capture": True,
        },
        "coverage_contract": {
            "annual_backfill_years": list(ANNUAL_YEARS),
            "boundary_probe_year": BOUNDARY_PROBE_YEAR,
            "complete_for_singapore_claimed": False,
            "daily_delta_after_authorized_backfill": True,
            "documented_records_after_year": 2000,
            "end_year": END_YEAR,
            "start_year": START_YEAR,
            **_null_counts(),
        },
        "development_register_boundary": {
            "development_register_url": DEVELOPMENT_REGISTER_URL,
            "exact_join_key_documented": False,
            "joined_to_planning_decisions": False,
            "polygon_source_is_separate": True,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "coordinates": None,
            "data_centre_capacity": None,
            "data_centre_type": None,
            "facility_operator": None,
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "physical_lifecycle_status": None,
            "planning_decision_status_is_physical_lifecycle": False,
        },
        "publisher": "Urban Redevelopment Authority of Singapore (URA)",
        "release_id": RELEASE_ID,
        "retention": {
            "access_key_or_token_retained": False,
            "planning_decision_rows_retained": False,
            "raw_response_bodies_retained": False,
            "registration_fields_retained": False,
            "result_text_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_urls": {
            "api_documentation": API_DOCS_URL,
            "api_open_data_licence": OPEN_DATA_LICENCE_URL,
            "api_terms_of_service": API_TERMS_URL,
            "development_register_separate_unjoined": DEVELOPMENT_REGISTER_URL,
            "planning_decision_api": PLANNING_ENDPOINT,
            "registration": REGISTRATION_URL,
            "robots": ROBOTS_URL,
            "token_api": TOKEN_ENDPOINT,
        },
        "title": "Singapore URA Planning_Decision access assessment",
        "unit_contract": {
            "automatic_merge_by_address_or_lot_permitted": False,
            "deduplication_key": "exact dr_id",
            "development_register_polygon_is_same_unit": False,
            "one_retained_row_per_dr_id": True,
            "planning_decision_is_atlas_project": False,
            "planning_decision_is_atlas_site": False,
            "planning_decision_record_unit": "URA planning decision record",
            "project_count": None,
            "site_count": None,
        },
    }


def query_plan() -> dict[str, Any]:
    annual_rows: list[dict[str, Any]] = []
    for year in ANNUAL_YEARS:
        annual_rows.append(
            {
                "counts": _null_counts(),
                "network_requests": 0,
                "query_id": f"annual-{year}",
                "request_headers_required": ["AccessKey", "Token"],
                "request_url": annual_request_url(year),
                "status": "not_executed_no_authorized_credentials",
                "year": year,
            }
        )
    return {
        "annual_backfill": {
            "rows": annual_rows,
            "year_count": len(ANNUAL_YEARS),
            "year_end": END_YEAR,
            "year_start": START_YEAR,
        },
        "application_success_contract": source_definition()[
            "application_success_contract"
        ],
        "boundary_probe": {
            "counts": _null_counts(),
            "network_requests": 0,
            "query_id": "boundary-year-2000-preflight",
            "reason": (
                "documentation says only records after 2000 can be retrieved; "
                "probe before deciding whether 2000 belongs in the backfill"
            ),
            "request_headers_required": ["AccessKey", "Token"],
            "request_url": annual_request_url(BOUNDARY_PROBE_YEAR),
            "status": "not_executed_no_authorized_credentials",
            "year": BOUNDARY_PROBE_YEAR,
        },
        "classification_contract": source_definition()[
            "classification_contract"
        ],
        "daily_delta_contract": {
            "activation": (
                "only after an authorized annual capture and a valid daily token"
            ),
            "counts": _null_counts(),
            "date_format": "dd/mm/yyyy",
            "maximum_lookback": "one year",
            "network_requests": 0,
            "parameter": "last_dnload_date",
            "request_headers_required": ["AccessKey", "Token"],
            "request_url_template": (
                f"{PLANNING_ENDPOINT}&last_dnload_date={{dd/mm/yyyy}}"
            ),
            "status": "not_started_no_authorized_capture",
            "tombstone_contract": {
                "delete_ind_exact_value": "Yes",
                "deleted_record_is_retained_as_active_decision": False,
                "key": "exact dr_id",
                "meaning": "remove or tombstone the exact dr_id state",
            },
            "update_frequency": "daily",
            "year_and_last_dnload_date_may_be_combined": False,
        },
        "deduplication_if_executed": "one row per exact dr_id",
        "endpoint": PLANNING_ENDPOINT,
        "format": QUERY_PLAN_FORMAT,
        "http_method": "GET",
        "release_id": RELEASE_ID,
        "union": {
            "all_rows_classified": False,
            "closed_union_sha256": None,
            "counts": _null_counts(),
            "retained_source_rows": 0,
            "status": "not_built_no_authorized_capture",
        },
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "api_documentation_findings": {
            "annual_parameter": "year",
            "annual_year_boundary_text": "Only records after year 2000",
            "daily_delta_parameter": "last_dnload_date",
            "daily_delta_lookback_limit": "one year",
            "daily_delta_update_frequency": "Daily",
            "delete_ind_yes_only_documented_for_delta": True,
            "required_headers": ["AccessKey", "Token"],
            "year_and_delta_are_mutually_exclusive": True,
        },
        "development_register": {
            "join_performed": False,
            "planning_api_dr_id_join_documented": False,
            "role": "separate unjoined polygon source",
            "url": DEVELOPMENT_REGISTER_URL,
        },
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {"role": "API documentation", "url": API_DOCS_URL},
            {"role": "AccessKey registration", "url": REGISTRATION_URL},
            {"role": "daily token endpoint", "url": TOKEN_ENDPOINT},
            {"role": "Planning_Decision endpoint", "url": PLANNING_ENDPOINT},
            {
                "role": "API-specific Open Data Licence",
                "url": OPEN_DATA_LICENCE_URL,
            },
            {"role": "API terms of service", "url": API_TERMS_URL},
            {"role": "API host robots policy", "url": ROBOTS_URL},
        ],
        "release_id": RELEASE_ID,
        "robots_findings": {
            "generic_user_agent_group_present": False,
            "googlebot_disallow_value": "",
            "http_status": 200,
            "robots_is_access_or_reuse_permission": False,
            "searchsg_disallow_value": "",
        },
        "rights_access_findings": {
            "licence_direct_get_http_status": 403,
            "registration_links_api_terms": True,
            "registration_links_open_data_licence": True,
            "terms_direct_get_http_status": 403,
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "documented_response_fields": [
            {"name": "dr_id", "role": "unique record key"},
            {"name": "submission_no", "role": "submission number"},
            {"name": "decision_no", "role": "decision number"},
            {"name": "decision_date", "role": "dd/mm/yyyy decision date"},
            {"name": "decision_type", "role": "regulatory decision type"},
            {"name": "submission_desc", "role": "proposal description"},
            {"name": "address", "role": "site address text"},
            {"name": "mkts_lotno", "role": "MK/TS lot number text"},
            {"name": "delete_ind", "role": "daily-delta deletion flag"},
            {
                "name": "appl_type",
                "nullable": True,
                "role": "example payload field not listed in response table",
            },
        ],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "decision_type": None,
            "planning_decision_is_physical_lifecycle": False,
            "physical_construction_status": None,
            "physical_operation_status": None,
            "regulatory_status": None,
        },
        "metric_contract": {
            "annual_energy_consumption_mwh": None,
            "backup_generation_capacity_mw": None,
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "metric_scope": None,
            "pue": None,
            "retained_metric_rows": 0,
            "source_metric_statement_count": None,
        },
        "release_id": RELEASE_ID,
        "retained_planning_decision_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": _null_counts(),
        "unit_contract": source_definition()["unit_contract"],
    }


def assessment_document(inventory: Mapping[str, Any]) -> dict[str, Any]:
    validate_retrieval_inventory(inventory)
    return {
        "access_boundary": source_definition()["access"],
        "assessed_at": inventory["audit_completed_at"],
        "assessment_id": RELEASE_ID,
        "atlas_decision": {
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            **DOWNSTREAM_IMPORT_POLICY,
            "retained_source_rows": 0,
            "status": "credential_required_metadata_only",
        },
        "coverage": {
            "annual_queries_completed": 0,
            "annual_queries_planned": len(ANNUAL_YEARS),
            "boundary_probe_completed": False,
            "complete_for_singapore": False,
            "daily_delta_started": False,
            "source_union_sha256": None,
            **_null_counts(),
        },
        "development_register_boundary": source_definition()[
            "development_register_boundary"
        ],
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": schema_document()["lifecycle_contract"],
        "metric_boundary": schema_document()["metric_contract"],
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "audit_metadata_sha256": sha256_bytes(canonical_json(inventory)),
            "captured_success_envelopes": 0,
            "controlled_audit_requests": inventory["network_requests"],
            "credentialed_requests": 0,
            "raw_source_bodies_retained": False,
            "result_bearing_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "URA Planning_Decision",
            "operator": "Urban Redevelopment Authority of Singapore",
            "service_url": PLANNING_ENDPOINT,
        },
        "unit_boundary": source_definition()["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""Singapore URA Planning_Decision access assessment

Official API documentation: {API_DOCS_URL}
Registration: {REGISTRATION_URL}
API-specific Open Data Licence: {OPEN_DATA_LICENCE_URL}
API terms of service: {API_TERMS_URL}

This bundle republishes no URA planning-decision records, descriptions,
addresses, lot numbers, credentials, tokens, registration details, or raw
response bodies. It contains only this project's audit metadata and hashes,
null findings, documented schema, and an unexecuted retrieval plan. Attribution
under the API-specific Open Data Licence is required for any later authorized
use of URA source data; no such source-data use occurs in this bundle.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Singapore URA Planning_Decision source assessment

URA documents `Planning_Decision` at {API_DOCS_URL}. Access requires a
registered AccessKey and a token generated for that day's API access. This
assessment did not register, solve or automate a CAPTCHA, request credentials,
send credentials, or capture a planning-decision result.

The seven-request controlled audit covered the API documentation, registration,
API-specific Open Data Licence, API terms, robots policy, and exact no-header
token and planning probes. The two probes returned HTTP 200 application error
envelopes: `Invalid Access Key` and `Invalid input.` Their `Result` values were
strings, not arrays. HTTP 200 can never mean zero records unless `Status` is
exactly `Success` and `Result` is an array. Only request metadata and body hashes
are retained.

The closed future plan first probes year 2000 because the documentation says
only records after 2000 are retrievable. It then requests each year 2001-2026.
After an authorized backfill, a daily `last_dnload_date=dd/mm/yyyy` delta may be
run with no more than a one-year lookback. `year` and `last_dnload_date` cannot
be combined. A delta row with `delete_ind == Yes` tombstones the exact `dr_id`.
Rows are never merged by address or lot; the unit is one row per exact `dr_id`.

Every result, decision, search, permit, project, site, classification, and
metric count remains null. Retained source rows are zero. A Written Permission
or other planning decision is regulatory status, not evidence of construction
or operation. No coordinates, facility operator, data-centre type, power, PUE,
or energy value is inferred. The Development Register polygon dataset remains a
separate unjoined source. This assessment cannot feed the construction master,
map, or current-coverage ledger until an authorized row capture exists and is
reviewed.

Validate the frozen `0555`/`0444` bundle entirely offline:

```bash
python3 scripts/validate_singapore_ura_planning_decisions.py
```

Reproduce all derived files from pinned audit metadata without network access:

```bash
python3 scripts/build_singapore_ura_planning_decisions.py --output /tmp/ura-planning-release
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise SingaporeURAPlanningDecisionError(
            "retrieval inventory differs from pinned audit"
        )
    _utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 7:
        raise SingaporeURAPlanningDecisionError(
            "controlled audit must contain seven requests"
        )
    if inventory.get("network_requests") != len(requests):
        raise SingaporeURAPlanningDecisionError(
            "controlled network request arithmetic differs"
        )
    if inventory.get("documentation_requests") != 5:
        raise SingaporeURAPlanningDecisionError(
            "documentation request count differs"
        )
    if inventory.get("unauthenticated_error_probe_requests") != 2:
        raise SingaporeURAPlanningDecisionError(
            "unauthenticated error probe count differs"
        )
    zero_fields = (
        "captcha_automation_requests",
        "captured_success_envelopes",
        "credentialed_requests",
        "registration_submissions",
        "result_bearing_requests",
        "retained_source_rows",
    )
    if any(inventory.get(field) != 0 for field in zero_fields):
        raise SingaporeURAPlanningDecisionError(
            "fail-closed audit counter differs"
        )
    if inventory.get("planning_capture_started") is not False:
        raise SingaporeURAPlanningDecisionError(
            "planning capture must remain unstarted"
        )
    if inventory.get("raw_response_bodies_retained") is not False:
        raise SingaporeURAPlanningDecisionError(
            "raw response bodies cannot be retained"
        )
    if inventory.get("http_200_error_envelope_means_zero") is not False:
        raise SingaporeURAPlanningDecisionError(
            "HTTP 200 error envelopes cannot mean zero"
        )

    expected_ids = [
        "api_documentation_audit",
        "registration_page_audit",
        "api_open_data_licence_audit",
        "api_terms_of_service_audit",
        "eservice_robots_audit",
        "token_endpoint_no_access_key_probe",
        "planning_year_no_headers_probe",
    ]
    expected_urls = [
        API_DOCS_URL,
        REGISTRATION_URL,
        OPEN_DATA_LICENCE_URL,
        API_TERMS_URL,
        ROBOTS_URL,
        TOKEN_ENDPOINT,
        PLANNING_ERROR_PROBE_URL,
    ]
    if [row.get("request_id") for row in requests] != expected_ids:
        raise SingaporeURAPlanningDecisionError("controlled request IDs differ")
    if [row.get("url") for row in requests] != expected_urls:
        raise SingaporeURAPlanningDecisionError("controlled request URLs differ")
    if [row.get("http_status") for row in requests] != [
        200,
        200,
        403,
        403,
        200,
        200,
        200,
    ]:
        raise SingaporeURAPlanningDecisionError(
            "controlled request statuses differ"
        )

    for index, row in enumerate(requests):
        _official_url(row.get("url"), f"request[{index}].url")
        _utc_timestamp(row.get("server_date"), f"request[{index}].server_date")
        if (
            row.get("method") != "GET"
            or row.get("body_retained") is not False
            or row.get("access_key_header_sent") is not False
            or row.get("token_header_sent") is not False
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or not isinstance(row.get("http_status"), int)
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise SingaporeURAPlanningDecisionError(
                f"controlled request row {index} is invalid"
            )
    if [row["request_class"] for row in requests].count("documentation") != 5:
        raise SingaporeURAPlanningDecisionError(
            "documentation request classification differs"
        )
    probes = requests[-2:]
    if (
        probes[0].get("application_status") != "Error"
        or probes[0].get("application_message") != "Invalid Access Key"
        or probes[1].get("application_status") != "Error"
        or probes[1].get("application_message") != "Invalid input."
        or any(row.get("result_json_type") != "string" for row in probes)
        or any(row.get("result_is_array") is not False for row in probes)
    ):
        raise SingaporeURAPlanningDecisionError(
            "unauthenticated application error metadata differs"
        )


def derive_release_files(inventory: Mapping[str, Any]) -> dict[str, bytes]:
    validate_retrieval_inventory(inventory)
    return {
        "ATTRIBUTION.txt": attribution_bytes(),
        "README.md": readme_bytes(),
        "assessment.json": canonical_json(assessment_document(inventory)),
        "definition.json": canonical_json(source_definition()),
        "observations.jsonl": b"",
        "query-plan.json": canonical_json(query_plan()),
        "retrieval-inventory.json": canonical_json(inventory),
        "schema.json": canonical_json(schema_document()),
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


def _freeze_tree(root: Path) -> None:
    for entry in sorted(root.rglob("*"), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def is_frozen_release(root: Path) -> bool:
    if root.is_symlink() or not root.is_dir():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    return all(
        not entry.is_symlink()
        and entry.is_file()
        and stat.S_IMODE(entry.stat().st_mode) == 0o444
        for entry in root.iterdir()
    )


def write_release_bundle(inventory: Mapping[str, Any], output: Path) -> None:
    """Write one new frozen bundle atomically from pinned metadata."""

    if output.exists() or output.is_symlink():
        raise SingaporeURAPlanningDecisionError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise SingaporeURAPlanningDecisionError(
            "output parent must be a regular directory"
        )
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent))
    )
    try:
        files = derive_release_files(inventory)
        for name, body in files.items():
            (temporary / name).write_bytes(body)
        manifest_body = canonical_json(_manifest(files))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        _freeze_tree(temporary)
        if output.exists() or output.is_symlink():
            raise SingaporeURAPlanningDecisionError(
                "output appeared during atomic build"
            )
        os.replace(temporary, output)
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SingaporeURAPlanningDecisionError(
            f"{label} must be a regular file"
        )
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SingaporeURAPlanningDecisionError(f"invalid {label}") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise SingaporeURAPlanningDecisionError(
            f"{label} must contain canonical JSON"
        )
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SingaporeURAPlanningDecisionError(
            "release must be a regular directory"
        )
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != EXPECTED_FILES:
        raise SingaporeURAPlanningDecisionError("release file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SingaporeURAPlanningDecisionError(
            "release entries must be regular files without symlinks"
        )
    if not is_frozen_release(root):
        raise SingaporeURAPlanningDecisionError(
            "release modes are not frozen"
        )

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise SingaporeURAPlanningDecisionError(
                f"derived file differs: {name}"
            )

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise SingaporeURAPlanningDecisionError("manifest inventory differs")
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    sidecar_path = root / MANIFEST_HASH_FILENAME
    if sidecar_path.read_text(encoding="utf-8") != sidecar:
        raise SingaporeURAPlanningDecisionError("manifest sidecar differs")

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        external = _load_canonical_json(definition_path, "external definition")
        if external != definition or definition_path.read_bytes() != canonical_json(
            definition
        ):
            raise SingaporeURAPlanningDecisionError(
                "external definition differs"
            )

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    if assessment["atlas_decision"]["status"] != "credential_required_metadata_only":
        raise SingaporeURAPlanningDecisionError("assessment decision differs")
    for field in _null_counts():
        if assessment["coverage"][field] is not None:
            raise SingaporeURAPlanningDecisionError(
                f"unexecuted coverage count must be null: {field}"
            )
    if (
        assessment["atlas_decision"]["retained_source_rows"] != 0
        or schema["retained_planning_decision_rows"] != 0
        or schema["classification_rows"] != []
        or (root / "observations.jsonl").read_bytes()
    ):
        raise SingaporeURAPlanningDecisionError(
            "metadata-only assessment cannot emit source rows"
        )
    annual_rows = plan["annual_backfill"]["rows"]
    if (
        len(annual_rows) != len(ANNUAL_YEARS)
        or any(row["network_requests"] != 0 for row in annual_rows)
        or plan["boundary_probe"]["network_requests"] != 0
        or plan["daily_delta_contract"]["network_requests"] != 0
    ):
        raise SingaporeURAPlanningDecisionError(
            "future query plan must remain unexecuted"
        )
    return {
        "assessment": assessment,
        "definition": definition,
        "inventory": inventory,
        "manifest": manifest,
        "query_plan": plan,
        "schema": schema,
        "source_inventory": _load_canonical_json(
            root / "source-inventory.json", "source inventory"
        ),
    }
