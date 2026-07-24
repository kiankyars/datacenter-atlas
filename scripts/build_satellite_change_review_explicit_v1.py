#!/usr/bin/env python3
"""Publish or validate the explicit-v1 identity-blind analyst review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change_blind_preparation_explicit_v1 import (
    suggested_generated_at,
)
from datacenter_atlas.satellite_change_review_explicit_v1 import (
    OUTPUT_PATH,
    publish_analyst_review,
    validate_analyst_review,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--generated-at", default=suggested_generated_at())
    result.add_argument("--validate-only", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        result = validate_analyst_review(OUTPUT_PATH)
    else:
        result = publish_analyst_review(arguments.generated_at, OUTPUT_PATH)
    print(
        json.dumps(
            {
                "generated_at": result["generated_at"],
                "manifest_sha256": hashlib.sha256(
                    (OUTPUT_PATH / "manifest.json").read_bytes()
                ).hexdigest(),
                "output": str(OUTPUT_PATH),
                "review_id": result["review_id"],
                "summary": result["summary"],
                "tree_inventory": result["tree_inventory"],
                "validated": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
