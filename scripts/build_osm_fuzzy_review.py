#!/usr/bin/env python3
"""Build the isolated, review-only fuzzy OSM candidate release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.fuzzy_snapshot import (  # noqa: E402
    DEFAULT_EXTRACTION_MANIFEST,
    DEFAULT_MATERIALIZATION,
    build_fuzzy_review_snapshot,
)
from datacenter_atlas.global_snapshot import (  # noqa: E402
    DEFAULT_MAP_GENERATOR,
    DEFAULT_NATURAL_EARTH_INPUT,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--extraction-manifest", type=Path, default=DEFAULT_EXTRACTION_MANIFEST
    )
    result.add_argument("--materialization", type=Path, default=DEFAULT_MATERIALIZATION)
    result.add_argument(
        "--natural-earth-input", type=Path, default=DEFAULT_NATURAL_EARTH_INPUT
    )
    result.add_argument("--map-generator", type=Path, default=DEFAULT_MAP_GENERATOR)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--as-of", required=True)
    result.add_argument("--recorded-at", required=True)
    result.add_argument(
        "--retrieved-at",
        required=True,
        help="Verified Planet retrieval completion timestamp used by evidence rows",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    output = build_fuzzy_review_snapshot(
        extraction_manifest=arguments.extraction_manifest,
        materialization=arguments.materialization,
        natural_earth_input=arguments.natural_earth_input,
        output_directory=arguments.output_dir,
        as_of=arguments.as_of,
        recorded_at=arguments.recorded_at,
        retrieved_at=arguments.retrieved_at,
        map_generator=arguments.map_generator,
    )
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
