#!/usr/bin/env python3
"""Publish the immutable federation v32 partial-publication incident."""

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.federation_v32_incident import main


if __name__ == "__main__":
    raise SystemExit(main())
