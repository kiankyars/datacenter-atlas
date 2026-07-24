#!/usr/bin/env python3
"""Validate the immutable, metadata-only Cleanview assessment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.cleanview_assessment import validate_assessment_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "cleanview-2026-07-18-v1"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_assessment_bundle(arguments.assessment)
    assessment = bundle["assessment"]
    schema = bundle["schema"]
    print(
        json.dumps(
            {
                "assessment_id": assessment["assessment_id"],
                "assessment_status": assessment["atlas_decision"]["status"],
                "current_record_count": assessment["coverage_assessment"][
                    "live_record_count"
                ],
                "data_endpoint_requests": assessment["retrieval_batch"][
                    "data_endpoint_requests"
                ],
                "facility_leads": schema["facility_lead_count"],
                "official_artifacts": len(assessment["official_artifacts"]),
                "raw_artifacts_retained": assessment["retrieval_batch"][
                    "raw_artifacts_retained"
                ],
                "schema_fields": schema["response"]["record_field_count"],
                "unique_facility_count": schema["unique_facility_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
