#!/usr/bin/env python3
"""Validate the frozen Ireland planning-observation release offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.ireland_planning import (
    MANIFEST_FILENAME,
    RELEASE_ID,
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
    summary = bundle["summary"]
    print(
        json.dumps(
            {
                "baseline_exact_phrase_count": summary[
                    "baseline_exact_phrase_count"
                ],
                "extension_count": summary["extension_count"],
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "matched_planning_application_observations": summary[
                    "matched_observation_count"
                ],
                "network_requests": 0,
                "open_raw_artifacts_retained": assessment[
                    "retrieval_batch"
                ]["open_raw_artifacts_retained"],
                "precision_review_rows_retrieved": assessment[
                    "retrieval_batch"
                ]["precision_review_rows_retrieved"],
                "release_id": assessment["release_id"],
                "source_total_rows": assessment["coverage_assessment"][
                    "source_total_rows"
                ],
                "unique_site_count": summary["unique_site_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
