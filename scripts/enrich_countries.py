#!/usr/bin/env python3
"""Enrich current geocoded atlas snapshots with Natural Earth countries."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.database import initialize
from datacenter_atlas.natural_earth import enrich_administrative_assignments
from datacenter_atlas.service import validate_database


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path, help="Verified boundary bundle")
    result.add_argument("--database", required=True, type=Path)
    result.add_argument("--as-of", required=True)
    result.add_argument("--recorded-at", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = arguments.input.resolve()
    database = arguments.database.resolve()
    if database == bundle or database.is_relative_to(bundle):
        raise SystemExit("database path must be outside the immutable boundary bundle")
    connection, _ = initialize(database)
    try:
        result = enrich_administrative_assignments(
            connection,
            bundle,
            as_of=arguments.as_of,
            recorded_at=arguments.recorded_at,
        )
        errors = validate_database(connection)
        if errors:
            raise ValueError("database validation failed: " + "; ".join(errors))
    finally:
        connection.close()
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
