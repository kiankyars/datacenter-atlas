#!/usr/bin/env python3
"""Validate the frozen Poland GDOŚ/SIOS/Ekoportal assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.poland_gdos_sios_ekoportal import (
    RELEASE_ID,
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
    retrieval = assessment["retrieval_batch"]
    print(
        json.dumps(
            {
                "controlled_audit_request_attempts": retrieval[
                    "direct_request_attempts"
                ],
                "release_id": RELEASE_ID,
                "result_bearing_search_requests": retrieval[
                    "result_bearing_search_requests"
                ],
                "result_count": assessment["coverage"]["result_count"],
                "source_rows": assessment["atlas_decision"][
                    "retained_source_rows"
                ],
                "status": assessment["atlas_decision"]["status"],
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
