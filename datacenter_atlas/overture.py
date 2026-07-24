"""Bounded Overture building-footprint discovery bundles.

This module retains the exact bounded GeoJSONSeq fetch, derives transparent
shape measurements with the Python standard library, and emits review-only
large/industrial building candidates.  It never promotes a footprint to a
data-centre identity, lifecycle, operating-status, or power claim.
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import uuid


SOURCE_FILENAME = "buildings.geojsonseq"
FETCH_STATE_FILENAME = "fetch-state.json"
ATLAS_REFERENCE_FILENAME = "atlas-reference.jsonl"
CANDIDATES_FILENAME = "candidates.geojsonseq"
CANDIDATES_CSV_FILENAME = "candidates.csv"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_SCHEMA_VERSION = 1
OVERTURE_RELEASE = "2026-06-17.0"
OVERTURE_SCHEMA_VERSION = "v1.17.0"
OVERTURE_CLI_VERSION = "1.0.1"
OVERTURE_THEME = "buildings"
OVERTURE_TYPE = "building"
OVERTURE_FORMAT = "geojsonseq"
OVERTURE_S3_PATH = (
    "s3://overturemaps-us-west-2/release/2026-06-17.0/"
    "theme=buildings/type=building/*"
)
OVERTURE_BUILDINGS_URL = "https://docs.overturemaps.org/guides/buildings/"
OVERTURE_RELEASE_URL = (
    "https://docs.overturemaps.org/blog/2026/06/17/release-notes/"
)
OVERTURE_ATTRIBUTION_URL = "https://docs.overturemaps.org/attribution/"
OVERTURE_GERS_URL = "https://docs.overturemaps.org/gers/"
OVERTURE_CLI_URL = "https://github.com/OvertureMaps/overturemaps-py"
OVERTURE_ATTRIBUTION = "© OpenStreetMap contributors, Overture Maps Foundation"
OVERTURE_THEME_LICENSE = "ODbL-1.0"
EARTH_MEAN_RADIUS_METRES = 6_371_008.8
BBOX_VALIDATION_TOLERANCE_DEGREES = 0.00001
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OSM_STABLE_KEY_RE = re.compile(r"^osm:(node|way|relation)/(\d+)$")
_OSM_URL_RE = re.compile(r"^https://www\.openstreetmap\.org/(node|way|relation)/(\d+)$")
_OSM_RECORD_RE = re.compile(r"^([nwr])(\d+)@(\d+)$")
_OSM_TYPE = {"n": "node", "w": "way", "r": "relation"}
_SOURCE_KEYS = {
    "property",
    "dataset",
    "license",
    "record_id",
    "update_time",
    "confidence",
    "between",
}
INDUSTRIAL_LABELS = frozenset(
    {"factory", "hangar", "industrial", "manufacturing", "warehouse"}
)
REVIEW_CONSTRAINTS = {
    "purpose": "blind_building_footprint_discovery_review",
    "bounded_bbox_not_global_coverage": True,
    "candidate_is_not_data_centre_identity": True,
    "candidate_is_not_lifecycle_or_status_claim": True,
    "candidate_is_not_operating_status_claim": True,
    "candidate_is_not_power_or_energy_claim": True,
    "candidate_is_not_automatic_atlas_import": True,
    "atlas_cross_reference_is_non_merging": True,
    "independent_review_required": True,
}


class OvertureValidationError(ValueError):
    """Raised when a pinned Overture input or bundle violates its contract."""


@dataclass(frozen=True, slots=True)
class OvertureConfig:
    bbox: tuple[float, float, float, float] = (-90.10, 34.95, -89.95, 35.10)
    release: str = OVERTURE_RELEASE
    cli_version: str = OVERTURE_CLI_VERSION
    minimum_large_area_m2: float = 10_000.0
    minimum_very_large_area_m2: float = 25_000.0
    near_distance_m: float = 100.0
    possible_distance_m: float = 500.0
    novel_distance_m: float = 2_000.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bbox, tuple)
            or len(self.bbox) != 4
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in self.bbox
            )
        ):
            raise OvertureValidationError("Overture bbox must contain four finite numbers")
        xmin, ymin, xmax, ymax = (float(value) for value in self.bbox)
        if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
            raise OvertureValidationError("Overture bbox bounds or ordering are invalid")
        object.__setattr__(self, "bbox", (xmin, ymin, xmax, ymax))
        if self.release != OVERTURE_RELEASE:
            raise OvertureValidationError(
                f"this lane is pinned to Overture release {OVERTURE_RELEASE}"
            )
        if self.cli_version != OVERTURE_CLI_VERSION:
            raise OvertureValidationError(
                f"this lane is pinned to overturemaps CLI {OVERTURE_CLI_VERSION}"
            )
        numbers = (
            self.minimum_large_area_m2,
            self.minimum_very_large_area_m2,
            self.near_distance_m,
            self.possible_distance_m,
            self.novel_distance_m,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0
            for value in numbers
        ):
            raise OvertureValidationError("Overture thresholds must be finite and positive")
        if self.minimum_very_large_area_m2 < self.minimum_large_area_m2:
            raise OvertureValidationError("very-large area must be at least the large area")
        if not self.near_distance_m < self.possible_distance_m < self.novel_distance_m:
            raise OvertureValidationError("Overture distance thresholds must increase")

    def selection_document(self) -> dict[str, Any]:
        return {
            "algorithm": (
                "area_gte_very_large_or_area_gte_large_and_explicit_industrial_label"
            ),
            "minimum_large_area_m2": float(self.minimum_large_area_m2),
            "minimum_very_large_area_m2": float(self.minimum_very_large_area_m2),
            "industrial_class_or_subtype_labels": sorted(INDUSTRIAL_LABELS),
            "geometry_measurement": {
                "area": "local_equirectangular_shoelace_outer_minus_holes",
                "rectangularity": "footprint_area_divided_by_axis_aligned_bbox_area",
                "earth_mean_radius_metres": EARTH_MEAN_RADIUS_METRES,
                "approximate": True,
            },
        }

    def distance_document(self) -> dict[str, Any]:
        return {
            "algorithm": "haversine_from_derived_footprint_centroid",
            "near_distance_m": float(self.near_distance_m),
            "possible_distance_m": float(self.possible_distance_m),
            "novel_distance_m": float(self.novel_distance_m),
            "novel_means_only": (
                "no exact upstream OSM identity and no v3 atlas coordinate within threshold"
            ),
        }


@dataclass(frozen=True, slots=True)
class GeometryMetrics:
    area_m2: float
    rectangularity: float
    centroid_longitude: float
    centroid_latitude: float
    bbox: tuple[float, float, float, float]
    rings: int
    vertices: int
    geometry_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "approximate_footprint_area_m2": round(self.area_m2, 3),
            "axis_aligned_rectangularity": round(self.rectangularity, 6),
            "derived_centroid": {
                "longitude": round(self.centroid_longitude, 7),
                "latitude": round(self.centroid_latitude, 7),
            },
            "geometry_bbox": [round(value, 7) for value in self.bbox],
            "geometry_type": self.geometry_type,
            "ring_count": self.rings,
            "vertex_count_including_ring_closures": self.vertices,
        }


def _canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        return (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OvertureValidationError(f"{field} must be a non-empty RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OvertureValidationError(f"{field} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OvertureValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _raw_record(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _coordinate(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) < 2:
        raise OvertureValidationError(f"{field} must contain longitude and latitude")
    longitude, latitude = value[:2]
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in (longitude, latitude)
    ):
        raise OvertureValidationError(f"{field} coordinate values must be finite numbers")
    longitude, latitude = float(longitude), float(latitude)
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise OvertureValidationError(f"{field} coordinate falls outside WGS84 bounds")
    return longitude, latitude


def _polygons(geometry: Any) -> list[list[list[Any]]]:
    if not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"}:
        raise OvertureValidationError("Overture geometry has unexpected fields")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        raise OvertureValidationError(
            "Overture building geometry must be Polygon or MultiPolygon"
        )
    if not isinstance(polygons, list) or not polygons:
        raise OvertureValidationError("Overture building geometry has no polygons")
    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise OvertureValidationError(
                f"Overture polygon {polygon_index} has no rings"
            )
        for ring_index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4:
                raise OvertureValidationError(
                    f"Overture polygon {polygon_index} ring {ring_index} is too short"
                )
            first = _coordinate(ring[0], "Overture ring first vertex")
            last = _coordinate(ring[-1], "Overture ring last vertex")
            if first != last:
                raise OvertureValidationError("Overture polygon ring is not closed")
            for vertex_index, vertex in enumerate(ring):
                _coordinate(vertex, f"Overture ring vertex {vertex_index}")
    return polygons


def _ring_measurement(
    ring: Sequence[Any], *, longitude_origin: float, latitude_origin: float
) -> tuple[float, float, float]:
    cosine = math.cos(math.radians(latitude_origin))
    projected = [
        (
            EARTH_MEAN_RADIUS_METRES
            * math.radians(longitude - longitude_origin)
            * cosine,
            EARTH_MEAN_RADIUS_METRES * math.radians(latitude - latitude_origin),
        )
        for longitude, latitude in (
            _coordinate(vertex, "Overture ring vertex") for vertex in ring
        )
    ]
    cross_sum = 0.0
    centroid_x_sum = 0.0
    centroid_y_sum = 0.0
    for (x1, y1), (x2, y2) in zip(projected, projected[1:]):
        cross = x1 * y2 - x2 * y1
        cross_sum += cross
        centroid_x_sum += (x1 + x2) * cross
        centroid_y_sum += (y1 + y2) * cross
    signed_area = cross_sum / 2.0
    if abs(signed_area) <= 1e-9:
        raise OvertureValidationError("Overture polygon ring has zero projected area")
    centroid_x = centroid_x_sum / (6.0 * signed_area)
    centroid_y = centroid_y_sum / (6.0 * signed_area)
    return abs(signed_area), centroid_x, centroid_y


def geometry_metrics(geometry: Any) -> GeometryMetrics:
    """Measure a full Polygon/MultiPolygon without changing its coordinates."""
    polygons = _polygons(geometry)
    coordinates = [
        _coordinate(vertex, "Overture geometry vertex")
        for polygon in polygons
        for ring in polygon
        for vertex in ring
    ]
    longitude_origin = sum(point[0] for point in coordinates) / len(coordinates)
    latitude_origin = sum(point[1] for point in coordinates) / len(coordinates)
    weighted_x = 0.0
    weighted_y = 0.0
    total_area = 0.0
    for polygon in polygons:
        outer_area, outer_x, outer_y = _ring_measurement(
            polygon[0],
            longitude_origin=longitude_origin,
            latitude_origin=latitude_origin,
        )
        polygon_area = outer_area
        polygon_x = outer_area * outer_x
        polygon_y = outer_area * outer_y
        for hole in polygon[1:]:
            hole_area, hole_x, hole_y = _ring_measurement(
                hole,
                longitude_origin=longitude_origin,
                latitude_origin=latitude_origin,
            )
            polygon_area -= hole_area
            polygon_x -= hole_area * hole_x
            polygon_y -= hole_area * hole_y
        if polygon_area <= 0:
            raise OvertureValidationError("Overture polygon holes consume its outer ring")
        total_area += polygon_area
        weighted_x += polygon_x
        weighted_y += polygon_y
    centroid_x = weighted_x / total_area
    centroid_y = weighted_y / total_area
    cosine = math.cos(math.radians(latitude_origin))
    centroid_longitude = longitude_origin + math.degrees(
        centroid_x / (EARTH_MEAN_RADIUS_METRES * cosine)
    )
    centroid_latitude = latitude_origin + math.degrees(
        centroid_y / EARTH_MEAN_RADIUS_METRES
    )
    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]
    xmin, xmax = min(longitudes), max(longitudes)
    ymin, ymax = min(latitudes), max(latitudes)
    width = EARTH_MEAN_RADIUS_METRES * math.radians(xmax - xmin) * cosine
    height = EARTH_MEAN_RADIUS_METRES * math.radians(ymax - ymin)
    bbox_area = width * height
    if bbox_area <= 0:
        raise OvertureValidationError("Overture building bounding box has zero area")
    rectangularity = total_area / bbox_area
    if not 0 < rectangularity <= 1.000001:
        raise OvertureValidationError("Overture rectangularity falls outside (0, 1]")
    return GeometryMetrics(
        area_m2=total_area,
        rectangularity=min(1.0, rectangularity),
        centroid_longitude=centroid_longitude,
        centroid_latitude=centroid_latitude,
        bbox=(xmin, ymin, xmax, ymax),
        rings=sum(len(polygon) for polygon in polygons),
        vertices=len(coordinates),
        geometry_type=str(geometry["type"]),
    )


def _haversine_metres(
    longitude_a: float,
    latitude_a: float,
    longitude_b: float,
    latitude_b: float,
) -> float:
    latitude_a_radians = math.radians(latitude_a)
    latitude_b_radians = math.radians(latitude_b)
    latitude_delta = latitude_b_radians - latitude_a_radians
    longitude_delta = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_a_radians)
        * math.cos(latitude_b_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_METRES * math.asin(min(1.0, math.sqrt(value)))


def _bbox_text(bbox: Sequence[float]) -> str:
    return ",".join(f"{value:.10f}".rstrip("0").rstrip(".") for value in bbox)


def _fetch_command(config: OvertureConfig) -> list[str]:
    return [
        "uvx",
        "--from",
        f"overturemaps=={config.cli_version}",
        "overturemaps",
        "download",
        f"--bbox={_bbox_text(config.bbox)}",
        "-f",
        OVERTURE_FORMAT,
        f"--type={OVERTURE_TYPE}",
        f"--release={config.release}",
        "--output",
        SOURCE_FILENAME,
    ]


def _read_fetch_state(path: Path, config: OvertureConfig) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise OvertureValidationError("Overture fetch state must be a regular file")
    raw = path.read_bytes()
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OvertureValidationError("Overture fetch state is not valid JSON") from error
    expected_keys = {
        "last_release",
        "last_run",
        "theme",
        "type",
        "bbox",
        "backend",
        "output",
    }
    if not isinstance(state, dict) or set(state) != expected_keys:
        raise OvertureValidationError("Overture fetch state has unexpected fields")
    if state.get("last_release") != config.release:
        raise OvertureValidationError("Overture fetch state release does not match its pin")
    if state.get("theme") != OVERTURE_THEME or state.get("type") != OVERTURE_TYPE:
        raise OvertureValidationError("Overture fetch state theme/type changed")
    if state.get("backend") != OVERTURE_FORMAT:
        raise OvertureValidationError("Overture fetch state backend is not GeoJSONSeq")
    _timestamp(state.get("last_run"), "Overture fetch state last_run")
    output = state.get("output")
    if not isinstance(output, str) or not output:
        raise OvertureValidationError("Overture fetch state output is invalid")
    bbox = state.get("bbox")
    expected_bbox = dict(zip(("xmin", "ymin", "xmax", "ymax"), config.bbox))
    if not isinstance(bbox, dict) or set(bbox) != set(expected_bbox):
        raise OvertureValidationError("Overture fetch state bbox is invalid")
    if any(
        isinstance(bbox[key], bool)
        or not isinstance(bbox[key], (int, float))
        or float(bbox[key]) != expected
        for key, expected in expected_bbox.items()
    ):
        raise OvertureValidationError("Overture fetch state bbox changed")
    return raw, state


def _upstream_osm_identities(properties: Mapping[str, Any]) -> list[str]:
    identities: set[str] = set()
    stable_key = properties.get("stable_key")
    if isinstance(stable_key, str):
        match = _OSM_STABLE_KEY_RE.fullmatch(stable_key)
        if match is not None:
            identities.add(f"{match.group(1)}/{int(match.group(2))}")
    source_url = properties.get("source_url")
    if isinstance(source_url, str):
        match = _OSM_URL_RE.fullmatch(source_url)
        if match is not None:
            identities.add(f"{match.group(1)}/{int(match.group(2))}")
    return sorted(identities)


def _atlas_references(
    atlas_path: Path,
    atlas_manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if atlas_path.is_symlink() or not atlas_path.is_file():
        raise OvertureValidationError("v3 atlas input must be a regular file")
    if atlas_manifest_path.is_symlink() or not atlas_manifest_path.is_file():
        raise OvertureValidationError("v3 release manifest must be a regular file")
    atlas_raw = atlas_path.read_bytes()
    manifest_raw = atlas_manifest_path.read_bytes()
    try:
        atlas = json.loads(atlas_raw)
        release_manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise OvertureValidationError("v3 atlas lineage is not valid JSON") from error
    if (
        not isinstance(atlas, dict)
        or atlas.get("type") != "FeatureCollection"
        or not isinstance(atlas.get("features"), list)
    ):
        raise OvertureValidationError("v3 atlas input is not a FeatureCollection")
    atlas_record = _raw_record(atlas_raw)
    release_record = _raw_record(manifest_raw)
    expected_atlas = (
        release_manifest.get("files", {}).get(atlas_path.name)
        if isinstance(release_manifest, dict)
        else None
    )
    if expected_atlas != atlas_record:
        raise OvertureValidationError("v3 release manifest does not bind atlas.geojson")
    references: list[dict[str, Any]] = []
    entity_ids: set[str] = set()
    for index, feature in enumerate(atlas["features"], start=1):
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise OvertureValidationError(f"v3 atlas feature {index} is invalid")
        properties = feature["properties"]
        longitude = properties.get("longitude")
        latitude = properties.get("latitude")
        if (
            isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
        ):
            continue
        longitude, latitude = float(longitude), float(latitude)
        if (
            not math.isfinite(longitude)
            or not math.isfinite(latitude)
            or not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
        ):
            raise OvertureValidationError(f"v3 atlas feature {index} coordinates are invalid")
        entity_id = properties.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id or entity_id in entity_ids:
            raise OvertureValidationError(f"v3 atlas feature {index} entity ID is invalid")
        entity_ids.add(entity_id)
        references.append(
            {
                "entity_id": entity_id,
                "entity_kind": properties.get("entity_kind"),
                "name": properties.get("name"),
                "longitude": longitude,
                "latitude": latitude,
                "stable_key": properties.get("stable_key"),
                "source_family": properties.get("source_family"),
                "source_url": properties.get("source_url"),
                "upstream_osm_identities": _upstream_osm_identities(properties),
            }
        )
    references.sort(key=lambda item: item["entity_id"])
    lineage = {
        "release_directory": atlas_path.parent.name,
        "atlas_as_of": atlas.get("atlas_as_of"),
        "atlas_recorded_at": _timestamp(
            atlas.get("atlas_recorded_at"), "v3 atlas recorded_at"
        ),
        "atlas_feature_count": len(atlas["features"]),
        "coordinate_reference_count": len(references),
        "atlas_file": {"filename": atlas_path.name, **atlas_record},
        "release_manifest": {
            "filename": atlas_manifest_path.name,
            **release_record,
        },
    }
    return references, lineage


def _atlas_reference_bytes(references: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json(dict(reference)) for reference in references)


def _parse_atlas_reference_bytes(raw: bytes) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    entity_ids: set[str] = set()
    for line_number, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.endswith(b"\n"):
            raise OvertureValidationError(
                f"atlas-reference line {line_number} lacks a newline"
            )
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise OvertureValidationError(
                f"atlas-reference line {line_number} is invalid JSON"
            ) from error
        if line != _canonical_json(value):
            raise OvertureValidationError(
                f"atlas-reference line {line_number} is not canonical"
            )
        expected_keys = {
            "entity_id",
            "entity_kind",
            "name",
            "longitude",
            "latitude",
            "stable_key",
            "source_family",
            "source_url",
            "upstream_osm_identities",
        }
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise OvertureValidationError(
                f"atlas-reference line {line_number} has unexpected fields"
            )
        entity_id = value.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id or entity_id in entity_ids:
            raise OvertureValidationError(
                f"atlas-reference line {line_number} has an invalid entity ID"
            )
        entity_ids.add(entity_id)
        identities = value.get("upstream_osm_identities")
        if (
            not isinstance(identities, list)
            or identities != sorted(set(identities))
            or any(
                not isinstance(identity, str)
                or not re.fullmatch(r"(?:node|way|relation)/[0-9]+", identity)
                for identity in identities
            )
        ):
            raise OvertureValidationError(
                f"atlas-reference line {line_number} identities are invalid"
            )
        for field in ("longitude", "latitude"):
            number = value.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise OvertureValidationError(
                    f"atlas-reference line {line_number} coordinate is invalid"
                )
        references.append(value)
    if references != sorted(references, key=lambda item: item["entity_id"]):
        raise OvertureValidationError("atlas-reference records are not entity-ID sorted")
    return references


def _iter_source_features(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if path.is_symlink() or not path.is_file():
        raise OvertureValidationError("Overture GeoJSONSeq source must be a regular file")
    with path.open("rb") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.endswith(b"\n"):
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} lacks a newline"
                )
            payload = raw_line[1:] if raw_line.startswith(b"\x1e") else raw_line
            try:
                value = json.loads(payload)
            except json.JSONDecodeError as error:
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} is invalid JSON"
                ) from error
            if not isinstance(value, dict) or set(value) != {
                "id",
                "type",
                "geometry",
                "properties",
            }:
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} has unexpected fields"
                )
            if value.get("type") != "Feature" or not isinstance(
                value.get("properties"), dict
            ):
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} is not a feature"
                )
            gers_id = value.get("id")
            try:
                parsed_id = uuid.UUID(str(gers_id))
            except (ValueError, AttributeError) as error:
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} GERS ID is invalid"
                ) from error
            if str(parsed_id) != gers_id:
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} GERS ID is not canonical"
                )
            sources = value["properties"].get("sources")
            if not isinstance(sources, list) or not sources:
                raise OvertureValidationError(
                    f"Overture GeoJSONSeq line {line_number} has no sources"
                )
            for source_index, source_item in enumerate(sources):
                if not isinstance(source_item, dict) or set(source_item) != _SOURCE_KEYS:
                    raise OvertureValidationError(
                        f"Overture line {line_number} source {source_index} schema changed"
                    )
                if any(
                    not isinstance(source_item.get(field), str)
                    or not source_item[field]
                    for field in ("dataset", "license", "update_time")
                ):
                    raise OvertureValidationError(
                        f"Overture line {line_number} source {source_index} is incomplete"
                    )
                _timestamp(
                    source_item["update_time"],
                    f"Overture line {line_number} source {source_index} update_time",
                )
            yield line_number, value


def _overture_osm_identities(properties: Mapping[str, Any]) -> list[str]:
    identities: set[str] = set()
    for source in properties.get("sources", []):
        if not isinstance(source, Mapping) or source.get("dataset") != "OpenStreetMap":
            continue
        record_id = source.get("record_id")
        if not isinstance(record_id, str):
            continue
        match = _OSM_RECORD_RE.fullmatch(record_id)
        if match is not None:
            identities.add(f"{_OSM_TYPE[match.group(1)]}/{int(match.group(2))}")
    return sorted(identities)


def _source_freshness(
    sources: Sequence[Mapping[str, Any]], generated_at: str
) -> dict[str, Any]:
    timestamps = sorted(
        _timestamp(source["update_time"], "Overture source update_time")
        for source in sources
    )
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    latest = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
    return {
        "earliest_source_update_time": timestamps[0],
        "latest_source_update_time": timestamps[-1],
        "latest_source_age_days_at_generation": round(
            (generated - latest).total_seconds() / 86_400, 3
        ),
    }


def _compact_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": reference["entity_id"],
        "entity_kind": reference["entity_kind"],
        "name": reference["name"],
        "longitude": reference["longitude"],
        "latitude": reference["latitude"],
        "stable_key": reference["stable_key"],
        "source_family": reference["source_family"],
        "source_url": reference["source_url"],
        "upstream_osm_identities": reference["upstream_osm_identities"],
    }


def _cross_reference(
    metrics: GeometryMetrics,
    properties: Mapping[str, Any],
    atlas_references: Sequence[Mapping[str, Any]],
    identity_index: Mapping[str, Sequence[Mapping[str, Any]]],
    config: OvertureConfig,
) -> dict[str, Any]:
    overture_identities = _overture_osm_identities(properties)
    exact = {
        reference["entity_id"]: reference
        for identity in overture_identities
        for reference in identity_index.get(identity, ())
    }
    nearest_reference: Mapping[str, Any] | None = None
    nearest_distance: float | None = None
    for reference in atlas_references:
        distance = _haversine_metres(
            metrics.centroid_longitude,
            metrics.centroid_latitude,
            float(reference["longitude"]),
            float(reference["latitude"]),
        )
        if nearest_distance is None or (distance, reference["entity_id"]) < (
            nearest_distance,
            nearest_reference["entity_id"],
        ):
            nearest_distance = distance
            nearest_reference = reference
    if exact:
        label = "known_exact_upstream_osm_identity"
    elif nearest_distance is not None and nearest_distance <= config.near_distance_m:
        label = "known_v3_coordinate_within_100m"
    elif nearest_distance is not None and nearest_distance <= config.possible_distance_m:
        label = "near_v3_coordinate_within_500m"
    elif nearest_distance is not None and nearest_distance <= config.novel_distance_m:
        label = "near_v3_coordinate_within_2km"
    else:
        label = "novel_to_v3_atlas_no_coordinate_within_2km"
    nearest = None
    if nearest_reference is not None and nearest_distance is not None:
        nearest = {
            **_compact_reference(nearest_reference),
            "distance_m": round(nearest_distance, 3),
        }
    return {
        "label": label,
        "overture_upstream_osm_identities": overture_identities,
        "exact_upstream_osm_matches": [
            _compact_reference(reference)
            for reference in sorted(exact.values(), key=lambda item: item["entity_id"])
        ],
        "nearest_v3_atlas_coordinate": nearest,
        "atlas_merge_performed": False,
        "novel_label_is_only_relative_to_v3_atlas": True,
    }


def _selection(
    metrics: GeometryMetrics,
    properties: Mapping[str, Any],
    config: OvertureConfig,
) -> tuple[bool, list[str], bool]:
    labels = {
        str(properties.get(field)).strip().casefold()
        for field in ("class", "subtype")
        if isinstance(properties.get(field), str) and properties[field].strip()
    }
    industrial = bool(labels & INDUSTRIAL_LABELS)
    large = metrics.area_m2 >= config.minimum_large_area_m2
    very_large = metrics.area_m2 >= config.minimum_very_large_area_m2
    reasons: list[str] = []
    if large:
        reasons.append(
            f"area_gte_{_bbox_text((config.minimum_large_area_m2,))}_m2"
        )
    if very_large:
        reasons.append(
            f"area_gte_{_bbox_text((config.minimum_very_large_area_m2,))}_m2"
        )
    for label in sorted(labels & INDUSTRIAL_LABELS):
        reasons.append(f"explicit_industrial_class_or_subtype:{label}")
    return very_large or (large and industrial), reasons, industrial


def _priority(cross_reference: Mapping[str, Any], industrial: bool) -> dict[str, Any]:
    label = cross_reference["label"]
    if label == "novel_to_v3_atlas_no_coordinate_within_2km" and industrial:
        return {"rank": 1, "tier": "novel_industrial_label"}
    if label == "novel_to_v3_atlas_no_coordinate_within_2km":
        return {"rank": 2, "tier": "novel_very_large_footprint"}
    if label == "known_exact_upstream_osm_identity":
        return {"rank": 4, "tier": "exact_known_upstream_identity"}
    return {"rank": 3, "tier": "near_known_atlas_coordinate"}


def _candidate(
    feature: Mapping[str, Any],
    metrics: GeometryMetrics,
    reasons: Sequence[str],
    industrial: bool,
    atlas_references: Sequence[Mapping[str, Any]],
    identity_index: Mapping[str, Sequence[Mapping[str, Any]]],
    config: OvertureConfig,
    generated_at: str,
) -> dict[str, Any]:
    properties = feature["properties"]
    cross_reference = _cross_reference(
        metrics, properties, atlas_references, identity_index, config
    )
    return {
        "type": "Feature",
        "id": feature["id"],
        "geometry": feature["geometry"],
        "properties": {
            "gers_id": feature["id"],
            "overture_release": config.release,
            "overture_theme": OVERTURE_THEME,
            "overture_type": OVERTURE_TYPE,
            "overture_properties": properties,
            "measurements": metrics.as_dict(),
            "source_freshness": _source_freshness(
                properties["sources"], generated_at
            ),
            "selection": {
                "selected": True,
                "reasons": list(reasons),
                "explicit_industrial_label": industrial,
            },
            "atlas_cross_reference": cross_reference,
            "review_priority": _priority(cross_reference, industrial),
            "review_constraints": dict(REVIEW_CONSTRAINTS),
        },
    }


def _source_inventory_document(
    inventory: Mapping[tuple[str, str], Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for (dataset, license_name), stats in sorted(inventory.items()):
        result.append(
            {
                "dataset": dataset,
                "license": license_name,
                "feature_references": stats["feature_references"],
                "source_property_references": stats["source_property_references"],
                "references_with_record_id": stats["references_with_record_id"],
                "distinct_record_ids": len(stats["record_ids"]),
                "earliest_update_time": min(stats["update_times"]),
                "latest_update_time": max(stats["update_times"]),
                "properties": sorted(stats["properties"]),
            }
        )
    return result


_CSV_FIELDS = (
    "review_priority_rank",
    "review_priority_tier",
    "gers_id",
    "primary_name",
    "building_class",
    "building_subtype",
    "approximate_footprint_area_m2",
    "axis_aligned_rectangularity",
    "centroid_longitude",
    "centroid_latitude",
    "latest_source_update_time",
    "atlas_cross_reference_label",
    "nearest_v3_atlas_distance_m",
    "exact_upstream_osm_entity_ids_json",
    "selection_reasons_json",
    "source_datasets_json",
    "source_licenses_json",
    "review_only",
    "data_centre_identity_inferred",
    "lifecycle_or_status_inferred",
    "power_or_energy_inferred",
)


def _candidate_csv(candidates: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for candidate in candidates:
        properties = candidate["properties"]
        overture = properties["overture_properties"]
        measurements = properties["measurements"]
        cross_reference = properties["atlas_cross_reference"]
        nearest = cross_reference["nearest_v3_atlas_coordinate"]
        names = overture.get("names")
        primary_name = names.get("primary") if isinstance(names, Mapping) else None
        sources = overture["sources"]
        writer.writerow(
            {
                "review_priority_rank": properties["review_priority"]["rank"],
                "review_priority_tier": properties["review_priority"]["tier"],
                "gers_id": candidate["id"],
                "primary_name": primary_name,
                "building_class": overture.get("class"),
                "building_subtype": overture.get("subtype"),
                "approximate_footprint_area_m2": measurements[
                    "approximate_footprint_area_m2"
                ],
                "axis_aligned_rectangularity": measurements[
                    "axis_aligned_rectangularity"
                ],
                "centroid_longitude": measurements["derived_centroid"]["longitude"],
                "centroid_latitude": measurements["derived_centroid"]["latitude"],
                "latest_source_update_time": properties["source_freshness"][
                    "latest_source_update_time"
                ],
                "atlas_cross_reference_label": cross_reference["label"],
                "nearest_v3_atlas_distance_m": (
                    nearest["distance_m"] if nearest is not None else None
                ),
                "exact_upstream_osm_entity_ids_json": json.dumps(
                    [
                        item["entity_id"]
                        for item in cross_reference["exact_upstream_osm_matches"]
                    ],
                    separators=(",", ":"),
                ),
                "selection_reasons_json": json.dumps(
                    properties["selection"]["reasons"], separators=(",", ":")
                ),
                "source_datasets_json": json.dumps(
                    sorted({source["dataset"] for source in sources}),
                    separators=(",", ":"),
                ),
                "source_licenses_json": json.dumps(
                    sorted({source["license"] for source in sources}),
                    separators=(",", ":"),
                ),
                "review_only": "true",
                "data_centre_identity_inferred": "false",
                "lifecycle_or_status_inferred": "false",
                "power_or_energy_inferred": "false",
            }
        )
    return stream.getvalue().encode("utf-8")


def _derive_candidates(
    source_path: Path,
    atlas_references: Sequence[Mapping[str, Any]],
    *,
    config: OvertureConfig,
    generated_at: str,
) -> tuple[bytes, bytes, dict[str, Any], list[dict[str, Any]]]:
    identity_index: dict[str, list[Mapping[str, Any]]] = {}
    for reference in atlas_references:
        for identity in reference["upstream_osm_identities"]:
            identity_index.setdefault(identity, []).append(reference)
    for references in identity_index.values():
        references.sort(key=lambda item: item["entity_id"])

    gers_ids: set[str] = set()
    inventory: dict[tuple[str, str], dict[str, Any]] = {}
    geometry_types: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    features_intersecting_bbox = 0
    features_extending_outside_bbox = 0
    features_just_outside_bbox_within_tolerance = 0
    total_source_references = 0
    xmin, ymin, xmax, ymax = config.bbox
    for line_number, feature in _iter_source_features(source_path):
        gers_id = feature["id"]
        if gers_id in gers_ids:
            raise OvertureValidationError(
                f"Overture GeoJSONSeq line {line_number} repeats GERS ID {gers_id}"
            )
        gers_ids.add(gers_id)
        metrics = geometry_metrics(feature["geometry"])
        geometry_types[metrics.geometry_type] += 1
        gxmin, gymin, gxmax, gymax = metrics.bbox
        intersects = gxmax >= xmin and gxmin <= xmax and gymax >= ymin and gymin <= ymax
        intersects_with_tolerance = (
            gxmax >= xmin - BBOX_VALIDATION_TOLERANCE_DEGREES
            and gxmin <= xmax + BBOX_VALIDATION_TOLERANCE_DEGREES
            and gymax >= ymin - BBOX_VALIDATION_TOLERANCE_DEGREES
            and gymin <= ymax + BBOX_VALIDATION_TOLERANCE_DEGREES
        )
        if not intersects_with_tolerance:
            raise OvertureValidationError(
                f"Overture GeoJSONSeq line {line_number} does not intersect pinned bbox"
            )
        if intersects:
            features_intersecting_bbox += 1
        else:
            features_just_outside_bbox_within_tolerance += 1
        if gxmin < xmin or gymin < ymin or gxmax > xmax or gymax > ymax:
            features_extending_outside_bbox += 1

        feature_inventory_keys: set[tuple[str, str]] = set()
        for source in feature["properties"]["sources"]:
            key = (source["dataset"], source["license"])
            stats = inventory.setdefault(
                key,
                {
                    "feature_references": 0,
                    "source_property_references": 0,
                    "references_with_record_id": 0,
                    "record_ids": set(),
                    "update_times": [],
                    "properties": set(),
                },
            )
            stats["source_property_references"] += 1
            total_source_references += 1
            feature_inventory_keys.add(key)
            if source["record_id"] is not None:
                if not isinstance(source["record_id"], str) or not source["record_id"]:
                    raise OvertureValidationError(
                        f"Overture line {line_number} source record ID is invalid"
                    )
                stats["references_with_record_id"] += 1
                stats["record_ids"].add(source["record_id"])
            stats["update_times"].append(
                _timestamp(source["update_time"], "Overture source update_time")
            )
            source_property = source["property"]
            if not isinstance(source_property, str):
                raise OvertureValidationError(
                    f"Overture line {line_number} source property is invalid"
                )
            stats["properties"].add(source_property)
        for key in feature_inventory_keys:
            inventory[key]["feature_references"] += 1

        selected, reasons, industrial = _selection(
            metrics, feature["properties"], config
        )
        if selected:
            candidates.append(
                _candidate(
                    feature,
                    metrics,
                    reasons,
                    industrial,
                    atlas_references,
                    identity_index,
                    config,
                    generated_at,
                )
            )

    candidates.sort(
        key=lambda item: (
            item["properties"]["review_priority"]["rank"],
            -item["properties"]["measurements"]["approximate_footprint_area_m2"],
            item["id"],
        )
    )
    candidate_raw = b"".join(_canonical_json(candidate) for candidate in candidates)
    csv_raw = _candidate_csv(candidates)
    labels = Counter(
        candidate["properties"]["atlas_cross_reference"]["label"]
        for candidate in candidates
    )
    tiers = Counter(
        candidate["properties"]["review_priority"]["tier"]
        for candidate in candidates
    )
    stats = {
        "source_features": len(gers_ids),
        "distinct_gers_ids": len(gers_ids),
        "features_intersecting_bbox": features_intersecting_bbox,
        "features_just_outside_bbox_within_0_00001_degree_tolerance": (
            features_just_outside_bbox_within_tolerance
        ),
        "features_extending_outside_bbox": features_extending_outside_bbox,
        "geometry_types": dict(sorted(geometry_types.items())),
        "source_property_references": total_source_references,
        "source_inventory": _source_inventory_document(inventory),
        "candidate_features": len(candidates),
        "candidates_by_atlas_cross_reference_label": dict(sorted(labels.items())),
        "candidates_by_review_priority_tier": dict(sorted(tiers.items())),
    }
    return candidate_raw, csv_raw, stats, candidates


def _artifact(
    raw_or_path: bytes | Path,
    *,
    media_type: str,
    records: int | None = None,
) -> dict[str, Any]:
    record = (
        _raw_record(raw_or_path)
        if isinstance(raw_or_path, bytes)
        else _file_record(raw_or_path)
    )
    result = {"media_type": media_type, **record}
    if records is not None:
        result["records"] = records
    return result


def _manifest_document(
    source_path: Path,
    state_raw: bytes,
    state: Mapping[str, Any],
    atlas_references: Sequence[Mapping[str, Any]],
    atlas_lineage: Mapping[str, Any],
    candidate_raw: bytes,
    candidate_csv: bytes,
    stats: Mapping[str, Any],
    *,
    config: OvertureConfig,
    generated_at: str,
) -> dict[str, Any]:
    atlas_reference_raw = _atlas_reference_bytes(atlas_references)
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "pipeline": "overture_bounded_building_discovery_bundle",
        "generated_at": generated_at,
        "scope": dict(REVIEW_CONSTRAINTS),
        "source": {
            "publisher": "Overture Maps Foundation",
            "release": config.release,
            "schema_version": OVERTURE_SCHEMA_VERSION,
            "theme": OVERTURE_THEME,
            "type": OVERTURE_TYPE,
            "format": OVERTURE_FORMAT,
            "bbox": list(config.bbox),
            "official_s3_path": OVERTURE_S3_PATH,
            "buildings_documentation_url": OVERTURE_BUILDINGS_URL,
            "release_notes_url": OVERTURE_RELEASE_URL,
            "attribution_url": OVERTURE_ATTRIBUTION_URL,
            "gers_documentation_url": OVERTURE_GERS_URL,
            "theme_license": OVERTURE_THEME_LICENSE,
            "attribution": OVERTURE_ATTRIBUTION,
            "cli": {
                "package": "overturemaps",
                "version": config.cli_version,
                "official_repository": OVERTURE_CLI_URL,
                "reproduction_command": _fetch_command(config),
                "executed_command_was_not_captured_by_cli_state": True,
            },
            "fetch_state": dict(state),
            "input_filename": source_path.name,
        },
        "selection": config.selection_document(),
        "atlas_cross_reference": {
            "lineage": dict(atlas_lineage),
            "distance_policy": config.distance_document(),
            "exact_identity_policy": (
                "Overture OpenStreetMap sources record_id mapped to unmerged v3 atlas "
                "explicit OSM stable keys and OpenStreetMap URLs"
            ),
            "candidate_merge_performed": False,
        },
        "counts": {
            key: value
            for key, value in stats.items()
            if key != "source_inventory"
        },
        "source_inventory": stats["source_inventory"],
        "artifacts": {
            SOURCE_FILENAME: _artifact(
                source_path,
                media_type="application/geo+json-seq",
                records=stats["source_features"],
            ),
            FETCH_STATE_FILENAME: _artifact(
                state_raw,
                media_type="application/json",
            ),
            ATLAS_REFERENCE_FILENAME: _artifact(
                atlas_reference_raw,
                media_type="application/x-ndjson",
                records=len(atlas_references),
            ),
            CANDIDATES_FILENAME: _artifact(
                candidate_raw,
                media_type="application/geo+json-seq",
                records=stats["candidate_features"],
            ),
            CANDIDATES_CSV_FILENAME: _artifact(
                candidate_csv,
                media_type="text/csv",
                records=stats["candidate_features"],
            ),
        },
    }


def build_overture_bundle(
    source_path: str | Path,
    fetch_state_path: str | Path,
    atlas_path: str | Path,
    *,
    generated_at: str,
    atlas_manifest_path: str | Path | None = None,
    config: OvertureConfig = OvertureConfig(),
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Build all derived bytes while retaining the source as an exact copied artifact."""
    if not isinstance(config, OvertureConfig):
        raise OvertureValidationError("config must be an OvertureConfig")
    source = Path(source_path)
    state_path = Path(fetch_state_path)
    atlas = Path(atlas_path)
    atlas_manifest = (
        Path(atlas_manifest_path)
        if atlas_manifest_path is not None
        else atlas.with_name(MANIFEST_FILENAME)
    )
    if source.is_symlink() or not source.is_file():
        raise OvertureValidationError("Overture source input must be a regular file")
    generated = _timestamp(generated_at, "Overture bundle generated_at")
    state_raw, state = _read_fetch_state(state_path, config)
    if Path(state["output"]).resolve() != source.resolve():
        raise OvertureValidationError(
            "Overture fetch state output does not identify the supplied source"
        )
    atlas_references, atlas_lineage = _atlas_references(atlas, atlas_manifest)
    atlas_reference_raw = _atlas_reference_bytes(atlas_references)
    candidate_raw, candidate_csv, stats, _ = _derive_candidates(
        source,
        atlas_references,
        config=config,
        generated_at=generated,
    )
    manifest = _manifest_document(
        source,
        state_raw,
        state,
        atlas_references,
        atlas_lineage,
        candidate_raw,
        candidate_csv,
        stats,
        config=config,
        generated_at=generated,
    )
    manifest_raw = _canonical_json(manifest, pretty=True)
    sidecar_raw = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return {
        FETCH_STATE_FILENAME: state_raw,
        ATLAS_REFERENCE_FILENAME: atlas_reference_raw,
        CANDIDATES_FILENAME: candidate_raw,
        CANDIDATES_CSV_FILENAME: candidate_csv,
        MANIFEST_FILENAME: manifest_raw,
        MANIFEST_HASH_FILENAME: sidecar_raw,
    }, manifest


def _config_from_manifest(manifest: Mapping[str, Any]) -> OvertureConfig:
    source = manifest.get("source")
    selection = manifest.get("selection")
    cross_reference = manifest.get("atlas_cross_reference")
    if not all(
        isinstance(value, Mapping)
        for value in (source, selection, cross_reference)
    ):
        raise OvertureValidationError("Overture bundle configuration is missing")
    cli = source.get("cli")
    distance = cross_reference.get("distance_policy")
    if not isinstance(cli, Mapping) or not isinstance(distance, Mapping):
        raise OvertureValidationError("Overture bundle tool or distance pin is missing")
    bbox = source.get("bbox")
    if not isinstance(bbox, list):
        raise OvertureValidationError("Overture bundle bbox is invalid")
    try:
        return OvertureConfig(
            bbox=tuple(bbox),
            release=source.get("release"),
            cli_version=cli.get("version"),
            minimum_large_area_m2=selection.get("minimum_large_area_m2"),
            minimum_very_large_area_m2=selection.get(
                "minimum_very_large_area_m2"
            ),
            near_distance_m=distance.get("near_distance_m"),
            possible_distance_m=distance.get("possible_distance_m"),
            novel_distance_m=distance.get("novel_distance_m"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, OvertureValidationError):
            raise
        raise OvertureValidationError("Overture bundle configuration is invalid") from error


def validate_overture_bundle(
    directory: str | Path,
    *,
    atlas_path: str | Path | None = None,
    atlas_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Rebuild the shortlist from exact bundle inputs and verify every hash."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise OvertureValidationError("Overture bundle must be a regular directory")
    expected_files = {
        SOURCE_FILENAME,
        FETCH_STATE_FILENAME,
        ATLAS_REFERENCE_FILENAME,
        CANDIDATES_FILENAME,
        CANDIDATES_CSV_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != expected_files or len(entries) != len(
        expected_files
    ):
        raise OvertureValidationError("Overture bundle closed file set changed")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OvertureValidationError("Overture bundle contains a non-regular file")
    manifest_raw = (root / MANIFEST_FILENAME).read_bytes()
    sidecar_raw = (root / MANIFEST_HASH_FILENAME).read_bytes()
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise OvertureValidationError("Overture manifest hash sidecar does not match")
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise OvertureValidationError("Overture manifest is not valid JSON") from error
    if manifest_raw != _canonical_json(manifest, pretty=True):
        raise OvertureValidationError("Overture manifest is not canonical JSON")
    expected_manifest_keys = {
        "schema_version",
        "pipeline",
        "generated_at",
        "scope",
        "source",
        "selection",
        "atlas_cross_reference",
        "counts",
        "source_inventory",
        "artifacts",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_manifest_keys:
        raise OvertureValidationError("Overture manifest has unexpected fields")
    if (
        manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION
        or manifest.get("pipeline") != "overture_bounded_building_discovery_bundle"
        or manifest.get("scope") != REVIEW_CONSTRAINTS
    ):
        raise OvertureValidationError("Overture manifest identity or safeguards changed")
    generated = _timestamp(manifest.get("generated_at"), "Overture generated_at")
    config = _config_from_manifest(manifest)
    if manifest.get("selection") != config.selection_document():
        raise OvertureValidationError("Overture selection policy changed")
    cross_reference = manifest.get("atlas_cross_reference")
    exact_identity_policy = (
        "Overture OpenStreetMap sources record_id mapped to unmerged v3 atlas "
        "explicit OSM stable keys and OpenStreetMap URLs"
    )
    if (
        set(cross_reference)
        != {
            "lineage",
            "distance_policy",
            "exact_identity_policy",
            "candidate_merge_performed",
        }
        or cross_reference.get("distance_policy") != config.distance_document()
        or cross_reference.get("exact_identity_policy") != exact_identity_policy
        or cross_reference.get("candidate_merge_performed") is not False
    ):
        raise OvertureValidationError("Overture atlas cross-reference policy changed")
    source = manifest.get("source")
    expected_source_keys = {
        "publisher",
        "release",
        "schema_version",
        "theme",
        "type",
        "format",
        "bbox",
        "official_s3_path",
        "buildings_documentation_url",
        "release_notes_url",
        "attribution_url",
        "gers_documentation_url",
        "theme_license",
        "attribution",
        "cli",
        "fetch_state",
        "input_filename",
    }
    expected_source_fields = {
        "publisher": "Overture Maps Foundation",
        "release": config.release,
        "schema_version": OVERTURE_SCHEMA_VERSION,
        "theme": OVERTURE_THEME,
        "type": OVERTURE_TYPE,
        "format": OVERTURE_FORMAT,
        "bbox": list(config.bbox),
        "official_s3_path": OVERTURE_S3_PATH,
        "buildings_documentation_url": OVERTURE_BUILDINGS_URL,
        "release_notes_url": OVERTURE_RELEASE_URL,
        "attribution_url": OVERTURE_ATTRIBUTION_URL,
        "gers_documentation_url": OVERTURE_GERS_URL,
        "theme_license": OVERTURE_THEME_LICENSE,
        "attribution": OVERTURE_ATTRIBUTION,
        "input_filename": source.get("input_filename"),
    }
    if not isinstance(source, dict) or set(source) != expected_source_keys or any(
        source.get(key) != value for key, value in expected_source_fields.items()
    ):
        raise OvertureValidationError("Overture source lineage changed")
    if not isinstance(source.get("input_filename"), str) or not source["input_filename"]:
        raise OvertureValidationError("Overture original input filename is invalid")
    cli = source.get("cli")
    if cli != {
        "package": "overturemaps",
        "version": config.cli_version,
        "official_repository": OVERTURE_CLI_URL,
        "reproduction_command": _fetch_command(config),
        "executed_command_was_not_captured_by_cli_state": True,
    }:
        raise OvertureValidationError("Overture CLI pin changed")
    state_raw, state = _read_fetch_state(root / FETCH_STATE_FILENAME, config)
    if source.get("fetch_state") != state:
        raise OvertureValidationError("Overture embedded fetch state changed")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_files - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }:
        raise OvertureValidationError("Overture artifact inventory changed")
    for filename, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            raise OvertureValidationError(f"Overture artifact {filename} is invalid")
        record = _file_record(root / filename)
        if any(artifact.get(field) != value for field, value in record.items()):
            raise OvertureValidationError(f"Overture artifact {filename} hash changed")

    atlas_reference_raw = (root / ATLAS_REFERENCE_FILENAME).read_bytes()
    references = _parse_atlas_reference_bytes(atlas_reference_raw)
    lineage = cross_reference.get("lineage")
    if (
        not isinstance(lineage, dict)
        or set(lineage)
        != {
            "release_directory",
            "atlas_as_of",
            "atlas_recorded_at",
            "atlas_feature_count",
            "coordinate_reference_count",
            "atlas_file",
            "release_manifest",
        }
        or lineage.get("release_directory") != "2026-07-18-global-open-v3"
        or lineage.get("atlas_as_of") != "2026-07-18"
        or lineage.get("coordinate_reference_count") != len(references)
    ):
        raise OvertureValidationError("Overture atlas-reference count changed")
    _timestamp(lineage.get("atlas_recorded_at"), "Overture atlas lineage recorded_at")
    atlas_feature_count = lineage.get("atlas_feature_count")
    if (
        isinstance(atlas_feature_count, bool)
        or not isinstance(atlas_feature_count, int)
        or atlas_feature_count < len(references)
    ):
        raise OvertureValidationError("Overture atlas feature count is invalid")
    for field, filename in (
        ("atlas_file", "atlas.geojson"),
        ("release_manifest", MANIFEST_FILENAME),
    ):
        record = lineage.get(field)
        if (
            not isinstance(record, dict)
            or set(record) != {"filename", "bytes", "sha256"}
            or record.get("filename") != filename
            or isinstance(record.get("bytes"), bool)
            or not isinstance(record.get("bytes"), int)
            or record["bytes"] <= 0
            or not isinstance(record.get("sha256"), str)
            or _SHA256_RE.fullmatch(record["sha256"]) is None
        ):
            raise OvertureValidationError(f"Overture atlas lineage {field} is invalid")
    if atlas_path is not None:
        atlas = Path(atlas_path)
        atlas_manifest = (
            Path(atlas_manifest_path)
            if atlas_manifest_path is not None
            else atlas.with_name(MANIFEST_FILENAME)
        )
        live_references, live_lineage = _atlas_references(atlas, atlas_manifest)
        if (
            live_lineage != lineage
            or _atlas_reference_bytes(live_references) != atlas_reference_raw
        ):
            raise OvertureValidationError("Overture v3 atlas cross-reference input changed")

    candidate_raw, candidate_csv, stats, _ = _derive_candidates(
        root / SOURCE_FILENAME,
        references,
        config=config,
        generated_at=generated,
    )
    if candidate_raw != (root / CANDIDATES_FILENAME).read_bytes():
        raise OvertureValidationError("Overture candidate GeoJSONSeq does not reproduce")
    if candidate_csv != (root / CANDIDATES_CSV_FILENAME).read_bytes():
        raise OvertureValidationError("Overture candidate CSV does not reproduce")
    expected_counts = {key: value for key, value in stats.items() if key != "source_inventory"}
    if manifest.get("counts") != expected_counts:
        raise OvertureValidationError("Overture manifest counts do not reproduce")
    if manifest.get("source_inventory") != stats["source_inventory"]:
        raise OvertureValidationError("Overture source inventory does not reproduce")
    expected_artifacts = {
        SOURCE_FILENAME: _artifact(
            root / SOURCE_FILENAME,
            media_type="application/geo+json-seq",
            records=stats["source_features"],
        ),
        FETCH_STATE_FILENAME: _artifact(state_raw, media_type="application/json"),
        ATLAS_REFERENCE_FILENAME: _artifact(
            atlas_reference_raw,
            media_type="application/x-ndjson",
            records=len(references),
        ),
        CANDIDATES_FILENAME: _artifact(
            candidate_raw,
            media_type="application/geo+json-seq",
            records=stats["candidate_features"],
        ),
        CANDIDATES_CSV_FILENAME: _artifact(
            candidate_csv,
            media_type="text/csv",
            records=stats["candidate_features"],
        ),
    }
    if artifacts != expected_artifacts:
        raise OvertureValidationError("Overture artifact metadata does not reproduce")
    return manifest


def _write_fsync(path: Path, raw: bytes) -> None:
    with path.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _copy_fsync(source: Path, destination: Path) -> None:
    with source.open("rb") as input_file, destination.open("wb") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        output_file.flush()
        os.fsync(output_file.fileno())


def write_overture_bundle(
    source_path: str | Path,
    fetch_state_path: str | Path,
    atlas_path: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
    atlas_manifest_path: str | Path | None = None,
    config: OvertureConfig = OvertureConfig(),
) -> dict[str, Any]:
    """Atomically publish a closed, self-validating Overture discovery bundle."""
    source = Path(source_path)
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise OvertureValidationError(
            f"refusing existing Overture bundle output: {destination}"
        )
    derived, manifest = build_overture_bundle(
        source,
        fetch_state_path,
        atlas_path,
        generated_at=generated_at,
        atlas_manifest_path=atlas_manifest_path,
        config=config,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        _copy_fsync(source, stage / SOURCE_FILENAME)
        for filename, raw in derived.items():
            _write_fsync(stage / filename, raw)
        validate_overture_bundle(
            stage,
            atlas_path=atlas_path,
            atlas_manifest_path=atlas_manifest_path,
        )
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return manifest


__all__ = [
    "ATLAS_REFERENCE_FILENAME",
    "BUNDLE_SCHEMA_VERSION",
    "CANDIDATES_CSV_FILENAME",
    "CANDIDATES_FILENAME",
    "FETCH_STATE_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OVERTURE_CLI_VERSION",
    "OVERTURE_RELEASE",
    "OvertureConfig",
    "OvertureValidationError",
    "REVIEW_CONSTRAINTS",
    "SOURCE_FILENAME",
    "build_overture_bundle",
    "geometry_metrics",
    "validate_overture_bundle",
    "write_overture_bundle",
]
