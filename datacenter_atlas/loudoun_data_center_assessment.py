"""Build and validate the fail-closed Loudoun County data-center assessment."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit


ASSESSMENT_FILENAME = "assessment.json"
SCHEMA_FILENAME = "schema.json"
CALIBRATION_FILENAME = "calibration.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-loudoun-data-center-assessment-v1"
SCHEMA_FORMAT = "datacenter-atlas-loudoun-data-center-schema-v1"
CALIBRATION_FORMAT = "datacenter-atlas-loudoun-data-center-calibration-v1"
ASSESSMENT_ID = "loudoun-data-center-2026-07-18-v1"
SCHEMA_ID = "loudoun-data-center-layers-2026-07-18-v1"
CALIBRATION_ID = "loudoun-data-center-aggregate-calibration-2026-07-18-v1"

EXISTING_ITEM_ID = "ffa967f21077455eaade4f258e3f5326"
PIPELINE_ITEM_ID = "2a084dcc039249f286685205f1f4b33b"
ITEM_OWNER = "Doug.Gibson@loudoun.gov_LoudounGIS"
EXISTING_SERVICE_URL = (
    "https://services1.arcgis.com/MxjRokvPm7bjslyR/arcgis/rest/services/"
    "Existing_Data_Center_Parcel/FeatureServer"
)
PIPELINE_SERVICE_URL = (
    "https://services1.arcgis.com/MxjRokvPm7bjslyR/arcgis/rest/services/"
    "Pipeline_Data_Center_Areas/FeatureServer"
)
ASSESSOR_GUIDELINES_URL = (
    "https://www.loudoun.gov/DocumentCenter/View/219238/"
    "462-Data-Center-2026-Guidelines-PDF"
)
ASSESSOR_GUIDELINES_SHA256 = (
    "dfed31cd8b7d2abf2db882595d5d5d6567a9327c2063ca1c75ec043073c75134"
)
ASSESSOR_GUIDELINES_BYTES = 112159

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    SCHEMA_FILENAME,
    CALIBRATION_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_OFFICIAL_HOSTS = {"services1.arcgis.com", "www.arcgis.com", "www.loudoun.gov"}


def _count_query(service_url: str) -> str:
    return f"{service_url}/1/query?{urlencode({'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'})}"


def _statistics_query(service_url: str, object_id: str, field: str) -> str:
    statistic = json.dumps(
        [
            {
                "statisticType": "count",
                "onStatisticField": object_id,
                "outStatisticFieldName": "record_count",
            }
        ],
        separators=(",", ":"),
    )
    return f"{service_url}/1/query?{urlencode({'where': '1=1', 'outStatistics': statistic, 'groupByFieldsForStatistics': field, 'orderByFields': field, 'returnGeometry': 'false', 'f': 'json'})}"


ARTIFACT_URLS = {
    "geohub_page": "https://www.loudoun.gov/1776/GeoHub-and-Other-Online-Resources",
    "mapping_products_page": "https://www.loudoun.gov/1774/Mapping-Products-for-Purchase",
    "assessor_guidelines_pdf": ASSESSOR_GUIDELINES_URL,
    "existing_item": (
        f"https://www.arcgis.com/sharing/rest/content/items/{EXISTING_ITEM_ID}?f=pjson"
    ),
    "existing_service": f"{EXISTING_SERVICE_URL}?f=pjson",
    "existing_layer": f"{EXISTING_SERVICE_URL}/1?f=pjson",
    "existing_count": _count_query(EXISTING_SERVICE_URL),
    "existing_data_center_status": _statistics_query(
        EXISTING_SERVICE_URL, "OBJECTID_1", "Data_Center_Status"
    ),
    "existing_built_status": _statistics_query(
        EXISTING_SERVICE_URL, "OBJECTID_1", "Built_Status"
    ),
    "pipeline_item": (
        f"https://www.arcgis.com/sharing/rest/content/items/{PIPELINE_ITEM_ID}?f=pjson"
    ),
    "pipeline_service": f"{PIPELINE_SERVICE_URL}?f=pjson",
    "pipeline_layer": f"{PIPELINE_SERVICE_URL}/1?f=pjson",
    "pipeline_count": _count_query(PIPELINE_SERVICE_URL),
    "pipeline_status": _statistics_query(
        PIPELINE_SERVICE_URL, "OBJECTID", "FIRST_Status"
    ),
}

_JSON_ARTIFACT_IDS = set(ARTIFACT_URLS) - {
    "assessor_guidelines_pdf",
    "geohub_page",
    "mapping_products_page",
}

_EXISTING_FIELD_NAMES = [
    "OBJECTID_1",
    "Data_Center_Status",
    "PA_GIS_ACRE",
    "PA_LEGAL_ACRE",
    "Existing_Acres",
    "PA_MCPI",
    "CONCATENATE_Permit_Number",
    "Overall_SQ_FT",
    "LU_DISPLAY",
    "LU_MULTI_USE_SUBCD2",
    "LU_MULTI_USE_SUBCD1",
    "Project",
    "Owner",
    "Ownership_Category",
    "CONCATENATE_Permit_Square_Feet",
    "ZONING_ACRES",
    "Proposed_SQ_FT",
    "Built_Status",
    "PLACE_TYPE",
    "PLACE_TYPE_ACRES",
    "POLICY_AREA",
    "POLIICY_SUB_AREA",
    "POLICY_ACRES",
    "ZONING",
    "ORDINANCE",
    "Zoning_Case_Number",
    "ELECTION_DISTRICT",
    "ELEC_ACRES",
    "PLANNING_SUBAREA",
    "PLANN_ACRES",
    "Source",
    "Shape__Area",
    "Shape__Length",
]

_PIPELINE_FIELD_NAMES = [
    "OBJECTID",
    "Application",
    "FIRST_Status",
    "FIRST_Subdivision",
    "FIRST_Zoning_Case_Num",
    "FIRST_Overall_SQ_FT",
    "SUM_Pipeline_Acres",
    "Shape__Area",
    "Shape__Length",
]

_EXPECTED_DISTRIBUTIONS = {
    "existing_built_status": [
        {"count": 103, "value": "BUILT"},
        {"count": 6, "value": "BUILT/UNDER CONSTRUCTION"},
        {"count": 1, "value": "BULT/UNDER CONSTRUCTION"},
        {"count": 29, "value": "UNDER CONSTRUCTION"},
    ],
    "existing_data_center_status": [{"count": 139, "value": "Existing"}],
    "pipeline_status": [
        {"count": 51, "value": "Active"},
        {"count": 16, "value": "Approved"},
        {"count": 18, "value": "Approved: Conditionally"},
    ],
}

_EXPECTED_RIGHTS = {
    "access_or_download_availability_is_a_redistribution_license": False,
    "affirmative_commercial_use_permission_found": False,
    "affirmative_public_database_redistribution_permission_found": False,
    "aggregate_count_schema_and_report_facts_publication_permitted": True,
    "arcgis_access_information_is_blank": True,
    "arcgis_items_are_public": True,
    "arcgis_terms_of_use_is_null": True,
    "available_to_public_item_statement_found": True,
    "county_acknowledgement_requested_for_derived_products": True,
    "county_geohub_described_as_open_data": True,
    "countywide_or_selected_area_download_at_no_cost_documented": True,
    "derivative_database_publication_permitted": False,
    "explicit_standard_license_identifier_found": False,
    "feature_attribute_redistribution_permitted": False,
    "feature_geometry_redistribution_permitted": False,
    "legal_conclusion_claimed": False,
    "raw_feature_cache_for_atlas_release_permitted": False,
}

_EXPECTED_ACCESS = {
    "anonymous_count_queries_succeeded": True,
    "anonymous_grouped_statistics_queries_succeeded": True,
    "count_only_query_requests": 2,
    "feature_query_capability_advertised": True,
    "full_feature_query_requests": 0,
    "geometry_out_sr_4326_query_performed": False,
    "grouped_statistics_query_requests": 3,
    "max_record_count": 2000,
    "supported_layer_query_formats": "JSON, geoJSON, PBF",
}

_EXPECTED_COUNTS = {
    "building_count": None,
    "counts_are_county_classified_parcel_records": True,
    "counts_are_unique_sites": False,
    "counts_may_overlap_conceptually": True,
    "existing_parcel_records": 139,
    "pipeline_parcel_records": 85,
    "record_counts_summed": False,
    "unique_site_count": None,
}

_EXPECTED_GRANULARITY = {
    "automatic_cross_layer_merge_permitted": False,
    "existing_records_are_buildings": False,
    "existing_records_are_parcel_records": True,
    "parcel_count_is_facility_count": False,
    "pipeline_records_are_parcel_records": True,
    "pipeline_records_are_physical_sites": False,
    "record_count_is_unique_site_count": False,
}

_EXPECTED_FRESHNESS = {
    "aggregate_queries_are_snapshot_scoped": True,
    "arcgis_item_modified_dates_are_row_freshness": False,
    "per_record_freshness_retrieved": False,
    "service_snapshot_version_field_found": False,
}

_EXPECTED_DECISION = {
    "aggregate_calibration_created": True,
    "automatic_merge_permitted": False,
    "construction_status_promotion_permitted": False,
    "feature_release_created": False,
    "publication_eligible_metadata_assessment_created": True,
    "review_leads_emitted": 0,
    "source_feature_content_publication_eligible": False,
    "status": "rights_blocked_metadata_and_aggregates_only",
    "typed_power_or_energy_promotion_permitted": False,
    "unique_site_count_published": False,
}

_EXPECTED_PERMISSION_REQUIREMENTS = {
    "attribution_and_notice_requirements",
    "commercial_use_in_a_compiled_data_product",
    "local_storage_and_raw_feature_response_cache",
    "modification_and_derivative_database_creation",
    "public_display_and_redistribution_of_attributes_and_geometries",
    "refresh_retention_termination_and_deletion_terms",
    "sublicensing_or_downstream_end_user_access",
}

_PUBLIC_AVAILABILITY_STATEMENT = (
    "These data were generated for use by Loudoun County and are available to "
    "the public. These data are intended for use at 1:2400 scale or smaller. "
    "Acknowledgement of Loudoun County would be appreciated in products derived "
    "from this data."
)
_PIPELINE_DISCLAIMER_STATEMENT = (
    "Loudoun County is not liable for any use of or reliance upon this map or "
    "data, or any information contained herein. While reasonable efforts have "
    "been made to obtain accurate data, the County makes no warranty, expressed "
    "or implied, as to its accuracy, completeness, or fitness for use of any "
    "purpose."
)

_EXPECTED_STATUS_SEMANTICS = {
    "county_classifications_are_evergreen_atlas_lifecycle": False,
    "existing_built_status": {
        "atlas_auto_promotion": False,
        "exact_data_dictionary_found": False,
        "source_field": "Built_Status",
        "source_values_preserved_verbatim": True,
    },
    "existing_data_center_status": {
        "atlas_auto_promotion": False,
        "exact_data_dictionary_found": False,
        "source_field": "Data_Center_Status",
        "source_values_preserved_verbatim": True,
    },
    "pipeline_status": {
        "atlas_auto_promotion": False,
        "exact_data_dictionary_found": False,
        "physical_construction_evidence": False,
        "source_field": "FIRST_Status",
        "source_values_preserved_verbatim": True,
    },
    "snapshot_scope_only": True,
}

_EXPECTED_POWER_ENERGY = {
    "annual_energy_inference_permitted": False,
    "documented_energy_fields": [],
    "documented_mw_or_mva_fields": [],
    "floor_area_to_power_conversion_permitted": False,
    "operational_workload_fields": [],
    "power_capacity_inference_permitted": False,
    "pue_fields": [],
    "source_values_retrieved": False,
}

_EXPECTED_UNIT_SEMANTICS = {
    "acreage_fields": [
        "existing.Existing_Acres",
        "existing.PA_GIS_ACRE",
        "existing.PA_LEGAL_ACRE",
        "existing.PLACE_TYPE_ACRES",
        "existing.POLICY_ACRES",
        "existing.ZONING_ACRES",
        "existing.ELEC_ACRES",
        "existing.PLANN_ACRES",
        "pipeline.SUM_Pipeline_Acres",
    ],
    "feature_record_unit": "parcel_record",
    "no_unit_conversion_performed": True,
    "square_foot_fields": [
        "existing.CONCATENATE_Permit_Square_Feet",
        "existing.Overall_SQ_FT",
        "existing.Proposed_SQ_FT",
        "pipeline.FIRST_Overall_SQ_FT",
    ],
}

_EXPECTED_INFERENCE_BANS = {
    "do_not_assign_assessor_aggregate_types_or_counts_to_gis_parcels",
    "do_not_call_parcels_buildings_campuses_facilities_or_unique_sites",
    "do_not_convert_acres_or_square_feet_to_power_or_energy",
    "do_not_merge_existing_and_pipeline_parcel_counts",
    "do_not_normalize_the_bult_status_typo_silently",
    "do_not_promote_county_status_labels_without_exact_semantics",
    "do_not_publish_feature_attributes_or_geometries_without_explicit_rights",
    "do_not_repair_nonreconciling_assessor_totals",
}

_EXPECTED_ASSESSOR_ROWS = [
    {
        "built_square_feet": 6693767,
        "complete_data_centers": 40,
        "improved_parcels": 15,
        "normalized_type": "Enterprise/Hyperscale",
        "parcels": 32,
        "source_label": "Enter./Hyper.",
        "under_construction_data_centers": 9,
        "under_construction_square_feet": 1460840,
        "vacant_land_parcels": 17,
    },
    {
        "built_square_feet": 11584508,
        "complete_data_centers": 74,
        "improved_parcels": 58,
        "normalized_type": "Net Lease",
        "parcels": 94,
        "source_label": "Net Lease",
        "under_construction_data_centers": 15,
        "under_construction_square_feet": 3978866,
        "vacant_land_parcels": 36,
    },
    {
        "built_square_feet": 26032761,
        "complete_data_centers": 101,
        "improved_parcels": 78,
        "normalized_type": "Retail/Colo",
        "parcels": 125,
        "source_label": "Retail/Colo",
        "under_construction_data_centers": 13,
        "under_construction_square_feet": 3774197,
        "vacant_land_parcels": 45,
    },
]

_EXPECTED_ASSESSOR_TOTAL = {
    "built_square_feet": 44311036,
    "complete_data_centers": 209,
    "improved_parcels": 153,
    "parcels": 251,
    "under_construction_data_centers": 43,
    "under_construction_square_feet": 9213903,
    "vacant_land_parcels": 98,
}


def _reconciliation() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for field in _EXPECTED_ASSESSOR_TOTAL:
        row_sum = sum(row[field] for row in _EXPECTED_ASSESSOR_ROWS)
        official_total = _EXPECTED_ASSESSOR_TOTAL[field]
        result[field] = {
            "category_row_sum": row_sum,
            "delta_row_sum_minus_official_total": row_sum - official_total,
            "official_total": official_total,
            "reconciles": row_sum == official_total,
        }
    return result


_EXPECTED_RECONCILIATION = _reconciliation()


def _parcel_composition_reconciliation() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _EXPECTED_ASSESSOR_ROWS:
        classified = row["improved_parcels"] + row["vacant_land_parcels"]
        records.append(
            {
                "classified_parcel_sum": classified,
                "delta_classified_sum_minus_parcels": classified - row["parcels"],
                "normalized_type": row["normalized_type"],
                "parcels": row["parcels"],
                "reconciles": classified == row["parcels"],
            }
        )
    total_classified = (
        _EXPECTED_ASSESSOR_TOTAL["improved_parcels"]
        + _EXPECTED_ASSESSOR_TOTAL["vacant_land_parcels"]
    )
    records.append(
        {
            "classified_parcel_sum": total_classified,
            "delta_classified_sum_minus_parcels": (
                total_classified - _EXPECTED_ASSESSOR_TOTAL["parcels"]
            ),
            "normalized_type": "Official total",
            "parcels": _EXPECTED_ASSESSOR_TOTAL["parcels"],
            "reconciles": total_classified
            == _EXPECTED_ASSESSOR_TOTAL["parcels"],
        }
    )
    return records


_EXPECTED_PARCEL_COMPOSITION_RECONCILIATION = (
    _parcel_composition_reconciliation()
)


class LoudounDataCenterAssessmentError(ValueError):
    """Raised when the Loudoun assessment crosses its governance boundary."""


def canonical_json(value: Any) -> bytes:
    """Return the canonical JSON encoding used by immutable bundles."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest for in-memory source material."""

    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LoudounDataCenterAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LoudounDataCenterAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LoudounDataCenterAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LoudounDataCenterAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LoudounDataCenterAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LoudounDataCenterAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise LoudounDataCenterAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != canonical_json(value):
        raise LoudounDataCenterAssessmentError(f"{label} is not canonical JSON")
    return value


def _json_body(bodies: Mapping[str, bytes], artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(bodies[artifact_id].decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise LoudounDataCenterAssessmentError(
            f"{artifact_id} did not contain valid JSON"
        ) from error
    if not isinstance(value, dict) or "error" in value:
        raise LoudounDataCenterAssessmentError(
            f"{artifact_id} did not contain a successful JSON object"
        )
    return value


def _html_text(value: bytes, label: str) -> str:
    try:
        decoded = value.decode("utf-8")
    except UnicodeError as error:
        raise LoudounDataCenterAssessmentError(f"invalid {label} HTML") from error
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", decoded)).split())


def _field_contract(raw: Any) -> dict[str, Any]:
    field = _object(raw, "layer field")
    return {
        "alias": field.get("alias"),
        "domain": deepcopy(field.get("domain")),
        "editable": field.get("editable"),
        "length": field.get("length"),
        "name": field.get("name"),
        "nullable": field.get("nullable"),
        "type": field.get("type"),
    }


def _portal_time(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoudounDataCenterAssessmentError(f"{field} must be epoch milliseconds")
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _validate_retrieval_inputs(
    retrievals: Mapping[str, Mapping[str, Any]], bodies: Mapping[str, bytes]
) -> dict[str, dict[str, Any]]:
    if set(retrievals) != set(ARTIFACT_URLS) or set(bodies) != set(ARTIFACT_URLS):
        raise LoudounDataCenterAssessmentError("official artifact set differs")
    result: dict[str, dict[str, Any]] = {}
    for artifact_id, expected_url in ARTIFACT_URLS.items():
        record = _object(retrievals[artifact_id], f"retrievals.{artifact_id}")
        body = bodies[artifact_id]
        effective_url = record.get("effective_url")
        content_type = record.get("content_type")
        if (
            not isinstance(body, bytes)
            or not body
            or record.get("url") != expected_url
            or record.get("http_status") != 200
            or not isinstance(effective_url, str)
            or urlsplit(effective_url).scheme != "https"
            or urlsplit(effective_url).hostname not in _OFFICIAL_HOSTS
            or not isinstance(content_type, str)
            or not content_type
        ):
            raise LoudounDataCenterAssessmentError(
                "artifact retrieval metadata is invalid"
            )
        result[artifact_id] = {
            "bytes": len(body),
            "content_type": content_type,
            "effective_url": effective_url,
            "http_status": 200,
            "sha256": sha256_bytes(body),
            "url": expected_url,
        }
    pdf = result["assessor_guidelines_pdf"]
    if (
        pdf["bytes"] != ASSESSOR_GUIDELINES_BYTES
        or pdf["sha256"] != ASSESSOR_GUIDELINES_SHA256
        or not bodies["assessor_guidelines_pdf"].startswith(b"%PDF-")
    ):
        raise LoudounDataCenterAssessmentError(
            "assessor PDF changed; inspect and bump the calibration"
        )
    return result


def _validate_item(
    item: Mapping[str, Any], *, item_id: str, title: str, service_url: str
) -> dict[str, Any]:
    if (
        item.get("id") != item_id
        or item.get("title") != title
        or item.get("owner") != ITEM_OWNER
        or item.get("access") != "public"
        or item.get("type") != "Feature Service"
        or item.get("url") != service_url
        or item.get("termsOfUse") is not None
        or item.get("accessInformation") != ""
    ):
        raise LoudounDataCenterAssessmentError(
            f"ArcGIS item {item_id} contract changed; bump assessment"
        )
    license_text = _html_text(
        str(item.get("licenseInfo", "")).encode("utf-8"), f"{title} license"
    )
    if _PUBLIC_AVAILABILITY_STATEMENT not in license_text:
        raise LoudounDataCenterAssessmentError("public availability statement changed")
    statements = [_PUBLIC_AVAILABILITY_STATEMENT]
    if item_id == PIPELINE_ITEM_ID:
        if _PIPELINE_DISCLAIMER_STATEMENT not in license_text:
            raise LoudounDataCenterAssessmentError("pipeline disclaimer changed")
        statements.append(_PIPELINE_DISCLAIMER_STATEMENT)
    return {
        "access_information": "",
        "created_at": _portal_time(item.get("created"), f"{title}.created"),
        "item_id": item_id,
        "license_statements": statements,
        "modified_at": _portal_time(item.get("modified"), f"{title}.modified"),
        "owner": ITEM_OWNER,
        "public_access": True,
        "terms_of_use": None,
        "title": title,
    }


def _validate_service(
    service: Mapping[str, Any], *, item_id: str, layer_name: str
) -> None:
    layers = service.get("layers")
    if (
        service.get("currentVersion") != 12
        or service.get("serviceItemId") != item_id
        or service.get("maxRecordCount") != 2000
        or service.get("supportedQueryFormats") != "JSON"
        or service.get("capabilities") != "Query"
        or service.get("tables") != []
        or not isinstance(layers, list)
        or len(layers) != 1
        or layers[0].get("id") != 1
        or layers[0].get("name") != layer_name
        or layers[0].get("geometryType") != "esriGeometryPolygon"
    ):
        raise LoudounDataCenterAssessmentError(
            f"service {item_id} contract changed; bump assessment"
        )


def _layer_schema(
    layer: Mapping[str, Any],
    *,
    item: Mapping[str, Any],
    item_id: str,
    name: str,
    object_id: str,
    expected_fields: list[str],
    feature_count: int,
    count_artifact_id: str,
) -> dict[str, Any]:
    fields = [_field_contract(raw) for raw in layer.get("fields", [])]
    description_text = _html_text(
        str(layer.get("description", "")).encode("utf-8"), f"{name} description"
    )
    if (
        layer.get("id") != 1
        or layer.get("name") != name
        or layer.get("type") != "Feature Layer"
        or layer.get("geometryType") != "esriGeometryPolygon"
        or layer.get("objectIdField") != object_id
        or layer.get("globalIdField") != ""
        or layer.get("maxRecordCount") != 2000
        or layer.get("supportedQueryFormats") != "JSON, geoJSON, PBF"
        or layer.get("capabilities") != "Query"
        or layer.get("relationships") != []
        or [field["name"] for field in fields] != expected_fields
        or "A parcel is a tract or plot of land surveyed and defined by legal ownership."
        not in description_text
        or layer.get("advancedQueryCapabilities", {}).get("supportsPagination")
        is not True
        or layer.get("advancedQueryCapabilities", {}).get("supportsStatistics")
        is not True
    ):
        raise LoudounDataCenterAssessmentError(
            f"layer {item_id}/1 contract changed; bump assessment"
        )
    spatial_reference = _object(
        _object(layer.get("extent"), f"{name}.extent").get("spatialReference"),
        f"{name}.spatial_reference",
    )
    if spatial_reference.get("wkid") != 2924:
        raise LoudounDataCenterAssessmentError("layer spatial reference changed")
    return {
        "count_query_artifact_id": count_artifact_id,
        "description_defines_parcel_by_legal_ownership": True,
        "display_field": layer.get("displayField"),
        "feature_count": feature_count,
        "field_count": len(fields),
        "fields": fields,
        "geometry_type": "esriGeometryPolygon",
        "item": deepcopy(item),
        "layer_id": 1,
        "max_record_count": 2000,
        "name": name,
        "object_id_field": object_id,
        "record_unit": "parcel_record",
        "relationships": [],
        "source_spatial_reference": {"latestWkid": 2924, "wkid": 2924},
        "supported_query_formats": "JSON, geoJSON, PBF",
        "supports_pagination": True,
        "supports_statistics": True,
    }


def _count(payload: Mapping[str, Any], expected: int, label: str) -> int:
    if set(payload) != {"count"} or payload.get("count") != expected:
        raise LoudounDataCenterAssessmentError(f"{label} count changed; bump assessment")
    return expected


def _distribution(
    payload: Mapping[str, Any], field: str, expected_total: int, label: str
) -> list[dict[str, Any]]:
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise LoudounDataCenterAssessmentError(f"{label} returned no groups")
    result: list[dict[str, Any]] = []
    for raw in features:
        feature = _object(raw, f"{label} group")
        if set(feature) != {"attributes"}:
            raise LoudounDataCenterAssessmentError(
                f"{label} aggregate unexpectedly contained feature geometry"
            )
        attributes = _object(feature.get("attributes"), f"{label} attributes")
        value = attributes.get(field)
        count = attributes.get("record_count")
        if (
            set(attributes) != {field, "record_count"}
            or not isinstance(value, str)
            or not value
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
        ):
            raise LoudounDataCenterAssessmentError(f"invalid {label} group")
        result.append({"count": count, "value": value})
    result.sort(key=lambda record: record["value"])
    if sum(record["count"] for record in result) != expected_total:
        raise LoudounDataCenterAssessmentError(f"{label} groups do not reconcile")
    return result


def build_assessment_documents(
    retrievals: Mapping[str, Mapping[str, Any]],
    bodies: Mapping[str, bytes],
    assessed_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Derive deterministic metadata-only documents from official responses."""

    assessed_at = _timestamp(assessed_at, "assessed_at")
    official_artifacts = _validate_retrieval_inputs(retrievals, bodies)
    payloads = {
        artifact_id: _json_body(bodies, artifact_id)
        for artifact_id in _JSON_ARTIFACT_IDS
    }

    geohub_text = _html_text(bodies["geohub_page"], "GeoHub page")
    mapping_text = _html_text(bodies["mapping_products_page"], "mapping page")
    if not all(
        marker in geohub_text
        for marker in (
            "As an open data platform",
            "share, view, download, or map spatial data on the fly",
        )
    ):
        raise LoudounDataCenterAssessmentError("GeoHub open-data text changed")
    if not all(
        marker in mapping_text
        for marker in (
            "available at no cost",
            "spreadsheet (CSV)",
            "KML",
            "shapefile (SHP)",
        )
    ):
        raise LoudounDataCenterAssessmentError("mapping download text changed")

    existing_item = _validate_item(
        payloads["existing_item"],
        item_id=EXISTING_ITEM_ID,
        title="Existing_Data_Center_Parcel",
        service_url=EXISTING_SERVICE_URL,
    )
    pipeline_item = _validate_item(
        payloads["pipeline_item"],
        item_id=PIPELINE_ITEM_ID,
        title="Pipeline_Data_Center_Areas",
        service_url=PIPELINE_SERVICE_URL,
    )
    _validate_service(
        payloads["existing_service"],
        item_id=EXISTING_ITEM_ID,
        layer_name="Existing_DC_Parcels_March1",
    )
    _validate_service(
        payloads["pipeline_service"],
        item_id=PIPELINE_ITEM_ID,
        layer_name="Proposed_DC_Parcels_March1_SINGLE",
    )
    existing_count = _count(payloads["existing_count"], 139, "existing")
    pipeline_count = _count(payloads["pipeline_count"], 85, "pipeline")
    distributions = {
        "existing_data_center_status": _distribution(
            payloads["existing_data_center_status"],
            "Data_Center_Status",
            existing_count,
            "existing Data_Center_Status",
        ),
        "existing_built_status": _distribution(
            payloads["existing_built_status"],
            "Built_Status",
            existing_count,
            "existing Built_Status",
        ),
        "pipeline_status": _distribution(
            payloads["pipeline_status"],
            "FIRST_Status",
            pipeline_count,
            "pipeline FIRST_Status",
        ),
    }
    if distributions != _EXPECTED_DISTRIBUTIONS:
        raise LoudounDataCenterAssessmentError(
            "county status distributions changed; bump assessment"
        )

    layers = {
        "existing": _layer_schema(
            payloads["existing_layer"],
            item=existing_item,
            item_id=EXISTING_ITEM_ID,
            name="Existing_DC_Parcels_March1",
            object_id="OBJECTID_1",
            expected_fields=_EXISTING_FIELD_NAMES,
            feature_count=existing_count,
            count_artifact_id="existing_count",
        ),
        "pipeline": _layer_schema(
            payloads["pipeline_layer"],
            item=pipeline_item,
            item_id=PIPELINE_ITEM_ID,
            name="Proposed_DC_Parcels_March1_SINGLE",
            object_id="OBJECTID",
            expected_fields=_PIPELINE_FIELD_NAMES,
            feature_count=pipeline_count,
            count_artifact_id="pipeline_count",
        ),
    }

    assessment = {
        "access_assessment": deepcopy(_EXPECTED_ACCESS),
        "assessed_at": assessed_at,
        "assessment_id": ASSESSMENT_ID,
        "atlas_decision": deepcopy(_EXPECTED_DECISION),
        "count_assessment": deepcopy(_EXPECTED_COUNTS),
        "format": ASSESSMENT_FORMAT,
        "freshness_assessment": deepcopy(_EXPECTED_FRESHNESS),
        "granularity_assessment": deepcopy(_EXPECTED_GRANULARITY),
        "official_artifacts": official_artifacts,
        "permission_required_for_feature_release": sorted(
            _EXPECTED_PERMISSION_REQUIREMENTS
        ),
        "retrieval_batch": {
            "aggregate_result_rows_retrieved": 8,
            "count_only_query_requests": 2,
            "feature_rows_retrieved": 0,
            "full_feature_query_requests": 0,
            "grouped_statistics_query_requests": 3,
            "network_retrievals": len(ARTIFACT_URLS),
            "out_sr_4326_feature_queries": 0,
            "raw_artifacts_retained": False,
            "raw_feature_responses_retained": False,
            "retrieved_at": assessed_at,
            "transient_official_pdf_retrievals": 1,
            "transient_source_inspection_only": True,
        },
        "rights_assessment": deepcopy(_EXPECTED_RIGHTS),
        "schema_version": SCHEMA_VERSION,
        "source": {
            "assessor_guidelines_url": ASSESSOR_GUIDELINES_URL,
            "geohub_url": ARTIFACT_URLS["geohub_page"],
            "jurisdiction": "Loudoun County, Virginia, United States",
            "mapping_products_url": ARTIFACT_URLS["mapping_products_page"],
            "name": "Loudoun County data-center GIS and assessor calibration",
        },
    }
    schema = {
        "assessment_id": ASSESSMENT_ID,
        "contains_feature_attributes": False,
        "contains_feature_geometries": False,
        "contains_feature_records": False,
        "facility_lead_count": 0,
        "facility_leads": [],
        "format": SCHEMA_FORMAT,
        "generated_at": assessed_at,
        "inference_bans": sorted(_EXPECTED_INFERENCE_BANS),
        "layers": layers,
        "output_spatial_reference_retrieved": None,
        "power_energy_semantics": deepcopy(_EXPECTED_POWER_ENERGY),
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "status_semantics": deepcopy(_EXPECTED_STATUS_SEMANTICS),
        "unique_facility_count": None,
        "unit_semantics": deepcopy(_EXPECTED_UNIT_SEMANTICS),
    }
    calibration = {
        "assessment_id": ASSESSMENT_ID,
        "assessor_report": {
            "as_of_date": "2026-01-01",
            "category_rows": deepcopy(_EXPECTED_ASSESSOR_ROWS),
            "category_rows_reconcile_to_official_total": False,
            "official_artifact_id": "assessor_guidelines_pdf",
            "official_total": deepcopy(_EXPECTED_ASSESSOR_TOTAL),
            "parcel_composition_reconciliation": deepcopy(
                _EXPECTED_PARCEL_COMPOSITION_RECONCILIATION
            ),
            "published_on_report": "2026 Loudoun County Data Center Guidelines",
            "reconciliation": deepcopy(_EXPECTED_RECONCILIATION),
            "source_header_spelling_preserved_in_note": (
                "The PDF spells the under-construction column 'Under Contruction'."
            ),
        },
        "calibration_id": CALIBRATION_ID,
        "contains_feature_attributes_or_geometry": False,
        "contains_source_feature_rows": False,
        "format": CALIBRATION_FORMAT,
        "generated_at": assessed_at,
        "gis_snapshot": {
            "counts": deepcopy(_EXPECTED_COUNTS),
            "distributions": deepcopy(_EXPECTED_DISTRIBUTIONS),
            "distribution_values_normalized": False,
            "status_values_are_county_classifications_only": True,
        },
        "mapping_boundary": {
            "assessor_aggregate_categories_assigned_to_gis_rows": False,
            "cross_source_reconciliation_attempted": False,
            "gis_layer_counts_compared_as_equivalent_to_report_parcels": False,
            "gis_layer_counts_summed": False,
            "mw_or_energy_inferred": False,
            "report_complete_data_centers_are_parcel_counts": False,
            "report_under_construction_data_centers_are_gis_status_counts": False,
        },
        "schema_version": SCHEMA_VERSION,
        "unique_facility_count": None,
    }
    return assessment, schema, calibration


def _validate_artifacts(artifacts: Any) -> None:
    records = _object(artifacts, "official_artifacts")
    if set(records) != set(ARTIFACT_URLS):
        raise LoudounDataCenterAssessmentError("official artifact set differs")
    for artifact_id, expected_url in ARTIFACT_URLS.items():
        record = _object(records[artifact_id], f"official_artifacts.{artifact_id}")
        effective_url = record.get("effective_url")
        if (
            record.get("url") != expected_url
            or record.get("http_status") != 200
            or not isinstance(effective_url, str)
            or urlsplit(effective_url).scheme != "https"
            or urlsplit(effective_url).hostname not in _OFFICIAL_HOSTS
            or not isinstance(record.get("content_type"), str)
            or not record.get("content_type")
            or isinstance(record.get("bytes"), bool)
            or not isinstance(record.get("bytes"), int)
            or record.get("bytes") <= 0
            or not isinstance(record.get("sha256"), str)
            or not _SHA256_RE.fullmatch(record["sha256"])
        ):
            raise LoudounDataCenterAssessmentError(
                "artifact retrieval metadata is invalid"
            )
    pdf = _object(records["assessor_guidelines_pdf"], "assessor PDF artifact")
    if (
        pdf.get("bytes") != ASSESSOR_GUIDELINES_BYTES
        or pdf.get("sha256") != ASSESSOR_GUIDELINES_SHA256
    ):
        raise LoudounDataCenterAssessmentError("assessor PDF pin changed")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact rights, access, counts, and publication boundary."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise LoudounDataCenterAssessmentError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    batch = _object(document.get("retrieval_batch"), "retrieval_batch")
    if batch != {
        "aggregate_result_rows_retrieved": 8,
        "count_only_query_requests": 2,
        "feature_rows_retrieved": 0,
        "full_feature_query_requests": 0,
        "grouped_statistics_query_requests": 3,
        "network_retrievals": len(ARTIFACT_URLS),
        "out_sr_4326_feature_queries": 0,
        "raw_artifacts_retained": False,
        "raw_feature_responses_retained": False,
        "retrieved_at": assessed_at,
        "transient_official_pdf_retrievals": 1,
        "transient_source_inspection_only": True,
    }:
        raise LoudounDataCenterAssessmentError("retrieval boundary changed")
    _validate_artifacts(document.get("official_artifacts"))
    if document.get("source") != {
        "assessor_guidelines_url": ASSESSOR_GUIDELINES_URL,
        "geohub_url": ARTIFACT_URLS["geohub_page"],
        "jurisdiction": "Loudoun County, Virginia, United States",
        "mapping_products_url": ARTIFACT_URLS["mapping_products_page"],
        "name": "Loudoun County data-center GIS and assessor calibration",
    }:
        raise LoudounDataCenterAssessmentError("source identity changed")
    if document.get("rights_assessment") != _EXPECTED_RIGHTS:
        raise LoudounDataCenterAssessmentError("Loudoun rights must remain fail closed")
    if document.get("access_assessment") != _EXPECTED_ACCESS:
        raise LoudounDataCenterAssessmentError("Loudoun access boundary changed")
    if document.get("count_assessment") != _EXPECTED_COUNTS:
        raise LoudounDataCenterAssessmentError("parcel count semantics changed")
    if document.get("granularity_assessment") != _EXPECTED_GRANULARITY:
        raise LoudounDataCenterAssessmentError("parcel granularity changed")
    if document.get("freshness_assessment") != _EXPECTED_FRESHNESS:
        raise LoudounDataCenterAssessmentError("freshness semantics changed")
    if document.get("atlas_decision") != _EXPECTED_DECISION:
        raise LoudounDataCenterAssessmentError("Atlas decision changed")
    requirements = document.get("permission_required_for_feature_release")
    if (
        not isinstance(requirements, list)
        or set(requirements) != _EXPECTED_PERMISSION_REQUIREMENTS
        or len(requirements) != len(_EXPECTED_PERMISSION_REQUIREMENTS)
    ):
        raise LoudounDataCenterAssessmentError("permission unlock path changed")


def _validate_item_schema(
    item: Mapping[str, Any], *, item_id: str, title: str, pipeline: bool
) -> None:
    expected_statements = [_PUBLIC_AVAILABILITY_STATEMENT]
    if pipeline:
        expected_statements.append(_PIPELINE_DISCLAIMER_STATEMENT)
    if (
        item.get("item_id") != item_id
        or item.get("title") != title
        or item.get("owner") != ITEM_OWNER
        or item.get("public_access") is not True
        or item.get("terms_of_use") is not None
        or item.get("access_information") != ""
        or item.get("license_statements") != expected_statements
    ):
        raise LoudounDataCenterAssessmentError("ArcGIS item rights metadata changed")
    _timestamp(item.get("created_at"), f"{title}.created_at")
    _timestamp(item.get("modified_at"), f"{title}.modified_at")


def validate_schema_document(document: Mapping[str, Any]) -> None:
    """Validate exact layer contracts without accepting feature rows."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != SCHEMA_FORMAT
        or document.get("schema_id") != SCHEMA_ID
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise LoudounDataCenterAssessmentError("schema identity is invalid")
    _timestamp(document.get("generated_at"), "schema.generated_at")
    if (
        document.get("contains_feature_records") is not False
        or document.get("contains_feature_attributes") is not False
        or document.get("contains_feature_geometries") is not False
        or document.get("output_spatial_reference_retrieved") is not None
        or document.get("facility_leads") != []
        or document.get("facility_lead_count") != 0
        or document.get("unique_facility_count") is not None
    ):
        raise LoudounDataCenterAssessmentError("schema must remain metadata only")
    layers = _object(document.get("layers"), "layers")
    expected = {
        "existing": {
            "count": 139,
            "count_artifact": "existing_count",
            "fields": _EXISTING_FIELD_NAMES,
            "item_id": EXISTING_ITEM_ID,
            "name": "Existing_DC_Parcels_March1",
            "object_id": "OBJECTID_1",
            "pipeline": False,
            "title": "Existing_Data_Center_Parcel",
        },
        "pipeline": {
            "count": 85,
            "count_artifact": "pipeline_count",
            "fields": _PIPELINE_FIELD_NAMES,
            "item_id": PIPELINE_ITEM_ID,
            "name": "Proposed_DC_Parcels_March1_SINGLE",
            "object_id": "OBJECTID",
            "pipeline": True,
            "title": "Pipeline_Data_Center_Areas",
        },
    }
    if set(layers) != set(expected):
        raise LoudounDataCenterAssessmentError("layer set differs")
    for layer_key, spec in expected.items():
        layer = _object(layers[layer_key], f"layers.{layer_key}")
        fields = layer.get("fields")
        if not isinstance(fields, list):
            raise LoudounDataCenterAssessmentError("layer fields must be a list")
        if (
            layer.get("layer_id") != 1
            or layer.get("name") != spec["name"]
            or layer.get("object_id_field") != spec["object_id"]
            or layer.get("record_unit") != "parcel_record"
            or layer.get("feature_count") != spec["count"]
            or layer.get("count_query_artifact_id") != spec["count_artifact"]
            or layer.get("geometry_type") != "esriGeometryPolygon"
            or layer.get("field_count") != len(spec["fields"])
            or [field.get("name") for field in fields] != spec["fields"]
            or layer.get("relationships") != []
            or layer.get("max_record_count") != 2000
            or layer.get("supported_query_formats") != "JSON, geoJSON, PBF"
            or layer.get("supports_pagination") is not True
            or layer.get("supports_statistics") is not True
            or layer.get("description_defines_parcel_by_legal_ownership")
            is not True
            or layer.get("source_spatial_reference")
            != {"latestWkid": 2924, "wkid": 2924}
        ):
            raise LoudounDataCenterAssessmentError("layer contract changed")
        _validate_item_schema(
            _object(layer.get("item"), f"layers.{layer_key}.item"),
            item_id=spec["item_id"],
            title=spec["title"],
            pipeline=spec["pipeline"],
        )
    if document.get("status_semantics") != _EXPECTED_STATUS_SEMANTICS:
        raise LoudounDataCenterAssessmentError("county status semantics changed")
    if document.get("power_energy_semantics") != _EXPECTED_POWER_ENERGY:
        raise LoudounDataCenterAssessmentError("power or energy boundary changed")
    if document.get("unit_semantics") != _EXPECTED_UNIT_SEMANTICS:
        raise LoudounDataCenterAssessmentError("parcel or source unit changed")
    if document.get("inference_bans") != sorted(_EXPECTED_INFERENCE_BANS):
        raise LoudounDataCenterAssessmentError("inference boundary changed")


def validate_calibration_document(document: Mapping[str, Any]) -> None:
    """Validate live aggregates and the 2026 assessor report facts."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != CALIBRATION_FORMAT
        or document.get("calibration_id") != CALIBRATION_ID
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise LoudounDataCenterAssessmentError("calibration identity is invalid")
    _timestamp(document.get("generated_at"), "calibration.generated_at")
    if (
        document.get("contains_source_feature_rows") is not False
        or document.get("contains_feature_attributes_or_geometry") is not False
        or document.get("unique_facility_count") is not None
    ):
        raise LoudounDataCenterAssessmentError("calibration must remain aggregate only")
    gis = _object(document.get("gis_snapshot"), "gis_snapshot")
    if (
        gis.get("counts") != _EXPECTED_COUNTS
        or gis.get("distributions") != _EXPECTED_DISTRIBUTIONS
        or gis.get("distribution_values_normalized") is not False
        or gis.get("status_values_are_county_classifications_only") is not True
    ):
        raise LoudounDataCenterAssessmentError("GIS aggregate snapshot changed")
    report = _object(document.get("assessor_report"), "assessor_report")
    if (
        report.get("as_of_date") != "2026-01-01"
        or report.get("category_rows") != _EXPECTED_ASSESSOR_ROWS
        or report.get("official_total") != _EXPECTED_ASSESSOR_TOTAL
        or report.get("reconciliation") != _EXPECTED_RECONCILIATION
        or report.get("parcel_composition_reconciliation")
        != _EXPECTED_PARCEL_COMPOSITION_RECONCILIATION
        or report.get("category_rows_reconcile_to_official_total") is not False
        or report.get("official_artifact_id") != "assessor_guidelines_pdf"
        or report.get("published_on_report")
        != "2026 Loudoun County Data Center Guidelines"
        or report.get("source_header_spelling_preserved_in_note")
        != "The PDF spells the under-construction column 'Under Contruction'."
    ):
        raise LoudounDataCenterAssessmentError(
            "assessor calibration or nonreconciliation changed"
        )
    if document.get("mapping_boundary") != {
        "assessor_aggregate_categories_assigned_to_gis_rows": False,
        "cross_source_reconciliation_attempted": False,
        "gis_layer_counts_compared_as_equivalent_to_report_parcels": False,
        "gis_layer_counts_summed": False,
        "mw_or_energy_inferred": False,
        "report_complete_data_centers_are_parcel_counts": False,
        "report_under_construction_data_centers_are_gis_status_counts": False,
    }:
        raise LoudounDataCenterAssessmentError("calibration mapping boundary changed")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable Loudoun bundle without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise LoudounDataCenterAssessmentError(
            "assessment bundle must be a directory"
        )
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise LoudounDataCenterAssessmentError(
            "assessment entries must be regular files"
        )
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise LoudounDataCenterAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    schema = _load_json(directory / SCHEMA_FILENAME, "schema")
    calibration = _load_json(directory / CALIBRATION_FILENAME, "calibration")
    validate_assessment_document(assessment)
    validate_schema_document(schema)
    validate_calibration_document(calibration)
    if not (
        assessment.get("assessed_at")
        == schema.get("generated_at")
        == calibration.get("generated_at")
    ):
        raise LoudounDataCenterAssessmentError("bundle timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise LoudounDataCenterAssessmentError("manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    expected_payloads = {
        ASSESSMENT_FILENAME,
        SCHEMA_FILENAME,
        CALIBRATION_FILENAME,
    }
    if set(files) != expected_payloads:
        raise LoudounDataCenterAssessmentError("manifest file set differs")
    for filename in sorted(expected_payloads):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise LoudounDataCenterAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (
        directory.joinpath(MANIFEST_HASH_FILENAME).read_text(encoding="utf-8")
        != expected_sidecar
    ):
        raise LoudounDataCenterAssessmentError("manifest sidecar mismatch")
    return {
        "assessment": assessment,
        "calibration": calibration,
        "schema": schema,
    }


def write_assessment_bundle(
    output: str | Path,
    assessment: Mapping[str, Any],
    schema: Mapping[str, Any],
    calibration: Mapping[str, Any],
    *,
    freeze: bool = False,
) -> Path:
    """Atomically write one canonical bundle and optionally make it read-only."""

    directory = Path(output)
    if directory.exists() or directory.is_symlink():
        raise LoudounDataCenterAssessmentError("output bundle already exists")
    validate_assessment_document(assessment)
    validate_schema_document(schema)
    validate_calibration_document(calibration)
    if not (
        assessment.get("assessed_at")
        == schema.get("generated_at")
        == calibration.get("generated_at")
    ):
        raise LoudounDataCenterAssessmentError("bundle timestamps differ")

    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{directory.name}.", dir=directory.parent)
    )
    try:
        payloads = {
            ASSESSMENT_FILENAME: canonical_json(assessment),
            CALIBRATION_FILENAME: canonical_json(calibration),
            SCHEMA_FILENAME: canonical_json(schema),
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
                for filename, body in sorted(payloads.items())
            },
            "format": ASSESSMENT_FORMAT,
            "generated_at": assessment["assessed_at"],
            "schema_version": SCHEMA_VERSION,
        }
        manifest_bytes = canonical_json(manifest)
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_bytes)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_bytes)}  manifest.json\n", encoding="utf-8"
        )
        validate_assessment_bundle(temporary)
        if directory.exists() or directory.is_symlink():
            raise LoudounDataCenterAssessmentError("output bundle already exists")
        temporary.replace(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    if freeze:
        for filename in _EXPECTED_FILES:
            (directory / filename).chmod(0o444)
        directory.chmod(0o555)
    return directory
