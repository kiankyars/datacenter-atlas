#!/usr/bin/env python3
"""Materialize a verified fuzzy OSM PBF as loss-aware review JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.osm_fuzzy import materialize_fuzzy_extract  # noqa: E402
from datacenter_atlas.osm_planet import PlanetMaterializationError  # noqa: E402


DEFAULT_DIRECTORY = PROJECT_ROOT / "source_cache" / "osm-planet-260713"
DEFAULT_MANIFEST = DEFAULT_DIRECTORY / "fuzzy-extract-manifest.json"
DEFAULT_OUTPUT = DEFAULT_DIRECTORY / "fuzzy-materialized-review"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--filtered-pbf", type=Path)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--osmium-binary", default="osmium")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = materialize_fuzzy_extract(
            arguments.extraction_manifest,
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
