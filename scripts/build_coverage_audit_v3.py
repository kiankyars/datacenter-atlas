#!/usr/bin/env python3
"""Build, validate, freeze, and publish a deterministic coverage audit v3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.coverage_audit_v3 import write_coverage_audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    audit = write_coverage_audit(args.definition, args.output_dir)
    print(
        json.dumps(
            {
                "as_of": audit["as_of"],
                "audit_id": audit["audit_id"],
                "coverage_groups": len(audit["groups"]),
                "generated_at": audit["generated_at"],
                "methodology_support_artifacts": len(
                    audit["inputs"]["methodology_support_artifacts"]
                ),
                "output_dir": str(args.output_dir.resolve()),
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
