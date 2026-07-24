#!/usr/bin/env python3
"""Import a verified UVA DC-SENSE v2.0 CSV or fetch bundle offline."""

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
from datacenter_atlas.uva import UVADataverseAdapter, UVA_LOCAL_FILENAME


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path, help="CSV artifact or fetch bundle")
    result.add_argument("--database", required=True, type=Path)
    result.add_argument("--retrieved-at", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    source_artifact = (
        arguments.input / UVA_LOCAL_FILENAME
        if arguments.input.is_dir()
        else arguments.input
    )
    if source_artifact.resolve() == arguments.database.resolve():
        raise SystemExit("database path must not overwrite the UVA source artifact")
    connection, _ = initialize(arguments.database)
    try:
        result = UVADataverseAdapter().import_file(
            connection,
            arguments.input,
            retrieved_at=arguments.retrieved_at,
        )
    finally:
        connection.close()
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
