"""Compatibility alias for the Middle East and Turkiye gap carrier."""

import sys

from .datacenter_atlas import (
    global_official_builds_middle_east_turkiye_gap_20260721 as _implementation,
)


sys.modules[__name__] = _implementation
