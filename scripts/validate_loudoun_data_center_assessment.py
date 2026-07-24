#!/usr/bin/env python3
"""Validate the frozen Loudoun metadata-and-aggregates assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.loudoun_data_center_assessment import (
    ASSESSMENT_ID,
    validate_assessment_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = PROJECT_ROOT / "source_assessments" / ASSESSMENT_ID


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
                "assessor_official_total": calibration["assessor_report"][
                    "official_total"
                ],
                "assessor_rows_reconcile": calibration["assessor_report"][
                    "category_rows_reconcile_to_official_total"
                ],
                "existing_parcel_records": assessment["count_assessment"][
                    "existing_parcel_records"
                ],
                "feature_rows_retrieved": assessment["retrieval_batch"][
                    "feature_rows_retrieved"
                ],
                "network_requests": 0,
                "pipeline_parcel_records": assessment["count_assessment"][
                    "pipeline_parcel_records"
                ],
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
