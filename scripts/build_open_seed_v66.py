#!/usr/bin/env python3
"""Build and freeze the strict v65-successor open seed v66."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v66 import main


if __name__ == "__main__":
    raise SystemExit(main())
