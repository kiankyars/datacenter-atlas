"""Build sparse ohsome query targets from Taginfo distribution signals.

Taginfo's distribution images indicate only whether a tag occurs in a one-degree
cell.  They are a query-planning signal, not facility geometry or a facility
count.  Raw API responses are retained byte-for-byte for reproducibility.
"""

from __future__ import annotations

import binascii
import hashlib
import json
import struct
import time
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .ohsome import DATA_CENTER_FILTER, DEFAULT_USER_AGENT


TAGINFO_BASE_URL = "https://taginfo.openstreetmap.org/api/4"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "Open Database License (ODbL) 1.0"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
TARGETING_SIGNAL = (
    "Taginfo occupied-cell targeting signal; not facility geometry or a "
    "facility count"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def explicit_tag_pairs(tag_filter: str = DATA_CENTER_FILTER) -> tuple[tuple[str, str], ...]:
    """Parse the equality terms in the exact ohsome data-centre filter."""
    if not isinstance(tag_filter, str):
        raise TypeError("tag_filter must be a string")
    expression = tag_filter.strip()
    if not (expression.startswith("(") and expression.endswith(")")):
        raise ValueError("tag filter must be a parenthesized OR of equality terms")
    terms = expression[1:-1].split(" or ")
    if not terms or any(not term for term in terms):
        raise ValueError("tag filter has no equality terms")

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for term in terms:
        if term.count("=") != 1:
            raise ValueError(f"unsupported tag-filter term: {term!r}")
        key, value = term.split("=", 1)
        if not key or not value or any(char.isspace() for char in key + value):
            raise ValueError(f"invalid tag-filter equality term: {term!r}")
        pair = (key, value)
        if pair in seen:
            raise ValueError(f"duplicate tag-filter equality term: {term!r}")
        seen.add(pair)
        pairs.append(pair)
    return tuple(pairs)


def taginfo_url(endpoint: str, key: str, value: str) -> str:
    if endpoint not in {"tag/stats", "tag/distribution/nodes", "tag/distribution/ways"}:
        raise ValueError(f"unsupported Taginfo endpoint: {endpoint}")
    if not key or not value:
        raise ValueError("Taginfo key and value must be non-empty")
    query = urllib.parse.urlencode((("key", key), ("value", value)))
    return f"{TAGINFO_BASE_URL}/{endpoint}?{query}"


def decode_distribution_png(payload: bytes) -> set[tuple[int, int]]:
    """Decode a Taginfo 1-bit distribution PNG into occupied ``(x, y)`` pixels."""
    if not isinstance(payload, bytes) or not payload.startswith(PNG_SIGNATURE):
        raise ValueError("Taginfo distribution response is not a PNG")

    position = len(PNG_SIGNATURE)
    ihdr: tuple[int, int, int, int, int, int, int] | None = None
    idat_parts: list[bytes] = []
    palette: bytes | None = None
    transparency: bytes | None = None
    saw_iend = False
    while position < len(payload):
        if position + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", payload[position : position + 4])[0]
        chunk_type = payload[position + 4 : position + 8]
        data_start = position + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ValueError("truncated PNG chunk data")
        data = payload[data_start:data_end]
        declared_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
        if declared_crc != actual_crc:
            raise ValueError(f"PNG {chunk_type.decode('ascii', 'replace')} CRC mismatch")
        position = crc_end

        if chunk_type == b"IHDR":
            if ihdr is not None or length != 13:
                raise ValueError("invalid PNG IHDR")
            ihdr = struct.unpack(">IIBBBBB", data)
        elif chunk_type == b"IDAT":
            if ihdr is None or saw_iend:
                raise ValueError("invalid PNG IDAT placement")
            idat_parts.append(data)
        elif chunk_type == b"PLTE":
            if palette is not None or saw_iend:
                raise ValueError("invalid PNG palette placement")
            palette = data
        elif chunk_type == b"tRNS":
            if transparency is not None or saw_iend:
                raise ValueError("invalid PNG transparency placement")
            transparency = data
        elif chunk_type == b"IEND":
            if length != 0 or saw_iend:
                raise ValueError("invalid PNG IEND")
            saw_iend = True
            break

    if ihdr is None or not saw_iend or position != len(payload):
        raise ValueError("incomplete PNG")
    width, height, bit_depth, color_type, compression, filter_method, interlace = ihdr
    if (width, height) != (360, 180):
        raise ValueError(f"Taginfo distribution PNG must be 360x180, got {width}x{height}")
    if (bit_depth, color_type, compression, filter_method, interlace) != (1, 3, 0, 0, 0):
        raise ValueError("unsupported Taginfo PNG encoding")
    if palette is None or len(palette) != 6:
        raise ValueError("Taginfo distribution PNG must have a two-entry palette")
    if transparency is None or not transparency or transparency[0] != 0:
        raise ValueError("Taginfo distribution PNG background must be transparent")
    occupied_alpha = transparency[1] if len(transparency) > 1 else 255
    if occupied_alpha == 0:
        raise ValueError("Taginfo distribution PNG occupied pixels must be visible")
    if not idat_parts:
        raise ValueError("PNG has no image data")

    row_bytes = (width + 7) // 8
    expected_size = height * (row_bytes + 1)
    try:
        raw = zlib.decompress(b"".join(idat_parts))
    except zlib.error as error:
        raise ValueError(f"invalid PNG compressed data: {error}") from error
    if len(raw) != expected_size:
        raise ValueError(
            f"PNG scanline data has {len(raw)} bytes; expected {expected_size}"
        )

    occupied: set[tuple[int, int]] = set()
    previous = bytearray(row_bytes)
    offset = 0
    for y in range(height):
        filter_type = raw[offset]
        packed = bytearray(raw[offset + 1 : offset + 1 + row_bytes])
        offset += row_bytes + 1
        _unfilter_scanline(packed, previous, filter_type)
        for x in range(width):
            if packed[x // 8] & (1 << (7 - (x % 8))):
                occupied.add((x, y))
        previous = packed
    return occupied


def _unfilter_scanline(row: bytearray, previous: bytearray, filter_type: int) -> None:
    if filter_type == 0:
        return
    if filter_type not in {1, 2, 3, 4}:
        raise ValueError(f"unsupported PNG filter type: {filter_type}")
    for index in range(len(row)):
        left = row[index - 1] if index else 0
        above = previous[index]
        upper_left = previous[index - 1] if index else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        else:
            predictor = _paeth(left, above, upper_left)
        row[index] = (row[index] + predictor) & 0xFF


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def pixel_bbox(x: int, y: int) -> tuple[int, int, int, int]:
    """Return the WGS84 one-degree cell for a Taginfo distribution pixel."""
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
        raise TypeError("pixel coordinates must be integers")
    if not 0 <= x < 360 or not 0 <= y < 180:
        raise ValueError("pixel coordinates are outside the 360x180 Taginfo grid")
    west = -180 + x
    north = 90 - y
    return west, north - 1, west + 1, north


def aggregate_targets(
    occupied_by_signal: dict[tuple[str, str, str], set[tuple[int, int]]],
    cell_degrees: int,
) -> list[dict[str, Any]]:
    """Union occupied pixels and aggregate them to aligned coarse query cells."""
    if isinstance(cell_degrees, bool) or not isinstance(cell_degrees, int):
        raise TypeError("cell_degrees must be an integer")
    if cell_degrees < 1 or 180 % cell_degrees or 360 % cell_degrees:
        raise ValueError("cell_degrees must be a positive common divisor of 180 and 360")

    coarse: dict[tuple[int, int], dict[str, Any]] = {}
    for signal, pixels in sorted(occupied_by_signal.items()):
        if len(signal) != 3:
            raise ValueError("signal keys must be (key, value, element_type)")
        key, value, element_type = signal
        if element_type not in {"nodes", "ways"}:
            raise ValueError(f"unsupported distribution element type: {element_type}")
        for x, y in sorted(pixels):
            west, south, _, _ = pixel_bbox(x, y)
            coarse_west = -180 + ((west + 180) // cell_degrees) * cell_degrees
            coarse_south = -90 + ((south + 90) // cell_degrees) * cell_degrees
            target = coarse.setdefault(
                (coarse_west, coarse_south),
                {"pixels": set(), "signals": set()},
            )
            target["pixels"].add((x, y))
            target["signals"].add((key, value, element_type))

    results: list[dict[str, Any]] = []
    for index, ((west, south), target) in enumerate(sorted(coarse.items(), key=lambda item: (item[0][1], item[0][0]))):
        signals = [
            {"key": key, "value": value, "element_type": element_type}
            for key, value, element_type in sorted(target["signals"])
        ]
        results.append(
            {
                "id": f"t{index:05d}",
                "bbox": [west, south, west + cell_degrees, south + cell_degrees],
                "west": west,
                "south": south,
                "east": west + cell_degrees,
                "north": south + cell_degrees,
                "ohsome_bbox": (
                    f"t{index:05d}:{west},{south},"
                    f"{west + cell_degrees},{south + cell_degrees}"
                ),
                "targeting_signal": TARGETING_SIGNAL,
                "occupied_1deg_signal_cells": len(target["pixels"]),
                "tag_signals": signals,
            }
        )
    return results


def parse_stats(payload: bytes, expected_url: str) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Taginfo stats response is invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("Taginfo stats response must be a JSON object")
    if document.get("url") != expected_url:
        raise ValueError("Taginfo stats response URL does not match the request URL")
    data_until = document.get("data_until")
    if not isinstance(data_until, str) or not data_until.strip():
        raise ValueError("Taginfo stats response has no data_until timestamp")
    rows = document.get("data")
    if not isinstance(rows, list):
        raise ValueError("Taginfo stats response data must be a list")
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Taginfo stats response contains a non-object row")
        element_type = row.get("type")
        count = row.get("count")
        if element_type not in {"all", "nodes", "ways", "relations"}:
            raise ValueError(f"unknown Taginfo stats type: {element_type!r}")
        if element_type in counts:
            raise ValueError(f"duplicate Taginfo stats type: {element_type}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"invalid Taginfo count for {element_type}")
        counts[element_type] = count
    if set(counts) != {"all", "nodes", "ways", "relations"}:
        raise ValueError("Taginfo stats response must include all/nodes/ways/relations")
    if counts["all"] != counts["nodes"] + counts["ways"] + counts["relations"]:
        raise ValueError("Taginfo all count does not equal nodes + ways + relations")
    return {"data_until": data_until, "counts": counts}


class TaginfoTargetFetcher:
    """Fetch raw Taginfo signals and produce deterministic targeted ohsome bboxes."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        request_interval: float = 0.25,
        request_timeout: float = 60.0,
        max_response_bytes: int = 5_000_000,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if request_interval < 0 or request_timeout <= 0 or max_response_bytes <= 0:
            raise ValueError("invalid request configuration")
        self.user_agent = user_agent
        self.request_interval = request_interval
        self.request_timeout = request_timeout
        self.max_response_bytes = max_response_bytes
        self.opener = opener
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def fetch(self, output_directory: str | Path, *, cell_degrees: int = 5) -> dict[str, Any]:
        if isinstance(cell_degrees, bool) or not isinstance(cell_degrees, int):
            raise TypeError("cell_degrees must be an integer")
        if cell_degrees < 1 or 180 % cell_degrees or 360 % cell_degrees:
            raise ValueError("cell_degrees must be a positive common divisor of 180 and 360")
        output = Path(output_directory)
        raw_directory = output / "raw"
        raw_directory.mkdir(parents=True, exist_ok=True)

        occupied: dict[tuple[str, str, str], set[tuple[int, int]]] = {}
        records: list[dict[str, Any]] = []
        data_until_values: set[str] = set()
        unlocated_relations = 0
        nonzero_stats_empty_distributions = 0
        pairs = explicit_tag_pairs()

        for pair_index, (key, value) in enumerate(pairs):
            prefix = f"{pair_index:03d}-{_safe_name(key)}-{_safe_name(value)}"
            stats_url = taginfo_url("tag/stats", key, value)
            stats_payload = self._get(stats_url)
            stats = parse_stats(stats_payload, stats_url)
            data_until_values.add(stats["data_until"])
            stats_relative = f"raw/{prefix}-stats.json"
            (output / stats_relative).write_bytes(stats_payload)
            record: dict[str, Any] = {
                "key": key,
                "value": value,
                "data_until": stats["data_until"],
                "counts": stats["counts"],
                "stats": _response_record(stats_url, stats_relative, stats_payload),
                "distribution_availability": {
                    "nodes": stats["counts"]["nodes"] > 0,
                    "ways": stats["counts"]["ways"] > 0,
                    "relations_spatially_unavailable": stats["counts"]["relations"] > 0,
                },
                "distributions": [],
            }
            unlocated_relations += stats["counts"]["relations"]

            for element_type in ("nodes", "ways"):
                if stats["counts"][element_type] == 0:
                    continue
                distribution_url = taginfo_url(
                    f"tag/distribution/{element_type}", key, value
                )
                distribution_payload = self._get(distribution_url)
                pixels = decode_distribution_png(distribution_payload)
                if pixels:
                    occupied[(key, value, element_type)] = pixels
                else:
                    nonzero_stats_empty_distributions += 1
                distribution_relative = f"raw/{prefix}-{element_type}.png"
                (output / distribution_relative).write_bytes(distribution_payload)
                record["distributions"].append(
                    {
                        **_response_record(
                            distribution_url,
                            distribution_relative,
                            distribution_payload,
                        ),
                        "element_type": element_type,
                        "occupied_1deg_signal_cells": len(pixels),
                        "stats_nonzero_but_distribution_empty": not pixels,
                        "targeting_signal": TARGETING_SIGNAL,
                    }
                )
            records.append(record)

        bboxes = aggregate_targets(occupied, cell_degrees)
        bbox_document = {
            "schema_version": 1,
            "targeting_signal": TARGETING_SIGNAL,
            "cell_degrees": cell_degrees,
            "bbox_count": len(bboxes),
            "ohsome_bboxes_parameter": "|".join(
                target["ohsome_bbox"] for target in bboxes
            ),
            "bboxes": bboxes,
        }
        bbox_payload = _canonical_json_bytes(bbox_document)
        bbox_path = output / "target_bboxes.json"
        bbox_path.write_bytes(bbox_payload)

        manifest = {
            "schema_version": 1,
            "source": {
                "name": "Taginfo global OpenStreetMap tag statistics and distributions",
                "api_base_url": TAGINFO_BASE_URL,
                "attribution": OSM_ATTRIBUTION,
                "license": OSM_LICENSE,
                "copyright_url": OSM_COPYRIGHT_URL,
            },
            "targeting_signal": TARGETING_SIGNAL,
            "limitations": [
                "Occupied pixels localize tag presence only; they are not facility geometry or counts.",
                "Node and way distributions are unioned; Taginfo provides no relation distribution endpoint here.",
                f"{unlocated_relations} relation tag occurrences are counted but not spatially targeted.",
                (
                    f"{nonzero_stats_empty_distributions} nonzero node/way stats returned a "
                    "valid empty distribution image and therefore added no spatial target."
                ),
            ],
            "ohsome_filter": DATA_CENTER_FILTER,
            "cell_degrees": cell_degrees,
            "data_until": sorted(data_until_values),
            "tag_pair_count": len(pairs),
            "tag_pairs": records,
            "summary": {
                "nonempty_distribution_signals": len(occupied),
                "unique_occupied_1deg_signal_cells": len(
                    set().union(*occupied.values()) if occupied else set()
                ),
                "target_bbox_count": len(bboxes),
                "unlocated_relation_tag_occurrences": unlocated_relations,
                "nonzero_stats_empty_distributions": nonzero_stats_empty_distributions,
            },
            "bbox_file": {
                "path": bbox_path.name,
                "bytes": len(bbox_payload),
                "sha256": hashlib.sha256(bbox_payload).hexdigest(),
            },
        }
        (output / "manifest.json").write_bytes(_canonical_json_bytes(manifest))
        return manifest

    def _get(self, url: str) -> bytes:
        if not url.startswith(f"{TAGINFO_BASE_URL}/"):
            raise ValueError("refusing a non-Taginfo API URL")
        now = self.monotonic()
        if self._last_request_at is not None:
            wait = self.request_interval - (now - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        request = urllib.request.Request(
            url,
            headers={"Accept": "*/*", "User-Agent": self.user_agent},
            method="GET",
        )
        with self.opener(request, timeout=self.request_timeout) as response:
            payload = response.read(self.max_response_bytes + 1)
        self._last_request_at = self.monotonic()
        if len(payload) > self.max_response_bytes:
            raise ValueError(f"Taginfo response exceeds {self.max_response_bytes} bytes")
        return payload


def _response_record(url: str, relative_path: str, payload: bytes) -> dict[str, Any]:
    return {
        "request_url": url,
        "response_file": relative_path,
        "response_bytes": len(payload),
        "response_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _canonical_json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_name(value: str) -> str:
    rendered = "".join(character if character.isalnum() else "-" for character in value)
    rendered = "-".join(part for part in rendered.split("-") if part)
    if not rendered:
        raise ValueError("cannot create a safe filename from an empty tag component")
    return rendered.lower()
