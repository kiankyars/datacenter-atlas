#!/usr/bin/env python3
"""Run or offline-validate the exact v57 multi-tile change batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datacenter_atlas.satellite_change_mosaic_batch_v1 import (  # noqa: E402
    BATCH_MANIFEST_FILENAME,
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    PREPARATION_DEFINITION_PATH,
    PREPARATION_DIRECTORY_PATH,
    MosaicBatchConfig,
    SatelliteChangeMosaicBatchV1Error,
    execute_satellite_change_mosaic_batch_v1,
    validate_satellite_change_mosaic_batch_v1,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--preparation-dir",
        type=Path,
        default=ROOT / PREPARATION_DIRECTORY_PATH,
    )
    result.add_argument(
        "--definition",
        type=Path,
        default=ROOT / PREPARATION_DEFINITION_PATH,
    )
    result.add_argument("--output-dir", type=Path, default=ROOT / DEFAULT_OUTPUT_PATH)
    result.add_argument("--max-jobs", type=int, default=1)
    result.add_argument("--max-job-attempts", type=int, default=3)
    result.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    )
    result.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the complete checkpoint and outputs without executing imagery",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        config = MosaicBatchConfig(
            timeout_seconds=arguments.timeout_seconds,
            minimum_interval_seconds=arguments.minimum_interval_seconds,
            max_job_attempts=arguments.max_job_attempts,
        )
        if arguments.validate_only:
            manifest = validate_satellite_change_mosaic_batch_v1(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
                config=config,
            )
        else:
            manifest = execute_satellite_change_mosaic_batch_v1(
                arguments.preparation_dir,
                arguments.output_dir,
                definition_path=arguments.definition,
                config=config,
                max_jobs=arguments.max_jobs,
            )
    except SatelliteChangeMosaicBatchV1Error as error:
        print(f"satellite-change-mosaic-batch-v1 error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "manifest": str(
                    (arguments.output_dir / BATCH_MANIFEST_FILENAME).resolve()
                ),
                "state": manifest["state"],
                "summary": manifest["summary"],
                "selection": manifest["selection"],
                "last_run": manifest["runs"][-1] if manifest["runs"] else None,
                "scope": manifest["scope"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
