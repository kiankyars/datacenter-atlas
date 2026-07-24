"""Pinned Microsoft Global ML Building Footprints inventory and review lane.

The upstream building polygons are lawful, useful visual-review context.  They
are not data-centre observations.  This module inventories the complete
official shard index and extracts only explicitly bounded pilot AOIs around
separately sourced construction records.  It never creates or merges an atlas
entity and never infers lifecycle, type, capacity, power, or energy from a
footprint, height, or confidence value.
"""

from __future__ import annotations

import base64
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import csv
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


SCHEMA_VERSION = 1
BUNDLE_FORMAT = "datacenter-atlas-microsoft-global-ml-buildings-review-v1"
DATASET_ID = "microsoft-global-ml-building-footprints"
PUBLISHER = "Microsoft"
DATA_LICENSE = "CDLA-Permissive-2.0"
OFFICIAL_HOST = "minedbuildings.z5.web.core.windows.net"
RAW_GITHUB_HOST = "raw.githubusercontent.com"
EARTH_MEAN_RADIUS_METRES = 6_371_008.8

INDEX_FILENAME = "dataset-links.csv"
LICENSE_FILENAME = "LICENSE.upstream"
INVENTORY_FILENAME = "global-inventory.jsonl"
LOCATION_INVENTORY_FILENAME = "location-inventory.jsonl"
INVENTORY_SUMMARY_FILENAME = "inventory-summary.json"
UPSTREAM_METADATA_FILENAME = "upstream-metadata.json"
PRIORS_FILENAME = "construction-priors.jsonl"
REVIEW_FILENAME = "review-context.geojsonl"
REVIEW_CSV_FILENAME = "review-context.csv"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

BASE_FILES = {
    INDEX_FILENAME,
    LICENSE_FILENAME,
    INVENTORY_FILENAME,
    LOCATION_INVENTORY_FILENAME,
    INVENTORY_SUMMARY_FILENAME,
    UPSTREAM_METADATA_FILENAME,
    PRIORS_FILENAME,
    REVIEW_FILENAME,
    REVIEW_CSV_FILENAME,
    COVERAGE_FILENAME,
    README_FILENAME,
    ATTRIBUTION_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
RAW_REPRODUCTION_FILES = {INDEX_FILENAME, LICENSE_FILENAME, PRIORS_FILENAME}

REVIEW_POLICY = {
    "purpose": "bounded_building_footprint_review_context",
    "review_only": True,
    "auto_merge_permitted": False,
    "building_footprint_establishes_data_centre_identity": False,
    "building_footprint_establishes_lifecycle_or_construction_status": False,
    "building_footprint_establishes_data_centre_type": False,
    "building_height_establishes_capacity_power_or_energy": False,
    "footprint_confidence_establishes_height_or_data_centre_identity": False,
    "operating_status_inference_permitted": False,
    "unique_site_count_inference_permitted": False,
    "independent_lifecycle_corroboration": False,
    "construction_prior_is_source_supported_context_not_a_geometry_match": True,
    "manual_imagery_and_document_review_required": True,
    "global_building_footprint_completeness_claimed": False,
    "global_data_centre_completeness_claimed": False,
}

ATLAS_NULL_FIELDS = {
    "annual_energy_mwh": None,
    "construction_status": None,
    "data_centre_identity": None,
    "data_centre_type": None,
    "gross_facility_power_mw": None,
    "it_capacity_mw": None,
    "operating_status": None,
    "pue": None,
    "unique_site_id": None,
}

VINTAGE_CAVEAT = (
    "No per-feature imagery or inference date is supplied. The pinned upstream "
    "README describes imagery spanning 2014-2024 in the dataset introduction "
    "and some 2026 updates derived from 2021-2025 imagery; a selected shard or "
    "footprint must not be assigned either range without separate evidence."
)

CONTINENTAL_LOCATIONS = {
    "Africa",
    "Asia",
    "AustraliaOceania",
    "Europe",
    "NorthAmerica",
    "SouthAmerica",
}

INDEX_HEADER = ("Location", "QuadKey", "Url", "Size", "UploadDate")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_QUADKEY_RE = re.compile(r"^[0-3]{9}$")
_SIZE_RE = re.compile(r"^(0|[1-9]\d*)(?:\.(\d+))?(B|KB|MB|GB)$")
_PILOT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SIZE_MULTIPLIERS = {
    "B": Decimal(1),
    "KB": Decimal(1024),
    "MB": Decimal(1024**2),
    "GB": Decimal(1024**3),
}


class MicrosoftBuildingFootprintsError(ValueError):
    """Raised when a fetch, inventory, or frozen bundle fails closed."""


def _canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    else:
        text = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    return (text + "\n").encode("utf-8")


def _jsonl(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json(record) for record in records)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _md5_base64(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MicrosoftBuildingFootprintsError(f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MicrosoftBuildingFootprintsError(
            f"{field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MicrosoftBuildingFootprintsError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _finite_number(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise MicrosoftBuildingFootprintsError(f"{field} must be a finite number")
    return float(value)


def _checkpoint(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) < {"bytes", "sha256"}:
        raise MicrosoftBuildingFootprintsError(f"{field} checkpoint is missing")
    size = value.get("bytes")
    digest = value.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise MicrosoftBuildingFootprintsError(f"{field}.bytes must be positive")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise MicrosoftBuildingFootprintsError(f"{field}.sha256 is invalid")
    result = {"bytes": size, "sha256": digest}
    md5 = value.get("content_md5_base64")
    if md5 is not None:
        if not isinstance(md5, str) or not md5:
            raise MicrosoftBuildingFootprintsError(
                f"{field}.content_md5_base64 is invalid"
            )
        result["content_md5_base64"] = md5
    return result


def _verify_checkpoint(path: Path, expected: Mapping[str, Any], field: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise MicrosoftBuildingFootprintsError(f"{field} must be a regular file")
    actual = _file_record(path)
    if actual != {"bytes": expected["bytes"], "sha256": expected["sha256"]}:
        raise MicrosoftBuildingFootprintsError(f"{field} checkpoint changed")
    expected_md5 = expected.get("content_md5_base64")
    if expected_md5 is not None and _md5_base64(path) != expected_md5:
        raise MicrosoftBuildingFootprintsError(f"{field} Content-MD5 changed")


def _url(value: Any, field: str, *, hosts: set[str]) -> str:
    if not isinstance(value, str) or not value:
        raise MicrosoftBuildingFootprintsError(f"{field} URL is missing")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.fragment:
        raise MicrosoftBuildingFootprintsError(f"{field} URL is not an allowed HTTPS URL")
    return value


def _bbox(value: Any, field: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise MicrosoftBuildingFootprintsError(f"{field} must have four coordinates")
    west, south, east, north = (
        _finite_number(item, f"{field}[{index}]") for index, item in enumerate(value)
    )
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise MicrosoftBuildingFootprintsError(f"{field} bounds are invalid")
    return west, south, east, north


def _bbox_area_km2(bbox: Sequence[float]) -> float:
    west, south, east, north = (float(value) for value in bbox)
    latitude = math.radians((south + north) / 2)
    width_km = (east - west) * 111.320 * math.cos(latitude)
    height_km = (north - south) * 110.574
    return width_km * height_km


def _load_definition(path: str | Path) -> tuple[dict[str, Any], bytes]:
    definition_path = Path(path)
    if definition_path.is_symlink() or not definition_path.is_file():
        raise MicrosoftBuildingFootprintsError("definition must be a regular file")
    raw = definition_path.read_bytes()
    try:
        definition = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MicrosoftBuildingFootprintsError("definition is not valid UTF-8 JSON") from error
    expected_keys = {
        "schema_version",
        "format",
        "bundle_id",
        "generated_at",
        "upstream",
        "construction_master",
        "selection",
        "pilots",
    }
    if not isinstance(definition, dict) or set(definition) != expected_keys:
        raise MicrosoftBuildingFootprintsError("definition fields changed")
    if (
        definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("format") != BUNDLE_FORMAT
    ):
        raise MicrosoftBuildingFootprintsError("definition identity changed")
    if not isinstance(definition.get("bundle_id"), str) or not definition["bundle_id"]:
        raise MicrosoftBuildingFootprintsError("bundle_id is missing")
    definition["generated_at"] = _timestamp(
        definition.get("generated_at"), "definition.generated_at"
    )

    upstream = definition.get("upstream")
    if not isinstance(upstream, dict) or set(upstream) != {
        "dataset_id",
        "publisher",
        "data_license",
        "index",
        "repository",
    }:
        raise MicrosoftBuildingFootprintsError("upstream definition changed")
    if (
        upstream.get("dataset_id") != DATASET_ID
        or upstream.get("publisher") != PUBLISHER
        or upstream.get("data_license") != DATA_LICENSE
    ):
        raise MicrosoftBuildingFootprintsError("upstream identity or license changed")

    index = upstream.get("index")
    if not isinstance(index, dict) or set(index) != {
        "url",
        "bytes",
        "sha256",
        "content_md5_base64",
        "last_modified",
        "etag",
        "expected_rows",
        "expected_unique_location_quadkeys",
        "expected_unique_urls",
        "expected_locations",
        "advertised_compressed_bytes_binary_approx",
    }:
        raise MicrosoftBuildingFootprintsError("index pin fields changed")
    _url(index.get("url"), "upstream.index", hosts={OFFICIAL_HOST})
    _checkpoint(index, "upstream.index")
    for key in (
        "expected_rows",
        "expected_unique_location_quadkeys",
        "expected_unique_urls",
        "expected_locations",
        "advertised_compressed_bytes_binary_approx",
    ):
        value = index.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MicrosoftBuildingFootprintsError(f"upstream.index.{key} is invalid")
    if not isinstance(index.get("last_modified"), str) or not index["last_modified"]:
        raise MicrosoftBuildingFootprintsError("index Last-Modified pin is missing")
    if not isinstance(index.get("etag"), str) or not index["etag"]:
        raise MicrosoftBuildingFootprintsError("index ETag pin is missing")

    repository = upstream.get("repository")
    if not isinstance(repository, dict) or set(repository) != {
        "url",
        "commit",
        "license_url",
        "license_file",
        "readme_url",
        "readme_file",
    }:
        raise MicrosoftBuildingFootprintsError("repository pin fields changed")
    _url(repository.get("url"), "repository", hosts={"github.com"})
    if not isinstance(repository.get("commit"), str) or _COMMIT_RE.fullmatch(
        repository["commit"]
    ) is None:
        raise MicrosoftBuildingFootprintsError("repository commit is invalid")
    _url(repository.get("license_url"), "repository.license", hosts={RAW_GITHUB_HOST})
    _url(repository.get("readme_url"), "repository.readme", hosts={RAW_GITHUB_HOST})
    _checkpoint(repository.get("license_file"), "repository.license_file")
    _checkpoint(repository.get("readme_file"), "repository.readme_file")

    construction = definition.get("construction_master")
    if not isinstance(construction, dict) or set(construction) != {
        "path",
        "bytes",
        "sha256",
        "manifest_sha256",
    }:
        raise MicrosoftBuildingFootprintsError("construction-master pin fields changed")
    path_value = construction.get("path")
    if (
        not isinstance(path_value, str)
        or not path_value
        or Path(path_value).is_absolute()
        or ".." in Path(path_value).parts
    ):
        raise MicrosoftBuildingFootprintsError("construction-master path is unsafe")
    _checkpoint(construction, "construction_master")
    if not isinstance(construction.get("manifest_sha256"), str) or _SHA256_RE.fullmatch(
        construction["manifest_sha256"]
    ) is None:
        raise MicrosoftBuildingFootprintsError("construction-master manifest pin is invalid")

    selection = definition.get("selection")
    expected_selection = {
        "geometry_predicate": "source_footprint_bbox_intersects_inclusive_aoi_bbox",
        "aoi_half_width_m": 1000,
        "maximum_aoi_area_km2": 4.1,
        "country_specific_shards_only": True,
        "continental_duplicate_shards_excluded": True,
    }
    if selection != expected_selection:
        raise MicrosoftBuildingFootprintsError("selection policy changed")

    pilots = definition.get("pilots")
    if not isinstance(pilots, list) or not pilots or len(pilots) > 16:
        raise MicrosoftBuildingFootprintsError("pilots must be a bounded non-empty list")
    pilot_ids: set[str] = set()
    location_quadkeys: set[tuple[str, str]] = set()
    filenames: set[str] = set()
    prior_rows: set[str] = set()
    for index_number, pilot in enumerate(pilots):
        field = f"pilots[{index_number}]"
        expected_pilot_keys = {
            "pilot_id",
            "location",
            "quadkey",
            "country_specific",
            "shard_filename",
            "shard_url",
            "advertised_size",
            "upload_date",
            "shard_bytes",
            "shard_sha256",
            "content_md5_base64",
            "last_modified",
            "etag",
            "decompressed_bytes",
            "decompressed_sha256",
            "expected_source_features",
            "expected_selected_features",
            "aoi",
            "construction_prior",
        }
        if not isinstance(pilot, dict) or set(pilot) != expected_pilot_keys:
            raise MicrosoftBuildingFootprintsError(f"{field} fields changed")
        pilot_id = pilot.get("pilot_id")
        if not isinstance(pilot_id, str) or _PILOT_ID_RE.fullmatch(pilot_id) is None:
            raise MicrosoftBuildingFootprintsError(f"{field}.pilot_id is invalid")
        if pilot_id in pilot_ids:
            raise MicrosoftBuildingFootprintsError("pilot IDs are not unique")
        pilot_ids.add(pilot_id)
        location = pilot.get("location")
        quadkey = pilot.get("quadkey")
        if not isinstance(location, str) or not location or location in CONTINENTAL_LOCATIONS:
            raise MicrosoftBuildingFootprintsError(
                f"{field} must use a country-specific, non-continental location"
            )
        if pilot.get("country_specific") is not True:
            raise MicrosoftBuildingFootprintsError(f"{field} is not country-specific")
        if not isinstance(quadkey, str) or _QUADKEY_RE.fullmatch(quadkey) is None:
            raise MicrosoftBuildingFootprintsError(f"{field}.quadkey is invalid")
        pair = (location, quadkey)
        if pair in location_quadkeys:
            raise MicrosoftBuildingFootprintsError("selected shard pair is duplicated")
        location_quadkeys.add(pair)
        filename = pilot.get("shard_filename")
        expected_filename = f"shard-{location}-{quadkey}.csv.gz"
        if filename != expected_filename or filename in filenames:
            raise MicrosoftBuildingFootprintsError(f"{field}.shard_filename is invalid")
        filenames.add(filename)
        shard_url = _url(pilot.get("shard_url"), f"{field}.shard", hosts={OFFICIAL_HOST})
        parsed_path = urllib.parse.unquote(urllib.parse.urlsplit(shard_url).path)
        if (
            f"/RegionName={location}/" not in parsed_path
            or f"/quadkey={quadkey}/" not in parsed_path
        ):
            raise MicrosoftBuildingFootprintsError(f"{field}.shard URL identity changed")
        _checkpoint(
            {
                "bytes": pilot.get("shard_bytes"),
                "sha256": pilot.get("shard_sha256"),
                "content_md5_base64": pilot.get("content_md5_base64"),
            },
            f"{field}.shard",
        )
        for key in ("decompressed_bytes", "expected_source_features", "expected_selected_features"):
            value = pilot.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MicrosoftBuildingFootprintsError(f"{field}.{key} is invalid")
        if pilot["decompressed_bytes"] <= 0 or pilot["expected_source_features"] <= 0:
            raise MicrosoftBuildingFootprintsError(f"{field} source counts must be positive")
        if not isinstance(pilot.get("decompressed_sha256"), str) or _SHA256_RE.fullmatch(
            pilot["decompressed_sha256"]
        ) is None:
            raise MicrosoftBuildingFootprintsError(f"{field} decompressed hash is invalid")
        for key in ("advertised_size", "upload_date", "last_modified", "etag"):
            if not isinstance(pilot.get(key), str) or not pilot[key]:
                raise MicrosoftBuildingFootprintsError(f"{field}.{key} is missing")
        _advertised_size(pilot["advertised_size"], f"{field}.advertised_size")
        aoi = pilot.get("aoi")
        if not isinstance(aoi, dict) or set(aoi) != {
            "center_longitude",
            "center_latitude",
            "bbox",
        }:
            raise MicrosoftBuildingFootprintsError(f"{field}.aoi fields changed")
        longitude = _finite_number(aoi.get("center_longitude"), f"{field}.aoi.longitude")
        latitude = _finite_number(aoi.get("center_latitude"), f"{field}.aoi.latitude")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise MicrosoftBuildingFootprintsError(f"{field}.aoi center is invalid")
        west, south, east, north = _bbox(aoi.get("bbox"), f"{field}.aoi.bbox")
        if not (west <= longitude <= east and south <= latitude <= north):
            raise MicrosoftBuildingFootprintsError(f"{field}.aoi does not contain its center")
        if _bbox_area_km2((west, south, east, north)) > selection["maximum_aoi_area_km2"]:
            raise MicrosoftBuildingFootprintsError(f"{field}.aoi exceeds the area ceiling")
        prior = pilot.get("construction_prior")
        expected_prior_keys = {
            "row_id",
            "source_line_number",
            "source_line_bytes",
            "source_line_sha256",
            "name",
            "country",
            "entity_kind",
            "longitude",
            "latitude",
            "tier",
            "normalized_status",
            "reported_status",
            "reported_status_date",
            "construction_method",
            "source_release_id",
            "source_record_id",
            "source_manifest_sha256",
            "source_artifact_sha256",
            "source_url",
            "source_license",
            "evidence_ids",
        }
        if not isinstance(prior, dict) or set(prior) != expected_prior_keys:
            raise MicrosoftBuildingFootprintsError(f"{field}.construction_prior changed")
        row_id = prior.get("row_id")
        if not isinstance(row_id, str) or not row_id or row_id in prior_rows:
            raise MicrosoftBuildingFootprintsError("construction-prior row IDs are invalid")
        prior_rows.add(row_id)
        for key in ("source_line_number", "source_line_bytes"):
            value = prior.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise MicrosoftBuildingFootprintsError(f"{field}.construction_prior.{key} is invalid")
        for key in ("source_line_sha256", "source_manifest_sha256", "source_artifact_sha256"):
            value = prior.get(key)
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise MicrosoftBuildingFootprintsError(f"{field}.construction_prior.{key} is invalid")
        if prior.get("longitude") != longitude or prior.get("latitude") != latitude:
            raise MicrosoftBuildingFootprintsError(
                f"{field} AOI center must equal the construction-prior coordinate"
            )
        if not isinstance(prior.get("evidence_ids"), list) or not prior["evidence_ids"]:
            raise MicrosoftBuildingFootprintsError(f"{field} evidence IDs are missing")
    return definition, raw


def _advertised_size(value: str, field: str) -> Decimal:
    match = _SIZE_RE.fullmatch(value)
    if match is None:
        raise MicrosoftBuildingFootprintsError(f"{field} has an invalid advertised size")
    number = match.group(1)
    fraction = match.group(2)
    if fraction is not None:
        number = f"{number}.{fraction}"
    try:
        return Decimal(number) * _SIZE_MULTIPLIERS[match.group(3)]
    except InvalidOperation as error:
        raise MicrosoftBuildingFootprintsError(f"{field} has an invalid size") from error


def _rounded_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def inventory_index(
    index_path: str | Path,
    *,
    definition_path: str | Path | None = None,
    _definition: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Parse and inventory every row in one exact official dataset index."""

    if definition_path is not None and _definition is not None:
        raise MicrosoftBuildingFootprintsError(
            "supply either definition_path or the internal definition, not both"
        )
    definition: Mapping[str, Any] | None = _definition
    if definition_path is not None:
        definition, _ = _load_definition(definition_path)
    path = Path(index_path)
    if path.is_symlink() or not path.is_file():
        raise MicrosoftBuildingFootprintsError("dataset index must be a regular file")
    if definition is not None:
        _verify_checkpoint(path, definition["upstream"]["index"], "dataset index")
    selected = (
        {(item["location"], item["quadkey"]): item for item in definition["pilots"]}
        if definition is not None
        else {}
    )
    normalized: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    urls: set[str] = set()
    locations: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"advertised": Decimal(0), "quadkeys": 0, "selected": 0}
    )
    advertised_total = Decimal(0)
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != INDEX_HEADER:
                raise MicrosoftBuildingFootprintsError("dataset index header changed")
            previous: tuple[str, str] | None = None
            for line_number, row in enumerate(reader, 2):
                if set(row) != set(INDEX_HEADER) or any(value is None for value in row.values()):
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} is malformed"
                    )
                location = row["Location"]
                quadkey = row["QuadKey"]
                url = row["Url"]
                advertised_text = row["Size"]
                upload_date = row["UploadDate"]
                if not location or not isinstance(location, str):
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} location is missing"
                    )
                if _QUADKEY_RE.fullmatch(quadkey) is None:
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} quadkey is invalid"
                    )
                parsed_url = _url(url, f"dataset index row {line_number}", hosts={OFFICIAL_HOST})
                decoded_path = urllib.parse.unquote(urllib.parse.urlsplit(parsed_url).path)
                if (
                    f"/RegionName={location}/" not in decoded_path
                    or f"/quadkey={quadkey}/" not in decoded_path
                    or not decoded_path.endswith(".csv.gz")
                ):
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} URL identity changed"
                    )
                try:
                    datetime.strptime(upload_date, "%Y-%m-%d")
                except ValueError as error:
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} upload date is invalid"
                    ) from error
                advertised = _advertised_size(
                    advertised_text, f"dataset index row {line_number}"
                )
                pair = (location, quadkey)
                if pair in pairs or url in urls:
                    raise MicrosoftBuildingFootprintsError(
                        f"dataset index row {line_number} is duplicated"
                    )
                if previous is not None and pair < previous:
                    raise MicrosoftBuildingFootprintsError("dataset index ordering changed")
                previous = pair
                pairs.add(pair)
                urls.add(url)
                selected_pilot = selected.get(pair)
                if selected_pilot is not None and (
                    selected_pilot["shard_url"] != url
                    or selected_pilot["advertised_size"] != advertised_text
                    or selected_pilot["upload_date"] != upload_date
                ):
                    raise MicrosoftBuildingFootprintsError(
                        f"selected shard {location}/{quadkey} does not match the pinned index"
                    )
                normalized.append(
                    {
                        "advertised_size": advertised_text,
                        "advertised_size_binary_bytes_approx_decimal": format(
                            advertised, "f"
                        ),
                        "location": location,
                        "quadkey": quadkey,
                        "selected_for_pilot": (
                            selected_pilot["pilot_id"] if selected_pilot else None
                        ),
                        "upload_date": upload_date,
                        "url": url,
                    }
                )
                advertised_total += advertised
                locations[location]["advertised"] += advertised
                locations[location]["quadkeys"] += 1
                locations[location]["selected"] += int(selected_pilot is not None)
    except UnicodeDecodeError as error:
        raise MicrosoftBuildingFootprintsError("dataset index is not UTF-8") from error

    location_records = [
        {
            "advertised_compressed_bytes_binary_approx": _rounded_decimal(
                values["advertised"]
            ),
            "location": location,
            "quadkey_rows": values["quadkeys"],
            "selected_country_shard_rows": values["selected"],
        }
        for location, values in sorted(locations.items())
    ]
    summary = {
        "advertised_compressed_bytes_binary_approx": _rounded_decimal(
            advertised_total
        ),
        "advertised_sizes_are_rounded_index_labels_not_actual_byte_counts": True,
        "binary_unit_basis": 1024,
        "index_rows": len(normalized),
        "locations": len(locations),
        "selected_country_shards": len(selected),
        "unique_location_quadkeys": len(pairs),
        "unique_urls": len(urls),
    }
    if definition is not None:
        expected = definition["upstream"]["index"]
        expected_summary = {
            "index_rows": expected["expected_rows"],
            "unique_location_quadkeys": expected[
                "expected_unique_location_quadkeys"
            ],
            "unique_urls": expected["expected_unique_urls"],
            "locations": expected["expected_locations"],
            "advertised_compressed_bytes_binary_approx": expected[
                "advertised_compressed_bytes_binary_approx"
            ],
        }
        for key, value in expected_summary.items():
            if summary[key] != value:
                raise MicrosoftBuildingFootprintsError(
                    f"dataset index {key} changed: {summary[key]} != {value}"
                )
        if summary["selected_country_shards"] != len(definition["pilots"]):
            raise MicrosoftBuildingFootprintsError(
                "not every pinned pilot shard exists in the official index"
            )
    return normalized, location_records, summary


class PinnedHTTPDownloader:
    """Small HTTPS downloader with explicit request and size ceilings."""

    def __init__(
        self,
        *,
        maximum_requests: int = 8,
        minimum_interval_seconds: float = 0.25,
        timeout_seconds: float = 90.0,
    ) -> None:
        if maximum_requests <= 0 or minimum_interval_seconds < 0 or timeout_seconds <= 0:
            raise MicrosoftBuildingFootprintsError("invalid downloader limits")
        self.maximum_requests = maximum_requests
        self.minimum_interval_seconds = float(minimum_interval_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.requests_made = 0
        self._last_request_started: float | None = None

    def download(self, url: str, destination: Path, expected_bytes: int) -> dict[str, Any]:
        if self.requests_made >= self.maximum_requests:
            raise MicrosoftBuildingFootprintsError("HTTP request ceiling exceeded")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            OFFICIAL_HOST,
            RAW_GITHUB_HOST,
        }:
            raise MicrosoftBuildingFootprintsError("refusing unapproved download host")
        if destination.exists() or destination.is_symlink():
            raise MicrosoftBuildingFootprintsError("refusing existing download target")
        if self._last_request_started is not None:
            delay = self.minimum_interval_seconds - (
                time.monotonic() - self._last_request_started
            )
            if delay > 0:
                time.sleep(delay)
        self._last_request_started = time.monotonic()
        self.requests_made += 1
        request = urllib.request.Request(
            url,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "datacenter-atlas-microsoft-buildings/1",
            },
        )
        digest = hashlib.sha256()
        size = 0
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                encoding = response.headers.get("Content-Encoding")
                if encoding not in {None, "identity"}:
                    raise MicrosoftBuildingFootprintsError(
                        "server returned an encoded representation"
                    )
                length = response.headers.get("Content-Length")
                if length is not None and int(length) != expected_bytes:
                    raise MicrosoftBuildingFootprintsError(
                        "server Content-Length differs from the pin"
                    )
                with destination.open("xb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > expected_bytes:
                            raise MicrosoftBuildingFootprintsError(
                                "download exceeded its pinned size"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                headers = {
                    "content_md5_base64": response.headers.get("Content-MD5"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except (OSError, urllib.error.URLError, ValueError) as error:
            if destination.exists() and not destination.is_symlink():
                destination.unlink()
            if isinstance(error, MicrosoftBuildingFootprintsError):
                raise
            raise MicrosoftBuildingFootprintsError(f"download failed: {url}") from error
        if size != expected_bytes:
            destination.unlink(missing_ok=True)
            raise MicrosoftBuildingFootprintsError("download ended before its pinned size")
        return {"bytes": size, "sha256": digest.hexdigest(), **headers}


def _verify_observed_http_metadata(
    observed: Any, expected: Mapping[str, Any], field: str
) -> None:
    if not isinstance(observed, Mapping):
        return
    for observed_key, expected_key in (
        ("content_md5_base64", "content_md5_base64"),
        ("etag", "etag"),
        ("last_modified", "last_modified"),
    ):
        observed_value = observed.get(observed_key)
        expected_value = expected.get(expected_key)
        if (
            observed_value is not None
            and expected_value is not None
            and observed_value != expected_value
        ):
            raise MicrosoftBuildingFootprintsError(
                f"{field} HTTP {observed_key} changed"
            )


def _coordinate(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) < 2:
        raise MicrosoftBuildingFootprintsError(f"{field} coordinate is invalid")
    longitude = _finite_number(value[0], f"{field}.longitude")
    latitude = _finite_number(value[1], f"{field}.latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise MicrosoftBuildingFootprintsError(f"{field} coordinate is outside WGS84")
    return longitude, latitude


def _polygons(geometry: Any) -> list[list[list[Any]]]:
    if not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"}:
        raise MicrosoftBuildingFootprintsError("source geometry fields changed")
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        polygons = [geometry.get("coordinates")]
    elif geometry_type == "MultiPolygon":
        polygons = geometry.get("coordinates")
    else:
        raise MicrosoftBuildingFootprintsError(
            "source building geometry must be Polygon or MultiPolygon"
        )
    if not isinstance(polygons, list) or not polygons:
        raise MicrosoftBuildingFootprintsError("source geometry has no polygons")
    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise MicrosoftBuildingFootprintsError(
                f"source polygon {polygon_index} has no rings"
            )
        for ring_index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4:
                raise MicrosoftBuildingFootprintsError(
                    f"source polygon {polygon_index} ring {ring_index} is too short"
                )
            if _coordinate(ring[0], "ring first vertex") != _coordinate(
                ring[-1], "ring last vertex"
            ):
                raise MicrosoftBuildingFootprintsError("source polygon ring is not closed")
            for vertex_index, vertex in enumerate(ring):
                _coordinate(vertex, f"ring vertex {vertex_index}")
    return polygons


def _ring_measurement(
    ring: Sequence[Any], *, longitude_origin: float, latitude_origin: float
) -> tuple[float, float, float]:
    cosine = math.cos(math.radians(latitude_origin))
    projected = [
        (
            EARTH_MEAN_RADIUS_METRES
            * math.radians(longitude - longitude_origin)
            * cosine,
            EARTH_MEAN_RADIUS_METRES * math.radians(latitude - latitude_origin),
        )
        for longitude, latitude in (
            _coordinate(vertex, "ring vertex") for vertex in ring
        )
    ]
    cross_sum = 0.0
    centroid_x_sum = 0.0
    centroid_y_sum = 0.0
    for (x1, y1), (x2, y2) in zip(projected, projected[1:]):
        cross = x1 * y2 - x2 * y1
        cross_sum += cross
        centroid_x_sum += (x1 + x2) * cross
        centroid_y_sum += (y1 + y2) * cross
    signed_area = cross_sum / 2.0
    if abs(signed_area) <= 1e-9:
        raise MicrosoftBuildingFootprintsError("source polygon ring has zero area")
    return (
        abs(signed_area),
        centroid_x_sum / (6.0 * signed_area),
        centroid_y_sum / (6.0 * signed_area),
    )


def _geometry_metrics(geometry: Any) -> dict[str, Any]:
    polygons = _polygons(geometry)
    coordinates = [
        _coordinate(vertex, "geometry vertex")
        for polygon in polygons
        for ring in polygon
        for vertex in ring
    ]
    longitude_origin = sum(point[0] for point in coordinates) / len(coordinates)
    latitude_origin = sum(point[1] for point in coordinates) / len(coordinates)
    weighted_x = 0.0
    weighted_y = 0.0
    total_area = 0.0
    for polygon in polygons:
        outer_area, outer_x, outer_y = _ring_measurement(
            polygon[0],
            longitude_origin=longitude_origin,
            latitude_origin=latitude_origin,
        )
        polygon_area = outer_area
        polygon_x = outer_area * outer_x
        polygon_y = outer_area * outer_y
        for hole in polygon[1:]:
            hole_area, hole_x, hole_y = _ring_measurement(
                hole,
                longitude_origin=longitude_origin,
                latitude_origin=latitude_origin,
            )
            polygon_area -= hole_area
            polygon_x -= hole_area * hole_x
            polygon_y -= hole_area * hole_y
        if polygon_area <= 0:
            raise MicrosoftBuildingFootprintsError(
                "source polygon holes consume the outer ring"
            )
        total_area += polygon_area
        weighted_x += polygon_x
        weighted_y += polygon_y
    centroid_x = weighted_x / total_area
    centroid_y = weighted_y / total_area
    cosine = math.cos(math.radians(latitude_origin))
    centroid_longitude = longitude_origin + math.degrees(
        centroid_x / (EARTH_MEAN_RADIUS_METRES * cosine)
    )
    centroid_latitude = latitude_origin + math.degrees(
        centroid_y / EARTH_MEAN_RADIUS_METRES
    )
    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]
    return {
        "approximate_footprint_area_m2": round(total_area, 3),
        "bbox": [
            round(min(longitudes), 12),
            round(min(latitudes), 12),
            round(max(longitudes), 12),
            round(max(latitudes), 12),
        ],
        "centroid_latitude": round(centroid_latitude, 9),
        "centroid_longitude": round(centroid_longitude, 9),
        "geometry_type": geometry["type"],
        "measurement_method": "local_equirectangular_shoelace_outer_minus_holes",
        "rings": sum(len(polygon) for polygon in polygons),
        "vertices_including_ring_closures": len(coordinates),
    }


def _intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _haversine_metres(
    longitude_a: float,
    latitude_a: float,
    longitude_b: float,
    latitude_b: float,
) -> float:
    latitude_a_radians = math.radians(latitude_a)
    latitude_b_radians = math.radians(latitude_b)
    latitude_delta = latitude_b_radians - latitude_a_radians
    longitude_delta = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_a_radians)
        * math.cos(latitude_b_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_METRES * math.asin(min(1.0, math.sqrt(value)))


def _validate_source_feature(value: Any, line_number: int) -> tuple[dict[str, Any], float, float]:
    if not isinstance(value, dict) or set(value) != {"type", "properties", "geometry"}:
        raise MicrosoftBuildingFootprintsError(
            f"source feature line {line_number} fields changed"
        )
    if value.get("type") != "Feature":
        raise MicrosoftBuildingFootprintsError(
            f"source feature line {line_number} is not a Feature"
        )
    properties = value.get("properties")
    if not isinstance(properties, dict) or set(properties) != {"height", "confidence"}:
        raise MicrosoftBuildingFootprintsError(
            f"source feature line {line_number} properties changed"
        )
    height = _finite_number(properties.get("height"), "source height")
    confidence = _finite_number(properties.get("confidence"), "source confidence")
    if height < 0 and height != -1:
        raise MicrosoftBuildingFootprintsError("source height is outside documented semantics")
    if confidence != -1 and not 0 <= confidence <= 1:
        raise MicrosoftBuildingFootprintsError(
            "source confidence is outside documented semantics"
        )
    _polygons(value.get("geometry"))
    return value, height, confidence


def _prior_record(pilot: Mapping[str, Any]) -> dict[str, Any]:
    prior = pilot["construction_prior"]
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": pilot["pilot_id"],
        "construction_master_source": {
            "row_id": prior["row_id"],
            "source_line_bytes": prior["source_line_bytes"],
            "source_line_number": prior["source_line_number"],
            "source_line_sha256": prior["source_line_sha256"],
        },
        "source_supported_record": {
            "construction": {
                "method": prior["construction_method"],
                "source_supported": True,
                "verification_status": "source_supported_not_independently_verified",
                "verified": False,
            },
            "country": prior["country"],
            "entity_kind": prior["entity_kind"],
            "latitude": prior["latitude"],
            "lifecycle": {
                "normalized_status": prior["normalized_status"],
                "reported_status": prior["reported_status"],
                "reported_status_date": prior["reported_status_date"],
            },
            "longitude": prior["longitude"],
            "name": prior["name"],
            "source_lineage": {
                "artifact_sha256": prior["source_artifact_sha256"],
                "evidence_ids": prior["evidence_ids"],
                "license": prior["source_license"],
                "manifest_sha256": prior["source_manifest_sha256"],
                "record_id": prior["source_record_id"],
                "release_id": prior["source_release_id"],
                "url": prior["source_url"],
            },
            "tier": prior["tier"],
        },
        "relationship_policy": {
            "building_footprints_are_only_bounded_review_context": True,
            "construction_prior_applies_to_the_source_record_only": True,
            "footprint_match_or_merge_performed": False,
            "independent_lifecycle_corroboration_from_this_lane": False,
        },
    }


def _verify_construction_row(pilot: Mapping[str, Any], raw: bytes, row: Any) -> None:
    prior = pilot["construction_prior"]
    if len(raw) != prior["source_line_bytes"] or _sha256_bytes(raw) != prior[
        "source_line_sha256"
    ]:
        raise MicrosoftBuildingFootprintsError(
            f"construction-master row changed: {prior['row_id']}"
        )
    if not isinstance(row, dict) or row.get("row_id") != prior["row_id"]:
        raise MicrosoftBuildingFootprintsError("construction-master row identity changed")
    entity = row.get("entity")
    lifecycle = row.get("lifecycle")
    construction = row.get("construction")
    source = row.get("source")
    if not all(isinstance(item, dict) for item in (entity, lifecycle, construction, source)):
        raise MicrosoftBuildingFootprintsError("construction-master row shape changed")
    expected = {
        "name": entity.get("name"),
        "country": entity.get("country"),
        "entity_kind": entity.get("kind"),
        "longitude": entity.get("longitude"),
        "latitude": entity.get("latitude"),
        "tier": row.get("tier"),
        "normalized_status": lifecycle.get("normalized_status"),
        "reported_status": lifecycle.get("reported_status"),
        "reported_status_date": lifecycle.get("reported_status_date"),
        "construction_method": construction.get("method"),
        "source_release_id": source.get("release_id"),
        "source_record_id": source.get("record_id"),
        "source_manifest_sha256": source.get("manifest_sha256"),
        "source_artifact_sha256": source.get("artifact_sha256"),
        "source_url": source.get("source_url"),
        "source_license": source.get("source_license"),
        "evidence_ids": source.get("evidence_ids"),
    }
    for key, value in expected.items():
        if prior.get(key) != value:
            raise MicrosoftBuildingFootprintsError(
                f"construction-master row field changed: {prior['row_id']} {key}"
            )
    if (
        construction.get("source_supported") is not True
        or construction.get("verified") is not False
        or construction.get("verification_status")
        != "source_supported_not_independently_verified"
    ):
        raise MicrosoftBuildingFootprintsError(
            "construction-master source-supported boundary changed"
        )


def _extract_construction_priors(
    definition: Mapping[str, Any], construction_master_path: Path
) -> list[dict[str, Any]]:
    manifest_path = construction_master_path.with_name(MANIFEST_FILENAME)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MicrosoftBuildingFootprintsError("construction-master manifest is missing")
    manifest_raw = manifest_path.read_bytes()
    if _sha256_bytes(manifest_raw) != definition["construction_master"][
        "manifest_sha256"
    ]:
        raise MicrosoftBuildingFootprintsError(
            "construction-master manifest checkpoint changed"
        )
    try:
        construction_manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MicrosoftBuildingFootprintsError(
            "construction-master manifest is invalid"
        ) from error
    outputs = (
        construction_manifest.get("outputs")
        if isinstance(construction_manifest, dict)
        else None
    )
    source_output = (
        outputs.get(construction_master_path.name)
        if isinstance(outputs, dict)
        else None
    )
    if not isinstance(source_output, dict) or {
        "bytes": source_output.get("bytes"),
        "sha256": source_output.get("sha256"),
    } != {
        "bytes": definition["construction_master"]["bytes"],
        "sha256": definition["construction_master"]["sha256"],
    }:
        raise MicrosoftBuildingFootprintsError(
            "construction-master manifest does not pin the supplied JSONL"
        )
    sidecar_path = construction_master_path.with_name(MANIFEST_HASH_FILENAME)
    expected_sidecar = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if (
        sidecar_path.is_symlink()
        or not sidecar_path.is_file()
        or sidecar_path.read_bytes() != expected_sidecar
    ):
        raise MicrosoftBuildingFootprintsError(
            "construction-master manifest sidecar changed"
        )
    _verify_checkpoint(
        construction_master_path,
        definition["construction_master"],
        "construction master",
    )
    wanted = {
        item["construction_prior"]["row_id"]: item for item in definition["pilots"]
    }
    found: set[str] = set()
    with construction_master_path.open("rb") as source:
        for line_number, raw in enumerate(source, 1):
            if line_number not in {
                item["construction_prior"]["source_line_number"]
                for item in definition["pilots"]
            }:
                continue
            try:
                row = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise MicrosoftBuildingFootprintsError(
                    f"construction-master line {line_number} is invalid"
                ) from error
            row_id = row.get("row_id") if isinstance(row, dict) else None
            pilot = wanted.get(row_id)
            if pilot is None:
                raise MicrosoftBuildingFootprintsError(
                    f"construction-master expected line {line_number} has another row"
                )
            if pilot["construction_prior"]["source_line_number"] != line_number:
                raise MicrosoftBuildingFootprintsError(
                    "construction-master row line number changed"
                )
            _verify_construction_row(pilot, raw, row)
            found.add(row_id)
    if found != set(wanted):
        raise MicrosoftBuildingFootprintsError("construction-master prior rows are missing")
    return [_prior_record(pilot) for pilot in sorted(definition["pilots"], key=lambda x: x["pilot_id"])]


def _validate_prior_bytes(raw: bytes, definition: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = [
        _prior_record(pilot)
        for pilot in sorted(definition["pilots"], key=lambda x: x["pilot_id"])
    ]
    if raw != _jsonl(expected):
        raise MicrosoftBuildingFootprintsError("construction-prior subset changed")
    return expected


def _source_attribute_context(height: float, confidence: float) -> dict[str, Any]:
    return {
        "confidence_applies_to_footprint_not_height": True,
        "confidence_missing_legacy_sentinel": confidence == -1,
        "confidence_raw": confidence,
        "footprint_confidence": None if confidence == -1 else confidence,
        "height_establishes_no_capacity_power_or_energy": True,
        "height_m": None if height == -1 else height,
        "height_missing_sentinel": height == -1,
        "height_raw": height,
    }


def _review_feature(
    pilot: Mapping[str, Any],
    source_feature: Mapping[str, Any],
    *,
    line_number: int,
    line_sha256: str,
    height: float,
    confidence: float,
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    prior = pilot["construction_prior"]
    context_digest = hashlib.sha256(
        (
            f"{pilot['pilot_id']}\0{pilot['shard_sha256']}\0"
            f"{line_number}\0{line_sha256}"
        ).encode("utf-8")
    ).hexdigest()
    distance = _haversine_metres(
        metrics["centroid_longitude"],
        metrics["centroid_latitude"],
        prior["longitude"],
        prior["latitude"],
    )
    return {
        "type": "Feature",
        "id": f"msft-gmlbf:{context_digest}",
        "geometry": source_feature["geometry"],
        "properties": {
            "atlas_fields": dict(ATLAS_NULL_FIELDS),
            "auto_merge_permitted": False,
            "construction_prior_context": {
                "coordinate_distance_from_derived_footprint_centroid_m": round(
                    distance, 3
                ),
                "latitude": prior["latitude"],
                "longitude": prior["longitude"],
                "name": prior["name"],
                "row_id": prior["row_id"],
                "source_reported_status": prior["reported_status"],
                "status_is_not_independently_corroborated_by_this_footprint": True,
            },
            "footprint_or_height_establishes_no_data_centre_fact": True,
            "geometry_context": dict(metrics),
            "independent_lifecycle_corroboration": False,
            "pilot_aoi": {
                "bbox": pilot["aoi"]["bbox"],
                "relationship": "source_footprint_bbox_intersects_bounded_review_aoi_only",
            },
            "pilot_id": pilot["pilot_id"],
            "review_only": True,
            "schema_version": SCHEMA_VERSION,
            "source": {
                "confidence_and_height_vintage_is_not_known_per_feature": True,
                "data_license": DATA_LICENSE,
                "decompressed_line_number": line_number,
                "decompressed_line_sha256": line_sha256,
                "location": pilot["location"],
                "publisher": PUBLISHER,
                "quadkey": pilot["quadkey"],
                "shard_sha256": pilot["shard_sha256"],
                "shard_url": pilot["shard_url"],
                "vintage_caveat": VINTAGE_CAVEAT,
            },
            "source_attributes": _source_attribute_context(height, confidence),
            "unique_site_counted": False,
        },
    }


def _scan_shard(
    shard_path: Path, pilot: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _verify_checkpoint(
        shard_path,
        {
            "bytes": pilot["shard_bytes"],
            "sha256": pilot["shard_sha256"],
            "content_md5_base64": pilot["content_md5_base64"],
        },
        f"pilot shard {pilot['pilot_id']}",
    )
    selected: list[dict[str, Any]] = []
    decompressed_hash = hashlib.sha256()
    decompressed_bytes = 0
    feature_count = 0
    geometry_types: Counter[str] = Counter()
    height_count = 0
    confidence_count = 0
    selected_height_count = 0
    selected_confidence_count = 0
    selected_areas: list[float] = []
    aoi_bbox = pilot["aoi"]["bbox"]
    try:
        with gzip.open(shard_path, "rb") as source:
            for line_number, raw in enumerate(source, 1):
                decompressed_hash.update(raw)
                decompressed_bytes += len(raw)
                if not raw.endswith(b"\n"):
                    raise MicrosoftBuildingFootprintsError(
                        f"shard {pilot['pilot_id']} line {line_number} lacks newline"
                    )
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise MicrosoftBuildingFootprintsError(
                        f"shard {pilot['pilot_id']} line {line_number} is invalid JSON"
                    ) from error
                feature, height, confidence = _validate_source_feature(
                    value, line_number
                )
                metrics = _geometry_metrics(feature["geometry"])
                feature_count += 1
                geometry_types[metrics["geometry_type"]] += 1
                height_count += int(height != -1)
                confidence_count += int(confidence != -1)
                if not _intersects(metrics["bbox"], aoi_bbox):
                    continue
                selected_height_count += int(height != -1)
                selected_confidence_count += int(confidence != -1)
                selected_areas.append(metrics["approximate_footprint_area_m2"])
                selected.append(
                    _review_feature(
                        pilot,
                        feature,
                        line_number=line_number,
                        line_sha256=_sha256_bytes(raw),
                        height=height,
                        confidence=confidence,
                        metrics=metrics,
                    )
                )
    except (OSError, EOFError) as error:
        raise MicrosoftBuildingFootprintsError(
            f"pilot shard {pilot['pilot_id']} is not a valid gzip stream"
        ) from error
    if decompressed_bytes != pilot["decompressed_bytes"] or decompressed_hash.hexdigest() != pilot[
        "decompressed_sha256"
    ]:
        raise MicrosoftBuildingFootprintsError(
            f"pilot shard {pilot['pilot_id']} decompressed checkpoint changed"
        )
    if feature_count != pilot["expected_source_features"]:
        raise MicrosoftBuildingFootprintsError(
            f"pilot shard {pilot['pilot_id']} source-feature count changed"
        )
    if len(selected) != pilot["expected_selected_features"]:
        raise MicrosoftBuildingFootprintsError(
            f"pilot shard {pilot['pilot_id']} selected-feature count changed"
        )
    coverage = {
        "aoi": {
            "area_km2_approx": round(_bbox_area_km2(aoi_bbox), 6),
            "bbox": aoi_bbox,
            "center_latitude": pilot["aoi"]["center_latitude"],
            "center_longitude": pilot["aoi"]["center_longitude"],
        },
        "confidence_present_source_features": confidence_count,
        "confidence_present_selected_features": selected_confidence_count,
        "decompressed_bytes": decompressed_bytes,
        "decompressed_sha256": decompressed_hash.hexdigest(),
        "features_establishing_data_centre_identity_status_type_capacity_power_or_energy": 0,
        "geometry_types": dict(sorted(geometry_types.items())),
        "height_present_source_features": height_count,
        "height_present_selected_features": selected_height_count,
        "location": pilot["location"],
        "pilot_id": pilot["pilot_id"],
        "quadkey": pilot["quadkey"],
        "selected_approximate_area_m2": {
            "maximum": round(max(selected_areas), 3) if selected_areas else None,
            "minimum": round(min(selected_areas), 3) if selected_areas else None,
            "sum": round(sum(selected_areas), 3),
        },
        "selected_features": len(selected),
        "source_features": feature_count,
        "source_shard": {
            "bytes": pilot["shard_bytes"],
            "sha256": pilot["shard_sha256"],
            "url": pilot["shard_url"],
        },
    }
    return selected, coverage


CSV_FIELDS = (
    "context_id",
    "pilot_id",
    "construction_master_row_id",
    "location",
    "quadkey",
    "source_line_number",
    "source_line_sha256",
    "source_height_raw",
    "source_height_m",
    "source_height_missing",
    "source_confidence_raw",
    "source_footprint_confidence",
    "source_confidence_missing",
    "approximate_footprint_area_m2",
    "centroid_longitude",
    "centroid_latitude",
    "distance_from_construction_prior_m",
    "review_only",
    "auto_merge_permitted",
    "data_centre_identity",
    "construction_status",
    "data_centre_type",
    "it_capacity_mw",
    "gross_facility_power_mw",
    "annual_energy_mwh",
    "operating_status",
    "unique_site_id",
)


def _review_csv(features: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for feature in features:
        properties = feature["properties"]
        attributes = properties["source_attributes"]
        geometry = properties["geometry_context"]
        prior = properties["construction_prior_context"]
        source = properties["source"]
        atlas = properties["atlas_fields"]
        writer.writerow(
            {
                "context_id": feature["id"],
                "pilot_id": properties["pilot_id"],
                "construction_master_row_id": prior["row_id"],
                "location": source["location"],
                "quadkey": source["quadkey"],
                "source_line_number": source["decompressed_line_number"],
                "source_line_sha256": source["decompressed_line_sha256"],
                "source_height_raw": attributes["height_raw"],
                "source_height_m": attributes["height_m"],
                "source_height_missing": str(attributes["height_missing_sentinel"]).lower(),
                "source_confidence_raw": attributes["confidence_raw"],
                "source_footprint_confidence": attributes["footprint_confidence"],
                "source_confidence_missing": str(
                    attributes["confidence_missing_legacy_sentinel"]
                ).lower(),
                "approximate_footprint_area_m2": geometry[
                    "approximate_footprint_area_m2"
                ],
                "centroid_longitude": geometry["centroid_longitude"],
                "centroid_latitude": geometry["centroid_latitude"],
                "distance_from_construction_prior_m": prior[
                    "coordinate_distance_from_derived_footprint_centroid_m"
                ],
                "review_only": "true",
                "auto_merge_permitted": "false",
                "data_centre_identity": atlas["data_centre_identity"],
                "construction_status": atlas["construction_status"],
                "data_centre_type": atlas["data_centre_type"],
                "it_capacity_mw": atlas["it_capacity_mw"],
                "gross_facility_power_mw": atlas["gross_facility_power_mw"],
                "annual_energy_mwh": atlas["annual_energy_mwh"],
                "operating_status": atlas["operating_status"],
                "unique_site_id": atlas["unique_site_id"],
            }
        )
    return buffer.getvalue().encode("utf-8")


def _upstream_metadata(definition: Mapping[str, Any]) -> dict[str, Any]:
    upstream = definition["upstream"]
    repository = upstream["repository"]
    return {
        "attribute_semantics": {
            "confidence": (
                "0..1 footprint confidence; -1 is the documented legacy missing "
                "placeholder; confidence applies to footprint, not height"
            ),
            "height": "metres above ground; -1 is the documented missing placeholder",
        },
        "coverage_caveats": {
            "global_building_footprint_completeness_claimed": False,
            "global_data_centre_completeness_claimed": False,
            "official_index_inventory_is_not_downloaded_global_geometry": True,
            "upstream_documents_missing_tiles_and_geographic_quality_variation": True,
        },
        "data_license": upstream["data_license"],
        "dataset_id": upstream["dataset_id"],
        "distribution": {
            "country_and_lod9_quadkey_partitioned": True,
            "file_extension": ".csv.gz",
            "index": upstream["index"],
            "payload_format": "gzip-compressed line-delimited GeoJSON features",
        },
        "publisher": upstream["publisher"],
        "repository": {
            "commit": repository["commit"],
            "license_file": repository["license_file"],
            "readme_file": repository["readme_file"],
            "url": repository["url"],
        },
        "vintage_caveat": VINTAGE_CAVEAT,
    }


def _coverage_document(
    inventory: Mapping[str, Any],
    pilot_coverage: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    totals = {
        "compressed_selected_shard_bytes": sum(
            item["source_shard"]["bytes"] for item in pilot_coverage
        ),
        "confidence_present_selected_features": sum(
            item["confidence_present_selected_features"] for item in pilot_coverage
        ),
        "features_establishing_data_centre_identity_status_type_capacity_power_or_energy": 0,
        "height_present_selected_features": sum(
            item["height_present_selected_features"] for item in pilot_coverage
        ),
        "selected_features": sum(item["selected_features"] for item in pilot_coverage),
        "source_features_in_selected_shards": sum(
            item["source_features"] for item in pilot_coverage
        ),
    }
    return {
        "completeness": {
            "global_building_geometry_downloaded": False,
            "global_building_footprint_completeness_claimed": False,
            "global_data_centre_completeness_claimed": False,
            "official_index_rows_inventoried": inventory["index_rows"],
            "selected_country_shards_downloaded": len(pilot_coverage),
            "selected_country_shards_only": True,
        },
        "inventory": dict(inventory),
        "pilots": list(pilot_coverage),
        "review_policy": dict(REVIEW_POLICY),
        "totals": totals,
        "vintage_caveat": VINTAGE_CAVEAT,
    }


def _readme(definition: Mapping[str, Any], coverage: Mapping[str, Any]) -> bytes:
    inventory = coverage["inventory"]
    totals = coverage["totals"]
    text = f"""# Microsoft Global ML Building Footprints inventory and review pilot

This frozen bundle inventories all {inventory['index_rows']:,} rows and
{inventory['locations']:,} locations in the exact official Microsoft shard
index. It does **not** download the global geometry corpus. It retains
{len(coverage['pilots'])} country-specific shards and extracts
{totals['selected_features']:,} footprints whose geometry bounding boxes
intersect four bounded review AOIs around separately sourced construction
records.

The footprint rows are non-merging review context. A footprint, modelled height,
or model confidence establishes no data-centre identity, unique site, type,
lifecycle or construction status, operating status, capacity, power, PUE, or
annual energy. The construction priors remain source-supported records and are
not independently corroborated by this lane.

Upstream files use a `.csv.gz` extension but contain gzip-compressed,
line-delimited GeoJSON. Height is in metres with `-1` for missing. Confidence is
a footprint confidence from 0 to 1, with `-1` for legacy missing values; it does
not apply to height.

Vintage caveat: {VINTAGE_CAVEAT}

Source: Microsoft Global ML Building Footprints, pinned repository commit
`{definition['upstream']['repository']['commit']}` and exact index checkpoint.
Data license: CDLA Permissive 2.0. See `ATTRIBUTION.txt` and
`upstream-metadata.json`.
"""
    return text.encode("utf-8")


def _attribution(definition: Mapping[str, Any]) -> bytes:
    sources = sorted(
        {
            (
                item["construction_prior"]["source_url"],
                item["construction_prior"]["source_license"],
            )
            for item in definition["pilots"]
        }
    )
    lines = [
        "Microsoft Global ML Building Footprints",
        f"Publisher: {PUBLISHER}",
        f"Data license: {DATA_LICENSE}",
        f"Official index: {definition['upstream']['index']['url']}",
        f"Repository commit: {definition['upstream']['repository']['commit']}",
        "",
        "Construction-prior source records (context only; no footprint match):",
    ]
    lines.extend(f"- {url} ({license_name})" for url, license_name in sources)
    lines.extend(
        [
            "",
            "No Atlas entity, lifecycle status, type, capacity, power, energy, or unique",
            "site is created or corroborated by the building-footprint context.",
        ]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _write_file(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise MicrosoftBuildingFootprintsError(f"refusing existing output file: {path.name}")
    path.write_bytes(raw)


def _artifact(path: Path, *, records: int | None = None) -> dict[str, Any]:
    result = _file_record(path)
    if records is not None:
        result["records"] = records
    return result


def _derive_bundle_files(
    directory: Path,
    definition: Mapping[str, Any],
    definition_raw: bytes,
) -> dict[str, Any]:
    prior_raw = (directory / PRIORS_FILENAME).read_bytes()
    prior_records = _validate_prior_bytes(prior_raw, definition)
    inventory_rows, location_rows, inventory_summary = inventory_index(
        directory / INDEX_FILENAME, _definition=definition
    )
    expected_index = definition["upstream"]["index"]
    for key, expected_key in (
        ("index_rows", "expected_rows"),
        ("unique_location_quadkeys", "expected_unique_location_quadkeys"),
        ("unique_urls", "expected_unique_urls"),
        ("locations", "expected_locations"),
        (
            "advertised_compressed_bytes_binary_approx",
            "advertised_compressed_bytes_binary_approx",
        ),
    ):
        if inventory_summary[key] != expected_index[expected_key]:
            raise MicrosoftBuildingFootprintsError(f"inventory {key} changed")
    selected_pairs = {
        (pilot["location"], pilot["quadkey"]): pilot for pilot in definition["pilots"]
    }
    selected_inventory = {
        (row["location"], row["quadkey"]): row
        for row in inventory_rows
        if row["selected_for_pilot"] is not None
    }
    if set(selected_inventory) != set(selected_pairs):
        raise MicrosoftBuildingFootprintsError("selected index rows changed")
    for pair, pilot in selected_pairs.items():
        row = selected_inventory[pair]
        if (
            row["url"] != pilot["shard_url"]
            or row["advertised_size"] != pilot["advertised_size"]
            or row["upload_date"] != pilot["upload_date"]
        ):
            raise MicrosoftBuildingFootprintsError("selected index shard pin changed")

    _write_file(directory / INVENTORY_FILENAME, _jsonl(inventory_rows))
    _write_file(directory / LOCATION_INVENTORY_FILENAME, _jsonl(location_rows))
    _write_file(
        directory / INVENTORY_SUMMARY_FILENAME,
        _canonical_json(inventory_summary, pretty=True),
    )
    upstream_metadata = _upstream_metadata(definition)
    _write_file(
        directory / UPSTREAM_METADATA_FILENAME,
        _canonical_json(upstream_metadata, pretty=True),
    )

    review_features: list[dict[str, Any]] = []
    pilot_coverage: list[dict[str, Any]] = []
    for pilot in sorted(definition["pilots"], key=lambda item: item["pilot_id"]):
        features, coverage = _scan_shard(directory / pilot["shard_filename"], pilot)
        review_features.extend(features)
        pilot_coverage.append(coverage)
    review_features.sort(
        key=lambda feature: (
            feature["properties"]["pilot_id"],
            feature["properties"]["source"]["decompressed_line_number"],
            feature["id"],
        )
    )
    _write_file(directory / REVIEW_FILENAME, _jsonl(review_features))
    _write_file(directory / REVIEW_CSV_FILENAME, _review_csv(review_features))
    coverage = _coverage_document(inventory_summary, pilot_coverage)
    _write_file(directory / COVERAGE_FILENAME, _canonical_json(coverage, pretty=True))
    _write_file(directory / README_FILENAME, _readme(definition, coverage))
    _write_file(directory / ATTRIBUTION_FILENAME, _attribution(definition))

    record_counts = {
        INDEX_FILENAME: inventory_summary["index_rows"],
        INVENTORY_FILENAME: len(inventory_rows),
        LOCATION_INVENTORY_FILENAME: len(location_rows),
        PRIORS_FILENAME: len(prior_records),
        REVIEW_FILENAME: len(review_features),
        REVIEW_CSV_FILENAME: len(review_features),
    }
    output_names = _expected_files(definition) - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    outputs = {
        name: _artifact(directory / name, records=record_counts.get(name))
        for name in sorted(output_names)
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "bundle_id": definition["bundle_id"],
        "generated_at": definition["generated_at"],
        "definition": {
            "bytes": len(definition_raw),
            "sha256": _sha256_bytes(definition_raw),
        },
        "inventory": inventory_summary,
        "outputs": outputs,
        "review_policy": dict(REVIEW_POLICY),
        "source_checkpoints": {
            "construction_master": definition["construction_master"],
            "index": definition["upstream"]["index"],
            "repository": definition["upstream"]["repository"],
            "shards": [
                {
                    "bytes": pilot["shard_bytes"],
                    "filename": pilot["shard_filename"],
                    "location": pilot["location"],
                    "quadkey": pilot["quadkey"],
                    "sha256": pilot["shard_sha256"],
                    "url": pilot["shard_url"],
                }
                for pilot in sorted(definition["pilots"], key=lambda item: item["pilot_id"])
            ],
        },
        "totals": coverage["totals"],
        "upstream_metadata": upstream_metadata,
    }
    manifest_raw = _canonical_json(manifest, pretty=True)
    _write_file(directory / MANIFEST_FILENAME, manifest_raw)
    _write_file(
        directory / MANIFEST_HASH_FILENAME,
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    return manifest


def _expected_files(definition: Mapping[str, Any]) -> set[str]:
    return BASE_FILES | {pilot["shard_filename"] for pilot in definition["pilots"]}


def _validate_static(
    directory: Path,
    definition: Mapping[str, Any],
    definition_raw: bytes,
    *,
    require_frozen: bool,
) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise MicrosoftBuildingFootprintsError("bundle must be a regular directory")
    entries = list(directory.iterdir())
    expected_files = _expected_files(definition)
    if {entry.name for entry in entries} != expected_files or len(entries) != len(
        expected_files
    ):
        raise MicrosoftBuildingFootprintsError("bundle closed file set changed")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise MicrosoftBuildingFootprintsError("bundle contains a non-regular file")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != 0o555:
            raise MicrosoftBuildingFootprintsError("bundle directory is not frozen 0555")
        if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries):
            raise MicrosoftBuildingFootprintsError("bundle files are not frozen 0444")

    manifest_raw = (directory / MANIFEST_FILENAME).read_bytes()
    expected_sidecar = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise MicrosoftBuildingFootprintsError("manifest sidecar changed")
    try:
        manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MicrosoftBuildingFootprintsError("manifest is not valid JSON") from error
    if manifest_raw != _canonical_json(manifest, pretty=True):
        raise MicrosoftBuildingFootprintsError("manifest is not canonical JSON")
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "format",
        "bundle_id",
        "generated_at",
        "definition",
        "inventory",
        "outputs",
        "review_policy",
        "source_checkpoints",
        "totals",
        "upstream_metadata",
    }:
        raise MicrosoftBuildingFootprintsError("manifest fields changed")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("bundle_id") != definition["bundle_id"]
        or manifest.get("generated_at") != definition["generated_at"]
        or manifest.get("review_policy") != REVIEW_POLICY
    ):
        raise MicrosoftBuildingFootprintsError("manifest identity or safeguards changed")
    if manifest.get("definition") != {
        "bytes": len(definition_raw),
        "sha256": _sha256_bytes(definition_raw),
    }:
        raise MicrosoftBuildingFootprintsError("manifest definition checkpoint changed")
    expected_outputs = expected_files - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != expected_outputs:
        raise MicrosoftBuildingFootprintsError("manifest output inventory changed")
    for name in expected_outputs:
        expected = manifest["outputs"][name]
        actual = _file_record(directory / name)
        if actual != {"bytes": expected.get("bytes"), "sha256": expected.get("sha256")}:
            raise MicrosoftBuildingFootprintsError(f"bundle output changed: {name}")
    _verify_checkpoint(directory / INDEX_FILENAME, definition["upstream"]["index"], "index")
    _verify_checkpoint(
        directory / LICENSE_FILENAME,
        definition["upstream"]["repository"]["license_file"],
        "upstream license file",
    )
    for pilot in definition["pilots"]:
        _verify_checkpoint(
            directory / pilot["shard_filename"],
            {
                "bytes": pilot["shard_bytes"],
                "sha256": pilot["shard_sha256"],
                "content_md5_base64": pilot["content_md5_base64"],
            },
            f"shard {pilot['pilot_id']}",
        )
    _validate_prior_bytes((directory / PRIORS_FILENAME).read_bytes(), definition)
    return manifest


def _copy_reproduction_inputs(
    source: Path, destination: Path, definition: Mapping[str, Any]
) -> None:
    names = RAW_REPRODUCTION_FILES | {
        pilot["shard_filename"] for pilot in definition["pilots"]
    }
    for name in sorted(names):
        shutil.copyfile(source / name, destination / name)


def validate_bundle(
    directory: str | Path,
    *,
    definition_path: str | Path,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate and reproduce every bundle byte without network access."""

    definition, definition_raw = _load_definition(definition_path)
    root = Path(directory)
    manifest = _validate_static(
        root, definition, definition_raw, require_frozen=require_frozen
    )
    with tempfile.TemporaryDirectory(prefix="microsoft-buildings-reproduce-") as temporary:
        reproduced = Path(temporary) / "bundle"
        reproduced.mkdir()
        _copy_reproduction_inputs(root, reproduced, definition)
        _derive_bundle_files(reproduced, definition, definition_raw)
        for name in sorted(_expected_files(definition)):
            if _file_record(root / name) != _file_record(reproduced / name):
                raise MicrosoftBuildingFootprintsError(
                    f"bundle differs from offline reproduction: {name}"
                )
    return manifest


def _freeze(directory: Path) -> None:
    for entry in directory.iterdir():
        entry.chmod(0o444)
    directory.chmod(0o555)


def _unfreeze_for_cleanup(directory: Path) -> None:
    if not directory.exists() or directory.is_symlink():
        return
    directory.chmod(0o755)
    for entry in directory.iterdir():
        if not entry.is_symlink():
            entry.chmod(0o644)


def fetch_and_build_bundle(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    construction_master_path: str | Path | None = None,
    downloader: Any | None = None,
) -> dict[str, Any]:
    """Fetch exact pinned assets, derive the bounded lane, validate, and freeze it."""

    definition_file = Path(definition_path)
    definition, definition_raw = _load_definition(definition_file)
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise MicrosoftBuildingFootprintsError(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    master = (
        Path(construction_master_path)
        if construction_master_path is not None
        else Path(__file__).resolve().parents[1] / definition["construction_master"]["path"]
    )
    client = downloader or PinnedHTTPDownloader()
    if not callable(getattr(client, "download", None)):
        raise MicrosoftBuildingFootprintsError("downloader must provide download()")
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        upstream = definition["upstream"]
        index = upstream["index"]
        observed = client.download(
            index["url"], stage / INDEX_FILENAME, index["bytes"]
        )
        _verify_observed_http_metadata(observed, index, "dataset index")
        _verify_checkpoint(stage / INDEX_FILENAME, index, "downloaded index")
        inventory_index(stage / INDEX_FILENAME, definition_path=definition_file)

        repository = upstream["repository"]
        client.download(
            repository["license_url"],
            stage / LICENSE_FILENAME,
            repository["license_file"]["bytes"],
        )
        _verify_checkpoint(
            stage / LICENSE_FILENAME,
            repository["license_file"],
            "downloaded upstream license",
        )
        readme_temporary = stage / ".upstream-readme.tmp"
        client.download(
            repository["readme_url"],
            readme_temporary,
            repository["readme_file"]["bytes"],
        )
        _verify_checkpoint(
            readme_temporary,
            repository["readme_file"],
            "downloaded upstream README",
        )
        readme_temporary.unlink()

        for pilot in sorted(definition["pilots"], key=lambda item: item["pilot_id"]):
            observed = client.download(
                pilot["shard_url"],
                stage / pilot["shard_filename"],
                pilot["shard_bytes"],
            )
            _verify_observed_http_metadata(observed, pilot, pilot["pilot_id"])
            _verify_checkpoint(
                stage / pilot["shard_filename"],
                {
                    "bytes": pilot["shard_bytes"],
                    "sha256": pilot["shard_sha256"],
                    "content_md5_base64": pilot["content_md5_base64"],
                },
                f"downloaded shard {pilot['pilot_id']}",
            )

        prior_records = _extract_construction_priors(definition, master)
        _write_file(stage / PRIORS_FILENAME, _jsonl(prior_records))
        manifest = _derive_bundle_files(stage, definition, definition_raw)
        _validate_static(
            stage, definition, definition_raw, require_frozen=False
        )
        _freeze(stage)
        validate_bundle(stage, definition_path=definition_file, require_frozen=True)
        stage.replace(destination)
        return manifest
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            _unfreeze_for_cleanup(stage)
            shutil.rmtree(stage)
        raise


__all__ = [
    "BUNDLE_FORMAT",
    "MicrosoftBuildingFootprintsError",
    "PinnedHTTPDownloader",
    "REVIEW_POLICY",
    "fetch_and_build_bundle",
    "inventory_index",
    "validate_bundle",
]
