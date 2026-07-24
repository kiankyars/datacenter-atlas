#!/usr/bin/env python3
"""Publish or validate the immutable construction map v31."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_map_v31 import (  # noqa: E402
    BUNDLE,
    DEFINITION,
    ConstructionMapV31Error,
    publish_construction_map_v31,
    validate_construction_map_v31,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    result.add_argument("--generated-at")
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.publish:
            if arguments.generated_at is None:
                raise ConstructionMapV31Error(
                    "--publish requires --generated-at"
                )
            result = publish_construction_map_v31(arguments.generated_at)
        else:
            result = validate_construction_map_v31(
                BUNDLE,
                map_definition_path=DEFINITION,
            )
    except ConstructionMapV31Error as error:
        print(f"construction-map-v31 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
