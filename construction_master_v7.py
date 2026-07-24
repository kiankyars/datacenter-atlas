"""Workspace-layout alias for the construction-master v7 implementation."""

from __future__ import annotations

import sys

from .datacenter_atlas import construction_master_v7 as _implementation


sys.modules[__name__] = _implementation
