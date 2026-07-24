"""Conservative, offline OpenStreetMap/Overpass JSON adapter."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .adapters import ImportResult
from .models import (
    Building,
    Campus,
    EntityKind,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
    OperatingModel,
    Project,
    Workload,
)
from .repository import (
    add_building,
    add_campus,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_operating_model,
    add_project,
    add_snapshot,
    add_workload,
    stable_id,
)


OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "ODbL-1.0"
DATA_CENTER_VALUES = {"data_center", "data_centre", "datacenter", "datacentre"}
DIRECT_MARKER_KEYS = {
    "amenity",
    "building",
    "construction",
    "construction:building",
    "industrial",
    "landuse",
    "man_made",
    "proposed",
    "proposed:building",
    "site",
    "telecom",
}


def _normalized(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _is_data_center_value(value: object) -> bool:
    return _normalized(value) in DATA_CENTER_VALUES


def is_explicit_data_center(tags: dict[str, str]) -> bool:
    for key, value in tags.items():
        normalized_key = _normalized(key)
        if normalized_key in DIRECT_MARKER_KEYS and _is_data_center_value(value):
            return True
        if normalized_key.startswith(("construction:", "proposed:")) and _is_data_center_value(value):
            return True
    return False


def infer_lifecycle(tags: dict[str, str]) -> tuple[LifecycleStatus, float, str]:
    normalized = {_normalized(key): _normalized(value) for key, value in tags.items()}
    proposed_marker = any(
        (key == "proposed" or key.startswith("proposed:")) and value in DATA_CENTER_VALUES
        for key, value in normalized.items()
    )
    construction_marker = any(
        (key == "construction" or key.startswith("construction:"))
        and value in DATA_CENTER_VALUES
        for key, value in normalized.items()
    )
    if normalized.get("building") == "proposed" and proposed_marker:
        return LifecycleStatus.PROPOSED, 0.70, "osm_explicit_proposed_tag"
    if normalized.get("landuse") == "proposed" and proposed_marker:
        return LifecycleStatus.PROPOSED, 0.65, "osm_explicit_proposed_tag"
    if proposed_marker:
        return LifecycleStatus.PROPOSED, 0.65, "osm_explicit_proposed_tag"
    if normalized.get("building") == "construction" and construction_marker:
        return LifecycleStatus.UNDER_CONSTRUCTION, 0.80, "osm_explicit_construction_tag"
    if normalized.get("landuse") == "construction" and construction_marker:
        return LifecycleStatus.UNDER_CONSTRUCTION, 0.75, "osm_explicit_construction_tag"
    if construction_marker:
        return LifecycleStatus.UNDER_CONSTRUCTION, 0.75, "osm_explicit_construction_tag"
    return LifecycleStatus.UNKNOWN, 0.45, "osm_geometry_only_no_operational_inference"


def _points_from_geometry(geometry: Iterable[dict[str, Any]]) -> list[list[float]]:
    points = []
    for point in geometry:
        if "lat" not in point or "lon" not in point:
            continue
        points.append([float(point["lon"]), float(point["lat"])])
    return points


def _close_ring(points: list[list[float]]) -> list[list[float]]:
    if points and points[0] != points[-1]:
        return [*points, points[0]]
    return points


def _bounds_geometry(bounds: dict[str, Any]) -> dict[str, Any] | None:
    required = ("minlat", "minlon", "maxlat", "maxlon")
    if not all(key in bounds for key in required):
        return None
    minlat, minlon, maxlat, maxlon = (float(bounds[key]) for key in required)
    ring = [
        [minlon, minlat],
        [maxlon, minlat],
        [maxlon, maxlat],
        [minlon, maxlat],
        [minlon, minlat],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def extract_geometry(element: dict[str, Any]) -> dict[str, Any] | None:
    element_type = element.get("type")
    if element_type == "node" and "lat" in element and "lon" in element:
        return {
            "type": "Point",
            "coordinates": [float(element["lon"]), float(element["lat"])],
        }

    direct_geometry = element.get("geometry")
    if isinstance(direct_geometry, dict) and direct_geometry.get("type") in {
        "Point",
        "LineString",
        "Polygon",
        "MultiLineString",
        "MultiPolygon",
    }:
        if _all_coordinates(direct_geometry):
            return direct_geometry

    direct_points = _points_from_geometry(direct_geometry or [])
    if direct_points:
        if len(direct_points) >= 3 and direct_points[0] == direct_points[-1]:
            return {"type": "Polygon", "coordinates": [direct_points]}
        return {"type": "LineString", "coordinates": direct_points}

    if element_type == "relation":
        closed_rings: list[list[list[float]]] = []
        lines: list[list[list[float]]] = []
        for member in element.get("members") or []:
            points = _points_from_geometry(member.get("geometry") or [])
            if not points:
                continue
            if len(points) >= 3 and points[0] == points[-1] and member.get("role") != "inner":
                closed_rings.append(points)
            else:
                lines.append(points)
        if len(closed_rings) == 1:
            return {"type": "Polygon", "coordinates": [closed_rings[0]]}
        if closed_rings:
            return {
                "type": "MultiPolygon",
                "coordinates": [[[point for point in ring]] for ring in closed_rings],
            }
        if lines:
            return {"type": "MultiLineString", "coordinates": lines}

    return _bounds_geometry(element.get("bounds") or {})


def _all_coordinates(geometry: dict[str, Any] | None) -> list[list[float]]:
    if not geometry:
        return []
    coordinates = geometry.get("coordinates")
    points: list[list[float]] = []

    def visit(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            points.append([float(value[0]), float(value[1])])
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(coordinates)
    return points


def extract_center(
    element: dict[str, Any], geometry: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    if element.get("type") == "node" and "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    points = _all_coordinates(geometry)
    if not points:
        return None, None
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return (min(latitudes) + max(latitudes)) / 2, (min(longitudes) + max(longitudes)) / 2


def infer_entity_kind(element: dict[str, Any], tags: dict[str, str]) -> EntityKind:
    if element.get("type") == "node":
        return EntityKind.FACILITY
    normalized = {_normalized(key): _normalized(value) for key, value in tags.items()}
    building_marker = normalized.get("building") in DATA_CENTER_VALUES or any(
        key.endswith(":building") and value in DATA_CENTER_VALUES
        for key, value in normalized.items()
    )
    if normalized.get("building") in {"construction", "proposed"} and (
        normalized.get("construction") in DATA_CENTER_VALUES
        or normalized.get("proposed") in DATA_CENTER_VALUES
    ):
        building_marker = True
    if building_marker:
        return EntityKind.BUILDING
    if normalized.get("site") in DATA_CENTER_VALUES or normalized.get("type") == "site":
        return EntityKind.CAMPUS
    return EntityKind.FACILITY


def _explicit_operating_model(tags: dict[str, str]) -> OperatingModel | None:
    raw = tags.get("data_center:operating_model") or tags.get("datacenter:operating_model")
    if not raw:
        return None
    try:
        return OperatingModel(_normalized(raw))
    except ValueError:
        return None


def _explicit_workloads(tags: dict[str, str]) -> list[Workload]:
    raw = tags.get("data_center:workload") or tags.get("datacenter:workload") or ""
    workloads = []
    for value in raw.split(";"):
        if not value.strip():
            continue
        try:
            workloads.append(Workload(_normalized(value)))
        except ValueError:
            continue
    return workloads


class OpenStreetMapAdapter:
    source_name = "openstreetmap"

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
        provenance: dict[str, Any] | None = None,
    ) -> ImportResult:
        input_path = Path(path)
        raw = input_path.read_bytes()
        payload = json.loads(raw)
        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise ValueError("OSM input must be an Overpass JSON object with an elements list")

        imported = 0
        skipped = 0
        entities_created = 0
        evidence_created = 0
        warnings: list[str] = []
        file_hash = hashlib.sha256(raw).hexdigest()
        evidence_provenance: dict[str, Any] | None = None
        if provenance is not None:
            if not isinstance(provenance, dict):
                raise ValueError("OSM provenance must be a JSON object")
            try:
                evidence_provenance = json.loads(
                    json.dumps(
                        provenance,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError("OSM provenance must be finite JSON data") from error
            provenance_input_sha256 = evidence_provenance.get("input_sha256")
            if provenance_input_sha256 not in {None, file_hash}:
                raise ValueError(
                    "OSM provenance input_sha256 does not match the imported JSON"
                )
            evidence_provenance["input_sha256"] = file_hash

        with connection:
            for element in elements:
                if not isinstance(element, dict):
                    skipped += 1
                    warnings.append("skipped non-object element")
                    continue
                element_type = element.get("type")
                element_id = element.get("id")
                if element_type not in {"node", "way", "relation"} or element_id is None:
                    skipped += 1
                    warnings.append("skipped element missing supported type or id")
                    continue
                tags = {
                    str(key): str(value)
                    for key, value in (element.get("tags") or {}).items()
                }
                if not is_explicit_data_center(tags):
                    skipped += 1
                    continue

                source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}"
                element_blob = json.dumps(element, sort_keys=True, separators=(",", ":")).encode()
                element_hash = hashlib.sha256(element_blob).hexdigest()
                evidence_id = stable_id(
                    "evidence", "osm", element_type, element_id, retrieved_at, element_hash
                )
                name = tags.get("name") or f"OpenStreetMap {element_type} {element_id}"
                published_at = element.get("timestamp")
                as_of_date = str(published_at or retrieved_at)[:10]
                evidence = Evidence(
                    id=evidence_id,
                    kind=EvidenceKind.OPENSTREETMAP,
                    title=f"OpenStreetMap {element_type} {element_id}: {name}",
                    source_url=source_url,
                    publisher="OpenStreetMap contributors",
                    source_family="openstreetmap",
                    license=OSM_LICENSE,
                    attribution=OSM_ATTRIBUTION,
                    published_at=str(published_at) if published_at else None,
                    retrieved_at=retrieved_at,
                    excerpt=json.dumps(tags, sort_keys=True),
                )
                evidence_metadata: dict[str, Any] = {
                    "element_type": element_type,
                    "element_id": element_id,
                    "input_sha256": file_hash,
                }
                if evidence_provenance is not None:
                    evidence_metadata["provenance"] = evidence_provenance
                evidence_created += int(
                    add_evidence(
                        connection,
                        evidence,
                        content_hash=element_hash,
                        metadata=evidence_metadata,
                    )
                )

                geometry = extract_geometry(element)
                latitude, longitude = extract_center(element, geometry)
                kind = infer_entity_kind(element, tags)
                stable_key = f"osm:{element_type}/{element_id}"
                status, status_confidence, status_method = infer_lifecycle(tags)

                if kind is EntityKind.CAMPUS:
                    primary_id = stable_id("entity", stable_key, "campus")
                    entities_created += int(
                        add_campus(
                            connection,
                            Campus(primary_id, stable_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )
                elif kind is EntityKind.BUILDING:
                    facility_key = f"{stable_key}:facility-container"
                    facility_id = stable_id("entity", facility_key, "facility")
                    entities_created += int(
                        add_facility(
                            connection,
                            Facility(facility_id, facility_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )
                    add_snapshot(
                        connection,
                        snapshot_id=stable_id("snapshot", facility_id, evidence_id),
                        entity_id=facility_id,
                        name=f"{name} facility",
                        latitude=latitude,
                        longitude=longitude,
                        geometry=geometry,
                        tags=tags,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_synthetic_facility_container",
                        confidence=0.60,
                    )
                    primary_id = stable_id("entity", stable_key, "building")
                    entities_created += int(
                        add_building(
                            connection,
                            Building(primary_id, stable_key, evidence_id, facility_id),
                            created_at=retrieved_at,
                        )
                    )
                else:
                    primary_id = stable_id("entity", stable_key, "facility")
                    entities_created += int(
                        add_facility(
                            connection,
                            Facility(primary_id, stable_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )

                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", primary_id, evidence_id),
                    entity_id=primary_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    tags=tags,
                    evidence_id=evidence_id,
                    as_of_date=as_of_date,
                    recorded_at=retrieved_at,
                    method="osm_explicit_data_center_tag",
                    confidence=0.80,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", primary_id, evidence_id, status.value),
                        entity_id=primary_id,
                        status=status,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method=status_method,
                        confidence=status_confidence,
                    ),
                )

                operating_model = _explicit_operating_model(tags)
                if operating_model:
                    add_operating_model(
                        connection,
                        observation_id=stable_id(
                            "operating-model", primary_id, evidence_id, operating_model.value
                        ),
                        entity_id=primary_id,
                        operating_model=operating_model,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_explicit_classification_tag",
                        confidence=0.70,
                    )
                for workload in _explicit_workloads(tags):
                    add_workload(
                        connection,
                        observation_id=stable_id(
                            "workload", primary_id, evidence_id, workload.value
                        ),
                        entity_id=primary_id,
                        workload=workload,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_explicit_classification_tag",
                        confidence=0.65,
                    )

                if status in {LifecycleStatus.PROPOSED, LifecycleStatus.UNDER_CONSTRUCTION}:
                    project_key = f"{stable_key}:development-project"
                    project_id = stable_id("entity", project_key, "project")
                    entities_created += int(
                        add_project(
                            connection,
                            Project(project_id, project_key, evidence_id, primary_id),
                            created_at=retrieved_at,
                        )
                    )
                    add_snapshot(
                        connection,
                        snapshot_id=stable_id("snapshot", project_id, evidence_id),
                        entity_id=project_id,
                        name=f"{name} development project",
                        latitude=latitude,
                        longitude=longitude,
                        geometry=geometry,
                        tags=tags,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_lifecycle_project",
                        confidence=status_confidence,
                    )
                    add_lifecycle(
                        connection,
                        LifecycleObservation(
                            id=stable_id("lifecycle", project_id, evidence_id, status.value),
                            entity_id=project_id,
                            status=status,
                            evidence_id=evidence_id,
                            as_of_date=as_of_date,
                            recorded_at=retrieved_at,
                            method=status_method,
                            confidence=status_confidence,
                        ),
                    )

                imported += 1

        return ImportResult(
            source=self.source_name,
            examined_elements=len(elements),
            imported_elements=imported,
            skipped_elements=skipped,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )
