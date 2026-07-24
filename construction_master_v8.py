"""Workspace-layout alias for the construction-master v8 implementation."""

from __future__ import annotations

import sys

from .datacenter_atlas import construction_master_v8 as _implementation


sys.modules[__name__] = _implementation
