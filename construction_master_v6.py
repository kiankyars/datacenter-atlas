"""Workspace-layout alias for the construction-master v6 implementation."""

from __future__ import annotations

import sys

from .datacenter_atlas import construction_master_v6 as _implementation


sys.modules[__name__] = _implementation
