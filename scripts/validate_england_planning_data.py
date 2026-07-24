#!/usr/bin/env python3
"""Validate the frozen England Planning Data release without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.england_planning_data import (
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
    print(
        json.dumps(
            {
                "bulk_csv_sha256": bundle["inventory"]["source_file"]["sha256"],
                "explicit_planning_observations": len(bundle["observations"]),
                "explicit_context_classification_counts": bundle["assessment"][
                    "selection_assessment"
                ]["explicit_context_classification_counts"],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "network_requests": 0,
                "optional_incremental_counts": bundle["assessment"][
                    "selection_assessment"
                ]["optional_incremental_counts"],
                "release_id": RELEASE_ID,
                "source_rows": bundle["inventory"]["source_rows"],
                "validation_mode": "offline",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
