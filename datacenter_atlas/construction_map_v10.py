"""Frozen v26 successor carrier for the deterministic construction map.

The schema remains v2. This carrier byte-pins the accepted v25 carrier and
applies only the v26 master identity and exact v62 coordinate projection. It
creates no identity decision, current-status claim, or physical-site count.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "cdb2cf235fc053b00d093874d1ca024dffdb4ba09fe5c89ad3c97168c483249b"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v9.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v10 accepted-v25 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v9 changed; refusing v26 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v9", "construction_map_v10", 2),
    ("ConstructionMapV9Error", "ConstructionMapV10Error", 1),
    ("build_index_v9", "build_index_v10", 1),
    ("is_frozen_map_v9", "is_frozen_map_v10", 1),
    ("validate_map_definition_v9", "validate_map_definition_v10", 1),
    ("construction_master_v9", "construction_master_v10", 1),
    ("ConstructionMasterV9Error", "ConstructionMasterV10Error", 1),
    ("v25", "v26", 4),
    ("v59", "v62", 2),
    ("2026-07-21T03:50:01Z", "2026-07-21T05:05:01Z", 1),
    (
        'added_replacement_rows_unmapped": 157',
        'added_replacement_rows_unmapped": 167',
        1,
    ),
    ('default_visible_rows": 6492', 'default_visible_rows": 6493', 1),
    (
        'mapped_by_tier": {"A": 212, "B": 6280, "C": 102494}',
        'mapped_by_tier": {"A": 213, "B": 6280, "C": 102494}',
        1,
    ),
    ('mapped_replacement_rows\\\\": 93', 'mapped_replacement_rows\\\\": 94', 1),
    ('mapped_rows": 108986', 'mapped_rows": 108987', 1),
    ('master_rows": 109274', 'master_rows": 109285', 1),
    ('unmapped_rows": 288', 'unmapped_rows": 298', 1),
    ("109_274", "109_285", 1),
    ("len(replacement_ids) != 362", "len(replacement_ids) != 373", 1),
    ("len(added) != 163", "len(added) != 174", 1),
    ("108,986", "108,987", 1),
    ("109,274", "109,285", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

# IAD5 is the only additional coordinate-bearing role-marked v62 observation.
globals()["EXPECTED_FIXED"]["mapped_rows_with_any_role"] = 69
