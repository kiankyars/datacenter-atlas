"""Compatibility alias for the versioned federation v5 carrier."""

import sys

from .datacenter_atlas import federated_release_v5 as _implementation


sys.modules[__name__] = _implementation
