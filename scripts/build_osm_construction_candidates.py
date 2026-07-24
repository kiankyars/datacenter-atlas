#!/usr/bin/env python3
"""Build the atomic review-only OSM structural construction candidate bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.osm_construction import (  # noqa: E402
    materialize_construction_candidates,
)
from datacenter_atlas.osm_planet import PlanetMaterializationError  # noqa: E402


DEFAULT_SOURCE_DIRECTORY = PROJECT_ROOT / "source_cache" / "osm-planet-260713"
DEFAULT_EXTRACTION_MANIFEST = DEFAULT_SOURCE_DIRECTORY / "construction-extract-manifest.json"
DEFAULT_EXACT_MANIFEST = DEFAULT_SOURCE_DIRECTORY / "materialized" / "manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "releases" / "2026-07-18-osm-construction-candidates-v3"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extraction-manifest", type=Path, default=DEFAULT_EXTRACTION_MANIFEST
    )
    parser.add_argument("--filtered-pbf", type=Path)
    parser.add_argument(
        "--exact-materialization-manifest", type=Path, default=DEFAULT_EXACT_MANIFEST
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--osmium-binary", default="osmium")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = materialize_construction_candidates(
            arguments.extraction_manifest,
            arguments.exact_materialization_manifest,
            arguments.output_directory,
            filtered_pbf=arguments.filtered_pbf,
            osmium_binary=arguments.osmium_binary,
            dry_run=arguments.dry_run,
        )
    except PlanetMaterializationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
