"""Bounded Denmark Plandata.dk local-plan source assessment.

The lane searches only the local-plan name field on three official WFS layers.
It keeps planning observations separate from physical data-centre lifecycle and
capacity facts.  Proposal, adopted, and effective dates are planning facts;
cancelled plans are negative planning observations.  None proves construction.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
import uuid
import xml.etree.ElementTree as ET


SCHEMA_VERSION = 1
ASSESSMENT_DATE = date(2026, 7, 19)
RELEASE_ID = "denmark-plandata-local-plan-data-centre-search-2026-07-19-v1"
RELEASE_FORMAT = "datacenter-atlas-denmark-plandata-assessment-v1"
CAPTURE_FORMAT = "datacenter-atlas-denmark-plandata-capture-v1"
DEFINITION_FORMAT = "datacenter-atlas-denmark-plandata-definition-v1"
OBSERVATION_FORMAT = "datacenter-atlas-denmark-plandata-observation-v1"

PUBLISHER = "Plan- og Landdistriktsstyrelsen / Plandata.dk"
DATASET_TITLE = "Local plan - PlanDK"
DATASET_ID = "7a0b537c-8161-4827-a9c8-c39aff0ca49d"
DATASET_URL = (
    "https://datavejviser.dk/katalog/plan-og-landdistriktsstyrelsen/"
    f"{DATASET_ID}"
)
LICENSE_JSONLD_URL = f"{DATASET_URL}.jsonld"
LICENSE_URI = (
    "http://publications.europa.eu/resource/authority/licence/CC_BY_4_0"
)
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
WFS_INTRO_URL = (
    "https://www.plandata.dk/webservices/introduktion-til-webservices/wfs"
)
DATA_MODEL_URL = (
    "https://www.plandata.dk/teknisk-information/datamodeller/lokalplaner"
)
WFS_URL = "https://geoserver.plandata.dk/geoserver/wfs"
CAPABILITIES_URL = (
    f"{WFS_URL}?request=getcapabilities&service=wfs&servicename=wfs"
)
ROBOTS_URL = "https://geoserver.plandata.dk/robots.txt"
INSPIRE_WFS_URL = (
    "https://inspire.plandata.dk/geoserver/ows?service=wfs&version=1.0.0&"
    "request=GetCapabilities"
)

MIN_REQUEST_INTERVAL_SECONDS = 5.0
MAX_CONTROLLED_REQUESTS = 115
PAGE_SIZE = 100
MAX_PAGES_PER_QUERY = 3
MAX_FEATURES = 8_100
MAX_BODY_BYTES = 25 * 1024 * 1024

# Direct local HTTP GETs made while implementing this lane.  Only the final 35
# are hash-bound capture evidence.  Browser/search tooling is excluded because
# it may be cached or proxied and exposes no reliable origin-request count.
TASK_DIRECT_LOCAL_GETS = 67
TASK_PREFLIGHT_GETS = 12
TASK_ABORTED_CAPTURE_GETS = 17
TASK_STATUS_DIAGNOSTIC_GETS = 3
TASK_FROZEN_CAPTURE_GETS = 35

LAYER_SPECS: tuple[dict[str, str], ...] = (
    {
        "layer": "pdk:theme_pdk_lokalplan_forslag",
        "planning_status": "proposal",
        "status_literal": "F",
    },
    {
        "layer": "pdk:theme_pdk_lokalplan_vedtaget",
        "planning_status": "adopted",
        "status_literal": "V",
    },
    {
        "layer": "pdk:theme_pdk_lokalplan_aflyst",
        "planning_status": "cancelled",
        "status_literal": "A",
    },
)
SEARCH_LITERALS = (
    "datacenter",
    "datacentre",
    "datacentret",
    "data center",
    "data centre",
    "servercenter",
    "servercentre",
    "servercentret",
    "serverhal",
)

# These raw DescribeFeatureType hashes were independently observed immediately
# before the controlled capture.  A changed schema must be reviewed explicitly.
EXPECTED_SCHEMA_SHA256 = {
    "pdk:theme_pdk_lokalplan_forslag": (
        "c124e8ec21dc4f786b36b5ef5d8a52222960376f94419145b4168ad52e1ad7ef"
    ),
    "pdk:theme_pdk_lokalplan_vedtaget": (
        "8469abff4157ee238c315c7f4dba06821916e9959205e1b4142ecc9bb0649fca"
    ),
    "pdk:theme_pdk_lokalplan_aflyst": (
        "f209e5903239ea80eba58bddaa93076e0bb7203a6d63aa7c34a451e9055a757d"
    ),
}
EXPECTED_SCHEMA_FIELD_COUNTS = {
    "pdk:theme_pdk_lokalplan_forslag": 326,
    "pdk:theme_pdk_lokalplan_vedtaget": 328,
    "pdk:theme_pdk_lokalplan_aflyst": 327,
}
ROBOTS_404_SHA256 = (
    "533a1ca5d6595793725bca7641d9461a0f00dd1732dded3e4281196f5dd21736"
)

FEATURE_PROPERTIES = (
    "id",
    "planid",
    "komnr",
    "plannr",
    "plannavn",
    "datoforsl",
    "datovedt",
    "datoikraft",
    "datoaflyst",
    "doklink",
    "kommunenavn",
    "status",
    "datoopdt",
)
SCHEMA_CRITICAL_TYPES = {
    "id": "xsd:int",
    "planid": "xsd:int",
    "komnr": "xsd:int",
    "plannr": "xsd:string",
    "plannavn": "xsd:string",
    "datoforsl": "xsd:int",
    "datovedt": "xsd:int",
    "datoikraft": "xsd:int",
    "datoaflyst": "xsd:int",
    "doklink": "xsd:string",
    "kommunenavn": "xsd:string",
    "status": "xsd:string",
    "datoopdt": "xsd:dateTime",
    "megawatt": "xsd:decimal",
    "maxetager": "xsd:decimal",
    "maxbygnhjd": "xsd:decimal",
    "geometri": "gml:MultiSurfacePropertyType",
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "capture-metadata.json",
    "definition.json",
    "observations.jsonl",
    "query-membership.jsonl",
    "query-plan.json",
    "schema.json",
    "source-inventory.json",
}
EXPECTED_FILES = DERIVED_FILENAMES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, WFS_URL)


class DenmarkPlandataError(ValueError):
    """Raised when the bounded assessment fails its closed contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(dict(row)) for row in rows)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _strict_json(body: bytes, *, label: str) -> Any:
    if not isinstance(body, bytes) or len(body) > MAX_BODY_BYTES:
        raise DenmarkPlandataError(f"{label} is not bounded bytes")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DenmarkPlandataError(f"{label} is not UTF-8") from error

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DenmarkPlandataError(
                    f"{label} contains duplicate JSON key {key}"
                )
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
    except json.JSONDecodeError as error:
        raise DenmarkPlandataError(f"{label} is invalid JSON") from error


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DenmarkPlandataError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DenmarkPlandataError(f"{label} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DenmarkPlandataError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _official_url(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise DenmarkPlandataError(f"{label} must be a URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.fragment
        or parsed.hostname
        not in {
            "datavejviser.dk",
            "geoserver.plandata.dk",
            "inspire.plandata.dk",
            "www.plandata.dk",
        }
    ):
        raise DenmarkPlandataError(f"{label} is outside the official hosts")
    return value


def describe_feature_type_url(layer: str) -> str:
    if layer not in {row["layer"] for row in LAYER_SPECS}:
        raise DenmarkPlandataError("layer is outside the closed plan")
    parameters = (
        ("service", "WFS"),
        ("version", "2.0.0"),
        ("request", "DescribeFeatureType"),
        ("typeNames", layer),
    )
    return f"{WFS_URL}?{urlencode(parameters, quote_via=quote)}"


def property_is_like_filter(literal: str) -> str:
    if literal not in SEARCH_LITERALS:
        raise DenmarkPlandataError("literal is outside the closed plan")
    return (
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
        '<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!" '
        'matchCase="false"><fes:ValueReference>plannavn</fes:ValueReference>'
        f"<fes:Literal>*{literal}*</fes:Literal>"
        "</fes:PropertyIsLike></fes:Filter>"
    )


def hits_url(layer: str, literal: str) -> str:
    if layer not in {row["layer"] for row in LAYER_SPECS}:
        raise DenmarkPlandataError("layer is outside the closed plan")
    parameters = (
        ("service", "WFS"),
        ("version", "2.0.0"),
        ("request", "GetFeature"),
        ("typeNames", layer),
        ("resultType", "hits"),
        ("filter", property_is_like_filter(literal)),
    )
    return f"{WFS_URL}?{urlencode(parameters, quote_via=quote)}"


def feature_page_url(layer: str, literal: str, *, page: int) -> str:
    if layer not in {row["layer"] for row in LAYER_SPECS}:
        raise DenmarkPlandataError("layer is outside the closed plan")
    if not 1 <= page <= MAX_PAGES_PER_QUERY:
        raise DenmarkPlandataError("page is outside the bounded plan")
    parameters = (
        ("service", "WFS"),
        ("version", "2.0.0"),
        ("request", "GetFeature"),
        ("typeNames", layer),
        ("outputFormat", "application/json"),
        ("srsName", "EPSG:4326"),
        ("count", str(PAGE_SIZE)),
        ("startIndex", str((page - 1) * PAGE_SIZE)),
        ("sortBy", "id A"),
        ("propertyName", ",".join((*FEATURE_PROPERTIES, "geometri"))),
        ("filter", property_is_like_filter(literal)),
    )
    return f"{WFS_URL}?{urlencode(parameters, quote_via=quote)}"


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    index = 0
    for layer_spec in LAYER_SPECS:
        for literal in SEARCH_LITERALS:
            index += 1
            rows.append(
                {
                    "case_sensitive": False,
                    "field": "plannavn",
                    "hits_url": hits_url(layer_spec["layer"], literal),
                    "layer": layer_spec["layer"],
                    "literal": literal,
                    "maximum_features": PAGE_SIZE * MAX_PAGES_PER_QUERY,
                    "maximum_pages": MAX_PAGES_PER_QUERY,
                    "ogc_operator": "PropertyIsLike",
                    "planning_status": layer_spec["planning_status"],
                    "query_id": f"q{index:02d}",
                    "wildcard_mode": "contains",
                }
            )
    return {
        "closed": True,
        "field": "plannavn",
        "format": "datacenter-atlas-denmark-plandata-query-plan-v1",
        "global_feature_cap": MAX_FEATURES,
        "layer_count": len(LAYER_SPECS),
        "literal_count": len(SEARCH_LITERALS),
        "query_count": len(rows),
        "rows": rows,
    }


def _literal(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("@value"), str):
        return value["@value"]
    return None


def validate_license_jsonld(body: bytes) -> dict[str, Any]:
    value = _strict_json(body, label="licence JSON-LD")
    if not isinstance(value, dict) or not isinstance(value.get("@graph"), list):
        raise DenmarkPlandataError("licence JSON-LD graph changed")
    graph = value["@graph"]
    nodes = {
        row.get("@id"): row
        for row in graph
        if isinstance(row, dict) and isinstance(row.get("@id"), str)
    }
    datasets = [
        row
        for row in graph
        if isinstance(row, dict) and _literal(row.get("dct:title")) == DATASET_TITLE
    ]
    if len(datasets) != 1:
        raise DenmarkPlandataError("exact local-plan dataset identity changed")
    dataset = datasets[0]
    licence = dataset.get("dct:license")
    if not isinstance(licence, dict) or licence.get("@id") != LICENSE_URI:
        raise DenmarkPlandataError("dataset licence URI changed")
    refs = dataset.get("dcat:distribution")
    if not isinstance(refs, list) or len(refs) != 4:
        raise DenmarkPlandataError("dataset distribution inventory changed")
    access_urls: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict) or not isinstance(ref.get("@id"), str):
            raise DenmarkPlandataError("distribution reference changed")
        node = nodes.get(ref["@id"])
        if not isinstance(node, dict):
            raise DenmarkPlandataError("distribution node is missing")
        node_licence = node.get("dct:license")
        if (
            not isinstance(node_licence, dict)
            or node_licence.get("@id") != LICENSE_URI
        ):
            raise DenmarkPlandataError("distribution licence URI changed")
        access = node.get("dcat:accessURL")
        if not isinstance(access, dict) or not isinstance(access.get("@id"), str):
            raise DenmarkPlandataError("distribution access URL changed")
        access_urls.append(access["@id"])
    if INSPIRE_WFS_URL not in access_urls:
        raise DenmarkPlandataError("catalogued WFS distribution changed")

    publisher_names: set[str] = set()
    publisher_refs = dataset.get("dct:publisher")
    if not isinstance(publisher_refs, list):
        raise DenmarkPlandataError("dataset publisher references changed")
    for ref in publisher_refs:
        if not isinstance(ref, dict) or not isinstance(ref.get("@id"), str):
            raise DenmarkPlandataError("dataset publisher reference changed")
        node = nodes.get(ref["@id"])
        if not isinstance(node, dict):
            continue
        for key in ("foaf:name", "rdfs:label", "dct:title"):
            candidate = _literal(node.get(key))
            if candidate:
                publisher_names.add(candidate)
    if "Plan- og Landdistriktsstyrelsen" not in publisher_names:
        raise DenmarkPlandataError("official publisher identity changed")
    return {
        "catalogued_wfs_access_url": INSPIRE_WFS_URL,
        "dataset_title": DATASET_TITLE,
        "distribution_count": 4,
        "distribution_licence_uris": [LICENSE_URI],
        "licence_uri": LICENSE_URI,
        "publisher_names": sorted(publisher_names),
    }


def _xml_root(body: bytes, *, label: str) -> ET.Element:
    if not isinstance(body, bytes) or not body or len(body) > MAX_BODY_BYTES:
        raise DenmarkPlandataError(f"{label} is not bounded XML bytes")
    prefix = body[:2048].lower()
    if b"<html" in prefix or b"<!doctype" in prefix or b"<!entity" in prefix:
        raise DenmarkPlandataError(f"{label} is HTML or unsafe XML")
    try:
        return ET.fromstring(body)
    except ET.ParseError as error:
        raise DenmarkPlandataError(f"{label} is invalid XML") from error


def validate_capabilities_xml(body: bytes) -> dict[str, Any]:
    root = _xml_root(body, label="GetCapabilities")
    wfs = "{http://www.opengis.net/wfs/2.0}"
    ows = "{http://www.opengis.net/ows/1.1}"
    if root.tag != f"{wfs}WFS_Capabilities" or root.get("version") != "2.0.0":
        raise DenmarkPlandataError("WFS capabilities identity changed")
    names = {
        node.text
        for node in root.findall(f".//{wfs}FeatureType/{wfs}Name")
        if node.text
    }
    required_layers = {row["layer"] for row in LAYER_SPECS}
    if not required_layers <= names:
        raise DenmarkPlandataError("required local-plan layers disappeared")
    operations = {
        node.get("name")
        for node in root.findall(f".//{ows}Operation")
        if node.get("name")
    }
    if not {"DescribeFeatureType", "GetFeature"} <= operations:
        raise DenmarkPlandataError("required WFS operations disappeared")
    constraints: dict[str, str] = {}
    for node in root.findall(f".//{ows}Constraint"):
        name = node.get("name")
        default = node.find(f"{ows}DefaultValue")
        if name and default is not None and default.text:
            constraints[name] = default.text.strip()
    if constraints.get("ImplementsResultPaging") != "TRUE":
        raise DenmarkPlandataError("WFS result paging support changed")
    if constraints.get("CountDefault") != "1000000":
        raise DenmarkPlandataError("WFS documented default count changed")
    values = {
        node.text.strip()
        for node in root.findall(f".//{ows}Value")
        if node.text and node.text.strip()
    }
    if "application/json" not in values:
        raise DenmarkPlandataError("GeoJSON output support disappeared")
    title = root.find(f".//{ows}ServiceIdentification/{ows}Title")
    if title is None or not title.text or "Plandata" not in title.text:
        raise DenmarkPlandataError("WFS service title changed")
    return {
        "count_default": 1_000_000,
        "feature_type_count": len(names),
        "implements_result_paging": True,
        "required_layers_present": sorted(required_layers),
        "service_title": title.text.strip(),
        "update_sequence": root.get("updateSequence"),
        "version": "2.0.0",
    }


def validate_schema_xml(
    layer: str, body: bytes, *, enforce_pinned_hash: bool = True
) -> dict[str, Any]:
    if layer not in EXPECTED_SCHEMA_SHA256:
        raise DenmarkPlandataError("schema layer is outside the closed plan")
    raw_hash = sha256_bytes(body)
    if enforce_pinned_hash and raw_hash != EXPECTED_SCHEMA_SHA256[layer]:
        raise DenmarkPlandataError(f"DescribeFeatureType drift for {layer}")
    root = _xml_root(body, label=f"DescribeFeatureType {layer}")
    xs = "{http://www.w3.org/2001/XMLSchema}"
    if root.tag != f"{xs}schema" or root.get("targetNamespace") != (
        "http://www.plansystemdk.dk"
    ):
        raise DenmarkPlandataError("DescribeFeatureType namespace changed")
    local = layer.split(":", 1)[1]
    complex_type = root.find(f".//{xs}complexType[@name='{local}Type']")
    if complex_type is None:
        raise DenmarkPlandataError("layer complex type changed")
    sequence = complex_type.find(f".//{xs}sequence")
    if sequence is None:
        raise DenmarkPlandataError("layer schema sequence disappeared")
    fields: list[dict[str, Any]] = []
    for node in sequence.findall(f"{xs}element"):
        fields.append(
            {
                "max_occurs": node.get("maxOccurs"),
                "min_occurs": node.get("minOccurs"),
                "name": node.get("name"),
                "nillable": node.get("nillable"),
                "type": node.get("type"),
            }
        )
    if len(fields) != EXPECTED_SCHEMA_FIELD_COUNTS[layer]:
        raise DenmarkPlandataError("layer schema field count changed")
    if len({row["name"] for row in fields}) != len(fields):
        raise DenmarkPlandataError("layer schema contains duplicate fields")
    by_name = {row["name"]: row for row in fields}
    for name, expected_type in SCHEMA_CRITICAL_TYPES.items():
        row = by_name.get(name)
        if row != {
            "max_occurs": "1",
            "min_occurs": "0",
            "name": name,
            "nillable": "true",
            "type": expected_type,
        }:
            raise DenmarkPlandataError(f"critical schema field changed: {name}")
    return {
        "critical_fields": {
            name: by_name[name] for name in sorted(SCHEMA_CRITICAL_TYPES)
        },
        "field_count": len(fields),
        "field_sequence_sha256": sha256_bytes(canonical_json(fields)),
        "layer": layer,
        "raw_sha256": raw_hash,
        "target_namespace": root.get("targetNamespace"),
    }


def parse_hits_xml(body: bytes) -> dict[str, Any]:
    root = _xml_root(body, label="GetFeature hits")
    if root.tag != "{http://www.opengis.net/wfs/2.0}FeatureCollection":
        raise DenmarkPlandataError("hits response is not a WFS FeatureCollection")
    matched = root.get("numberMatched")
    returned = root.get("numberReturned")
    if not isinstance(matched, str) or not matched.isdigit():
        raise DenmarkPlandataError("hits numberMatched is not an integer")
    if returned != "0":
        raise DenmarkPlandataError("hits response unexpectedly returned features")
    timestamp = root.get("timeStamp")
    _parse_timestamp(timestamp, label="hits timeStamp")
    return {
        "number_matched": int(matched),
        "number_returned": 0,
        "server_timestamp": timestamp,
    }


def _validate_geometry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"coordinates", "type"}:
        raise DenmarkPlandataError("feature geometry schema changed")
    if value["type"] not in {"Polygon", "MultiPolygon"}:
        raise DenmarkPlandataError("feature geometry type changed")
    coordinate_count = 0

    def visit(node: Any) -> None:
        nonlocal coordinate_count
        if (
            isinstance(node, list)
            and len(node) >= 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in node[:2])
        ):
            longitude = float(node[0])
            latitude = float(node[1])
            if not (math.isfinite(longitude) and math.isfinite(latitude)):
                raise DenmarkPlandataError("feature geometry is not finite")
            if not (7.0 <= longitude <= 16.0 and 54.0 <= latitude <= 58.5):
                raise DenmarkPlandataError("feature geometry is outside Denmark")
            coordinate_count += 1
            return
        if not isinstance(node, list) or not node:
            raise DenmarkPlandataError("feature geometry coordinates changed")
        for child in node:
            visit(child)

    visit(value["coordinates"])
    if coordinate_count < 4:
        raise DenmarkPlandataError("feature geometry has too few coordinates")
    return value


def _validate_projected_feature(
    feature: Any, *, layer_spec: Mapping[str, str], literal: str
) -> dict[str, Any]:
    if not isinstance(feature, dict) or set(feature) != {
        "feature_id",
        "geometry",
        "properties",
    }:
        raise DenmarkPlandataError("captured feature schema changed")
    feature_id = feature.get("feature_id")
    properties = feature.get("properties")
    if not isinstance(feature_id, str) or not feature_id:
        raise DenmarkPlandataError("captured feature id changed")
    if not isinstance(properties, dict) or set(properties) != set(FEATURE_PROPERTIES):
        raise DenmarkPlandataError("captured projected properties changed")
    name = properties.get("plannavn")
    if not isinstance(name, str) or literal.casefold() not in name.casefold():
        raise DenmarkPlandataError("captured feature violates exact name filter")
    if properties.get("status") != layer_spec["status_literal"]:
        raise DenmarkPlandataError("captured status disagrees with status layer")
    for field in ("id", "planid", "komnr"):
        if isinstance(properties.get(field), bool) or not isinstance(
            properties.get(field), int
        ):
            raise DenmarkPlandataError(f"captured source integer changed: {field}")
    expected_prefix = f"{layer_spec['layer'].split(':', 1)[1]}."
    if feature_id != f"{expected_prefix}{properties['id']}":
        raise DenmarkPlandataError("captured feature id and source id disagree")
    for field in ("plannr", "doklink", "kommunenavn"):
        if properties.get(field) is not None and not isinstance(
            properties.get(field), str
        ):
            raise DenmarkPlandataError(f"captured source text changed: {field}")
    for field in ("datoforsl", "datovedt", "datoikraft", "datoaflyst"):
        field_value = properties.get(field)
        if field_value is not None and (
            isinstance(field_value, bool) or not isinstance(field_value, int)
        ):
            raise DenmarkPlandataError(f"captured source date changed: {field}")
    updated = properties.get("datoopdt")
    if updated is not None:
        _parse_timestamp(updated, label="captured datoopdt")
    _validate_geometry(feature.get("geometry"))
    return feature


def parse_feature_page(
    body: bytes, *, layer_spec: Mapping[str, str], literal: str, matched: int
) -> dict[str, Any]:
    value = _strict_json(body, label="GetFeature page")
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise DenmarkPlandataError("GetFeature page is not GeoJSON")
    features = value.get("features")
    if not isinstance(features, list) or len(features) > PAGE_SIZE:
        raise DenmarkPlandataError("GetFeature page feature count changed")
    if value.get("numberReturned") != len(features):
        raise DenmarkPlandataError("GetFeature numberReturned disagrees")
    if value.get("numberMatched") != matched:
        raise DenmarkPlandataError("GetFeature numberMatched drifted during paging")
    rows: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise DenmarkPlandataError("GeoJSON feature schema changed")
        feature_id = feature.get("id")
        properties = feature.get("properties")
        if not isinstance(feature_id, str) or not feature_id:
            raise DenmarkPlandataError("GeoJSON feature id changed")
        if not isinstance(properties, dict) or set(properties) != set(
            FEATURE_PROPERTIES
        ):
            raise DenmarkPlandataError("GeoJSON projected properties changed")
        projected = {
            "feature_id": feature_id,
            "geometry": feature.get("geometry"),
            "properties": {key: properties[key] for key in FEATURE_PROPERTIES},
        }
        rows.append(
            _validate_projected_feature(
                projected, layer_spec=layer_spec, literal=literal
            )
        )
    if len({row["feature_id"] for row in rows}) != len(rows):
        raise DenmarkPlandataError("page contains duplicate feature ids")
    return {
        "features": rows,
        "number_matched": matched,
        "number_returned": len(rows),
        "server_timestamp": value.get("timeStamp"),
    }


def source_definition() -> dict[str, Any]:
    return {
        "coverage_contract": {
            "attached_document_text_searched": False,
            "complete_for_denmark_claimed": False,
            "geometry_is_facility_footprint": False,
            "national_data_centre_completeness_claimed": False,
            "scope": (
                "case-insensitive contains matches in plannavn on three current "
                "Plandata.dk local-plan status layers"
            ),
            "unique_physical_site_count": None,
        },
        "downstream_import_policy": {
            "construction_map_import_permitted": False,
            "construction_master_import_permitted": False,
            "current_coverage_ledger_import_permitted": False,
            "reason": "planning-name matches require source-document and physical review",
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_consumption_mwh": None,
            "automatic_identity_merge_permitted": False,
            "construction_status": None,
            "data_centre_type": None,
            "gross_facility_power_mw": None,
            "identity": None,
            "it_capacity_mw": None,
            "megawatt_field_converted": False,
            "operator": None,
            "planning_maxima_are_observed_actuals": False,
            "planning_status_is_physical_lifecycle": False,
            "pue": None,
            "workload": None,
        },
        "network_policy": {
            "maximum_controlled_requests": MAX_CONTROLLED_REQUESTS,
            "maximum_features": MAX_FEATURES,
            "maximum_pages_per_positive_query": MAX_PAGES_PER_QUERY,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "page_size": PAGE_SIZE,
            "retry_attempts": 0,
            "stop_on_error_html_or_pagination_inconsistency": True,
        },
        "publisher": PUBLISHER,
        "query_contract": {
            "case_sensitive": False,
            "field": "plannavn",
            "layers": [row["layer"] for row in LAYER_SPECS],
            "literals": list(SEARCH_LITERALS),
            "ogc_operator": "PropertyIsLike",
            "query_count": 27,
            "query_plan_file": "query-plan.json",
            "wildcard_mode": "contains",
        },
        "release_id": RELEASE_ID,
        "retention": {
            "document_requests": 0,
            "pdf_requests": 0,
            "projected_feature_metadata_retained": True,
            "raw_response_bodies_retained": False,
        },
        "rights": {
            "attribution": PUBLISHER,
            "catalogued_dataset_and_distribution_licence_uri": LICENSE_URI,
            "catalogued_licence_human_url": CC_BY_4_URL,
            "licence_scope_extended_to_linked_documents": False,
            "legal_conclusion_claimed": False,
            "official_alternative_wfs_endpoint_same_dataset_inferred": True,
            "robots_absence_is_permission": False,
            "verified_local_date": ASSESSMENT_DATE.isoformat(),
        },
        "schema_version": SCHEMA_VERSION,
        "source_urls": {
            "data_model": DATA_MODEL_URL,
            "dataset_record": DATASET_URL,
            "licence_jsonld": LICENSE_JSONLD_URL,
            "wfs": WFS_URL,
            "wfs_intro": WFS_INTRO_URL,
        },
        "unit_contract": {
            "adopted_or_effective_plan_is_construction": False,
            "cancelled_layer_is_negative_planning_evidence": True,
            "feature_is_unique_physical_site": False,
            "proposal_is_construction": False,
            "source_unit": "status-layer local-plan feature",
        },
    }


def _request_metadata(
    value: Any,
    *,
    request_id: str,
    url: str,
    status: int = 200,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DenmarkPlandataError(f"request metadata changed: {request_id}")
    required = {
        "body_retained",
        "bytes",
        "completed_at",
        "content_type",
        "http_status",
        "media_type",
        "method",
        "redirect_count",
        "request_id",
        "requested_at",
        "response_date",
        "sha256",
        "url",
    }
    if set(value) != required:
        raise DenmarkPlandataError(f"request metadata schema changed: {request_id}")
    _official_url(value.get("url"), label=f"{request_id}.url")
    _parse_timestamp(value.get("requested_at"), label=f"{request_id}.requested_at")
    _parse_timestamp(value.get("completed_at"), label=f"{request_id}.completed_at")
    if value.get("response_date") is not None:
        _parse_timestamp(value["response_date"], label=f"{request_id}.response_date")
    if (
        value.get("request_id") != request_id
        or value.get("url") != url
        or value.get("http_status") != status
        or value.get("method") != "GET"
        or value.get("redirect_count") != 0
        or value.get("body_retained") is not False
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] < 1
        or not _SHA256_RE.fullmatch(str(value.get("sha256", "")))
        or not isinstance(value.get("content_type"), str)
        or not isinstance(value.get("media_type"), str)
    ):
        raise DenmarkPlandataError(f"request metadata invalid: {request_id}")
    return value


def validate_capture(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "capture_window",
        "control",
        "controlled_request_count",
        "detail_requests",
        "document_requests",
        "feature_rows_retrieved",
        "format",
        "layers",
        "login_or_captcha_requests",
        "maximum_controlled_requests",
        "maximum_features",
        "minimum_request_interval_seconds",
        "pdf_requests",
        "raw_response_bodies_retained",
        "release_id",
        "schema_version",
    }:
        raise DenmarkPlandataError("capture envelope schema changed")
    if (
        value["format"] != CAPTURE_FORMAT
        or value["release_id"] != RELEASE_ID
        or value["schema_version"] != SCHEMA_VERSION
        or value["minimum_request_interval_seconds"]
        < MIN_REQUEST_INTERVAL_SECONDS
        or value["maximum_controlled_requests"] != MAX_CONTROLLED_REQUESTS
        or value["maximum_features"] != MAX_FEATURES
        or value["raw_response_bodies_retained"] is not False
        or any(
            value[field] != 0
            for field in (
                "detail_requests",
                "document_requests",
                "login_or_captcha_requests",
                "pdf_requests",
            )
        )
    ):
        raise DenmarkPlandataError("capture contract changed")
    window = value["capture_window"]
    if not isinstance(window, dict) or set(window) != {
        "closed",
        "completed_at",
        "started_at",
    } or window["closed"] is not True:
        raise DenmarkPlandataError("capture window is not closed")
    started = _parse_timestamp(window["started_at"], label="capture started_at")
    completed = _parse_timestamp(window["completed_at"], label="capture completed_at")
    if completed < started:
        raise DenmarkPlandataError("capture window is reversed")

    control = value["control"]
    if not isinstance(control, dict) or set(control) != {
        "capabilities",
        "licence_jsonld",
        "robots",
        "schemas",
    }:
        raise DenmarkPlandataError("control evidence schema changed")
    licence = control["licence_jsonld"]
    if not isinstance(licence, dict) or set(licence) != {"request", "summary"}:
        raise DenmarkPlandataError("licence control changed")
    _request_metadata(
        licence["request"],
        request_id="licence-jsonld",
        url=LICENSE_JSONLD_URL,
    )
    licence_summary = licence["summary"]
    if not isinstance(licence_summary, dict) or set(licence_summary) != {
        "catalogued_wfs_access_url",
        "dataset_title",
        "distribution_count",
        "distribution_licence_uris",
        "licence_uri",
        "publisher_names",
    }:
        raise DenmarkPlandataError("licence evidence summary changed")
    if licence["request"]["media_type"] != "application/ld+json" or licence_summary.get(
        "licence_uri"
    ) != LICENSE_URI:
        raise DenmarkPlandataError("licence evidence changed")
    if (
        licence_summary.get("distribution_count") != 4
        or licence_summary.get("dataset_title") != DATASET_TITLE
        or licence_summary.get("catalogued_wfs_access_url") != INSPIRE_WFS_URL
        or licence_summary.get("distribution_licence_uris") != [LICENSE_URI]
        or "Plan- og Landdistriktsstyrelsen"
        not in licence_summary.get("publisher_names", [])
    ):
        raise DenmarkPlandataError("licence distribution count changed")

    robots = control["robots"]
    if not isinstance(robots, dict) or set(robots) != {"request", "summary"}:
        raise DenmarkPlandataError("robots control changed")
    _request_metadata(
        robots["request"], request_id="robots", url=ROBOTS_URL, status=404
    )
    if (
        robots["request"]["media_type"] != "text/html"
        or robots["request"]["sha256"] != ROBOTS_404_SHA256
        or robots["summary"]
        != {
            "robots_rule_published": False,
            "robots_rule_is_reuse_permission": False,
        }
    ):
        raise DenmarkPlandataError("robots 404 evidence changed")

    capabilities = control["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "request",
        "summary",
    }:
        raise DenmarkPlandataError("capabilities control changed")
    _request_metadata(
        capabilities["request"],
        request_id="wfs-capabilities",
        url=CAPABILITIES_URL,
    )
    if capabilities["request"]["media_type"] != "application/xml":
        raise DenmarkPlandataError("capabilities content type changed")
    capability_summary = capabilities["summary"]
    if not isinstance(capability_summary, dict) or set(capability_summary) != {
        "count_default",
        "feature_type_count",
        "implements_result_paging",
        "required_layers_present",
        "service_title",
        "update_sequence",
        "version",
    }:
        raise DenmarkPlandataError("capabilities summary schema changed")
    if capability_summary.get("required_layers_present") != sorted(
        row["layer"] for row in LAYER_SPECS
    ) or capability_summary.get("implements_result_paging") is not True:
        raise DenmarkPlandataError("capabilities summary changed")
    if (
        capability_summary.get("count_default") != 1_000_000
        or capability_summary.get("version") != "2.0.0"
        or not isinstance(capability_summary.get("feature_type_count"), int)
        or capability_summary["feature_type_count"] < 3
        or not isinstance(capability_summary.get("service_title"), str)
        or "Plandata" not in capability_summary["service_title"]
    ):
        raise DenmarkPlandataError("capabilities semantic summary changed")

    schemas = control["schemas"]
    if not isinstance(schemas, list) or len(schemas) != len(LAYER_SPECS):
        raise DenmarkPlandataError("schema control inventory changed")
    for index, (schema, layer_spec) in enumerate(zip(schemas, LAYER_SPECS, strict=True)):
        layer = layer_spec["layer"]
        if not isinstance(schema, dict) or set(schema) != {
            "request",
            "summary",
        }:
            raise DenmarkPlandataError("schema control row changed")
        _request_metadata(
            schema["request"],
            request_id=f"schema-{index + 1:02d}",
            url=describe_feature_type_url(layer),
        )
        summary = schema["summary"]
        if (
            schema["request"]["media_type"] != "application/gml+xml"
            or summary.get("layer") != layer
            or summary.get("raw_sha256") != EXPECTED_SCHEMA_SHA256[layer]
            or summary.get("field_count") != EXPECTED_SCHEMA_FIELD_COUNTS[layer]
            or summary.get("target_namespace") != "http://www.plansystemdk.dk"
            or not _SHA256_RE.fullmatch(
                str(summary.get("field_sequence_sha256", ""))
            )
        ):
            raise DenmarkPlandataError("pinned schema evidence changed")
        critical = summary.get("critical_fields")
        if not isinstance(critical, dict) or set(critical) != set(
            SCHEMA_CRITICAL_TYPES
        ):
            raise DenmarkPlandataError("critical schema summary changed")
        for field, field_type in SCHEMA_CRITICAL_TYPES.items():
            if critical[field] != {
                "max_occurs": "1",
                "min_occurs": "0",
                "name": field,
                "nillable": "true",
                "type": field_type,
            }:
                raise DenmarkPlandataError("critical schema field summary changed")

    layers = value["layers"]
    if not isinstance(layers, list) or len(layers) != len(LAYER_SPECS):
        raise DenmarkPlandataError("captured layer inventory changed")
    plan_rows = query_plan()["rows"]
    expected_queries = iter(plan_rows)
    request_count = 6
    feature_count = 0
    request_starts: list[datetime] = []
    control_requests = [
        licence["request"],
        robots["request"],
        capabilities["request"],
        *(schema["request"] for schema in schemas),
    ]
    request_starts.extend(
        _parse_timestamp(row["requested_at"], label="request start")
        for row in control_requests
    )
    for layer_capture, layer_spec in zip(layers, LAYER_SPECS, strict=True):
        if not isinstance(layer_capture, dict) or set(layer_capture) != {
            "layer",
            "planning_status",
            "queries",
        }:
            raise DenmarkPlandataError("captured layer row changed")
        if (
            layer_capture["layer"] != layer_spec["layer"]
            or layer_capture["planning_status"] != layer_spec["planning_status"]
            or not isinstance(layer_capture["queries"], list)
            or len(layer_capture["queries"]) != len(SEARCH_LITERALS)
        ):
            raise DenmarkPlandataError("captured layer identity changed")
        for query in layer_capture["queries"]:
            expected = next(expected_queries)
            if not isinstance(query, dict) or set(query) != {
                "captured_feature_count",
                "complete",
                "hits",
                "hits_request",
                "layer",
                "literal",
                "pages",
                "query_id",
                "truncated",
            }:
                raise DenmarkPlandataError("captured query schema changed")
            if any(query[key] != expected[key] for key in ("layer", "literal", "query_id")):
                raise DenmarkPlandataError("captured query differs from closed plan")
            _request_metadata(
                query["hits_request"],
                request_id=f"{expected['query_id']}-hits",
                url=expected["hits_url"],
            )
            request_starts.append(
                _parse_timestamp(
                    query["hits_request"]["requested_at"],
                    label="hits request start",
                )
            )
            if query["hits_request"]["media_type"] not in {
                "application/xml",
                "text/xml",
            }:
                raise DenmarkPlandataError("hits response content type changed")
            hits = query["hits"]
            if not isinstance(hits, dict) or set(hits) != {
                "number_matched",
                "number_returned",
                "server_timestamp",
            } or hits["number_returned"] != 0:
                raise DenmarkPlandataError("hits summary changed")
            matched = hits["number_matched"]
            if isinstance(matched, bool) or not isinstance(matched, int) or matched < 0:
                raise DenmarkPlandataError("hits count is invalid")
            _parse_timestamp(hits["server_timestamp"], label="hits server timestamp")
            pages = query["pages"]
            if not isinstance(pages, list):
                raise DenmarkPlandataError("query pages changed")
            expected_page_count = min(
                math.ceil(matched / PAGE_SIZE), MAX_PAGES_PER_QUERY
            )
            if len(pages) != expected_page_count:
                raise DenmarkPlandataError("query pagination count is inconsistent")
            query_features: list[dict[str, Any]] = []
            for page_number, page in enumerate(pages, 1):
                if not isinstance(page, dict) or set(page) != {
                    "features",
                    "number_matched",
                    "number_returned",
                    "page",
                    "request",
                    "server_timestamp",
                    "start_index",
                }:
                    raise DenmarkPlandataError("page capture schema changed")
                _request_metadata(
                    page["request"],
                    request_id=f"{expected['query_id']}-page-{page_number:02d}",
                    url=feature_page_url(
                        expected["layer"], expected["literal"], page=page_number
                    ),
                )
                if page["request"]["media_type"] != "application/json":
                    raise DenmarkPlandataError("page content type changed")
                if (
                    page["page"] != page_number
                    or page["start_index"] != (page_number - 1) * PAGE_SIZE
                    or page["number_matched"] != matched
                    or page["number_returned"] != len(page["features"])
                    or not 1 <= len(page["features"]) <= PAGE_SIZE
                ):
                    raise DenmarkPlandataError("page arithmetic is inconsistent")
                if page_number < expected_page_count and len(page["features"]) != PAGE_SIZE:
                    raise DenmarkPlandataError("non-final page is short")
                if page["server_timestamp"] is not None:
                    _parse_timestamp(
                        page["server_timestamp"], label="page server timestamp"
                    )
                for feature in page["features"]:
                    _validate_projected_feature(
                        feature, layer_spec=layer_spec, literal=expected["literal"]
                    )
                query_features.extend(page["features"])
                request_starts.append(
                    _parse_timestamp(
                        page["request"]["requested_at"], label="page request start"
                    )
                )
            if len({row["feature_id"] for row in query_features}) != len(query_features):
                raise DenmarkPlandataError("query pagination repeated a feature")
            expected_captured = min(matched, PAGE_SIZE * MAX_PAGES_PER_QUERY)
            if (
                len(query_features) != expected_captured
                or query["captured_feature_count"] != expected_captured
                or query["complete"] is not (matched <= expected_captured)
                or query["truncated"] is not (matched > expected_captured)
            ):
                raise DenmarkPlandataError("query completeness arithmetic changed")
            request_count += 1 + len(pages)
            feature_count += len(query_features)
    try:
        next(expected_queries)
    except StopIteration:
        pass
    else:
        raise DenmarkPlandataError("not all closed queries were captured")
    if request_count > MAX_CONTROLLED_REQUESTS or feature_count > MAX_FEATURES:
        raise DenmarkPlandataError("global capture cap exceeded")
    if (
        value["controlled_request_count"] != request_count
        or value["feature_rows_retrieved"] != feature_count
    ):
        raise DenmarkPlandataError("global capture arithmetic changed")
    for earlier, later in zip(request_starts, request_starts[1:], strict=False):
        if (later - earlier).total_seconds() < MIN_REQUEST_INTERVAL_SECONDS:
            raise DenmarkPlandataError("controlled requests were not paced by five seconds")
    return value


def _observation_id(layer: str, feature_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{layer}|{feature_id}"))


def derive_observations(capture: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_capture(dict(capture))
    if any(
        query["truncated"]
        for layer in capture["layers"]
        for query in layer["queries"]
    ):
        return [], []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    memberships: dict[tuple[str, str], list[dict[str, str]]] = {}
    status_by_layer = {row["layer"]: row for row in LAYER_SPECS}
    for layer in capture["layers"]:
        for query in layer["queries"]:
            for page in query["pages"]:
                for feature in page["features"]:
                    key = (layer["layer"], feature["feature_id"])
                    prior = by_key.setdefault(key, feature)
                    if prior != feature:
                        raise DenmarkPlandataError("feature changed across exact queries")
                    memberships.setdefault(key, []).append(
                        {
                            "literal": query["literal"],
                            "query_id": query["query_id"],
                        }
                    )
    observations: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    for (layer_name, feature_id), feature in sorted(by_key.items()):
        layer_spec = status_by_layer[layer_name]
        props = feature["properties"]
        observation_id = _observation_id(layer_name, feature_id)
        exact_memberships = sorted(
            memberships[(layer_name, feature_id)], key=lambda row: row["query_id"]
        )
        for membership in exact_memberships:
            membership_rows.append(
                {
                    "literal": membership["literal"],
                    "observation_id": observation_id,
                    "query_id": membership["query_id"],
                    "source_feature_id": feature_id,
                    "source_layer": layer_name,
                }
            )
        cancelled = layer_spec["planning_status"] == "cancelled"
        observations.append(
            {
                "annual_energy_consumption_mwh": None,
                "atlas_identity": None,
                "cancelled_planning_negative": cancelled,
                "construction_status": None,
                "data_centre_type": None,
                "document_link_present": bool(props["doklink"]),
                "document_requested": False,
                "facility_coordinates": None,
                "format": OBSERVATION_FORMAT,
                "gross_facility_power_mw": None,
                "it_capacity_mw": None,
                "matched_literals": sorted(
                    {row["literal"] for row in exact_memberships}
                ),
                "municipality_code": props["komnr"],
                "municipality_name": props["kommunenavn"],
                "observation_id": observation_id,
                "operator": None,
                "physical_lifecycle_inferred": False,
                "plan_dates_raw": {
                    "adopted": props["datovedt"],
                    "cancelled": props["datoaflyst"],
                    "effective": props["datoikraft"],
                    "proposal": props["datoforsl"],
                    "updated": props["datoopdt"],
                },
                "plan_id": props["planid"],
                "plan_name_raw": props["plannavn"],
                "plan_number_raw": props["plannr"],
                "planning_area_geometry": feature["geometry"],
                "planning_maxima_captured": False,
                "planning_maxima_are_observed_actuals": False,
                "planning_status": layer_spec["planning_status"],
                "planning_status_is_construction": False,
                "planning_status_raw": props["status"],
                "pue": None,
                "review_only": True,
                "source_feature_id": feature_id,
                "source_layer": layer_name,
                "source_megawatt_captured": False,
                "source_megawatt_is_capacity_or_consumption": False,
                "source_record_unit": "status-layer local-plan feature",
                "source_tier": "C",
                "source_url": WFS_URL,
                "workload": None,
            }
        )
    return observations, sorted(
        membership_rows,
        key=lambda row: (row["query_id"], row["source_feature_id"]),
    )


def assessment_document(capture: Mapping[str, Any]) -> dict[str, Any]:
    observations, memberships = derive_observations(capture)
    queries = [
        query for layer in capture["layers"] for query in layer["queries"]
    ]
    truncated = any(query["truncated"] for query in queries)
    status_counts = Counter(row["planning_status"] for row in observations)
    return {
        "assessed_at": capture["capture_window"]["completed_at"],
        "atlas_decision": {
            **source_definition()["downstream_import_policy"],
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            "retained_source_rows": len(observations),
            "status": (
                "bounded_query_truncated_metadata_only"
                if truncated
                else "complete_closed_query_review_assessment"
            ),
        },
        "counts": {
            "cancelled_planning_negative_rows": status_counts["cancelled"],
            "exact_deduplicated_source_observations": len(observations),
            "feature_rows_retrieved": capture["feature_rows_retrieved"],
            "query_memberships": len(memberships),
            "raw_hits_by_query": {
                query["query_id"]: query["hits"]["number_matched"]
                for query in queries
            },
            "raw_hits_total": sum(
                query["hits"]["number_matched"] for query in queries
            ),
            "status_layer_observation_counts": {
                key: status_counts[key] for key in ("proposal", "adopted", "cancelled")
            },
            "unique_physical_site_count": None,
        },
        "coverage": {
            "all_27_queries_complete": not truncated,
            "attached_documents_searched": False,
            "complete_for_denmark": False,
            "field_searched": "plannavn",
            "national_data_centre_completeness_claimed": False,
            "source_scope": "three Plandata.dk current local-plan status layers",
        },
        "format": RELEASE_FORMAT,
        "inference_boundary": source_definition()["inference_policy"],
        "release_id": RELEASE_ID,
        "retrieval": {
            "controlled_request_count": capture["controlled_request_count"],
            "detail_requests": 0,
            "document_requests": 0,
            "minimum_request_interval_seconds": capture[
                "minimum_request_interval_seconds"
            ],
            "pdf_requests": 0,
            "raw_response_bodies_retained": False,
        },
        "rights": source_definition()["rights"],
        "schema_version": SCHEMA_VERSION,
        "semantic_boundary": {
            "adopted_or_effective_is_physical_lifecycle": False,
            "cancelled_is_negative_planning_evidence": True,
            "identity_operator_type_it_mw_pue_energy_workload_status_unknown": True,
            "megawatt_interpreted_without_definition": False,
            "planning_maxima_interpreted_as_observed": False,
            "proposal_is_physical_lifecycle": False,
        },
        "task_request_accounting": {
            "aborted_capture_attempt": {
                "artifact_or_coverage_evidence": False,
                "reason": (
                    "feature parser expected the human label Vedtaget, but the "
                    "official adopted layer returned the exact status code V"
                ),
                "request_count": TASK_ABORTED_CAPTURE_GETS,
                "requests": {
                    "controls": {
                        "capabilities_200": 1,
                        "licence_jsonld_200": 1,
                        "robots_404": 1,
                        "schema_200": 3,
                    },
                    "q01_through_q09_hits_xml_200": 9,
                    "q10_hits_xml_200_number_matched_3": 1,
                    "q10_page_1_json_200_three_features": 1,
                },
                "response_bodies_retained": False,
                "response_metadata_retained": False,
                "result": "stopped_before_artifact_write_then_clean_restart",
            },
            "browser_or_search_tool_requests_included": False,
            "browser_or_search_tool_reason": (
                "may be cached or proxied and exposes no reliable origin-request count"
            ),
            "direct_local_official_endpoint_gets_total": TASK_DIRECT_LOCAL_GETS,
            "direct_local_total_below_predeclared_115_hard_cap": True,
            "frozen_hash_bound_capture_gets": TASK_FROZEN_CAPTURE_GETS,
            "minimum_request_interval_applies_to": (
                "frozen_hash_bound_capture_only"
            ),
            "implementation_preflight_gets": {
                "request_count": TASK_PREFLIGHT_GETS,
                "response_bodies_retained": False,
                "response_metadata_retained": False,
                "types": {
                    "first_control_pass": (
                        "licence 200, robots 404, capabilities 200, three schemas 200"
                    ),
                    "schema_semantic_pass": "licence 200 and three schemas 200",
                    "single_hits_probes": "two XML 200 zero-hit responses",
                },
            },
            "status_code_diagnostic_gets": {
                "request_count": TASK_STATUS_DIAGNOSTIC_GETS,
                "response_bodies_retained": False,
                "response_metadata_retained": False,
                "result": "one JSON 200 feature per layer established F, V, and A",
            },
            "unfrozen_gets_not_coverage_evidence": (
                TASK_PREFLIGHT_GETS
                + TASK_ABORTED_CAPTURE_GETS
                + TASK_STATUS_DIAGNOSTIC_GETS
            ),
            "request_reconciliation": "35 frozen + 32 unfrozen = 67 direct local GETs",
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-denmark-plandata-schema-v1",
        "observation_contract": {
            "atlas_identity": None,
            "construction_status": None,
            "data_centre_type": None,
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "operator": None,
            "pue": None,
            "workload": None,
        },
        "projected_source_properties": list(FEATURE_PROPERTIES),
        "schema_version": SCHEMA_VERSION,
        "source_megawatt_and_planning_maxima_projected": False,
    }


def source_inventory_document(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "catalogue": {
            "dataset_title": DATASET_TITLE,
            "dataset_url": DATASET_URL,
            "licence_uri": LICENSE_URI,
            "publisher": PUBLISHER,
        },
        "control_request_count": 6,
        "format": "datacenter-atlas-denmark-plandata-source-inventory-v1",
        "layer_schemas": [
            row["summary"] for row in capture["control"]["schemas"]
        ],
        "robots": capture["control"]["robots"]["summary"],
        "task_direct_local_request_accounting": assessment_document(capture)[
            "task_request_accounting"
        ],
        "wfs_capabilities": capture["control"]["capabilities"]["summary"],
    }


def attribution_bytes() -> bytes:
    return f"""Denmark Plandata.dk local-plan source assessment

Source attribution: {PUBLISHER}
Dataset record: {DATASET_URL}
Official WFS: {WFS_URL}
Catalogue licence URI: {LICENSE_URI}
Human-readable licence: {CC_BY_4_URL}

The official Datavejviser JSON-LD record declares CC BY 4.0 for the named
local-plan dataset and its four listed distributions.  This assessment uses an
official Plandata.dk WFS endpoint identified by Plandata.dk's own WFS guide.
It does not extend that licence to linked plan documents or make a legal
conclusion.  Plandata.dk/Plan- og Landdistriktsstyrelsen attribution is retained.
""".encode("utf-8")


def readme_bytes(capture: Mapping[str, Any]) -> bytes:
    assessment = assessment_document(capture)
    counts = assessment["counts"]
    return f"""# Denmark Plandata.dk local-plan assessment

This frozen release executes 27 exact, predeclared, case-insensitive OGC
`PropertyIsLike` queries against `plannavn`: nine literals across proposal,
adopted, and cancelled local-plan layers.  Its final hash-bound capture made
{capture['controlled_request_count']} controlled requests at a minimum five-
second interval and retrieved {capture['feature_rows_retrieved']} paged feature
rows.  The exact query membership total is {counts['query_memberships']}; the
closed union contains {counts['exact_deduplicated_source_observations']} source
observations.  These are planning-name matches, not a Danish data-centre census.

The control pass revalidated the official Datavejviser JSON-LD licence record,
the absent robots path (HTTP 404), WFS 2.0 capabilities, and the complete schema
of each selected layer.  Robots absence is not permission.  Every response URL,
timestamp, status, redirect count, byte count, media type, and SHA-256 is bound
in `capture-metadata.json`; raw response bodies are not retained.

Across local implementation and the final capture, this task made exactly
{TASK_DIRECT_LOCAL_GETS} direct GETs to official endpoints.  Of those, 35 are
the final hash-bound capture above.  Twelve implementation preflight GETs and
three one-feature status-code diagnostics were not retained.  A first capture
attempt made 17 GETs: six controls, q01-q09 hit counts, the q10 hit count, and
q10 page 1.  It stopped before writing any artifact because the parser expected
the human label `Vedtaget` while the adopted WFS layer returned exact status
code `V`.  Its response bodies and per-request metadata were discarded, and it
is not coverage evidence.  A clean restart pinned `F`, `V`, and `A`.  The 32
unfrozen GETs are disclosed only as task accounting.  Browser/search tooling is
excluded from the direct-GET total because it may be cached or proxied and does
not expose a reliable origin-request count.  The five-second interval applies
only to the clean 35-request frozen capture; no pacing claim is made for the 32
discarded probes.  The task total reconciles as 35 + 32 = 67 direct local GETs,
which remains below the predeclared 115-request hard cap.

Positive queries are sorted by source `id`, paged at 100 rows, and capped at
three pages.  The global contract permits at most 8,100 retrieved features and
115 controlled requests.  Any response error, unexpected HTML outside the
pinned robots 404, redirect, schema drift, short non-final page, repeated page
feature, count drift, or other pagination inconsistency fails closed.  A query
over 300 hits may be audited but causes the entire observation union to remain
empty rather than publishing a truncated subset.  No detail pages or PDFs were
requested in this first pass.

Proposal, adopted, and effective values are administrative planning facts, not
physical construction, completion, commissioning, or operation.  Cancelled is
negative planning evidence.  The source schema exposes planning maxima and a
`megawatt` field, but this lane deliberately does not retrieve those values:
maxima are not observed actuals, and megawatt cannot become capacity or energy
without a source definition.  Atlas identity, operator, data-centre type, IT
MW, gross facility power, PUE, annual energy, workload, physical status, and
unique-site count all remain unknown.  Planning polygons are not facility
footprints or facility coordinates.

Construction-master, construction-map, and current-coverage-ledger imports are
all forbidden.  Validate without network access with:

```bash
python3 scripts/validate_denmark_plandata_local_plans.py
```
""".encode("utf-8")


def derive_release_files(capture: Mapping[str, Any]) -> dict[str, bytes]:
    validated = validate_capture(dict(capture))
    observations, memberships = derive_observations(validated)
    return {
        "ATTRIBUTION.txt": attribution_bytes(),
        "README.md": readme_bytes(validated),
        "assessment.json": canonical_json(assessment_document(validated)),
        "capture-metadata.json": canonical_json(validated),
        "definition.json": canonical_json(source_definition()),
        "observations.jsonl": jsonl(observations),
        "query-membership.jsonl": jsonl(memberships),
        "query-plan.json": canonical_json(query_plan()),
        "schema.json": canonical_json(schema_document()),
        "source-inventory.json": canonical_json(
            source_inventory_document(validated)
        ),
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


def freeze_release(root: Path) -> None:
    for entry in sorted(root.rglob("*"), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def is_frozen_release(root: Path) -> bool:
    return (
        root.is_dir()
        and not root.is_symlink()
        and stat.S_IMODE(root.stat().st_mode) == 0o555
        and all(
            not entry.is_symlink()
            and entry.is_file()
            and stat.S_IMODE(entry.stat().st_mode) == 0o444
            for entry in root.rglob("*")
        )
    )


def write_release_bundle(
    output: Path, capture: Mapping[str, Any], *, freeze: bool = True
) -> Path:
    if output.exists() or output.is_symlink():
        raise DenmarkPlandataError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        files = derive_release_files(capture)
        for name, body in files.items():
            (temporary / name).write_bytes(body)
        manifest_body = canonical_json(_manifest(files))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        if freeze:
            freeze_release(temporary)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise
    return output


def _load_canonical_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise DenmarkPlandataError(f"{label} must be a regular file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DenmarkPlandataError(f"invalid {label}") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise DenmarkPlandataError(f"{label} must be canonical JSON")
    return value


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise DenmarkPlandataError("release must be a regular directory")
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise DenmarkPlandataError("release file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in root.rglob("*")):
        raise DenmarkPlandataError("release entries must be regular files")
    if require_frozen and not is_frozen_release(root):
        raise DenmarkPlandataError("release modes are not frozen")
    capture = _load_canonical_json(
        root / "capture-metadata.json", label="capture metadata"
    )
    files = derive_release_files(capture)
    for name, expected in files.items():
        if (root / name).read_bytes() != expected:
            raise DenmarkPlandataError(f"derived file differs: {name}")
    manifest = _load_canonical_json(root / MANIFEST_FILENAME, label="manifest")
    if manifest != _manifest(files):
        raise DenmarkPlandataError("manifest inventory differs")
    raw_manifest = (root / MANIFEST_FILENAME).read_bytes()
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != (
        f"{sha256_bytes(raw_manifest)}  {MANIFEST_FILENAME}\n"
    ):
        raise DenmarkPlandataError("manifest sidecar differs")
    definition = _load_canonical_json(root / "definition.json", label="definition")
    if definition != source_definition():
        raise DenmarkPlandataError("release definition changed")
    if definition_path is not None:
        if definition_path.is_symlink() or not definition_path.is_file():
            raise DenmarkPlandataError("external definition must be a regular file")
        if definition_path.read_bytes() != canonical_json(definition):
            raise DenmarkPlandataError("external definition differs")
    assessment = _load_canonical_json(root / "assessment.json", label="assessment")
    for key in (
        "construction_map_import_permitted",
        "construction_master_import_permitted",
        "current_coverage_ledger_import_permitted",
    ):
        if assessment["atlas_decision"][key] is not False:
            raise DenmarkPlandataError("downstream import permission changed")
    return {
        "assessment": assessment,
        "capture": capture,
        "definition": definition,
        "manifest": manifest,
    }
