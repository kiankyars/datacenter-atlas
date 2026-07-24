"""Fail-closed Malaysia KPKT OSC 3 Plus source assessment.

KPKT's OSC 3 Plus service publishes municipal calendar and meeting surfaces,
but the bounded audit did not find an affirmative source-record reuse scope.
This lane therefore stops at the rights gate.  It records only access and
rights-audit metadata and does not request PBT calendars or meeting pages.
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
    "malaysia-kpkt-osc3plus-selected-pbt-current-calendar-2026-07-18-v1"
)
RELEASE_FORMAT = "datacenter-atlas-malaysia-kpkt-osc3plus-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-malaysia-kpkt-osc3plus-definition-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-malaysia-kpkt-osc3plus-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-malaysia-kpkt-osc3plus-audit-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-malaysia-kpkt-osc3plus-schema-v1"
SOURCE_INVENTORY_FORMAT = (
    "datacenter-atlas-malaysia-kpkt-osc3plus-source-inventory-v1"
)

START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 7, 18)
CALENDAR_YEAR = 2026
SEARCH_TERMS = (
    "pusat data",
    "data centre",
    "data center",
    "pusat ibu sawat komputer",
)
MIN_REQUEST_INTERVAL_SECONDS = 5.0
MAX_PBT_CALENDAR_REQUESTS = 5
MAX_MEETING_PAGES_PER_PBT = 100
MAX_MEETING_PAGE_REQUESTS = MAX_PBT_CALENDAR_REQUESTS * MAX_MEETING_PAGES_PER_PBT

SERVICE_ORIGIN = "https://osc3plus.kpkt.gov.my"
SERVICE_URL = f"{SERVICE_ORIGIN}/"
ROBOTS_URL = f"{SERVICE_ORIGIN}/robots.txt"
TERMS_URL = f"{SERVICE_ORIGIN}/term&condition"
PRIVACY_URL = f"{SERVICE_ORIGIN}/privacyPolicy"
SECURITY_URL = f"{SERVICE_ORIGIN}/securityPolicy"
DISCLAIMER_URL = f"{SERVICE_ORIGIN}/disclaimer"
DBKL_OSC_URL = "https://osc.dbkl.gov.my/"
DBKL_DASHBOARD_URL = "https://oscdashboardawam.dbkl.gov.my/"
DBKL_DASHBOARD_ROBOTS_URL = "https://oscdashboardawam.dbkl.gov.my/robots.txt"

PBT_ALLOWLIST: tuple[dict[str, str], ...] = (
    {
        "code": "MBJB",
        "country": "Malaysia",
        "local_authority_area": "Johor Bahru",
        "name": "Majlis Bandaraya Johor Bahru",
        "role": "selected PBT; not a Johor completeness boundary",
        "state": "Johor",
        "url": f"{SERVICE_ORIGIN}/pbt/MBJB",
    },
    {
        "code": "MBIP",
        "country": "Malaysia",
        "local_authority_area": "Iskandar Puteri",
        "name": "Majlis Bandaraya Iskandar Puteri",
        "role": "selected PBT; not a Johor completeness boundary",
        "state": "Johor",
        "url": f"{SERVICE_ORIGIN}/pbt/MBIP",
    },
    {
        "code": "MPKu",
        "country": "Malaysia",
        "local_authority_area": "Kulai",
        "name": "Majlis Perbandaran Kulai",
        "role": "selected PBT; not a Johor completeness boundary",
        "state": "Johor",
        "url": f"{SERVICE_ORIGIN}/pbt/MPKu",
    },
    {
        "code": "MBPG",
        "country": "Malaysia",
        "local_authority_area": "Pasir Gudang",
        "name": "Majlis Bandaraya Pasir Gudang",
        "role": "selected PBT; not a Johor completeness boundary",
        "state": "Johor",
        "url": f"{SERVICE_ORIGIN}/pbt/MBPG",
    },
    {
        "code": "MPSep",
        "country": "Malaysia",
        "local_authority_area": "Sepang",
        "name": "Majlis Perbandaran Sepang",
        "role": "selected Cyberjaya comparator; not a DBKL substitute",
        "state": "Selangor",
        "url": f"{SERVICE_ORIGIN}/pbt/MPSep",
    },
)

AUDIT_URLS = (
    SERVICE_URL,
    ROBOTS_URL,
    TERMS_URL,
    PRIVACY_URL,
    SECURITY_URL,
    DISCLAIMER_URL,
)
MEETING_PATH_PATTERN = r"^/takwim/meeting/[1-9][0-9]*$"

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
    "response_date",
    "sha256",
    "url",
}


class MalaysiaKPKTOSC3PlusError(ValueError):
    """Raised when the KPKT OSC 3 Plus assessment fails its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise MalaysiaKPKTOSC3PlusError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MalaysiaKPKTOSC3PlusError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MalaysiaKPKTOSC3PlusError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise MalaysiaKPKTOSC3PlusError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "osc.dbkl.gov.my",
        "osc3plus.kpkt.gov.my",
        "oscdashboardawam.dbkl.gov.my",
    }:
        raise MalaysiaKPKTOSC3PlusError(f"{field} must use an allowed official host")
    return value


RIGHTS_POLICY: dict[str, Any] = {
    "affirmative_automated_reuse_scope_found": False,
    "assessment_metadata_publication_permitted": True,
    "copyright_notice_present_on_service_root": True,
    "legal_conclusion_claimed": False,
    "meeting_or_agenda_metadata_publication_permitted": False,
    "policy_endpoints_available_during_audit": False,
    "raw_source_response_publication_permitted": False,
    "result_or_derived_row_publication_permitted": False,
    "rights_clarification_required_before_pbt_or_meeting_request": True,
    "robots_rule_is_reuse_permission": False,
    "verified_local_date": END_DATE.isoformat(),
    "reason": (
        "The public service and permissive crawl directive establish access, "
        "not a source-record reuse licence. The service root asserted copyright, "
        "and all four linked policy endpoints returned HTTP 500 during the "
        "bounded audit. Source-specific clarification is required before any "
        "PBT calendar or meeting-page request."
    ),
}

DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "explicit_positive_contract_present": False,
    "reason": (
        "rights-gated metadata-only assessment with no agenda observation, "
        "project/site resolution, physical-lifecycle evidence, or metrics"
    ),
}

PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": END_DATE.isoformat(),
    "audit_completed_at": "2026-07-19T04:12:35Z",
    "controlled_audit_requests": 6,
    "controlled_http_requests": [
        {
            "bytes": 14615,
            "content_type": "text/html",
            "http_status": 200,
            "method": "GET",
            "response_date": "2026-07-19T04:12:29Z",
            "sha256": "163082d2802914a9567680ec3f0354ab50105bbc1bd1c39560d5d91cdcd27085",
            "url": SERVICE_URL,
        },
        {
            "bytes": 24,
            "content_type": "text/plain",
            "http_status": 200,
            "method": "GET",
            "response_date": "2026-07-19T04:12:31Z",
            "sha256": "e5c4b84484ee4216e9373be99380320c25dd94805f99f0a805846f087636553f",
            "url": ROBOTS_URL,
        },
        {
            "bytes": 6529,
            "content_type": "text/html",
            "http_status": 500,
            "method": "GET",
            "response_date": "2026-07-19T04:12:31Z",
            "sha256": "4cad6df2ec36aa9b3f84a39cc99bb9729ef5a8569efab06a6c8ac3d609702824",
            "url": TERMS_URL,
        },
        {
            "bytes": 6529,
            "content_type": "text/html",
            "http_status": 500,
            "method": "GET",
            "response_date": "2026-07-19T04:12:32Z",
            "sha256": "4cad6df2ec36aa9b3f84a39cc99bb9729ef5a8569efab06a6c8ac3d609702824",
            "url": PRIVACY_URL,
        },
        {
            "bytes": 6529,
            "content_type": "text/html",
            "http_status": 500,
            "method": "GET",
            "response_date": "2026-07-19T04:12:34Z",
            "sha256": "4cad6df2ec36aa9b3f84a39cc99bb9729ef5a8569efab06a6c8ac3d609702824",
            "url": SECURITY_URL,
        },
        {
            "bytes": 6529,
            "content_type": "text/html",
            "http_status": 500,
            "method": "GET",
            "response_date": "2026-07-19T04:12:35Z",
            "sha256": "4cad6df2ec36aa9b3f84a39cc99bb9729ef5a8569efab06a6c8ac3d609702824",
            "url": DISCLAIMER_URL,
        },
    ],
    "format": RETRIEVAL_FORMAT,
    "meeting_page_requests": 0,
    "pbt_calendar_requests": 0,
    "raw_response_bodies_retained": False,
    "release_id": RELEASE_ID,
    "result_bearing_traversal_requests": 0,
    "source_capture_started": False,
}


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "policy_endpoint_http_statuses": {
                "disclaimer": 500,
                "privacy": 500,
                "security": 500,
                "terms": 500,
            },
            "pbt_calendar_capture_started": False,
            "primary_host_robots_http_status": 200,
            "primary_host_robots_has_empty_generic_disallow": True,
            "root_footer_copyright_notice_present": True,
            "root_footer_copyright_year_end": 2026,
            "service_landing_http_status": 200,
        },
        "coverage_contract": {
            "agenda_presentation_item_count": None,
            "bounded_date_end": END_DATE.isoformat(),
            "bounded_date_start": START_DATE.isoformat(),
            "calendar_event_count": None,
            "calendar_year": CALENDAR_YEAR,
            "complete_for_johor_claimed": False,
            "complete_for_malaysia_claimed": False,
            "complete_for_selangor_claimed": False,
            "geography": (
                "selected local-authority pages in Johor and Selangor, Malaysia"
            ),
            "meeting_page_count": None,
            "pbt_allowlist": [dict(row) for row in PBT_ALLOWLIST],
            "project_count": None,
            "result_count": None,
            "search_terms": list(SEARCH_TERMS),
            "site_count": None,
            "scope_type": "selected_pbt_allowlist",
        },
        "dbkl_coverage_gap": {
            "cyberjaya_is_kuala_lumpur_city": False,
            "dbkl_dashboard_robots_url": DBKL_DASHBOARD_ROBOTS_URL,
            "dbkl_dashboard_url": DBKL_DASHBOARD_URL,
            "dbkl_osc_url": DBKL_OSC_URL,
            "dbkl_requests_performed": 0,
            "dbkl_result_count": None,
            "dbkl_uncovered": True,
            "mpsep_is_dbkl_substitute": False,
            "status": "not_audited_outside_bounded_kpkt_rights_assessment",
        },
        "format": DEFINITION_FORMAT,
        "future_authorized_traversal_contract": {
            "accept_only_allowlisted_pbt_pages": True,
            "calendar_event_date_end_inclusive": END_DATE.isoformat(),
            "calendar_event_date_start_inclusive": START_DATE.isoformat(),
            "calendar_events_source": "inline current-year event objects",
            "discover_meeting_links_from_allowlisted_pages_only": True,
            "exact_literal_casefolded_match_required": True,
            "http_method": "GET",
            "integer_guessing_of_meeting_ids_permitted": False,
            "meeting_path_pattern": MEETING_PATH_PATTERN,
            "observation_key": ["meeting_id", "presentation_ordinal"],
            "observation_unit": "agenda_presentation_item",
            "same_official_origin_required": True,
        },
        "inference_policy": {
            "administrative_meeting_status_is_physical_lifecycle": False,
            "agenda_presentation_item_is_atlas_project": False,
            "agenda_presentation_item_is_atlas_site": False,
            "automatic_entity_merge_permitted": False,
            "automatic_project_merge_permitted": False,
            "automatic_site_merge_permitted": False,
            "data_centre_type": None,
            "physical_lifecycle_status": None,
            "review_only": True,
        },
        "network_policy_if_rights_later_clarified": {
            "maximum_meeting_page_requests": MAX_MEETING_PAGE_REQUESTS,
            "maximum_meeting_pages_per_pbt": MAX_MEETING_PAGES_PER_PBT,
            "maximum_pbt_calendar_requests": MAX_PBT_CALENDAR_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "one_request_at_a_time": True,
            "response_body_hash_required": True,
            "stop_and_null_counts_on_cap_or_error": True,
            "stop_before_first_pbt_request_unless_rights_gate_is_affirmative": True,
        },
        "publisher": "Kementerian Perumahan dan Kerajaan Tempatan (KPKT)",
        "release_id": RELEASE_ID,
        "retention": {
            "agenda_or_meeting_items_retained": False,
            "applicant_fields_retained": False,
            "contact_fields_retained": False,
            "derived_rows_retained": False,
            "personal_data_retained": False,
            "raw_html_or_excerpts_retained": False,
            "raw_response_bodies_retained": False,
            "result_titles_or_descriptions_retained": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "malaysia-kpkt-osc3plus-current-calendar",
        "source_urls": {
            "disclaimer": DISCLAIMER_URL,
            "privacy": PRIVACY_URL,
            "robots": ROBOTS_URL,
            "security": SECURITY_URL,
            "service": SERVICE_URL,
            "terms": TERMS_URL,
        },
        "title": (
            "Malaysia KPKT OSC 3 Plus selected-PBT access and rights assessment"
        ),
        "unit_contract": {
            "administrative_status_is_physical_lifecycle": False,
            "agenda_presentation_item_is_atlas_project": False,
            "agenda_presentation_item_is_atlas_site": False,
            "agenda_presentation_item_count": None,
            "calendar_event_count": None,
            "meeting_page_count": None,
            "project_count": None,
            "result_count": None,
            "site_count": None,
            "source_observation_unit": "agenda_presentation_item",
        },
    }


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, pbt in enumerate(PBT_ALLOWLIST, 1):
        rows.append(
            {
                "agenda_presentation_item_count": None,
                "calendar_event_count": None,
                "classification_counts": {
                    "ancillary_or_context": None,
                    "direct_data_centre_project": None,
                    "excluded": None,
                },
                "meeting_page_count": None,
                "meeting_page_network_requests": 0,
                "pbt_calendar_network_requests": 0,
                "pbt_code": pbt["code"],
                "pbt_url": pbt["url"],
                "query_id": f"pbt{index:02d}",
                "result_count": None,
                "state": pbt["state"],
                "status": "not_executed_rights_scope_not_affirmed",
            }
        )
    return {
        "classification_contract": {
            "ancillary_or_context": (
                "the agenda item mentions a data centre only as infrastructure "
                "context or concerns an ancillary work"
            ),
            "direct_data_centre_project": (
                "the agenda item itself concerns a data-centre build or expansion"
            ),
            "excluded": "the literal has no data-centre project relevance",
        },
        "date_end_inclusive_local": END_DATE.isoformat(),
        "date_start_inclusive_local": START_DATE.isoformat(),
        "deduplication_if_executed": (
            "exact (meeting_id, presentation_ordinal) only"
        ),
        "format": QUERY_PLAN_FORMAT,
        "http_method": "GET",
        "meeting_path_pattern": MEETING_PATH_PATTERN,
        "release_id": RELEASE_ID,
        "rows": rows,
        "search_terms": list(SEARCH_TERMS),
        "union": {
            "agenda_presentation_item_count": None,
            "all_rows_classified": False,
            "calendar_event_count": None,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "closed_union_sha256": None,
            "meeting_page_count": None,
            "project_count": None,
            "result_count": None,
            "site_count": None,
            "status": "not_built_rights_scope_not_affirmed",
        },
    }


def source_inventory_document() -> dict[str, Any]:
    return {
        "audited_official_sources": [
            {"role": "service root and footer rights surface", "url": SERVICE_URL},
            {"role": "service robots policy", "url": ROBOTS_URL},
            {"role": "linked terms endpoint; returned HTTP 500", "url": TERMS_URL},
            {
                "role": "linked privacy endpoint; returned HTTP 500",
                "url": PRIVACY_URL,
            },
            {
                "role": "linked security endpoint; returned HTTP 500",
                "url": SECURITY_URL,
            },
            {
                "role": "linked disclaimer endpoint; returned HTTP 500",
                "url": DISCLAIMER_URL,
            },
        ],
        "dbkl_uncovered_gap": {
            "dbkl_dashboard_robots_url": DBKL_DASHBOARD_ROBOTS_URL,
            "dbkl_dashboard_url": DBKL_DASHBOARD_URL,
            "dbkl_osc_url": DBKL_OSC_URL,
            "network_requests": 0,
            "result_count": None,
            "status": "not_audited_and_not_substituted_by_mpsep",
        },
        "format": SOURCE_INVENTORY_FORMAT,
        "future_authorized_pbt_sources": [dict(row) for row in PBT_ALLOWLIST],
        "jurisdiction_scope": {
            "complete_for_johor": False,
            "complete_for_malaysia": False,
            "complete_for_selangor": False,
            "scope_type": "selected_pbt_allowlist",
        },
        "release_id": RELEASE_ID,
        "rights_surface_findings": {
            "affirmative_reuse_scope_found": False,
            "copyright_notice_present_on_service_root": True,
            "policy_endpoint_statuses": [500, 500, 500, 500],
            "raw_footer_or_policy_text_retained": False,
        },
        "robots_findings": {
            "generic_user_agent_group_present": True,
            "generic_disallow_value_empty": True,
            "robots_http_status": 200,
            "robots_rule_is_reuse_permission": False,
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "administrative_calendar_or_meeting_status": None,
            "administrative_status_is_physical_lifecycle": False,
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
        "retained_agenda_observation_rows": 0,
        "retained_classification_rows": 0,
        "retained_derived_rows": 0,
        "schema_version": SCHEMA_VERSION,
        "source_counts": {
            "agenda_presentation_item_count": None,
            "calendar_event_count": None,
            "meeting_page_count": None,
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
            "status": "rights_scope_unconfirmed_metadata_only",
        },
        "coverage": {
            "agenda_presentation_item_count": None,
            "all_union_rows_classified": False,
            "calendar_event_count": None,
            "classification_counts": {
                "ancillary_or_context": None,
                "direct_data_centre_project": None,
                "excluded": None,
            },
            "complete_for_johor": False,
            "complete_for_malaysia": False,
            "complete_for_selangor": False,
            "date_end": END_DATE.isoformat(),
            "date_start": START_DATE.isoformat(),
            "meeting_page_count": None,
            "pbt_pages_completed": 0,
            "pbt_pages_planned": len(PBT_ALLOWLIST),
            "project_count": None,
            "result_count": None,
            "site_count": None,
            "source_union_sha256": None,
        },
        "dbkl_coverage_gap": source_definition()["dbkl_coverage_gap"],
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": schema_document()["lifecycle_contract"],
        "metric_boundary": schema_document()["metric_contract"],
        "pii_policy": {
            "applicant_capture_performed": False,
            "contacts_retained": False,
            "meeting_items_retained": False,
            "natural_person_data_retained": False,
            "organization_resolution_performed": False,
        },
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "audit_metadata_sha256": sha256_bytes(canonical_json(inventory)),
            "controlled_audit_requests": inventory["controlled_audit_requests"],
            "meeting_page_requests": inventory["meeting_page_requests"],
            "pbt_calendar_requests": inventory["pbt_calendar_requests"],
            "raw_source_bodies_retained": False,
            "result_bearing_traversal_requests": inventory[
                "result_bearing_traversal_requests"
            ],
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "OSC 3 Plus Online",
            "operator": "Kementerian Perumahan dan Kerajaan Tempatan",
            "service_url": SERVICE_URL,
        },
        "unit_boundary": source_definition()["unit_contract"],
    }


def attribution_bytes() -> bytes:
    return f"""Malaysia KPKT OSC 3 Plus access assessment

Official service: {SERVICE_URL}
Robots policy: {ROBOTS_URL}

This bundle republishes no KPKT or PBT calendar events, meeting pages, agenda
items, result titles, applicants, contacts, personal data, raw HTML, excerpts,
or derived source rows. It contains only the atlas project's audit metadata,
response hashes, null coverage findings, and a future rights-gated query plan.
No source-record reuse licence is asserted.
""".encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Malaysia KPKT OSC 3 Plus source assessment

The official service is KPKT's OSC 3 Plus at {SERVICE_URL}. A bounded audit
requested only the service root, its robots file, and four linked policy
endpoints. The service root and robots file returned HTTP 200. Each policy
endpoint returned HTTP 500. The root asserted copyright, while robots exposed
an empty generic disallow directive. Crawl access is not treated as reuse
permission.

The rights gate stopped the run before every PBT calendar and meeting page.
The predeclared future allowlist is MBJB, MBIP, MPKu, MBPG, and MPSep. MPSep is
an outside-Johor Cyberjaya comparator and is not a substitute for Kuala Lumpur
city or DBKL. DBKL remains an explicit uncovered gap.

If rights are later clarified, each allowlisted PBT page may be requested once
for inline 2026 calendar events dated no later than 2026-07-18. Meeting pages
may be followed only when a same-origin link is discovered from an allowlisted
page and its path matches `{MEETING_PATH_PATTERN}`. Integer guessing is
forbidden. The exact literals are `pusat data`, `data centre`, `data center`,
and `pusat ibu sawat komputer`. The source observation unit would be one agenda
presentation item keyed by exact meeting ID and presentation ordinal.

No source traversal occurred, so result, event, meeting-page, agenda-item,
classification, project, site, and source metric-statement counts remain null.
Exact retained row counts are zero. An agenda item or administrative meeting
status is not a physical project, site, construction milestone, or operating
status. No data-centre type, power, PUE, or energy value is emitted.

This assessment cannot feed the construction master, map, or current-coverage
ledger. The frozen bundle uses directory mode `0555` and file mode `0444`.
Validate it without network access:

```bash
python3 scripts/validate_malaysia_kpkt_osc3plus.py
```

Reproduce all derived files from pinned audit metadata in a separate directory:

```bash
python3 scripts/build_malaysia_kpkt_osc3plus.py --output /tmp/malaysia-kpkt-release
```
""".encode("utf-8")


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise MalaysiaKPKTOSC3PlusError(
            "retrieval inventory differs from pinned audit"
        )
    _utc_timestamp(inventory.get("audit_completed_at"), "audit_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 6:
        raise MalaysiaKPKTOSC3PlusError(
            "controlled audit must contain six requests"
        )
    if inventory.get("controlled_audit_requests") != len(requests):
        raise MalaysiaKPKTOSC3PlusError("controlled audit arithmetic differs")
    if inventory.get("result_bearing_traversal_requests") != 0:
        raise MalaysiaKPKTOSC3PlusError(
            "result-bearing traversal requests must stay zero"
        )
    if inventory.get("pbt_calendar_requests") != 0:
        raise MalaysiaKPKTOSC3PlusError("PBT calendar requests must stay zero")
    if inventory.get("meeting_page_requests") != 0:
        raise MalaysiaKPKTOSC3PlusError("meeting page requests must stay zero")
    if inventory.get("source_capture_started") is not False:
        raise MalaysiaKPKTOSC3PlusError("source capture must stay unstarted")
    if inventory.get("raw_response_bodies_retained") is not False:
        raise MalaysiaKPKTOSC3PlusError("raw source bodies cannot be retained")

    expected_statuses = [200, 200, 500, 500, 500, 500]
    expected_content_types = [
        "text/html",
        "text/plain",
        "text/html",
        "text/html",
        "text/html",
        "text/html",
    ]
    expected_bytes = [14615, 24, 6529, 6529, 6529, 6529]
    for index, row in enumerate(requests):
        if set(row) != _AUDIT_ROW_KEYS:
            raise MalaysiaKPKTOSC3PlusError(
                f"request audit row {index} fields differ"
            )
        _official_url(row.get("url"), f"request[{index}].url")
        _utc_timestamp(row.get("response_date"), f"request[{index}].response_date")
        if (
            row.get("method") != "GET"
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or isinstance(row.get("http_status"), bool)
            or not isinstance(row.get("http_status"), int)
            or not isinstance(row.get("content_type"), str)
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise MalaysiaKPKTOSC3PlusError(
                f"request audit row {index} is invalid"
            )
    if [row["url"] for row in requests] != list(AUDIT_URLS):
        raise MalaysiaKPKTOSC3PlusError("controlled audit URL order differs")
    if [row["http_status"] for row in requests] != expected_statuses:
        raise MalaysiaKPKTOSC3PlusError("controlled audit statuses differ")
    if [row["content_type"] for row in requests] != expected_content_types:
        raise MalaysiaKPKTOSC3PlusError("controlled audit content types differ")
    if [row["bytes"] for row in requests] != expected_bytes:
        raise MalaysiaKPKTOSC3PlusError("controlled audit byte counts differ")


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
        raise MalaysiaKPKTOSC3PlusError("output already exists")
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
        raise MalaysiaKPKTOSC3PlusError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MalaysiaKPKTOSC3PlusError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise MalaysiaKPKTOSC3PlusError(f"{label} must contain canonical JSON")
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise MalaysiaKPKTOSC3PlusError("release must be a regular directory")
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise MalaysiaKPKTOSC3PlusError("release file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in root.rglob("*")):
        raise MalaysiaKPKTOSC3PlusError(
            "release entries must be regular files without symlinks"
        )
    if not is_frozen_release(root):
        raise MalaysiaKPKTOSC3PlusError("release modes are not frozen")

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise MalaysiaKPKTOSC3PlusError(f"derived file differs: {name}")

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise MalaysiaKPKTOSC3PlusError("manifest inventory differs")
    sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != sidecar:
        raise MalaysiaKPKTOSC3PlusError("manifest sidecar differs")

    definition = _load_canonical_json(root / "definition.json", "definition")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise MalaysiaKPKTOSC3PlusError(
                "external definition must be a regular file"
            )
        if definition_path.read_bytes() != canonical_json(definition):
            raise MalaysiaKPKTOSC3PlusError("external definition differs")

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    plan = _load_canonical_json(root / "query-plan.json", "query plan")
    if assessment["atlas_decision"]["status"] != (
        "rights_scope_unconfirmed_metadata_only"
    ):
        raise MalaysiaKPKTOSC3PlusError("assessment decision differs")
    nullable_counts = (
        "agenda_presentation_item_count",
        "calendar_event_count",
        "meeting_page_count",
        "project_count",
        "result_count",
        "site_count",
    )
    if any(assessment["coverage"][field] is not None for field in nullable_counts):
        raise MalaysiaKPKTOSC3PlusError(
            "unexecuted traversal source counts must be null"
        )
    if any(
        value is not None
        for value in assessment["coverage"]["classification_counts"].values()
    ):
        raise MalaysiaKPKTOSC3PlusError(
            "unexecuted traversal classification counts must be null"
        )
    if (
        schema["classification_rows"] != []
        or schema["retained_agenda_observation_rows"] != 0
        or schema["retained_classification_rows"] != 0
        or schema["retained_derived_rows"] != 0
        or schema["metric_contract"]["retained_metric_rows"] != 0
        or (root / "observations.jsonl").read_bytes()
    ):
        raise MalaysiaKPKTOSC3PlusError(
            "rights-gated assessment cannot emit source or derived rows"
        )
    if any(
        row["pbt_calendar_network_requests"] != 0
        or row["meeting_page_network_requests"] != 0
        for row in plan["rows"]
    ):
        raise MalaysiaKPKTOSC3PlusError("query plan must remain unexecuted")
    permission_keys = (
        "construction_map_import_permitted",
        "construction_master_import_permitted",
        "current_coverage_ledger_import_permitted",
        "explicit_positive_contract_present",
    )
    if any(DOWNSTREAM_IMPORT_POLICY[key] for key in permission_keys):
        raise MalaysiaKPKTOSC3PlusError("downstream import policy differs")
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
