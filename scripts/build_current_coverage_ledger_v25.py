#!/usr/bin/env python3
"""Publish or validate the immutable current-coverage ledger v25."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.current_coverage_v25 import (  # noqa: E402
    publish_current_coverage_ledger_v25,
    validate_current_coverage_ledger_v25,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at", help="canonical UTC publication timestamp")
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.validate_only:
        if arguments.generated_at:
            parser.error("--generated-at cannot be combined with --validate-only")
        manifest = validate_current_coverage_ledger_v25()
    else:
        if not arguments.generated_at:
            parser.error("--generated-at is required for first publication")
        manifest = publish_current_coverage_ledger_v25(arguments.generated_at)
    print(
        json.dumps(
            {
                "generated_at": manifest["generated_at"],
                "ledger_id": manifest["ledger_id"],
                "artifacts": manifest["successor_delta"]["final_entries"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
