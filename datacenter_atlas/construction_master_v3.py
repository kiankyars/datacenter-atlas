"""Frozen v17 carrier for the role-preserving construction-master schema.

The schema remains v2.  The carrier byte-pins the accepted v2 implementation,
applies a closed, audited identity/count patch for the v42-to-v44 replacement,
and executes that patched source in this module.  This keeps the historical v2
carrier immutable while failing closed if its source bytes ever drift.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
import os as _carrier_os
from pathlib import Path as _CarrierPath
from typing import Any as _Any


_BASE_SOURCE_SHA256 = (
    "cc728bef65911346347ec4eecd1debe82fe48910160b2ffb3cde87dda5aba311"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v2.py")


def _replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v3 frozen patch boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v2 source changed; refusing v3 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("ConstructionMasterV2Error", "ConstructionMasterV3Error", 69),
    ("write_construction_master_v2", "write_construction_master_v3", 3),
    ("is_frozen_master_v2", "is_frozen_master_v3", 3),
    ("validate_construction_master_v2", "validate_construction_master_v3", 2),
    ('GENERATED_AT = "2026-07-20T06:00:00Z"', 'GENERATED_AT = "2026-07-20T08:15:00Z"', 1),
    ('    "added_replacement_rows": 63,', '    "added_replacement_rows": 100,', 2),
    ('    "replacement_rows": 262,', '    "replacement_rows": 299,', 2),
    ('    "replacement_rows_with_any_role": 89,', '    "replacement_rows_with_any_role": 102,', 1),
    ('    "replacement_rows_with_operator": 30,', '    "replacement_rows_with_operator": 35,', 1),
    ('    "replacement_rows_with_owner": 46,', '    "replacement_rows_with_owner": 47,', 1),
    ('    "replacement_rows_with_source_role_tags": 50,', '    "replacement_rows_with_source_role_tags": 63,', 1),
    ('    "rows_with_contract_marker": 262,', '    "rows_with_contract_marker": 299,', 1),
    ('    "tier_a_rows": 382,', '    "tier_a_rows": 419,', 1),
    ('    "total_rows": 109_174,', '    "total_rows": 109_211,', 1),
    ('release_manifest.get("construction_pipeline_records") != 262', 'release_manifest.get("construction_pipeline_records") != 299', 1),
    ('expected_release.get("construction_pipeline_records") != 262', 'expected_release.get("construction_pipeline_records") != 299', 1),
    ('            "added_rows": 63,', '            "added_rows": 100,', 1),
    ("109,174", "109,211", 1),
    ("382 Tier A", "419 Tier A", 1),
    ("262-row", "299-row", 1),
    ("v42", "v44", 7),
    ("v16", "v17", 3),
    ("V16", "V17", 2),
    (
        "        stage.replace(destination)",
        "        if destination.exists() or destination.is_symlink():\n"
        "            raise ConstructionMasterV3Error(\n"
        "                f\"refusing late output collision: {destination}\"\n"
        "            )\n"
        "        stage.replace(destination)",
        1,
    ),
):
    _source = _replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

_write_construction_master_v3_unlocked = globals()["write_construction_master_v3"]


def write_construction_master_v3(
    definition_path: str | _CarrierPath,
    output_directory: str | _CarrierPath,
    *,
    freeze: bool = False,
) -> dict[str, _Any]:
    """Build v17 under an exclusive sibling lock and publish atomically."""

    destination = _CarrierPath(
        _carrier_os.path.abspath(_carrier_os.fspath(output_directory))
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = _carrier_os.open(
            lock,
            _carrier_os.O_CREAT | _carrier_os.O_EXCL | _carrier_os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        error_type = globals()["ConstructionMasterV3Error"]
        raise error_type(
            f"refusing active output lock: {lock}"
        ) from error
    try:
        _carrier_os.write(descriptor, f"pid={_carrier_os.getpid()}\n".encode("ascii"))
        _carrier_os.fsync(descriptor)
        return _write_construction_master_v3_unlocked(
            definition_path,
            destination,
            freeze=freeze,
        )
    finally:
        _carrier_os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
