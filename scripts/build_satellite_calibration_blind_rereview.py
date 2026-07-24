#!/usr/bin/env python3
"""Build or validate the closed algorithm-v2 identity-blind rereview audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datacenter_atlas.satellite_calibration_blind_rereview import (  # noqa: E402
    SatelliteCalibrationBlindRereviewError,
    validate_satellite_calibration_blind_rereview,
    write_satellite_calibration_blind_rereview,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.validate_only:
            result = validate_satellite_calibration_blind_rereview(arguments.output_dir, definition_path=arguments.definition)
        else:
            result = write_satellite_calibration_blind_rereview(arguments.output_dir, definition_path=arguments.definition)
    except SatelliteCalibrationBlindRereviewError as error:
        print(f"satellite-calibration-blind-rereview error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

