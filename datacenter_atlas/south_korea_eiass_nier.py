"""Fail-closed South Korea EIASS/NIER EIA project-source assessment.

Current NIER project-list APIs are documented by the Korean Public Data
Portal and carry attribution licences, but invocation requires a service key.
The documentation does not define stable ordering, snapshot semantics, page
size limits, or exact matching for the project-name search parameter.  The API
host's robots endpoint also returned HTTP 500 in the controlled audit.

This module therefore reproduces a frozen zero-row assessment.  It never calls
an API operation or EIASS search, and it does not infer physical construction,
data-centre type, capacity, PUE, or energy use from an administrative EIA
record.
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
RELEASE_ID = "south-korea-eiass-nier-eia-project-search-2026-07-19-v1"
RELEASE_FORMAT = "datacenter-atlas-south-korea-eiass-nier-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-south-korea-eiass-nier-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-south-korea-eiass-nier-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-south-korea-eiass-nier-audit-v1"
SCHEMA_FORMAT = "datacenter-atlas-south-korea-eiass-nier-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-south-korea-eiass-nier-source-inventory-v1"
)

ASSESSMENT_LOCAL_DATE = date(2026, 7, 19)
SEARCH_TERMS = ("데이터센터", "데이터 센터")
CONDITIONAL_ENGLISH_TERMS = ("data center", "data centre")
MIN_REQUEST_INTERVAL_SECONDS = 3.0
AUDIT_REQUEST_START_INTERVAL_SECONDS = 3.2
MAX_DIRECT_REQUEST_ATTEMPTS = 40

DATA_GO_ROBOTS_URL = "https://www.data.go.kr/robots.txt"
DATA_GO_API_ROBOTS_URL = "https://apis.data.go.kr/robots.txt"
MIGRATION_NOTICE_URL = (
    "https://www.data.go.kr/bbs/ntc/selectNotice.do?"
    "originId=NOTICE_0000000004067"
)
DATA_GO_POLICY_URL = "https://www.data.go.kr/ugs/selectPortalPolicyView.do"
EIA_API_METADATA_URL = "https://www.data.go.kr/data/15142987/openapi.do"
PRE_STRATEGY_SMALL_API_METADATA_URL = (
    "https://www.data.go.kr/data/15142990/openapi.do"
)
BUSINESS_AREA_API_METADATA_URL = (
    "https://www.data.go.kr/data/15142907/openapi.do"
)
EIASS_ROBOTS_URL = "https://www.eiass.go.kr/robots.txt"
EIASS_CANONICAL_ROBOTS_URL = "https://eiasas.eiass.go.kr/robots.txt"
KOGL_ROBOTS_URL = "https://www.kogl.or.kr/robots.txt"

EIA_API_BASE_URL = (
    "https://apis.data.go.kr/1480523/"
    "EnvrnAffcEvlDscssSttusInfoInqireService"
)
EIA_LIST_PATH = "/getDscssBsnsListInfoInqire"
PRE_STRATEGY_SMALL_API_BASE_URL = (
    "https://apis.data.go.kr/1480523/"
    "BeffatStrtgySmallScaleDscssSttusInfoInqireService"
)
PRE_STRATEGY_SMALL_LIST_PATH = (
    "/getBsnsStrtgySmallScaleDscssListInfoInqire"
)
BUSINESS_AREA_API_BASE_URL = (
    "https://apis.data.go.kr/1480523/BsnsAreaService"
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
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class SouthKoreaEIASSNIERAssessmentError(ValueError):
    """Raised when the South Korea assessment violates its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{field} must be an RFC 3339 UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{field} must be an RFC 3339 UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC)


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise SouthKoreaEIASSNIERAssessmentError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "apis.data.go.kr",
        "eiasas.eiass.go.kr",
        "www.data.go.kr",
        "www.eiass.go.kr",
        "www.kogl.or.kr",
    }:
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{field} must use an allowed official host"
        )
    return value


RIGHTS_POLICY: dict[str, Any] = {
    "api_metadata_affirms_attribution_reuse_scope": True,
    "api_metadata_marks_third_party_rights_included": True,
    "api_metadata_publication_permitted": True,
    "api_result_or_derived_row_publication_permitted_if_conditions_met": True,
    "data_go_policy_type_one_allows_commercial_and_noncommercial_use": True,
    "data_go_policy_type_one_allows_derivative_works": True,
    "data_go_policy_type_one_requires_attribution": True,
    "eiass_direct_rights_page_request_made": False,
    "eiass_footer_all_rights_reserved": True,
    "eiass_official_rights_pages_observed_via_browser_proxy": True,
    "eiass_terms_restrict_unapproved_reproduction_distribution_alteration_or_commercial_use": True,
    "eiass_unmarked_material_requires_prior_consultation": True,
    "eiass_web_result_reuse_scope_affirmed": False,
    "legal_conclusion_claimed": False,
    "raw_audit_response_redistribution_permitted": False,
    "robots_rule_is_reuse_permission": False,
    "verified_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "reason": (
        "The two NIER list-API metadata pages mark the resources as including "
        "third-party rights under an attribution condition and as Public "
        "Works Type 1. The directly audited Data Portal policy defines Type 1 "
        "as attribution-required use that permits commercial, noncommercial, "
        "and derivative use. This affirmative API scope does not automatically "
        "apply to EIASS web-search pages or attached assessment documents. "
        "Browser-proxy review of the official EIASS copyright policy and terms "
        "found an All Rights Reserved footer, free-reuse language limited to "
        "KOGL-marked works, prior-consultation language for unmarked material, "
        "and restrictions on unapproved reproduction, distribution, alteration, "
        "sale, or commercial use. Those EIASS pages were not directly requested "
        "after the robots origins failed."
    ),
}


DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "reason": (
        "zero-row source assessment with no API invocation, no project/site "
        "resolution, and no physical-construction or operating evidence"
    ),
}


PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "analysis_temporary_response_bodies_deleted": True,
    "assessment_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T09:16:49Z",
    "audit_request_start_interval_seconds": (
        AUDIT_REQUEST_START_INTERVAL_SECONDS
    ),
    "browser_proxy_origin_request_count": None,
    "browser_proxy_research_excluded_from_direct_request_arithmetic": True,
    "browser_proxy_research_used": True,
    "completed_response_requests": 7,
    "controlled_http_requests": [
        {
            "body_retained": False,
            "bytes": 286,
            "content_type": "text/plain; charset=UTF-8",
            "elapsed_seconds": 0.708,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_robots",
            "response_body_received": True,
            "sha256": (
                "91cd7b24dcd33000f491982e4c281ca5"
                "44915c8e55a9fc40904cf6148ef1ad04"
            ),
            "started_at": "2026-07-19T09:12:40.185Z",
            "url": DATA_GO_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": 0.983,
            "error_class": "URLError",
            "error_detail_category": "unclassified_network_error",
            "http_status": None,
            "location": None,
            "method": "GET",
            "outcome": "network_error",
            "redirect_followed": False,
            "request_id": "eiass_robots",
            "response_body_received": False,
            "sha256": _EMPTY_SHA256,
            "started_at": "2026-07-19T09:12:43.386Z",
            "url": EIASS_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": 1.341,
            "error_class": "URLError",
            "error_detail_category": "tls_handshake_failure",
            "http_status": None,
            "location": None,
            "method": "GET",
            "outcome": "network_error",
            "redirect_followed": False,
            "request_id": "eiass_canonical_robots",
            "response_body_received": False,
            "sha256": _EMPTY_SHA256,
            "started_at": "2026-07-19T09:13:45.645Z",
            "url": EIASS_CANONICAL_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 103582,
            "content_type": "text/html;charset=UTF-8",
            "elapsed_seconds": 1.347,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_migration_notice",
            "response_body_received": True,
            "sha256": (
                "a7294063b72462da7e1692991f86506b"
                "fa4a6d3ed0cd64af9342314c6aa2a058"
            ),
            "started_at": "2026-07-19T09:13:51.269Z",
            "url": MIGRATION_NOTICE_URL,
        },
        {
            "body_retained": False,
            "bytes": 191266,
            "content_type": "text/html;charset=UTF-8",
            "elapsed_seconds": 2.195,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_eia_discussion_api_metadata",
            "response_body_received": True,
            "sha256": (
                "38fd07c220cdab45259338213900779f5"
                "29466a789a655ca51c10ecca75c5c5a"
            ),
            "started_at": "2026-07-19T09:13:54.470Z",
            "url": EIA_API_METADATA_URL,
        },
        {
            "body_retained": False,
            "bytes": 184092,
            "content_type": "text/html;charset=UTF-8",
            "elapsed_seconds": 2.195,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_pre_strategy_small_api_metadata",
            "response_body_received": True,
            "sha256": (
                "51f53a96220fd402b63533cabdc4b751"
                "367176b9b1b3ca64d63ed41a4bec5670"
            ),
            "started_at": "2026-07-19T09:13:57.675Z",
            "url": PRE_STRATEGY_SMALL_API_METADATA_URL,
        },
        {
            "body_retained": False,
            "bytes": 180215,
            "content_type": "text/html;charset=UTF-8",
            "elapsed_seconds": 2.161,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_business_area_api_metadata",
            "response_body_received": True,
            "sha256": (
                "020385ff91c6307503efd443337f473d"
                "3f38e5e6fd1bc9ead98126d2429732e1"
            ),
            "started_at": "2026-07-19T09:14:00.880Z",
            "url": BUSINESS_AREA_API_METADATA_URL,
        },
        {
            "body_retained": False,
            "bytes": 18,
            "content_type": "text/plain; charset=utf-8",
            "elapsed_seconds": 5.148,
            "http_status": 500,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_api_robots",
            "response_body_received": True,
            "sha256": (
                "a4ee54ef165943917e45affee4a3b475"
                "e713db508001e4f300630a8bbf79c13d"
            ),
            "started_at": "2026-07-19T09:15:33.088Z",
            "url": DATA_GO_API_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": 20.524,
            "error_class": "URLError",
            "error_detail_category": "timeout",
            "http_status": None,
            "location": None,
            "method": "GET",
            "outcome": "network_error",
            "redirect_followed": False,
            "request_id": "kogl_robots",
            "response_body_received": False,
            "sha256": _EMPTY_SHA256,
            "started_at": "2026-07-19T09:16:21.429Z",
            "url": KOGL_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 174624,
            "content_type": "text/html;charset=UTF-8",
            "elapsed_seconds": 1.734,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "data_go_portal_policy",
            "response_body_received": True,
            "sha256": (
                "e5070bc824f080a71e0069b310d66c84"
                "c7b047cb33bf28a2d7857d3f5583b3eb"
            ),
            "started_at": "2026-07-19T09:16:46.704Z",
            "url": DATA_GO_POLICY_URL,
        },
    ],
    "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
    "direct_request_attempts": 10,
    "documentation_requests": 5,
    "failed_network_requests": 3,
    "format": RETRIEVAL_FORMAT,
    "http_error_responses": 1,
    "raw_response_bodies_retained": False,
    "result_bearing_api_requests": 0,
    "result_bearing_search_requests": 0,
    "robots_requests": 5,
    "search_capture_started": False,
    "search_export_requests": 0,
    "source_attachment_requests": 0,
    "source_detail_requests": 0,
    "source_document_requests": 0,
    "successful_http_200_requests": 6,
}


def _endpoint_contracts() -> dict[str, Any]:
    return {
        "environmental_impact_assessment_discussion_list": {
            "base_url": EIA_API_BASE_URL,
            "data_format": "XML",
            "item_fields": [
                "bizNm",
                "ccilOrganNm",
                "eiaCd",
                "eiaSeq",
                "firstCtgCd",
                "rnum",
                "stepChangeDt",
            ],
            "operation_path": EIA_LIST_PATH,
            "optional_query_parameters": [
                "numOfRows",
                "searchStep1",
                "searchStep2",
                "searchOrgan",
                "searchText",
            ],
            "page_number_base_documented": False,
            "page_size_default_documented": False,
            "page_size_default": None,
            "page_size_maximum_documented": False,
            "page_size_maximum": None,
            "required_query_parameters": ["serviceKey", "pageNo"],
            "response_pagination_fields": [
                "numOfRows",
                "pageNo",
                "totalCount",
            ],
            "search_text_documentation": "business-name search term",
        },
        "pre_strategy_small_scale_discussion_list": {
            "base_url": PRE_STRATEGY_SMALL_API_BASE_URL,
            "data_format": "XML",
            "item_fields": [
                "applyDt",
                "bizNm",
                "bizSeq",
                "ccilStepCd",
                "perCd",
                "rnum",
            ],
            "operation_path": PRE_STRATEGY_SMALL_LIST_PATH,
            "optional_query_parameters": [
                "pressGubn",
                "searchStep1",
                "searchStep2",
                "searchOrgan",
                "searchText",
            ],
            "page_number_base_documented": False,
            "page_size_default_documented": False,
            "page_size_default": None,
            "page_size_maximum_documented": False,
            "page_size_maximum": None,
            "press_gubn_values": {
                "M": "small_scale",
                "S": "strategic",
                "null": "prior_environmental_review",
            },
            "required_query_parameters": [
                "serviceKey",
                "pageNo",
                "numOfRows",
            ],
            "response_pagination_fields": [
                "numOfRows",
                "pageNo",
                "totalCount",
            ],
            "search_text_documentation": "business-name search",
        },
        "shared_semantics": {
            "anonymous_invocation_documented": False,
            "exact_phrase_matching_documented": False,
            "machine_readable_project_list_endpoints_found": True,
            "pagination_fields_documented": True,
            "service_key_required": True,
            "snapshot_or_as_of_semantics_documented": False,
            "stable_sort_documented": False,
            "substring_matching_documented": False,
            "total_count_documented": True,
        },
    }


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "anonymous_api_access_documented": False,
            "api_host_robots_http_status": 500,
            "api_host_robots_policy_obtained": False,
            "api_invocation_performed": False,
            "canonical_eiass_robots_outcome": "tls_handshake_failure",
            "data_go_development_traffic_period": None,
            "data_go_development_traffic_value": 10000,
            "data_go_free": True,
            "data_go_portal_documentation_robots_http_status": 200,
            "data_go_portal_documentation_robots_wildcard_root_disallow": False,
            "development_review": "automatic_approval",
            "operation_review": "automatic_approval",
            "service_key_required": True,
            "usage_application_surface_present": True,
            "www_eiass_robots_outcome": "network_error",
        },
        "business_area_geometry_api": {
            "base_url": BUSINESS_AREA_API_BASE_URL,
            "data_formats": ["JSON", "XML"],
            "discovery_source": False,
            "license_label": "unrestricted",
            "operation_paths": ["/getInfoWFS", "/getInfoWMS"],
            "service_key_required": True,
            "wfs_required_parameters": [
                "ServiceKey",
                "srsName",
                "maxFeatures",
            ],
            "why_not_used": (
                "geometry service is not a documented data-centre or project-"
                "name discovery endpoint and was not invoked"
            ),
        },
        "coverage_contract": {
            "all_environmental_assessment_categories_captured": False,
            "all_korean_data_centre_projects_claimed": False,
            "broader_building_planning_and_grid_permits_covered": False,
            "complete_for_south_korea_claimed": False,
            "full_corpus_enumeration_executed": False,
            "result_count": None,
            "site_count": None,
            "source_scope": (
                "NIER EIASS environmental-impact discussion-status lists for "
                "EIA plus prior, strategic, and small-scale assessment records"
            ),
        },
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "endpoint_contracts": _endpoint_contracts(),
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "administrative_eia_record_is_atlas_project": False,
            "administrative_eia_record_is_atlas_site": False,
            "administrative_eia_stage_is_physical_lifecycle": False,
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "construction_status": None,
            "data_centre_type": None,
            "review_only": True,
        },
        "migration_notice": {
            "attachment_labelled_recovering": True,
            "attachment_requested": False,
            "notice_date": "2025-05-07",
            "notice_url": MIGRATION_NOTICE_URL,
            "old_kei_api_count": 22,
            "old_kei_services_discontinued": True,
            "reason": "EIASS transferred from KEI to NIER",
            "replacement_description": "identical NIER OpenAPI services",
            "replacement_mapping_attachment_contents_verified": False,
        },
        "network_policy": {
            "current_audit_remaining_attempt_budget": 30,
            "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "one_request_at_a_time": True,
            "response_body_hash_required": True,
            "stop_and_null_counts_on_cap_or_error": True,
            "stop_before_first_result_request_unless_access_robots_rights_and_reproducibility_gates_are_affirmative": True,
        },
        "publisher": (
            "Climate Energy Environment Ministry, National Institute of "
            "Environmental Research (NIER), via the Public Data Portal"
        ),
        "release_id": RELEASE_ID,
        "retention": {
            "administrative_eia_rows_retained": False,
            "applicant_or_contact_fields_retained": False,
            "attachments_or_documents_retained": False,
            "geometry_retained": False,
            "raw_response_bodies_retained": False,
            "result_titles_or_descriptions_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "south-korea-eiass-nier-eia-project-search",
        "source_urls": {
            "business_area_api_metadata": BUSINESS_AREA_API_METADATA_URL,
            "data_go_policy": DATA_GO_POLICY_URL,
            "eia_api_metadata": EIA_API_METADATA_URL,
            "migration_notice": MIGRATION_NOTICE_URL,
            "pre_strategy_small_api_metadata": (
                PRE_STRATEGY_SMALL_API_METADATA_URL
            ),
        },
        "unit_contract": {
            "administrative_record_is_physical_project": False,
            "administrative_record_is_physical_site": False,
            "project_count": None,
            "record_count": None,
            "site_count": None,
            "source_observation_unit": (
                "environmental_assessment_discussion_status_record"
            ),
        },
    }


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, term in enumerate(SEARCH_TERMS, start=1):
        rows.append(
            {
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "english_term_enabled": None,
                "exact_literal_local_postfilter_completed": False,
                "network_requests": 0,
                "pages_retrieved": 0,
                "query_id": f"ko-{index:02d}",
                "result_count": None,
                "source_exact_phrase_semantics_documented": False,
                "status": (
                    "not_executed_credential_robots_reproducibility_gate"
                ),
                "term": term,
                "term_language": "ko",
            }
        )
    for index, term in enumerate(CONDITIONAL_ENGLISH_TERMS, start=1):
        rows.append(
            {
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "english_term_enabled": False,
                "exact_literal_local_postfilter_completed": False,
                "network_requests": 0,
                "pages_retrieved": 0,
                "query_id": f"en-{index:02d}",
                "result_count": None,
                "source_exact_phrase_semantics_documented": False,
                "status": "not_enabled_gates_failed",
                "term": term,
                "term_language": "en",
            }
        )
    return {
        "classification_contract_if_authorized": {
            "administrative_record_is_review_only": True,
            "automatic_promotion_permitted": False,
            "exact_literal_local_postfilter_required": True,
            "human_classification_required": True,
        },
        "conditional_english_terms": list(CONDITIONAL_ENGLISH_TERMS),
        "english_terms_enabled": False,
        "format": QUERY_PLAN_FORMAT,
        "full_corpus_enumeration_required_for_completeness": True,
        "korean_literals": list(SEARCH_TERMS),
        "mechanically_complete_capture_possible_under_current_contract": False,
        "planned_endpoint_paths": [EIA_LIST_PATH, PRE_STRATEGY_SMALL_LIST_PATH],
        "release_id": RELEASE_ID,
        "rows": rows,
        "schema_version": SCHEMA_VERSION,
        "search_capture_started": False,
        "source_queries_submitted": 0,
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "administrative_eia_stage_is_physical_lifecycle": False,
            "physical_construction_status": None,
            "physical_operation_status": None,
            "source_lifecycle_statement_count": None,
        },
        "metric_contract": {
            "annual_energy_consumption_mwh": None,
            "gross_power_mw": None,
            "it_capacity_mw": None,
            "pue": None,
            "retained_metric_rows": 0,
            "source_metric_statement_count": None,
        },
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "source_observation_unit": (
            "environmental_assessment_discussion_status_record"
        ),
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "api_endpoints_documented": 2,
        "api_operations_invoked": 0,
        "format": SOURCE_INVENTORY_FORMAT,
        "geometry_operations_invoked": 0,
        "migration_notice_records_retained": 0,
        "release_id": RELEASE_ID,
        "retained_environmental_assessment_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "environmental_assessment_record_count": None,
            "project_count": None,
            "result_count": None,
            "site_count": None,
        },
        "unit_contract": source_definition()["unit_contract"],
    }


def assessment_document(inventory: Mapping[str, Any]) -> dict[str, Any]:
    validate_retrieval_inventory(inventory)
    return {
        "assessed_at": inventory["audit_completed_at"],
        "assessment_id": RELEASE_ID,
        "atlas_decision": {
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            **DOWNSTREAM_IMPORT_POLICY,
            "retained_source_rows": 0,
            "status": (
                "credential_and_reproducibility_gates_blocked_metadata_only"
            ),
        },
        "blockers": {
            "access": (
                "both list operations require a Public Data Portal serviceKey; "
                "no API operation was invoked in this assessment"
            ),
            "api_robots": (
                "the documented API host robots request returned HTTP 500, so "
                "no usable policy was obtained"
            ),
            "coverage": (
                "EIASS discussion-status records do not cover every Korean "
                "planning, building, grid, or physical construction event"
            ),
            "eiass_direct_access": (
                "both EIASS robots origins failed before an HTTP response"
            ),
            "reproducibility": (
                "page-size default and maximum, stable ordering, snapshot "
                "semantics, and exact or substring search behavior are not "
                "documented"
            ),
        },
        "coverage": {
            "all_union_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_south_korea": False,
            "environmental_assessment_record_count": None,
            "project_count": None,
            "query_variants_completed": 0,
            "query_variants_planned": (
                len(SEARCH_TERMS) + len(CONDITIONAL_ENGLISH_TERMS)
            ),
            "result_count": None,
            "site_count": None,
            "source_union_sha256": None,
        },
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": schema_document()["lifecycle_contract"],
        "machine_readable_endpoint_finding": {
            "current_list_endpoints_documented": True,
            "open_licence_documented": True,
            "public_but_key_gated": True,
            "uncredentialed_anonymous_endpoint_found": False,
        },
        "metric_boundary": schema_document()["metric_contract"],
        "pii_policy": {
            "applicant_capture_performed": False,
            "contact_fields_retained": False,
            "documents_retained": False,
            "natural_person_fields_retained": False,
        },
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "audit_metadata_sha256": sha256_bytes(canonical_json(inventory)),
            "completed_response_requests": inventory[
                "completed_response_requests"
            ],
            "direct_request_attempt_cap": inventory[
                "direct_request_attempt_cap"
            ],
            "direct_request_attempts": inventory["direct_request_attempts"],
            "failed_network_requests": inventory["failed_network_requests"],
            "minimum_request_start_interval_seconds": inventory[
                "audit_request_start_interval_seconds"
            ],
            "raw_source_bodies_retained": False,
            "result_bearing_api_requests": 0,
            "result_bearing_search_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "EIASS/NIER environmental-assessment project lists",
            "operator": (
                "National Institute of Environmental Research via data.go.kr"
            ),
        },
        "unit_boundary": source_definition()["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""South Korea EIASS/NIER source assessment

Public Data Portal EIA list metadata: {EIA_API_METADATA_URL}
Public Data Portal prior/strategic/small-scale list metadata: {PRE_STRATEGY_SMALL_API_METADATA_URL}
Public Data Portal business-area metadata: {BUSINESS_AREA_API_METADATA_URL}
Public Data Portal migration notice: {MIGRATION_NOTICE_URL}
Public Data Portal policy and Type 1 terms: {DATA_GO_POLICY_URL}

The NIER list-API metadata is marked as including third-party rights under an
attribution condition and as Public Works Type 1. The portal policy states
that Type 1 requires attribution and permits commercial, noncommercial, and
derivative use.

This bundle republishes no API row, EIASS search result, EIA document,
attachment, contact field, or geometry. It contains only atlas-authored audit
metadata, response hashes, null counts, and an unexecuted query plan.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# South Korea EIASS/NIER source assessment

Two current machine-readable NIER project-list operations are documented on
the Korean Public Data Portal:

- `{EIA_API_BASE_URL}{EIA_LIST_PATH}` for environmental-impact-assessment
  discussion-status projects; and
- `{PRE_STRATEGY_SMALL_API_BASE_URL}{PRE_STRATEGY_SMALL_LIST_PATH}` for prior,
  strategic, and small-scale assessment discussion-status projects.

Both return XML and expose `pageNo`, `numOfRows`, and `totalCount`. The first
requires `serviceKey` and `pageNo`; the second also requires `numOfRows`.
Both offer an optional `searchText` documented only as a business-name search.
No exact-phrase or substring behavior, page-size default or maximum, stable
sort, or snapshot/as-of contract is documented.

The API metadata marks both resources as including third-party rights under
an attribution condition and as Public Works Type 1. The directly audited
portal policy defines Type 1 as attribution-required reuse permitting
commercial, noncommercial, and derivative use. This API licence does not
automatically license EIASS web pages, search results, or assessment documents.
Browser-proxy review of the official EIASS copyright policy and terms found an
All Rights Reserved footer, free reuse limited to KOGL-marked works, prior
consultation for unmarked material, and restrictions on unapproved
reproduction, distribution, alteration, sale, or commercial use. Those rights
pages were not directly requested after both EIASS robots origins failed.

Access is public but key-gated, not anonymous: each operation requires a
Public Data Portal `serviceKey`; the metadata labels development and operating
review as automatic approval, the service as free, and development traffic as
10,000 without documenting the period. No credential was supplied or used.

The 7 May 2025 portal notice says 22 former KEI EIASS OpenAPI services were
discontinued after EIASS moved to NIER and points to identical NIER
replacements. Its mapping attachment is labelled as recovering, so the
attachment was not requested and its contents are not claimed verified.

Capture stopped before every search and API operation. The API host's
`robots.txt` returned HTTP 500. Direct robots requests to both EIASS hostnames
failed before an HTTP response. With access and reproducibility gates still
open, neither `데이터센터` nor `데이터 센터` was submitted; conditional English
terms `data center` and `data centre` were not enabled.

The controlled audit made exactly 10 direct-origin attempts, serially paced at
least {MIN_REQUEST_INTERVAL_SECONDS:.1f} seconds between starts under a cap of
{MAX_DIRECT_REQUEST_ATTEMPTS}. Seven attempts returned an HTTP response, three
failed at the network layer, and all result, export, detail, attachment, and
document requests remained zero. Browser-proxy research is disclosed
separately because its origin request count is unavailable.

An EIA discussion-status row is review-only administrative evidence. It is not
proof of a physical data-centre site or that construction started, completed,
or entered operation. Data-centre type, IT capacity, gross power, PUE, and
annual energy remain null. This release cannot feed the construction master,
construction map, or current-coverage ledger.

Validate the frozen bundle offline:

```bash
python3 scripts/validate_south_korea_eiass_nier.py
```

Rebuild derived files from pinned audit metadata without network access:

```bash
python3 scripts/build_south_korea_eiass_nier.py --output /tmp/south-korea-eiass-nier
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise SouthKoreaEIASSNIERAssessmentError(
            "retrieval inventory differs from pinned audit"
        )
    _parse_utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 10:
        raise SouthKoreaEIASSNIERAssessmentError(
            "controlled audit must contain ten direct attempts"
        )
    if inventory.get("direct_request_attempts") != len(requests):
        raise SouthKoreaEIASSNIERAssessmentError(
            "direct request arithmetic differs"
        )
    if inventory.get("direct_request_attempt_cap") != 40:
        raise SouthKoreaEIASSNIERAssessmentError("direct request cap differs")
    if len(requests) > inventory["direct_request_attempt_cap"]:
        raise SouthKoreaEIASSNIERAssessmentError("direct request cap exceeded")
    if inventory.get("audit_request_start_interval_seconds", 0) < 3.0:
        raise SouthKoreaEIASSNIERAssessmentError(
            "request pacing contract is below three seconds"
        )

    expected_statuses = [200, None, None, 200, 200, 200, 200, 500, None, 200]
    expected_outcomes = [
        "response",
        "network_error",
        "network_error",
        "response",
        "response",
        "response",
        "response",
        "response",
        "network_error",
        "response",
    ]
    if [row.get("http_status") for row in requests] != expected_statuses:
        raise SouthKoreaEIASSNIERAssessmentError(
            "controlled audit statuses differ"
        )
    if [row.get("outcome") for row in requests] != expected_outcomes:
        raise SouthKoreaEIASSNIERAssessmentError(
            "controlled audit outcomes differ"
        )

    starts: list[datetime] = []
    for index, row in enumerate(requests):
        _official_url(row.get("url"), f"request[{index}].url")
        starts.append(
            _parse_utc_timestamp(
                row.get("started_at"), f"request[{index}].started_at"
            )
        )
        if (
            row.get("method") != "GET"
            or row.get("body_retained") is not False
            or row.get("redirect_followed") is not False
            or not isinstance(row.get("elapsed_seconds"), (int, float))
            or row["elapsed_seconds"] < 0
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise SouthKoreaEIASSNIERAssessmentError(
                f"controlled request row {index} is invalid"
            )
        if row["outcome"] == "response":
            if (
                not isinstance(row.get("http_status"), int)
                or not isinstance(row.get("bytes"), int)
                or isinstance(row.get("bytes"), bool)
                or row["bytes"] <= 0
                or row.get("response_body_received") is not True
            ):
                raise SouthKoreaEIASSNIERAssessmentError(
                    f"response row {index} is invalid"
                )
        elif (
            row.get("http_status") is not None
            or row.get("bytes") != 0
            or row.get("response_body_received") is not False
            or row.get("sha256") != _EMPTY_SHA256
        ):
            raise SouthKoreaEIASSNIERAssessmentError(
                f"network-error row {index} is invalid"
            )

    for before, after in zip(starts, starts[1:]):
        if (after - before).total_seconds() < MIN_REQUEST_INTERVAL_SECONDS:
            raise SouthKoreaEIASSNIERAssessmentError(
                "controlled request starts are too close"
            )

    arithmetic = (
        inventory.get("completed_response_requests", 0)
        + inventory.get("failed_network_requests", 0)
    )
    if arithmetic != len(requests):
        raise SouthKoreaEIASSNIERAssessmentError(
            "response and failure arithmetic differs"
        )
    if inventory.get("successful_http_200_requests") != 6:
        raise SouthKoreaEIASSNIERAssessmentError(
            "successful response arithmetic differs"
        )
    if inventory.get("http_error_responses") != 1:
        raise SouthKoreaEIASSNIERAssessmentError(
            "HTTP error response arithmetic differs"
        )
    for field in (
        "result_bearing_api_requests",
        "result_bearing_search_requests",
        "search_export_requests",
        "source_attachment_requests",
        "source_detail_requests",
        "source_document_requests",
    ):
        if inventory.get(field) != 0:
            raise SouthKoreaEIASSNIERAssessmentError(f"{field} must stay zero")
    if inventory.get("search_capture_started") is not False:
        raise SouthKoreaEIASSNIERAssessmentError(
            "search capture must stay unstarted"
        )
    if inventory.get("raw_response_bodies_retained") is not False:
        raise SouthKoreaEIASSNIERAssessmentError(
            "raw response bodies cannot be retained"
        )
    if inventory.get("analysis_temporary_response_bodies_deleted") is not True:
        raise SouthKoreaEIASSNIERAssessmentError(
            "temporary response bodies must be deleted"
        )
    if any(
        path in urlsplit(row["url"]).path
        for row in requests
        for path in (EIA_LIST_PATH, PRE_STRATEGY_SMALL_LIST_PATH)
    ):
        raise SouthKoreaEIASSNIERAssessmentError(
            "a result-bearing API path was requested"
        )
    lowered_urls = "\n".join(row["url"].casefold() for row in requests)
    if any(
        term.casefold() in lowered_urls
        for term in SEARCH_TERMS + CONDITIONAL_ENGLISH_TERMS
    ):
        raise SouthKoreaEIASSNIERAssessmentError(
            "a data-centre search literal was submitted"
        )
    if requests[0]["sha256"] != (
        "91cd7b24dcd33000f491982e4c281ca5"
        "44915c8e55a9fc40904cf6148ef1ad04"
    ):
        raise SouthKoreaEIASSNIERAssessmentError(
            "Data Portal robots checkpoint differs"
        )
    if requests[7]["http_status"] != 500:
        raise SouthKoreaEIASSNIERAssessmentError(
            "API robots checkpoint differs"
        )
    if inventory.get("browser_proxy_research_used") is not True or inventory.get(
        "browser_proxy_origin_request_count"
    ) is not None:
        raise SouthKoreaEIASSNIERAssessmentError(
            "browser-proxy accounting disclosure differs"
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
    if not root.is_dir() or root.is_symlink():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    return all(
        stat.S_IMODE(entry.stat().st_mode)
        == (0o555 if entry.is_dir() else 0o444)
        for entry in root.rglob("*")
    )


def write_release_bundle(inventory: Mapping[str, Any], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise SouthKoreaEIASSNIERAssessmentError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
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
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{label} must be a regular file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SouthKoreaEIASSNIERAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise SouthKoreaEIASSNIERAssessmentError(
            f"{label} must contain canonical JSON"
        )
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise SouthKoreaEIASSNIERAssessmentError(
            "release must be a regular directory"
        )
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise SouthKoreaEIASSNIERAssessmentError("release file set differs")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise SouthKoreaEIASSNIERAssessmentError(
            "release cannot contain symlinks"
        )
    if not is_frozen_release(root):
        raise SouthKoreaEIASSNIERAssessmentError(
            "release modes are not frozen"
        )

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise SouthKoreaEIASSNIERAssessmentError(
                f"derived file differs: {name}"
            )

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise SouthKoreaEIASSNIERAssessmentError(
            "manifest inventory differs"
        )
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise SouthKoreaEIASSNIERAssessmentError(
            "manifest sidecar differs"
        )

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise SouthKoreaEIASSNIERAssessmentError(
                "external definition must be a regular file"
            )
        if definition_path.read_bytes() != canonical_json(definition):
            raise SouthKoreaEIASSNIERAssessmentError(
                "external definition differs"
            )

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    if assessment["atlas_decision"]["status"] != (
        "credential_and_reproducibility_gates_blocked_metadata_only"
    ):
        raise SouthKoreaEIASSNIERAssessmentError(
            "assessment decision differs"
        )
    if assessment["coverage"]["result_count"] is not None:
        raise SouthKoreaEIASSNIERAssessmentError(
            "unexecuted result count must be null"
        )
    if schema["classification_rows"] != [] or (
        root / "observations.jsonl"
    ).read_bytes():
        raise SouthKoreaEIASSNIERAssessmentError(
            "blocked assessment cannot emit source rows"
        )
    if plan["source_queries_submitted"] != 0 or any(
        row["network_requests"] != 0 for row in plan["rows"]
    ):
        raise SouthKoreaEIASSNIERAssessmentError(
            "query plan must remain unexecuted"
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
