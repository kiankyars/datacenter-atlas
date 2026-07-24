"""Compatibility alias for the strict frozen open-seed v86 queue."""

import sys

from .datacenter_atlas import satellite_queue_v86 as _implementation


sys.modules[__name__] = _implementation
