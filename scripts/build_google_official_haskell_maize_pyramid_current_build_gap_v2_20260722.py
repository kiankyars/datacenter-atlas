#!/usr/bin/env python3
"""Publish or validate the chronology-correct Google tranche v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.google_official_haskell_maize_pyramid_current_build_gap_v2_20260722 import (  # noqa: E402
    publish_artifact,
    validate_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorded-at", help="canonical fused UTC timestamp")
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.validate_only:
        if arguments.recorded_at:
            parser.error("--recorded-at cannot be used with --validate-only")
        manifest = validate_artifact()
        status = "validated"
    else:
        manifest = publish_artifact(arguments.recorded_at) if arguments.recorded_at else publish_artifact()
        status = "published"
    print(
        json.dumps(
            {
                "artifact_id": manifest["artifact_id"],
                "recorded_at": manifest["recorded_at"],
                "rejected_incident": manifest["incident_lineage"]["artifact_id"],
                "source_records": manifest["curated_source_records"],
                "status": status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
