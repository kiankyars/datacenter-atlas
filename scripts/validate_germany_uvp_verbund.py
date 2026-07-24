#!/usr/bin/env python3
"""Validate the frozen Germany UVP-Verbund assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.germany_uvp_verbund import (
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
    print(
        json.dumps(
            {
                "assessment_artifact_indexing_permitted": assessment[
                    "atlas_decision"
                ]["assessment_artifact_indexing_permitted"],
                "closed_query_completed": assessment["coverage_assessment"][
                    "closed_query_completed"
                ],
                "controlled_network_requests": assessment["retrieval_batch"][
                    "controlled_network_requests"
                ],
                "direct_rows": assessment["coverage_assessment"][
                    "classification_counts"
                ]["direct"],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "publication_observation_rows": assessment["atlas_decision"][
                    "publication_observation_rows"
                ],
                "release_id": RELEASE_ID,
                "result_count": assessment["coverage_assessment"]["result_count"],
                "unique_physical_site_count": assessment["coverage_assessment"][
                    "unique_physical_site_count"
                ],
                "validation_mode": "offline",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
