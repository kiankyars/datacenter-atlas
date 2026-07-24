"""Compatibility alias for the four-candidate unresolved-build artifact."""

import sys

from .datacenter_atlas import (
    global_official_builds_unresolved_four_20260721 as _implementation,
)


sys.modules[__name__] = _implementation
