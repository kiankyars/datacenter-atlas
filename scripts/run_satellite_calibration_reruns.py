#!/usr/bin/env python3
"""Validate inputs or execute a bounded exact algorithm-v2 calibration rerun shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.satellite_calibration_rerun import (  # noqa: E402
    SatelliteCalibrationRerunError,
    execute_satellite_calibration_reruns,
    validate_satellite_calibration_rerun_inputs,
    validate_satellite_calibration_rerun_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-dir", required=True, type=Path)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--minimum-interval-seconds", type=float, default=1.1)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-inputs-only", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.validate_inputs_only:
            payload = validate_satellite_calibration_rerun_inputs(
                arguments.preparation_dir, definition_path=arguments.definition
            )
        elif arguments.validate_only:
            if arguments.output_dir is None:
                parser.error("--output-dir is required for output validation")
            payload = validate_satellite_calibration_rerun_output(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
            )
        else:
            if arguments.output_dir is None:
                parser.error("--output-dir is required for numerical execution")
            payload = execute_satellite_calibration_reruns(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
                start_index=arguments.start_index,
                max_jobs=arguments.max_jobs,
                max_attempts=arguments.max_attempts,
                timeout_seconds=arguments.timeout_seconds,
                minimum_interval_seconds=arguments.minimum_interval_seconds,
            )
    except SatelliteCalibrationRerunError as error:
        print(f"satellite-calibration-rerun error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
