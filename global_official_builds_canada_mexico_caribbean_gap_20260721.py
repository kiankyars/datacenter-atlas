"""Compatibility alias for the Canada/Mexico/Caribbean gap carrier."""

import sys

from .datacenter_atlas import (
    global_official_builds_canada_mexico_caribbean_gap_20260721 as _implementation,
)


sys.modules[__name__] = _implementation
