#!/usr/bin/env python3
"""Create a bounded, explicitly bound multi-tile Sentinel-2 change bundle."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change import (
    CLEAR_SCL_CLASSES,
    REQUIRED_ASSETS,
    asset_scale_offset,
    derive_change,
    item_summary,
    parse_bbox,
    report_source,
)
from datacenter_atlas.satellite_change_mosaic import (
    ALGORITHM_VERSION,
    MAX_COMPANION_TIME_DELTA_SECONDS,
    REPORT_SCHEMA_VERSION,
    SPECTRAL_CORE_ALGORITHM_VERSION,
    ArrayTile,
    GridSpec,
    GridWindow,
    SentinelMosaicContractError,
    epoch_metadata_coverage,
    grid_from_item,
    grid_offset,
    mosaic_nonzero_tiles,
    parse_item_binding,
    parse_rfc3339_instant,
    parse_sha256,
    require_complete_spatial_coverage,
    select_bound_items,
    validate_epoch_grid_contract,
    window_from_wgs84_bbox,
)


REPORT_CLASSIFICATION = {
    "label": "large_spectral_change_candidate",
    "identity_claim": False,
    "lifecycle_claim": False,
    "operating_status_claim": False,
    "power_claim": False,
    "energy_claim": False,
    "operator_claim": False,
    "data_centre_type_claim": False,
    "it_capacity_claim": False,
    "pue_claim": False,
    "workload_claim": False,
    "review_required": True,
    "limitations": [
        "10 m optical change cannot by itself identify a data centre.",
        "Single-date pairs are vulnerable to seasonal, atmospheric, and registration effects.",
        "Operator, data-centre type, IT capacity, PUE, workload, power, energy, "
        "and operating status cannot be inferred from this evidence bundle.",
    ],
}
GEOJSON_COLLECTION_PROPERTIES = {
    "schema_version": REPORT_SCHEMA_VERSION,
    "algorithm_version": ALGORITHM_VERSION,
    "meaning": "imagery change proposal only; not a data-centre identification",
    "identity_claim": False,
    "lifecycle_claim": False,
    "operating_status_claim": False,
    "power_claim": False,
    "energy_claim": False,
    "operator_claim": False,
    "data_centre_type_claim": False,
    "it_capacity_claim": False,
    "pue_claim": False,
    "workload_claim": False,
    "review_required": True,
}


def _read_bound_json(path: Path, expected_sha256: str) -> Mapping[str, Any]:
    """Hash, decode, and parse one regular non-symlink file from the same bytes."""

    try:
        named = os.lstat(path)
        if stat.S_ISLNK(named.st_mode) or not stat.S_ISREG(named.st_mode):
            raise SentinelMosaicContractError(
                f"STAC response must be a regular non-symlink file: {path}"
            )
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                named.st_dev,
                named.st_ino,
            ) != (opened.st_dev, opened.st_ino):
                raise SentinelMosaicContractError(
                    f"STAC response path changed while opening: {path}"
                )
            raw = stream.read()
    except SentinelMosaicContractError:
        raise
    except OSError as error:
        raise SentinelMosaicContractError(f"STAC response is unreadable: {path}") from error
    if sha256(raw).hexdigest() != expected_sha256:
        raise SentinelMosaicContractError(f"frozen STAC response hash mismatch: {path}")
    try:
        text = raw.decode("utf-8")

        def reject_constant(value: str) -> None:
            raise SentinelMosaicContractError(
                f"STAC response contains non-finite number {value}: {path}"
            )

        value = json.loads(text, parse_constant=reject_constant)
    except SentinelMosaicContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SentinelMosaicContractError(f"invalid STAC JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise SentinelMosaicContractError(f"STAC JSON must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _imports() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        import numpy as np
        from affine import Affine
        from PIL import Image
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.features import shapes
        from rasterio.warp import (
            reproject,
            transform as transform_coordinates,
            transform_bounds,
            transform_geom,
        )
        from rasterio.windows import Window
    except ImportError as error:
        raise SystemExit(
            "Install the pinned imagery runtime, for example: "
            "uv run --python 3.12 --with numpy==2.5.1 --with pillow==12.3.0 "
            "--with rasterio==1.5.0 python scripts/sentinel_change_mosaic.py ..."
        ) from error
    return (
        np,
        Affine,
        Image,
        rasterio,
        Resampling,
        shapes,
        reproject,
        transform_coordinates,
        transform_bounds,
        (transform_geom, Window),
    )


def _intersection(left: GridWindow, right: GridWindow) -> GridWindow | None:
    column_start = max(left.left, right.left)
    row_start = max(left.top, right.top)
    column_stop = min(left.right, right.right)
    row_stop = min(left.bottom, right.bottom)
    if column_start >= column_stop or row_start >= row_stop:
        return None
    return GridWindow(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    )


def _asset_nodata(item: Mapping[str, Any], asset_name: str) -> float:
    asset = item["assets"][asset_name]
    bands = asset.get("raster:bands")
    if not isinstance(bands, list) or len(bands) != 1 or not isinstance(bands[0], Mapping):
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} requires one raster:bands record"
        )
    nodata = bands[0].get("nodata")
    if isinstance(nodata, bool) or not isinstance(nodata, (int, float)):
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} requires numeric nodata"
        )
    value = float(nodata)
    if not math.isfinite(value) or value != 0:
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} must declare zero nodata"
        )
    return value


def _validate_dataset_header(
    source: Any,
    item: Mapping[str, Any],
    asset_name: str,
    expected: GridSpec,
) -> None:
    if source.count != 1:
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} must contain one band"
        )
    if int(source.width) != expected.width or int(source.height) != expected.height:
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} shape differs from frozen STAC"
        )
    if source.crs is None or source.crs.to_epsg() != expected.epsg:
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} CRS differs from frozen STAC"
        )
    actual_transform = tuple(float(value) for value in source.transform[:6])
    if any(
        not math.isclose(actual, frozen, rel_tol=0.0, abs_tol=1e-9)
        for actual, frozen in zip(actual_transform, expected.transform_tuple)
    ):
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} transform differs from frozen STAC"
        )
    expected_nodata = _asset_nodata(item, asset_name)
    if source.nodata is None or not math.isclose(
        float(source.nodata), expected_nodata, rel_tol=0.0, abs_tol=0.0
    ):
        raise SentinelMosaicContractError(
            f"item {item['id']} asset {asset_name} nodata differs from frozen STAC"
        )


def _target_grid(
    Affine: Any,
    rasterio: Any,
    transform_bounds: Any,
    primary_item: Mapping[str, Any],
    bbox: tuple[float, float, float, float],
) -> tuple[tuple[int, int], Any, Any, GridSpec]:
    red = grid_from_item(primary_item, "red")
    window = window_from_wgs84_bbox(red, bbox, transform_bounds)
    transform = Affine(*red.transform_tuple) * Affine.translation(
        window.col_off, window.row_off
    )
    crs = rasterio.crs.CRS.from_epsg(red.epsg)
    return (window.height, window.width), transform, crs, red


def _native_request_window(
    anchor: GridSpec,
    target_grid: tuple[tuple[int, int], Any, Any],
    *,
    interpolation_halo: int,
) -> GridWindow:
    target_shape, target_transform, target_crs = target_grid
    if target_crs.to_epsg() != anchor.epsg:
        raise SentinelMosaicContractError("native asset and target grids use different CRS values")
    height, width = target_shape
    left = float(target_transform.c)
    top = float(target_transform.f)
    right = left + float(target_transform.a) * width
    bottom = top + float(target_transform.e) * height
    column_start = math.floor((left - anchor.c) / anchor.a)
    column_stop = math.ceil((right - anchor.c) / anchor.a)
    row_start = math.floor((anchor.f - top) / anchor.a)
    row_stop = math.ceil((anchor.f - bottom) / anchor.a)
    return GridWindow(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    ).padded(interpolation_halo)


def _asset_resampling_policy(asset_name: str, Resampling: Any) -> tuple[Any, int]:
    """Return the fixed categorical/continuous resampling and halo contract."""

    if asset_name not in REQUIRED_ASSETS:
        raise SentinelMosaicContractError(f"unsupported asset: {asset_name}")
    if asset_name == "swir16":
        return Resampling.bilinear, 1
    return Resampling.nearest, 0


def _reproject_mosaic(
    np: Any,
    Affine: Any,
    Resampling: Any,
    reproject: Any,
    values: Any,
    nonzero: Any,
    request: GridWindow,
    anchor: GridSpec,
    target_grid: tuple[tuple[int, int], Any, Any],
    *,
    resampling: Any,
) -> tuple[Any, Any]:
    """Align a complete native mosaic and its conservative data-valid mask."""

    target_shape, target_transform, target_crs = target_grid
    source_transform = Affine(*anchor.transform_tuple) * Affine.translation(
        request.col_off, request.row_off
    )
    destination = np.zeros(target_shape, dtype=values.dtype)
    aligned, resolved_transform = reproject(
        source=values,
        destination=destination,
        src_transform=source_transform,
        src_crs=f"EPSG:{anchor.epsg}",
        src_nodata=0,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=0,
        resampling=resampling,
        init_dest_nodata=True,
        num_threads=1,
    )
    validity_resampling = (
        Resampling.min if resampling == Resampling.bilinear else Resampling.nearest
    )
    validity_destination = np.zeros(target_shape, dtype=np.uint8)
    aligned_validity, validity_transform = reproject(
        source=np.asarray(nonzero, dtype=np.uint8),
        destination=validity_destination,
        src_transform=source_transform,
        src_crs=f"EPSG:{anchor.epsg}",
        src_nodata=None,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=0,
        resampling=validity_resampling,
        init_dest_nodata=True,
        num_threads=1,
    )
    if (
        aligned.shape != target_shape
        or aligned_validity.shape != target_shape
        or resolved_transform != target_transform
        or validity_transform != target_transform
    ):
        raise SentinelMosaicContractError(
            "asset reprojection did not preserve the exact target grid"
        )
    return aligned, aligned_validity == 1


def _read_asset_mosaic(
    np: Any,
    Affine: Any,
    rasterio: Any,
    Resampling: Any,
    reproject: Any,
    Window: Any,
    primary_item: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    asset_name: str,
    target_grid: tuple[tuple[int, int], Any, Any],
) -> tuple[Any, Any]:
    anchor = grid_from_item(primary_item, asset_name)
    native_resolution_ratio = anchor.resolution / float(target_grid[1].a)
    if not math.isclose(
        native_resolution_ratio,
        round(native_resolution_ratio),
        rel_tol=0.0,
        abs_tol=1e-8,
    ) or native_resolution_ratio < 1:
        raise SentinelMosaicContractError(
            f"asset {asset_name} resolution is not an integer target-grid multiple"
        )
    selected_resampling, interpolation_halo = _asset_resampling_policy(
        asset_name, Resampling
    )
    if selected_resampling == Resampling.bilinear and native_resolution_ratio != 2:
        raise SentinelMosaicContractError(
            f"asset {asset_name} bilinear policy requires exact 20 m input"
        )
    if selected_resampling == Resampling.nearest and native_resolution_ratio not in {
        1,
        2,
    }:
        raise SentinelMosaicContractError(
            f"asset {asset_name} nearest policy requires exact 10 m or 20 m input"
        )
    request = _native_request_window(
        anchor, target_grid, interpolation_halo=interpolation_halo
    )
    tiles: list[ArrayTile] = []
    scales: set[tuple[float, float]] = set()
    for item in sorted(items, key=lambda value: str(value["id"])):
        grid = grid_from_item(item, asset_name)
        column_offset, row_offset = grid_offset(grid, anchor)
        footprint = GridWindow(column_offset, row_offset, grid.width, grid.height)
        intersection = _intersection(request, footprint)
        if intersection is None:
            continue
        local_column = intersection.col_off - footprint.col_off
        local_row = intersection.row_off - footprint.row_off
        href = item["assets"][asset_name]["href"]
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open(href) as source:
                _validate_dataset_header(source, item, asset_name, grid)
                array = source.read(
                    1,
                    window=Window(
                        local_column,
                        local_row,
                        intersection.width,
                        intersection.height,
                    ),
                )
        expected_shape = (intersection.height, intersection.width)
        if array.shape != expected_shape:
            raise SentinelMosaicContractError(
                f"item {item['id']} asset {asset_name} read was clipped"
            )
        scales.add(asset_scale_offset(item, asset_name))
        tiles.append(
            ArrayTile(
                item_id=str(item["id"]),
                row_offset=intersection.row_off - request.row_off,
                column_offset=intersection.col_off - request.col_off,
                values=array,
            )
        )
    if len(scales) != 1:
        raise SentinelMosaicContractError(
            f"asset {asset_name} selected items use different scale/offset metadata"
        )
    values, nonzero, spatial = mosaic_nonzero_tiles(
        tiles, (request.height, request.width)
    )
    require_complete_spatial_coverage(spatial)
    return _reproject_mosaic(
        np,
        Affine,
        Resampling,
        reproject,
        values,
        nonzero,
        request,
        anchor,
        target_grid,
        resampling=selected_resampling,
    )


def _read_scene(
    np: Any,
    Affine: Any,
    rasterio: Any,
    Resampling: Any,
    reproject: Any,
    Window: Any,
    primary_item: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    target_grid: tuple[tuple[int, int], Any, Any],
) -> tuple[dict[str, Any], Any]:
    raw: dict[str, Any] = {}
    nonzero: dict[str, Any] = {}
    for asset_name in REQUIRED_ASSETS:
        raw[asset_name], nonzero[asset_name] = _read_asset_mosaic(
            np,
            Affine,
            rasterio,
            Resampling,
            reproject,
            Window,
            primary_item,
            items,
            asset_name,
            target_grid,
        )
    reflectance: dict[str, Any] = {}
    for asset_name in ("red", "green", "blue", "nir", "swir16"):
        scale, offset = asset_scale_offset(primary_item, asset_name)
        reflectance[asset_name] = raw[asset_name].astype(np.float32) * scale + offset
    clear = np.isin(raw["scl"], sorted(CLEAR_SCL_CLASSES))
    clear &= np.stack(
        [nonzero[asset_name] for asset_name in REQUIRED_ASSETS]
    ).all(axis=0)
    return reflectance, clear


def _rasterize_exact_aoi_center_mask(
    np: Any,
    transform_coordinates: Any,
    bbox: tuple[float, float, float, float],
    grid_transform: Any,
    crs: Any,
    shape: tuple[int, int],
) -> Any:
    """Use the algorithm-v2 exact WGS84 pixel-center inclusion contract."""

    if (
        not isinstance(shape, tuple)
        or len(shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in shape
        )
    ):
        raise SentinelMosaicContractError(
            "analysis grid shape must contain positive height and width"
        )
    height, width = shape
    columns, rows = np.meshgrid(
        np.arange(width, dtype=np.float64) + 0.5,
        np.arange(height, dtype=np.float64) + 0.5,
    )
    xs = (
        float(grid_transform.a) * columns
        + float(grid_transform.b) * rows
        + float(grid_transform.c)
    )
    ys = (
        float(grid_transform.d) * columns
        + float(grid_transform.e) * rows
        + float(grid_transform.f)
    )
    longitudes, latitudes = transform_coordinates(
        crs, "EPSG:4326", xs.ravel(), ys.ravel()
    )
    longitude_grid = np.asarray(longitudes, dtype=np.float64).reshape(shape)
    latitude_grid = np.asarray(latitudes, dtype=np.float64).reshape(shape)
    west, south, east, north = bbox
    inside = (
        np.isfinite(longitude_grid)
        & np.isfinite(latitude_grid)
        & (longitude_grid >= west)
        & (longitude_grid <= east)
        & (latitude_grid >= south)
        & (latitude_grid <= north)
    )
    if not inside.any():
        raise SentinelMosaicContractError("AOI contains no native raster pixel centers")
    return inside


def _valid_pixel_fraction(np: Any, valid_mask: Any, aoi_mask: Any) -> float:
    valid = np.asarray(valid_mask, dtype=bool)
    inside = np.asarray(aoi_mask, dtype=bool)
    if valid.shape != inside.shape:
        raise SentinelMosaicContractError("valid and AOI masks use different grids")
    denominator = int(np.count_nonzero(inside))
    if denominator == 0:
        raise SentinelMosaicContractError("AOI contains no native raster pixel centers")
    return float(np.count_nonzero(valid & inside) / denominator)


def _rgb_images(
    np: Any,
    Image: Any,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    valid: Any,
) -> tuple[Any, Any]:
    before_rgb = np.stack([before["red"], before["green"], before["blue"]], axis=-1)
    after_rgb = np.stack([after["red"], after["green"], after["blue"]], axis=-1)
    combined = np.concatenate([before_rgb[valid], after_rgb[valid]], axis=0)
    lows = np.quantile(combined, 0.02, axis=0)
    highs = np.quantile(combined, 0.98, axis=0)
    span = np.maximum(highs - lows, 1e-6)

    def render(rgb: Any) -> Any:
        stretched = np.clip((rgb - lows) / span, 0, 1)
        stretched = np.power(stretched, 0.85)
        pixels = (stretched * 255).astype(np.uint8)
        pixels[~valid] = np.array([96, 96, 96], dtype=np.uint8)
        return Image.fromarray(pixels)

    return render(before_rgb), render(after_rgb)


def _write_proposals(
    np: Any,
    shapes: Any,
    transform_geom: Any,
    output: Path,
    mask: Any,
    transform: Any,
    crs: Any,
    *,
    minimum_area_m2: float,
) -> tuple[int, float]:
    def ring_area(ring: Sequence[Sequence[float]]) -> float:
        return abs(
            sum(
                float(x1) * float(y2) - float(x2) * float(y1)
                for (x1, y1), (x2, y2) in zip(ring, ring[1:])
            )
        ) / 2

    def geometry_area(geometry: Mapping[str, Any]) -> float:
        coordinates = geometry.get("coordinates", [])
        if geometry.get("type") == "Polygon":
            polygons = [coordinates]
        elif geometry.get("type") == "MultiPolygon":
            polygons = coordinates
        else:
            return 0.0
        return sum(
            max(
                0.0,
                ring_area(polygon[0])
                - sum(ring_area(hole) for hole in polygon[1:]),
            )
            for polygon in polygons
            if polygon
        )

    features: list[dict[str, Any]] = []
    total_area = 0.0
    for geometry, value in shapes(
        mask.astype(np.uint8), mask=mask, transform=transform
    ):
        if int(value) != 1:
            continue
        area = geometry_area(geometry)
        if area < minimum_area_m2:
            continue
        rounded_area = round(area, 1)
        total_area += rounded_area
        features.append(
            {
                "type": "Feature",
                "id": f"change-proposal-{len(features) + 1}",
                "geometry": transform_geom(
                    crs, "EPSG:4326", geometry, precision=7
                ),
                "properties": {
                    "class": "large_spectral_change_candidate",
                    "area_m2": rounded_area,
                    "identity_claim": False,
                    "lifecycle_claim": False,
                    "operating_status_claim": False,
                    "power_claim": False,
                    "energy_claim": False,
                    "operator_claim": False,
                    "data_centre_type_claim": False,
                    "it_capacity_claim": False,
                    "pue_claim": False,
                    "workload_claim": False,
                    "review_required": True,
                },
            }
        )
    output.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": features,
                "properties": GEOJSON_COLLECTION_PROPERTIES,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(features), total_area


def _epoch_summary(
    primary_item: Mapping[str, Any], items: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    properties = primary_item["properties"]
    return {
        "primary_id": primary_item["id"],
        "datatake_id": properties["s2:datatake_id"],
        "datastrip_id": properties["s2:datastrip_id"],
        "items": [
            item_summary(item)
            for item in sorted(items, key=lambda value: str(value["id"]))
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-stac", required=True, type=Path)
    parser.add_argument("--baseline-stac-sha256", required=True, type=parse_sha256)
    parser.add_argument("--baseline-primary", required=True, type=parse_item_binding)
    parser.add_argument(
        "--baseline-companion", action="append", default=[], type=parse_item_binding
    )
    parser.add_argument("--current-stac", required=True, type=Path)
    parser.add_argument("--current-stac-sha256", required=True, type=parse_sha256)
    parser.add_argument("--current-primary", required=True, type=parse_item_binding)
    parser.add_argument(
        "--current-companion", action="append", default=[], type=parse_item_binding
    )
    parser.add_argument("--bbox", required=True, type=parse_bbox)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--entity-name", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--minimum-component-area-m2", type=float, default=5_000.0)
    return parser


def _normalize_bbox_argument(argv: Sequence[str] | None) -> list[str]:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        index = arguments.index("--bbox")
        value = arguments[index + 1]
    except (ValueError, IndexError):
        return arguments
    if value.startswith("-"):
        arguments[index : index + 2] = [f"--bbox={value}"]
    return arguments


def _require_distinct_epochs(
    baseline_primary: Mapping[str, Any], current_primary: Mapping[str, Any]
) -> None:
    baseline_instant = parse_rfc3339_instant(
        baseline_primary["properties"].get("datetime"),
        "baseline primary datetime",
    )
    current_instant = parse_rfc3339_instant(
        current_primary["properties"].get("datetime"),
        "current primary datetime",
    )
    if baseline_instant >= current_instant:
        raise SentinelMosaicContractError(
            "baseline primary datetime must precede current primary datetime"
        )
    baseline_tile = (
        baseline_primary["properties"].get("mgrs:utm_zone"),
        baseline_primary["properties"].get("mgrs:latitude_band"),
        baseline_primary["properties"].get("mgrs:grid_square"),
    )
    current_tile = (
        current_primary["properties"].get("mgrs:utm_zone"),
        current_primary["properties"].get("mgrs:latitude_band"),
        current_primary["properties"].get("mgrs:grid_square"),
    )
    if baseline_tile != current_tile:
        raise SentinelMosaicContractError(
            "baseline and current primary items must use the same MGRS tile"
        )


def _require_equal_epoch_primary_grids(
    baseline_primary: Mapping[str, Any], current_primary: Mapping[str, Any]
) -> None:
    """Require the frozen primary scene grids to be identical across epochs."""

    for asset_name in ("red", "swir16", "scl"):
        if grid_from_item(baseline_primary, asset_name) != grid_from_item(
            current_primary, asset_name
        ):
            raise SentinelMosaicContractError(
                f"baseline and current primary {asset_name} grids must be exactly equal"
            )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(_normalize_bbox_argument(argv))
    if args.minimum_component_area_m2 <= 0:
        raise SystemExit("--minimum-component-area-m2 must be greater than zero")
    if args.output_dir.exists():
        if not args.output_dir.is_dir() or any(args.output_dir.iterdir()):
            raise SystemExit("--output-dir must be absent or an empty directory")
    (
        np,
        Affine,
        Image,
        rasterio,
        Resampling,
        shapes,
        reproject,
        transform_coordinates,
        transform_bounds,
        geo,
    ) = _imports()
    transform_geom, Window = geo

    baseline_document = _read_bound_json(
        args.baseline_stac, args.baseline_stac_sha256
    )
    current_document = _read_bound_json(
        args.current_stac, args.current_stac_sha256
    )
    baseline_primary, baseline_items = select_bound_items(
        baseline_document, args.baseline_primary, args.baseline_companion
    )
    current_primary, current_items = select_bound_items(
        current_document, args.current_primary, args.current_companion
    )
    _require_distinct_epochs(baseline_primary, current_primary)
    validate_epoch_grid_contract(baseline_items)
    validate_epoch_grid_contract(current_items)
    _require_equal_epoch_primary_grids(baseline_primary, current_primary)
    baseline_coverage = epoch_metadata_coverage(
        baseline_primary, baseline_items, args.bbox, transform_bounds
    )
    current_coverage = epoch_metadata_coverage(
        current_primary, current_items, args.bbox, transform_bounds
    )
    if not baseline_coverage["complete"] or not current_coverage["complete"]:
        raise SentinelMosaicContractError(
            "explicit item bindings do not provide complete metadata-grid coverage"
        )

    shape, transform, crs, _ = _target_grid(
        Affine, rasterio, transform_bounds, baseline_primary, args.bbox
    )
    target_grid = (shape, transform, crs)
    baseline, baseline_clear = _read_scene(
        np,
        Affine,
        rasterio,
        Resampling,
        reproject,
        Window,
        baseline_primary,
        baseline_items,
        target_grid,
    )
    current, current_clear = _read_scene(
        np,
        Affine,
        rasterio,
        Resampling,
        reproject,
        Window,
        current_primary,
        current_items,
        target_grid,
    )
    aoi_mask = _rasterize_exact_aoi_center_mask(
        np,
        transform_coordinates,
        args.bbox,
        transform,
        crs,
        shape,
    )
    valid = baseline_clear & current_clear & aoi_mask
    result = derive_change(baseline, current, valid)
    result["metrics"]["valid_pixel_fraction"] = _valid_pixel_fraction(
        np, result["valid_mask"], aoi_mask
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    before_image, after_image = _rgb_images(
        np, Image, baseline, current, result["valid_mask"]
    )
    before_path = args.output_dir / "before.png"
    after_path = args.output_dir / "after.png"
    before_image.save(before_path, optimize=True)
    after_image.save(after_path, optimize=True)

    overlay = np.asarray(after_image).copy()
    proposal = result["proposal_mask"]
    overlay[proposal] = (
        0.45 * overlay[proposal] + 0.55 * np.array([255, 36, 36])
    ).astype(np.uint8)
    overlay_path = args.output_dir / "change-overlay.png"
    overlay_image = Image.fromarray(overlay)
    overlay_image.save(overlay_path, optimize=True)
    comparison = Image.new("RGB", (before_image.width * 3, before_image.height))
    comparison.paste(before_image, (0, 0))
    comparison.paste(after_image, (before_image.width, 0))
    comparison.paste(overlay_image, (before_image.width * 2, 0))
    comparison_path = args.output_dir / "comparison.png"
    comparison.save(comparison_path, optimize=True)

    proposals_path = args.output_dir / "change-proposals.geojson"
    feature_count, proposal_area = _write_proposals(
        np,
        shapes,
        transform_geom,
        proposals_path,
        proposal,
        transform,
        crs,
        minimum_area_m2=args.minimum_component_area_m2,
    )
    pixel_area = abs(float(transform.a * transform.e - transform.b * transform.d))
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
        "entity": {"id": args.entity_id, "name": args.entity_name},
        "aoi_bbox_wgs84": list(args.bbox),
        "baseline": _epoch_summary(baseline_primary, baseline_items),
        "current": _epoch_summary(current_primary, current_items),
        "source": report_source(baseline_primary, current_primary),
        "classification": REPORT_CLASSIFICATION,
        "mosaic_contract": {
            "explicit_item_hash_bindings": True,
            "same_datatake_and_datastrip_required": True,
            "maximum_companion_sensing_time_delta_seconds": (
                MAX_COMPANION_TIME_DELTA_SECONDS
            ),
            "product_uri_identity_policy": "exact_except_mgrs_tile_token",
            "frozen_stac_response_sha256": {
                "baseline": args.baseline_stac_sha256,
                "current": args.current_stac_sha256,
            },
            "nonzero_overlap_conflict_policy": "reject",
            "missing_spatial_coverage_policy": "reject",
            "nodata_policy": "invalid_never_clear",
            "baseline_metadata_coverage": baseline_coverage,
            "current_metadata_coverage": current_coverage,
        },
        "grid": {
            "crs": str(crs),
            "width": int(proposal.shape[1]),
            "height": int(proposal.shape[0]),
            "pixel_area_m2": pixel_area,
            "clear_scl_classes": sorted(CLEAR_SCL_CLASSES),
            "aoi_inclusion": "exact_wgs84_pixel_centers",
        },
        "thresholds": result["thresholds"],
        "radiometry": {
            "reflectance": "STAC raster scale and offset applied per epoch and band",
            "normalized_index_negative_reflectance_policy": "clip_to_zero",
        },
        "metrics": {
            **result["metrics"],
            "proposal_component_count": feature_count,
            "proposal_area_m2_after_component_filter": round(proposal_area, 1),
        },
        "outputs": {},
    }
    for output in (
        before_path,
        after_path,
        overlay_path,
        comparison_path,
        proposals_path,
    ):
        report["outputs"][output.name] = {
            "sha256": _sha256(output),
            "bytes": output.stat().st_size,
        }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"output": str(report_path.resolve()), **report["metrics"]},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SentinelMosaicContractError as error:
        raise SystemExit(str(error)) from error
