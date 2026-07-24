"""Frozen v25 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v24 carrier and
applies only the closed v56-to-v59 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exact.
No identity decision, satellite payload, or physical-site count is added.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "c5e6d1573ca8af855a35f57e57e1579f6588370458a3cac5cddf1fde92157946"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v8.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v9 accepted-v24 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v8 changed; refusing v25 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v8", "construction_master_v9", 2),
    ("ConstructionMasterV8Error", "ConstructionMasterV9Error", 1),
    ("is_frozen_master_v8", "is_frozen_master_v9", 1),
    ("v24", "v25", 3),
    ("V24", "V25", 1),
    ("v56", "v59", 2),
    ("2026-07-20T23:05:00Z", "2026-07-21T03:50:00Z", 1),
    ('added_replacement_rows": 149', 'added_replacement_rows": 163', 1),
    ('replacement_rows": 348', 'replacement_rows": 362', 1),
    (
        'replacement_rows_with_any_role": 126',
        'replacement_rows_with_any_role": 127',
        1,
    ),
    (
        'replacement_rows_with_source_role_tags\\\\": 87',
        'replacement_rows_with_source_role_tags\\\\": 88',
        1,
    ),
    ('rows_with_contract_marker": 348', 'rows_with_contract_marker": 362', 1),
    ('tier_a_rows": 468', 'tier_a_rows": 482', 1),
    ('total_rows": 109_260', 'total_rows": 109_274', 1),
    (
        'construction_pipeline_records") != 348',
        'construction_pipeline_records") != 362',
        1,
    ),
    ('added_rows": 149', 'added_rows": 163', 1),
    ("109,260", "109,274", 1),
    ("468 Tier A", "482 Tier A", 1),
    ("348-row", "362-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
