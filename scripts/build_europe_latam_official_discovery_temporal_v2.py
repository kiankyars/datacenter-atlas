#!/usr/bin/env python3
"""Build the Europe/LatAm temporal incident and accepted v2 successor."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.europe_latam_official_discovery_temporal_v2 import main


if __name__ == "__main__":
    raise SystemExit(main())
