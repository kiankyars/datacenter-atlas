#!/usr/bin/env python3
"""Build or offline-validate the immutable v24 construction master."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_master_v8 import (  # noqa: E402
    ConstructionMasterV8Error,
    validate_construction_master_v8,
    write_construction_master_v8,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--freeze", action=argparse.BooleanOptionalAction, default=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.validate_only:
            manifest = validate_construction_master_v8(
                arguments.output, definition_path=arguments.definition
            )
        else:
            manifest = write_construction_master_v8(
                arguments.definition,
                arguments.output,
                freeze=arguments.freeze,
            )
    except ConstructionMasterV8Error as error:
        print(f"construction-master-v8 error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "format": manifest["format"],
                "output": str(arguments.output),
                "rows": manifest["row_counts"]["total"],
                "tiers": manifest["row_counts"]["by_tier"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
