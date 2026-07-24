#!/usr/bin/env python3
"""Validate and summarize an exact Microsoft buildings shard index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.microsoft_building_footprints import inventory_index


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = (
    PROJECT_ROOT
    / "sources"
    / "microsoft-global-ml-building-footprints-2026-07-18-v1.json"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", required=True, type=Path)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    rows, locations, summary = inventory_index(
        arguments.index, definition_path=arguments.definition
    )
    print(
        json.dumps(
            {
                "index": str(arguments.index.resolve()),
                "network_requests": 0,
                "normalized_rows": len(rows),
                "location_rows": len(locations),
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
