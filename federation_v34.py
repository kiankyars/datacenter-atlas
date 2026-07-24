"""Compatibility alias for the immutable federation v34 builder."""

import sys

from .datacenter_atlas import federation_v34 as _implementation


sys.modules[__name__] = _implementation
