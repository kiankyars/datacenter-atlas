"""Frozen v25 successor carrier for the deterministic construction map.

The schema remains v2. This carrier byte-pins the accepted v24 carrier and
applies only the v25 master identity and exact v59 coordinate projection. It
creates no identity decision, current-status claim, or physical-site count.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "7b91d74faf58eac1e1ab5c9717ab4fea79a099283389fe0650aae15aebe4642a"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v8.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v9 accepted-v24 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v8 changed; refusing v25 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v8", "construction_map_v9", 2),
    ("ConstructionMapV8Error", "ConstructionMapV9Error", 1),
    ("build_index_v8", "build_index_v9", 1),
    ("is_frozen_map_v8", "is_frozen_map_v9", 1),
    ("validate_map_definition_v8", "validate_map_definition_v9", 1),
    ("construction_master_v8", "construction_master_v9", 1),
    ("ConstructionMasterV8Error", "ConstructionMasterV9Error", 1),
    ("v24", "v25", 4),
    ("v56", "v59", 2),
    ("2026-07-20T23:05:01Z", "2026-07-21T03:50:01Z", 1),
    (
        'added_replacement_rows_unmapped": 144',
        'added_replacement_rows_unmapped": 157',
        1,
    ),
    ('default_visible_rows": 6486', 'default_visible_rows": 6492', 1),
    (
        'mapped_by_tier": {"A": 206, "B": 6280, "C": 102494}',
        'mapped_by_tier": {"A": 212, "B": 6280, "C": 102494}',
        1,
    ),
    ('mapped_replacement_rows\\": 87', 'mapped_replacement_rows\\": 93', 1),
    ('mapped_rows": 108980', 'mapped_rows": 108986', 1),
    ('master_rows": 109260', 'master_rows": 109274', 1),
    ('unmapped_rows": 280', 'unmapped_rows": 288', 1),
    ("109_260", "109_274", 1),
    ("len(replacement_ids) != 348", "len(replacement_ids) != 362", 1),
    ("len(added) != 149", "len(added) != 163", 1),
    ("108,980", "108,986", 1),
    ("109,260", "109,274", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
