"""Frozen v27 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v26 carrier and
applies only the closed v62-to-v67 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exact.
No identity decision, satellite payload, or physical-site count is added.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "d77c8bd461ea0365708b56a0f55596f9d581ed8a1f520181e85cba78775926bb"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v10.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v11 accepted-v26 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v10 changed; refusing v27 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v10", "construction_master_v11", 2),
    ("ConstructionMasterV10Error", "ConstructionMasterV11Error", 1),
    ("is_frozen_master_v10", "is_frozen_master_v11", 1),
    ("v26", "v27", 3),
    ("V26", "V27", 1),
    ("v62", "v67", 2),
    ("V62", "V67", 1),
    ("2026-07-21T05:05:00Z", "2026-07-21T08:05:00Z", 1),
    ('added_replacement_rows": 174', 'added_replacement_rows": 202', 1),
    ('replacement_rows": 373', 'replacement_rows": 401', 1),
    (
        'replacement_rows_with_any_role": 129',
        'replacement_rows_with_any_role": 142',
        1,
    ),
    (
        'replacement_rows_with_source_role_tags\\\\\\\\\\\\\\\\": 90',
        'replacement_rows_with_source_role_tags\\\\\\\\\\\\\\\\": 103',
        1,
    ),
    ('rows_with_contract_marker": 373', 'rows_with_contract_marker": 401', 1),
    ('tier_a_rows": 493', 'tier_a_rows": 521', 1),
    ('total_rows": 109_285', 'total_rows": 109_313', 1),
    (
        'construction_pipeline_records") != 373',
        'construction_pipeline_records") != 401',
        1,
    ),
    ('added_rows": 174', 'added_rows": 202', 1),
    ("109,285", "109,313", 1),
    ("493 Tier A", "521 Tier A", 1),
    ("373-row", "401-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

globals()["MASTER_ID"] = "2026-07-21-public-open-v27"
globals()["REPLACEMENT_DEFINITION_RELEASE_ID"] = "2026-07-21-open-seed-v67"
globals()["EXPECTED_FIXED"].update(
    {
        "replacement_rows_with_operator": 58,
        "replacement_rows_with_owner": 48,
        "replacement_rows_with_tenants": 7,
    }
)
