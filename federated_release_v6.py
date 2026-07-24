"""Compatibility alias for the governed federation v6 carrier."""

import sys

from .datacenter_atlas import federated_release_v6 as _implementation


sys.modules[__name__] = _implementation
