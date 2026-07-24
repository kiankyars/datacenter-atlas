"""Compatibility alias for five-source open seed v86."""

import sys

from .datacenter_atlas import open_seed_v86 as _implementation


sys.modules[__name__] = _implementation
