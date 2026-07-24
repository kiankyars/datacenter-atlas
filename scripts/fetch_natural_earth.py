#!/usr/bin/env python3
"""Fetch or checkpoint the pinned Natural Earth country-boundary artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.natural_earth import (
    NATURAL_EARTH_USER_AGENT,
    NaturalEarthFetcher,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--fetched-at", help="Override the UTC checkpoint timestamp")
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument("--user-agent", default=NATURAL_EARTH_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = NaturalEarthFetcher(
        user_agent=arguments.user_agent,
        timeout=arguments.timeout,
    ).fetch(arguments.output, fetched_at=arguments.fetched_at)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
