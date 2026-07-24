#!/usr/bin/env python3
"""Build or validate the immutable Sentinel analyst-review calibration audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.satellite_calibration import (  # noqa: E402
    SatelliteCalibrationError,
    validate_satellite_calibration,
    write_satellite_calibration,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and fully reproduce an existing output offline",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.validate_only:
            manifest = validate_satellite_calibration(
                arguments.output, definition_path=arguments.definition
            )
        else:
            manifest = write_satellite_calibration(
                arguments.definition, arguments.output, freeze=True
            )
    except SatelliteCalibrationError as error:
        print(f"satellite-calibration error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "calibration_id": manifest["calibration_id"],
                "format": manifest["format"],
                "output": str(arguments.output),
                "records": manifest["counts"]["count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
