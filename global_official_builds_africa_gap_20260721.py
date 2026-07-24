"""Compatibility alias for the Africa official-build gap carrier."""

import sys

from .datacenter_atlas import (
    global_official_builds_africa_gap_20260721 as _implementation,
)


sys.modules[__name__] = _implementation
