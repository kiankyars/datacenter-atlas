#!/usr/bin/env python3
"""Publish the governed four-candidate unresolved-build artifact."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.global_official_builds_unresolved_four_20260721 import main


if __name__ == "__main__":
    raise SystemExit(main())
