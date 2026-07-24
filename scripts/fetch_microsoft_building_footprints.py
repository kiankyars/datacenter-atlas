#!/usr/bin/env python3
"""Fetch, derive, validate, and freeze the pinned Microsoft buildings lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.microsoft_building_footprints import (
    PinnedHTTPDownloader,
    fetch_and_build_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = (
    PROJECT_ROOT
    / "sources"
    / "microsoft-global-ml-building-footprints-2026-07-18-v1.json"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument(
        "--construction-master",
        type=Path,
        help="override the exact construction-master JSONL path",
    )
    result.add_argument("--maximum-requests", type=int, default=8)
    result.add_argument("--minimum-interval-seconds", type=float, default=0.25)
    result.add_argument("--timeout-seconds", type=float, default=90.0)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    downloader = PinnedHTTPDownloader(
        maximum_requests=arguments.maximum_requests,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        timeout_seconds=arguments.timeout_seconds,
    )
    manifest = fetch_and_build_bundle(
        arguments.definition,
        arguments.output,
        construction_master_path=arguments.construction_master,
        downloader=downloader,
    )
    print(
        json.dumps(
            {
                "bundle": str(arguments.output.resolve()),
                "bundle_id": manifest["bundle_id"],
                "inventory": manifest["inventory"],
                "network_requests": downloader.requests_made,
                "totals": manifest["totals"],
                "validated_after_freeze": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
