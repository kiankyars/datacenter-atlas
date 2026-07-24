"""Frozen v23 successor carrier for the deterministic construction map.

The schema remains v2. This carrier byte-pins the accepted v17 map carrier and
applies the v23 master identity and exact v55 replacement projection directly.
It creates no identity decision or physical-site count.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = (
    "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v3.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v7 accepted-v17 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v3 changed; refusing v23 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v3", "construction_map_v7", 7),
    ("ConstructionMapV3Error", "ConstructionMapV7Error", 3),
    ("build_index_v3", "build_index_v7", 1),
    ("is_frozen_map_v3", "is_frozen_map_v7", 1),
    ("validate_map_definition_v3", "validate_map_definition_v7", 1),
    ("construction_master_v3", "construction_master_v7", 1),
    ("ConstructionMasterV3Error", "ConstructionMasterV7Error", 1),
    ("v17", "v23", 4),
    ("v44", "v55", 2),
    (
        'GENERATED_AT = "2026-07-20T08:30:00Z"',
        'GENERATED_AT = "2026-07-20T20:20:01Z"',
        1,
    ),
    (
        '    "added_replacement_rows_unmapped": 97,',
        '    "added_replacement_rows_unmapped": 144,',
        1,
    ),
    ('    "default_visible_rows": 6481,', '    "default_visible_rows": 6484,', 1),
    (
        '    "mapped_by_tier": {"A": 201, "B": 6280, "C": 102494},',
        '    "mapped_by_tier": {"A": 204, "B": 6280, "C": 102494},',
        1,
    ),
    ('    "mapped_replacement_rows": 82,', '    "mapped_replacement_rows": 85,', 1),
    ('    "mapped_rows": 108975,', '    "mapped_rows": 108978,', 1),
    ('    "master_rows": 109211,', '    "master_rows": 109258,', 1),
    ('    "unmapped_rows": 236,', '    "unmapped_rows": 280,', 1),
    ("109_211", "109_258", 1),
    ("len(replacement_ids) != 299", "len(replacement_ids) != 346", 1),
    ("len(added) != 100", "len(added) != 147", 1),
    ("108,975", "108,978", 1),
    ("109,211", "109,258", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
