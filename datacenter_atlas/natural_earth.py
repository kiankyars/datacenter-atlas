"""Pinned Natural Earth country boundaries and evidence-backed enrichment.

Natural Earth 1:10m Admin-0 Countries v5.1.1 is public-domain reference
geometry.  This module verifies the exact upstream bytes, validates all 258
features without a GIS dependency, and records spatial assignments separately
from source snapshots.  It never rewrites source tags.

The point-in-polygon policy is intentionally conservative:

* an interior hit in exactly one feature is assigned;
* no hit is recorded as unmatched;
* multiple interior hits are unresolved as ambiguous;
* any polygon-edge or hole-edge contact is unresolved as boundary.

Thus shared borders, disputed overlaps, and numerical edge cases are surfaced
rather than resolved with an arbitrary feature order.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, cast

from ._iso3166 import ISO_3166_1
from .models import (
    AdministrativeAssignment,
    AdministrativeResolutionStatus,
    Evidence,
    EvidenceKind,
)
from .repository import (
    add_administrative_assignment,
    add_evidence,
    stable_id,
    utc_now,
)
from .timestamps import (
    canonical_read_cutoff,
    canonical_storage_timestamp,
    require_canonical_persistence_state,
)


NATURAL_EARTH_VERSION = "5.1.1"
NATURAL_EARTH_COMMIT = "ca96624a56bd078437bca8184e78163e5039ad19"
NATURAL_EARTH_FILENAME = "ne_10m_admin_0_countries.geojson"
NATURAL_EARTH_RAW_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{NATURAL_EARTH_COMMIT}/geojson/{NATURAL_EARTH_FILENAME}"
)
NATURAL_EARTH_INFO_URL = (
    "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/"
    "10m-admin-0-countries/"
)
NATURAL_EARTH_RIGHTS_URL = (
    "https://www.naturalearthdata.com/about/terms-of-use/"
)
NATURAL_EARTH_EXPECTED_BYTES = 13_287_234
NATURAL_EARTH_SHA256 = (
    "239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255"
)
NATURAL_EARTH_FEATURE_COUNT = 258
NATURAL_EARTH_LICENSE = "Public Domain"
NATURAL_EARTH_SOURCE_FAMILY = "natural_earth"
NATURAL_EARTH_PUBLISHER = "Natural Earth"
NATURAL_EARTH_ATTRIBUTION = "Natural Earth"
NATURAL_EARTH_MANIFEST = "manifest.json"
NATURAL_EARTH_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)
BOUNDARY_EPSILON = 1e-10


class NaturalEarthError(ValueError):
    """The pinned artifact or its geometry does not satisfy the contract."""


@dataclass(frozen=True, slots=True)
class NaturalEarthArtifact:
    url: str = NATURAL_EARTH_RAW_URL
    version: str = NATURAL_EARTH_VERSION
    commit: str = NATURAL_EARTH_COMMIT
    filename: str = NATURAL_EARTH_FILENAME
    expected_bytes: int = NATURAL_EARTH_EXPECTED_BYTES
    sha256: str = NATURAL_EARTH_SHA256
    feature_count: int = NATURAL_EARTH_FEATURE_COUNT

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise ValueError("Natural Earth URL must use HTTPS")
        if not self.version.strip() or not self.commit.strip():
            raise ValueError("Natural Earth version and commit are required")
        if Path(self.filename).name != self.filename:
            raise ValueError("Natural Earth filename must be a basename")
        if self.expected_bytes <= 0 or self.feature_count <= 0:
            raise ValueError("Natural Earth byte and feature counts must be positive")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("Natural Earth SHA256 must be lowercase hexadecimal")


NATURAL_EARTH_ARTIFACT = NaturalEarthArtifact()


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CanonicalCountry:
    name: str
    iso_a2: str | None
    iso_a3: str | None
    method: str


@dataclass(frozen=True, slots=True)
class NaturalEarthFeature:
    feature_id: str
    admin: str
    sovereignt: str
    feature_type: str
    note_adm0: str | None
    note_brk: str | None
    source_iso_a2: str
    source_iso_a3: str
    source_iso_a2_eh: str
    source_iso_a3_eh: str
    canonical_country: CanonicalCountry
    bbox: tuple[float, float, float, float]
    crosses_antimeridian: bool
    polygon_bboxes: tuple[tuple[float, float, float, float], ...]
    polygon_crosses_antimeridian: tuple[bool, ...]
    geometry_type: str
    coordinates: Any


@dataclass(frozen=True, slots=True)
class NaturalEarthDataset:
    artifact: NaturalEarthArtifact
    verification: ArtifactVerification
    features: tuple[NaturalEarthFeature, ...]
    canonicalization_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class SpatialMatch:
    status: AdministrativeResolutionStatus
    feature: NaturalEarthFeature | None
    match_feature_ids: tuple[str, ...]
    method: str
    confidence: float


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    examined_snapshots: int
    assignments_created: int
    evidence_created: int
    assigned: int
    unmatched: int
    ambiguous: int
    boundary: int
    source_conflicts: int


class _PointRelation(StrEnum):
    OUTSIDE = "outside"
    INSIDE = "inside"
    BOUNDARY = "boundary"


_ISO_BY_A2 = {alpha2: (alpha2, alpha3, names) for alpha2, alpha3, names in ISO_3166_1}
_ISO_BY_A3 = {alpha3: (alpha2, alpha3, names) for alpha2, alpha3, names in ISO_3166_1}
_ISO_BY_NAME = {
    name.casefold(): (alpha2, alpha3, names)
    for alpha2, alpha3, names in ISO_3166_1
    for name in names
}
_SOURCE_COUNTRY_ALIASES = {
    "ivory coast": "CI",
}


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, digest.hexdigest()


def verify_natural_earth_artifact(
    path: str | Path,
    *,
    artifact: NaturalEarthArtifact = NATURAL_EARTH_ARTIFACT,
) -> ArtifactVerification:
    source = Path(path)
    if not source.is_file():
        raise NaturalEarthError(f"Natural Earth artifact is not a file: {source}")
    byte_count, sha256 = _hash_file(source)
    if byte_count != artifact.expected_bytes:
        raise NaturalEarthError(
            "Natural Earth byte count does not match the pin: "
            f"expected {artifact.expected_bytes}, got {byte_count}"
        )
    if sha256 != artifact.sha256:
        raise NaturalEarthError(
            "Natural Earth SHA256 does not match the pin: "
            f"expected {artifact.sha256}, got {sha256}"
        )
    return ArtifactVerification(source, byte_count, sha256)


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NaturalEarthError(f"{field} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NaturalEarthError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NaturalEarthError(f"{field} must include a timezone")
    return value


def _require_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise NaturalEarthError(f"{field} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise NaturalEarthError(f"{field} must be an ISO date") from error
    return value


def _write_json_atomic(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _manifest_document(
    artifact: NaturalEarthArtifact,
    verification: ArtifactVerification,
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": "Natural Earth 1:10m Admin-0 Countries",
        "theme_version": artifact.version,
        "git_commit": artifact.commit,
        "source_family": NATURAL_EARTH_SOURCE_FAMILY,
        "license": NATURAL_EARTH_LICENSE,
        "public_domain": True,
        "official_info_url": NATURAL_EARTH_INFO_URL,
        "official_rights_url": NATURAL_EARTH_RIGHTS_URL,
        "fetched_at": fetched_at,
        "artifact": {
            "file": artifact.filename,
            "url": artifact.url,
            "bytes": verification.bytes,
            "sha256": verification.sha256,
            "feature_count": artifact.feature_count,
        },
    }


def _validate_manifest(document: Any, artifact: NaturalEarthArtifact) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise NaturalEarthError("Natural Earth manifest must be a JSON object")
    expected = {
        "schema_version": 1,
        "dataset": "Natural Earth 1:10m Admin-0 Countries",
        "theme_version": artifact.version,
        "git_commit": artifact.commit,
        "source_family": NATURAL_EARTH_SOURCE_FAMILY,
        "license": NATURAL_EARTH_LICENSE,
        "public_domain": True,
        "official_info_url": NATURAL_EARTH_INFO_URL,
        "official_rights_url": NATURAL_EARTH_RIGHTS_URL,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise NaturalEarthError(f"Natural Earth manifest has unexpected {key}")
    _require_timestamp(document.get("fetched_at"), "Natural Earth fetched_at")
    checkpoint = document.get("artifact")
    expected_checkpoint = {
        "file": artifact.filename,
        "url": artifact.url,
        "bytes": artifact.expected_bytes,
        "sha256": artifact.sha256,
        "feature_count": artifact.feature_count,
    }
    if checkpoint != expected_checkpoint:
        raise NaturalEarthError("Natural Earth artifact checkpoint does not match the pin")
    return document


def validate_natural_earth_bundle(
    path: str | Path,
    *,
    artifact: NaturalEarthArtifact = NATURAL_EARTH_ARTIFACT,
) -> tuple[Path, dict[str, Any], ArtifactVerification]:
    bundle = Path(path)
    manifest_path = bundle / NATURAL_EARTH_MANIFEST
    if not bundle.is_dir() or not manifest_path.is_file():
        raise NaturalEarthError("Natural Earth bundle must contain manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NaturalEarthError("Natural Earth manifest is invalid JSON") from error
    _validate_manifest(manifest, artifact)
    source = bundle / artifact.filename
    verification = verify_natural_earth_artifact(source, artifact=artifact)
    return source, manifest, verification


class NaturalEarthFetcher:
    """Fetch or checkpoint exactly one immutable Natural Earth GeoJSON file."""

    def __init__(
        self,
        *,
        artifact: NaturalEarthArtifact = NATURAL_EARTH_ARTIFACT,
        user_agent: str = NATURAL_EARTH_USER_AGENT,
        timeout: float = 120.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.artifact = artifact
        self.user_agent = user_agent
        self.timeout = timeout
        self.opener = opener

    def fetch(
        self, output_directory: str | Path, *, fetched_at: str | None = None
    ) -> dict[str, Any]:
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir():
            raise ValueError(f"Natural Earth output is not a directory: {output}")
        artifact_path = output / self.artifact.filename
        manifest_path = output / NATURAL_EARTH_MANIFEST
        checkpoint_time = _require_timestamp(fetched_at or utc_now(), "fetched_at")

        if artifact_path.exists():
            verification = verify_natural_earth_artifact(
                artifact_path, artifact=self.artifact
            )
            if manifest_path.exists():
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
                return _validate_manifest(document, self.artifact)
            document = _manifest_document(
                self.artifact, verification, checkpoint_time
            )
            _write_json_atomic(manifest_path, document)
            return document
        if manifest_path.exists():
            raise NaturalEarthError("manifest exists but the Natural Earth artifact is missing")

        request = urllib.request.Request(
            self.artifact.url,
            headers={
                "Accept": "application/geo+json, application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        temporary = artifact_path.with_name(f".{artifact_path.name}.tmp")
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with self.opener(request, timeout=self.timeout) as response, temporary.open(
                "wb"
            ) as destination:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise NaturalEarthError("Natural Earth response was not raw bytes")
                    byte_count += len(chunk)
                    if byte_count > self.artifact.expected_bytes:
                        raise NaturalEarthError(
                            "Natural Earth response exceeds the pinned byte count"
                        )
                    digest.update(chunk)
                    destination.write(chunk)
            if byte_count != self.artifact.expected_bytes:
                raise NaturalEarthError(
                    "downloaded Natural Earth byte count does not match the pin"
                )
            if digest.hexdigest() != self.artifact.sha256:
                raise NaturalEarthError(
                    "downloaded Natural Earth SHA256 does not match the pin"
                )
            temporary.replace(artifact_path)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        verification = verify_natural_earth_artifact(
            artifact_path, artifact=self.artifact
        )
        document = _manifest_document(self.artifact, verification, checkpoint_time)
        _write_json_atomic(manifest_path, document)
        return document


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NaturalEarthError(f"Natural Earth {field} must be non-empty text")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NaturalEarthError(f"Natural Earth {field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise NaturalEarthError(f"Natural Earth {field} must be finite")
    return result


def _bbox(value: Any, field: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise NaturalEarthError(f"Natural Earth {field} must contain four numbers")
    result = tuple(_number(item, field) for item in value)
    min_x, min_y, max_x, max_y = result
    if not -180 <= min_x <= 180 or not -180 <= max_x <= 180:
        raise NaturalEarthError(f"Natural Earth {field} longitude is out of bounds")
    if not -90 <= min_y <= max_y <= 90:
        raise NaturalEarthError(f"Natural Earth {field} latitude is out of bounds")
    return cast(tuple[float, float, float, float], result)


def _position(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise NaturalEarthError(f"Natural Earth {field} position must have two numbers")
    longitude = _number(value[0], field)
    latitude = _number(value[1], field)
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise NaturalEarthError(f"Natural Earth {field} position is out of bounds")
    return longitude, latitude


def _ring(value: Any, field: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 4:
        raise NaturalEarthError(f"Natural Earth {field} ring needs at least four positions")
    result = tuple(_position(position, field) for position in value)
    if result[0] != result[-1]:
        raise NaturalEarthError(f"Natural Earth {field} ring is not closed")
    return result


def _polygon(value: Any, field: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    if not isinstance(value, list) or not value:
        raise NaturalEarthError(f"Natural Earth {field} polygon has no rings")
    return tuple(_ring(ring, field) for ring in value)


def _geometry(value: Any, field: str) -> tuple[str, Any]:
    if not isinstance(value, dict):
        raise NaturalEarthError(f"Natural Earth {field} geometry must be an object")
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "Polygon":
        return geometry_type, _polygon(coordinates, field)
    if geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise NaturalEarthError(f"Natural Earth {field} multipolygon is empty")
        return geometry_type, tuple(
            _polygon(polygon, field) for polygon in coordinates
        )
    raise NaturalEarthError(f"Natural Earth {field} geometry must be Polygon/MultiPolygon")


def _geometry_points(geometry_type: str, coordinates: Any) -> Iterable[tuple[float, float]]:
    polygons = (coordinates,) if geometry_type == "Polygon" else coordinates
    for polygon in polygons:
        for ring in polygon:
            yield from ring


def _geometry_crosses_antimeridian(geometry_type: str, coordinates: Any) -> bool:
    polygons = (coordinates,) if geometry_type == "Polygon" else coordinates
    return any(
        abs(end[0] - start[0]) > 180
        for polygon in polygons
        for ring in polygon
        for start, end in zip(ring, ring[1:])
    )


def _geometry_polygons(geometry_type: str, coordinates: Any) -> tuple[Any, ...]:
    return (coordinates,) if geometry_type == "Polygon" else coordinates


def _polygon_bbox(
    polygon: Sequence[Sequence[tuple[float, float]]],
) -> tuple[float, float, float, float]:
    points = [point for ring in polygon for point in ring]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _polygon_crosses_antimeridian(
    polygon: Sequence[Sequence[tuple[float, float]]],
) -> bool:
    return any(
        abs(end[0] - start[0]) > 180
        for ring in polygon
        for start, end in zip(ring, ring[1:])
    )


def _canonical_country(properties: Mapping[str, Any]) -> CanonicalCountry:
    standard_a2 = _required_text(properties.get("ISO_A2"), "ISO_A2")
    standard_a3 = _required_text(properties.get("ISO_A3"), "ISO_A3")
    eh_a2 = _required_text(properties.get("ISO_A2_EH"), "ISO_A2_EH")
    eh_a3 = _required_text(properties.get("ISO_A3_EH"), "ISO_A3_EH")
    use_fallback = standard_a2 == "-99" or standard_a3 == "-99"
    alpha2, alpha3 = (eh_a2, eh_a3) if use_fallback else (standard_a2, standard_a3)
    record_a2 = _ISO_BY_A2.get(alpha2)
    record_a3 = _ISO_BY_A3.get(alpha3)
    if record_a2 is not None and record_a3 is not None and record_a2[:2] == record_a3[:2]:
        return CanonicalCountry(
            name=record_a2[2][0],
            iso_a2=record_a2[0],
            iso_a3=record_a2[1],
            method="iso_eh_fallback" if use_fallback else "iso_standard",
        )
    return CanonicalCountry(
        name=_required_text(properties.get("ADMIN"), "ADMIN"),
        iso_a2=None,
        iso_a3=None,
        method="natural_earth_non_iso_label",
    )


def canonicalize_source_country(value: Any) -> CanonicalCountry | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    upper = text.upper()
    record = _ISO_BY_A2.get(upper) or _ISO_BY_A3.get(upper)
    if record is None:
        record = _ISO_BY_NAME.get(text.casefold())
    if record is None:
        record = _ISO_BY_A2.get(_SOURCE_COUNTRY_ALIASES.get(text.casefold(), ""))
    if record is None:
        return None
    return CanonicalCountry(record[2][0], record[0], record[1], "source_tag_iso")


def load_natural_earth_dataset(
    path: str | Path,
    *,
    artifact: NaturalEarthArtifact = NATURAL_EARTH_ARTIFACT,
) -> NaturalEarthDataset:
    source, _manifest, verification = validate_natural_earth_bundle(
        path, artifact=artifact
    )
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NaturalEarthError("Natural Earth GeoJSON is invalid UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise NaturalEarthError("Natural Earth root must be a FeatureCollection")
    if document.get("name") != "ne_10m_admin_0_countries":
        raise NaturalEarthError("Natural Earth collection name does not match the theme")
    if document.get("crs") != {
        "type": "name",
        "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
    }:
        raise NaturalEarthError("Natural Earth CRS must be CRS84")
    _bbox(document.get("bbox"), "collection bbox")
    raw_features = document.get("features")
    if not isinstance(raw_features, list) or len(raw_features) != artifact.feature_count:
        raise NaturalEarthError(
            f"Natural Earth must contain exactly {artifact.feature_count} features"
        )

    features: list[NaturalEarthFeature] = []
    feature_ids: set[str] = set()
    canonicalization_counts = {
        "iso_standard": 0,
        "iso_eh_fallback": 0,
        "natural_earth_non_iso_label": 0,
    }
    for index, raw_feature in enumerate(raw_features):
        field = f"feature {index}"
        if not isinstance(raw_feature, dict) or raw_feature.get("type") != "Feature":
            raise NaturalEarthError(f"Natural Earth {field} must be a Feature")
        properties = raw_feature.get("properties")
        if not isinstance(properties, dict):
            raise NaturalEarthError(f"Natural Earth {field} properties must be an object")
        ne_id = properties.get("NE_ID")
        if isinstance(ne_id, bool) or not isinstance(ne_id, int) or ne_id <= 0:
            raise NaturalEarthError(f"Natural Earth {field} NE_ID must be positive")
        feature_id = str(ne_id)
        if feature_id in feature_ids:
            raise NaturalEarthError(f"Natural Earth duplicate NE_ID {feature_id}")
        feature_ids.add(feature_id)
        recorded_bbox = _bbox(raw_feature.get("bbox"), f"{field} bbox")
        geometry_type, coordinates = _geometry(raw_feature.get("geometry"), field)
        points = list(_geometry_points(geometry_type, coordinates))
        actual_bbox = (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )
        if any(
            not math.isclose(recorded, actual, rel_tol=0, abs_tol=1e-12)
            for recorded, actual in zip(recorded_bbox, actual_bbox, strict=True)
        ):
            raise NaturalEarthError(f"Natural Earth {field} bbox does not match geometry")
        canonical = _canonical_country(properties)
        canonicalization_counts[canonical.method] += 1
        polygons = _geometry_polygons(geometry_type, coordinates)
        features.append(
            NaturalEarthFeature(
                feature_id=feature_id,
                admin=_required_text(properties.get("ADMIN"), f"{field}.ADMIN"),
                sovereignt=_required_text(
                    properties.get("SOVEREIGNT"), f"{field}.SOVEREIGNT"
                ),
                feature_type=_required_text(properties.get("TYPE"), f"{field}.TYPE"),
                note_adm0=_optional_text(
                    properties.get("NOTE_ADM0"), f"{field}.NOTE_ADM0"
                ),
                note_brk=_optional_text(
                    properties.get("NOTE_BRK"), f"{field}.NOTE_BRK"
                ),
                source_iso_a2=_required_text(
                    properties.get("ISO_A2"), f"{field}.ISO_A2"
                ),
                source_iso_a3=_required_text(
                    properties.get("ISO_A3"), f"{field}.ISO_A3"
                ),
                source_iso_a2_eh=_required_text(
                    properties.get("ISO_A2_EH"), f"{field}.ISO_A2_EH"
                ),
                source_iso_a3_eh=_required_text(
                    properties.get("ISO_A3_EH"), f"{field}.ISO_A3_EH"
                ),
                canonical_country=canonical,
                bbox=recorded_bbox,
                crosses_antimeridian=_geometry_crosses_antimeridian(
                    geometry_type, coordinates
                ),
                polygon_bboxes=tuple(_polygon_bbox(polygon) for polygon in polygons),
                polygon_crosses_antimeridian=tuple(
                    _polygon_crosses_antimeridian(polygon) for polygon in polygons
                ),
                geometry_type=geometry_type,
                coordinates=coordinates,
            )
        )
    return NaturalEarthDataset(
        artifact=artifact,
        verification=verification,
        features=tuple(features),
        canonicalization_counts=canonicalization_counts,
    )


def _bbox_contains(
    bbox: tuple[float, float, float, float],
    longitude: float,
    latitude: float,
    *,
    crosses_antimeridian: bool = False,
) -> bool:
    min_x, min_y, max_x, max_y = bbox
    if not min_y - BOUNDARY_EPSILON <= latitude <= max_y + BOUNDARY_EPSILON:
        return False
    if crosses_antimeridian:
        return True
    if min_x <= max_x:
        return min_x - BOUNDARY_EPSILON <= longitude <= max_x + BOUNDARY_EPSILON
    return longitude >= min_x - BOUNDARY_EPSILON or longitude <= max_x + BOUNDARY_EPSILON


def _unwrap_ring(
    ring: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    unwrapped = [ring[0]]
    for longitude, latitude in ring[1:]:
        previous = unwrapped[-1][0]
        while longitude - previous > 180:
            longitude -= 360
        while longitude - previous < -180:
            longitude += 360
        unwrapped.append((longitude, latitude))
    return tuple(unwrapped)


def _point_on_segment(
    point_x: float,
    point_y: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    start_x, start_y = start
    end_x, end_y = end
    cross = (point_x - start_x) * (end_y - start_y) - (
        point_y - start_y
    ) * (end_x - start_x)
    scale = max(1.0, abs(end_x - start_x), abs(end_y - start_y))
    if abs(cross) > BOUNDARY_EPSILON * scale:
        return False
    return (
        min(start_x, end_x) - BOUNDARY_EPSILON
        <= point_x
        <= max(start_x, end_x) + BOUNDARY_EPSILON
        and min(start_y, end_y) - BOUNDARY_EPSILON
        <= point_y
        <= max(start_y, end_y) + BOUNDARY_EPSILON
    )


def _ring_relation_for_longitude(
    ring: Sequence[tuple[float, float]], longitude: float, latitude: float
) -> _PointRelation:
    inside = False
    for start, end in zip(ring, ring[1:]):
        if _point_on_segment(longitude, latitude, start, end):
            return _PointRelation.BOUNDARY
        start_x, start_y = start
        end_x, end_y = end
        if (start_y > latitude) != (end_y > latitude):
            intersection_x = start_x + (latitude - start_y) * (
                end_x - start_x
            ) / (end_y - start_y)
            if longitude < intersection_x:
                inside = not inside
    return _PointRelation.INSIDE if inside else _PointRelation.OUTSIDE


def _ring_relation(
    ring: Sequence[tuple[float, float]], longitude: float, latitude: float
) -> _PointRelation:
    unwrapped = _unwrap_ring(ring)
    mean_longitude = sum(point[0] for point in unwrapped[:-1]) / max(
        1, len(unwrapped) - 1
    )
    nearest_wrap = round((mean_longitude - longitude) / 360)
    inside = False
    for wrap in (nearest_wrap - 1, nearest_wrap, nearest_wrap + 1):
        relation = _ring_relation_for_longitude(
            unwrapped, longitude + 360 * wrap, latitude
        )
        if relation is _PointRelation.BOUNDARY:
            return relation
        if relation is _PointRelation.INSIDE:
            inside = True
    return _PointRelation.INSIDE if inside else _PointRelation.OUTSIDE


def _polygon_relation(
    polygon: Sequence[Sequence[tuple[float, float]]],
    longitude: float,
    latitude: float,
) -> _PointRelation:
    outer = _ring_relation(polygon[0], longitude, latitude)
    if outer is not _PointRelation.INSIDE:
        return outer
    for hole in polygon[1:]:
        relation = _ring_relation(hole, longitude, latitude)
        if relation is _PointRelation.BOUNDARY:
            return relation
        if relation is _PointRelation.INSIDE:
            return _PointRelation.OUTSIDE
    return _PointRelation.INSIDE


def feature_point_relation(
    feature: NaturalEarthFeature, longitude: float, latitude: float
) -> _PointRelation:
    if not _bbox_contains(
        feature.bbox,
        longitude,
        latitude,
        crosses_antimeridian=feature.crosses_antimeridian,
    ):
        return _PointRelation.OUTSIDE
    polygons = _geometry_polygons(feature.geometry_type, feature.coordinates)
    inside = False
    for polygon, polygon_bbox, crosses_antimeridian in zip(
        polygons,
        feature.polygon_bboxes,
        feature.polygon_crosses_antimeridian,
        strict=True,
    ):
        if not _bbox_contains(
            polygon_bbox,
            longitude,
            latitude,
            crosses_antimeridian=crosses_antimeridian,
        ):
            continue
        relation = _polygon_relation(polygon, longitude, latitude)
        if relation is _PointRelation.BOUNDARY:
            return relation
        if relation is _PointRelation.INSIDE:
            inside = True
    return _PointRelation.INSIDE if inside else _PointRelation.OUTSIDE


def assign_country(
    dataset: NaturalEarthDataset, longitude: float, latitude: float
) -> SpatialMatch:
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("longitude must be finite and within [-180, 180]")
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("latitude must be finite and within [-90, 90]")
    interiors: list[NaturalEarthFeature] = []
    boundaries: list[NaturalEarthFeature] = []
    for feature in dataset.features:
        relation = feature_point_relation(feature, longitude, latitude)
        if relation is _PointRelation.INSIDE:
            interiors.append(feature)
        elif relation is _PointRelation.BOUNDARY:
            boundaries.append(feature)
    matches = sorted(
        {feature.feature_id for feature in (*interiors, *boundaries)},
        key=lambda value: int(value),
    )
    if boundaries:
        return SpatialMatch(
            AdministrativeResolutionStatus.BOUNDARY,
            None,
            tuple(matches),
            "natural_earth_v5_1_1_boundary_contact_unresolved",
            1.0,
        )
    if len(interiors) > 1:
        return SpatialMatch(
            AdministrativeResolutionStatus.AMBIGUOUS,
            None,
            tuple(matches),
            "natural_earth_v5_1_1_multiple_containing_features_unresolved",
            1.0,
        )
    if not interiors:
        return SpatialMatch(
            AdministrativeResolutionStatus.UNMATCHED,
            None,
            (),
            "natural_earth_v5_1_1_no_containing_feature",
            1.0,
        )
    feature = interiors[0]
    return SpatialMatch(
        AdministrativeResolutionStatus.ASSIGNED,
        feature,
        (feature.feature_id,),
        f"natural_earth_v5_1_1_point_in_polygon_{feature.canonical_country.method}",
        0.99 if feature.canonical_country.iso_a3 else 0.85,
    )


def _snapshot_country_tag(tags: Mapping[str, Any]) -> str | None:
    for key in ("country", "country_name", "addr:country"):
        value = tags.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _current_coordinate_snapshots(
    connection: sqlite3.Connection, *, as_of: str, recorded_at: str
) -> list[sqlite3.Row]:
    recorded_at = canonical_read_cutoff(recorded_at)
    require_canonical_persistence_state(connection)
    return connection.execute(
        """
        WITH eligible AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY entity_id
                       ORDER BY as_of_date DESC, recorded_at DESC, id DESC
                   ) AS temporal_rank
            FROM entity_snapshots
            WHERE as_of_date <= ?
              AND (valid_to_date IS NULL OR ? < valid_to_date)
              AND recorded_at <= ?
              AND (superseded_at IS NULL OR ? < superseded_at)
        )
        SELECT * FROM eligible
        WHERE temporal_rank = 1
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY entity_id
        """,
        (as_of, as_of, recorded_at, recorded_at),
    ).fetchall()


def enrich_administrative_assignments(
    connection: sqlite3.Connection,
    bundle: str | Path,
    *,
    as_of: str,
    recorded_at: str,
    artifact: NaturalEarthArtifact = NATURAL_EARTH_ARTIFACT,
) -> EnrichmentResult:
    """Assign current geocoded snapshots without changing their source tags."""
    _require_date(as_of, "as_of")
    try:
        recorded_at = canonical_storage_timestamp(recorded_at, "recorded_at")
        require_canonical_persistence_state(connection)
    except ValueError as error:
        raise NaturalEarthError(str(error)) from error
    source, manifest, verification = validate_natural_earth_bundle(
        bundle, artifact=artifact
    )
    dataset = load_natural_earth_dataset(bundle, artifact=artifact)
    snapshots = _current_coordinate_snapshots(
        connection, as_of=as_of, recorded_at=recorded_at
    )
    evidence_id = stable_id(
        "evidence",
        NATURAL_EARTH_SOURCE_FAMILY,
        artifact.version,
        artifact.commit,
        verification.sha256,
        manifest["fetched_at"],
    )
    evidence_created = 0
    assignments_created = 0
    counts = {
        AdministrativeResolutionStatus.ASSIGNED: 0,
        AdministrativeResolutionStatus.UNMATCHED: 0,
        AdministrativeResolutionStatus.AMBIGUOUS: 0,
        AdministrativeResolutionStatus.BOUNDARY: 0,
    }
    source_conflicts = 0
    match_cache: dict[tuple[float, float], SpatialMatch] = {}
    with connection:
        evidence_created += int(
            add_evidence(
                connection,
                Evidence(
                    id=evidence_id,
                    kind=EvidenceKind.THIRD_PARTY_DATASET,
                    title=(
                        "Natural Earth 1:10m Admin-0 Countries "
                        f"v{artifact.version}"
                    ),
                    source_url=artifact.url,
                    publisher=NATURAL_EARTH_PUBLISHER,
                    source_family=NATURAL_EARTH_SOURCE_FAMILY,
                    license=NATURAL_EARTH_LICENSE,
                    attribution=NATURAL_EARTH_ATTRIBUTION,
                    published_at=artifact.version,
                    retrieved_at=manifest["fetched_at"],
                    excerpt=(
                        "Public-domain country boundary geometry used for deterministic "
                        "point-in-polygon administrative enrichment."
                    ),
                ),
                content_hash=verification.sha256,
                metadata={
                    "theme_version": artifact.version,
                    "git_commit": artifact.commit,
                    "artifact_url": artifact.url,
                    "artifact_file": source.name,
                    "artifact_bytes": verification.bytes,
                    "artifact_sha256": verification.sha256,
                    "feature_count": artifact.feature_count,
                    "official_info_url": NATURAL_EARTH_INFO_URL,
                    "official_rights_url": NATURAL_EARTH_RIGHTS_URL,
                    "public_domain": True,
                    "point_in_polygon_policy": {
                        "bbox_pruning": True,
                        "polygon_holes": "hole interiors are outside; hole edges are boundary",
                        "antimeridian": "rings are unwrapped relative to each query longitude",
                        "boundary_epsilon_degrees": BOUNDARY_EPSILON,
                        "boundary_contacts": "unresolved",
                        "multiple_feature_matches": "unresolved as ambiguous",
                        "single_strict_interior": "assigned",
                    },
                    "provenance": {
                        "artifact_url": artifact.url,
                        "artifact_bytes": verification.bytes,
                        "artifact_sha256": verification.sha256,
                        "git_commit": artifact.commit,
                    },
                },
            )
        )
        for snapshot in snapshots:
            tags = json.loads(snapshot["tags_json"] or "{}")
            if not isinstance(tags, dict):
                raise NaturalEarthError(
                    f"snapshot {snapshot['id']} tags_json must decode to an object"
                )
            source_country_tag = _snapshot_country_tag(tags)
            point = (float(snapshot["longitude"]), float(snapshot["latitude"]))
            match = match_cache.get(point)
            if match is None:
                match = assign_country(dataset, *point)
                match_cache[point] = match
            counts[match.status] += 1
            feature = match.feature
            country = feature.canonical_country if feature is not None else None
            source_country = canonicalize_source_country(source_country_tag)
            if (
                country is not None
                and country.iso_a3 is not None
                and source_country is not None
                and source_country.iso_a3 != country.iso_a3
            ):
                source_conflicts += 1
            notes = json.dumps(
                {
                    "policy": (
                        "assign only exactly one strict interior; boundary and multiple "
                        "matches remain unresolved"
                    ),
                    "match_feature_ids": match.match_feature_ids,
                    "source_country_tag": source_country_tag,
                    "source_country_conflict": bool(
                        country is not None
                        and country.iso_a3 is not None
                        and source_country is not None
                        and source_country.iso_a3 != country.iso_a3
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            assignment = AdministrativeAssignment(
                id=stable_id(
                    "administrative_assignment",
                    snapshot["entity_id"],
                    snapshot["id"],
                    evidence_id,
                    as_of,
                    recorded_at,
                    match.status.value,
                    ",".join(match.match_feature_ids),
                ),
                entity_id=snapshot["entity_id"],
                resolution_status=match.status,
                country_name=country.name if country is not None else None,
                iso_a2=country.iso_a2 if country is not None else None,
                iso_a3=country.iso_a3 if country is not None else None,
                source_admin=feature.admin if feature is not None else None,
                source_sovereignt=feature.sovereignt if feature is not None else None,
                source_type=feature.feature_type if feature is not None else None,
                source_note_adm0=feature.note_adm0 if feature is not None else None,
                source_note_brk=feature.note_brk if feature is not None else None,
                source_feature_id=feature.feature_id if feature is not None else None,
                match_feature_ids_json=json.dumps(
                    match.match_feature_ids, separators=(",", ":")
                ),
                source_country_tag=source_country_tag,
                coordinate_snapshot_id=snapshot["id"],
                boundary_evidence_id=evidence_id,
                as_of_date=as_of,
                recorded_at=recorded_at,
                method=match.method,
                confidence=match.confidence,
                notes=notes,
            )
            assignments_created += int(
                add_administrative_assignment(connection, assignment)
            )
    return EnrichmentResult(
        examined_snapshots=len(snapshots),
        assignments_created=assignments_created,
        evidence_created=evidence_created,
        assigned=counts[AdministrativeResolutionStatus.ASSIGNED],
        unmatched=counts[AdministrativeResolutionStatus.UNMATCHED],
        ambiguous=counts[AdministrativeResolutionStatus.AMBIGUOUS],
        boundary=counts[AdministrativeResolutionStatus.BOUNDARY],
        source_conflicts=source_conflicts,
    )
