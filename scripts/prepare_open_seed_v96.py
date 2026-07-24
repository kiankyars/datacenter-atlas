#!/usr/bin/env python3
"""Run the governed v96 private prepublication carrier; never publish."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v96 import main


if __name__ == "__main__":
    raise SystemExit(main())
