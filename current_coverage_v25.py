"""Workspace-layout compatibility import for current-coverage ledger v25."""

from .datacenter_atlas.current_coverage_v25 import *  # noqa: F401,F403
from .datacenter_atlas.current_coverage_v25 import (  # noqa: F401
    _canonical_json,
    _require_dependencies_before,
    _require_inputs,
    _validate_bundle,
    _write_bundle,
)
