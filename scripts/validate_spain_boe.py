#!/usr/bin/env python3
"""Validate the frozen Spain BOE source assessment without network access."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.spain_boe import RELEASE_ID, SpainBOEError, validate_release_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", nargs="?", type=Path, default=DEFAULT_RELEASE)
    arguments = parser.parse_args(argv)
    bundle = validate_release_bundle(arguments.release)
    counts = bundle["assessment"]["coverage_assessment"]["classification_counts"]
    print(
        f"validated {arguments.release}: "
        f"direct={counts['direct_project_build_expansion_candidate']} "
        f"context={counts['ancillary_or_administrative_context']} "
        f"excluded={counts['excluded_non_build_or_non_datacentre']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpainBOEError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
