#!/usr/bin/env python3
"""Validate the frozen Malaysia KPKT OSC 3 Plus assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.malaysia_kpkt_osc3plus import (
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
                "agenda_presentation_item_count": assessment["coverage"][
                    "agenda_presentation_item_count"
                ],
                "assessment_status": assessment["atlas_decision"]["status"],
                "controlled_audit_requests": assessment["retrieval_batch"][
                    "controlled_audit_requests"
                ],
                "frozen": is_frozen_release(arguments.release),
                "manifest_sha256": sha256_bytes(
                    (arguments.release / MANIFEST_FILENAME).read_bytes()
                ),
                "meeting_page_requests": assessment["retrieval_batch"][
                    "meeting_page_requests"
                ],
                "pbt_calendar_requests": assessment["retrieval_batch"][
                    "pbt_calendar_requests"
                ],
                "project_count": assessment["coverage"]["project_count"],
                "release_id": RELEASE_ID,
                "result_bearing_traversal_requests": assessment[
                    "retrieval_batch"
                ]["result_bearing_traversal_requests"],
                "result_count": assessment["coverage"]["result_count"],
                "site_count": assessment["coverage"]["site_count"],
                "source_rows": assessment["atlas_decision"][
                    "retained_source_rows"
                ],
                "validation_mode": "offline",
                "validation_network_requests": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
