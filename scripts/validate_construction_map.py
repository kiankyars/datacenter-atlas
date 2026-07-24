#!/usr/bin/env python3
"""Validate and reproduce a frozen construction-map bundle offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.construction_map import validate_construction_map


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--map-dir", type=Path, required=True)
    result.add_argument("--master-dir", type=Path, required=True)
    result.add_argument("--master-definition", type=Path, required=True)
    result.add_argument("--map-definition", type=Path, required=True)
    result.add_argument("--static-only", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = validate_construction_map(
        arguments.map_dir,
        master_directory=arguments.master_dir,
        master_definition_path=arguments.master_definition,
        map_definition_path=arguments.map_definition,
        reproduce=not arguments.static_only,
    )
    print(
        json.dumps(
            {
                "map_id": manifest["map_id"],
                "mapped_observation_rows": manifest["outputs"][
                    "construction-map-index.json.gz"
                ]["records"],
                "network_requests": 0,
                "reproduced": not arguments.static_only,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
