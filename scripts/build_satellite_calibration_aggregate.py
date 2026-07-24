#!/usr/bin/env python3
"""Define, build, or validate a label-blind algorithm-v2 numerical aggregate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.satellite_calibration_aggregate import (  # noqa: E402
    SatelliteCalibrationAggregateError,
    validate_satellite_calibration_aggregate,
    write_satellite_calibration_aggregate,
    write_satellite_calibration_aggregate_definition,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preparation-dir", type=Path)
    parser.add_argument("--shard-dir", action="append", default=[], type=Path)
    parser.add_argument("--release-id")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-definition", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.write_definition:
            if arguments.preparation_dir is None or arguments.release_id is None:
                parser.error(
                    "--write-definition requires --preparation-dir and --release-id"
                )
            payload = write_satellite_calibration_aggregate_definition(
                arguments.preparation_dir,
                arguments.shard_dir,
                arguments.definition,
                release_id=arguments.release_id,
            )
        elif arguments.validate_only:
            if arguments.output_dir is None:
                parser.error("--validate-only requires --output-dir")
            payload = validate_satellite_calibration_aggregate(
                arguments.output_dir, definition_path=arguments.definition
            )
        else:
            if arguments.output_dir is None:
                parser.error("build requires --output-dir")
            if arguments.shard_dir or arguments.preparation_dir or arguments.release_id:
                parser.error(
                    "build reads all source paths from --definition; source arguments are unsupported"
                )
            payload = write_satellite_calibration_aggregate(
                arguments.output_dir, definition_path=arguments.definition
            )
    except SatelliteCalibrationAggregateError as error:
        print(f"satellite-calibration-aggregate error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
