#!/usr/bin/env python3
"""Build or validate an immutable structural-candidate fusion bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.candidate_fusion import (  # noqa: E402
    CandidateFusionError,
    validate_candidate_fusion,
    write_candidate_fusion,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and fully reproduce an existing output",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.validate_only:
            manifest = validate_candidate_fusion(
                arguments.output, definition_path=arguments.definition
            )
        else:
            manifest = write_candidate_fusion(arguments.definition, arguments.output)
    except CandidateFusionError as error:
        print(f"candidate-fusion error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "format": manifest["format"],
                "generated_at": manifest["generated_at"],
                "output": str(arguments.output),
                "review_candidates": manifest["counts"]["primary_shortlist"][
                    "candidates_with_any_fusion_opportunity"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
