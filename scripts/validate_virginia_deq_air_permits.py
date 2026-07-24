#!/usr/bin/env python3
"""Validate the frozen Virginia DEQ air-permit evidence lane offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.virginia_deq_air_permits import (
    ASSESSMENT_ID,
    MANIFEST_FILENAME,
    sha256_bytes,
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
    issued = bundle["issued_permits"]
    applications = bundle["applications"]
    output = {
        "application_document_links": applications["document_inventory"][
            "total_document_links"
        ],
        "application_rows": len(applications["records"]),
        "application_status_counts": {"application_under_review": 1},
        "assessment_id": assessment["assessment_id"],
        "construction_verified_rows": assessment["coverage_assessment"][
            "construction_verified_rows"
        ],
        "distinct_resolved_issued_document_urls": issued["document_inventory"][
            "distinct_resolved_urls"
        ],
        "issued_permit_document_rows": len(issued["records"]),
        "issued_permit_status_counts": {"issued_permit": len(issued["records"])},
        "manifest_sha256": sha256_bytes(
            (arguments.assessment / MANIFEST_FILENAME).read_bytes()
        ),
        "network_requests": 0,
        "page_widget_reported_rows": issued["count_reconciliation"][
            "page_widget_reported_rows"
        ],
        "parsed_table_rows": issued["count_reconciliation"]["parsed_table_rows"],
        "publication_eligible_rows": assessment["coverage_assessment"][
            "publication_eligible_rows"
        ],
        "rights_status": assessment["atlas_decision"]["status"],
        "typed_facility_capacity_rows": assessment["coverage_assessment"][
            "typed_facility_capacity_rows"
        ],
        "typed_facility_energy_rows": assessment["coverage_assessment"][
            "typed_facility_energy_rows"
        ],
        "unique_physical_site_count": issued["unique_physical_site_count"],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
