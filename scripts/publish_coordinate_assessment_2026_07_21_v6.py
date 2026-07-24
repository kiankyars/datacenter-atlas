#!/usr/bin/env python3
"""Publish the immutable site-coordinate assessment v6."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from datacenter_atlas.site_coordinate_assessment_v6 import main as module_main

    return module_main()


if __name__ == "__main__":
    raise SystemExit(main())
