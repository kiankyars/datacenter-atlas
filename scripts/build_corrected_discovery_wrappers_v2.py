#!/usr/bin/env python3
"""Build and freeze timestamp-corrected discovery wrappers v2."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.corrected_discovery_wrappers_v2 import main


if __name__ == "__main__":
    raise SystemExit(main())
