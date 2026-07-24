#!/usr/bin/env python3
"""Explicitly authorized final publisher for construction timeline v11."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datacenter_atlas.datacenter_atlas.construction_timeline_v11 import (
    publisher_main,
)

if __name__ == "__main__":
    raise SystemExit(publisher_main())
