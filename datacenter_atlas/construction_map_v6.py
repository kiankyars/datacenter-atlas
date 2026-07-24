"""Frozen v22 successor carrier for the deterministic construction map.

The schema remains v2. This carrier byte-pins the accepted v21 map carrier and
applies only the v22 master identity and exact v49 replacement projection.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = (
    "a64ddbcea72743e5f181a5c6ccc45d3812f47bdcce8d575267d54257bd99138f"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v5.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v6 accepted-v21 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v5 changed; refusing v22 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v5", "construction_map_v6", 2),
    ("ConstructionMapV5Error", "ConstructionMapV6Error", 1),
    ("build_index_v5", "build_index_v6", 1),
    ("is_frozen_map_v5", "is_frozen_map_v6", 1),
    ("validate_map_definition_v5", "validate_map_definition_v6", 1),
    ("construction_master_v5", "construction_master_v6", 1),
    ("ConstructionMasterV5Error", "ConstructionMasterV6Error", 1),
    ("v21", "v22", 4),
    ("v47", "v49", 2),
    (
        'GENERATED_AT = "2026-07-20T10:26:32Z"',
        'GENERATED_AT = "2026-07-20T16:52:31Z"',
        1,
    ),
    (
        '    "added_replacement_rows_unmapped": 111,',
        '    "added_replacement_rows_unmapped": 125,',
        1,
    ),
    ('    "master_rows": 109225,', '    "master_rows": 109239,', 1),
    ('    "unmapped_rows": 250,', '    "unmapped_rows": 264,', 1),
    ("109_225", "109_239", 1),
    ("len(replacement_ids) != 313", "len(replacement_ids) != 327", 1),
    ("len(added) != 114", "len(added) != 128", 1),
    ("109,225", "109,239", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
