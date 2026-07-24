#!/usr/bin/env python3
"""Publish the immutable Aalsmeer/BUE1 official-coordinate assessment."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from datacenter_atlas.official_coordinate_assessment_aalsmeer_bue1_20260722 import (
        main as module_main,
    )

    return module_main()


if __name__ == "__main__":
    raise SystemExit(main())
