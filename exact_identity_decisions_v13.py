"""Workspace-layout compatibility import for exact-identity v13."""

from .datacenter_atlas.exact_identity_decisions_v13 import *  # noqa: F401,F403
from .datacenter_atlas.exact_identity_decisions_v13 import (  # noqa: F401
    _assert_forbidden_lineage_absent,
    _canonical_json,
    _guard_state,
    _require_guard_state,
    _v13_document,
)
