#!/usr/bin/env python3
"""Offline validator for the frozen Singapore BCA Green Mark release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.singapore_bca_green_mark import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    is_frozen_release,
    sha256_bytes,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--definition",
        type=Path,
        default=PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json",
    )
    parser.add_argument(
        "--release",
        type=Path,
        default=PROJECT_ROOT / "source_assessments" / RELEASE_ID,
    )
    arguments = parser.parse_args(argv)
    bundle = validate_release_bundle(
        arguments.release, definition_path=arguments.definition
    )
    assessment = bundle["assessment"]
    print(
        json.dumps(
            {
                "certification_observation_count": assessment[
                    "certification_observation_count"
                ],
                "classification_counts": assessment["classification_counts"],
                "data_centre_match_union_count": assessment[
                    "data_centre_match_union_count"
                ],
                "frozen": is_frozen_release(arguments.release),
                "http_requests": 0,
                "lead_count": assessment["lead_count"],
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "mode": "offline_validate",
                "release_id": RELEASE_ID,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
