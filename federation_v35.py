"""Compatibility alias for the immutable federation v35 builder."""

import sys

from .datacenter_atlas import federation_v35 as _implementation


sys.modules[__name__] = _implementation
