#!/usr/bin/env python3
"""Build the collision-isolated official open seed v51 exactly once."""

from __future__ import annotations

from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.open_seed_v51 import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
