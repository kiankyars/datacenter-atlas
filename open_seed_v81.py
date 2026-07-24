"""Compatibility alias for append-only open seed v81."""

import sys

from .datacenter_atlas import open_seed_v81 as _implementation


sys.modules[__name__] = _implementation
