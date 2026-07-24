#!/usr/bin/env python3
"""Build or verify the immutable v35 federation successor."""

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.federation_v35 import main


if __name__ == "__main__":
    raise SystemExit(main())
