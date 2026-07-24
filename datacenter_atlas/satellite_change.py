"""Deterministic Sentinel-2 change proposals for analyst review.

The numerical functions import NumPy lazily so the core registry remains usable
without geospatial extras.  Outputs from this module are evidence proposals,
never data-centre identity decisions.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


ALGORITHM_VERSION = "sentinel-2-l2a-change-v2"
REPORT_SCHEMA_VERSION = "1.1"
CLEAR_SCL_CLASSES = frozenset({4, 5, 6, 7})
REQUIRED_ASSETS = ("red", "green", "blue", "nir", "swir16", "scl")
EARTH_SEARCH_ASSET_POLICY_ID = "earth-search-sentinel-cogs-v1"
EARTH_SEARCH_ASSET_HOST = "sentinel-cogs.s3.us-west-2.amazonaws.com"
EARTH_SEARCH_ASSET_PATH_PREFIX = "/sentinel-s2-l2a-cogs/"
SENTINEL_DATA_LEGAL_NOTICE_URL = (
    "https://sentinels.copernicus.eu/documents/247904/690755/"
    "Sentinel_Data_Legal_Notice"
)
REPORT_SOURCE_BASE = {
    "catalog": "Element 84 Earth Search v1",
    "catalog_url": "https://earth-search.aws.element84.com/v1",
    "dataset": "Copernicus Sentinel-2 Level-2A",
    "license_url": SENTINEL_DATA_LEGAL_NOTICE_URL,
    "asset_url_policy": EARTH_SEARCH_ASSET_POLICY_ID,
    "asset_host": EARTH_SEARCH_ASSET_HOST,
    "asset_path_prefix": EARTH_SEARCH_ASSET_PATH_PREFIX,
}


def parse_bbox(value: str | Sequence[float]) -> tuple[float, float, float, float]:
    """Parse and validate a WGS84 ``west,south,east,north`` bounding box."""

    if isinstance(value, str):
        parts: Sequence[str | float] = [part.strip() for part in value.split(",")]
    else:
        parts = value
    if len(parts) != 4:
        raise ValueError("bbox must contain west,south,east,north")
    try:
        west, south, east, north = (float(part) for part in parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox values must be finite numbers") from exc
    if not all(isfinite(number) for number in (west, south, east, north)):
        raise ValueError("bbox values must be finite numbers")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be ordered WGS84 coordinates")
    return west, south, east, north


def canonical_sha256(value: object) -> str:
    """Hash a JSON-compatible value with a stable canonical encoding."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def select_feature(document: Mapping[str, Any], item_id: str) -> Mapping[str, Any]:
    """Select a single STAC item from a Feature or FeatureCollection document."""

    if document.get("type") == "Feature":
        features: Iterable[Mapping[str, Any]] = (document,)
    elif document.get("type") == "FeatureCollection":
        raw_features = document.get("features")
        if not isinstance(raw_features, list):
            raise ValueError("FeatureCollection.features must be an array")
        features = raw_features
    else:
        raise ValueError("expected a STAC Feature or FeatureCollection")

    matches = [feature for feature in features if feature.get("id") == item_id]
    if not matches:
        raise ValueError(f"STAC item not found: {item_id}")
    if len(matches) != 1:
        raise ValueError(f"STAC item is not unique: {item_id}")
    feature = matches[0]
    validate_item(feature)
    return feature


def validate_asset_href(href: str) -> None:
    """Accept only the public Earth Search Sentinel-2 COG namespace."""

    if not isinstance(href, str) or not href.startswith(
        f"https://{EARTH_SEARCH_ASSET_HOST}/"
    ):
        raise ValueError("asset href must use the approved Earth Search HTTPS host")
    parsed = urlsplit(href)
    if parsed.scheme != "https" or parsed.netloc != EARTH_SEARCH_ASSET_HOST:
        raise ValueError("asset href must use the exact approved HTTPS origin")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise ValueError("asset href credentials and ports are not allowed")
    if parsed.query or parsed.fragment:
        raise ValueError("asset href query strings and fragments are not allowed")
    if not parsed.path.startswith(EARTH_SEARCH_ASSET_PATH_PREFIX):
        raise ValueError("asset href is outside the Sentinel-2 L2A COG path")
    if (
        "%" in parsed.path
        or "\\" in parsed.path
        or "//" in parsed.path
        or not re.fullmatch(r"/[A-Za-z0-9._~/-]+", parsed.path)
        or any(part in {"", ".", ".."} for part in parsed.path.split("/")[1:])
    ):
        raise ValueError("asset href path is not canonical and traversal-free")


def _acquisition_year(item: Mapping[str, Any]) -> int:
    value = item.get("properties", {}).get("datetime")
    if not isinstance(value, str):
        raise ValueError("STAC item properties.datetime is required for attribution")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("STAC item properties.datetime must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("STAC item properties.datetime must include a timezone")
    return parsed.year


def report_source(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Build exact legal attribution from the selected acquisition years."""

    years = sorted({_acquisition_year(baseline), _acquisition_year(current)})
    return {
        **REPORT_SOURCE_BASE,
        "attribution_notices": [
            f"Contains modified Copernicus Sentinel data {year}" for year in years
        ],
    }


def validate_item(item: Mapping[str, Any]) -> None:
    """Validate the minimum Sentinel-2 STAC shape needed by the processor."""

    if not isinstance(item.get("id"), str) or not item["id"].strip():
        raise ValueError("STAC item id is required")
    properties = item.get("properties")
    if not isinstance(properties, Mapping) or not isinstance(properties.get("datetime"), str):
        raise ValueError(f"STAC item {item['id']} is missing properties.datetime")
    assets = item.get("assets")
    if not isinstance(assets, Mapping):
        raise ValueError(f"STAC item {item['id']} is missing assets")
    for key in REQUIRED_ASSETS:
        asset = assets.get(key)
        if not isinstance(asset, Mapping) or not isinstance(asset.get("href"), str):
            raise ValueError(f"STAC item {item['id']} is missing asset {key}")
        try:
            validate_asset_href(asset["href"])
        except ValueError as error:
            raise ValueError(
                f"STAC item {item['id']} asset {key} has an unsafe href: {error}"
            ) from error


def mgrs_tile(item: Mapping[str, Any]) -> str | None:
    properties = item.get("properties", {})
    zone = properties.get("mgrs:utm_zone")
    band = properties.get("mgrs:latitude_band")
    square = properties.get("mgrs:grid_square")
    if zone is None or not band or not square:
        return None
    return f"{zone}{band}{square}"


def asset_scale_offset(item: Mapping[str, Any], asset_name: str) -> tuple[float, float]:
    """Return STAC raster scale/offset, falling back only to identity."""

    asset = item["assets"][asset_name]
    bands = asset.get("raster:bands")
    if isinstance(bands, list) and bands and isinstance(bands[0], Mapping):
        scale = float(bands[0].get("scale", 1.0))
        offset = float(bands[0].get("offset", 0.0))
        if not isfinite(scale) or not isfinite(offset) or scale <= 0:
            raise ValueError(f"invalid raster scale/offset for asset {asset_name}")
        return scale, offset
    return 1.0, 0.0


def item_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return compact provider-bound lineage for auditing a scene read."""

    properties = item["properties"]
    return {
        "id": item["id"],
        "collection": item.get("collection"),
        "datetime": properties["datetime"],
        "cloud_cover": properties.get("eo:cloud_cover"),
        "processing_baseline": properties.get("s2:processing_baseline"),
        "mgrs_tile": mgrs_tile(item),
        "assets": {
            key: {
                "href": item["assets"][key]["href"],
                "scale": asset_scale_offset(item, key)[0],
                "offset": asset_scale_offset(item, key)[1],
            }
            for key in REQUIRED_ASSETS
        },
        "stac_item_sha256": canonical_sha256(item),
    }


def ensure_comparable(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    """Reject scene pairs that cannot share a deterministic pixel grid."""

    validate_item(baseline)
    validate_item(current)
    baseline_tile = mgrs_tile(baseline)
    current_tile = mgrs_tile(current)
    if baseline_tile and current_tile and baseline_tile != current_tile:
        raise ValueError(
            f"scene MGRS tiles differ: baseline={baseline_tile}, current={current_tile}"
        )
    if baseline["properties"]["datetime"] >= current["properties"]["datetime"]:
        raise ValueError("baseline datetime must precede current datetime")


def derive_change(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    valid_mask: Any,
    *,
    minimum_absolute_change: float = 0.08,
    quantile: float = 0.90,
) -> dict[str, Any]:
    """Calculate auditable indices and a conservative large-change proposal mask.

    ``baseline`` and ``current`` contain co-registered reflectance arrays for
    red, green, blue, nir and swir16.  Arrays are expected to be floating point
    surface reflectance after each asset's STAC scale and offset are applied.
    """

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised by the CLI message
        raise RuntimeError("satellite change processing requires NumPy") from exc

    def nd(a: Any, b: Any) -> Any:
        # Atmospheric correction can yield small negative surface-reflectance
        # values.  Clipping only for normalized indices preserves their
        # physical [-1, 1] range; absolute band change still uses the original
        # scaled reflectance arrays.
        a = np.maximum(a, 0)
        b = np.maximum(b, 0)
        denominator = a + b
        return np.divide(
            a - b,
            denominator,
            out=np.zeros_like(denominator, dtype=np.float32),
            where=denominator > 1e-6,
        )

    required_reflectance = ("red", "green", "blue", "nir", "swir16")
    for name, scene in (("baseline", baseline), ("current", current)):
        missing = sorted(set(required_reflectance) - set(scene))
        if missing:
            raise ValueError(f"{name} scene is missing bands: {', '.join(missing)}")

    baseline_stack = np.stack([baseline[key] for key in required_reflectance])
    current_stack = np.stack([current[key] for key in required_reflectance])
    valid = np.asarray(valid_mask, dtype=bool)
    if valid.shape != baseline_stack.shape[1:] or current_stack.shape != baseline_stack.shape:
        raise ValueError("scene bands and valid mask must share one pixel grid")
    valid &= np.isfinite(baseline_stack).all(axis=0)
    valid &= np.isfinite(current_stack).all(axis=0)
    if not valid.any():
        raise ValueError("scene pair has no mutually valid pixels")

    baseline_ndvi = nd(baseline["nir"], baseline["red"])
    current_ndvi = nd(current["nir"], current["red"])
    baseline_ndbi = nd(baseline["swir16"], baseline["nir"])
    current_ndbi = nd(current["swir16"], current["nir"])
    absolute_change = np.mean(np.abs(current_stack - baseline_stack), axis=0)
    ndvi_change = current_ndvi - baseline_ndvi
    ndbi_change = current_ndbi - baseline_ndbi
    brightness_change = np.mean(current_stack[:3] - baseline_stack[:3], axis=0)

    adaptive = float(np.quantile(absolute_change[valid], quantile))
    threshold = max(float(minimum_absolute_change), adaptive)
    material_transition = (
        (ndvi_change <= -0.12)
        | (ndbi_change >= 0.12)
        | (np.abs(brightness_change) >= 0.10)
    )
    proposal = valid & (absolute_change >= threshold) & material_transition

    def valid_mean(array: Any) -> float:
        return float(np.mean(array[valid]))

    return {
        "baseline_ndvi": baseline_ndvi,
        "current_ndvi": current_ndvi,
        "baseline_ndbi": baseline_ndbi,
        "current_ndbi": current_ndbi,
        "absolute_change": absolute_change,
        "ndvi_change": ndvi_change,
        "ndbi_change": ndbi_change,
        "brightness_change": brightness_change,
        "proposal_mask": proposal,
        "valid_mask": valid,
        "thresholds": {
            "minimum_absolute_reflectance_change": float(minimum_absolute_change),
            "adaptive_quantile": float(quantile),
            "adaptive_absolute_reflectance_change": adaptive,
            "applied_absolute_reflectance_change": threshold,
            "ndvi_loss": -0.12,
            "ndbi_gain": 0.12,
            "absolute_brightness_change": 0.10,
        },
        "metrics": {
            "valid_pixel_fraction": float(valid.mean()),
            "proposal_pixel_fraction_of_valid": float(proposal.sum() / valid.sum()),
            "mean_baseline_ndvi": valid_mean(baseline_ndvi),
            "mean_current_ndvi": valid_mean(current_ndvi),
            "mean_ndvi_change": valid_mean(ndvi_change),
            "mean_ndbi_change": valid_mean(ndbi_change),
            "mean_absolute_reflectance_change": valid_mean(absolute_change),
        },
    }
