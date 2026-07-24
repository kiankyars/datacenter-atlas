from __future__ import annotations

import binascii
import hashlib
import json
import struct
import tempfile
import unittest
import urllib.parse
import zlib
from pathlib import Path

from datacenter_atlas.ohsome import DATA_CENTER_FILTER
from datacenter_atlas.taginfo_targets import (
    OSM_ATTRIBUTION,
    TARGETING_SIGNAL,
    TaginfoTargetFetcher,
    aggregate_targets,
    decode_distribution_png,
    explicit_tag_pairs,
    pixel_bbox,
    taginfo_url,
)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def distribution_png(pixels: set[tuple[int, int]], filters: list[int] | None = None) -> bytes:
    width, height = 360, 180
    rows: list[bytes] = []
    previous = bytes(45)
    for y in range(height):
        raw = bytearray(45)
        for x, pixel_y in pixels:
            if pixel_y == y:
                raw[x // 8] |= 1 << (7 - x % 8)
        filter_type = filters[y] if filters else 0
        encoded = bytearray(raw)
        if filter_type:
            for index in range(len(raw) - 1, -1, -1):
                left = raw[index - 1] if index else 0
                above = previous[index]
                upper_left = previous[index - 1] if index else 0
                if filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = above
                elif filter_type == 3:
                    predictor = (left + above) // 2
                elif filter_type == 4:
                    estimate = left + above - upper_left
                    distances = (
                        abs(estimate - left),
                        abs(estimate - above),
                        abs(estimate - upper_left),
                    )
                    predictor = (left, above, upper_left)[distances.index(min(distances))]
                else:
                    raise AssertionError("unsupported test filter")
                encoded[index] = (raw[index] - predictor) & 0xFF
        rows.append(bytes((filter_type,)) + encoded)
        previous = bytes(raw)
    ihdr = struct.pack(">IIBBBBB", width, height, 1, 3, 0, 0, 0)
    palette = b"\x00\x00\x00\xb4\x00\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"PLTE", palette)
        + png_chunk(b"tRNS", b"\x00")
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + png_chunk(b"IEND", b"")
    )


def stats_payload(url: str, *, nodes: int = 0, ways: int = 0, relations: int = 0) -> bytes:
    return json.dumps(
        {
            "url": url,
            "data_until": "2026-07-17T00:59:29Z",
            "total": 4,
            "data": [
                {"type": "all", "count": nodes + ways + relations, "count_fraction": 0.0},
                {"type": "nodes", "count": nodes, "count_fraction": 0.0},
                {"type": "ways", "count": ways, "count_fraction": 0.0},
                {"type": "relations", "count": relations, "count_fraction": 0.0},
            ],
        },
        separators=(",", ":"),
    ).encode()


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.payload if limit < 0 else self.payload[:limit]


class DistributionPngTests(unittest.TestCase):
    def test_known_pixels_and_global_orientation(self) -> None:
        pixels = {(0, 0), (359, 0), (180, 90), (0, 179), (359, 179)}
        self.assertEqual(decode_distribution_png(distribution_png(pixels)), pixels)
        self.assertEqual(pixel_bbox(0, 0), (-180, 89, -179, 90))
        self.assertEqual(pixel_bbox(359, 0), (179, 89, 180, 90))
        self.assertEqual(pixel_bbox(0, 179), (-180, -90, -179, -89))
        self.assertEqual(pixel_bbox(359, 179), (179, -90, 180, -89))

    def test_empty_map(self) -> None:
        self.assertEqual(decode_distribution_png(distribution_png(set())), set())

    def test_all_png_filters_are_decoded(self) -> None:
        filters = [row % 5 for row in range(180)]
        pixels = {(0, 0), (8, 1), (179, 89), (180, 90), (359, 179)}
        self.assertEqual(decode_distribution_png(distribution_png(pixels, filters)), pixels)

    def test_bad_crc_is_rejected(self) -> None:
        payload = bytearray(distribution_png({(1, 1)}))
        payload[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            decode_distribution_png(bytes(payload))


class TargetPlanningTests(unittest.TestCase):
    def test_filter_pairs_are_exact_and_deterministic(self) -> None:
        pairs = explicit_tag_pairs()
        self.assertEqual(len(pairs), 92)
        self.assertEqual(pairs[0], ("telecom", "data_center"))
        self.assertEqual(pairs[-1], ("proposed:industrial", "datacentre"))
        self.assertEqual(DATA_CENTER_FILTER.count(" or ") + 1, len(pairs))

    def test_aggregate_unions_signals_and_handles_edges(self) -> None:
        targets = aggregate_targets(
            {
                ("telecom", "data_center", "nodes"): {(0, 0), (1, 1), (359, 179)},
                ("building", "data_centre", "ways"): {(0, 0), (180, 90)},
            },
            5,
        )
        by_bbox = {tuple(target["bbox"]): target for target in targets}
        self.assertIn((-180, 85, -175, 90), by_bbox)
        self.assertIn((175, -90, 180, -85), by_bbox)
        self.assertIn((0, -5, 5, 0), by_bbox)
        northwest = by_bbox[(-180, 85, -175, 90)]
        self.assertEqual(northwest["occupied_1deg_signal_cells"], 2)
        self.assertEqual(len(northwest["tag_signals"]), 2)
        self.assertEqual(northwest["west"], -180)
        self.assertEqual(northwest["north"], 90)
        self.assertEqual(northwest["ohsome_bbox"], "t00002:-180,85,-175,90")
        self.assertEqual(northwest["targeting_signal"], TARGETING_SIGNAL)
        self.assertEqual(
            sum(target["occupied_1deg_signal_cells"] for target in targets),
            4,
        )

    def test_invalid_coarsening_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            aggregate_targets({}, 7)


class FetchTests(unittest.TestCase):
    def test_fetch_preserves_bytes_hashes_urls_and_is_deterministic(self) -> None:
        first_pair = explicit_tag_pairs()[0]
        node_png = distribution_png({(0, 0), (359, 179)})
        way_png = distribution_png({(180, 90)})
        requests: list[str] = []

        def opener(request, *, timeout):
            self.assertEqual(timeout, 60.0)
            self.assertIn("DataCenterAtlas", request.get_header("User-agent"))
            requests.append(request.full_url)
            parsed = urllib.parse.urlparse(request.full_url)
            query = urllib.parse.parse_qs(parsed.query)
            pair = (query["key"][0], query["value"][0])
            if parsed.path.endswith("/stats"):
                nodes = 3 if pair == first_pair else 0
                ways = 2 if pair == first_pair else 0
                relations = 1 if pair == first_pair else 0
                return FakeResponse(
                    stats_payload(request.full_url, nodes=nodes, ways=ways, relations=relations)
                )
            if parsed.path.endswith("/nodes"):
                return FakeResponse(node_png)
            if parsed.path.endswith("/ways"):
                return FakeResponse(way_png)
            raise AssertionError(request.full_url)

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            fetcher = TaginfoTargetFetcher(
                opener=opener,
                sleeper=lambda _: None,
                request_interval=0,
            )
            first_manifest = fetcher.fetch(first, cell_degrees=5)
            second_manifest = TaginfoTargetFetcher(
                opener=opener,
                sleeper=lambda _: None,
                request_interval=0,
            ).fetch(second, cell_degrees=5)

            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(
                (Path(first) / "manifest.json").read_bytes(),
                (Path(second) / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                (Path(first) / "target_bboxes.json").read_bytes(),
                (Path(second) / "target_bboxes.json").read_bytes(),
            )
            record = first_manifest["tag_pairs"][0]
            saved_stats = (Path(first) / record["stats"]["response_file"]).read_bytes()
            self.assertEqual(hashlib.sha256(saved_stats).hexdigest(), record["stats"]["response_sha256"])
            node_record = record["distributions"][0]
            saved_nodes = (Path(first) / node_record["response_file"]).read_bytes()
            self.assertEqual(saved_nodes, node_png)
            self.assertEqual(
                hashlib.sha256(saved_nodes).hexdigest(),
                node_record["response_sha256"],
            )
            self.assertEqual(record["data_until"], "2026-07-17T00:59:29Z")
            self.assertEqual(first_manifest["source"]["attribution"], OSM_ATTRIBUTION)
            self.assertEqual(first_manifest["summary"]["unique_occupied_1deg_signal_cells"], 3)
            self.assertEqual(first_manifest["summary"]["unlocated_relation_tag_occurrences"], 1)
            self.assertEqual(first_manifest["summary"]["target_bbox_count"], 3)
            self.assertEqual(len(requests), 2 * (92 + 2))
            self.assertEqual(
                record["stats"]["request_url"],
                taginfo_url("tag/stats", *first_pair),
            )

    def test_nonzero_stats_with_empty_distribution_is_retained_as_mismatch(self) -> None:
        first_pair = explicit_tag_pairs()[0]

        def opener(request, *, timeout):
            if urllib.parse.urlparse(request.full_url).path.endswith("/nodes"):
                return FakeResponse(distribution_png(set()))
            parsed = urllib.parse.urlparse(request.full_url)
            query = urllib.parse.parse_qs(parsed.query)
            pair = (query["key"][0], query["value"][0])
            return FakeResponse(
                stats_payload(request.full_url, nodes=1 if pair == first_pair else 0)
            )

        with tempfile.TemporaryDirectory() as directory:
            manifest = TaginfoTargetFetcher(
                opener=opener,
                request_interval=0,
            ).fetch(directory)
            distribution = manifest["tag_pairs"][0]["distributions"][0]
            self.assertEqual(distribution["occupied_1deg_signal_cells"], 0)
            self.assertTrue(distribution["stats_nonzero_but_distribution_empty"])
            self.assertEqual(manifest["summary"]["nonzero_stats_empty_distributions"], 1)
            self.assertEqual(manifest["summary"]["target_bbox_count"], 0)


if __name__ == "__main__":
    unittest.main()
