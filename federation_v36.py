"""Compatibility alias for the immutable federation v36 builder."""

import sys

from .datacenter_atlas import federation_v36 as _implementation


sys.modules[__name__] = _implementation
