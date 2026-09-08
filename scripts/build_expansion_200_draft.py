#!/usr/bin/env python3
"""Build or validate the opt-in initial-three expansion draft, not the public core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.expansion_200_initial_three import (  # noqa: E402
    REVIEW_PINS,
    contract_path,
    draft_path,
)
from datacenter_atlas.verified_construction_core_v018 import (  # noqa: E402
    build_draft,
    validate_draft,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=draft_path())
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        manifest = validate_draft(args.output_dir, contract_path(), REVIEW_PINS)
    else:
        manifest = build_draft(contract_path(), REVIEW_PINS, args.output_dir)
    print(json.dumps({key: manifest[key] for key in (
        "release_status", "publishable_as_final", "counts"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
