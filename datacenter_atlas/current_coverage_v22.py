"""Preparation-only, fail-closed current-coverage ledger v22 successor.

V22 is defined as an exact seven-for-seven successor of accepted v21. All seven
replacement lanes are accepted and pinned here. Definition and component
digests remain explicit fuses until the complete successor is reviewed.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from . import current_coverage_v21 as _v21


V22_LEDGER_ID = "current-coverage-2026-07-21-v22"
V22_GENERATED_AT = "2026-07-21T11:15:30Z"
V22_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v22.json"
V22_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v22"
V22_DEFINITION_SHA256: str | None = (
    "ee84ae4fd321ff4eb31e9d48359b18b8cb6d960d7ed4bf80a5d822e2386bd483"
)
REPLACEMENT_7_SHA256: str | None = (
    "5e0ea4d1b2ecda8d0727e505b76ea2f5a63a750956ea9ccc05f6b1f52881882d"
)
ALL_ENTRIES_SHA256: str | None = (
    "0e040c51333e9d3c01d9fc00d4071da0aa420ca0528a4176f28a1f8019cb8daa"
)

DEFINITION_SCHEMA_VERSION_V4 = _v21.DEFINITION_SCHEMA_VERSION_V4
LEDGER_SCHEMA_VERSION_V4 = _v21.LEDGER_SCHEMA_VERSION_V4
LEDGER_FORMAT_V4 = _v21.LEDGER_FORMAT_V4
BUNDLE_FORMAT_V4 = _v21.BUNDLE_FORMAT_V4
ARTIFACT_KINDS_V4 = _v21.ARTIFACT_KINDS_V4
RECORD_UNITS_V4 = _v21.RECORD_UNITS_V4
SCOPE_POLICY = _v21.SCOPE_POLICY
BUNDLE_FILES = _v21.BUNDLE_FILES
LEDGER_FILENAME = _v21.LEDGER_FILENAME
MANIFEST_FILENAME = _v21.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _v21.MANIFEST_HASH_FILENAME

V21_BASE_LINEAGE = {
    "definition": {
        "bytes": 146_115,
        "path": "sources/current-coverage-2026-07-21-v21.json",
        "sha256": "116fdc6beb9c03ba386c80aab43de406049567246e7a40f439c5712b0101ea78",
    },
    "ledger": {
        "bytes": 100_079,
        "path": (
            "current_coverage_ledgers/2026-07-21-v21/"
            "current-coverage-ledger.json"
        ),
        "sha256": "9198ddec824d84826e74b5696fbf3746128c3e8a670d45e98282f15a95613d80",
    },
    "ledger_id": "current-coverage-2026-07-21-v21",
    "manifest": {
        "bytes": 27_661,
        "path": "current_coverage_ledgers/2026-07-21-v21/manifest.json",
        "sha256": "9870a32f953f09df8f5314fbd365ef6e563e2b86b964fa1795f725b535a983e3",
    },
}
V21_SIDECAR = {
    "bytes": 80,
    "path": "current_coverage_ledgers/2026-07-21-v21/manifest.sha256",
    "sha256": "c27ab348ee9f9f93fb1d520bac59042738446b903f45d4b2d045ff53991ea0ed",
}
V21_BUNDLE_TREE_SHA256 = (
    "7aa1fb23ca9f11b11eae05c2a531040d6e9289ffff1bc7040e429872791e3eb6"
)

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v27": "construction-map-public-open-v28",
    "construction-master-public-open-v27": "construction-master-public-open-v28",
    "construction-timeline-public-open-v3": "construction-timeline-public-open-v5",
    "coverage-audit-public-open-v27": "coverage-audit-public-open-v28",
    "exact-identity-decisions-public-open-v6": (
        "exact-identity-decisions-public-open-v8"
    ),
    "federation-public-open-v28": "federation-public-open-v31",
    "seed-epoch-official-v56": "seed-epoch-official-v71",
}
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
UNCHANGED_40_SHA256 = (
    "6178822f9c84a39cabef04a370b852b70db3bc25906202f4734ed0dbe14a19d1"
)
REMOVED_7_SHA256 = (
    "41912a1fe2651fc3a2e0eda511df1007c79486189dfa76eaeacdfb7a174208b9"
)
PARITY_GAPS_SHA256 = (
    "90daddf0a5c47b21190b7061dd3000f9eee20b7f3a1dfd16a9ad5a3973f664f9"
)

PENDING_DOWNSTREAM_REPLACEMENTS: dict[str, Mapping[str, Any] | None] = {}
PENDING_DOWNSTREAM_PIN_BLUEPRINT: dict[str, Mapping[str, Any]] = {}

_ACCEPTED_FILES = {
    "construction map v28 coverage": (
        "construction_maps/2026-07-21-public-open-v28/coverage.json",
        7_465,
        "2c46219d54acf600b902b9650d5fb2077bdcd75cf5ceff1385c67a88d9282ac4",
        0o444,
    ),
    "construction map v28 definition": (
        "sources/construction-map-2026-07-21-public-open-v28.json",
        2_442,
        "52aa5b4443f60efb6ff2b983566bc194f707345e5eeaca613512c1791b6bbd85",
        0o444,
    ),
    "construction map v28 index": (
        "construction_maps/2026-07-21-public-open-v28/construction-map-index.json.gz",
        6_680_645,
        "17a6fe1c50546c5c1e08c0afcde78cb1c1490bae499d66fe427d345e0e45dde5",
        0o444,
    ),
    "construction map v28 manifest": (
        "construction_maps/2026-07-21-public-open-v28/manifest.json",
        2_192,
        "199d2c73cd73871ebe183d10531e44c1c8a0f4387973730523d9c78e65f70e6f",
        0o444,
    ),
    "construction master v28 coverage": (
        "construction_master/2026-07-21-public-open-v28/coverage.json",
        8_550,
        "cf3fe9a5b8864a02900f5711617f18e6a496ce6e5cdbbfb53f42875f000f553a",
        0o444,
    ),
    "construction master v28 definition": (
        "sources/construction-master-2026-07-21-public-open-v28.json",
        5_659,
        "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533",
        0o444,
    ),
    "construction master v28 manifest": (
        "construction_master/2026-07-21-public-open-v28/manifest.json",
        9_720,
        "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c",
        0o444,
    ),
    "coverage v28 definition": (
        "sources/coverage-audit-2026-07-21-public-open-v28.json",
        5_920,
        "5fb9f2d544f3411014271461fee8b821d7677a5c6db6ebad70586545e706cff0",
        0o444,
    ),
    "coverage v28 manifest": (
        "audits/2026-07-21-public-open-coverage-v28/manifest.json",
        3_379,
        "e45f001d3bcd5d619889ed8bb6a96da4aed0e8e8331daed2a98bac8e65d8f1a0",
        0o444,
    ),
    "federation v31 definition": (
        "sources/federation-2026-07-21-public-open-v31.json",
        1_788,
        "83a878ee72563e6572a53cf09236c0af469e629bc04482401d6891b54d108ee1",
        0o444,
    ),
    "federation v31 index": (
        "federated_indexes/2026-07-21-public-open-v31/federated-index.json",
        31_096,
        "02907b58973b74461a6117bc4373ea6ac06e5026b4fdf632e43fdaa05043e576",
        0o444,
    ),
    "federation v31 manifest": (
        "federated_indexes/2026-07-21-public-open-v31/manifest.json",
        986,
        "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101",
        0o444,
    ),
    "identity v8 accounting": (
        "exact_identity_decisions/2026-07-21-public-open-v8/accounting.json",
        981,
        "f0102c137cf17a76994f94ac43c23c4f9b98963f956e295aaea16935a5d457fb",
        0o444,
    ),
    "identity v8 definition": (
        "sources/exact-identity-decisions-2026-07-21-public-open-v8.json",
        1_735,
        "304144a09b1ec4773b662823501ac4a01505e2550d4a0270123fb20391980704",
        0o444,
    ),
    "identity v8 manifest": (
        "exact_identity_decisions/2026-07-21-public-open-v8/manifest.json",
        11_438,
        "63492e7fe633591577cdbb3f8c05c5097a52ac4f85190bdc532c869d5fe93401",
        0o444,
    ),
    "seed v71 definition": (
        "sources/open-seed-2026-07-21-v71.json",
        86_839,
        "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38",
        0o644,
    ),
    "seed v71 manifest": (
        "releases/2026-07-21-open-seed-v71/manifest.json",
        12_577,
        "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
        0o444,
    ),
    "timeline v5 coverage": (
        "construction_timelines/2026-07-21-public-open-v5/coverage.json",
        31_650,
        "e7d61b3ae399aaae5bd062e73bad7251c57396a7a00a1c36061aa01d3fb0c3ca",
        0o444,
    ),
    "timeline v5 definition": (
        "sources/construction-timeline-2026-07-21-public-open-v5.json",
        2_676,
        "f70f520e3ab887f0efea717c6850cb05dc26ce9b6b0697f96e0e6a9b8670a739",
        0o444,
    ),
    "timeline v5 manifest": (
        "construction_timelines/2026-07-21-public-open-v5/manifest.json",
        3_632,
        "aa378cde74d50b6016c5cd040a32a24e044489c0eb0fe9b412450d8abb038dba",
        0o444,
    ),
}

_ACCEPTED_TREES = {
    "construction map v28": (
        "construction_maps/2026-07-21-public-open-v28",
        "57b705610c92e7414666ceff0051b973417a587037730a2e687a3809d3bbab9a",
    ),
    "construction master v28": (
        "construction_master/2026-07-21-public-open-v28",
        "ab0cd348fd72700e012902f5130a3cbb3045e897d9609f32583fc4fa0a25209f",
    ),
    "coverage v28": (
        "audits/2026-07-21-public-open-coverage-v28",
        "5d2f271b5dcd6eee6d2f53f1347370fafad7ff6d32effe0defe5e6516acc2207",
    ),
    "federation v31": (
        "federated_indexes/2026-07-21-public-open-v31",
        "978b1a574071f0128538aafee4503436fd0ae95284a60e236b0ee9065834f55c",
    ),
    "identity v8": (
        "exact_identity_decisions/2026-07-21-public-open-v8",
        "607485d7106a06dd32f31f56fd2b5ca395f76e300b3a12b3c55ab533c1fa2b0f",
    ),
    "seed v71": (
        "releases/2026-07-21-open-seed-v71",
        "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720",
    ),
    "timeline v5": (
        "construction_timelines/2026-07-21-public-open-v5",
        "06ea50e5675c9931459fff09fd8bcfab92ebc3c0d9346fd5f5564fa65fa9641d",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v28": (
        "construction_maps/2026-07-21-public-open-v28/manifest.json",
        "generated_at",
        "2026-07-21T11:02:30Z",
    ),
    "construction master v28": (
        "construction_master/2026-07-21-public-open-v28/manifest.json",
        "generated_at",
        "2026-07-21T10:56:30Z",
    ),
    "coverage v28": (
        "audits/2026-07-21-public-open-coverage-v28/manifest.json",
        "generated_at",
        "2026-07-21T10:49:30Z",
    ),
    "federation v31": (
        "federated_indexes/2026-07-21-public-open-v31/manifest.json",
        "generated_at",
        "2026-07-21T10:32:00Z",
    ),
    "identity v8": (
        "exact_identity_decisions/2026-07-21-public-open-v8/manifest.json",
        "recorded_at",
        "2026-07-21T10:34:40Z",
    ),
    "seed v71": (
        "releases/2026-07-21-open-seed-v71/manifest.json",
        "recorded_at",
        "2026-07-21T10:17:38Z",
    ),
    "timeline v5": (
        "construction_timelines/2026-07-21-public-open-v5/manifest.json",
        "generated_at",
        "2026-07-21T10:25:32Z",
    ),
}


class CurrentCoverageV22Error(_v21.CurrentCoverageV21Error):
    """Raised when the v22 preparation or publication contract fails closed."""


class PendingDownstreamPinsError(CurrentCoverageV22Error):
    """Raised while a downstream replacement or publication fuse is unresolved."""


@dataclass(frozen=True)
class CurrentCoverageV22Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedV22Publication:
    bundle_identity: tuple[int, int]
    bundle_member_identities: Mapping[str, tuple[int, int]]
    bundle_stage: Path
    bundle_tree_sha256: str
    definition_identity: tuple[int, int]
    definition_raw: bytes
    definition_stage: Path
    generated_at: datetime


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CurrentCoverageV22Error(f"{label} must be canonical UTC seconds")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV22Error(f"{label} is invalid") from error
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise CurrentCoverageV22Error(f"{label} must be canonical UTC seconds")
    return parsed.astimezone(UTC)


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV22Error(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV22Error(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise CurrentCoverageV22Error(f"{label} is not canonical JSON")
    return raw, document


def _inside(package_root: Path, relative: str, label: str) -> Path:
    candidate = package_root / relative
    resolved = candidate.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV22Error(f"{label} escapes package root") from error
    return candidate


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise CurrentCoverageV22Error(f"accepted tree is not a regular directory: {root}")
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CurrentCoverageV22Error(f"accepted tree contains symlink: {path}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode()
            )
        else:
            raise CurrentCoverageV22Error(f"accepted tree entry is unsupported: {path}")
    return digest.hexdigest()


def _load_v21_base(package_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for label, spec in (
        ("definition", V21_BASE_LINEAGE["definition"]),
        ("ledger", V21_BASE_LINEAGE["ledger"]),
        ("manifest", V21_BASE_LINEAGE["manifest"]),
    ):
        path = _inside(package_root, str(spec["path"]), f"v21 {label}")
        raw, document = _read_json(path, f"v21 {label}")
        if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
            raise CurrentCoverageV22Error(f"accepted v21 {label} pin changed")
        documents[label] = document
    sidecar = _inside(
        package_root, str(V21_SIDECAR["path"]), "accepted v21 sidecar"
    )
    if sidecar.is_symlink() or not sidecar.is_file():
        raise CurrentCoverageV22Error("accepted v21 sidecar is not regular")
    sidecar_raw = sidecar.read_bytes()
    if (
        len(sidecar_raw) != V21_SIDECAR["bytes"]
        or _sha256(sidecar_raw) != V21_SIDECAR["sha256"]
    ):
        raise CurrentCoverageV22Error("accepted v21 sidecar pin changed")
    bundle = package_root / "current_coverage_ledgers/2026-07-21-v21"
    if _tree_digest(bundle) != V21_BUNDLE_TREE_SHA256:
        raise CurrentCoverageV22Error("accepted v21 bundle tree changed")
    if documents["definition"].get("ledger_id") != V21_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV22Error("accepted v21 definition identity changed")
    if documents["ledger"].get("ledger_id") != V21_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV22Error("accepted v21 ledger identity changed")
    return documents["definition"], documents["ledger"]


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v21._checkpoint(
        checkpoint_id, path, byte_count, sha256, binding=binding
    )


def _metric(
    label: str, checkpoint_id: str, pointer: str, value: Any
) -> dict[str, Any]:
    return _v21._metric(label, checkpoint_id, pointer, value)


def _replacement(
    base_entries: Mapping[str, Mapping[str, Any]],
    previous_id: str,
    new_id: str,
    *,
    checkpoints: list[dict[str, Any]],
    limitations: list[str],
    metrics: list[dict[str, Any]],
    record_units: list[str] | None = None,
) -> dict[str, Any]:
    entry = deepcopy(dict(base_entries[previous_id]))
    entry["artifact_id"] = new_id
    entry["checkpoints"] = checkpoints
    entry["limitations"] = limitations
    entry["metrics"] = metrics
    if record_units is not None:
        entry["record_units"] = sorted(record_units)
    return entry


def _accepted_replacement_entries(
    base_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    construction_map = _replacement(
        base_entries,
        "construction-map-public-open-v27",
        "construction-map-public-open-v28",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-21-public-open-v28/coverage.json",
                7_465,
                "2c46219d54acf600b902b9650d5fb2077bdcd75cf5ceff1385c67a88d9282ac4",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-21-public-open-v28.json",
                2_442,
                "52aa5b4443f60efb6ff2b983566bc194f707345e5eeaca613512c1791b6bbd85",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-21-public-open-v28/manifest.json",
                2_192,
                "199d2c73cd73871ebe183d10531e44c1c8a0f4387973730523d9c78e65f70e6f",
            ),
        ],
        limitations=[
            "Map rows are a presentation derivative of construction-master v28 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Three hundred thirty-two master observations lack coordinates, including 314 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows_unmapped",
                "coverage",
                "/projection/added_replacement_rows_unmapped",
                201,
            ),
            _metric(
                "default_visible_rows",
                "definition",
                "/expected_projection/default_visible_rows",
                6_502,
            ),
            _metric(
                "mapped_replacement_rows",
                "coverage",
                "/counts/mapped_replacement_rows",
                103,
            ),
            _metric(
                "mapped_rows_with_any_role",
                "coverage",
                "/counts/mapped_rows_with_any_role",
                75,
            ),
            _metric(
                "mapped_tier_a_rows",
                "coverage",
                "/mapped_counts/by_tier/A",
                222,
            ),
            _metric(
                "mapped_tier_b_rows",
                "coverage",
                "/mapped_counts/by_tier/B",
                6_280,
            ),
            _metric(
                "mapped_tier_c_rows",
                "coverage",
                "/mapped_counts/by_tier/C",
                102_494,
            ),
            _metric(
                "mapped_total_rows",
                "coverage",
                "/counts/mapped_observation_rows",
                108_996,
            ),
            _metric(
                "mapped_unknown_country_rows",
                "coverage",
                "/mapped_counts/by_country/Unknown",
                102_541,
            ),
            _metric(
                "master_total_rows",
                "coverage",
                "/counts/master_observation_rows",
                109_328,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/counts/unique_physical_site_count",
                None,
            ),
            _metric(
                "unmapped_rows",
                "coverage",
                "/counts/unmapped_observation_rows",
                332,
            ),
        ],
    )
    master = _replacement(
        base_entries,
        "construction-master-public-open-v27",
        "construction-master-public-open-v28",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_master/2026-07-21-public-open-v28/coverage.json",
                8_550,
                "cf3fe9a5b8864a02900f5711617f18e6a496ce6e5cdbbfb53f42875f000f553a",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-21-public-open-v28.json",
                5_659,
                "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-21-public-open-v28/manifest.json",
                9_720,
                "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c",
            ),
        ],
        limitations=[
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses, including 408 source-normalized under_construction rows, are source-scoped last-observed facts and do not establish current construction after reported_status_date.",
            "Only 536 Tier-A source-supported observation rows enter construction arithmetic; the 109,328 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows",
                "coverage",
                "/replacement_invariants/added_replacement_rows",
                217,
            ),
            _metric(
                "base_rows",
                "coverage",
                "/replacement_invariants/base_rows",
                109_111,
            ),
            _metric(
                "contract_marked_rows",
                "coverage",
                "/replacement_invariants/rows_with_contract_marker",
                416,
            ),
            _metric(
                "inherited_rows",
                "coverage",
                "/replacement_invariants/inherited_rows",
                108_912,
            ),
            _metric(
                "publication_contract_version",
                "coverage",
                "/replacement/publication_contract_version",
                4,
            ),
            _metric(
                "replacement_rows",
                "coverage",
                "/replacement_invariants/replacement_rows",
                416,
            ),
            _metric(
                "role_rows_with_any_role",
                "coverage",
                "/role_counts/rows_with_any_role",
                145,
            ),
            _metric(
                "role_rows_with_customers",
                "coverage",
                "/role_counts/with_core_role/customers",
                2,
            ),
            _metric(
                "role_rows_with_operator",
                "coverage",
                "/role_counts/with_core_role/operator",
                59,
            ),
            _metric(
                "role_rows_with_owner",
                "coverage",
                "/role_counts/with_core_role/owner",
                48,
            ),
            _metric(
                "role_rows_with_source_role_tags",
                "coverage",
                "/role_counts/rows_with_source_role_tags",
                106,
            ),
            _metric(
                "role_rows_with_tenants",
                "coverage",
                "/role_counts/with_core_role/tenants",
                7,
            ),
            _metric(
                "role_rows_with_users",
                "coverage",
                "/role_counts/with_core_role/users",
                36,
            ),
            _metric(
                "satellite_recovery_control_plane_bytes",
                "coverage",
                "/satellite_recovery_acceptance/control_plane_bytes",
                15_313,
            ),
            _metric(
                "satellite_recovery_control_plane_files",
                "coverage",
                "/satellite_recovery_acceptance/control_plane_files",
                4,
            ),
            _metric(
                "satellite_recovery_rows",
                "coverage",
                "/satellite_recovery_acceptance/rows_created",
                0,
            ),
            _metric(
                "status_under_construction_rows",
                "coverage",
                "/row_counts/by_normalized_status/under_construction",
                408,
            ),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 536),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric(
                "tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494
            ),
            _metric(
                "total_master_rows", "coverage", "/row_counts/total", 109_328
            ),
            _metric(
                "unchanged_replacement_rows",
                "coverage",
                "/replacement_invariants/unchanged_replacement_rows",
                199,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/row_counts/unique_physical_site_count",
                None,
            ),
        ],
    )
    coverage = _replacement(
        base_entries,
        "coverage-audit-public-open-v27",
        "coverage-audit-public-open-v28",
        checkpoints=[
            _checkpoint(
                "manifest",
                "audits/2026-07-21-public-open-coverage-v28/manifest.json",
                3_379,
                "e45f001d3bcd5d619889ed8bb6a96da4aed0e8e8331daed2a98bac8e65d8f1a0",
            )
        ],
        limitations=[
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 835 source and source-country groups and 4,056 open gaps are coverage-accounting units, not site counts.",
            "The satellite methodology-support artifact is non-countable review support and creates no facility, lifecycle, identity, status, or capacity claim.",
        ],
        metrics=[
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 835),
            _metric(
                "methodology_support_artifacts",
                "manifest",
                "/counts/methodology_support_artifacts",
                1,
            ),
            _metric(
                "methodology_support_jobs",
                "manifest",
                "/counts/methodology_support_jobs",
                74,
            ),
            _metric(
                "methodology_support_views",
                "manifest",
                "/counts/methodology_support_views",
                71,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "manifest",
                "/counts/non_review_source_scoped_entity_records",
                10_105,
            ),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 4_056),
            _metric(
                "review_only_source_scoped_rows",
                "manifest",
                "/counts/review_only_source_scoped_entity_records",
                6_130,
            ),
            _metric(
                "source_scoped_rows",
                "manifest",
                "/counts/source_scoped_entity_records",
                16_235,
            ),
            _metric(
                "unique_physical_sites",
                "manifest",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
    )
    federation = _replacement(
        base_entries,
        "federation-public-open-v28",
        "federation-public-open-v31",
        checkpoints=[
            _checkpoint(
                "index",
                "federated_indexes/2026-07-21-public-open-v31/federated-index.json",
                31_096,
                "02907b58973b74461a6117bc4373ea6ac06e5026b4fdf632e43fdaa05043e576",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-21-public-open-v31/manifest.json",
                986,
                "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101",
            ),
        ],
        limitations=[
            "Historical lifecycle observations are last-observed facts and do not establish current construction without later evidence.",
            "The 16,235 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,666 construction-pipeline records include 6,130 review-only fuzzy rows and only 536 non-review observations; they are not all confirmed construction sites.",
        ],
        metrics=[
            _metric(
                "capacity_observations",
                "index",
                "/counts/capacity_estimates",
                1_318,
            ),
            _metric(
                "construction_pipeline_records",
                "index",
                "/counts/construction_pipeline_records",
                6_666,
            ),
            _metric(
                "non_review_construction_pipeline_records",
                "index",
                "/counts/non_review_construction_pipeline_records",
                536,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "index",
                "/counts/non_review_source_scoped_entity_records",
                10_105,
            ),
            _metric(
                "review_only_construction_pipeline_records",
                "index",
                "/counts/review_only_construction_pipeline_records",
                6_130,
            ),
            _metric(
                "review_only_source_scoped_rows",
                "index",
                "/counts/review_only_source_scoped_entity_records",
                6_130,
            ),
            _metric(
                "source_scoped_rows",
                "index",
                "/counts/source_scoped_entity_records",
                16_235,
            ),
            _metric(
                "unique_physical_sites",
                "index",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
    )
    identity = _replacement(
        base_entries,
        "exact-identity-decisions-public-open-v6",
        "exact-identity-decisions-public-open-v8",
        checkpoints=[
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-21-public-open-v8/accounting.json",
                981,
                "f0102c137cf17a76994f94ac43c23c4f9b98963f956e295aaea16935a5d457fb",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-21-public-open-v8.json",
                1_735,
                "304144a09b1ec4773b662823501ac4a01505e2550d4a0270123fb20391980704",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-21-public-open-v8/manifest.json",
                11_438,
                "63492e7fe633591577cdbb3f8c05c5097a52ac4f85190bdc532c869d5fe93401",
            ),
        ],
        limitations=deepcopy(
            base_entries["exact-identity-decisions-public-open-v6"]["limitations"]
        ),
        metrics=[
            _metric(
                "ambiguous_identity_candidate_references",
                "accounting",
                "/ambiguous_identity_candidate_references",
                127,
            ),
            _metric(
                "canonical_topology_links",
                "accounting",
                "/canonical_topology_links",
                2_392,
            ),
            _metric(
                "exact_component_reductions",
                "accounting",
                "/exact_component_reductions",
                1_732,
            ),
            _metric(
                "exact_source_record_components",
                "accounting",
                "/exact_source_record_components",
                8_373,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "accounting",
                "/non_review_source_scoped_entity_records",
                10_105,
            ),
            _metric(
                "physical_site_lower_bound",
                "accounting",
                "/physical_site_lower_bound",
                None,
            ),
            _metric(
                "physical_site_upper_bound",
                "accounting",
                "/physical_site_upper_bound",
                None,
            ),
            _metric(
                "raw_topology_links", "accounting", "/raw_topology_links", 2_797
            ),
            _metric(
                "release_candidate_references",
                "accounting",
                "/release_candidate_references",
                100_411,
            ),
            _metric(
                "review_only_rows_in_public_accounting",
                "manifest",
                "/scope/review_only_rows_in_public_accounting",
                False,
            ),
            _metric(
                "source_scoped_entity_rows",
                "accounting",
                "/source_scoped_entity_records",
                16_235,
            ),
            _metric(
                "unique_physical_sites",
                "accounting",
                "/unique_physical_sites",
                None,
            ),
            _metric(
                "unresolved_candidate_references",
                "accounting",
                "/unresolved_candidate_references",
                100_538,
            ),
        ],
    )
    seed = _replacement(
        base_entries,
        "seed-epoch-official-v56",
        "seed-epoch-official-v71",
        checkpoints=[
            _checkpoint(
                "manifest",
                "releases/2026-07-21-open-seed-v71/manifest.json",
                12_577,
                "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
            )
        ],
        limitations=[
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; last-observed status is not current status and absent fields are not inferred from satellite imagery.",
            "The 458 freshness rows are non-additive with timeline v5 and classify current status as unknown rather than asserting current construction.",
            "The 810 source-scoped entity rows comprise 427 campus observations and 383 project observations, not deduplicated physical sites.",
        ],
        metrics=[
            _metric("campus_rows", "manifest", "/entities_by_kind/campus", 427),
            _metric(
                "capacity_observations", "manifest", "/capacity_estimates", 532
            ),
            _metric(
                "construction_pipeline_records",
                "manifest",
                "/construction_pipeline_records",
                416,
            ),
            _metric(
                "construction_source_signals",
                "manifest",
                "/construction_source_signals",
                318,
            ),
            _metric(
                "current_status_inferred",
                "manifest",
                "/current_status_inferred",
                False,
            ),
            _metric("evidence_records", "manifest", "/evidence_records", 512),
            _metric(
                "lifecycle_freshness_records",
                "manifest",
                "/lifecycle_freshness_records",
                458,
            ),
            _metric(
                "lifecycle_status_semantics",
                "manifest",
                "/lifecycle_status_semantics",
                "last_observed",
            ),
            _metric("project_rows", "manifest", "/entities_by_kind/project", 383),
            _metric(
                "publication_contract_version",
                "manifest",
                "/publication_contract_version",
                4,
            ),
            _metric(
                "resolution_candidates", "manifest", "/resolution_candidates", 6
            ),
            _metric(
                "source_scoped_entity_rows", "manifest", "/entities", 810
            ),
        ],
        record_units=[
            "capacity_observation",
            "construction_pipeline_record",
            "lifecycle_observation",
            "source_scoped_entity_row",
        ],
    )
    timeline = _replacement(
        base_entries,
        "construction-timeline-public-open-v3",
        "construction-timeline-public-open-v5",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_timelines/2026-07-21-public-open-v5/coverage.json",
                31_650,
                "e7d61b3ae399aaae5bd062e73bad7251c57396a7a00a1c36061aa01d3fb0c3ca",
                binding=("manifest", "/files/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-timeline-2026-07-21-public-open-v5.json",
                2_676,
                "f70f520e3ab887f0efea717c6850cb05dc26ce9b6b0697f96e0e6a9b8670a739",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_timelines/2026-07-21-public-open-v5/manifest.json",
                3_632,
                "aa378cde74d50b6016c5cd040a32a24e044489c0eb0fe9b412450d8abb038dba",
            ),
        ],
        limitations=[
            "Dated raw observations and last-observed statuses do not establish current construction; all 458 timeline current-status classifications remain unknown and current_construction_claimed is false.",
            "No interpolation, forecast conversion, persistence assumption, quarterly parity, cross-source identity resolution, or satellite lifecycle promotion is applied.",
            "The 474 lifecycle observations across 458 source-scoped timelines and 203 source families are not cross-source-deduplicated unique physical sites.",
            "The STT Johor under-construction observation is a stale historical fact dated 2025-02-24, not a current construction classification.",
        ],
        metrics=[
            _metric(
                "current_construction_claimed",
                "coverage",
                "/scope/current_construction_claimed",
                False,
            ),
            _metric(
                "current_status_classification",
                "coverage",
                "/scope/current_status_classification",
                "unknown",
            ),
            _metric(
                "entities_with_lifecycle_observations",
                "coverage",
                "/counts/entities_with_lifecycle_observations",
                458,
            ),
            _metric(
                "raw_lifecycle_observations",
                "coverage",
                "/counts/raw_lifecycle_observations",
                474,
            ),
            _metric(
                "source_families", "coverage", "/counts/source_families", 203
            ),
            _metric(
                "stt_current_construction_claim",
                "coverage",
                "/stt_johor_historical_only/current_construction_claim",
                False,
            ),
            _metric(
                "stt_freshness_class",
                "coverage",
                "/stt_johor_historical_only/freshness_class",
                "stale_over_365_days",
            ),
            _metric(
                "stt_observation_age_days",
                "coverage",
                "/stt_johor_historical_only/observation_age_days",
                512,
            ),
            _metric(
                "stt_status",
                "coverage",
                "/stt_johor_historical_only/status",
                "under_construction",
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/scope/unique_physical_sites",
                None,
            ),
        ],
    )
    return {
        construction_map["artifact_id"]: construction_map,
        master["artifact_id"]: master,
        coverage["artifact_id"]: coverage,
        federation["artifact_id"]: federation,
        identity["artifact_id"]: identity,
        seed["artifact_id"]: seed,
        timeline["artifact_id"]: timeline,
    }


def pending_downstream_pins() -> tuple[str, ...]:
    return tuple(
        sorted(
            artifact_id
            for artifact_id, spec in PENDING_DOWNSTREAM_REPLACEMENTS.items()
            if spec is None
        )
    )


def _require_downstream_pins() -> None:
    pending = pending_downstream_pins()
    if pending:
        raise PendingDownstreamPinsError(
            "v22 downstream pins remain unresolved: " + ", ".join(pending)
        )


def _validate_accepted_inputs(package_root: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(package_root).resolve()
    base_definition, _base_ledger = _load_v21_base(root)
    for label, (relative, byte_count, digest, mode) in _ACCEPTED_FILES.items():
        path = _inside(root, relative, f"accepted {label}")
        if path.is_symlink() or not path.is_file():
            raise CurrentCoverageV22Error(f"accepted {label} is not a regular file")
        raw = path.read_bytes()
        if (
            len(raw) != byte_count
            or _sha256(raw) != digest
            or stat.S_IMODE(path.stat().st_mode) != mode
        ):
            raise CurrentCoverageV22Error(f"accepted {label} pin or mode changed")
    for label, (relative, digest) in _ACCEPTED_TREES.items():
        path = _inside(root, relative, f"accepted {label} tree")
        if _tree_digest(path) != digest:
            raise CurrentCoverageV22Error(f"accepted {label} tree changed")
        if stat.S_IMODE(path.stat().st_mode) != 0o555:
            raise CurrentCoverageV22Error(f"accepted {label} tree is not frozen")
    now = datetime.now(UTC)
    for label, (relative, field, expected) in _SOURCE_TIMESTAMPS.items():
        path = _inside(root, relative, f"accepted {label} timestamp")
        _, document = _read_json(path, f"accepted {label} timestamp")
        if document.get(field) != expected:
            raise CurrentCoverageV22Error(f"accepted {label} timestamp changed")
        if _parse_timestamp(expected, label) > now:
            raise CurrentCoverageV22Error(f"accepted {label} timestamp is future")
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    accepted = _accepted_replacement_entries(base_entries)
    previous_id: str | None = None
    for artifact_id in sorted(accepted):
        try:
            artifact = _v21._entry_v4(root, accepted[artifact_id], previous_id)
        except _v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV22Error(str(error)) from error
        previous_id = artifact["artifact_id"]
    return accepted


_UPDATED_GAP_SUMMARIES = {
    "benchmark-parity-not-computed": (
        "No licensed, row-level external benchmark denominator is pinned; the 43 selected calibration labels and 458 source-scoped last-observed timelines provide neither recall nor SemiAnalysis-equivalent precision, feature, field, current-status, or quarterly parity."
    ),
    "global-construction-coverage-partial": (
        "The expanded official open seed, planning and permit review lanes, structural shortlist, footprint context, 458 last-observed timelines, and satellite review still do not establish a complete global construction census; the accepted Unknown034 catalog-only continuation is non-additive and promotes no source batch or site claim."
    ),
    "site-resolution-partial": (
        "Resolution links remain advisory; England, Ireland, NSW, Netherlands, New Zealand, and France observations, 458 source-scoped lifecycle timelines, and selected imagery labels are not cross-source deduplicated, no merges are accepted, and unique physical sites remain null."
    ),
}


def preview_parity_gaps(package_root: str | Path) -> list[dict[str, Any]]:
    base_definition, _ = _load_v21_base(Path(package_root).resolve())
    result: list[dict[str, Any]] = []
    for raw_gap in base_definition["parity_gaps"]:
        gap = deepcopy(raw_gap)
        gap["affected_artifact_ids"] = sorted(
            {
                ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in gap["affected_artifact_ids"]
            }
        )
        if gap["gap_id"] in _UPDATED_GAP_SUMMARIES:
            gap["summary"] = _UPDATED_GAP_SUMMARIES[gap["gap_id"]]
        result.append(gap)
    return result


def preview_v22_delta(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root).resolve()
    base_definition, _ = _load_v21_base(root)
    accepted = _validate_accepted_inputs(root)
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    unchanged = [
        base_entries[artifact_id]
        for artifact_id in sorted(set(base_entries) - REMOVED_ARTIFACT_IDS)
    ]
    removed = [
        base_entries[artifact_id] for artifact_id in sorted(REMOVED_ARTIFACT_IDS)
    ]
    if len(unchanged) != 40 or len(removed) != 7 or len(accepted) != 7:
        raise CurrentCoverageV22Error("v22 prep delta arithmetic changed")
    if _component_digest(unchanged) != UNCHANGED_40_SHA256:
        raise CurrentCoverageV22Error("v22 unchanged-entry digest changed")
    if _component_digest(removed) != REMOVED_7_SHA256:
        raise CurrentCoverageV22Error("v22 removed-entry digest changed")
    replacement_rows = [accepted[artifact_id] for artifact_id in sorted(accepted)]
    if (
        REPLACEMENT_7_SHA256 is None
        or _component_digest(replacement_rows) != REPLACEMENT_7_SHA256
    ):
        raise CurrentCoverageV22Error("v22 replacement-entry digest changed")
    combined = {entry["artifact_id"]: entry for entry in unchanged}
    combined.update(accepted)
    ordered = [combined[artifact_id] for artifact_id in sorted(combined)]
    if ALL_ENTRIES_SHA256 is None or _component_digest(ordered) != ALL_ENTRIES_SHA256:
        raise CurrentCoverageV22Error("v22 all-entry digest changed")
    if _sha256(_canonical_line(preview_parity_gaps(root))) != PARITY_GAPS_SHA256:
        raise CurrentCoverageV22Error("v22 parity-gap digest changed")
    return {
        "accepted_replacement_ids": sorted(accepted),
        "base_entries": len(base_entries),
        "final_entries": 47,
        "pending_replacement_ids": list(pending_downstream_pins()),
        "parity_gaps_sha256": PARITY_GAPS_SHA256,
        "removed_7_sha256": REMOVED_7_SHA256,
        "replacement_7_sha256": REPLACEMENT_7_SHA256,
        "unchanged_40_sha256": UNCHANGED_40_SHA256,
    }


def make_v22_definition(package_root: str | Path, *, generated_at: str) -> bytes:
    """Render v22 only after all seven replacements and final digests are sealed."""

    root = Path(package_root).resolve()
    base_definition, _ = _load_v21_base(root)
    accepted = _validate_accepted_inputs(root)
    _require_downstream_pins()
    if REPLACEMENT_7_SHA256 is None or ALL_ENTRIES_SHA256 is None:
        raise PendingDownstreamPinsError("v22 replacement digest fuses are unresolved")
    generated = _parse_timestamp(generated_at, "v22 generated_at")
    if generated_at != V22_GENERATED_AT:
        raise CurrentCoverageV22Error("v22 generated_at changed")
    for label, (_relative, _field, expected) in _SOURCE_TIMESTAMPS.items():
        if _parse_timestamp(expected, label) > generated:
            raise CurrentCoverageV22Error(
                f"accepted {label} post-dates v22 generated_at"
            )
    replacements = dict(accepted)
    replacements.update(
        {
            artifact_id: deepcopy(dict(spec))
            for artifact_id, spec in PENDING_DOWNSTREAM_REPLACEMENTS.items()
            if spec is not None
        }
    )
    if set(replacements) != REPLACEMENT_ARTIFACT_IDS:
        raise CurrentCoverageV22Error("v22 replacement inventory changed")
    base_entries = {
        entry["artifact_id"]: deepcopy(entry)
        for entry in base_definition["entries"]
    }
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    ordered = [base_entries[artifact_id] for artifact_id in sorted(base_entries)]
    replacement_rows = [
        base_entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
    ]
    if (
        len(ordered) != 47
        or _component_digest(replacement_rows) != REPLACEMENT_7_SHA256
        or _component_digest(ordered) != ALL_ENTRIES_SHA256
    ):
        raise CurrentCoverageV22Error("v22 sealed entry digest changed")
    document = {
        "base_ledger": V21_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": generated_at,
        "ledger_id": V22_LEDGER_ID,
        "parity_gaps": preview_parity_gaps(root),
        "schema_version": DEFINITION_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    forbidden = {
        *REMOVED_ARTIFACT_IDS,
        "epoch-official-open-seed-v68",
        "federation-public-open-v29",
        "federation-public-open-v30",
    }
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV22Error("v22 contains superseded or rejected lineage")
    return raw


def _validate_v22_definition(
    definition_path: str | Path,
    *,
    require_live: bool,
) -> tuple[dict[str, Any], bytes, Path, datetime]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path.parent != package_root / "sources":
        raise CurrentCoverageV22Error("v22 definition stage must be inside sources")
    raw, document = _read_json(path, "v22 definition")
    if stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise CurrentCoverageV22Error("v22 definition must be frozen 0444")
    if V22_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v22 definition digest fuse is unresolved")
    if _sha256(raw) != V22_DEFINITION_SHA256:
        raise CurrentCoverageV22Error("v22 definition content changed")
    generated_at = document.get("generated_at")
    if raw != make_v22_definition(package_root, generated_at=generated_at):
        raise CurrentCoverageV22Error(
            "v22 definition differs from its pinned transformation"
        )
    if set(document) != {
        "base_ledger",
        "entries",
        "generated_at",
        "ledger_id",
        "parity_gaps",
        "schema_version",
        "scope",
    }:
        raise CurrentCoverageV22Error("v22 definition keys differ")
    if (
        document.get("base_ledger") != V21_BASE_LINEAGE
        or document.get("ledger_id") != V22_LEDGER_ID
        or document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4
        or document.get("scope") != SCOPE_POLICY
    ):
        raise CurrentCoverageV22Error("v22 identity, base, schema, or scope changed")
    generated = _parse_timestamp(generated_at, "v22 generated_at")
    if require_live and generated > datetime.now(UTC):
        raise CurrentCoverageV22Error("v22 generated_at is not yet live")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 47:
        raise CurrentCoverageV22Error("v22 must contain exactly 47 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if (
        len(artifact_ids) != 47
        or None in artifact_ids
        or artifact_ids & REMOVED_ARTIFACT_IDS
        or not REPLACEMENT_ARTIFACT_IDS <= artifact_ids
    ):
        raise CurrentCoverageV22Error("v22 entry inventory is invalid")
    return document, raw, package_root, generated


def build_current_coverage_ledger_v22(
    definition_path: str | Path,
) -> CurrentCoverageV22Bundle:
    """Reproduce all three v22 bundle files without publishing any path."""

    definition, definition_raw, package_root, _generated = _validate_v22_definition(
        definition_path, require_live=False
    )
    _base_definition, base_ledger = _load_v21_base(package_root)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    for spec in definition["entries"]:
        try:
            artifact = _v21._entry_v4(package_root, spec, previous_id)
        except _v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV22Error(str(error)) from error
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _v21._legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _v21._legacy.CurrentCoverageError as error:
        raise CurrentCoverageV22Error(str(error)) from error
    inventory_counts = _v21._inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(base_ledger["artifact_inventory_counts"])
    expected_inventory["by_record_unit"]["lifecycle_observation"] += 1
    if inventory_counts != expected_inventory:
        raise CurrentCoverageV22Error("v22 artifact inventory arithmetic changed")
    generated_at = definition["generated_at"]
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V21_BASE_LINEAGE,
        "format": LEDGER_FORMAT_V4,
        "generated_at": generated_at,
        "ledger_id": V22_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    ledger_bytes = _canonical_json(ledger)
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "base_ledger": V21_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V22_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT_V4,
        "generated_at": generated_at,
        "input_checkpoints": {
            artifact["artifact_id"]: {
                checkpoint["checkpoint_id"]: {
                    "bytes": checkpoint["bytes"],
                    "path": checkpoint["path"],
                    "sha256": checkpoint["sha256"],
                }
                for checkpoint in artifact["checkpoints"]
            }
            for artifact in artifacts
        },
        "ledger_id": V22_LEDGER_ID,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV22Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _validate_v22_bundle(
    output_path: str | Path,
    *,
    definition_path: str | Path,
    require_live: bool,
) -> dict[str, Any]:
    _require_downstream_pins()
    directory = Path(os.path.abspath(os.fspath(output_path)))
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV22Error("v22 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV22Error("v22 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV22Error("v22 bundle must be frozen 0555/0444")
    definition, _definition_raw, _root, generated = _validate_v22_definition(
        definition_path, require_live=require_live
    )
    expected = build_current_coverage_ledger_v22(definition_path)
    expected_files = {
        LEDGER_FILENAME: expected.ledger_bytes,
        MANIFEST_FILENAME: expected.manifest_bytes,
        MANIFEST_HASH_FILENAME: expected.manifest_hash_bytes,
    }
    for filename, expected_raw in expected_files.items():
        path = directory / filename
        if path.read_bytes() != expected_raw:
            raise CurrentCoverageV22Error(f"v22 {filename} differs")
    if require_live:
        _assert_final_root_ctimes(
            (Path(definition_path), directory), generated
        )
    if definition["generated_at"] != expected.manifest["generated_at"]:
        raise CurrentCoverageV22Error("v22 definition and bundle time differ")
    return dict(expected.manifest)


def _aware_utc(value: datetime | None, label: str) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise CurrentCoverageV22Error(f"{label} lacks timezone")
    return result.astimezone(UTC)


def _stage_paths(definition_stage: Path, bundle_stage: Path) -> tuple[Path, ...]:
    if definition_stage.is_symlink() or not definition_stage.is_file():
        raise CurrentCoverageV22Error("v22 definition stage must be a regular file")
    if bundle_stage.is_symlink() or not bundle_stage.is_dir():
        raise CurrentCoverageV22Error("v22 bundle stage must be a regular directory")
    descendants = sorted(
        bundle_stage.rglob("*"), key=lambda path: path.relative_to(bundle_stage).as_posix()
    )
    for path in descendants:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise CurrentCoverageV22Error(f"v22 stage is contaminated: {path}")
    return (definition_stage, bundle_stage, *descendants)


def _assert_stage_precedes_target(
    paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise CurrentCoverageV22Error("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target + 0.000_001:
            raise CurrentCoverageV22Error(
                f"v22 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctimes(
    final_paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in final_paths:
        if path.is_symlink() or not path.exists():
            raise CurrentCoverageV22Error(f"v22 final root is absent: {path}")
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target:
            raise CurrentCoverageV22Error(
                f"v22 final root rename predates generated_at: {path.name}"
            )


def validate_private_staging_boundary(
    staged_definition: str | Path,
    staged_bundle: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    wall_clock: datetime | None = None,
) -> datetime:
    """Allow hidden future-dated stages only when every staged inode precedes it."""

    definition_stage = Path(staged_definition)
    bundle_stage = Path(staged_bundle)
    _raw, document = _read_json(definition_stage, "staged v22 definition")
    if document.get("ledger_id") != V22_LEDGER_ID:
        raise CurrentCoverageV22Error("staged v22 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV22Error("staged v22 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v22 generated_at")
    now = _aware_utc(wall_clock, "v22 staging wall clock")
    if now >= generated:
        raise CurrentCoverageV22Error(
            "v22 generated_at must remain future while private staging completes"
        )
    for final in (Path(final_definition), Path(final_bundle)):
        if final.exists() or final.is_symlink():
            raise CurrentCoverageV22Error("v22 final path exposed during staging")
    _assert_stage_precedes_target(
        _stage_paths(definition_stage, bundle_stage), generated
    )
    return generated


def validate_prepublication_boundary(
    staged_definition: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    staged_bundle: str | Path | None = None,
    wall_clock: datetime | None = None,
) -> datetime:
    """Reject early exposure, a non-live target, or post-target staged bytes."""

    stage = Path(staged_definition)
    raw, document = _read_json(stage, "staged v22 definition")
    if document.get("ledger_id") != V22_LEDGER_ID:
        raise CurrentCoverageV22Error("staged v22 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV22Error("staged v22 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v22 generated_at")
    now = _aware_utc(wall_clock, "v22 publication wall clock")
    final_definition_path = Path(final_definition)
    final_bundle_path = Path(final_bundle)
    definition_exposed = (
        final_definition_path.exists() or final_definition_path.is_symlink()
    )
    bundle_exposed = final_bundle_path.exists() or final_bundle_path.is_symlink()
    if now < generated and definition_exposed:
        raise CurrentCoverageV22Error(
            "final v22 definition was exposed before generated_at"
        )
    if now < generated and bundle_exposed:
        raise CurrentCoverageV22Error(
            "final v22 bundle was exposed before generated_at"
        )
    if definition_exposed or bundle_exposed:
        raise CurrentCoverageV22Error("v22 final path collision")
    if now < generated:
        raise CurrentCoverageV22Error("v22 generated_at is not yet live")
    if V22_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v22 definition digest fuse is unresolved")
    if _sha256(raw) != V22_DEFINITION_SHA256:
        raise CurrentCoverageV22Error("staged v22 definition digest changed")
    if staged_bundle is not None:
        bundle_stage = Path(staged_bundle)
        _validate_v22_bundle(
            bundle_stage, definition_path=stage, require_live=False
        )
        paths = _stage_paths(stage, bundle_stage)
    else:
        paths = (stage,)
    _assert_stage_precedes_target(paths, generated)
    return generated


def preflight_v22_publication(package_root: str | Path) -> dict[str, Any]:
    """Validate accepted inputs and report the unresolved publication fuses."""

    root = Path(package_root).resolve()
    preview = preview_v22_delta(root)
    final_definition = root / V22_DEFINITION_PATH
    final_bundle = root / V22_BUNDLE_PATH
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV22Error("v22 final definition must remain absent")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV22Error("v22 final bundle must remain absent")
    _require_downstream_pins()
    if V22_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v22 definition digest fuse is unresolved")
    return preview


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    if not expected:
        raise CurrentCoverageV22Error(f"v22 stage type changed: {path}")
    return metadata.st_dev, metadata.st_ino


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV22Error("refusing substituted v22 definition stage")
    path.chmod(0o600)
    path.unlink()


def _discard_bundle_stage(
    path: Path,
    identity: tuple[int, int],
    member_identities: Mapping[str, tuple[int, int]] | None = None,
) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV22Error("refusing substituted v22 bundle stage")
    entries = list(path.iterdir())
    if not {entry.name for entry in entries}.issubset(BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV22Error("refusing contaminated v22 bundle cleanup")
    if member_identities is not None:
        actual = {
            entry.name: (
                entry.stat(follow_symlinks=False).st_dev,
                entry.stat(follow_symlinks=False).st_ino,
            )
            for entry in entries
        }
        if actual != dict(member_identities):
            raise CurrentCoverageV22Error(
                "refusing identity-changed v22 bundle cleanup"
            )
    path.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    path.rmdir()


@contextmanager
def _publication_locks(
    final_definition: Path, final_bundle: Path
) -> Iterator[None]:
    try:
        with _v21._exclusive_output_lock(final_definition):
            with _v21._exclusive_output_lock(final_bundle):
                yield
    except _v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV22Error(str(error).replace("v21", "v22")) from error


def _require_final_paths_absent(
    final_definition: Path, final_bundle: Path, label: str
) -> None:
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV22Error(f"{label} v22 definition path is occupied")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV22Error(f"{label} v22 bundle path is occupied")


def _prepare_v22_publication(
    package_root: Path,
    *,
    generated_at: str,
    wall_clock: datetime,
) -> _PreparedV22Publication:
    final_definition = package_root / V22_DEFINITION_PATH
    final_bundle = package_root / V22_BUNDLE_PATH
    raw = make_v22_definition(package_root, generated_at=generated_at)
    if V22_DEFINITION_SHA256 is None or _sha256(raw) != V22_DEFINITION_SHA256:
        raise CurrentCoverageV22Error("v22 staged definition digest changed")

    definition_stage: Path | None = None
    bundle_stage: Path | None = None
    definition_identity: tuple[int, int] | None = None
    bundle_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{final_definition.name}.",
            suffix=".stage",
            dir=final_definition.parent,
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
        definition_stage.chmod(0o444)
        _fsync_regular(definition_stage)

        bundle_stage = Path(
            tempfile.mkdtemp(
                prefix=f".{final_bundle.name}.", dir=final_bundle.parent
            )
        )
        bundle_identity = _path_identity(bundle_stage, directory=True)
        bundle = build_current_coverage_ledger_v22(definition_stage)
        staged_files = {
            LEDGER_FILENAME: bundle.ledger_bytes,
            MANIFEST_FILENAME: bundle.manifest_bytes,
            MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
        }
        for filename, content in staged_files.items():
            path = bundle_stage / filename
            _v21._write_file(path, content)
            path.chmod(0o444)
            _fsync_regular(path)
        bundle_stage.chmod(0o555)
        _fsync_directory(bundle_stage)
        _validate_v22_bundle(
            bundle_stage, definition_path=definition_stage, require_live=False
        )
        generated = validate_private_staging_boundary(
            definition_stage,
            bundle_stage,
            final_definition,
            final_bundle,
            wall_clock=wall_clock,
        )
        return _PreparedV22Publication(
            bundle_identity=bundle_identity,
            bundle_member_identities={
                path.name: _path_identity(path, directory=False)
                for path in bundle_stage.iterdir()
            },
            bundle_stage=bundle_stage,
            bundle_tree_sha256=_tree_digest(bundle_stage),
            definition_identity=definition_identity,
            definition_raw=raw,
            definition_stage=definition_stage,
            generated_at=generated,
        )
    except BaseException as primary_error:
        try:
            if bundle_stage is not None and bundle_identity is not None:
                _discard_bundle_stage(bundle_stage, bundle_identity)
            if definition_stage is not None and definition_identity is not None:
                _discard_file_stage(definition_stage, definition_identity)
        except Exception as cleanup_error:
            primary_error.add_note(f"v22 stage cleanup failed: {cleanup_error}")
        raise


def _wait_until(
    target: float,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    while True:
        remaining = target - clock()
        if remaining <= 0:
            return
        sleeper(min(remaining, 0.25))


def _path_has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    expected_type = (
        stat.S_ISDIR(metadata.st_mode)
        if directory
        else stat.S_ISREG(metadata.st_mode)
    )
    return expected_type and (metadata.st_dev, metadata.st_ino) == identity


def _rollback_owned_bundle_promotion(
    prepared: _PreparedV22Publication, final_bundle: Path
) -> None:
    if not _path_has_identity(
        final_bundle, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV22Error(
            "refusing rollback of a substituted v22 final bundle"
        )
    if prepared.bundle_stage.exists() or prepared.bundle_stage.is_symlink():
        raise CurrentCoverageV22Error(
            "refusing rollback over an occupied v22 private bundle stage"
        )
    try:
        _v21._promote_noreplace(final_bundle, prepared.bundle_stage)
    except _v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV22Error(
            str(error).replace("v21", "v22")
        ) from error
    if final_bundle.exists() or final_bundle.is_symlink() or not _path_has_identity(
        prepared.bundle_stage, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV22Error(
            "v22 bundle rollback did not restore the owned private inode"
        )
    _fsync_directory(final_bundle.parent)


def _promote_staged_pair(
    prepared: _PreparedV22Publication,
    final_definition: Path,
    final_bundle: Path,
) -> None:
    try:
        _v21._promote_noreplace(prepared.bundle_stage, final_bundle)
    except _v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV22Error(
            str(error).replace("v21", "v22")
        ) from error
    if not _path_has_identity(final_bundle, prepared.bundle_identity, directory=True):
        raise CurrentCoverageV22Error("v22 final bundle identity changed on promotion")
    _fsync_directory(final_bundle.parent)
    try:
        _v21._promote_noreplace(prepared.definition_stage, final_definition)
    except BaseException as definition_error:
        try:
            _rollback_owned_bundle_promotion(prepared, final_bundle)
        except Exception as rollback_error:
            definition_error.add_note(
                f"v22 owned-bundle rollback failed: {rollback_error}"
            )
        if isinstance(definition_error, _v21.CurrentCoverageV21Error):
            raise CurrentCoverageV22Error(
                str(definition_error).replace("v21", "v22")
            ) from definition_error
        raise
    if not _path_has_identity(
        final_definition, prepared.definition_identity, directory=False
    ):
        raise CurrentCoverageV22Error(
            "v22 final definition identity changed on promotion"
        )
    _fsync_directory(final_definition.parent)


def publish_current_coverage_v22(
    package_root: str | Path,
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Stage both artifacts before target, then publish them without replacement."""

    root = Path(package_root).resolve()
    final_definition = root / V22_DEFINITION_PATH
    final_bundle = root / V22_BUNDLE_PATH
    target = _parse_timestamp(generated_at, "v22 generated_at")
    if _clock() >= target.timestamp():
        raise CurrentCoverageV22Error(
            "v22 generated_at must be future before private staging starts"
        )
    preflight_v22_publication(root)
    with _publication_locks(final_definition, final_bundle):
        _require_final_paths_absent(final_definition, final_bundle, "initial")
        prepared = _prepare_v22_publication(
            root,
            generated_at=generated_at,
            wall_clock=datetime.fromtimestamp(_clock(), UTC),
        )
        try:
            _require_final_paths_absent(final_definition, final_bundle, "pre-wait")
            _wait_until(target.timestamp(), clock=_clock, sleeper=_sleep)
            validate_prepublication_boundary(
                prepared.definition_stage,
                final_definition,
                final_bundle,
                staged_bundle=prepared.bundle_stage,
                wall_clock=datetime.fromtimestamp(_clock(), UTC),
            )
            if (
                prepared.definition_stage.read_bytes() != prepared.definition_raw
                or _tree_digest(prepared.bundle_stage)
                != prepared.bundle_tree_sha256
            ):
                raise CurrentCoverageV22Error(
                    "v22 private stage changed while awaiting publication"
                )
            _require_final_paths_absent(final_definition, final_bundle, "late")
            _promote_staged_pair(
                prepared, final_definition, final_bundle
            )
            if stat.S_IMODE(final_definition.stat().st_mode) != 0o444:
                raise CurrentCoverageV22Error(
                    "v22 final definition must be frozen 0444"
                )
            _assert_final_root_ctimes(
                (final_definition, final_bundle), prepared.generated_at
            )
        except BaseException as primary_error:
            try:
                owned_final_exists = _path_has_identity(
                    final_definition,
                    prepared.definition_identity,
                    directory=False,
                ) or _path_has_identity(
                    final_bundle, prepared.bundle_identity, directory=True
                )
                if not owned_final_exists:
                    if (
                        prepared.bundle_stage.exists()
                        and _tree_digest(prepared.bundle_stage)
                        != prepared.bundle_tree_sha256
                    ):
                        raise CurrentCoverageV22Error(
                            "refusing cleanup of changed v22 private bundle"
                        )
                    _discard_bundle_stage(
                        prepared.bundle_stage,
                        prepared.bundle_identity,
                        prepared.bundle_member_identities,
                    )
                    _discard_file_stage(
                        prepared.definition_stage, prepared.definition_identity
                    )
            except Exception as cleanup_error:
                primary_error.add_note(f"v22 stage cleanup failed: {cleanup_error}")
            raise
    return validate_current_coverage_ledger_v22(
        final_bundle, definition_path=final_definition
    )


def write_v22_definition(
    package_root: str | Path, output_path: str | Path, *, generated_at: str
) -> str:
    """Refuse publication until all downstream and digest fuses are sealed."""

    preflight_v22_publication(package_root)
    raw = make_v22_definition(package_root, generated_at=generated_at)
    if _sha256(raw) != V22_DEFINITION_SHA256:
        raise CurrentCoverageV22Error("v22 definition digest changed")
    destination = Path(os.path.abspath(os.fspath(output_path)))
    if destination.exists() or destination.is_symlink():
        raise CurrentCoverageV22Error(f"refusing existing output: {destination}")
    raise CurrentCoverageV22Error(
        "v22 definition cannot publish alone; use the paired v22 publisher"
    )


def write_current_coverage_ledger_v22(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    if freeze is not True:
        raise CurrentCoverageV22Error("v22 publication requires freeze=True")
    definition = Path(definition_path)
    root = definition.parent.parent.resolve()
    preflight_v22_publication(root)
    if Path(output_path).resolve() != root / V22_BUNDLE_PATH:
        raise CurrentCoverageV22Error("v22 bundle publication path changed")
    raise CurrentCoverageV22Error(
        "v22 bundle cannot publish alone; use the paired v22 publisher"
    )


def validate_current_coverage_ledger_v22(
    output_path: str | Path, *, definition_path: str | Path
) -> dict[str, Any]:
    _require_downstream_pins()
    definition = Path(definition_path).resolve()
    root = definition.parent.parent.resolve()
    output = Path(output_path).resolve()
    if definition != root / V22_DEFINITION_PATH:
        raise CurrentCoverageV22Error("v22 definition publication path changed")
    if output != root / V22_BUNDLE_PATH:
        raise CurrentCoverageV22Error("v22 bundle publication path changed")
    return _validate_v22_bundle(
        output, definition_path=definition, require_live=True
    )


__all__ = [
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_KINDS_V4",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT_V4",
    "CurrentCoverageV22Bundle",
    "CurrentCoverageV22Error",
    "DEFINITION_SCHEMA_VERSION_V4",
    "LEDGER_FORMAT_V4",
    "LEDGER_SCHEMA_VERSION_V4",
    "PENDING_DOWNSTREAM_PIN_BLUEPRINT",
    "PENDING_DOWNSTREAM_REPLACEMENTS",
    "PendingDownstreamPinsError",
    "PARITY_GAPS_SHA256",
    "RECORD_UNITS_V4",
    "REMOVED_7_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_7_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "SCOPE_POLICY",
    "UNCHANGED_40_SHA256",
    "V21_BASE_LINEAGE",
    "V22_BUNDLE_PATH",
    "V22_DEFINITION_PATH",
    "V22_DEFINITION_SHA256",
    "V22_GENERATED_AT",
    "V22_LEDGER_ID",
    "build_current_coverage_ledger_v22",
    "make_v22_definition",
    "pending_downstream_pins",
    "preflight_v22_publication",
    "preview_parity_gaps",
    "preview_v22_delta",
    "publish_current_coverage_v22",
    "validate_current_coverage_ledger_v22",
    "validate_private_staging_boundary",
    "validate_prepublication_boundary",
    "write_current_coverage_ledger_v22",
    "write_v22_definition",
]
