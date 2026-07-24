#!/usr/bin/env python3
"""Build a deterministic offline satellite-review queue from release GeoJSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_catalog import Provider
from datacenter_atlas.satellite_queue import QueueConfig, write_queue_bundle


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Release atlas GeoJSON FeatureCollection",
    )
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument(
        "--generated-at",
        required=True,
        help="Explicit timezone-aware generation timestamp for reproducible provenance",
    )
    result.add_argument("--baseline-target", required=True)
    result.add_argument("--current-target", required=True)
    result.add_argument(
        "--provider",
        choices=[item.value for item in Provider],
        default=Provider.EARTH_SEARCH.value,
    )
    result.add_argument("--query-window-days", type=int, default=45)
    result.add_argument("--max-cloud-cover", type=float, default=20.0)
    result.add_argument("--catalog-limit", type=int, default=100)
    result.add_argument("--aoi-half-side-km", type=float, default=2.0)
    result.add_argument(
        "--minimum-component-area-m2", type=float, default=5_000.0
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = QueueConfig(
        baseline_target=arguments.baseline_target,
        current_target=arguments.current_target,
        provider=arguments.provider,
        query_window_days=arguments.query_window_days,
        max_cloud_cover=arguments.max_cloud_cover,
        catalog_limit=arguments.catalog_limit,
        aoi_half_side_km=arguments.aoi_half_side_km,
        minimum_component_area_m2=arguments.minimum_component_area_m2,
    )
    manifest = write_queue_bundle(
        arguments.input,
        arguments.output_dir,
        generated_at=arguments.generated_at,
        config=config,
    )
    print(
        json.dumps(
            {
                "manifest": str((arguments.output_dir / "manifest.json").resolve()),
                "manifest_sha256": str(
                    (arguments.output_dir / "manifest.sha256").resolve()
                ),
                "queue": str(
                    (
                        arguments.output_dir / "satellite-review-queue.jsonl"
                    ).resolve()
                ),
                "counts": manifest["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

