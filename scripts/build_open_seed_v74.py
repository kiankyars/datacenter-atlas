#!/usr/bin/env python3
"""Build and freeze the coordinate-only open seed v74."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v74 import main


if __name__ == "__main__":
    raise SystemExit(main())
