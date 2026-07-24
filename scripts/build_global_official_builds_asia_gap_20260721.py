#!/usr/bin/env python3
"""Publish the Asia official-build gap assessment and source records."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.global_official_builds_asia_gap_20260721 import main


if __name__ == "__main__":
    raise SystemExit(main())
