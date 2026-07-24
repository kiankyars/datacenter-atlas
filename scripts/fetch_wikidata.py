#!/usr/bin/env python3
"""Fetch a resumable, hash-verified Wikidata data-center candidate bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.wikidata import WikidataFetcher, WIKIDATA_USER_AGENT


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--page-size", type=int, default=200)
    result.add_argument("--batch-size", type=int, default=50)
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument("--max-retries", type=int, default=3)
    result.add_argument("--retry-base-seconds", type=float, default=1.0)
    result.add_argument("--transient-failure-limit", type=int, default=3)
    result.add_argument(
        "--max-requests",
        type=int,
        help="Checkpoint after this many successful logical requests",
    )
    result.add_argument("--user-agent", default=WIKIDATA_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = WikidataFetcher(
        user_agent=arguments.user_agent,
        timeout=arguments.timeout,
        max_retries=arguments.max_retries,
        retry_base_seconds=arguments.retry_base_seconds,
        transient_failure_limit=arguments.transient_failure_limit,
    ).fetch(
        arguments.output,
        page_size=arguments.page_size,
        batch_size=arguments.batch_size,
        max_requests=arguments.max_requests,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("state") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
