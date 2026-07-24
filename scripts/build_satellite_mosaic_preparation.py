#!/usr/bin/env python3
"""Build or validate the metadata-only Sentinel mosaic-v3 preparation release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datacenter_atlas.satellite_mosaic_preparation import (  # noqa: E402
    SatelliteMosaicPreparationError,
    validate_satellite_mosaic_preparation,
    write_satellite_mosaic_preparation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.validate_only:
            manifest = validate_satellite_mosaic_preparation(
                arguments.output_dir, definition_path=arguments.definition
            )
        else:
            manifest = write_satellite_mosaic_preparation(
                arguments.output_dir, definition_path=arguments.definition
            )
    except SatelliteMosaicPreparationError as error:
        print(f"satellite-mosaic-preparation error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
