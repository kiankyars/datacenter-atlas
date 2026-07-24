#!/usr/bin/env python3
"""Validate the frozen blind-tile frame preflight without network I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.blind_tile_frame import (
    RELEASE_ID,
    is_frozen_release,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--definition",
        type=Path,
        default=PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json",
    )
    parser.add_argument(
        "--release",
        type=Path,
        default=PROJECT_ROOT / "blind_tile_frames" / RELEASE_ID,
    )
    arguments = parser.parse_args(argv)
    result = validate_release_bundle(
        arguments.release, definition_path=arguments.definition
    )
    print(
        json.dumps(
            {
                "fixture_only": True,
                "frame_cell_count": result["frame_cell_count"],
                "frozen": is_frozen_release(arguments.release),
                "http_requests": 0,
                "manifest_sha256": result["manifest_sha256"],
                "mode": "offline_synthetic_preflight_validate",
                "production_frame_built": False,
                "release_id": RELEASE_ID,
                "sample_cell_count": result["sample_cell_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
