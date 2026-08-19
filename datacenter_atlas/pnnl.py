"""Pinned fetch and conservative offline import for the PNNL/IM3 atlas.

The published GeoPackage is an OpenStreetMap-derived discovery source.  Its
records become source-scoped candidates only: this adapter does not turn them
into OpenStreetMap element identities, merge them with other sources, or infer
projects, lifecycle stages, capacity, operating models, or workloads.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import struct
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .adapters import ImportResult
from .models import (
    Building,
    Campus,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
)
from .repository import (
    add_building,
    add_campus,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_snapshot,
    stable_id,
    utc_now,
)


PNNL_IM3_ARTIFACT_URL = (
    "https://raw.githubusercontent.com/IMMM-SFA/datacenter-atlas/"
    "74ab37d5b9d200400a01639f9ffc3c3a8b716314/"
    "data_center_database/im3_us_data_center_locations.gpkg"
)
PNNL_IM3_DOI = "https://doi.org/10.57931/3017294"
PNNL_IM3_VERSION = "2026-02-09"
PNNL_IM3_EXPECTED_BYTES = 843_776
PNNL_IM3_SHA256 = "1c0d8c206eb2070785e594784fda90f615e6ed7fd9646d67e1a9de237b8cc9f4"
PNNL_IM3_FILENAME = "im3_us_data_center_locations.gpkg"
PNNL_IM3_LICENSE = "ODbL-1.0"
PNNL_IM3_SOURCE_FAMILY = "openstreetmap:pnnl_im3"
PNNL_IM3_ATTRIBUTION = (
    "© OpenStreetMap contributors; PNNL/IM3 Open Source Data Center Atlas "
    "(v2026.02.09)"
)
PNNL_IM3_PUBLISHER = "Pacific Northwest National Laboratory (PNNL) / IM3"
PNNL_IM3_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)
PNNL_IM3_MANIFEST = "manifest.json"


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    url: str = PNNL_IM3_ARTIFACT_URL
    doi: str = PNNL_IM3_DOI
    version: str = PNNL_IM3_VERSION
    expected_bytes: int = PNNL_IM3_EXPECTED_BYTES
    sha256: str = PNNL_IM3_SHA256
    filename: str = PNNL_IM3_FILENAME

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise ValueError("PNNL/IM3 artifact URL must use HTTPS")
        if self.expected_bytes <= 0:
            raise ValueError("PNNL/IM3 expected byte count must be positive")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("PNNL/IM3 expected SHA256 must be lowercase hexadecimal")
        if Path(self.filename).name != self.filename:
            raise ValueError("PNNL/IM3 artifact filename must be a basename")


PNNL_IM3_ARTIFACT = ArtifactSpec()


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    path: Path
    byte_count: int
    sha256: str


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, digest.hexdigest()


def verify_artifact(
    path: str | Path,
    *,
    artifact: ArtifactSpec = PNNL_IM3_ARTIFACT,
) -> ArtifactVerification:
    """Verify the raw artifact before SQLite is allowed to interpret it."""
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise ValueError(f"PNNL/IM3 artifact is not a file: {artifact_path}")
    byte_count, sha256 = _hash_file(artifact_path)
    if byte_count != artifact.expected_bytes:
        raise ValueError(
            "PNNL/IM3 artifact byte count does not match pinned artifact: "
            f"expected {artifact.expected_bytes}, got {byte_count}"
        )
    if sha256 != artifact.sha256:
        raise ValueError(
            "PNNL/IM3 artifact SHA256 does not match pinned artifact: "
            f"expected {artifact.sha256}, got {sha256}"
        )
    return ArtifactVerification(artifact_path, byte_count, sha256)


def _manifest_document(
    artifact: ArtifactSpec,
    verification: ArtifactVerification,
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": "IM3 Open Source Data Center Atlas",
        "version": artifact.version,
        "doi": artifact.doi,
        "source_family": PNNL_IM3_SOURCE_FAMILY,
        "upstream_source_family": "openstreetmap",
        "independent_corroboration": False,
        "license": PNNL_IM3_LICENSE,
        "fetched_at": fetched_at,
        "artifact": {
            "file": artifact.filename,
            "url": artifact.url,
            "bytes": verification.byte_count,
            "sha256": verification.sha256,
        },
    }


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_manifest(document: Any, artifact: ArtifactSpec) -> None:
    expected = {
        "schema_version": 1,
        "dataset": "IM3 Open Source Data Center Atlas",
        "version": artifact.version,
        "doi": artifact.doi,
        "source_family": PNNL_IM3_SOURCE_FAMILY,
        "upstream_source_family": "openstreetmap",
        "independent_corroboration": False,
        "license": PNNL_IM3_LICENSE,
    }
    if not isinstance(document, dict):
        raise ValueError("PNNL/IM3 manifest must be a JSON object")
    for key, value in expected.items():
        if document.get(key) != value:
            raise ValueError(f"PNNL/IM3 manifest has unexpected {key}")
    checkpoint = document.get("artifact")
    if not isinstance(checkpoint, dict):
        raise ValueError("PNNL/IM3 manifest is missing its artifact checkpoint")
    expected_checkpoint = {
        "file": artifact.filename,
        "url": artifact.url,
        "bytes": artifact.expected_bytes,
        "sha256": artifact.sha256,
    }
    if checkpoint != expected_checkpoint:
        raise ValueError("PNNL/IM3 manifest artifact checkpoint does not match the pin")
    _require_timestamp(document.get("fetched_at"), "PNNL/IM3 manifest fetched_at")


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


class PNNLIM3Fetcher:
    """Fetch exactly one pinned artifact and checkpoint its raw-byte digest."""

    def __init__(
        self,
        *,
        artifact: ArtifactSpec = PNNL_IM3_ARTIFACT,
        user_agent: str = PNNL_IM3_USER_AGENT,
        timeout: float = 120.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if timeout <= 0:
            raise ValueError("request timeout must be positive")
        self.artifact = artifact
        self.user_agent = user_agent
        self.timeout = timeout
        self.opener = opener

    def fetch(
        self,
        output_directory: str | Path,
        *,
        fetched_at: str | None = None,
    ) -> dict[str, Any]:
        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)
        if not output_path.is_dir():
            raise ValueError(f"PNNL/IM3 output is not a directory: {output_path}")
        artifact_path = output_path / self.artifact.filename
        manifest_path = output_path / PNNL_IM3_MANIFEST

        if artifact_path.exists():
            verification = verify_artifact(artifact_path, artifact=self.artifact)
            if manifest_path.exists():
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
                _validate_manifest(document, self.artifact)
                return document
            checkpoint_time = _require_timestamp(fetched_at or utc_now(), "fetched_at")
            document = _manifest_document(
                self.artifact, verification, checkpoint_time
            )
            _write_json_atomic(manifest_path, document)
            return document

        if manifest_path.exists():
            raise ValueError("PNNL/IM3 manifest exists but its artifact is missing")

        checkpoint_time = _require_timestamp(fetched_at or utc_now(), "fetched_at")
        request = urllib.request.Request(
            self.artifact.url,
            headers={
                "Accept": "application/geopackage+sqlite3, application/octet-stream",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        with self.opener(request, timeout=self.timeout) as response:
            downloaded = bytearray()
            digest = hashlib.sha256()
            limit = self.artifact.expected_bytes + 1
            while len(downloaded) < limit:
                chunk = response.read(min(1024 * 1024, limit - len(downloaded)))
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ValueError("PNNL/IM3 download did not return raw bytes")
                downloaded.extend(chunk)
                digest.update(chunk)
            raw = bytes(downloaded)
        if len(raw) != self.artifact.expected_bytes:
            raise ValueError(
                "downloaded PNNL/IM3 artifact byte count does not match pin: "
                f"expected {self.artifact.expected_bytes}, got {len(raw)}"
            )
        sha256 = digest.hexdigest()
        if sha256 != self.artifact.sha256:
            raise ValueError(
                "downloaded PNNL/IM3 artifact SHA256 does not match pin: "
                f"expected {self.artifact.sha256}, got {sha256}"
            )

        temporary = artifact_path.with_name(f".{artifact_path.name}.tmp")
        temporary.write_bytes(raw)
        temporary.replace(artifact_path)
        verification = verify_artifact(artifact_path, artifact=self.artifact)
        document = _manifest_document(
            self.artifact, verification, checkpoint_time
        )
        _write_json_atomic(manifest_path, document)
        return document


@dataclass(frozen=True, slots=True)
class GeoPackageGeometry:
    geometry: dict[str, Any] | None
    srs_id: int
    envelope: tuple[float, ...]
    raw_sha256: str
    empty: bool


class _WKBReader:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.offset = 0

    def _read(self, length: int) -> bytes:
        if length < 0 or self.offset + length > len(self.raw):
            raise ValueError("truncated GeoPackage WKB geometry")
        start = self.offset
        self.offset += length
        return self.raw[start : self.offset]

    def _uint32(self, endian: str) -> int:
        return struct.unpack(f"{endian}I", self._read(4))[0]

    def _double(self, endian: str) -> float:
        value = struct.unpack(f"{endian}d", self._read(8))[0]
        if not math.isfinite(value):
            raise ValueError("GeoPackage geometry coordinate must be finite")
        return value

    def _count(self, endian: str, item_size: int = 1) -> int:
        count = self._uint32(endian)
        if count > 1_000_000 or count * item_size > len(self.raw) - self.offset:
            raise ValueError("GeoPackage geometry component count is out of bounds")
        return count

    def geometry(self) -> dict[str, Any]:
        byte_order = self._read(1)[0]
        if byte_order not in (0, 1):
            raise ValueError("invalid WKB byte-order marker")
        endian = "<" if byte_order else ">"
        geometry_type = self._uint32(endian)
        if geometry_type & 0xE0000000 or geometry_type >= 1000:
            raise ValueError("only two-dimensional standard WKB is supported")

        if geometry_type == 1:
            return {"type": "Point", "coordinates": self._point(endian)}
        if geometry_type == 2:
            return {"type": "LineString", "coordinates": self._points(endian)}
        if geometry_type == 3:
            ring_count = self._count(endian, 4)
            rings = [self._ring(endian) for _ in range(ring_count)]
            return {"type": "Polygon", "coordinates": rings}
        if geometry_type in (4, 5, 6, 7):
            member_count = self._count(endian, 5)
            members = [self.geometry() for _ in range(member_count)]
            expected = {
                4: "Point",
                5: "LineString",
                6: "Polygon",
            }.get(geometry_type)
            if expected and any(member["type"] != expected for member in members):
                raise ValueError(f"WKB collection member must be {expected}")
            if geometry_type == 4:
                return {
                    "type": "MultiPoint",
                    "coordinates": [member["coordinates"] for member in members],
                }
            if geometry_type == 5:
                return {
                    "type": "MultiLineString",
                    "coordinates": [member["coordinates"] for member in members],
                }
            if geometry_type == 6:
                return {
                    "type": "MultiPolygon",
                    "coordinates": [member["coordinates"] for member in members],
                }
            return {"type": "GeometryCollection", "geometries": members}
        raise ValueError(f"unsupported WKB geometry type: {geometry_type}")

    def _point(self, endian: str) -> list[float]:
        longitude = self._double(endian)
        latitude = self._double(endian)
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("EPSG:4326 geometry coordinate is outside valid bounds")
        return [longitude, latitude]

    def _points(self, endian: str) -> list[list[float]]:
        count = self._count(endian, 16)
        return [self._point(endian) for _ in range(count)]

    def _ring(self, endian: str) -> list[list[float]]:
        points = self._points(endian)
        if len(points) < 4 or points[0] != points[-1]:
            raise ValueError("GeoPackage polygon rings must be closed with four points")
        return points


def _coordinates(geometry: dict[str, Any]) -> Iterable[list[float]]:
    if geometry["type"] == "GeometryCollection":
        for member in geometry["geometries"]:
            yield from _coordinates(member)
        return

    def visit(value: Any) -> Iterable[list[float]]:
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from visit(item)

    yield from visit(geometry["coordinates"])


def _validate_envelope(
    envelope: tuple[float, ...], geometry: dict[str, Any]
) -> None:
    if not envelope:
        return
    coordinates = list(_coordinates(geometry))
    if not coordinates:
        raise ValueError("non-empty GeoPackage envelope has no geometry coordinates")
    actual = (
        min(point[0] for point in coordinates),
        max(point[0] for point in coordinates),
        min(point[1] for point in coordinates),
        max(point[1] for point in coordinates),
    )
    if any(
        not math.isclose(recorded, decoded, rel_tol=1e-12, abs_tol=1e-12)
        for recorded, decoded in zip(envelope[:4], actual, strict=True)
    ):
        raise ValueError("GeoPackage geometry envelope does not match decoded WKB")


def parse_geopackage_geometry(
    raw: bytes,
    *,
    expected_srs_id: int = 4326,
) -> GeoPackageGeometry:
    """Decode a bounded, standard two-dimensional GeoPackage geometry blob."""
    if not isinstance(raw, bytes) or len(raw) < 8:
        raise ValueError("GeoPackage geometry must be a non-truncated byte string")
    if raw[:2] != b"GP":
        raise ValueError("invalid GeoPackage geometry magic")
    if raw[2] != 0:
        raise ValueError(f"unsupported GeoPackage geometry version: {raw[2]}")
    flags = raw[3]
    if flags & 0xC0:
        raise ValueError("GeoPackage geometry reserved flag bits must be zero")
    if flags & 0x20:
        raise ValueError("extended GeoPackage geometry is not supported")
    endian = "<" if flags & 0x01 else ">"
    envelope_code = (flags >> 1) & 0x07
    envelope_lengths = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}
    if envelope_code not in envelope_lengths:
        raise ValueError("invalid GeoPackage geometry envelope code")
    empty = bool(flags & 0x10)
    srs_id = struct.unpack(f"{endian}i", raw[4:8])[0]
    if srs_id != expected_srs_id:
        raise ValueError(
            f"GeoPackage geometry must use EPSG:{expected_srs_id}, got {srs_id}"
        )
    envelope_length = envelope_lengths[envelope_code]
    header_length = 8 + 8 * envelope_length
    if len(raw) < header_length:
        raise ValueError("truncated GeoPackage geometry envelope")
    envelope = (
        struct.unpack(f"{endian}{envelope_length}d", raw[8:header_length])
        if envelope_length
        else ()
    )
    if any(not math.isfinite(value) for value in envelope):
        raise ValueError("GeoPackage geometry envelope must be finite")
    if empty:
        return GeoPackageGeometry(
            geometry=None,
            srs_id=srs_id,
            envelope=envelope,
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            empty=True,
        )
    reader = _WKBReader(raw[header_length:])
    geometry = reader.geometry()
    if reader.offset != len(reader.raw):
        raise ValueError("GeoPackage geometry has trailing WKB bytes")
    _validate_envelope(envelope, geometry)
    return GeoPackageGeometry(
        geometry=geometry,
        srs_id=srs_id,
        envelope=envelope,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        empty=False,
    )


@dataclass(frozen=True, slots=True)
class PNNLIM3Feature:
    layer: str
    source_id: str
    name: str | None
    operator: str | None
    reference: str | None
    square_feet: float | None
    longitude: float
    latitude: float
    source_type: str
    source_rows: tuple[dict[str, Any], ...]
    geometry: GeoPackageGeometry
    content_hash: str


_LAYER_GEOMETRY_TYPES = {
    "point": "POINT",
    "building": "POLYGON",
    "campus": "MULTIPOLYGON",
}
_LAYER_ENTITY_KINDS = {
    "point": "facility",
    "building": "building",
    "campus": "campus",
}
_REQUIRED_SOURCE_COLUMNS = {
    "fid",
    "geom",
    "id",
    "state",
    "state_abb",
    "state_id",
    "county",
    "county_id",
    "operator",
    "ref",
    "name",
    "sqft",
    "lon",
    "lat",
    "type",
}
_COUNTY_ROW_FIELDS = ("fid", "state", "state_abb", "state_id", "county", "county_id")
_SHARED_FIELDS = ("id", "operator", "ref", "name", "sqft", "lon", "lat", "type")


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri_path = urllib.parse.quote(str(path.resolve()), safe="/")
    connection = sqlite3.connect(
        f"file:{uri_path}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _validate_geopackage_schema(connection: sqlite3.Connection) -> None:
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    if application_id != 0x47504B47:
        raise ValueError("PNNL/IM3 input is not a GeoPackage SQLite database")
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"PNNL/IM3 GeoPackage integrity check failed: {integrity}")

    contents = {
        row["table_name"]: (row["data_type"], row["srs_id"])
        for row in connection.execute(
            "SELECT table_name, data_type, srs_id FROM gpkg_contents"
        )
        if row["table_name"] in _LAYER_GEOMETRY_TYPES
    }
    if contents != {layer: ("features", 4326) for layer in _LAYER_GEOMETRY_TYPES}:
        raise ValueError("PNNL/IM3 GeoPackage must contain all three EPSG:4326 layers")

    geometry_columns = {
        row["table_name"]: (
            row["column_name"],
            row["geometry_type_name"],
            row["srs_id"],
            row["z"],
            row["m"],
        )
        for row in connection.execute(
            "SELECT table_name, column_name, geometry_type_name, srs_id, z, m "
            "FROM gpkg_geometry_columns"
        )
        if row["table_name"] in _LAYER_GEOMETRY_TYPES
    }
    expected_geometry_columns = {
        layer: ("geom", geometry_type, 4326, 0, 0)
        for layer, geometry_type in _LAYER_GEOMETRY_TYPES.items()
    }
    if geometry_columns != expected_geometry_columns:
        raise ValueError("PNNL/IM3 GeoPackage geometry columns do not match the pin")

    for layer in _LAYER_GEOMETRY_TYPES:
        columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({layer})")
        }
        missing = _REQUIRED_SOURCE_COLUMNS - columns
        if missing:
            raise ValueError(
                f"PNNL/IM3 {layer} layer is missing columns: {', '.join(sorted(missing))}"
            )


def _require_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"PNNL/IM3 {field} must be null or non-empty text")
    return value


def _require_text(value: Any, field: str) -> str:
    result = _require_optional_text(value, field)
    if result is None:
        raise ValueError(f"PNNL/IM3 {field} must be non-empty text")
    return result


def _require_coordinate(value: Any, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"PNNL/IM3 {field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"PNNL/IM3 {field} is outside valid bounds")
    return result


def _source_row(row: sqlite3.Row) -> dict[str, Any]:
    return {field: row[field] for field in _COUNTY_ROW_FIELDS + _SHARED_FIELDS}


def _group_layer_rows(
    connection: sqlite3.Connection,
    layer: str,
) -> tuple[list[PNNLIM3Feature], int]:
    rows = list(connection.execute(f"SELECT * FROM {layer} ORDER BY id, fid"))
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        source_id = _require_text(row["id"], f"{layer}.id")
        groups.setdefault(source_id, []).append(row)

    features: list[PNNLIM3Feature] = []
    duplicate_rows = 0
    expected_geometry_type = {
        "point": "Point",
        "building": "Polygon",
        "campus": "MultiPolygon",
    }[layer]
    for source_id, group in groups.items():
        first = group[0]
        duplicate_rows += len(group) - 1
        for row in group[1:]:
            for field in _SHARED_FIELDS:
                if row[field] != first[field]:
                    raise ValueError(
                        f"PNNL/IM3 duplicate county rows disagree on {layer}/{source_id}.{field}"
                    )
            if bytes(row["geom"]) != bytes(first["geom"]):
                raise ValueError(
                    f"PNNL/IM3 duplicate county rows disagree on {layer}/{source_id}.geom"
                )

        source_type = _require_text(first["type"], f"{layer}/{source_id}.type")
        if source_type != layer:
            raise ValueError(
                f"PNNL/IM3 {layer}/{source_id} source type must equal its layer"
            )
        geometry_blob = first["geom"]
        if not isinstance(geometry_blob, bytes):
            raise ValueError(f"PNNL/IM3 {layer}/{source_id}.geom must be bytes")
        geometry = parse_geopackage_geometry(geometry_blob)
        if geometry.geometry is None or geometry.geometry["type"] != expected_geometry_type:
            raise ValueError(
                f"PNNL/IM3 {layer}/{source_id} geometry must be {expected_geometry_type}"
            )

        longitude = _require_coordinate(
            first["lon"], f"{layer}/{source_id}.lon", -180, 180
        )
        latitude = _require_coordinate(
            first["lat"], f"{layer}/{source_id}.lat", -90, 90
        )
        source_rows = tuple(_source_row(row) for row in group)
        canonical = {
            "layer": layer,
            "source_id": source_id,
            "source_rows": source_rows,
            "geometry_sha256": geometry.raw_sha256,
        }
        content_hash = hashlib.sha256(
            json.dumps(
                canonical,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        square_feet = first["sqft"]
        if square_feet is not None:
            if (
                isinstance(square_feet, bool)
                or not isinstance(square_feet, (int, float))
                or not math.isfinite(float(square_feet))
                or float(square_feet) < 0
            ):
                raise ValueError(f"PNNL/IM3 {layer}/{source_id}.sqft is invalid")
            square_feet = float(square_feet)
        features.append(
            PNNLIM3Feature(
                layer=layer,
                source_id=source_id,
                name=_require_optional_text(first["name"], f"{layer}/{source_id}.name"),
                operator=_require_optional_text(
                    first["operator"], f"{layer}/{source_id}.operator"
                ),
                reference=_require_optional_text(
                    first["ref"], f"{layer}/{source_id}.ref"
                ),
                square_feet=square_feet,
                longitude=longitude,
                latitude=latitude,
                source_type=source_type,
                source_rows=source_rows,
                geometry=geometry,
                content_hash=content_hash,
            )
        )
    return features, duplicate_rows


def read_pnnl_im3_features(path: str | Path) -> tuple[list[PNNLIM3Feature], int]:
    """Read and validate already-verified GeoPackage feature rows offline."""
    source = _readonly_connection(Path(path))
    try:
        _validate_geopackage_schema(source)
        features: list[PNNLIM3Feature] = []
        duplicate_rows = 0
        for layer in _LAYER_GEOMETRY_TYPES:
            layer_features, layer_duplicates = _group_layer_rows(source, layer)
            features.extend(layer_features)
            duplicate_rows += layer_duplicates
        return features, duplicate_rows
    finally:
        source.close()


def _resolve_input(path: str | Path, artifact: ArtifactSpec) -> Path:
    input_path = Path(path)
    if input_path.is_dir():
        manifest_path = input_path / PNNL_IM3_MANIFEST
        if not manifest_path.is_file():
            raise ValueError("PNNL/IM3 bundle directory is missing manifest.json")
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_manifest(document, artifact)
        return input_path / artifact.filename
    return input_path


def _feature_metadata(
    feature: PNNLIM3Feature,
    verification: ArtifactVerification,
    artifact: ArtifactSpec,
) -> dict[str, Any]:
    return {
        "dataset_version": artifact.version,
        "dataset_doi": artifact.doi,
        "artifact_url": artifact.url,
        "artifact_bytes": verification.byte_count,
        "artifact_sha256": verification.sha256,
        "input_sha256": verification.sha256,
        "provenance": {
            "artifact_url": artifact.url,
            "artifact_bytes": verification.byte_count,
            "artifact_sha256": verification.sha256,
        },
        "layer": feature.layer,
        "source_id": feature.source_id,
        "source_rows": feature.source_rows,
        "source_row_count": len(feature.source_rows),
        "upstream_source_family": "openstreetmap",
        "independent_corroboration": False,
        "duplicate_county_rows_are_independent_evidence": False,
        "geometry": {
            "format": "GeoPackageBinary/WKB",
            "srs_id": feature.geometry.srs_id,
            "envelope": feature.geometry.envelope,
            "raw_sha256": feature.geometry.raw_sha256,
        },
    }


def _feature_tags(feature: PNNLIM3Feature) -> dict[str, str]:
    first = feature.source_rows[0]
    county_rows = [
        {
            key: row[key]
            for key in ("fid", "state", "state_abb", "state_id", "county", "county_id")
        }
        for row in feature.source_rows
    ]
    tags = {
        "country": "United States",
        "addr:country": "US",
        "addr:state": str(first["state_abb"]),
        "pnnl_im3:dataset_version": PNNL_IM3_VERSION,
        "pnnl_im3:layer": feature.layer,
        "pnnl_im3:source_id": feature.source_id,
        "pnnl_im3:state": str(first["state"]),
        "pnnl_im3:state_abb": str(first["state_abb"]),
        "pnnl_im3:state_id": str(first["state_id"]),
        "pnnl_im3:county_rows": json.dumps(
            county_rows, sort_keys=True, separators=(",", ":")
        ),
        "pnnl_im3:source_type": feature.source_type,
    }
    if feature.operator is not None:
        tags["pnnl_im3:operator"] = feature.operator
    if feature.reference is not None:
        tags["pnnl_im3:ref"] = feature.reference
    if feature.square_feet is not None:
        tags["pnnl_im3:sqft"] = str(feature.square_feet)
    return tags


class PNNLIM3GeoPackageAdapter:
    """Import the pinned atlas as unmerged, UNKNOWN-lifecycle candidates."""

    source_name = "pnnl_im3"

    def __init__(self, *, artifact: ArtifactSpec = PNNL_IM3_ARTIFACT) -> None:
        self.artifact = artifact

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        _require_timestamp(retrieved_at, "retrieved_at")
        input_path = _resolve_input(path, self.artifact)
        verification = verify_artifact(input_path, artifact=self.artifact)
        features, duplicate_rows = read_pnnl_im3_features(input_path)
        entities_created = 0
        evidence_created = 0
        warnings = [
            (
                f"grouped {len(feature.source_rows)} county rows for source feature "
                f"{feature.layer}/{feature.source_id}; duplicate source rows are not "
                "independent corroboration"
            )
            for feature in features
            if len(feature.source_rows) > 1
        ]

        with connection:
            for feature in features:
                stable_key = (
                    f"pnnl_im3:{self.artifact.version}:"
                    f"{feature.layer}/{feature.source_id}"
                )
                evidence_id = stable_id(
                    "evidence",
                    "pnnl_im3",
                    self.artifact.version,
                    feature.layer,
                    feature.source_id,
                    retrieved_at,
                    feature.content_hash,
                )
                title_name = feature.name or feature.operator
                title = f"PNNL/IM3 {feature.layer} {feature.source_id}"
                if title_name:
                    title = f"{title}: {title_name}"
                evidence_created += int(
                    add_evidence(
                        connection,
                        Evidence(
                            id=evidence_id,
                            kind=EvidenceKind.THIRD_PARTY_DATASET,
                            title=title,
                            source_url=self.artifact.doi,
                            publisher=PNNL_IM3_PUBLISHER,
                            source_family=PNNL_IM3_SOURCE_FAMILY,
                            license=PNNL_IM3_LICENSE,
                            attribution=PNNL_IM3_ATTRIBUTION,
                            published_at=self.artifact.version,
                            retrieved_at=retrieved_at,
                            excerpt=(
                                f"Source-scoped {feature.layer} candidate; "
                                f"{len(feature.source_rows)} county row(s) grouped."
                            ),
                        ),
                        content_hash=feature.content_hash,
                        metadata=_feature_metadata(feature, verification, self.artifact),
                    )
                )

                display_name = feature.name or feature.operator or title
                if feature.layer == "campus":
                    entity_id = stable_id("entity", stable_key, "campus")
                    entities_created += int(
                        add_campus(
                            connection,
                            Campus(entity_id, stable_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )
                elif feature.layer == "point":
                    entity_id = stable_id("entity", stable_key, "facility")
                    entities_created += int(
                        add_facility(
                            connection,
                            Facility(entity_id, stable_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )
                else:
                    container_key = f"{stable_key}:structural-facility-container"
                    facility_id = stable_id("entity", container_key, "facility")
                    entities_created += int(
                        add_facility(
                            connection,
                            Facility(facility_id, container_key, evidence_id),
                            created_at=retrieved_at,
                        )
                    )
                    container_tags = _feature_tags(feature)
                    container_tags["pnnl_im3:structural_role"] = "building_parent"
                    add_snapshot(
                        connection,
                        snapshot_id=stable_id("snapshot", facility_id, evidence_id),
                        entity_id=facility_id,
                        name=f"{display_name} facility container",
                        latitude=feature.latitude,
                        longitude=feature.longitude,
                        geometry=feature.geometry.geometry,
                        tags=container_tags,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.version,
                        recorded_at=retrieved_at,
                        method="pnnl_im3_structural_facility_container",
                        confidence=0.80,
                    )
                    entity_id = stable_id("entity", stable_key, "building")
                    entities_created += int(
                        add_building(
                            connection,
                            Building(entity_id, stable_key, evidence_id, facility_id),
                            created_at=retrieved_at,
                        )
                    )

                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id),
                    entity_id=entity_id,
                    name=display_name,
                    latitude=feature.latitude,
                    longitude=feature.longitude,
                    geometry=feature.geometry.geometry,
                    tags=_feature_tags(feature),
                    evidence_id=evidence_id,
                    as_of_date=self.artifact.version,
                    recorded_at=retrieved_at,
                    method="pnnl_im3_source_scoped_candidate",
                    confidence=0.80,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", entity_id, evidence_id, "unknown"),
                        entity_id=entity_id,
                        status=LifecycleStatus.UNKNOWN,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.version,
                        recorded_at=retrieved_at,
                        method="pnnl_im3_does_not_establish_lifecycle",
                        confidence=1.0,
                    ),
                )

        return ImportResult(
            source=self.source_name,
            examined_elements=len(features) + duplicate_rows,
            imported_elements=len(features),
            skipped_elements=duplicate_rows,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )


# Short aliases keep integration readable without weakening the explicit class name.
PNNLIM3Adapter = PNNLIM3GeoPackageAdapter
PNNLAdapter = PNNLIM3GeoPackageAdapter
