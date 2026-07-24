"""Validate the EPA ECHO/FRS rights assessment and bounded review pilot."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit


ASSESSMENT_FILENAME = "assessment.json"
PILOT_FILENAME = "pilot.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-source-rights-assessment-v1"
PILOT_FORMAT = "datacenter-atlas-epa-echo-frs-review-pilot-v1"
ASSESSMENT_ID = "epa-echo-frs-2026-07-18-v1"
PILOT_ID = "epa-echo-frs-naics-518210-2026-07-18-v1"
SOURCE_FAMILY = "epa_echo_frs"
QUERY_ROWS = 928
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    PILOT_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_OFFICIAL_HOSTS = {
    "Data.gov": {"catalog.data.gov"},
    "EPA": {"www.epa.gov"},
    "EPA ECHO": {"echo.epa.gov", "echodata.epa.gov"},
}
_REQUIRED_RETRIEVALS = {
    "data_gov_frs_facility_interests",
    "echo_all_data_services_v3_pdf",
    "echo_all_data_swagger",
    "echo_frs_download_summary",
    "echo_naics_518210_probe",
    "echo_search_criteria_help",
    "echo_web_services",
    "epa_disclaimers",
    "frs_data_download_options",
}
_QUERY_ENDPOINT = (
    "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"
)
_FACILITY_INTERESTS_CATALOG_URL = (
    "https://catalog.data.gov/dataset/"
    "epa-facility-registry-service-frs-facility-interests-dataset-download"
)
_EXPECTED_LEADS = {
    "110070205789": (
        "SYCAMORE ORANGETOWN - DATA CENTER BUILDING",
        "Orangeburg",
        "NY",
        ["data center", "building"],
    ),
    "110071506594": (
        "NVA13 - DATA CENTER SITE PLAN",
        "Manassas",
        "VA",
        ["data center", "site plan"],
    ),
    "110071509321": (
        "NTT GLOBAL DATA CENTER VA10 EARLY GRADING PLAN",
        "Gainesville",
        "VA",
        ["data center", "early grading plan"],
    ),
    "110071854750": (
        "SDC DFW-VII DATA CENTER PHASE 2",
        "Garland",
        "TX",
        ["data center", "phase 2"],
    ),
}
_INFERENCE_BANS = {
    "do_not_infer_construction_from_facility_name",
    "do_not_infer_data_center_identity_from_naics_alone",
    "do_not_infer_energy_from_naics_or_name",
    "do_not_infer_site_uniqueness_from_frs_registry_id",
    "do_not_merge_review_leads_into_atlas",
    "do_not_transfer_facility_interests_cc0_to_all_echo_program_data",
}


class EPAEchoFRSAssessmentError(ValueError):
    """Raised when the ECHO/FRS assessment or pilot fails closed."""


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
        raise EPAEchoFRSAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EPAEchoFRSAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EPAEchoFRSAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EPAEchoFRSAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EPAEchoFRSAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EPAEchoFRSAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise EPAEchoFRSAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != _canonical_json(value):
        raise EPAEchoFRSAssessmentError(f"{label} is not canonical JSON")
    return value


def _validate_retrievals(retrievals: Any, assessed_at: str) -> None:
    if not isinstance(retrievals, list):
        raise EPAEchoFRSAssessmentError("official_retrievals must be a list")
    source_ids: set[str] = set()
    for index, raw in enumerate(retrievals):
        record = _object(raw, f"official_retrievals[{index}]")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise EPAEchoFRSAssessmentError("retrieval source_id must be non-empty")
        if source_id in source_ids:
            raise EPAEchoFRSAssessmentError("retrieval source IDs must be unique")
        source_ids.add(source_id)
        publisher = record.get("publisher")
        url = record.get("url")
        if publisher not in _OFFICIAL_HOSTS or not isinstance(url, str):
            raise EPAEchoFRSAssessmentError("retrieval publisher or URL is invalid")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _OFFICIAL_HOSTS[publisher]
        ):
            raise EPAEchoFRSAssessmentError(
                "retrieval must use an official HTTPS host"
            )
        retrieved_at = _timestamp(
            record.get("retrieved_at"), "retrieval retrieved_at"
        )
        if retrieved_at > assessed_at:
            raise EPAEchoFRSAssessmentError("retrieval cannot postdate assessment")
        if record.get("http_status") != 200:
            raise EPAEchoFRSAssessmentError("retrieval HTTP status must be 200")
        byte_count = record.get("bytes")
        digest = record.get("sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise EPAEchoFRSAssessmentError(
                "retrieval size or SHA-256 is invalid"
            )
        if record.get("raw_artifact_retained") is not False:
            raise EPAEchoFRSAssessmentError(
                "assessment must not retain fetched source artifacts"
            )
    if source_ids != _REQUIRED_RETRIEVALS:
        raise EPAEchoFRSAssessmentError("official retrieval set differs")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact ECHO/FRS access, rights, and coverage decision."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise EPAEchoFRSAssessmentError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    _validate_retrievals(document.get("official_retrievals"), assessed_at)

    source = _object(document.get("source"), "source")
    if (
        source.get("name") != "EPA ECHO / Facility Registry Service (FRS)"
        or source.get("source_family") != SOURCE_FAMILY
        or source.get("query_endpoint") != _QUERY_ENDPOINT
        or source.get("facility_interests_catalog_url")
        != _FACILITY_INTERESTS_CATALOG_URL
    ):
        raise EPAEchoFRSAssessmentError("source identity changed")

    access = _object(document.get("access_assessment"), "access_assessment")
    required_access = {
        "authentication_required": False,
        "bulk_rest_loop_permitted_for_pilot": False,
        "data_downloads_recommended_for_large_volume": True,
        "get_query_only_services_public": True,
        "naics_518210_query_rows_at_probe": QUERY_ROWS,
        "pilot_get_facilities_requests": 1,
        "pilot_pagination_requests": 0,
        "responseset": 1000,
    }
    if any(access.get(key) != value for key, value in required_access.items()):
        raise EPAEchoFRSAssessmentError("access assessment changed")
    if access.get("query_naics") != "518210":
        raise EPAEchoFRSAssessmentError("bounded query changed")

    frs = _object(document.get("frs_identity_assessment"), "FRS assessment")
    expected_frs = {
        "frs_is_complete_us_data_center_inventory": False,
        "frs_links_program_records_for_the_same_facility_or_interest": True,
        "frs_registry_id_is_unique_physical_site_proof": False,
        "frs_supports_identity_and_address_fields": True,
        "frs_supports_naics_and_coordinates_when_available": True,
    }
    if any(frs.get(key) != value for key, value in expected_frs.items()):
        raise EPAEchoFRSAssessmentError("FRS identity semantics changed")

    rights = _object(document.get("rights_assessment"), "rights_assessment")
    expected_rights = {
        "cc0_applies_to_all_echo_program_data": False,
        "epa_produced_geospatial_data_public_domain_unless_specified": True,
        "facility_interests_catalog_license": "CC0-1.0",
        "facility_interests_catalog_modified": "2026-07-05",
        "facility_interests_cc0_scope_exact": True,
        "legal_conclusion_claimed": False,
        "pilot_field_lineage_to_cc0_download_verified": False,
        "pilot_publication_eligible": False,
        "referenced_third_party_data_may_have_separate_rights": True,
    }
    if any(rights.get(key) != value for key, value in expected_rights.items()):
        raise EPAEchoFRSAssessmentError("rights scope must fail closed")
    if (
        rights.get("facility_interests_cc0_scope")
        != "the cataloged EPA FRS Facility Interests dataset download only"
    ):
        raise EPAEchoFRSAssessmentError("CC0 dataset scope changed")

    coverage = _object(document.get("coverage_assessment"), "coverage_assessment")
    expected_coverage = {
        "all_data_centres_globally_claim_supported": False,
        "construction_verified_rows": 0,
        "excluded_false_positive_examples": 2,
        "name_token_review_leads": 4,
        "naics_518210_query_rows": QUERY_ROWS,
        "typed_capacity_rows": 0,
        "united_states_completeness_claimed": False,
        "unique_physical_site_count": None,
    }
    if any(coverage.get(key) != value for key, value in expected_coverage.items()):
        raise EPAEchoFRSAssessmentError("coverage assessment changed")

    fields = _object(document.get("field_assessment"), "field_assessment")
    missing = fields.get("unsupported_or_unverified_fields")
    required_missing = {
        "annual_energy_mwh",
        "construction_lifecycle_status",
        "coordinates",
        "data_center_type",
        "gross_power_capacity_mw",
        "it_load_mw",
        "operating_model",
        "operational_workload",
        "pue",
    }
    if not isinstance(missing, list) or set(missing) != required_missing:
        raise EPAEchoFRSAssessmentError("field-gap set changed")
    if (
        fields.get("facility_name_is_construction_verification") is not False
        or fields.get("naics_518210_is_data_center_proof") is not False
        or fields.get("name_tokens_establish_capacity_energy_or_pue") is not False
    ):
        raise EPAEchoFRSAssessmentError("field promotion controls changed")

    bans = document.get("inference_bans")
    if not isinstance(bans, list) or set(bans) != _INFERENCE_BANS:
        raise EPAEchoFRSAssessmentError("inference bans changed")

    decision = _object(document.get("atlas_decision"), "atlas_decision")
    expected_decision = {
        "auto_merge_permitted": False,
        "bounded_review_pilot_implemented": True,
        "bulk_rest_loop_permitted": False,
        "construction_status_promotion_permitted": False,
        "publication_eligible": False,
        "source_family": SOURCE_FAMILY,
        "status": "bounded_review_only_pending_exact_frs_field_lineage",
        "typed_metric_promotion_permitted": False,
    }
    if any(decision.get(key) != value for key, value in expected_decision.items()):
        raise EPAEchoFRSAssessmentError("Atlas decision changed")


def _validate_query(query: Any) -> None:
    record = _object(query, "query")
    url = record.get("url")
    if not isinstance(url, str):
        raise EPAEchoFRSAssessmentError("query URL must be text")
    parsed = urlsplit(url)
    if f"{parsed.scheme}://{parsed.netloc}{parsed.path}" != _QUERY_ENDPOINT:
        raise EPAEchoFRSAssessmentError("query endpoint changed")
    if parse_qs(parsed.query) != {
        "output": ["JSON"],
        "p_ncs": ["518210"],
        "responseset": ["1000"],
    }:
        raise EPAEchoFRSAssessmentError("query parameters changed")
    expected = {
        "bulk_loop_used": False,
        "executed_get_facilities_requests": 1,
        "http_status": 200,
        "pagination_requests": 0,
        "query_rows": QUERY_ROWS,
        "raw_response_retained": False,
        "responseset": 1000,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise EPAEchoFRSAssessmentError("bounded query controls changed")
    _timestamp(record.get("retrieved_at"), "query retrieved_at")
    if (
        record.get("bytes") != 352
        or record.get("sha256")
        != "ba8877cd529440865581cff92f1dc513ee9885ca28a466d90a3d6de19b6eddee"
    ):
        raise EPAEchoFRSAssessmentError("bounded query checkpoint changed")


def validate_pilot_document(document: Mapping[str, Any]) -> None:
    """Validate the conservative four-row, name-token-only review pilot."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != PILOT_FORMAT
        or document.get("pilot_id") != PILOT_ID
        or document.get("assessment_id") != ASSESSMENT_ID
        or document.get("source_family") != SOURCE_FAMILY
    ):
        raise EPAEchoFRSAssessmentError("pilot identity is invalid")
    _timestamp(document.get("generated_at"), "generated_at")
    expected_controls = {
        "atlas_merge_permitted": False,
        "construction_verified_rows": 0,
        "publication_eligible_rows": 0,
        "raw_source_artifacts_retained": False,
        "review_only": True,
        "typed_capacity_rows": 0,
        "typed_energy_rows": 0,
        "typed_pue_rows": 0,
        "typed_workload_rows": 0,
        "unique_physical_site_count": None,
    }
    if any(document.get(key) != value for key, value in expected_controls.items()):
        raise EPAEchoFRSAssessmentError("pilot must remain local and review-only")
    _validate_query(document.get("query"))

    screening = _object(document.get("screening"), "screening")
    expected_screening = {
        "explicit_name_token_required": True,
        "included_rows": 4,
        "naics_518210_is_data_center_proof": False,
        "screened_query_rows": QUERY_ROWS,
    }
    if any(
        screening.get(key) != value for key, value in expected_screening.items()
    ):
        raise EPAEchoFRSAssessmentError("screening semantics changed")

    leads = document.get("leads")
    if not isinstance(leads, list) or len(leads) != 4:
        raise EPAEchoFRSAssessmentError("pilot must contain four review leads")
    ids: list[str] = []
    null_fields = (
        "annual_energy_mwh",
        "atlas_lifecycle_status",
        "data_center_type",
        "gross_power_capacity_mw",
        "it_load_mw",
        "latitude",
        "longitude",
        "operating_model",
        "operational_workload",
        "pue",
    )
    for index, raw in enumerate(leads):
        lead = _object(raw, f"leads[{index}]")
        registry_id = lead.get("frs_registry_id")
        if registry_id not in _EXPECTED_LEADS or registry_id in ids:
            raise EPAEchoFRSAssessmentError("pilot FRS identity set differs")
        ids.append(registry_id)
        name, city, state, tokens = _EXPECTED_LEADS[registry_id]
        if (
            lead.get("lead_id") != f"epa-frs-{registry_id}"
            or lead.get("facility_name") != name
            or lead.get("city") != city
            or lead.get("state") != state
            or lead.get("country_code") != "US"
            or lead.get("naics_code") != "518210"
            or lead.get("name_token_matches") != tokens
        ):
            raise EPAEchoFRSAssessmentError("pilot lead facts changed")
        if any(lead.get(field) is not None for field in null_fields):
            raise EPAEchoFRSAssessmentError("review lead promoted an unsupported field")
        if (
            lead.get("construction_verified") is not False
            or lead.get("naics_is_data_center_proof") is not False
            or lead.get("publication_eligible") is not False
            or lead.get("review_only") is not True
            or lead.get("auto_merge_permitted") is not False
            or lead.get("rights_status")
            != "pending_exact_field_lineage_to_cc0_frs_download"
        ):
            raise EPAEchoFRSAssessmentError("review lead controls changed")
    if ids != sorted(_EXPECTED_LEADS):
        raise EPAEchoFRSAssessmentError("pilot leads must be deterministically sorted")

    excluded = document.get("excluded_examples")
    if not isinstance(excluded, list) or len(excluded) != 2:
        raise EPAEchoFRSAssessmentError("excluded false-positive set differs")
    construction_company = _object(excluded[0], "excluded_examples[0]")
    generic_building = _object(excluded[1], "excluded_examples[1]")
    if construction_company != {
        "exclusion_reason": (
            "construction_company_name_without_explicit_data_center_site_identity"
        ),
        "facility_name": "JE DUNN CONSTRUCTION",
        "frs_registry_id": "110070251348",
    }:
        raise EPAEchoFRSAssessmentError("construction-company exclusion changed")
    if generic_building != {
        "exclusion_reason": (
            "generic_building_name_without_explicit_data_center_identity"
        ),
        "facility_name": "INTERNATIONAL BUILDING",
        "frs_registry_id": None,
    }:
        raise EPAEchoFRSAssessmentError("generic-building exclusion changed")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable assessment and pilot without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise EPAEchoFRSAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise EPAEchoFRSAssessmentError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise EPAEchoFRSAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    pilot = _load_json(directory / PILOT_FILENAME, "pilot")
    validate_assessment_document(assessment)
    validate_pilot_document(pilot)
    if pilot.get("generated_at") != assessment.get("assessed_at"):
        raise EPAEchoFRSAssessmentError("assessment and pilot timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise EPAEchoFRSAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME, PILOT_FILENAME}:
        raise EPAEchoFRSAssessmentError("assessment manifest file set differs")
    for filename in (ASSESSMENT_FILENAME, PILOT_FILENAME):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise EPAEchoFRSAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (
        directory.joinpath(MANIFEST_HASH_FILENAME).read_text(encoding="utf-8")
        != expected_sidecar
    ):
        raise EPAEchoFRSAssessmentError("assessment manifest sidecar mismatch")
    return {"assessment": assessment, "pilot": pilot}


__all__ = [
    "ASSESSMENT_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "PILOT_FILENAME",
    "EPAEchoFRSAssessmentError",
    "validate_assessment_bundle",
    "validate_assessment_document",
    "validate_pilot_document",
]
