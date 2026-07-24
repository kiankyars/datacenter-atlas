"""Validate the fail-closed Cleanview data-centers API assessment."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


ASSESSMENT_FILENAME = "assessment.json"
SCHEMA_FILENAME = "schema.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-cleanview-assessment-v1"
SCHEMA_FORMAT = "datacenter-atlas-cleanview-schema-assessment-v1"
ASSESSMENT_ID = "cleanview-2026-07-18-v1"
SCHEMA_ID = "cleanview-data-centers-openapi-0.1.0-2026-07-18-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    SCHEMA_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_OFFICIAL_HOSTS = {"api.cleanview.co", "cleanview.co", "docs.cleanview.co"}
_EXPECTED_SOURCE_IDS = {
    "api_introduction",
    "api_robots",
    "authentication_docs",
    "data_centers_docs",
    "docs_index",
    "docs_robots",
    "main_robots",
    "main_sitemap",
    "openapi_spec",
    "pricing",
    "privacy_candidate",
    "privacy_policy_candidate",
    "terms_candidate",
    "terms_of_service_candidate",
}

_EXPECTED_RIGHTS = {
    "affirmative_commercial_use_permission_found": False,
    "affirmative_public_redistribution_permission_found": False,
    "custom_product_integration_license_advertised": True,
    "derivative_database_publication_permitted": False,
    "legal_conclusion_claimed": False,
    "privacy_page_found": False,
    "public_api_documentation_is_a_data_license": False,
    "robots_or_content_signal_is_a_data_license": False,
    "source_record_cache_for_atlas_release_permitted": False,
    "terms_page_found": False,
    "written_custom_license_required": True,
}

_EXPECTED_ACCESS = {
    "anonymous_access_documented": False,
    "api_base_url": "https://api.cleanview.co/api/v1",
    "api_key_header": "x-api-key",
    "api_key_manually_provisioned": True,
    "api_key_required": True,
    "api_key_used": False,
    "data_endpoint_requests": 0,
    "data_endpoint_url": "https://api.cleanview.co/api/v1/data-centers",
    "endpoint_filters": False,
    "endpoint_pagination": False,
    "endpoint_returns_all_records": True,
    "intended_use_reviewed_before_key_issue": True,
    "minimal_bounded_data_probe_possible": False,
    "probe_performed": False,
}

_EXPECTED_PRICING = {
    "custom_api_access_advertised": True,
    "custom_license_for_product_integration_advertised": True,
    "explicit_public_redistribution_right_advertised": False,
    "pro_monthly_updates_advertised": True,
    "pro_product_integration_right_advertised": False,
    "pro_unlimited_downloads_advertised": True,
    "pro_use_in_own_tools_advertised": True,
    "required_plan_for_atlas_request": "Custom",
}

_EXPECTED_COVERAGE = {
    "advertised_api_record_unit": "data_center_project_record",
    "advertised_audit_approved_records_only": True,
    "advertised_geographic_scope": "United States",
    "canonical_facility_count": None,
    "example_generated_at": "2024-12-12T10:00:00.000Z",
    "example_total_count": 1176,
    "example_total_count_is_current_verified_count": False,
    "global_coverage_claim_supported": False,
    "live_record_count": None,
    "project_record_count_is_unique_site_count": False,
    "publication_facility_leads": 0,
}

_EXPECTED_FRESHNESS = {
    "current_dataset_generated_at": None,
    "data_center_docs_claim_continuous_updates": True,
    "endpoint_has_record_last_updated_field": False,
    "general_api_docs_claim_most_data_updated_daily": True,
    "generated_at_is_response_level_only": True,
    "pricing_pro_claims_monthly_updates": True,
    "record_freshness_sla_found": False,
}

_EXPECTED_DECISION = {
    "auto_merge_permitted": False,
    "construction_status_promotion_permitted": False,
    "current_record_count_published": False,
    "publication_eligible_pilot_created": False,
    "review_leads_emitted": 0,
    "source_content_publication_eligible": False,
    "status": "api_and_rights_blocked_metadata_only",
    "typed_capacity_promotion_permitted": False,
    "unique_facility_count_published": False,
}

_EXPECTED_PERMISSION_REQUIREMENTS = {
    "api_key_issued_for_declared_atlas_product_integration",
    "commercial_use_of_compiled_data",
    "local_storage_and_cache",
    "public_display_and_redistribution_of_derived_records",
    "refresh_rate_limits_and_attribution_terms",
    "retention_and_deletion_terms_after_termination",
    "sublicensing_or_downstream_end_user_access",
    "transformation_and_derivative_database_creation",
}

_EXPECTED_RECORD_FIELDS = {
    "building_square_footage": {
        "nullable": True,
        "required": False,
        "type": "integer",
    },
    "cap_ex": {"nullable": True, "required": False, "type": "number"},
    "capacity_mw": {"nullable": True, "required": False, "type": "number"},
    "county": {"nullable": True, "required": False, "type": "string"},
    "developer": {"nullable": True, "required": False, "type": "string"},
    "land_acres": {"nullable": True, "required": False, "type": "integer"},
    "latitude": {"nullable": True, "required": False, "type": "number"},
    "longitude": {"nullable": True, "required": False, "type": "number"},
    "operating_year": {"nullable": True, "required": False, "type": "integer"},
    "project_name": {"nullable": False, "required": False, "type": "string"},
    "source_1": {"nullable": False, "required": False, "type": "string"},
    "source_2": {"nullable": True, "required": False, "type": "string"},
    "source_3": {"nullable": True, "required": False, "type": "string"},
    "state": {"nullable": True, "required": False, "type": "string"},
    "status": {"nullable": True, "required": False, "type": "string"},
}

_EXPECTED_FIELD_GAPS = {
    "annual_energy_mwh",
    "campus_or_building_parent_id",
    "capacity_metric_scope_it_or_gross",
    "construction_evidence",
    "country_code",
    "facility_type",
    "first_seen_at",
    "last_verified_at",
    "operational_workload",
    "permit_or_groundbreaking_evidence",
    "project_or_facility_stable_id",
    "pue",
    "record_updated_at",
    "source_publication_dates",
    "status_evidence",
}

_EXPECTED_STATUS_SEMANTICS = {
    "advertised_common_values": ["Cancelled", "Operating", "Planned"],
    "atlas_lifecycle_mapping_permitted": False,
    "cancelled_description_also_mentions_postponed": True,
    "openapi_enum_defined": False,
    "operating_is_independent_construction_or_operation_evidence": False,
    "operating_year_distinguishes_actual_from_planned": False,
    "planned_means_under_construction": False,
}

_EXPECTED_CAPACITY_SEMANTICS = {
    "annual_energy_inference_permitted": False,
    "atlas_gross_power_capacity_mapping_permitted": False,
    "atlas_it_load_mapping_permitted": False,
    "capacity_mw_metric_scope": "unspecified_power_capacity",
    "capacity_mw_may_be_estimated": True,
}


class CleanviewAssessmentError(ValueError):
    """Raised when the Cleanview assessment violates its fail-closed boundary."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CleanviewAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CleanviewAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CleanviewAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CleanviewAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CleanviewAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CleanviewAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise CleanviewAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != _canonical_json(value):
        raise CleanviewAssessmentError(f"{label} is not canonical JSON")
    return value


def _validate_artifacts(artifacts: Any) -> None:
    records = _object(artifacts, "official_artifacts")
    if set(records) != _EXPECTED_SOURCE_IDS:
        raise CleanviewAssessmentError("official artifact set differs")
    statuses: Counter[int] = Counter()
    for source_id, raw in records.items():
        record = _object(raw, f"official_artifacts.{source_id}")
        url = record.get("url")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        status = record.get("http_status")
        content_type = record.get("content_type")
        if not isinstance(url, str):
            raise CleanviewAssessmentError("artifact URL must be a string")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in _OFFICIAL_HOSTS:
            raise CleanviewAssessmentError("artifact must use an official Cleanview host")
        if (
            not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or status not in {200, 404}
            or not isinstance(content_type, str)
            or not content_type
        ):
            raise CleanviewAssessmentError("artifact retrieval metadata is invalid")
        statuses[status] += 1
    if statuses != {200: 9, 404: 5}:
        raise CleanviewAssessmentError("artifact status counts changed")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact access, rights, coverage, and Atlas decision."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise CleanviewAssessmentError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    batch = _object(document.get("retrieval_batch"), "retrieval_batch")
    if (
        _timestamp(batch.get("retrieved_at"), "retrieved_at") != assessed_at
        or batch.get("network_retrievals") != 14
        or batch.get("data_endpoint_requests") != 0
        or batch.get("raw_artifacts_retained") is not False
        or batch.get("transient_inspection_only") is not True
    ):
        raise CleanviewAssessmentError("retrieval boundary changed")
    _validate_artifacts(document.get("official_artifacts"))

    source = _object(document.get("source"), "source")
    if source != {
        "data_centers_docs_url": "https://docs.cleanview.co/api-reference/endpoint/data-centers",
        "name": "Cleanview",
        "openapi_url": "https://docs.cleanview.co/api-reference/openapi.json",
        "pricing_url": "https://cleanview.co/pricing",
    }:
        raise CleanviewAssessmentError("source identity changed")
    if document.get("rights_assessment") != _EXPECTED_RIGHTS:
        raise CleanviewAssessmentError("Cleanview rights must remain fail closed")
    if document.get("access_assessment") != _EXPECTED_ACCESS:
        raise CleanviewAssessmentError("Cleanview API access boundary changed")
    if document.get("pricing_assessment") != _EXPECTED_PRICING:
        raise CleanviewAssessmentError("Cleanview pricing boundary changed")
    if document.get("coverage_assessment") != _EXPECTED_COVERAGE:
        raise CleanviewAssessmentError("Cleanview coverage claims changed")
    if document.get("freshness_assessment") != _EXPECTED_FRESHNESS:
        raise CleanviewAssessmentError("Cleanview freshness claims changed")
    if document.get("atlas_decision") != _EXPECTED_DECISION:
        raise CleanviewAssessmentError("Atlas decision changed")
    requirements = document.get("permission_required_for_reassessment")
    if (
        not isinstance(requirements, list)
        or set(requirements) != _EXPECTED_PERMISSION_REQUIREMENTS
        or len(requirements) != len(_EXPECTED_PERMISSION_REQUIREMENTS)
    ):
        raise CleanviewAssessmentError("required Cleanview permission changed")
    legal_discovery = _object(document.get("legal_discovery"), "legal_discovery")
    if legal_discovery != {
        "candidate_404_responses": 4,
        "main_sitemap_exact_legal_or_privacy_paths": 0,
        "main_sitemap_url_count": 26754,
        "pricing_path_present_in_main_sitemap": True,
    }:
        raise CleanviewAssessmentError("legal-page discovery changed")


def validate_schema_document(document: Mapping[str, Any]) -> None:
    """Validate the exact documented response contract without response data."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != SCHEMA_FORMAT
        or document.get("schema_id") != SCHEMA_ID
        or document.get("assessment_id") != ASSESSMENT_ID
        or document.get("openapi_version") != "3.0.0"
        or document.get("api_info_version") != "0.1.0"
    ):
        raise CleanviewAssessmentError("schema identity is invalid")
    _timestamp(document.get("generated_at"), "schema generated_at")
    endpoint = _object(document.get("endpoint"), "endpoint")
    if endpoint != {
        "api_key_required": True,
        "full_download_only": True,
        "method": "GET",
        "pagination": False,
        "path": "/data-centers",
        "server": "https://api.cleanview.co/api/v1",
    }:
        raise CleanviewAssessmentError("endpoint contract changed")
    response = _object(document.get("response"), "response")
    if response.get("top_level_required") != [
        "customer",
        "data",
        "metadata",
        "success",
    ]:
        raise CleanviewAssessmentError("top-level response contract changed")
    if response.get("metadata_fields") != {
        "generated_at": {"format": "date-time", "required": False, "type": "string"},
        "total_count": {"required": False, "type": "integer"},
    }:
        raise CleanviewAssessmentError("metadata response fields changed")
    if response.get("customer_fields") != {
        "id": {"required": False, "type": "string"},
        "name": {"required": False, "type": "string"},
    }:
        raise CleanviewAssessmentError("customer response fields changed")
    if response.get("record_fields") != _EXPECTED_RECORD_FIELDS:
        raise CleanviewAssessmentError("data-center record schema changed")
    if response.get("record_field_count") != 15:
        raise CleanviewAssessmentError("data-center field count changed")
    if document.get("field_gaps") != sorted(_EXPECTED_FIELD_GAPS):
        raise CleanviewAssessmentError("documented field gaps changed")
    if document.get("status_semantics") != _EXPECTED_STATUS_SEMANTICS:
        raise CleanviewAssessmentError("status semantics changed")
    if document.get("capacity_semantics") != _EXPECTED_CAPACITY_SEMANTICS:
        raise CleanviewAssessmentError("capacity semantics changed")
    if (
        document.get("contains_api_response_records") is not False
        or document.get("contains_example_project_values") is not False
        or document.get("facility_leads") != []
        or document.get("facility_lead_count") != 0
        or document.get("unique_facility_count") is not None
    ):
        raise CleanviewAssessmentError("schema assessment must not contain source rows")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable Cleanview bundle without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise CleanviewAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise CleanviewAssessmentError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise CleanviewAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    schema = _load_json(directory / SCHEMA_FILENAME, "schema assessment")
    validate_assessment_document(assessment)
    validate_schema_document(schema)
    if schema.get("generated_at") != assessment.get("assessed_at"):
        raise CleanviewAssessmentError("bundle timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise CleanviewAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME, SCHEMA_FILENAME}:
        raise CleanviewAssessmentError("assessment manifest file set differs")
    for filename in (ASSESSMENT_FILENAME, SCHEMA_FILENAME):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise CleanviewAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    sidecar = directory / MANIFEST_HASH_FILENAME
    if sidecar.read_text(encoding="utf-8") != expected_sidecar:
        raise CleanviewAssessmentError("assessment manifest sidecar mismatch")
    return {"assessment": assessment, "schema": schema}
