"""Compatibility shim for the private/prepublication coverage-audit v32 API."""

from .datacenter_atlas.coverage_audit_v32 import *  # noqa: F401,F403
from .datacenter_atlas.coverage_audit_v32 import (  # noqa: F401
    FORBIDDEN_STALE_ACTIVE_TOKENS,
    V83_SUPPORT_ID,
    _canonical_json,
    _require_inputs,
    _timeline_gate,
    legacy,
)
