"""Build and validate the open Ireland planning-application review lane."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from unicodedata import normalize as unicode_normalize
from urllib.parse import quote, urlencode, urlsplit


SCHEMA_VERSION = 1
RELEASE_FORMAT = "datacenter-atlas-ireland-planning-release-v1"
SCHEMA_FORMAT = "datacenter-atlas-ireland-planning-schema-v1"
SUMMARY_FORMAT = "datacenter-atlas-ireland-planning-summary-v1"
RELEASE_ID = "ireland-planning-data-centres-2026-07-18-v1"
DATASET_PAGE_URL = "https://data.gov.ie/en_GB/dataset/irishplanningapplications1"
CKAN_PACKAGE_URL = (
    "https://data.gov.ie/api/3/action/package_show?id=irishplanningapplications1"
)
CC_BY_4_LEGALCODE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode.en"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
SERVICE_URL = (
    "https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/"
    "IrishPlanningApplications/FeatureServer"
)
LAYER_URL = f"{SERVICE_URL}/0"
KPMG_REPORT_URL = (
    "https://enterprise.gov.ie/en/publications/publication-files/"
    "the-value-of-data-centres-to-ireland.pdf"
)

BASELINE_WHERE = (
    "(DevelopmentDescription LIKE '%data center%' OR "
    "DevelopmentDescription LIKE '%data centre%' OR "
    "DevelopmentDescription LIKE '%datacenter%' OR "
    "DevelopmentDescription LIKE '%datacentre%')"
)
EXTENSION_WHERE = (
    "(DevelopmentDescription LIKE '%data hall%' OR "
    "DevelopmentDescription LIKE '%data processing centre%') AND NOT "
    f"{BASELINE_WHERE}"
)
FINAL_WHERE = (
    f"({BASELINE_WHERE} OR DevelopmentDescription LIKE '%data hall%' OR "
    "DevelopmentDescription LIKE '%data processing centre%')"
)
DATA_HALL_INCREMENTAL_WHERE = (
    "DevelopmentDescription LIKE '%data hall%' AND NOT " + BASELINE_WHERE
)
DATA_PROCESSING_INCREMENTAL_WHERE = (
    "DevelopmentDescription LIKE '%data processing centre%' AND NOT "
    + BASELINE_WHERE
)
SERVER_ROOM_INCREMENTAL_WHERE = (
    "DevelopmentDescription LIKE '%server room%' AND NOT " + BASELINE_WHERE
)
COLOCATION_INCREMENTAL_WHERE = (
    "DevelopmentDescription LIKE '%co-location facility%' AND NOT "
    + BASELINE_WHERE
)

MATCH_TERMS = (
    "data center",
    "data centre",
    "datacenter",
    "datacentre",
    "data hall",
    "data processing centre",
)
BASELINE_TERMS = MATCH_TERMS[:4]
EXTENSION_TERMS = MATCH_TERMS[4:]

SOURCE_FIELDS = (
    "OBJECTID",
    "PlanningAuthority",
    "ApplicationNumber",
    "DevelopmentDescription",
    "DevelopmentAddress",
    "DevelopmentPostcode",
    "ITMEasting",
    "ITMNorthing",
    "ApplicationStatus",
    "ApplicationType",
    "ApplicantForename",
    "ApplicantSurname",
    "ApplicantAddress",
    "Decision",
    "LandUseCode",
    "AreaofSite",
    "NumResidentialUnits",
    "OneOffHouse",
    "FloorArea",
    "ReceivedDate",
    "WithdrawnDate",
    "DecisionDate",
    "DecisionDueDate",
    "GrantDate",
    "ExpiryDate",
    "AppealRefNumber",
    "AppealStatus",
    "AppealDecision",
    "AppealDecisionDate",
    "AppealSubmittedDate",
    "FIRequestDate",
    "FIRecDate",
    "LinkAppDetails",
    "OneOffKPI",
    "ETL_DATE",
    "SiteId",
    "ORIG_FID",
)
DATE_FIELDS = (
    "ReceivedDate",
    "WithdrawnDate",
    "DecisionDate",
    "DecisionDueDate",
    "GrantDate",
    "ExpiryDate",
    "AppealDecisionDate",
    "AppealSubmittedDate",
    "FIRequestDate",
    "FIRecDate",
    "ETL_DATE",
)
STATUS_FIELDS = (
    "ApplicationStatus",
    "ApplicationType",
    "Decision",
    "AppealStatus",
    "AppealDecision",
)
NUMERIC_FIELD_UNITS = {
    "AreaofSite": "unknown_source_unit",
    "FloorArea": "unknown_source_unit",
    "ITMEasting": "unknown_source_unit",
    "ITMNorthing": "unknown_source_unit",
    "NumResidentialUnits": "count",
    "OBJECTID": "identifier_not_quantity",
    "ORIG_FID": "identifier_not_quantity",
}

_EXPECTED_TOTAL_COUNT = 499_712
_EXPECTED_BASELINE_COUNT = 102
_EXPECTED_DATA_HALL_INCREMENTAL_COUNT = 11
_EXPECTED_DATA_PROCESSING_INCREMENTAL_COUNT = 1
_EXPECTED_EXTENSION_COUNT = 12
_EXPECTED_FINAL_COUNT = 114
_EXPECTED_SERVER_ROOM_INCREMENTAL_COUNT = 14
_EXPECTED_COLOCATION_INCREMENTAL_COUNT = 2
_EXPECTED_KPMG_BYTES = 2_370_214
_EXPECTED_KPMG_SHA256 = (
    "827cce20e9a206694e02c26bb823bf5700f974b7e08dc99f9ef41d68b5b091c7"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OFFICIAL_HOSTS = {
    "creativecommons.org",
    "data.gov.ie",
    "services.arcgis.com",
}


def _query_url(parameters: Iterable[tuple[str, str]]) -> str:
    return f"{LAYER_URL}/query?{urlencode(list(parameters), quote_via=quote)}"


def _count_url(where: str) -> str:
    return _query_url(
        (("where", where), ("returnCountOnly", "true"), ("f", "json"))
    )


MATCHED_PAGE_URL = _query_url(
    (
        ("where", FINAL_WHERE),
        ("outFields", "*"),
        ("returnGeometry", "true"),
        ("outSR", "4326"),
        ("orderByFields", "OBJECTID ASC"),
        ("resultOffset", "0"),
        ("resultRecordCount", "2000"),
        ("f", "json"),
    )
)
COLOCATION_REVIEW_PAGE_URL = _query_url(
    (
        ("where", COLOCATION_INCREMENTAL_WHERE),
        (
            "outFields",
            "OBJECTID,PlanningAuthority,ApplicationNumber,"
            "DevelopmentDescription,DevelopmentAddress",
        ),
        ("returnGeometry", "false"),
        ("orderByFields", "OBJECTID ASC"),
        ("resultOffset", "0"),
        ("resultRecordCount", "2000"),
        ("f", "json"),
    )
)

RAW_ARTIFACTS = {
    "baseline_count": {
        "filename": "raw/baseline-count.json",
        "url": _count_url(BASELINE_WHERE),
    },
    "cc_by_4_legalcode": {
        "filename": "raw/cc-by-4.0-legalcode.html",
        "url": CC_BY_4_LEGALCODE_URL,
    },
    "ckan_package": {
        "filename": "raw/data-gov-ie-package.json",
        "url": CKAN_PACKAGE_URL,
    },
    "colocation_incremental_count": {
        "filename": "raw/colocation-incremental-count.json",
        "url": _count_url(COLOCATION_INCREMENTAL_WHERE),
    },
    "colocation_review_page_00000": {
        "filename": "raw/colocation-review-page-00000.json",
        "url": COLOCATION_REVIEW_PAGE_URL,
    },
    "data_hall_incremental_count": {
        "filename": "raw/data-hall-incremental-count.json",
        "url": _count_url(DATA_HALL_INCREMENTAL_WHERE),
    },
    "data_processing_incremental_count": {
        "filename": "raw/data-processing-incremental-count.json",
        "url": _count_url(DATA_PROCESSING_INCREMENTAL_WHERE),
    },
    "dataset_page": {
        "filename": "raw/data-gov-ie-dataset.html",
        "url": DATASET_PAGE_URL,
    },
    "extension_count": {
        "filename": "raw/extension-count.json",
        "url": _count_url(EXTENSION_WHERE),
    },
    "feature_service": {
        "filename": "raw/feature-service.json",
        "url": f"{SERVICE_URL}?f=pjson",
    },
    "final_count": {
        "filename": "raw/final-count.json",
        "url": _count_url(FINAL_WHERE),
    },
    "layer_definition": {
        "filename": "raw/layer-0.json",
        "url": f"{LAYER_URL}?f=pjson",
    },
    "matched_features_page_00000": {
        "filename": "raw/matched-features-page-00000.json",
        "url": MATCHED_PAGE_URL,
    },
    "server_room_incremental_count": {
        "filename": "raw/server-room-incremental-count.json",
        "url": _count_url(SERVER_ROOM_INCREMENTAL_WHERE),
    },
    "total_count": {
        "filename": "raw/total-count.json",
        "url": _count_url("1=1"),
    },
}
_RIGHTS_EVIDENCE_ARTIFACT_IDS = frozenset(
    {"cc_by_4_legalcode", "dataset_page"}
)
_RIGHTS_EVIDENCE_FILENAMES = frozenset(
    RAW_ARTIFACTS[artifact_id]["filename"]
    for artifact_id in _RIGHTS_EVIDENCE_ARTIFACT_IDS
)
_MANIFEST_LICENSE_SCOPE = (
    "CC BY 4.0 applies to IrishPlanningApplications dataset/service artifacts "
    "and the attributed derived observations; rights-evidence reference copies "
    "retain their own terms"
)

DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "observations.csv",
    "observations.jsonl",
    "relationship-suggestions.jsonl",
    "schema.json",
    "summary.json",
}
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
_EXPECTED_FILES = (
    {record["filename"] for record in RAW_ARTIFACTS.values()}
    | DERIVED_FILENAMES
    | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
)

_EXPECTED_RIGHTS = {
    "adaptation_permitted": True,
    "affirmative_commercial_use_permission_found": True,
    "affirmative_redistribution_permission_found": True,
    "attribution_required": True,
    "dataset_is_open": True,
    "indicate_changes_required": True,
    "legal_conclusion_claimed": False,
    "license_id": "CC-BY-4.0",
    "license_title": "Creative Commons Attribution 4.0",
    "license_url": CC_BY_4_URL,
    "no_additional_restrictions_required": True,
    "raw_source_release_permitted": True,
}

_EXPECTED_STATUS_SEMANTICS = {
    "appeal_fields_are_source_process_fields": True,
    "application_status_is_facility_lifecycle": False,
    "decision_is_construction_or_operation_evidence": False,
    "expiry_date_is_operation_evidence": False,
    "grant_date_is_construction_evidence": False,
    "refused_withdrawn_and_expired_values_preserved": True,
}

_EXPECTED_GRANULARITY = {
    "application_observation_is_unique_facility": False,
    "auto_entity_merge_permitted": False,
    "duplicate_amendment_retention_fi_and_appeal_records_kept_separate": True,
    "relationship_suggestions_are_review_only": True,
    "unique_site_count": None,
}

_EXPECTED_INFERENCE_BANS = {
    "do_not_infer_annual_energy",
    "do_not_infer_construction_or_operation_from_application_fields",
    "do_not_infer_data_centre_type_or_workload_from_description",
    "do_not_infer_mw_mva_or_it_capacity",
    "do_not_infer_pue",
    "do_not_merge_application_observations_automatically",
    "do_not_treat_application_count_as_unique_site_count",
    "do_not_use_kpmg_aggregates_to_label_or_size_application_rows",
}

_EXPECTED_DECISION = {
    "auto_merge_permitted": False,
    "construction_status_promotion_permitted": False,
    "open_source_release_created": True,
    "planning_application_observations_published": _EXPECTED_FINAL_COUNT,
    "source_content_publication_eligible": True,
    "status": "cc_by_4_open_planning_observations",
    "typed_power_energy_or_pue_promotion_permitted": False,
    "unique_site_count_published": False,
}


class IrelandPlanningError(ValueError):
    """Raised when the Ireland planning release violates its contract."""


def canonical_json(value: Any) -> bytes:
    """Return canonical pretty JSON for immutable release documents."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _jsonl(values: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
        for value in values
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IrelandPlanningError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IrelandPlanningError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IrelandPlanningError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IrelandPlanningError(f"{field} must be an object")
    return value


def _raw_json(raw_bodies: Mapping[str, bytes], artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(raw_bodies[artifact_id].decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise IrelandPlanningError(f"invalid JSON artifact {artifact_id}") from error
    if not isinstance(value, dict):
        raise IrelandPlanningError(f"{artifact_id} must contain an object")
    return value


def _count(payload: Mapping[str, Any], artifact_id: str) -> int:
    if set(payload) != {"count"}:
        raise IrelandPlanningError(f"{artifact_id} is not count-only")
    count = payload.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise IrelandPlanningError(f"{artifact_id} count is invalid")
    return count


def _validate_retrievals(
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
) -> dict[str, dict[str, Any]]:
    if set(retrievals) != set(RAW_ARTIFACTS) or set(raw_bodies) != set(
        RAW_ARTIFACTS
    ):
        raise IrelandPlanningError("open artifact set differs")
    result: dict[str, dict[str, Any]] = {}
    for artifact_id, specification in RAW_ARTIFACTS.items():
        record = _object(retrievals[artifact_id], f"retrievals.{artifact_id}")
        body = raw_bodies[artifact_id]
        effective_url = record.get("effective_url")
        content_type = record.get("content_type")
        if (
            not isinstance(body, bytes)
            or not body
            or record.get("url") != specification["url"]
            or record.get("http_status") != 200
            or not isinstance(effective_url, str)
            or urlsplit(effective_url).scheme != "https"
            or urlsplit(effective_url).hostname not in _OFFICIAL_HOSTS
            or not isinstance(content_type, str)
            or not content_type
        ):
            raise IrelandPlanningError("open artifact retrieval metadata is invalid")
        result[artifact_id] = {
            "bytes": len(body),
            "content_type": content_type,
            "effective_url": effective_url,
            "filename": specification["filename"],
            "http_status": 200,
            "license_id": (
                None
                if artifact_id in _RIGHTS_EVIDENCE_ARTIFACT_IDS
                else "CC-BY-4.0"
            ),
            "rights_scope": (
                "license_evidence_reference_copy"
                if artifact_id in _RIGHTS_EVIDENCE_ARTIFACT_IDS
                else "licensed_dataset_or_service_artifact"
            ),
            "sha256": sha256_bytes(body),
            "url": specification["url"],
        }
    return result


def _validate_calibration(calibration: Mapping[str, Any]) -> dict[str, Any]:
    record = deepcopy(dict(calibration))
    if record != {
        "aggregate_only": True,
        "as_of_year": 2025,
        "bytes": _EXPECTED_KPMG_BYTES,
        "content_type": "application/pdf",
        "http_status": 200,
        "installed_it_capacity_mw": 1543,
        "operational_grid_connected_buildings": 72,
        "operational_sites": 36,
        "planning_projects_excluded": True,
        "raw_artifact_retained": False,
        "rights_notice": "KPMG All Rights Reserved",
        "row_labeling_or_capacity_assignment_permitted": False,
        "sha256": _EXPECTED_KPMG_SHA256,
        "url": KPMG_REPORT_URL,
    }:
        raise IrelandPlanningError("restricted calibration boundary changed")
    return record


def _date_contract(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IrelandPlanningError("ArcGIS date value must be numeric epoch milliseconds")
    timestamp = datetime.fromtimestamp(value / 1000, tz=UTC)
    return {
        "source_epoch_ms": value,
        "utc": timestamp.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    }


def _matched_terms(description: Any) -> list[str]:
    if not isinstance(description, str):
        return []
    normalized = description.casefold()
    return [term for term in MATCH_TERMS if term in normalized]


def _normalize_feature(feature: Mapping[str, Any], retrieved_at: str) -> dict[str, Any]:
    attributes = _object(feature.get("attributes"), "feature attributes")
    if set(attributes) != set(SOURCE_FIELDS):
        raise IrelandPlanningError("feature attribute set differs from layer schema")
    object_id = attributes.get("OBJECTID")
    if isinstance(object_id, bool) or not isinstance(object_id, int):
        raise IrelandPlanningError("OBJECTID must be an integer")
    terms = _matched_terms(attributes.get("DevelopmentDescription"))
    if not terms:
        raise IrelandPlanningError("feature does not match the documented vocabulary")
    geometry = feature.get("geometry")
    coordinates: dict[str, Any] | None
    if geometry is None:
        coordinates = None
    else:
        geometry_record = _object(geometry, "feature geometry")
        longitude = geometry_record.get("x")
        latitude = geometry_record.get("y")
        if (
            isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
            or not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
        ):
            raise IrelandPlanningError("feature geometry is not valid EPSG:4326")
        coordinates = {
            "crs": "EPSG:4326",
            "latitude": latitude,
            "longitude": longitude,
        }
    dates = {
        field: _date_contract(attributes.get(field)) for field in DATE_FIELDS
    }
    numeric_fields = {
        field: {
            "unit": unit,
            "value": attributes.get(field),
        }
        for field, unit in NUMERIC_FIELD_UNITS.items()
    }
    return {
        "coordinates": coordinates,
        "dates": dates,
        "evidence_scope": {
            "construction_evidence": False,
            "facility_lifecycle_status": None,
            "operation_evidence": False,
            "record_type": "planning_application_observation",
        },
        "license": {
            "id": "CC-BY-4.0",
            "title": "Creative Commons Attribution 4.0",
            "url": CC_BY_4_URL,
        },
        "matched_terms": terms,
        "observation_id": f"ie-planning-application:layer-0:{object_id}",
        "observation_type": "planning_application",
        "retrieved_at": retrieved_at,
        "source_application_key": {
            "application_number": attributes.get("ApplicationNumber"),
            "planning_authority": attributes.get("PlanningAuthority"),
        },
        "source_attributes": dict(attributes),
        "source_geometry": deepcopy(geometry),
        "source_layer_id": 0,
        "source_numeric_fields": numeric_fields,
        "source_status": {
            field: attributes.get(field) for field in STATUS_FIELDS
        },
    }


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicode_normalize("NFKC", value).casefold().split())


def _relationship_suggestions(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groupers: dict[str, defaultdict[str, list[str]]] = {
        "shared_authority_application_number": defaultdict(list),
        "shared_authority_normalized_address": defaultdict(list),
        "shared_exact_wgs84_coordinate": defaultdict(list),
        "shared_source_site_id": defaultdict(list),
    }
    for observation in observations:
        attributes = observation["source_attributes"]
        observation_id = observation["observation_id"]
        authority = _normalized_text(attributes.get("PlanningAuthority"))
        application = _normalized_text(attributes.get("ApplicationNumber"))
        address = _normalized_text(attributes.get("DevelopmentAddress"))
        site_id = _normalized_text(attributes.get("SiteId"))
        coordinates = observation["coordinates"]
        if authority and application:
            groupers["shared_authority_application_number"][
                f"{authority}\u0000{application}"
            ].append(observation_id)
        if authority and address:
            groupers["shared_authority_normalized_address"][
                f"{authority}\u0000{address}"
            ].append(observation_id)
        if coordinates is not None:
            groupers["shared_exact_wgs84_coordinate"][
                f"{coordinates['longitude']!r}\u0000{coordinates['latitude']!r}"
            ].append(observation_id)
        if site_id:
            groupers["shared_source_site_id"][site_id].append(observation_id)

    suggestions: list[dict[str, Any]] = []
    for basis in sorted(groupers):
        for key, raw_members in sorted(groupers[basis].items()):
            members = sorted(set(raw_members))
            if len(members) < 2:
                continue
            digest = hashlib.sha256(f"{basis}\u0000{key}".encode()).hexdigest()[:20]
            suggestions.append(
                {
                    "auto_merge_permitted": False,
                    "basis": basis,
                    "member_observation_ids": members,
                    "review_only": True,
                    "suggestion_id": f"ie-planning-relationship:{digest}",
                }
            )
    return suggestions


def _source_value_counts(
    observations: list[dict[str, Any]], field: str
) -> dict[str, int]:
    values: Counter[str] = Counter()
    for observation in observations:
        value = observation["source_attributes"].get(field)
        key = "<null>" if value is None else str(value)
        values[key] += 1
    return dict(sorted(values.items()))


def _received_year_counts(observations: list[dict[str, Any]]) -> dict[str, int]:
    values: Counter[str] = Counter()
    for observation in observations:
        contract = observation["dates"]["ReceivedDate"]
        if contract is None:
            values["<null>"] += 1
        else:
            values[contract["utc"][:4]] += 1
    return dict(sorted(values.items()))


def _build_summary(
    observations: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    retrieved_at: str,
) -> dict[str, Any]:
    object_ids = [
        observation["source_attributes"]["OBJECTID"] for observation in observations
    ]
    application_keys = {
        (
            observation["source_attributes"].get("PlanningAuthority"),
            observation["source_attributes"].get("ApplicationNumber"),
        )
        for observation in observations
    }
    members_in_suggestions = {
        member
        for suggestion in suggestions
        for member in suggestion["member_observation_ids"]
    }
    suggestion_counts = Counter(
        suggestion["basis"] for suggestion in suggestions
    )
    description_counts = Counter(
        term for observation in observations for term in observation["matched_terms"]
    )
    numeric_non_null = {
        field: sum(
            observation["source_attributes"].get(field) is not None
            for observation in observations
        )
        for field in NUMERIC_FIELD_UNITS
    }
    date_non_null = {
        field: sum(observation["dates"][field] is not None for observation in observations)
        for field in DATE_FIELDS
    }
    explicit_flags = {
        "appeal_reference_present": sum(
            bool(observation["source_attributes"].get("AppealRefNumber"))
            for observation in observations
        ),
        "decision_mentions_refusal": sum(
            "refus"
            in str(observation["source_attributes"].get("Decision") or "").casefold()
            for observation in observations
        ),
        "expiry_date_present": date_non_null["ExpiryDate"],
        "fi_request_or_response_present": sum(
            observation["dates"]["FIRequestDate"] is not None
            or observation["dates"]["FIRecDate"] is not None
            for observation in observations
        ),
        "grant_date_present": date_non_null["GrantDate"],
        "withdrawn_date_present": date_non_null["WithdrawnDate"],
    }
    return {
        "application_status_counts_exact": _source_value_counts(
            observations, "ApplicationStatus"
        ),
        "application_type_counts_exact": _source_value_counts(
            observations, "ApplicationType"
        ),
        "appeal_decision_counts_exact": _source_value_counts(
            observations, "AppealDecision"
        ),
        "appeal_status_counts_exact": _source_value_counts(
            observations, "AppealStatus"
        ),
        "authority_application_key_count": len(application_keys),
        "baseline_exact_phrase_count": _EXPECTED_BASELINE_COUNT,
        "coordinate_counts": {
            "complete_wgs84_points": sum(
                observation["coordinates"] is not None
                for observation in observations
            ),
            "missing_geometry": sum(
                observation["coordinates"] is None for observation in observations
            ),
        },
        "decision_counts_exact": _source_value_counts(observations, "Decision"),
        "distinct_objectid_count": len(set(object_ids)),
        "explicit_source_field_flag_counts": explicit_flags,
        "extension_count": _EXPECTED_EXTENSION_COUNT,
        "format": SUMMARY_FORMAT,
        "generated_at": retrieved_at,
        "land_use_code_counts_exact": _source_value_counts(
            observations, "LandUseCode"
        ),
        "matched_observation_count": len(observations),
        "matched_term_counts": dict(sorted(description_counts.items())),
        "numeric_field_non_null_counts": numeric_non_null,
        "observation_ids_sha256": sha256_bytes(
            (
                "\n".join(
                    observation["observation_id"] for observation in observations
                )
                + "\n"
            ).encode()
        ),
        "observations_in_relationship_suggestions": len(members_in_suggestions),
        "planning_authority_counts_exact": _source_value_counts(
            observations, "PlanningAuthority"
        ),
        "potential_relationship_group_count": len(suggestions),
        "received_before_2012_count": sum(
            count
            for year, count in _received_year_counts(observations).items()
            if year != "<null>" and int(year) < 2012
        ),
        "received_year_counts": _received_year_counts(observations),
        "relationship_suggestion_counts_by_basis": dict(
            sorted(suggestion_counts.items())
        ),
        "release_id": RELEASE_ID,
        "source_date_non_null_counts": date_non_null,
        "unique_site_count": None,
    }


def _csv_bytes(observations: list[dict[str, Any]]) -> bytes:
    normalized_fields = [
        "observation_id",
        "observation_type",
        "retrieved_at",
        "matched_terms",
        "longitude",
        "latitude",
        "geometry_crs",
        "facility_lifecycle_status",
        "construction_evidence",
        "operation_evidence",
    ] + [f"date_{field}_utc" for field in DATE_FIELDS]
    source_fields = [f"source_{field}" for field in SOURCE_FIELDS]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(normalized_fields + source_fields)
    for observation in observations:
        coordinates = observation["coordinates"]
        normalized = [
            observation["observation_id"],
            observation["observation_type"],
            observation["retrieved_at"],
            "|".join(observation["matched_terms"]),
            "" if coordinates is None else coordinates["longitude"],
            "" if coordinates is None else coordinates["latitude"],
            "" if coordinates is None else coordinates["crs"],
            "",
            "false",
            "false",
        ] + [
            ""
            if observation["dates"][field] is None
            else observation["dates"][field]["utc"]
            for field in DATE_FIELDS
        ]
        attributes = observation["source_attributes"]
        source_values = [
            "" if attributes.get(field) is None else attributes.get(field)
            for field in SOURCE_FIELDS
        ]
        writer.writerow(normalized + source_values)
    return output.getvalue().encode("utf-8")


def _attribution_text(retrieved_at: str) -> bytes:
    return (
        "IrishPlanningApplications\n"
        "Source creator: Department of Housing, Local Government and Heritage, Ireland\n"
        f"Source: {DATASET_PAGE_URL}\n"
        f"Retrieved: {retrieved_at}\n"
        f"License: Creative Commons Attribution 4.0 International ({CC_BY_4_URL})\n"
        "\n"
        "Changes made by Data Center Atlas: filtered Planning Application Points using the "
        "documented data-centre phrase vocabulary; requested source geometry in EPSG:4326; "
        "created deterministic JSONL and CSV planning-application observations; represented "
        "ArcGIS date values as both source epoch milliseconds and UTC timestamps; and created "
        "review-only relationship suggestions. Source attributes remain available unchanged "
        "in the raw response and normalized observations. No endorsement is implied.\n"
    ).encode("utf-8")


def _readme_text(summary: Mapping[str, Any], retrieved_at: str) -> bytes:
    return (
        "# Ireland planning-application data-centre observations\n\n"
        "This CC BY 4.0 source release contains planning-application observations, not a "
        "facility inventory. It preserves 102 exact four-phrase matches and adds 12 audited "
        "high-precision `data hall` / `data processing centre` matches, for "
        f"{summary['matched_observation_count']} observations at {retrieved_at}.\n\n"
        "Buildings, campuses, amendments, retention cases, further-information records, and "
        "appeals may produce multiple applications. Application status, decision, grant, "
        "withdrawal, appeal, and expiry fields are exact process evidence only. They do not "
        "prove construction or operation. Relationship suggestions are review-only, and the "
        "unique-site count is deliberately null.\n\n"
        "`observations.jsonl` and `observations.csv` are deterministic normalized views. The "
        "`raw/` directory preserves all 15 open-source retrieval inputs byte-for-byte; the "
        "dataset and service artifacts are CC BY 4.0, while the dataset-page and license-text "
        "copies are retained only as rights evidence. The restricted calibration PDF is not "
        "retained. See "
        "`ATTRIBUTION.txt` for required credit and `assessment.json` for query, rights, and "
        "inference boundaries.\n"
    ).encode("utf-8")


def derive_release_files(
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
    calibration: Mapping[str, Any],
    retrieved_at: str,
) -> dict[str, bytes]:
    """Derive every normalized release file from pinned raw official inputs."""

    retrieved_at = _timestamp(retrieved_at, "retrieved_at")
    official_artifacts = _validate_retrievals(retrievals, raw_bodies)
    calibration_record = _validate_calibration(calibration)
    package = _raw_json(raw_bodies, "ckan_package")
    service = _raw_json(raw_bodies, "feature_service")
    layer = _raw_json(raw_bodies, "layer_definition")
    feature_page = _raw_json(raw_bodies, "matched_features_page_00000")

    package_result = _object(package.get("result"), "CKAN package result")
    resource_urls = {
        resource.get("url")
        for resource in package_result.get("resources", [])
        if isinstance(resource, Mapping)
    }
    if (
        package.get("success") is not True
        or package_result.get("id") != "8ca4be85-d587-4bdb-8ef9-66e6734df69f"
        or package_result.get("title") != "IrishPlanningApplications"
        or package_result.get("license_id") != "CC-BY-4.0"
        or package_result.get("license_url") != CC_BY_4_URL
        or package_result.get("updated") != "2026-02-24"
        or SERVICE_URL not in resource_urls
        or "participating Irish Local Authorities"
        not in str(package_result.get("notes"))
        or "since 2012" not in str(package_result.get("notes"))
    ):
        raise IrelandPlanningError("official CKAN dataset contract changed")
    dataset_page = raw_bodies["dataset_page"]
    if (
        b"Creative Commons Attribution 4.0" not in dataset_page
        or b"2026-02-24" not in dataset_page
    ):
        raise IrelandPlanningError("dataset page license or update date changed")
    legalcode = raw_bodies["cc_by_4_legalcode"]
    if b"Attribution 4.0 International" not in legalcode:
        raise IrelandPlanningError("CC BY 4.0 legalcode marker missing")

    if (
        service.get("currentVersion") != 12
        or service.get("serviceItemId") != "8f69dffe26324ba3acc653cf6cb5cf8b"
        or service.get("maxRecordCount") != 2000
        or service.get("capabilities") != "Query,Extract"
    ):
        raise IrelandPlanningError("FeatureServer contract changed")
    fields = layer.get("fields")
    if (
        layer.get("id") != 0
        or layer.get("name") != "Planning Application Points"
        or layer.get("geometryType") != "esriGeometryPoint"
        or layer.get("objectIdField") != "OBJECTID"
        or layer.get("maxRecordCount") != 2000
        or not isinstance(fields, list)
        or tuple(field.get("name") for field in fields) != SOURCE_FIELDS
        or layer.get("relationships") != []
        or layer.get("advancedQueryCapabilities", {}).get("supportsPagination")
        is not True
        or layer.get("advancedQueryCapabilities", {}).get("supportsOrderBy")
        is not True
    ):
        raise IrelandPlanningError("layer 0 schema changed")

    expected_counts = {
        "baseline_count": _EXPECTED_BASELINE_COUNT,
        "colocation_incremental_count": _EXPECTED_COLOCATION_INCREMENTAL_COUNT,
        "data_hall_incremental_count": _EXPECTED_DATA_HALL_INCREMENTAL_COUNT,
        "data_processing_incremental_count": _EXPECTED_DATA_PROCESSING_INCREMENTAL_COUNT,
        "extension_count": _EXPECTED_EXTENSION_COUNT,
        "final_count": _EXPECTED_FINAL_COUNT,
        "server_room_incremental_count": _EXPECTED_SERVER_ROOM_INCREMENTAL_COUNT,
        "total_count": _EXPECTED_TOTAL_COUNT,
    }
    for artifact_id, expected in expected_counts.items():
        if _count(_raw_json(raw_bodies, artifact_id), artifact_id) != expected:
            raise IrelandPlanningError(f"{artifact_id} changed; bump release ID")

    colocation_page = _raw_json(raw_bodies, "colocation_review_page_00000")
    colocation_features = colocation_page.get("features")
    if (
        not isinstance(colocation_features, list)
        or len(colocation_features) != _EXPECTED_COLOCATION_INCREMENTAL_COUNT
        or colocation_page.get("geometryType") != "esriGeometryPoint"
        or colocation_page.get("exceededTransferLimit") is True
    ):
        raise IrelandPlanningError("co-location precision-review page is incomplete")
    colocation_object_ids = [
        feature.get("attributes", {}).get("OBJECTID")
        for feature in colocation_features
    ]
    if colocation_object_ids != [355889, 387473]:
        raise IrelandPlanningError("co-location precision-review rows changed")
    for feature in colocation_features:
        description = str(
            feature.get("attributes", {}).get("DevelopmentDescription") or ""
        ).casefold()
        if "co-location facility" not in description or not any(
            term in description
            for term in ("antenna", "broadband", "telecommunications", "tower")
        ):
            raise IrelandPlanningError(
                "co-location exclusion no longer has telecommunications evidence"
            )

    features = feature_page.get("features")
    if (
        not isinstance(features, list)
        or len(features) != _EXPECTED_FINAL_COUNT
        or feature_page.get("geometryType") != "esriGeometryPoint"
        or feature_page.get("spatialReference")
        != {"wkid": 4326, "latestWkid": 4326}
        or feature_page.get("exceededTransferLimit") is True
    ):
        raise IrelandPlanningError("matched feature page is incomplete")
    object_ids = [feature.get("attributes", {}).get("OBJECTID") for feature in features]
    if (
        object_ids != sorted(object_ids)
        or len(set(object_ids)) != len(object_ids)
        or any(isinstance(value, bool) or not isinstance(value, int) for value in object_ids)
    ):
        raise IrelandPlanningError("matched features are not uniquely OBJECTID ordered")

    observations = [
        _normalize_feature(_object(feature, "feature"), retrieved_at)
        for feature in features
    ]
    suggestions = _relationship_suggestions(observations)
    summary = _build_summary(observations, suggestions, retrieved_at)
    if summary["matched_observation_count"] != _EXPECTED_FINAL_COUNT:
        raise IrelandPlanningError("normalized observation count changed")

    schema = {
        "assessment_id": RELEASE_ID,
        "date_fields": {
            field: {
                "csv_normalized_utc_field": f"date_{field}_utc",
                "normalized_utc_field": f"dates.{field}.utc",
                "source_encoding": "ArcGIS epoch milliseconds",
                "source_value_preserved": True,
            }
            for field in DATE_FIELDS
        },
        "field_count": len(fields),
        "format": SCHEMA_FORMAT,
        "generated_at": retrieved_at,
        "geometry": {
            "output_crs": "EPSG:4326",
            "source_geometry_type": "esriGeometryPoint",
            "source_geometry_preserved": True,
        },
        "numeric_field_units": deepcopy(NUMERIC_FIELD_UNITS),
        "schema_version": SCHEMA_VERSION,
        "source_fields": deepcopy(fields),
        "source_layer_id": 0,
        "source_layer_name": "Planning Application Points",
        "unknown_units_are_not_inferred": True,
    }
    vocabulary = {
        "baseline_count": _EXPECTED_BASELINE_COUNT,
        "baseline_terms": list(BASELINE_TERMS),
        "baseline_where": BASELINE_WHERE,
        "extension_count": _EXPECTED_EXTENSION_COUNT,
        "extension_terms": list(EXTENSION_TERMS),
        "final_count": _EXPECTED_FINAL_COUNT,
        "final_where": FINAL_WHERE,
        "manual_precision_review": {
            "co-location facility": {
                "decision": "excluded",
                "incremental_count": _EXPECTED_COLOCATION_INCREMENTAL_COUNT,
                "review_candidate_objectids": colocation_object_ids,
                "reason": "both reviewed rows described telecommunications co-location",
            },
            "data hall": {
                "decision": "included",
                "incremental_count": _EXPECTED_DATA_HALL_INCREMENTAL_COUNT,
                "reviewed_as_data_centre_related": _EXPECTED_DATA_HALL_INCREMENTAL_COUNT,
            },
            "data processing centre": {
                "decision": "included",
                "incremental_count": _EXPECTED_DATA_PROCESSING_INCREMENTAL_COUNT,
                "reviewed_as_data_centre_related": _EXPECTED_DATA_PROCESSING_INCREMENTAL_COUNT,
            },
            "server room": {
                "decision": "excluded",
                "incremental_count": _EXPECTED_SERVER_ROOM_INCREMENTAL_COUNT,
                "reason": "phrase is not specific enough for automatic inclusion",
            },
        },
    }
    assessment = {
        "assessed_at": retrieved_at,
        "atlas_decision": deepcopy(_EXPECTED_DECISION),
        "coverage_assessment": {
            "advertised_coverage": (
                "merged participating Irish local-authority planning registers; "
                "advertised as all applications received since 2012"
            ),
            "global_completeness_claimed": False,
            "matched_planning_application_observations": _EXPECTED_FINAL_COUNT,
            "matched_rows_received_before_2012": summary[
                "received_before_2012_count"
            ],
            "participating_authority_scope_is_all_ireland_completeness": False,
            "source_total_rows": _EXPECTED_TOTAL_COUNT,
            "unique_site_count": None,
        },
        "format": RELEASE_FORMAT,
        "granularity_assessment": deepcopy(_EXPECTED_GRANULARITY),
        "inference_bans": sorted(_EXPECTED_INFERENCE_BANS),
        "official_open_artifacts": official_artifacts,
        "query_assessment": {
            "baseline_count_query_url": RAW_ARTIFACTS["baseline_count"]["url"],
            "count_only_query_count": 8,
            "feature_page_count": 2,
            "feature_query_url": MATCHED_PAGE_URL,
            "final_count_query_url": RAW_ARTIFACTS["final_count"]["url"],
            "matched_feature_page_count": 1,
            "order_by_fields": "OBJECTID ASC",
            "out_fields": "*",
            "out_sr": 4326,
            "pagination_required": False,
            "precision_review_feature_page_count": 1,
            "precision_review_query_url": COLOCATION_REVIEW_PAGE_URL,
            "return_geometry": True,
        },
        "release_id": RELEASE_ID,
        "restricted_operational_calibration": calibration_record,
        "retrieval_batch": {
            "matched_feature_rows_retrieved": _EXPECTED_FINAL_COUNT,
            "network_retrievals": len(RAW_ARTIFACTS) + 1,
            "open_raw_artifacts_retained": len(RAW_ARTIFACTS),
            "precision_review_rows_retrieved": (
                _EXPECTED_COLOCATION_INCREMENTAL_COUNT
            ),
            "restricted_calibration_raw_retained": False,
            "retrieved_at": retrieved_at,
        },
        "rights_assessment": deepcopy(_EXPECTED_RIGHTS),
        "schema_version": SCHEMA_VERSION,
        "source": {
            "creator": "Department of Housing, Local Government and Heritage",
            "dataset_page_url": DATASET_PAGE_URL,
            "dataset_title": "IrishPlanningApplications",
            "dataset_updated": "2026-02-24",
            "layer_id": 0,
            "layer_name": "Planning Application Points",
            "service_url": SERVICE_URL,
        },
        "status_semantics": deepcopy(_EXPECTED_STATUS_SEMANTICS),
        "vocabulary_assessment": vocabulary,
    }

    result = {
        "ATTRIBUTION.txt": _attribution_text(retrieved_at),
        "README.md": _readme_text(summary, retrieved_at),
        "assessment.json": canonical_json(assessment),
        "observations.csv": _csv_bytes(observations),
        "observations.jsonl": _jsonl(observations),
        "relationship-suggestions.jsonl": _jsonl(suggestions),
        "schema.json": canonical_json(schema),
        "summary.json": canonical_json(summary),
    }
    return result


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise IrelandPlanningError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IrelandPlanningError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise IrelandPlanningError(f"{label} is not canonical object JSON")
    return value


def _validate_assessment(document: Mapping[str, Any]) -> None:
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != RELEASE_FORMAT
        or document.get("release_id") != RELEASE_ID
    ):
        raise IrelandPlanningError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    if document.get("rights_assessment") != _EXPECTED_RIGHTS:
        raise IrelandPlanningError("CC BY 4.0 rights or attribution changed")
    if document.get("status_semantics") != _EXPECTED_STATUS_SEMANTICS:
        raise IrelandPlanningError("planning status semantics changed")
    if document.get("granularity_assessment") != _EXPECTED_GRANULARITY:
        raise IrelandPlanningError("planning observation granularity changed")
    if document.get("inference_bans") != sorted(_EXPECTED_INFERENCE_BANS):
        raise IrelandPlanningError("inference boundary changed")
    if document.get("atlas_decision") != _EXPECTED_DECISION:
        raise IrelandPlanningError("Atlas publication decision changed")
    batch = _object(document.get("retrieval_batch"), "retrieval_batch")
    if batch != {
        "matched_feature_rows_retrieved": _EXPECTED_FINAL_COUNT,
        "network_retrievals": len(RAW_ARTIFACTS) + 1,
        "open_raw_artifacts_retained": len(RAW_ARTIFACTS),
        "precision_review_rows_retrieved": (
            _EXPECTED_COLOCATION_INCREMENTAL_COUNT
        ),
        "restricted_calibration_raw_retained": False,
        "retrieved_at": assessed_at,
    }:
        raise IrelandPlanningError("retrieval boundary changed")
    _validate_calibration(
        _object(
            document.get("restricted_operational_calibration"),
            "restricted_operational_calibration",
        )
    )
    artifacts = _object(document.get("official_open_artifacts"), "artifacts")
    if set(artifacts) != set(RAW_ARTIFACTS):
        raise IrelandPlanningError("open artifact set differs")
    for artifact_id, specification in RAW_ARTIFACTS.items():
        record = _object(artifacts[artifact_id], f"artifacts.{artifact_id}")
        is_rights_evidence = artifact_id in _RIGHTS_EVIDENCE_ARTIFACT_IDS
        if (
            record.get("url") != specification["url"]
            or record.get("filename") != specification["filename"]
            or record.get("http_status") != 200
            or record.get("license_id")
            != (None if is_rights_evidence else "CC-BY-4.0")
            or record.get("rights_scope")
            != (
                "license_evidence_reference_copy"
                if is_rights_evidence
                else "licensed_dataset_or_service_artifact"
            )
            or not isinstance(record.get("bytes"), int)
            or record.get("bytes") <= 0
            or not isinstance(record.get("sha256"), str)
            or not _SHA256_RE.fullmatch(record["sha256"])
        ):
            raise IrelandPlanningError("open artifact metadata is invalid")


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the frozen release and reproduce every derived byte offline."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise IrelandPlanningError("release bundle must be a directory")
    actual_files: set[str] = set()
    for entry in directory.rglob("*"):
        if entry.is_symlink():
            raise IrelandPlanningError("release entries must not be symlinks")
        if entry.is_file():
            actual_files.add(entry.relative_to(directory).as_posix())
        elif not entry.is_dir():
            raise IrelandPlanningError("release entries must be files or directories")
    if actual_files != _EXPECTED_FILES:
        raise IrelandPlanningError(f"release file set differs: {sorted(actual_files)}")

    assessment = _load_canonical_json(directory / "assessment.json", "assessment")
    schema = _load_canonical_json(directory / "schema.json", "schema")
    summary = _load_canonical_json(directory / "summary.json", "summary")
    _validate_assessment(assessment)
    if (
        schema.get("schema_version") != SCHEMA_VERSION
        or schema.get("format") != SCHEMA_FORMAT
        or schema.get("assessment_id") != RELEASE_ID
        or schema.get("generated_at") != assessment.get("assessed_at")
        or schema.get("numeric_field_units") != NUMERIC_FIELD_UNITS
        or schema.get("unknown_units_are_not_inferred") is not True
        or schema.get("field_count") != len(SOURCE_FIELDS)
        or tuple(field.get("name") for field in schema.get("source_fields", []))
        != SOURCE_FIELDS
    ):
        raise IrelandPlanningError("release schema changed")
    if (
        summary.get("format") != SUMMARY_FORMAT
        or summary.get("release_id") != RELEASE_ID
        or summary.get("generated_at") != assessment.get("assessed_at")
        or summary.get("matched_observation_count") != _EXPECTED_FINAL_COUNT
        or summary.get("baseline_exact_phrase_count") != _EXPECTED_BASELINE_COUNT
        or summary.get("extension_count") != _EXPECTED_EXTENSION_COUNT
        or summary.get("unique_site_count") is not None
    ):
        raise IrelandPlanningError("release summary changed")

    manifest = _load_canonical_json(directory / MANIFEST_FILENAME, "manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
        or manifest.get("license_id") != "CC-BY-4.0"
        or manifest.get("license_scope") != _MANIFEST_LICENSE_SCOPE
    ):
        raise IrelandPlanningError("manifest identity is invalid")
    manifest_files = _object(manifest.get("files"), "manifest files")
    expected_manifest_files = _EXPECTED_FILES - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    if set(manifest_files) != expected_manifest_files:
        raise IrelandPlanningError("manifest file set differs")
    for filename in sorted(expected_manifest_files):
        record = _object(manifest_files[filename], f"manifest.{filename}")
        artifact = directory / filename
        if filename in _RIGHTS_EVIDENCE_FILENAMES:
            expected_role = "raw_rights_evidence"
        elif filename.startswith("raw/"):
            expected_role = "raw_official"
        else:
            expected_role = "derived"
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
            or record.get("role") != expected_role
        ):
            raise IrelandPlanningError(f"manifest mismatch for {filename}")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (
        directory.joinpath(MANIFEST_HASH_FILENAME).read_text(encoding="utf-8")
        != expected_sidecar
    ):
        raise IrelandPlanningError("manifest sidecar mismatch")

    artifacts = assessment["official_open_artifacts"]
    raw_bodies = {
        artifact_id: directory.joinpath(specification["filename"]).read_bytes()
        for artifact_id, specification in RAW_ARTIFACTS.items()
    }
    retrievals = {
        artifact_id: {
            "content_type": artifacts[artifact_id]["content_type"],
            "effective_url": artifacts[artifact_id]["effective_url"],
            "http_status": artifacts[artifact_id]["http_status"],
            "url": artifacts[artifact_id]["url"],
        }
        for artifact_id in RAW_ARTIFACTS
    }
    reproduced = derive_release_files(
        retrievals,
        raw_bodies,
        assessment["restricted_operational_calibration"],
        assessment["assessed_at"],
    )
    for filename, expected in reproduced.items():
        if directory.joinpath(filename).read_bytes() != expected:
            raise IrelandPlanningError(f"offline reproduction mismatch for {filename}")
    return {"assessment": assessment, "schema": schema, "summary": summary}


def write_release_bundle(
    output: str | Path,
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
    calibration: Mapping[str, Any],
    retrieved_at: str,
    *,
    freeze: bool = False,
) -> Path:
    """Write a new release, validate it, and optionally freeze it read-only."""

    directory = Path(output)
    if directory.exists() or directory.is_symlink():
        raise IrelandPlanningError("output release already exists")
    derived = derive_release_files(
        retrievals, raw_bodies, calibration, retrieved_at
    )
    directory.mkdir(parents=True)
    for artifact_id, specification in RAW_ARTIFACTS.items():
        destination = directory / specification["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw_bodies[artifact_id])
    for filename, body in derived.items():
        (directory / filename).write_bytes(body)
    files: dict[str, Any] = {}
    for filename in sorted(
        _EXPECTED_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    ):
        artifact = directory / filename
        if filename in _RIGHTS_EVIDENCE_FILENAMES:
            role = "raw_rights_evidence"
        elif filename.startswith("raw/"):
            role = "raw_official"
        else:
            role = "derived"
        files[filename] = {
            "bytes": artifact.stat().st_size,
            "role": role,
            "sha256": _sha256(artifact),
        }
    manifest = {
        "files": files,
        "format": RELEASE_FORMAT,
        "generated_at": _timestamp(retrieved_at, "retrieved_at"),
        "license_id": "CC-BY-4.0",
        "license_scope": _MANIFEST_LICENSE_SCOPE,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }
    manifest_bytes = canonical_json(manifest)
    (directory / MANIFEST_FILENAME).write_bytes(manifest_bytes)
    (directory / MANIFEST_HASH_FILENAME).write_text(
        f"{sha256_bytes(manifest_bytes)}  manifest.json\n", encoding="utf-8"
    )
    validate_release_bundle(directory)
    if freeze:
        for entry in sorted(directory.rglob("*"), reverse=True):
            if entry.is_file():
                entry.chmod(0o444)
            elif entry.is_dir():
                entry.chmod(0o555)
        directory.chmod(0o555)
    return directory
