#!/usr/bin/env python3
"""Validate the immutable, metadata-only PWC Build-Out assessment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.pwc_build_out_assessment import validate_assessment_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "pwc-build-out-2026-07-18-v1"
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
                "building_records": assessment["count_assessment"][
                    "building_records"
                ],
                "campus_project_records": assessment["count_assessment"][
                    "campus_project_records"
                ],
                "feature_rows_retrieved": assessment["retrieval_batch"][
                    "feature_rows_retrieved"
                ],
                "layer_schema_count": len(schema["layers"]),
                "network_requests": 0,
                "planning_site_application_records": assessment[
                    "count_assessment"
                ]["planning_site_application_records"],
                "raw_artifacts_retained": assessment["retrieval_batch"][
                    "raw_artifacts_retained"
                ],
                "unique_site_count": assessment["count_assessment"][
                    "unique_site_count"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
