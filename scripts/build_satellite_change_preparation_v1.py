#!/usr/bin/env python3
"""Build or offline-validate the frozen v57 catalog-to-change preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datacenter_atlas.satellite_change_preparation_v1 import (  # noqa: E402
    DEFINITION_PATH,
    OUTPUT_PATH,
    SatelliteChangePreparationV1Error,
    validate_satellite_change_preparation_v1,
    write_satellite_change_preparation_v1,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", type=Path, default=ROOT / DEFINITION_PATH)
    result.add_argument("--output-dir", type=Path, default=ROOT / OUTPUT_PATH)
    result.add_argument("--validate-only", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.validate_only:
            manifest = validate_satellite_change_preparation_v1(
                arguments.output_dir, definition_path=arguments.definition
            )
        else:
            manifest = write_satellite_change_preparation_v1(
                arguments.output_dir, definition_path=arguments.definition
            )
    except SatelliteChangePreparationV1Error as error:
        print(f"satellite-change-preparation-v1 error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "format": manifest["format"],
                "output": str(arguments.output_dir),
                "summary": manifest["summary"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
