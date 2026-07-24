"""Frozen v17 carrier for the deterministic construction map.

The map schema remains v2.  This carrier byte-pins the accepted v2 map source,
applies a closed identity/count patch for the v17 master, and removes the old
dataset-specific assumption that every row added after v33 lacks coordinates.
The three coordinate-bearing additive v44 rows remain ordinary observations;
they are not identity, lifecycle, or capacity inferences.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
import os as _carrier_os
from pathlib import Path as _CarrierPath
from typing import Any as _Any


_BASE_SOURCE_SHA256 = (
    "6f5e15e4bf86db7df31a55e1177057ac27d407ce7012cf8d7b2d1631018afe0b"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_map_v2.py")


def _replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v3 frozen patch boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v2 source changed; refusing v3 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    (
        "        if record_id in added_source_record_ids:\n"
        "            raise ConstructionMapV2Error(\"an additive v42 row unexpectedly became mapped\")\n",
        "",
        1,
    ),
    (
        "    if set(added_unmapped_ids) != added_source_record_ids:\n"
        "        raise ConstructionMapV2Error(\"not all 63 additive v42 rows remain unmapped\")\n",
        "",
        1,
    ),
    ("construction_master_v2", "construction_master_v3", 3),
    ("ConstructionMasterV2Error", "ConstructionMasterV3Error", 2),
    ("ConstructionMapV2Error", "ConstructionMapV3Error", 58),
    ("build_index_v2", "build_index_v3", 3),
    ("write_construction_map_v2", "write_construction_map_v3", 3),
    ("is_frozen_map_v2", "is_frozen_map_v3", 3),
    ("validate_construction_map_v2", "validate_construction_map_v3", 2),
    ("validate_map_definition_v2", "validate_map_definition_v3", 4),
    ('GENERATED_AT = "2026-07-20T06:15:00Z"', 'GENERATED_AT = "2026-07-20T08:30:00Z"', 1),
    ('    "added_replacement_rows_unmapped": 63,', '    "added_replacement_rows_unmapped": 97,', 1),
    ('    "default_visible_rows": 6479,', '    "default_visible_rows": 6481,', 1),
    ('    "mapped_by_tier": {"A": 199, "B": 6280, "C": 102494},', '    "mapped_by_tier": {"A": 201, "B": 6280, "C": 102494},', 1),
    ('    "mapped_replacement_rows": 80,', '    "mapped_replacement_rows": 82,', 1),
    ('    "mapped_rows": 108973,', '    "mapped_rows": 108975,', 1),
    ('    "master_rows": 109174,', '    "master_rows": 109211,', 1),
    ('    "unmapped_rows": 201,', '    "unmapped_rows": 236,', 1),
    ("109_174", "109_211", 1),
    ("len(replacement_ids) != 262", "len(replacement_ids) != 299", 1),
    ("len(added) != 63", "len(added) != 100", 1),
    ("108,973", "108,975", 1),
    ("109,174", "109,211", 1),
    ("v42", "v44", 2),
    ("v16", "v17", 2),
    (
        "        stage.replace(destination)",
        "        if destination.exists() or destination.is_symlink():\n"
        "            raise ConstructionMapV3Error(\n"
        "                f\"refusing late output collision: {destination}\"\n"
        "            )\n"
        "        stage.replace(destination)",
        1,
    ),
):
    _source = _replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

_write_construction_map_v3_unlocked = globals()["write_construction_map_v3"]


def write_construction_map_v3(
    master_directory: str | _CarrierPath,
    output_directory: str | _CarrierPath,
    *,
    master_definition_path: str | _CarrierPath,
    map_definition_path: str | _CarrierPath,
    freeze: bool = False,
) -> dict[str, _Any]:
    """Build the v17 map under an exclusive sibling lock and publish atomically."""

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
        error_type = globals()["ConstructionMapV3Error"]
        raise error_type(f"refusing active output lock: {lock}") from error
    try:
        _carrier_os.write(descriptor, f"pid={_carrier_os.getpid()}\n".encode("ascii"))
        _carrier_os.fsync(descriptor)
        return _write_construction_map_v3_unlocked(
            master_directory,
            destination,
            master_definition_path=master_definition_path,
            map_definition_path=map_definition_path,
            freeze=freeze,
        )
    finally:
        _carrier_os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
