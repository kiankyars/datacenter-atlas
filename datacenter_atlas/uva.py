"""Pinned UVA Dataverse v2.0 fetch and conservative offline adapter.

The source is a modeled Virginia facility dataset.  It supports source-scoped
facility, geometry, power, energy, and coarse operating-model observations;
it does not establish current lifecycle, a construction project, measured
energy, or workload.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable, Mapping
import urllib.request

from .adapters import ImportResult
from .models import (
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
    OperatingModel,
)
from .repository import (
    add_capacity,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_operating_model,
    add_snapshot,
    stable_id,
    utc_now,
)


UVA_DATASET_NAME = (
    "AI-Enabled Synthesis of Open Source Multi-Attribute, Temporal Dataset "
    "Related to Data Centers in Virginia"
)
UVA_DOI = "https://doi.org/10.18130/V3/AYLB4S"
UVA_PERSISTENT_ID = "doi:10.18130/V3/AYLB4S"
UVA_VERSION = "2.0"
UVA_RELEASE_DATE = "2026-05-18"
UVA_RELEASE_TIME = "2026-05-18T12:12:38Z"
UVA_METADATA_URL = (
    "https://dataverse.lib.virginia.edu/api/datasets/:persistentId/versions/2.0"
    "?persistentId=doi%3A10.18130%2FV3%2FAYLB4S"
)
UVA_DATAFILE_ID = 120633
UVA_DATA_URL = (
    "https://dataverse.lib.virginia.edu/api/access/datafile/120633?format=original"
)
UVA_LOCAL_FILENAME = "ModelOutput.tab"
UVA_ORIGINAL_FILENAME = "ModelOutput.csv"
UVA_METADATA_FILENAME = "dataverse-dataset-metadata.json"
UVA_MANIFEST_FILENAME = "manifest.json"
UVA_EXPECTED_BYTES = 1_273_747
UVA_MD5 = "947213715a464b3ee9538af4da70cc2e"
UVA_SHA256 = "e5caed9572af6dec15dd525de105301baae2c1fbbca31c552b2a33c28befd69c"
UVA_EXPECTED_ROWS = 382
UVA_EXPECTED_COLUMNS = 161
UVA_DATASET_ID = 120631
UVA_DATASET_VERSION_ID = 3155
UVA_LICENSE = "CC0-1.0"
UVA_SOURCE_FAMILY = "uva_dataverse_dc_sense"
UVA_PUBLISHER = "University of Virginia Dataverse"
UVA_ATTRIBUTION = (
    "Ghate, Chen, Kishore, and Marathe, UVA DC-SENSE Virginia data-centre "
    "dataset v2.0"
)
UVA_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)

# A conservative envelope enclosing Virginia.  Every facility centre and
# every source polygon vertex must remain inside it.
VIRGINIA_LATITUDE_BOUNDS = (36.5, 39.5)
VIRGINIA_LONGITUDE_BOUNDS = (-83.7, -75.0)

BASE_COLUMNS = (
    "lat",
    "lon",
    "building_footprint_polygon",
    "building_footprint_area",
    "number_of_floors",
    "total_building_area",
    "construction_year",
    "Predicted_IT_Whitespace_Area_mean",
    "Predicted_IT_Whitespace_Area_std",
    "Predicted_Built-out_Power_mean",
    "Predicted_Built-out_Power_std",
    "Predicted_Facility_Type",
)
PROFILE_COLUMN_PREFIXES = (
    "IT_power_mean",
    "IT_power_std",
    "Typical_Day_Facility_Power_mean",
    "Typical_Day_Facility_Power_std",
    "Peak_Temperature_Day_Facility_Power_mean",
    "Peak_Temperature_Day_Facility_Power_std",
)
DISTANCE_COLUMNS = (
    "distance_to_substation",
    "distance_to_highway",
    "distance_to_residential",
    "distance_to_water",
    "distance_to_transmission",
)
EXPECTED_COLUMNS = (
    *BASE_COLUMNS,
    *(
        f"{prefix}_AtHour_{hour:02d}"
        for prefix in PROFILE_COLUMN_PREFIXES
        for hour in range(24)
    ),
    *DISTANCE_COLUMNS,
)
if len(EXPECTED_COLUMNS) != UVA_EXPECTED_COLUMNS:
    raise RuntimeError("UVA schema constant does not contain exactly 161 columns")

FACILITY_TYPES = frozenset(
    {"Hyperscale", "Large Campus", "Colocation", "Enterprise"}
)
OPERATING_MODEL_MAP: dict[str, tuple[OperatingModel, float]] = {
    "Hyperscale": (OperatingModel.HYPERSCALER, 0.55),
    "Colocation": (OperatingModel.COLOCATION, 0.60),
    "Enterprise": (OperatingModel.ENTERPRISE_PRIVATE, 0.50),
}


@dataclass(frozen=True, slots=True)
class UVAArtifactSpec:
    metadata_url: str = UVA_METADATA_URL
    data_url: str = UVA_DATA_URL
    doi: str = UVA_DOI
    persistent_id: str = UVA_PERSISTENT_ID
    version: str = UVA_VERSION
    release_date: str = UVA_RELEASE_DATE
    release_time: str = UVA_RELEASE_TIME
    dataset_id: int = UVA_DATASET_ID
    dataset_version_id: int = UVA_DATASET_VERSION_ID
    datafile_id: int = UVA_DATAFILE_ID
    local_filename: str = UVA_LOCAL_FILENAME
    original_filename: str = UVA_ORIGINAL_FILENAME
    metadata_filename: str = UVA_METADATA_FILENAME
    expected_bytes: int = UVA_EXPECTED_BYTES
    md5: str = UVA_MD5
    sha256: str = UVA_SHA256
    expected_rows: int = UVA_EXPECTED_ROWS

    def __post_init__(self) -> None:
        for field in ("metadata_url", "data_url", "doi"):
            if not getattr(self, field).startswith("https://"):
                raise ValueError(f"UVA {field} must use HTTPS")
        if self.expected_bytes <= 0 or self.expected_rows <= 0:
            raise ValueError("UVA expected bytes and rows must be positive")
        if not re.fullmatch(r"[0-9a-f]{32}", self.md5):
            raise ValueError("UVA MD5 pin must be lowercase hexadecimal")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("UVA SHA256 pin must be lowercase hexadecimal")
        for field in ("local_filename", "original_filename", "metadata_filename"):
            value = getattr(self, field)
            if not value or Path(value).name != value:
                raise ValueError(f"UVA {field} must be a basename")


UVA_ARTIFACT = UVAArtifactSpec()


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    path: Path
    byte_count: int
    md5: str
    sha256: str


@dataclass(frozen=True, slots=True)
class MetadataVerification:
    path: Path
    byte_count: int
    sha256: str
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Profile24:
    mean_mw: tuple[float, ...]
    std_mw: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.mean_mw) != 24 or len(self.std_mw) != 24:
            raise ValueError("UVA power profiles must contain exactly 24 mean/std values")

    def metadata(self) -> dict[str, Any]:
        return {
            "hours_local_model_index": list(range(24)),
            "mean_mw": list(self.mean_mw),
            "reported_std_mw": list(self.std_mw),
            "uncertainty_note": "reported model std; not a calibrated confidence interval",
        }


@dataclass(frozen=True, slots=True)
class UVAFacilityRecord:
    row_number: int
    latitude: float
    longitude: float
    coordinate_key: str
    geometry: dict[str, Any]
    building_footprint_area: float
    number_of_floors: int
    total_building_area: float
    construction_year: int
    whitespace_area_mean: float
    whitespace_area_std: float
    critical_it_mw_mean: float
    critical_it_mw_std: float
    facility_type: str
    it_power: Profile24
    typical_day_facility_power: Profile24
    peak_temperature_day_facility_power: Profile24
    distances: dict[str, float]
    content_hash: str

    @property
    def critical_it_interval(self) -> tuple[float, float, float]:
        return (
            max(0.0, self.critical_it_mw_mean - self.critical_it_mw_std),
            self.critical_it_mw_mean,
            self.critical_it_mw_mean + self.critical_it_mw_std,
        )

    @property
    def annual_energy_interval(self) -> tuple[float, float, float]:
        means = self.typical_day_facility_power.mean_mw
        stds = self.typical_day_facility_power.std_mw
        return (
            sum(max(0.0, mean - std) for mean, std in zip(means, stds, strict=True))
            * 365.0,
            sum(means) * 365.0,
            sum(mean + std for mean, std in zip(means, stds, strict=True)) * 365.0,
        )


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


def _require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"refusing UVA {label} symlink: {path}")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as error:
        raise ValueError(f"UVA {label} is missing: {path}") from error
    if not stat.S_ISREG(mode):
        raise ValueError(f"UVA {label} is not a regular file: {path}")


def _hash_file(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            byte_count += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return byte_count, md5.hexdigest(), sha256.hexdigest()


def verify_artifact(
    path: str | Path,
    *,
    artifact: UVAArtifactSpec = UVA_ARTIFACT,
) -> ArtifactVerification:
    artifact_path = Path(path)
    _require_regular_file(artifact_path, "artifact")
    byte_count, md5, sha256 = _hash_file(artifact_path)
    if byte_count != artifact.expected_bytes:
        raise ValueError(
            f"UVA artifact byte count mismatch: expected {artifact.expected_bytes}, "
            f"got {byte_count}"
        )
    if not hmac.compare_digest(md5, artifact.md5):
        raise ValueError(f"UVA artifact MD5 mismatch: expected {artifact.md5}, got {md5}")
    if not hmac.compare_digest(sha256, artifact.sha256):
        raise ValueError(
            f"UVA artifact SHA256 mismatch: expected {artifact.sha256}, got {sha256}"
        )
    return ArtifactVerification(artifact_path, byte_count, md5, sha256)


def _metadata_version(document: Mapping[str, Any]) -> Mapping[str, Any]:
    if document.get("status") != "OK" or not isinstance(document.get("data"), Mapping):
        raise ValueError("UVA Dataverse metadata must be an OK response object")
    data = document["data"]
    if "latestVersion" in data:
        raise ValueError(
            "UVA metadata is a moving dataset-level response, not the pinned v2.0 endpoint"
        )
    return data


def validate_metadata_document(
    document: Mapping[str, Any],
    *,
    artifact: UVAArtifactSpec = UVA_ARTIFACT,
) -> None:
    version = _metadata_version(document)
    expected_version = {
        "id": artifact.dataset_version_id,
        "datasetId": artifact.dataset_id,
        "datasetPersistentId": artifact.persistent_id,
        "versionNumber": 2,
        "versionMinorNumber": 0,
        "versionState": "RELEASED",
        "releaseTime": artifact.release_time,
    }
    for field, expected in expected_version.items():
        if version.get(field) != expected:
            raise ValueError(f"UVA metadata {field} does not match pinned v2.0")
    license_document = version.get("license")
    if not isinstance(license_document, Mapping) or license_document.get(
        "rightsIdentifier"
    ) != UVA_LICENSE:
        raise ValueError("UVA metadata license is not CC0-1.0")

    citation = version.get("metadataBlocks")
    try:
        citation_fields = citation["citation"]["fields"]
    except (KeyError, TypeError) as error:
        raise ValueError("UVA metadata is missing citation fields") from error
    titles = [
        field.get("value")
        for field in citation_fields
        if isinstance(field, Mapping) and field.get("typeName") == "title"
    ]
    if titles != [UVA_DATASET_NAME]:
        raise ValueError("UVA metadata title does not match the pinned dataset")

    files = version.get("files")
    if not isinstance(files, list):
        raise ValueError("UVA metadata files must be a list")
    matches = [
        item
        for item in files
        if isinstance(item, Mapping)
        and isinstance(item.get("dataFile"), Mapping)
        and item["dataFile"].get("id") == artifact.datafile_id
    ]
    if len(matches) != 1:
        raise ValueError("UVA metadata must contain exactly one pinned datafile")
    item = matches[0]
    datafile = item["dataFile"]
    expected_file = {
        "datasetVersionId": artifact.dataset_version_id,
        "originalFileName": artifact.original_filename,
        "originalFileSize": artifact.expected_bytes,
        "md5": artifact.md5,
        "tabularData": True,
    }
    for field, expected in expected_file.items():
        actual = item.get(field) if field == "datasetVersionId" else datafile.get(field)
        if actual != expected:
            raise ValueError(f"UVA metadata datafile.{field} does not match the pin")
    checksum = datafile.get("checksum")
    if not isinstance(checksum, Mapping) or checksum != {
        "type": "MD5",
        "value": artifact.md5,
    }:
        raise ValueError("UVA metadata datafile checksum does not match the pin")


def verify_metadata(
    path: str | Path,
    *,
    artifact: UVAArtifactSpec = UVA_ARTIFACT,
) -> MetadataVerification:
    metadata_path = Path(path)
    _require_regular_file(metadata_path, "version metadata")
    raw = metadata_path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("UVA version metadata is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise ValueError("UVA version metadata must be a JSON object")
    validate_metadata_document(document, artifact=artifact)
    return MetadataVerification(
        metadata_path,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        document,
    )


def _manifest_document(
    artifact: UVAArtifactSpec,
    source: ArtifactVerification,
    metadata: MetadataVerification,
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": UVA_DATASET_NAME,
        "version": artifact.version,
        "release_date": artifact.release_date,
        "doi": artifact.doi,
        "source_family": UVA_SOURCE_FAMILY,
        "independent_corroboration": True,
        "license": UVA_LICENSE,
        "fetched_at": fetched_at,
        "version_metadata": {
            "file": artifact.metadata_filename,
            "url": artifact.metadata_url,
            "bytes": metadata.byte_count,
            "sha256": metadata.sha256,
        },
        "artifact": {
            "file": artifact.local_filename,
            "original_filename": artifact.original_filename,
            "url": artifact.data_url,
            "datafile_id": artifact.datafile_id,
            "bytes": source.byte_count,
            "md5": source.md5,
            "sha256": source.sha256,
            "rows": artifact.expected_rows,
            "columns": UVA_EXPECTED_COLUMNS,
        },
    }


def _validate_manifest(
    document: Any,
    artifact: UVAArtifactSpec,
    source: ArtifactVerification,
    metadata: MetadataVerification,
) -> None:
    if not isinstance(document, dict):
        raise ValueError("UVA fetch manifest must be a JSON object")
    _require_timestamp(document.get("fetched_at"), "UVA manifest fetched_at")
    expected = _manifest_document(
        artifact, source, metadata, document["fetched_at"]
    )
    if document != expected:
        raise ValueError("UVA fetch manifest does not match the verified pinned bundle")


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"refusing to replace UVA symlink: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"refusing to overwrite UVA temporary file: {temporary}")
    try:
        with temporary.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    except Exception:
        if temporary.is_file() and not temporary.is_symlink():
            temporary.unlink()
        raise


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_response(response: Any, maximum_bytes: int, label: str) -> bytes:
    payload = bytearray()
    while len(payload) <= maximum_bytes:
        chunk = response.read(min(1024 * 1024, maximum_bytes + 1 - len(payload)))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise ValueError(f"UVA {label} response did not return raw bytes")
        payload.extend(chunk)
    if len(payload) > maximum_bytes:
        raise ValueError(f"UVA {label} response exceeded its byte limit")
    return bytes(payload)


class UVADataFetcher:
    """Fetch exactly the pinned v2.0 metadata and original-format CSV bytes."""

    def __init__(
        self,
        *,
        artifact: UVAArtifactSpec = UVA_ARTIFACT,
        user_agent: str = UVA_USER_AGENT,
        timeout: float = 120.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if timeout <= 0:
            raise ValueError("UVA request timeout must be positive")
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
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        if output.is_symlink() or not output.is_dir():
            raise ValueError("UVA output must be a non-symlink directory")
        source_path = output / self.artifact.local_filename
        metadata_path = output / self.artifact.metadata_filename
        manifest_path = output / UVA_MANIFEST_FILENAME
        source_exists = source_path.exists() or source_path.is_symlink()
        metadata_exists = metadata_path.exists() or metadata_path.is_symlink()
        manifest_exists = manifest_path.exists() or manifest_path.is_symlink()
        if source_exists != metadata_exists:
            raise ValueError("UVA bundle is incomplete: artifact and metadata must coexist")
        if manifest_exists and not source_exists:
            raise ValueError("UVA manifest exists but its artifact and metadata are missing")

        if source_exists:
            source = verify_artifact(source_path, artifact=self.artifact)
            metadata = verify_metadata(metadata_path, artifact=self.artifact)
            if manifest_exists:
                if manifest_path.is_symlink():
                    raise ValueError("refusing UVA manifest symlink")
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
                _validate_manifest(document, self.artifact, source, metadata)
                return document
            checkpoint_time = _require_timestamp(fetched_at or utc_now(), "fetched_at")
            document = _manifest_document(
                self.artifact, source, metadata, checkpoint_time
            )
            _atomic_write(manifest_path, _json_bytes(document))
            return document

        checkpoint_time = _require_timestamp(fetched_at or utc_now(), "fetched_at")
        metadata_request = urllib.request.Request(
            self.artifact.metadata_url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        with self.opener(metadata_request, timeout=self.timeout) as response:
            metadata_raw = _read_response(response, 5_000_000, "metadata")
        try:
            metadata_document = json.loads(metadata_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("downloaded UVA metadata is not valid JSON") from error
        if not isinstance(metadata_document, dict):
            raise ValueError("downloaded UVA metadata must be an object")
        validate_metadata_document(metadata_document, artifact=self.artifact)

        data_request = urllib.request.Request(
            self.artifact.data_url,
            headers={
                "Accept": "text/csv, application/octet-stream",
                "Accept-Encoding": "identity",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        with self.opener(data_request, timeout=self.timeout) as response:
            source_raw = _read_response(
                response, self.artifact.expected_bytes, "artifact"
            )
        if len(source_raw) != self.artifact.expected_bytes:
            raise ValueError("downloaded UVA artifact byte count does not match the pin")
        if not hmac.compare_digest(hashlib.md5(source_raw).hexdigest(), self.artifact.md5):
            raise ValueError("downloaded UVA artifact MD5 does not match the pin")
        if not hmac.compare_digest(
            hashlib.sha256(source_raw).hexdigest(), self.artifact.sha256
        ):
            raise ValueError("downloaded UVA artifact SHA256 does not match the pin")

        published: list[Path] = []
        try:
            _atomic_write(metadata_path, metadata_raw)
            published.append(metadata_path)
            _atomic_write(source_path, source_raw)
            published.append(source_path)
            source = verify_artifact(source_path, artifact=self.artifact)
            metadata = verify_metadata(metadata_path, artifact=self.artifact)
            document = _manifest_document(
                self.artifact, source, metadata, checkpoint_time
            )
            _atomic_write(manifest_path, _json_bytes(document))
            return document
        except Exception:
            if not manifest_path.exists():
                for path in reversed(published):
                    if path.is_file() and not path.is_symlink():
                        path.unlink()
            raise


def _parse_float(raw: str, field: str, *, nonnegative: bool = True) -> float:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ValueError(f"UVA {field} must be a non-empty canonical numeric string")
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"UVA {field} must be numeric") from error
    if not math.isfinite(value):
        raise ValueError(f"UVA {field} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"UVA {field} must be non-negative")
    return value


def _parse_integer(raw: str, field: str, *, minimum: int, maximum: int) -> int:
    if not re.fullmatch(r"[0-9]+", raw or ""):
        raise ValueError(f"UVA {field} must be an integer")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"UVA {field} is outside its allowed range")
    return value


def _parse_coordinate(
    raw: str,
    field: str,
    bounds: tuple[float, float],
) -> float:
    value = _parse_float(raw, field, nonnegative=False)
    if not bounds[0] <= value <= bounds[1]:
        raise ValueError(f"UVA {field} is outside the Virginia envelope")
    return value


def _parse_polygon(raw: str, row_number: int) -> dict[str, Any]:
    try:
        source_points = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"UVA row {row_number} polygon is not valid JSON") from error
    if not isinstance(source_points, list) or len(source_points) < 3:
        raise ValueError(f"UVA row {row_number} polygon needs at least three vertices")
    ring: list[list[float]] = []
    for index, point in enumerate(source_points):
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(isinstance(value, bool) for value in point)
        ):
            raise ValueError(
                f"UVA row {row_number} polygon vertex {index} must be [lat, lon]"
            )
        try:
            latitude, longitude = (float(value) for value in point)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"UVA row {row_number} polygon vertex {index} must be numeric"
            ) from error
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError(f"UVA row {row_number} polygon vertices must be finite")
        if not VIRGINIA_LATITUDE_BOUNDS[0] <= latitude <= VIRGINIA_LATITUDE_BOUNDS[1]:
            raise ValueError(f"UVA row {row_number} polygon latitude is outside Virginia")
        if not VIRGINIA_LONGITUDE_BOUNDS[0] <= longitude <= VIRGINIA_LONGITUDE_BOUNDS[1]:
            raise ValueError(f"UVA row {row_number} polygon longitude is outside Virginia")
        ring.append([longitude, latitude])
    if len({tuple(point) for point in ring}) < 3:
        raise ValueError(f"UVA row {row_number} polygon has fewer than three unique vertices")
    if ring[0] != ring[-1]:
        ring.append(ring[0].copy())
    doubled_area = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(ring[:-1], ring[1:], strict=True)
    )
    if doubled_area == 0:
        raise ValueError(f"UVA row {row_number} polygon has zero area")
    return {"type": "Polygon", "coordinates": [ring]}


def _profile(row: Mapping[str, str], mean_prefix: str, std_prefix: str) -> Profile24:
    means = tuple(
        _parse_float(row[f"{mean_prefix}_AtHour_{hour:02d}"], f"{mean_prefix}[{hour}]")
        for hour in range(24)
    )
    stds = tuple(
        _parse_float(row[f"{std_prefix}_AtHour_{hour:02d}"], f"{std_prefix}[{hour}]")
        for hour in range(24)
    )
    return Profile24(means, stds)


def _canonical_row_hash(row: Mapping[str, str]) -> str:
    payload = {field: row[field] for field in EXPECTED_COLUMNS}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_records(
    path: Path,
    artifact: UVAArtifactSpec,
) -> list[UVAFacilityRecord]:
    try:
        source = path.open("r", encoding="utf-8", newline="")
    except UnicodeError as error:
        raise ValueError("UVA artifact must be UTF-8 CSV") from error
    with source:
        reader = csv.reader(source)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError("UVA artifact is empty") from error
        if tuple(header) != EXPECTED_COLUMNS:
            raise ValueError("UVA artifact columns or column order do not match v2.0")
        raw_rows: list[dict[str, str]] = []
        for row_number, values in enumerate(reader, start=2):
            if len(values) != len(EXPECTED_COLUMNS):
                raise ValueError(
                    f"UVA row {row_number} has {len(values)} columns; expected 161"
                )
            raw_rows.append(dict(zip(EXPECTED_COLUMNS, values, strict=True)))
    if len(raw_rows) != artifact.expected_rows:
        raise ValueError(
            f"UVA artifact has {len(raw_rows)} rows; expected {artifact.expected_rows}"
        )

    records: list[UVAFacilityRecord] = []
    seen_coordinates: set[tuple[float, float]] = set()
    for row_number, row in enumerate(raw_rows, start=2):
        latitude = _parse_coordinate(
            row["lat"], f"row {row_number} lat", VIRGINIA_LATITUDE_BOUNDS
        )
        longitude = _parse_coordinate(
            row["lon"], f"row {row_number} lon", VIRGINIA_LONGITUDE_BOUNDS
        )
        coordinates = (latitude, longitude)
        if coordinates in seen_coordinates:
            raise ValueError(f"UVA row {row_number} duplicates facility coordinates")
        seen_coordinates.add(coordinates)
        facility_type = row["Predicted_Facility_Type"]
        if facility_type not in FACILITY_TYPES:
            raise ValueError(f"UVA row {row_number} has unknown facility type")
        records.append(
            UVAFacilityRecord(
                row_number=row_number,
                latitude=latitude,
                longitude=longitude,
                coordinate_key=f"{row['lat']},{row['lon']}",
                geometry=_parse_polygon(row["building_footprint_polygon"], row_number),
                building_footprint_area=_parse_float(
                    row["building_footprint_area"], "building_footprint_area"
                ),
                number_of_floors=_parse_integer(
                    row["number_of_floors"], "number_of_floors", minimum=1, maximum=100
                ),
                total_building_area=_parse_float(
                    row["total_building_area"], "total_building_area"
                ),
                construction_year=_parse_integer(
                    row["construction_year"],
                    "construction_year",
                    minimum=1900,
                    maximum=2026,
                ),
                whitespace_area_mean=_parse_float(
                    row["Predicted_IT_Whitespace_Area_mean"],
                    "Predicted_IT_Whitespace_Area_mean",
                ),
                whitespace_area_std=_parse_float(
                    row["Predicted_IT_Whitespace_Area_std"],
                    "Predicted_IT_Whitespace_Area_std",
                ),
                critical_it_mw_mean=_parse_float(
                    row["Predicted_Built-out_Power_mean"],
                    "Predicted_Built-out_Power_mean",
                ),
                critical_it_mw_std=_parse_float(
                    row["Predicted_Built-out_Power_std"],
                    "Predicted_Built-out_Power_std",
                ),
                facility_type=facility_type,
                it_power=_profile(row, "IT_power_mean", "IT_power_std"),
                typical_day_facility_power=_profile(
                    row,
                    "Typical_Day_Facility_Power_mean",
                    "Typical_Day_Facility_Power_std",
                ),
                peak_temperature_day_facility_power=_profile(
                    row,
                    "Peak_Temperature_Day_Facility_Power_mean",
                    "Peak_Temperature_Day_Facility_Power_std",
                ),
                distances={
                    field: _parse_float(row[field], field) for field in DISTANCE_COLUMNS
                },
                content_hash=_canonical_row_hash(row),
            )
        )
    return records


def read_uva_facilities(
    path: str | Path,
    *,
    artifact: UVAArtifactSpec = UVA_ARTIFACT,
) -> list[UVAFacilityRecord]:
    source = Path(path)
    verify_artifact(source, artifact=artifact)
    return _read_records(source, artifact)


def _resolve_input(
    path: str | Path,
    artifact: UVAArtifactSpec,
) -> tuple[Path, MetadataVerification | None]:
    source = Path(path)
    if source.is_symlink():
        raise ValueError(f"refusing UVA input symlink: {source}")
    if not source.is_dir():
        return source, None
    manifest_path = source / UVA_MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("UVA bundle is missing a regular manifest.json")
    source_path = source / artifact.local_filename
    metadata = verify_metadata(source / artifact.metadata_filename, artifact=artifact)
    verification = verify_artifact(source_path, artifact=artifact)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("UVA bundle manifest is not valid JSON") from error
    _validate_manifest(document, artifact, verification, metadata)
    return source_path, metadata


def _record_metadata(
    record: UVAFacilityRecord,
    verification: ArtifactVerification,
    artifact: UVAArtifactSpec,
    metadata: MetadataVerification | None,
) -> dict[str, Any]:
    low_it, base_it, high_it = record.critical_it_interval
    low_energy, base_energy, high_energy = record.annual_energy_interval
    metadata_checkpoint = (
        None
        if metadata is None
        else {
            "url": artifact.metadata_url,
            "bytes": metadata.byte_count,
            "sha256": metadata.sha256,
        }
    )
    return {
        "dataset_version": artifact.version,
        "dataset_release_time": artifact.release_time,
        "dataset_doi": artifact.doi,
        "source_family": UVA_SOURCE_FAMILY,
        "independent_corroboration": True,
        "license": UVA_LICENSE,
        "input_sha256": verification.sha256,
        "provenance": {
            "artifact_url": artifact.data_url,
            "artifact_bytes": verification.byte_count,
            "artifact_md5": verification.md5,
            "artifact_sha256": verification.sha256,
            "version_metadata": metadata_checkpoint,
        },
        "artifact": {
            "url": artifact.data_url,
            "datafile_id": artifact.datafile_id,
            "original_filename": artifact.original_filename,
            "bytes": verification.byte_count,
            "md5": verification.md5,
            "sha256": verification.sha256,
        },
        "version_metadata": metadata_checkpoint,
        "source_row_number": record.row_number,
        "source_content_sha256": record.content_hash,
        "coordinates": {
            "source_order": "latitude_longitude",
            "latitude": record.latitude,
            "longitude": record.longitude,
        },
        "geometry": {
            "source_order": "latitude_longitude",
            "atlas_order": "longitude_latitude",
            "geojson": record.geometry,
        },
        "modeled_attributes": {
            "building_footprint_area": record.building_footprint_area,
            "number_of_floors": record.number_of_floors,
            "total_building_area": record.total_building_area,
            "it_whitespace_area_mean": record.whitespace_area_mean,
            "it_whitespace_area_reported_std": record.whitespace_area_std,
            "predicted_facility_type": record.facility_type,
            "construction_year": {
                "value": record.construction_year,
                "interpretation": (
                    "descriptive model output only; not evidence of current construction, "
                    "operational status, or a construction project"
                ),
            },
        },
        "profiles": {
            "it_power": record.it_power.metadata(),
            "typical_day_facility_power": record.typical_day_facility_power.metadata(),
            "peak_temperature_day_facility_power": (
                record.peak_temperature_day_facility_power.metadata()
            ),
        },
        "distance_fields": {
            "values": record.distances,
            "unit": None,
            "unit_note": "preserved source values; unit is not declared in column names",
        },
        "capacity_derivations": {
            "critical_it_mw": {
                "low": low_it,
                "base": base_it,
                "high": high_it,
                "rule": "modeled mean plus/minus one reported std; lower bound floored at zero",
            },
            "annual_energy_mwh": {
                "low": low_energy,
                "base": base_energy,
                "high": high_energy,
                "rule": (
                    "sum of 24 typical-day modeled facility MW values times 365; "
                    "hourly low/high use mean plus/minus reported std"
                ),
            },
            "uncertainty_note": "reported std is not a calibrated confidence interval",
        },
    }


def _snapshot_tags(record: UVAFacilityRecord, artifact: UVAArtifactSpec) -> dict[str, str]:
    return {
        "country": "United States",
        "addr:country": "US",
        "addr:state": "VA",
        "uva_dc_sense:dataset_version": artifact.version,
        "uva_dc_sense:facility_type_model_output": record.facility_type,
        "uva_dc_sense:construction_year_model_output": str(record.construction_year),
        "uva_dc_sense:building_footprint_area": str(record.building_footprint_area),
        "uva_dc_sense:number_of_floors": str(record.number_of_floors),
        "uva_dc_sense:total_building_area": str(record.total_building_area),
        "uva_dc_sense:source_content_sha256": record.content_hash,
    }


class UVADataverseAdapter:
    """Import pinned UVA model rows without promoting them to construction claims."""

    source_name = "uva_dc_sense"

    def __init__(self, *, artifact: UVAArtifactSpec = UVA_ARTIFACT) -> None:
        self.artifact = artifact

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        _require_timestamp(retrieved_at, "retrieved_at")
        source_path, metadata = _resolve_input(path, self.artifact)
        verification = verify_artifact(source_path, artifact=self.artifact)
        records = _read_records(source_path, self.artifact)
        entities_created = 0
        evidence_created = 0
        with connection:
            for record in records:
                stable_key = (
                    f"uva_dc_sense:{self.artifact.version}:{record.coordinate_key}:"
                    f"{record.content_hash}"
                )
                evidence_id = stable_id(
                    "evidence",
                    UVA_SOURCE_FAMILY,
                    self.artifact.version,
                    record.coordinate_key,
                    record.content_hash,
                    retrieved_at,
                )
                evidence_created += int(
                    add_evidence(
                        connection,
                        Evidence(
                            id=evidence_id,
                            kind=EvidenceKind.THIRD_PARTY_DATASET,
                            title=(
                                f"UVA DC-SENSE v{self.artifact.version} modeled facility "
                                f"at {record.latitude:.6f}, {record.longitude:.6f}"
                            ),
                            source_url=self.artifact.doi,
                            publisher=UVA_PUBLISHER,
                            source_family=UVA_SOURCE_FAMILY,
                            license=UVA_LICENSE,
                            attribution=UVA_ATTRIBUTION,
                            published_at=self.artifact.release_time,
                            retrieved_at=retrieved_at,
                            excerpt=(
                                "Modeled Virginia facility row. Construction year is descriptive "
                                "model output; lifecycle remains unknown."
                            ),
                        ),
                        content_hash=record.content_hash,
                        metadata=_record_metadata(
                            record, verification, self.artifact, metadata
                        ),
                    )
                )
                entity_id = stable_id("entity", stable_key, "facility")
                entities_created += int(
                    add_facility(
                        connection,
                        Facility(entity_id, stable_key, evidence_id),
                        created_at=retrieved_at,
                    )
                )
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id),
                    entity_id=entity_id,
                    name=(
                        f"UVA modeled Virginia data-centre facility "
                        f"({record.latitude:.6f}, {record.longitude:.6f})"
                    ),
                    latitude=record.latitude,
                    longitude=record.longitude,
                    geometry=record.geometry,
                    tags=_snapshot_tags(record, self.artifact),
                    evidence_id=evidence_id,
                    as_of_date=self.artifact.release_date,
                    recorded_at=retrieved_at,
                    method="uva_dc_sense_v2_modeled_facility",
                    confidence=0.70,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", entity_id, evidence_id, "unknown"),
                        entity_id=entity_id,
                        status=LifecycleStatus.UNKNOWN,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.release_date,
                        recorded_at=retrieved_at,
                        method="uva_dc_sense_does_not_establish_lifecycle",
                        confidence=1.0,
                    ),
                )

                low, base, high = record.critical_it_interval
                add_capacity(
                    connection,
                    CapacityEstimate(
                        id=stable_id(
                            "capacity", entity_id, evidence_id, CapacityMetric.CRITICAL_IT_MW
                        ),
                        entity_id=entity_id,
                        metric=CapacityMetric.CRITICAL_IT_MW,
                        low=low,
                        base=base,
                        high=high,
                        method=EstimateMethod.MODELED,
                        confidence=0.45,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.release_date,
                        recorded_at=retrieved_at,
                        stage=CapacityStage.UNKNOWN,
                        notes=(
                            "UVA DC-SENSE modeled built-out critical IT power; low/high are "
                            "mean ± one reported std (lower floored at zero). Reported std is "
                            "not a calibrated confidence interval; lifecycle stage is unknown."
                        ),
                    )
                )
                energy_low, energy_base, energy_high = record.annual_energy_interval
                add_capacity(
                    connection,
                    CapacityEstimate(
                        id=stable_id(
                            "capacity",
                            entity_id,
                            evidence_id,
                            CapacityMetric.ANNUAL_ENERGY_MWH,
                        ),
                        entity_id=entity_id,
                        metric=CapacityMetric.ANNUAL_ENERGY_MWH,
                        low=energy_low,
                        base=energy_base,
                        high=energy_high,
                        method=EstimateMethod.MODELED,
                        confidence=0.40,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.release_date,
                        recorded_at=retrieved_at,
                        stage=CapacityStage.UNKNOWN,
                        notes=(
                            "Extrapolated modeled annual energy: sum of 24 typical-day facility "
                            "power means × 365. Hourly low/high use mean ± reported std; std is "
                            "not a calibrated confidence interval. This is not metered energy."
                        ),
                    )
                )

                mapped = OPERATING_MODEL_MAP.get(record.facility_type)
                if mapped is not None:
                    operating_model, confidence = mapped
                    add_operating_model(
                        connection,
                        observation_id=stable_id(
                            "operating_model", entity_id, evidence_id, operating_model
                        ),
                        entity_id=entity_id,
                        operating_model=operating_model,
                        evidence_id=evidence_id,
                        as_of_date=self.artifact.release_date,
                        recorded_at=retrieved_at,
                        method="uva_dc_sense_predicted_facility_type_mapping",
                        confidence=confidence,
                    )

        return ImportResult(
            source=self.source_name,
            examined_elements=len(records),
            imported_elements=len(records),
            skipped_elements=0,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=(),
        )


# Concise aliases for scripts and external integration.
UVAAdapter = UVADataverseAdapter
UVAFetcher = UVADataFetcher
