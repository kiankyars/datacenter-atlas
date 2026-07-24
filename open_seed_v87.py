"""Compatibility alias for open seed v87."""

import sys

from .datacenter_atlas import open_seed_v87 as _implementation


sys.modules[__name__] = _implementation
