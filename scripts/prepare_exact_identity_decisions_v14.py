#!/usr/bin/env python3
"""Run private prepublication validation for exact-identity v14."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.exact_identity_decisions_v14 import (
    prepare_main,
)

if __name__ == "__main__":
    raise SystemExit(prepare_main())
