#!/usr/bin/env python3
"""Publish the governed official current-build gap tranche."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.global_official_current_build_gap_20260721 import build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recorded-at")
    arguments = parser.parse_args()
    print(json.dumps(build(recorded_at=arguments.recorded_at), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
