#!/usr/bin/env python3
"""Import a verified Wikidata candidate bundle into an atlas database offline."""

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
from datacenter_atlas.wikidata import WikidataAdapter, validate_wikidata_bundle


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path, help="Verified bundle directory")
    result.add_argument("--database", required=True, type=Path)
    result.add_argument(
        "--retrieved-at",
        help="Must match manifest retrieved_completed_at; defaults to that value",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = arguments.input.resolve()
    database = arguments.database.resolve()
    if database == bundle or database.is_relative_to(bundle):
        raise SystemExit("database path must be outside the immutable Wikidata bundle")
    view = validate_wikidata_bundle(bundle)
    retrieved_at = arguments.retrieved_at or view.manifest["retrieved_completed_at"]
    connection, _ = initialize(database)
    try:
        import_result = WikidataAdapter().import_file(
            connection,
            bundle,
            retrieved_at=retrieved_at,
        )
    finally:
        connection.close()
    print(json.dumps(asdict(import_result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
