"""Compatibility alias for the immutable federation v37 builder."""

import sys

from .datacenter_atlas import federation_v37 as _implementation


sys.modules[__name__] = _implementation
