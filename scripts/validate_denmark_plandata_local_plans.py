#!/usr/bin/env python3
"""Validate the frozen Denmark Plandata.dk assessment without network I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.denmark_plandata_local_plans import (
    RELEASE_ID,
    is_frozen_release,
    sha256_bytes,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "release",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "source_assessments" / RELEASE_ID,
    )
    parser.add_argument(
        "--definition",
        type=Path,
        default=PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json",
    )
    arguments = parser.parse_args(argv)
    bundle = validate_release_bundle(
        arguments.release, definition_path=arguments.definition
    )
    print(
        json.dumps(
            {
                "controlled_request_count": bundle["capture"][
                    "controlled_request_count"
                ],
                "counts": bundle["assessment"]["counts"],
                "frozen": is_frozen_release(arguments.release),
                "http_requests": 0,
                "manifest_sha256": sha256_bytes(
                    (arguments.release / "manifest.json").read_bytes()
                ),
                "mode": "offline_validate",
                "release_id": RELEASE_ID,
                "status": bundle["assessment"]["atlas_decision"]["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
