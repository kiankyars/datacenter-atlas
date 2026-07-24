#!/usr/bin/env python3
"""Validate a frozen Italy MASE VIA/VAS assessment without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.italy_mase_via_vas import (
    ItalyMASEVIAVASError,
    RELEASE_ID,
    is_frozen_release,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("release", nargs="?", type=Path, default=DEFAULT_RELEASE)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(arguments.release)
    assessment = bundle["assessment"]
    print(
        json.dumps(
            {
                "capture_window": assessment["coverage"]["capture_window"],
                "classification_counts": assessment["classification_counts"],
                "counts": assessment["counts"],
                "frozen": is_frozen_release(arguments.release),
                "release": str(arguments.release),
                "release_id": RELEASE_ID,
                "rights_decision": bundle["manifest"]["rights_decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ItalyMASEVIAVASError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
