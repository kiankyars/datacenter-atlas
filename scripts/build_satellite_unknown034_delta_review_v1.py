#!/usr/bin/env python3
"""Build or offline-validate the frozen Unknown034 delta review v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_unknown034_delta_review_v1 import (
    validate_unknown034_delta_review_v1,
    write_unknown034_delta_review_v1,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--validate-only", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        manifest = validate_unknown034_delta_review_v1(
            arguments.output_dir, arguments.definition
        )
    else:
        manifest = write_unknown034_delta_review_v1(
            arguments.definition, arguments.output_dir
        )
    print(
        json.dumps(
            {
                "manifest": str(
                    (arguments.output_dir / "review-manifest.json").resolve()
                ),
                "review_id": manifest["review_id"],
                "summary": manifest["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
