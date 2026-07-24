"""Deterministic review-job queue for coordinate-bearing atlas entities.

This module only prioritizes already-known atlas entities and prepares bounded
arguments for the existing Sentinel catalog and change workflows.  It performs
no network requests and makes no imagery-derived identity, lifecycle, operating
status, workload, or power claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import EntityKind, LifecycleStatus
from .satellite_catalog import Provider


QUEUE_FILENAME = "satellite-review-queue.jsonl"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
QUEUE_BUNDLE_FILES = frozenset(
    {QUEUE_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
)
QUEUE_SCHEMA_VERSION = 1
EARTH_RADIUS_KM = 6_371.0088
ELIGIBLE_ENTITY_KINDS = frozenset(
    {EntityKind.CAMPUS.value, EntityKind.FACILITY.value, EntityKind.PROJECT.value}
)
KNOWN_ENTITY_KINDS = frozenset(item.value for item in EntityKind)
KNOWN_LIFECYCLE_STATUSES = frozenset(item.value for item in LifecycleStatus)
REVIEW_CONSTRAINTS = {
    "queue_basis": "existing_atlas_entity_and_location",
    "imagery_identity_claim": False,
    "imagery_lifecycle_claim": False,
    "imagery_operating_status_claim": False,
    "imagery_power_claim": False,
    "review_required": True,
}
QUEUE_SCOPE = {
    "purpose": "bounded imagery review planning for existing atlas entities",
    "network_requests_performed": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_power_inference": False,
    "automatic_entity_merge": False,
}
QUEUE_ORDERING_POLICY = {
    "primary": "priority.rank ascending",
    "secondary": [
        "missing status_as_of first",
        "status age_days_at_atlas_as_of descending",
        "entity.id ascending",
        "location.part_index ascending",
    ],
    "freshness_reference": "source.atlas_as_of",
}
STATUS_FRESHNESS_BUCKETS = (
    "missing",
    "age_days_0_30",
    "age_days_31_90",
    "age_days_91_180",
    "age_days_181_365",
    "age_days_366_plus",
)

_ACTIVE_CONSTRUCTION = frozenset(
    {
        LifecycleStatus.SITE_PREPARATION.value,
        LifecycleStatus.CLEARING.value,
        LifecycleStatus.CIVIL_WORKS.value,
        LifecycleStatus.FOUNDATIONS.value,
        LifecycleStatus.SHELL.value,
        LifecycleStatus.MEP_ELECTRICAL.value,
        LifecycleStatus.UNDER_CONSTRUCTION.value,
        LifecycleStatus.COMMISSIONING.value,
        LifecycleStatus.EXPANSION.value,
    }
)
_PROPOSED_PIPELINE = frozenset(
    {
        LifecycleStatus.LEAD.value,
        LifecycleStatus.CANDIDATE.value,
        LifecycleStatus.ANNOUNCED.value,
        LifecycleStatus.PROPOSED.value,
        LifecycleStatus.SITE_CONTROL.value,
        LifecycleStatus.PERMITTING.value,
        LifecycleStatus.PERMITTED.value,
    }
)
_INACTIVE = frozenset(
    {
        LifecycleStatus.PAUSED.value,
        LifecycleStatus.CANCELLED.value,
        LifecycleStatus.REPURPOSED.value,
        LifecycleStatus.DECOMMISSIONED.value,
        LifecycleStatus.DEMOLISHED.value,
    }
)
PRIORITY_POLICY = (
    {
        "rank": 0,
        "tier": "active_construction",
        "statuses": sorted(_ACTIVE_CONSTRUCTION),
        "reason": "visible construction or expansion state",
    },
    {
        "rank": 1,
        "tier": "proposed_pipeline",
        "statuses": sorted(_PROPOSED_PIPELINE),
        "reason": "pre-operational proposal or development state",
    },
    {
        "rank": 2,
        "tier": "unknown",
        "statuses": [LifecycleStatus.UNKNOWN.value],
        "reason": "unknown lifecycle has high review information value",
    },
    {
        "rank": 3,
        "tier": "operational",
        "statuses": [LifecycleStatus.OPERATIONAL.value],
        "reason": "operational sites follow unresolved pipeline sites",
    },
    {
        "rank": 4,
        "tier": "inactive",
        "statuses": sorted(_INACTIVE),
        "reason": "paused or terminal state",
    },
)


class QueueValidationError(ValueError):
    """Raised when the atlas, configuration, or output contract is invalid."""


def _calendar_date(value: date | str, field: str) -> date:
    if isinstance(value, datetime):
        raise QueueValidationError(f"{field} must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise QueueValidationError(f"{field} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise QueueValidationError(f"{field} must be a valid YYYY-MM-DD date") from error
    if parsed.isoformat() != value:
        raise QueueValidationError(f"{field} must use canonical YYYY-MM-DD")
    return parsed


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueueValidationError(f"{field} must be a non-empty RFC 3339 timestamp")
    if not value.endswith("Z") and not (
        len(value) >= 6 and value[-6] in {"+", "-"} and value[-3] == ":"
    ):
        raise QueueValidationError(f"{field} must include a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QueueValidationError(f"{field} is not a valid RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QueueValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _provider(value: Provider | str) -> Provider:
    if isinstance(value, Provider):
        return value
    try:
        return Provider(value)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(item.value for item in Provider)
        raise QueueValidationError(f"provider must be one of: {allowed}") from error


@dataclass(frozen=True, slots=True)
class QueueConfig:
    baseline_target: date | str
    current_target: date | str
    provider: Provider | str = Provider.EARTH_SEARCH
    query_window_days: int = 45
    max_cloud_cover: float = 20.0
    catalog_limit: int = 100
    aoi_half_side_km: float = 2.0
    minimum_component_area_m2: float = 5_000.0

    def __post_init__(self) -> None:
        baseline = _calendar_date(self.baseline_target, "baseline_target")
        current = _calendar_date(self.current_target, "current_target")
        provider = _provider(self.provider)
        if baseline >= current:
            raise QueueValidationError("baseline_target must be before current_target")
        if isinstance(self.query_window_days, bool) or not isinstance(
            self.query_window_days, int
        ):
            raise QueueValidationError("query_window_days must be an integer")
        if not 0 <= self.query_window_days <= 366:
            raise QueueValidationError("query_window_days must be between 0 and 366")
        window = timedelta(days=self.query_window_days)
        try:
            baseline_start = baseline - window
            baseline_end = baseline + window
            current_start = current - window
            current_end = current + window
        except OverflowError as error:
            raise QueueValidationError("query window exceeds calendar bounds") from error
        if baseline_end >= current_start:
            raise QueueValidationError(
                "baseline and current query windows must not overlap"
            )
        if isinstance(self.max_cloud_cover, bool) or not isinstance(
            self.max_cloud_cover, (int, float)
        ):
            raise QueueValidationError("max_cloud_cover must be numeric")
        cloud = float(self.max_cloud_cover)
        if not math.isfinite(cloud) or not 0 <= cloud <= 100:
            raise QueueValidationError("max_cloud_cover must be between 0 and 100")
        if isinstance(self.catalog_limit, bool) or not isinstance(self.catalog_limit, int):
            raise QueueValidationError("catalog_limit must be an integer")
        if not 1 <= self.catalog_limit <= 100:
            raise QueueValidationError("catalog_limit must be between 1 and 100")
        half_side = _positive_number(
            self.aoi_half_side_km, "aoi_half_side_km"
        )
        if half_side > 25:
            raise QueueValidationError("aoi_half_side_km must not exceed 25 km")
        minimum_area = _positive_number(
            self.minimum_component_area_m2, "minimum_component_area_m2"
        )
        object.__setattr__(self, "baseline_target", baseline)
        object.__setattr__(self, "current_target", current)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "max_cloud_cover", cloud)
        object.__setattr__(self, "aoi_half_side_km", half_side)
        object.__setattr__(self, "minimum_component_area_m2", minimum_area)

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_target": self.baseline_target.isoformat(),
            "current_target": self.current_target.isoformat(),
            "provider": self.provider.value,
            "query_window_days": self.query_window_days,
            "max_cloud_cover": _compact_number(self.max_cloud_cover),
            "catalog_limit": self.catalog_limit,
            "aoi_half_side_km": _compact_number(self.aoi_half_side_km),
            "minimum_component_area_m2": _compact_number(
                self.minimum_component_area_m2
            ),
            "eligible_entity_kinds": sorted(ELIGIBLE_ENTITY_KINDS),
        }


@dataclass(frozen=True, slots=True)
class QueueBundle:
    queue_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    manifest: Mapping[str, Any]


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QueueValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise QueueValidationError(f"{field} must be finite and positive")
    return result


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _canonical_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _manifest_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise QueueValidationError(f"{field} must be lowercase SHA-256 hexadecimal")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QueueValidationError(f"{field} must be a non-negative integer")
    return value


def _validate_release_manifest_lineage(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QueueValidationError("release manifest lineage must be an object or null")
    expected_keys = {
        "file",
        "bytes",
        "sha256",
        "format",
        "as_of",
        "recorded_at",
        "atlas_file",
        "atlas_bytes",
        "atlas_sha256",
    }
    if set(value) != expected_keys:
        raise QueueValidationError("release manifest lineage has unexpected fields")
    if value.get("file") != "manifest.json":
        raise QueueValidationError("release manifest lineage file must be manifest.json")
    atlas_file = _required_text(value.get("atlas_file"), "release lineage atlas_file")
    if Path(atlas_file).name != atlas_file:
        raise QueueValidationError("release lineage atlas_file must be a basename")
    result = dict(value)
    result["format"] = _optional_text(
        value.get("format"), "release manifest lineage format"
    )
    if result["format"] != value.get("format"):
        raise QueueValidationError("release manifest lineage format is not canonical")
    result["as_of"] = (
        _calendar_date(value["as_of"], "release manifest lineage as_of").isoformat()
        if value.get("as_of") is not None
        else None
    )
    if result["as_of"] != value.get("as_of"):
        raise QueueValidationError("release manifest lineage as_of is not canonical")
    result["recorded_at"] = (
        _timestamp(value["recorded_at"], "release manifest lineage recorded_at")
        if value.get("recorded_at") is not None
        else None
    )
    if result["recorded_at"] != value.get("recorded_at"):
        raise QueueValidationError(
            "release manifest lineage recorded_at is not canonical UTC"
        )
    result["bytes"] = _nonnegative_integer(
        value.get("bytes"), "release manifest lineage bytes"
    )
    result["atlas_bytes"] = _nonnegative_integer(
        value.get("atlas_bytes"), "release manifest lineage atlas_bytes"
    )
    result["sha256"] = _sha256_value(
        value.get("sha256"), "release manifest lineage sha256"
    )
    result["atlas_sha256"] = _sha256_value(
        value.get("atlas_sha256"), "release manifest lineage atlas_sha256"
    )
    return result


def _decode_geojson(raw: bytes) -> Mapping[str, Any]:
    if not isinstance(raw, bytes) or not raw:
        raise QueueValidationError("atlas GeoJSON must contain raw bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise QueueValidationError("atlas GeoJSON must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise QueueValidationError(f"atlas GeoJSON contains non-finite number {value}")

    try:
        document = json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise QueueValidationError("atlas GeoJSON is not valid JSON") from error
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise QueueValidationError("atlas GeoJSON must be a FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise QueueValidationError("atlas GeoJSON features must be an array")
    return document


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueueValidationError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueueValidationError(f"{field} must be text or null")
    return value.strip() or None


def _iso_code(value: Any, field: str, length: int) -> str | None:
    result = _optional_text(value, field)
    if result is not None and (
        len(result) != length
        or not result.isascii()
        or not result.isalpha()
        or result != result.upper()
    ):
        raise QueueValidationError(
            f"{field} must be null or an uppercase ISO alpha-{length} code"
        )
    return result


def _status_freshness(
    status_as_of_value: Any, *, atlas_as_of: date, field: str
) -> dict[str, Any]:
    if status_as_of_value is None:
        return {
            "status_as_of": None,
            "age_days_at_atlas_as_of": None,
            "missing": True,
        }
    status_as_of = _calendar_date(status_as_of_value, field)
    if status_as_of > atlas_as_of:
        raise QueueValidationError(f"{field} must not be after atlas_as_of")
    return {
        "status_as_of": status_as_of.isoformat(),
        "age_days_at_atlas_as_of": (atlas_as_of - status_as_of).days,
        "missing": False,
    }


def _freshness_bucket(freshness: Mapping[str, Any]) -> str:
    if freshness["missing"]:
        return "missing"
    age = freshness["age_days_at_atlas_as_of"]
    if age <= 30:
        return "age_days_0_30"
    if age <= 90:
        return "age_days_31_90"
    if age <= 180:
        return "age_days_91_180"
    if age <= 365:
        return "age_days_181_365"
    return "age_days_366_plus"


def _freshness_order(freshness: Mapping[str, Any]) -> tuple[int, int]:
    if freshness["missing"]:
        return 0, 0
    return 1, -int(freshness["age_days_at_atlas_as_of"])


def _country_identity(entity: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        entity["country"],
        entity["country_iso_a2"],
        entity["country_iso_a3"],
    )


def _country_sort_key(
    identity: tuple[str | None, str | None, str | None]
) -> tuple[str, str, str]:
    country, iso_a2, iso_a3 = identity
    return iso_a3 or "", iso_a2 or "", country or ""


def _country_count_rows(
    counts: Mapping[
        tuple[str | None, str | None, str | None], Mapping[str, int]
    ],
) -> list[dict[str, Any]]:
    return [
        {
            "country": identity[0],
            "country_iso_a2": identity[1],
            "country_iso_a3": identity[2],
            "entities": sum(counts[identity].values()),
            "by_priority_tier": dict(sorted(counts[identity].items())),
        }
        for identity in sorted(counts, key=_country_sort_key)
    ]


def _coordinate(value: Any, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QueueValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise QueueValidationError(f"{field} is outside WGS84 bounds")
    return result


def _geometry_points(value: Any, field: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []

    def visit(coordinates: Any, coordinate_field: str) -> None:
        if not isinstance(coordinates, list) or not coordinates:
            raise QueueValidationError(f"{coordinate_field} must be a non-empty array")
        if (
            len(coordinates) >= 2
            and isinstance(coordinates[0], (int, float))
            and not isinstance(coordinates[0], bool)
            and isinstance(coordinates[1], (int, float))
            and not isinstance(coordinates[1], bool)
        ):
            longitude = _coordinate(
                coordinates[0], f"{coordinate_field} longitude", -180, 180
            )
            latitude = _coordinate(
                coordinates[1], f"{coordinate_field} latitude", -90, 90
            )
            points.append((longitude, latitude))
            return
        for index, item in enumerate(coordinates):
            visit(item, f"{coordinate_field}[{index}]")

    if value is None:
        return points
    if not isinstance(value, Mapping):
        raise QueueValidationError(f"{field} must be a GeoJSON geometry or null")
    geometry_type = value.get("type")
    if geometry_type == "GeometryCollection":
        geometries = value.get("geometries")
        if not isinstance(geometries, list):
            raise QueueValidationError(f"{field}.geometries must be an array")
        for index, geometry in enumerate(geometries):
            points.extend(_geometry_points(geometry, f"{field}.geometries[{index}]"))
        return points
    if geometry_type not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    }:
        raise QueueValidationError(f"{field} has unsupported geometry type")
    visit(value.get("coordinates"), f"{field}.coordinates")
    return points


def _geometry_center(geometry: Any, field: str) -> tuple[float, float] | None:
    if geometry is None:
        return None
    points = _geometry_points(geometry, field)
    if not points:
        return None
    reference = points[0][0]
    unwrapped = [
        reference + ((longitude - reference + 180) % 360) - 180
        for longitude, _ in points
    ]
    if max(unwrapped) - min(unwrapped) > 180:
        raise QueueValidationError(f"{field} spans more than 180 degrees longitude")
    longitude = (min(unwrapped) + max(unwrapped)) / 2
    longitude = ((longitude + 180) % 360) - 180
    latitude = (min(point[1] for point in points) + max(point[1] for point in points)) / 2
    return latitude, longitude


def _feature_center(
    properties: Mapping[str, Any], geometry: Any, field: str
) -> tuple[float, float, str] | None:
    latitude_value = properties.get("latitude")
    longitude_value = properties.get("longitude")
    if (latitude_value is None) != (longitude_value is None):
        raise QueueValidationError(
            f"{field} latitude and longitude must both be present or both be null"
        )
    if latitude_value is not None:
        latitude = _coordinate(latitude_value, f"{field}.latitude", -90, 90)
        longitude = _coordinate(longitude_value, f"{field}.longitude", -180, 180)
        if longitude == 180:
            longitude = -180.0
        return latitude, longitude, "properties.latitude_longitude"
    center = _geometry_center(geometry, f"{field}.geometry")
    if center is None:
        return None
    return center[0], center[1], "geometry_bounds_center"


def _priority(status_value: Any, field: str) -> tuple[str, int, str, str]:
    if status_value is None:
        status = LifecycleStatus.UNKNOWN.value
    else:
        status = _required_text(status_value, field)
        if status not in KNOWN_LIFECYCLE_STATUSES:
            raise QueueValidationError(f"{field} has unknown lifecycle status {status!r}")
    if status in _ACTIVE_CONSTRUCTION:
        return status, 0, "active_construction", "visible construction or expansion state"
    if status in _PROPOSED_PIPELINE:
        return status, 1, "proposed_pipeline", "pre-operational proposal or development state"
    if status == LifecycleStatus.UNKNOWN.value:
        return status, 2, "unknown", "unknown lifecycle has high review information value"
    if status == LifecycleStatus.OPERATIONAL.value:
        return status, 3, "operational", "operational sites follow unresolved pipeline sites"
    if status in _INACTIVE:
        return status, 4, "inactive", "paused or terminal state"
    raise QueueValidationError(f"{field} is not covered by the priority policy")


def _aoi_bboxes(
    latitude: float, longitude: float, half_side_km: float
) -> list[tuple[float, float, float, float]]:
    angular = half_side_km / EARTH_RADIUS_KM
    latitude_delta = math.degrees(angular)
    south = max(-90.0, latitude - latitude_delta)
    north = min(90.0, latitude + latitude_delta)
    reaches_pole = south == -90.0 or north == 90.0
    cosine = math.cos(math.radians(latitude))
    ratio = math.sin(angular) / max(abs(cosine), 1e-15)
    if reaches_pole or ratio >= 1:
        longitude_delta = 180.0
    else:
        longitude_delta = math.degrees(math.asin(ratio))
    if longitude_delta >= 180:
        raw_parts = [(-180.0, south, 180.0, north)]
    else:
        west = longitude - longitude_delta
        east = longitude + longitude_delta
        if west < -180:
            raw_parts = [(-180.0, south, east, north), (west + 360, south, 180.0, north)]
        elif east > 180:
            raw_parts = [(-180.0, south, east - 360, north), (west, south, 180.0, north)]
        else:
            raw_parts = [(west, south, east, north)]
    parts = [tuple(round(value, 7) for value in part) for part in raw_parts]
    for west, part_south, east, part_north in parts:
        if not -180 <= west < east <= 180 or not -90 <= part_south < part_north <= 90:
            raise QueueValidationError("generated AOI is not a valid non-wrapping WGS84 bbox")
    return sorted(parts)


def _number_argument(value: int | float) -> str:
    result = f"{value:.10f}".rstrip("0").rstrip(".")
    return result if result not in {"-0", ""} else "0"


def _bbox_argument(bbox: Sequence[float]) -> str:
    return ",".join(_number_argument(value) for value in bbox)


def _queue_id(entity_id: str, part: int, bbox: Sequence[float]) -> str:
    identity = json.dumps(
        {"entity_id": entity_id, "part": part, "bbox": list(bbox)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"satq-{hashlib.sha256(identity).hexdigest()[:24]}"


def _query_dates(target: date, window_days: int) -> tuple[str, str]:
    return (
        (target - timedelta(days=window_days)).isoformat(),
        (target + timedelta(days=window_days)).isoformat(),
    )


def _job_record(
    *,
    entity: Mapping[str, Any],
    latitude: float,
    longitude: float,
    coordinate_method: str,
    bbox: tuple[float, float, float, float],
    part_index: int,
    part_count: int,
    status: str,
    priority_rank: int,
    priority_tier: str,
    priority_reason: str,
    status_freshness: Mapping[str, Any],
    config: QueueConfig,
) -> dict[str, Any]:
    queue_id = _queue_id(str(entity["id"]), part_index, bbox)
    catalog_directory = f"jobs/{queue_id}/catalog"
    change_directory = f"jobs/{queue_id}/change"
    baseline_start, baseline_end = _query_dates(
        config.baseline_target, config.query_window_days
    )
    current_start, current_end = _query_dates(
        config.current_target, config.query_window_days
    )
    bbox_text = _bbox_argument(bbox)
    catalog_arguments = [
        "--provider",
        config.provider.value,
        "--bbox",
        bbox_text,
        "--baseline-start",
        baseline_start,
        "--baseline-end",
        baseline_end,
        "--baseline-target",
        config.baseline_target.isoformat(),
        "--current-start",
        current_start,
        "--current-end",
        current_end,
        "--current-target",
        config.current_target.isoformat(),
        "--max-cloud-cover",
        _number_argument(config.max_cloud_cover),
        "--limit",
        str(config.catalog_limit),
        "--temporal-window-days",
        str(config.query_window_days),
        "--output-dir",
        catalog_directory,
    ]
    change_arguments = [
        "--baseline-stac",
        f"{catalog_directory}/baseline-response.json",
        "--baseline-id",
        "{selected_ids.baseline}",
        "--current-stac",
        f"{catalog_directory}/current-response.json",
        "--current-id",
        "{selected_ids.current}",
        "--bbox",
        bbox_text,
        "--entity-id",
        str(entity["id"]),
        "--entity-name",
        str(entity["name"]),
        "--output-dir",
        change_directory,
        "--minimum-component-area-m2",
        _number_argument(config.minimum_component_area_m2),
    ]
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "queue_id": queue_id,
        "priority": {
            "rank": priority_rank,
            "tier": priority_tier,
            "reason": priority_reason,
            "lifecycle_status": status,
        },
        "status_freshness": dict(status_freshness),
        "entity": dict(entity),
        "location": {
            "center_wgs84": {
                "latitude": round(latitude, 7),
                "longitude": round(longitude, 7),
                "method": coordinate_method,
            },
            "aoi_bbox_wgs84": list(bbox),
            "aoi_half_side_km": _compact_number(config.aoi_half_side_km),
            "part_index": part_index,
            "part_count": part_count,
        },
        "catalog_job": {
            "script": "scripts/catalog_satellite.py",
            "arguments": catalog_arguments,
            "output_directory": catalog_directory,
        },
        "change_job_template": {
            "script": "scripts/sentinel_change.py",
            "arguments": change_arguments,
            "catalog_manifest": f"{catalog_directory}/manifest.json",
            "selected_id_json_pointers": {
                "{selected_ids.baseline}": "/selected_ids/baseline",
                "{selected_ids.current}": "/selected_ids/current",
            },
            "output_directory": change_directory,
        },
        "review_constraints": dict(REVIEW_CONSTRAINTS),
    }


def build_queue_bundle(
    raw_geojson: bytes,
    *,
    source_name: str,
    generated_at: str,
    config: QueueConfig,
    release_manifest_lineage: Mapping[str, Any] | None = None,
) -> QueueBundle:
    """Build queue bytes and a hash-bound manifest without network access."""
    if not isinstance(config, QueueConfig):
        raise QueueValidationError("config must be a QueueConfig")
    source_name = _required_text(source_name, "source_name")
    if Path(source_name).name != source_name:
        raise QueueValidationError("source_name must be a basename")
    generated = _timestamp(generated_at, "generated_at")
    if release_manifest_lineage is not None:
        release_manifest_lineage = _validate_release_manifest_lineage(
            release_manifest_lineage
        )
    document = _decode_geojson(raw_geojson)
    if release_manifest_lineage is not None:
        source_sha256 = hashlib.sha256(raw_geojson).hexdigest()
        if (
            release_manifest_lineage["atlas_file"] != source_name
            or release_manifest_lineage["atlas_bytes"] != len(raw_geojson)
            or release_manifest_lineage["atlas_sha256"] != source_sha256
        ):
            raise QueueValidationError(
                "release manifest lineage does not match exact source atlas bytes"
            )
    features = document["features"]
    atlas_as_of = _calendar_date(document.get("atlas_as_of"), "atlas_as_of")
    jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    queued_entity_ids: set[str] = set()
    missing_coordinates = 0
    split_entities = 0
    excluded_kinds: dict[str, int] = {}
    eligible_kinds: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    country_tier_counts: dict[
        tuple[str | None, str | None, str | None], dict[str, int]
    ] = {}
    freshness_counts = {bucket: 0 for bucket in STATUS_FRESHNESS_BUCKETS}

    for index, feature in enumerate(features):
        field = f"feature {index}"
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise QueueValidationError(f"{field} must be a GeoJSON Feature")
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise QueueValidationError(f"{field}.properties must be an object")
        entity_id = _required_text(properties.get("entity_id"), f"{field}.entity_id")
        feature_id = feature.get("id")
        if feature_id is not None and feature_id != entity_id:
            raise QueueValidationError(f"{field}.id must match properties.entity_id")
        if entity_id in seen_ids:
            raise QueueValidationError(f"duplicate atlas entity_id: {entity_id}")
        seen_ids.add(entity_id)
        entity_kind = _required_text(
            properties.get("entity_kind"), f"{field}.entity_kind"
        )
        if entity_kind not in KNOWN_ENTITY_KINDS:
            raise QueueValidationError(f"{field}.entity_kind is unknown: {entity_kind!r}")
        if entity_kind not in ELIGIBLE_ENTITY_KINDS:
            excluded_kinds[entity_kind] = excluded_kinds.get(entity_kind, 0) + 1
            continue
        eligible_kinds[entity_kind] = eligible_kinds.get(entity_kind, 0) + 1
        center = _feature_center(properties, feature.get("geometry"), field)
        if center is None:
            missing_coordinates += 1
            continue
        latitude, longitude, coordinate_method = center
        latitude = round(latitude, 7)
        longitude = round(longitude, 7)
        status, priority_rank, priority_tier, priority_reason = _priority(
            properties.get("status"), f"{field}.status"
        )
        status_freshness = _status_freshness(
            properties.get("status_as_of"),
            atlas_as_of=atlas_as_of,
            field=f"{field}.status_as_of",
        )
        name = _optional_text(properties.get("name"), f"{field}.name")
        stable_key = _optional_text(
            properties.get("stable_key"), f"{field}.stable_key"
        )
        display_name = name or stable_key or entity_id
        entity = {
            "id": entity_id,
            "kind": entity_kind,
            "name": display_name,
            "stable_key": stable_key,
            "target_entity_id": _optional_text(
                properties.get("target_entity_id"), f"{field}.target_entity_id"
            ),
            "source_family": _optional_text(
                properties.get("source_family"), f"{field}.source_family"
            ),
            "source_url": _optional_text(
                properties.get("source_url"), f"{field}.source_url"
            ),
            "source_license": _optional_text(
                properties.get("source_license"), f"{field}.source_license"
            ),
            "snapshot_evidence_id": _optional_text(
                properties.get("snapshot_evidence_id"),
                f"{field}.snapshot_evidence_id",
            ),
            "status_evidence_id": _optional_text(
                properties.get("status_evidence_id"), f"{field}.status_evidence_id"
            ),
            "status_as_of": status_freshness["status_as_of"],
            "country": _optional_text(properties.get("country"), f"{field}.country"),
            "country_iso_a2": _iso_code(
                properties.get("country_iso_a2"), f"{field}.country_iso_a2", 2
            ),
            "country_iso_a3": _iso_code(
                properties.get("country_iso_a3"), f"{field}.country_iso_a3", 3
            ),
        }
        bboxes = _aoi_bboxes(latitude, longitude, config.aoi_half_side_km)
        if len(bboxes) > 1:
            split_entities += 1
        queued_entity_ids.add(entity_id)
        tier_counts[priority_tier] = tier_counts.get(priority_tier, 0) + 1
        country_tiers = country_tier_counts.setdefault(_country_identity(entity), {})
        country_tiers[priority_tier] = country_tiers.get(priority_tier, 0) + 1
        freshness_bucket = _freshness_bucket(status_freshness)
        freshness_counts[freshness_bucket] += 1
        for part_index, bbox in enumerate(bboxes, start=1):
            jobs.append(
                _job_record(
                    entity=entity,
                    latitude=latitude,
                    longitude=longitude,
                    coordinate_method=coordinate_method,
                    bbox=bbox,
                    part_index=part_index,
                    part_count=len(bboxes),
                    status=status,
                    priority_rank=priority_rank,
                    priority_tier=priority_tier,
                    priority_reason=priority_reason,
                    status_freshness=status_freshness,
                    config=config,
                )
            )

    jobs.sort(
        key=lambda job: (
            job["priority"]["rank"],
            *_freshness_order(job["status_freshness"]),
            job["entity"]["id"],
            job["location"]["part_index"],
        )
    )
    for position, job in enumerate(jobs, start=1):
        job["queue_position"] = position
    queue_bytes = b"".join(_canonical_line(job) for job in jobs)
    source_attribution = document.get("attribution")
    if source_attribution is not None and not (
        isinstance(source_attribution, list)
        and all(isinstance(item, str) for item in source_attribution)
    ):
        raise QueueValidationError("atlas attribution must be an array of strings or null")
    atlas_recorded_at = document.get("atlas_recorded_at")
    if atlas_recorded_at is not None:
        atlas_recorded_at = _timestamp(atlas_recorded_at, "atlas_recorded_at")
    manifest = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "pipeline": "global_satellite_review_queue",
        "generated_at": generated,
        "scope": dict(QUEUE_SCOPE),
        "source": {
            "file": source_name,
            "bytes": len(raw_geojson),
            "sha256": hashlib.sha256(raw_geojson).hexdigest(),
            "atlas_as_of": atlas_as_of.isoformat(),
            "atlas_recorded_at": atlas_recorded_at,
            "attribution": source_attribution or [],
            "release_manifest": release_manifest_lineage,
        },
        "configuration": config.as_dict(),
        "priority_policy": list(PRIORITY_POLICY),
        "ordering_policy": dict(QUEUE_ORDERING_POLICY),
        "counts": {
            "features_examined": len(features),
            "eligible_features_by_kind": dict(sorted(eligible_kinds.items())),
            "excluded_features_by_kind": dict(sorted(excluded_kinds.items())),
            "skipped_missing_coordinates": missing_coordinates,
            "entities_queued": len(queued_entity_ids),
            "queue_jobs": len(jobs),
            "entities_split_at_antimeridian": split_entities,
            "queued_entities_by_priority_tier": dict(sorted(tier_counts.items())),
            "queued_entities_by_country_priority_tier": _country_count_rows(
                country_tier_counts
            ),
            "queued_entities_by_status_freshness": freshness_counts,
        },
        "artifacts": {
            QUEUE_FILENAME: {
                "format": "application/x-ndjson",
                "records": len(jobs),
                "bytes": len(queue_bytes),
                "sha256": hashlib.sha256(queue_bytes).hexdigest(),
            }
        },
    }
    manifest_bytes = _manifest_bytes(manifest)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_hash_bytes = f"{manifest_digest}  {MANIFEST_FILENAME}\n".encode("ascii")
    return QueueBundle(queue_bytes, manifest_bytes, manifest_hash_bytes, manifest)


_MANIFEST_KEYS = {
    "schema_version",
    "pipeline",
    "generated_at",
    "scope",
    "source",
    "configuration",
    "priority_policy",
    "ordering_policy",
    "counts",
    "artifacts",
}
_SOURCE_KEYS = {
    "file",
    "bytes",
    "sha256",
    "atlas_as_of",
    "atlas_recorded_at",
    "attribution",
    "release_manifest",
}
_CONFIGURATION_KEYS = {
    "baseline_target",
    "current_target",
    "provider",
    "query_window_days",
    "max_cloud_cover",
    "catalog_limit",
    "aoi_half_side_km",
    "minimum_component_area_m2",
    "eligible_entity_kinds",
}
_JOB_KEYS = {
    "schema_version",
    "queue_id",
    "queue_position",
    "priority",
    "status_freshness",
    "entity",
    "location",
    "catalog_job",
    "change_job_template",
    "review_constraints",
}
_ENTITY_KEYS = {
    "id",
    "kind",
    "name",
    "stable_key",
    "target_entity_id",
    "source_family",
    "source_url",
    "source_license",
    "snapshot_evidence_id",
    "status_evidence_id",
    "status_as_of",
    "country",
    "country_iso_a2",
    "country_iso_a3",
}


def _decode_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise QueueValidationError(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise QueueValidationError(f"{label} contains non-finite number {value}")

    try:
        value = json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise QueueValidationError(f"{label} is not valid JSON") from error
    if not isinstance(value, Mapping):
        raise QueueValidationError(f"{label} must contain a JSON object")
    return value


def _queue_config_from_manifest(value: Any) -> QueueConfig:
    if not isinstance(value, Mapping) or set(value) != _CONFIGURATION_KEYS:
        raise QueueValidationError("queue manifest configuration schema is invalid")
    if value.get("eligible_entity_kinds") != sorted(ELIGIBLE_ENTITY_KINDS):
        raise QueueValidationError("queue manifest eligible entity kinds changed")
    config = QueueConfig(
        baseline_target=value.get("baseline_target"),
        current_target=value.get("current_target"),
        provider=value.get("provider"),
        query_window_days=value.get("query_window_days"),
        max_cloud_cover=value.get("max_cloud_cover"),
        catalog_limit=value.get("catalog_limit"),
        aoi_half_side_km=value.get("aoi_half_side_km"),
        minimum_component_area_m2=value.get("minimum_component_area_m2"),
    )
    if _canonical_line(value) != _canonical_line(config.as_dict()):
        raise QueueValidationError("queue manifest configuration is not canonical")
    return config


def _validate_entity(value: Any, label: str, *, atlas_as_of: date) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ENTITY_KEYS:
        raise QueueValidationError(f"{label} entity schema is invalid")
    entity_id = _required_text(value.get("id"), f"{label} entity id")
    kind = _required_text(value.get("kind"), f"{label} entity kind")
    if kind not in ELIGIBLE_ENTITY_KINDS:
        raise QueueValidationError(f"{label} entity kind is not queue-eligible")
    entity = {
        "id": entity_id,
        "kind": kind,
        "name": _required_text(value.get("name"), f"{label} entity name"),
    }
    for field in sorted(
        _ENTITY_KEYS
        - {
            "id",
            "kind",
            "name",
            "status_as_of",
            "country_iso_a2",
            "country_iso_a3",
        }
    ):
        entity[field] = _optional_text(
            value.get(field), f"{label} entity {field}"
        )
    entity["status_as_of"] = _status_freshness(
        value.get("status_as_of"),
        atlas_as_of=atlas_as_of,
        field=f"{label} entity status_as_of",
    )["status_as_of"]
    entity["country_iso_a2"] = _iso_code(
        value.get("country_iso_a2"), f"{label} entity country_iso_a2", 2
    )
    entity["country_iso_a3"] = _iso_code(
        value.get("country_iso_a3"), f"{label} entity country_iso_a3", 3
    )
    return entity


def _validate_job_record(
    value: Mapping[str, Any], *, position: int, config: QueueConfig, atlas_as_of: date
) -> dict[str, Any]:
    label = f"queue record {position}"
    if set(value) != _JOB_KEYS or value.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise QueueValidationError(f"{label} schema is invalid")
    if value.get("queue_position") != position:
        raise QueueValidationError(f"{label} queue_position is not contiguous")
    priority = value.get("priority")
    if not isinstance(priority, Mapping) or set(priority) != {
        "rank",
        "tier",
        "reason",
        "lifecycle_status",
    }:
        raise QueueValidationError(f"{label} priority schema is invalid")
    status, rank, tier, reason = _priority(
        priority.get("lifecycle_status"), f"{label} lifecycle_status"
    )
    if priority != {
        "rank": rank,
        "tier": tier,
        "reason": reason,
        "lifecycle_status": status,
    }:
        raise QueueValidationError(f"{label} priority does not match policy")
    entity = _validate_entity(value.get("entity"), label, atlas_as_of=atlas_as_of)
    status_freshness = value.get("status_freshness")
    expected_freshness = _status_freshness(
        entity["status_as_of"],
        atlas_as_of=atlas_as_of,
        field=f"{label} status_as_of",
    )
    if (
        not isinstance(status_freshness, Mapping)
        or set(status_freshness)
        != {"status_as_of", "age_days_at_atlas_as_of", "missing"}
        or status_freshness != expected_freshness
    ):
        raise QueueValidationError(f"{label} status freshness is invalid")
    location = value.get("location")
    if not isinstance(location, Mapping) or set(location) != {
        "center_wgs84",
        "aoi_bbox_wgs84",
        "aoi_half_side_km",
        "part_index",
        "part_count",
    }:
        raise QueueValidationError(f"{label} location schema is invalid")
    center = location.get("center_wgs84")
    if not isinstance(center, Mapping) or set(center) != {
        "latitude",
        "longitude",
        "method",
    }:
        raise QueueValidationError(f"{label} center schema is invalid")
    latitude = _coordinate(center.get("latitude"), f"{label} latitude", -90, 90)
    longitude = _coordinate(center.get("longitude"), f"{label} longitude", -180, 180)
    coordinate_method = center.get("method")
    if coordinate_method not in {
        "properties.latitude_longitude",
        "geometry_bounds_center",
    }:
        raise QueueValidationError(f"{label} coordinate method is invalid")
    half_side = _positive_number(
        location.get("aoi_half_side_km"), f"{label} aoi_half_side_km"
    )
    if half_side != config.aoi_half_side_km:
        raise QueueValidationError(f"{label} AOI size differs from manifest")
    bbox_value = location.get("aoi_bbox_wgs84")
    if not isinstance(bbox_value, list) or len(bbox_value) != 4:
        raise QueueValidationError(f"{label} bbox must contain four coordinates")
    bbox = tuple(
        _coordinate(
            coordinate,
            f"{label} bbox coordinate {index}",
            -180 if index in {0, 2} else -90,
            180 if index in {0, 2} else 90,
        )
        for index, coordinate in enumerate(bbox_value)
    )
    west, south, east, north = bbox
    if not west < east or not south < north:
        raise QueueValidationError(f"{label} bbox is not non-wrapping and ordered")
    part_index = location.get("part_index")
    part_count = location.get("part_count")
    if (
        isinstance(part_index, bool)
        or not isinstance(part_index, int)
        or isinstance(part_count, bool)
        or not isinstance(part_count, int)
        or not 1 <= part_index <= part_count
    ):
        raise QueueValidationError(f"{label} AOI part numbering is invalid")
    expected_bboxes = _aoi_bboxes(latitude, longitude, half_side)
    if part_count != len(expected_bboxes) or bbox != expected_bboxes[part_index - 1]:
        raise QueueValidationError(f"{label} bbox does not match its center and AOI size")
    expected = _job_record(
        entity=entity,
        latitude=latitude,
        longitude=longitude,
        coordinate_method=str(coordinate_method),
        bbox=bbox,
        part_index=part_index,
        part_count=part_count,
        status=status,
        priority_rank=rank,
        priority_tier=tier,
        priority_reason=reason,
        status_freshness=expected_freshness,
        config=config,
    )
    expected["queue_position"] = position
    if _canonical_line(value) != _canonical_line(expected):
        raise QueueValidationError(f"{label} does not match the deterministic job schema")
    return expected


def _bundle_file(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.is_file() or path.is_symlink():
        raise QueueValidationError(f"queue bundle {name} must be a regular file")
    if directory.resolve() not in path.resolve().parents:
        raise QueueValidationError(f"queue bundle {name} escapes its directory")
    return path


def validate_queue_bundle(path: str | Path) -> Mapping[str, Any]:
    """Strictly verify a closed-world satellite review queue bundle."""
    directory = Path(path)
    if not directory.is_dir() or directory.is_symlink():
        raise QueueValidationError(f"queue bundle is not a regular directory: {directory}")
    entries = list(directory.iterdir())
    names = {entry.name for entry in entries}
    if names != QUEUE_BUNDLE_FILES or len(entries) != len(QUEUE_BUNDLE_FILES):
        missing = sorted(QUEUE_BUNDLE_FILES - names)
        extra = sorted(names - QUEUE_BUNDLE_FILES)
        raise QueueValidationError(
            f"queue bundle file set is invalid; missing={missing}, extra={extra}"
        )
    queue_path = _bundle_file(directory, QUEUE_FILENAME)
    manifest_path = _bundle_file(directory, MANIFEST_FILENAME)
    sidecar_path = _bundle_file(directory, MANIFEST_HASH_FILENAME)
    queue_raw = queue_path.read_bytes()
    manifest_raw = manifest_path.read_bytes()
    sidecar_raw = sidecar_path.read_bytes()
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise QueueValidationError("queue manifest SHA-256 sidecar does not match exact bytes")
    manifest = _decode_json_object(manifest_raw, "queue manifest")
    if manifest_raw != _manifest_bytes(manifest):
        raise QueueValidationError("queue manifest is not canonical pretty JSON")
    if set(manifest) != _MANIFEST_KEYS:
        raise QueueValidationError("queue manifest schema has unexpected fields")
    if (
        manifest.get("schema_version") != QUEUE_SCHEMA_VERSION
        or manifest.get("pipeline") != "global_satellite_review_queue"
    ):
        raise QueueValidationError("queue manifest identity is invalid")
    if manifest.get("generated_at") != _timestamp(
        manifest.get("generated_at"), "queue manifest generated_at"
    ):
        raise QueueValidationError("queue manifest generated_at is not canonical UTC")
    if manifest.get("scope") != QUEUE_SCOPE:
        raise QueueValidationError("queue manifest scope safeguards changed")
    if _canonical_line({"policy": manifest.get("priority_policy")}) != _canonical_line(
        {"policy": list(PRIORITY_POLICY)}
    ):
        raise QueueValidationError("queue manifest priority policy changed")
    if manifest.get("ordering_policy") != QUEUE_ORDERING_POLICY:
        raise QueueValidationError("queue manifest ordering policy changed")
    source = manifest.get("source")
    if not isinstance(source, Mapping) or set(source) != _SOURCE_KEYS:
        raise QueueValidationError("queue manifest source schema is invalid")
    source_file = _required_text(source.get("file"), "queue manifest source file")
    if Path(source_file).name != source_file:
        raise QueueValidationError("queue manifest source file must be a basename")
    _nonnegative_integer(source.get("bytes"), "queue manifest source bytes")
    _sha256_value(source.get("sha256"), "queue manifest source sha256")
    atlas_as_of = _calendar_date(
        source.get("atlas_as_of"), "queue manifest atlas_as_of"
    )
    if source.get("atlas_as_of") != atlas_as_of.isoformat():
        raise QueueValidationError("queue manifest atlas_as_of is not canonical")
    if source.get("atlas_recorded_at") is not None and source[
        "atlas_recorded_at"
    ] != _timestamp(source["atlas_recorded_at"], "queue manifest atlas_recorded_at"):
        raise QueueValidationError("queue manifest atlas_recorded_at is not canonical UTC")
    attribution = source.get("attribution")
    if not isinstance(attribution, list) or not all(
        isinstance(item, str) for item in attribution
    ):
        raise QueueValidationError("queue manifest attribution must be an array of strings")
    release_lineage = source.get("release_manifest")
    if release_lineage is not None:
        release_lineage = _validate_release_manifest_lineage(release_lineage)
        if (
            release_lineage["atlas_file"] != source_file
            or release_lineage["atlas_bytes"] != source["bytes"]
            or release_lineage["atlas_sha256"] != source["sha256"]
        ):
            raise QueueValidationError(
                "queue release-manifest lineage does not match source atlas identity"
            )
    config = _queue_config_from_manifest(manifest.get("configuration"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {QUEUE_FILENAME}:
        raise QueueValidationError("queue manifest artifact inventory is invalid")
    queue_checkpoint = artifacts[QUEUE_FILENAME]
    if not isinstance(queue_checkpoint, Mapping) or set(queue_checkpoint) != {
        "format",
        "records",
        "bytes",
        "sha256",
    }:
        raise QueueValidationError("queue artifact checkpoint schema is invalid")
    if queue_checkpoint.get("format") != "application/x-ndjson":
        raise QueueValidationError("queue artifact format is invalid")
    record_count = _nonnegative_integer(
        queue_checkpoint.get("records"), "queue artifact record count"
    )
    queue_byte_count = _nonnegative_integer(
        queue_checkpoint.get("bytes"), "queue artifact byte count"
    )
    if queue_byte_count != len(queue_raw):
        raise QueueValidationError("queue artifact byte count does not match")
    if queue_checkpoint.get("sha256") != hashlib.sha256(queue_raw).hexdigest():
        raise QueueValidationError("queue artifact SHA-256 does not match")
    if queue_raw and not queue_raw.endswith(b"\n"):
        raise QueueValidationError("queue JSONL must end with a newline")
    lines = queue_raw.splitlines(keepends=True)
    if len(lines) != record_count:
        raise QueueValidationError("queue JSONL record count does not match manifest")
    records: list[dict[str, Any]] = []
    queue_ids: set[str] = set()
    for position, line in enumerate(lines, start=1):
        if not line.endswith(b"\n") or line in {b"\n", b"\r\n"}:
            raise QueueValidationError(f"queue record {position} line framing is invalid")
        record = _decode_json_object(line[:-1], f"queue record {position}")
        if line != _canonical_line(record):
            raise QueueValidationError(f"queue record {position} is not canonical JSONL")
        queue_id = _required_text(record.get("queue_id"), f"queue record {position} queue_id")
        if queue_id in queue_ids:
            raise QueueValidationError(f"duplicate queue_id: {queue_id}")
        queue_ids.add(queue_id)
        validated = _validate_job_record(
            record, position=position, config=config, atlas_as_of=atlas_as_of
        )
        records.append(validated)
    order = [
        (
            record["priority"]["rank"],
            *_freshness_order(record["status_freshness"]),
            record["entity"]["id"],
            record["location"]["part_index"],
        )
        for record in records
    ]
    if order != sorted(order):
        raise QueueValidationError("queue records are not in deterministic priority order")
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["entity"]["id"], []).append(record)
    for entity_id, entity_records in groups.items():
        expected_count = entity_records[0]["location"]["part_count"]
        if (
            len(entity_records) != expected_count
            or {record["location"]["part_index"] for record in entity_records}
            != set(range(1, expected_count + 1))
        ):
            raise QueueValidationError(f"entity {entity_id} AOI parts are incomplete")
        invariant = {
            "entity": entity_records[0]["entity"],
            "priority": entity_records[0]["priority"],
            "status_freshness": entity_records[0]["status_freshness"],
            "center": entity_records[0]["location"]["center_wgs84"],
            "half_side": entity_records[0]["location"]["aoi_half_side_km"],
        }
        for record in entity_records[1:]:
            if invariant != {
                "entity": record["entity"],
                "priority": record["priority"],
                "status_freshness": record["status_freshness"],
                "center": record["location"]["center_wgs84"],
                "half_side": record["location"]["aoi_half_side_km"],
            }:
                raise QueueValidationError(f"entity {entity_id} AOI parts disagree")
    counts = manifest.get("counts")
    expected_count_keys = {
        "features_examined",
        "eligible_features_by_kind",
        "excluded_features_by_kind",
        "skipped_missing_coordinates",
        "entities_queued",
        "queue_jobs",
        "entities_split_at_antimeridian",
        "queued_entities_by_priority_tier",
        "queued_entities_by_country_priority_tier",
        "queued_entities_by_status_freshness",
    }
    if not isinstance(counts, Mapping) or set(counts) != expected_count_keys:
        raise QueueValidationError("queue manifest count schema is invalid")
    eligible_counts = counts.get("eligible_features_by_kind")
    excluded_counts = counts.get("excluded_features_by_kind")
    tier_counts = counts.get("queued_entities_by_priority_tier")
    country_counts = counts.get("queued_entities_by_country_priority_tier")
    freshness_counts = counts.get("queued_entities_by_status_freshness")
    for value, label, allowed in (
        (eligible_counts, "eligible kind counts", ELIGIBLE_ENTITY_KINDS),
        (excluded_counts, "excluded kind counts", KNOWN_ENTITY_KINDS - ELIGIBLE_ENTITY_KINDS),
        (
            tier_counts,
            "priority tier counts",
            {policy["tier"] for policy in PRIORITY_POLICY},
        ),
    ):
        if not isinstance(value, Mapping) or not set(value).issubset(allowed):
            raise QueueValidationError(f"queue manifest {label} are invalid")
        for key, count in value.items():
            _nonnegative_integer(count, f"queue manifest {label} {key}")
    if not isinstance(country_counts, list):
        raise QueueValidationError("queue manifest country/tier counts are invalid")
    normalized_country_counts: list[dict[str, Any]] = []
    country_identities: set[tuple[str | None, str | None, str | None]] = set()
    allowed_tiers = {policy["tier"] for policy in PRIORITY_POLICY}
    for index, row in enumerate(country_counts):
        label = f"queue manifest country/tier count {index}"
        if not isinstance(row, Mapping) or set(row) != {
            "country",
            "country_iso_a2",
            "country_iso_a3",
            "entities",
            "by_priority_tier",
        }:
            raise QueueValidationError(f"{label} schema is invalid")
        identity = (
            _optional_text(row.get("country"), f"{label} country"),
            _iso_code(row.get("country_iso_a2"), f"{label} country_iso_a2", 2),
            _iso_code(row.get("country_iso_a3"), f"{label} country_iso_a3", 3),
        )
        if identity in country_identities:
            raise QueueValidationError(f"{label} duplicates a country identity")
        country_identities.add(identity)
        entities = _nonnegative_integer(row.get("entities"), f"{label} entities")
        by_tier = row.get("by_priority_tier")
        if (
            entities == 0
            or not isinstance(by_tier, Mapping)
            or not by_tier
            or not set(by_tier).issubset(allowed_tiers)
        ):
            raise QueueValidationError(f"{label} priority-tier counts are invalid")
        for tier, count in by_tier.items():
            if _nonnegative_integer(count, f"{label} tier {tier}") == 0:
                raise QueueValidationError(f"{label} contains a zero tier count")
        if entities != sum(by_tier.values()):
            raise QueueValidationError(f"{label} counts do not reconcile")
        normalized_country_counts.append(
            {
                "country": identity[0],
                "country_iso_a2": identity[1],
                "country_iso_a3": identity[2],
                "entities": entities,
                "by_priority_tier": dict(sorted(by_tier.items())),
            }
        )
    if country_counts != sorted(
        normalized_country_counts,
        key=lambda row: _country_sort_key(
            (row["country"], row["country_iso_a2"], row["country_iso_a3"])
        ),
    ):
        raise QueueValidationError("queue manifest country/tier counts are not canonical")
    if not isinstance(freshness_counts, Mapping) or set(
        freshness_counts
    ) != set(STATUS_FRESHNESS_BUCKETS):
        raise QueueValidationError("queue manifest freshness counts are invalid")
    for bucket in STATUS_FRESHNESS_BUCKETS:
        _nonnegative_integer(
            freshness_counts[bucket], f"queue manifest freshness count {bucket}"
        )
    missing_coordinates = _nonnegative_integer(
        counts.get("skipped_missing_coordinates"),
        "queue manifest skipped_missing_coordinates",
    )
    entities_queued = _nonnegative_integer(
        counts.get("entities_queued"), "queue manifest entities_queued"
    )
    queue_jobs = _nonnegative_integer(
        counts.get("queue_jobs"), "queue manifest queue_jobs"
    )
    split_entities = _nonnegative_integer(
        counts.get("entities_split_at_antimeridian"),
        "queue manifest entities_split_at_antimeridian",
    )
    features_examined = _nonnegative_integer(
        counts.get("features_examined"), "queue manifest features_examined"
    )
    actual_tiers: dict[str, int] = {}
    actual_country_tiers: dict[
        tuple[str | None, str | None, str | None], dict[str, int]
    ] = {}
    actual_freshness = {bucket: 0 for bucket in STATUS_FRESHNESS_BUCKETS}
    for entity_records in groups.values():
        tier = entity_records[0]["priority"]["tier"]
        actual_tiers[tier] = actual_tiers.get(tier, 0) + 1
        entity = entity_records[0]["entity"]
        country_tiers = actual_country_tiers.setdefault(_country_identity(entity), {})
        country_tiers[tier] = country_tiers.get(tier, 0) + 1
        bucket = _freshness_bucket(entity_records[0]["status_freshness"])
        actual_freshness[bucket] += 1
    if (
        queue_jobs != len(records)
        or entities_queued != len(groups)
        or split_entities != sum(len(group) > 1 for group in groups.values())
        or dict(sorted(tier_counts.items())) != dict(sorted(actual_tiers.items()))
        or country_counts != _country_count_rows(actual_country_tiers)
        or dict(freshness_counts) != actual_freshness
        or sum(eligible_counts.values()) != entities_queued + missing_coordinates
        or features_examined
        != sum(eligible_counts.values()) + sum(excluded_counts.values())
    ):
        raise QueueValidationError("queue manifest counts do not reconcile")
    return manifest


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise QueueValidationError(f"output directory may not be a symlink: {path.parent}")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def _bundle_payloads(bundle: QueueBundle) -> dict[str, bytes]:
    return {
        QUEUE_FILENAME: bundle.queue_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _adjacent_release_manifest_lineage(
    source: Path, source_raw: bytes
) -> dict[str, Any] | None:
    release_manifest = source.with_name("manifest.json")
    if not release_manifest.exists():
        if release_manifest.is_symlink():
            raise QueueValidationError("adjacent release manifest is a broken symlink")
        return None
    if not release_manifest.is_file() or release_manifest.is_symlink():
        raise QueueValidationError("adjacent release manifest must be a regular file")
    manifest_raw = release_manifest.read_bytes()
    try:
        manifest_text = manifest_raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise QueueValidationError("adjacent release manifest must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise QueueValidationError(
            f"adjacent release manifest contains non-finite number {value}"
        )

    try:
        document = json.loads(manifest_text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise QueueValidationError("adjacent release manifest is not valid JSON") from error
    if not isinstance(document, Mapping):
        raise QueueValidationError("adjacent release manifest must contain an object")
    files = document.get("files")
    if not isinstance(files, Mapping):
        raise QueueValidationError("adjacent release manifest has no files object")
    checkpoint = files.get(source.name)
    if not isinstance(checkpoint, Mapping):
        raise QueueValidationError(
            f"adjacent release manifest does not bind {source.name}"
        )
    if set(checkpoint) != {"bytes", "sha256"}:
        raise QueueValidationError(
            f"adjacent release manifest {source.name} entry has unexpected fields"
        )
    expected_bytes = _nonnegative_integer(
        checkpoint.get("bytes"), f"release manifest {source.name} bytes"
    )
    expected_sha256 = _sha256_value(
        checkpoint.get("sha256"), f"release manifest {source.name} sha256"
    )
    actual_sha256 = hashlib.sha256(source_raw).hexdigest()
    if expected_bytes != len(source_raw) or expected_sha256 != actual_sha256:
        raise QueueValidationError(
            f"adjacent release manifest does not match exact {source.name} bytes"
        )
    return _validate_release_manifest_lineage(
        {
            "file": "manifest.json",
            "bytes": len(manifest_raw),
            "sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "format": document.get("format"),
            "as_of": document.get("as_of"),
            "recorded_at": document.get("recorded_at"),
            "atlas_file": source.name,
            "atlas_bytes": len(source_raw),
            "atlas_sha256": actual_sha256,
        }
    )


def write_queue_bundle(
    input_path: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
    config: QueueConfig,
) -> Mapping[str, Any]:
    """Publish one validated, immutable offline queue bundle atomically."""
    source = Path(input_path)
    if not source.is_file() or source.is_symlink():
        raise QueueValidationError(f"atlas GeoJSON is not a regular file: {source}")
    raw = source.read_bytes()
    release_manifest_lineage = _adjacent_release_manifest_lineage(source, raw)
    bundle = build_queue_bundle(
        raw,
        source_name=source.name,
        generated_at=generated_at,
        config=config,
        release_manifest_lineage=release_manifest_lineage,
    )
    output = Path(output_directory)
    if output.is_symlink():
        raise QueueValidationError(f"queue output may not be a symlink: {output}")
    expected = _bundle_payloads(bundle)
    if output.exists():
        if not output.is_dir():
            raise QueueValidationError(
                f"queue output is not a regular directory: {output}"
            )
        validate_queue_bundle(output)
        differing = [
            name for name, raw_bytes in expected.items()
            if (output / name).read_bytes() != raw_bytes
        ]
        if differing:
            raise QueueValidationError(
                "existing queue bundle is valid but not byte-identical; "
                f"refusing to replace: {sorted(differing)}"
            )
        return bundle.manifest

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir() or parent.is_symlink():
        raise QueueValidationError(
            f"queue output parent is not a regular directory: {parent}"
        )
    if not output.name:
        raise QueueValidationError("queue output must have a directory basename")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent)
    )
    try:
        for name, raw_bytes in expected.items():
            _write_atomic(staging / name, raw_bytes)
        validate_queue_bundle(staging)
        if output.exists() or output.is_symlink():
            raise QueueValidationError(
                f"queue output appeared during publication: {output}"
            )
        os.rename(staging, output)
        _fsync_directory(parent)
    except Exception:
        if staging.exists() and staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise
    return bundle.manifest
