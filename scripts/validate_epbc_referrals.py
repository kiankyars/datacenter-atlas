#!/usr/bin/env python3
"""Validate a frozen EPBC referrals metadata-only assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.epbc_referrals import (
    EPBCReferralsError,
    RELEASE_ID,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("release", nargs="?", type=Path, default=DEFAULT_RELEASE)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(arguments.release)
    print(
        json.dumps(
            {
                "classification_counts": bundle["query_summary"][
                    "classification_counts"
                ],
                "network_request_count": bundle["retrieval_inventory"][
                    "network_request_count"
                ],
                "release": str(arguments.release),
                "release_id": RELEASE_ID,
                "status": bundle["assessment"]["release_decision"]["status"],
                "unique_physical_site_count": bundle["assessment"][
                    "coverage_assessment"
                ]["physical_unique_site_count"],
                "unique_referral_count": bundle["query_summary"][
                    "unique_referral_count"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EPBCReferralsError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

