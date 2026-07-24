#!/usr/bin/env python3
"""Fetch resumable ohsome GeoJSON shards for explicit data-centre tags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.ohsome import BoundingBox, DEFAULT_USER_AGENT, OhsomeFetcher


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Fetch serial, resumable data-centre shards from the official ohsome API."
    )
    argument_parser.add_argument("--output", required=True, help="Output directory")
    argument_parser.add_argument("--time", required=True, help="Single ohsome snapshot time")
    argument_parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=(-180.0, -90.0, 180.0, 90.0),
    )
    argument_parser.add_argument("--cell-degrees", type=float, default=20.0)
    argument_parser.add_argument("--minimum-span", type=float, default=0.25)
    argument_parser.add_argument("--max-depth", type=int, default=8)
    argument_parser.add_argument("--max-retries", type=int, default=3)
    argument_parser.add_argument("--request-timeout", type=float, default=120.0)
    argument_parser.add_argument("--request-interval", type=float, default=1.0)
    argument_parser.add_argument("--max-response-bytes", type=int, default=50_000_000)
    argument_parser.add_argument("--max-features", type=int, default=25_000)
    argument_parser.add_argument("--max-requests", type=int)
    argument_parser.add_argument(
        "--target-bboxes",
        help="Taginfo target_bboxes.json; enables sparse, named-bbox requests",
    )
    argument_parser.add_argument(
        "--target-bboxes-sha256",
        help="Optional expected SHA256 of --target-bboxes",
    )
    argument_parser.add_argument(
        "--target-batch-size",
        type=int,
        default=25,
        help="Maximum named bboxes per spatially compact request (default: 25)",
    )
    argument_parser.add_argument(
        "--max-batch-span-degrees",
        type=float,
        default=20.0,
        help="Maximum longitude and latitude envelope of a targeted request (default: 20)",
    )
    argument_parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Explicitly reset failed leaf tasks to pending after validating the saved bundle",
    )
    argument_parser.add_argument(
        "--transient-failure-limit",
        type=int,
        default=3,
        help="Stop after this many consecutive exhausted 429/500/502/503 responses (default: 3)",
    )
    argument_parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return argument_parser


def main() -> int:
    arguments = parser().parse_args()
    fetcher = OhsomeFetcher(
        user_agent=arguments.user_agent,
        request_interval=arguments.request_interval,
        request_timeout=arguments.request_timeout,
        max_retries=arguments.max_retries,
        max_response_bytes=arguments.max_response_bytes,
        max_features=arguments.max_features,
    )
    manifest = fetcher.fetch(
        arguments.output,
        snapshot_time=arguments.time,
        bounds=BoundingBox(*arguments.bbox),
        cell_degrees=arguments.cell_degrees,
        minimum_span=arguments.minimum_span,
        max_depth=arguments.max_depth,
        max_requests=arguments.max_requests,
        target_bboxes=arguments.target_bboxes,
        target_bboxes_sha256=arguments.target_bboxes_sha256,
        target_batch_size=arguments.target_batch_size,
        max_batch_span_degrees=arguments.max_batch_span_degrees,
        retry_failed=arguments.retry_failed,
        transient_failure_limit=arguments.transient_failure_limit,
    )
    print(json.dumps(manifest["summary"], sort_keys=True))
    deliberate_checkpoint = (
        arguments.max_requests is not None
        and manifest.get("last_run", {}).get("stop_reason") == "max_requests_checkpoint"
    )
    if manifest["summary"]["failed"]:
        return 1
    return 1 if manifest["summary"]["pending"] and not deliberate_checkpoint else 0


if __name__ == "__main__":
    raise SystemExit(main())
