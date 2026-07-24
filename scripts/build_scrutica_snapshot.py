#!/usr/bin/env python3
"""Build an immutable, isolated Scrutica discovery release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.scrutica_snapshot import build_scrutica_snapshot


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--as-of", required=True)
    result.add_argument("--recorded-at", required=True)
    result.add_argument(
        "--retrieved-at",
        required=True,
        help="Uniform offline-import timestamp at or after the completed source fetch",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    output = build_scrutica_snapshot(
        source_bundle=arguments.input,
        output_directory=arguments.output_dir,
        as_of=arguments.as_of,
        recorded_at=arguments.recorded_at,
        retrieved_at=arguments.retrieved_at,
    )
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
