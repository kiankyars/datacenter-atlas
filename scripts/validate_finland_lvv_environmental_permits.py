#!/usr/bin/env python3
"""Validate the frozen Finland LVV assessment entirely offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.finland_lvv_environmental_permits import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    is_frozen_release,
    sha256_bytes,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(
        arguments.release,
        definition_path=arguments.definition,
    )
    assessment = bundle["assessment"]
    print(
        json.dumps(
            {
                "assessment_status": assessment["atlas_decision"]["status"],
                "controlled_audit_requests": assessment["retrieval_batch"][
                    "controlled_audit_requests"
                ],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "permit_case_count": assessment["coverage"][
                    "license_or_permit_case_count"
                ],
                "project_count": assessment["coverage"]["project_count"],
                "publication_count": assessment["coverage"]["publication_count"],
                "release_id": RELEASE_ID,
                "result_bearing_search_requests": assessment["retrieval_batch"][
                    "result_bearing_search_requests"
                ],
                "result_count": assessment["coverage"]["result_count"],
                "site_count": assessment["coverage"]["site_count"],
                "source_rows": assessment["atlas_decision"]["retained_source_rows"],
                "validation_network_requests": 0,
                "validation_mode": "offline",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
