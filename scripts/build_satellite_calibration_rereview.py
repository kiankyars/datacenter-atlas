#!/usr/bin/env python3
"""Build or validate a fail-closed algorithm-v2 re-review preparation bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.satellite_calibration_rereview import (  # noqa: E402
    SatelliteCalibrationRereviewError,
    validate_satellite_calibration_rereview,
    write_satellite_calibration_rereview,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.validate_only:
            manifest = validate_satellite_calibration_rereview(
                arguments.output, definition_path=arguments.definition
            )
        else:
            manifest = write_satellite_calibration_rereview(
                arguments.definition, arguments.output
            )
    except SatelliteCalibrationRereviewError as error:
        print(f"satellite-calibration-rereview error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "algorithm_v2_outputs": manifest["counts"]["algorithm_v2_outputs_available"],
                "historical_items": manifest["counts"]["historical_items"],
                "output": str(arguments.output),
                "preparation_id": manifest["preparation_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
