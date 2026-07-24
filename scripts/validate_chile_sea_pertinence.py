#!/usr/bin/env python3
"""Validate the frozen Chile SEA e-Pertinencia assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.chile_sea_pertinence import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    is_frozen_release,
    sha256_bytes,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(arguments.release)
    assessment = bundle["assessment"]
    selection = assessment["selection_assessment"]
    print(
        json.dumps(
            {
                "construction_evidence_rows": assessment["coverage_assessment"][
                    "construction_evidence_rows"
                ],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "network_requests": 0,
                "operation_evidence_rows": assessment["coverage_assessment"][
                    "operation_evidence_rows"
                ],
                "raw_query_hits": selection["raw_query_hits"],
                "release_id": RELEASE_ID,
                "review_candidate_rows": selection["review_candidate_rows"],
                "terminal_process_exclusion_rows": selection[
                    "terminal_process_exclusion_rows"
                ],
                "unique_physical_site_count": assessment["coverage_assessment"][
                    "unique_physical_site_count"
                ],
                "unique_qid_process_rows": selection["unique_qid_process_rows"],
                "validation_mode": "offline",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
