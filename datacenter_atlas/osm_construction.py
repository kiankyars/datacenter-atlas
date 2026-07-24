"""Review-only OSM Planet discovery for explicit structural construction tags.

The lane is intentionally not a data-centre classifier.  It preserves every
explicitly matched construction/proposed object, computes reproducible geometry
facts, and uses transparent size/tag/proximity rules only to prioritize manual
review.  Exact OSM identities already present in the canonical data-centre
layer are linked and excluded from the shortlist.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ElementTree

from .osm_planet import (
    MissingReferenceError,
    OSM_ATTRIBUTION,
    OSM_COPYRIGHT_URL,
    OSM_LICENSE,
    PlanetMaterializationError,
    TYPE_ORDER,
    _Resolver,
    _absolute,
    _base_element,
    _bounds,
    _center,
    _element_attributes,
    _local_name,
    _parse_coordinate,
    _parse_osm_id,
    _parse_tags,
    _point,
    _relation_polygon_geometry,
    _run,
    _safe_manifest_path,
    _write_bytes_atomic,
    canonical_json_bytes,
    convert_pbf_to_xml,
    inspect_file,
    is_exact_match,
    osmium_version,
    parse_osm_xml,
    pretty_json_bytes,
    sha256_bytes,
)


SCHEMA_VERSION = 1
EXTRACTION_PIPELINE = "openstreetmap_planet_structural_construction_extraction"
BUNDLE_PIPELINE = "openstreetmap_planet_structural_construction_candidates"
FILTER_VERSION = "osm-structural-construction-v1"
PRIOR_VERSION = "osm-structural-review-prior-v3"

DEFAULT_XML_FILENAME = "construction-filtered.osm"
MATCHES_FILENAME = "construction-matches.jsonl.gz"
POWER_CONTEXT_FILENAME = "power-context.jsonl.gz"
PRIMARY_PBF_FILENAME = "primary-matches-with-references.osm.pbf"
SHORTLIST_GEOJSON_FILENAME = "shortlist.geojson"
SHORTLIST_CSV_FILENAME = "shortlist.csv"
KNOWN_LINKS_FILENAME = "known-data-centre-links.json"
MANIFEST_FILENAME = "manifest.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"

PHASE_VALUES_BY_KEY: dict[str, frozenset[str]] = {
    "building": frozenset({"construction", "proposed"}),
    "landuse": frozenset({"construction", "proposed"}),
    "site": frozenset({"construction", "proposed"}),
    "man_made": frozenset({"construction", "proposed"}),
    "industrial": frozenset({"construction", "proposed"}),
    "power": frozenset({"construction", "proposed"}),
}
NESTED_PHASE_KEYS = (
    "construction:building",
    "proposed:building",
    "construction:landuse",
    "proposed:landuse",
    "construction:site",
    "proposed:site",
    "construction:man_made",
    "proposed:man_made",
    "construction:industrial",
    "proposed:industrial",
    "construction:power",
    "proposed:power",
)
DIRECT_STRUCTURAL_VALUES = (
    "building",
    "commercial",
    "factory",
    "industrial",
    "logistics",
    "manufacture",
    "manufacturing",
    "plant",
    "storage",
    "warehouse",
    "works",
)
POWER_CONTEXT_VALUES = ("plant", "substation")
ADDITIONAL_PRIMARY_TAGS = (("man_made", "foundation"),)
POWER_ASSET_VALUES = frozenset({"generator", "plant", "substation", "transformer"})

INDUSTRIAL_TOKENS = frozenset(
    {
        "commercial",
        "distribution",
        "factory",
        "industrial",
        "logistics",
        "manufacture",
        "manufacturing",
        "plant",
        "storage",
        "warehouse",
        "works",
    }
)
ELECTRICAL_TOKENS = frozenset(
    {"electric", "electrical", "generator", "power", "substation", "transformer"}
)
STRUCTURAL_PRIOR_KEYS = frozenset(
    {
        "building",
        "construction",
        "industrial",
        "landuse",
        "man_made",
        "power",
        "proposed",
        "site",
        *NESTED_PHASE_KEYS,
    }
)

PRIOR_CONTRACT = {
    "version": PRIOR_VERSION,
    "industrial_tokens": sorted(INDUSTRIAL_TOKENS),
    "electrical_tokens": sorted(ELECTRICAL_TOKENS),
    "structural_source_tag_keys": sorted(STRUCTURAL_PRIOR_KEYS),
    "power_context_values": list(POWER_CONTEXT_VALUES),
    "explicit_power_asset_exclusion": {
        "power_values": sorted(POWER_ASSET_VALUES),
        "phase_power_keys": ["construction:power", "proposed:power"],
        "direct_phase_values": sorted({*POWER_ASSET_VALUES, "power"}),
        "direct_phase_power_prefix_excluded": True,
        "industrial_values": ["power", "power_generation"],
        "power_asset_namespace_prefixes": [
            "generator:",
            "plant:",
            "substation:",
            "transformer:",
        ],
    },
    "footprint_area_points": [
        {"minimum_square_metres": 100_000, "points": 4},
        {"minimum_square_metres": 50_000, "points": 3},
        {"minimum_square_metres": 20_000, "points": 2},
        {"minimum_square_metres": 10_000, "points": 1},
    ],
    "explicit_industrial_source_tag_points": 2,
    "explicit_electrical_source_tag_points": 2,
    "nearest_power_context_points": [
        {"maximum_metres": 2_000, "points": 2},
        {"maximum_metres": 5_000, "points": 1},
    ],
    "shortlist_minimum_footprint_square_metres": 10_000,
    "shortlist_minimum_points": 3,
    "known_exact_osm_identities_excluded": True,
    "identity_capacity_workload_or_source_status_inference": False,
    "review_only": True,
}


@dataclass(frozen=True, slots=True)
class ConstructionExtractionInput:
    manifest_path: Path
    manifest_raw: bytes
    document: dict[str, Any]
    pbf_path: Path
    pbf_facts: dict[str, Any]
    source_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class KnownExactLayer:
    manifest_path: Path
    manifest_raw: bytes
    document: dict[str, Any]
    json_path: Path
    json_raw: bytes
    identities: frozenset[tuple[str, int]]
    elements: dict[tuple[str, int], dict[str, Any]]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def osmium_filter_expressions() -> tuple[str, ...]:
    exact = [
        f"nwr/{key}={value}"
        for key in sorted(PHASE_VALUES_BY_KEY)
        for value in sorted(PHASE_VALUES_BY_KEY[key])
    ]
    nested = [f"nwr/{key}" for key in NESTED_PHASE_KEYS]
    direct = [
        f"nwr/{key}={value}"
        for key in ("construction", "proposed")
        for value in DIRECT_STRUCTURAL_VALUES
    ]
    additional = [f"nwr/{key}={value}" for key, value in ADDITIONAL_PRIMARY_TAGS]
    context = [f"nwr/power={value}" for value in POWER_CONTEXT_VALUES]
    return tuple((*exact, *nested, *direct, *additional, *context))


def filter_manifest_document() -> dict[str, Any]:
    expressions = osmium_filter_expressions()
    primary_count = len(expressions) - len(POWER_CONTEXT_VALUES)
    contract: dict[str, Any] = {
        "version": FILTER_VERSION,
        "osmium_expressions": list(expressions),
        "primary_expression_count": primary_count,
        "context_expression_count": len(POWER_CONTEXT_VALUES),
        "primary_match_scope": "explicit_structural_construction_or_proposed_tags_only",
        "context_match_scope": "power_plant_or_substation_tags_only",
        "generic_construction_or_proposed_wildcards_used": False,
        "name_or_free_text_search_used": False,
        "road_rail_or_waterway_filters_used": False,
        "object_types": ["node", "way", "relation"],
        "referenced_nodes_and_members_retained": True,
        "omit_referenced_flag_used": False,
        "output_object_counts_include_references": True,
        "converted_to_geojson_during_extraction": False,
    }
    contract["contract_sha256"] = sha256_bytes(canonical_json_bytes(contract))
    return contract


FILTER_SHA256 = filter_manifest_document()["contract_sha256"]
PRIOR_SHA256 = sha256_bytes(canonical_json_bytes(PRIOR_CONTRACT))


def primary_trigger_tags(tags: Mapping[str, str]) -> list[dict[str, str]]:
    triggers: list[dict[str, str]] = []
    for key in sorted(PHASE_VALUES_BY_KEY):
        value = tags.get(key)
        if value in PHASE_VALUES_BY_KEY[key]:
            triggers.append({"key": key, "value": value, "rule": "phase_value"})
    for key in NESTED_PHASE_KEYS:
        value = tags.get(key)
        if isinstance(value, str):
            triggers.append({"key": key, "value": value, "rule": "nested_phase_key"})
    for key in ("construction", "proposed"):
        value = tags.get(key)
        if value in DIRECT_STRUCTURAL_VALUES:
            triggers.append({"key": key, "value": value, "rule": "structural_allowlist"})
    for key, allowed_value in ADDITIONAL_PRIMARY_TAGS:
        value = tags.get(key)
        if value == allowed_value:
            triggers.append({"key": key, "value": value, "rule": "explicit_foundation"})
    return triggers


def is_power_context(tags: Mapping[str, str]) -> bool:
    return tags.get("power") in POWER_CONTEXT_VALUES


def is_explicit_power_asset(tags: Mapping[str, str]) -> bool:
    if tags.get("power") in POWER_ASSET_VALUES:
        return True
    if any(tags.get(key) in POWER_ASSET_VALUES for key in ("construction:power", "proposed:power")):
        return True
    for key in ("construction", "proposed"):
        value = tags.get(key)
        if value in POWER_ASSET_VALUES or value == "power" or (
            isinstance(value, str) and value.startswith("power:")
        ):
            return True
    if tags.get("industrial") in {"power", "power_generation"}:
        return True
    prefixes = ("generator:", "plant:", "substation:", "transformer:")
    return any(key.startswith(prefixes) for key in tags)


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink {label}: {path}")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise PlanetMaterializationError(f"{label} is missing: {path}") from error
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlanetMaterializationError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(document, dict):
        raise PlanetMaterializationError(f"{label} must be a JSON object")
    return document, raw


def _record_path(base: Path, value: Any, label: str) -> Path:
    return _safe_manifest_path(base, value, label)


def validate_extraction_input(
    extraction_manifest: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
) -> ConstructionExtractionInput:
    manifest_path = _absolute(extraction_manifest)
    document, raw = _read_json(manifest_path, "construction extraction manifest")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "pipeline": EXTRACTION_PIPELINE,
        "state": "completed",
        "review_only": True,
        "filter": filter_manifest_document(),
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise PlanetMaterializationError(
                f"construction extraction manifest {key} does not match"
            )
    rights = document.get("rights")
    if rights != {
        "license": OSM_LICENSE,
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
    }:
        raise PlanetMaterializationError("construction extraction rights do not match")
    record = document.get("output")
    if not isinstance(record, Mapping):
        raise PlanetMaterializationError("construction extraction output is missing")
    record_path = _record_path(manifest_path.parent, record.get("path"), "construction PBF")
    pbf_path = _absolute(filtered_pbf) if filtered_pbf is not None else record_path
    if pbf_path != record_path:
        raise PlanetMaterializationError(
            "explicit construction PBF does not match the extraction manifest"
        )
    facts = inspect_file(pbf_path, ("md5", "sha256"))
    for key in ("bytes", "md5", "sha256"):
        if record.get(key) != facts[key]:
            raise PlanetMaterializationError(
                f"construction extraction output {key} does not match"
            )
    source = document.get("source")
    if not isinstance(source, Mapping) or source.get("snapshot_date") != document.get(
        "snapshot_date"
    ):
        raise PlanetMaterializationError("construction Planet source lineage is malformed")
    if not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64:
        raise PlanetMaterializationError("construction Planet source SHA256 is malformed")
    verification = source.get("verification")
    if not isinstance(verification, Mapping) or any(
        verification.get(key) is not True
        for key in ("exact_size", "official_md5", "verified_before_extraction")
    ):
        raise PlanetMaterializationError("construction Planet verification is incomplete")
    fileinfo = document.get("fileinfo")
    counts = (
        fileinfo.get("object_counts_including_references")
        if isinstance(fileinfo, Mapping)
        else None
    )
    if not isinstance(counts, Mapping):
        raise PlanetMaterializationError("construction extraction counts are missing")
    normalized: dict[str, int] = {}
    for singular, plural in (("node", "nodes"), ("way", "ways"), ("relation", "relations")):
        value = counts.get(plural)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PlanetMaterializationError(f"construction {plural} count is invalid")
        normalized[singular] = value
    return ConstructionExtractionInput(
        manifest_path, raw, document, pbf_path, facts, normalized
    )


def load_known_exact_layer(
    exact_manifest: str | Path,
    *,
    expected_planet_sha256: str,
) -> KnownExactLayer:
    manifest_path = _absolute(exact_manifest)
    document, manifest_raw = _read_json(manifest_path, "exact OSM materialization manifest")
    if (
        document.get("pipeline") != "openstreetmap_planet_materialize"
        or document.get("state") != "completed"
    ):
        raise PlanetMaterializationError("exact OSM materialization is not completed")
    planet = document.get("inputs", {}).get("planet_source")
    if not isinstance(planet, Mapping) or planet.get("sha256") != expected_planet_sha256:
        raise PlanetMaterializationError(
            "exact OSM layer and construction extraction use different Planet bytes"
        )
    record = document.get("outputs", {}).get("overpass_json")
    if not isinstance(record, Mapping):
        raise PlanetMaterializationError("exact OSM overpass output is missing")
    json_path = _record_path(manifest_path.parent, record.get("path"), "exact OSM JSON")
    json_document, json_raw = _read_json(json_path, "exact OSM JSON")
    actual = {
        "bytes": len(json_raw),
        "md5": hashlib.md5(json_raw).hexdigest(),
        "sha256": sha256_bytes(json_raw),
    }
    for key, value in actual.items():
        if record.get(key) != value:
            raise PlanetMaterializationError(f"exact OSM JSON {key} does not match")
    raw_elements = json_document.get("elements")
    if not isinstance(raw_elements, list):
        raise PlanetMaterializationError("exact OSM JSON elements are missing")
    elements: dict[tuple[str, int], dict[str, Any]] = {}
    for raw_element in raw_elements:
        if not isinstance(raw_element, Mapping):
            raise PlanetMaterializationError("exact OSM element is malformed")
        object_type, element_id = raw_element.get("type"), raw_element.get("id")
        identity = (object_type, element_id)
        if object_type not in TYPE_ORDER or not isinstance(element_id, int) or element_id <= 0:
            raise PlanetMaterializationError("exact OSM identity is malformed")
        if identity in elements:
            raise PlanetMaterializationError("exact OSM JSON contains a duplicate identity")
        elements[identity] = dict(raw_element)
    if record.get("element_count") != len(elements):
        raise PlanetMaterializationError("exact OSM element count does not match")
    return KnownExactLayer(
        manifest_path,
        manifest_raw,
        document,
        json_path,
        json_raw,
        frozenset(elements),
        elements,
    )


def _element_url(object_type: str, element_id: int) -> str:
    return f"https://www.openstreetmap.org/{object_type}/{element_id}"


def _materialize_element(
    object_type: str,
    record: Any,
    parsed: Any,
    resolver: _Resolver,
) -> dict[str, Any]:
    output = _base_element(object_type, record.element_id, record.attributes, record.tags)
    output["source_url"] = _element_url(object_type, record.element_id)
    if object_type == "node":
        point = _point(record)
        if point is None:
            resolver._record_missing("node", record.element_id, "coordinate", record.element_id)
        else:
            output.update(point)
        return output
    if object_type == "way":
        output["nodes"] = list(record.node_refs)
        geometry = resolver.way_points(record)
        if geometry:
            bounds = _bounds(geometry)
            output["geometry"] = geometry
            if bounds is not None:
                output["bounds"] = bounds
                output["center"] = _center(bounds)
        else:
            output["geometry_status"] = "unavailable_no_coordinates"
        return output
    output["members"] = resolver.relation_members(record)
    geometry, report = _relation_polygon_geometry(record, parsed, resolver)
    if report is not None:
        output["geometry_assembly"] = report
    if geometry is not None:
        output["geometry"] = geometry
        coordinates = list(_iter_geojson_points(geometry))
        bounds = _bounds({"lat": lat, "lon": lon} for lon, lat in coordinates)
        if bounds is not None:
            output["bounds"] = bounds
            output["center"] = _center(bounds)
    else:
        points = resolver.relation_points(record)
        bounds = _bounds(points)
        if bounds is not None:
            output["bounds"] = bounds
            output["center"] = _center(bounds)
            output["geometry_status"] = "non_polygon_bounds_only"
        else:
            output["geometry_status"] = "unavailable_no_coordinates"
    return output


def _iter_geojson_points(geometry: Mapping[str, Any]) -> Iterable[tuple[float, float]]:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon" and isinstance(coordinates, list):
        polygons = [coordinates]
    elif geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        polygons = coordinates
    else:
        return
    for polygon in polygons:
        for ring in polygon:
            for point in ring:
                if isinstance(point, list) and len(point) >= 2:
                    yield float(point[0]), float(point[1])


def _polygon_geometry(element: Mapping[str, Any]) -> dict[str, Any] | None:
    geometry = element.get("geometry")
    if (
        isinstance(geometry, Mapping)
        and geometry.get("type") in {"Polygon", "MultiPolygon"}
    ):
        return dict(geometry)
    if element.get("type") == "way" and isinstance(geometry, list):
        coordinates = [
            [float(point["lon"]), float(point["lat"])]
            for point in geometry
            if isinstance(point, Mapping) and "lon" in point and "lat" in point
        ]
        if len(coordinates) >= 4 and coordinates[0] == coordinates[-1]:
            return {"type": "Polygon", "coordinates": [coordinates]}
        return None
    return None


def _unwrap_longitudes(points: Sequence[Sequence[float]]) -> list[float]:
    if not points:
        return []
    values = [float(points[0][0])]
    for point in points[1:]:
        value = float(point[0])
        while value - values[-1] > 180:
            value -= 360
        while value - values[-1] < -180:
            value += 360
        values.append(value)
    return values


def _ring_area_square_metres(points: Sequence[Sequence[float]]) -> float:
    if len(points) < 4:
        return 0.0
    longitudes = _unwrap_longitudes(points)
    latitudes = [float(point[1]) for point in points]
    latitude_origin = math.radians(sum(latitudes[:-1]) / max(1, len(latitudes) - 1))
    radius = 6_371_008.8
    projected = [
        (
            radius * math.radians(longitude) * math.cos(latitude_origin),
            radius * math.radians(latitude),
        )
        for longitude, latitude in zip(longitudes, latitudes)
    ]
    return abs(
        sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(projected, projected[1:]))
    ) / 2


def footprint_area_square_metres(geometry: Mapping[str, Any] | None) -> float | None:
    if geometry is None:
        return None
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon" and isinstance(coordinates, list):
        polygons = [coordinates]
    elif geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        polygons = coordinates
    else:
        return None
    total = 0.0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            continue
        outer = _ring_area_square_metres(polygon[0])
        holes = sum(_ring_area_square_metres(ring) for ring in polygon[1:])
        total += max(0.0, outer - holes)
    return round(total, 3) if total > 0 else None


def _tag_tokens(tags: Mapping[str, str]) -> set[str]:
    tokens: set[str] = set()
    for key, value in tags.items():
        if key not in STRUCTURAL_PRIOR_KEYS:
            continue
        normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
        tokens.update(normalized.split())
    return tokens


def _source_tag_families(triggers: Sequence[Mapping[str, str]]) -> list[str]:
    families: set[str] = set()
    for trigger in triggers:
        key, value = trigger["key"], trigger["value"]
        if key.startswith("construction") or value == "construction":
            families.add("construction")
        if key.startswith("proposed") or value == "proposed":
            families.add("proposed")
    return sorted(families)


def _center_of(element: Mapping[str, Any]) -> tuple[float, float] | None:
    if element.get("type") == "node" and isinstance(element.get("lat"), (int, float)):
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, Mapping) and isinstance(center.get("lat"), (int, float)):
        return float(center["lat"]), float(center["lon"])
    return None


def _haversine_metres(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_latitude, delta_longitude = lat2 - lat1, lon2 - lon1
    value = math.sin(delta_latitude / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(value)))


class _PowerIndex:
    def __init__(self, contexts: Sequence[Mapping[str, Any]]) -> None:
        self.cells: dict[tuple[int, int], list[tuple[tuple[float, float], Mapping[str, Any]]]] = defaultdict(list)
        for context in contexts:
            center = _center_of(context)
            if center is None:
                continue
            self.cells[(math.floor(center[0]), math.floor(center[1]))].append((center, context))

    def nearest(
        self, center: tuple[float, float], maximum_metres: float = 5_000
    ) -> tuple[float, Mapping[str, Any]] | None:
        latitude, longitude = center
        latitude_cell, longitude_cell = math.floor(latitude), math.floor(longitude)
        cosine = max(0.001, abs(math.cos(math.radians(latitude))))
        longitude_degrees = maximum_metres / (111_320 * cosine)
        longitude_span = min(360, math.ceil(longitude_degrees) + 1)
        best: tuple[float, Mapping[str, Any]] | None = None
        for candidate_latitude in range(latitude_cell - 1, latitude_cell + 2):
            for offset in range(-longitude_span, longitude_span + 1):
                candidate_longitude = ((longitude_cell + offset + 180) % 360) - 180
                for point, context in self.cells.get((candidate_latitude, candidate_longitude), ()):
                    distance = _haversine_metres(center, point)
                    if distance <= maximum_metres and (best is None or distance < best[0]):
                        best = (distance, context)
        return best


def _area_points(area: float | None) -> int:
    if area is None:
        return 0
    if area >= 100_000:
        return 4
    if area >= 50_000:
        return 3
    if area >= 20_000:
        return 2
    if area >= 10_000:
        return 1
    return 0


def _score_candidate(
    element: dict[str, Any],
    triggers: Sequence[Mapping[str, str]],
    power_index: _PowerIndex,
) -> dict[str, Any]:
    polygon = _polygon_geometry(element)
    area = footprint_area_square_metres(polygon)
    tokens = _tag_tokens(element["tags"])
    industrial = bool(tokens & INDUSTRIAL_TOKENS)
    explicit_power_asset = is_explicit_power_asset(element["tags"])
    electrical = (
        any(trigger["key"].endswith("power") or trigger["key"] == "power" for trigger in triggers)
        or bool(tokens & ELECTRICAL_TOKENS)
    )
    center = _center_of(element)
    nearest = power_index.nearest(center) if center is not None else None
    points = _area_points(area)
    reasons: list[dict[str, Any]] = []
    if points:
        reasons.append({"signal": "footprint_area", "points": points, "square_metres": area})
    if industrial:
        points += 2
        reasons.append({"signal": "explicit_industrial_source_tag", "points": 2})
    if electrical:
        points += 2
        reasons.append({"signal": "explicit_electrical_source_tag", "points": 2})
    nearest_record = None
    if nearest is not None:
        distance, context = nearest
        adjacency_points = 2 if distance <= 2_000 else 1
        points += adjacency_points
        nearest_record = {
            "distance_metres": round(distance, 3),
            "type": context["type"],
            "id": context["id"],
            "source_url": context["source_url"],
            "power_tag": context["tags"]["power"],
        }
        reasons.append(
            {
                "signal": "nearest_power_context_center_distance",
                "points": adjacency_points,
                **nearest_record,
            }
        )
    return {
        "footprint_square_metres": area,
        "explicit_industrial_source_tag": industrial,
        "explicit_electrical_source_tag": electrical,
        "explicit_power_asset_source_tag": explicit_power_asset,
        "nearest_power_context": nearest_record,
        "review_score": points,
        "review_reasons": reasons,
        "shortlisted": (
            not explicit_power_asset
            and area is not None
            and area >= 10_000
            and points >= 3
        ),
    }


def _counts_by_type(elements: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(element["type"]) for element in elements)
    return {
        "node": counts["node"],
        "way": counts["way"],
        "relation": counts["relation"],
        "total": sum(counts.values()),
    }


def build_candidate_documents(
    parsed: Any,
    known_exact: KnownExactLayer,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    resolver = _Resolver(parsed)
    primary: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    triggers_by_identity: dict[tuple[str, int], list[dict[str, str]]] = {}
    for object_type, table in (
        ("node", parsed.nodes),
        ("way", parsed.ways),
        ("relation", parsed.relations),
    ):
        for element_id in sorted(table):
            record = table[element_id]
            triggers = primary_trigger_tags(record.tags)
            context = is_power_context(record.tags)
            if not triggers and not context:
                continue
            materialized = _materialize_element(object_type, record, parsed, resolver)
            if triggers:
                materialized["discovery"] = {
                    "filter_version": FILTER_VERSION,
                    "trigger_tags": triggers,
                    "source_tag_families": _source_tag_families(triggers),
                    "review_only": True,
                    "data_centre_identity_inferred": False,
                }
                primary.append(materialized)
                triggers_by_identity[(object_type, element_id)] = triggers
            if context:
                center = _center_of(materialized)
                context_record = {
                    "type": object_type,
                    "id": element_id,
                    "source_url": materialized["source_url"],
                    "tags": materialized["tags"],
                    "center": ({"lat": center[0], "lon": center[1]} if center else None),
                }
                contexts.append(context_record)
    if resolver.missing:
        raise MissingReferenceError(resolver.missing)

    power_index = _PowerIndex(contexts)
    known_links: list[dict[str, Any]] = []
    shortlist: list[dict[str, Any]] = []
    geometry_unavailable = 0
    for element in primary:
        identity = (element["type"], element["id"])
        if is_exact_match(element["tags"]) and identity not in known_exact.identities:
            raise PlanetMaterializationError(
                f"{identity[0]}/{identity[1]} has a canonical exact data-centre tag "
                "but is absent from the hash-bound exact layer"
            )
        score = _score_candidate(element, triggers_by_identity[identity], power_index)
        element["review_prior"] = score
        if score["footprint_square_metres"] is None:
            geometry_unavailable += 1
        if identity in known_exact.identities:
            exact_element = known_exact.elements[identity]
            link = {
                "type": identity[0],
                "id": identity[1],
                "source_url": element["source_url"],
                "link_method": "identical_osm_object_type_and_id",
                "exact_layer_source_tags": exact_element.get("tags", {}),
                "excluded_from_shortlist": True,
            }
            element["known_exact_data_centre_layer_link"] = link
            known_links.append(link)
            continue
        if score["shortlisted"]:
            shortlist.append(element)

    shortlist.sort(
        key=lambda item: (
            -item["review_prior"]["review_score"],
            -item["review_prior"]["footprint_square_metres"],
            TYPE_ORDER[item["type"]],
            item["id"],
        )
    )
    known_links.sort(key=lambda item: (TYPE_ORDER[item["type"]], item["id"]))
    matches_document = {
        "schema_version": SCHEMA_VERSION,
        "generator": "DataCenterAtlas/0.1 OSM structural construction discovery",
        "review_only": True,
        "selection": "all_explicit_primary_filter_matches_exactly_once",
        "filter": filter_manifest_document(),
        "rights": {
            "license": OSM_LICENSE,
            "attribution": OSM_ATTRIBUTION,
            "copyright_url": OSM_COPYRIGHT_URL,
        },
        "elements": primary,
    }
    contexts_document = {
        "schema_version": SCHEMA_VERSION,
        "review_only": True,
        "selection": "power_plant_or_substation_context_centres",
        "distance_role": "context_only_not_evidence_of_data_centre_identity",
        "elements": contexts,
        "rights": {
            "license": OSM_LICENSE,
            "attribution": OSM_ATTRIBUTION,
            "copyright_url": OSM_COPYRIGHT_URL,
        },
    }
    links_document = {
        "schema_version": SCHEMA_VERSION,
        "review_only": True,
        "link_method": "identical_osm_object_type_and_id",
        "exact_layer_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
        "exact_layer_json_sha256": sha256_bytes(known_exact.json_raw),
        "links": known_links,
    }
    integrity = {
        "source_object_counts_including_references": {
            key: parsed.source_counts.get(key, 0) for key in TYPE_ORDER
        },
        "raw_primary_match_counts": _counts_by_type(primary),
        "power_context_counts": _counts_by_type(contexts),
        "reference_only_object_count": sum(parsed.source_counts.values())
        - len({(element["type"], element["id"]) for element in (*primary, *contexts)}),
        "shortlisted_counts": _counts_by_type(shortlist),
        "known_exact_identity_exclusion_count": len(known_links),
        "raw_matches_without_polygon_footprint_count": geometry_unavailable,
        "missing_reference_count": 0,
        "all_primary_matches_emitted_once": len(primary)
        == len({(element["type"], element["id"]) for element in primary}),
        "identity_capacity_workload_or_source_status_inference": False,
    }
    return matches_document, contexts_document, links_document, shortlist, integrity


def _shortlist_geojson(shortlist: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for element in shortlist:
        geometry = _polygon_geometry(element)
        if geometry is None:
            raise PlanetMaterializationError("shortlisted element has no polygon geometry")
        prior = element["review_prior"]
        features.append(
            {
                "type": "Feature",
                "id": f"{element['type']}/{element['id']}",
                "geometry": geometry,
                "properties": {
                    "osm_type": element["type"],
                    "osm_id": element["id"],
                    "source_url": element["source_url"],
                    "source_tags": element["tags"],
                    "trigger_tags": element["discovery"]["trigger_tags"],
                    "source_tag_families": element["discovery"]["source_tag_families"],
                    **prior,
                    "review_only": True,
                    "data_centre_identity_inferred": False,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "OSM structural construction review shortlist",
        "review_only": True,
        "features": features,
    }


def _shortlist_csv(shortlist: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = (
        "rank",
        "osm_type",
        "osm_id",
        "source_url",
        "footprint_square_metres",
        "review_score",
        "source_tag_families_json",
        "trigger_tags_json",
        "explicit_industrial_source_tag",
        "explicit_electrical_source_tag",
        "explicit_power_asset_source_tag",
        "nearest_power_context_json",
        "source_tags_json",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for rank, element in enumerate(shortlist, 1):
        prior = element["review_prior"]
        writer.writerow(
            {
                "rank": rank,
                "osm_type": element["type"],
                "osm_id": element["id"],
                "source_url": element["source_url"],
                "footprint_square_metres": prior["footprint_square_metres"],
                "review_score": prior["review_score"],
                "source_tag_families_json": json.dumps(element["discovery"]["source_tag_families"], sort_keys=True),
                "trigger_tags_json": json.dumps(element["discovery"]["trigger_tags"], sort_keys=True),
                "explicit_industrial_source_tag": str(prior["explicit_industrial_source_tag"]).lower(),
                "explicit_electrical_source_tag": str(prior["explicit_electrical_source_tag"]).lower(),
                "explicit_power_asset_source_tag": str(prior["explicit_power_asset_source_tag"]).lower(),
                "nearest_power_context_json": json.dumps(prior["nearest_power_context"], sort_keys=True),
                "source_tags_json": json.dumps(element["tags"], sort_keys=True, ensure_ascii=False),
            }
        )
    return output.getvalue().encode("utf-8")


def _readme(integrity: Mapping[str, Any], snapshot_date: Any) -> bytes:
    raw = integrity["raw_primary_match_counts"]["total"]
    shortlisted = integrity["shortlisted_counts"]["total"]
    excluded = integrity["known_exact_identity_exclusion_count"]
    return f"""# OSM structural construction review candidates

This immutable, review-only bundle comes from the official {snapshot_date} OpenStreetMap Planet.
It materializes all {raw:,} objects matched by the versioned explicit structural construction filter
and prioritizes {shortlisted:,} large, industrial-tagged, or power-context-adjacent polygon objects.

These are **not identified data centres**. Size, source tags, and distance to a mapped power object
are review priors only. The pipeline infers no data-centre identity, capacity, workload, operator,
or lifecycle state beyond preserving the source tags. {excluded:,} objects sharing an exact OSM
type/ID with the canonical exact data-centre tag layer are linked in
`{KNOWN_LINKS_FILENAME}` and excluded from the shortlist.

Objects explicitly source-tagged as power plants, substations, generators, or transformers remain
in the raw/context layers but are excluded from the shortlist as known power assets. This prevents a
power project from ranking itself through a zero-distance context match.

`{MATCHES_FILENAME}` is the lossless matched-object layer. `{SHORTLIST_GEOJSON_FILENAME}` and
`{SHORTLIST_CSV_FILENAME}` are ordered review queues. `{POWER_CONTEXT_FILENAME}` contains only the
mapped power-object centres used by the distance prior. See `manifest.json` for byte hashes,
filter/prior contracts, counts, and complete lineage.

OpenStreetMap-derived data is © OpenStreetMap contributors and licensed ODbL 1.0.
""".encode("utf-8")


def _attribution() -> bytes:
    return (
        "© OpenStreetMap contributors\n"
        "License: Open Database License (ODbL) 1.0\n"
        "https://www.openstreetmap.org/copyright\n"
    ).encode("utf-8")


def _output_record(path: Path) -> dict[str, Any]:
    return {"path": path.name, **inspect_file(path, ("md5", "sha256"))}


def _validate_existing_bundle(
    destination: Path,
    extraction: ConstructionExtractionInput,
    known_exact: KnownExactLayer,
) -> dict[str, Any]:
    manifest, _ = _read_json(destination / MANIFEST_FILENAME, "candidate bundle manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != BUNDLE_PIPELINE
        or manifest.get("state") != "completed"
        or manifest.get("review_only") is not True
        or manifest.get("filter") != filter_manifest_document()
        or manifest.get("review_prior") != {
            **PRIOR_CONTRACT,
            "contract_sha256": PRIOR_SHA256,
        }
    ):
        raise PlanetMaterializationError("existing candidate bundle contract does not match")
    expected_inputs = {
        "construction_extraction_manifest_sha256": sha256_bytes(extraction.manifest_raw),
        "construction_filtered_pbf_sha256": extraction.pbf_facts["sha256"],
        "known_exact_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
        "known_exact_json_sha256": sha256_bytes(known_exact.json_raw),
        "planet_sha256": extraction.document["source"]["sha256"],
    }
    if manifest.get("input_hashes") != expected_inputs:
        raise PlanetMaterializationError("existing candidate bundle input hashes do not match")
    outputs = manifest.get("outputs")
    expected_names = {
        MATCHES_FILENAME,
        POWER_CONTEXT_FILENAME,
        SHORTLIST_GEOJSON_FILENAME,
        SHORTLIST_CSV_FILENAME,
        KNOWN_LINKS_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
    if not isinstance(outputs, Mapping) or set(outputs) != expected_names:
        raise PlanetMaterializationError("existing candidate bundle output inventory is invalid")
    for name in sorted(expected_names):
        record = outputs[name]
        if not isinstance(record, Mapping) or record.get("path") != name:
            raise PlanetMaterializationError(f"existing candidate output {name} is malformed")
        facts = inspect_file(destination / name, ("md5", "sha256"))
        if any(record.get(key) != facts[key] for key in ("bytes", "md5", "sha256")):
            raise PlanetMaterializationError(f"existing candidate output {name} hash does not match")
    return manifest


def _materialize_construction_candidates_in_memory(
    extraction_manifest: str | Path,
    exact_materialization_manifest: str | Path,
    output_directory: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    extraction = validate_extraction_input(extraction_manifest, filtered_pbf=filtered_pbf)
    known_exact = load_known_exact_layer(
        exact_materialization_manifest,
        expected_planet_sha256=extraction.document["source"]["sha256"],
    )
    destination = _absolute(output_directory)
    if destination.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink output directory: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise PlanetMaterializationError("candidate output exists and is not a directory")
        return _validate_existing_bundle(destination, extraction, known_exact)
    planned_command = [
        osmium_binary,
        "cat",
        "--no-progress",
        str(extraction.pbf_path),
        "--output",
        DEFAULT_XML_FILENAME,
        "--output-format",
        "osm",
        "--fsync",
    ]
    if dry_run:
        return {
            "schema_version": SCHEMA_VERSION,
            "pipeline": BUNDLE_PIPELINE,
            "state": "dry_run",
            "review_only": True,
            "filter": filter_manifest_document(),
            "review_prior": {**PRIOR_CONTRACT, "contract_sha256": PRIOR_SHA256},
            "planned_command": planned_command,
            "output_directory": str(destination),
            "writes_performed": False,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    try:
        version = osmium_version(osmium_binary=osmium_binary, runner=runner)
        xml_path = stage / DEFAULT_XML_FILENAME
        command = convert_pbf_to_xml(
            extraction.pbf_path, xml_path, osmium_binary=osmium_binary, runner=runner
        )
        parsed = parse_osm_xml(xml_path)
        parsed_counts = {key: parsed.source_counts.get(key, 0) for key in TYPE_ORDER}
        if parsed_counts != extraction.source_counts:
            raise PlanetMaterializationError(
                f"construction XML counts {parsed_counts} do not match {extraction.source_counts}"
            )
        matches, contexts, links, shortlist, integrity = build_candidate_documents(
            parsed, known_exact
        )
        payloads = {
            MATCHES_FILENAME: canonical_json_bytes(matches),
            POWER_CONTEXT_FILENAME: canonical_json_bytes(contexts),
            SHORTLIST_GEOJSON_FILENAME: canonical_json_bytes(_shortlist_geojson(shortlist)),
            SHORTLIST_CSV_FILENAME: _shortlist_csv(shortlist),
            KNOWN_LINKS_FILENAME: canonical_json_bytes(links),
            README_FILENAME: _readme(integrity, extraction.document.get("snapshot_date")),
            ATTRIBUTION_FILENAME: _attribution(),
        }
        for name, payload in payloads.items():
            _write_bytes_atomic(stage / name, payload)
        outputs = {name: _output_record(stage / name) for name in sorted(payloads)}
        input_hashes = {
            "construction_extraction_manifest_sha256": sha256_bytes(extraction.manifest_raw),
            "construction_filtered_pbf_sha256": extraction.pbf_facts["sha256"],
            "known_exact_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
            "known_exact_json_sha256": sha256_bytes(known_exact.json_raw),
            "planet_sha256": extraction.document["source"]["sha256"],
        }
        relative_command = [
            str(item).replace(str(stage) + os.sep, "") for item in command
        ]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": BUNDLE_PIPELINE,
            "state": "completed",
            "review_only": True,
            "candidate_layer_not_data_centre_census": True,
            "materialized_at": clock(),
            "snapshot_date": extraction.document.get("snapshot_date"),
            "input_hashes": input_hashes,
            "inputs": {
                "construction_extraction_manifest": {
                    "path": os.path.relpath(extraction.manifest_path, destination),
                    "bytes": len(extraction.manifest_raw),
                    "sha256": input_hashes["construction_extraction_manifest_sha256"],
                    "pipeline": extraction.document.get("pipeline"),
                },
                "construction_filtered_pbf": {
                    "path": os.path.relpath(extraction.pbf_path, destination),
                    **extraction.pbf_facts,
                },
                "known_exact_materialization_manifest": {
                    "path": os.path.relpath(known_exact.manifest_path, destination),
                    "bytes": len(known_exact.manifest_raw),
                    "sha256": input_hashes["known_exact_manifest_sha256"],
                    "pipeline": known_exact.document.get("pipeline"),
                },
                "known_exact_json": {
                    "path": os.path.relpath(known_exact.json_path, destination),
                    "bytes": len(known_exact.json_raw),
                    "sha256": input_hashes["known_exact_json_sha256"],
                },
                "planet_source": extraction.document.get("source"),
            },
            "filter": filter_manifest_document(),
            "review_prior": {**PRIOR_CONTRACT, "contract_sha256": PRIOR_SHA256},
            "transform": {
                "bridge": "filtered_pbf_to_osm_xml_to_lossless_matches_and_review_shortlist",
                "command": relative_command,
                "tool_version": version,
                "references_required": True,
                "footprint_method": "local_equirectangular_shoelace_outer_minus_inner_rings",
                "power_distance_method": "haversine_between_object_bounds_centres",
                "known_identity_link_method": "identical_osm_object_type_and_id",
                "identity_capacity_workload_or_source_status_inference": False,
            },
            "counts": integrity,
            "outputs": outputs,
            "rights": {
                "license": OSM_LICENSE,
                "attribution": OSM_ATTRIBUTION,
                "copyright_url": OSM_COPYRIGHT_URL,
                "database_rights_apply_to_derived_output": True,
            },
        }
        _write_bytes_atomic(stage / MANIFEST_FILENAME, pretty_json_bytes(manifest))
        xml_path.unlink()
        if destination.exists():
            raise PlanetMaterializationError(
                "candidate output appeared while atomic bundle was being built"
            )
        stage.replace(destination)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _command_output(
    runner: Callable[..., Any], command: Sequence[str], output_path: Path
) -> list[str]:
    if output_path.exists() or output_path.is_symlink():
        raise PlanetMaterializationError(f"refusing existing command output: {output_path}")
    _run(runner, list(command))
    facts = inspect_file(output_path)
    if facts["bytes"] <= 0:
        raise PlanetMaterializationError(f"command created an empty output: {output_path}")
    return list(command)


def _pbf_counts(
    pbf_path: Path,
    *,
    osmium_binary: str,
    runner: Callable[..., Any],
) -> tuple[dict[str, int], list[str]]:
    command = [
        osmium_binary,
        "fileinfo",
        "--extended",
        "--json",
        "--no-progress",
        str(pbf_path),
    ]
    result = _run(runner, command)
    stdout = getattr(result, "stdout", "")
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="strict")
    try:
        document = json.loads(str(stdout))
        raw_counts = document["data"]["count"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise PlanetMaterializationError("osmium fileinfo returned malformed counts") from error
    counts: dict[str, int] = {}
    for singular, plural in (("node", "nodes"), ("way", "ways"), ("relation", "relations")):
        value = raw_counts.get(plural)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PlanetMaterializationError(f"osmium fileinfo {plural} count is invalid")
        counts[singular] = value
    return counts, command


def _run_check_refs(
    pbf_path: Path,
    *,
    osmium_binary: str,
    runner: Callable[..., Any],
) -> list[str]:
    command = [
        osmium_binary,
        "check-refs",
        "--no-progress",
        "-r",
        str(pbf_path),
    ]
    _run(runner, command)
    return command


def _subextract_command(
    source: Path,
    output: Path,
    expressions: Sequence[str],
    *,
    osmium_binary: str,
    retain_references: bool,
    generator: str,
) -> list[str]:
    reference_option = "--remove-tags" if retain_references else "--omit-referenced"
    return [
        osmium_binary,
        "tags-filter",
        "--no-progress",
        "--fsync",
        reference_option,
        f"--generator={generator}",
        "--output",
        str(output),
        str(source),
        *expressions,
    ]


def _export_command(
    source: Path,
    output: Path,
    geometry_types: str,
    *,
    osmium_binary: str,
) -> list[str]:
    return [
        osmium_binary,
        "export",
        "--no-progress",
        "--fsync",
        "--add-unique-id=type_id",
        "--geometry-types",
        geometry_types,
        "--output-format",
        "geojsonseq",
        "--output",
        str(output),
        str(source),
    ]


def _iter_match_records(xml_path: Path) -> Iterable[dict[str, Any]]:
    last_key: tuple[int, int] | None = None
    try:
        iterator = ElementTree.iterparse(xml_path, events=("end",))
        for _, element in iterator:
            object_type = _local_name(element.tag)
            if object_type not in TYPE_ORDER:
                continue
            element_id = _parse_osm_id(element.attrib.get("id"), f"{object_type} id")
            order_key = (TYPE_ORDER[object_type], element_id)
            if last_key is not None and order_key <= last_key:
                raise PlanetMaterializationError(
                    "primary match XML is not strictly ordered by typed OSM identity"
                )
            last_key = order_key
            output = _base_element(
                object_type,
                element_id,
                _element_attributes(element.attrib),
                _parse_tags(element),
            )
            output["source_url"] = _element_url(object_type, element_id)
            if object_type == "node":
                latitude = _parse_coordinate(element.attrib.get("lat"), "latitude")
                longitude = _parse_coordinate(element.attrib.get("lon"), "longitude")
                if latitude is not None and longitude is not None:
                    output.update({"lat": latitude, "lon": longitude})
            elif object_type == "way":
                output["nodes"] = [
                    _parse_osm_id(child.attrib.get("ref"), "way node reference")
                    for child in element
                    if _local_name(child.tag) == "nd"
                ]
            else:
                members: list[dict[str, Any]] = []
                for child in element:
                    if _local_name(child.tag) != "member":
                        continue
                    member_type = child.attrib.get("type")
                    if member_type not in TYPE_ORDER:
                        raise PlanetMaterializationError(
                            f"relation/{element_id} has unsupported member type {member_type!r}"
                        )
                    members.append(
                        {
                            "type": member_type,
                            "ref": _parse_osm_id(
                                child.attrib.get("ref"), "relation member reference"
                            ),
                            "role": child.attrib.get("role", ""),
                        }
                    )
                output["members"] = members
            yield output
            element.clear()
    except ElementTree.ParseError as error:
        raise PlanetMaterializationError(f"primary match XML is malformed: {error}") from error


def _iter_geojson_sequence(path: Path) -> Iterable[dict[str, Any]]:
    if path.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink GeoJSON sequence: {path}")
    with path.open("rb") as source:
        for line_number, raw in enumerate(source, 1):
            payload = raw.lstrip(b"\x1e").strip()
            if not payload:
                continue
            try:
                feature = json.loads(payload)
            except json.JSONDecodeError as error:
                raise PlanetMaterializationError(
                    f"malformed GeoJSON sequence line {line_number}"
                ) from error
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise PlanetMaterializationError(
                    f"GeoJSON sequence line {line_number} is not a Feature"
                )
            yield feature


def _export_identity(feature_id: Any) -> tuple[str, int, tuple[int, int]]:
    if not isinstance(feature_id, str) or len(feature_id) < 2:
        raise PlanetMaterializationError("Osmium export feature ID is malformed")
    try:
        numeric = int(feature_id[1:])
    except ValueError as error:
        raise PlanetMaterializationError("Osmium export feature ID is malformed") from error
    if numeric <= 0:
        raise PlanetMaterializationError("Osmium export feature ID is non-positive")
    if feature_id[0] == "n":
        return "node", numeric, (0, numeric)
    if feature_id[0] == "a":
        if numeric % 2 == 0:
            return "way", numeric // 2, (1, numeric)
        return "relation", (numeric - 1) // 2, (1, numeric)
    raise PlanetMaterializationError(
        f"unexpected Osmium export feature ID prefix: {feature_id[0]!r}"
    )


def _feature_tags(feature: Mapping[str, Any]) -> dict[str, str]:
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        raise PlanetMaterializationError("Osmium export feature properties are missing")
    tags: dict[str, str] = {}
    for key, value in properties.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PlanetMaterializationError("Osmium export source tags must be strings")
        tags[key] = value
    return dict(sorted(tags.items()))


def _feature_center(feature: Mapping[str, Any]) -> tuple[float, float] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, Mapping):
        return None
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            return float(coordinates[1]), float(coordinates[0])
        return None
    points = list(_iter_geojson_points(geometry))
    bounds = _bounds({"lat": lat, "lon": lon} for lon, lat in points)
    if bounds is None:
        return None
    center = _center(bounds)
    return center["lat"], center["lon"]


@dataclass(frozen=True, slots=True)
class _IndexedPowerContext:
    latitude: float
    longitude: float
    object_type: str
    element_id: int
    power_tag: str


class _CompactPowerIndex:
    CELL_DEGREES = 0.05
    LONGITUDE_CELL_COUNT = int(360 / CELL_DEGREES)

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list[_IndexedPowerContext]] = defaultdict(list)

    @classmethod
    def _cell(cls, center: tuple[float, float]) -> tuple[int, int]:
        latitude, longitude = center
        return (
            math.floor((latitude + 90) / cls.CELL_DEGREES),
            math.floor((longitude + 180) / cls.CELL_DEGREES)
            % cls.LONGITUDE_CELL_COUNT,
        )

    def add(
        self,
        center: tuple[float, float],
        object_type: str,
        element_id: int,
        power_tag: str,
    ) -> None:
        record = _IndexedPowerContext(
            center[0], center[1], object_type, element_id, power_tag
        )
        self.cells[self._cell(center)].append(record)

    def nearest(
        self, center: tuple[float, float], maximum_metres: float = 5_000
    ) -> tuple[float, Mapping[str, Any]] | None:
        latitude, longitude = center
        latitude_cell, longitude_cell = self._cell(center)
        latitude_span = math.ceil(
            maximum_metres / (111_320 * self.CELL_DEGREES)
        ) + 1
        cosine = max(0.001, abs(math.cos(math.radians(latitude))))
        longitude_degrees = maximum_metres / (111_320 * cosine)
        longitude_span = min(
            self.LONGITUDE_CELL_COUNT // 2,
            math.ceil(longitude_degrees / self.CELL_DEGREES) + 1,
        )
        best: tuple[float, _IndexedPowerContext] | None = None
        for candidate_latitude in range(
            latitude_cell - latitude_span, latitude_cell + latitude_span + 1
        ):
            for offset in range(-longitude_span, longitude_span + 1):
                candidate_longitude = (
                    longitude_cell + offset
                ) % self.LONGITUDE_CELL_COUNT
                for context in self.cells.get(
                    (candidate_latitude, candidate_longitude), ()
                ):
                    distance = _haversine_metres(
                        center, (context.latitude, context.longitude)
                    )
                    if distance > maximum_metres:
                        continue
                    candidate_key = (
                        distance,
                        TYPE_ORDER[context.object_type],
                        context.element_id,
                    )
                    best_key = (
                        best[0],
                        TYPE_ORDER[best[1].object_type],
                        best[1].element_id,
                    ) if best is not None else None
                    if best_key is None or candidate_key < best_key:
                        best = (distance, context)
        if best is None:
            return None
        distance, context = best
        return distance, {
            "type": context.object_type,
            "id": context.element_id,
            "source_url": _element_url(context.object_type, context.element_id),
            "tags": {"power": context.power_tag},
        }


def _gzip_json_lines(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with path.open("xb") as raw_output:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_output,
            compresslevel=6,
            mtime=0,
        ) as compressed:
            for record in records:
                compressed.write(canonical_json_bytes(record))
                count += 1
        raw_output.flush()
        os.fsync(raw_output.fileno())
    return count


def _count_total(counts: Mapping[str, int]) -> int:
    return sum(counts.get(key, 0) for key in TYPE_ORDER)


def _rss_bytes(who: int) -> int:
    value = int(resource.getrusage(who).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _validate_existing_streaming_bundle(
    destination: Path,
    extraction: ConstructionExtractionInput,
    known_exact: KnownExactLayer,
) -> dict[str, Any]:
    manifest, _ = _read_json(destination / MANIFEST_FILENAME, "candidate bundle manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != BUNDLE_PIPELINE
        or manifest.get("state") != "completed"
        or manifest.get("review_only") is not True
        or manifest.get("filter") != filter_manifest_document()
        or manifest.get("review_prior")
        != {**PRIOR_CONTRACT, "contract_sha256": PRIOR_SHA256}
    ):
        raise PlanetMaterializationError("existing candidate bundle contract does not match")
    expected_inputs = {
        "construction_extraction_manifest_sha256": sha256_bytes(extraction.manifest_raw),
        "construction_filtered_pbf_sha256": extraction.pbf_facts["sha256"],
        "known_exact_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
        "known_exact_json_sha256": sha256_bytes(known_exact.json_raw),
        "planet_sha256": extraction.document["source"]["sha256"],
    }
    if manifest.get("input_hashes") != expected_inputs:
        raise PlanetMaterializationError("existing candidate bundle input hashes do not match")
    expected_names = {
        MATCHES_FILENAME,
        POWER_CONTEXT_FILENAME,
        PRIMARY_PBF_FILENAME,
        SHORTLIST_GEOJSON_FILENAME,
        SHORTLIST_CSV_FILENAME,
        KNOWN_LINKS_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != expected_names:
        raise PlanetMaterializationError("existing candidate bundle output inventory is invalid")
    for name in sorted(expected_names):
        record = outputs[name]
        facts = inspect_file(destination / name, ("md5", "sha256"))
        if (
            not isinstance(record, Mapping)
            or record.get("path") != name
            or any(record.get(key) != facts[key] for key in ("bytes", "md5", "sha256"))
        ):
            raise PlanetMaterializationError(
                f"existing candidate output {name} hash does not match"
            )
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise PlanetMaterializationError("existing candidate counts are missing")
    raw = counts.get("raw_primary_match_counts", {}).get("total")
    polygon = counts.get("polygon_geometry_count")
    no_polygon = counts.get("raw_matches_without_polygon_footprint_count")
    if not all(isinstance(value, int) and value >= 0 for value in (raw, polygon, no_polygon)):
        raise PlanetMaterializationError("existing candidate reconciliation counts are invalid")
    if raw != polygon + no_polygon:
        raise PlanetMaterializationError("existing candidate raw reconciliation does not balance")
    excluded = counts.get("polygon_exclusion_stages")
    if not isinstance(excluded, Mapping) or polygon != sum(excluded.values()):
        raise PlanetMaterializationError("existing candidate exclusion stages do not balance")
    return manifest


def materialize_construction_candidates(
    extraction_manifest: str | Path,
    exact_materialization_manifest: str | Path,
    output_directory: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """Stream the Planet-scale lane without loading retained references into RAM."""
    extraction = validate_extraction_input(extraction_manifest, filtered_pbf=filtered_pbf)
    known_exact = load_known_exact_layer(
        exact_materialization_manifest,
        expected_planet_sha256=extraction.document["source"]["sha256"],
    )
    destination = _absolute(output_directory)
    if destination.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink output directory: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise PlanetMaterializationError("candidate output exists and is not a directory")
        return _validate_existing_streaming_bundle(destination, extraction, known_exact)
    primary_expressions = osmium_filter_expressions()[:-len(POWER_CONTEXT_VALUES)]
    context_expressions = osmium_filter_expressions()[-len(POWER_CONTEXT_VALUES):]
    if dry_run:
        return {
            "schema_version": SCHEMA_VERSION,
            "pipeline": BUNDLE_PIPELINE,
            "state": "dry_run",
            "review_only": True,
            "filter": filter_manifest_document(),
            "review_prior": {**PRIOR_CONTRACT, "contract_sha256": PRIOR_SHA256},
            "streaming_plan": {
                "primary_expression_count": len(primary_expressions),
                "context_expression_count": len(context_expressions),
                "raw_materialization": "ordered_jsonl_gzip_plus_reference_complete_pbf",
                "geometry_scope": "primary_polygons_only",
                "context_scope": "power_points_and_polygons_reduced_to_centres",
            },
            "output_directory": str(destination),
            "writes_performed": False,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    started_monotonic = time.perf_counter()
    started_at = clock()
    commands: dict[str, list[str]] = {}
    try:
        tool_version = osmium_version(osmium_binary=osmium_binary, runner=runner)
        primary_refs = stage / PRIMARY_PBF_FILENAME
        primary_matches = stage / "primary-matches-only.osm.pbf"
        context_refs = stage / "power-context-with-references.osm.pbf"
        context_matches = stage / "power-context-matches-only.osm.pbf"
        for name, output, expressions, retain_refs, generator in (
            (
                "primary_reference_extract",
                primary_refs,
                primary_expressions,
                True,
                "DataCenterAtlas/0.1 structural-primary-with-references",
            ),
            (
                "primary_match_extract",
                primary_matches,
                primary_expressions,
                False,
                "DataCenterAtlas/0.1 structural-primary-matches-only",
            ),
            (
                "context_reference_extract",
                context_refs,
                context_expressions,
                True,
                "DataCenterAtlas/0.1 power-context-with-references",
            ),
            (
                "context_match_extract",
                context_matches,
                context_expressions,
                False,
                "DataCenterAtlas/0.1 power-context-matches-only",
            ),
        ):
            command = _subextract_command(
                extraction.pbf_path,
                output,
                expressions,
                osmium_binary=osmium_binary,
                retain_references=retain_refs,
                generator=generator,
            )
            commands[name] = _command_output(runner, command, output)

        commands["primary_check_refs"] = _run_check_refs(
            primary_refs, osmium_binary=osmium_binary, runner=runner
        )
        commands["context_check_refs"] = _run_check_refs(
            context_refs, osmium_binary=osmium_binary, runner=runner
        )
        primary_raw_counts, commands["primary_match_fileinfo"] = _pbf_counts(
            primary_matches, osmium_binary=osmium_binary, runner=runner
        )
        primary_reference_counts, commands["primary_reference_fileinfo"] = _pbf_counts(
            primary_refs, osmium_binary=osmium_binary, runner=runner
        )
        context_raw_counts, commands["context_match_fileinfo"] = _pbf_counts(
            context_matches, osmium_binary=osmium_binary, runner=runner
        )
        context_reference_counts, commands["context_reference_fileinfo"] = _pbf_counts(
            context_refs, osmium_binary=osmium_binary, runner=runner
        )

        primary_xml = stage / "primary-matches-only.osm"
        commands["primary_match_xml"] = convert_pbf_to_xml(
            primary_matches,
            primary_xml,
            osmium_binary=osmium_binary,
            runner=runner,
        )
        known_links: list[dict[str, Any]] = []
        raw_counts: Counter[str] = Counter()

        def raw_records() -> Iterable[dict[str, Any]]:
            for element in _iter_match_records(primary_xml):
                triggers = primary_trigger_tags(element["tags"])
                if not triggers:
                    raise PlanetMaterializationError(
                        f"{element['type']}/{element['id']} passed the primary PBF "
                        "but not the hash-bound classifier"
                    )
                identity = (element["type"], element["id"])
                element["discovery"] = {
                    "filter_version": FILTER_VERSION,
                    "trigger_tags": triggers,
                    "source_tag_families": _source_tag_families(triggers),
                    "review_only": True,
                    "data_centre_identity_inferred": False,
                }
                if is_exact_match(element["tags"]) and identity not in known_exact.identities:
                    raise PlanetMaterializationError(
                        f"{identity[0]}/{identity[1]} has a canonical exact data-centre tag "
                        "but is absent from the hash-bound exact layer"
                    )
                if identity in known_exact.identities:
                    exact_element = known_exact.elements[identity]
                    link = {
                        "type": identity[0],
                        "id": identity[1],
                        "source_url": element["source_url"],
                        "link_method": "identical_osm_object_type_and_id",
                        "exact_layer_source_tags": exact_element.get("tags", {}),
                        "excluded_from_shortlist": True,
                    }
                    element["known_exact_data_centre_layer_link"] = link
                    known_links.append(link)
                raw_counts[element["type"]] += 1
                yield element

        written_raw = _gzip_json_lines(stage / MATCHES_FILENAME, raw_records())
        normalized_raw_counts = {
            "node": raw_counts["node"],
            "way": raw_counts["way"],
            "relation": raw_counts["relation"],
            "total": sum(raw_counts.values()),
        }
        if written_raw != _count_total(primary_raw_counts) or normalized_raw_counts != {
            **primary_raw_counts,
            "total": _count_total(primary_raw_counts),
        }:
            raise PlanetMaterializationError(
                "lossless primary JSONL counts do not match the match-only PBF"
            )

        context_sequence = stage / "power-context.geojsonseq"
        commands["context_geometry_export"] = _command_output(
            runner,
            _export_command(
                context_refs,
                context_sequence,
                "point,polygon",
                osmium_binary=osmium_binary,
            ),
            context_sequence,
        )
        power_index = _CompactPowerIndex()
        context_counts: Counter[str] = Counter()
        seen_context_features: set[int] = set()

        def context_records() -> Iterable[dict[str, Any]]:
            for feature in _iter_geojson_sequence(context_sequence):
                object_type, element_id, order_key = _export_identity(feature.get("id"))
                feature_key = (order_key[1] << 1) | order_key[0]
                if feature_key in seen_context_features:
                    raise PlanetMaterializationError(
                        "power context geometry sequence contains a duplicate feature"
                    )
                seen_context_features.add(feature_key)
                tags = _feature_tags(feature)
                if not is_power_context(tags):
                    raise PlanetMaterializationError(
                        "power context export emitted a non-context object"
                    )
                center = _feature_center(feature)
                if center is None:
                    continue
                power_index.add(center, object_type, element_id, tags["power"])
                context_counts[object_type] += 1
                yield {
                    "type": object_type,
                    "id": element_id,
                    "source_url": _element_url(object_type, element_id),
                    "tags": tags,
                    "center": {"lat": center[0], "lon": center[1]},
                    "review_only": True,
                    "context_only_not_data_centre_candidate": True,
                }

        written_context = _gzip_json_lines(
            stage / POWER_CONTEXT_FILENAME, context_records()
        )
        if written_context != sum(context_counts.values()):
            raise PlanetMaterializationError("power context JSONL count is inconsistent")

        primary_sequence = stage / "primary-polygons.geojsonseq"
        commands["primary_polygon_export"] = _command_output(
            runner,
            _export_command(
                primary_refs,
                primary_sequence,
                "polygon",
                osmium_binary=osmium_binary,
            ),
            primary_sequence,
        )
        polygon_counts: Counter[str] = Counter()
        exclusion_counts: Counter[str] = Counter()
        shortlist: list[dict[str, Any]] = []
        seen_polygon_features: set[int] = set()
        for feature in _iter_geojson_sequence(primary_sequence):
            object_type, element_id, order_key = _export_identity(feature.get("id"))
            if object_type == "node":
                raise PlanetMaterializationError("primary polygon export emitted a node")
            feature_key = (order_key[1] << 1) | order_key[0]
            if feature_key in seen_polygon_features:
                raise PlanetMaterializationError(
                    "primary polygon geometry sequence contains a duplicate feature"
                )
            seen_polygon_features.add(feature_key)
            tags = _feature_tags(feature)
            triggers = primary_trigger_tags(tags)
            if not triggers:
                raise PlanetMaterializationError(
                    "primary polygon export emitted a non-primary object"
                )
            geometry = feature.get("geometry")
            if not isinstance(geometry, Mapping) or geometry.get("type") not in {
                "Polygon",
                "MultiPolygon",
            }:
                raise PlanetMaterializationError("primary polygon geometry is malformed")
            center = _feature_center(feature)
            if center is None:
                raise PlanetMaterializationError("primary polygon has no centre")
            element = {
                "type": object_type,
                "id": element_id,
                "source_url": _element_url(object_type, element_id),
                "tags": tags,
                "geometry": dict(geometry),
                "center": {"lat": center[0], "lon": center[1]},
                "discovery": {
                    "filter_version": FILTER_VERSION,
                    "trigger_tags": triggers,
                    "source_tag_families": _source_tag_families(triggers),
                    "review_only": True,
                    "data_centre_identity_inferred": False,
                },
            }
            identity = (object_type, element_id)
            if is_exact_match(tags) and identity not in known_exact.identities:
                raise PlanetMaterializationError(
                    f"{object_type}/{element_id} has an exact tag but no exact-layer identity"
                )
            prior = _score_candidate(element, triggers, power_index)
            element["review_prior"] = prior
            polygon_counts[object_type] += 1
            if identity in known_exact.identities:
                exclusion_counts["known_exact_identity"] += 1
            elif prior["explicit_power_asset_source_tag"]:
                exclusion_counts["explicit_power_asset"] += 1
            elif prior["footprint_square_metres"] is None or prior[
                "footprint_square_metres"
            ] < PRIOR_CONTRACT["shortlist_minimum_footprint_square_metres"]:
                exclusion_counts["below_minimum_footprint"] += 1
            elif prior["review_score"] < PRIOR_CONTRACT["shortlist_minimum_points"]:
                exclusion_counts["below_minimum_review_score"] += 1
            else:
                exclusion_counts["shortlisted"] += 1
                shortlist.append(element)

        shortlist.sort(
            key=lambda item: (
                -item["review_prior"]["review_score"],
                -item["review_prior"]["footprint_square_metres"],
                TYPE_ORDER[item["type"]],
                item["id"],
            )
        )
        shortlist_counts = _counts_by_type(shortlist)
        polygon_total = sum(polygon_counts.values())
        if polygon_total != sum(exclusion_counts.values()):
            raise PlanetMaterializationError("polygon exclusion stages do not reconcile")
        raw_total = normalized_raw_counts["total"]
        if polygon_total > raw_total:
            raise PlanetMaterializationError("polygon count exceeds raw primary count")

        _write_bytes_atomic(
            stage / SHORTLIST_GEOJSON_FILENAME,
            canonical_json_bytes(_shortlist_geojson(shortlist)),
        )
        _write_bytes_atomic(stage / SHORTLIST_CSV_FILENAME, _shortlist_csv(shortlist))
        known_links.sort(key=lambda item: (TYPE_ORDER[item["type"]], item["id"]))
        links_document = {
            "schema_version": SCHEMA_VERSION,
            "review_only": True,
            "link_method": "identical_osm_object_type_and_id",
            "exact_layer_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
            "exact_layer_json_sha256": sha256_bytes(known_exact.json_raw),
            "links": known_links,
        }
        _write_bytes_atomic(
            stage / KNOWN_LINKS_FILENAME, canonical_json_bytes(links_document)
        )

        context_usable_counts = {
            "node": context_counts["node"],
            "way": context_counts["way"],
            "relation": context_counts["relation"],
            "total": sum(context_counts.values()),
        }
        counts = {
            "combined_extraction_object_counts_including_references": {
                **extraction.source_counts,
                "total": _count_total(extraction.source_counts),
            },
            "primary_reference_object_counts": {
                **primary_reference_counts,
                "total": _count_total(primary_reference_counts),
            },
            "raw_primary_match_counts": normalized_raw_counts,
            "power_context_raw_match_counts": {
                **context_raw_counts,
                "total": _count_total(context_raw_counts),
            },
            "power_context_reference_object_counts": {
                **context_reference_counts,
                "total": _count_total(context_reference_counts),
            },
            "power_context_with_usable_centre_counts": context_usable_counts,
            "power_context_without_usable_centre_count": _count_total(context_raw_counts)
            - context_usable_counts["total"],
            "polygon_geometry_counts": {
                "way": polygon_counts["way"],
                "relation": polygon_counts["relation"],
                "total": polygon_total,
            },
            "polygon_geometry_count": polygon_total,
            "raw_matches_without_polygon_footprint_count": raw_total - polygon_total,
            "polygon_exclusion_stages": {
                "known_exact_identity": exclusion_counts["known_exact_identity"],
                "explicit_power_asset": exclusion_counts["explicit_power_asset"],
                "below_minimum_footprint": exclusion_counts["below_minimum_footprint"],
                "below_minimum_review_score": exclusion_counts[
                    "below_minimum_review_score"
                ],
                "shortlisted": exclusion_counts["shortlisted"],
            },
            "shortlisted_counts": shortlist_counts,
            "known_exact_identity_exclusion_count": len(known_links),
            "known_exact_polygon_exclusion_count": exclusion_counts[
                "known_exact_identity"
            ],
            "primary_referential_integrity_check_passed": True,
            "context_referential_integrity_check_passed": True,
            "lossless_jsonl_matches_match_only_pbf_counts": True,
            "raw_identity_order": "node_then_way_then_relation_each_by_ascending_osm_id",
            "shortlist_order": "review_score_desc_area_desc_type_order_osm_id",
            "identity_capacity_workload_or_source_status_inference": False,
        }
        _write_bytes_atomic(
            stage / README_FILENAME,
            _readme(counts, extraction.document.get("snapshot_date")),
        )
        _write_bytes_atomic(stage / ATTRIBUTION_FILENAME, _attribution())

        for temporary in (
            primary_matches,
            context_refs,
            context_matches,
            primary_xml,
            context_sequence,
            primary_sequence,
        ):
            temporary.unlink()

        payload_names = {
            MATCHES_FILENAME,
            POWER_CONTEXT_FILENAME,
            PRIMARY_PBF_FILENAME,
            SHORTLIST_GEOJSON_FILENAME,
            SHORTLIST_CSV_FILENAME,
            KNOWN_LINKS_FILENAME,
            README_FILENAME,
            ATTRIBUTION_FILENAME,
        }
        outputs = {name: _output_record(stage / name) for name in sorted(payload_names)}
        input_hashes = {
            "construction_extraction_manifest_sha256": sha256_bytes(extraction.manifest_raw),
            "construction_filtered_pbf_sha256": extraction.pbf_facts["sha256"],
            "known_exact_manifest_sha256": sha256_bytes(known_exact.manifest_raw),
            "known_exact_json_sha256": sha256_bytes(known_exact.json_raw),
            "planet_sha256": extraction.document["source"]["sha256"],
        }
        elapsed = round(time.perf_counter() - started_monotonic, 3)
        relative_commands = {
            name: [str(item).replace(str(stage) + os.sep, "") for item in command]
            for name, command in commands.items()
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": BUNDLE_PIPELINE,
            "state": "completed",
            "review_only": True,
            "candidate_layer_not_data_centre_census": True,
            "started_at": started_at,
            "materialized_at": clock(),
            "snapshot_date": extraction.document.get("snapshot_date"),
            "input_hashes": input_hashes,
            "inputs": {
                "construction_extraction_manifest": {
                    "path": os.path.relpath(extraction.manifest_path, destination),
                    "bytes": len(extraction.manifest_raw),
                    "sha256": input_hashes["construction_extraction_manifest_sha256"],
                    "pipeline": extraction.document.get("pipeline"),
                },
                "construction_filtered_pbf": {
                    "path": os.path.relpath(extraction.pbf_path, destination),
                    **extraction.pbf_facts,
                },
                "known_exact_materialization_manifest": {
                    "path": os.path.relpath(known_exact.manifest_path, destination),
                    "bytes": len(known_exact.manifest_raw),
                    "sha256": input_hashes["known_exact_manifest_sha256"],
                    "pipeline": known_exact.document.get("pipeline"),
                },
                "known_exact_json": {
                    "path": os.path.relpath(known_exact.json_path, destination),
                    "bytes": len(known_exact.json_raw),
                    "sha256": input_hashes["known_exact_json_sha256"],
                },
                "planet_source": extraction.document.get("source"),
            },
            "filter": filter_manifest_document(),
            "review_prior": {**PRIOR_CONTRACT, "contract_sha256": PRIOR_SHA256},
            "transform": {
                "mode": "streaming_planet_scale_materialization",
                "commands": relative_commands,
                "tool_version": tool_version,
                "raw_materialization": "gzip_json_lines_from_match_only_osm_xml",
                "native_reference_layer": PRIMARY_PBF_FILENAME,
                "reference_object_tags_removed_in_native_layer": True,
                "matched_object_tags_attributes_and_references_preserved": True,
                "geometry_scope": "primary_polygon_features_only",
                "context_scope": "power_points_and_polygons_reduced_to_centres",
                "footprint_method": "local_equirectangular_shoelace_outer_minus_inner_rings",
                "power_distance_method": "haversine_between_geometry_bounds_centres",
                "known_identity_link_method": "identical_osm_object_type_and_id",
                "identity_capacity_workload_or_source_status_inference": False,
            },
            "runtime": {
                "elapsed_seconds": elapsed,
                "peak_python_rss_bytes": _rss_bytes(resource.RUSAGE_SELF),
                "peak_child_process_rss_bytes": _rss_bytes(resource.RUSAGE_CHILDREN),
            },
            "counts": counts,
            "outputs": outputs,
            "rights": {
                "license": OSM_LICENSE,
                "attribution": OSM_ATTRIBUTION,
                "copyright_url": OSM_COPYRIGHT_URL,
                "database_rights_apply_to_derived_output": True,
            },
        }
        _write_bytes_atomic(stage / MANIFEST_FILENAME, pretty_json_bytes(manifest))
        if destination.exists():
            raise PlanetMaterializationError(
                "candidate output appeared while atomic bundle was being built"
            )
        stage.replace(destination)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


__all__ = [
    "BUNDLE_PIPELINE",
    "EXTRACTION_PIPELINE",
    "FILTER_SHA256",
    "FILTER_VERSION",
    "PRIOR_CONTRACT",
    "PRIOR_SHA256",
    "build_candidate_documents",
    "filter_manifest_document",
    "footprint_area_square_metres",
    "is_explicit_power_asset",
    "load_known_exact_layer",
    "materialize_construction_candidates",
    "osmium_filter_expressions",
    "primary_trigger_tags",
    "validate_extraction_input",
]
