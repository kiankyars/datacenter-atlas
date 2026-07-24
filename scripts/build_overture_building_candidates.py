#!/usr/bin/env python3
"""Build an atomic review-only bundle from one pinned Overture building fetch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.overture import write_overture_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = (
    PROJECT_ROOT / "releases" / "2026-07-18-global-open-v3" / "atlas.geojson"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path)
    result.add_argument(
        "--fetch-state",
        type=Path,
        help="CLI state sidecar (default: <input>.state)",
    )
    result.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    result.add_argument(
        "--atlas-manifest",
        type=Path,
        help="release manifest (default: manifest.json beside --atlas)",
    )
    result.add_argument("--output", required=True, type=Path)
    result.add_argument(
        "--generated-at",
        required=True,
        help="explicit timezone-aware bundle generation timestamp",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    state = arguments.fetch_state or Path(f"{arguments.input}.state")
    manifest = write_overture_bundle(
        arguments.input,
        state,
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
                "scope": manifest["scope"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
