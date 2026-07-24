#!/usr/bin/env python3
"""Fetch a verified, resumable Scrutica facility-discovery bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.scrutica import (
    SCRUTICA_DEFAULT_INTERVAL_SECONDS,
    SCRUTICA_USER_AGENT,
    ScruticaFetcher,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path, help="Output bundle directory")
    result.add_argument(
        "--max-requests",
        type=int,
        default=50,
        help=(
            "Maximum MCP HTTP attempts this run (directory requests are excluded; "
            "default: 50)"
        ),
    )
    result.add_argument(
        "--max-failures",
        type=int,
        default=10,
        help="Stop after this many facility tasks exhaust retries (default: 10)",
    )
    result.add_argument(
        "--retry-failed",
        action="store_true",
        help="Explicitly requeue facility tasks that previously exhausted retries",
    )
    result.add_argument("--created-at", help="Override the initial UTC checkpoint timestamp")
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument(
        "--interval-seconds",
        type=float,
        default=SCRUTICA_DEFAULT_INTERVAL_SECONDS,
        help="Minimum spacing between MCP requests; cannot be below 1.1 seconds",
    )
    result.add_argument("--max-attempts", type=int, default=3)
    result.add_argument("--user-agent", default=SCRUTICA_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = ScruticaFetcher(
        user_agent=arguments.user_agent,
        timeout=arguments.timeout,
        interval_seconds=arguments.interval_seconds,
        max_attempts=arguments.max_attempts,
    ).fetch(
        arguments.output,
        created_at=arguments.created_at,
        max_requests=arguments.max_requests,
        max_failures=arguments.max_failures,
        retry_failed=arguments.retry_failed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

