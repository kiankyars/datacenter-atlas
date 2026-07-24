#!/usr/bin/env python3
"""Extract a review-only annual building-signal change bundle from pinned COGs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_buildings_temporal import write_candidate_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = (
    PROJECT_ROOT / "releases" / "2026-07-18-global-open-v3" / "atlas.geojson"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    result.add_argument(
        "--atlas-manifest",
        type=Path,
        help="release manifest (default: manifest.json beside --atlas)",
    )
    result.add_argument(
        "--generated-at",
        required=True,
        help="explicit timezone-aware candidate-bundle timestamp",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = write_candidate_bundle(
        arguments.input,
        arguments.atlas,
        arguments.output,
        generated_at=arguments.generated_at,
        atlas_manifest_path=arguments.atlas_manifest,
    )
    print(
        json.dumps(
            {
                "manifest": str((arguments.output / "manifest.json").resolve()),
                "counts": manifest["counts"],
                "review_constraints": manifest["review_constraints"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
