"""Frozen v23 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v17 carrier and
applies the closed v44-to-v55 replacement-release/count transition directly.
The v14 base master and accepted Unknown033 recovery control plane remain
exactly the v17 inputs. No identity decision or physical-site count is added.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = (
    "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v3.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v7 accepted-v17 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v3 changed; refusing v23 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v3", "construction_master_v7", 7),
    ("ConstructionMasterV3Error", "ConstructionMasterV7Error", 3),
    ("is_frozen_master_v3", "is_frozen_master_v7", 1),
    ("v17", "v23", 3),
    ("V17", "V23", 1),
    ("v44", "v55", 2),
    (
        'GENERATED_AT = "2026-07-20T08:15:00Z"',
        'GENERATED_AT = "2026-07-20T20:20:00Z"',
        1,
    ),
    ('    "added_replacement_rows": 100,', '    "added_replacement_rows": 147,', 1),
    ('    "replacement_rows": 299,', '    "replacement_rows": 346,', 1),
    (
        '    "replacement_rows_with_any_role": 102,',
        '    "replacement_rows_with_any_role": 124,',
        1,
    ),
    (
        '    "replacement_rows_with_operator": 35,',
        '    "replacement_rows_with_operator": 48,',
        1,
    ),
    (
        "    ('    \"replacement_rows_with_source_role_tags\": 50,', "
        "'    \"replacement_rows_with_source_role_tags\": 63,', 1),",
        "    ('    \"replacement_rows_with_source_role_tags\": 50,', "
        "'    \"replacement_rows_with_source_role_tags\": 85,', 1),\n"
        "    ('    \"replacement_rows_with_tenants\": 4,', "
        "'    \"replacement_rows_with_tenants\": 6,', 1),\n"
        "    ('    \"replacement_rows_with_customers\": 1,', "
        "'    \"replacement_rows_with_customers\": 2,', 1),",
        1,
    ),
    (
        '    "rows_with_contract_marker": 299,',
        '    "rows_with_contract_marker": 346,',
        1,
    ),
    ('    "tier_a_rows": 419,', '    "tier_a_rows": 466,', 1),
    ('    "total_rows": 109_211,', '    "total_rows": 109_258,', 1),
    (
        'release_manifest.get("construction_pipeline_records") != 299',
        'release_manifest.get("construction_pipeline_records") != 346',
        1,
    ),
    (
        'expected_release.get("construction_pipeline_records") != 299',
        'expected_release.get("construction_pipeline_records") != 346',
        1,
    ),
    ('            "added_rows": 100,', '            "added_rows": 147,', 1),
    ("109,211", "109,258", 1),
    ("419 Tier A", "466 Tier A", 1),
    ("299-row", "346-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
