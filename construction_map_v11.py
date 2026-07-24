"""Workspace-layout alias for the construction-map v11 implementation."""

from __future__ import annotations

import sys

from .datacenter_atlas import construction_map_v11 as _implementation


sys.modules[__name__] = _implementation
