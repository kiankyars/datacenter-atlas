#!/usr/bin/env python3
"""Build v0.17 or validate any supported Verified Construction Core preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.verified_construction_core_v017 import (  # noqa: E402
    CURRENT_V17_PREVIEW_DIR,
    build_preview,
    validate_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=CURRENT_V17_PREVIEW_DIR,
        help="preview directory (default: current v0.17 artifact path)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an existing v0.1-v0.17 preview without the ignored source corpus",
    )
    arguments = parser.parse_args()
    if arguments.validate_only:
        manifest = validate_preview(arguments.output_dir)
    else:
        manifest = build_preview(arguments.output_dir)
    print(
        json.dumps(
            {
                "preview_id": manifest["preview_id"],
                "release_status": manifest["release_status"],
                "publishable_as_final": manifest["publishable_as_final"],
                "counts": manifest["counts"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
