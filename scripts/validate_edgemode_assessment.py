#!/usr/bin/env python3
"""Validate the immutable EdgeMode rights assessment and EDGAR pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.edgemode_assessment import validate_assessment_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "edgemode-2026-07-18-v1"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_assessment_bundle(arguments.assessment)
    assessment = bundle["assessment"]
    pilot = bundle["pilot"]
    print(
        json.dumps(
            {
                "assessment_id": assessment["assessment_id"],
                "assessment_status": assessment["atlas_decision"]["status"],
                "construction_verified_rows": pilot["construction_verified_rows"],
                "network_requests": 0,
                "pilot_id": pilot["pilot_id"],
                "pilot_rows": len(pilot["leads"]),
                "typed_capacity_rows": pilot["typed_capacity_rows"],
                "unique_facility_count": pilot["unique_facility_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
