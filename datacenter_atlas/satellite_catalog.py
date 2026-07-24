"""Deterministic Sentinel-2 STAC query, normalization, and scene planning.

This module deliberately stops at catalog planning.  It does not make network
requests or interpret visible change as the identity of a facility.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Mapping, Sequence


EARTH_SEARCH_V1_ENDPOINT = "https://earth-search.aws.element84.com/v1/search"
COPERNICUS_STAC_ENDPOINT = "https://stac.dataspace.copernicus.eu/v1/search"
SENTINEL_2_L2A_COLLECTION = "sentinel-2-l2a"

OUTPUT_LABELS = ("imagery_evidence", "visible_change_proposal")
SCOPE_NOTE = (
    "Visible-surface imagery evidence and change proposals require independent "
    "corroboration for facility identity."
)


class CatalogValidationError(ValueError):
    """Raised when a query, STAC response, or selection is invalid."""


class Provider(str, Enum):
    EARTH_SEARCH = "earth-search-v1"
    COPERNICUS = "copernicus-data-space"


@dataclass(frozen=True, slots=True)
class _ProviderConfig:
    endpoint: str
    collection: str
    default_license: str
    default_license_url: str
    default_attribution: str


_PROVIDERS = {
    Provider.EARTH_SEARCH: _ProviderConfig(
        endpoint=EARTH_SEARCH_V1_ENDPOINT,
        collection=SENTINEL_2_L2A_COLLECTION,
        default_license="proprietary",
        default_license_url=(
            "https://sentinel.esa.int/documents/247904/690755/"
            "Sentinel_Data_Legal_Notice"
        ),
        default_attribution="Contains modified Copernicus Sentinel data",
    ),
    Provider.COPERNICUS: _ProviderConfig(
        endpoint=COPERNICUS_STAC_ENDPOINT,
        collection=SENTINEL_2_L2A_COLLECTION,
        default_license="other",
        default_license_url=(
            "https://sentinels.copernicus.eu/documents/247904/690755/"
            "Sentinel_Data_Legal_Notice"
        ),
        default_attribution="Copernicus Sentinel data",
    ),
}


def _provider(value: Provider | str) -> Provider:
    if isinstance(value, Provider):
        return value
    try:
        return Provider(value)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(provider.value for provider in Provider)
        raise CatalogValidationError(f"provider must be one of: {allowed}") from error


def _calendar_date(value: date | str, field: str) -> date:
    if isinstance(value, datetime):
        raise CatalogValidationError(f"{field} must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CatalogValidationError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CatalogValidationError(f"{field} is not a valid calendar date") from error


def _bbox(value: Sequence[float]) -> tuple[float, float, float, float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != 4
    ):
        raise CatalogValidationError("bbox must contain west, south, east, north")
    coordinates: list[float] = []
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise CatalogValidationError("bbox coordinates must be numbers")
        coordinate = float(coordinate)
        if not math.isfinite(coordinate):
            raise CatalogValidationError("bbox coordinates must be finite")
        coordinates.append(coordinate)
    west, south, east, north = coordinates
    if not -180 <= west < east <= 180:
        raise CatalogValidationError(
            "bbox longitude must satisfy -180 <= west < east <= 180"
        )
    if not -90 <= south < north <= 90:
        raise CatalogValidationError(
            "bbox latitude must satisfy -90 <= south < north <= 90"
        )
    return west, south, east, north


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    """A bounded Sentinel-2 search shared by both supported STAC providers."""

    bbox: tuple[float, float, float, float] | Sequence[float]
    start_date: date | str
    end_date: date | str
    max_cloud_cover: float = 20.0
    limit: int = 100

    def __post_init__(self) -> None:
        bounds = _bbox(self.bbox)
        start = _calendar_date(self.start_date, "start_date")
        end = _calendar_date(self.end_date, "end_date")
        if start > end:
            raise CatalogValidationError("start_date must not be after end_date")
        cloud = self.max_cloud_cover
        if isinstance(cloud, bool) or not isinstance(cloud, (int, float)):
            raise CatalogValidationError("max_cloud_cover must be a number")
        cloud = float(cloud)
        if not math.isfinite(cloud) or not 0 <= cloud <= 100:
            raise CatalogValidationError("max_cloud_cover must be between 0 and 100")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise CatalogValidationError("limit must be an integer")
        if not 1 <= self.limit <= 100:
            raise CatalogValidationError("limit must be between 1 and 100")
        object.__setattr__(self, "bbox", bounds)
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)
        object.__setattr__(self, "max_cloud_cover", cloud)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "max_cloud_cover": _compact_number(self.max_cloud_cover),
            "limit": self.limit,
        }


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def build_stac_payload(
    provider: Provider | str, query: CatalogQuery
) -> dict[str, Any]:
    """Build the deterministic JSON body for a STAC Item Search POST."""
    if not isinstance(query, CatalogQuery):
        raise CatalogValidationError("query must be a CatalogQuery")
    selected_provider = _provider(provider)
    collection = _PROVIDERS[selected_provider].collection
    return {
        "collections": [collection],
        "bbox": list(query.bbox),
        "datetime": (
            f"{query.start_date.isoformat()}T00:00:00Z/"
            f"{query.end_date.isoformat()}T23:59:59Z"
        ),
        "query": {
            "eo:cloud_cover": {
                "lte": _compact_number(query.max_cloud_cover),
            }
        },
        "limit": query.limit,
        "sortby": [
            {"field": "properties.datetime", "direction": "asc"},
            {"field": "id", "direction": "asc"},
        ],
    }


def build_stac_request(
    provider: Provider | str, query: CatalogQuery
) -> dict[str, Any]:
    """Return a serializable request plan; no network request is performed."""
    selected_provider = _provider(provider)
    return {
        "method": "POST",
        "url": _PROVIDERS[selected_provider].endpoint,
        "headers": {"Content-Type": "application/json"},
        "payload": build_stac_payload(selected_provider, query),
    }


_ASSET_ALIASES = {
    "B02": ("b02", "b02_10m", "blue"),
    "B03": ("b03", "b03_10m", "green"),
    "B04": ("b04", "b04_10m", "red"),
    "B08": ("b08", "b08_10m", "nir", "nir08"),
    "B11": ("b11", "b11_20m", "swir16", "swir_1"),
    "SCL": ("scl", "scl_20m"),
}
_ALIAS_TO_BAND = {
    alias: band for band, aliases in _ASSET_ALIASES.items() for alias in aliases
}
_MGRS_PATTERN = re.compile(r"(?:^|[_-])(?:MGRS-?|T)?(\d{2}[C-X][A-Z]{2})(?:[_-]|$)")


def _asset_band(key: str, asset: Mapping[str, Any]) -> str | None:
    normalized_key = key.lower().replace("-", "_")
    if normalized_key in _ALIAS_TO_BAND:
        return _ALIAS_TO_BAND[normalized_key]
    candidates: list[str] = []
    title = asset.get("title")
    if isinstance(title, str):
        candidates.append(title)
    bands = asset.get("eo:bands") or asset.get("bands") or []
    if isinstance(bands, list):
        for band in bands:
            if isinstance(band, Mapping):
                for name in (band.get("name"), band.get("common_name")):
                    if isinstance(name, str):
                        candidates.append(name)
    for candidate in candidates:
        normalized = candidate.lower().replace("-", "_").replace(" ", "_")
        if normalized in _ALIAS_TO_BAND:
            return _ALIAS_TO_BAND[normalized]
    return None


def _relevant_assets(value: object, item_index: int) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise CatalogValidationError(f"feature {item_index} assets must be an object")
    choices: dict[str, list[tuple[int, str, str]]] = {}
    for key, asset in value.items():
        if not isinstance(key, str) or not isinstance(asset, Mapping):
            raise CatalogValidationError(f"feature {item_index} has an invalid asset")
        band = _asset_band(key, asset)
        if band is None:
            continue
        href = asset.get("href")
        if not isinstance(href, str) or not href.strip():
            raise CatalogValidationError(
                f"feature {item_index} asset {key!r} requires a non-empty href"
            )
        normalized_key = key.lower().replace("-", "_")
        aliases = _ASSET_ALIASES[band]
        priority = aliases.index(normalized_key) if normalized_key in aliases else len(aliases)
        choices.setdefault(band, []).append((priority, key, href))
    if not choices:
        raise CatalogValidationError(f"feature {item_index} has no relevant Sentinel-2 assets")
    return {
        band: sorted(choices[band], key=lambda option: (option[0], option[1]))[0][2]
        for band in _ASSET_ALIASES
        if band in choices
    }


def _rfc3339(value: object, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{field} must be a non-empty RFC 3339 timestamp")
    if not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value):
        raise CatalogValidationError(f"{field} must include a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CatalogValidationError(f"{field} is not a valid RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise CatalogValidationError(f"{field} must include a timezone")
    utc_value = parsed.astimezone(UTC)
    rendered = utc_value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return rendered, utc_value


def _cloud_cover(value: object, item_index: int) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogValidationError(f"feature {item_index} requires numeric eo:cloud_cover")
    cloud = float(value)
    if not math.isfinite(cloud) or not 0 <= cloud <= 100:
        raise CatalogValidationError(
            f"feature {item_index} eo:cloud_cover must be between 0 and 100"
        )
    return _compact_number(cloud)


def _mgrs_tile(properties: Mapping[str, Any], item_id: str) -> str | None:
    for key in ("s2:mgrs_tile", "mgrs:tile", "grid:code"):
        value = properties.get(key)
        if isinstance(value, str):
            match = re.search(r"(\d{2}[C-X][A-Z]{2})", value.upper())
            if match:
                return match.group(1)
    parts = (
        properties.get("mgrs:utm_zone"),
        properties.get("mgrs:latitude_band"),
        properties.get("mgrs:grid_square"),
    )
    if all(part is not None for part in parts):
        candidate = "".join(str(part) for part in parts).upper()
        if re.fullmatch(r"\d{2}[C-X][A-Z]{2}", candidate):
            return candidate
    match = _MGRS_PATTERN.search(item_id.upper())
    return match.group(1) if match else None


def _text_or_default(value: object, default: str, field: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_feature_collection(
    provider: Provider | str, feature_collection: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Normalize and deterministically sort one STAC FeatureCollection."""
    selected_provider = _provider(provider)
    config = _PROVIDERS[selected_provider]
    if not isinstance(feature_collection, Mapping):
        raise CatalogValidationError("STAC response must be an object")
    if feature_collection.get("type") != "FeatureCollection":
        raise CatalogValidationError("STAC response type must be FeatureCollection")
    features = feature_collection.get("features")
    if not isinstance(features, list):
        raise CatalogValidationError("STAC FeatureCollection features must be an array")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(features):
        if not isinstance(item, Mapping) or item.get("type") != "Feature":
            raise CatalogValidationError(f"feature {index} must be a STAC Feature")
        item_id = item.get("id")
        collection = item.get("collection")
        properties = item.get("properties")
        if not isinstance(item_id, str) or not item_id.strip():
            raise CatalogValidationError(f"feature {index} requires a non-empty id")
        item_id = item_id.strip()
        if item_id in seen:
            raise CatalogValidationError(f"duplicate STAC item id: {item_id}")
        seen.add(item_id)
        if not isinstance(collection, str) or not collection.strip():
            raise CatalogValidationError(f"feature {index} requires a collection")
        collection = collection.strip()
        if collection != config.collection:
            raise CatalogValidationError(
                f"feature {index} collection must be {config.collection!r}"
            )
        if not isinstance(properties, Mapping):
            raise CatalogValidationError(f"feature {index} properties must be an object")
        timestamp, _ = _rfc3339(properties.get("datetime"), f"feature {index} datetime")
        bounds = _bbox(item.get("bbox"))
        license_value = item.get("license", properties.get("license"))
        attribution_value = item.get("attribution", properties.get("attribution"))
        records.append(
            {
                "output_label": OUTPUT_LABELS[0],
                "provider": selected_provider.value,
                "collection": collection,
                "item_id": item_id,
                "datetime": timestamp,
                "cloud_cover": _cloud_cover(properties.get("eo:cloud_cover"), index),
                "bbox": list(bounds),
                "mgrs_tile": _mgrs_tile(properties, item_id),
                "assets": _relevant_assets(item.get("assets"), index),
                "license": _text_or_default(
                    license_value, config.default_license, f"feature {index} license"
                ),
                "license_url": config.default_license_url,
                "attribution": _text_or_default(
                    attribution_value,
                    config.default_attribution,
                    f"feature {index} attribution",
                ),
            }
        )
    return sorted(records, key=lambda record: (record["datetime"], record["item_id"]))


def parse_feature_collection(raw_response: bytes | str) -> Mapping[str, Any]:
    """Decode an exact raw response, rejecting non-JSON and non-object values."""
    if isinstance(raw_response, bytes):
        try:
            text = raw_response.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CatalogValidationError("raw STAC response must be UTF-8") from error
    elif isinstance(raw_response, str):
        text = raw_response
    else:
        raise CatalogValidationError("raw STAC response must be bytes or text")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise CatalogValidationError("raw STAC response is not valid JSON") from error
    if not isinstance(parsed, Mapping):
        raise CatalogValidationError("raw STAC response must contain a JSON object")
    return parsed


def _record_datetime(record: Mapping[str, Any], index: int) -> datetime:
    _, parsed = _rfc3339(record.get("datetime"), f"record {index} datetime")
    return parsed


def _seasonal_distance(first: datetime, second: datetime) -> int:
    first_day = date(2000, first.month, first.day)
    second_day = date(2000, second.month, second.day)
    distance = abs((first_day - second_day).days)
    return min(distance, 366 - distance)


def select_scene_pair(
    records: Sequence[Mapping[str, Any]],
    *,
    baseline_date: date | str,
    current_date: date | str,
    temporal_window_days: int = 45,
) -> dict[str, Mapping[str, Any]]:
    """Select a deterministic before/after pair within bounded date windows.

    Pair ranking, in order, prefers the same known MGRS tile, closest season,
    lowest combined cloud cover, closest targets, then stable timestamps/IDs.
    """
    baseline_target = _calendar_date(baseline_date, "baseline_date")
    current_target = _calendar_date(current_date, "current_date")
    if baseline_target >= current_target:
        raise CatalogValidationError("baseline_date must be before current_date")
    if isinstance(temporal_window_days, bool) or not isinstance(temporal_window_days, int):
        raise CatalogValidationError("temporal_window_days must be an integer")
    if not 0 <= temporal_window_days <= 366:
        raise CatalogValidationError("temporal_window_days must be between 0 and 366")
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise CatalogValidationError("records must be a sequence")

    prepared: list[tuple[Mapping[str, Any], datetime, float, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise CatalogValidationError(f"record {index} must be an object")
        item_id = record.get("item_id")
        provider = record.get("provider")
        cloud = record.get("cloud_cover")
        if not isinstance(item_id, str) or not item_id:
            raise CatalogValidationError(f"record {index} requires item_id")
        if not isinstance(provider, str) or not provider:
            raise CatalogValidationError(f"record {index} requires provider")
        key = provider, item_id
        if key in seen:
            raise CatalogValidationError(f"duplicate normalized record: {provider}/{item_id}")
        seen.add(key)
        timestamp = _record_datetime(record, index)
        cloud_value = float(_cloud_cover(cloud, index))
        tile = record.get("mgrs_tile")
        if tile is not None and (not isinstance(tile, str) or not tile):
            raise CatalogValidationError(f"record {index} mgrs_tile must be text or null")
        prepared.append((record, timestamp, cloud_value, item_id, tile))

    baseline_datetime = datetime.combine(baseline_target, datetime.min.time(), UTC)
    current_datetime = datetime.combine(current_target, datetime.min.time(), UTC)
    baseline_candidates = [
        item
        for item in prepared
        if abs((item[1].date() - baseline_target).days) <= temporal_window_days
    ]
    current_candidates = [
        item
        for item in prepared
        if abs((item[1].date() - current_target).days) <= temporal_window_days
    ]
    if not baseline_candidates:
        raise CatalogValidationError("no scene falls within the baseline temporal window")
    if not current_candidates:
        raise CatalogValidationError("no scene falls within the current temporal window")

    ranked: list[tuple[tuple[Any, ...], Mapping[str, Any], Mapping[str, Any]]] = []
    for baseline in baseline_candidates:
        for current in current_candidates:
            if baseline[1] >= current[1]:
                continue
            same_known_tile = baseline[4] is not None and baseline[4] == current[4]
            target_distance = abs((baseline[1] - baseline_datetime).total_seconds()) + abs(
                (current[1] - current_datetime).total_seconds()
            )
            rank = (
                0 if same_known_tile else 1,
                _seasonal_distance(baseline[1], current[1]),
                baseline[2] + current[2],
                target_distance,
                baseline[1],
                current[1],
                baseline[3],
                current[3],
            )
            ranked.append((rank, baseline[0], current[0]))
    if not ranked:
        raise CatalogValidationError("no chronological scene pair exists in the temporal windows")
    _, baseline_record, current_record = min(ranked, key=lambda option: option[0])
    return {"baseline": baseline_record, "current": current_record}


def _raw_bytes(raw_response: bytes | str) -> bytes:
    if isinstance(raw_response, bytes):
        return raw_response
    if isinstance(raw_response, str):
        return raw_response.encode("utf-8")
    raise CatalogValidationError("raw STAC response must be bytes or text")


def build_manifest(
    provider: Provider | str,
    query: CatalogQuery,
    raw_response: bytes | str,
    *,
    baseline_date: date | str,
    current_date: date | str,
    retrieved_at: str,
    temporal_window_days: int = 45,
) -> dict[str, Any]:
    """Build a provenance manifest from one exact raw STAC response."""
    selected_provider = _provider(provider)
    raw = _raw_bytes(raw_response)
    response = parse_feature_collection(raw)
    records = normalize_feature_collection(selected_provider, response)
    selected = select_scene_pair(
        records,
        baseline_date=baseline_date,
        current_date=current_date,
        temporal_window_days=temporal_window_days,
    )
    retrieved, _ = _rfc3339(retrieved_at, "retrieved_at")
    return {
        "schema_version": 1,
        "output_labels": list(OUTPUT_LABELS),
        "scope_note": SCOPE_NOTE,
        "query": {
            "provider": selected_provider.value,
            "parameters": query.as_dict(),
            "request": build_stac_request(selected_provider, query),
            "selection": {
                "baseline_date": _calendar_date(
                    baseline_date, "baseline_date"
                ).isoformat(),
                "current_date": _calendar_date(current_date, "current_date").isoformat(),
                "temporal_window_days": temporal_window_days,
            },
        },
        "normalized_results": records,
        "selected_ids": {
            "baseline": selected["baseline"]["item_id"],
            "current": selected["current"]["item_id"],
        },
        "retrieved_at": retrieved,
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _validate_query_response(
    records: Sequence[Mapping[str, Any]], query: CatalogQuery, label: str
) -> None:
    if len(records) > query.limit:
        raise CatalogValidationError(
            f"{label} response contains more records than the requested limit"
        )
    west, south, east, north = query.bbox
    for index, record in enumerate(records):
        timestamp = _record_datetime(record, index)
        if not query.start_date <= timestamp.date() <= query.end_date:
            raise CatalogValidationError(
                f"{label} record {record.get('item_id')} falls outside its query dates"
            )
        if float(record["cloud_cover"]) > query.max_cloud_cover:
            raise CatalogValidationError(
                f"{label} record {record.get('item_id')} exceeds the cloud limit"
            )
        item_west, item_south, item_east, item_north = record["bbox"]
        if item_east < west or east < item_west or item_north < south or north < item_south:
            raise CatalogValidationError(
                f"{label} record {record.get('item_id')} does not intersect the query AOI"
            )


def build_pair_manifest(
    provider: Provider | str,
    baseline_query: CatalogQuery,
    baseline_raw_response: bytes | str,
    current_query: CatalogQuery,
    current_raw_response: bytes | str,
    *,
    baseline_date: date | str,
    current_date: date | str,
    retrieved_at: str,
    temporal_window_days: int = 45,
) -> dict[str, Any]:
    """Build a pair manifest from two independently bounded STAC responses.

    Separate windows avoid silently losing the current scene when a multi-year
    query reaches its API item limit.  The exact bytes and query plan for both
    responses remain independently hashed.
    """

    selected_provider = _provider(provider)
    if not isinstance(baseline_query, CatalogQuery) or not isinstance(
        current_query, CatalogQuery
    ):
        raise CatalogValidationError("baseline_query and current_query must be CatalogQuery values")
    if baseline_query.end_date >= current_query.start_date:
        raise CatalogValidationError("baseline and current query windows must not overlap")
    baseline_target = _calendar_date(baseline_date, "baseline_date")
    current_target = _calendar_date(current_date, "current_date")
    if not baseline_query.start_date <= baseline_target <= baseline_query.end_date:
        raise CatalogValidationError("baseline_date must fall within the baseline query")
    if not current_query.start_date <= current_target <= current_query.end_date:
        raise CatalogValidationError("current_date must fall within the current query")

    baseline_raw = _raw_bytes(baseline_raw_response)
    current_raw = _raw_bytes(current_raw_response)
    baseline_records = normalize_feature_collection(
        selected_provider, parse_feature_collection(baseline_raw)
    )
    current_records = normalize_feature_collection(
        selected_provider, parse_feature_collection(current_raw)
    )
    _validate_query_response(baseline_records, baseline_query, "baseline")
    _validate_query_response(current_records, current_query, "current")
    selected = select_scene_pair(
        [*baseline_records, *current_records],
        baseline_date=baseline_target,
        current_date=current_target,
        temporal_window_days=temporal_window_days,
    )
    retrieved, _ = _rfc3339(retrieved_at, "retrieved_at")
    return {
        "schema_version": 1,
        "output_labels": list(OUTPUT_LABELS),
        "scope_note": SCOPE_NOTE,
        "queries": {
            "provider": selected_provider.value,
            "baseline": {
                "parameters": baseline_query.as_dict(),
                "request": build_stac_request(selected_provider, baseline_query),
                "raw_response_sha256": hashlib.sha256(baseline_raw).hexdigest(),
            },
            "current": {
                "parameters": current_query.as_dict(),
                "request": build_stac_request(selected_provider, current_query),
                "raw_response_sha256": hashlib.sha256(current_raw).hexdigest(),
            },
            "selection": {
                "baseline_date": baseline_target.isoformat(),
                "current_date": current_target.isoformat(),
                "temporal_window_days": temporal_window_days,
            },
        },
        "normalized_results": {
            "baseline": baseline_records,
            "current": current_records,
        },
        "selected_ids": {
            "baseline": selected["baseline"]["item_id"],
            "current": selected["current"]["item_id"],
        },
        "retrieved_at": retrieved,
    }


def manifest_json(manifest: Mapping[str, Any]) -> str:
    """Serialize a manifest with stable keys and no platform-dependent spacing."""
    if not isinstance(manifest, Mapping):
        raise CatalogValidationError("manifest must be an object")
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
