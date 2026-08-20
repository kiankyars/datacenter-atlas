#!/usr/bin/env python3
"""Build or validate the tracked Verified Construction Core v0.1 preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.verified_construction_core import (  # noqa: E402
    PREVIEW_DIR,
    build_preview,
    validate_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PREVIEW_DIR,
        help="new preview directory (default: tracked preview path)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an existing preview without needing the ignored source corpus",
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
