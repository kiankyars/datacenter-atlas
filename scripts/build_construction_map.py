#!/usr/bin/env python3
"""Build a deterministic browser map from a frozen construction master."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.construction_map import write_construction_map


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--master-dir", type=Path, required=True)
    result.add_argument("--master-definition", type=Path, required=True)
    result.add_argument("--map-definition", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = write_construction_map(
        arguments.master_dir,
        arguments.output_dir,
        master_definition_path=arguments.master_definition,
        map_definition_path=arguments.map_definition,
        freeze=True,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
