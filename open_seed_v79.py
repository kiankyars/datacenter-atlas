"""Compatibility alias for append-only open seed v79."""

import sys

from .datacenter_atlas import open_seed_v79 as _implementation


sys.modules[__name__] = _implementation
