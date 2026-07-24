#!/usr/bin/env python3
"""Publish the frozen AWS Clinton adaptive-reuse official-source artifact."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.aws_official_clinton_adaptive_reuse_current_build_gap_20260722 import main


if __name__ == "__main__":
    raise SystemExit(main())
