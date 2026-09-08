#!/usr/bin/env python3
"""Build or validate a reviewed opt-in expansion draft, not the public core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas import (  # noqa: E402
    expansion_200_fifth_reviewed,
    expansion_200_fourth_reviewed,
    expansion_200_initial_five,
    expansion_200_initial_three,
    expansion_200_second_reviewed,
    expansion_200_third_reviewed,
)
from datacenter_atlas.verified_construction_core_v018 import (  # noqa: E402
    build_draft,
    validate_draft,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    batches = {
        "initial-three": expansion_200_initial_three,
        "initial-five": expansion_200_initial_five,
        "second-reviewed": expansion_200_second_reviewed,
        "third-reviewed": expansion_200_third_reviewed,
        "fourth-reviewed": expansion_200_fourth_reviewed,
        "fifth-reviewed": expansion_200_fifth_reviewed,
    }
    parser.add_argument("--batch", choices=sorted(batches), default="initial-three")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    batch = batches[args.batch]
    output = args.output_dir or batch.draft_path()
    if args.validate_only:
        manifest = validate_draft(output, batch.contract_path(), batch.REVIEW_PINS)
    else:
        manifest = build_draft(batch.contract_path(), batch.REVIEW_PINS, output)
    print(json.dumps({key: manifest[key] for key in (
        "release_status", "publishable_as_final", "counts"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
