"""Compatibility alias for the governed US operator-gap tranche."""

import sys

from .datacenter_atlas import global_official_builds_us_operator_gap_20260721 as _implementation


sys.modules[__name__] = _implementation
