"""Frozen v20 successor to the accepted v17 construction-master carrier.

The schema remains v2. This module byte-pins the complete v17 carrier and
changes only its closed identity/count patch from open-seed v44 to v46. The
v14 base and zero-row Unknown033 satellite acceptance boundary remain intact.
"""

from __future__ import annotations

import hashlib as _successor_hashlib
from pathlib import Path as _SuccessorPath


_PREVIOUS_SOURCE_SHA256 = (
    "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b"
)
_PREVIOUS_SOURCE = _SuccessorPath(__file__).with_name("construction_master_v3.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v4 frozen successor boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_successor_raw = _PREVIOUS_SOURCE.read_bytes()
if _successor_hashlib.sha256(_successor_raw).hexdigest() != _PREVIOUS_SOURCE_SHA256:
    raise ImportError("construction_master_v3 source changed; refusing v4 carrier load")
_successor_source = _successor_raw.decode("utf-8")
for _successor_old, _successor_new, _successor_count in (
    ("construction_master_v3", "construction_master_v4", 7),
    ("ConstructionMasterV3Error", "ConstructionMasterV4Error", 3),
    ("is_frozen_master_v3", "is_frozen_master_v4", 1),
    ('2026-07-20T08:15:00Z', '2026-07-20T10:00:03Z', 1),
    ('    "added_replacement_rows": 100,', '    "added_replacement_rows": 118,', 1),
    ('    "replacement_rows": 299,', '    "replacement_rows": 317,', 1),
    ('    "rows_with_contract_marker": 299,', '    "rows_with_contract_marker": 317,', 1),
    ('    "tier_a_rows": 419,', '    "tier_a_rows": 437,', 1),
    ('    "total_rows": 109_211,', '    "total_rows": 109_229,', 1),
    ('!= 299', '!= 317', 2),
    ('            "added_rows": 100,', '            "added_rows": 118,', 1),
    ('"109,211"', '"109,229"', 1),
    ('"419 Tier A"', '"437 Tier A"', 1),
    ('"299-row"', '"317-row"', 1),
    ("v44", "v46", 2),
    ("v17", "v20", 3),
    ("V17", "V20", 1),
):
    _successor_source = _successor_replacement(
        _successor_source,
        _successor_old,
        _successor_new,
        _successor_count,
    )

exec(compile(_successor_source, __file__, "exec"), globals())
