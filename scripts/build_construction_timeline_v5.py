#!/usr/bin/env python3
"""Publish or validate the immutable open-seed-v71 construction timeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.construction_timeline_v5 import (
    BUNDLE,
    DEFINITION,
    validate_construction_timeline_bundle,
    write_construction_timeline_bundle,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", type=Path, default=DEFINITION)
    result.add_argument("--output-dir", type=Path, default=BUNDLE)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--verify-inputs", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        manifest = validate_construction_timeline_bundle(
            arguments.output_dir,
            definition_path=arguments.definition,
            verify_inputs=arguments.verify_inputs,
        )
    else:
        manifest = write_construction_timeline_bundle(
            arguments.definition,
            arguments.output_dir,
        )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
