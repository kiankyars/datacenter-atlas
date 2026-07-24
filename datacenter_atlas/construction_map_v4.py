"""Frozen v20 successor to the accepted v17 construction-map carrier.

The schema remains v2. This module byte-pins the complete v17 carrier and
changes only its master identity and projection counts for v20. No rows are
promoted, merged, or interpreted as unique physical sites.
"""

from __future__ import annotations

import hashlib as _successor_hashlib
from pathlib import Path as _SuccessorPath


_PREVIOUS_SOURCE_SHA256 = (
    "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6"
)
_PREVIOUS_SOURCE = _SuccessorPath(__file__).with_name("construction_map_v3.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v4 frozen successor boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_successor_raw = _PREVIOUS_SOURCE.read_bytes()
if _successor_hashlib.sha256(_successor_raw).hexdigest() != _PREVIOUS_SOURCE_SHA256:
    raise ImportError("construction_map_v3 source changed; refusing v4 carrier load")
_successor_source = _successor_raw.decode("utf-8")
for _successor_old, _successor_new, _successor_count in (
    ("construction_map_v3", "construction_map_v4", 7),
    ("construction_master_v3", "construction_master_v4", 1),
    ("ConstructionMapV3Error", "ConstructionMapV4Error", 3),
    ("ConstructionMasterV3Error", "ConstructionMasterV4Error", 1),
    ("build_index_v3", "build_index_v4", 1),
    ("is_frozen_map_v3", "is_frozen_map_v4", 1),
    ("validate_map_definition_v3", "validate_map_definition_v4", 1),
    ('2026-07-20T08:30:00Z', '2026-07-20T10:03:13Z', 1),
    ('    "added_replacement_rows_unmapped": 97,', '    "added_replacement_rows_unmapped": 115,', 1),
    ('    "master_rows": 109211,', '    "master_rows": 109229,', 1),
    ('    "unmapped_rows": 236,', '    "unmapped_rows": 254,', 1),
    ('"109_211"', '"109_229"', 1),
    ('"len(replacement_ids) != 299"', '"len(replacement_ids) != 317"', 1),
    ('"len(added) != 100"', '"len(added) != 118"', 1),
    ('"109,211"', '"109,229"', 1),
    ("v44", "v46", 2),
    ("v17", "v20", 4),
):
    _successor_source = _successor_replacement(
        _successor_source,
        _successor_old,
        _successor_new,
        _successor_count,
    )

exec(compile(_successor_source, __file__, "exec"), globals())
