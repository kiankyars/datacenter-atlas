#!/usr/bin/env python3
"""Build the offline ODbL-compatible global data-centre snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.global_snapshot import (  # noqa: E402
    DEFAULT_EXTRACTION_MANIFEST,
    DEFAULT_MAP_GENERATOR,
    DEFAULT_NATURAL_EARTH_INPUT,
    DEFAULT_OSM_MATERIALIZATION,
    DEFAULT_PNNL_INPUT,
    DEFAULT_UVA_INPUT,
    DEFAULT_WIKIDATA_INPUT,
    build_global_snapshot,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--extraction-manifest", type=Path, default=DEFAULT_EXTRACTION_MANIFEST
    )
    result.add_argument(
        "--osm-materialization", type=Path, default=DEFAULT_OSM_MATERIALIZATION
    )
    result.add_argument("--pnnl-input", type=Path, default=DEFAULT_PNNL_INPUT)
    result.add_argument(
        "--pnnl-retrieved-at",
        help="Defaults to fetched_at when --pnnl-input is a verified bundle",
    )
    result.add_argument("--wikidata-input", type=Path, default=DEFAULT_WIKIDATA_INPUT)
    result.add_argument("--uva-input", type=Path, default=DEFAULT_UVA_INPUT)
    result.add_argument(
        "--natural-earth-input", type=Path, default=DEFAULT_NATURAL_EARTH_INPUT
    )
    result.add_argument("--map-generator", type=Path, default=DEFAULT_MAP_GENERATOR)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--as-of", required=True)
    result.add_argument("--recorded-at", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    result = build_global_snapshot(
        extraction_manifest=arguments.extraction_manifest,
        osm_materialization=arguments.osm_materialization,
        pnnl_input=arguments.pnnl_input,
        pnnl_retrieved_at=arguments.pnnl_retrieved_at,
        wikidata_input=arguments.wikidata_input,
        uva_input=arguments.uva_input,
        natural_earth_input=arguments.natural_earth_input,
        output_directory=arguments.output_dir,
        as_of=arguments.as_of,
        recorded_at=arguments.recorded_at,
        map_generator=arguments.map_generator,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
