"""Compatibility alias for the fail-closed government-source gap artifact."""

import sys

from .datacenter_atlas import (
    global_official_builds_government_gap_20260721 as _implementation,
)


sys.modules[__name__] = _implementation

