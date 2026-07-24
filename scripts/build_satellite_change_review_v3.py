#!/usr/bin/env python3
"""Generate, publish, or offline-validate satellite-change analyst review v3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.satellite_change_review_v3 import (  # noqa: E402
    DEFINITION_PATH,
    OUTPUT_PATH,
    SatelliteChangeReviewV3Error,
    validate_satellite_change_review_v3,
    write_review_definition,
    write_satellite_change_review_v3,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--definition", type=Path, default=PACKAGE_ROOT / DEFINITION_PATH
    )
    result.add_argument("--output", type=Path, default=PACKAGE_ROOT / OUTPUT_PATH)
    result.add_argument(
        "--emit-definition",
        action="store_true",
        help="Create the canonical definition at --definition and exit.",
    )
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--freeze", action=argparse.BooleanOptionalAction, default=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    if arguments.emit_definition and arguments.validate_only:
        print(
            "satellite-change-review-v3 error: --emit-definition and "
            "--validate-only are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    try:
        if arguments.emit_definition:
            digest = write_review_definition(PACKAGE_ROOT, arguments.definition)
            payload = {"definition": str(arguments.definition), "sha256": digest}
        elif arguments.validate_only:
            manifest = validate_satellite_change_review_v3(
                arguments.output,
                definition_path=arguments.definition,
            )
            payload = {
                "decisions": 6,
                "output": str(arguments.output),
                "review_id": manifest["review_id"],
                "technical_multitile_failures": 1,
                "validated": True,
            }
        else:
            manifest = write_satellite_change_review_v3(
                arguments.definition,
                arguments.output,
                freeze=arguments.freeze,
            )
            payload = {
                "decisions": 6,
                "output": str(arguments.output),
                "review_id": manifest["review_id"],
                "technical_multitile_failures": 1,
            }
    except SatelliteChangeReviewV3Error as error:
        print(f"satellite-change-review-v3 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
