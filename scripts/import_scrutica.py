#!/usr/bin/env python3
"""Import strictly typed data centres from a verified Scrutica bundle."""

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
from datacenter_atlas.scrutica import ScruticaAdapter


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Scrutica fetch bundle; non-data-centre and ambiguous types stay raw only",
    )
    result.add_argument(
        "--database",
        required=True,
        type=Path,
        help="Dedicated Scrutica-only SQLite database; never use the open release DB",
    )
    result.add_argument("--retrieved-at", required=True)
    result.add_argument(
        "--allow-partial",
        action="store_true",
        help="Import only completed records and emit an explicit partial-coverage warning",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.input.resolve() == arguments.database.resolve():
        raise SystemExit("database path must not overwrite the Scrutica fetch bundle")
    connection, _ = initialize(arguments.database)
    try:
        import_result = ScruticaAdapter().import_file(
            connection,
            arguments.input,
            retrieved_at=arguments.retrieved_at,
            allow_partial=arguments.allow_partial,
        )
    finally:
        connection.close()
    print(json.dumps(asdict(import_result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
