#!/usr/bin/env python3
"""Validate the frozen NSW Major Projects source assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.nsw_major_projects import (
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
    coverage = assessment["coverage_assessment"]
    print(
        json.dumps(
            {
                "active_base_rows": coverage["active_base_rows"],
                "active_detail_rows": len(bundle["active_observations"]),
                "active_modification_rows": coverage["active_modification_rows"],
                "base_rows": coverage["base_rows"],
                "construction_verified_rows": coverage["construction_verified_rows"],
                "coordinates_retained_rows": coverage["coordinates_retained_rows"],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "modification_rows": coverage["modification_rows"],
                "network_requests": 0,
                "power_statement_rows": coverage["power_statement_rows"],
                "raw_inventory_sha256": assessment["retrieval_batch"][
                    "raw_inventory_sha256"
                ],
                "release_id": RELEASE_ID,
                "rights_status": assessment["atlas_decision"]["status"],
                "stage_counts": assessment["selection_assessment"]["stage_counts"],
                "total_list_rows": len(bundle["list_observations"]),
                "unique_physical_site_count": coverage["unique_physical_site_count"],
                "validation_mode": "offline",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
