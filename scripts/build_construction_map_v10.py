#!/usr/bin/env python3
"""Build or offline-validate the immutable v26 construction map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_map_v10 import (  # noqa: E402
    ConstructionMapV10Error,
    validate_construction_map_v10,
    write_construction_map_v10,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--master-dir", required=True, type=Path)
    result.add_argument("--master-definition", required=True, type=Path)
    result.add_argument("--map-definition", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--freeze", action=argparse.BooleanOptionalAction, default=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.validate_only:
            manifest = validate_construction_map_v10(
                arguments.output_dir,
                master_directory=arguments.master_dir,
                master_definition_path=arguments.master_definition,
                map_definition_path=arguments.map_definition,
            )
        else:
            manifest = write_construction_map_v10(
                arguments.master_dir,
                arguments.output_dir,
                master_definition_path=arguments.master_definition,
                map_definition_path=arguments.map_definition,
                freeze=arguments.freeze,
            )
    except ConstructionMapV10Error as error:
        print(f"construction-map-v10 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
