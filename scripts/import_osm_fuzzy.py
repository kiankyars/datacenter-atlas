#!/usr/bin/env python3
"""Import review-only fuzzy OSM matches as source-scoped facility leads."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.database import initialize  # noqa: E402
from datacenter_atlas.osm_fuzzy import OpenStreetMapFuzzyDiscoveryAdapter  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--retrieved-at", required=True)
    arguments = parser.parse_args(argv)
    connection, _ = initialize(arguments.database)
    try:
        result = OpenStreetMapFuzzyDiscoveryAdapter().import_file(
            connection, arguments.input, retrieved_at=arguments.retrieved_at
        )
    finally:
        connection.close()
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
