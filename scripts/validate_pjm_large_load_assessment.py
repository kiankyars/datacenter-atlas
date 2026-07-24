#!/usr/bin/env python3
"""Validate the immutable, metadata-only PJM large-load assessment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.pjm_large_load_assessment import validate_assessment_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "pjm-large-load-2026-07-18-v1"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_assessment_bundle(arguments.assessment)
    assessment = bundle["assessment"]
    calibration = bundle["calibration"]
    print(
        json.dumps(
            {
                "assessment_id": assessment["assessment_id"],
                "assessment_status": assessment["atlas_decision"]["status"],
                "facility_leads": calibration["facility_lead_count"],
                "network_requests": 0,
                "numeric_series": calibration["numeric_series_count"],
                "official_artifacts": len(assessment["official_artifacts"]),
                "raw_artifacts_retained": assessment["coverage_assessment"][
                    "raw_artifacts_retained"
                ],
                "unique_facility_count": calibration["unique_facility_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
