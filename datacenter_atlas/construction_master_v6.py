"""Frozen v22 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v21 carrier and
applies only the closed v47-to-v49 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exactly
the v21 inputs.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = (
    "1f52ccc0d1436c818f40f4b6ef170e4f225124ee20d905a3d7dda9fd5f4ad82b"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v5.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v6 accepted-v21 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v5 changed; refusing v22 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v5", "construction_master_v6", 2),
    ("ConstructionMasterV5Error", "ConstructionMasterV6Error", 1),
    ("is_frozen_master_v5", "is_frozen_master_v6", 1),
    ("v21", "v22", 3),
    ("V21", "V22", 1),
    ("v47", "v49", 2),
    (
        'GENERATED_AT = "2026-07-20T10:26:31Z"',
        'GENERATED_AT = "2026-07-20T16:52:30Z"',
        1,
    ),
    ('    "added_replacement_rows": 114,', '    "added_replacement_rows": 128,', 1),
    ('    "replacement_rows": 313,', '    "replacement_rows": 327,', 1),
    (
        '    "replacement_rows_with_any_role": 108,',
        '    "replacement_rows_with_any_role": 114,',
        1,
    ),
    (
        '    "replacement_rows_with_operator": 40,',
        '    "replacement_rows_with_operator": 45,',
        1,
    ),
    (
        r'replacement_rows_with_source_role_tags\": 69,',
        r'replacement_rows_with_source_role_tags\": 75,',
        1,
    ),
    (
        '    "rows_with_contract_marker": 313,',
        '    "rows_with_contract_marker": 327,',
        1,
    ),
    ('    "tier_a_rows": 433,', '    "tier_a_rows": 447,', 1),
    ('    "total_rows": 109_225,', '    "total_rows": 109_239,', 1),
    (
        'release_manifest.get("construction_pipeline_records") != 313',
        'release_manifest.get("construction_pipeline_records") != 327',
        1,
    ),
    (
        'expected_release.get("construction_pipeline_records") != 313',
        'expected_release.get("construction_pipeline_records") != 327',
        1,
    ),
    ('            "added_rows": 114,', '            "added_rows": 128,', 1),
    ("109,225", "109,239", 1),
    ("433 Tier A", "447 Tier A", 1),
    ("313-row", "327-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
