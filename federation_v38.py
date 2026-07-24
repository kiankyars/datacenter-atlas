"""Compatibility alias for the governed federation v38 builder."""

import sys

from .datacenter_atlas import federation_v38 as _implementation


sys.modules[__name__] = _implementation
