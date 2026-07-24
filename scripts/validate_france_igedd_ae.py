#!/usr/bin/env python3
"""Validate a frozen France IGEDD Ae assessment without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.france_igedd_ae import (
    FranceIGEDDAEError,
    RELEASE_ID,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("release", nargs="?", type=Path, default=DEFAULT_RELEASE)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(arguments.release)
    print(
        json.dumps(
            {
                "archive_matches": bundle["annual_index"][
                    "archive_closed_match_count"
                ],
                "classification_counts": bundle["assessment"][
                    "classification_counts"
                ],
                "current_2026_origin_capture_complete": False,
                "planned_data_centre_units": bundle["assessment"][
                    "coverage_assessment"
                ]["planned_data_centre_units_in_direct_projects"],
                "release": str(arguments.release),
                "release_id": RELEASE_ID,
                "unique_project_sites": bundle["assessment"][
                    "coverage_assessment"
                ]["unique_project_site_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FranceIGEDDAEError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
