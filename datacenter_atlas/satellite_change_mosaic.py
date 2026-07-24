"""Fail-closed contracts for deterministic multi-tile Sentinel-2 change inputs.

This module deliberately does not query a STAC API.  Production processing may
use only item IDs and canonical item hashes explicitly supplied by its caller.
The discovery helper is for read-only preflight of an already archived response;
its output is a proposed binding, never an implicit scene selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from .satellite_change import (
    ALGORITHM_VERSION as SPECTRAL_CORE_ALGORITHM_VERSION,
    REQUIRED_ASSETS,
    canonical_sha256,
    mgrs_tile,
    validate_item,
)


ALGORITHM_VERSION = "sentinel-2-l2a-change-mosaic-v3"
REPORT_SCHEMA_VERSION = "1.2"
MAX_PREFLIGHT_WINDOW_CELLS = 5_000_000
# Conservative implementation ceiling, not an official mission limit.  Frozen
# adjacent-granule observations span 3.417--14.723 seconds.
MAX_COMPANION_TIME_DELTA_SECONDS = 30.0
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
_PRODUCT_URI_PATTERN = re.compile(
    r"(?P<satellite>S2[ABC])_MSIL2A_"
    r"(?P<sensing>\d{8}T\d{6})_N(?P<baseline>\d{4})_"
    r"R(?P<orbit>\d{3})_T(?P<tile>\d{2}[A-Z]{3})_"
    r"(?P<generation>\d{8}T\d{6})\.SAFE"
)


class SentinelMosaicContractError(ValueError):
    """Raised when an explicit multi-tile input fails closed."""


@dataclass(frozen=True, order=True)
class ItemBinding:
    """An exact caller-supplied STAC identity binding."""

    item_id: str
    stac_item_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise SentinelMosaicContractError("item binding ID is required")
        if self.item_id != self.item_id.strip() or any(
            character.isspace() for character in self.item_id
        ):
            raise SentinelMosaicContractError("item binding ID is not canonical")
        if not isinstance(self.stac_item_sha256, str) or not _HASH_PATTERN.fullmatch(
            self.stac_item_sha256
        ):
            raise SentinelMosaicContractError(
                "item binding hash must be a lowercase canonical SHA-256"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.item_id,
            "stac_item_sha256": self.stac_item_sha256,
        }


@dataclass(frozen=True)
class GridSpec:
    """An explicit north-up raster grid from STAC projection metadata."""

    epsg: int
    width: int
    height: int
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @property
    def resolution(self) -> float:
        return self.a

    @property
    def transform_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.a, self.b, self.c, self.d, self.e, self.f)


@dataclass(frozen=True)
class GridWindow:
    """An integer window on a grid's infinite pixel lattice."""

    col_off: int
    row_off: int
    width: int
    height: int

    def __post_init__(self) -> None:
        for label, value in (
            ("column offset", self.col_off),
            ("row offset", self.row_off),
            ("width", self.width),
            ("height", self.height),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise SentinelMosaicContractError(f"grid window {label} must be integer")
        if self.width <= 0 or self.height <= 0:
            raise SentinelMosaicContractError("grid window must have positive dimensions")

    @property
    def left(self) -> int:
        return self.col_off

    @property
    def top(self) -> int:
        return self.row_off

    @property
    def right(self) -> int:
        return self.col_off + self.width

    @property
    def bottom(self) -> int:
        return self.row_off + self.height

    def padded(self, pixels: int) -> GridWindow:
        if isinstance(pixels, bool) or not isinstance(pixels, int) or pixels < 0:
            raise SentinelMosaicContractError("grid padding must be a non-negative integer")
        return GridWindow(
            self.col_off - pixels,
            self.row_off - pixels,
            self.width + pixels * 2,
            self.height + pixels * 2,
        )


@dataclass(frozen=True)
class ArrayTile:
    """One bounded native array positioned on an output mosaic lattice."""

    item_id: str
    row_offset: int
    column_offset: int
    values: Any


def parse_sha256(value: str) -> str:
    """Require one lowercase canonical SHA-256 digest."""

    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise SentinelMosaicContractError(
            "hash must be a lowercase canonical SHA-256"
        )
    return value


def parse_rfc3339_instant(value: Any, label: str = "datetime") -> datetime:
    """Parse one timezone-aware RFC 3339 timestamp and normalize it to UTC."""

    if not isinstance(value, str) or not _RFC3339_PATTERN.fullmatch(value):
        raise SentinelMosaicContractError(
            f"{label} must be a timezone-aware RFC 3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise SentinelMosaicContractError(
            f"{label} must be a valid timezone-aware RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SentinelMosaicContractError(
            f"{label} must include a timezone offset"
        )
    return parsed.astimezone(timezone.utc)


def parse_item_binding(value: str) -> ItemBinding:
    """Parse an exact ``ITEM_ID=LOWERCASE_SHA256`` CLI binding."""

    if not isinstance(value, str):
        raise SentinelMosaicContractError("item binding must be text")
    item_id, separator, digest = value.partition("=")
    if separator != "=" or "=" in digest:
        raise SentinelMosaicContractError(
            "item binding must use ITEM_ID=LOWERCASE_SHA256"
        )
    return ItemBinding(item_id=item_id, stac_item_sha256=digest)


def _features(document: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(document, Mapping):
        raise SentinelMosaicContractError("STAC document must be an object")
    if document.get("type") == "Feature":
        values: Sequence[Any] = (document,)
    elif document.get("type") == "FeatureCollection":
        values = document.get("features")
        if not isinstance(values, list):
            raise SentinelMosaicContractError(
                "STAC FeatureCollection.features must be an array"
            )
    else:
        raise SentinelMosaicContractError(
            "expected a STAC Feature or FeatureCollection"
        )
    if any(not isinstance(feature, Mapping) for feature in values):
        raise SentinelMosaicContractError("STAC features must be objects")
    return tuple(values)


def _select_exact_feature(
    features: Sequence[Mapping[str, Any]], binding: ItemBinding
) -> Mapping[str, Any]:
    matches = [feature for feature in features if feature.get("id") == binding.item_id]
    if not matches:
        raise SentinelMosaicContractError(
            f"explicitly bound STAC item is absent: {binding.item_id}"
        )
    if len(matches) != 1:
        raise SentinelMosaicContractError(
            f"explicitly bound STAC item is not unique: {binding.item_id}"
        )
    feature = matches[0]
    try:
        validate_item(feature)
    except ValueError as error:
        raise SentinelMosaicContractError(
            f"explicitly bound STAC item is invalid: {binding.item_id}"
        ) from error
    actual = canonical_sha256(feature)
    if actual != binding.stac_item_sha256:
        raise SentinelMosaicContractError(
            f"canonical STAC item hash mismatch: {binding.item_id}"
        )
    return feature


def _acquisition_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise SentinelMosaicContractError("STAC item properties are required")
    values: list[str] = []
    for field in ("s2:datatake_id", "s2:datastrip_id"):
        value = properties.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise SentinelMosaicContractError(
                f"STAC item {item.get('id')} lacks canonical {field}"
            )
        values.append(value)
    return values[0], values[1]


def _item_instant(item: Mapping[str, Any]) -> datetime:
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise SentinelMosaicContractError("STAC item properties are required")
    return parse_rfc3339_instant(
        properties.get("datetime"), f"STAC item {item.get('id')} datetime"
    )


def _same_product_contract(
    primary: Mapping[str, Any], companion: Mapping[str, Any]
) -> None:
    primary_properties = primary["properties"]
    companion_properties = companion["properties"]
    for field in (
        "platform",
        "constellation",
        "instruments",
        "s2:product_type",
        "s2:processing_baseline",
        "s2:datatake_id",
        "s2:datatake_type",
        "s2:datastrip_id",
        "s2:sequence",
        "s2:generation_time",
        "processing:software",
    ):
        primary_value = primary_properties.get(field)
        companion_value = companion_properties.get(field)
        if primary_value is None or companion_value is None:
            raise SentinelMosaicContractError(
                f"same-product field {field} is required on both items"
            )
        if primary_value != companion_value:
            raise SentinelMosaicContractError(
                f"companion {companion['id']} differs on {field}"
            )
    if primary.get("collection") != companion.get("collection"):
        raise SentinelMosaicContractError(
            f"companion {companion['id']} differs on collection"
        )
    if _product_uri_identity(primary) != _product_uri_identity(companion):
        raise SentinelMosaicContractError(
            f"companion {companion['id']} differs on parsed product identity"
        )


def _product_uri_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise SentinelMosaicContractError("STAC item properties are required")
    value = properties.get("s2:product_uri")
    if not isinstance(value, str):
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} requires s2:product_uri"
        )
    match = _PRODUCT_URI_PATTERN.fullmatch(value)
    if match is None:
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} has noncanonical s2:product_uri"
        )
    tile = mgrs_tile(item)
    if tile != match.group("tile"):
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} product URI tile differs from MGRS metadata"
        )
    platform = properties.get("platform")
    if platform != f"sentinel-{match.group('satellite')[-2:].lower()}":
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} product URI satellite differs from platform"
        )
    processing_baseline = properties.get("s2:processing_baseline")
    if not isinstance(processing_baseline, str) or processing_baseline.replace(
        ".", ""
    ) != match.group("baseline"):
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} product URI baseline differs from metadata"
        )
    return (
        match.group("satellite"),
        match.group("sensing"),
        match.group("baseline"),
        match.group("orbit"),
        match.group("generation"),
    )


def _companion_time_delta_seconds(
    primary: Mapping[str, Any], companion: Mapping[str, Any]
) -> float:
    return abs((_item_instant(companion) - _item_instant(primary)).total_seconds())


def select_bound_items(
    document: Mapping[str, Any],
    primary: ItemBinding,
    companions: Sequence[ItemBinding],
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """Select only explicitly bound same-acquisition items from an archive.

    Unlisted response features are ignored even when they could fill a coverage
    gap.  This is the production selection boundary that prevents implicit scene
    substitution.
    """

    if isinstance(companions, (str, bytes)) or not isinstance(companions, Sequence):
        raise SentinelMosaicContractError("companion bindings must be a sequence")
    bindings = (primary, *companions)
    ids = [binding.item_id for binding in bindings]
    if len(ids) != len(set(ids)):
        raise SentinelMosaicContractError("item bindings contain a duplicate ID")
    features = _features(document)
    primary_item = _select_exact_feature(features, primary)
    acquisition = _acquisition_identity(primary_item)
    _item_instant(primary_item)
    _product_uri_identity(primary_item)
    selected: list[Mapping[str, Any]] = [primary_item]
    seen_tiles: set[str] = set()
    primary_tile = mgrs_tile(primary_item)
    if not primary_tile:
        raise SentinelMosaicContractError(
            f"primary item {primary.item_id} lacks an explicit MGRS tile"
        )
    seen_tiles.add(primary_tile)
    for binding in sorted(companions):
        item = _select_exact_feature(features, binding)
        if _acquisition_identity(item) != acquisition:
            raise SentinelMosaicContractError(
                f"companion {binding.item_id} differs on datatake or datastrip"
            )
        if _companion_time_delta_seconds(
            primary_item, item
        ) > MAX_COMPANION_TIME_DELTA_SECONDS:
            raise SentinelMosaicContractError(
                f"companion {binding.item_id} exceeds the normalized sensing-time delta"
            )
        _same_product_contract(primary_item, item)
        tile = mgrs_tile(item)
        if not tile:
            raise SentinelMosaicContractError(
                f"companion {binding.item_id} lacks an explicit MGRS tile"
            )
        if tile in seen_tiles:
            raise SentinelMosaicContractError(
                f"selected items duplicate MGRS tile {tile}"
            )
        seen_tiles.add(tile)
        selected.append(item)
    return primary_item, tuple(sorted(selected, key=lambda item: str(item["id"])))


def discover_same_acquisition_bindings(
    document: Mapping[str, Any], primary: ItemBinding
) -> tuple[ItemBinding, ...]:
    """Propose exact bindings from one already archived response for preflight.

    The caller must explicitly pass any returned companions to
    :func:`select_bound_items` for production use.
    """

    features = _features(document)
    primary_item = _select_exact_feature(features, primary)
    acquisition = _acquisition_identity(primary_item)
    _item_instant(primary_item)
    _product_uri_identity(primary_item)
    candidates: list[ItemBinding] = []
    seen_ids: set[str] = set()
    for feature in features:
        if _acquisition_identity(feature) != acquisition:
            continue
        if _companion_time_delta_seconds(
            primary_item, feature
        ) > MAX_COMPANION_TIME_DELTA_SECONDS:
            continue
        item_id = feature.get("id")
        if not isinstance(item_id, str) or item_id in seen_ids:
            raise SentinelMosaicContractError(
                "same-acquisition response items must have unique IDs"
            )
        try:
            validate_item(feature)
        except ValueError as error:
            raise SentinelMosaicContractError(
                f"same-acquisition STAC item is invalid: {item_id}"
            ) from error
        _same_product_contract(primary_item, feature)
        seen_ids.add(item_id)
        candidates.append(ItemBinding(item_id, canonical_sha256(feature)))
    return tuple(sorted(candidates))


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SentinelMosaicContractError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SentinelMosaicContractError(f"{label} must be finite")
    return result


def grid_from_item(item: Mapping[str, Any], asset_name: str) -> GridSpec:
    """Read an asset grid only from explicit STAC projection metadata."""

    if asset_name not in REQUIRED_ASSETS:
        raise SentinelMosaicContractError(f"unsupported asset grid: {asset_name}")
    properties = item.get("properties")
    assets = item.get("assets")
    if not isinstance(properties, Mapping) or not isinstance(assets, Mapping):
        raise SentinelMosaicContractError("STAC item projection metadata is missing")
    asset = assets.get(asset_name)
    if not isinstance(asset, Mapping):
        raise SentinelMosaicContractError(
            f"STAC item {item.get('id')} lacks asset {asset_name}"
        )
    item_epsg = properties.get("proj:epsg")
    asset_epsg = asset.get("proj:epsg")
    if asset_epsg is not None and item_epsg is not None and asset_epsg != item_epsg:
        raise SentinelMosaicContractError(
            f"asset {asset_name} EPSG conflicts with item metadata"
        )
    epsg = asset_epsg if asset_epsg is not None else item_epsg
    if isinstance(epsg, bool) or not isinstance(epsg, int) or epsg <= 0:
        raise SentinelMosaicContractError(
            f"asset {asset_name} requires an explicit positive proj:epsg"
        )
    shape = asset.get("proj:shape")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in shape
        )
    ):
        raise SentinelMosaicContractError(
            f"asset {asset_name} requires positive proj:shape [height,width]"
        )
    transform = asset.get("proj:transform")
    if not isinstance(transform, list) or len(transform) != 6:
        raise SentinelMosaicContractError(
            f"asset {asset_name} requires a six-value proj:transform"
        )
    a, b, c, d, e, f = (
        _finite_number(value, f"asset {asset_name} transform") for value in transform
    )
    tolerance = max(abs(a), abs(e), 1.0) * 1e-12
    if a <= 0 or e >= 0 or abs(a + e) > tolerance or abs(b) > tolerance or abs(d) > tolerance:
        raise SentinelMosaicContractError(
            f"asset {asset_name} grid must be north-up with square positive pixels"
        )
    return GridSpec(
        epsg=epsg,
        width=shape[1],
        height=shape[0],
        a=a,
        b=b,
        c=c,
        d=d,
        e=e,
        f=f,
    )


def _integer_offset(value: float, label: str) -> int:
    nearest = round(value)
    if not math.isclose(value, nearest, rel_tol=0.0, abs_tol=1e-8):
        raise SentinelMosaicContractError(f"{label} is not on the shared pixel lattice")
    return int(nearest)


def grid_offset(child: GridSpec, anchor: GridSpec) -> tuple[int, int]:
    """Return a same-resolution child grid offset on the anchor lattice."""

    if child.epsg != anchor.epsg:
        raise SentinelMosaicContractError("asset grids use different CRS values")
    if not math.isclose(child.resolution, anchor.resolution, rel_tol=0.0, abs_tol=1e-10):
        raise SentinelMosaicContractError("asset grids use different native resolutions")
    for label, left, right in (
        ("x rotation", child.b, anchor.b),
        ("y rotation", child.d, anchor.d),
        ("y resolution", child.e, anchor.e),
    ):
        if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-10):
            raise SentinelMosaicContractError(f"asset grids differ on {label}")
    return (
        _integer_offset((child.c - anchor.c) / anchor.resolution, "column origin"),
        _integer_offset((anchor.f - child.f) / anchor.resolution, "row origin"),
    )


def _require_mixed_resolution_alignment(child: GridSpec, red: GridSpec) -> int:
    if child.epsg != red.epsg:
        raise SentinelMosaicContractError("mixed-resolution assets use different CRS values")
    ratio = child.resolution / red.resolution
    integer_ratio = _integer_offset(ratio, "native resolution ratio")
    if integer_ratio <= 0:
        raise SentinelMosaicContractError("native resolution ratio must be positive")
    column_offset = _integer_offset(
        (child.c - red.c) / red.resolution, "mixed-grid column origin"
    )
    row_offset = _integer_offset(
        (red.f - child.f) / red.resolution, "mixed-grid row origin"
    )
    if column_offset % integer_ratio or row_offset % integer_ratio:
        raise SentinelMosaicContractError(
            "mixed-resolution origin is shifted by a partial native cell"
        )
    red_bounds = (
        red.c,
        red.f + red.e * red.height,
        red.c + red.a * red.width,
        red.f,
    )
    child_bounds = (
        child.c,
        child.f + child.e * child.height,
        child.c + child.a * child.width,
        child.f,
    )
    if child_bounds != red_bounds:
        raise SentinelMosaicContractError(
            "10 m and 20 m grids must have exactly equal physical bounds"
        )
    return integer_ratio


def validate_epoch_grid_contract(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Require exact per-band and cross-tile Sentinel grid invariants."""

    if not items:
        raise SentinelMosaicContractError("an epoch must contain at least one item")
    ordered = tuple(sorted(items, key=lambda item: str(item.get("id"))))
    primary_red = grid_from_item(ordered[0], "red")
    primary_twenty = grid_from_item(ordered[0], "swir16")
    if not math.isclose(primary_red.resolution, 10.0, rel_tol=0.0, abs_tol=1e-10):
        raise SentinelMosaicContractError("Sentinel reflectance grid must be exactly 10 m")
    if not math.isclose(primary_twenty.resolution, 20.0, rel_tol=0.0, abs_tol=1e-10):
        raise SentinelMosaicContractError("Sentinel SWIR/SCL grid must be exactly 20 m")
    for item in ordered:
        red = grid_from_item(item, "red")
        grid_offset(red, primary_red)
        for asset_name in ("green", "blue", "nir"):
            asset_grid = grid_from_item(item, asset_name)
            if asset_grid != red:
                raise SentinelMosaicContractError(
                    f"item {item.get('id')} asset {asset_name} differs from red grid"
                )
        swir = grid_from_item(item, "swir16")
        scl = grid_from_item(item, "scl")
        if scl != swir:
            raise SentinelMosaicContractError(
                f"item {item.get('id')} SCL and SWIR grids differ"
            )
        ratio = _require_mixed_resolution_alignment(swir, red)
        if ratio != 2:
            raise SentinelMosaicContractError(
                f"item {item.get('id')} expected exact 20 m to 10 m ratio"
            )
        grid_offset(swir, primary_twenty)
    return {
        "epsg": primary_red.epsg,
        "item_count": len(ordered),
        "native_resolutions_m": {"reflectance_10m": 10.0, "swir_scl_20m": 20.0},
        "red_grid": primary_red,
        "swir_scl_grid": primary_twenty,
    }


def window_from_wgs84_bbox(
    grid: GridSpec,
    bbox: Sequence[float],
    transform_bounds: Callable[..., Sequence[float]],
) -> GridWindow:
    """Return the smallest native window covering a projected WGS84 bbox."""

    if len(bbox) != 4:
        raise SentinelMosaicContractError("bbox must contain four values")
    west, south, east, north = (
        _finite_number(value, "bbox coordinate") for value in bbox
    )
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise SentinelMosaicContractError("bbox must be ordered WGS84 coordinates")
    try:
        projected = transform_bounds(
            "EPSG:4326", f"EPSG:{grid.epsg}", west, south, east, north
        )
    except Exception as error:  # pragma: no cover - backend-specific exception types
        raise SentinelMosaicContractError("bbox projection failed") from error
    if not isinstance(projected, Sequence) or len(projected) != 4:
        raise SentinelMosaicContractError("bbox projection returned invalid bounds")
    left, bottom, right, top = (
        _finite_number(value, "projected bbox coordinate") for value in projected
    )
    column_start = math.floor((left - grid.c) / grid.a)
    column_stop = math.ceil((right - grid.c) / grid.a)
    row_start = math.floor((grid.f - top) / grid.a)
    row_stop = math.ceil((grid.f - bottom) / grid.a)
    return GridWindow(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    )


def _grid_rectangle(grid: GridSpec, anchor: GridSpec) -> GridWindow:
    column, row = grid_offset(grid, anchor)
    return GridWindow(column, row, grid.width, grid.height)


def rectangles_cover_window(rectangles: Iterable[GridWindow], window: GridWindow) -> bool:
    """Test exact coverage by an axis-aligned union without raster allocation."""

    clipped: list[tuple[int, int, int, int]] = []
    for rectangle in rectangles:
        left = max(window.left, rectangle.left)
        right = min(window.right, rectangle.right)
        top = max(window.top, rectangle.top)
        bottom = min(window.bottom, rectangle.bottom)
        if left < right and top < bottom:
            clipped.append((left, top, right, bottom))
    if not clipped:
        return False
    y_points = sorted(
        {window.top, window.bottom}
        | {top for _, top, _, _ in clipped}
        | {bottom for _, _, _, bottom in clipped}
    )
    for top, bottom in zip(y_points, y_points[1:]):
        if top >= bottom or bottom <= window.top or top >= window.bottom:
            continue
        intervals = sorted(
            (left, right)
            for left, rectangle_top, right, rectangle_bottom in clipped
            if rectangle_top <= top and rectangle_bottom >= bottom
        )
        cursor = window.left
        for left, right in intervals:
            if right <= cursor:
                continue
            if left > cursor:
                return False
            cursor = max(cursor, right)
            if cursor >= window.right:
                break
        if cursor < window.right:
            return False
    return True


def epoch_metadata_coverage(
    primary_item: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    bbox: Sequence[float],
    transform_bounds: Callable[..., Sequence[float]],
) -> dict[str, Any]:
    """Prove archived-grid coverage for all required assets without opening COGs."""

    validate_epoch_grid_contract(items)
    if primary_item.get("id") not in {item.get("id") for item in items}:
        raise SentinelMosaicContractError("primary item is absent from bound epoch items")
    assets: dict[str, Any] = {}
    complete = True
    for asset_name in REQUIRED_ASSETS:
        anchor = grid_from_item(primary_item, asset_name)
        request = window_from_wgs84_bbox(anchor, bbox, transform_bounds)
        interpolation_halo = 1 if asset_name == "swir16" else 0
        required_window = request.padded(interpolation_halo)
        if required_window.width * required_window.height > MAX_PREFLIGHT_WINDOW_CELLS:
            raise SentinelMosaicContractError(
                f"asset {asset_name} preflight window exceeds the fixed cell ceiling"
            )
        grids = [grid_from_item(item, asset_name) for item in items]
        covered = rectangles_cover_window(
            (_grid_rectangle(grid, anchor) for grid in grids), required_window
        )
        complete &= covered
        assets[asset_name] = {
            "complete": covered,
            "interpolation_halo_pixels": interpolation_halo,
            "required_window": {
                "col_off": required_window.col_off,
                "row_off": required_window.row_off,
                "width": required_window.width,
                "height": required_window.height,
            },
        }
    return {"assets": assets, "complete": complete}


def preflight_archived_epoch(
    document: Mapping[str, Any],
    primary: ItemBinding,
    bbox: Sequence[float],
    transform_bounds: Callable[..., Sequence[float]],
) -> dict[str, Any]:
    """Discover and assess same-acquisition companions in one frozen response."""

    discovered = discover_same_acquisition_bindings(document, primary)
    companions = tuple(binding for binding in discovered if binding.item_id != primary.item_id)
    primary_item, items = select_bound_items(document, primary, companions)
    coverage = epoch_metadata_coverage(primary_item, items, bbox, transform_bounds)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "spectral_core_algorithm_version": SPECTRAL_CORE_ALGORITHM_VERSION,
        "primary": primary.as_dict(),
        "companion_contract": {
            "maximum_normalized_sensing_time_delta_seconds": (
                MAX_COMPANION_TIME_DELTA_SECONDS
            ),
            "product_uri_identity": "exact_except_mgrs_tile_token",
            "same_datatake_and_datastrip": True,
        },
        "proposed_explicit_bindings": [binding.as_dict() for binding in discovered],
        "coverage": coverage,
        "metadata_solvable": coverage["complete"],
        "network_requests": 0,
    }


def mosaic_nonzero_tiles(
    tiles: Sequence[ArrayTile], output_shape: tuple[int, int]
) -> tuple[Any, Any, Any]:
    """Mosaic nonzero arrays deterministically and reject conflicting overlap.

    Returns ``(values, nonzero_data_mask, spatial_coverage_mask)``.  Spatial
    coverage is tracked independently from nonzero data so an uncovered pixel
    can never be mistaken for a valid zero or a clear observation.
    """

    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - optional runtime guard
        raise RuntimeError("multi-tile mosaicking requires NumPy") from error
    if (
        not isinstance(output_shape, tuple)
        or len(output_shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in output_shape
        )
    ):
        raise SentinelMosaicContractError(
            "mosaic output shape must contain positive integer height and width"
        )
    if not tiles:
        raise SentinelMosaicContractError("mosaic requires at least one tile")
    ids = [tile.item_id for tile in tiles]
    if len(ids) != len(set(ids)):
        raise SentinelMosaicContractError("mosaic tiles contain a duplicate item ID")
    ordered = sorted(tiles, key=lambda tile: tile.item_id)
    first = np.asarray(ordered[0].values)
    if first.ndim != 2 or first.size == 0:
        raise SentinelMosaicContractError("mosaic tile arrays must be non-empty and 2D")
    dtype = first.dtype
    values = np.zeros(output_shape, dtype=dtype)
    nonzero = np.zeros(output_shape, dtype=bool)
    spatial = np.zeros(output_shape, dtype=bool)
    for tile in ordered:
        array = np.asarray(tile.values)
        if array.ndim != 2 or array.size == 0:
            raise SentinelMosaicContractError(
                f"mosaic tile {tile.item_id} is not a non-empty 2D array"
            )
        if array.dtype != dtype:
            raise SentinelMosaicContractError("mosaic tile dtypes differ")
        for label, offset in (
            ("row", tile.row_offset),
            ("column", tile.column_offset),
        ):
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise SentinelMosaicContractError(
                    f"mosaic tile {tile.item_id} {label} offset is invalid"
                )
        bottom = tile.row_offset + array.shape[0]
        right = tile.column_offset + array.shape[1]
        if bottom > output_shape[0] or right > output_shape[1]:
            raise SentinelMosaicContractError(
                f"mosaic tile {tile.item_id} exceeds the output grid"
            )
        row_slice = slice(tile.row_offset, bottom)
        column_slice = slice(tile.column_offset, right)
        destination = values[row_slice, column_slice]
        destination_nonzero = nonzero[row_slice, column_slice]
        source_nonzero = array != 0
        conflicts = destination_nonzero & source_nonzero & (destination != array)
        if np.any(conflicts):
            raise SentinelMosaicContractError(
                f"mosaic has conflicting nonzero overlap at item {tile.item_id}"
            )
        fill = source_nonzero & ~destination_nonzero
        destination[fill] = array[fill]
        destination_nonzero |= source_nonzero
        spatial[row_slice, column_slice] = True
    return values, nonzero, spatial


def require_complete_spatial_coverage(
    spatial_coverage: Any, required_mask: Any | None = None
) -> None:
    """Reject any required pixel not covered by an explicitly selected grid."""

    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - optional runtime guard
        raise RuntimeError("coverage validation requires NumPy") from error
    spatial = np.asarray(spatial_coverage, dtype=bool)
    if spatial.ndim != 2 or spatial.size == 0:
        raise SentinelMosaicContractError("spatial coverage must be a non-empty 2D mask")
    if required_mask is None:
        required = np.ones(spatial.shape, dtype=bool)
    else:
        required = np.asarray(required_mask, dtype=bool)
        if required.shape != spatial.shape:
            raise SentinelMosaicContractError(
                "required and spatial coverage masks use different grids"
            )
    if np.any(required & ~spatial):
        raise SentinelMosaicContractError(
            "explicitly selected tiles do not completely cover the required grid"
        )
