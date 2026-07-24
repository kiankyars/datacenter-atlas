#!/usr/bin/env python3
"""Build and atomically publish a deterministic coverage audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.coverage_audit import write_coverage_audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    audit = write_coverage_audit(args.definition, args.output_dir)
    print(
        json.dumps(
            {
                "audit_id": audit["audit_id"],
                "generated_at": audit["generated_at"],
                "source_scoped_entity_records": audit["totals"][
                    "source_scoped_entity_records"
                ],
                "coverage_groups": len(audit["groups"]),
                "output_dir": str(args.output_dir.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
