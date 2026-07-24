#!/usr/bin/env python3
"""Extract a deterministic review-only data-centre news candidate bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.gdelt import write_candidate_bundle


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument(
        "--generated-at",
        required=True,
        help="Explicit timezone-aware timestamp for reproducible candidate provenance",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = write_candidate_bundle(
        arguments.input,
        arguments.output,
        generated_at=arguments.generated_at,
    )
    print(
        json.dumps(
            {
                "manifest": str((arguments.output / "manifest.json").resolve()),
                "candidates": str((arguments.output / "candidates.jsonl").resolve()),
                "counts": manifest["counts"],
                "scope": manifest["scope"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

