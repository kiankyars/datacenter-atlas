"""Validate the EdgeMode source-rights assessment and bounded EDGAR pilot."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


ASSESSMENT_FILENAME = "assessment.json"
PILOT_FILENAME = "pilot.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-source-rights-assessment-v1"
PILOT_FORMAT = "datacenter-atlas-edgemode-edgar-pilot-v1"
ASSESSMENT_ID = "edgemode-2026-07-18-v1"
PILOT_ID = "sec-edgar-edgemode-2026-07-18-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    PILOT_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_OFFICIAL_HOSTS = {
    "EdgeMode": {"www.edgemode.io"},
    "SEC": {"data.sec.gov", "www.sec.gov"},
}
_REQUIRED_RETRIEVALS = {
    "edgemode_home",
    "edgemode_sitemap",
    "sec_edgar_api_docs",
    "sec_edgemode_2026_01_22_8k",
    "sec_edgemode_2026_03_23_8k",
    "sec_edgemode_2026_06_24_8k",
    "sec_edgemode_2026_07_01_8k",
    "sec_edgemode_2026_q1_10q",
    "sec_edgemode_submissions",
    "sec_reuse_faq",
}
_NAMED_PROJECT_IDS = {
    "sec-edgar-edgm-caceres",
    "sec-edgar-edgm-cordoba",
    "sec-edgar-edgm-malpica-mora",
    "sec-edgar-edgm-tocumen",
    "sec-edgar-edgm-tomelloso",
    "sec-edgar-edgm-torrecampo",
    "sec-edgar-edgm-vianos",
    "sec-edgar-edgm-villasequilla",
}
_UNRESOLVED_LEAD_ID = "sec-edgar-edgm-palma-unresolved"


class EdgeModeAssessmentError(ValueError):
    """Raised when the EdgeMode assessment or pilot fails closed."""


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
        raise EdgeModeAssessmentError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EdgeModeAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EdgeModeAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EdgeModeAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EdgeModeAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EdgeModeAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise EdgeModeAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != _canonical_json(value):
        raise EdgeModeAssessmentError(f"{label} is not canonical JSON")
    return value


def _validate_retrievals(retrievals: Any) -> None:
    if not isinstance(retrievals, list):
        raise EdgeModeAssessmentError("official_retrievals must be a list")
    source_ids: set[str] = set()
    for index, raw in enumerate(retrievals):
        record = _object(raw, f"official_retrievals[{index}]")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise EdgeModeAssessmentError("retrieval source_id must be non-empty")
        if source_id in source_ids:
            raise EdgeModeAssessmentError("retrieval source_id values must be unique")
        source_ids.add(source_id)
        publisher = record.get("publisher")
        url = record.get("url")
        if publisher not in _OFFICIAL_HOSTS or not isinstance(url, str):
            raise EdgeModeAssessmentError("retrieval publisher or URL is invalid")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in _OFFICIAL_HOSTS[publisher]:
            raise EdgeModeAssessmentError("retrieval must use an official HTTPS host")
        _timestamp(record.get("retrieved_at"), "retrieval retrieved_at")
        if record.get("http_status") != 200:
            raise EdgeModeAssessmentError("retrieval HTTP status must be 200")
        byte_count = record.get("bytes")
        digest = record.get("sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise EdgeModeAssessmentError("retrieval size or SHA-256 is invalid")
        if record.get("raw_artifact_retained") is not False:
            raise EdgeModeAssessmentError("assessment must not retain fetched pages")
    if source_ids != _REQUIRED_RETRIEVALS:
        raise EdgeModeAssessmentError("official retrieval set differs")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact source-governance decision."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise EdgeModeAssessmentError("assessment identity is invalid")
    _timestamp(document.get("assessed_at"), "assessed_at")
    _validate_retrievals(document.get("official_retrievals"))

    source = _object(document.get("source"), "source")
    if (
        source.get("name") != "EdgeMode"
        or source.get("cik") != "0001652958"
        or source.get("official_website") != "https://www.edgemode.io/"
        or source.get("sec_submissions_api")
        != "https://data.sec.gov/submissions/CIK0001652958.json"
    ):
        raise EdgeModeAssessmentError("source identity changed")

    access = _object(document.get("access_assessment"), "access_assessment")
    required_access = {
        "direct_edgemode_api_documented": False,
        "edgemode_sitemap_url_count": 3,
        "sec_api_authentication_required": False,
        "sec_company_submissions_api_available": True,
        "sec_recent_8k_10q_10k_records_at_probe": 109,
    }
    if any(access.get(key) != value for key, value in required_access.items()):
        raise EdgeModeAssessmentError("access assessment changed")
    if (
        access.get("latest_filing_at_probe") != "2026-07-15"
        or access.get("latest_data_center_relevant_filing_at_probe")
        != "2026-07-06"
        or access.get("sec_api_is_an_edgemode_operated_api") is not False
    ):
        raise EdgeModeAssessmentError("filing cutoff or API ownership changed")

    rights = _object(document.get("rights_assessment"), "rights_assessment")
    website = _object(rights.get("edgemode_website"), "edgemode website rights")
    if (
        website.get("copyright_notice") != "All rights reserved"
        or website.get("redistribution_license_found") is not False
        or website.get("commercial_reuse_permission_clear") is not False
        or website.get("bulk_fetch_permitted") is not False
        or website.get("direct_release_permitted") is not False
    ):
        raise EdgeModeAssessmentError("direct EdgeMode website rights must fail closed")
    edgar = _object(rights.get("sec_edgar"), "SEC EDGAR rights")
    if (
        edgar.get("public_filing_content_free_to_access_and_reuse") is not True
        or edgar.get("reuse_statement_is_unqualified") is not True
        or edgar.get("commercial_use_expressly_named") is not False
        or edgar.get("commercial_use_permission_clear_for_bounded_pilot") is not True
        or edgar.get("scripted_access_allowed_subject_to_fair_access") is not True
        or edgar.get("bounded_derived_pilot_permitted") is not True
        or edgar.get("legal_conclusion_claimed") is not False
    ):
        raise EdgeModeAssessmentError("SEC EDGAR reuse decision changed")

    coverage = _object(document.get("coverage_assessment"), "coverage_assessment")
    expected_coverage = {
        "all_data_centres_globally_claim_supported": False,
        "named_project_identity_leads": 8,
        "pilot_rows": 9,
        "unresolved_additional_land_labels": 1,
        "unique_facility_count": None,
        "website_claimed_spain_campuses": 5,
        "website_claimed_it_load_mw_minimum": 1500,
        "sec_disclosed_spain_aggregate_capacity_mw": 4350,
        "sec_disclosed_panama_project_capacity_mw": 1000,
        "website_and_filing_scope_reconciled": False,
    }
    if any(coverage.get(key) != value for key, value in expected_coverage.items()):
        raise EdgeModeAssessmentError("coverage assessment changed")

    fields = _object(document.get("field_assessment"), "field_assessment")
    missing = fields.get("structured_fields_not_available")
    required_missing = {
        "annual_energy_mwh",
        "construction_lifecycle_status",
        "coordinates",
        "current_site_allocated_power_mw",
        "gross_power_capacity_mw",
        "it_load_mw_from_edgar",
        "operational_workload",
        "pue",
    }
    if not isinstance(missing, list) or not required_missing.issubset(missing):
        raise EdgeModeAssessmentError("required field gaps are missing")
    if (
        fields.get("developer_language_is_construction_verification") is not False
        or fields.get("source_mw_is_typed_as_gross_or_it_load") is not False
        or fields.get("intended_workload_is_operational_workload") is not False
    ):
        raise EdgeModeAssessmentError("field promotion controls changed")

    decision = _object(document.get("atlas_decision"), "atlas_decision")
    expected_decision = {
        "direct_edgemode_bulk_fetch_permitted": False,
        "direct_edgemode_release_permitted": False,
        "sec_edgar_bounded_pilot_implemented": True,
        "sec_edgar_bounded_pilot_publication_eligible": True,
        "sec_edgar_lane_review_only": True,
        "source_family": "sec_edgar_edgemode",
        "status": "bounded_sec_edgar_pilot_only",
    }
    if any(decision.get(key) != value for key, value in expected_decision.items()):
        raise EdgeModeAssessmentError("Atlas decision changed")
    if (
        decision.get("auto_merge_permitted") is not False
        or decision.get("construction_status_promotion_permitted") is not False
        or decision.get("typed_capacity_promotion_permitted") is not False
    ):
        raise EdgeModeAssessmentError("pilot promotion controls changed")


def validate_pilot_document(document: Mapping[str, Any]) -> None:
    """Validate the bounded, derived, review-only EDGAR lead set."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != PILOT_FORMAT
        or document.get("pilot_id") != PILOT_ID
        or document.get("assessment_id") != ASSESSMENT_ID
        or document.get("source_family") != "sec_edgar_edgemode"
    ):
        raise EdgeModeAssessmentError("pilot identity is invalid")
    _timestamp(document.get("generated_at"), "pilot generated_at")
    if (
        document.get("raw_source_artifacts_retained") is not False
        or document.get("review_only") is not True
        or document.get("unique_facility_count") is not None
        or document.get("construction_verified_rows") != 0
        or document.get("typed_capacity_rows") != 0
    ):
        raise EdgeModeAssessmentError("pilot must remain review-only and untyped")

    evidence = document.get("evidence_documents")
    if not isinstance(evidence, list) or len(evidence) != 5:
        raise EdgeModeAssessmentError("pilot evidence document set differs")
    evidence_ids: set[str] = set()
    for index, raw in enumerate(evidence):
        record = _object(raw, f"evidence_documents[{index}]")
        evidence_id = record.get("evidence_id")
        url = record.get("url")
        digest = record.get("sha256")
        if (
            not isinstance(evidence_id, str)
            or evidence_id in evidence_ids
            or not isinstance(url, str)
            or urlsplit(url).hostname != "www.sec.gov"
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise EdgeModeAssessmentError("pilot evidence record is invalid")
        evidence_ids.add(evidence_id)

    leads = document.get("leads")
    if not isinstance(leads, list) or len(leads) != 9:
        raise EdgeModeAssessmentError("pilot must contain nine review leads")
    lead_ids: set[str] = set()
    countries: dict[str, int] = {}
    unresolved = 0
    for index, raw in enumerate(leads):
        lead = _object(raw, f"leads[{index}]")
        lead_id = lead.get("lead_id")
        if not isinstance(lead_id, str) or lead_id in lead_ids:
            raise EdgeModeAssessmentError("lead IDs must be unique")
        lead_ids.add(lead_id)
        country = lead.get("country_code")
        if country not in {"ES", "PA"}:
            raise EdgeModeAssessmentError("pilot country is invalid")
        countries[country] = countries.get(country, 0) + 1
        if lead.get("project_identity_status") == "unresolved_land_label":
            unresolved += 1
        elif lead.get("project_identity_status") != "named_project":
            raise EdgeModeAssessmentError("project identity status is invalid")
        references = lead.get("evidence_ids")
        if (
            not isinstance(references, list)
            or not references
            or not set(references).issubset(evidence_ids)
        ):
            raise EdgeModeAssessmentError("lead evidence references are invalid")
        null_fields = (
            "annual_energy_mwh",
            "atlas_lifecycle_status",
            "gross_power_capacity_mw",
            "it_load_mw",
            "latitude",
            "longitude",
            "pue",
        )
        if any(lead.get(field) is not None for field in null_fields):
            raise EdgeModeAssessmentError("review lead promoted an unsupported field")
        source_power = lead.get("source_power_statements")
        if not isinstance(source_power, list):
            raise EdgeModeAssessmentError("source power statements must be a list")
        expected_metric = (
            "unspecified_power_capacity" if source_power else "not_available"
        )
        if (
            lead.get("construction_verified") is not False
            or lead.get("operational_workload_verified") is not False
            or lead.get("source_mw_metric_type") != expected_metric
        ):
            raise EdgeModeAssessmentError("review lead semantics changed")
    if lead_ids != _NAMED_PROJECT_IDS | {_UNRESOLVED_LEAD_ID}:
        raise EdgeModeAssessmentError("pilot lead identity set differs")
    if countries != {"ES": 8, "PA": 1} or unresolved != 1:
        raise EdgeModeAssessmentError("pilot geography or ambiguity count differs")

    reconciliation = _object(
        document.get("capacity_reconciliation"), "capacity_reconciliation"
    )
    expected_reconciliation = {
        "five_site_management_plan_mw": 1800,
        "named_spain_project_scoped_mw_sum": 2850,
        "spain_aggregate_mw": 4350,
        "unallocated_spain_aggregate_gap_mw": 1500,
        "panama_project_scoped_mw": 1000,
        "cross_country_total_emitted": False,
        "typed_capacity_total_emitted": False,
    }
    if any(
        reconciliation.get(key) != value
        for key, value in expected_reconciliation.items()
    ):
        raise EdgeModeAssessmentError("capacity reconciliation changed")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable assessment and pilot without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise EdgeModeAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise EdgeModeAssessmentError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise EdgeModeAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    pilot = _load_json(directory / PILOT_FILENAME, "pilot")
    validate_assessment_document(assessment)
    validate_pilot_document(pilot)
    if pilot.get("generated_at") != assessment.get("assessed_at"):
        raise EdgeModeAssessmentError("assessment and pilot timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise EdgeModeAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME, PILOT_FILENAME}:
        raise EdgeModeAssessmentError("assessment manifest file set differs")
    for filename in (ASSESSMENT_FILENAME, PILOT_FILENAME):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise EdgeModeAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (directory / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != expected_sidecar:
        raise EdgeModeAssessmentError("assessment manifest sidecar mismatch")
    return {"assessment": assessment, "pilot": pilot}
