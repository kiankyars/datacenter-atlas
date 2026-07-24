#!/usr/bin/env python3
"""Publish the frozen Sabey official current-build source artifact."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.sabey_official_current_build_gap_20260722 import main


if __name__ == "__main__":
    raise SystemExit(main())
