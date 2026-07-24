#!/usr/bin/env python3
"""Build and publish the append-only open seed v92 release."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v92 import main


if __name__ == "__main__":
    raise SystemExit(main())
