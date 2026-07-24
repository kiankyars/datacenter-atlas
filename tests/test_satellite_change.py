from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

from datacenter_atlas.satellite_change_batch import (
    SatelliteChangeBatchError,
    _validate_geojson,
)
from datacenter_atlas.satellite_change import (
    EARTH_SEARCH_ASSET_HOST,
    EARTH_SEARCH_ASSET_PATH_PREFIX,
    asset_scale_offset,
    canonical_sha256,
    ensure_comparable,
    item_summary,
    parse_bbox,
    select_feature,
)
from scripts.sentinel_change import (
    _align_to_target_grid,
    _covering_window,
    _normalize_bbox_argument,
    _pad_window,
    _read_asset,
    _rasterize_exact_aoi_center_mask,
    _require_window_within_grid,
    _valid_pixel_fraction,
    _write_proposals,
    build_parser,
)


def _item(item_id: str, when: str, tile: str = "15SYU") -> dict[str, object]:
    zone = int(tile[:2])
    assets = {
        key: {
            "href": (
                f"https://{EARTH_SEARCH_ASSET_HOST}{EARTH_SEARCH_ASSET_PATH_PREFIX}"
                f"{zone}/{tile[2]}/{tile[3:]}/{when[:4]}/{item_id}/{key}.tif"
            ),
            "raster:bands": [{"scale": 0.0001, "offset": -0.1}],
        }
        for key in ("red", "green", "blue", "nir", "swir16", "scl")
    }
    assets["scl"] = {
        "href": (
            f"https://{EARTH_SEARCH_ASSET_HOST}{EARTH_SEARCH_ASSET_PATH_PREFIX}"
            f"{zone}/{tile[2]}/{tile[3:]}/{when[:4]}/{item_id}/scl.tif"
        )
    }
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "properties": {
            "datetime": when,
            "eo:cloud_cover": 1.5,
            "mgrs:utm_zone": zone,
            "mgrs:latitude_band": tile[2],
            "mgrs:grid_square": tile[3:],
        },
        "assets": assets,
    }


class SatelliteChangeMetadataTests(unittest.TestCase):
    def test_covering_windows_omit_no_frozen_aoi_pixel_centers(self) -> None:
        from affine import Affine
        import numpy as np
        from rasterio.enums import Resampling
        from rasterio.windows import Window, from_bounds, transform as window_transform
        from rasterio.warp import reproject
        from rasterio.warp import transform as transform_coordinates
        from rasterio.warp import transform_bounds

        fixtures = (
            (
                "satq-9e1d2b4c11c8f416b4c8eea8",
                (-77.5309118, 38.71965, -77.484794, 38.7556228),
                "EPSG:32617",
                Affine(10, 0, 699960, 0, -10, 4400040),
                (10150, 10451, 417, 415),
                160_362,
                6,
            ),
            (
                "satq-0415838405650334018145ec",
                (-77.5309118, 38.71965, -77.484794, 38.7556228),
                "EPSG:32617",
                Affine(10, 0, 699960, 0, -10, 4400040),
                (10150, 10451, 417, 415),
                160_362,
                6,
            ),
            (
                "satq-fddd4db6778876be9e76cc4c",
                (-80.5564315, 33.1589737, -80.5134525, 33.1949465),
                "EPSG:32617",
                Affine(10, 0, 499980, 0, -10, 3700020),
                (4136, 2701, 403, 402),
                159_785,
                102,
            ),
            (
                "satq-18542a69413d3f8a7d012ea9",
                (-97.4168483, 32.8846205, -97.3740029, 32.9205933),
                "EPSG:32614",
                Affine(10, 0, 600000, 0, -10, 3700020),
                (4803, 5636, 407, 406),
                159_880,
                0,
            ),
            (
                "satq-51c83c399743270854947aea",
                (-80.5580555, 33.159712, -80.5150761, 33.1956848),
                "EPSG:32617",
                Affine(10, 0, 499980, 0, -10, 3700020),
                (4121, 2693, 403, 402),
                159_778,
                64,
            ),
        )
        for (
            queue_id,
            bbox,
            crs,
            source_transform,
            expected_window,
            expected_aoi_pixels,
            legacy_omissions,
        ) in fixtures:
            with self.subTest(queue_id=queue_id):
                window = _covering_window(
                    transform_bounds,
                    from_bounds,
                    Window,
                    bbox,
                    crs,
                    source_transform,
                )
                self.assertEqual(
                    (
                        int(window.col_off),
                        int(window.row_off),
                        int(window.width),
                        int(window.height),
                    ),
                    expected_window,
                )
                _require_window_within_grid(window, 10_980, 10_980, "red")
                mask = _rasterize_exact_aoi_center_mask(
                    np,
                    transform_coordinates,
                    bbox,
                    window_transform(window, source_transform),
                    crs,
                    (int(window.height), int(window.width)),
                )
                self.assertEqual(int(mask.sum()), expected_aoi_pixels)

                reference = Window(
                    window.col_off - 2,
                    window.row_off - 2,
                    window.width + 4,
                    window.height + 4,
                )
                reference_mask = _rasterize_exact_aoi_center_mask(
                    np,
                    transform_coordinates,
                    bbox,
                    window_transform(reference, source_transform),
                    crs,
                    (int(reference.height), int(reference.width)),
                )
                self.assertEqual(int(reference_mask.sum()) - int(mask.sum()), 0)

                projected = transform_bounds("EPSG:4326", crs, *bbox)
                legacy = from_bounds(
                    *projected,
                    transform=source_transform,
                ).round_offsets().round_lengths()
                legacy_mask = _rasterize_exact_aoi_center_mask(
                    np,
                    transform_coordinates,
                    bbox,
                    window_transform(legacy, source_transform),
                    crs,
                    (int(legacy.height), int(legacy.width)),
                )
                self.assertEqual(
                    expected_aoi_pixels - int(legacy_mask.sum()),
                    legacy_omissions,
                )

                target_grid = (
                    (int(window.height), int(window.width)),
                    window_transform(window, source_transform),
                    crs,
                )
                scl_transform = Affine(
                    20,
                    0,
                    source_transform.c,
                    0,
                    -20,
                    source_transform.f,
                )
                scl_window = _covering_window(
                    transform_bounds,
                    from_bounds,
                    Window,
                    bbox,
                    crs,
                    scl_transform,
                )
                reference_window = _pad_window(scl_window, Window, 2)

                def categorical_values(native_window: Window) -> object:
                    rows = np.arange(
                        int(native_window.row_off),
                        int(native_window.row_off + native_window.height),
                    )[:, None]
                    columns = np.arange(
                        int(native_window.col_off),
                        int(native_window.col_off + native_window.width),
                    )[None, :]
                    return ((rows * 3 + columns * 5) % 4 + 4).astype(np.uint8)

                scl, _, _ = _align_to_target_grid(
                    np,
                    reproject,
                    categorical_values(scl_window),
                    window_transform(scl_window, scl_transform),
                    crs,
                    0,
                    target_grid,
                    Resampling.nearest,
                )
                full_source_reference, _, _ = _align_to_target_grid(
                    np,
                    reproject,
                    categorical_values(reference_window),
                    window_transform(reference_window, scl_transform),
                    crs,
                    0,
                    target_grid,
                    Resampling.nearest,
                )
                np.testing.assert_array_equal(scl, full_source_reference)

    def test_covering_window_rejects_dataset_edge_crossing(self) -> None:
        from rasterio.windows import Window

        _require_window_within_grid(Window(0, 0, 100, 100), 100, 100, "red")
        for window in (
            Window(-1, 0, 100, 100),
            Window(0, -1, 100, 100),
            Window(0, 0, 101, 100),
            Window(0, 0, 100, 101),
        ):
            with self.subTest(window=window):
                with self.assertRaisesRegex(ValueError, "multi-tile mosaic"):
                    _require_window_within_grid(window, 100, 100, "red")
        support = _pad_window(Window(1, 1, 98, 98), Window, 1)
        self.assertEqual(support, Window(0, 0, 100, 100))
        _require_window_within_grid(support, 100, 100, "swir16")
        with self.assertRaisesRegex(ValueError, "multi-tile mosaic"):
            _require_window_within_grid(
                _pad_window(Window(0, 0, 100, 100), Window, 1),
                100,
                100,
                "swir16",
            )

    def test_bilinear_halo_matches_full_source_reference(self) -> None:
        from affine import Affine
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.io import MemoryFile
        from rasterio.warp import reproject

        full = (
            np.arange(64, dtype=np.uint16).reshape(8, 8) * 3 + 10
        ).astype(np.uint16)
        full_transform = Affine(20, 0, 500000, 0, -20, 3700160)
        target_grid = (
            (8, 8),
            Affine(10, 0, 500040, 0, -10, 3700120),
            "EPSG:32617",
        )
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff",
                width=8,
                height=8,
                count=1,
                dtype="uint16",
                crs="EPSG:32617",
                transform=full_transform,
                nodata=0,
            ) as dataset:
                dataset.write(full, 1)
                reference, _, _ = _align_to_target_grid(
                    np,
                    reproject,
                    rasterio.band(dataset, 1),
                    dataset.transform,
                    dataset.crs,
                    dataset.nodata,
                    target_grid,
                    Resampling.bilinear,
                )

        unpadded, _, _ = _align_to_target_grid(
            np,
            reproject,
            full[2:6, 2:6],
            Affine(20, 0, 500040, 0, -20, 3700120),
            "EPSG:32617",
            0,
            target_grid,
            Resampling.bilinear,
        )
        padded, padded_transform, _ = _align_to_target_grid(
            np,
            reproject,
            full[1:7, 1:7],
            Affine(20, 0, 500020, 0, -20, 3700140),
            "EPSG:32617",
            0,
            target_grid,
            Resampling.bilinear,
        )
        self.assertEqual(int(np.count_nonzero(unpadded != reference)), 28)
        self.assertEqual(
            int(np.max(np.abs(unpadded.astype(int) - reference.astype(int)))),
            7,
        )
        np.testing.assert_array_equal(padded, reference)
        self.assertEqual(padded_transform, target_grid[1])

    def test_read_asset_preserves_falsy_nearest_resampling(self) -> None:
        from affine import Affine
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.io import MemoryFile
        from rasterio.windows import Window, from_bounds
        from rasterio.warp import reproject, transform_bounds

        source = np.array(
            [
                [0, 0, 0, 0],
                [0, 4, 5, 0],
                [0, 6, 7, 0],
                [0, 0, 0, 0],
            ],
            dtype=np.uint8,
        )
        source_transform = Affine(1, 0, 0, 0, -1, 4)
        target_grid = (
            (4, 4),
            Affine(0.5, 0, 1, 0, -0.5, 3),
            rasterio.crs.CRS.from_epsg(4326),
        )
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff",
                width=4,
                height=4,
                count=1,
                dtype="uint8",
                crs="EPSG:4326",
                transform=source_transform,
                nodata=0,
            ) as dataset:
                dataset.write(source, 1)
            item = {"assets": {"scl": {"href": memory.name}}}
            with mock.patch(
                "scripts.sentinel_change.validate_asset_href",
                return_value=None,
            ):
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="Setting the shape on a NumPy array has been deprecated",
                        category=DeprecationWarning,
                    )
                    aligned, aligned_transform, aligned_crs = _read_asset(
                        np,
                        rasterio,
                        Resampling,
                        transform_bounds,
                        reproject,
                        Window,
                        from_bounds,
                        item,
                        "scl",
                        (1.0, 1.0, 3.0, 3.0),
                        target_grid=target_grid,
                        resampling=Resampling.nearest,
                    )
        np.testing.assert_array_equal(
            aligned,
            np.array(
                [
                    [4, 4, 5, 5],
                    [4, 4, 5, 5],
                    [6, 6, 7, 7],
                    [6, 6, 7, 7],
                ],
                dtype=np.uint8,
            ),
        )
        self.assertEqual(aligned_transform, target_grid[1])
        self.assertEqual(aligned_crs, target_grid[2])

    def test_native_band_is_reprojected_to_exact_red_grid(self) -> None:
        from affine import Affine
        import numpy as np
        from rasterio.enums import Resampling
        from rasterio.warp import reproject

        source = np.array([[1, 2], [3, 4]], dtype=np.uint16)
        target_grid = (
            (4, 4),
            Affine(10, 0, 500000, 0, -10, 3700000),
            "EPSG:32617",
        )
        aligned, aligned_transform, aligned_crs = _align_to_target_grid(
            np,
            reproject,
            source,
            Affine(20, 0, 500000, 0, -20, 3700000),
            "EPSG:32617",
            0,
            target_grid,
            Resampling.nearest,
        )
        np.testing.assert_array_equal(
            aligned,
            np.array(
                [
                    [1, 1, 2, 2],
                    [1, 1, 2, 2],
                    [3, 3, 4, 4],
                    [3, 3, 4, 4],
                ],
                dtype=np.uint16,
            ),
        )
        self.assertEqual(aligned.shape, target_grid[0])
        self.assertEqual(aligned_transform, target_grid[1])
        self.assertEqual(aligned_crs, target_grid[2])

    def test_exact_aoi_mask_clips_projected_envelope_and_preserves_tolerance(self) -> None:
        import numpy as np
        from affine import Affine
        from rasterio.features import shapes
        from rasterio.warp import transform as transform_coordinates
        from rasterio.warp import transform_geom

        bbox = (-97.4168483, 32.8846205, -97.3740029, 32.9205933)
        grid_transform = Affine(10, 0, 648030, 0, -10, 3643660)
        grid_shape = (406, 407)
        aoi_mask = _rasterize_exact_aoi_center_mask(
            np,
            transform_coordinates,
            bbox,
            grid_transform,
            "EPSG:32614",
            grid_shape,
        )
        self.assertEqual(int(aoi_mask.sum()), 159_880)
        self.assertEqual(aoi_mask.size - int(aoi_mask.sum()), 5_362)
        with self.assertRaisesRegex(ValueError, "no native raster pixel centers"):
            _rasterize_exact_aoi_center_mask(
                np,
                transform_coordinates,
                (0.0, 0.0, 0.0001, 0.0001),
                grid_transform,
                "EPSG:32614",
                grid_shape,
            )

        valid = np.ones(grid_shape, dtype=bool)
        first_inside = tuple(np.argwhere(aoi_mask)[0])
        valid[first_inside] = False
        self.assertEqual(
            _valid_pixel_fraction(np, valid, aoi_mask),
            159_879 / 159_880,
        )
        with self.assertRaisesRegex(ValueError, "no native raster pixel centers"):
            _valid_pixel_fraction(
                np,
                valid,
                np.zeros(grid_shape, dtype=bool),
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unmasked_path = root / "unmasked.geojson"
            unmasked_count, unmasked_area = _write_proposals(
                np,
                shapes,
                transform_geom,
                unmasked_path,
                np.ones(grid_shape, dtype=bool),
                grid_transform,
                "EPSG:32614",
                minimum_area_m2=1,
            )
            with self.assertRaisesRegex(
                SatelliteChangeBatchError,
                "outside the queue AOI",
            ):
                _validate_geojson(
                    unmasked_path,
                    expected_count=unmasked_count,
                    expected_area_m2=unmasked_area,
                    minimum_component_area_m2=1,
                    aoi_bbox=bbox,
                )

            masked_path = root / "masked.geojson"
            masked_count, masked_area = _write_proposals(
                np,
                shapes,
                transform_geom,
                masked_path,
                aoi_mask,
                grid_transform,
                "EPSG:32614",
                minimum_area_m2=1,
            )
            self.assertEqual((masked_count, masked_area), (1, 15_988_000.0))
            _validate_geojson(
                masked_path,
                expected_count=masked_count,
                expected_area_m2=masked_area,
                minimum_component_area_m2=1,
                aoi_bbox=bbox,
            )

            tampered = json.loads(masked_path.read_text(encoding="utf-8"))
            ring = tampered["features"][0]["geometry"]["coordinates"][0]
            outside = [bbox[0] - 0.001, ring[0][1]]
            ring[0] = outside
            ring[-1] = outside
            masked_path.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SatelliteChangeBatchError,
                "outside the queue AOI",
            ):
                _validate_geojson(
                    masked_path,
                    expected_count=masked_count,
                    expected_area_m2=masked_area,
                    minimum_component_area_m2=1,
                    aoi_bbox=bbox,
                )

    def test_queue_style_negative_bbox_is_accepted_by_cli_parser(self) -> None:
        arguments = [
            "--baseline-stac",
            "before.json",
            "--baseline-id",
            "before",
            "--current-stac",
            "after.json",
            "--current-id",
            "after",
            "--bbox",
            "-90.1,34.9,-90.0,35.1",
            "--entity-id",
            "entity",
            "--entity-name",
            "Example",
            "--output-dir",
            "output",
        ]
        normalized = _normalize_bbox_argument(arguments)
        self.assertIn("--bbox=-90.1,34.9,-90.0,35.1", normalized)
        self.assertEqual(
            build_parser().parse_args(normalized).bbox,
            (-90.1, 34.9, -90.0, 35.1),
        )

    def test_parse_bbox(self) -> None:
        self.assertEqual(parse_bbox("-90.1,34.9,-90.0,35.1"), (-90.1, 34.9, -90.0, 35.1))
        with self.assertRaisesRegex(ValueError, "ordered WGS84"):
            parse_bbox("10,20,9,21")

    def test_select_feature_and_summary_are_deterministic(self) -> None:
        item = _item("scene-a", "2024-06-01T00:00:00Z")
        selected = select_feature({"type": "FeatureCollection", "features": [item]}, "scene-a")
        summary = item_summary(selected)
        self.assertEqual(summary["mgrs_tile"], "15SYU")
        self.assertEqual(summary["assets"]["red"]["scale"], 0.0001)
        self.assertEqual(summary["assets"]["scl"]["scale"], 1.0)
        self.assertEqual(summary["stac_item_sha256"], canonical_sha256(item))

    def test_select_feature_rejects_missing_item(self) -> None:
        with self.assertRaisesRegex(ValueError, "not found"):
            select_feature({"type": "FeatureCollection", "features": []}, "missing")

    def test_comparability_requires_time_order_and_same_tile(self) -> None:
        early = _item("early", "2024-06-01T00:00:00Z")
        late = _item("late", "2026-06-01T00:00:00Z")
        ensure_comparable(early, late)
        with self.assertRaisesRegex(ValueError, "must precede"):
            ensure_comparable(late, early)
        with self.assertRaisesRegex(ValueError, "MGRS tiles differ"):
            ensure_comparable(early, _item("other", "2026-06-01T00:00:00Z", "16SBD"))

    def test_invalid_scale_is_rejected(self) -> None:
        item = _item("bad", "2024-06-01T00:00:00Z")
        item["assets"]["red"]["raster:bands"][0]["scale"] = 0
        with self.assertRaisesRegex(ValueError, "invalid raster"):
            asset_scale_offset(item, "red")


if __name__ == "__main__":
    unittest.main()
