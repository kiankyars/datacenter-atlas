"""Coverage-audit carrier accepting governed federation-v6 manifests.

The wire schema remains coverage-audit v2. This carrier byte-pins the complete
accepted implementation and changes only its federation validator from v2 to
v6, which accepts governed open-seed successor metadata without rewriting or
promoting any child claim.
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
            "coverage_audit_v5 accepted-v32 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("coverage_audit_v2 changed; refusing v32 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("federated_release_v2", "federated_release_v6", 1),
    ("federation_v2", "federation_v6", 4),
    (
        "federated v2 input validation failed",
        "federated v6 input validation failed",
        1,
    ),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())  # noqa: S102
