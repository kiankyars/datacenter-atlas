#!/usr/bin/env python3
"""Run, replay-verify, freeze, or offline-validate singleton batch v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datacenter_atlas.satellite_change_singleton_batch_v2 import (  # noqa: E402
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    PREPARATION_DEFINITION_PATH,
    PREPARATION_DIRECTORY_PATH,
    SatelliteChangeSingletonBatchV2Error,
    SingletonBatchConfig,
    execute_satellite_change_singleton_batch_v2,
    freeze_satellite_change_singleton_batch_v2,
    validate_satellite_change_singleton_batch_v2,
    verify_satellite_change_singleton_batch_v2_determinism,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--preparation-dir", type=Path, default=ROOT / PREPARATION_DIRECTORY_PATH
    )
    result.add_argument(
        "--definition", type=Path, default=ROOT / PREPARATION_DEFINITION_PATH
    )
    result.add_argument("--output-dir", type=Path, default=ROOT / DEFAULT_OUTPUT_PATH)
    result.add_argument("--max-jobs", type=int, default=6)
    result.add_argument("--max-job-attempts", type=int, default=2)
    result.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    )
    action = result.add_mutually_exclusive_group()
    action.add_argument("--verify-determinism", action="store_true")
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--validate-only", action="store_true")
    action.add_argument("--validate-unfrozen", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = SingletonBatchConfig(
        timeout_seconds=arguments.timeout_seconds,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        max_job_attempts=arguments.max_job_attempts,
    )
    try:
        if arguments.verify_determinism:
            manifest = verify_satellite_change_singleton_batch_v2_determinism(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
            )
            result = {"determinism": manifest["determinism"], "state": manifest["state"]}
        elif arguments.freeze:
            freeze = freeze_satellite_change_singleton_batch_v2(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
            )
            result = {"freeze": freeze, "state": "frozen"}
        elif arguments.validate_only or arguments.validate_unfrozen:
            manifest = validate_satellite_change_singleton_batch_v2(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
                require_frozen=not arguments.validate_unfrozen,
            )
            result = {
                "determinism": manifest["determinism"],
                "state": manifest["state"],
                "summary": manifest["summary"],
            }
        else:
            manifest = execute_satellite_change_singleton_batch_v2(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
                config=config,
                max_jobs=arguments.max_jobs,
            )
            result = {
                "determinism": manifest["determinism"],
                "state": manifest["state"],
                "summary": manifest["summary"],
            }
    except SatelliteChangeSingletonBatchV2Error as error:
        print(f"satellite-change-singleton-batch-v2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
