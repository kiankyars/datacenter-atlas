#!/usr/bin/env python3
"""Validate or run the coverage-reselected side-by-side change batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_reselected_change_batch import (
    CHANGE_BATCH_MANIFEST_FILENAME,
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ChangeBatchConfig,
    execute_satellite_reselected_change_batch,
    validate_reselected_change_inputs,
    validate_satellite_reselected_change_batch,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--queue-dir", required=True, type=Path)
    result.add_argument("--source-catalog-batch-dir", required=True, type=Path)
    result.add_argument("--reselection-release-dir", required=True, type=Path)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--max-jobs", type=int, default=1)
    result.add_argument("--max-job-attempts", type=int, default=3)
    result.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    )
    mode = result.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate-inputs-only",
        action="store_true",
        help="Validate queue, source catalog, release bytes, and task bindings only",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing side-by-side output without executing analysis",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = ChangeBatchConfig(
        timeout_seconds=arguments.timeout_seconds,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        max_job_attempts=arguments.max_job_attempts,
    )
    if arguments.validate_inputs_only:
        manifest = validate_reselected_change_inputs(
            arguments.queue_dir,
            arguments.source_catalog_batch_dir,
            arguments.reselection_release_dir,
        )
        payload = manifest
    else:
        if arguments.output_dir is None:
            parser().error(
                "--output-dir is required unless --validate-inputs-only is used"
            )
        if arguments.validate_only:
            manifest = validate_satellite_reselected_change_batch(
                arguments.queue_dir,
                arguments.source_catalog_batch_dir,
                arguments.reselection_release_dir,
                arguments.output_dir,
                config=config,
            )
        else:
            manifest = execute_satellite_reselected_change_batch(
                arguments.queue_dir,
                arguments.source_catalog_batch_dir,
                arguments.reselection_release_dir,
                arguments.output_dir,
                config=config,
                max_jobs=arguments.max_jobs,
            )
        payload = {
            "manifest": str(
                (arguments.output_dir / CHANGE_BATCH_MANIFEST_FILENAME).resolve()
            ),
            "pipeline": manifest["pipeline"],
            "state": manifest["state"],
            "summary": manifest["summary"],
            "selection": manifest["selection"],
            "last_run": manifest["runs"][-1] if manifest["runs"] else None,
            "scope": manifest["scope"],
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
