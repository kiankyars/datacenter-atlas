"""Fail-closed Finland environmental-permit source assessment.

Finland's LVV environmental-matters service exposes a public search API, but
the official LVV open-data catalogue does not identify that service as an
open dataset.  This lane therefore records only access, robots, schema, and
rights-audit metadata.  It does not execute result-bearing searches or retain
permit cases, documents, applicants, projects, sites, or metrics.
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
    "finland-lvv-environmental-permit-data-centre-search-"
    "2016-2026-2026-07-18-v1"
)
RELEASE_FORMAT = "datacenter-atlas-finland-lvv-permit-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-finland-lvv-permit-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-finland-lvv-permit-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-finland-lvv-permit-audit-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-finland-lvv-permit-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-finland-lvv-permit-source-inventory-v1"
)

START_DATE = date(2016, 1, 1)
END_DATE = date(2026, 7, 18)
SEARCH_TERMS = ("datakeskus", "datakeskukset", "data center", "data centre")
DATE_BASES = ("case_created", "latest_document_published")
PAGE_SIZE = 25
MAX_PAGES_PER_QUERY = 40
MAX_RESULT_BEARING_REQUESTS = (
    len(SEARCH_TERMS) * len(DATE_BASES) * MAX_PAGES_PER_QUERY
)
MIN_REQUEST_INTERVAL_SECONDS = 5.0

SERVICE_ORIGIN = "https://ytietopalvelu.lvv.fi"
SERVICE_URL = f"{SERVICE_ORIGIN}/"
SEARCH_ENDPOINT = f"{SERVICE_ORIGIN}/api/v1/cases/search"
OPENAPI_URL = f"{SERVICE_ORIGIN}/swagger/v1/swagger.json"
SERVICE_ROBOTS_URL = f"{SERVICE_ORIGIN}/robots.txt"
LVV_OPEN_DATA_URL = "https://lvv.fi/yhteystiedot/avoin-data"
LVV_ROBOTS_URL = "https://lvv.fi/robots.txt"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/deed.fi"
YVA_LANDING_URL = (
    "https://www.ymparisto.fi/fi/osallistu-ja-vaikuta/"
    "ymparistovaikutusten-arviointi"
)
YVA_SEARCH_URL = "https://www.ymparisto.fi/fi/search"
YMPARISTO_ROBOTS_URL = "https://www.ymparisto.fi/robots.txt"
LEGACY_SERVICE_URL = "https://ylupa.avi.fi/"

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


class FinlandLVVPermitError(ValueError):
    """Raised when the Finland access assessment fails its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FinlandLVVPermitError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FinlandLVVPermitError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FinlandLVVPermitError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise FinlandLVVPermitError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "creativecommons.org",
        "lvv.fi",
        "www.ymparisto.fi",
        "ylupa.avi.fi",
        "ytietopalvelu.lvv.fi",
    }:
        raise FinlandLVVPermitError(f"{field} must use an allowed official host")
    return value


def query_request_body(
    term: str,
    date_basis: str,
    *,
    offset: int = 0,
) -> dict[str, Any]:
    """Return one predeclared future request body without sending it."""

    if term not in SEARCH_TERMS:
        raise FinlandLVVPermitError("term is outside the closed query plan")
    if date_basis not in DATE_BASES:
        raise FinlandLVVPermitError("date basis is outside the closed query plan")
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or offset % PAGE_SIZE
        or offset >= PAGE_SIZE * MAX_PAGES_PER_QUERY
    ):
        raise FinlandLVVPermitError("offset is outside the bounded page plan")

    start = f"{START_DATE.isoformat()}T00:00:00Z"
    end = f"{END_DATE.isoformat()}T23:59:59Z"
    return {
        "createdEnd": end if date_basis == "case_created" else None,
        "createdStart": start if date_basis == "case_created" else None,
        "documentPublishEnd": (
            end if date_basis == "latest_document_published" else None
        ),
        "documentPublishStart": (
            start if date_basis == "latest_document_published" else None
        ),
        "fetchNext": PAGE_SIZE,
        "offset": offset,
        "orderByField": 0,
        "query": term,
        "sortDirection": 0,
        "type": 0,
    }


RIGHTS_POLICY: dict[str, Any] = {
    "affirmative_retained_data_scope_found": False,
    "assessment_metadata_publication_permitted": True,
    "cc_by_4_0_applies_to_lvv_produced_open_data": True,
    "cc_by_4_0_url": CC_BY_4_URL,
    "environmental_permit_service_listed_in_open_data_catalogue": False,
    "legal_conclusion_claimed": False,
    "lvv_open_data_catalogue_url": LVV_OPEN_DATA_URL,
    "permit_case_metadata_publication_permitted": False,
    "permit_documents_publication_permitted": False,
    "raw_api_response_publication_permitted": False,
    "reason": (
        "LVV's open-data page says it is the collected list of LVV open-data "
        "contents and applies CC BY 4.0 to LVV-produced open data, but the "
        "listed contents do not include the environmental-matters permit "
        "service. Public viewing and an unauthenticated API do not by "
        "themselves affirm a redistribution scope."
    ),
    "rights_clarification_required_before_capture": True,
    "verified_local_date": END_DATE.isoformat(),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "reason": (
        "rights-gated metadata-only assessment with no source rows, project/site "
        "resolution, or physical-lifecycle evidence"
    ),
}

PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": END_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T03:32:14Z",
    "controlled_http_requests": [
        {
            "body_retained": False,
            "bytes": 4275,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "request_id": "service_landing_audit",
            "response_date": "2026-07-19T03:32:12Z",
            "sha256": "b2ab45675d7ee29fd750e892412c79213ebb306d2a8d08d1757f08e1b09c1959",
            "url": SERVICE_URL,
        },
        {
            "body_retained": False,
            "bytes": 12885,
            "content_type": "application/json",
            "http_status": 200,
            "method": "GET",
            "request_id": "openapi_contract_audit",
            "response_date": "2026-07-19T03:32:12Z",
            "sha256": "9dfdc756a680f2cf7caf3c85ad30da9c4df159872315caa48fa43e22e5db7e59",
            "url": OPENAPI_URL,
        },
        {
            "body_retained": False,
            "bytes": 527,
            "content_type": "text/plain",
            "http_status": 404,
            "method": "GET",
            "request_id": "service_robots_audit",
            "response_date": "2026-07-19T03:32:13Z",
            "sha256": "ad3584a8d830e90490779ca89b691f7f30db2e4008f6cbb470788d7029127304",
            "url": SERVICE_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 2,
            "content_type": "application/json",
            "http_status": 200,
            "method": "POST",
            "request_body_bytes": 244,
            "request_body_retained": False,
            "request_body_sha256": "b68c4f557ecfd4b0de2260bf7fc47dfcb516e6513bb3d8b6371b11e16878612f",
            "request_id": "synthetic_guaranteed_no_match_machine_access_probe",
            "response_date": "2026-07-19T03:30:47Z",
            "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            "url": SEARCH_ENDPOINT,
        },
        {
            "body_retained": False,
            "bytes": 308559,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "request_id": "lvv_open_data_rights_audit",
            "response_date": "2026-07-19T03:32:13Z",
            "sha256": "7ec8e8af5961e44f0e2256f8c0d382d8206b9dfd94a978f2f9891e615dafacff",
            "url": LVV_OPEN_DATA_URL,
        },
        {
            "body_retained": False,
            "bytes": 538,
            "content_type": "text/plain",
            "http_status": 200,
            "method": "GET",
            "request_id": "lvv_robots_audit",
            "response_date": "2026-07-19T03:32:13Z",
            "sha256": "69d901a27e829f546ae6d0db261989149e314e1eea83ca2cd2482f27071f60b9",
            "url": LVV_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 70122,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "request_id": "ymparisto_yva_landing_audit",
            "response_date": "2026-07-19T03:32:14Z",
            "sha256": "d1e44691f882530b1d9df4a58355239bf0fe61f606ddee1e142acc86a240b2bd",
            "url": YVA_LANDING_URL,
        },
        {
            "body_retained": False,
            "bytes": 2005,
            "content_type": "text/plain",
            "http_status": 200,
            "method": "GET",
            "request_id": "ymparisto_robots_audit",
            "response_date": "2026-07-19T03:32:14Z",
            "sha256": "17f7b0b22f4a02e7b9d4b252bf47b78870c738d7f35dcfdb043b02470e347603",
            "url": YMPARISTO_ROBOTS_URL,
        },
    ],
    "format": RETRIEVAL_FORMAT,
    "network_requests": 8,
    "raw_response_bodies_retained": False,
    "release_id": RELEASE_ID,
    "result_bearing_search_requests": 0,
    "search_capture_started": False,
    "synthetic_no_match_probe_requests": 1,
}


def source_definition() -> dict[str, Any]:
    query_variants = []
    for index, (term, date_basis) in enumerate(
        (
            (term, date_basis)
            for term in SEARCH_TERMS
            for date_basis in DATE_BASES
        ),
        1,
    ):
        query_variants.append(
            {
                "date_basis": date_basis,
                "query_id": f"q{index:02d}",
                "request_body_first_page": query_request_body(term, date_basis),
                "term": term,
            }
        )
    return {
        "access": {
            "api_authentication_required_by_openapi": False,
            "api_machine_access_verified_with_synthetic_no_match": True,
            "api_openapi_available": True,
            "api_search_capture_started": False,
            "primary_host_robots_http_status": 404,
            "primary_host_robots_rule_published": False,
            "tls_certificate_valid_during_audit": True,
        },
        "coverage_contract": {
            "bounded_date_end": END_DATE.isoformat(),
            "bounded_date_start": START_DATE.isoformat(),
            "complete_for_finland_claimed": False,
            "date_bases": list(DATE_BASES),
            "geography": "Finland national LVV water and environmental permit cases",
            "query_variants": query_variants,
            "result_count": None,
            "search_terms": list(SEARCH_TERMS),
            "unique_physical_site_count": None,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "data_centre_type": None,
            "permit_process_status_is_physical_lifecycle": False,
            "physical_lifecycle_status": None,
            "review_only": True,
        },
        "network_policy_if_rights_later_clarified": {
            "maximum_pages_per_query": MAX_PAGES_PER_QUERY,
            "maximum_result_bearing_requests": MAX_RESULT_BEARING_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "page_size": PAGE_SIZE,
            "response_body_hash_required": True,
            "stop_and_null_counts_on_cap_or_error": True,
            "stop_before_first_query_unless_rights_gate_is_affirmative": True,
        },
        "publisher": "Lupa- ja valvontavirasto (LVV)",
        "release_id": RELEASE_ID,
        "retention": {
            "applicant_field_retained": False,
            "case_rows_retained": False,
            "contact_fields_retained": False,
            "documents_or_attachments_retained": False,
            "map_or_geometry_retained": False,
            "personal_data_retained": False,
            "raw_api_response_bodies_retained": False,
            "result_titles_or_descriptions_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "finland-lvv-environmental-permit-data-centre-search",
        "source_urls": {
            "lvv_open_data": LVV_OPEN_DATA_URL,
            "openapi": OPENAPI_URL,
            "search_api": SEARCH_ENDPOINT,
            "service": SERVICE_URL,
            "service_robots": SERVICE_ROBOTS_URL,
            "ymparisto_robots": YMPARISTO_ROBOTS_URL,
            "ymparisto_yva_landing": YVA_LANDING_URL,
            "ymparisto_yva_search": YVA_SEARCH_URL,
        },
        "title": "Finland LVV environmental-permit access and rights assessment",
        "unit_contract": {
            "api_search_result_unit": "permit_case_search_record",
            "document_publication_is_case_record": False,
            "permit_case_is_atlas_project": False,
            "permit_case_is_atlas_site": False,
            "project_count": None,
            "publication_count": None,
            "site_count": None,
        },
    }


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, (term, date_basis) in enumerate(
        (
            (term, date_basis)
            for term in SEARCH_TERMS
            for date_basis in DATE_BASES
        ),
        1,
    ):
        rows.append(
            {
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "date_basis": date_basis,
                "exact_literal_local_postfilter_completed": False,
                "network_requests": 0,
                "pages_retrieved": 0,
                "query_id": f"q{index:02d}",
                "request_body_first_page": query_request_body(term, date_basis),
                "result_count": None,
                "status": "not_executed_rights_scope_not_affirmed",
                "term": term,
            }
        )
    return {
        "classification_contract": {
            "ancillary_or_context": (
                "data-centre language appears, but the permit case concerns "
                "ancillary infrastructure, context, or a different regulated activity"
            ),
            "direct_data_centre_project": (
                "the regulated case itself is a data-centre build or expansion"
            ),
            "excluded": "the exact literal has no data-centre project relevance",
        },
        "date_range_end_inclusive_utc": f"{END_DATE.isoformat()}T23:59:59Z",
        "date_range_start_inclusive_utc": f"{START_DATE.isoformat()}T00:00:00Z",
        "deduplication_if_executed": "exact CaseResponse.id only",
        "endpoint": SEARCH_ENDPOINT,
        "english_variant_support_basis": (
            "OpenAPI defines query as an unrestricted string and the service UI "
            "describes substring search without a language restriction"
        ),
        "exact_literal_postfilter_if_executed": (
            "Unicode casefolded literal match in the retained case name, journal "
            "number, organization-only applicant, or municipality fields"
        ),
        "format": QUERY_PLAN_FORMAT,
        "http_method": "POST",
        "release_id": RELEASE_ID,
        "rows": rows,
        "union": {
            "all_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "closed_union_sha256": None,
            "permit_case_count": None,
            "project_count": None,
            "publication_count": None,
            "site_count": None,
            "status": "not_built_rights_scope_not_affirmed",
        },
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {
                "role": "primary national environmental-permit search service",
                "url": SERVICE_URL,
            },
            {
                "role": "public machine-readable API contract",
                "url": OPENAPI_URL,
            },
            {
                "role": "permit case search endpoint",
                "url": SEARCH_ENDPOINT,
            },
            {
                "role": "primary service robots location; returned HTTP 404",
                "url": SERVICE_ROBOTS_URL,
            },
            {
                "role": "LVV open-data catalogue and CC BY 4.0 statement",
                "url": LVV_OPEN_DATA_URL,
            },
            {
                "role": "secondary national YVA discovery landing",
                "url": YVA_LANDING_URL,
            },
            {
                "role": "secondary YVA host robots policy",
                "url": YMPARISTO_ROBOTS_URL,
            },
        ],
        "release_id": RELEASE_ID,
        "robots_findings": {
            "lvv_main_host": {
                "crawl_delay_seconds": 5,
                "disallowed_paths_include": ["/search/", "/haku/", "/sok/"],
                "robots_http_status": 200,
            },
            "primary_service_host": {
                "robots_http_status": 404,
                "robots_rule_published": False,
            },
            "ymparisto_host": {
                "canonical_finnish_search_path": "/fi/search",
                "canonical_path_is_exact_prefix_match_for_listed_disallow": False,
                "disallowed_paths_include": ["/search/", "/index.php/search/"],
                "robots_http_status": 200,
                "robots_rule_is_reuse_permission": False,
            },
        },
        "service_migration": {
            "current_service_url": SERVICE_URL,
            "legacy_certificate_expired_at": "2026-04-30T09:07:36Z",
            "legacy_service_url": LEGACY_SERVICE_URL,
            "legacy_url_redirect_observed_to_current_service": True,
        },
        "tls_audit": {
            "current_certificate_not_after": "2027-01-18T23:59:59Z",
            "current_certificate_sha256_fingerprint": (
                "d2a06fb158c154112b1b9a25da28ac0712dc4b43c469d4ce0fc47ca3f5987b37"
            ),
            "current_certificate_valid_during_audit": True,
            "legacy_certificate_sha256_fingerprint": (
                "a27cfb4481eb7cb1898a2077249a5457b61da1951a0ef57a853a7434732114fc"
            ),
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "permit_process_status": None,
            "permit_process_status_is_physical_lifecycle": False,
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
        "retained_document_publication_rows": 0,
        "retained_permit_case_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "license_or_permit_case_count": None,
            "project_count": None,
            "publication_count": None,
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
            "status": "rights_scope_unconfirmed_metadata_only",
        },
        "coverage": {
            "all_union_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_finland": False,
            "date_end": END_DATE.isoformat(),
            "date_start": START_DATE.isoformat(),
            "license_or_permit_case_count": None,
            "project_count": None,
            "publication_count": None,
            "query_variants_completed": 0,
            "query_variants_planned": len(SEARCH_TERMS) * len(DATE_BASES),
            "result_count": None,
            "site_count": None,
            "source_union_sha256": None,
        },
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": schema_document()["lifecycle_contract"],
        "metric_boundary": schema_document()["metric_contract"],
        "pii_policy": {
            "applicant_capture_performed": False,
            "contacts_retained": False,
            "natural_person_applicants_retained": False,
            "organization_resolution_performed": False,
        },
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "audit_metadata_sha256": sha256_bytes(canonical_json(inventory)),
            "controlled_audit_requests": inventory["network_requests"],
            "raw_source_bodies_retained": False,
            "result_bearing_search_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "Ympäristöasioiden tietopalvelu",
            "operator": "Lupa- ja valvontavirasto",
            "openapi_url": OPENAPI_URL,
            "service_url": SERVICE_URL,
        },
        "unit_boundary": source_definition()["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""Finland LVV environmental-permit access assessment

Official service: {SERVICE_URL}
OpenAPI contract: {OPENAPI_URL}
Rights surface: {LVV_OPEN_DATA_URL}
Secondary YVA landing: {YVA_LANDING_URL}

This bundle republishes no LVV permit cases, result text, applicant fields,
documents, attachments, or ymparisto.fi YVA records. It contains only the
atlas project's own audit metadata, hashes, null coverage findings, and a
future query plan. The LVV open-data page identifies CC BY 4.0 for LVV-produced
open data, but did not list the environmental-permit service during the audit;
that license is therefore not asserted for source records in this bundle.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Finland LVV environmental-permit source assessment

The official national source is LVV's Ympäristöasioiden tietopalvelu at
{SERVICE_URL}. Its public OpenAPI at {OPENAPI_URL} documents an unauthenticated
`POST /api/v1/cases/search`. A synthetic guaranteed-no-match request returned
HTTP 200 with an empty array, and the service host's `robots.txt` returned HTTP
404. Machine access is available.

Capture did not start because an affirmative retained-data scope was not
found. LVV's official open-data page, {LVV_OPEN_DATA_URL}, says it collects the
links to LVV open-data contents and applies CC BY 4.0 to LVV-produced open data.
The listed contents did not include the environmental-permit service. Public
viewing and an unauthenticated API are not treated as redistribution terms.

The closed future plan contains the exact literals `datakeskus`,
`datakeskukset`, `data center`, and `data centre`. Each term has one case-created
and one latest-document-published query bounded from 2016-01-01 through
2026-07-18 inclusive. If LVV later clarifies rights, results must be locally
postfiltered to the exact literal, unioned only by exact `CaseResponse.id`, and
every union row classified as direct, ancillary/context, or excluded. Until
then, result, permit-case, publication, project, site, and classification counts
remain null.

A permit case and its administrative process status are not a physical project,
site, construction milestone, or operating status. No entity, project, or site
merge is performed. No data-centre type, power, PUE, or energy-consumption value
is emitted. Applicant and contact fields are not retained. This assessment
cannot feed the construction master, map, or current-coverage ledger.

The frozen bundle uses directory mode `0555` and file mode `0444`. Validate it
without network access:

```bash
python3 scripts/validate_finland_lvv_environmental_permits.py
```

Reproduce the derived files from the pinned audit inventory in a separate
directory:

```bash
python3 scripts/build_finland_lvv_environmental_permits.py --output /tmp/finland-lvv-release
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise FinlandLVVPermitError("retrieval inventory differs from pinned audit")
    _utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise FinlandLVVPermitError("controlled audit must contain eight requests")
    if inventory.get("network_requests") != len(requests):
        raise FinlandLVVPermitError("audit request arithmetic differs")
    if inventory.get("result_bearing_search_requests") != 0:
        raise FinlandLVVPermitError("result-bearing search requests must stay zero")
    if inventory.get("search_capture_started") is not False:
        raise FinlandLVVPermitError("source search capture must stay unstarted")
    if inventory.get("raw_response_bodies_retained") is not False:
        raise FinlandLVVPermitError("raw source bodies cannot be retained")

    for index, row in enumerate(requests):
        _official_url(row.get("url"), f"request[{index}].url")
        _utc_timestamp(row.get("response_date"), f"request[{index}].response_date")
        if (
            row.get("method") not in {"GET", "POST"}
            or row.get("body_retained") is not False
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or not isinstance(row.get("http_status"), int)
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise FinlandLVVPermitError(f"request audit row {index} is invalid")
    if [row["http_status"] for row in requests] != [
        200,
        200,
        404,
        200,
        200,
        200,
        200,
        200,
    ]:
        raise FinlandLVVPermitError("controlled audit statuses differ")
    no_match = requests[3]
    if (
        no_match.get("method") != "POST"
        or no_match.get("request_body_retained") is not False
        or no_match.get("request_body_bytes") != 244
        or no_match.get("request_body_sha256")
        != "b68c4f557ecfd4b0de2260bf7fc47dfcb516e6513bb3d8b6371b11e16878612f"
    ):
        raise FinlandLVVPermitError("synthetic no-match probe differs")


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
        stat.S_IMODE(entry.stat().st_mode) == (0o555 if entry.is_dir() else 0o444)
        for entry in root.rglob("*")
    )


def write_release_bundle(inventory: Mapping[str, Any], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise FinlandLVVPermitError("output already exists")
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
        raise FinlandLVVPermitError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FinlandLVVPermitError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise FinlandLVVPermitError(f"{label} must contain canonical JSON")
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise FinlandLVVPermitError("release must be a regular directory")
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise FinlandLVVPermitError("release file set differs")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise FinlandLVVPermitError("release cannot contain symlinks")
    if not is_frozen_release(root):
        raise FinlandLVVPermitError("release modes are not frozen")

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise FinlandLVVPermitError(f"derived file differs: {name}")

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise FinlandLVVPermitError("manifest inventory differs")
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise FinlandLVVPermitError("manifest sidecar differs")

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise FinlandLVVPermitError("external definition must be a regular file")
        if definition_path.read_bytes() != canonical_json(definition):
            raise FinlandLVVPermitError("external definition differs")

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    if assessment["atlas_decision"]["status"] != "rights_scope_unconfirmed_metadata_only":
        raise FinlandLVVPermitError("assessment decision differs")
    if assessment["coverage"]["result_count"] is not None:
        raise FinlandLVVPermitError("unexecuted search result count must be null")
    if assessment["coverage"]["site_count"] is not None:
        raise FinlandLVVPermitError("unexecuted site count must be null")
    if schema["classification_rows"] != [] or (root / "observations.jsonl").read_bytes():
        raise FinlandLVVPermitError("rights-gated assessment cannot emit source rows")
    if any(row["network_requests"] != 0 for row in plan["rows"]):
        raise FinlandLVVPermitError("query plan must remain unexecuted")
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
