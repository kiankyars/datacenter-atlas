"""Explainable, read-only cross-source entity-resolution candidate reports."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from math import asin, cos, floor, inf, isfinite, nextafter, pi, radians, sin, sqrt
from typing import Any, Iterable, Mapping, Sequence
from unicodedata import normalize as normalize_unicode
from urllib.parse import urlsplit

from ._iso3166 import ISO_3166_1
from .timestamps import canonical_read_cutoff, require_canonical_persistence_state


EARTH_RADIUS_M = 6_371_008.8
_WORD_RE = re.compile(r"[a-z0-9]+")
_VALUE_SPLIT_RE = re.compile(r"\s*(?:[;,|]|\s+&\s+)\s*")
_OSM_STABLE_IDENTITY_RE = re.compile(
    r"^(?:osm(?:-[a-z0-9_-]+)?|openstreetmap(?:[:_-][a-z0-9_-]+)*)"
    r":(?:[^:]+:)*(node|way|relation)[/:](\d+)(?::|$)",
    flags=re.IGNORECASE,
)
_OSM_URL_IDENTITY_RE = re.compile(
    r"(?:^|/)(node|way|relation)/(\d+)(?:/|$)",
    flags=re.IGNORECASE,
)
_NAME_NOISE = {
    "campus",
    "center",
    "centre",
    "data",
    "datacenter",
    "datacentre",
    "facility",
    "limited",
    "llc",
    "ltd",
}
_COUNTRY_EXTRA_ALIASES = {
    "bolivia plurinational state of": "BO",
    "brunei": "BN",
    "congo brazzaville": "CG",
    "congo kinshasa": "CD",
    "czech republic": "CZ",
    "democratic republic of congo": "CD",
    "east timor": "TL",
    "great britain": "GB",
    "iran islamic republic of": "IR",
    "ivory coast": "CI",
    "lao people s democratic republic": "LA",
    "laos": "LA",
    "micronesia": "FM",
    "moldova republic of": "MD",
    "north korea": "KP",
    "republic of korea": "KR",
    "russia": "RU",
    "south korea": "KR",
    "syrian arab republic": "SY",
    "taiwan province of china": "TW",
    "tanzania united republic of": "TZ",
    "the netherlands": "NL",
    "turkey": "TR",
    "u s": "US",
    "u s a": "US",
    "uk": "GB",
    "vatican city": "VA",
    "venezuela bolivarian republic of": "VE",
    "viet nam": "VN",
    "vietnam": "VN",
}


@dataclass(frozen=True, slots=True)
class ResolutionThresholds:
    """Conservative spatial and score gates for candidate classification."""

    nearby_max_distance_m: float = 5_000.0
    same_site_max_distance_m: float = 1_500.0
    part_of_max_distance_m: float = 3_000.0
    same_site_min_score: float = 0.62
    part_of_min_score: float = 0.55

    def __post_init__(self) -> None:
        distances = (
            self.nearby_max_distance_m,
            self.same_site_max_distance_m,
            self.part_of_max_distance_m,
        )
        if not all(isfinite(value) and value > 0 for value in distances):
            raise ValueError("resolution distance thresholds must be finite and positive")
        if self.same_site_max_distance_m > self.nearby_max_distance_m:
            raise ValueError("same-site distance cannot exceed nearby distance")
        if self.part_of_max_distance_m > self.nearby_max_distance_m:
            raise ValueError("part-of distance cannot exceed nearby distance")
        scores = (self.same_site_min_score, self.part_of_min_score)
        if not all(isfinite(value) and 0 <= value <= 1 for value in scores):
            raise ValueError("resolution score thresholds must be between zero and one")


@dataclass(frozen=True, slots=True)
class CandidateLink:
    """An advisory relationship between two canonical entities, never a merge."""

    relationship_suggestion: str
    score: float
    distance_m: float
    left_entity_id: str
    left_entity_kind: str
    left_name: str | None
    left_source_family: str
    left_evidence_id: str
    right_entity_id: str
    right_entity_kind: str
    right_name: str | None
    right_source_family: str
    right_evidence_id: str
    suggested_parent_entity_id: str | None
    suggested_child_entity_id: str | None
    signals: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["signals"] = dict(sorted(result["signals"].items()))
        return result


@dataclass(frozen=True, slots=True)
class _Record:
    entity_id: str
    kind: str
    name: str | None
    latitude: float
    longitude: float
    geometry: Mapping[str, Any] | None
    tags: Mapping[str, Any]
    evidence_id: str
    source_family: str
    stable_key: str | None = None
    source_url: str | None = None
    source_root: str | None = None

    def __post_init__(self) -> None:
        if self.source_root is None:
            object.__setattr__(self, "source_root", _source_root(self.source_family))


def _words(value: object) -> list[str]:
    decomposed = normalize_unicode("NFKD", str(value or "").casefold())
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return _WORD_RE.findall(ascii_value)


def _normalized_text(value: object) -> str:
    return " ".join(_words(value))


def _build_country_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for alpha_2, alpha_3, names in ISO_3166_1:
        for value in (alpha_2, alpha_3, *names):
            normalized = _normalized_text(value)
            previous = aliases.setdefault(normalized, alpha_2)
            if previous != alpha_2:
                raise RuntimeError(f"ambiguous ISO 3166-1 country alias: {value}")
    for value, alpha_2 in _COUNTRY_EXTRA_ALIASES.items():
        aliases[_normalized_text(value)] = alpha_2
    return aliases


_COUNTRY_ALIASES = _build_country_aliases()


def _normalized_name(value: object) -> str:
    words = [word for word in _words(value) if word not in _NAME_NOISE]
    return " ".join(words)


def _similarity(left: object, right: object, *, names: bool = False) -> float:
    normalize = _normalized_name if names else _normalized_text
    left_value = normalize(left)
    right_value = normalize(right)
    if not left_value or not right_value:
        return 0.0
    if left_value == right_value:
        return 1.0
    left_words = set(left_value.split())
    right_words = set(right_value.split())
    union = left_words | right_words
    jaccard = len(left_words & right_words) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_value, right_value, autojunk=False).ratio()
    return 0.6 * sequence + 0.4 * jaccard


def _country(tags: Mapping[str, Any]) -> str | None:
    value = (
        tags.get("country")
        or tags.get("country_name")
        or tags.get("addr:country")
        or tags.get("iso_country_code")
    )
    normalized = _normalized_text(value)
    if not normalized:
        return None
    return _COUNTRY_ALIASES.get(normalized, normalized)


def _address(tags: Mapping[str, Any]) -> str:
    direct = tags.get("address") or tags.get("addr:full")
    if direct:
        return str(direct)
    components = (
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode"),
    )
    return " ".join(str(value) for value in components if value)


def _organizations(tags: Mapping[str, Any]) -> set[str]:
    values: list[str] = []
    for key in (
        "owner",
        "owners",
        "operator",
        "operators",
        "role:owner",
        "role:operator",
    ):
        raw = tags.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
        elif raw:
            values.extend(_VALUE_SPLIT_RE.split(str(raw)))
    return {_normalized_text(value) for value in values if _normalized_text(value)}


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _osm_identity_tokens(record: _Record) -> set[str]:
    """Return exact typed OSM identities without treating generic URLs as IDs."""

    identities: set[str] = set()
    if isinstance(record.stable_key, str):
        match = _OSM_STABLE_IDENTITY_RE.search(record.stable_key.strip())
        if match:
            identities.add(
                f"openstreetmap:{match.group(1).casefold()}/{match.group(2)}"
            )

    url_values = [record.source_url]
    url_values.extend(
        record.tags.get(key)
        for key in (
            "scrutica:upstream_source_url",
            "openstreetmap:url",
            "osm:url",
            "source:url",
        )
    )
    for value in url_values:
        if not isinstance(value, str):
            continue
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if hostname != "openstreetmap.org" and not hostname.endswith(
            ".openstreetmap.org"
        ):
            continue
        match = _OSM_URL_IDENTITY_RE.search(parsed.path)
        if match:
            identities.add(f"openstreetmap:{match.group(1).casefold()}/{match.group(2)}")
    return identities


def haversine_distance_m(
    left_latitude: float,
    left_longitude: float,
    right_latitude: float,
    right_longitude: float,
) -> float:
    """Return great-circle distance in metres between two WGS84 points."""

    left_lat = radians(left_latitude)
    right_lat = radians(right_latitude)
    delta_lat = radians(right_latitude - left_latitude)
    delta_lon = radians(right_longitude - left_longitude)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(left_lat) * cos(right_lat) * sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(haversine)))


def _unit_sphere_coordinates(record: _Record) -> tuple[float, float, float]:
    latitude = radians(record.latitude)
    longitude = radians(record.longitude)
    latitude_cosine = cos(latitude)
    return (
        latitude_cosine * cos(longitude),
        latitude_cosine * sin(longitude),
        sin(latitude),
    )


def _spatial_candidate_pairs(
    records: Sequence[_Record],
    max_distance_m: float,
) -> Iterable[tuple[_Record, _Record]]:
    """Yield each pair that may be within ``max_distance_m`` exactly once.

    Unit-sphere XYZ cells avoid longitude discontinuities and shrinking
    longitude degrees near the poles. Any two points within the great-circle
    threshold have a 3-D chord no longer than the cell side, so their cells
    differ by at most one on every axis.
    """

    if max_distance_m >= pi * EARTH_RADIUS_M:
        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                yield left, right
        return

    chord_threshold = 2 * sin(max_distance_m / (2 * EARTH_RADIUS_M))
    cell_size = nextafter(chord_threshold, inf)
    buckets: dict[tuple[int, int, int], list[int]] = {}
    cells: list[tuple[int, int, int]] = []
    for index, record in enumerate(records):
        cell = tuple(
            floor(coordinate / cell_size)
            for coordinate in _unit_sphere_coordinates(record)
        )
        cells.append(cell)
        buckets.setdefault(cell, []).append(index)

    for left_index, left in enumerate(records):
        cell_x, cell_y, cell_z = cells[left_index]
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                for delta_z in (-1, 0, 1):
                    neighbor = (
                        cell_x + delta_x,
                        cell_y + delta_y,
                        cell_z + delta_z,
                    )
                    for right_index in buckets.get(neighbor, ()):
                        if right_index > left_index:
                            yield left, records[right_index]


def _spatial_candidate_pairs_between(
    left_records: Sequence[_Record],
    right_records: Sequence[_Record],
    max_distance_m: float,
) -> Iterable[tuple[_Record, _Record]]:
    """Yield cross-collection pairs that may be within the distance threshold.

    This is the two-release analogue of :func:`_spatial_candidate_pairs`.  It
    indexes only the right collection, so it never emits within-release pairs
    and preserves left/right release orientation in every result.
    """

    if max_distance_m >= pi * EARTH_RADIUS_M:
        for left in left_records:
            for right in right_records:
                yield left, right
        return

    chord_threshold = 2 * sin(max_distance_m / (2 * EARTH_RADIUS_M))
    cell_size = nextafter(chord_threshold, inf)
    buckets: dict[tuple[int, int, int], list[_Record]] = {}
    for right in right_records:
        cell = tuple(
            floor(coordinate / cell_size)
            for coordinate in _unit_sphere_coordinates(right)
        )
        buckets.setdefault(cell, []).append(right)

    for left in left_records:
        cell_x, cell_y, cell_z = (
            floor(coordinate / cell_size)
            for coordinate in _unit_sphere_coordinates(left)
        )
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                for delta_z in (-1, 0, 1):
                    yield from (
                        (left, right)
                        for right in buckets.get(
                            (
                                cell_x + delta_x,
                                cell_y + delta_y,
                                cell_z + delta_z,
                            ),
                            (),
                        )
                    )


def _coordinate_pairs(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:2])
    ):
        longitude = float(value[0])
        latitude = float(value[1])
        if isfinite(longitude) and isfinite(latitude):
            yield longitude, latitude
        return
    if isinstance(value, list):
        for item in value:
            yield from _coordinate_pairs(item)


def _bounds(geometry: Mapping[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not geometry:
        return None
    points = list(_coordinate_pairs(geometry.get("coordinates")))
    if not points:
        return None
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _bounds_contains(
    bounds: tuple[float, float, float, float] | None,
    longitude: float,
    latitude: float,
) -> bool:
    if bounds is None:
        return False
    west, south, east, north = bounds
    return west <= longitude <= east and south <= latitude <= north


def _bounds_overlap(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> bool:
    if left is None or right is None:
        return False
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )


def _point_in_ring(
    longitude: float,
    latitude: float,
    ring: Any,
) -> bool:
    if not isinstance(ring, list):
        return False
    points = list(_coordinate_pairs(ring))
    if len(points) < 3:
        return False
    inside = False
    previous_longitude, previous_latitude = points[-1]
    for current_longitude, current_latitude in points:
        if (
            (current_latitude > latitude) != (previous_latitude > latitude)
            and longitude
            < (previous_longitude - current_longitude)
            * (latitude - current_latitude)
            / (previous_latitude - current_latitude)
            + current_longitude
        ):
            inside = not inside
        previous_longitude, previous_latitude = current_longitude, current_latitude
    return inside


def _point_in_polygon(longitude: float, latitude: float, coordinates: Any) -> bool:
    if not isinstance(coordinates, list) or not coordinates:
        return False
    if not _point_in_ring(longitude, latitude, coordinates[0]):
        return False
    return not any(
        _point_in_ring(longitude, latitude, hole) for hole in coordinates[1:]
    )


def _geometry_contains(
    geometry: Mapping[str, Any] | None,
    longitude: float,
    latitude: float,
) -> bool:
    if not geometry:
        return False
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return _point_in_polygon(longitude, latitude, coordinates)
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return any(
            _point_in_polygon(longitude, latitude, polygon) for polygon in coordinates
        )
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        return isinstance(geometries, list) and any(
            isinstance(item, dict) and _geometry_contains(item, longitude, latitude)
            for item in geometries
        )
    return False


def _source_family(row: sqlite3.Row) -> str:
    explicit = _normalized_text(row["source_family"])
    if explicit:
        return explicit.replace(" ", "_")
    publisher = _normalized_text(row["publisher"])
    if publisher:
        return f"publisher:{publisher.replace(' ', '_')}"
    hostname = urlsplit(str(row["source_url"] or "")).hostname
    if hostname:
        return f"host:{hostname.casefold()}"
    return f"evidence:{row['evidence_id']}"


def _source_root(source_family: str, metadata: Mapping[str, Any] | None = None) -> str:
    """Return the upstream provenance root used for independence checks.

    Namespaced PNNL IM3 records and other explicitly OSM-derived families share
    the OpenStreetMap root. ``_source_family`` normalizes punctuation in an
    explicit family, so accept both the source identifier's colon form and its
    normalized underscore form.
    """

    upstream = metadata.get("upstream_source_family") if metadata else None
    if isinstance(upstream, str) and upstream.strip():
        normalized_upstream = _normalized_text(upstream).replace(" ", "_")
        if normalized_upstream:
            return _source_root(normalized_upstream)

    normalized = source_family.casefold()
    if normalized == "openstreetmap" or normalized.startswith(
        ("openstreetmap:", "openstreetmap_")
    ):
        return "openstreetmap"
    return normalized


def _current_records(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
) -> list[_Record]:
    recorded_at = canonical_read_cutoff(recorded_at)
    require_canonical_persistence_state(connection)
    rows = connection.execute(
        """
        WITH eligible AS (
            SELECT snapshots.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY snapshots.entity_id
                       ORDER BY snapshots.as_of_date DESC,
                                snapshots.recorded_at DESC,
                                snapshots.id DESC
                   ) AS temporal_rank
            FROM entity_snapshots AS snapshots
            WHERE snapshots.as_of_date <= ?
              AND (snapshots.valid_to_date IS NULL OR ? < snapshots.valid_to_date)
              AND snapshots.recorded_at <= ?
              AND (snapshots.superseded_at IS NULL OR ? < snapshots.superseded_at)
        )
        SELECT eligible.*, entities.kind, entities.stable_key, evidence.source_family,
               evidence.publisher, evidence.source_url, evidence.metadata_json
        FROM eligible
        JOIN entities ON entities.id = eligible.entity_id
        JOIN evidence ON evidence.id = eligible.evidence_id
        WHERE eligible.temporal_rank = 1
          AND entities.kind IN ('campus', 'facility')
        ORDER BY entities.id
        """,
        (as_of, as_of, recorded_at, recorded_at),
    ).fetchall()

    records: list[_Record] = []
    for row in rows:
        if row["latitude"] is None or row["longitude"] is None:
            continue
        try:
            tags = json.loads(row["tags_json"] or "{}")
            geometry = json.loads(row["geometry_json"]) if row["geometry_json"] else None
            evidence_metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            not isinstance(tags, dict)
            or not isinstance(evidence_metadata, dict)
            or (geometry is not None and not isinstance(geometry, dict))
        ):
            continue
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        if (
            not isfinite(latitude)
            or not isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            continue
        source_family = _source_family(row)
        records.append(
            _Record(
                entity_id=str(row["entity_id"]),
                kind=str(row["kind"]),
                name=row["name"],
                latitude=latitude,
                longitude=longitude,
                geometry=geometry,
                tags=tags,
                evidence_id=str(row["evidence_id"]),
                source_family=source_family,
                stable_key=str(row["stable_key"]),
                source_url=(
                    str(row["source_url"]) if row["source_url"] is not None else None
                ),
                source_root=_source_root(source_family, evidence_metadata),
            )
        )
    return records


def _signals(
    left: _Record,
    right: _Record,
    distance_m: float,
    thresholds: ResolutionThresholds,
) -> dict[str, Any]:
    left_source_root = left.source_root
    right_source_root = right.source_root
    left_country = _country(left.tags)
    right_country = _country(right.tags)
    left_bounds = _bounds(left.geometry)
    right_bounds = _bounds(right.geometry)
    left_contains_right = _geometry_contains(
        left.geometry, right.longitude, right.latitude
    )
    right_contains_left = _geometry_contains(
        right.geometry, left.longitude, left.latitude
    )
    left_bounds_contain_right = _bounds_contains(
        left_bounds, right.longitude, right.latitude
    )
    right_bounds_contain_left = _bounds_contains(
        right_bounds, left.longitude, left.latitude
    )
    bounds_overlap = _bounds_overlap(left_bounds, right_bounds)
    geometry_score = (
        1.0
        if left_contains_right or right_contains_left
        else 0.5
        if left_bounds_contain_right or right_bounds_contain_left or bounds_overlap
        else 0.0
    )
    left_identities = _osm_identity_tokens(left)
    right_identities = _osm_identity_tokens(right)
    matching_identities = sorted(left_identities & right_identities)
    distance_score = max(
        0.0, 1.0 - distance_m / thresholds.nearby_max_distance_m
    )
    return {
        "address_similarity": round(
            _similarity(_address(left.tags), _address(right.tags)), 6
        ),
        "country_left": left_country,
        "country_match": (
            left_country == right_country
            if left_country is not None and right_country is not None
            else None
        ),
        "country_right": right_country,
        "distance_score": round(distance_score, 6),
        "geometry_bounds_overlap": bounds_overlap,
        "geometry_left_bounds_contain_right": left_bounds_contain_right,
        "geometry_left_contains_right": left_contains_right,
        "geometry_right_bounds_contain_left": right_bounds_contain_left,
        "geometry_right_contains_left": right_contains_left,
        "geometry_score": geometry_score,
        "name_similarity": round(_similarity(left.name, right.name, names=True), 6),
        "exact_upstream_identity_match": bool(matching_identities),
        "matching_upstream_identities": matching_identities,
        "owner_operator_similarity": round(
            _set_similarity(_organizations(left.tags), _organizations(right.tags)), 6
        ),
        "left_source_root": left_source_root,
        "right_source_root": right_source_root,
        "source_independent": left_source_root != right_source_root,
    }


def _score(signals: Mapping[str, Any]) -> float:
    score = (
        0.35 * signals["distance_score"]
        + 0.30 * signals["name_similarity"]
        + 0.15 * signals["address_similarity"]
        + 0.12 * signals["owner_operator_similarity"]
        + 0.08 * signals["geometry_score"]
    )
    if signals.get("exact_upstream_identity_match"):
        score = max(score, 0.99)
    return round(min(1.0, max(0.0, score)), 6)


def _relationship(
    left: _Record,
    right: _Record,
    *,
    distance_m: float,
    score: float,
    thresholds: ResolutionThresholds,
) -> tuple[str, str | None, str | None]:
    if left.kind != right.kind:
        campus = left if left.kind == "campus" else right
        facility = right if left.kind == "campus" else left
        if (
            distance_m <= thresholds.part_of_max_distance_m
            and score >= thresholds.part_of_min_score
        ):
            return "part_of_candidate", campus.entity_id, facility.entity_id
        return "nearby_only", None, None
    if (
        distance_m <= thresholds.same_site_max_distance_m
        and score >= thresholds.same_site_min_score
    ):
        return "same_site_candidate", None, None
    return "nearby_only", None, None


def _candidate_link(
    left: _Record,
    right: _Record,
    *,
    thresholds: ResolutionThresholds,
) -> CandidateLink | None:
    left_country = _country(left.tags)
    right_country = _country(right.tags)
    if left_country and right_country and left_country != right_country:
        return None
    distance_m = haversine_distance_m(
        left.latitude,
        left.longitude,
        right.latitude,
        right.longitude,
    )
    exact_identity_match = bool(
        _osm_identity_tokens(left) & _osm_identity_tokens(right)
    )
    if distance_m > thresholds.nearby_max_distance_m and not exact_identity_match:
        return None
    signals = _signals(left, right, distance_m, thresholds)
    score = _score(signals)
    relationship, parent_id, child_id = _relationship(
        left,
        right,
        distance_m=distance_m,
        score=score,
        thresholds=thresholds,
    )
    return CandidateLink(
        relationship_suggestion=relationship,
        score=score,
        distance_m=round(distance_m, 3),
        left_entity_id=left.entity_id,
        left_entity_kind=left.kind,
        left_name=left.name,
        left_source_family=left.source_family,
        left_evidence_id=left.evidence_id,
        right_entity_id=right.entity_id,
        right_entity_kind=right.kind,
        right_name=right.name,
        right_source_family=right.source_family,
        right_evidence_id=right.evidence_id,
        suggested_parent_entity_id=parent_id,
        suggested_child_entity_id=child_id,
        signals=signals,
    )


def _candidate_sort_key(item: CandidateLink) -> tuple[str, str, str]:
    return (
        item.left_entity_id,
        item.right_entity_id,
        item.relationship_suggestion,
    )


def generate_candidate_links(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
    thresholds: ResolutionThresholds | None = None,
) -> list[CandidateLink]:
    """Compare current cross-source campuses/facilities without modifying the database."""

    thresholds = thresholds or ResolutionThresholds()
    records = _current_records(connection, as_of=as_of, recorded_at=recorded_at)
    candidates: list[CandidateLink] = []
    for left, right in _spatial_candidate_pairs(
        records, thresholds.nearby_max_distance_m
    ):
        if left.source_family == right.source_family:
            continue
        candidate = _candidate_link(left, right, thresholds=thresholds)
        if candidate is not None:
            candidates.append(candidate)
    return sorted(candidates, key=_candidate_sort_key)


def generate_candidate_links_between(
    left_connection: sqlite3.Connection,
    right_connection: sqlite3.Connection,
    *,
    left_as_of: str,
    left_recorded_at: str,
    right_as_of: str,
    right_recorded_at: str,
    thresholds: ResolutionThresholds | None = None,
) -> list[CandidateLink]:
    """Compare two release databases without copying or mutating either one.

    The left/right orientation is retained in every candidate.  Unlike the
    within-database report, equal source-family labels are not suppressed:
    two separately published releases can legitimately contain duplicate
    source-scoped observations that need an explicit advisory link.
    """

    thresholds = thresholds or ResolutionThresholds()
    left_records = _current_records(
        left_connection,
        as_of=left_as_of,
        recorded_at=left_recorded_at,
    )
    right_records = _current_records(
        right_connection,
        as_of=right_as_of,
        recorded_at=right_recorded_at,
    )
    candidates: list[CandidateLink] = []
    compared_pairs: set[tuple[str, str]] = set()
    for left, right in _spatial_candidate_pairs_between(
        left_records,
        right_records,
        thresholds.nearby_max_distance_m,
    ):
        pair = (left.entity_id, right.entity_id)
        compared_pairs.add(pair)
        candidate = _candidate_link(left, right, thresholds=thresholds)
        if candidate is not None:
            candidates.append(candidate)
    right_by_osm_identity: dict[str, list[_Record]] = {}
    for right in right_records:
        for identity in _osm_identity_tokens(right):
            right_by_osm_identity.setdefault(identity, []).append(right)
    for left in left_records:
        exact_rights = {
            right.entity_id: right
            for identity in _osm_identity_tokens(left)
            for right in right_by_osm_identity.get(identity, ())
        }
        for right in exact_rights.values():
            pair = (left.entity_id, right.entity_id)
            if pair in compared_pairs:
                continue
            compared_pairs.add(pair)
            candidate = _candidate_link(left, right, thresholds=thresholds)
            if candidate is not None:
                candidates.append(candidate)
    return sorted(candidates, key=_candidate_sort_key)


def candidate_links_to_json(candidates: Sequence[CandidateLink]) -> str:
    """Serialize candidate links to stable, pretty-printed JSON."""

    rows = [candidate.as_dict() for candidate in candidates]
    rows.sort(key=lambda row: (row["left_entity_id"], row["right_entity_id"]))
    return json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


CSV_FIELDS = (
    "relationship_suggestion",
    "score",
    "distance_m",
    "left_entity_id",
    "left_entity_kind",
    "left_name",
    "left_source_family",
    "left_evidence_id",
    "right_entity_id",
    "right_entity_kind",
    "right_name",
    "right_source_family",
    "right_evidence_id",
    "suggested_parent_entity_id",
    "suggested_child_entity_id",
    "signals_json",
)


def candidate_links_to_csv(candidates: Sequence[CandidateLink]) -> str:
    """Serialize candidate links to deterministic RFC 4180-style CSV."""

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for candidate in sorted(
        candidates, key=lambda item: (item.left_entity_id, item.right_entity_id)
    ):
        row = candidate.as_dict()
        row["signals_json"] = json.dumps(
            row.pop("signals"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        writer.writerow(row)
    return stream.getvalue()
