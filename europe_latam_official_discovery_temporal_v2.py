"""Compatibility import for the Europe/LatAm temporal correction."""

from .datacenter_atlas.europe_latam_official_discovery_temporal_v2 import *  # noqa: F403
from .datacenter_atlas.europe_latam_official_discovery_temporal_v2 import (  # noqa: F401
    _semantic_source,
    _validate_raw_capture,
    _validate_source_collisions,
    _validate_source_successor,
)
