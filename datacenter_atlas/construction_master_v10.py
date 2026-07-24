"""Frozen v26 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v25 carrier and
applies only the closed v59-to-v62 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exact.
No identity decision, satellite payload, or physical-site count is added.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "63ce982579d7d052729a5844954442da868f3126565910e2f5fc5b9f37f9b22d"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v9.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v10 accepted-v25 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v9 changed; refusing v26 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v9", "construction_master_v10", 2),
    ("ConstructionMasterV9Error", "ConstructionMasterV10Error", 1),
    ("is_frozen_master_v9", "is_frozen_master_v10", 1),
    ("v25", "v26", 3),
    ("V25", "V26", 1),
    ("v59", "v62", 2),
    ("2026-07-21T03:50:00Z", "2026-07-21T05:05:00Z", 1),
    ('added_replacement_rows": 163', 'added_replacement_rows": 174', 1),
    ('replacement_rows": 362', 'replacement_rows": 373', 1),
    (
        'replacement_rows_with_any_role": 127',
        'replacement_rows_with_any_role": 129',
        1,
    ),
    (
        'replacement_rows_with_source_role_tags\\\\\\\\": 88',
        'replacement_rows_with_source_role_tags\\\\\\\\": 90',
        1,
    ),
    ('rows_with_contract_marker": 362', 'rows_with_contract_marker": 373', 1),
    ('tier_a_rows": 482', 'tier_a_rows": 493', 1),
    ('total_rows": 109_274', 'total_rows": 109_285', 1),
    (
        'construction_pipeline_records") != 362',
        'construction_pipeline_records") != 373',
        1,
    ),
    ('added_rows": 163', 'added_rows": 174', 1),
    ("109,274", "109,285", 1),
    ("482 Tier A", "493 Tier A", 1),
    ("362-row", "373-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

# V62 adds two operator-marked rows after the v59 boundary. The remaining
# fixed invariants are transformed in the closed carrier patch above.
globals()["EXPECTED_FIXED"]["replacement_rows_with_operator"] = 51
