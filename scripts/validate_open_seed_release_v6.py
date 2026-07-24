#!/usr/bin/env python3
"""Validate frozen open-seed v61 offline and byte-for-byte."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_release_v6 import validate_open_seed_release_v6


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("definition", type=Path)
    parser.add_argument("release", type=Path)
    arguments = parser.parse_args()
    manifest = validate_open_seed_release_v6(arguments.definition, arguments.release)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
