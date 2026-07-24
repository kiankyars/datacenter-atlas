#!/usr/bin/env python3
"""Run or offline-validate a bounded satellite change-proposal batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change_batch import (
    CHANGE_BATCH_MANIFEST_FILENAME,
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ChangeBatchConfig,
    execute_satellite_change_batch,
    validate_satellite_change_batch,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--queue-dir", required=True, type=Path)
    result.add_argument(
        "--catalog-batch-dir",
        required=True,
        action="append",
        type=Path,
        help="Validated catalog batch; repeat for non-overlapping batches",
    )
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument(
        "--queue-id",
        action="append",
        help="Explicit queue ID to select; repeat as needed (first run only)",
    )
    result.add_argument(
        "--exclusion-file",
        type=Path,
        help="Canonical queue-bound exclusion JSON (first run only)",
    )
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
        help="Perform complete offline validation without executing change analysis",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = ChangeBatchConfig(
        timeout_seconds=arguments.timeout_seconds,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        max_job_attempts=arguments.max_job_attempts,
    )
    if arguments.validate_only:
        manifest = validate_satellite_change_batch(
            arguments.queue_dir,
            arguments.catalog_batch_dir,
            arguments.output_dir,
            config=config,
            include_queue_ids=arguments.queue_id,
            exclusion_file=arguments.exclusion_file,
        )
    else:
        manifest = execute_satellite_change_batch(
            arguments.queue_dir,
            arguments.catalog_batch_dir,
            arguments.output_dir,
            config=config,
            include_queue_ids=arguments.queue_id,
            exclusion_file=arguments.exclusion_file,
            max_jobs=arguments.max_jobs,
        )
    print(
        json.dumps(
            {
                "manifest": str(
                    (arguments.output_dir / CHANGE_BATCH_MANIFEST_FILENAME).resolve()
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
