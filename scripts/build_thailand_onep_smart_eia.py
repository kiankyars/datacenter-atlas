#!/usr/bin/env python3
"""Build the frozen Thailand ONEP Smart EIA source assessment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.thailand_onep_smart_eia import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    canonical_json,
    is_frozen_release,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    parser.add_argument(
        "--write-definition",
        action="store_true",
        help="write the canonical checked-in definition before building",
    )
    parser.add_argument(
        "--freeze", action=argparse.BooleanOptionalAction, default=True
    )
    arguments = parser.parse_args(argv)
    if arguments.write_definition:
        if arguments.definition.exists() or arguments.definition.is_symlink():
            raise ValueError("definition output already exists")
        arguments.definition.parent.mkdir(parents=True, exist_ok=True)
        arguments.definition.write_bytes(canonical_json(source_definition()))
    write_release_bundle(arguments.output, freeze=arguments.freeze)
    bundle = validate_release_bundle(
        arguments.output,
        definition_path=arguments.definition,
        require_frozen=arguments.freeze,
    )
    assessment = bundle["assessment"]
    print(
        json.dumps(
            {
                "frozen": is_frozen_release(arguments.output),
                "http_requests": 0,
                "manifest_sha256": sha256_bytes(
                    (arguments.output / MANIFEST_FILENAME).read_bytes()
                ),
                "mode": "offline_build_and_validate",
                "output": str(arguments.output),
                "release_id": RELEASE_ID,
                "retained_source_rows": assessment["atlas_decision"][
                    "retained_source_rows"
                ],
                "source_report_total_count_observed": assessment["coverage"][
                    "source_report_total_count_observed"
                ],
                "status": assessment["atlas_decision"]["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
