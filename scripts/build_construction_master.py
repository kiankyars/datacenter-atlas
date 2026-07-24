#!/usr/bin/env python3
"""Build or offline-validate an immutable public/open construction master."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_master import (  # noqa: E402
    ConstructionMasterError,
    validate_construction_master,
    write_construction_master,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and reproduce an existing bundle without network access",
    )
    parser.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="freeze a newly built bundle 0555/0444 (default: true)",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.validate_only:
            manifest = validate_construction_master(
                arguments.output, definition_path=arguments.definition
            )
        else:
            manifest = write_construction_master(
                arguments.definition,
                arguments.output,
                freeze=arguments.freeze,
            )
    except ConstructionMasterError as error:
        print(f"construction-master error: {error}", file=sys.stderr)
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
