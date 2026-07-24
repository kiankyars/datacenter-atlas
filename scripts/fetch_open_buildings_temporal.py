#!/usr/bin/env python3
"""Fetch a bounded, generation-pinned Open Buildings Temporal source plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_buildings_temporal import (
    AnonymousGCSClient,
    OpenBuildingsTemporalConfig,
    write_source_bundle,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument(
        "--generated-at",
        required=True,
        help="explicit timezone-aware source-bundle timestamp",
    )
    result.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=OpenBuildingsTemporalConfig().bbox,
    )
    result.add_argument("--country-iso3", default="EGY")
    result.add_argument("--s2cell-token", default="15")
    result.add_argument("--projected-crs", default="EPSG:32636")
    result.add_argument("--maximum-requests", type=int, default=32)
    result.add_argument("--minimum-interval-seconds", type=float, default=0.25)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = OpenBuildingsTemporalConfig(
        bbox=tuple(arguments.bbox),
        country_iso3=arguments.country_iso3,
        s2cell_token=arguments.s2cell_token,
        projected_crs=arguments.projected_crs,
    )
    client = AnonymousGCSClient(
        maximum_requests=arguments.maximum_requests,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
    )
    manifest = write_source_bundle(
        arguments.output,
        generated_at=arguments.generated_at,
        config=config,
        client=client,
    )
    print(
        json.dumps(
            {
                "manifest": str((arguments.output / "manifest.json").resolve()),
                "years": manifest["query"]["years"],
                "selected_tiles": len(manifest["selected_tiles"]),
                "requests_made": client.requests_made,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
