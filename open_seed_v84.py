"""Compatibility alias for append-only open seed v84."""

import sys

from .datacenter_atlas import open_seed_v84 as _implementation


sys.modules[__name__] = _implementation
