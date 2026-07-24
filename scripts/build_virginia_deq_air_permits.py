#!/usr/bin/env python3
"""Rebuild an exact copy of the frozen Virginia DEQ air-permit evidence lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.virginia_deq_air_permits import (
    ASSESSMENT_ID,
    MANIFEST_FILENAME,
    build_assessment_bundle,
    sha256_bytes,
    validate_assessment_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_BUNDLE = PROJECT_ROOT / "source_assessments" / ASSESSMENT_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--source-bundle",
        type=Path,
        default=DEFAULT_SOURCE_BUNDLE,
        help="Validated frozen input bundle (default: the repository snapshot)",
    )
    result.add_argument("--output-dir", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    source = validate_assessment_bundle(arguments.source_bundle)
    output = build_assessment_bundle(
        arguments.output_dir,
        source["assessment"],
        source["issued_permits"],
        source["applications"],
    )
    manifest_digest = sha256_bytes((output / MANIFEST_FILENAME).read_bytes())
    print(
        json.dumps(
            {
                "application_rows": len(source["applications"]["records"]),
                "assessment_id": ASSESSMENT_ID,
                "issued_permit_rows": len(source["issued_permits"]["records"]),
                "manifest_sha256": manifest_digest,
                "network_requests": 0,
                "output": str(output),
                "rights_status": source["assessment"]["atlas_decision"]["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
