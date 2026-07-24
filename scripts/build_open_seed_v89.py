#!/usr/bin/env python3
"""Publish the immutable open-seed v89 successor."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v89 import main


if __name__ == "__main__":
    raise SystemExit(main())
