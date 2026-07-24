"""Workspace-layout alias for the construction-map v6 implementation."""

from __future__ import annotations

import sys

from .datacenter_atlas import construction_map_v6 as _implementation


sys.modules[__name__] = _implementation
