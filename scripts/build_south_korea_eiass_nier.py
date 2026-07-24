#!/usr/bin/env python3
"""Build the South Korea EIASS/NIER assessment without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.south_korea_eiass_nier import (
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    canonical_json,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    return result


def _write_definition(path: Path) -> None:
    expected = canonical_json(source_definition())
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError("existing source definition differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    _write_definition(arguments.definition)
    write_release_bundle(PINNED_RETRIEVAL_INVENTORY, arguments.output)
    bundle = validate_release_bundle(
        arguments.output,
        definition_path=arguments.definition,
    )
    assessment = bundle["assessment"]
    retrieval = assessment["retrieval_batch"]
    print(
        json.dumps(
            {
                "build_mode": "offline_from_pinned_audit_metadata",
                "build_network_requests": 0,
                "completed_response_requests": retrieval[
                    "completed_response_requests"
                ],
                "direct_request_attempt_cap": retrieval[
                    "direct_request_attempt_cap"
                ],
                "direct_request_attempts": retrieval[
                    "direct_request_attempts"
                ],
                "failed_network_requests": retrieval[
                    "failed_network_requests"
                ],
                "release_id": RELEASE_ID,
                "result_bearing_api_requests": retrieval[
                    "result_bearing_api_requests"
                ],
                "result_count": assessment["coverage"]["result_count"],
                "source_rows": assessment["atlas_decision"][
                    "retained_source_rows"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
