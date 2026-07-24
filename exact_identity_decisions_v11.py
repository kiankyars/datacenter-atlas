"""Workspace-layout compatibility import for exact-identity v11."""

from .datacenter_atlas.exact_identity_decisions_v11 import *  # noqa: F401,F403
from .datacenter_atlas.exact_identity_decisions_v11 import (  # noqa: F401
    _assert_forbidden_lineage_absent,
    _canonical_json,
    _guard_state,
    _require_configured_federation,
    _require_guard_state,
    _v11_document,
)

