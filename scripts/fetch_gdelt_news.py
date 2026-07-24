#!/usr/bin/env python3
"""Fetch the pinned GDELT Web NGrams raw snapshot pair at low rate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.gdelt import (
    GDELT_DEFAULT_INTERVAL_SECONDS,
    GDELT_USER_AGENT,
    PINNED_SNAPSHOT,
    GDELTSnapshotFetcher,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--max-requests", type=int, default=2)
    result.add_argument("--retry-failed", action="store_true")
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument("--max-attempts", type=int, default=3)
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=GDELT_DEFAULT_INTERVAL_SECONDS,
    )
    result.add_argument("--user-agent", default=GDELT_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = GDELTSnapshotFetcher(
        user_agent=arguments.user_agent,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        timeout=arguments.timeout,
        max_attempts=arguments.max_attempts,
    ).fetch(
        arguments.output,
        max_requests=arguments.max_requests,
        retry_failed=arguments.retry_failed,
    )
    print(
        json.dumps(
            {
                "snapshot_id": PINNED_SNAPSHOT.snapshot_id,
                "manifest": str((arguments.output / "manifest.json").resolve()),
                "state": manifest["state"],
                "summary": manifest["summary"],
                "last_run": manifest["last_run"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

