#!/usr/bin/env python3
"""Fetch Taginfo occupied-cell signals for targeted ohsome extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.ohsome import DEFAULT_USER_AGENT
from datacenter_atlas.taginfo_targets import TaginfoTargetFetcher


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Fetch Taginfo tag-distribution signals and produce sparse bbox targets "
            "for ohsome. Outputs are targeting signals, not facility geometry or counts."
        )
    )
    argument_parser.add_argument("--output", required=True, type=Path)
    argument_parser.add_argument("--cell-degrees", type=int, default=5)
    argument_parser.add_argument("--request-interval", type=float, default=0.25)
    argument_parser.add_argument("--request-timeout", type=float, default=60.0)
    argument_parser.add_argument("--max-response-bytes", type=int, default=5_000_000)
    argument_parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return argument_parser


def main() -> int:
    arguments = parser().parse_args()
    manifest = TaginfoTargetFetcher(
        user_agent=arguments.user_agent,
        request_interval=arguments.request_interval,
        request_timeout=arguments.request_timeout,
        max_response_bytes=arguments.max_response_bytes,
    ).fetch(arguments.output, cell_degrees=arguments.cell_degrees)
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

