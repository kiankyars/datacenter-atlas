"""Fail-closed India PARIVESH environmental-clearance source assessment.

The bounded audit found useful official discovery surfaces but no affirmative
permission to reproduce PARIVESH proposal records.  It therefore stops before
every proposal search, result page, project detail, and document request.  The
frozen assessment retains only request metadata and hashes, null source counts,
and a rights-gated future query plan.
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
    "india-parivesh-environmental-clearance-data-centre-rights-audit-"
    "2026-07-18-v1"
)
RELEASE_FORMAT = "datacenter-atlas-india-parivesh-ec-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-india-parivesh-ec-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-india-parivesh-ec-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-india-parivesh-ec-audit-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-india-parivesh-ec-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-india-parivesh-ec-source-inventory-v1"
)

ASSESSMENT_LOCAL_DATE = date(2026, 7, 18)
PLANNED_QUERY_START_DATE = date(2006, 9, 14)
PLANNED_QUERY_END_DATE = ASSESSMENT_LOCAL_DATE
SEARCH_TERMS = (
    "data centre",
    "data center",
    "datacentre",
    "datacenter",
)
QUERY_YEARS = tuple(
    range(PLANNED_QUERY_START_DATE.year, PLANNED_QUERY_END_DATE.year + 1)
)
MIN_REQUEST_INTERVAL_SECONDS = 5.0
MAX_PAGES_PER_QUERY = 10
PAGE_SIZE_CEILING_IF_SUPPORTED = 100
MAX_RESULT_BEARING_REQUESTS = (
    len(SEARCH_TERMS) * len(QUERY_YEARS) * MAX_PAGES_PER_QUERY
)

CURRENT_SERVICE_URL = "https://parivesh.nic.in/"
CURRENT_ROBOTS_URL = "https://parivesh.nic.in/robots.txt"
CURRENT_COPYRIGHT_API_URL = "https://parivesh.nic.in/cms/pages/get"
CURRENT_COPYRIGHT_PAGE_ID = 1317164
LEGACY_COPYRIGHT_URL = (
    "https://environmentclearance.nic.in/CopyrightPolicy.aspx"
)
LEGACY_ROBOTS_URL = "https://environmentclearance.nic.in/robots.txt"
DATA_GOV_CATALOG_URL = (
    "https://www.data.gov.in/catalog/"
    "environmental-clearance-granted-parivesh-20"
)
DATA_GOV_RESOURCE_URL = (
    "https://www.data.gov.in/resource/"
    "state-wise-environmental-clearance-proposals-granted-during-2022"
)
DATA_GOV_LICENSE_URL = "https://www.data.gov.in/Godl"

AUDIT_REQUESTS = (
    ("GET", CURRENT_SERVICE_URL),
    ("GET", CURRENT_ROBOTS_URL),
    ("POST", CURRENT_COPYRIGHT_API_URL),
    ("GET", LEGACY_COPYRIGHT_URL),
    ("GET", LEGACY_ROBOTS_URL),
    ("GET", DATA_GOV_CATALOG_URL),
    ("GET", DATA_GOV_RESOURCE_URL),
    ("GET", DATA_GOV_LICENSE_URL),
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
_AUDIT_ROW_KEYS = {
    "bytes",
    "content_type",
    "http_status",
    "method",
    "observed_at",
    "request_bytes",
    "request_sha256",
    "response_body_retained",
    "sha256",
    "tls_verification_bypassed",
    "url",
}


class IndiaPARIVESHEnvironmentalClearanceError(ValueError):
    """Raised when the India PARIVESH assessment fails its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{field} must be a timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{field} must be RFC 3339"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{field} must be a URL"
        )
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "environmentclearance.nic.in",
        "parivesh.nic.in",
        "www.data.gov.in",
    }:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{field} must use an allowed official host"
        )
    return value


RIGHTS_POLICY: dict[str, Any] = {
    "affirmative_parivesh_proposal_record_reuse_scope_found": False,
    "assessment_metadata_publication_permitted": True,
    "current_parivesh_copyright_policy_requires_permission": True,
    "data_gov_aggregate_is_released_under_ndsap": True,
    "data_gov_godl_affirmative_for_published_dataset_resources": True,
    "data_gov_godl_scope_affirmed_for_parivesh_project_rows": False,
    "legal_conclusion_claimed": False,
    "legacy_environmental_clearance_copyright_policy_requires_permission": True,
    "parivesh_project_or_proposal_row_publication_permitted": False,
    "project_search_requires_prior_rights_clarification": True,
    "raw_source_response_publication_permitted": False,
    "result_or_derived_row_publication_permitted": False,
    "robots_rule_is_reuse_permission": False,
    "verified_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "reason": (
        "The current PARIVESH CMS copyright surface and the legacy "
        "environmental-clearance copyright surface both condition reproduction "
        "on permission. The Government Open Data License is affirmative for "
        "the separately published data.gov.in resource, but that resource is "
        "only a 2022 state aggregate and does not affirm rights for PARIVESH "
        "proposal-level records. Access and robots findings are not treated as "
        "reuse permission."
    ),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "reason": (
        "rights-gated metadata-only assessment with no proposal rows, "
        "project/site resolution, physical-lifecycle evidence, coordinates, "
        "or source metrics"
    ),
}

PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T04:40:54Z",
    "audit_request_interval_seconds": 2.0,
    "controlled_audit_requests": 8,
    "controlled_http_requests": [
        {
            "bytes": 1723,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:35Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "451cc80a56b3beeb0b38c2f421beb2f81dc4efe0d0e7484164a6126e02f641c2",
            "tls_verification_bypassed": False,
            "url": CURRENT_SERVICE_URL,
        },
        {
            "bytes": 431,
            "content_type": "text/html",
            "http_status": 404,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:38Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "270d2fb55aa801662897590a27ec1c152407fa36be1d6678c27fd8c1859239e4",
            "tls_verification_bypassed": False,
            "url": CURRENT_ROBOTS_URL,
        },
        {
            "bytes": 612,
            "content_type": "application/json",
            "http_status": 200,
            "method": "POST",
            "observed_at": "2026-07-19T04:40:41Z",
            "request_bytes": 128,
            "request_sha256": "f673ee38aae564eb025e5a6bb17554ac12735e7046f4c19c54c8680b5914d56c",
            "response_body_retained": False,
            "sha256": "d1e2c0c0eb06401427fd729990df1241d90be084f70beb17b8fc18c918b74927",
            "tls_verification_bypassed": False,
            "url": CURRENT_COPYRIGHT_API_URL,
        },
        {
            "bytes": 13176,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:44Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "c7bffe221412e3faf1caf56d93eb18c014001947c1d1de2507a594c5833a23dd",
            "tls_verification_bypassed": False,
            "url": LEGACY_COPYRIGHT_URL,
        },
        {
            "bytes": 23,
            "content_type": "text/plain",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:47Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "16ceb5ee3e0dc13aa9adf31a3ebbe45a1d965b8c2b9f72eaf84e5911e140ed95",
            "tls_verification_bypassed": False,
            "url": LEGACY_ROBOTS_URL,
        },
        {
            "bytes": 1017703,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:50Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "b33c1193729b615a31ed91b838af00b583dc661b04a90058ab25ca5aad31610b",
            "tls_verification_bypassed": False,
            "url": DATA_GOV_CATALOG_URL,
        },
        {
            "bytes": 997941,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:52Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "af0cc5b630c67ab74b201b6a58458cc6fa4b3aee172fd97831d6c0f45c319c38",
            "tls_verification_bypassed": False,
            "url": DATA_GOV_RESOURCE_URL,
        },
        {
            "bytes": 993255,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "observed_at": "2026-07-19T04:40:54Z",
            "request_bytes": 0,
            "request_sha256": None,
            "response_body_retained": False,
            "sha256": "35c9dbe242030e380e9e5583e7920eb07aa464ff3904f019b7e9cb4e750abdb9",
            "tls_verification_bypassed": False,
            "url": DATA_GOV_LICENSE_URL,
        },
    ],
    "data_gov_metadata_requests": 3,
    "data_gov_resource_body_requests": 0,
    "format": RETRIEVAL_FORMAT,
    "project_detail_requests": 0,
    "project_document_requests": 0,
    "proposal_result_requests": 0,
    "proposal_search_requests": 0,
    "raw_response_bodies_retained": False,
    "release_id": RELEASE_ID,
    "rights_and_access_metadata_requests": 8,
    "source_capture_started": False,
}


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "current_copyright_cms_http_status": 200,
            "current_copyright_page_id": CURRENT_COPYRIGHT_PAGE_ID,
            "current_portal_http_status": 200,
            "current_robots_http_status": 404,
            "current_robots_rule_published": False,
            "legacy_copyright_http_status": 200,
            "legacy_robots_allows_root": True,
            "legacy_robots_http_status": 200,
            "proposal_search_started": False,
        },
        "coverage_contract": {
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_india_claimed": False,
            "decision_or_publication_count": None,
            "environmental_clearance_proposal_count": None,
            "geography": "India",
            "observed_source_date_end": None,
            "observed_source_date_start": None,
            "project_count": None,
            "proposal_search_executed": False,
            "result_count": None,
            "site_count": None,
        },
        "data_gov_alternative": {
            "aggregate_row_count": None,
            "catalog_published_date": "2023-06-15",
            "catalog_updated_date": "2023-06-15",
            "file_body_requested": False,
            "file_size_metadata_bytes": 386,
            "geographic_unit": "state_or_union_territory",
            "open_license": "Government Open Data License - India",
            "project_level": False,
            "resource_period": "2022",
            "suitable_for_project_discovery": False,
        },
        "format": DEFINITION_FORMAT,
        "future_authorized_query_contract": {
            "automatic_fuzzy_match_permitted": False,
            "date_sharding": "calendar_year_clipped_to_planned_query_bounds",
            "deduplication": (
                "exact official opaque record identifier when exposed; "
                "otherwise no automatic deduplication"
            ),
            "endpoint": None,
            "exact_casefolded_literal_match_required": True,
            "human_classification_required": True,
            "interface_and_schema_reverification_required": True,
            "page_size_ceiling_if_interface_supports_it": (
                PAGE_SIZE_CEILING_IF_SUPPORTED
            ),
            "permission_scope_must_cover_proposal_and_result_metadata": True,
            "planned_lower_bound_basis": (
                "atlas-selected planning bound aligned to the date of the "
                "EIA Notification 2006; not evidence of PARIVESH record "
                "availability, observed coverage, or completeness"
            ),
            "planned_query_count": len(SEARCH_TERMS) * len(QUERY_YEARS),
            "planned_query_date_end_inclusive": (
                PLANNED_QUERY_END_DATE.isoformat()
            ),
            "planned_query_date_start_inclusive": (
                PLANNED_QUERY_START_DATE.isoformat()
            ),
            "query_years": list(QUERY_YEARS),
            "search_terms": list(SEARCH_TERMS),
            "source_observation_unit": (
                "environmental_clearance_proposal_stage_record"
            ),
        },
        "inference_policy": {
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "data_centre_type": None,
            "environmental_clearance_status_is_physical_lifecycle": False,
            "physical_lifecycle_status": None,
            "review_only": True,
        },
        "network_policy_if_rights_later_clarified": {
            "maximum_pages_per_query": MAX_PAGES_PER_QUERY,
            "maximum_result_bearing_requests": MAX_RESULT_BEARING_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "one_request_at_a_time": True,
            "response_body_hash_required": True,
            "stop_and_null_counts_on_cap_error_or_pagination_ambiguity": True,
            "stop_before_first_result_request_unless_rights_gate_is_affirmative": True,
        },
        "publisher": (
            "Ministry of Environment, Forest and Climate Change, Government of India"
        ),
        "release_id": RELEASE_ID,
        "retention": {
            "applicant_fields_retained": False,
            "contact_fields_retained": False,
            "derived_rows_retained": False,
            "personal_data_retained": False,
            "project_documents_retained": False,
            "proposal_or_result_rows_retained": False,
            "raw_html_json_or_excerpts_retained": False,
            "raw_response_bodies_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": (
            "india-parivesh-environmental-clearance-data-centre-rights-assessment"
        ),
        "source_urls": {
            "current_copyright_cms": CURRENT_COPYRIGHT_API_URL,
            "current_portal": CURRENT_SERVICE_URL,
            "current_robots": CURRENT_ROBOTS_URL,
            "data_gov_catalog": DATA_GOV_CATALOG_URL,
            "data_gov_license": DATA_GOV_LICENSE_URL,
            "data_gov_resource": DATA_GOV_RESOURCE_URL,
            "legacy_copyright": LEGACY_COPYRIGHT_URL,
            "legacy_robots": LEGACY_ROBOTS_URL,
        },
        "title": (
            "India PARIVESH environmental-clearance data-centre rights audit "
            "with an unexecuted atlas-selected future query plan"
        ),
        "unit_contract": {
            "decision_or_publication_count": None,
            "environmental_clearance_proposal_count": None,
            "environmental_clearance_status_is_physical_lifecycle": False,
            "project_count": None,
            "proposal_stage_record_is_atlas_project": False,
            "proposal_stage_record_is_atlas_site": False,
            "result_count": None,
            "site_count": None,
            "source_observation_unit": (
                "environmental_clearance_proposal_stage_record"
            ),
        },
    }


def _date_bounds_for_year(year: int) -> tuple[date, date]:
    lower = max(PLANNED_QUERY_START_DATE, date(year, 1, 1))
    upper = min(PLANNED_QUERY_END_DATE, date(year, 12, 31))
    return lower, upper


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for year in QUERY_YEARS:
        lower, upper = _date_bounds_for_year(year)
        for term_index, term in enumerate(SEARCH_TERMS, 1):
            rows.append(
                {
                    "classification_counts": {
                        "ancillary_or_context": None,
                        "direct_data_centre_project": None,
                        "excluded": None,
                    },
                    "planned_query_date_end_inclusive": upper.isoformat(),
                    "planned_query_date_start_inclusive": lower.isoformat(),
                    "decision_or_publication_count": None,
                    "environmental_clearance_proposal_count": None,
                    "network_requests": 0,
                    "pages_retrieved": 0,
                    "project_count": None,
                    "query_id": f"y{year}-t{term_index:02d}",
                    "result_count": None,
                    "search_term": term,
                    "site_count": None,
                    "status": "not_executed_rights_scope_not_affirmed",
                }
            )
    return {
        "classification_contract": {
            "ancillary_or_context": (
                "the official record mentions a data centre only as context "
                "or concerns an ancillary work"
            ),
            "direct_data_centre_project": (
                "the environmental-clearance record itself concerns a "
                "data-centre build or expansion"
            ),
            "excluded": "the literal has no data-centre project relevance",
        },
        "deduplication_if_executed": (
            "exact official opaque record identifier when exposed; otherwise "
            "retain query membership without automatic entity collapse"
        ),
        "endpoint": None,
        "format": QUERY_PLAN_FORMAT,
        "maximum_pages_per_query": MAX_PAGES_PER_QUERY,
        "maximum_result_bearing_requests": MAX_RESULT_BEARING_REQUESTS,
        "observed_source_coverage_claimed": False,
        "planned_lower_bound_basis": (
            "atlas-selected planning bound aligned to the date of the EIA "
            "Notification 2006; not evidence of PARIVESH record availability, "
            "observed coverage, or completeness"
        ),
        "planned_query_count": len(rows),
        "planned_query_date_end_inclusive": (
            PLANNED_QUERY_END_DATE.isoformat()
        ),
        "planned_query_date_start_inclusive": (
            PLANNED_QUERY_START_DATE.isoformat()
        ),
        "release_id": RELEASE_ID,
        "rights_and_interface_gates": {
            "affirmative_proposal_record_reuse_permission_required": True,
            "credential_or_access_control_circumvention_permitted": False,
            "interface_and_schema_reverification_required": True,
            "technical_endpoint_selected": False,
        },
        "rows": rows,
        "search_terms": list(SEARCH_TERMS),
        "union": {
            "all_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "closed_union_sha256": None,
            "decision_or_publication_count": None,
            "environmental_clearance_proposal_count": None,
            "project_count": None,
            "result_count": None,
            "site_count": None,
            "status": "not_built_rights_scope_not_affirmed",
        },
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "audited_official_sources": [
            {"role": "current service root", "url": CURRENT_SERVICE_URL},
            {"role": "current host robots path; HTTP 404", "url": CURRENT_ROBOTS_URL},
            {
                "role": "current CMS copyright surface",
                "url": CURRENT_COPYRIGHT_API_URL,
            },
            {
                "role": "legacy environmental-clearance copyright surface",
                "url": LEGACY_COPYRIGHT_URL,
            },
            {"role": "legacy host robots policy", "url": LEGACY_ROBOTS_URL},
            {"role": "open-data catalog metadata", "url": DATA_GOV_CATALOG_URL},
            {"role": "2022 aggregate resource metadata", "url": DATA_GOV_RESOURCE_URL},
            {"role": "Government Open Data License - India", "url": DATA_GOV_LICENSE_URL},
        ],
        "data_gov_alternative": source_definition()["data_gov_alternative"],
        "format": SOURCE_INVENTORY_FORMAT,
        "release_id": RELEASE_ID,
        "rights_surface_findings": {
            "affirmative_parivesh_project_row_reuse_scope_found": False,
            "current_and_legacy_copyright_surfaces_require_permission": True,
            "data_gov_open_scope_is_separate_aggregate_resource": True,
            "raw_policy_text_or_excerpt_retained": False,
        },
        "robots_findings": {
            "current_host_robots_http_status": 404,
            "current_host_robots_rule_published": False,
            "legacy_host_generic_allow_root": True,
            "legacy_host_robots_http_status": 200,
            "robots_rule_is_reuse_permission": False,
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "environmental_clearance_or_proposal_status": None,
            "environmental_clearance_status_is_physical_lifecycle": False,
            "physical_construction_status": None,
            "physical_operation_status": None,
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
        "retained_classification_rows": 0,
        "retained_derived_rows": 0,
        "retained_proposal_or_result_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "decision_or_publication_count": None,
            "environmental_clearance_proposal_count": None,
            "project_count": None,
            "result_count": None,
            "site_count": None,
        },
        "unit_contract": source_definition()["unit_contract"],
    }


def assessment_document(inventory: Mapping[str, Any]) -> dict[str, Any]:
    validate_retrieval_inventory(inventory)
    definition = source_definition()
    return {
        "assessed_at": inventory["audit_completed_at"],
        "assessment_id": RELEASE_ID,
        "atlas_decision": {
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            **DOWNSTREAM_IMPORT_POLICY,
            "retained_source_rows": 0,
            "status": "rights_scope_unconfirmed_metadata_only",
        },
        "coverage": {
            "all_union_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_india": False,
            "decision_or_publication_count": None,
            "environmental_clearance_proposal_count": None,
            "observed_source_date_end": None,
            "observed_source_date_start": None,
            "project_count": None,
            "proposal_search_executed": False,
            "result_count": None,
            "site_count": None,
            "source_union_sha256": None,
        },
        "data_gov_alternative": definition["data_gov_alternative"],
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": schema_document()["lifecycle_contract"],
        "metric_boundary": schema_document()["metric_contract"],
        "pii_policy": {
            "applicant_capture_performed": False,
            "contacts_retained": False,
            "natural_person_data_retained": False,
            "organization_resolution_performed": False,
            "proposal_documents_retained": False,
        },
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "audit_metadata_sha256": sha256_bytes(canonical_json(inventory)),
            "controlled_audit_requests": inventory["controlled_audit_requests"],
            "data_gov_metadata_requests": inventory["data_gov_metadata_requests"],
            "data_gov_resource_body_requests": inventory[
                "data_gov_resource_body_requests"
            ],
            "project_detail_requests": inventory["project_detail_requests"],
            "project_document_requests": inventory["project_document_requests"],
            "proposal_result_requests": inventory["proposal_result_requests"],
            "proposal_search_requests": inventory["proposal_search_requests"],
            "raw_source_bodies_retained": False,
            "rights_and_access_metadata_requests": inventory[
                "rights_and_access_metadata_requests"
            ],
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "PARIVESH",
            "operator": (
                "Ministry of Environment, Forest and Climate Change, Government of India"
            ),
            "service_url": CURRENT_SERVICE_URL,
        },
        "unit_boundary": definition["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""India PARIVESH environmental-clearance access assessment

Current official service: {CURRENT_SERVICE_URL}
Legacy copyright surface: {LEGACY_COPYRIGHT_URL}
Open-data catalog metadata: {DATA_GOV_CATALOG_URL}
Open-data licence: {DATA_GOV_LICENSE_URL}

This bundle republishes no PARIVESH searches, results, proposal records,
project details, documents, titles, descriptions, applicants, contacts,
personal data, response bodies, policy excerpts, or derived source rows. It
contains only atlas-authored audit metadata and response hashes, null coverage
findings, and a future rights-gated query plan. No proposal-record reuse
licence is asserted. The separate data.gov.in aggregate was not downloaded.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# India PARIVESH environmental-clearance source assessment

PARIVESH is the official Government of India workflow for environmental and
other green-clearance proposals. A bounded eight-request audit inspected only
the current service root, its robots path, the current CMS copyright surface,
the legacy environmental-clearance copyright and robots surfaces, and three
data.gov.in metadata/licence pages. It made zero proposal-search, result,
project-detail, project-document, or data-file requests.

The current and legacy copyright surfaces both require permission for
reproduction. The legacy robots file allows root crawling, while the current
robots path returned HTTP 404; neither finding is reuse permission. The
Government Open Data License is affirmative for resources separately
published on data.gov.in. The only PARIVESH 2.0 catalog resource found in this
bounded lane is a 386-byte, state-level aggregate for 2022, published and last
updated on 2023-06-15. It is not a project-level discovery source, and its CSV
body was not requested. Its open licence does not establish that PARIVESH
proposal rows may be reproduced.

The rights gate therefore stopped the run before source discovery. Result,
proposal, decision/publication, classification, project, site, and source
metric-statement counts remain null; exact retained row counts are zero. No
response body or excerpt is in this bundle.

If explicit permission later covers proposal and result metadata, the frozen
plan shards {len(SEARCH_TERMS)} exact case-folded English literals across
{len(QUERY_YEARS)} annual windows. Its {PLANNED_QUERY_START_DATE.isoformat()}
lower bound is atlas-selected and aligned to the date of the EIA Notification
2006; it is not evidence of PARIVESH record availability, observed coverage,
or completeness. The planned upper bound is
{PLANNED_QUERY_END_DATE.isoformat()}. The literals are `data centre`, `data
center`, `datacentre`, and `datacenter`. The technical interface and schema
must first be reverified. The plan then permits at most
{MAX_PAGES_PER_QUERY} pages per term-year query,
{MAX_RESULT_BEARING_REQUESTS} result-bearing requests total, one request at a
time with at least {MIN_REQUEST_INTERVAL_SECONDS:.0f} seconds between requests.
Any cap, error, or pagination ambiguity stops the run with source counts null.

A PARIVESH proposal stage or environmental-clearance decision is a regulatory
status, not evidence that physical construction started or that a site is
operating. The assessment emits no data-centre type, coordinates, power, PUE,
or energy value and cannot feed the construction master, map, or current-
coverage ledger.

The frozen bundle uses directory mode `0555` and file mode `0444`. Validate it
offline:

```bash
python3 scripts/validate_india_parivesh_environmental_clearances.py
```

Reproduce every derived file from the pinned audit metadata in a separate
directory:

```bash
python3 scripts/build_india_parivesh_environmental_clearances.py \\
  --output /tmp/india-parivesh-release
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "retrieval inventory differs from pinned audit"
        )
    _utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit must contain eight requests"
        )
    if inventory.get("controlled_audit_requests") != len(requests):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit arithmetic differs"
        )
    if inventory.get("rights_and_access_metadata_requests") != len(requests):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "rights/access audit arithmetic differs"
        )
    zero_request_fields = (
        "data_gov_resource_body_requests",
        "project_detail_requests",
        "project_document_requests",
        "proposal_result_requests",
        "proposal_search_requests",
    )
    if any(inventory.get(field) != 0 for field in zero_request_fields):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "result, project, document, and data-file requests must stay zero"
        )
    if inventory.get("data_gov_metadata_requests") != 3:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "data.gov.in metadata request count differs"
        )
    if inventory.get("source_capture_started") is not False:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "source capture must stay unstarted"
        )
    if inventory.get("raw_response_bodies_retained") is not False:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "raw response bodies cannot be retained"
        )

    expected_statuses = [200, 404, 200, 200, 200, 200, 200, 200]
    expected_content_types = [
        "text/html",
        "text/html",
        "application/json",
        "text/html",
        "text/plain",
        "text/html",
        "text/html",
        "text/html",
    ]
    expected_bytes = [1723, 431, 612, 13176, 23, 1017703, 997941, 993255]
    if [(row["method"], row["url"]) for row in requests] != list(AUDIT_REQUESTS):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit request order differs"
        )
    for index, row in enumerate(requests):
        if set(row) != _AUDIT_ROW_KEYS:
            raise IndiaPARIVESHEnvironmentalClearanceError(
                f"request audit row {index} fields differ"
            )
        _official_url(row.get("url"), f"request[{index}].url")
        _utc_timestamp(row.get("observed_at"), f"request[{index}].observed_at")
        if (
            isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or isinstance(row.get("http_status"), bool)
            or not isinstance(row.get("http_status"), int)
            or not isinstance(row.get("content_type"), str)
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
            or row.get("response_body_retained") is not False
            or row.get("tls_verification_bypassed") is not False
        ):
            raise IndiaPARIVESHEnvironmentalClearanceError(
                f"request audit row {index} is invalid"
            )
        if row["method"] == "GET":
            if row["request_bytes"] != 0 or row["request_sha256"] is not None:
                raise IndiaPARIVESHEnvironmentalClearanceError(
                    f"GET request audit row {index} has a request body"
                )
        elif row["method"] == "POST":
            if (
                row["request_bytes"] != 128
                or not isinstance(row["request_sha256"], str)
                or not _SHA256_RE.fullmatch(row["request_sha256"])
            ):
                raise IndiaPARIVESHEnvironmentalClearanceError(
                    "copyright CMS request metadata differs"
                )
        else:
            raise IndiaPARIVESHEnvironmentalClearanceError(
                f"request audit row {index} method differs"
            )
    if [row["http_status"] for row in requests] != expected_statuses:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit statuses differ"
        )
    if [row["content_type"] for row in requests] != expected_content_types:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit content types differ"
        )
    if [row["bytes"] for row in requests] != expected_bytes:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "controlled audit byte counts differ"
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
        not entry.is_symlink()
        and entry.is_file()
        and stat.S_IMODE(entry.stat().st_mode) == 0o444
        for entry in root.rglob("*")
    )


def write_release_bundle(inventory: Mapping[str, Any], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise IndiaPARIVESHEnvironmentalClearanceError("output already exists")
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
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{label} must be a regular file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"invalid {label}"
        ) from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            f"{label} must contain canonical JSON"
        )
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "release must be a regular directory"
        )
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "release file set differs"
        )
    if any(entry.is_symlink() or not entry.is_file() for entry in root.rglob("*")):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "release entries must be regular files without symlinks"
        )
    if not is_frozen_release(root):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "release modes are not frozen"
        )

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise IndiaPARIVESHEnvironmentalClearanceError(
                f"derived file differs: {name}"
            )

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "manifest inventory differs"
        )
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "manifest sidecar differs"
        )

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise IndiaPARIVESHEnvironmentalClearanceError(
                "external definition must be a regular file"
            )
        if definition_path.read_bytes() != canonical_json(definition):
            raise IndiaPARIVESHEnvironmentalClearanceError(
                "external definition differs"
            )

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    nullable_counts = (
        "decision_or_publication_count",
        "environmental_clearance_proposal_count",
        "project_count",
        "result_count",
        "site_count",
    )
    if assessment["atlas_decision"]["status"] != (
        "rights_scope_unconfirmed_metadata_only"
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "assessment decision differs"
        )
    if any(assessment["coverage"][field] is not None for field in nullable_counts):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "unexecuted proposal source counts must be null"
        )
    if (
        assessment["coverage"]["observed_source_date_start"] is not None
        or assessment["coverage"]["observed_source_date_end"] is not None
        or assessment["coverage"]["proposal_search_executed"] is not False
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "observed source coverage must remain null and unexecuted"
        )
    if any(
        value is not None
        for value in assessment["coverage"]["classification_counts"].values()
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "unexecuted proposal classification counts must be null"
        )
    if (
        schema["classification_rows"] != []
        or schema["retained_classification_rows"] != 0
        or schema["retained_derived_rows"] != 0
        or schema["retained_proposal_or_result_rows"] != 0
        or schema["metric_contract"]["retained_metric_rows"] != 0
        or (root / "observations.jsonl").read_bytes()
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "rights-gated assessment cannot emit source or derived rows"
        )
    if len(plan["rows"]) != len(SEARCH_TERMS) * len(QUERY_YEARS):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "future query plan row count differs"
        )
    if (
        plan["observed_source_coverage_claimed"] is not False
        or plan["planned_query_date_start_inclusive"]
        != PLANNED_QUERY_START_DATE.isoformat()
        or plan["planned_query_date_end_inclusive"]
        != PLANNED_QUERY_END_DATE.isoformat()
        or "atlas-selected" not in plan["planned_lower_bound_basis"]
        or "not evidence" not in plan["planned_lower_bound_basis"]
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "planned query bounds are ambiguous or differ"
        )
    if any(
        row["network_requests"] != 0
        or row["pages_retrieved"] != 0
        or row["status"] != "not_executed_rights_scope_not_affirmed"
        for row in plan["rows"]
    ):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "future query plan must remain unexecuted"
        )
    permission_keys = (
        "construction_map_import_permitted",
        "construction_master_import_permitted",
        "current_coverage_ledger_import_permitted",
        "explicit_positive_contract_present",
    )
    if any(DOWNSTREAM_IMPORT_POLICY[key] for key in permission_keys):
        raise IndiaPARIVESHEnvironmentalClearanceError(
            "downstream import policy differs"
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
