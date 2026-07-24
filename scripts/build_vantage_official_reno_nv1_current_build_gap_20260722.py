#!/usr/bin/env python3
"""Publish the frozen Vantage NV1/NV12 official-source artifact."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.vantage_official_reno_nv1_current_build_gap_20260722 import main


if __name__ == "__main__":
    raise SystemExit(main())
