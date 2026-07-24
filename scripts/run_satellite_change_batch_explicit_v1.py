#!/usr/bin/env python3
"""Run or offline-validate the exact v71 eleven-job change tranche."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change_batch_explicit_v1 import (
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    ExplicitChangeBatchConfig,
    execute_explicit_satellite_change_batch_v1,
    output_tree_sha256,
    validate_explicit_satellite_change_batch_v1,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_PATH)
    result.add_argument("--max-jobs", type=int, default=11)
    result.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    )
    result.add_argument("--validate-only", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    config = ExplicitChangeBatchConfig(
        timeout_seconds=arguments.timeout_seconds,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
    )
    if arguments.validate_only:
        document = validate_explicit_satellite_change_batch_v1(
            arguments.output_dir, config=config
        )
    else:
        document = execute_explicit_satellite_change_batch_v1(
            arguments.output_dir,
            config=config,
            max_jobs=arguments.max_jobs,
        )
    manifest_path = arguments.output_dir / "batch-manifest.json"
    manifest_raw = manifest_path.read_bytes()
    print(
        json.dumps(
            {
                "manifest": str(manifest_path.resolve()),
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "output_tree_sha256": output_tree_sha256(arguments.output_dir),
                "scope": document["scope"],
                "state": document["state"],
                "summary": document["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
