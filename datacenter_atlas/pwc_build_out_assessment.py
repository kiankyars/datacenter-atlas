"""Build and validate the fail-closed PWC Build-Out GIS assessment."""

from __future__ import annotations

from copy import deepcopy
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
ASSESSMENT_FORMAT = "datacenter-atlas-pwc-build-out-assessment-v1"
SCHEMA_FORMAT = "datacenter-atlas-pwc-build-out-schema-assessment-v1"
ASSESSMENT_ID = "pwc-build-out-2026-07-18-v1"
SCHEMA_ID = "pwc-build-out-layers-9-11-2026-07-18-v1"
SERVICE_URL = (
    "https://gisweb.pwcva.gov/arcgis/rest/services/Planning/"
    "Build_Out_Analysis/MapServer"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    SCHEMA_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_OFFICIAL_HOSTS = {
    "gisdata-pwcgov.opendata.arcgis.com",
    "gisweb.pwcva.gov",
    "www.arcgis.com",
    "www.pwcva.gov",
}


ARTIFACT_URLS = {
    "build_out_page": (
        "https://www.pwcva.gov/department/planning-office/build-out-analysis"
    ),
    "gts_disclaimer": "https://www.pwcva.gov/disclaimer/",
    "open_data_portal": "https://gisdata-pwcgov.opendata.arcgis.com/",
    "open_data_site_item": (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "c7172932e18d4960af3c27747299f120?f=pjson"
    ),
    "open_data_terms_page": (
        "https://gisdata-pwcgov.opendata.arcgis.com/pages/terms-of-use"
    ),
    "open_data_terms_item": (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "b4be75279f694af994ea9ed9c8ea5fd0?f=pjson"
    ),
    "open_data_terms_data": (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "b4be75279f694af994ea9ed9c8ea5fd0/data?f=json"
    ),
    "service_definition": f"{SERVICE_URL}?f=pjson",
    "layer_9_definition": f"{SERVICE_URL}/9?f=pjson",
    "layer_9_iteminfo": f"{SERVICE_URL}/9/iteminfo?f=pjson",
    "layer_9_portal_item": (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "9c8104d64b1c4c45942aec06ccbe5f44?f=pjson"
    ),
    "layer_9_count": (
        f"{SERVICE_URL}/9/query?where=1%3D1&returnCountOnly=true&f=json"
    ),
    "layer_10_definition": f"{SERVICE_URL}/10?f=pjson",
    "layer_10_iteminfo": f"{SERVICE_URL}/10/iteminfo?f=pjson",
    "layer_10_portal_item": (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "6f78a8a553db46cb9bd14e22a9560c86?f=pjson"
    ),
    "layer_10_count": (
        f"{SERVICE_URL}/10/query?where=1%3D1&returnCountOnly=true&f=json"
    ),
    "layer_11_definition": f"{SERVICE_URL}/11?f=pjson",
    "layer_11_iteminfo": f"{SERVICE_URL}/11/iteminfo?f=pjson",
    "layer_11_count": (
        f"{SERVICE_URL}/11/query?where=1%3D1&returnCountOnly=true&f=json"
    ),
}

_JSON_ARTIFACT_IDS = {
    "open_data_site_item",
    "open_data_terms_item",
    "open_data_terms_data",
    "service_definition",
    "layer_9_definition",
    "layer_9_iteminfo",
    "layer_9_portal_item",
    "layer_9_count",
    "layer_10_definition",
    "layer_10_iteminfo",
    "layer_10_portal_item",
    "layer_10_count",
    "layer_11_definition",
    "layer_11_iteminfo",
    "layer_11_count",
}

_LAYER_SPECS = {
    9: {
        "count": 243,
        "entity_level": "building_record",
        "geometry_type": "esriGeometryPoint",
        "item_title": "Data Center Buildings",
        "name": "Data Center Buildings",
    },
    10: {
        "count": 72,
        "entity_level": "campus_project_record",
        "geometry_type": "esriGeometryPolygon",
        "item_title": "Data Center Projects",
        "name": "Data Center Campuses",
    },
    11: {
        "count": 61,
        "entity_level": "planning_site_application_record",
        "geometry_type": "esriGeometryPoint",
        "item_title": "gisdb.PLANNING.DataCenterSites",
        "name": "Data Center Sites",
    },
}

_EXPECTED_FIELD_NAMES = {
    9: [
        "OBJECTID",
        "GlobalID",
        "GPIN",
        "BuildingName",
        "PID",
        "Address",
        "BuildingID",
        "BuildingStatus",
        "YearBuilt",
        "GFASource",
        "PermitCase",
        "PermitStatus",
        "GFA",
        "DCOOD",
        "OCCDate",
        "BPGFA",
        "EnergovID",
        "CreateUser",
        "CreateDate",
        "LastEditUser",
        "LastEditDate",
        "Shape",
        "ApprovedGFA",
        "PermittedGFA",
        "REATaxedGFA",
        "PlanningCaseNumber",
        "PlanningCaseName",
        "PlanCaseEnergovID",
    ],
    10: [
        "OBJECTID",
        "ZoningDistrict",
        "CaseNumber",
        "CaseName",
        "EnergovID",
        "RemainingGFA",
        "ChangeTrigger",
        "GISAcreage",
        "MagistDist",
        "GlobalID",
        "CreateUser",
        "CreateDate",
        "LastEditUser",
        "LastEditDate",
        "ProjectStatus",
        "CampusName",
        "PlannedGFA",
        "DCOOD",
        "Shape",
        "Shape.STArea()",
        "Shape.STLength()",
    ],
    11: [
        "OBJECTID",
        "GlobalID",
        "ZoningCaseNumber",
        "CaseName",
        "AppType",
        "Workclass",
        "Acreage",
        "GFA",
        "Zoned",
        "Status",
        "AppAccDate",
        "Address",
        "CreateUser",
        "CreateDate",
        "LastEditUser",
        "LastEditDate",
        "Shape",
    ],
}

_EXPECTED_CODED_VALUES = {
    (9, "BuildingStatus"): [
        ["Completed", "Completed"],
        ["Pending", "Pending"],
        ["Planned", "Planned"],
        ["Under Construction", "Under Construction"],
        ["Approved Site Plan", "Approved Site Plan"],
    ],
    (9, "GFASource"): [
        ["Building Permit", "Building Permit"],
        ["Estimated", "Estimated"],
        ["Proffer", "Proffer"],
        ["Site Plan", "Site Plan"],
        ["Waiver", "Waiver"],
        ["Real Estate Assessements", "Real Estate Assessments"],
    ],
    (9, "PermitStatus"): [
        ["Issued", "Issued"],
        ["Pending", "Pending"],
        ["Planned", "Planned"],
        ["Potential", "Potential"],
        ["Finaled", "Finaled"],
    ],
    (9, "DCOOD"): [["Yes", "Yes"], ["No", "No"]],
    (10, "MagistDist"): [
        ["Brentsville", "Brentsville"],
        ["Coles", "Coles"],
        ["Gainesville", "Gainesville"],
        ["Neabsco", "Neabsco"],
        ["Occoquan", "Occoquan"],
        ["Potomac", "Potomac"],
        ["Woodbridge", "Woodbridge"],
    ],
    (10, "DCOOD"): [["Yes", "Yes"], ["No", "No"]],
}

_EXPECTED_RIGHTS = {
    "affirmative_commercial_use_permission_found": False,
    "affirmative_public_redistribution_permission_found": False,
    "build_out_page_advertises_attribute_export": True,
    "build_out_page_advertises_layer_download": True,
    "cc_by_sa_version_or_deed_url_identified": False,
    "derivative_database_publication_permitted": False,
    "download_availability_is_treated_as_redistribution_license": False,
    "layer_11_iteminfo_license_is_blank": True,
    "layer_9_and_10_portal_items_link_to_county_disclaimer": True,
    "legal_conclusion_claimed": False,
    "open_data_portal_site_item_license_text": "CC-BY-SA",
    "portal_site_item_license_scope_covers_layers_9_10_11": False,
    "portal_site_item_license_treated_as_layer_data_license": False,
    "public_display_of_source_rows_permitted": False,
    "raw_feature_cache_for_atlas_release_permitted": False,
    "terms_are_reference_use_conditions_and_disclaimers": True,
}

_EXPECTED_ACCESS = {
    "anonymous_count_queries_succeeded": True,
    "count_only_query_requests": 3,
    "feature_query_capability_advertised": True,
    "full_feature_query_requests": 0,
    "geometry_out_sr_4326_query_performed": False,
    "max_record_count": 2000,
    "pagination_supported": True,
    "service_url": SERVICE_URL,
    "supported_query_formats": "JSON, geoJSON, PBF",
}

_EXPECTED_COUNTS = {
    "building_records": 243,
    "campus_project_records": 72,
    "counts_are_distinct_entity_levels": True,
    "counts_may_overlap_conceptually": True,
    "planning_site_application_records": 61,
    "record_counts_summed": False,
    "unique_site_count": None,
}

_EXPECTED_FRESHNESS = {
    "build_out_page_claims_data_center_updates_as_quickly_as_possible": True,
    "build_out_page_claims_quarterly_or_case_triggered_updates": True,
    "count_queries_are_snapshot_scoped": True,
    "layer_9_and_10_portal_item_modified_is_row_freshness": False,
    "per_record_create_and_last_edit_fields_documented": True,
    "record_dates_retrieved": False,
    "service_snapshot_version_field_found": False,
}

_EXPECTED_GRANULARITY = {
    "auto_merge_permitted": False,
    "building_campus_or_site_relationships_documented": False,
    "campus_project_records_are_unique_facilities": False,
    "cross_layer_global_id_join_documented": False,
    "entity_levels_kept_separate": True,
    "planning_site_application_records_are_physical_sites": False,
    "record_count_is_unique_site_count": False,
}

_EXPECTED_DECISION = {
    "auto_merge_permitted": False,
    "construction_status_promotion_permitted": False,
    "feature_release_created": False,
    "publication_eligible_release_created": False,
    "review_leads_emitted": 0,
    "source_content_publication_eligible": False,
    "status": "rights_blocked_metadata_only",
    "typed_power_or_energy_promotion_permitted": False,
    "unique_site_count_published": False,
}

_EXPECTED_PERMISSION_REQUIREMENTS = {
    "attribution_and_notice_requirements",
    "clarification_whether_and_which_cc_by_sa_version_applies_to_layers_9_10_11",
    "commercial_use_in_a_compiled_data_product",
    "local_storage_and_raw_response_cache",
    "modification_and_derivative_database_creation",
    "public_display_and_redistribution_of_source_derived_records",
    "refresh_retention_and_termination_terms",
    "share_alike_scope_if_applicable",
    "sublicensing_or_downstream_end_user_access",
}

_EXPECTED_GFA_SEMANTICS = {
    "9": {
        "ApprovedGFA": {
            "quantity": "approved_gross_floor_area",
            "source_alias": "Approved GFA",
            "unit": "square_feet",
            "value_provenance_fields": ["ApprovedGFA"],
        },
        "BPGFA": {
            "quantity": "building_permit_gross_floor_area",
            "source_alias": "Building Permit GFA",
            "unit": "square_feet",
            "value_provenance_fields": ["BPGFA", "PermitCase", "PermitStatus"],
        },
        "GFA": {
            "quantity": "planned_gross_floor_area",
            "source_alias": "Planned GFA",
            "unit": "square_feet",
            "value_provenance_fields": ["GFA", "GFASource"],
        },
        "PermittedGFA": {
            "quantity": "permitted_gross_floor_area",
            "source_alias": "Permitted GFA",
            "unit": "square_feet",
            "value_provenance_fields": [
                "PermittedGFA",
                "PermitCase",
                "PermitStatus",
            ],
        },
        "REATaxedGFA": {
            "quantity": "real_estate_assessment_taxed_gross_floor_area",
            "source_alias": "REA Taxed GFA",
            "unit": "square_feet",
            "value_provenance_fields": ["REATaxedGFA"],
        },
    },
    "10": {
        "PlannedGFA": {
            "quantity": "planned_gross_floor_area",
            "source_alias": "Planned GFA",
            "unit": "square_feet",
            "value_provenance_fields": ["PlannedGFA", "CaseNumber"],
        },
        "RemainingGFA": {
            "quantity": "remaining_gross_floor_area",
            "source_alias": "Remaining SqFt",
            "unit": "square_feet",
            "value_provenance_fields": ["RemainingGFA", "CaseNumber"],
        },
    },
    "11": {
        "GFA": {
            "quantity": "application_gross_floor_area",
            "source_alias": "Gross Floor Area (GFA)",
            "unit": "square_feet",
            "value_provenance_fields": ["GFA", "ZoningCaseNumber"],
        }
    },
}

_EXPECTED_IDENTIFIER_FIELDS = {
    "9": [
        "OBJECTID",
        "GlobalID",
        "GPIN",
        "PID",
        "BuildingID",
        "EnergovID",
        "PermitCase",
        "PlanningCaseNumber",
        "PlanCaseEnergovID",
    ],
    "10": ["OBJECTID", "GlobalID", "CaseNumber", "EnergovID"],
    "11": ["OBJECTID", "GlobalID", "ZoningCaseNumber"],
}

_EXPECTED_STATUS_SEMANTICS = {
    "completed_means_operational": False,
    "county_under_construction_evidence": {
        "atlas_auto_promotion": False,
        "evidence_scope": "source_record_and_retrieval_snapshot_only",
        "layer_id": 9,
        "records_retrieved": False,
        "source_field": "BuildingStatus",
        "source_value": "Under Construction",
    },
    "layer_10_project_status_is_free_text": True,
    "layer_11_status_is_application_status": True,
    "permit_status_is_building_lifecycle_status": False,
}

_EXPECTED_POWER_ENERGY = {
    "annual_energy_inference_permitted": False,
    "capacity_or_power_fields_documented": [],
    "operational_workload_fields_documented": [],
    "power_capacity_inference_permitted": False,
    "pue_fields_documented": [],
}

_EXPECTED_INFERENCE_BANS = {
    "do_not_call_completed_operational_without_separate_evidence",
    "do_not_convert_gfa_to_power_or_energy",
    "do_not_merge_building_campus_and_site_records_automatically",
    "do_not_promote_application_status_to_facility_lifecycle",
    "do_not_publish_a_sum_of_layer_counts_as_unique_sites",
    "do_not_treat_portal_site_cc_by_sa_as_a_layer_license",
}


class PWCBuildOutAssessmentError(ValueError):
    """Raised when the PWC assessment violates its fail-closed boundary."""


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
        raise PWCBuildOutAssessmentError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PWCBuildOutAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PWCBuildOutAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PWCBuildOutAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PWCBuildOutAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PWCBuildOutAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise PWCBuildOutAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != canonical_json(value):
        raise PWCBuildOutAssessmentError(f"{label} is not canonical JSON")
    return value


def _json_body(bodies: Mapping[str, bytes], artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(bodies[artifact_id].decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise PWCBuildOutAssessmentError(
            f"{artifact_id} did not contain valid JSON"
        ) from error
    if not isinstance(value, dict):
        raise PWCBuildOutAssessmentError(f"{artifact_id} must contain an object")
    return value


def _validate_retrieval_inputs(
    retrievals: Mapping[str, Mapping[str, Any]], bodies: Mapping[str, bytes]
) -> dict[str, dict[str, Any]]:
    if set(retrievals) != set(ARTIFACT_URLS) or set(bodies) != set(ARTIFACT_URLS):
        raise PWCBuildOutAssessmentError("official artifact set differs")
    result: dict[str, dict[str, Any]] = {}
    for artifact_id, expected_url in ARTIFACT_URLS.items():
        record = _object(retrievals[artifact_id], f"retrievals.{artifact_id}")
        body = bodies[artifact_id]
        if not isinstance(body, bytes) or not body:
            raise PWCBuildOutAssessmentError("artifact bodies must be non-empty bytes")
        effective_url = record.get("effective_url")
        content_type = record.get("content_type")
        status = record.get("http_status")
        if (
            record.get("url") != expected_url
            or not isinstance(effective_url, str)
            or urlsplit(effective_url).scheme != "https"
            or urlsplit(effective_url).hostname not in _OFFICIAL_HOSTS
            or status != 200
            or not isinstance(content_type, str)
            or not content_type
        ):
            raise PWCBuildOutAssessmentError("artifact retrieval metadata is invalid")
        result[artifact_id] = {
            "bytes": len(body),
            "content_type": content_type,
            "effective_url": effective_url,
            "http_status": 200,
            "sha256": sha256_bytes(body),
            "url": expected_url,
        }
    return result


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


def _portal_modified_at(item: Mapping[str, Any]) -> str:
    value = item.get("modified")
    if isinstance(value, bool) or not isinstance(value, int):
        raise PWCBuildOutAssessmentError("portal item modified value is invalid")
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def build_assessment_documents(
    retrievals: Mapping[str, Mapping[str, Any]],
    bodies: Mapping[str, bytes],
    assessed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive deterministic metadata-only documents from transient responses."""

    assessed_at = _timestamp(assessed_at, "assessed_at")
    official_artifacts = _validate_retrieval_inputs(retrievals, bodies)
    payloads = {
        artifact_id: _json_body(bodies, artifact_id)
        for artifact_id in _JSON_ARTIFACT_IDS
    }

    service = payloads["service_definition"]
    if (
        service.get("currentVersion") != 10.91
        or service.get("mapName") != "Build Out Analysis"
        or service.get("maxRecordCount") != 2000
        or service.get("supportedQueryFormats") != "JSON, geoJSON, PBF"
    ):
        raise PWCBuildOutAssessmentError("service contract changed; bump assessment")

    site_item = payloads["open_data_site_item"]
    terms_item = payloads["open_data_terms_item"]
    terms_data = payloads["open_data_terms_data"]
    if (
        site_item.get("id") != "c7172932e18d4960af3c27747299f120"
        or site_item.get("owner") != "PrinceWilliamCounty"
        or site_item.get("type") != "Web Mapping Application"
        or site_item.get("licenseInfo") != "CC-BY-SA"
    ):
        raise PWCBuildOutAssessmentError("Open Data site license scope changed")
    if (
        terms_item.get("id") != "b4be75279f694af994ea9ed9c8ea5fd0"
        or terms_item.get("owner") != "PrinceWilliamCounty"
        or terms_item.get("title")
        != "Prince William County GIS Data Portal Terms of Use"
    ):
        raise PWCBuildOutAssessmentError("Open Data terms item changed")
    terms_markdown = (
        terms_data.get("values", {})
        .get("layout", {})
        .get("sections", [{}])[0]
        .get("rows", [{}])[0]
        .get("cards", [{}])[0]
        .get("component", {})
        .get("settings", {})
        .get("markdown")
    )
    if not isinstance(terms_markdown, str) or not all(
        marker in terms_markdown
        for marker in (
            "reference purposes only",
            "indemnify and hold harmless",
            "reserves the right to deny access",
            'provided <i>"as is"</i>',
        )
    ):
        raise PWCBuildOutAssessmentError("Open Data terms text changed")

    layer_schemas: dict[str, Any] = {}
    portal_items: dict[int, Mapping[str, Any]] = {
        9: payloads["layer_9_portal_item"],
        10: payloads["layer_10_portal_item"],
    }
    for layer_id, spec in _LAYER_SPECS.items():
        layer = payloads[f"layer_{layer_id}_definition"]
        iteminfo = payloads[f"layer_{layer_id}_iteminfo"]
        count_response = payloads[f"layer_{layer_id}_count"]
        if set(count_response) != {"count"} or count_response.get("count") != spec[
            "count"
        ]:
            raise PWCBuildOutAssessmentError(
                f"layer {layer_id} count changed; bump assessment"
            )
        if (
            layer.get("id") != layer_id
            or layer.get("name") != spec["name"]
            or layer.get("geometryType") != spec["geometry_type"]
            or layer.get("maxRecordCount") != 2000
            or layer.get("relationships") != []
            or iteminfo.get("title") != spec["item_title"]
        ):
            raise PWCBuildOutAssessmentError(
                f"layer {layer_id} identity changed; bump assessment"
            )
        fields = [_field_contract(field) for field in layer.get("fields", [])]
        if [field["name"] for field in fields] != _EXPECTED_FIELD_NAMES[layer_id]:
            raise PWCBuildOutAssessmentError(
                f"layer {layer_id} field contract changed; bump assessment"
            )
        portal_metadata: dict[str, Any] | None = None
        if layer_id in portal_items:
            portal = portal_items[layer_id]
            expected_item_id = {
                9: "9c8104d64b1c4c45942aec06ccbe5f44",
                10: "6f78a8a553db46cb9bd14e22a9560c86",
            }[layer_id]
            if (
                portal.get("id") != expected_item_id
                or portal.get("owner") != "PrinceWilliamCounty"
                or portal.get("url") != f"{SERVICE_URL}/{layer_id}"
                or "pwcva.gov/disclaimer" not in str(portal.get("licenseInfo"))
            ):
                raise PWCBuildOutAssessmentError(
                    f"layer {layer_id} portal item changed"
                )
            portal_metadata = {
                "item_id": portal["id"],
                "modified_at": _portal_modified_at(portal),
                "owner": portal["owner"],
                "public_access": portal.get("access") == "public",
            }
        elif iteminfo.get("licenseInfo") not in {"", None}:
            raise PWCBuildOutAssessmentError("layer 11 licenseInfo is no longer blank")

        layer_schemas[str(layer_id)] = {
            "count_query_artifact_id": f"layer_{layer_id}_count",
            "description": layer.get("description"),
            "display_field": layer.get("displayField"),
            "entity_level": spec["entity_level"],
            "extent": deepcopy(layer.get("extent")),
            "feature_count": spec["count"],
            "field_count": len(fields),
            "fields": fields,
            "geometry_field": deepcopy(layer.get("geometryField")),
            "geometry_type": spec["geometry_type"],
            "item_access_information": iteminfo.get("accessInformation"),
            "item_title": iteminfo.get("title"),
            "layer_id": layer_id,
            "max_record_count": layer.get("maxRecordCount"),
            "name": spec["name"],
            "portal_item": portal_metadata,
            "relationships": [],
            "source_spatial_reference": deepcopy(
                layer.get("sourceSpatialReference")
            ),
            "supported_query_formats": layer.get("supportedQueryFormats"),
            "supports_pagination": layer.get("advancedQueryCapabilities", {}).get(
                "supportsPagination"
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
        "permission_required_for_reassessment": sorted(
            _EXPECTED_PERMISSION_REQUIREMENTS
        ),
        "retrieval_batch": {
            "count_only_query_requests": 3,
            "feature_rows_retrieved": 0,
            "full_feature_query_requests": 0,
            "network_retrievals": len(ARTIFACT_URLS),
            "raw_artifacts_retained": False,
            "raw_feature_responses_retained": False,
            "retrieved_at": assessed_at,
            "transient_inspection_only": True,
        },
        "rights_assessment": deepcopy(_EXPECTED_RIGHTS),
        "schema_version": SCHEMA_VERSION,
        "source": {
            "build_out_page_url": ARTIFACT_URLS["build_out_page"],
            "jurisdiction": "Prince William County, Virginia, United States",
            "name": "Prince William County Build-Out Analysis",
            "service_url": SERVICE_URL,
        },
    }
    schema = {
        "assessment_id": ASSESSMENT_ID,
        "contains_addresses_coordinates_or_feature_geometries": False,
        "contains_feature_records": False,
        "facility_lead_count": 0,
        "facility_leads": [],
        "format": SCHEMA_FORMAT,
        "generated_at": assessed_at,
        "gfa_semantics": deepcopy(_EXPECTED_GFA_SEMANTICS),
        "identifier_fields": deepcopy(_EXPECTED_IDENTIFIER_FIELDS),
        "inference_bans": sorted(_EXPECTED_INFERENCE_BANS),
        "layers": layer_schemas,
        "output_spatial_reference_retrieved": None,
        "power_energy_semantics": deepcopy(_EXPECTED_POWER_ENERGY),
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "status_semantics": deepcopy(_EXPECTED_STATUS_SEMANTICS),
        "unique_facility_count": None,
        "unit_provenance": {
            "acreage_fields_use_acres_from_source_names_or_aliases": [
                "10.GISAcreage",
                "11.Acreage",
            ],
            "gfa_square_feet_basis": (
                "The official Build-Out page describes non-residential GFA in "
                "square feet; layer aliases additionally say Remaining SqFt and "
                "Gross Floor Area (GFA)."
            ),
            "no_unit_conversion_performed": True,
        },
    }
    return assessment, schema


def _coded_values(layer: Mapping[str, Any], field_name: str) -> list[list[str]]:
    fields = layer.get("fields")
    if not isinstance(fields, list):
        raise PWCBuildOutAssessmentError("layer fields must be a list")
    for raw in fields:
        field = _object(raw, "layer field")
        if field.get("name") != field_name:
            continue
        domain = _object(field.get("domain"), f"{field_name} domain")
        values = domain.get("codedValues")
        if not isinstance(values, list):
            raise PWCBuildOutAssessmentError("codedValues must be a list")
        result: list[list[str]] = []
        for raw_value in values:
            value = _object(raw_value, "coded value")
            name = value.get("name")
            code = value.get("code")
            if not isinstance(name, str) or not isinstance(code, str):
                raise PWCBuildOutAssessmentError("coded values must be strings")
            result.append([name, code])
        return result
    raise PWCBuildOutAssessmentError(f"missing coded field {field_name}")


def _validate_artifacts(artifacts: Any) -> None:
    records = _object(artifacts, "official_artifacts")
    if set(records) != set(ARTIFACT_URLS):
        raise PWCBuildOutAssessmentError("official artifact set differs")
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
            raise PWCBuildOutAssessmentError("artifact retrieval metadata is invalid")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the exact rights, access, counts, and publication boundary."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != ASSESSMENT_FORMAT
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise PWCBuildOutAssessmentError("assessment identity is invalid")
    assessed_at = _timestamp(document.get("assessed_at"), "assessed_at")
    batch = _object(document.get("retrieval_batch"), "retrieval_batch")
    if batch != {
        "count_only_query_requests": 3,
        "feature_rows_retrieved": 0,
        "full_feature_query_requests": 0,
        "network_retrievals": len(ARTIFACT_URLS),
        "raw_artifacts_retained": False,
        "raw_feature_responses_retained": False,
        "retrieved_at": assessed_at,
        "transient_inspection_only": True,
    }:
        raise PWCBuildOutAssessmentError("retrieval boundary changed")
    _validate_artifacts(document.get("official_artifacts"))
    if document.get("source") != {
        "build_out_page_url": ARTIFACT_URLS["build_out_page"],
        "jurisdiction": "Prince William County, Virginia, United States",
        "name": "Prince William County Build-Out Analysis",
        "service_url": SERVICE_URL,
    }:
        raise PWCBuildOutAssessmentError("source identity changed")
    if document.get("rights_assessment") != _EXPECTED_RIGHTS:
        raise PWCBuildOutAssessmentError("PWC rights must remain fail closed")
    if document.get("access_assessment") != _EXPECTED_ACCESS:
        raise PWCBuildOutAssessmentError("PWC access boundary changed")
    if document.get("count_assessment") != _EXPECTED_COUNTS:
        raise PWCBuildOutAssessmentError("PWC count semantics changed")
    if document.get("freshness_assessment") != _EXPECTED_FRESHNESS:
        raise PWCBuildOutAssessmentError("PWC freshness semantics changed")
    if document.get("granularity_assessment") != _EXPECTED_GRANULARITY:
        raise PWCBuildOutAssessmentError("PWC entity granularity changed")
    if document.get("atlas_decision") != _EXPECTED_DECISION:
        raise PWCBuildOutAssessmentError("PWC Atlas decision changed")
    requirements = document.get("permission_required_for_reassessment")
    if (
        not isinstance(requirements, list)
        or set(requirements) != _EXPECTED_PERMISSION_REQUIREMENTS
        or len(requirements) != len(_EXPECTED_PERMISSION_REQUIREMENTS)
    ):
        raise PWCBuildOutAssessmentError("PWC permission unlock path changed")


def validate_schema_document(document: Mapping[str, Any]) -> None:
    """Validate exact layer contracts without accepting feature records."""

    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != SCHEMA_FORMAT
        or document.get("schema_id") != SCHEMA_ID
        or document.get("assessment_id") != ASSESSMENT_ID
    ):
        raise PWCBuildOutAssessmentError("schema identity is invalid")
    _timestamp(document.get("generated_at"), "schema generated_at")
    if (
        document.get("contains_feature_records") is not False
        or document.get("contains_addresses_coordinates_or_feature_geometries")
        is not False
        or document.get("output_spatial_reference_retrieved") is not None
        or document.get("facility_leads") != []
        or document.get("facility_lead_count") != 0
        or document.get("unique_facility_count") is not None
    ):
        raise PWCBuildOutAssessmentError("schema must remain metadata only")
    layers = _object(document.get("layers"), "layers")
    if set(layers) != {"9", "10", "11"}:
        raise PWCBuildOutAssessmentError("layer set differs")
    for layer_id, spec in _LAYER_SPECS.items():
        layer = _object(layers[str(layer_id)], f"layers.{layer_id}")
        fields = layer.get("fields")
        if not isinstance(fields, list):
            raise PWCBuildOutAssessmentError("layer fields must be a list")
        if (
            layer.get("layer_id") != layer_id
            or layer.get("name") != spec["name"]
            or layer.get("item_title") != spec["item_title"]
            or layer.get("entity_level") != spec["entity_level"]
            or layer.get("feature_count") != spec["count"]
            or layer.get("geometry_type") != spec["geometry_type"]
            or layer.get("field_count") != len(_EXPECTED_FIELD_NAMES[layer_id])
            or [field.get("name") for field in fields]
            != _EXPECTED_FIELD_NAMES[layer_id]
            or layer.get("relationships") != []
            or layer.get("max_record_count") != 2000
            or layer.get("supported_query_formats") != "JSON, geoJSON, PBF"
            or layer.get("supports_pagination") is not True
            or layer.get("count_query_artifact_id")
            != f"layer_{layer_id}_count"
        ):
            raise PWCBuildOutAssessmentError(
                f"layer {layer_id} contract changed"
            )
        source_sr = _object(
            layer.get("source_spatial_reference"),
            f"layers.{layer_id}.source_spatial_reference",
        )
        if source_sr.get("wkid") != 102746 or source_sr.get("latestWkid") != 2283:
            raise PWCBuildOutAssessmentError("source spatial reference changed")
    for (layer_id, field_name), expected in _EXPECTED_CODED_VALUES.items():
        if _coded_values(_object(layers[str(layer_id)], "layer"), field_name) != expected:
            raise PWCBuildOutAssessmentError("coded value domain changed")
    if document.get("gfa_semantics") != _EXPECTED_GFA_SEMANTICS:
        raise PWCBuildOutAssessmentError("GFA units or provenance changed")
    if document.get("identifier_fields") != _EXPECTED_IDENTIFIER_FIELDS:
        raise PWCBuildOutAssessmentError("identifier semantics changed")
    if document.get("status_semantics") != _EXPECTED_STATUS_SEMANTICS:
        raise PWCBuildOutAssessmentError("status evidence semantics changed")
    if document.get("power_energy_semantics") != _EXPECTED_POWER_ENERGY:
        raise PWCBuildOutAssessmentError("power or energy semantics changed")
    if document.get("inference_bans") != sorted(_EXPECTED_INFERENCE_BANS):
        raise PWCBuildOutAssessmentError("inference boundary changed")
    unit_provenance = _object(document.get("unit_provenance"), "unit_provenance")
    if (
        unit_provenance.get("no_unit_conversion_performed") is not True
        or unit_provenance.get(
            "acreage_fields_use_acres_from_source_names_or_aliases"
        )
        != ["10.GISAcreage", "11.Acreage"]
        or not isinstance(unit_provenance.get("gfa_square_feet_basis"), str)
    ):
        raise PWCBuildOutAssessmentError("unit provenance changed")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the immutable PWC bundle without network requests."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise PWCBuildOutAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise PWCBuildOutAssessmentError("assessment entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise PWCBuildOutAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    schema = _load_json(directory / SCHEMA_FILENAME, "schema assessment")
    validate_assessment_document(assessment)
    validate_schema_document(schema)
    if schema.get("generated_at") != assessment.get("assessed_at"):
        raise PWCBuildOutAssessmentError("bundle timestamps differ")

    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != ASSESSMENT_ID
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise PWCBuildOutAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME, SCHEMA_FILENAME}:
        raise PWCBuildOutAssessmentError("assessment manifest file set differs")
    for filename in (ASSESSMENT_FILENAME, SCHEMA_FILENAME):
        record = _object(files[filename], f"manifest {filename}")
        artifact = directory / filename
        if (
            record.get("bytes") != artifact.stat().st_size
            or record.get("sha256") != _sha256(artifact)
        ):
            raise PWCBuildOutAssessmentError(f"{filename} hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    sidecar = directory / MANIFEST_HASH_FILENAME
    if sidecar.read_text(encoding="utf-8") != expected_sidecar:
        raise PWCBuildOutAssessmentError("assessment manifest sidecar mismatch")
    return {"assessment": assessment, "schema": schema}


def write_assessment_bundle(
    output: str | Path,
    assessment: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    freeze: bool = False,
) -> Path:
    """Write one new canonical bundle and optionally make it read-only."""

    directory = Path(output)
    if directory.exists() or directory.is_symlink():
        raise PWCBuildOutAssessmentError("output bundle already exists")
    validate_assessment_document(assessment)
    validate_schema_document(schema)
    if assessment.get("assessed_at") != schema.get("generated_at"):
        raise PWCBuildOutAssessmentError("bundle timestamps differ")
    directory.mkdir(parents=True)
    assessment_bytes = canonical_json(assessment)
    schema_bytes = canonical_json(schema)
    (directory / ASSESSMENT_FILENAME).write_bytes(assessment_bytes)
    (directory / SCHEMA_FILENAME).write_bytes(schema_bytes)
    manifest = {
        "assessment_id": ASSESSMENT_ID,
        "files": {
            ASSESSMENT_FILENAME: {
                "bytes": len(assessment_bytes),
                "sha256": sha256_bytes(assessment_bytes),
            },
            SCHEMA_FILENAME: {
                "bytes": len(schema_bytes),
                "sha256": sha256_bytes(schema_bytes),
            },
        },
        "format": ASSESSMENT_FORMAT,
        "generated_at": assessment["assessed_at"],
        "schema_version": SCHEMA_VERSION,
    }
    manifest_bytes = canonical_json(manifest)
    (directory / MANIFEST_FILENAME).write_bytes(manifest_bytes)
    (directory / MANIFEST_HASH_FILENAME).write_text(
        f"{sha256_bytes(manifest_bytes)}  manifest.json\n", encoding="utf-8"
    )
    validate_assessment_bundle(directory)
    if freeze:
        for filename in _EXPECTED_FILES:
            (directory / filename).chmod(0o444)
        directory.chmod(0o555)
    return directory
