"""Frozen v24 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v23 carrier and
applies only the closed v55-to-v56 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exact.
No identity decision, satellite payload, or physical-site count is added.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "80fb676a3f30b92a105a656b206b837360705a3ad2534a663bc53a5488e42f02"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v7.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v8 accepted-v23 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v7 changed; refusing v24 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v7", "construction_master_v8", 2),
    ("ConstructionMasterV7Error", "ConstructionMasterV8Error", 1),
    ("is_frozen_master_v7", "is_frozen_master_v8", 1),
    ("v23", "v24", 3),
    ("V23", "V24", 1),
    ("v55", "v56", 2),
    ("2026-07-20T20:20:00Z", "2026-07-20T23:05:00Z", 1),
    ('added_replacement_rows": 147', 'added_replacement_rows": 149', 1),
    ('replacement_rows": 346', 'replacement_rows": 348', 1),
    (
        'replacement_rows_with_any_role": 124',
        'replacement_rows_with_any_role": 126',
        1,
    ),
    (
        'replacement_rows_with_operator": 48',
        'replacement_rows_with_operator": 49',
        1,
    ),
    (
        'replacement_rows_with_source_role_tags\\": 85',
        'replacement_rows_with_source_role_tags\\": 87',
        1,
    ),
    ('rows_with_contract_marker": 346', 'rows_with_contract_marker": 348', 1),
    ('tier_a_rows": 466', 'tier_a_rows": 468', 1),
    ('total_rows": 109_258', 'total_rows": 109_260', 1),
    (
        'construction_pipeline_records") != 346',
        'construction_pipeline_records") != 348',
        2,
    ),
    ('added_rows": 147', 'added_rows": 149', 1),
    ("109,258", "109,260", 1),
    ("466 Tier A", "468 Tier A", 1),
    ("346-row", "348-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
