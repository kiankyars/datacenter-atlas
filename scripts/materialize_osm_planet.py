#!/usr/bin/env python3
"""Materialize a filtered OSM planet PBF as loss-aware Overpass JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.osm_planet import (  # noqa: E402
    PlanetMaterializationError,
    materialize_planet_extract,
)


DEFAULT_EXTRACTION_DIRECTORY = PROJECT_ROOT / "source_cache" / "osm-planet-260713"
DEFAULT_EXTRACTION_MANIFEST = DEFAULT_EXTRACTION_DIRECTORY / "extract-manifest.json"
DEFAULT_OUTPUT_DIRECTORY = DEFAULT_EXTRACTION_DIRECTORY / "materialized"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert the verified, reference-retaining OSM planet extract through OSM "
            "XML into deterministic Overpass JSON without losing non-area relations."
        )
    )
    parser.add_argument(
        "--extraction-manifest",
        type=Path,
        default=DEFAULT_EXTRACTION_MANIFEST,
        help=f"completed extraction manifest (default: {DEFAULT_EXTRACTION_MANIFEST})",
    )
    parser.add_argument(
        "--filtered-pbf",
        type=Path,
        help="optional explicit PBF path; it must exactly match the manifest record",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help=f"atomic output bundle directory (default: {DEFAULT_OUTPUT_DIRECTORY})",
    )
    parser.add_argument("--osmium-binary", default="osmium")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate lineage and print the command plan without executing or writing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        manifest = materialize_planet_extract(
            arguments.extraction_manifest,
            arguments.output_directory,
            filtered_pbf=arguments.filtered_pbf,
            osmium_binary=arguments.osmium_binary,
            dry_run=arguments.dry_run,
        )
    except PlanetMaterializationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
