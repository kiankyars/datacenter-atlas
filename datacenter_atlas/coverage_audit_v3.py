"""Strict v26 coverage-audit carrier over the accepted v25 implementation.

The wire schema remains coverage-audit v2. This carrier byte-pins the complete
accepted implementation and changes only its federation validator from v2 to
v3 so publication-v4 child freshness can be checked without mutating v25.
"""

from __future__ import annotations

import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath


_BASE_SOURCE_SHA256 = "f4af61258d90054fe6f3c28c2470164c096e2186cf97d4445a09aa4675bb2b52"
_BASE_SOURCE = _CarrierPath(__file__).with_name("coverage_audit_v2.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "coverage_audit_v3 accepted-v25 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("coverage_audit_v2 changed; refusing v26 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("federated_release_v2", "federated_release_v3", 1),
    ("federation_v2", "federation_v3", 4),
    (
        "federated v2 input validation failed",
        "federated v3 input validation failed",
        1,
    ),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())
