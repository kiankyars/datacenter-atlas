#!/usr/bin/env python3
"""Create a bounded Sentinel-2 before/after change-evidence bundle."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change import (
    ALGORITHM_VERSION,
    CLEAR_SCL_CLASSES,
    REPORT_SCHEMA_VERSION,
    asset_scale_offset,
    derive_change,
    ensure_comparable,
    item_summary,
    parse_bbox,
    report_source,
    select_feature,
    validate_asset_href,
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _imports() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    try:
        import numpy as np
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
        from rasterio.windows import Window, from_bounds
    except ImportError as exc:
        raise SystemExit(
            "Install the optional imagery runtime, for example: "
            "uv run --python 3.12 --with numpy --with pillow --with rasterio "
            "python datacenter_atlas/scripts/sentinel_change.py ..."
        ) from exc
    return (
        np,
        Image,
        rasterio,
        Resampling,
        shapes,
        transform_bounds,
        (transform_geom, transform_coordinates, reproject, Window, from_bounds),
    )


def _covering_window(
    transform_bounds: Any,
    from_bounds: Any,
    Window: Any,
    bbox: tuple[float, float, float, float],
    crs: Any,
    grid_transform: Any,
) -> Any:
    """Return the smallest native window that covers the projected AOI envelope."""

    projected = transform_bounds("EPSG:4326", crs, *bbox)
    fractional = from_bounds(*projected, transform=grid_transform)
    column_start = math.floor(float(fractional.col_off))
    row_start = math.floor(float(fractional.row_off))
    column_stop = math.ceil(float(fractional.col_off + fractional.width))
    row_stop = math.ceil(float(fractional.row_off + fractional.height))
    if column_stop <= column_start or row_stop <= row_start:
        raise ValueError("AOI does not produce a positive native covering window")
    return Window(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    )


def _require_window_within_grid(
    window: Any,
    width: int,
    height: int,
    asset_name: str,
) -> None:
    """Reject an AOI that cannot be represented by one complete asset grid."""

    if (
        float(window.col_off) < 0
        or float(window.row_off) < 0
        or float(window.col_off + window.width) > width
        or float(window.row_off + window.height) > height
    ):
        raise ValueError(
            f"AOI covering window crosses asset {asset_name}; "
            "a future multi-tile mosaic is required"
        )


def _pad_window(window: Any, Window: Any, pixels: int) -> Any:
    """Expand a native window by a fixed interpolation-support halo."""

    if isinstance(pixels, bool) or not isinstance(pixels, int) or pixels <= 0:
        raise ValueError("window padding must be a positive integer")
    return Window(
        window.col_off - pixels,
        window.row_off - pixels,
        window.width + 2 * pixels,
        window.height + 2 * pixels,
    )


def _align_to_target_grid(
    np: Any,
    reproject: Any,
    source: Any,
    source_transform: Any,
    source_crs: Any,
    source_nodata: Any,
    target_grid: tuple[tuple[int, int], Any, Any],
    resampling: Any,
) -> tuple[Any, Any, Any]:
    """Reproject one bounded native array onto an exact shared target grid."""

    target_shape, target_transform, target_crs = target_grid
    if (
        not isinstance(target_shape, tuple)
        or len(target_shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in target_shape
        )
    ):
        raise ValueError("target grid shape must contain positive height and width")
    destination = np.zeros(target_shape, dtype=source.dtype)
    aligned, resolved_transform = reproject(
        source=source,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=0 if source_nodata is None else source_nodata,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=0,
        resampling=resampling,
        init_dest_nodata=True,
        num_threads=1,
    )
    if aligned.shape != target_shape or resolved_transform != target_transform:
        raise ValueError("asset reprojection did not preserve the exact target grid")
    return aligned, resolved_transform, target_crs


def _read_asset(
    np: Any,
    rasterio: Any,
    Resampling: Any,
    transform_bounds: Any,
    reproject: Any,
    Window: Any,
    from_bounds: Any,
    item: Mapping[str, Any],
    asset_name: str,
    bbox: tuple[float, float, float, float],
    *,
    target_grid: tuple[tuple[int, int], Any, Any] | None = None,
    resampling: Any | None = None,
) -> tuple[Any, Any, Any]:
    href = item["assets"][asset_name]["href"]
    validate_asset_href(href)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(href) as source:
            window = _covering_window(
                transform_bounds,
                from_bounds,
                Window,
                bbox,
                source.crs,
                source.transform,
            )
            _require_window_within_grid(
                window,
                int(source.width),
                int(source.height),
                asset_name,
            )
            selected_resampling = (
                Resampling.bilinear if resampling is None else resampling
            )
            if target_grid is not None and selected_resampling == Resampling.bilinear:
                support_window = _pad_window(window, Window, 1)
                _require_window_within_grid(
                    support_window,
                    int(source.width),
                    int(source.height),
                    asset_name,
                )
                return _align_to_target_grid(
                    np,
                    reproject,
                    rasterio.band(source, 1),
                    source.transform,
                    source.crs,
                    source.nodata,
                    target_grid,
                    selected_resampling,
                )
            array = source.read(
                1,
                window=window,
            )
            window_transform = source.window_transform(window)
            expected_shape = (int(window.height), int(window.width))
            if array.shape != expected_shape:
                raise ValueError(
                    f"asset {asset_name} read was clipped instead of preserving "
                    "the requested covering window"
                )
            if target_grid is not None:
                return _align_to_target_grid(
                    np,
                    reproject,
                    array,
                    window_transform,
                    source.crs,
                    source.nodata,
                    target_grid,
                    selected_resampling,
                )
            return array, window_transform, source.crs


def _read_scene(
    np: Any,
    rasterio: Any,
    Resampling: Any,
    transform_bounds: Any,
    reproject: Any,
    Window: Any,
    from_bounds: Any,
    item: Mapping[str, Any],
    bbox: tuple[float, float, float, float],
    *,
    target_grid: tuple[tuple[int, int], Any, Any] | None = None,
) -> tuple[dict[str, Any], Any, Any, Any]:
    red, transform, crs = _read_asset(
        np,
        rasterio,
        Resampling,
        transform_bounds,
        reproject,
        Window,
        from_bounds,
        item,
        "red",
        bbox,
        target_grid=target_grid,
    )
    shape = red.shape
    shared_grid = (shape, transform, crs)
    raw = {"red": red}
    for asset_name in ("green", "blue", "nir", "swir16"):
        raw[asset_name], asset_transform, asset_crs = _read_asset(
            np,
            rasterio,
            Resampling,
            transform_bounds,
            reproject,
            Window,
            from_bounds,
            item,
            asset_name,
            bbox,
            target_grid=shared_grid,
        )
        if asset_crs != crs or asset_transform != transform:
            raise ValueError(f"asset {asset_name} did not align to the red grid")
    scl, scl_transform, scl_crs = _read_asset(
        np,
        rasterio,
        Resampling,
        transform_bounds,
        reproject,
        Window,
        from_bounds,
        item,
        "scl",
        bbox,
        target_grid=shared_grid,
        resampling=Resampling.nearest,
    )
    if scl_crs != crs or scl_transform != transform:
        raise ValueError("asset scl did not align to the red grid")

    reflectance: dict[str, Any] = {}
    for asset_name, array in raw.items():
        scale, offset = asset_scale_offset(item, asset_name)
        reflectance[asset_name] = array.astype(np.float32) * scale + offset
    clear = np.isin(scl, list(CLEAR_SCL_CLASSES))
    clear &= np.stack([array > 0 for array in raw.values()]).all(axis=0)
    return reflectance, clear, transform, crs


def _rasterize_exact_aoi_center_mask(
    np: Any,
    transform_coordinates: Any,
    bbox: tuple[float, float, float, float],
    grid_transform: Any,
    crs: Any,
    shape: tuple[int, int],
) -> Any:
    """Rasterize a WGS84 bbox by testing native-grid pixel centers.

    The bounded read still uses the projected axis-aligned envelope needed by
    rasterio, but that envelope is not the analysis AOI. Transforming every
    native pixel center back to WGS84 preserves the exact queue rectangle even
    where its edges curve in the projected CRS.
    """

    if (
        not isinstance(shape, tuple)
        or len(shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in shape
        )
    ):
        raise ValueError("analysis grid shape must contain positive height and width")
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
        crs,
        "EPSG:4326",
        xs.ravel(),
        ys.ravel(),
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
        raise ValueError("AOI contains no native raster pixel centers")
    return inside


def _valid_pixel_fraction(np: Any, valid_mask: Any, aoi_mask: Any) -> float:
    """Return mutually valid AOI pixels divided by exact AOI pixels."""

    valid = np.asarray(valid_mask, dtype=bool)
    inside = np.asarray(aoi_mask, dtype=bool)
    if valid.shape != inside.shape:
        raise ValueError("valid and AOI masks must share one pixel grid")
    pixels_inside_aoi = int(np.count_nonzero(inside))
    if pixels_inside_aoi == 0:
        raise ValueError("AOI contains no native raster pixel centers")
    valid_inside_aoi = int(np.count_nonzero(valid & inside))
    return float(valid_inside_aoi / pixels_inside_aoi)


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
            max(0.0, ring_area(polygon[0]) - sum(ring_area(hole) for hole in polygon[1:]))
            for polygon in polygons
            if polygon
        )

    features: list[dict[str, Any]] = []
    total_area = 0.0
    for geometry, value in shapes(mask.astype(np.uint8), mask=mask, transform=transform):
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
                "geometry": transform_geom(crs, "EPSG:4326", geometry, precision=7),
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
                "properties": {
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
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(features), total_area


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-stac", required=True, type=Path)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--current-stac", required=True, type=Path)
    parser.add_argument("--current-id", required=True)
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(_normalize_bbox_argument(argv))
    if args.minimum_component_area_m2 <= 0:
        raise SystemExit("--minimum-component-area-m2 must be greater than zero")
    np, Image, rasterio, Resampling, shapes, transform_bounds, geo = _imports()
    transform_geom, transform_coordinates, reproject, Window, from_bounds = geo

    baseline_document = _json(args.baseline_stac)
    current_document = _json(args.current_stac)
    baseline_item = select_feature(baseline_document, args.baseline_id)
    current_item = select_feature(current_document, args.current_id)
    ensure_comparable(baseline_item, current_item)

    baseline, baseline_clear, transform, crs = _read_scene(
        np,
        rasterio,
        Resampling,
        transform_bounds,
        reproject,
        Window,
        from_bounds,
        baseline_item,
        args.bbox,
    )
    current, current_clear, current_transform, current_crs = _read_scene(
        np,
        rasterio,
        Resampling,
        transform_bounds,
        reproject,
        Window,
        from_bounds,
        current_item,
        args.bbox,
        target_grid=(baseline["red"].shape, transform, crs),
    )
    if current_crs != crs or current_transform != transform:
        raise ValueError("scene grids are not co-registered after bounded reads")
    aoi_mask = _rasterize_exact_aoi_center_mask(
        np,
        transform_coordinates,
        args.bbox,
        transform,
        crs,
        baseline["red"].shape,
    )
    valid = baseline_clear & current_clear & aoi_mask
    result = derive_change(baseline, current, valid)
    result["metrics"]["valid_pixel_fraction"] = _valid_pixel_fraction(
        np,
        result["valid_mask"],
        aoi_mask,
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
        "entity": {"id": args.entity_id, "name": args.entity_name},
        "aoi_bbox_wgs84": list(args.bbox),
        "baseline": item_summary(baseline_item),
        "current": item_summary(current_item),
        "source": report_source(baseline_item, current_item),
        "classification": {
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
                "Operator, data-centre type, IT capacity, PUE, workload, power, energy, and operating status cannot be inferred from this evidence bundle.",
            ],
        },
        "grid": {
            "crs": str(crs),
            "width": int(proposal.shape[1]),
            "height": int(proposal.shape[0]),
            "pixel_area_m2": pixel_area,
            "clear_scl_classes": sorted(CLEAR_SCL_CLASSES),
        },
        "thresholds": result["thresholds"],
        "radiometry": {
            "reflectance": "STAC raster scale and offset applied per scene and band",
            "normalized_index_negative_reflectance_policy": "clip_to_zero",
        },
        "metrics": {
            **result["metrics"],
            "proposal_component_count": feature_count,
            "proposal_area_m2_after_component_filter": round(proposal_area, 1),
        },
        "outputs": {},
    }
    for path in (before_path, after_path, overlay_path, comparison_path, proposals_path):
        report["outputs"][path.name] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(report_path.resolve()), **report["metrics"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
