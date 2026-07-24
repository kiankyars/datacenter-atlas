#!/usr/bin/env python3
"""Fetch and checkpoint the pinned UVA DC-SENSE Dataverse v2.0 bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.uva import UVADataFetcher, UVA_USER_AGENT


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path, help="output bundle directory")
    result.add_argument("--fetched-at", help="override the UTC checkpoint timestamp")
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument("--user-agent", default=UVA_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = UVADataFetcher(
        user_agent=arguments.user_agent,
        timeout=arguments.timeout,
    ).fetch(arguments.output, fetched_at=arguments.fetched_at)
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
