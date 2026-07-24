#!/usr/bin/env python3
"""Build or offline-validate an immutable current-coverage ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.current_coverage import (  # noqa: E402
    CurrentCoverageError,
    validate_current_coverage_ledger,
    write_current_coverage_ledger,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate all pins and reproduce an existing bundle byte-for-byte",
    )
    parser.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="make a newly written bundle directory 0555 and files 0444",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.validate_only:
            manifest = validate_current_coverage_ledger(
                arguments.output,
                definition_path=arguments.definition,
            )
        else:
            manifest = write_current_coverage_ledger(
                arguments.definition,
                arguments.output,
                freeze=arguments.freeze,
            )
    except CurrentCoverageError as error:
        print(f"current-coverage error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "format": manifest["format"],
                "ledger_id": manifest["ledger_id"],
                "ledger_sha256": manifest["artifacts"][
                    "current-coverage-ledger.json"
                ]["sha256"],
                "output": str(arguments.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
