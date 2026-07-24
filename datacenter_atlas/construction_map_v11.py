"""Frozen v27 successor carrier for the deterministic construction map.

The schema remains v2. This carrier byte-pins the accepted v26 carrier and
applies only the v27 master identity and exact v67 coordinate projection. It
creates no identity decision, current-status claim, or physical-site count.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "b91ee693bac8c3d627ed5ec126eca66efe2c6e421481c888c47f12e074bb7311"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v10.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v11 accepted-v26 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v10 changed; refusing v27 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v10", "construction_map_v11", 2),
    ("ConstructionMapV10Error", "ConstructionMapV11Error", 1),
    ("build_index_v10", "build_index_v11", 1),
    ("is_frozen_map_v10", "is_frozen_map_v11", 1),
    ("validate_map_definition_v10", "validate_map_definition_v11", 1),
    ("construction_master_v10", "construction_master_v11", 1),
    ("ConstructionMasterV10Error", "ConstructionMasterV11Error", 1),
    ("v26", "v27", 4),
    ("v62", "v67", 3),
    ("2026-07-21T05:05:01Z", "2026-07-21T08:05:01Z", 1),
    (
        'added_replacement_rows_unmapped": 167',
        'added_replacement_rows_unmapped": 189',
        1,
    ),
    ('default_visible_rows": 6493', 'default_visible_rows": 6499', 1),
    (
        'mapped_by_tier": {"A": 213, "B": 6280, "C": 102494}',
        'mapped_by_tier": {"A": 219, "B": 6280, "C": 102494}',
        1,
    ),
    (
        'mapped_replacement_rows\\\\\\\\": 94',
        'mapped_replacement_rows\\\\\\\\": 100',
        1,
    ),
    ('mapped_rows": 108987', 'mapped_rows": 108993', 1),
    ('master_rows": 109285', 'master_rows": 109313', 1),
    ('unmapped_rows": 298', 'unmapped_rows": 320', 1),
    ("109_285", "109_313", 1),
    ("len(replacement_ids) != 373", "len(replacement_ids) != 401", 1),
    ("len(added) != 174", "len(added) != 202", 1),
    ("108,987", "108,993", 1),
    ("109,285", "109,313", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

globals()["MAP_ID"] = "2026-07-21-public-open-v27-construction-map-v2"
globals()["MASTER_ID"] = "2026-07-21-public-open-v27"
globals()["EXPECTED_FIXED"]["mapped_rows_with_any_role"] = 75
