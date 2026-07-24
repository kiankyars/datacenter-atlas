"""Compatibility alias for coordinate-only open seed v85."""

import sys

from .datacenter_atlas import open_seed_v85 as _implementation


sys.modules[__name__] = _implementation
