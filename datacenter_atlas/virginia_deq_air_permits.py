"""Validate and rebuild the frozen Virginia DEQ air-permit evidence lane.

The lane is intentionally review-only.  An issued air permit is permit evidence,
not proof that a data centre is planned, under construction, or operating.  The
source rights assessment also prohibits publishing the derived records or raw
Virginia DEQ documents from this bundle.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
from urllib.parse import urlsplit


ASSESSMENT_FILENAME = "assessment.json"
ISSUED_PERMITS_FILENAME = "issued_permits.json"
APPLICATIONS_FILENAME = "applications.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-source-rights-assessment-v1"
ISSUED_PERMITS_FORMAT = (
    "datacenter-atlas-virginia-deq-issued-air-permits-v1"
)
APPLICATIONS_FORMAT = "datacenter-atlas-virginia-deq-air-applications-v1"
ASSESSMENT_ID = "virginia-deq-air-permits-2026-07-13-v1"
SOURCE_FAMILY = "virginia_deq_air_permits"
SNAPSHOT_DATE = "2026-07-13"
GENERATED_AT = "2026-07-18T22:25:00Z"

ISSUED_PAGE_URL = (
    "https://www.deq.virginia.gov/news-info/shortcuts/permits/air/"
    "issued-air-permits-for-data-centers"
)
RASPBERRY_PAGE_URL = (
    "https://www.deq.virginia.gov/news-info/shortcuts/topics-of-interest/"
    "google-s-project-raspberry"
)
TERMS_URL = "https://www.deq.virginia.gov/news-info/about-us/terms-of-use"
SOURCE_HEADING = "Issued Air Permits for Data Centers as of 7/13/2026"

ISSUED_ROWS = 198
WIDGET_ROWS = 194
APPLICATION_ROWS = 1
_OFFICIAL_HOST = "www.deq.virginia.gov"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    ISSUED_PERMITS_FILENAME,
    APPLICATIONS_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_EXPECTED_DOCUMENT_HASHES = {
    ASSESSMENT_FILENAME: (
        "e51aa4ab07d822d995dd030f725f01ca75fe40bbb378d8b9adc6b960ca69fe39"
    ),
    ISSUED_PERMITS_FILENAME: (
        "c15c349c1e4110d769c09d44928c1aa7b38b1d70d18cd4bf3d54b0040a11b493"
    ),
    APPLICATIONS_FILENAME: (
        "ff4caf6b01fe89223eb9f093bcbc1cd4bbb78a4ca4e80bc0f9070439fd426d21"
    ),
}

_EXPECTED_SOURCE = {
    "issued_permits_page": ISSUED_PAGE_URL,
    "name": "Virginia Department of Environmental Quality data-center air permits",
    "project_raspberry_page": RASPBERRY_PAGE_URL,
    "snapshot_date": SNAPSHOT_DATE,
    "snapshot_heading": SOURCE_HEADING,
    "source_family": SOURCE_FAMILY,
    "terms_url": TERMS_URL,
}
_EXPECTED_RIGHTS = {
    "affirmative_redistribution_license_found": False,
    "all_rights_reserved_notice_present": True,
    "derived_record_publication_permitted": False,
    "legal_conclusion_claimed": False,
    "public_access_is_reuse_license": False,
    "raw_html_retention_in_release_permitted": False,
    "raw_permit_or_application_document_retention_in_release_permitted": False,
    "terms_notice": (
        "All contents of the Virginia Department of Environmental Quality Web "
        "Site are: and/or its suppliers. All rights reserved."
    ),
    "third_party_or_applicant_document_rights_may_differ": True,
}
_EXPECTED_ACCESS = {
    "application_document_links_inventoried": 8,
    "browser_text_access_available": True,
    "document_body_parsing_performed": False,
    "issued_permit_document_links_inventoried_rows": ISSUED_ROWS,
    "raw_document_fetch_performed": False,
    "source_page_snapshot_date": SNAPSHOT_DATE,
    "unattended_http_access_reliable": False,
    "unattended_http_probe_status": 403,
}
_EXPECTED_COVERAGE = {
    "application_document_links": 8,
    "application_under_review_rows": APPLICATION_ROWS,
    "construction_verified_rows": 0,
    "distinct_resolved_issued_permit_document_urls": 196,
    "issued_permit_rows": ISSUED_ROWS,
    "page_widget_reported_rows": WIDGET_ROWS,
    "parsed_table_rows": ISSUED_ROWS,
    "publication_eligible_rows": 0,
    "resolved_issued_permit_document_row_urls": 197,
    "shared_issued_permit_document_url_rows": 2,
    "status_counts": {
        "application_under_review": APPLICATION_ROWS,
        "issued_permit": ISSUED_ROWS,
    },
    "typed_facility_capacity_rows": 0,
    "typed_facility_energy_rows": 0,
    "unique_physical_site_count": None,
    "unresolved_issued_permit_document_row_urls": 1,
    "virginia_completeness_claimed": False,
}
_EXPECTED_DECISION = {
    "application_lane_separate_from_issued_permits": True,
    "auto_merge_permitted": False,
    "construction_status_promotion_permitted": False,
    "issued_permit_table_captured": True,
    "publication_eligible": False,
    "raw_release_permitted": False,
    "source_family": SOURCE_FAMILY,
    "status": "rights_blocked_local_review_only",
    "typed_facility_metric_promotion_permitted": False,
}
_INFERENCE_BANS = {
    "do_not_assign_air_permit_status_to_atlas_lifecycle",
    "do_not_convert_or_sum_generator_kwe_into_facility_mw",
    "do_not_infer_annual_energy_from_generator_nameplate_or_operating_limits",
    "do_not_merge_records_sharing_a_registration_number",
    "do_not_mix_under_review_applications_with_issued_permits",
    "do_not_treat_issued_air_permit_as_construction_or_operation_proof",
    "do_not_treat_page_row_count_as_unique_physical_sites",
}
_DUPLICATE_REGISTRATIONS = {
    "21527",
    "71804",
    "73200",
    "73370",
    "73643",
    "73670",
    "73717",
    "73977",
}
_EXPECTED_PROGRAM_COUNTS = {
    "Article 1 - Title V": 2,
    "Article 5 - SOP": 6,
    "Article 6 - mNSR": 190,
}
_EXPECTED_REGION_COUNTS = {
    "Northern": 171,
    "Piedmont": 22,
    "Southwest": 2,
    "Tidewater": 1,
    "Valley": 2,
}
_SHARED_DOCUMENT_URL = (
    "https://www.deq.virginia.gov/home/showpublisheddocument/"
    "35458/639105417604630000"
)
_ISSUED_RECORD_KEYS = {
    "annual_energy_mwh",
    "atlas_lifecycle_status",
    "auto_merge_permitted",
    "construction_verified",
    "data_center_type",
    "document_bytes",
    "document_checkpoint_status",
    "document_sha256",
    "facility_operational_status",
    "gross_power_capacity_mw",
    "issuance_date_iso",
    "issuance_date_parse_status",
    "issuance_date_source",
    "it_load_mw",
    "locality",
    "operating_model",
    "operational_workload",
    "permit_action_number",
    "permit_document_url",
    "permit_document_url_status",
    "permit_evidence_only",
    "program_type_normalized",
    "program_type_source",
    "publication_eligible",
    "pue",
    "record_key",
    "record_status",
    "regional_office",
    "registration_number",
    "registration_or_application_id",
    "review_only",
    "site_name",
    "source_page_snapshot_date",
    "source_page_url",
    "source_row_number",
}
_ISSUED_NULL_FIELDS = {
    "annual_energy_mwh",
    "atlas_lifecycle_status",
    "data_center_type",
    "document_bytes",
    "document_sha256",
    "facility_operational_status",
    "gross_power_capacity_mw",
    "it_load_mw",
    "operating_model",
    "operational_workload",
    "pue",
}
_APPLICATION_RECORD_KEYS = {
    "aggregate_generator_count",
    "aggregate_generator_nameplate",
    "annual_energy_mwh",
    "applicant",
    "application_documents",
    "application_received_date",
    "application_status",
    "associated_company",
    "atlas_lifecycle_status",
    "auto_merge_permitted",
    "construction_verified",
    "data_center_building_count_source_stated",
    "facility_operational_status",
    "generator_metrics",
    "generator_metrics_source",
    "gross_power_capacity_mw",
    "it_load_mw",
    "locality",
    "location_text",
    "operating_limit_proposals",
    "operational_workload",
    "permit_document_parsing_performed",
    "program_type",
    "project_name",
    "publication_eligible",
    "pue",
    "record_key",
    "record_status",
    "regional_office",
    "registration_number",
    "registration_or_application_id",
    "review_only",
    "source_page_observed_date",
    "source_page_url",
    "source_section",
    "source_status_text",
    "total_generator_electrical_nameplate_mw",
    "unique_physical_site_count",
}
_APPLICATION_NULL_FIELDS = {
    "aggregate_generator_count",
    "aggregate_generator_nameplate",
    "annual_energy_mwh",
    "atlas_lifecycle_status",
    "facility_operational_status",
    "gross_power_capacity_mw",
    "it_load_mw",
    "operational_workload",
    "pue",
    "total_generator_electrical_nameplate_mw",
    "unique_physical_site_count",
}
_GENERATOR_SIGNATURES = [
    (114, "critical_emergency_engine_generator", "=", 2750, "=", 4043),
    (6, "critical_emergency_engine_generator", "=", 1750, "=", 2584),
    (2, "emergency_diesel_fire_pump", None, None, "<", 750),
    (1, "emergency_generator_booster_pump", "=", 1000, "<", 1500),
    (1, "emergency_generator_hub", "=", 1000, "=", 1500),
    (1, "emergency_generator_site_entrance_booth", "<", 560, "<", 750),
]


class VirginiaDEQAirPermitsError(ValueError):
    """Raised when the Virginia DEQ lane fails its conservative contract."""


def canonical_json(value: Any) -> bytes:
    """Return the canonical JSON representation used by the frozen bundle."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VirginiaDEQAirPermitsError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise VirginiaDEQAirPermitsError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise VirginiaDEQAirPermitsError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VirginiaDEQAirPermitsError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise VirginiaDEQAirPermitsError(f"{label} must be a regular file")
    try:
        body = path.read_bytes()
        value = json.loads(body)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VirginiaDEQAirPermitsError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise VirginiaDEQAirPermitsError(f"{label} must contain an object")
    if body != canonical_json(value):
        raise VirginiaDEQAirPermitsError(f"{label} is not canonical JSON")
    return value


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise VirginiaDEQAirPermitsError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != _OFFICIAL_HOST:
        raise VirginiaDEQAirPermitsError(
            f"{field} must use the official Virginia DEQ HTTPS host"
        )
    return value


def _exact_document_hash(document: Mapping[str, Any], filename: str) -> None:
    digest = sha256_bytes(canonical_json(document))
    if digest != _EXPECTED_DOCUMENT_HASHES[filename]:
        raise VirginiaDEQAirPermitsError(
            f"{filename} differs from the frozen source assessment"
        )


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact rights, access, coverage, and inference boundary."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise VirginiaDEQAirPermitsError("assessment identity is invalid")
    if _timestamp(document.get("assessed_at"), "assessed_at") != GENERATED_AT:
        raise VirginiaDEQAirPermitsError("assessment timestamp changed")
    if document.get("source") != _EXPECTED_SOURCE:
        raise VirginiaDEQAirPermitsError("source identity changed")
    if document.get("rights_assessment") != _EXPECTED_RIGHTS:
        raise VirginiaDEQAirPermitsError("Virginia DEQ rights must fail closed")
    if document.get("access_assessment") != _EXPECTED_ACCESS:
        raise VirginiaDEQAirPermitsError("access and PDF parsing boundary changed")
    if document.get("coverage_assessment") != _EXPECTED_COVERAGE:
        raise VirginiaDEQAirPermitsError("coverage or status counts changed")
    if document.get("atlas_decision") != _EXPECTED_DECISION:
        raise VirginiaDEQAirPermitsError("Atlas decision changed")

    fields = _object(document.get("field_assessment"), "field_assessment")
    if (
        fields.get("application_page_generator_metrics_source_typed") is not True
        or fields.get("application_pdf_generator_metrics_parsed") is not False
        or fields.get("issued_permit_is_construction_verification") is not False
        or fields.get("permit_document_generator_metrics_parsed") is not False
        or fields.get("permit_document_nameplate_is_facility_or_it_load")
        is not False
    ):
        raise VirginiaDEQAirPermitsError("field promotion boundary changed")
    unsupported = fields.get("unsupported_or_unverified_atlas_fields")
    if not isinstance(unsupported, list) or set(unsupported) != {
        "annual_energy_mwh",
        "construction_lifecycle_status",
        "data_center_type",
        "gross_power_capacity_mw",
        "it_load_mw",
        "operating_model",
        "operational_workload",
        "pue",
        "unique_physical_site_count",
    }:
        raise VirginiaDEQAirPermitsError("unsupported Atlas field set changed")
    bans = document.get("inference_bans")
    if not isinstance(bans, list) or set(bans) != _INFERENCE_BANS:
        raise VirginiaDEQAirPermitsError("inference bans changed")

    reconciliation = _object(
        document.get("table_reconciliation"), "table_reconciliation"
    )
    if (
        reconciliation.get("page_widget_reported_rows") != WIDGET_ROWS
        or reconciliation.get("parsed_table_rows") != ISSUED_ROWS
        or reconciliation.get("count_discrepancy_preserved") is not True
        or reconciliation.get("document_link_anomalies")
        != [
            {
                "registration_or_application_id": "74063-5",
                "status": "official_link_unresolved",
            },
            {
                "registration_or_application_id": "74333-1",
                "shares_document_url_with": "74331-1",
                "status": "shared_official_url",
            },
        ]
    ):
        raise VirginiaDEQAirPermitsError("table reconciliation changed")

    observations = document.get("official_observations")
    if not isinstance(observations, list) or len(observations) != 3:
        raise VirginiaDEQAirPermitsError("official observation set changed")
    for raw in observations:
        observation = _object(raw, "official observation")
        _official_url(observation.get("url"), "observation URL")
        if (
            observation.get("publisher") != "Virginia DEQ"
            or observation.get("http_status") != 200
            or observation.get("retrieval_channel") != "browser_text"
            or observation.get("raw_artifact_retained") is not False
            or observation.get("raw_bytes") is not None
            or observation.get("raw_sha256") is not None
        ):
            raise VirginiaDEQAirPermitsError(
                "official observation must remain derived-facts-only"
            )
        if _timestamp(observation.get("observed_at"), "observed_at") > GENERATED_AT:
            raise VirginiaDEQAirPermitsError("observation postdates assessment")

    probes = document.get("unattended_http_probes")
    if not isinstance(probes, list) or len(probes) != 3:
        raise VirginiaDEQAirPermitsError("unattended probe set changed")
    for raw in probes:
        probe = _object(raw, "unattended probe")
        if (
            probe.get("http_status") != 403
            or probe.get("probe_response_is_source_content") is not False
            or isinstance(probe.get("bytes"), bool)
            or not isinstance(probe.get("bytes"), int)
            or probe.get("bytes") <= 0
            or not isinstance(probe.get("sha256"), str)
            or not _SHA256_RE.fullmatch(probe["sha256"])
        ):
            raise VirginiaDEQAirPermitsError("unattended probe semantics changed")
        if _timestamp(probe.get("probed_at"), "probed_at") > GENERATED_AT:
            raise VirginiaDEQAirPermitsError("probe postdates assessment")
    _exact_document_hash(document, ASSESSMENT_FILENAME)


def _validate_issued_date(record: Mapping[str, Any]) -> None:
    permit_id = record.get("registration_or_application_id")
    if permit_id == "74333-1":
        if (
            record.get("issuance_date_source") != "03/26-2026"
            or record.get("issuance_date_iso") is not None
            or record.get("issuance_date_parse_status") != "source_format_anomaly"
        ):
            raise VirginiaDEQAirPermitsError("source date anomaly was not preserved")
        return
    source_date = record.get("issuance_date_source")
    if not isinstance(source_date, str):
        raise VirginiaDEQAirPermitsError("issuance source date must be text")
    try:
        parsed = datetime.strptime(source_date, "%m/%d/%Y")
    except ValueError as error:
        raise VirginiaDEQAirPermitsError("unexpected issuance date format") from error
    if (
        record.get("issuance_date_iso") != parsed.date().isoformat()
        or record.get("issuance_date_parse_status") != "exact_mm_dd_yyyy"
    ):
        raise VirginiaDEQAirPermitsError("issuance date normalization changed")


def _validate_duplicate_groups(
    groups: Any, records: list[Mapping[str, Any]]
) -> None:
    if not isinstance(groups, list) or len(groups) != len(_DUPLICATE_REGISTRATIONS):
        raise VirginiaDEQAirPermitsError("possible-duplicate group set changed")
    by_registration: dict[str, list[str]] = defaultdict(list)
    for record in records:
        by_registration[str(record["registration_number"])].append(
            str(record["record_key"])
        )
    repeated = {key for key, values in by_registration.items() if len(values) > 1}
    if repeated != _DUPLICATE_REGISTRATIONS:
        raise VirginiaDEQAirPermitsError("repeated registration set changed")
    seen: set[str] = set()
    for raw in groups:
        group = _object(raw, "possible duplicate group")
        registration = group.get("registration_number")
        if not isinstance(registration, str) or registration in seen:
            raise VirginiaDEQAirPermitsError("duplicate registration group invalid")
        seen.add(registration)
        if (
            registration not in _DUPLICATE_REGISTRATIONS
            or group.get("group_id")
            != f"va-deq-registration-{registration}"
            or group.get("basis")
            != "same_registration_number_different_permit_action"
            or group.get("record_keys") != by_registration[registration]
            or group.get("merge_approved") is not False
            or group.get("review_only") is not True
        ):
            raise VirginiaDEQAirPermitsError(
                "possible duplicate must remain review-only and unmerged"
            )


def validate_issued_permits_document(document: Mapping[str, Any]) -> None:
    """Validate all 198 issued-permit evidence rows without lifecycle promotion."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ISSUED_PERMITS_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
        or document.get("source_family") != SOURCE_FAMILY
    ):
        raise VirginiaDEQAirPermitsError("issued-permit identity is invalid")
    if _timestamp(document.get("generated_at"), "generated_at") != GENERATED_AT:
        raise VirginiaDEQAirPermitsError("issued-permit timestamp changed")
    if (
        document.get("source_heading") != SOURCE_HEADING
        or document.get("source_page_snapshot_date") != SNAPSHOT_DATE
        or document.get("source_page_url") != ISSUED_PAGE_URL
        or document.get("publication_eligible") is not False
        or document.get("raw_source_artifacts_retained") is not False
        or document.get("review_only") is not True
        or document.get("unique_physical_site_count") is not None
    ):
        raise VirginiaDEQAirPermitsError("issued table must remain local review-only")
    if document.get("count_reconciliation") != {
        "count_discrepancy_preserved": True,
        "page_widget_reported_rows": WIDGET_ROWS,
        "parsed_table_rows": ISSUED_ROWS,
    }:
        raise VirginiaDEQAirPermitsError("issued row-count discrepancy changed")
    if document.get("document_inventory") != {
        "distinct_resolved_urls": 196,
        "resolved_row_urls": 197,
        "shared_url_rows": 2,
        "unresolved_row_urls": 1,
    }:
        raise VirginiaDEQAirPermitsError("permit document inventory changed")

    raw_records = document.get("records")
    if not isinstance(raw_records, list) or len(raw_records) != ISSUED_ROWS:
        raise VirginiaDEQAirPermitsError("issued table must contain 198 rows")
    records: list[Mapping[str, Any]] = []
    ids: list[str] = []
    keys: list[str] = []
    urls: list[str] = []
    url_statuses: Counter[str] = Counter()
    program_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    for index, raw in enumerate(raw_records, start=1):
        record = _object(raw, f"records[{index - 1}]")
        records.append(record)
        if set(record) != _ISSUED_RECORD_KEYS:
            raise VirginiaDEQAirPermitsError("issued record field set changed")
        permit_id = record.get("registration_or_application_id")
        registration = record.get("registration_number")
        action = record.get("permit_action_number")
        if (
            not all(isinstance(value, str) and value for value in (permit_id, registration, action))
            or permit_id != f"{registration}-{action}"
            or record.get("record_key")
            != f"virginia-deq-air-permit:{permit_id}"
            or record.get("source_row_number") != index
        ):
            raise VirginiaDEQAirPermitsError("issued record key or row order changed")
        ids.append(permit_id)
        keys.append(str(record["record_key"]))
        if (
            record.get("record_status") != "issued_permit"
            or record.get("permit_evidence_only") is not True
            or record.get("construction_verified") is not False
            or record.get("auto_merge_permitted") is not False
            or record.get("publication_eligible") is not False
            or record.get("review_only") is not True
            or record.get("document_checkpoint_status")
            != "not_fetched_or_retained_due_fail_closed_rights"
            or record.get("source_page_snapshot_date") != SNAPSHOT_DATE
            or record.get("source_page_url") != ISSUED_PAGE_URL
        ):
            raise VirginiaDEQAirPermitsError(
                "issued permit cannot become construction or operation proof"
            )
        if any(record.get(field) is not None for field in _ISSUED_NULL_FIELDS):
            raise VirginiaDEQAirPermitsError(
                "issued permit promoted an unsupported Atlas field"
            )
        for text_field in ("site_name", "locality", "regional_office"):
            if not isinstance(record.get(text_field), str) or not record[text_field]:
                raise VirginiaDEQAirPermitsError(
                    f"issued {text_field} must be non-empty"
                )

        _validate_issued_date(record)
        normalized_program = record.get("program_type_normalized")
        source_program = record.get("program_type_source")
        if permit_id == "74335-1":
            if (
                source_program != "Article 6 mNSR"
                or normalized_program != "Article 6 - mNSR"
            ):
                raise VirginiaDEQAirPermitsError(
                    "source program-format anomaly was not preserved"
                )
        elif source_program != normalized_program:
            raise VirginiaDEQAirPermitsError("unexpected program normalization")
        program_counts[str(normalized_program)] += 1
        region_counts[str(record["regional_office"])] += 1

        status = record.get("permit_document_url_status")
        url_statuses[str(status)] += 1
        url = record.get("permit_document_url")
        if permit_id == "74063-5":
            if status != "official_link_unresolved" or url is not None:
                raise VirginiaDEQAirPermitsError(
                    "unresolved official permit link was inferred or changed"
                )
        elif permit_id in {"74331-1", "74333-1"}:
            if status != "shared_official_url" or url != _SHARED_DOCUMENT_URL:
                raise VirginiaDEQAirPermitsError(
                    "shared official permit document URL changed"
                )
            urls.append(str(url))
        else:
            if status != "resolved_official_url":
                raise VirginiaDEQAirPermitsError("permit URL status changed")
            urls.append(_official_url(url, "permit document URL"))

    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        raise VirginiaDEQAirPermitsError("issued record keys must be unique")
    if ids[0] != "11541-3" or ids[-1] != "81609-5":
        raise VirginiaDEQAirPermitsError("issued table boundary rows changed")
    if dict(program_counts) != _EXPECTED_PROGRAM_COUNTS:
        raise VirginiaDEQAirPermitsError("issued program counts changed")
    if dict(region_counts) != _EXPECTED_REGION_COUNTS:
        raise VirginiaDEQAirPermitsError("issued regional-office counts changed")
    if url_statuses != Counter(
        {
            "resolved_official_url": 195,
            "shared_official_url": 2,
            "official_link_unresolved": 1,
        }
    ):
        raise VirginiaDEQAirPermitsError("issued permit URL counts changed")
    if len(urls) != 197 or len(set(urls)) != 196:
        raise VirginiaDEQAirPermitsError("resolved permit URL inventory changed")
    duplicate_urls = {url for url, count in Counter(urls).items() if count > 1}
    if duplicate_urls != {_SHARED_DOCUMENT_URL}:
        raise VirginiaDEQAirPermitsError("unexpected shared permit URL")
    _validate_duplicate_groups(document.get("possible_duplicate_groups"), records)
    _exact_document_hash(document, ISSUED_PERMITS_FILENAME)


def _metric_signature(metric: Mapping[str, Any]) -> tuple[Any, ...]:
    electrical = metric.get("electrical_nameplate")
    electrical_comparator = None
    electrical_value = None
    if electrical is not None:
        electrical_object = _object(electrical, "electrical_nameplate")
        if electrical_object.get("unit") != "kWe":
            raise VirginiaDEQAirPermitsError("generator electrical unit changed")
        electrical_comparator = electrical_object.get("comparator")
        electrical_value = electrical_object.get("value")
    engine = _object(metric.get("engine_power"), "engine_power")
    if engine.get("unit") != "bhp":
        raise VirginiaDEQAirPermitsError("generator engine unit changed")
    return (
        metric.get("count"),
        metric.get("equipment_role"),
        electrical_comparator,
        electrical_value,
        engine.get("comparator"),
        engine.get("value"),
    )


def validate_applications_document(document: Mapping[str, Any]) -> None:
    """Validate the separate Project Raspberry under-review application record."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != APPLICATIONS_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
        or document.get("source_family") != SOURCE_FAMILY
    ):
        raise VirginiaDEQAirPermitsError("application identity is invalid")
    if _timestamp(document.get("generated_at"), "generated_at") != GENERATED_AT:
        raise VirginiaDEQAirPermitsError("application timestamp changed")
    if (
        document.get("application_count") != APPLICATION_ROWS
        or document.get("source_page_url") != RASPBERRY_PAGE_URL
        or document.get("source_page_observed_date") != "2026-07-18"
        or document.get("publication_eligible") is not False
        or document.get("raw_source_artifacts_retained") is not False
        or document.get("review_only") is not True
        or document.get("unique_physical_site_count") is not None
        or document.get("document_inventory")
        != {
            "distinct_official_document_urls": 8,
            "raw_documents_retained": 0,
            "total_document_links": 8,
        }
    ):
        raise VirginiaDEQAirPermitsError(
            "application lane must remain separate and review-only"
        )
    records = document.get("records")
    if not isinstance(records, list) or len(records) != APPLICATION_ROWS:
        raise VirginiaDEQAirPermitsError("application record count changed")
    record = _object(records[0], "records[0]")
    if set(record) != _APPLICATION_RECORD_KEYS:
        raise VirginiaDEQAirPermitsError("application record field set changed")
    if any(record.get(field) is not None for field in _APPLICATION_NULL_FIELDS):
        raise VirginiaDEQAirPermitsError(
            "generator metrics were summed or promoted into an Atlas metric"
        )
    expected_identity = {
        "applicant": "Helio Capital LLC",
        "application_received_date": "2026-05-13",
        "application_status": "under_review",
        "associated_company": "Google LLC",
        "construction_verified": False,
        "data_center_building_count_source_stated": 3,
        "generator_metrics_source": (
            "official_project_page_summary_not_linked_pdf_parse"
        ),
        "locality": "Botetourt County",
        "permit_document_parsing_performed": False,
        "program_type": "Article 6 - mNSR",
        "project_name": "Project Raspberry",
        "record_key": "virginia-deq-air-application:21819-1",
        "record_status": "application_under_review",
        "regional_office": "Blue Ridge",
        "registration_number": "21819",
        "registration_or_application_id": "21819-1",
        "source_page_observed_date": "2026-07-18",
        "source_page_url": RASPBERRY_PAGE_URL,
        "source_section": "Minor New Source Review (NSR) Permit",
        "source_status_text": "currently under review",
    }
    if any(record.get(key) != value for key, value in expected_identity.items()):
        raise VirginiaDEQAirPermitsError(
            "under-review application identity or status changed"
        )
    if (
        record.get("auto_merge_permitted") is not False
        or record.get("publication_eligible") is not False
        or record.get("review_only") is not True
    ):
        raise VirginiaDEQAirPermitsError("application controls changed")

    documents = record.get("application_documents")
    if not isinstance(documents, list) or len(documents) != 8:
        raise VirginiaDEQAirPermitsError("application document inventory changed")
    document_urls: list[str] = []
    document_roles: set[str] = set()
    for raw in documents:
        linked = _object(raw, "application document")
        if set(linked) != {
            "document_bytes",
            "document_checkpoint_status",
            "document_date",
            "document_role",
            "document_sha256",
            "document_url",
            "publication_eligible",
            "raw_document_retained",
            "title",
        }:
            raise VirginiaDEQAirPermitsError("application document fields changed")
        url = _official_url(linked.get("document_url"), "application document URL")
        document_urls.append(url)
        role = linked.get("document_role")
        if not isinstance(role, str) or not role or role in document_roles:
            raise VirginiaDEQAirPermitsError("application document roles differ")
        document_roles.add(role)
        if (
            linked.get("document_bytes") is not None
            or linked.get("document_sha256") is not None
            or linked.get("raw_document_retained") is not False
            or linked.get("publication_eligible") is not False
            or linked.get("document_checkpoint_status")
            != "not_fetched_or_retained_due_fail_closed_rights"
        ):
            raise VirginiaDEQAirPermitsError(
                "application documents must remain unparsed and unretained"
            )
    if len(set(document_urls)) != 8:
        raise VirginiaDEQAirPermitsError("application document URLs must be unique")

    metrics = record.get("generator_metrics")
    if not isinstance(metrics, list) or len(metrics) != 6:
        raise VirginiaDEQAirPermitsError("generator metric group count changed")
    signatures: list[tuple[Any, ...]] = []
    for raw in metrics:
        metric = _object(raw, "generator metric")
        if set(metric) != {
            "count",
            "electrical_nameplate",
            "emissions_tier",
            "engine_power",
            "equipment_role",
            "manufacturer",
            "model",
            "per_building_count",
            "source_scope",
            "source_text",
        }:
            raise VirginiaDEQAirPermitsError("generator metric fields changed")
        if (
            metric.get("source_scope") != "applicant_proposed"
            or not isinstance(metric.get("source_text"), str)
            or not metric.get("source_text")
        ):
            raise VirginiaDEQAirPermitsError("generator provenance changed")
        signatures.append(_metric_signature(metric))
    if signatures != _GENERATOR_SIGNATURES:
        raise VirginiaDEQAirPermitsError(
            "source-typed generator counts or nameplate values changed"
        )
    if record.get("operating_limit_proposals") != [
        {
            "equipment_scope": (
                "114 2,750-kWe and 6 1,750-kWe critical emergency generator sets"
            ),
            "hours": 3617,
            "limit_basis": "combined",
            "period": "12-month rolling period",
            "source_stated_equipment_count": 120,
        },
        {
            "equipment_scope": "each remaining emergency generator and fire pump",
            "hours": 100,
            "limit_basis": "individual",
            "period": "12-month rolling period",
            "source_stated_equipment_count": None,
        },
    ]:
        raise VirginiaDEQAirPermitsError("operating-limit provenance changed")
    _exact_document_hash(document, APPLICATIONS_FILENAME)


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable four-file bundle without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise VirginiaDEQAirPermitsError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise VirginiaDEQAirPermitsError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise VirginiaDEQAirPermitsError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    issued = _load_json(
        directory / ISSUED_PERMITS_FILENAME, "issued-permit table"
    )
    applications = _load_json(
        directory / APPLICATIONS_FILENAME, "application table"
    )
    validate_assessment_document(assessment)
    validate_issued_permits_document(issued)
    validate_applications_document(applications)
    if not (
        assessment.get("assessed_at")
        == issued.get("generated_at")
        == applications.get("generated_at")
    ):
        raise VirginiaDEQAirPermitsError("bundle timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != GENERATED_AT
    ):
        raise VirginiaDEQAirPermitsError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    expected_payload_files = {
        ASSESSMENT_FILENAME,
        ISSUED_PERMITS_FILENAME,
        APPLICATIONS_FILENAME,
    }
    if set(files) != expected_payload_files:
        raise VirginiaDEQAirPermitsError("assessment manifest file set differs")
    for filename in sorted(expected_payload_files):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            set(record) != {"bytes", "sha256"}
            or record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise VirginiaDEQAirPermitsError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (
        directory.joinpath(MANIFEST_HASH_FILENAME).read_text(encoding="utf-8")
        != expected_sidecar
    ):
        raise VirginiaDEQAirPermitsError("assessment manifest sidecar mismatch")
    return {
        "applications": applications,
        "assessment": assessment,
        "issued_permits": issued,
        "manifest": manifest,
    }


def build_assessment_bundle(
    output: str | Path,
    assessment: Mapping[str, Any],
    issued_permits: Mapping[str, Any],
    applications: Mapping[str, Any],
) -> Path:
    """Atomically write one exact, new copy of the frozen source assessment."""

    destination = Path(output)
    if destination.exists() or destination.is_symlink():
        raise VirginiaDEQAirPermitsError("output bundle already exists")
    validate_assessment_document(assessment)
    validate_issued_permits_document(issued_permits)
    validate_applications_document(applications)
    if not (
        assessment.get("assessed_at")
        == issued_permits.get("generated_at")
        == applications.get("generated_at")
    ):
        raise VirginiaDEQAirPermitsError("bundle timestamps differ")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        payloads = {
            ASSESSMENT_FILENAME: canonical_json(assessment),
            ISSUED_PERMITS_FILENAME: canonical_json(issued_permits),
            APPLICATIONS_FILENAME: canonical_json(applications),
        }
        for filename, body in payloads.items():
            (temporary / filename).write_bytes(body)
        manifest = {
            "assessment_id": ASSESSMENT_ID,
            "files": {
                filename: {
                    "bytes": len(body),
                    "sha256": sha256_bytes(body),
                }
                for filename, body in payloads.items()
            },
            "format": ASSESSMENT_FORMAT,
            "generated_at": GENERATED_AT,
            "schema_version": SCHEMA_VERSION,
        }
        manifest_bytes = canonical_json(manifest)
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_bytes)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_bytes)}  manifest.json\n",
            encoding="utf-8",
        )
        validate_assessment_bundle(temporary)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return destination


__all__ = [
    "APPLICATIONS_FILENAME",
    "APPLICATIONS_FORMAT",
    "ASSESSMENT_FILENAME",
    "ASSESSMENT_FORMAT",
    "ASSESSMENT_ID",
    "ISSUED_PERMITS_FILENAME",
    "ISSUED_PERMITS_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "VirginiaDEQAirPermitsError",
    "build_assessment_bundle",
    "canonical_json",
    "sha256_bytes",
    "validate_applications_document",
    "validate_assessment_bundle",
    "validate_assessment_document",
    "validate_issued_permits_document",
]
