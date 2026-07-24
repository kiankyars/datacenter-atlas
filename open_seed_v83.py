"""Compatibility alias for append-only open seed v83."""

import sys

from .datacenter_atlas import open_seed_v83 as _implementation


sys.modules[__name__] = _implementation
