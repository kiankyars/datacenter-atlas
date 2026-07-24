#!/usr/bin/env python3
"""Build and validate the blind-tile frame synthetic preflight without network I/O."""

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
    build_preflight_bundle,
    is_frozen_release,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "blind_tile_frames" / RELEASE_ID


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--freeze", action=argparse.BooleanOptionalAction, default=True
    )
    arguments = parser.parse_args(argv)
    result = build_preflight_bundle(
        arguments.output,
        definition_path=arguments.definition,
        freeze=arguments.freeze,
    )
    print(
        json.dumps(
            {
                "fixture_only": True,
                "frame_cell_count": result["frame_cell_count"],
                "frozen": is_frozen_release(arguments.output),
                "http_requests": 0,
                "manifest_sha256": result["manifest_sha256"],
                "mode": "offline_synthetic_preflight_build_and_validate",
                "output": str(arguments.output),
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
