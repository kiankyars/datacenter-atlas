"""Bounded Google Open Buildings Temporal v1 review-lane bundles.

The upstream data are annual model rasters, not building footprints or lifecycle
observations.  This module pins the anonymous Google Cloud Storage manifests and
COG generations, reads only one bounded AOI, and emits review-only aggregate
change signals.  It never creates or mutates atlas entities.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


DATASET_ID = "GOOGLE/Research/open-buildings-temporal/v1"
DATASET_VERSION = "v1"
GCS_BUCKET = "open-buildings-temporal-data"
GCS_PREFIX = "v1"
YEARS = tuple(range(2016, 2024))
BANDS = (
    "building_fractional_count",
    "building_height",
    "building_presence",
)
BAND_RANGES = {
    "building_fractional_count": (0.0, 0.0216),
    "building_height": (0.0, 100.0),
    "building_presence": (0.0, 1.0),
}
MISSING_VALUE = -99.0
STORAGE_GRID_RESOLUTION_M = 0.5
EFFECTIVE_RESOLUTION_M = 4.0
DATASET_URL = (
    "https://developers.google.com/earth-engine/datasets/catalog/"
    "GOOGLE_Research_open-buildings-temporal_v1"
)
PROJECT_URL = "https://sites.research.google/gr/open-buildings/temporal/"
DOWNLOAD_NOTEBOOK_URL = (
    "https://github.com/google-research/google-research/blob/master/"
    "building_detection/open_buildings_temporal_download_region_geotiffs.ipynb"
)
SENTINEL_LEGAL_NOTICE_URL = (
    "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice"
)
LICENSE = "CC-BY-4.0"
ATTRIBUTION = (
    "Google Research Open Buildings 2.5D Temporal Dataset (CC BY 4.0); "
    "leverages Copernicus Sentinel-2 data (2015-present)"
)
SCHEMA_VERSION = 1
QUERY_FILENAME = "query.json"
SOURCE_MANIFEST_FILENAME = "manifest.json"
SOURCE_MANIFEST_HASH_FILENAME = "manifest.sha256"
OBSERVATIONS_FILENAME = "annual-observations.jsonl"
DELTAS_FILENAME = "annual-deltas.jsonl"
CANDIDATES_FILENAME = "candidates.jsonl"
ATLAS_PRIORS_FILENAME = "atlas-priors.jsonl"
CANDIDATE_MANIFEST_FILENAME = "manifest.json"
CANDIDATE_MANIFEST_HASH_FILENAME = "manifest.sha256"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_S2_TOKEN_RE = re.compile(r"^[0-9a-f]{1,16}$")

REVIEW_CONSTRAINTS = {
    "purpose": "bounded_annual_building_signal_change_review",
    "bounded_aoi_not_global_coverage": True,
    "candidate_is_not_building_or_data_centre_identity": True,
    "candidate_is_not_lifecycle_or_construction_status": True,
    "candidate_is_not_operating_status": True,
    "candidate_is_not_power_capacity_or_energy": True,
    "candidate_is_not_automatic_atlas_import": True,
    "atlas_cross_reference_is_prior_only_and_non_merging": True,
    "independent_imagery_and_document_review_required": True,
}
SENTINEL_SOURCE_FAMILY_CONSTRAINT = {
    "source_family_key": "sentinel-2-derived/google-open-buildings-temporal-v1",
    "upstream_sensor_provenance_root": "Copernicus Sentinel-2",
    "derived_product": "Google Open Buildings Temporal v1",
    "shared_provenance_root_with_atlas_sentinel_cv_lane": True,
    "independent_corroboration_from_atlas_sentinel_cv_lane": False,
    "must_not_be_counted_as_an_independent_evidence_family": True,
}


class OpenBuildingsTemporalValidationError(ValueError):
    """Raised when a bounded source or candidate bundle fails closed."""


@dataclass(frozen=True, slots=True)
class OpenBuildingsTemporalConfig:
    """One deliberately small AOI and its explicit upstream manifest partition."""

    bbox: tuple[float, float, float, float] = (
        30.8658,
        30.8399,
        30.8699,
        30.8439,
    )
    country_iso3: str = "EGY"
    s2cell_token: str = "15"
    projected_crs: str = "EPSG:32636"
    years: tuple[int, ...] = YEARS
    maximum_aoi_area_km2: float = 1.0
    minimum_fractional_count_delta: float = 5.0
    minimum_presence_mean_delta: float = 0.0
    presence_height_screen: float = 0.5
    atlas_prior_radius_m: float = 2_000.0

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
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings bbox must contain four finite numbers"
            )
        west, south, east, north = (float(value) for value in self.bbox)
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings bbox bounds or ordering are invalid"
            )
        object.__setattr__(self, "bbox", (west, south, east, north))
        if (
            not isinstance(self.country_iso3, str)
            or re.fullmatch(r"[A-Z]{3}", self.country_iso3) is None
        ):
            raise OpenBuildingsTemporalValidationError(
                "country_iso3 must be an uppercase ISO alpha-3 code"
            )
        if (
            not isinstance(self.s2cell_token, str)
            or _S2_TOKEN_RE.fullmatch(self.s2cell_token) is None
        ):
            raise OpenBuildingsTemporalValidationError("invalid S2 cell token")
        if (
            not isinstance(self.projected_crs, str)
            or re.fullmatch(r"EPSG:\d+", self.projected_crs) is None
        ):
            raise OpenBuildingsTemporalValidationError(
                "projected_crs must be EPSG:<code>"
            )
        if self.years != YEARS:
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings Temporal v1 lane requires all annual years 2016-2023"
            )
        numbers = (
            self.maximum_aoi_area_km2,
            self.minimum_fractional_count_delta,
            self.presence_height_screen,
            self.atlas_prior_radius_m,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0
            for value in numbers
        ):
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings numeric configuration must be finite and positive"
            )
        if (
            isinstance(self.minimum_presence_mean_delta, bool)
            or not isinstance(self.minimum_presence_mean_delta, (int, float))
            or not math.isfinite(float(self.minimum_presence_mean_delta))
            or float(self.minimum_presence_mean_delta) < 0
        ):
            raise OpenBuildingsTemporalValidationError(
                "minimum presence delta must be finite and nonnegative"
            )
        if not 0 < float(self.presence_height_screen) <= 1:
            raise OpenBuildingsTemporalValidationError(
                "presence height screen must fall in (0, 1]"
            )
        if _bbox_area_km2(self.bbox) > float(self.maximum_aoi_area_km2):
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings AOI exceeds the configured bounded-area ceiling"
            )

    def selection_document(self) -> dict[str, Any]:
        return {
            "algorithm": "positive_consecutive_year_count_and_presence_signal",
            "minimum_fractional_count_delta": float(
                self.minimum_fractional_count_delta
            ),
            "minimum_presence_mean_delta_exclusive": float(
                self.minimum_presence_mean_delta
            ),
            "thresholds_are_review_queue_heuristics_not_calibrated_probabilities": True,
        }


def _bbox_area_km2(bbox: Sequence[float]) -> float:
    west, south, east, north = (float(value) for value in bbox)
    latitude = math.radians((south + north) / 2)
    width_km = (east - west) * 111.320 * math.cos(latitude)
    height_km = (north - south) * 110.574
    return width_km * height_km


def _canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        return (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _jsonl(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json(record) for record in records)


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenBuildingsTemporalValidationError(
            f"{field} must be a non-empty RFC 3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OpenBuildingsTemporalValidationError(
            f"{field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OpenBuildingsTemporalValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _raw_record(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _write_fsync(path: Path, raw: bytes) -> None:
    with path.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _manifest_filename(config: OpenBuildingsTemporalConfig, year: int) -> str:
    return (
        f"{config.s2cell_token}_{config.projected_crs.replace(':', '_')}_"
        f"{year}_06_30.json"
    )


def _manifest_object_name(config: OpenBuildingsTemporalConfig, year: int) -> str:
    return f"{GCS_PREFIX}/manifests/{_manifest_filename(config, year)}"


def _query_document(
    config: OpenBuildingsTemporalConfig, projected_bbox: Sequence[float]
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline": "google_open_buildings_temporal_bounded_query",
        "dataset": {
            "id": DATASET_ID,
            "version": DATASET_VERSION,
            "bucket": GCS_BUCKET,
            "official_catalog_url": DATASET_URL,
            "official_project_url": PROJECT_URL,
            "official_download_notebook_url": DOWNLOAD_NOTEBOOK_URL,
            "selected_license": LICENSE,
            "attribution": ATTRIBUTION,
            "sentinel_data_legal_notice_url": SENTINEL_LEGAL_NOTICE_URL,
        },
        "aoi": {
            "bbox_wgs84": list(config.bbox),
            "approximate_area_km2": round(_bbox_area_km2(config.bbox), 6),
            "maximum_area_km2": float(config.maximum_aoi_area_km2),
            "country_iso3_coverage_hint": config.country_iso3,
            "s2cell_token": config.s2cell_token,
            "projected_crs": config.projected_crs,
            "projected_bbox": [round(float(value), 6) for value in projected_bbox],
            "country_hint_does_not_replace_per_pixel_coverage_check": True,
        },
        "years": list(config.years),
        "semantics": {
            "bands": {
                "building_fractional_count": (
                    "model output intended as source data for AOI building-count estimates"
                ),
                "building_height": (
                    "modelled height above terrain in metres, screened by building presence"
                ),
                "building_presence": (
                    "uncalibrated model confidence usable only for relative ranking"
                ),
            },
            "missing_value": MISSING_VALUE,
            "storage_grid_resolution_m": STORAGE_GRID_RESOLUTION_M,
            "effective_spatial_resolution_m": EFFECTIVE_RESOLUTION_M,
            "storage_grid_does_not_imply_half_metre_effective_precision": True,
            "presence_height_screen": float(config.presence_height_screen),
            "annual_inference_dates": "June 30, 2016-2023",
        },
        "selection": config.selection_document(),
        "atlas_prior_radius_m": float(config.atlas_prior_radius_m),
        "review_constraints": REVIEW_CONSTRAINTS,
    }


def _config_from_query(query: Mapping[str, Any]) -> OpenBuildingsTemporalConfig:
    try:
        aoi = query["aoi"]
        selection = query["selection"]
        semantics = query["semantics"]
        return OpenBuildingsTemporalConfig(
            bbox=tuple(aoi["bbox_wgs84"]),
            country_iso3=aoi["country_iso3_coverage_hint"],
            s2cell_token=aoi["s2cell_token"],
            projected_crs=aoi["projected_crs"],
            years=tuple(query["years"]),
            maximum_aoi_area_km2=aoi["maximum_area_km2"],
            minimum_fractional_count_delta=selection["minimum_fractional_count_delta"],
            minimum_presence_mean_delta=selection[
                "minimum_presence_mean_delta_exclusive"
            ],
            presence_height_screen=semantics["presence_height_screen"],
            atlas_prior_radius_m=query["atlas_prior_radius_m"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, OpenBuildingsTemporalValidationError):
            raise
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings query configuration is invalid"
        ) from error


def _raster_modules() -> tuple[Any, Any]:
    try:
        import numpy
        import rasterio
        import rasterio.warp
        import rasterio.windows
    except ImportError as error:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings COG access requires rasterio and numpy; run with "
            "`uv run --with rasterio` or install the optional raster dependency"
        ) from error
    return rasterio, numpy


def _project_bbox(bbox: Sequence[float], crs: str) -> tuple[float, float, float, float]:
    rasterio, _ = _raster_modules()
    return tuple(
        float(value)
        for value in rasterio.warp.transform_bounds("EPSG:4326", crs, *bbox)
    )


def _tile_bounds(source: Mapping[str, Any]) -> tuple[float, float, float, float]:
    try:
        transform = source["affineTransform"]
        dimensions = source["dimensions"]
        x0 = float(transform["translateX"])
        y0 = float(transform["translateY"])
        x1 = x0 + float(transform["scaleX"]) * int(dimensions["width"])
        y1 = y0 + float(transform["scaleY"]) * int(dimensions["height"])
    except (KeyError, TypeError, ValueError) as error:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings upstream tile geometry is invalid"
        ) from error
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _intersects(first: Sequence[float], second: Sequence[float]) -> bool:
    left, bottom, right, top = (float(value) for value in first)
    other_left, other_bottom, other_right, other_top = (
        float(value) for value in second
    )
    return not (
        right <= other_left
        or other_right <= left
        or top <= other_bottom
        or other_top <= bottom
    )


def _parse_upstream_manifest(
    raw: bytes,
    config: OpenBuildingsTemporalConfig,
    year: int,
    projected_bbox: Sequence[float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} manifest is not valid JSON"
        ) from error
    expected_keys = {
        "bands",
        "endTime",
        "name",
        "properties",
        "skipMetadataRead",
        "startTime",
        "tilesets",
        "uriPrefix",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} upstream manifest schema changed"
        )
    timestamp = f"{year}-06-30T07:00:00Z"
    expected_name = (
        "projects/mmeka-ee/assets/open-buildings-temporal/"
        f"{config.s2cell_token}_{config.projected_crs.replace(':', '_')}_{year}_06_30"
    )
    if (
        document.get("name") != expected_name
        or document.get("startTime") != timestamp
        or document.get("endTime") != timestamp
        or document.get("skipMetadataRead") is not True
        or document.get("uriPrefix") != f"gs://{GCS_BUCKET}/{GCS_PREFIX}/geotiffs/1"
    ):
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} manifest identity changed"
        )
    expected_bands = [
        {
            "id": "building_fractional_count",
            "tilesetId": "a0",
            "missingData": {"values": [MISSING_VALUE]},
        },
        {
            "id": "building_height",
            "tilesetId": "a0",
            "tilesetBandIndex": 1,
            "missingData": {"values": [MISSING_VALUE]},
        },
        {
            "id": "building_presence",
            "tilesetId": "a0",
            "tilesetBandIndex": 2,
            "missingData": {"values": [MISSING_VALUE]},
        },
    ]
    if document.get("bands") != expected_bands:
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} band semantics changed"
        )
    properties = document.get("properties")
    try:
        inference_time = float(properties.get("inference_time_epoch_s", -1))
    except (AttributeError, TypeError, ValueError):
        inference_time = -1
    if (
        not isinstance(properties, dict)
        or set(properties)
        != {
            "imagery_start_time_epoch_s",
            "imagery_end_time_epoch_s",
            "inference_time_epoch_s",
            "s2cell_token",
        }
        or properties.get("s2cell_token") != config.s2cell_token
        or inference_time != datetime(year, 6, 30, 7, tzinfo=UTC).timestamp()
    ):
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} temporal properties changed"
        )
    tilesets = document.get("tilesets")
    if not isinstance(tilesets, list) or len(tilesets) != 1:
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} tileset inventory changed"
        )
    tileset = tilesets[0]
    if (
        not isinstance(tileset, dict)
        or set(tileset) != {"crs", "dataType", "id", "sources"}
        or tileset.get("crs") != config.projected_crs
        or tileset.get("dataType") != "FLOAT"
        or tileset.get("id") != "a0"
        or not isinstance(tileset.get("sources"), list)
    ):
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} tileset schema changed"
        )
    selected = []
    for source in tileset["sources"]:
        if not isinstance(source, dict) or set(source) != {
            "affineTransform",
            "dimensions",
            "uris",
        }:
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} tile source schema changed"
            )
        transform = source["affineTransform"]
        dimensions = source["dimensions"]
        if (
            not isinstance(transform, dict)
            or set(transform) != {"scaleX", "translateX", "scaleY", "translateY"}
            or transform.get("scaleX") != STORAGE_GRID_RESOLUTION_M
            or transform.get("scaleY") != -STORAGE_GRID_RESOLUTION_M
            or dimensions != {"width": 25000, "height": 25000}
            or not isinstance(source.get("uris"), list)
            or len(source["uris"]) != 1
            or not isinstance(source["uris"][0], str)
            or not source["uris"][0].endswith(".tif")
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} storage-grid contract changed"
            )
        if _intersects(_tile_bounds(source), projected_bbox):
            selected.append(source)
    if len(selected) != 1:
        raise OpenBuildingsTemporalValidationError(
            f"bounded AOI must intersect exactly one Open Buildings tile for {year}; "
            f"found {len(selected)}"
        )
    return document, selected[0]


def _normalize_object_metadata(
    value: Mapping[str, Any], expected_name: str
) -> dict[str, Any]:
    try:
        name = value["name"]
        generation = str(value["generation"])
        size = int(value["size"])
        md5 = value["md5Hash"]
        crc32c = value["crc32c"]
        etag = value["etag"]
        updated = value["updated"]
    except (KeyError, TypeError, ValueError) as error:
        raise OpenBuildingsTemporalValidationError(
            f"GCS metadata is incomplete for {expected_name}"
        ) from error
    try:
        md5_bytes = base64.b64decode(md5, validate=True)
        crc_bytes = base64.b64decode(crc32c, validate=True)
    except (ValueError, TypeError) as error:
        raise OpenBuildingsTemporalValidationError(
            f"GCS hashes are invalid for {expected_name}"
        ) from error
    if (
        name != expected_name
        or not generation.isdigit()
        or size <= 0
        or len(md5_bytes) != 16
        or len(crc_bytes) != 4
        or not isinstance(etag, str)
        or not etag
    ):
        raise OpenBuildingsTemporalValidationError(
            f"GCS metadata is invalid for {expected_name}"
        )
    _timestamp(updated, f"GCS {expected_name} updated")
    return {
        "name": name,
        "generation": generation,
        "bytes": size,
        "md5_base64": md5,
        "md5_hex": md5_bytes.hex(),
        "crc32c_base64": crc32c,
        "etag": etag,
        "updated": updated,
    }


def _validate_object_record(
    value: Mapping[str, Any], expected_name: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "generation",
        "bytes",
        "md5_base64",
        "md5_hex",
        "crc32c_base64",
        "etag",
        "updated",
    }:
        raise OpenBuildingsTemporalValidationError(
            f"stored GCS metadata schema changed for {expected_name}"
        )
    try:
        md5 = base64.b64decode(value["md5_base64"], validate=True)
        crc32c = base64.b64decode(value["crc32c_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise OpenBuildingsTemporalValidationError(
            f"stored GCS hashes are invalid for {expected_name}"
        ) from error
    if (
        value["name"] != expected_name
        or not isinstance(value["generation"], str)
        or not value["generation"].isdigit()
        or isinstance(value["bytes"], bool)
        or not isinstance(value["bytes"], int)
        or value["bytes"] <= 0
        or len(md5) != 16
        or value["md5_hex"] != md5.hex()
        or len(crc32c) != 4
        or not isinstance(value["etag"], str)
        or not value["etag"]
    ):
        raise OpenBuildingsTemporalValidationError(
            f"stored GCS metadata is invalid for {expected_name}"
        )
    _timestamp(value["updated"], f"GCS {expected_name} updated")
    return dict(value)


class AnonymousGCSClient:
    """Small bounded anonymous JSON-API client with transparent pacing."""

    def __init__(
        self,
        *,
        maximum_requests: int = 32,
        minimum_interval_seconds: float = 0.25,
        user_agent: str = "datacenter-atlas-open-buildings-review/1.0",
        opener: Any = urllib.request,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_requests < 24:
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings source fetch needs a request budget of at least 24"
            )
        if minimum_interval_seconds < 0:
            raise OpenBuildingsTemporalValidationError(
                "minimum request interval must be nonnegative"
            )
        self.maximum_requests = maximum_requests
        self.minimum_interval_seconds = float(minimum_interval_seconds)
        self.user_agent = user_agent
        self.opener = opener
        self.sleep = sleep
        self.monotonic = monotonic
        self.requests_made = 0
        self._last_request_started: float | None = None

    def _read(self, url: str) -> bytes:
        last_error: BaseException | None = None
        for attempt in range(3):
            if self.requests_made >= self.maximum_requests:
                raise OpenBuildingsTemporalValidationError(
                    "Open Buildings GCS request budget exhausted"
                )
            now = self.monotonic()
            if self._last_request_started is not None:
                remaining = self.minimum_interval_seconds - (
                    now - self._last_request_started
                )
                if remaining > 0:
                    self.sleep(remaining)
            self._last_request_started = self.monotonic()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept-Encoding": "identity",
                    "User-Agent": self.user_agent,
                },
            )
            self.requests_made += 1
            try:
                with self.opener.urlopen(request, timeout=60) as response:
                    if response.status != 200:
                        raise OpenBuildingsTemporalValidationError(
                            f"unexpected GCS HTTP status {response.status}"
                        )
                    return response.read()
            except urllib.error.HTTPError as error:
                last_error = error
                transient = error.code in {429, 500, 502, 503, 504}
                error.close()
                if not transient:
                    break
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
            if attempt < 2:
                self.sleep(min(4.0, float(2**attempt)))
        raise OpenBuildingsTemporalValidationError(
            f"anonymous GCS request failed: {url}"
        ) from last_error

    def metadata(self, object_name: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(object_name, safe="")
        raw = self._read(
            f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded}"
        )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise OpenBuildingsTemporalValidationError(
                f"GCS metadata response is invalid for {object_name}"
            ) from error
        return _normalize_object_metadata(value, object_name)

    def download(self, metadata: Mapping[str, Any]) -> bytes:
        object_name = metadata["name"]
        encoded = urllib.parse.quote(object_name, safe="")
        raw = self._read(
            f"https://storage.googleapis.com/download/storage/v1/b/{GCS_BUCKET}/o/"
            f"{encoded}?alt=media&generation={metadata['generation']}"
        )
        digest = hashlib.md5(raw, usedforsecurity=False).hexdigest()
        if len(raw) != metadata["bytes"] or digest != metadata["md5_hex"]:
            raise OpenBuildingsTemporalValidationError(
                f"GCS object bytes changed for {object_name}"
            )
        return raw


def _object_name(document: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    uri = f"{document['uriPrefix']}{source['uris'][0]}"
    prefix = f"gs://{GCS_BUCKET}/"
    if not uri.startswith(prefix):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings tile URI left the pinned public bucket"
        )
    return uri.removeprefix(prefix)


def write_source_bundle(
    output_directory: str | Path,
    *,
    generated_at: str,
    config: OpenBuildingsTemporalConfig = OpenBuildingsTemporalConfig(),
    client: Any | None = None,
    project_bbox: Callable[[Sequence[float], str], Sequence[float]] = _project_bbox,
) -> dict[str, Any]:
    """Fetch eight exact upstream manifests and atomically publish their tile plan."""
    if not isinstance(config, OpenBuildingsTemporalConfig):
        raise OpenBuildingsTemporalValidationError(
            "config must be OpenBuildingsTemporalConfig"
        )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise OpenBuildingsTemporalValidationError(
            f"refusing existing Open Buildings source output: {destination}"
        )
    generated = _timestamp(generated_at, "Open Buildings source generated_at")
    projected_bbox = tuple(
        float(value) for value in project_bbox(config.bbox, config.projected_crs)
    )
    if len(projected_bbox) != 4 or not all(
        math.isfinite(value) for value in projected_bbox
    ):
        raise OpenBuildingsTemporalValidationError("projected AOI bbox is invalid")
    query = _query_document(config, projected_bbox)
    query_raw = _canonical_json(query, pretty=True)
    gcs = client or AnonymousGCSClient()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    source_files: list[dict[str, Any]] = []
    selected_tiles: list[dict[str, Any]] = []
    artifacts: dict[str, dict[str, Any]] = {QUERY_FILENAME: _raw_record(query_raw)}
    try:
        _write_fsync(stage / QUERY_FILENAME, query_raw)
        for year in config.years:
            manifest_name = _manifest_object_name(config, year)
            metadata = gcs.metadata(manifest_name)
            raw = gcs.download(metadata)
            document, selected = _parse_upstream_manifest(
                raw, config, year, projected_bbox
            )
            local_filename = _manifest_filename(config, year)
            _write_fsync(stage / local_filename, raw)
            raw_record = _raw_record(raw)
            artifacts[local_filename] = raw_record
            source_files.append(
                {
                    "year": year,
                    "local_filename": local_filename,
                    "object": metadata,
                    **raw_record,
                }
            )
            tile_name = _object_name(document, selected)
            tile_metadata = gcs.metadata(tile_name)
            selected_tiles.append(
                {
                    "year": year,
                    "object": tile_metadata,
                    "source": selected,
                    "tile_bounds_projected": [
                        round(value, 6) for value in _tile_bounds(selected)
                    ],
                    "full_object_not_downloaded_cog_range_reads_only": True,
                }
            )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": "google_open_buildings_temporal_source_bundle",
            "generated_at": generated,
            "query": query,
            "source_files": source_files,
            "selected_tiles": selected_tiles,
            "artifacts": artifacts,
        }
        manifest_raw = _canonical_json(manifest, pretty=True)
        sidecar_raw = (
            f"{hashlib.sha256(manifest_raw).hexdigest()}  {SOURCE_MANIFEST_FILENAME}\n"
        ).encode("ascii")
        _write_fsync(stage / SOURCE_MANIFEST_FILENAME, manifest_raw)
        _write_fsync(stage / SOURCE_MANIFEST_HASH_FILENAME, sidecar_raw)
        validate_source_bundle(stage)
        stage.replace(destination)
        return manifest
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise


def _parse_canonical_json(path: Path, field: str) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OpenBuildingsTemporalValidationError(
            f"{field} is not valid JSON"
        ) from error
    if raw != _canonical_json(value, pretty=True):
        raise OpenBuildingsTemporalValidationError(f"{field} is not canonical JSON")
    return raw, value


def validate_source_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source bundle must be a regular directory"
        )
    manifest_path = root / SOURCE_MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source manifest is missing"
        )
    manifest_raw, manifest = _parse_canonical_json(
        manifest_path, "Open Buildings source manifest"
    )
    sidecar = root / SOURCE_MANIFEST_HASH_FILENAME
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {SOURCE_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if (
        sidecar.is_symlink()
        or not sidecar.is_file()
        or sidecar.read_bytes() != expected_sidecar
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source manifest sidecar does not match"
        )
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "pipeline",
        "generated_at",
        "query",
        "source_files",
        "selected_tiles",
        "artifacts",
    }:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source manifest schema changed"
        )
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != "google_open_buildings_temporal_source_bundle"
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source manifest identity changed"
        )
    _timestamp(manifest.get("generated_at"), "Open Buildings source generated_at")
    query = manifest.get("query")
    if not isinstance(query, dict):
        raise OpenBuildingsTemporalValidationError("Open Buildings query is invalid")
    config = _config_from_query(query)
    projected_bbox = query.get("aoi", {}).get("projected_bbox")
    if (
        not isinstance(projected_bbox, list)
        or len(projected_bbox) != 4
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in projected_bbox
        )
        or query != _query_document(config, projected_bbox)
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings query contract changed"
        )
    query_path = root / QUERY_FILENAME
    if (
        query_path.is_symlink()
        or not query_path.is_file()
        or query_path.read_bytes() != _canonical_json(query, pretty=True)
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings query artifact changed"
        )
    source_files = manifest.get("source_files")
    selected_tiles = manifest.get("selected_tiles")
    if (
        not isinstance(source_files, list)
        or not isinstance(selected_tiles, list)
        or len(source_files) != len(YEARS)
        or len(selected_tiles) != len(YEARS)
        or [item.get("year") for item in source_files] != list(YEARS)
        or [item.get("year") for item in selected_tiles] != list(YEARS)
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings annual source inventory changed"
        )
    expected_files = {
        QUERY_FILENAME,
        SOURCE_MANIFEST_FILENAME,
        SOURCE_MANIFEST_HASH_FILENAME,
        *(_manifest_filename(config, year) for year in YEARS),
    }
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != expected_files or len(entries) != len(
        expected_files
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source bundle closed file set changed"
        )
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source bundle contains a non-regular file"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_files - {
        SOURCE_MANIFEST_FILENAME,
        SOURCE_MANIFEST_HASH_FILENAME,
    }:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings source artifact inventory changed"
        )
    for filename, record in artifacts.items():
        if record != _file_record(root / filename):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings source artifact hash changed: {filename}"
            )
    for source_file, tile in zip(source_files, selected_tiles, strict=True):
        year = source_file["year"]
        filename = _manifest_filename(config, year)
        if (
            set(source_file) != {"year", "local_filename", "object", "bytes", "sha256"}
            or source_file.get("local_filename") != filename
            or source_file.get("bytes") != artifacts[filename]["bytes"]
            or source_file.get("sha256") != artifacts[filename]["sha256"]
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} source-file lineage changed"
            )
        manifest_metadata = _validate_object_record(
            source_file.get("object", {}), _manifest_object_name(config, year)
        )
        if manifest_metadata != source_file["object"]:
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} manifest metadata changed"
            )
        raw = (root / filename).read_bytes()
        if (
            manifest_metadata["bytes"] != len(raw)
            or manifest_metadata["md5_hex"]
            != hashlib.md5(raw, usedforsecurity=False).hexdigest()
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} upstream manifest MD5 changed"
            )
        _, selected = _parse_upstream_manifest(raw, config, year, projected_bbox)
        expected_tile_name = _object_name(json.loads(raw), selected)
        if set(tile) != {
            "year",
            "object",
            "source",
            "tile_bounds_projected",
            "full_object_not_downloaded_cog_range_reads_only",
        }:
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} selected tile schema changed"
            )
        tile_metadata = _validate_object_record(
            tile.get("object", {}), expected_tile_name
        )
        if (
            tile_metadata != tile["object"]
            or tile.get("source") != selected
            or tile.get("tile_bounds_projected")
            != [round(value, 6) for value in _tile_bounds(selected)]
            or tile.get("full_object_not_downloaded_cog_range_reads_only") is not True
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} selected tile changed"
            )
    return manifest


def _generation_media_url(metadata: Mapping[str, Any]) -> str:
    encoded = urllib.parse.quote(metadata["name"], safe="")
    return (
        f"https://storage.googleapis.com/download/storage/v1/b/{GCS_BUCKET}/o/"
        f"{encoded}?alt=media&generation={metadata['generation']}"
    )


def _remote_observation(
    tile: Mapping[str, Any], query: Mapping[str, Any]
) -> dict[str, Any]:
    rasterio, numpy = _raster_modules()
    year = int(tile["year"])
    source = tile["source"]
    projected_bbox = query["aoi"]["projected_bbox"]
    url = _generation_media_url(tile["object"])
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="1",
        GDAL_HTTP_TIMEOUT="60",
    ):
        with rasterio.open(url) as dataset:
            expected_transform = source["affineTransform"]
            expected_dimensions = source["dimensions"]
            if (
                dataset.width != expected_dimensions["width"]
                or dataset.height != expected_dimensions["height"]
                or dataset.count != 3
                or tuple(dataset.dtypes) != ("float32", "float32", "float32")
                or str(dataset.crs) != query["aoi"]["projected_crs"]
                or dataset.nodata != MISSING_VALUE
                or not math.isclose(dataset.transform.a, expected_transform["scaleX"])
                or not math.isclose(dataset.transform.e, expected_transform["scaleY"])
                or not math.isclose(
                    dataset.transform.c, expected_transform["translateX"]
                )
                or not math.isclose(
                    dataset.transform.f, expected_transform["translateY"]
                )
            ):
                raise OpenBuildingsTemporalValidationError(
                    f"Open Buildings {year} COG profile changed"
                )
            window = (
                rasterio.windows.from_bounds(*projected_bbox, dataset.transform)
                .round_offsets()
                .round_lengths()
            )
            if (
                window.col_off < 0
                or window.row_off < 0
                or window.col_off + window.width > dataset.width
                or window.row_off + window.height > dataset.height
            ):
                raise OpenBuildingsTemporalValidationError(
                    f"Open Buildings {year} AOI window left its selected tile"
                )
            values = dataset.read(window=window, masked=True)
            actual_bounds = rasterio.windows.bounds(window, dataset.transform)
    combined_valid = numpy.ones(values.shape[1:], dtype=bool)
    for band_index, band_name in enumerate(BANDS):
        band = values[band_index]
        combined_valid &= ~numpy.ma.getmaskarray(band)
        combined_valid &= numpy.isfinite(band.data)
        low, high = BAND_RANGES[band_name]
        valid_values = band.data[combined_valid]
        if valid_values.size and (
            float(valid_values.min()) < low - 1e-6
            or float(valid_values.max()) > high + 1e-6
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} {band_name} left its documented range"
            )
    valid_count = int(combined_valid.sum())
    if valid_count == 0:
        raise OpenBuildingsTemporalValidationError(
            f"Open Buildings {year} AOI has no valid samples"
        )
    arrays: dict[str, dict[str, Any]] = {}
    stats: dict[str, dict[str, Any]] = {}
    for band_index, band_name in enumerate(BANDS):
        band = values[band_index]
        canonical = numpy.asarray(band.filled(MISSING_VALUE), dtype="<f4").tobytes(
            order="C"
        )
        selected = numpy.asarray(band.data[combined_valid], dtype="float64")
        arrays[band_name] = {
            "float32_little_endian_row_major_sha256": hashlib.sha256(
                canonical
            ).hexdigest(),
            "valid_samples": valid_count,
        }
        if band_name == "building_fractional_count":
            stats[band_name] = {
                "minimum": round(float(selected.min()), 6),
                "maximum": round(float(selected.max()), 6),
                "mean": round(float(selected.mean()), 6),
                "sum": round(float(selected.sum(dtype="float64")), 6),
                "sum_is_modelled_fractional_count_signal": True,
            }
        elif band_name == "building_presence":
            stats[band_name] = {
                "minimum": round(float(selected.min()), 6),
                "maximum": round(float(selected.max()), 6),
                "mean": round(float(selected.mean()), 6),
                "mean_is_uncalibrated_relative_confidence": True,
            }
        else:
            stats[band_name] = {
                "raw_minimum_for_range_validation_only": round(
                    float(selected.min()), 6
                ),
                "raw_maximum_for_range_validation_only": round(
                    float(selected.max()), 6
                ),
                "interpreted_only_after_building_presence_screen": True,
            }
    threshold = float(query["semantics"]["presence_height_screen"])
    presence = values[2].data
    height = values[1].data
    height_screen = combined_valid & (presence >= threshold)
    screened = numpy.asarray(height[height_screen], dtype="float64")
    height_summary = {
        "building_presence_threshold": threshold,
        "threshold_is_relative_screen_not_probability": True,
        "samples": int(height_screen.sum()),
        "mean_m": round(float(screened.mean()), 6) if screened.size else None,
        "maximum_m": round(float(screened.max()), 6) if screened.size else None,
    }
    stats["building_presence"]["samples_gte_height_screen"] = int(height_screen.sum())
    stats["building_presence"]["fraction_gte_height_screen"] = round(
        float(height_screen.sum()) / valid_count, 6
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "year": year,
        "inference_time": f"{year}-06-30T07:00:00Z",
        "source_object": tile["object"],
        "window": {
            "projected_crs": query["aoi"]["projected_crs"],
            "column_offset": int(window.col_off),
            "row_offset": int(window.row_off),
            "width_storage_pixels": int(window.width),
            "height_storage_pixels": int(window.height),
            "projected_bounds": [round(float(value), 6) for value in actual_bounds],
            "storage_grid_resolution_m": STORAGE_GRID_RESOLUTION_M,
            "effective_spatial_resolution_m": EFFECTIVE_RESOLUTION_M,
        },
        "samples": {
            "total_storage_pixels": int(values.shape[1] * values.shape[2]),
            "valid_storage_pixels": valid_count,
            "storage_pixels_are_not_independent_half_metre_detections": True,
        },
        "band_array_hashes": arrays,
        "band_statistics": stats,
        "presence_screened_height": height_summary,
        "semantics": {
            "fractional_count_is_model_signal_not_observed_building_count": True,
            "presence_is_uncalibrated_relative_confidence": True,
            "height_is_modelled_above_terrain_not_measured": True,
        },
    }


def _distance_m(first: Sequence[float], second: Sequence[float]) -> float:
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(value)))


def _atlas_priors(
    atlas_path: Path,
    atlas_manifest_path: Path,
    query: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if (
        atlas_path.is_symlink()
        or not atlas_path.is_file()
        or atlas_manifest_path.is_symlink()
        or not atlas_manifest_path.is_file()
    ):
        raise OpenBuildingsTemporalValidationError(
            "v3 atlas inputs must be regular files"
        )
    atlas_raw = atlas_path.read_bytes()
    try:
        atlas = json.loads(atlas_raw)
        release_manifest = json.loads(atlas_manifest_path.read_bytes())
    except json.JSONDecodeError as error:
        raise OpenBuildingsTemporalValidationError(
            "v3 atlas input is invalid JSON"
        ) from error
    file_record = release_manifest.get("files", {}).get("atlas.geojson")
    if file_record != _raw_record(atlas_raw):
        raise OpenBuildingsTemporalValidationError(
            "v3 release manifest does not bind atlas.geojson"
        )
    if (
        not isinstance(atlas, dict)
        or atlas.get("type") != "FeatureCollection"
        or not isinstance(atlas.get("features"), list)
    ):
        raise OpenBuildingsTemporalValidationError(
            "v3 atlas is not a FeatureCollection"
        )
    west, south, east, north = query["aoi"]["bbox_wgs84"]
    centre = ((west + east) / 2, (south + north) / 2)
    radius = float(query["atlas_prior_radius_m"])
    priors: list[dict[str, Any]] = []
    for feature in atlas["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") != "Point"
            or not isinstance(geometry.get("coordinates"), list)
            or len(geometry["coordinates"]) < 2
            or not isinstance(properties, dict)
        ):
            continue
        coordinates = geometry["coordinates"][:2]
        try:
            distance = _distance_m(centre, coordinates)
        except (TypeError, ValueError):
            continue
        entity_id = properties.get("entity_id")
        if distance <= radius and isinstance(entity_id, str) and entity_id:
            priors.append(
                {
                    "entity_id": entity_id,
                    "name": properties.get("name"),
                    "coordinates_wgs84": [float(coordinates[0]), float(coordinates[1])],
                    "distance_to_aoi_centroid_m": round(distance, 3),
                    "source_family": properties.get("source_family"),
                    "stable_key": properties.get("stable_key"),
                    "prior_only_not_candidate_identity": True,
                    "merge_performed": False,
                }
            )
    priors.sort(
        key=lambda item: (item["distance_to_aoi_centroid_m"], item["entity_id"])
    )
    lineage = {
        "release_directory": atlas_path.parent.name,
        "release_as_of": release_manifest.get("as_of"),
        "release_recorded_at": release_manifest.get("recorded_at"),
        "atlas_file": {"filename": atlas_path.name, **_raw_record(atlas_raw)},
        "release_manifest": {
            "filename": atlas_manifest_path.name,
            **_file_record(atlas_manifest_path),
        },
        "atlas_feature_count": len(atlas["features"]),
        "prior_count": len(priors),
        "radius_m": radius,
        "candidate_merge_performed": False,
    }
    _timestamp(lineage["release_recorded_at"], "v3 release recorded_at")
    return priors, lineage


def _deltas(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for before, after in zip(observations, observations[1:]):
        before_stats = before["band_statistics"]
        after_stats = after["band_statistics"]
        before_height = before["presence_screened_height"]["mean_m"]
        after_height = after["presence_screened_height"]["mean_m"]
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "start_year": before["year"],
                "end_year": after["year"],
                "fractional_count_sum_delta": round(
                    after_stats["building_fractional_count"]["sum"]
                    - before_stats["building_fractional_count"]["sum"],
                    6,
                ),
                "building_presence_mean_delta": round(
                    after_stats["building_presence"]["mean"]
                    - before_stats["building_presence"]["mean"],
                    6,
                ),
                "presence_screened_height_mean_delta_m": (
                    round(after_height - before_height, 6)
                    if before_height is not None and after_height is not None
                    else None
                ),
                "change_is_model_signal_not_observed_construction": True,
            }
        )
    return records


def _candidates(
    deltas: Sequence[Mapping[str, Any]],
    query: Mapping[str, Any],
    prior_ids: Sequence[str],
) -> list[dict[str, Any]]:
    selection = query["selection"]
    query_id = hashlib.sha256(_canonical_json(query, pretty=True)).hexdigest()[:20]
    result = []
    for delta in deltas:
        if (
            delta["fractional_count_sum_delta"]
            >= selection["minimum_fractional_count_delta"]
            and delta["building_presence_mean_delta"]
            > selection["minimum_presence_mean_delta_exclusive"]
        ):
            identity = (
                f"{query_id}:{delta['start_year']}:{delta['end_year']}:"
                f"{delta['fractional_count_sum_delta']}:"
                f"{delta['building_presence_mean_delta']}"
            )
            result.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": "open-buildings-temporal-"
                    + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    "aoi_query_sha256": hashlib.sha256(
                        _canonical_json(query, pretty=True)
                    ).hexdigest(),
                    "interval": {
                        "start_year": delta["start_year"],
                        "end_year": delta["end_year"],
                    },
                    "change_signal": dict(delta),
                    "nearby_v3_atlas_prior_ids": list(prior_ids),
                    "atlas_prior_ids_do_not_identify_the_changed_signal": True,
                    "review_constraints": REVIEW_CONSTRAINTS,
                }
            )
    return result


def _parse_jsonl(raw: bytes, field: str) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.endswith(b"\n"):
            raise OpenBuildingsTemporalValidationError(
                f"{field} line {line_number} lacks a newline"
            )
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise OpenBuildingsTemporalValidationError(
                f"{field} line {line_number} is invalid JSON"
            ) from error
        if not isinstance(value, dict) or line != _canonical_json(value):
            raise OpenBuildingsTemporalValidationError(
                f"{field} line {line_number} is not canonical JSON"
            )
        records.append(value)
    return records


def write_candidate_bundle(
    source_directory: str | Path,
    atlas_path: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
    atlas_manifest_path: str | Path | None = None,
    observation_reader: Callable[
        [Mapping[str, Any], Mapping[str, Any]], dict[str, Any]
    ] = _remote_observation,
) -> dict[str, Any]:
    """Read generation-pinned COG windows and publish an immutable review bundle."""
    source_root = Path(source_directory)
    source_manifest = validate_source_bundle(source_root)
    atlas = Path(atlas_path)
    atlas_manifest = (
        Path(atlas_manifest_path)
        if atlas_manifest_path
        else atlas.with_name("manifest.json")
    )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise OpenBuildingsTemporalValidationError(
            f"refusing existing Open Buildings candidate output: {destination}"
        )
    generated = _timestamp(generated_at, "Open Buildings candidate generated_at")
    query = source_manifest["query"]
    priors, atlas_lineage = _atlas_priors(atlas, atlas_manifest, query)
    observations = [
        observation_reader(tile, query) for tile in source_manifest["selected_tiles"]
    ]
    if [record.get("year") for record in observations] != list(YEARS):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings observation years do not reconcile"
        )
    delta_records = _deltas(observations)
    prior_ids = [record["entity_id"] for record in priors]
    candidates = _candidates(delta_records, query, prior_ids)
    observation_raw = _jsonl(observations)
    delta_raw = _jsonl(delta_records)
    candidate_raw = _jsonl(candidates)
    prior_raw = _jsonl(priors)
    artifact_raw = {
        OBSERVATIONS_FILENAME: observation_raw,
        DELTAS_FILENAME: delta_raw,
        CANDIDATES_FILENAME: candidate_raw,
        ATLAS_PRIORS_FILENAME: prior_raw,
    }
    artifacts = {
        filename: {
            **_raw_record(raw),
            "records": len(_parse_jsonl(raw, filename)),
            "media_type": "application/x-ndjson",
        }
        for filename, raw in artifact_raw.items()
    }
    source_manifest_path = source_root / SOURCE_MANIFEST_FILENAME
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "pipeline": "google_open_buildings_temporal_review_bundle",
        "generated_at": generated,
        "review_constraints": REVIEW_CONSTRAINTS,
        "source_family_constraint": SENTINEL_SOURCE_FAMILY_CONSTRAINT,
        "query": query,
        "source": {
            "directory_name": source_root.name,
            "manifest": {
                "filename": SOURCE_MANIFEST_FILENAME,
                **_file_record(source_manifest_path),
            },
        },
        "atlas_cross_reference": atlas_lineage,
        "counts": {
            "annual_observations": len(observations),
            "annual_deltas": len(delta_records),
            "review_candidates": len(candidates),
            "nearby_v3_atlas_priors": len(priors),
        },
        "artifacts": artifacts,
    }
    manifest_raw = _canonical_json(manifest, pretty=True)
    sidecar_raw = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {CANDIDATE_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for filename, raw in artifact_raw.items():
            _write_fsync(stage / filename, raw)
        _write_fsync(stage / CANDIDATE_MANIFEST_FILENAME, manifest_raw)
        _write_fsync(stage / CANDIDATE_MANIFEST_HASH_FILENAME, sidecar_raw)
        validate_candidate_bundle(
            stage,
            source_directory=source_root,
            atlas_path=atlas,
            atlas_manifest_path=atlas_manifest,
        )
        stage.replace(destination)
        return manifest
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise


def validate_candidate_bundle(
    directory: str | Path,
    *,
    source_directory: str | Path | None = None,
    atlas_path: str | Path | None = None,
    atlas_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate bundle must be a regular directory"
        )
    expected_files = {
        OBSERVATIONS_FILENAME,
        DELTAS_FILENAME,
        CANDIDATES_FILENAME,
        ATLAS_PRIORS_FILENAME,
        CANDIDATE_MANIFEST_FILENAME,
        CANDIDATE_MANIFEST_HASH_FILENAME,
    }
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != expected_files or len(entries) != len(
        expected_files
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate bundle closed file set changed"
        )
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate bundle contains a non-regular file"
        )
    manifest_raw, manifest = _parse_canonical_json(
        root / CANDIDATE_MANIFEST_FILENAME,
        "Open Buildings candidate manifest",
    )
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {CANDIDATE_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if (root / CANDIDATE_MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate manifest sidecar does not match"
        )
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "pipeline",
        "generated_at",
        "review_constraints",
        "source_family_constraint",
        "query",
        "source",
        "atlas_cross_reference",
        "counts",
        "artifacts",
    }:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate manifest schema changed"
        )
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != "google_open_buildings_temporal_review_bundle"
        or manifest.get("review_constraints") != REVIEW_CONSTRAINTS
        or manifest.get("source_family_constraint") != SENTINEL_SOURCE_FAMILY_CONSTRAINT
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate bundle safeguards changed"
        )
    _timestamp(manifest.get("generated_at"), "Open Buildings candidate generated_at")
    query = manifest.get("query")
    config = _config_from_query(query)
    if query != _query_document(config, query["aoi"]["projected_bbox"]):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate query changed"
        )
    artifacts = manifest.get("artifacts")
    artifact_names = expected_files - {
        CANDIDATE_MANIFEST_FILENAME,
        CANDIDATE_MANIFEST_HASH_FILENAME,
    }
    if not isinstance(artifacts, dict) or set(artifacts) != artifact_names:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate artifact inventory changed"
        )
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    for filename in artifact_names:
        raw = (root / filename).read_bytes()
        raw_record = _raw_record(raw)
        artifact = artifacts[filename]
        if (
            not isinstance(artifact, dict)
            or artifact.get("bytes") != raw_record["bytes"]
            or artifact.get("sha256") != raw_record["sha256"]
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings candidate artifact hash changed: {filename}"
            )
        records = _parse_jsonl(raw, filename)
        records_by_name[filename] = records
        if artifact != {
            **raw_record,
            "records": len(records),
            "media_type": "application/x-ndjson",
        }:
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings candidate artifact hash changed: {filename}"
            )
    observations = records_by_name[OBSERVATIONS_FILENAME]
    if [record.get("year") for record in observations] != list(YEARS):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings annual observations changed"
        )
    for record in observations:
        year = record.get("year")
        if (
            record.get("schema_version") != SCHEMA_VERSION
            or set(record)
            != {
                "schema_version",
                "year",
                "inference_time",
                "source_object",
                "window",
                "samples",
                "band_array_hashes",
                "band_statistics",
                "presence_screened_height",
                "semantics",
            }
            or set(record.get("band_statistics", {})) != set(BANDS)
            or set(record.get("band_array_hashes", {})) != set(BANDS)
            or record.get("semantics")
            != {
                "fractional_count_is_model_signal_not_observed_building_count": True,
                "presence_is_uncalibrated_relative_confidence": True,
                "height_is_modelled_above_terrain_not_measured": True,
            }
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} observation schema changed"
            )
        source_object = record["source_object"]
        source_name = (
            source_object.get("name") if isinstance(source_object, dict) else None
        )
        if not isinstance(source_name, str):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} observation source object changed"
            )
        _validate_object_record(source_object, source_name)
        window = record["window"]
        samples = record["samples"]
        height_summary = record["presence_screened_height"]
        if (
            record.get("inference_time") != f"{year}-06-30T07:00:00Z"
            or not isinstance(window, dict)
            or set(window)
            != {
                "projected_crs",
                "column_offset",
                "row_offset",
                "width_storage_pixels",
                "height_storage_pixels",
                "projected_bounds",
                "storage_grid_resolution_m",
                "effective_spatial_resolution_m",
            }
            or window.get("projected_crs") != query["aoi"]["projected_crs"]
            or window.get("storage_grid_resolution_m") != STORAGE_GRID_RESOLUTION_M
            or window.get("effective_spatial_resolution_m") != EFFECTIVE_RESOLUTION_M
            or any(
                isinstance(window.get(field), bool)
                or not isinstance(window.get(field), int)
                or window[field] < minimum
                for field, minimum in (
                    ("column_offset", 0),
                    ("row_offset", 0),
                    ("width_storage_pixels", 1),
                    ("height_storage_pixels", 1),
                )
            )
            or not isinstance(window.get("projected_bounds"), list)
            or len(window["projected_bounds"]) != 4
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in window["projected_bounds"]
            )
            or not isinstance(samples, dict)
            or set(samples)
            != {
                "total_storage_pixels",
                "valid_storage_pixels",
                "storage_pixels_are_not_independent_half_metre_detections",
            }
            or samples.get("storage_pixels_are_not_independent_half_metre_detections")
            is not True
            or isinstance(samples.get("total_storage_pixels"), bool)
            or not isinstance(samples.get("total_storage_pixels"), int)
            or samples["total_storage_pixels"]
            != window["width_storage_pixels"] * window["height_storage_pixels"]
            or isinstance(samples.get("valid_storage_pixels"), bool)
            or not isinstance(samples.get("valid_storage_pixels"), int)
            or not 0
            < samples["valid_storage_pixels"]
            <= samples["total_storage_pixels"]
            or not isinstance(height_summary, dict)
            or set(height_summary)
            != {
                "building_presence_threshold",
                "threshold_is_relative_screen_not_probability",
                "samples",
                "mean_m",
                "maximum_m",
            }
            or height_summary.get("building_presence_threshold")
            != query["semantics"]["presence_height_screen"]
            or height_summary.get("threshold_is_relative_screen_not_probability")
            is not True
            or isinstance(height_summary.get("samples"), bool)
            or not isinstance(height_summary.get("samples"), int)
            or not 0 <= height_summary["samples"] <= samples["valid_storage_pixels"]
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} window or height-screen contract changed"
            )
        for height_field in ("mean_m", "maximum_m"):
            value = height_summary[height_field]
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 <= float(value) <= 100
            ):
                raise OpenBuildingsTemporalValidationError(
                    f"Open Buildings {year} screened height changed"
                )
        for band_name, band_hash in record["band_array_hashes"].items():
            if (
                set(band_hash)
                != {
                    "float32_little_endian_row_major_sha256",
                    "valid_samples",
                }
                or _SHA256_RE.fullmatch(
                    str(band_hash["float32_little_endian_row_major_sha256"])
                )
                is None
                or band_hash["valid_samples"]
                != record["samples"]["valid_storage_pixels"]
            ):
                raise OpenBuildingsTemporalValidationError(
                    f"Open Buildings {year} {band_name} array hash changed"
                )
        count_stats = record["band_statistics"]["building_fractional_count"]
        presence_stats = record["band_statistics"]["building_presence"]
        height_stats = record["band_statistics"]["building_height"]
        if (
            set(count_stats)
            != {
                "minimum",
                "maximum",
                "mean",
                "sum",
                "sum_is_modelled_fractional_count_signal",
            }
            or count_stats.get("sum_is_modelled_fractional_count_signal") is not True
            or set(presence_stats)
            != {
                "minimum",
                "maximum",
                "mean",
                "mean_is_uncalibrated_relative_confidence",
                "samples_gte_height_screen",
                "fraction_gte_height_screen",
            }
            or presence_stats.get("mean_is_uncalibrated_relative_confidence")
            is not True
            or set(height_stats)
            != {
                "raw_minimum_for_range_validation_only",
                "raw_maximum_for_range_validation_only",
                "interpreted_only_after_building_presence_screen",
            }
            or height_stats.get("interpreted_only_after_building_presence_screen")
            is not True
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} band-statistic semantics changed"
            )
        if (
            presence_stats["samples_gte_height_screen"] != height_summary["samples"]
            or isinstance(presence_stats["fraction_gte_height_screen"], bool)
            or not isinstance(
                presence_stats["fraction_gte_height_screen"], (int, float)
            )
            or not 0 <= presence_stats["fraction_gte_height_screen"] <= 1
            or count_stats["sum"] < 0
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} screened sample counts changed"
            )
        valid_samples = samples["valid_storage_pixels"]
        if (
            not count_stats["minimum"] <= count_stats["mean"] <= count_stats["maximum"]
            or not presence_stats["minimum"]
            <= presence_stats["mean"]
            <= presence_stats["maximum"]
            or height_stats["raw_minimum_for_range_validation_only"]
            > height_stats["raw_maximum_for_range_validation_only"]
            or abs(count_stats["sum"] - count_stats["mean"] * valid_samples)
            > valid_samples * 0.00000051 + 0.000001
            or abs(
                presence_stats["fraction_gte_height_screen"]
                - height_summary["samples"] / valid_samples
            )
            > 0.00000051
            or (
                height_summary["mean_m"] is not None
                and height_summary["maximum_m"] is not None
                and height_summary["mean_m"] > height_summary["maximum_m"]
            )
        ):
            raise OpenBuildingsTemporalValidationError(
                f"Open Buildings {year} aggregate statistics do not reconcile"
            )
        numeric_ranges = (
            (
                count_stats,
                "minimum",
                "maximum",
                BAND_RANGES["building_fractional_count"],
            ),
            (presence_stats, "minimum", "maximum", BAND_RANGES["building_presence"]),
            (
                height_stats,
                "raw_minimum_for_range_validation_only",
                "raw_maximum_for_range_validation_only",
                BAND_RANGES["building_height"],
            ),
        )
        for stats, minimum_key, maximum_key, (low, high) in numeric_ranges:
            numeric_fields = [minimum_key, maximum_key]
            if "mean" in stats:
                numeric_fields.append("mean")
            if "sum" in stats:
                numeric_fields.append("sum")
            if (
                any(
                    isinstance(stats.get(field), bool)
                    or not isinstance(stats.get(field), (int, float))
                    or not math.isfinite(float(stats[field]))
                    for field in numeric_fields
                )
                or stats[minimum_key] < low - 1e-6
                or stats[maximum_key] > high + 1e-6
            ):
                raise OpenBuildingsTemporalValidationError(
                    f"Open Buildings {year} band values changed"
                )
    expected_deltas = _deltas(observations)
    if records_by_name[DELTAS_FILENAME] != expected_deltas:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings annual deltas do not reproduce"
        )
    priors = records_by_name[ATLAS_PRIORS_FILENAME]
    if priors != sorted(
        priors, key=lambda item: (item["distance_to_aoi_centroid_m"], item["entity_id"])
    ) or any(
        prior.get("prior_only_not_candidate_identity") is not True
        or prior.get("merge_performed") is not False
        for prior in priors
    ):
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings atlas priors changed"
        )
    expected_candidates = _candidates(
        expected_deltas, query, [prior["entity_id"] for prior in priors]
    )
    if records_by_name[CANDIDATES_FILENAME] != expected_candidates:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidates do not reproduce"
        )
    counts = {
        "annual_observations": len(observations),
        "annual_deltas": len(expected_deltas),
        "review_candidates": len(expected_candidates),
        "nearby_v3_atlas_priors": len(priors),
    }
    if manifest.get("counts") != counts:
        raise OpenBuildingsTemporalValidationError(
            "Open Buildings candidate counts do not reconcile"
        )
    if source_directory is not None:
        source_manifest = validate_source_bundle(source_directory)
        source_path = Path(source_directory) / SOURCE_MANIFEST_FILENAME
        source_lineage = manifest.get("source")
        if (
            not isinstance(source_lineage, dict)
            or set(source_lineage) != {"directory_name", "manifest"}
            or source_lineage.get("directory_name") != Path(source_directory).name
            or source_manifest.get("query") != query
            or source_lineage.get("manifest")
            != {"filename": SOURCE_MANIFEST_FILENAME, **_file_record(source_path)}
            or any(
                observation["source_object"] != tile["object"]
                for observation, tile in zip(
                    observations, source_manifest["selected_tiles"], strict=True
                )
            )
        ):
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings candidate source lineage changed"
            )
    if atlas_path is not None:
        atlas = Path(atlas_path)
        atlas_manifest = (
            Path(atlas_manifest_path)
            if atlas_manifest_path
            else atlas.with_name("manifest.json")
        )
        live_priors, live_lineage = _atlas_priors(atlas, atlas_manifest, query)
        if live_priors != priors or live_lineage != manifest.get(
            "atlas_cross_reference"
        ):
            raise OpenBuildingsTemporalValidationError(
                "Open Buildings v3 atlas prior input changed"
            )
    return manifest


__all__ = [
    "ATLAS_PRIORS_FILENAME",
    "AnonymousGCSClient",
    "BANDS",
    "CANDIDATES_FILENAME",
    "DATASET_ID",
    "DELTAS_FILENAME",
    "EFFECTIVE_RESOLUTION_M",
    "OBSERVATIONS_FILENAME",
    "OpenBuildingsTemporalConfig",
    "OpenBuildingsTemporalValidationError",
    "REVIEW_CONSTRAINTS",
    "SENTINEL_SOURCE_FAMILY_CONSTRAINT",
    "STORAGE_GRID_RESOLUTION_M",
    "YEARS",
    "validate_candidate_bundle",
    "validate_source_bundle",
    "write_candidate_bundle",
    "write_source_bundle",
]
