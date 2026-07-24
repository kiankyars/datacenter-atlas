#!/usr/bin/env python3
"""Publish or validate the immutable v83/federation-v34 coverage audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.coverage_audit_v30 import (  # noqa: E402
    publish_coverage_audit_v30,
    validate_coverage_audit_v30,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at", help="canonical UTC publication timestamp")
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.validate_only:
        if arguments.generated_at:
            parser.error("--generated-at cannot be combined with --validate-only")
        audit = validate_coverage_audit_v30()
    else:
        if not arguments.generated_at:
            parser.error("--generated-at is required for first publication")
        audit = publish_coverage_audit_v30(arguments.generated_at)
    print(
        json.dumps(
            {
                "audit_id": audit["audit_id"],
                "generated_at": audit["generated_at"],
                "coverage_groups": len(audit["groups"]),
                "source_scoped_entity_records": audit["totals"][
                    "source_scoped_entity_records"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
