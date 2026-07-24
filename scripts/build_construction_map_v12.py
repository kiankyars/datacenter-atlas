#!/usr/bin/env python3
"""Inspect, publish, or validate the immutable v28 construction map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_map_v12 import (  # noqa: E402
    BUNDLE,
    DEFINITION,
    MASTER,
    MASTER_DEFINITION,
    ConstructionMapV12Error,
    derive_candidate_projection,
    publish_construction_map_v12,
    validate_construction_map_v12,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--derive-candidate", action="store_true")
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    result.add_argument("--generated-at")
    result.add_argument("--master-dir", type=Path, default=MASTER)
    result.add_argument(
        "--master-definition", type=Path, default=MASTER_DEFINITION
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.derive_candidate:
            result = derive_candidate_projection(
                arguments.master_dir, arguments.master_definition
            )
        elif arguments.publish:
            if arguments.generated_at is None:
                raise ConstructionMapV12Error(
                    "--publish requires --generated-at"
                )
            result = publish_construction_map_v12(arguments.generated_at)
        else:
            result = validate_construction_map_v12(
                BUNDLE,
                master_directory=arguments.master_dir,
                master_definition_path=arguments.master_definition,
                map_definition_path=DEFINITION,
            )
    except ConstructionMapV12Error as error:
        print(f"construction-map-v12 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
