#!/usr/bin/env python3
"""Build a hash-pinned advisory crosswalk between two atlas releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.cross_release import (  # noqa: E402
    CrossReleaseResolutionError,
    build_cross_release_resolution,
)
from datacenter_atlas.resolution import ResolutionThresholds  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--left-release", required=True, type=Path)
    result.add_argument("--right-release", required=True, type=Path)
    result.add_argument("--left-label", required=True)
    result.add_argument("--right-label", required=True)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--generated-at", required=True)
    result.add_argument("--nearby-max-distance-m", type=float, default=5_000.0)
    result.add_argument("--same-site-max-distance-m", type=float, default=1_500.0)
    result.add_argument("--part-of-max-distance-m", type=float, default=3_000.0)
    result.add_argument("--same-site-min-score", type=float, default=0.62)
    result.add_argument("--part-of-min-score", type=float, default=0.55)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        manifest = build_cross_release_resolution(
            arguments.left_release,
            arguments.right_release,
            arguments.output_dir,
            left_label=arguments.left_label,
            right_label=arguments.right_label,
            generated_at=arguments.generated_at,
            thresholds=ResolutionThresholds(
                nearby_max_distance_m=arguments.nearby_max_distance_m,
                same_site_max_distance_m=arguments.same_site_max_distance_m,
                part_of_max_distance_m=arguments.part_of_max_distance_m,
                same_site_min_score=arguments.same_site_min_score,
                part_of_min_score=arguments.part_of_min_score,
            ),
        )
    except (CrossReleaseResolutionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_directory": str(arguments.output_dir.resolve()),
                "counts": manifest["counts"],
                "left_input": manifest["left_input"],
                "right_input": manifest["right_input"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
