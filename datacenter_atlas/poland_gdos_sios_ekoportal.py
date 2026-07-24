"""Fail-closed Poland GDOŚ/SIOS/Ekoportal source assessment.

The official GDOŚ register page splits its own and the regional directorates'
public document cards between SIOS for entries published from 1 June 2025 and
an Ekoportal archive for older entries.  SIOS disallows all crawling in its
robots policy and does not document exact-phrase or pagination semantics.  The
separate, statutory national GDOŚ EIA database is blocked outside Poland.

This module therefore retains only audit metadata and hashes.  It does not run
result-bearing searches, request exports, retain document-card rows, or infer
projects, sites, physical lifecycle, type, capacity, or energy consumption.
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
    "poland-gdos-sios-ekoportal-data-centre-source-audit-2026-07-19-v1"
)
RELEASE_FORMAT = "datacenter-atlas-poland-gdos-sios-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-poland-gdos-sios-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-poland-gdos-sios-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-poland-gdos-sios-audit-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-poland-gdos-sios-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-poland-gdos-sios-source-inventory-v1"
)

ASSESSMENT_LOCAL_DATE = date(2026, 7, 19)
CURRENT_SIOS_START_DATE = date(2025, 6, 1)
SEARCH_TERMS = (
    "centrum danych",
    "centra danych",
    "data center",
    "serwerownia",
)
MIN_REQUEST_INTERVAL_SECONDS = 3.0
AUDIT_REQUEST_START_INTERVAL_SECONDS = 3.2
MAX_DIRECT_REQUEST_ATTEMPTS = 40
MAX_PAGES_PER_QUERY_IF_DOCUMENTED = 10
MAX_RESULT_BEARING_REQUESTS_IF_AUTHORIZED = (
    len(SEARCH_TERMS) * MAX_PAGES_PER_QUERY_IF_DOCUMENTED
)

GDOS_PDWD_SCOPE_URL = (
    "https://www.gov.pl/web/gdos/"
    "publicznie-dostepny-wykaz-danych-o-dokumentach-zawierajacych-"
    "informacje-o-srodowisku-i-jego-ochronie"
)
GDOS_REUSE_URL = (
    "https://www.gov.pl/web/gdos/ponowne-wykorzytanie-informacji"
)
GDOS_EIA_DATABASE_PAGE_URL = (
    "https://www.gov.pl/web/gdos/"
    "bazy-danych-o-ocenach-oddzialywania-na-srodowisko"
)
SIOS_ORIGIN = "https://system.sios.pl"
SIOS_SEARCH_URL = f"{SIOS_ORIGIN}/search/common"
SIOS_ROBOTS_URL = f"{SIOS_ORIGIN}/robots.txt"
SIOS_TERMS_URL = f"{SIOS_ORIGIN}/public/docs/regulamin_sios.pdf"
SIOS_PDF_EXPORT_PATH = "/search/pdfextend"
SIOS_XLS_EXPORT_PATH = "/search/xlsextend"
EKO_ARCHIVE_URL = (
    "https://wykaz.ekoportal.pl/CardList.seam?"
    "urzad=Generalna+Dyrekcja+Ochrony+%C5%9Arodowiska"
)
EKO_ARCHIVE_CANONICAL_URL = (
    "https://wykaz.ekoportal.pl/?"
    "urzad=Generalna+Dyrekcja+Ochrony+%C5%9Arodowiska"
)
EKO_ROBOTS_URL = "https://wykaz.ekoportal.pl/robots.txt"
NATIONAL_EIA_URL = "https://bazaoos.gdos.gov.pl/web/guest/home"
NATIONAL_EIA_ROBOTS_URL = "https://bazaoos.gdos.gov.pl/robots.txt"

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


class PolandGDOSSIOSAssessmentError(ValueError):
    """Raised when the Poland source assessment fails its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PolandGDOSSIOSAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PolandGDOSSIOSAssessmentError(
            f"{field} must be RFC 3339"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolandGDOSSIOSAssessmentError(
            f"{field} must include a timezone"
        )
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise PolandGDOSSIOSAssessmentError(
            f"{field} must use canonical UTC whole seconds"
        )
    return canonical


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PolandGDOSSIOSAssessmentError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "bazaoos.gdos.gov.pl",
        "system.sios.pl",
        "www.gov.pl",
        "wykaz.ekoportal.pl",
    }:
        raise PolandGDOSSIOSAssessmentError(
            f"{field} must use an allowed authoritative host"
        )
    return value


RIGHTS_POLICY: dict[str, Any] = {
    "affirmative_common_search_result_reuse_scope_found": False,
    "assessment_metadata_publication_permitted": True,
    "gdos_general_reuse_surface_found": True,
    "gdos_general_reuse_surface_reserves_third_party_rights": True,
    "gdos_reuse_surface_scope_affirmed_for_all_sios_publishers": False,
    "gov_pl_cc_by_sa_applies_to_linked_sios_results": False,
    "legal_conclusion_claimed": False,
    "raw_response_redistribution_permitted": False,
    "result_or_derived_source_row_publication_permitted": False,
    "rights_clarification_required_before_result_capture": True,
    "robots_rule_is_reuse_permission": False,
    "sios_footer_all_rights_reserved": True,
    "sios_terms_identify_service_provider_as_system_copyright_owner": True,
    "verified_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "reason": (
        "GDOŚ publishes a general public-sector-information reuse surface and "
        "generally permits reuse of its works and databases unless reserved, "
        "subject to third-party rights. The common SIOS search is operated by "
        "a private service provider, carries an All Rights Reserved footer, "
        "and aggregates cards whose publishing authorities and rights are not "
        "bounded by the GDOŚ page. No result-level reuse grant for the common "
        "search or its exports was found. The gov.pl CC BY-SA footer covers "
        "gov.pl text, not automatically the linked SIOS database."
    ),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "reason": (
        "robots-, rights-, semantics-, and coverage-blocked metadata-only "
        "assessment with no source rows or physical-lifecycle evidence"
    ),
}


PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "analysis_temporary_response_bodies_deleted": True,
    "assessment_local_date": ASSESSMENT_LOCAL_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T08:29:04Z",
    "audit_request_start_interval_seconds": (
        AUDIT_REQUEST_START_INTERVAL_SECONDS
    ),
    "browser_proxy_origin_request_count": None,
    "browser_proxy_research_excluded_from_direct_request_arithmetic": True,
    "browser_proxy_research_used": True,
    "completed_response_requests": 8,
    "controlled_http_requests": [
        {
            "body_retained": False,
            "bytes": 28977,
            "content_type": None,
            "elapsed_seconds": 0.933,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:27:58Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "gdos_pdwd_scope_audit",
            "response_body_received": True,
            "sha256": (
                "5803c1367dc3f34a1d38b824046ad196"
                "b9a18d1abe04d827602d21a52b12186b"
            ),
            "url": GDOS_PDWD_SCOPE_URL,
        },
        {
            "body_retained": False,
            "bytes": 43547,
            "content_type": None,
            "elapsed_seconds": 1.044,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:01Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "gdos_reuse_rights_audit",
            "response_body_received": True,
            "sha256": (
                "3fbeafc73555141a93a326fa29c62aba"
                "5feb667d01599f0f1997d846e5e65abd"
            ),
            "url": GDOS_REUSE_URL,
        },
        {
            "body_retained": False,
            "bytes": 32394,
            "content_type": None,
            "elapsed_seconds": 0.87,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:04Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "gdos_national_eia_access_audit",
            "response_body_received": True,
            "sha256": (
                "416c6878bb9f59f20f9c5506a17e907"
                "9ce658bdea57609d1aa5fe7106fd51682"
            ),
            "url": GDOS_EIA_DATABASE_PAGE_URL,
        },
        {
            "body_retained": False,
            "bytes": 15986,
            "content_type": "text/html; charset=UTF-8",
            "elapsed_seconds": 0.717,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:07Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "sios_empty_search_form_contract_audit",
            "response_body_received": True,
            "sha256": (
                "d0a1e92b822c283d34f0f3ff1005a554"
                "301d4cc69213dda0c4225efa401dd1fc"
            ),
            "url": SIOS_SEARCH_URL,
        },
        {
            "body_retained": False,
            "bytes": 25,
            "content_type": "text/plain",
            "elapsed_seconds": 0.482,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:11Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "sios_robots_audit",
            "response_body_received": True,
            "sha256": (
                "46807e235496ba8d849f071626c6a5ab1"
                "dcc71b17faf8b90419144d940478c1d"
            ),
            "url": SIOS_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 214673,
            "content_type": "application/pdf",
            "elapsed_seconds": 1.187,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:14Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "sios_terms_rights_audit",
            "response_body_received": True,
            "sha256": (
                "b2026f3d948dcfdaf37b40d5b6893bfd"
                "eeef8ce66e71148cd5e06f782f51afb9"
            ),
            "url": SIOS_TERMS_URL,
        },
        {
            "body_retained": False,
            "bytes": 324,
            "content_type": "text/html; charset=iso-8859-1",
            "elapsed_seconds": 1.429,
            "http_status": 301,
            "location": EKO_ARCHIVE_CANONICAL_URL,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:17Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "ekoportal_archive_redirect_audit",
            "response_body_received": True,
            "sha256": (
                "712d7a122ec103ac94fa812341bc5b4e4"
                "8bac5152b057f219464b3e6b25446bd"
            ),
            "url": EKO_ARCHIVE_URL,
        },
        {
            "body_retained": False,
            "bytes": 455,
            "content_type": "text/html",
            "elapsed_seconds": 0.96,
            "http_status": 200,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:20Z",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": "ekoportal_robots_location_audit",
            "response_body_received": True,
            "sha256": (
                "27804a434a22f54cf4c8dad13564bddf"
                "0cdbf1f49f361f6d40d36571d07f8128"
            ),
            "url": EKO_ROBOTS_URL,
        },
        {
            "body_retained": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": 20.55,
            "error_class": "timeout",
            "http_status": None,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:23Z",
            "outcome": "timeout",
            "redirect_followed": False,
            "request_id": "national_eia_home_access_probe",
            "response_body_received": False,
            "sha256": _EMPTY_SHA256,
            "url": NATIONAL_EIA_URL,
        },
        {
            "body_retained": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": 20.003,
            "error_class": "timeout",
            "http_status": None,
            "location": None,
            "method": "GET",
            "observed_at": "2026-07-19T08:28:44Z",
            "outcome": "timeout",
            "redirect_followed": False,
            "request_id": "national_eia_robots_access_probe",
            "response_body_received": False,
            "sha256": _EMPTY_SHA256,
            "url": NATIONAL_EIA_ROBOTS_URL,
        },
    ],
    "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
    "direct_request_attempts": 10,
    "failed_timeout_requests": 2,
    "format": RETRIEVAL_FORMAT,
    "raw_response_bodies_retained": False,
    "release_id": RELEASE_ID,
    "result_bearing_search_requests": 0,
    "search_capture_started": False,
    "search_export_requests": 0,
    "source_detail_requests": 0,
    "source_document_requests": 0,
}


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "national_eia_direct_home_probe_outcome": "timeout",
            "national_eia_direct_robots_probe_outcome": "timeout",
            "national_eia_officially_blocked_outside_poland": True,
            "sios_empty_form_http_status": 200,
            "sios_result_capture_started": False,
            "sios_robots_disallows_root_for_all_user_agents": True,
            "sios_robots_http_status": 200,
        },
        "coverage_contract": {
            "complete_for_poland_claimed": False,
            "current_gdos_rdos_cards_start": (
                CURRENT_SIOS_START_DATE.isoformat()
            ),
            "current_register_scope": (
                "cards for documents received or produced by GDOŚ and the "
                "regional directorates; not every Polish environmental or "
                "planning authority"
            ),
            "ekoportal_archive_scope": (
                "older GDOŚ register cards linked by the official GDOŚ page"
            ),
            "national_eia_database_statutory_entry_duty_start": "2017-01-01",
            "national_eia_database_scope": (
                "national proceedings for environmental assessments, with "
                "statutory entry duties from 2017 and data for 2016"
            ),
            "national_eia_query_executed": False,
            "result_count": None,
            "site_count": None,
        },
        "endpoint_contract": {
            "api_or_bulk_download_contract_found": False,
            "export_routes_observed_but_not_requested": [
                SIOS_PDF_EXPORT_PATH,
                SIOS_XLS_EXPORT_PATH,
            ],
            "form_action": "current URL",
            "form_method": "GET",
            "form_parameters": {
                "approved_date_from": "optional date string",
                "approved_date_to": "optional date string",
                "doc_date_from": "optional date string",
                "doc_date_to": "optional date string",
                "doc_receipt_from": "optional date string",
                "doc_receipt_to": "optional date string",
                "docname": "optional document name, max 64 characters",
                "id_communities": "optional municipality selector",
                "id_districts": "optional district selector",
                "id_doctype": "optional document-type selector",
                "id_doctopic": "optional topic selector",
                "id_provinces": "optional voivodeship selector",
                "iid": "publisher or instance selector; empty form value 0",
                "keywords": "keyword string, max 64 characters",
                "nocard": "optional card number, max 16 characters",
                "submitSearch": "Szukaj",
            },
            "pagination_contract_documented": False,
            "pagination_parameter": None,
            "page_size_documented": False,
            "page_size": None,
            "query_match_semantics_documented": False,
            "search_endpoint": SIOS_SEARCH_URL,
            "stable_sort_contract_documented": False,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "administrative_card_is_atlas_project": False,
            "administrative_card_is_atlas_site": False,
            "administrative_publication_is_physical_lifecycle": False,
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "construction_status": None,
            "data_centre_type": None,
            "review_only": True,
        },
        "network_policy_if_all_gates_later_clear": {
            "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
            "maximum_pages_per_query_if_pagination_is_documented": (
                MAX_PAGES_PER_QUERY_IF_DOCUMENTED
            ),
            "maximum_result_bearing_requests_if_authorized": (
                MAX_RESULT_BEARING_REQUESTS_IF_AUTHORIZED
            ),
            "minimum_request_interval_seconds": (
                MIN_REQUEST_INTERVAL_SECONDS
            ),
            "one_request_at_a_time": True,
            "response_body_hash_required": True,
            "stop_and_null_counts_on_cap_or_error": True,
            "stop_before_first_result_request_unless_robots_rights_coverage_and_semantics_gates_are_affirmative": True,
        },
        "publisher": (
            "Generalna Dyrekcja Ochrony Środowiska (official scope and "
            "national EIA database); SIOS is operated by Internet Community"
        ),
        "release_id": RELEASE_ID,
        "retention": {
            "administrative_card_rows_retained": False,
            "applicant_or_natural_person_fields_retained": False,
            "attachments_or_documents_retained": False,
            "export_response_bodies_retained": False,
            "map_or_geometry_retained": False,
            "raw_response_bodies_retained": False,
            "result_titles_or_descriptions_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "poland-gdos-sios-ekoportal-data-centre-source-audit",
        "source_urls": {
            "ekoportal_archive": EKO_ARCHIVE_URL,
            "gdos_eia_database_page": GDOS_EIA_DATABASE_PAGE_URL,
            "gdos_pdwd_scope": GDOS_PDWD_SCOPE_URL,
            "gdos_reuse": GDOS_REUSE_URL,
            "national_eia_database": NATIONAL_EIA_URL,
            "sios_robots": SIOS_ROBOTS_URL,
            "sios_search": SIOS_SEARCH_URL,
            "sios_terms": SIOS_TERMS_URL,
        },
        "title": "Poland GDOŚ/SIOS/Ekoportal access and reuse assessment",
        "unit_contract": {
            "administrative_card_is_document": False,
            "administrative_card_is_physical_project": False,
            "administrative_card_is_physical_site": False,
            "source_observation_unit": "public_environmental_document_card",
            "document_count": None,
            "project_count": None,
            "publication_count": None,
            "site_count": None,
        },
    }


def query_plan() -> dict[str, Any]:
    roles = {
        "centrum danych": "direct_singular_polish",
        "centra danych": "direct_plural_polish",
        "data center": "direct_english",
        "serwerownia": "context_sensitive_server_room",
    }
    rows = []
    for index, term in enumerate(SEARCH_TERMS, 1):
        rows.append(
            {
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "exact_literal_local_postfilter_completed": False,
                "network_requests": 0,
                "pages_retrieved": 0,
                "planned_get_parameters": {
                    "iid": "0",
                    "keywords": term,
                    "submitSearch": "Szukaj",
                },
                "query_id": f"q{index:02d}",
                "result_count": None,
                "source_exact_phrase_semantics_documented": False,
                "status": (
                    "not_executed_robots_rights_coverage_semantics_gate"
                ),
                "term": term,
                "term_role": roles[term],
            }
        )
    return {
        "classification_contract_if_authorized": {
            "ancillary_or_context": (
                "the exact literal appears, but the card concerns utilities, "
                "backup generation, a server room within another facility, "
                "or another non-facility context"
            ),
            "direct_data_centre_project": (
                "the underlying proceeding concerns a data-centre build or "
                "expansion; still not evidence of physical construction"
            ),
            "excluded": "the literal is unrelated or a false positive",
            "serwerownia_never_auto_promoted": True,
        },
        "current_sios_date_end_inclusive": ASSESSMENT_LOCAL_DATE.isoformat(),
        "current_sios_date_start_inclusive": (
            CURRENT_SIOS_START_DATE.isoformat()
        ),
        "deduplication_if_executed": (
            "exact publisher/instance ID plus card number and year only"
        ),
        "endpoint": SIOS_SEARCH_URL,
        "exact_literal_postfilter_if_executed": (
            "Unicode-normalized casefolded literal match over fields explicitly "
            "returned by an authorized capture"
        ),
        "format": QUERY_PLAN_FORMAT,
        "http_method": "GET",
        "pagination": {
            "maximum_pages_if_later_documented": (
                MAX_PAGES_PER_QUERY_IF_DOCUMENTED
            ),
            "parameter": None,
            "page_size": None,
            "status": "not_documented_on_empty_public_form",
        },
        "release_id": RELEASE_ID,
        "rows": rows,
        "source_keyword_semantics": (
            "The UI exposes an unrestricted field labelled Słowo kluczowe, "
            "but does not document exact phrase, tokenization, stemming, or "
            "field coverage. The four strings are therefore a gated future "
            "literal plan, not claims about source-side exact matching."
        ),
        "union": {
            "all_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "document_card_count": None,
            "project_count": None,
            "site_count": None,
            "source_union_sha256": None,
            "status": "not_built",
        },
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {
                "role": "official GDOŚ PDWD scope and successor/archive routing",
                "url": GDOS_PDWD_SCOPE_URL,
            },
            {
                "role": "official GDOŚ public-sector-information reuse surface",
                "url": GDOS_REUSE_URL,
            },
            {
                "role": "official description of the statutory national EIA database and geoblock",
                "url": GDOS_EIA_DATABASE_PAGE_URL,
            },
            {
                "role": "current GDOŚ/RDOŚ public document-card search",
                "url": SIOS_SEARCH_URL,
            },
            {
                "role": "SIOS robots policy",
                "url": SIOS_ROBOTS_URL,
            },
            {
                "role": "SIOS service terms",
                "url": SIOS_TERMS_URL,
            },
            {
                "role": "officially linked pre-June-2025 GDOŚ archive",
                "url": EKO_ARCHIVE_URL,
            },
            {
                "role": "statutory national EIA database",
                "url": NATIONAL_EIA_URL,
            },
        ],
        "release_id": RELEASE_ID,
        "robots_findings": {
            "ekoportal_archive_host": {
                "robots_location_content_type": "text/html",
                "robots_location_http_status": 200,
                "robots_rule_file_observed": False,
            },
            "national_eia_host": {
                "direct_robots_probe_outcome": "timeout",
                "official_page_declares_access_blocked_outside_poland": True,
            },
            "robots_rule_is_reuse_permission": False,
            "sios_host": {
                "disallow_paths": ["/"],
                "robots_http_status": 200,
                "user_agent": "*",
            },
        },
        "scope_split": {
            "current_gdos_rdos_publication_start": "2025-06-01",
            "current_surface": SIOS_SEARCH_URL,
            "current_surface_is_national_all_authority_register": False,
            "legacy_surface": EKO_ARCHIVE_URL,
            "separate_national_eia_surface": NATIONAL_EIA_URL,
        },
        "web_research_accounting": {
            "browser_proxy_origin_request_count": None,
            "browser_proxy_requests_included_in_direct_audit_count": False,
            "direct_origin_audit_is_the_only_exact_request_ledger": True,
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "administrative_card_status": None,
            "administrative_publication_is_physical_lifecycle": False,
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
        "retained_document_card_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "document_card_count": None,
            "document_count": None,
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
            "status": "robots_rights_coverage_blocked_metadata_only",
        },
        "blockers": {
            "coverage": (
                "SIOS/Ekoportal routing on the GDOŚ page covers GDOŚ and RDOŚ "
                "cards, not all Polish authorities"
            ),
            "national_access": (
                "the statutory national EIA database is officially blocked "
                "outside Poland and both direct probes timed out"
            ),
            "rights": (
                "no common-search result-level reuse scope across publishers "
                "was affirmed"
            ),
            "robots": "SIOS robots disallows / for User-agent: *",
            "semantics": (
                "exact phrase, field coverage, pagination, page size, and "
                "stable sort are undocumented"
            ),
        },
        "coverage": {
            "all_union_rows_classified": False,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_poland": False,
            "document_card_count": None,
            "document_count": None,
            "project_count": None,
            "publication_count": None,
            "query_variants_completed": 0,
            "query_variants_planned": len(SEARCH_TERMS),
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
            "natural_person_fields_retained": False,
            "organization_resolution_performed": False,
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
            "direct_request_attempts": inventory[
                "direct_request_attempts"
            ],
            "failed_timeout_requests": inventory["failed_timeout_requests"],
            "minimum_request_start_interval_seconds": inventory[
                "audit_request_start_interval_seconds"
            ],
            "raw_source_bodies_retained": False,
            "result_bearing_search_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "GDOŚ PDWD, SIOS, Ekoportal archive, and national EIA database",
            "operator": "GDOŚ and publishing authorities; SIOS service by Internet Community",
            "search_url": SIOS_SEARCH_URL,
        },
        "unit_boundary": source_definition()["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""Poland GDOŚ/SIOS/Ekoportal source assessment

Official GDOŚ scope page: {GDOS_PDWD_SCOPE_URL}
Official GDOŚ reuse page: {GDOS_REUSE_URL}
Current public-card search: {SIOS_SEARCH_URL}
SIOS robots policy: {SIOS_ROBOTS_URL}
SIOS terms: {SIOS_TERMS_URL}
Official GDOŚ national EIA description: {GDOS_EIA_DATABASE_PAGE_URL}

This bundle republishes no SIOS or Ekoportal card, result text, export,
document, attachment, applicant field, geometry, or national EIA record. It
contains only the atlas project's audit metadata, hashes, null source counts,
and a gated future literal plan. No source-record licence is asserted.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Poland GDOŚ/SIOS/Ekoportal source assessment

The official GDOŚ page routes GDOŚ and regional-directorate document cards
published from 1 June 2025 to {SIOS_SEARCH_URL}, and older GDOŚ cards to an
Ekoportal archive. This is not an all-authority Polish register. SIOS is a
private hosted publication system used by public bodies.

The empty public SIOS form uses `GET` and exposes a `keywords` field with a
64-character limit, date and location filters, document type/topic selectors,
and `iid=0`. It also displays PDF and XLS export routes. The page documents no
API, exact-phrase behavior, field coverage, pagination parameter, page size,
stable sort, or stateless export contract. No export was requested.

Capture stopped before every result-bearing query. SIOS `robots.txt` returned
`User-agent: *` and `Disallow: /`. The SIOS footer says All Rights Reserved and
its terms identify the service provider as system copyright owner. GDOŚ has a
general public-sector-information reuse page, but it reserves third-party
rights and does not establish a common result-level licence across every SIOS
publisher. This is a conservative operational gate, not a legal conclusion.

The stronger national source is GDOŚ's statutory EIA database. GDOŚ states
that authorities have had a statutory entry duty since 1 January 2017, with
2016 proceedings loaded in 2017, but also states that access from outside
Poland is blocked. Direct home and robots probes from this environment both
timed out. No national EIA search or result request was made.

The gated future plan records the literals `centrum danych`, `centra danych`,
`data center`, and `serwerownia`. They were not submitted because source-side
exact matching is undocumented. If every gate is later cleared, results must
be locally exact-literal postfiltered and every row manually classified.
`serwerownia` is context-sensitive and can never auto-promote a project.

An environmental document card, EIA proceeding, application, decision, or
publication is not evidence that physical construction began. Construction
status, operating status, data-centre type, IT capacity, gross power, PUE, and
annual energy remain null. The release contains zero source rows and cannot
feed the construction master, construction map, or current-coverage ledger.

The controlled audit made exactly 10 direct-origin request attempts, below the
cap of {MAX_DIRECT_REQUEST_ATTEMPTS}, with request starts paced at least
{AUDIT_REQUEST_START_INTERVAL_SECONDS:.1f} seconds apart. Eight returned a
response and two national-EIA probes timed out. Result, export, detail, and
document requests were all zero. Browser-proxy research is disclosed
separately because its origin request count is unavailable and is excluded
from the exact direct-request ledger.

Validate the frozen bundle offline:

```bash
python3 scripts/validate_poland_gdos_sios_ekoportal.py
```

Reproduce all derived files from the pinned audit inventory:

```bash
python3 scripts/build_poland_gdos_sios_ekoportal.py --output /tmp/poland-gdos-release
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise PolandGDOSSIOSAssessmentError(
            "retrieval inventory differs from pinned audit"
        )
    _utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 10:
        raise PolandGDOSSIOSAssessmentError(
            "controlled audit must contain ten direct request attempts"
        )
    if inventory.get("direct_request_attempts") != len(requests):
        raise PolandGDOSSIOSAssessmentError(
            "direct request arithmetic differs"
        )
    if inventory.get("direct_request_attempt_cap") != 40:
        raise PolandGDOSSIOSAssessmentError("direct request cap differs")
    if inventory["direct_request_attempts"] > inventory[
        "direct_request_attempt_cap"
    ]:
        raise PolandGDOSSIOSAssessmentError("direct request cap exceeded")
    if inventory.get("audit_request_start_interval_seconds", 0) < 3.0:
        raise PolandGDOSSIOSAssessmentError("request pacing is below contract")
    if inventory.get("result_bearing_search_requests") != 0:
        raise PolandGDOSSIOSAssessmentError(
            "result-bearing search requests must stay zero"
        )
    for field in (
        "search_export_requests",
        "source_detail_requests",
        "source_document_requests",
    ):
        if inventory.get(field) != 0:
            raise PolandGDOSSIOSAssessmentError(f"{field} must stay zero")
    if inventory.get("search_capture_started") is not False:
        raise PolandGDOSSIOSAssessmentError("search capture must stay unstarted")
    if inventory.get("raw_response_bodies_retained") is not False:
        raise PolandGDOSSIOSAssessmentError("source bodies cannot be retained")
    if inventory.get("analysis_temporary_response_bodies_deleted") is not True:
        raise PolandGDOSSIOSAssessmentError(
            "temporary analysis bodies must be deleted"
        )

    expected_statuses = [200, 200, 200, 200, 200, 200, 301, 200, None, None]
    expected_outcomes = ["response"] * 8 + ["timeout", "timeout"]
    if [row.get("http_status") for row in requests] != expected_statuses:
        raise PolandGDOSSIOSAssessmentError("controlled audit statuses differ")
    if [row.get("outcome") for row in requests] != expected_outcomes:
        raise PolandGDOSSIOSAssessmentError("controlled audit outcomes differ")

    for index, row in enumerate(requests):
        _official_url(row.get("url"), f"request[{index}].url")
        _utc_timestamp(row.get("observed_at"), f"request[{index}].observed_at")
        if (
            row.get("method") != "GET"
            or row.get("body_retained") is not False
            or row.get("redirect_followed") is not False
            or not isinstance(row.get("elapsed_seconds"), (int, float))
            or row["elapsed_seconds"] < 0
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise PolandGDOSSIOSAssessmentError(
                f"controlled request row {index} is invalid"
            )
        if row["outcome"] == "response":
            if (
                not isinstance(row.get("http_status"), int)
                or isinstance(row.get("bytes"), bool)
                or not isinstance(row.get("bytes"), int)
                or row["bytes"] <= 0
                or row.get("response_body_received") is not True
            ):
                raise PolandGDOSSIOSAssessmentError(
                    f"response row {index} is invalid"
                )
        elif (
            row.get("http_status") is not None
            or row.get("bytes") != 0
            or row.get("response_body_received") is not False
            or row.get("error_class") != "timeout"
            or row.get("sha256") != _EMPTY_SHA256
        ):
            raise PolandGDOSSIOSAssessmentError(
                f"timeout row {index} is invalid"
            )

    if inventory.get("completed_response_requests") != 8:
        raise PolandGDOSSIOSAssessmentError("completed response count differs")
    if inventory.get("failed_timeout_requests") != 2:
        raise PolandGDOSSIOSAssessmentError("timeout count differs")
    if inventory["completed_response_requests"] + inventory[
        "failed_timeout_requests"
    ] != inventory["direct_request_attempts"]:
        raise PolandGDOSSIOSAssessmentError("outcome arithmetic differs")
    if requests[4]["sha256"] != (
        "46807e235496ba8d849f071626c6a5ab1"
        "dcc71b17faf8b90419144d940478c1d"
    ):
        raise PolandGDOSSIOSAssessmentError("SIOS robots checkpoint differs")
    if any("keywords=" in row["url"] for row in requests):
        raise PolandGDOSSIOSAssessmentError("a result query was requested")
    if any(
        path in urlsplit(row["url"]).path
        for row in requests
        for path in (SIOS_PDF_EXPORT_PATH, SIOS_XLS_EXPORT_PATH)
    ):
        raise PolandGDOSSIOSAssessmentError("an export route was requested")


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
        raise PolandGDOSSIOSAssessmentError("output already exists")
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
        raise PolandGDOSSIOSAssessmentError(
            f"{label} must be a regular file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolandGDOSSIOSAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise PolandGDOSSIOSAssessmentError(
            f"{label} must contain canonical JSON"
        )
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise PolandGDOSSIOSAssessmentError(
            "release must be a regular directory"
        )
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise PolandGDOSSIOSAssessmentError("release file set differs")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise PolandGDOSSIOSAssessmentError("release cannot contain symlinks")
    if not is_frozen_release(root):
        raise PolandGDOSSIOSAssessmentError("release modes are not frozen")

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise PolandGDOSSIOSAssessmentError(
                f"derived file differs: {name}"
            )

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise PolandGDOSSIOSAssessmentError("manifest inventory differs")
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise PolandGDOSSIOSAssessmentError("manifest sidecar differs")

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise PolandGDOSSIOSAssessmentError(
                "external definition must be a regular file"
            )
        if definition_path.read_bytes() != canonical_json(definition):
            raise PolandGDOSSIOSAssessmentError("external definition differs")

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    if assessment["atlas_decision"]["status"] != (
        "robots_rights_coverage_blocked_metadata_only"
    ):
        raise PolandGDOSSIOSAssessmentError("assessment decision differs")
    if assessment["coverage"]["result_count"] is not None:
        raise PolandGDOSSIOSAssessmentError(
            "unexecuted search result count must be null"
        )
    if assessment["coverage"]["site_count"] is not None:
        raise PolandGDOSSIOSAssessmentError(
            "unexecuted site count must be null"
        )
    if schema["classification_rows"] != [] or (
        root / "observations.jsonl"
    ).read_bytes():
        raise PolandGDOSSIOSAssessmentError(
            "blocked assessment cannot emit source rows"
        )
    if any(row["network_requests"] != 0 for row in plan["rows"]):
        raise PolandGDOSSIOSAssessmentError(
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
