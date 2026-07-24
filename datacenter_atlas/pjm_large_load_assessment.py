"""Validate the fail-closed PJM large-load source assessment."""

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
CALIBRATION_FILENAME = "calibration.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-pjm-large-load-assessment-v1"
CALIBRATION_FORMAT = "datacenter-atlas-pjm-large-load-calibration-v1"
ASSESSMENT_ID = "pjm-large-load-2026-07-18-v1"
CALIBRATION_ID = "pjm-large-load-metadata-only-2026-07-18-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    CALIBRATION_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}

_GOVERNANCE_SOURCE_IDS = {
    "las_materials_2025",
    "las_page_current",
    "load_forecast_process",
    "pjm_legal",
}
_PRESENTATION_2025_AGGREGATE_IDS = {
    "las_2025_aep",
    "las_2025_dominion",
    "las_2025_duke",
    "las_2025_exelon",
    "las_2025_novec",
    "las_2025_odec",
    "las_2025_ppl",
    "las_2025_pseg",
    "las_2025_rec",
    "las_2025_smeco",
}
_PRESENTATION_2025_PROJECT_DETAIL_IDS = {
    "las_2025_day_aes",
    "las_2025_duquesne",
    "las_2025_firstenergy",
}
_PJM_2025_AGGREGATE_IDS = {
    "las_2025_requests_xlsx",
    "las_2025_summary",
}
_PJM_2026_AGGREGATE_IDS = {
    "forecast_2026_accuracy_data",
    "forecast_2026_accuracy_report",
    "forecast_2026_capacity_obligations_adjustments",
    "forecast_2026_data",
    "forecast_2026_report",
    "forecast_2026_supplement",
    "forecast_2026_tables",
    "forecast_2026_total_adjustments_breakdown",
    "forecast_2026_total_monthly_adjustments",
    "las_2026_presentation",
}
_UTILITY_2026_AGGREGATE_IDS = {
    "forecast_2026_aep_documentation",
    "forecast_2026_dayton_documentation",
    "forecast_2026_dlco_documentation",
    "forecast_2026_dominion_documentation",
    "forecast_2026_dominion_vo_documentation",
    "forecast_2026_exelon_documentation",
    "forecast_2026_novec_documentation",
    "forecast_2026_odec_documentation",
    "forecast_2026_ppl_documentation",
    "forecast_2026_pseg_documentation",
    "forecast_2026_rec_documentation",
    "forecast_2026_smeco_documentation",
}
_UTILITY_2026_PROJECT_DETAIL_IDS = {
    "forecast_2026_firstenergy_documentation",
}
_EXPECTED_SOURCE_IDS = (
    _GOVERNANCE_SOURCE_IDS
    | _PRESENTATION_2025_AGGREGATE_IDS
    | _PRESENTATION_2025_PROJECT_DETAIL_IDS
    | _PJM_2025_AGGREGATE_IDS
    | _PJM_2026_AGGREGATE_IDS
    | _UTILITY_2026_AGGREGATE_IDS
    | _UTILITY_2026_PROJECT_DETAIL_IDS
)

_EXPECTED_RIGHTS = {
    "access_conveys_license": False,
    "affirmative_redistribution_license_found": False,
    "all_rights_reserved_notice_present": True,
    "atlas_policy_allows_metadata_hash_assessment": True,
    "bulk_numeric_extraction_for_atlas_release_permitted": False,
    "legal_conclusion_claimed": False,
    "public_or_for_public_use_marking_is_a_reuse_license": False,
    "raw_artifact_cache_for_atlas_release_permitted": False,
    "source_derived_project_row_release_permitted": False,
    "static_website_scope_only": True,
}

_EXPECTED_METRIC_SEMANTICS = {
    "contracted_capacity_mva": {
        "atlas_facility_field": None,
        "quantity_state": "contracted_apparent_power_service_or_nameplate",
        "unit": "MVA",
        "warning": "not MW; conversion requires an explicit source power factor",
    },
    "contracted_demand_mw": {
        "atlas_facility_field": None,
        "quantity_state": "contractual_minimum_or_service_commitment",
        "unit": "MW",
        "warning": "not metered demand and not verified physical capacity",
    },
    "forecast_energy_gwh": {
        "atlas_facility_field": None,
        "quantity_state": "modeled_energy_forecast",
        "unit": "GWh",
        "warning": "zonal forecast, not site annual consumption",
    },
    "forecast_peak_mw": {
        "atlas_facility_field": None,
        "quantity_state": "modeled_peak_forecast",
        "unit": "MW",
        "warning": "RTO, LDA, zone, EDC, or LSE forecast, not facility load",
    },
    "historical_aggregate_metered_energy_mwh": {
        "atlas_facility_field": None,
        "quantity_state": "historical_aggregate_metered_energy",
        "unit": "MWh",
        "warning": "aggregate history cannot be assigned to a facility",
    },
    "historical_aggregate_metered_peak_mw": {
        "atlas_facility_field": None,
        "quantity_state": "historical_aggregate_metered_peak",
        "unit": "MW",
        "warning": "aggregate history cannot be assigned to a facility",
    },
    "pjm_forecast_adjustment_mw": {
        "atlas_facility_field": None,
        "quantity_state": "pjm_modeled_forecast_inclusion",
        "unit": "MW",
        "warning": "not requested capacity, contract value, or actual load",
    },
    "requested_capacity_mva": {
        "atlas_facility_field": None,
        "quantity_state": "customer_or_utility_request_apparent_power",
        "unit": "MVA",
        "warning": "not MW; conversion requires an explicit source power factor",
    },
    "requested_capacity_mw": {
        "atlas_facility_field": None,
        "quantity_state": "customer_or_utility_request_facility_size_in_load_terms",
        "unit": "MW",
        "warning": "not a PJM-accepted forecast and not actual demand",
    },
    "requested_demand_mw": {
        "atlas_facility_field": None,
        "quantity_state": "submitted_demand_after_source_assumptions",
        "unit": "MW",
        "warning": "not metered demand and not necessarily accepted by PJM",
    },
}

_EXPECTED_STATUS_SEMANTICS = {
    "construction_commitment": {
        "atlas_lifecycle_status": None,
        "meaning": "utility legal obligation or capital-plan indication for grid facilities",
        "warning": "not verification that the customer data center is under construction",
    },
    "firm": {
        "atlas_lifecycle_status": None,
        "meaning": "PJM forecast-certainty class based on ESO or CC support",
        "warning": "not a physical lifecycle status",
    },
    "non_firm": {
        "atlas_lifecycle_status": None,
        "meaning": "PJM forecast-certainty class without ESO or CC support",
        "warning": "not equivalent to proposed, canceled, or inactive",
    },
    "projected_in_service_date": {
        "atlas_lifecycle_status": None,
        "meaning": "source-projected service date",
        "warning": "not commissioning or operational evidence",
    },
}

_EXPECTED_INFERENCE_BANS = {
    "do_not_assign_aggregate_history_or_forecasts_to_a_facility",
    "do_not_convert_mva_to_mw_without_an_explicit_power_factor",
    "do_not_infer_annual_energy_from_peak_mw",
    "do_not_promote_cc_or_firm_to_under_construction",
    "do_not_treat_projected_isd_as_commissioning_evidence",
    "do_not_treat_request_or_contract_values_as_metered_load",
    "do_not_treat_zone_edc_lse_rows_as_facilities",
}


class PJMLargeLoadAssessmentError(ValueError):
    """Raised when the PJM assessment fails its source-governance boundary."""


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
        raise PJMLargeLoadAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PJMLargeLoadAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PJMLargeLoadAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PJMLargeLoadAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PJMLargeLoadAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PJMLargeLoadAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise PJMLargeLoadAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != _canonical_json(value):
        raise PJMLargeLoadAssessmentError(f"{label} is not canonical JSON")
    return value


def _validate_artifacts(artifacts: Any) -> None:
    records = _object(artifacts, "official_artifacts")
    if set(records) != _EXPECTED_SOURCE_IDS:
        raise PJMLargeLoadAssessmentError("official artifact set differs")
    content_types: Counter[str] = Counter()
    for source_id, raw in records.items():
        record = _object(raw, f"official_artifacts.{source_id}")
        url = record.get("url")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        content_type = record.get("content_type")
        if not isinstance(url, str):
            raise PJMLargeLoadAssessmentError("artifact URL must be a string")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "www.pjm.com":
            raise PJMLargeLoadAssessmentError("artifact must use the official PJM host")
        if (
            not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or record.get("http_status") != 200
            or content_type
            not in {
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "text/html; charset=utf-8",
            }
        ):
            raise PJMLargeLoadAssessmentError("artifact retrieval metadata is invalid")
        content_types[content_type] += 1
        if source_id == "las_materials_2025":
            request = _object(record.get("request"), "LAS 2025 material request")
            if request != {
                "committee_id": "{713E4C1E-3BE3-463F-B9E5-EF7781013D7D}",
                "is_annual_meeting": "false",
                "method": "POST",
                "search_term": "",
                "year": "2025",
            }:
                raise PJMLargeLoadAssessmentError("LAS 2025 request changed")
        elif "request" in record:
            raise PJMLargeLoadAssessmentError("unexpected non-GET artifact request")
    if content_types != {
        "application/pdf": 31,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 7,
        "text/html; charset=utf-8": 4,
    }:
        raise PJMLargeLoadAssessmentError("artifact media-type counts changed")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact fail-closed source-rights assessment."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise PJMLargeLoadAssessmentError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    batch = _object(document.get("retrieval_batch"), "retrieval_batch")
    if (
        _timestamp(batch.get("retrieved_at"), "retrieved_at") != assessed_at
        or batch.get("network_retrievals") != 42
        or batch.get("raw_artifacts_retained") is not False
        or batch.get("transient_inspection_only") is not True
    ):
        raise PJMLargeLoadAssessmentError("retrieval batch boundary changed")
    _validate_artifacts(document.get("official_artifacts"))

    source = _object(document.get("source"), "source")
    if source != {
        "legal_notice_url": "https://www.pjm.com/about-pjm/legal.aspx",
        "load_analysis_subcommittee_url": "https://www.pjm.com/committees-and-groups/subcommittees/las.aspx",
        "load_forecast_process_url": "https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process",
        "name": "PJM Interconnection",
        "scope": "static pjm.com LAS and 2026 load-forecast materials",
    }:
        raise PJMLargeLoadAssessmentError("source identity changed")

    rights = _object(document.get("rights_assessment"), "rights_assessment")
    if rights != _EXPECTED_RIGHTS:
        raise PJMLargeLoadAssessmentError("PJM rights must remain fail closed")

    provenance = _object(document.get("provenance_assessment"), "provenance")
    if provenance != {
        "pjm_authored_or_generated_artifacts": 16,
        "pjm_hosting_implies_pjm_endorsement": False,
        "stakeholder_authored_artifacts": 26,
        "stakeholder_documents_are_primary_for_submitter_claims_only": True,
    }:
        raise PJMLargeLoadAssessmentError("artifact provenance changed")

    coverage = _object(document.get("coverage_assessment"), "coverage")
    expected_coverage = {
        "governance_and_discovery_endpoints": 4,
        "html_responses": 4,
        "pdf_documents": 31,
        "raw_artifacts_retained": 0,
        "retrievals": 42,
        "xlsx_workbooks": 7,
        "year_2025_large_load_presentations": 13,
        "year_2025_pjm_summary_documents": 1,
        "year_2025_request_workbooks": 1,
        "year_2026_edc_lse_supporting_documents": 13,
        "year_2026_pjm_forecast_suite_artifacts": 10,
    }
    if coverage != expected_coverage:
        raise PJMLargeLoadAssessmentError("coverage counts changed")

    granularity = _object(document.get("granularity_assessment"), "granularity")
    expected_granularity = {
        "anonymous_project_detail_document_count": 4,
        "canonical_facility_rows": 0,
        "facility_coordinates_exposed": 0,
        "facility_names_exposed": 0,
        "publication_facility_leads": 0,
        "unique_facility_count": None,
        "year_2025_aggregate_only_presentations": 10,
        "year_2025_anonymous_large_load_project_row_occurrences": 50,
        "year_2025_anonymous_project_detail_presentations": 3,
        "year_2025_request_workbook_granularity": "zone_edc_lse_year",
        "year_2025_summary_granularity": "rto_zone_edc_lse_year",
        "year_2026_firstenergy_anonymous_data_center_rows": 33,
        "year_2026_firstenergy_anonymous_non_data_center_rows": 8,
        "year_2026_firstenergy_anonymous_project_rows": 41,
        "year_2026_pjm_forecast_granularity": "rto_lda_zone_edc_lse_time",
    }
    if granularity != expected_granularity:
        raise PJMLargeLoadAssessmentError("document granularity changed")

    decision = _object(document.get("atlas_decision"), "atlas_decision")
    if decision != {
        "aggregate_numeric_calibration_emitted": False,
        "assessment_metadata_publication_eligible": True,
        "auto_merge_permitted": False,
        "construction_status_promotion_permitted": False,
        "review_lead_pilot_emitted": False,
        "source_content_publication_eligible": False,
        "status": "rights_blocked_metadata_only",
        "typed_power_promotion_permitted": False,
    }:
        raise PJMLargeLoadAssessmentError("Atlas decision changed")


def _validate_granularity_groups(groups: Any) -> None:
    records = _object(groups, "document_granularity")
    expected_groups = {
        "governance_and_discovery": (_GOVERNANCE_SOURCE_IDS, "metadata_only"),
        "pjm_2025_aggregates": (_PJM_2025_AGGREGATE_IDS, "aggregate"),
        "pjm_2026_forecast_suite": (_PJM_2026_AGGREGATE_IDS, "aggregate"),
        "stakeholder_2025_aggregate_only": (
            _PRESENTATION_2025_AGGREGATE_IDS,
            "aggregate",
        ),
        "stakeholder_2025_anonymous_project_detail": (
            _PRESENTATION_2025_PROJECT_DETAIL_IDS,
            "anonymous_project_detail",
        ),
        "utility_2026_aggregate_or_methodology": (
            _UTILITY_2026_AGGREGATE_IDS,
            "aggregate_or_methodology",
        ),
        "utility_2026_anonymous_project_detail": (
            _UTILITY_2026_PROJECT_DETAIL_IDS,
            "anonymous_project_detail",
        ),
    }
    if set(records) != set(expected_groups):
        raise PJMLargeLoadAssessmentError("granularity group set changed")
    all_source_ids: set[str] = set()
    for group_id, (expected_ids, expected_level) in expected_groups.items():
        record = _object(records[group_id], f"document_granularity.{group_id}")
        source_ids = record.get("source_ids")
        if (
            not isinstance(source_ids, list)
            or set(source_ids) != expected_ids
            or len(source_ids) != len(expected_ids)
            or record.get("level") != expected_level
            or record.get("facility_rows_emitted") != 0
        ):
            raise PJMLargeLoadAssessmentError("granularity group changed")
        if all_source_ids.intersection(source_ids):
            raise PJMLargeLoadAssessmentError("source appears in multiple groups")
        all_source_ids.update(source_ids)
    if all_source_ids != _EXPECTED_SOURCE_IDS:
        raise PJMLargeLoadAssessmentError("granularity groups are incomplete")


def validate_calibration_document(document: Mapping[str, Any]) -> None:
    """Validate the metadata-only calibration and its inference bans."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != CALIBRATION_FORMAT
        or document.get("calibration_id") != CALIBRATION_ID
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise PJMLargeLoadAssessmentError("calibration identity is invalid")
    _timestamp(document.get("generated_at"), "calibration generated_at")
    if (
        document.get("rights_blocked") is not True
        or document.get("publication_eligible") is not True
        or document.get("contains_source_numeric_values") is not False
        or document.get("contains_source_project_rows") is not False
        or document.get("numeric_series") != []
        or document.get("review_leads") != []
        or document.get("facility_lead_count") != 0
        or document.get("numeric_series_count") != 0
        or document.get("unique_facility_count") is not None
    ):
        raise PJMLargeLoadAssessmentError("calibration must remain metadata only")
    if document.get("metric_semantics") != _EXPECTED_METRIC_SEMANTICS:
        raise PJMLargeLoadAssessmentError("power and energy semantics changed")
    if document.get("status_semantics") != _EXPECTED_STATUS_SEMANTICS:
        raise PJMLargeLoadAssessmentError("status semantics changed")
    bans = document.get("inference_bans")
    if (
        not isinstance(bans, list)
        or set(bans) != _EXPECTED_INFERENCE_BANS
        or len(bans) != len(_EXPECTED_INFERENCE_BANS)
    ):
        raise PJMLargeLoadAssessmentError("inference bans changed")
    _validate_granularity_groups(document.get("document_granularity"))


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable assessment without making network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise PJMLargeLoadAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise PJMLargeLoadAssessmentError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise PJMLargeLoadAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    calibration = _load_json(directory / CALIBRATION_FILENAME, "calibration")
    validate_assessment_document(assessment)
    validate_calibration_document(calibration)
    if calibration.get("generated_at") != assessment.get("assessed_at"):
        raise PJMLargeLoadAssessmentError("bundle timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise PJMLargeLoadAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME, CALIBRATION_FILENAME}:
        raise PJMLargeLoadAssessmentError("assessment manifest file set differs")
    for filename in (ASSESSMENT_FILENAME, CALIBRATION_FILENAME):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise PJMLargeLoadAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    sidecar = directory / MANIFEST_HASH_FILENAME
    if sidecar.read_text(encoding="utf-8") != expected_sidecar:
        raise PJMLargeLoadAssessmentError("assessment manifest sidecar mismatch")
    return {"assessment": assessment, "calibration": calibration}
