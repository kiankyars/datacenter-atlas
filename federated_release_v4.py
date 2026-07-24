"""Compatibility alias for the versioned federation v4 carrier."""

import sys

from .datacenter_atlas import federated_release_v4 as _implementation


sys.modules[__name__] = _implementation
