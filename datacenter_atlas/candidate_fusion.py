"""Immutable, review-only fusion of structural construction candidates.

The lane is deliberately a prioritisation index, not a census or an entity
resolution system.  It keeps upstream source roots visible and treats spatial
relationships as review opportunities only.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import UTC, datetime
import hashlib
import io
import json
from math import asin, cos, floor, isfinite, pi, radians, sin, sqrt
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .global_snapshot import GlobalSnapshotError, validate_release_files
from .open_buildings_temporal import (
    OpenBuildingsTemporalValidationError,
    validate_candidate_bundle as validate_open_buildings_bundle,
)
from .overture import OvertureValidationError, validate_overture_bundle
from .satellite_batch import SatelliteBatchError, validate_satellite_batch
from .satellite_queue import QueueValidationError, validate_queue_bundle


FORMAT = "datacenter-atlas-candidate-fusion-v3"
SCHEMA_VERSION = 3
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
CANDIDATES_FILENAME = "fusion-candidates.jsonl"
CANDIDATES_CSV_FILENAME = "fusion-candidates.csv"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
BUNDLE_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
        CANDIDATES_FILENAME,
        CANDIDATES_CSV_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)
SCOPE = {
    "review_only": True,
    "candidate_merge_performed": False,
    "candidate_is_data_centre_identity_claim": False,
    "candidate_is_lifecycle_or_status_claim": False,
    "candidate_is_operating_status_claim": False,
    "candidate_is_type_workload_or_operating_model_claim": False,
    "candidate_is_capacity_power_or_energy_claim": False,
    "proximity_or_overlap_is_independent_corroboration": False,
    "distinct_source_root_is_confirmed_independence": False,
    "automatic_atlas_import_allowed": False,
    "unique_physical_site_count_computed": False,
}
EARTH_RADIUS_M = 6_371_008.8
GRID_DEGREES = 0.25
_OSM_URL_RE = re.compile(
    r"^https?://(?:www\.)?openstreetmap\.org/(node|way|relation)/(\d+)(?:[/?#]|$)",
    flags=re.IGNORECASE,
)
_OSM_STABLE_RE = re.compile(
    r"^(?:osm(?:-[a-z0-9_-]+)?|openstreetmap(?:[:_-][a-z0-9_-]+)*)"
    r":(?:[^:]+:)*(node|way|relation)[/:](\d+)(?::|$)",
    flags=re.IGNORECASE,
)


class CandidateFusionError(ValueError):
    """Raised when a fusion definition, input, or bundle fails closed."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateFusionError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateFusionError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateFusionError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise CandidateFusionError(f"{label} must be canonical UTC whole seconds")
    return value


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise CandidateFusionError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateFusionError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CandidateFusionError(f"{label} must be a JSON object")
    return value, raw


def _safe_relative(root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise CandidateFusionError(f"{label} path must be non-empty text")
    supplied = Path(raw_path)
    if supplied.is_absolute():
        raise CandidateFusionError(f"{label} path must be relative")
    resolved = (root / supplied).resolve()
    package_root = root.parent.resolve()
    if resolved != package_root and package_root not in resolved.parents:
        raise CandidateFusionError(f"{label} path escapes the package root")
    return resolved


def _expected_sha(spec: Mapping[str, Any], path: Path, label: str) -> dict[str, Any]:
    expected = spec.get("manifest_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise CandidateFusionError(f"{label} manifest_sha256 is invalid")
    manifest_path = path / MANIFEST_FILENAME
    checkpoint = _checkpoint(manifest_path)
    if checkpoint["sha256"] != expected:
        raise CandidateFusionError(f"{label} manifest hash changed")
    return checkpoint


def _feature_collection(path: Path) -> Iterator[dict[str, Any]]:
    """Stream a canonical GeoJSON FeatureCollection without loading it whole."""

    decoder = json.JSONDecoder()
    prefix = '{"features":['
    with path.open("r", encoding="utf-8") as source:
        buffer = source.read(1024 * 1024)
        if not buffer.startswith(prefix):
            raise CandidateFusionError(f"GeoJSON is not canonical features-first: {path}")
        position = len(prefix)
        while True:
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position >= len(buffer):
                more = source.read(1024 * 1024)
                if not more:
                    raise CandidateFusionError(f"GeoJSON feature array is truncated: {path}")
                buffer = buffer[position:] + more
                position = 0
                continue
            if buffer[position] == "]":
                suffix = buffer[position + 1 :] + source.read()
                try:
                    metadata = json.loads('{"features":[]' + suffix)
                except json.JSONDecodeError as error:
                    raise CandidateFusionError(
                        f"GeoJSON collection suffix is invalid: {path}"
                    ) from error
                if not isinstance(metadata, dict) or metadata.get("type") != "FeatureCollection":
                    raise CandidateFusionError(f"GeoJSON collection type is invalid: {path}")
                return
            if buffer[position] == ",":
                position += 1
                continue
            try:
                feature, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                more = source.read(1024 * 1024)
                if not more:
                    raise CandidateFusionError(f"GeoJSON feature is truncated: {path}")
                buffer = buffer[position:] + more
                position = 0
                continue
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise CandidateFusionError(f"GeoJSON member is not a feature: {path}")
            yield feature
            position = end
            if position > 4 * 1024 * 1024:
                buffer = buffer[position:]
                position = 0


def _coordinate_pairs(value: Any) -> Iterator[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and not isinstance(value[0], bool)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    ):
        longitude = float(value[0])
        latitude = float(value[1])
        if isfinite(longitude) and isfinite(latitude):
            yield longitude, latitude
        return
    if isinstance(value, list):
        for item in value:
            yield from _coordinate_pairs(item)


def _geometry_bounds(geometry: Mapping[str, Any]) -> tuple[float, float, float, float]:
    pairs = list(_coordinate_pairs(geometry.get("coordinates")))
    if not pairs:
        raise CandidateFusionError("candidate geometry has no finite coordinate pairs")
    longitudes = [pair[0] for pair in pairs]
    latitudes = [pair[1] for pair in pairs]
    bounds = min(longitudes), min(latitudes), max(longitudes), max(latitudes)
    if bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -90 or bounds[3] > 90:
        raise CandidateFusionError("candidate geometry is outside WGS84 bounds")
    return bounds


def _bounds_overlap(
    left: Sequence[float], right: Sequence[float]
) -> bool:
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )


def _point_in_ring(longitude: float, latitude: float, ring: Any) -> bool:
    points = list(_coordinate_pairs(ring))
    if len(points) < 3:
        return False
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > latitude) != (y2 > latitude):
            crossing = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing:
                inside = not inside
        previous = current
    return inside


def _point_in_polygon(longitude: float, latitude: float, polygon: Any) -> bool:
    if not isinstance(polygon, list) or not polygon:
        return False
    if not _point_in_ring(longitude, latitude, polygon[0]):
        return False
    return not any(_point_in_ring(longitude, latitude, hole) for hole in polygon[1:])


def _geometry_contains(geometry: Mapping[str, Any], longitude: float, latitude: float) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return _point_in_polygon(longitude, latitude, coordinates)
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return any(_point_in_polygon(longitude, latitude, item) for item in coordinates)
    return False


def _haversine(
    left_latitude: float,
    left_longitude: float,
    right_latitude: float,
    right_longitude: float,
) -> float:
    left_lat = radians(left_latitude)
    right_lat = radians(right_latitude)
    delta_lat = right_lat - left_lat
    delta_lon = radians(right_longitude - left_longitude)
    hav = sin(delta_lat / 2) ** 2 + cos(left_lat) * cos(right_lat) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(hav)))


def _rings(geometry: Mapping[str, Any]) -> Iterator[Any]:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon" and isinstance(coordinates, list):
        yield from coordinates
    elif geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        for polygon in coordinates:
            if isinstance(polygon, list):
                yield from polygon


def _point_to_geometry_distance(
    geometry: Mapping[str, Any], longitude: float, latitude: float
) -> float:
    if _geometry_contains(geometry, longitude, latitude):
        return 0.0
    metres_per_degree = pi * EARTH_RADIUS_M / 180.0
    cos_latitude = max(abs(cos(radians(latitude))), 1e-9)
    best = float("inf")
    for ring in _rings(geometry):
        points = list(_coordinate_pairs(ring))
        if len(points) < 2:
            continue
        for first, second in zip(points, points[1:]):
            ax = (first[0] - longitude) * cos_latitude * metres_per_degree
            ay = (first[1] - latitude) * metres_per_degree
            bx = (second[0] - longitude) * cos_latitude * metres_per_degree
            by = (second[1] - latitude) * metres_per_degree
            dx = bx - ax
            dy = by - ay
            denominator = dx * dx + dy * dy
            scalar = 0.0 if denominator == 0 else -(ax * dx + ay * dy) / denominator
            scalar = min(1.0, max(0.0, scalar))
            x = ax + scalar * dx
            y = ay + scalar * dy
            best = min(best, sqrt(x * x + y * y))
    if isfinite(best):
        return best
    bounds = _geometry_bounds(geometry)
    return _haversine(latitude, longitude, (bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2)


def _osm_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _OSM_URL_RE.search(value.strip()) or _OSM_STABLE_RE.search(value.strip())
    if not match:
        return None
    return f"{match.group(1).casefold()}/{match.group(2)}"


def _source_root(source_family: Any) -> str:
    normalized = str(source_family or "unknown").strip().casefold().replace(" ", "_")
    if normalized == "openstreetmap" or normalized.startswith(
        ("openstreetmap:", "openstreetmap_")
    ):
        return "openstreetmap"
    return normalized


def _overture_root(dataset: Any) -> str:
    normalized = str(dataset or "unknown").strip().casefold()
    if normalized == "openstreetmap":
        return "openstreetmap"
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown"


def _cell(latitude: float, longitude: float) -> tuple[int, int]:
    return floor((latitude + 90.0) / GRID_DEGREES), floor((longitude + 180.0) / GRID_DEGREES)


def _atlas_index(
    features: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], list[int]]]:
    records: list[dict[str, Any]] = []
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, Mapping) or properties.get("entity_kind") not in {
            "campus",
            "facility",
            "project",
        }:
            continue
        latitude = properties.get("latitude")
        longitude = properties.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        latitude = float(latitude)
        longitude = float(longitude)
        if not isfinite(latitude) or not isfinite(longitude):
            continue
        root = _source_root(properties.get("source_family"))
        identities = {
            identity
            for identity in (
                _osm_identity(properties.get("stable_key")),
                _osm_identity(properties.get("source_url")),
            )
            if identity
        }
        record = {
            "entity_id": properties.get("entity_id") or feature.get("id"),
            "entity_kind": properties.get("entity_kind"),
            "name": properties.get("name"),
            "latitude": latitude,
            "longitude": longitude,
            "source_family": properties.get("source_family"),
            "source_root": root,
            "source_url": properties.get("source_url"),
            "osm_identities": sorted(identities),
            "reference_status": properties.get("status"),
            "reference_status_as_of": properties.get("status_as_of"),
            "reference_status_evidence_id": properties.get("status_evidence_id"),
        }
        index = len(records)
        records.append(record)
        cells[_cell(latitude, longitude)].append(index)
    return records, cells


def _atlas_search_indices(
    bounds: Sequence[float],
    records: Sequence[Mapping[str, Any]],
    cells: Mapping[tuple[int, int], Sequence[int]],
    max_distance_m: float,
) -> Iterable[int]:
    mid_latitude = (bounds[1] + bounds[3]) / 2
    latitude_margin = max_distance_m / 110_574.0
    longitude_margin = max_distance_m / (111_320.0 * max(abs(cos(radians(mid_latitude))), 0.05))
    expanded = (
        max(-180.0, bounds[0] - longitude_margin),
        max(-90.0, bounds[1] - latitude_margin),
        min(180.0, bounds[2] + longitude_margin),
        min(90.0, bounds[3] + latitude_margin),
    )
    left = _cell(expanded[1], expanded[0])
    right = _cell(expanded[3], expanded[2])
    cell_count = (right[0] - left[0] + 1) * (right[1] - left[1] + 1)
    if bounds[2] - bounds[0] > 180 or cell_count > 20_000:
        return range(len(records))
    found: list[int] = []
    for latitude_cell in range(left[0], right[0] + 1):
        for longitude_cell in range(left[1], right[1] + 1):
            found.extend(cells.get((latitude_cell, longitude_cell), ()))
    return found


def _atlas_links(
    candidate_id: str,
    geometry: Mapping[str, Any],
    bounds: Sequence[float],
    atlas_records: Sequence[Mapping[str, Any]],
    atlas_cells: Mapping[tuple[int, int], Sequence[int]],
    max_distance_m: float,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for index in _atlas_search_indices(bounds, atlas_records, atlas_cells, max_distance_m):
        reference = atlas_records[index]
        distance = _point_to_geometry_distance(
            geometry, reference["longitude"], reference["latitude"]
        )
        if distance > max_distance_m:
            continue
        exact = candidate_id in reference["osm_identities"]
        shared = reference["source_root"] == "openstreetmap"
        links.append(
            {
                "atlas_entity_id": reference["entity_id"],
                "atlas_entity_kind": reference["entity_kind"],
                "atlas_entity_name": reference["name"],
                "distance_m": round(distance, 3),
                "relationship": (
                    "exact_shared_osm_identity"
                    if exact
                    else "geometry_contains_reference_point"
                    if distance == 0
                    else "within_configured_distance"
                ),
                "source_family": reference["source_family"],
                "source_root": reference["source_root"],
                "source_relationship": (
                    "shared_osm_root" if shared else "distinct_source_root_opportunity"
                ),
                "exact_upstream_identity_match": exact,
                "source_root_distinct_from_osm": not shared,
                "distinct_root_is_confirmed_independence": False,
                "reference_status": {
                    "applies_to_atlas_reference_entity_only": True,
                    "status": reference["reference_status"],
                    "as_of": reference["reference_status_as_of"],
                    "evidence_id": reference["reference_status_evidence_id"],
                },
                "candidate_identity_or_status_inferred": False,
            }
        )
    links.sort(key=lambda item: (item["distance_m"], str(item["atlas_entity_id"])))
    return links


def _overture_records(features: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for feature in features:
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise CandidateFusionError("Overture candidate feature is malformed")
        roots = sorted(
            {
                _overture_root(source.get("dataset"))
                for source in properties.get("overture_properties", {}).get("sources", [])
                if isinstance(source, Mapping)
            }
        )
        cross_reference = properties.get("atlas_cross_reference", {})
        identities = cross_reference.get("overture_upstream_osm_identities", [])
        records.append(
            {
                "gers_id": feature.get("id"),
                "bounds": _geometry_bounds(geometry),
                "upstream_source_roots": roots,
                "upstream_osm_identities": sorted(
                    identity for identity in identities if isinstance(identity, str)
                ),
                "review_priority_tier": properties.get("review_priority", {}).get("tier"),
            }
        )
    return records


def _overture_links(
    candidate_id: str, bounds: Sequence[float], overture_records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for record in overture_records:
        if not _bounds_overlap(bounds, record["bounds"]):
            continue
        shared = "openstreetmap" in record["upstream_source_roots"]
        exact = candidate_id in record["upstream_osm_identities"]
        links.append(
            {
                "gers_id": record["gers_id"],
                "relationship": (
                    "exact_shared_osm_identity"
                    if exact
                    else "geometry_bounds_overlap_only"
                ),
                "exact_upstream_identity_match": exact,
                "upstream_source_roots": record["upstream_source_roots"],
                "source_relationship": (
                    "shared_osm_root_mixed_or_only"
                    if shared
                    else "distinct_source_root_opportunity"
                ),
                "source_root_distinct_from_osm": not shared,
                "distinct_root_is_confirmed_independence": False,
                "overture_review_priority_tier": record["review_priority_tier"],
                "bounds_overlap_is_identity_or_status_evidence": False,
            }
        )
    links.sort(key=lambda item: str(item["gers_id"]))
    return links


def _queue_records(
    lines: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id: dict[str, dict[str, Any]] = {}
    for line in lines:
        entity = line.get("entity")
        location = line.get("location")
        if not isinstance(entity, Mapping) or not isinstance(location, Mapping):
            raise CandidateFusionError("satellite queue job is malformed")
        record = {
            "queue_id": line.get("queue_id"),
            "entity_id": entity.get("id"),
            "aoi_bbox_wgs84": location.get("aoi_bbox_wgs84"),
            "priority_tier": line.get("priority", {}).get("tier"),
        }
        if (
            not isinstance(record["queue_id"], str)
            or not isinstance(record["entity_id"], str)
            or not isinstance(record["aoi_bbox_wgs84"], list)
            or len(record["aoi_bbox_wgs84"]) != 4
        ):
            raise CandidateFusionError("satellite queue job identity is malformed")
        by_entity[record["entity_id"]].append(record)
        by_id[record["queue_id"]] = record
    for values in by_entity.values():
        values.sort(key=lambda item: item["queue_id"])
    return by_entity, by_id


def _satellite_links(
    bounds: Sequence[float],
    atlas_links: Sequence[Mapping[str, Any]],
    queue_by_entity: Mapping[str, Sequence[Mapping[str, Any]]],
    batch_states: Mapping[str, Mapping[str, Any]],
    analyst_reviews: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    for atlas_link in atlas_links:
        for queue in queue_by_entity.get(str(atlas_link["atlas_entity_id"]), ()):
            if not _bounds_overlap(bounds, queue["aoi_bbox_wgs84"]):
                continue
            queue_id = queue["queue_id"]
            batch = batch_states.get(queue_id)
            review = analyst_reviews.get(queue_id)
            decision = review.get("decision") if review else None
            retained = decision == "retain_site_aligned_change_candidate_for_manual_followup"
            if retained:
                outcome_class = "retained_visible_change_aoi_followup"
            elif decision == "reject_automated_mask_for_site_promotion":
                outcome_class = "rejected_for_site_promotion"
            elif review is not None:
                outcome_class = "reviewed_not_retained"
            else:
                outcome_class = "not_analyst_reviewed"
            links[queue_id] = {
                "queue_id": queue_id,
                "atlas_entity_id": queue["entity_id"],
                "relationship": "candidate_bounds_overlap_queue_aoi",
                "priority_tier": queue["priority_tier"],
                "catalog_state": batch.get("state") if batch else "not_run",
                "selected_scene_pair_available": bool(
                    batch and batch.get("state") == "completed"
                ),
                "analyst_review_decision": decision,
                "analyst_review_outcome_class": outcome_class,
                "analyst_retained_visible_change_candidate": retained,
                "imagery_source_root": "copernicus_sentinel_2",
                "queue_or_catalog_availability_is_change_evidence": False,
                "analyst_review_confirms_candidate_identity_or_status": False,
            }
    return [links[key] for key in sorted(links)]


def _priority(
    atlas_links: Sequence[Mapping[str, Any]],
    overture_links: Sequence[Mapping[str, Any]],
    open_buildings_links: Sequence[Mapping[str, Any]],
    satellite_links: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    roots = {
        link["source_root"]
        for link in atlas_links
        if link.get("source_root_distinct_from_osm") is True
    }
    for link in overture_links:
        if link.get("source_root_distinct_from_osm") is True:
            roots.update(link.get("upstream_source_roots", ()))
    if open_buildings_links:
        roots.add("copernicus_sentinel_2")
    if any(link.get("analyst_retained_visible_change_candidate") for link in satellite_links):
        roots.add("copernicus_sentinel_2")
    if any(link.get("analyst_retained_visible_change_candidate") for link in satellite_links):
        tier = "analyst_retained_visible_change_aoi_overlap_followup"
    elif roots:
        tier = "distinct_source_root_opportunity"
    else:
        tier = "shared_osm_root_or_queue_opportunity"
    return tier, sorted(roots)


def _derive(
    primary_features: Iterable[Mapping[str, Any]],
    *,
    atlas_features: Iterable[Mapping[str, Any]],
    overture_records: Sequence[Mapping[str, Any]],
    open_buildings: Sequence[Mapping[str, Any]],
    queue_by_entity: Mapping[str, Sequence[Mapping[str, Any]]],
    batch_states: Mapping[str, Mapping[str, Any]],
    analyst_reviews: Mapping[str, Mapping[str, Any]],
    atlas_max_distance_m: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    atlas_records, atlas_cells = _atlas_index(atlas_features)
    candidates: list[dict[str, Any]] = []
    primary_count = 0
    for feature in primary_features:
        primary_count += 1
        candidate_id = feature.get("id")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if (
            not isinstance(candidate_id, str)
            or not re.fullmatch(r"(?:way|relation)/\d+", candidate_id)
            or not isinstance(properties, Mapping)
            or not isinstance(geometry, Mapping)
        ):
            raise CandidateFusionError("primary shortlist feature is malformed")
        if properties.get("review_only") is not True or properties.get(
            "data_centre_identity_inferred"
        ) is not False:
            raise CandidateFusionError("primary shortlist safeguards changed")
        bounds = _geometry_bounds(geometry)
        atlas_links = _atlas_links(
            candidate_id,
            geometry,
            bounds,
            atlas_records,
            atlas_cells,
            atlas_max_distance_m,
        )
        overture_links = _overture_links(candidate_id, bounds, overture_records)
        open_buildings_links: list[dict[str, Any]] = []
        for bundle in open_buildings:
            if _bounds_overlap(bounds, bundle["aoi_bbox_wgs84"]):
                open_buildings_links.append(
                    {
                        "bundle_id": bundle["bundle_id"],
                        "relationship": "candidate_bounds_overlap_bounded_aoi",
                        "review_candidate_ids": bundle["candidate_ids"],
                        "imagery_source_root": "copernicus_sentinel_2",
                        "shared_imagery_root_with_sentinel_lane": True,
                        "aoi_signal_is_candidate_identity_or_status_evidence": False,
                    }
                )
        satellite_links = _satellite_links(
            bounds,
            atlas_links,
            queue_by_entity,
            batch_states,
            analyst_reviews,
        )
        if not (atlas_links or overture_links or open_buildings_links or satellite_links):
            continue
        tier, distinct_roots = _priority(
            atlas_links, overture_links, open_buildings_links, satellite_links
        )
        review_score = properties.get("review_score")
        area = properties.get("footprint_square_metres")
        candidates.append(
            {
                "schema_version": SCHEMA_VERSION,
                "candidate_id": candidate_id,
                "osm_source": {
                    "source_url": properties.get("source_url"),
                    "review_score": review_score,
                    "footprint_square_metres": area,
                    "source_tag_families": properties.get("source_tag_families"),
                },
                "review_priority": {
                    "tier": tier,
                    "distinct_non_osm_source_roots": distinct_roots,
                    "ordering_is_review_heuristic_not_probability": True,
                },
                "evidence_opportunities": {
                    "atlas_reference_proximity": atlas_links,
                    "overture_footprint_bounds": overture_links,
                    "open_buildings_temporal_aoi": open_buildings_links,
                    "sentinel_queue_or_review": satellite_links,
                },
                "safeguards": {
                    "review_only": True,
                    (
                        "spatial_relationship_is_identity_status_type_capacity_"
                        "power_or_energy_claim"
                    ): False,
                    "distinct_source_root_is_confirmed_independent_corroboration": False,
                    "automatic_atlas_import_allowed": False,
                },
                "_sort": (
                    0
                    if tier
                    == "analyst_retained_visible_change_aoi_overlap_followup"
                    else 1
                    if tier == "distinct_source_root_opportunity"
                    else 2,
                    -len(distinct_roots),
                    -sum(
                        1
                        for link in satellite_links
                        if link.get("analyst_retained_visible_change_candidate")
                    ),
                    -int(review_score or 0),
                    -float(area or 0),
                    candidate_id,
                ),
            }
        )
    candidates.sort(key=lambda item: item["_sort"])
    for rank, candidate in enumerate(candidates, start=1):
        candidate["review_priority"]["fusion_rank"] = rank
        del candidate["_sort"]

    tiers = Counter(candidate["review_priority"]["tier"] for candidate in candidates)
    atlas_links = [
        link
        for candidate in candidates
        for link in candidate["evidence_opportunities"]["atlas_reference_proximity"]
    ]
    overture_links = [
        link
        for candidate in candidates
        for link in candidate["evidence_opportunities"]["overture_footprint_bounds"]
    ]
    satellite_links = [
        link
        for candidate in candidates
        for link in candidate["evidence_opportunities"]["sentinel_queue_or_review"]
    ]
    analyst_outcome_links = Counter(
        link["analyst_review_outcome_class"] for link in satellite_links
    )
    analyst_outcome_candidates = Counter()
    for candidate in candidates:
        outcomes = {
            link["analyst_review_outcome_class"]
            for link in candidate["evidence_opportunities"]["sentinel_queue_or_review"]
            if link["analyst_review_outcome_class"] != "not_analyst_reviewed"
        }
        analyst_outcome_candidates.update(outcomes)
    linked_reviews_by_outcome: dict[str, set[str]] = defaultdict(set)
    for link in satellite_links:
        if link["analyst_review_outcome_class"] != "not_analyst_reviewed":
            linked_reviews_by_outcome[link["analyst_review_outcome_class"]].add(
                link["queue_id"]
            )
    input_reviews_by_outcome = Counter(
        "retained_visible_change_aoi_followup"
        if review.get("decision")
        == "retain_site_aligned_change_candidate_for_manual_followup"
        else "rejected_for_site_promotion"
        if review.get("decision") == "reject_automated_mask_for_site_promotion"
        else "reviewed_not_retained"
        for review in analyst_reviews.values()
    )
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "primary_shortlist": {
            "candidates_examined": primary_count,
            "candidates_with_any_fusion_opportunity": len(candidates),
            "candidates_without_fusion_opportunity": primary_count - len(candidates),
            "candidate_count_is_data_centre_count": False,
        },
        "review_priority_tiers": dict(sorted(tiers.items())),
        "atlas_reference_lane": {
            "site_level_reference_records_indexed": len(atlas_records),
            "spatial_links": len(atlas_links),
            "candidates_linked": sum(
                bool(candidate["evidence_opportunities"]["atlas_reference_proximity"])
                for candidate in candidates
            ),
            "shared_osm_root_links": sum(
                link["source_relationship"] == "shared_osm_root" for link in atlas_links
            ),
            "distinct_source_root_opportunity_links": sum(
                link["source_relationship"] == "distinct_source_root_opportunity"
                for link in atlas_links
            ),
            "exact_shared_osm_identity_links_in_shortlist": sum(
                link["exact_upstream_identity_match"] for link in atlas_links
            ),
        },
        "overture_lane": {
            "bounded_candidate_footprints_examined": len(overture_records),
            "bounds_overlap_links": len(overture_links),
            "candidates_linked": sum(
                bool(candidate["evidence_opportunities"]["overture_footprint_bounds"])
                for candidate in candidates
            ),
            "shared_osm_root_mixed_or_only_links": sum(
                link["source_relationship"] == "shared_osm_root_mixed_or_only"
                for link in overture_links
            ),
            "distinct_source_root_opportunity_links": sum(
                link["source_relationship"] == "distinct_source_root_opportunity"
                for link in overture_links
            ),
        },
        "open_buildings_temporal_lane": {
            "bounded_bundles_examined": len(open_buildings),
            "review_signals_examined": sum(
                len(bundle["candidate_ids"]) for bundle in open_buildings
            ),
            "candidate_aoi_overlap_links": sum(
                len(candidate["evidence_opportunities"]["open_buildings_temporal_aoi"])
                for candidate in candidates
            ),
            "shares_copernicus_sentinel_2_root_with_sentinel_lane": True,
        },
        "sentinel_lane": {
            "queue_aoi_overlap_links": len(satellite_links),
            "candidates_linked": sum(
                bool(candidate["evidence_opportunities"]["sentinel_queue_or_review"])
                for candidate in candidates
            ),
            "catalog_state_links": dict(
                sorted(Counter(link["catalog_state"] for link in satellite_links).items())
            ),
            "analyst_reviews_examined_by_outcome": dict(
                sorted(input_reviews_by_outcome.items())
            ),
            "analyst_review_aoi_overlap_links_by_outcome": dict(
                sorted(analyst_outcome_links.items())
            ),
            "candidates_with_analyst_review_aoi_overlap_by_outcome": dict(
                sorted(analyst_outcome_candidates.items())
            ),
            "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                outcome: len(queue_ids)
                for outcome, queue_ids in sorted(linked_reviews_by_outcome.items())
            },
            "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            "queue_or_catalog_availability_is_change_evidence": False,
        },
    }
    return candidates, coverage


def _read_json_lines(path: Path, label: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise CandidateFusionError(
                    f"{label} line {line_number} is invalid JSON"
                ) from error
            if not isinstance(value, dict):
                raise CandidateFusionError(f"{label} line {line_number} is not an object")
            values.append(value)
    return values


def _validate_gdelt_triage(directory: Path) -> dict[str, Any]:
    names = {entry.name for entry in directory.iterdir()}
    expected = {"README.md", "triage.json", MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if names != expected or any(
        entry.is_symlink() or not entry.is_file() for entry in directory.iterdir()
    ):
        raise CandidateFusionError("GDELT triage bundle closed file set changed")
    manifest, raw = _json_object(directory / MANIFEST_FILENAME, "GDELT triage manifest")
    sidecar = (directory / MANIFEST_HASH_FILENAME).read_bytes()
    if sidecar != f"{_sha256(raw)}  {MANIFEST_FILENAME}\n".encode("ascii"):
        raise CandidateFusionError("GDELT triage manifest sidecar changed")
    if (
        manifest.get("format") != "datacenter-atlas-gdelt-manual-triage-v1"
        or manifest.get("scope")
        != {
        "atlas_claims_created": False,
        "automatic_import_allowed": False,
        "review_only": True,
        }
    ):
        raise CandidateFusionError("GDELT triage safeguards changed")
    triage, triage_raw = _json_object(directory / "triage.json", "GDELT triage decisions")
    if manifest.get("artifacts", {}).get("triage.json", {}).get("sha256") != _sha256(triage_raw):
        raise CandidateFusionError("GDELT triage decisions hash changed")
    retained = [
        decision
        for decision in triage.get("decisions", [])
        if isinstance(decision, Mapping)
        and decision.get("disposition") == "retain_for_source_review"
    ]
    if len(retained) != manifest.get("counts", {}).get("retained_for_source_review"):
        raise CandidateFusionError("GDELT retained decision count changed")
    return {"manifest": manifest, "retained": retained}


def _load_definition(path: str | Path) -> tuple[dict[str, Any], bytes, Path]:
    supplied = Path(path)
    definition, raw = _json_object(supplied, "fusion definition")
    if raw != _canonical_json(definition):
        raise CandidateFusionError("fusion definition must be canonical pretty JSON")
    if set(definition) != {"schema_version", "generated_at", "parameters", "inputs"}:
        raise CandidateFusionError("fusion definition schema changed")
    if definition.get("schema_version") != SCHEMA_VERSION:
        raise CandidateFusionError("fusion definition version is unsupported")
    _timestamp(definition.get("generated_at"), "fusion definition generated_at")
    parameters = definition.get("parameters")
    if not isinstance(parameters, Mapping) or set(parameters) != {"atlas_max_distance_m"}:
        raise CandidateFusionError("fusion parameters schema changed")
    distance = parameters.get("atlas_max_distance_m")
    if (
        not isinstance(distance, (int, float))
        or not isfinite(float(distance))
        or distance <= 0
        or distance > 10_000
    ):
        raise CandidateFusionError("atlas_max_distance_m is invalid")
    inputs = definition.get("inputs")
    expected_inputs = {
        "osm_construction_bundle",
        "atlas_release",
        "overture_bundles",
        "open_buildings_temporal_bundles",
        "gdelt_triage_bundles",
        "satellite_queue_bundle",
        "satellite_batch_bundles",
        "satellite_analyst_reviews",
    }
    if not isinstance(inputs, Mapping) or set(inputs) != expected_inputs:
        raise CandidateFusionError("fusion input definition schema changed")
    return definition, raw, supplied.resolve()


def _load_inputs(definition: Mapping[str, Any], definition_path: Path) -> dict[str, Any]:
    root = definition_path.parent
    specs = definition["inputs"]
    lineage: list[dict[str, Any]] = []

    primary_spec = specs["osm_construction_bundle"]
    primary = _safe_relative(root, primary_spec.get("path"), "OSM construction bundle")
    primary_manifest_checkpoint = _expected_sha(primary_spec, primary, "OSM construction bundle")
    primary_manifest, _ = _json_object(primary / MANIFEST_FILENAME, "OSM construction manifest")
    if (
        primary_manifest.get("pipeline")
        != "openstreetmap_planet_structural_construction_candidates"
        or primary_manifest.get("state") != "completed"
        or primary_manifest.get("review_only") is not True
        or primary_manifest.get("candidate_layer_not_data_centre_census") is not True
    ):
        raise CandidateFusionError("OSM construction bundle safeguards changed")
    if set(entry.name for entry in primary.iterdir()) != set(
        primary_manifest.get("outputs", {})
    ) | {MANIFEST_FILENAME}:
        raise CandidateFusionError("OSM construction bundle closed file set changed")
    for name, checkpoint in primary_manifest["outputs"].items():
        if _checkpoint(primary / name) != {
            "bytes": checkpoint.get("bytes"),
            "sha256": checkpoint.get("sha256"),
        }:
            raise CandidateFusionError(f"OSM construction artifact changed: {name}")
    lineage.append(
        {
            "lane": "osm_planet_structural_construction",
            "path": primary_spec["path"],
            "manifest": primary_manifest_checkpoint,
        }
    )

    atlas_spec = specs["atlas_release"]
    atlas = _safe_relative(root, atlas_spec.get("path"), "Atlas release")
    atlas_manifest_checkpoint = _expected_sha(atlas_spec, atlas, "Atlas release")
    try:
        atlas_manifest = validate_release_files(atlas)
    except GlobalSnapshotError as error:
        raise CandidateFusionError(f"Atlas release validation failed: {error}") from error
    if atlas_manifest.get("format") != "datacenter-atlas-release-v1":
        raise CandidateFusionError("Atlas release format changed")
    lineage.append(
        {
            "lane": "known_atlas_entities",
            "path": atlas_spec["path"],
            "manifest": atlas_manifest_checkpoint,
        }
    )

    overture_records: list[dict[str, Any]] = []
    for index, spec in enumerate(specs["overture_bundles"]):
        directory = _safe_relative(root, spec.get("path"), f"Overture bundle {index}")
        checkpoint = _expected_sha(spec, directory, f"Overture bundle {index}")
        try:
            validate_overture_bundle(
                directory,
                atlas_path=atlas / "atlas.geojson",
                atlas_manifest_path=atlas / MANIFEST_FILENAME,
            )
        except OvertureValidationError as error:
            raise CandidateFusionError(f"Overture validation failed: {error}") from error
        overture_records.extend(
            _overture_records(
                _read_json_lines(
                    directory / "candidates.geojsonseq", "Overture candidates"
                )
            )
        )
        lineage.append(
            {
                "lane": "overture_buildings_bounded",
                "path": spec["path"],
                "manifest": checkpoint,
            }
        )

    open_buildings: list[dict[str, Any]] = []
    for index, spec in enumerate(specs["open_buildings_temporal_bundles"]):
        directory = _safe_relative(root, spec.get("path"), f"Open Buildings bundle {index}")
        checkpoint = _expected_sha(spec, directory, f"Open Buildings bundle {index}")
        manifest, _ = _json_object(directory / MANIFEST_FILENAME, "Open Buildings manifest")
        source_name = manifest.get("source", {}).get("directory_name")
        source_directory = directory.parent / str(source_name)
        try:
            validate_open_buildings_bundle(directory, source_directory=source_directory)
        except OpenBuildingsTemporalValidationError as error:
            raise CandidateFusionError(f"Open Buildings validation failed: {error}") from error
        candidates = _read_json_lines(directory / "candidates.jsonl", "Open Buildings candidates")
        open_buildings.append(
            {
                "bundle_id": directory.name,
                "aoi_bbox_wgs84": manifest["query"]["aoi"]["bbox_wgs84"],
                "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
            }
        )
        lineage.append(
            {
                "lane": "google_open_buildings_temporal_bounded",
                "path": spec["path"],
                "manifest": checkpoint,
            }
        )

    gdelt_retained = 0
    for index, spec in enumerate(specs["gdelt_triage_bundles"]):
        directory = _safe_relative(root, spec.get("path"), f"GDELT triage bundle {index}")
        checkpoint = _expected_sha(spec, directory, f"GDELT triage bundle {index}")
        gdelt = _validate_gdelt_triage(directory)
        gdelt_retained += len(gdelt["retained"])
        lineage.append(
            {
                "lane": "gdelt_manual_triage",
                "path": spec["path"],
                "manifest": checkpoint,
            }
        )

    queue_spec = specs["satellite_queue_bundle"]
    queue = _safe_relative(root, queue_spec.get("path"), "satellite queue bundle")
    queue_checkpoint = _expected_sha(queue_spec, queue, "satellite queue bundle")
    try:
        queue_manifest = validate_queue_bundle(queue)
    except QueueValidationError as error:
        raise CandidateFusionError(f"satellite queue validation failed: {error}") from error
    queue_lines = _read_json_lines(queue / "satellite-review-queue.jsonl", "satellite queue")
    queue_by_entity, queue_by_id = _queue_records(queue_lines)
    lineage.append(
        {
            "lane": "sentinel_review_queue",
            "path": queue_spec["path"],
            "manifest": queue_checkpoint,
        }
    )

    batch_states: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(specs["satellite_batch_bundles"]):
        directory = _safe_relative(root, spec.get("path"), f"satellite batch {index}")
        expected = spec.get("manifest_sha256")
        batch_manifest_path = directory / "batch-manifest.json"
        checkpoint = _checkpoint(batch_manifest_path)
        if checkpoint["sha256"] != expected:
            raise CandidateFusionError(f"satellite batch {index} manifest hash changed")
        try:
            batch = validate_satellite_batch(queue, directory)
        except SatelliteBatchError as error:
            raise CandidateFusionError(f"satellite batch validation failed: {error}") from error
        for queue_id, state in batch["jobs"].items():
            if queue_id in batch_states:
                raise CandidateFusionError(
                    f"satellite queue job occurs in multiple batches: {queue_id}"
                )
            batch_states[queue_id] = state
        lineage.append(
            {
                "lane": "sentinel_catalog_batch",
                "path": spec["path"],
                "manifest": checkpoint,
            }
        )

    analyst_reviews: dict[str, dict[str, Any]] = {}
    analyst_report_hashes: set[str] = set()
    analyst_review_hashes: set[str] = set()
    for index, spec in enumerate(specs["satellite_analyst_reviews"]):
        queue_id = spec.get("queue_id")
        if queue_id not in queue_by_id:
            raise CandidateFusionError(f"analyst review {index} queue_id is absent")
        if queue_id in analyst_reviews:
            raise CandidateFusionError(
                f"analyst review {index} repeats queue_id: {queue_id}"
            )
        review_path = _safe_relative(root, spec.get("path"), f"analyst review {index}")
        report_path = _safe_relative(root, spec.get("report_path"), f"analyst report {index}")
        if (
            review_path.parent != report_path.parent
            or review_path.parent.name != "change"
            or review_path.parent.parent.name != queue_id
            or batch_states.get(queue_id, {}).get("state") != "completed"
        ):
            raise CandidateFusionError(
                f"analyst review {index} batch or report lineage changed"
            )
        review_checkpoint = _checkpoint(review_path)
        report_checkpoint = _checkpoint(report_path)
        if review_checkpoint["sha256"] != spec.get("sha256") or report_checkpoint[
            "sha256"
        ] != spec.get("report_sha256"):
            raise CandidateFusionError(f"analyst review {index} input hash changed")
        if report_checkpoint["sha256"] in analyst_report_hashes:
            raise CandidateFusionError(
                f"analyst review {index} repeats an analyst report hash"
            )
        if review_checkpoint["sha256"] in analyst_review_hashes:
            raise CandidateFusionError(
                f"analyst review {index} repeats an analyst review hash"
            )
        analyst_report_hashes.add(report_checkpoint["sha256"])
        analyst_review_hashes.add(review_checkpoint["sha256"])
        review, _ = _json_object(review_path, f"analyst review {index}")
        report, _ = _json_object(report_path, f"analyst report {index}")
        scope = review.get("scope")
        classification = report.get("classification")
        entity = report.get("entity")
        if (
            review.get("input_report_sha256") != report_checkpoint["sha256"]
            or review.get("atlas_claims_created") is not False
            or review.get("automated_promotion_allowed") is not False
            or review.get("decision")
            not in {
                "reject_automated_mask_for_site_promotion",
                "retain_site_aligned_change_candidate_for_manual_followup",
            }
            or not isinstance(scope, Mapping)
            or scope
            != {
                "data_center_identity_confirmed": False,
                "lifecycle_status_confirmed": False,
                "operating_status_inferred": False,
                "power_or_energy_inferred": False,
                "review_required": True,
            }
            or not isinstance(classification, Mapping)
            or classification.get("identity_claim") is not False
            or classification.get("lifecycle_claim") is not False
            or classification.get("review_required") is not True
            or not isinstance(entity, Mapping)
            or entity.get("id") != queue_by_id[queue_id]["entity_id"]
        ):
            raise CandidateFusionError(f"analyst review {index} safeguards changed")
        analyst_reviews[queue_id] = review
        lineage.append(
            {
                "lane": "sentinel_analyst_review",
                "path": spec["path"],
                "review": review_checkpoint,
                "report": report_checkpoint,
                "queue_id": queue_id,
            }
        )

    return {
        "primary_path": primary / "shortlist.geojson",
        "primary_manifest": primary_manifest,
        "atlas_path": atlas / "atlas.geojson",
        "overture_records": overture_records,
        "open_buildings": open_buildings,
        "gdelt_retained": gdelt_retained,
        "queue_by_entity": queue_by_entity,
        "queue_job_count": len(queue_by_id),
        "batch_states": batch_states,
        "analyst_reviews": analyst_reviews,
        "lineage": lineage,
    }


def _csv_bytes(candidates: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "fusion_rank",
        "candidate_id",
        "source_url",
        "review_score",
        "footprint_square_metres",
        "review_priority_tier",
        "distinct_non_osm_source_roots_json",
        "atlas_links",
        "atlas_shared_osm_root_links",
        "atlas_distinct_root_opportunity_links",
        "overture_bounds_links",
        "open_buildings_aoi_links",
        "sentinel_queue_or_review_links",
        "analyst_retained_visible_change_aoi_overlap_links",
        "identity_status_type_capacity_power_or_energy_inferred",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for candidate in candidates:
        opportunities = candidate["evidence_opportunities"]
        atlas = opportunities["atlas_reference_proximity"]
        satellite = opportunities["sentinel_queue_or_review"]
        writer.writerow(
            {
                "fusion_rank": candidate["review_priority"]["fusion_rank"],
                "candidate_id": candidate["candidate_id"],
                "source_url": candidate["osm_source"]["source_url"],
                "review_score": candidate["osm_source"]["review_score"],
                "footprint_square_metres": candidate["osm_source"]["footprint_square_metres"],
                "review_priority_tier": candidate["review_priority"]["tier"],
                "distinct_non_osm_source_roots_json": json.dumps(
                    candidate["review_priority"]["distinct_non_osm_source_roots"],
                    separators=(",", ":"),
                ),
                "atlas_links": len(atlas),
                "atlas_shared_osm_root_links": sum(
                    link["source_relationship"] == "shared_osm_root" for link in atlas
                ),
                "atlas_distinct_root_opportunity_links": sum(
                    link["source_relationship"] == "distinct_source_root_opportunity"
                    for link in atlas
                ),
                "overture_bounds_links": len(opportunities["overture_footprint_bounds"]),
                "open_buildings_aoi_links": len(opportunities["open_buildings_temporal_aoi"]),
                "sentinel_queue_or_review_links": len(satellite),
                "analyst_retained_visible_change_aoi_overlap_links": sum(
                    link["analyst_retained_visible_change_candidate"] for link in satellite
                ),
                "identity_status_type_capacity_power_or_energy_inferred": "false",
            }
        )
    return output.getvalue().encode("utf-8")


def _attribution() -> bytes:
    return (
        "© OpenStreetMap contributors (ODbL 1.0)\n"
        "Overture Maps Foundation; see the pinned child bundle for per-source "
        "attribution (ODbL 1.0)\n"
        "Google Research Open Buildings 2.5D Temporal Dataset (CC BY 4.0); "
        "leverages Copernicus Sentinel-2 data\n"
        "Contains modified Copernicus Sentinel data\n"
        "Data from The GDELT Project (https://www.gdeltproject.org/)\n"
    ).encode("utf-8")


def _readme(coverage: Mapping[str, Any]) -> bytes:
    primary = coverage["primary_shortlist"]
    return f"""# OSM Planet candidate-fusion review index

This immutable bundle prioritises {primary['candidates_with_any_fusion_opportunity']:,} of
{primary['candidates_examined']:,} source-scoped structural-construction review candidates because
they have at least one configured proximity or bounds-overlap opportunity.

It is not a data-centre census, entity merge, lifecycle assessment, capacity estimate, power
estimate, or energy estimate. Distinct source roots are discovery opportunities only; they are not
proof that observations are independent. Open Buildings Temporal and the Sentinel review lane share
the Copernicus Sentinel-2 imagery root and must not be counted as separate imagery families.

The GDELT triage lane is represented in `coverage.json`, but its retained leads have no pinned
geometry and therefore create no spatial links. Queue and catalog availability are operational
review state, not visible-change evidence. Only an explicit analyst-retained result is labelled as a
visible-change follow-up, and even that confirms no data-centre identity or lifecycle status.
""".encode("utf-8")


def _payloads(
    candidates: Sequence[Mapping[str, Any]], coverage: Mapping[str, Any]
) -> dict[str, bytes]:
    return {
        CANDIDATES_FILENAME: b"".join(_canonical_line(candidate) for candidate in candidates),
        CANDIDATES_CSV_FILENAME: _csv_bytes(candidates),
        COVERAGE_FILENAME: _canonical_json(coverage),
        README_FILENAME: _readme(coverage),
        ATTRIBUTION_FILENAME: _attribution(),
    }


def _write_fsync(path: Path, raw: bytes) -> None:
    with path.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def write_candidate_fusion(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    definition, definition_raw, definition_file = _load_definition(definition_path)
    inputs = _load_inputs(definition, definition_file)
    with (inputs["atlas_path"]).open("r", encoding="utf-8") as source:
        atlas_document = json.load(source)
    if not isinstance(atlas_document, dict) or not isinstance(atlas_document.get("features"), list):
        raise CandidateFusionError("Atlas GeoJSON is malformed")
    candidates, coverage = _derive(
        _feature_collection(inputs["primary_path"]),
        atlas_features=atlas_document["features"],
        overture_records=inputs["overture_records"],
        open_buildings=inputs["open_buildings"],
        queue_by_entity=inputs["queue_by_entity"],
        batch_states=inputs["batch_states"],
        analyst_reviews=inputs["analyst_reviews"],
        atlas_max_distance_m=float(definition["parameters"]["atlas_max_distance_m"]),
    )
    coverage["osm_exact_identity_exclusions_before_fusion"] = inputs[
        "primary_manifest"
    ]["counts"]["known_exact_identity_exclusion_count"]
    coverage["gdelt_lane"] = {
        "retained_manual_triage_leads": inputs["gdelt_retained"],
        "retained_leads_with_pinned_geometry": 0,
        "spatial_links": 0,
        "reason_not_spatially_joined": "retained_leads_have_no_pinned_geometry",
    }
    coverage["sentinel_lane"]["queue_jobs_examined"] = inputs["queue_job_count"]
    coverage["sentinel_lane"]["catalog_batch_jobs_examined"] = len(inputs["batch_states"])
    coverage["sentinel_lane"]["analyst_reviews_examined"] = len(inputs["analyst_reviews"])
    payloads = _payloads(candidates, coverage)
    outputs = {
        name: {
            **_bytes_checkpoint(raw),
            "records": len(candidates)
            if name in {CANDIDATES_FILENAME, CANDIDATES_CSV_FILENAME}
            else None,
        }
        for name, raw in payloads.items()
    }
    for value in outputs.values():
        if value["records"] is None:
            del value["records"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": FORMAT,
        "generated_at": definition["generated_at"],
        "scope": SCOPE,
        "parameters": definition["parameters"],
        "definition": {
            "filename": definition_file.name,
            "bytes": len(definition_raw),
            "sha256": _sha256(definition_raw),
        },
        "inputs": inputs["lineage"],
        "counts": coverage,
        "outputs": outputs,
    }
    manifest_raw = _canonical_json(manifest)
    sidecar = f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise CandidateFusionError(f"refusing existing candidate-fusion output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    try:
        for name, raw in payloads.items():
            _write_fsync(stage / name, raw)
        _write_fsync(stage / MANIFEST_FILENAME, manifest_raw)
        _write_fsync(stage / MANIFEST_HASH_FILENAME, sidecar)
        validate_candidate_fusion(stage)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return manifest


def _bytes_checkpoint(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def validate_candidate_fusion(
    directory: str | Path, *, definition_path: str | Path | None = None
) -> dict[str, Any]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise CandidateFusionError("candidate-fusion bundle must be a regular directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CandidateFusionError("candidate-fusion closed file set changed")
    manifest, manifest_raw = _json_object(root / MANIFEST_FILENAME, "candidate-fusion manifest")
    if manifest_raw != _canonical_json(manifest):
        raise CandidateFusionError("candidate-fusion manifest is not canonical")
    if (root / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CandidateFusionError("candidate-fusion manifest sidecar changed")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != FORMAT
        or manifest.get("scope") != SCOPE
    ):
        raise CandidateFusionError("candidate-fusion identity or safeguards changed")
    _timestamp(manifest.get("generated_at"), "candidate-fusion generated_at")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != BUNDLE_FILES - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }:
        raise CandidateFusionError("candidate-fusion output inventory changed")
    for name, expected in outputs.items():
        checkpoint = _checkpoint(root / name)
        if checkpoint != {"bytes": expected.get("bytes"), "sha256": expected.get("sha256")}:
            raise CandidateFusionError(f"candidate-fusion output changed: {name}")
    lines = _read_json_lines(root / CANDIDATES_FILENAME, "fusion candidates")
    ranks = [line.get("review_priority", {}).get("fusion_rank") for line in lines]
    if ranks != list(range(1, len(lines) + 1)):
        raise CandidateFusionError("candidate-fusion ranks are not contiguous")
    if any(line.get("safeguards", {}).get("review_only") is not True for line in lines):
        raise CandidateFusionError("candidate-fusion row safeguards changed")
    if outputs[CANDIDATES_FILENAME].get("records") != len(lines) or outputs[
        CANDIDATES_CSV_FILENAME
    ].get("records") != len(lines):
        raise CandidateFusionError("candidate-fusion output record counts changed")
    coverage, coverage_raw = _json_object(root / COVERAGE_FILENAME, "candidate-fusion coverage")
    if coverage_raw != _canonical_json(coverage) or coverage != manifest.get("counts"):
        raise CandidateFusionError("candidate-fusion coverage does not match manifest")
    if coverage.get("primary_shortlist", {}).get(
        "candidates_with_any_fusion_opportunity"
    ) != len(lines):
        raise CandidateFusionError("candidate-fusion candidate count does not reconcile")
    if definition_path is not None:
        definition, definition_raw, definition_file = _load_definition(definition_path)
        if manifest.get("definition") != {
            "filename": definition_file.name,
            "bytes": len(definition_raw),
            "sha256": _sha256(definition_raw),
        }:
            raise CandidateFusionError("candidate-fusion definition lineage changed")
        inputs = _load_inputs(definition, definition_file)
        with inputs["atlas_path"].open("r", encoding="utf-8") as source:
            atlas_document = json.load(source)
        reproduced, reproduced_coverage = _derive(
            _feature_collection(inputs["primary_path"]),
            atlas_features=atlas_document["features"],
            overture_records=inputs["overture_records"],
            open_buildings=inputs["open_buildings"],
            queue_by_entity=inputs["queue_by_entity"],
            batch_states=inputs["batch_states"],
            analyst_reviews=inputs["analyst_reviews"],
            atlas_max_distance_m=float(definition["parameters"]["atlas_max_distance_m"]),
        )
        reproduced_coverage["osm_exact_identity_exclusions_before_fusion"] = inputs[
            "primary_manifest"
        ]["counts"]["known_exact_identity_exclusion_count"]
        reproduced_coverage["gdelt_lane"] = {
            "retained_manual_triage_leads": inputs["gdelt_retained"],
            "retained_leads_with_pinned_geometry": 0,
            "spatial_links": 0,
            "reason_not_spatially_joined": "retained_leads_have_no_pinned_geometry",
        }
        reproduced_coverage["sentinel_lane"]["queue_jobs_examined"] = inputs["queue_job_count"]
        reproduced_coverage["sentinel_lane"]["catalog_batch_jobs_examined"] = len(
            inputs["batch_states"]
        )
        reproduced_coverage["sentinel_lane"]["analyst_reviews_examined"] = len(
            inputs["analyst_reviews"]
        )
        if _payloads(reproduced, reproduced_coverage) != {
            name: (root / name).read_bytes()
            for name in BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
        }:
            raise CandidateFusionError("candidate-fusion outputs do not reproduce")
        if manifest.get("inputs") != inputs["lineage"]:
            raise CandidateFusionError("candidate-fusion input lineage changed")
    return manifest


__all__ = [
    "CandidateFusionError",
    "validate_candidate_fusion",
    "write_candidate_fusion",
]
