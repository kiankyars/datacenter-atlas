#!/usr/bin/env python3
"""Publish open seed v96 only with explicit command-line authorization."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_v96 import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish-authorized",
        action="store_true",
        help="cross the atomic no-replace publication barrier",
    )
    arguments = parser.parse_args()
    if not arguments.publish_authorized:
        parser.error("publication requires --publish-authorized")
    raise SystemExit(main(publication_authorized=True))
