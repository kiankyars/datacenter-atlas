"""Strict offline importer for manually verified, official-source records."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .adapters import ImportResult
from .models import (
    Campus,
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    LifecycleObservation,
    LifecycleStatus,
    OperatingModel,
    Project,
    Workload,
)
from .repository import (
    add_campus,
    add_capacity,
    add_evidence,
    add_lifecycle,
    add_operating_model,
    add_project,
    add_snapshot,
    add_workload,
    stable_id,
)


SCHEMA_VERSION = "1.0"
OFFICIAL_EVIDENCE_KINDS = {
    EvidenceKind.GOVERNMENT_RECORD,
    EvidenceKind.COMPANY_DISCLOSURE,
    EvidenceKind.UTILITY_RECORD,
    EvidenceKind.EQUIPMENT_ORDER,
    EvidenceKind.SATELLITE_IMAGERY,
}
MEASURED_ENERGY_EVIDENCE_KINDS = {
    EvidenceKind.GOVERNMENT_RECORD,
    EvidenceKind.UTILITY_RECORD,
}
CONSTRUCTION_STATUSES = {
    LifecycleStatus.SITE_PREPARATION,
    LifecycleStatus.CLEARING,
    LifecycleStatus.CIVIL_WORKS,
    LifecycleStatus.FOUNDATIONS,
    LifecycleStatus.SHELL,
    LifecycleStatus.MEP_ELECTRICAL,
    LifecycleStatus.UNDER_CONSTRUCTION,
    LifecycleStatus.COMMISSIONING,
}
CONSTRUCTION_METHODS = {
    "authoritative_construction_start",
    "authoritative_physical_status_update",
    "physical_observation",
}
LIFECYCLE_METHODS = {
    "authoritative_announcement",
    "authoritative_construction_start",
    "authoritative_physical_status_update",
    "authoritative_status_update",
    "government_record",
    "physical_observation",
    "analyst_synthesis",
}
SNAPSHOT_METHODS = {
    "authoritative_address_geocode",
    "authoritative_locality",
    "authoritative_site_plan",
    "physical_observation",
    "analyst_geolocation",
}
CLASSIFICATION_METHODS = {
    "company_disclosure",
    "government_record",
    "utility_record",
    "physical_observation",
    "analyst_synthesis",
}
ROLE_KEYS = {
    "owner",
    "operator",
    "developer",
    "landlord",
    "tenant",
    "user",
    "customer",
    "utility",
    "contractor",
    "investor",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CONTENT_HASH_VERIFICATIONS = {
    "fetched_bytes_sha256",
    "unverified_assertion",
}


@dataclass(frozen=True, slots=True)
class _EvidenceRecord:
    key: str
    model: Evidence
    content_hash: str
    content_hash_scope: str
    content_hash_verification: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _EntityRecord:
    ref: str
    stable_key: str
    name: str
    country: str
    address: str | None
    roles: dict[str, list[str]]
    latitude: float | None
    longitude: float | None
    geometry: dict[str, Any] | None
    evidence_key: str
    as_of_date: str
    method: str
    confidence: float


@dataclass(frozen=True, slots=True)
class _Observation:
    entity_ref: str
    value: Any
    evidence_key: str
    as_of_date: str
    method: str
    confidence: float


@dataclass(frozen=True, slots=True)
class _CapacityRecord:
    entity_ref: str
    metric: CapacityMetric
    stage: CapacityStage
    unit: str
    low: float
    base: float
    high: float
    method: EstimateMethod
    confidence: float
    evidence_key: str
    as_of_date: str
    target_date: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class _Document:
    evidence: tuple[_EvidenceRecord, ...]
    campus: _EntityRecord
    project: _EntityRecord | None
    lifecycle: tuple[_Observation, ...]
    operating_models: tuple[_Observation, ...]
    workloads: tuple[_Observation, ...]
    capacities: tuple[_CapacityRecord, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    return value


def _fields(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] = frozenset(),
) -> None:
    unknown = set(value) - required - optional
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{path} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{path} is missing fields: {', '.join(sorted(missing))}")


def _string(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{path} must be finite")
    return result


def _confidence(value: Any, path: str) -> float:
    result = _number(value, path)
    if not 0 <= result <= 1:
        raise ValueError(f"{path} must be between 0 and 1")
    return result


def _date(value: Any, path: str) -> str:
    text = _string(value, path)
    assert text is not None
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO 8601 date") from error
    if parsed.isoformat() != text:
        raise ValueError(f"{path} must be YYYY-MM-DD")
    return text


def _timestamp(value: Any, path: str) -> str:
    text = _string(value, path)
    assert text is not None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{path} must include a timezone")
    return text


def _published(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be null or an ISO 8601 date or timestamp")
    if "T" in value:
        return _timestamp(value, path)
    return _date(value, path)


def _enum(enum_type: type[Any], value: Any, path: str) -> Any:
    text = _string(value, path)
    try:
        return enum_type(text)
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{path} must be one of: {allowed}") from error


def _method(value: Any, path: str, allowed: set[str]) -> str:
    text = _string(value, path)
    assert text is not None
    if text not in allowed:
        raise ValueError(f"{path} must be one of: {', '.join(sorted(allowed))}")
    return text


def _url(value: Any, path: str) -> str:
    text = _string(value, path)
    assert text is not None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{path} must be an absolute HTTP(S) URL")
    return text


def _coordinate_pair(value: Any, path: str) -> tuple[float, float]:
    point = _object(value, path)
    _fields(point, path, required={"latitude", "longitude"})
    latitude = _number(point["latitude"], f"{path}.latitude")
    longitude = _number(point["longitude"], f"{path}.longitude")
    if not -90 <= latitude <= 90:
        raise ValueError(f"{path}.latitude must be in WGS84 degrees from -90 to 90")
    if not -180 <= longitude <= 180:
        raise ValueError(f"{path}.longitude must be in WGS84 degrees from -180 to 180")
    return latitude, longitude


def _geo_point(value: Any, path: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{path} must be [longitude, latitude] in WGS84 degrees")
    longitude = _number(value[0], f"{path}[0]")
    latitude = _number(value[1], f"{path}[1]")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError(f"{path} is outside valid WGS84 longitude/latitude bounds")
    return longitude, latitude


def _ring(value: Any, path: str) -> list[list[float]]:
    raw = _list(value, path)
    points = [[lon, lat] for lon, lat in (_geo_point(item, f"{path}[{i}]") for i, item in enumerate(raw))]
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError(f"{path} must be a closed GeoJSON linear ring with at least four points")
    return points


def _geometry(value: Any, path: str) -> dict[str, Any]:
    geometry = _object(value, path)
    _fields(geometry, path, required={"type", "coordinates"})
    geometry_type = _string(geometry["type"], f"{path}.type")
    coordinates = geometry["coordinates"]
    if geometry_type == "Point":
        longitude, latitude = _geo_point(coordinates, f"{path}.coordinates")
        return {"type": "Point", "coordinates": [longitude, latitude]}
    if geometry_type == "Polygon":
        rings = [_ring(ring, f"{path}.coordinates[{i}]") for i, ring in enumerate(_list(coordinates, f"{path}.coordinates"))]
        if not rings:
            raise ValueError(f"{path}.coordinates must contain at least one ring")
        return {"type": "Polygon", "coordinates": rings}
    if geometry_type == "MultiPolygon":
        polygons: list[list[list[list[float]]]] = []
        for i, polygon in enumerate(_list(coordinates, f"{path}.coordinates")):
            rings = [_ring(ring, f"{path}.coordinates[{i}][{j}]") for j, ring in enumerate(_list(polygon, f"{path}.coordinates[{i}]"))]
            if not rings:
                raise ValueError(f"{path}.coordinates[{i}] must contain at least one ring")
            polygons.append(rings)
        if not polygons:
            raise ValueError(f"{path}.coordinates must contain at least one polygon")
        return {"type": "MultiPolygon", "coordinates": polygons}
    raise ValueError(f"{path}.type must be Point, Polygon, or MultiPolygon")


def _geometry_points(geometry: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list) and len(value) == 2 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        ):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(geometry["coordinates"])
    return points


def _roles(value: Any, path: str) -> dict[str, list[str]]:
    roles = _object(value, path)
    unknown = set(roles) - ROLE_KEYS
    if unknown:
        raise ValueError(f"{path} has unknown role types: {', '.join(sorted(unknown))}")
    result: dict[str, list[str]] = {}
    for role, raw_names in roles.items():
        names = _list(raw_names, f"{path}.{role}")
        if not names:
            raise ValueError(f"{path}.{role} must not be empty")
        result[role] = []
        for index, name in enumerate(names):
            parsed = _string(name, f"{path}.{role}[{index}]")
            assert parsed is not None
            if parsed in result[role]:
                raise ValueError(f"{path}.{role} contains a duplicate value: {parsed}")
            result[role].append(parsed)
    return result


def _evidence_record(value: Any, index: int, retrieved_at: str) -> _EvidenceRecord:
    path = f"evidence[{index}]"
    record = _object(value, path)
    _fields(
        record,
        path,
        required={
            "key", "kind", "title", "source_url", "publisher", "source_family",
            "published_at", "retrieved_at", "license", "attribution", "excerpt",
            "content_hash", "metadata",
        },
    )
    key = _string(record["key"], f"{path}.key")
    assert key is not None
    kind = _enum(EvidenceKind, record["kind"], f"{path}.kind")
    if kind not in OFFICIAL_EVIDENCE_KINDS:
        raise ValueError(f"{path}.kind is not accepted for curated official-source evidence")
    evidence_retrieved_at = _timestamp(record["retrieved_at"], f"{path}.retrieved_at")
    if evidence_retrieved_at != retrieved_at:
        raise ValueError(f"{path}.retrieved_at must equal the import retrieved_at")
    content_hash = _string(record["content_hash"], f"{path}.content_hash")
    assert content_hash is not None
    if not SHA256_PATTERN.fullmatch(content_hash):
        raise ValueError(f"{path}.content_hash must be a lowercase SHA-256 hex digest")
    metadata = _object(record["metadata"], f"{path}.metadata")
    content_hash_scope = _string(
        metadata.get("content_hash_scope"),
        f"{path}.metadata.content_hash_scope",
    )
    content_hash_verification = _string(
        metadata.get("content_hash_verification"),
        f"{path}.metadata.content_hash_verification",
    )
    assert content_hash_scope is not None and content_hash_verification is not None
    if content_hash_verification not in CONTENT_HASH_VERIFICATIONS:
        allowed = ", ".join(sorted(CONTENT_HASH_VERIFICATIONS))
        raise ValueError(
            f"{path}.metadata.content_hash_verification must be one of: {allowed}"
        )
    try:
        json.dumps(metadata, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path}.metadata must be finite JSON data") from error
    evidence_id = stable_id("evidence", "curated-official", key, content_hash)
    title = _string(record["title"], f"{path}.title")
    publisher = _string(record["publisher"], f"{path}.publisher")
    source_family = _string(record["source_family"], f"{path}.source_family")
    license_name = _string(record["license"], f"{path}.license")
    attribution = _string(record["attribution"], f"{path}.attribution")
    excerpt = _string(record["excerpt"], f"{path}.excerpt")
    assert all(item is not None for item in (title, publisher, source_family, license_name, attribution, excerpt))
    return _EvidenceRecord(
        key=key,
        model=Evidence(
            id=evidence_id,
            kind=kind,
            title=title,
            source_url=_url(record["source_url"], f"{path}.source_url"),
            publisher=publisher,
            source_family=source_family,
            license=license_name,
            attribution=attribution,
            published_at=_published(record["published_at"], f"{path}.published_at"),
            retrieved_at=evidence_retrieved_at,
            excerpt=excerpt,
        ),
        content_hash=content_hash,
        content_hash_scope=content_hash_scope,
        content_hash_verification=content_hash_verification,
        metadata=metadata,
    )


def _entity_record(value: Any, path: str, ref: str) -> _EntityRecord:
    record = _object(value, path)
    _fields(
        record,
        path,
        required={
            "stable_key", "name", "country", "address", "roles", "coordinates",
            "geometry", "evidence_key", "as_of_date", "method", "confidence",
        },
    )
    coordinates = record["coordinates"]
    geometry_value = record["geometry"]
    method = _method(record["method"], f"{path}.method", SNAPSHOT_METHODS)
    if coordinates is None and geometry_value is None:
        if method != "authoritative_locality":
            raise ValueError(
                f"{path}.method must be authoritative_locality when coordinates and geometry are null"
            )
    elif method == "authoritative_locality":
        raise ValueError(
            f"{path}.method authoritative_locality requires null coordinates and geometry"
        )
    geometry = _geometry(geometry_value, f"{path}.geometry") if geometry_value is not None else None
    if coordinates is not None:
        latitude, longitude = _coordinate_pair(coordinates, f"{path}.coordinates")
    elif geometry is not None:
        points = _geometry_points(geometry)
        longitudes = [point[0] for point in points]
        latitudes = [point[1] for point in points]
        longitude = (min(longitudes) + max(longitudes)) / 2
        latitude = (min(latitudes) + max(latitudes)) / 2
    else:
        latitude = None
        longitude = None
    if geometry is None and coordinates is not None:
        geometry = {"type": "Point", "coordinates": [longitude, latitude]}
    elif coordinates is not None:
        points = _geometry_points(geometry)
        if not (
            min(point[0] for point in points) <= longitude <= max(point[0] for point in points)
            and min(point[1] for point in points) <= latitude <= max(point[1] for point in points)
        ):
            raise ValueError(f"{path}.coordinates must lie within the geometry bounds")
    stable_key = _string(record["stable_key"], f"{path}.stable_key")
    name = _string(record["name"], f"{path}.name")
    country = _string(record["country"], f"{path}.country")
    evidence_key = _string(record["evidence_key"], f"{path}.evidence_key")
    assert stable_key is not None and name is not None and country is not None and evidence_key is not None
    return _EntityRecord(
        ref=ref,
        stable_key=stable_key,
        name=name,
        country=country,
        address=_string(record["address"], f"{path}.address", nullable=True),
        roles=_roles(record["roles"], f"{path}.roles"),
        latitude=latitude,
        longitude=longitude,
        geometry=geometry,
        evidence_key=evidence_key,
        as_of_date=_date(record["as_of_date"], f"{path}.as_of_date"),
        method=method,
        confidence=_confidence(record["confidence"], f"{path}.confidence"),
    )


def _observation(
    value: Any,
    path: str,
    *,
    enum_type: type[Any],
    allowed_methods: set[str],
) -> _Observation:
    record = _object(value, path)
    _fields(
        record,
        path,
        required={"entity", "value", "evidence_key", "as_of_date", "method", "confidence"},
    )
    entity_ref = _string(record["entity"], f"{path}.entity")
    evidence_key = _string(record["evidence_key"], f"{path}.evidence_key")
    assert entity_ref is not None and evidence_key is not None
    return _Observation(
        entity_ref=entity_ref,
        value=_enum(enum_type, record["value"], f"{path}.value"),
        evidence_key=evidence_key,
        as_of_date=_date(record["as_of_date"], f"{path}.as_of_date"),
        method=_method(record["method"], f"{path}.method", allowed_methods),
        confidence=_confidence(record["confidence"], f"{path}.confidence"),
    )


def _capacity(value: Any, index: int) -> _CapacityRecord:
    path = f"capacities[{index}]"
    record = _object(value, path)
    _fields(
        record,
        path,
        required={
            "entity", "metric", "stage", "unit", "low", "base", "high", "method",
            "confidence", "evidence_key", "as_of_date", "target_date", "notes",
        },
    )
    metric = _enum(CapacityMetric, record["metric"], f"{path}.metric")
    unit = _string(record["unit"], f"{path}.unit")
    assert unit is not None
    if unit != metric.unit:
        raise ValueError(f"{path}.unit must be {metric.unit!r} for {metric.value}")
    entity_ref = _string(record["entity"], f"{path}.entity")
    evidence_key = _string(record["evidence_key"], f"{path}.evidence_key")
    assert entity_ref is not None and evidence_key is not None
    return _CapacityRecord(
        entity_ref=entity_ref,
        metric=metric,
        stage=_enum(CapacityStage, record["stage"], f"{path}.stage"),
        unit=unit,
        low=_number(record["low"], f"{path}.low"),
        base=_number(record["base"], f"{path}.base"),
        high=_number(record["high"], f"{path}.high"),
        method=_enum(EstimateMethod, record["method"], f"{path}.method"),
        confidence=_confidence(record["confidence"], f"{path}.confidence"),
        evidence_key=evidence_key,
        as_of_date=_date(record["as_of_date"], f"{path}.as_of_date"),
        target_date=(
            _date(record["target_date"], f"{path}.target_date")
            if record["target_date"] is not None
            else None
        ),
        notes=_string(record["notes"], f"{path}.notes", nullable=True),
    )


def _reject_duplicate_claim_keys(
    collection_name: str,
    collection: tuple[Any, ...],
    key_parts: Any,
) -> None:
    seen: dict[tuple[Any, ...], int] = {}
    for index, item in enumerate(collection):
        key = tuple(key_parts(item))
        if key in seen:
            raise ValueError(
                f"{collection_name}[{index}] duplicates the logical claim key from "
                f"{collection_name}[{seen[key]}]"
            )
        seen[key] = index


def _parse_document(path: Path, retrieved_at: str) -> _Document:
    _timestamp(retrieved_at, "retrieved_at")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid curated JSON: {error}") from error
    root = _object(raw, "root")
    _fields(
        root,
        "root",
        required={
            "schema_version", "evidence", "campus", "project", "lifecycle",
            "operating_models", "workloads", "capacities",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")

    evidence = tuple(
        _evidence_record(item, index, retrieved_at)
        for index, item in enumerate(_list(root["evidence"], "evidence"))
    )
    if not evidence:
        raise ValueError("evidence must contain at least one record")
    evidence_by_key = {item.key: item for item in evidence}
    if len(evidence_by_key) != len(evidence):
        raise ValueError("evidence keys must be unique")

    campus = _entity_record(root["campus"], "campus", "campus")
    project = (
        _entity_record(root["project"], "project", "project")
        if root["project"] is not None
        else None
    )
    lifecycle = tuple(
        _observation(
            item,
            f"lifecycle[{index}]",
            enum_type=LifecycleStatus,
            allowed_methods=LIFECYCLE_METHODS,
        )
        for index, item in enumerate(_list(root["lifecycle"], "lifecycle"))
    )
    operating_models = tuple(
        _observation(
            item,
            f"operating_models[{index}]",
            enum_type=OperatingModel,
            allowed_methods=CLASSIFICATION_METHODS,
        )
        for index, item in enumerate(_list(root["operating_models"], "operating_models"))
    )
    workloads = tuple(
        _observation(
            item,
            f"workloads[{index}]",
            enum_type=Workload,
            allowed_methods=CLASSIFICATION_METHODS,
        )
        for index, item in enumerate(_list(root["workloads"], "workloads"))
    )
    capacities = tuple(
        _capacity(item, index)
        for index, item in enumerate(_list(root["capacities"], "capacities"))
    )
    _reject_duplicate_claim_keys(
        "lifecycle",
        lifecycle,
        lambda item: (item.entity_ref, item.as_of_date),
    )
    _reject_duplicate_claim_keys(
        "operating_models",
        operating_models,
        lambda item: (item.entity_ref, item.as_of_date),
    )
    _reject_duplicate_claim_keys(
        "workloads",
        workloads,
        lambda item: (item.entity_ref, item.value.value, item.as_of_date),
    )
    _reject_duplicate_claim_keys(
        "capacities",
        capacities,
        lambda item: (
            item.entity_ref,
            item.metric.value,
            item.stage.value,
            item.as_of_date,
        ),
    )

    entity_refs = {"campus"} | ({"project"} if project else set())
    for entity in (campus, project):
        if entity is not None and entity.evidence_key not in evidence_by_key:
            raise ValueError(f"{entity.ref}.evidence_key references missing evidence: {entity.evidence_key}")
    for collection_name, collection in (
        ("lifecycle", lifecycle),
        ("operating_models", operating_models),
        ("workloads", workloads),
        ("capacities", capacities),
    ):
        for index, observation in enumerate(collection):
            if observation.entity_ref not in entity_refs:
                raise ValueError(f"{collection_name}[{index}].entity references a missing entity")
            if observation.evidence_key not in evidence_by_key:
                raise ValueError(
                    f"{collection_name}[{index}].evidence_key references missing evidence: "
                    f"{observation.evidence_key}"
                )

    for index, observation in enumerate(lifecycle):
        if observation.value in CONSTRUCTION_STATUSES and observation.method not in CONSTRUCTION_METHODS:
            raise ValueError(
                f"lifecycle[{index}] construction status requires "
                "authoritative_construction_start, authoritative_physical_status_update, "
                "or physical_observation"
            )
    for index, estimate in enumerate(capacities):
        if not (0 <= estimate.low <= estimate.base <= estimate.high):
            raise ValueError(f"capacities[{index}] must satisfy 0 <= low <= base <= high")
        if estimate.metric is CapacityMetric.PUE and estimate.low <= 0:
            raise ValueError(f"capacities[{index}] PUE must be greater than zero")
        evidence_kind = evidence_by_key[estimate.evidence_key].model.kind
        if (
            estimate.metric is CapacityMetric.ANNUAL_ENERGY_MWH
            and estimate.stage is CapacityStage.MEASURED
            and evidence_kind not in MEASURED_ENERGY_EVIDENCE_KINDS
        ):
            raise ValueError(
                f"capacities[{index}] measured annual energy requires utility_record "
                "or government_record evidence"
            )
    return _Document(
        evidence=evidence,
        campus=campus,
        project=project,
        lifecycle=lifecycle,
        operating_models=operating_models,
        workloads=workloads,
        capacities=capacities,
    )


def _entity_tags(entity: _EntityRecord) -> dict[str, str]:
    tags = {"source_dataset": "curated_official_sources", "country": entity.country}
    if entity.address:
        tags["address"] = entity.address
    for role, names in sorted(entity.roles.items()):
        tags[f"role:{role}"] = "; ".join(names)
    return tags


def _reject_existing_claim_key(
    connection: sqlite3.Connection,
    *,
    table: str,
    claim_id: str,
    entity_id: str,
    as_of_date: str,
    recorded_at: str,
    dimensions: dict[str, str] | None = None,
) -> None:
    allowed_dimensions = {
        "lifecycle_observations": set(),
        "operating_model_observations": set(),
        "workload_observations": {"workload"},
        "capacity_estimates": {"metric", "stage"},
    }
    if table not in allowed_dimensions:
        raise ValueError(f"unsupported curated claim table: {table}")
    dimensions = dimensions or {}
    if set(dimensions) != allowed_dimensions[table]:
        raise ValueError(f"invalid logical claim dimensions for {table}")
    clauses = [
        "entity_id = ?",
        "as_of_date = ?",
        "recorded_at = ?",
        "superseded_at IS NULL",
    ]
    parameters: list[str] = [entity_id, as_of_date, recorded_at]
    for column, value in sorted(dimensions.items()):
        clauses.append(f"{column} = ?")
        parameters.append(value)
    rows = connection.execute(
        f"SELECT id FROM {table} WHERE {' AND '.join(clauses)}",
        parameters,
    ).fetchall()
    conflicting_ids = sorted(row["id"] for row in rows if row["id"] != claim_id)
    if conflicting_ids:
        raise ValueError(
            f"{table} already has an active claim for the same logical key, "
            f"as_of_date, and recorded_at"
        )


class CuratedOfficialSourceAdapter:
    """Import a fully local, pre-verified record without fetching any source."""

    source_name = "curated_official_sources"

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        document = _parse_document(Path(path), retrieved_at)
        evidence_by_key = {item.key: item for item in document.evidence}
        evidence_created = 0
        entities_created = 0
        entity_ids: dict[str, str] = {}

        with connection:
            for item in document.evidence:
                evidence_created += int(
                    add_evidence(
                        connection,
                        item.model,
                        content_hash=item.content_hash,
                        metadata={
                            "curated_record_key": item.key,
                            "content_hash_scope": item.content_hash_scope,
                            "content_hash_verification": item.content_hash_verification,
                            "record": item.metadata,
                        },
                    )
                )

            campus_evidence = evidence_by_key[document.campus.evidence_key].model
            campus_id = stable_id("entity", document.campus.stable_key, "campus")
            entity_ids["campus"] = campus_id
            entities_created += int(
                add_campus(
                    connection,
                    Campus(campus_id, document.campus.stable_key, campus_evidence.id),
                    created_at=retrieved_at,
                )
            )
            entities: list[tuple[_EntityRecord, str]] = [(document.campus, campus_id)]
            if document.project:
                project_evidence = evidence_by_key[document.project.evidence_key].model
                project_id = stable_id("entity", document.project.stable_key, "project")
                entity_ids["project"] = project_id
                entities_created += int(
                    add_project(
                        connection,
                        Project(
                            project_id,
                            document.project.stable_key,
                            project_evidence.id,
                            campus_id,
                        ),
                        created_at=retrieved_at,
                    )
                )
                entities.append((document.project, project_id))

            for entity, entity_id in entities:
                evidence_id = evidence_by_key[entity.evidence_key].model.id
                add_snapshot(
                    connection,
                    snapshot_id=stable_id(
                        "snapshot", entity_id, evidence_id, entity.as_of_date, entity.method
                    ),
                    entity_id=entity_id,
                    name=entity.name,
                    latitude=entity.latitude,
                    longitude=entity.longitude,
                    geometry=entity.geometry,
                    tags=_entity_tags(entity),
                    evidence_id=evidence_id,
                    as_of_date=entity.as_of_date,
                    recorded_at=retrieved_at,
                    method=entity.method,
                    confidence=entity.confidence,
                )

            for observation in document.lifecycle:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = stable_id(
                    "lifecycle", entity_id, evidence_id, observation.as_of_date,
                    observation.value.value, observation.method,
                )
                _reject_existing_claim_key(
                    connection,
                    table="lifecycle_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=retrieved_at,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=observation_id,
                        entity_id=entity_id,
                        status=observation.value,
                        evidence_id=evidence_id,
                        as_of_date=observation.as_of_date,
                        recorded_at=retrieved_at,
                        method=observation.method,
                        confidence=observation.confidence,
                    ),
                )
            for observation in document.operating_models:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = stable_id(
                    "operating-model", entity_id, evidence_id, observation.as_of_date,
                    observation.value.value, observation.method,
                )
                _reject_existing_claim_key(
                    connection,
                    table="operating_model_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=retrieved_at,
                )
                add_operating_model(
                    connection,
                    observation_id=observation_id,
                    entity_id=entity_id,
                    operating_model=observation.value,
                    evidence_id=evidence_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=retrieved_at,
                    method=observation.method,
                    confidence=observation.confidence,
                )
            for observation in document.workloads:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = stable_id(
                    "workload", entity_id, evidence_id, observation.as_of_date,
                    observation.value.value, observation.method,
                )
                _reject_existing_claim_key(
                    connection,
                    table="workload_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=retrieved_at,
                    dimensions={"workload": observation.value.value},
                )
                add_workload(
                    connection,
                    observation_id=observation_id,
                    entity_id=entity_id,
                    workload=observation.value,
                    evidence_id=evidence_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=retrieved_at,
                    method=observation.method,
                    confidence=observation.confidence,
                )
            for estimate in document.capacities:
                entity_id = entity_ids[estimate.entity_ref]
                evidence_id = evidence_by_key[estimate.evidence_key].model.id
                estimate_id = stable_id(
                    "capacity", entity_id, evidence_id, estimate.metric.value,
                    estimate.stage.value, estimate.as_of_date, estimate.target_date,
                    estimate.low, estimate.base, estimate.high, estimate.method.value,
                )
                _reject_existing_claim_key(
                    connection,
                    table="capacity_estimates",
                    claim_id=estimate_id,
                    entity_id=entity_id,
                    as_of_date=estimate.as_of_date,
                    recorded_at=retrieved_at,
                    dimensions={
                        "metric": estimate.metric.value,
                        "stage": estimate.stage.value,
                    },
                )
                add_capacity(
                    connection,
                    CapacityEstimate(
                        id=estimate_id,
                        entity_id=entity_id,
                        metric=estimate.metric,
                        stage=estimate.stage,
                        low=estimate.low,
                        base=estimate.base,
                        high=estimate.high,
                        method=estimate.method,
                        confidence=estimate.confidence,
                        evidence_id=evidence_id,
                        as_of_date=estimate.as_of_date,
                        target_date=estimate.target_date,
                        recorded_at=retrieved_at,
                        notes=estimate.notes,
                    ),
                )

        return ImportResult(
            source=self.source_name,
            examined_elements=1,
            imported_elements=1,
            entities_created=entities_created,
            evidence_created=evidence_created,
        )
