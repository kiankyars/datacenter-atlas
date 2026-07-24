from __future__ import annotations

import contextlib
import hashlib
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

from datacenter_atlas.satellite_change import (
    CLEAR_SCL_CLASSES,
    EARTH_SEARCH_ASSET_HOST,
    EARTH_SEARCH_ASSET_PATH_PREFIX,
    canonical_sha256,
)
from datacenter_atlas.satellite_change_mosaic import (
    ALGORITHM_VERSION,
    ArrayTile,
    ItemBinding,
    SentinelMosaicContractError,
    epoch_metadata_coverage,
    grid_from_item,
    mosaic_nonzero_tiles,
    parse_item_binding,
    parse_rfc3339_instant,
    parse_sha256,
    preflight_archived_epoch,
    require_complete_spatial_coverage,
    select_bound_items,
    validate_epoch_grid_contract,
)
from scripts.sentinel_change import (
    _rasterize_exact_aoi_center_mask as v2_exact_aoi_center_mask,
)
from scripts.sentinel_change_mosaic import (
    GEOJSON_COLLECTION_PROPERTIES,
    REPORT_CLASSIFICATION,
    _asset_resampling_policy,
    _native_request_window,
    _read_bound_json,
    _rasterize_exact_aoi_center_mask as mosaic_exact_aoi_center_mask,
    _read_asset_mosaic,
    _require_distinct_epochs,
    _require_equal_epoch_primary_grids,
    _reproject_mosaic,
    main as mosaic_main,
)


def _asset(
    item_id: str,
    name: str,
    *,
    origin_x: int,
    origin_y: int,
    resolution: int,
    width: int,
    height: int,
) -> dict[str, object]:
    asset: dict[str, object] = {
        "href": (
            f"https://{EARTH_SEARCH_ASSET_HOST}{EARTH_SEARCH_ASSET_PATH_PREFIX}"
            f"31/T/AA/2024/1/{item_id}/{name}.tif"
        ),
        "proj:shape": [height, width],
        "proj:transform": [
            resolution,
            0,
            origin_x,
            0,
            -resolution,
            origin_y,
        ],
        "raster:bands": [{"nodata": 0}],
    }
    if name != "scl":
        asset["raster:bands"] = [
            {"nodata": 0, "scale": 0.0001, "offset": -0.1}
        ]
    return asset


def _item(
    item_id: str,
    tile: str,
    *,
    origin_x: int,
    origin_y: int = 200,
    when: str = "2024-06-01T10:00:00Z",
    datatake: str = "DATATAKE-1",
    datastrip: str = "DATASTRIP-1",
    epsg: int = 32631,
) -> dict[str, object]:
    assets = {
        name: _asset(
            item_id,
            name,
            origin_x=origin_x,
            origin_y=origin_y,
            resolution=10,
            width=10,
            height=10,
        )
        for name in ("red", "green", "blue", "nir")
    }
    for name in ("swir16", "scl"):
        assets[name] = _asset(
            item_id,
            name,
            origin_x=origin_x,
            origin_y=origin_y,
            resolution=20,
            width=5,
            height=5,
        )
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "properties": {
            "datetime": when,
            "platform": "sentinel-2b",
            "constellation": "sentinel-2",
            "instruments": ["msi"],
            "s2:product_type": "S2MSI2A",
            "s2:processing_baseline": "05.10",
            "s2:datatake_id": datatake,
            "s2:datatake_type": "INS-NOBS",
            "s2:datastrip_id": datastrip,
            "s2:sequence": "0",
            "s2:generation_time": "2024-06-01T12:00:00.000000Z",
            "s2:product_uri": (
                "S2B_MSIL2A_20240601T100000_N0510_R001_"
                f"T{tile}_20240601T120000.SAFE"
            ),
            "processing:software": {"sentinel2-to-stac": "fixture"},
            "proj:epsg": epsg,
            "mgrs:utm_zone": int(tile[:2]),
            "mgrs:latitude_band": tile[2],
            "mgrs:grid_square": tile[3:],
        },
        "assets": assets,
    }


def _binding(item: dict[str, object]) -> ItemBinding:
    return ItemBinding(str(item["id"]), canonical_sha256(item))


def _document(*items: dict[str, object]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": list(items)}


def _scaled_transform_bounds(
    _source: str, _destination: str, left: float, bottom: float, right: float, top: float
) -> tuple[float, float, float, float]:
    return left * 10, bottom * 10, right * 10, top * 10


class SentinelMosaicBindingTests(unittest.TestCase):
    def test_algorithm_identifier_is_distinct_from_v2(self) -> None:
        self.assertEqual(ALGORITHM_VERSION, "sentinel-2-l2a-change-mosaic-v3")

    def test_proposals_preserve_all_non_claim_semantics(self) -> None:
        claim_fields = {
            "identity_claim",
            "lifecycle_claim",
            "operating_status_claim",
            "power_claim",
            "energy_claim",
            "operator_claim",
            "data_centre_type_claim",
            "it_capacity_claim",
            "pue_claim",
            "workload_claim",
        }
        for contract in (REPORT_CLASSIFICATION, GEOJSON_COLLECTION_PROPERTIES):
            with self.subTest(contract=contract.get("schema_version", "report")):
                self.assertTrue(claim_fields.issubset(contract))
                self.assertTrue(all(contract[field] is False for field in claim_fields))
                self.assertIs(contract["review_required"], True)

    def test_binding_parser_requires_exact_lowercase_hash(self) -> None:
        digest = "a" * 64
        self.assertEqual(
            parse_item_binding(f"scene={digest}"), ItemBinding("scene", digest)
        )
        for value in ("scene", "scene=ABC", f" scene={digest}", f"scene={digest}=x"):
            with self.subTest(value=value):
                with self.assertRaises(SentinelMosaicContractError):
                    parse_item_binding(value)

    def test_response_hash_parser_rejects_noncanonical_digests(self) -> None:
        digest = "b" * 64
        self.assertEqual(parse_sha256(digest), digest)
        for value in ("B" * 64, "b" * 63, f" {digest}", f"{digest} "):
            with self.subTest(value=value):
                with self.assertRaises(SentinelMosaicContractError):
                    parse_sha256(value)

    def test_companion_must_match_both_datatake_and_datastrip(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        wrong_datatake = _item(
            "wrong-datatake", "31TAB", origin_x=80, datatake="DATATAKE-2"
        )
        wrong_datastrip = _item(
            "wrong-datastrip", "31TAC", origin_x=160, datastrip="DATASTRIP-2"
        )
        document = _document(primary, wrong_datatake, wrong_datastrip)
        for companion in (wrong_datatake, wrong_datastrip):
            with self.subTest(companion=companion["id"]):
                with self.assertRaisesRegex(
                    SentinelMosaicContractError, "datatake or datastrip"
                ):
                    select_bound_items(document, _binding(primary), [_binding(companion)])

    def test_companion_must_satisfy_normalized_sensing_time_bound(self) -> None:
        primary = _item(
            "primary", "31TAA", origin_x=0, when="2024-06-01T10:00:00Z"
        )
        one_minute_later = _item(
            "later", "31TAB", origin_x=80, when="2024-06-01T10:01:00Z"
        )
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "normalized sensing-time delta"
        ):
            select_bound_items(
                _document(primary, one_minute_later),
                _binding(primary),
                [_binding(one_minute_later)],
            )

        equivalent_offset = _item(
            "equivalent",
            "31TAC",
            origin_x=80,
            when="2024-06-01T12:00:00+02:00",
        )
        _, selected = select_bound_items(
            _document(primary, equivalent_offset),
            _binding(primary),
            [_binding(equivalent_offset)],
        )
        self.assertEqual(len(selected), 2)

        at_limit = _item(
            "at-limit", "31TAD", origin_x=80, when="2024-06-01T10:00:30Z"
        )
        _, selected = select_bound_items(
            _document(primary, at_limit),
            _binding(primary),
            [_binding(at_limit)],
        )
        self.assertEqual(len(selected), 2)

        over_limit = _item(
            "over-limit",
            "31TAE",
            origin_x=80,
            when="2024-06-01T10:00:30.001Z",
        )
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "normalized sensing-time delta"
        ):
            select_bound_items(
                _document(primary, over_limit),
                _binding(primary),
                [_binding(over_limit)],
            )

    def test_epoch_order_uses_normalized_instants_not_timestamp_text(self) -> None:
        baseline = _item(
            "baseline",
            "31TAA",
            origin_x=0,
            when="2024-06-01T10:00:00-05:00",
        )
        current = _item(
            "current",
            "31TAA",
            origin_x=0,
            when="2024-06-01T14:30:00Z",
        )
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "must precede"
        ):
            _require_distinct_epochs(baseline, current)
        self.assertGreater(
            parse_rfc3339_instant(baseline["properties"]["datetime"]),
            parse_rfc3339_instant(current["properties"]["datetime"]),
        )

    def test_duplicate_bindings_and_duplicate_mgrs_tiles_are_rejected(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        duplicate_tile = _item("duplicate-tile", "31TAA", origin_x=80)
        document = _document(primary, duplicate_tile)
        with self.assertRaisesRegex(SentinelMosaicContractError, "duplicate ID"):
            select_bound_items(document, _binding(primary), [_binding(primary)])
        with self.assertRaisesRegex(SentinelMosaicContractError, "duplicate MGRS"):
            select_bound_items(
                document, _binding(primary), [_binding(duplicate_tile)]
            )

    def test_product_uri_may_differ_only_on_mgrs_tile_token(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        companion = _item("companion", "31TAB", origin_x=80)
        _, selected = select_bound_items(
            _document(primary, companion),
            _binding(primary),
            [_binding(companion)],
        )
        self.assertEqual(len(selected), 2)

        wrong_orbit = _item("wrong-orbit", "31TAC", origin_x=80)
        wrong_orbit["properties"]["s2:product_uri"] = wrong_orbit["properties"][
            "s2:product_uri"
        ].replace("_R001_", "_R002_")
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "parsed product identity"
        ):
            select_bound_items(
                _document(primary, wrong_orbit),
                _binding(primary),
                [_binding(wrong_orbit)],
            )

        malformed = _item("malformed", "31TAD", origin_x=0)
        malformed["properties"]["s2:product_uri"] = "not-a-product-uri"
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "noncanonical s2:product_uri"
        ):
            select_bound_items(_document(malformed), _binding(malformed), [])

    def test_unlisted_companion_is_never_selected_implicitly(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        companion = _item("companion", "31TAB", origin_x=80)
        document = _document(primary, companion)
        selected_primary, selected = select_bound_items(
            document, _binding(primary), []
        )
        self.assertEqual(selected_primary["id"], "primary")
        self.assertEqual([item["id"] for item in selected], ["primary"])
        coverage = epoch_metadata_coverage(
            selected_primary,
            selected,
            (7.0, 13.0, 11.0, 17.0),
            _scaled_transform_bounds,
        )
        self.assertFalse(coverage["complete"])

        preflight = preflight_archived_epoch(
            document,
            _binding(primary),
            (7.0, 13.0, 11.0, 17.0),
            _scaled_transform_bounds,
        )
        self.assertTrue(preflight["metadata_solvable"])
        self.assertEqual(preflight["network_requests"], 0)
        self.assertEqual(
            [row["id"] for row in preflight["proposed_explicit_bindings"]],
            ["companion", "primary"],
        )

    def test_hash_mismatch_cannot_fall_back_to_another_response_item(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        alternate = _item("alternate", "31TAB", origin_x=80)
        with self.assertRaisesRegex(SentinelMosaicContractError, "hash mismatch"):
            select_bound_items(
                _document(primary, alternate),
                ItemBinding("primary", "0" * 64),
                [_binding(alternate)],
            )


class SentinelMosaicGridTests(unittest.TestCase):
    def test_horizontal_and_vertical_grid_boundaries_are_complete(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0, origin_y=200)
        horizontal = _item("horizontal", "31TAB", origin_x=80, origin_y=200)
        vertical = _item("vertical", "31TAC", origin_x=0, origin_y=120)
        for companion, bbox in (
            (horizontal, (7.0, 13.0, 11.0, 17.0)),
            (vertical, (3.0, 9.0, 7.0, 13.0)),
        ):
            with self.subTest(companion=companion["id"]):
                selected_primary, selected = select_bound_items(
                    _document(primary, companion),
                    _binding(primary),
                    [_binding(companion)],
                )
                coverage = epoch_metadata_coverage(
                    selected_primary,
                    selected,
                    bbox,
                    _scaled_transform_bounds,
                )
                self.assertTrue(coverage["complete"])
                self.assertTrue(
                    all(value["complete"] for value in coverage["assets"].values())
                )

    def test_exact_10m_and_20m_native_grids_are_supported(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        companion = _item("companion", "31TAB", origin_x=80)
        validated = validate_epoch_grid_contract((primary, companion))
        self.assertEqual(validated["epsg"], 32631)
        self.assertEqual(
            validated["native_resolutions_m"],
            {"reflectance_10m": 10.0, "swir_scl_20m": 20.0},
        )

    def test_cross_epoch_primary_grids_must_be_exactly_equal(self) -> None:
        baseline = _item(
            "baseline", "31TAA", origin_x=0, when="2024-06-01T10:00:00Z"
        )
        current = _item(
            "current", "31TAA", origin_x=0, when="2026-06-01T10:00:00Z"
        )
        validate_epoch_grid_contract((baseline,))
        validate_epoch_grid_contract((current,))
        _require_equal_epoch_primary_grids(baseline, current)

        shifted = _item(
            "shifted", "31TAA", origin_x=10, when="2026-06-01T10:00:00Z"
        )
        validate_epoch_grid_contract((shifted,))
        with self.assertRaisesRegex(
            SentinelMosaicContractError, "red grids must be exactly equal"
        ):
            _require_equal_epoch_primary_grids(baseline, shifted)

    def test_crs_and_grid_misalignment_are_rejected(self) -> None:
        primary = _item("primary", "31TAA", origin_x=0)
        wrong_crs = _item("wrong-crs", "31TAB", origin_x=80, epsg=32632)
        with self.assertRaisesRegex(SentinelMosaicContractError, "CRS"):
            validate_epoch_grid_contract((primary, wrong_crs))

        shifted = _item("shifted", "31TAB", origin_x=80)
        shifted["assets"]["swir16"]["proj:transform"][2] += 10
        shifted["assets"]["scl"]["proj:transform"][2] += 10
        with self.assertRaisesRegex(SentinelMosaicContractError, "partial native cell"):
            validate_epoch_grid_contract((primary, shifted))

        truncated = _item("truncated", "31TAB", origin_x=80)
        truncated["assets"]["swir16"]["proj:shape"][1] -= 1
        truncated["assets"]["scl"]["proj:shape"][1] -= 1
        with self.assertRaisesRegex(SentinelMosaicContractError, "physical bounds"):
            validate_epoch_grid_contract((primary, truncated))

    def test_scl_nearest_neighbor_preserves_clear_cloud_boundary(self) -> None:
        from affine import Affine
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject

        anchor_item = _item("primary", "31TAA", origin_x=0, origin_y=40)
        anchor = grid_from_item(anchor_item, "scl")
        target_grid = (
            (2, 4),
            Affine(10, 0, 0, 0, -10, 40),
            rasterio.crs.CRS.from_epsg(32631),
        )
        scl, valid = _reproject_mosaic(
            np,
            Affine,
            Resampling,
            reproject,
            np.array([[4, 9]], dtype=np.uint8),
            np.ones((1, 2), dtype=bool),
            request=type("Window", (), {"col_off": 0, "row_off": 0})(),
            anchor=anchor,
            target_grid=target_grid,
            resampling=Resampling.nearest,
        )
        np.testing.assert_array_equal(
            scl,
            np.array([[4, 4, 9, 9], [4, 4, 9, 9]], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            np.isin(scl, sorted(CLEAR_SCL_CLASSES)),
            np.array(
                [
                    [True, True, False, False],
                    [True, True, False, False],
                ]
            ),
        )
        self.assertTrue(valid.all())

    def test_only_swir_uses_bilinear_resampling_and_a_halo(self) -> None:
        from affine import Affine
        import rasterio
        from rasterio.enums import Resampling

        for asset_name in ("red", "green", "blue", "nir", "scl"):
            with self.subTest(asset=asset_name):
                self.assertEqual(
                    _asset_resampling_policy(asset_name, Resampling),
                    (Resampling.nearest, 0),
                )
        self.assertEqual(
            _asset_resampling_policy("swir16", Resampling),
            (Resampling.bilinear, 1),
        )

        primary = _item("primary", "31TAA", origin_x=0)
        companion = _item("companion", "31TAB", origin_x=80)
        coverage = epoch_metadata_coverage(
            primary,
            (primary, companion),
            (7.0, 13.0, 11.0, 17.0),
            _scaled_transform_bounds,
        )
        self.assertEqual(
            {
                name: value["interpolation_halo_pixels"]
                for name, value in coverage["assets"].items()
            },
            {
                "red": 0,
                "green": 0,
                "blue": 0,
                "nir": 0,
                "swir16": 1,
                "scl": 0,
            },
        )
        anchor = grid_from_item(primary, "swir16")
        target_grid = (
            (4, 4),
            Affine(10, 0, 20, 0, -10, 180),
            rasterio.crs.CRS.from_epsg(32631),
        )
        without_halo = _native_request_window(
            anchor, target_grid, interpolation_halo=0
        )
        with_halo = _native_request_window(
            anchor, target_grid, interpolation_halo=1
        )
        self.assertEqual(with_halo.col_off, without_halo.col_off - 1)
        self.assertEqual(with_halo.row_off, without_halo.row_off - 1)
        self.assertEqual(with_halo.width, without_halo.width + 2)
        self.assertEqual(with_halo.height, without_halo.height + 2)

    def test_mixed_resolution_reprojection_preserves_validity(self) -> None:
        from affine import Affine
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject

        anchor_item = _item("primary", "31TAA", origin_x=0, origin_y=40)
        anchor = grid_from_item(anchor_item, "swir16")
        values = np.array([[10, 20], [30, 40]], dtype=np.uint16)
        nonzero = np.ones((2, 2), dtype=bool)
        target_grid = (
            (4, 4),
            Affine(10, 0, 0, 0, -10, 40),
            rasterio.crs.CRS.from_epsg(32631),
        )
        aligned, valid = _reproject_mosaic(
            np,
            Affine,
            Resampling,
            reproject,
            values,
            nonzero,
            request=type("Window", (), {"col_off": 0, "row_off": 0})(),
            anchor=anchor,
            target_grid=target_grid,
            resampling=Resampling.bilinear,
        )
        self.assertEqual(aligned.shape, (4, 4))
        self.assertTrue(valid.all())
        self.assertGreater(int(aligned.max()), int(aligned.min()))

    def test_bounded_raster_reads_cross_a_horizontal_tile_boundary(self) -> None:
        from affine import Affine
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.io import MemoryFile
        from rasterio.warp import reproject
        from rasterio.windows import Window

        primary = _item("primary", "31TAA", origin_x=0, origin_y=200)
        companion = _item("companion", "31TAB", origin_x=80, origin_y=200)
        target_grid = (
            (4, 4),
            Affine(10, 0, 70, 0, -10, 170),
            rasterio.crs.CRS.from_epsg(32631),
        )
        with MemoryFile() as primary_memory, MemoryFile() as companion_memory:
            for memory, item, transform in (
                (primary_memory, primary, Affine(10, 0, 0, 0, -10, 200)),
                (companion_memory, companion, Affine(10, 0, 80, 0, -10, 200)),
            ):
                with memory.open(
                    driver="GTiff",
                    width=10,
                    height=10,
                    count=1,
                    dtype="uint16",
                    crs="EPSG:32631",
                    transform=transform,
                    nodata=0,
                ) as dataset:
                    dataset.write(np.full((10, 10), 100, dtype=np.uint16), 1)
                item["assets"]["red"]["href"] = memory.name
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Setting the shape on a NumPy array has been deprecated",
                    category=DeprecationWarning,
                )
                aligned, valid = _read_asset_mosaic(
                    np,
                    Affine,
                    rasterio,
                    Resampling,
                    reproject,
                    Window,
                    primary,
                    (companion, primary),
                    "red",
                    target_grid,
                )
        np.testing.assert_array_equal(
            aligned, np.full((4, 4), 100, dtype=np.uint16)
        )
        self.assertTrue(valid.all())

    def test_exact_aoi_center_mask_matches_algorithm_v2(self) -> None:
        from affine import Affine
        import numpy as np

        transform = Affine(0.1, 0, 0, 0, -0.1, 1)

        def identity(
            _source: object, _destination: object, xs: object, ys: object
        ) -> tuple[object, object]:
            return xs, ys

        arguments = (
            np,
            identity,
            (0.15, 0.15, 0.75, 0.85),
            transform,
            "EPSG:4326",
            (10, 10),
        )
        np.testing.assert_array_equal(
            mosaic_exact_aoi_center_mask(*arguments),
            v2_exact_aoi_center_mask(*arguments),
        )


class SentinelMosaicArrayTests(unittest.TestCase):
    def test_horizontal_boundary_mosaic(self) -> None:
        import numpy as np

        left = ArrayTile("left", 0, 0, np.array([[1, 2], [3, 4]], dtype=np.uint16))
        right = ArrayTile("right", 0, 2, np.array([[5, 6], [7, 8]], dtype=np.uint16))
        values, nonzero, spatial = mosaic_nonzero_tiles((right, left), (2, 4))
        np.testing.assert_array_equal(
            values, np.array([[1, 2, 5, 6], [3, 4, 7, 8]], dtype=np.uint16)
        )
        self.assertTrue(nonzero.all())
        self.assertTrue(spatial.all())

    def test_vertical_boundary_mosaic(self) -> None:
        import numpy as np

        top = ArrayTile("top", 0, 0, np.array([[1, 2]], dtype=np.uint16))
        bottom = ArrayTile("bottom", 1, 0, np.array([[3, 4]], dtype=np.uint16))
        values, _, spatial = mosaic_nonzero_tiles((top, bottom), (2, 2))
        np.testing.assert_array_equal(
            values, np.array([[1, 2], [3, 4]], dtype=np.uint16)
        )
        self.assertTrue(spatial.all())

    def test_nodata_overlap_is_not_a_conflict_or_valid_data(self) -> None:
        import numpy as np

        first = ArrayTile("a", 0, 0, np.array([[5, 0, 0]], dtype=np.uint16))
        second = ArrayTile("b", 0, 1, np.array([[0, 7, 8]], dtype=np.uint16))
        values, nonzero, spatial = mosaic_nonzero_tiles((first, second), (1, 4))
        np.testing.assert_array_equal(
            values, np.array([[5, 0, 7, 8]], dtype=np.uint16)
        )
        np.testing.assert_array_equal(
            nonzero, np.array([[True, False, True, True]])
        )
        self.assertTrue(spatial.all())

    def test_conflicting_nonzero_overlap_is_rejected(self) -> None:
        import numpy as np

        first = ArrayTile("a", 0, 0, np.array([[1, 2]], dtype=np.uint16))
        second = ArrayTile("b", 0, 1, np.array([[3, 4]], dtype=np.uint16))
        with self.assertRaisesRegex(SentinelMosaicContractError, "conflicting"):
            mosaic_nonzero_tiles((first, second), (1, 3))

    def test_incomplete_spatial_coverage_is_rejected_separately(self) -> None:
        import numpy as np

        tile = ArrayTile("a", 0, 0, np.array([[1, 2]], dtype=np.uint16))
        _, nonzero, spatial = mosaic_nonzero_tiles((tile,), (1, 4))
        self.assertFalse(spatial[0, 2:].any())
        self.assertFalse(nonzero[0, 2:].any())
        with self.assertRaisesRegex(SentinelMosaicContractError, "completely cover"):
            require_complete_spatial_coverage(spatial)

    def test_duplicate_ids_reject_and_input_order_is_otherwise_irrelevant(self) -> None:
        import numpy as np

        tiles = (
            ArrayTile("c", 0, 2, np.array([[3]], dtype=np.uint16)),
            ArrayTile("a", 0, 0, np.array([[1]], dtype=np.uint16)),
            ArrayTile("b", 0, 1, np.array([[2]], dtype=np.uint16)),
        )
        expected = None
        for permutation in itertools.permutations(tiles):
            values, nonzero, spatial = mosaic_nonzero_tiles(permutation, (1, 3))
            result = (values.tolist(), nonzero.tolist(), spatial.tolist())
            if expected is None:
                expected = result
            self.assertEqual(result, expected)
        duplicate = (
            tiles[0],
            ArrayTile("c", 0, 0, np.array([[3]], dtype=np.uint16)),
        )
        with self.assertRaisesRegex(SentinelMosaicContractError, "duplicate"):
            mosaic_nonzero_tiles(duplicate, (1, 3))


class SentinelMosaicFrozenResponseTests(unittest.TestCase):
    def test_repeated_local_cli_runs_have_identical_output_hashes(self) -> None:
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds

        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            baseline_item = _item(
                "baseline-scene",
                "31TAA",
                origin_x=500_000,
                origin_y=100,
                when="2024-06-01T10:00:00Z",
                datatake="BASELINE-DATATAKE",
                datastrip="BASELINE-DATASTRIP",
            )
            current_item = _item(
                "current-scene",
                "31TAA",
                origin_x=500_000,
                origin_y=100,
                when="2026-06-01T10:00:00Z",
                datatake="CURRENT-DATATAKE",
                datastrip="CURRENT-DATASTRIP",
            )

            for epoch, item in (
                ("baseline", baseline_item),
                ("current", current_item),
            ):
                for asset_name in ("red", "green", "blue", "nir", "swir16", "scl"):
                    asset = item["assets"][asset_name]
                    height, width = asset["proj:shape"]
                    transform = rasterio.Affine(*asset["proj:transform"])
                    dtype = "uint8" if asset_name == "scl" else "uint16"
                    if asset_name == "scl":
                        values = np.full((height, width), 4, dtype=np.uint8)
                    else:
                        values = np.full((height, width), 2_000, dtype=np.uint16)
                        if epoch == "current":
                            values[
                                height // 3 : height * 2 // 3,
                                width // 3 : width * 2 // 3,
                            ] = 5_000
                    raster_path = temporary_path / f"{epoch}-{asset_name}.tif"
                    with rasterio.open(
                        raster_path,
                        "w",
                        driver="GTiff",
                        width=width,
                        height=height,
                        count=1,
                        dtype=dtype,
                        crs="EPSG:32631",
                        transform=transform,
                        nodata=0,
                    ) as dataset:
                        dataset.write(values, 1)
                    asset["href"] = str(raster_path)

            baseline_response = temporary_path / "baseline-response.json"
            current_response = temporary_path / "current-response.json"
            baseline_raw = json.dumps(_document(baseline_item), sort_keys=True).encode(
                "utf-8"
            )
            current_raw = json.dumps(_document(current_item), sort_keys=True).encode(
                "utf-8"
            )
            baseline_response.write_bytes(baseline_raw)
            current_response.write_bytes(current_raw)
            projected_bbox = (500_030.0, 30.0, 500_070.0, 70.0)
            bbox = transform_bounds(
                "EPSG:32631", "EPSG:4326", *projected_bbox
            )

            common_arguments = [
                "--baseline-stac",
                str(baseline_response),
                "--baseline-stac-sha256",
                hashlib.sha256(baseline_raw).hexdigest(),
                "--baseline-primary",
                f"{baseline_item['id']}={canonical_sha256(baseline_item)}",
                "--current-stac",
                str(current_response),
                "--current-stac-sha256",
                hashlib.sha256(current_raw).hexdigest(),
                "--current-primary",
                f"{current_item['id']}={canonical_sha256(current_item)}",
                "--bbox",
                ",".join(str(value) for value in bbox),
                "--entity-id",
                "determinism-fixture",
                "--entity-name",
                "Determinism fixture",
                "--minimum-component-area-m2",
                "1",
            ]
            output_hashes: list[dict[str, str]] = []
            with mock.patch(
                "datacenter_atlas.satellite_change_mosaic.validate_item",
                return_value=None,
            ):
                for run_index in range(2):
                    output = temporary_path / f"output-{run_index}"
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            "ignore",
                            message=(
                                "Setting the shape on a NumPy array has been "
                                "deprecated"
                            ),
                            category=DeprecationWarning,
                        )
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(
                                mosaic_main(
                                    [
                                        *common_arguments,
                                        "--output-dir",
                                        str(output),
                                    ]
                                ),
                                0,
                            )
                    output_hashes.append(
                        {
                            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(output.iterdir())
                        }
                    )
            self.assertEqual(output_hashes[0], output_hashes[1])
            self.assertEqual(
                set(output_hashes[0]),
                {
                    "after.png",
                    "before.png",
                    "change-overlay.png",
                    "change-proposals.geojson",
                    "comparison.png",
                    "report.json",
                },
            )

    def test_cli_rejects_frozen_response_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            baseline = temporary_path / "baseline.json"
            current = temporary_path / "current.json"
            raw = json.dumps({"type": "FeatureCollection", "features": []}).encode(
                "utf-8"
            )
            baseline.write_bytes(raw)
            current.write_bytes(raw)
            with self.assertRaisesRegex(
                SentinelMosaicContractError, "hash mismatch"
            ):
                mosaic_main(
                    [
                        "--baseline-stac",
                        str(baseline),
                        "--baseline-stac-sha256",
                        "0" * 64,
                        "--baseline-primary",
                        f"baseline={'0' * 64}",
                        "--current-stac",
                        str(current),
                        "--current-stac-sha256",
                        hashlib.sha256(raw).hexdigest(),
                        "--current-primary",
                        f"current={'0' * 64}",
                        "--bbox",
                        "0,0,1,1",
                        "--entity-id",
                        "entity",
                        "--entity-name",
                        "Entity",
                        "--output-dir",
                        str(temporary_path / "output"),
                    ]
                )

    def test_hash_mismatch_is_rejected_before_stac_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            response = Path(temporary) / "response.json"
            response.write_text(
                json.dumps({"type": "FeatureCollection", "features": []}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SentinelMosaicContractError, "hash mismatch"
            ):
                _read_bound_json(response, "0" * 64)

    def test_hash_and_json_parse_use_the_same_immutable_byte_buffer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            response = Path(temporary) / "response.json"
            original = json.dumps({"marker": "original"}).encode("utf-8")
            replacement = json.dumps({"marker": "replacement"}).encode("utf-8")
            response.write_bytes(original)
            expected = hashlib.sha256(original).hexdigest()

            class MutatingDigest:
                def hexdigest(self) -> str:
                    response.write_bytes(replacement)
                    return expected

            with mock.patch(
                "scripts.sentinel_change_mosaic.sha256",
                return_value=MutatingDigest(),
            ):
                parsed = _read_bound_json(response, expected)
            self.assertEqual(parsed, {"marker": "original"})
            self.assertEqual(json.loads(response.read_bytes()), {"marker": "replacement"})

    def test_symlinked_stac_response_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            link = Path(temporary) / "link.json"
            raw = json.dumps({"type": "FeatureCollection", "features": []}).encode(
                "utf-8"
            )
            source.write_bytes(raw)
            link.symlink_to(source)
            with self.assertRaisesRegex(
                SentinelMosaicContractError, "non-symlink"
            ):
                _read_bound_json(link, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
