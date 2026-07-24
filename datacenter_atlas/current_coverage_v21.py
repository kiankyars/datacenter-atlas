"""Schema-v4 current-coverage ledger v21.

V21 is a byte-semantic successor of the accepted frozen v20 ledger. It keeps
forty unrelated entries unchanged, replaces the five public-core entries with
the accepted v27/v28/v6 chain, collapses the overlapping Unknown030 and
Unknown033 catalog checkpoints into one non-additive Unknown034 continuation,
and adds the accepted construction-timeline v3 row release. Schema v4 changes
only the controlled vocabularies needed by that timeline: ``construction_timeline``
and ``lifecycle_observation``. Historical status remains last-observed,
current construction remains unknown, and unique physical sites remain null.
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
from typing import Any, Iterator, Mapping, Sequence

from . import construction_map_v11 as _map_v11
from . import construction_master_v11 as _master_v11
from . import construction_timeline_v3 as _timeline_v3
from . import coverage_audit_v3 as _coverage_v3
from . import current_coverage as _legacy
from . import current_coverage_v20 as _v20
from . import exact_identity_decisions_v3 as _identity_v3
from . import federated_release_v3 as _federation_v3


V21_LEDGER_ID = "current-coverage-2026-07-21-v21"
V21_GENERATED_AT = "2026-07-21T08:40:00Z"
V21_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v21.json"
V21_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v21"
V21_DEFINITION_SHA256 = (
    "116fdc6beb9c03ba386c80aab43de406049567246e7a40f439c5712b0101ea78"
)

DEFINITION_SCHEMA_VERSION_V4 = 4
LEDGER_SCHEMA_VERSION_V4 = 4
LEDGER_FORMAT_V4 = "datacenter-atlas-current-coverage-ledger-v4"
BUNDLE_FORMAT_V4 = "datacenter-atlas-current-coverage-ledger-bundle-v4"

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2
ARTIFACT_KINDS_V4 = _legacy.ARTIFACT_KINDS | {"construction_timeline"}
RECORD_UNITS_V4 = _legacy.RECORD_UNITS | {"lifecycle_observation"}

V20_BASE_LINEAGE = {
    "definition": {
        "bytes": 143_354,
        "path": "sources/current-coverage-2026-07-20-v20.json",
        "sha256": "8a8aca77431ca21867f8f3317114b40cb41c642aacc9f333d7eb1f1a402410b3",
    },
    "ledger": {
        "bytes": 98_623,
        "path": (
            "current_coverage_ledgers/2026-07-20-v20/current-coverage-ledger.json"
        ),
        "sha256": "6a500f9d5b54aa695d1914e7f0c102696ad3e5cfd35d7dcb3105f34760e7bc3a",
    },
    "ledger_id": "current-coverage-2026-07-20-v20",
    "manifest": {
        "bytes": 27_429,
        "path": "current_coverage_ledgers/2026-07-20-v20/manifest.json",
        "sha256": "9e5eaee21e02888f361258fb6ee71a86664831f4073144641d43ad95a6361a26",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v26": "construction-map-public-open-v27",
    "construction-master-public-open-v26": "construction-master-public-open-v27",
    "coverage-audit-public-open-v26": "coverage-audit-public-open-v27",
    "exact-identity-decisions-public-open-v5": (
        "exact-identity-decisions-public-open-v6"
    ),
    "federation-public-open-v27": "federation-public-open-v28",
}
SATELLITE_REPLACEMENTS = {
    "satellite-recovery-unknown033-review-v1": (
        "satellite-unknown034-continuation-review-v1"
    ),
    "satellite-unknown-batch-030": ("satellite-unknown034-continuation-review-v1"),
}
TIMELINE_ARTIFACT_ID = "construction-timeline-public-open-v3"
SATELLITE_ARTIFACT_ID = "satellite-unknown034-continuation-review-v1"
ADDED_ARTIFACT_IDS = frozenset({TIMELINE_ARTIFACT_ID, SATELLITE_ARTIFACT_ID})
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS) | frozenset(
    SATELLITE_REPLACEMENTS
)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS

EXCLUDED_DISCOVERY_ARTIFACTS = {
    "global-underrepresented-official-discovery-2026-07-21-v1": {
        "bytes": 1_364,
        "path": (
            "source_artifacts/"
            "global-underrepresented-official-discovery-2026-07-21-v1/"
            "manifest.json"
        ),
        "sha256": "2a55ae530cdb478fd922d6fad30ce836682671cb0fed95a040d2788e6292c7be",
    },
    "second-underrepresented-official-discovery-2026-07-21-v1": {
        "bytes": 1_423,
        "path": (
            "source_artifacts/"
            "second-underrepresented-official-discovery-2026-07-21-v1/"
            "manifest.json"
        ),
        "sha256": "df5e44d95af1fe7b81c10f3d58006b4db6cbe68816aa502673b93c863c1b9750",
    },
}
EXCLUDED_CONCURRENT_ARTIFACT_MARKERS = frozenset(
    {
        "2026-07-21-global-open-v3-unknown-034-delta-review-v1",
        "unknown-034-delta-reselection-v2-001",
        "unknown-034-delta-reselected-v2-001",
        "unknown-034-delta-single-asset-v2-001",
    }
)

UNCHANGED_40_SHA256 = "807cd0c9ebb2b66da338c38700217f1004ea453d4e5eea609a5d048941eda83a"
REPLACEMENT_5_SHA256 = (
    "940efac618026aa4e3163f39bedf095fe59912890418b47ed9938808e730061f"
)
ADDED_2_SHA256 = "9b393d3fca6be132313b53648e8976e3a121b0edfa1eadcdec6a538ebea5c832"
REMOVED_7_SHA256 = "63b97aca733d1a1edbe0ac1a319d1be0a342896838951e3204094a48a5108d29"
ALL_ENTRIES_SHA256 = "4d34376df8eed90f3fad95e62f119bdec1e5c52ef7d9dbaf7a246b161e8c49c9"
PARITY_GAPS_SHA256 = "9332737caee2f11145c60557d954947d2fd7d6e464c5ccc53c94c7ceeab1245c"

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v20",
    "sha256": "96994eed8d97aba06f7f303bd39a75f3459bb0862150a72020513b72f403758f",
}

_ACCEPTED_TREES = {
    "construction-map-v27": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-21-public-open-v27",
        "sha256": "55a9811b96d5d644f325c4b82082c8c96c60c21011302fd43ed0e07b76fb665d",
    },
    "construction-master-v27": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-21-public-open-v27",
        "sha256": "15f5a8c5630faa28c45c7aaa4cb4cd212b472441db4c9e3a9daf80fb23bc25a9",
    },
    "construction-timeline-v3": {
        "directories": 1,
        "files": 7,
        "path": "construction_timelines/2026-07-21-public-open-v3",
        "sha256": "4b8bf25f4177bdeeacb87a17836060de225172db73731a2e73a192ce78ce773a",
    },
    "coverage-audit-v27": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-21-public-open-coverage-v27",
        "sha256": "a2f945f421e22776633c0dc5960301d429ef629882e7361204cd35912ab764e1",
    },
    "exact-identity-decisions-v6": {
        "directories": 1,
        "files": 9,
        "path": "exact_identity_decisions/2026-07-21-public-open-v6",
        "sha256": "44057ef4e03b3ce4412fb4d89b7e673cf9da8a289eb13ecbca6e11dcb9a4505d",
    },
    "federation-v28": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-21-public-open-v28",
        "sha256": "88113b5342b48be3dbe663bdc4da2fe57a5de75c983220f42e2ccc822b3f501a",
    },
    "unknown034-continuation": {
        "directories": 1,
        "files": 2,
        "path": (
            "satellite_review_continuations/"
            "2026-07-21-global-open-v3-unknown-034-continued-25"
        ),
        "sha256": "6a4cae88a202c6a7cfc06b7eef06668b2671ba51c0f693e1deab80f2079aec3e",
    },
}

_PINNED_FILES = {
    "v20 implementation": (
        "datacenter_atlas/current_coverage_v20.py",
        49_253,
        "d53d63e326b7f9a1459b51fdf937b12fb3c73aa3bdeaa76a1217b5ba27d538ee",
    ),
    "v20 compatibility wrapper": (
        "current_coverage_v20.py",
        150,
        "3a173a062509392117c12d04cecd363a4f367044e42bd8d9367ec3d92040a291",
    ),
    "v20 definition": (
        V20_BASE_LINEAGE["definition"]["path"],
        V20_BASE_LINEAGE["definition"]["bytes"],
        V20_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v20 ledger": (
        V20_BASE_LINEAGE["ledger"]["path"],
        V20_BASE_LINEAGE["ledger"]["bytes"],
        V20_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v20 manifest": (
        V20_BASE_LINEAGE["manifest"]["path"],
        V20_BASE_LINEAGE["manifest"]["bytes"],
        V20_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v20 sidecar": (
        "current_coverage_ledgers/2026-07-20-v20/manifest.sha256",
        80,
        "0ddf7f0699d1f8330df449956a7bafe86823dddbc124f8bccd30593d8368febf",
    ),
    "construction map v27 definition": (
        "sources/construction-map-2026-07-21-public-open-v27.json",
        2_442,
        "a7d62e22778ce4c70e5fbe015e67b5cf2702f19862dc63d93896d669bf4638f4",
    ),
    "construction map v27 coverage": (
        "construction_maps/2026-07-21-public-open-v27/coverage.json",
        7_465,
        "02edcf096c49e8e164b03f6270b38603c4464d3070198d11e69165c4002e8438",
    ),
    "construction map v27 manifest": (
        "construction_maps/2026-07-21-public-open-v27/manifest.json",
        2_192,
        "7115033102529e7dcca992960948463ead7f7d74a717510fdddbcfa2e89c6c38",
    ),
    "construction master v27 definition": (
        "sources/construction-master-2026-07-21-public-open-v27.json",
        5_659,
        "c0f2a5c89e44838da876d7629dc39f49bdaa497d882a2826fff92e6e7080198b",
    ),
    "construction master v27 coverage": (
        "construction_master/2026-07-21-public-open-v27/coverage.json",
        8_550,
        "8df2ba8c2211b0b55a363088b22ca14c5a6b508d6788dcae7e804a1ca6050635",
    ),
    "construction master v27 manifest": (
        "construction_master/2026-07-21-public-open-v27/manifest.json",
        9_720,
        "6a5f48a0c86220c66d13fc1bd0ec7a9716e624d3d952599e3b6660e07717f5e7",
    ),
    "coverage audit v27 definition": (
        "sources/coverage-audit-2026-07-21-public-open-v27.json",
        5_920,
        "0224660dd28426c51eb5a76d1264e46b7da629f42d9de2648296b0b0f7b6e9ec",
    ),
    "coverage audit v27 manifest": (
        "audits/2026-07-21-public-open-coverage-v27/manifest.json",
        3_379,
        "fc3c4af31d6f37f103d08ca4f1e9f78fa87a82e692c9abd19ddd9002176be64f",
    ),
    "exact identity v6 definition": (
        "sources/exact-identity-decisions-2026-07-21-public-open-v6.json",
        1_735,
        "2b9b26f452ebfc3d36f4bb36d9cc7198a29b8be8806657750f440a928671d759",
    ),
    "exact identity v6 accounting": (
        "exact_identity_decisions/2026-07-21-public-open-v6/accounting.json",
        981,
        "8dc15c12f4b6d5d0cebc309a5ab46d2eeb10b835906a43dbdd8c80d95fb8d922",
    ),
    "exact identity v6 manifest": (
        "exact_identity_decisions/2026-07-21-public-open-v6/manifest.json",
        11_438,
        "0af1e65f5b772b87e7dfe5b5c195513e79f31d4b5648fdcae5fd343f86f82ee9",
    ),
    "federation v28 definition": (
        "sources/federation-2026-07-21-public-open-v28.json",
        1_788,
        "6dbc1095c7fd8b6d36e217263aac23b0c612e84b7d781fa5cc32fbaa2c4e57d9",
    ),
    "federation v28 index": (
        "federated_indexes/2026-07-21-public-open-v28/federated-index.json",
        30_388,
        "d21cfa01157dc7529d71bfd99d4f6d2bbc74285a8c58392ee402dc767faf3210",
    ),
    "federation v28 manifest": (
        "federated_indexes/2026-07-21-public-open-v28/manifest.json",
        986,
        "d465a2de75b94168113b712740a1761e93887c1bc998a5164ba54489202e5f6e",
    ),
    "timeline v3 definition": (
        "sources/construction-timeline-2026-07-21-public-open-v3.json",
        2_838,
        "698648dda386a00e62247a4fdaf1aaf83ca2bc62f865ea366c5f51da2813d055",
    ),
    "timeline v3 coverage": (
        "construction_timelines/2026-07-21-public-open-v3/coverage.json",
        72_215,
        "6fbe901557f1f872c668c76f4f668d1548b9f2fc9c25509bab0aad4ba01b01c8",
    ),
    "timeline v3 manifest": (
        "construction_timelines/2026-07-21-public-open-v3/manifest.json",
        3_794,
        "4dc0c03968d2b3b07db225df3b3388ebabaeedb3ecb4f1ca0e3996a4e5070d20",
    ),
    "unknown034 continuation manifest": (
        "satellite_review_continuations/2026-07-21-global-open-v3-unknown-034-continued-25/continuation-manifest.json",
        7_574,
        "7ec2eff11515b7ffe18ea581e6c73fdf3751902d8bcb7e4fb94ffd380707c74a",
    ),
    "unknown034 cumulative batch manifest": (
        "satellite_review_runs/2026-07-21-global-open-v3-unknown-034/batch-manifest.json",
        6_487_582,
        "9cc51440c6d0f53a20f45fef61cf33345a47d0dd2f22265b188a692bd3eb6ebd",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v27": (
        "construction_maps/2026-07-21-public-open-v27/manifest.json",
        "generated_at",
        "2026-07-21T08:05:01Z",
    ),
    "construction master v27": (
        "construction_master/2026-07-21-public-open-v27/manifest.json",
        "generated_at",
        "2026-07-21T08:05:00Z",
    ),
    "construction timeline v3": (
        "construction_timelines/2026-07-21-public-open-v3/manifest.json",
        "generated_at",
        "2026-07-21T07:52:10Z",
    ),
    "coverage audit v27": (
        "audits/2026-07-21-public-open-coverage-v27/manifest.json",
        "generated_at",
        "2026-07-21T08:10:00Z",
    ),
    "exact identity v6": (
        "exact_identity_decisions/2026-07-21-public-open-v6/manifest.json",
        "recorded_at",
        "2026-07-21T07:57:00Z",
    ),
    "federation v28": (
        "federated_indexes/2026-07-21-public-open-v28/manifest.json",
        "generated_at",
        "2026-07-21T07:55:00Z",
    ),
    "unknown034 continuation": (
        "satellite_review_continuations/2026-07-21-global-open-v3-unknown-034-continued-25/continuation-manifest.json",
        "accepted_at",
        "2026-07-21T07:45:13Z",
    ),
}


class CurrentCoverageV21Error(_legacy.CurrentCoverageError):
    """Raised when the v21 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True)
class CurrentCoverageV21Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


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


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV21Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV21Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV21Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV21Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV21Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV21Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v20._v19._v14._tree_digest(path, label)
    except (ValueError, _v20._v19._v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV21Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV21Error(f"{label} closed tree changed")


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v20._checkpoint(checkpoint_id, path, byte_count, sha256, binding=binding)


def _metric(label: str, checkpoint_id: str, pointer: str, value: Any) -> dict[str, Any]:
    return _v20._metric(label, checkpoint_id, pointer, value)


def _replacement_checkpoints() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v27": [
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-21-public-open-v27/coverage.json",
                7_465,
                "02edcf096c49e8e164b03f6270b38603c4464d3070198d11e69165c4002e8438",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-21-public-open-v27.json",
                2_442,
                "a7d62e22778ce4c70e5fbe015e67b5cf2702f19862dc63d93896d669bf4638f4",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-21-public-open-v27/manifest.json",
                2_192,
                "7115033102529e7dcca992960948463ead7f7d74a717510fdddbcfa2e89c6c38",
            ),
        ],
        "construction-master-public-open-v27": [
            _checkpoint(
                "coverage",
                "construction_master/2026-07-21-public-open-v27/coverage.json",
                8_550,
                "8df2ba8c2211b0b55a363088b22ca14c5a6b508d6788dcae7e804a1ca6050635",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-21-public-open-v27.json",
                5_659,
                "c0f2a5c89e44838da876d7629dc39f49bdaa497d882a2826fff92e6e7080198b",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-21-public-open-v27/manifest.json",
                9_720,
                "6a5f48a0c86220c66d13fc1bd0ec7a9716e624d3d952599e3b6660e07717f5e7",
            ),
        ],
        "coverage-audit-public-open-v27": [
            _checkpoint(
                "manifest",
                "audits/2026-07-21-public-open-coverage-v27/manifest.json",
                3_379,
                "fc3c4af31d6f37f103d08ca4f1e9f78fa87a82e692c9abd19ddd9002176be64f",
            )
        ],
        "exact-identity-decisions-public-open-v6": [
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-21-public-open-v6/accounting.json",
                981,
                "8dc15c12f4b6d5d0cebc309a5ab46d2eeb10b835906a43dbdd8c80d95fb8d922",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-21-public-open-v6.json",
                1_735,
                "2b9b26f452ebfc3d36f4bb36d9cc7198a29b8be8806657750f440a928671d759",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-21-public-open-v6/manifest.json",
                11_438,
                "0af1e65f5b772b87e7dfe5b5c195513e79f31d4b5648fdcae5fd343f86f82ee9",
            ),
        ],
        "federation-public-open-v28": [
            _checkpoint(
                "index",
                "federated_indexes/2026-07-21-public-open-v28/federated-index.json",
                30_388,
                "d21cfa01157dc7529d71bfd99d4f6d2bbc74285a8c58392ee402dc767faf3210",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-21-public-open-v28/manifest.json",
                986,
                "d465a2de75b94168113b712740a1761e93887c1bc998a5164ba54489202e5f6e",
            ),
        ],
    }


def _replacement_limitations() -> dict[str, list[str]]:
    return {
        "construction-map-public-open-v27": [
            "Map rows are a presentation derivative of construction-master v27 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Three hundred twenty master observations lack coordinates, including 302 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        "construction-master-public-open-v27": [
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses are source-scoped last-observed facts and do not establish current construction after reported_status_date.",
            "Only 521 Tier-A source-supported observation rows enter construction arithmetic; the 109,313 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        "coverage-audit-public-open-v27": [
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 816 source and source-country groups and 3,959 open gaps are coverage-accounting units, not site counts.",
            "The satellite methodology-support artifact is non-countable review support and creates no facility, lifecycle, identity, status, or capacity claim.",
        ],
        "exact-identity-decisions-public-open-v6": [
            "Canonical topology links preserve explicit facility-contains-building and project-targets relationships and are non-additive; they are not unique physical-site counts.",
            "Exact same-kind source-record components collapse repeat occurrences only within their source-scoped keys and authorize neither cross-kind nor cross-source identity union.",
            "Review-only fuzzy references remain excluded from exact-component accounting; unresolved and ambiguous candidate references remain review work, while physical-site bounds and unique physical sites stay null.",
        ],
        "federation-public-open-v28": [
            "Historical lifecycle observations are last-observed facts and do not establish current construction without later evidence.",
            "The 16,208 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,651 construction-pipeline records include 6,130 review-only fuzzy rows and only 521 non-review observations; they are not all confirmed construction sites.",
        ],
    }


def _replacement_metrics() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v27": [
            _metric(
                "added_replacement_rows_unmapped",
                "coverage",
                "/projection/added_replacement_rows_unmapped",
                189,
            ),
            _metric(
                "default_visible_rows",
                "definition",
                "/expected_projection/default_visible_rows",
                6_499,
            ),
            _metric(
                "mapped_replacement_rows",
                "coverage",
                "/counts/mapped_replacement_rows",
                100,
            ),
            _metric(
                "mapped_rows_with_any_role",
                "coverage",
                "/counts/mapped_rows_with_any_role",
                75,
            ),
            _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 219),
            _metric(
                "mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280
            ),
            _metric(
                "mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494
            ),
            _metric(
                "mapped_total_rows",
                "coverage",
                "/counts/mapped_observation_rows",
                108_993,
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
                109_313,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/counts/unique_physical_site_count",
                None,
            ),
            _metric(
                "unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 320
            ),
        ],
        "construction-master-public-open-v27": [
            _metric(
                "added_replacement_rows",
                "coverage",
                "/replacement_invariants/added_replacement_rows",
                202,
            ),
            _metric(
                "base_rows", "coverage", "/replacement_invariants/base_rows", 109_111
            ),
            _metric(
                "contract_marked_rows",
                "coverage",
                "/replacement_invariants/rows_with_contract_marker",
                401,
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
                401,
            ),
            _metric(
                "role_rows_with_any_role",
                "coverage",
                "/role_counts/rows_with_any_role",
                142,
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
                58,
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
                103,
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
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 521),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
            _metric("total_master_rows", "coverage", "/row_counts/total", 109_313),
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
        "coverage-audit-public-open-v27": [
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 816),
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
                10_078,
            ),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 3_959),
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
                16_208,
            ),
            _metric(
                "unique_physical_sites",
                "manifest",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
        "exact-identity-decisions-public-open-v6": [
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
                2_377,
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
                8_346,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "accounting",
                "/non_review_source_scoped_entity_records",
                10_078,
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
            _metric("raw_topology_links", "accounting", "/raw_topology_links", 2_782),
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
                16_208,
            ),
            _metric(
                "unique_physical_sites", "accounting", "/unique_physical_sites", None
            ),
            _metric(
                "unresolved_candidate_references",
                "accounting",
                "/unresolved_candidate_references",
                100_538,
            ),
        ],
        "federation-public-open-v28": [
            _metric(
                "capacity_observations", "index", "/counts/capacity_estimates", 1_307
            ),
            _metric(
                "construction_pipeline_records",
                "index",
                "/counts/construction_pipeline_records",
                6_651,
            ),
            _metric(
                "non_review_construction_pipeline_records",
                "index",
                "/counts/non_review_construction_pipeline_records",
                521,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "index",
                "/counts/non_review_source_scoped_entity_records",
                10_078,
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
                16_208,
            ),
            _metric(
                "unique_physical_sites", "index", "/counts/unique_physical_sites", None
            ),
        ],
    }


def _replacement_entries(
    base_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    checkpoints = _replacement_checkpoints()
    limitations = _replacement_limitations()
    metrics = _replacement_metrics()
    if set(checkpoints) != REPLACEMENT_ARTIFACT_IDS or not (
        set(limitations) == set(metrics) == set(checkpoints)
    ):
        raise CurrentCoverageV21Error("v21 core replacement specification changed")
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in ARTIFACT_REPLACEMENTS.items():
        entry = deepcopy(dict(base_entries[old_id]))
        entry["artifact_id"] = new_id
        entry["checkpoints"] = checkpoints[new_id]
        entry["limitations"] = sorted(limitations[new_id])
        entry["metrics"] = metrics[new_id]
        result[new_id] = entry
    return result


def _satellite_entry() -> dict[str, Any]:
    return {
        "access_tier": "public_open",
        "artifact_id": SATELLITE_ARTIFACT_ID,
        "artifact_kind": "satellite_catalog_batch",
        "checkpoints": [
            _checkpoint(
                "batch_manifest",
                "satellite_review_runs/2026-07-21-global-open-v3-unknown-034/batch-manifest.json",
                6_487_582,
                "9cc51440c6d0f53a20f45fef61cf33345a47d0dd2f22265b188a692bd3eb6ebd",
                binding=("continuation_manifest", "/output/batch_manifest"),
            ),
            _checkpoint(
                "continuation_manifest",
                "satellite_review_continuations/2026-07-21-global-open-v3-unknown-034-continued-25/continuation-manifest.json",
                7_574,
                "7ec2eff11515b7ffe18ea581e6c73fdf3751902d8bcb7e4fb94ffd380707c74a",
            ),
        ],
        "current_role": "public_supporting_review_lane",
        "evidence_scope": "review_only",
        "limitations": sorted(
            [
                "Catalog-only completion establishes catalog availability, not visible change, identity, lifecycle, operating status, type, capacity, power, energy, or a data-centre claim.",
                "The accepted Unknown034 continuation and cumulative batch describe one successor state; they replace overlapping Unknown030 and Unknown033 accounting and must not be added to either predecessor or to each other.",
                "The cumulative batch remains incomplete with 2,036 pending catalog jobs; no imagery was downloaded, no change analysis ran, and no Atlas mutation or automated promotion occurred.",
            ]
        ),
        "metrics": [
            _metric(
                "atlas_mutation",
                "continuation_manifest",
                "/scope/atlas_mutation",
                False,
            ),
            _metric(
                "change_analysis_executed",
                "continuation_manifest",
                "/scope/change_analysis_executed",
                False,
            ),
            _metric(
                "cumulative_jobs_completed",
                "batch_manifest",
                "/summary/jobs_completed",
                4_397,
            ),
            _metric(
                "cumulative_jobs_failed", "batch_manifest", "/summary/jobs_failed", 0
            ),
            _metric(
                "cumulative_jobs_pending",
                "batch_manifest",
                "/summary/jobs_pending",
                2_036,
            ),
            _metric(
                "cumulative_jobs_selected",
                "batch_manifest",
                "/summary/jobs_selected",
                6_736,
            ),
            _metric(
                "cumulative_jobs_unavailable_no_scene",
                "batch_manifest",
                "/summary/jobs_unavailable_no_scene",
                303,
            ),
            _metric(
                "delta_jobs_completed",
                "continuation_manifest",
                "/output/delta/jobs_completed",
                22,
            ),
            _metric(
                "delta_jobs_failed",
                "continuation_manifest",
                "/output/delta/jobs_failed",
                0,
            ),
            _metric(
                "delta_jobs_unavailable_no_scene",
                "continuation_manifest",
                "/output/delta/jobs_unavailable_no_scene",
                3,
            ),
            _metric(
                "imagery_assets_downloaded",
                "continuation_manifest",
                "/scope/imagery_assets_downloaded",
                False,
            ),
            _metric("mode", "continuation_manifest", "/scope/mode", "catalog_only"),
        ],
        "publication_mode": "public_review_or_discovery",
        "record_units": ["catalog_job", "catalog_link"],
        "redistribution_status": "eligible_with_upstream_terms",
    }


def _timeline_entry() -> dict[str, Any]:
    return {
        "access_tier": "public_open",
        "artifact_id": TIMELINE_ARTIFACT_ID,
        "artifact_kind": "construction_timeline",
        "checkpoints": [
            _checkpoint(
                "coverage",
                "construction_timelines/2026-07-21-public-open-v3/coverage.json",
                72_215,
                "6fbe901557f1f872c668c76f4f668d1548b9f2fc9c25509bab0aad4ba01b01c8",
                binding=("manifest", "/files/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-timeline-2026-07-21-public-open-v3.json",
                2_838,
                "698648dda386a00e62247a4fdaf1aaf83ca2bc62f865ea366c5f51da2813d055",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_timelines/2026-07-21-public-open-v3/manifest.json",
                3_794,
                "4dc0c03968d2b3b07db225df3b3388ebabaeedb3ecb4f1ca0e3996a4e5070d20",
            ),
        ],
        "current_role": "authoritative_public_core",
        "evidence_scope": "source_scoped",
        "limitations": sorted(
            [
                "Dated raw observations and last-observed statuses do not establish current construction; all 443 timeline current-status classifications remain unknown and current_construction_claimed is false.",
                "No interpolation, forecast conversion, persistence assumption, quarterly parity, cross-source identity resolution, or satellite lifecycle promotion is applied.",
                "The STT Johor under-construction observation is a stale historical fact dated 2025-02-24, not a current construction classification.",
                "The 459 lifecycle observations across 443 source-scoped timelines and 197 source families are not cross-source-deduplicated unique physical sites.",
            ]
        ),
        "metrics": [
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
                443,
            ),
            _metric(
                "raw_lifecycle_observations",
                "coverage",
                "/counts/raw_lifecycle_observations",
                459,
            ),
            _metric("source_families", "coverage", "/counts/source_families", 197),
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
        "publication_mode": "public_row_release",
        "record_units": ["lifecycle_observation"],
        "redistribution_status": "eligible_with_upstream_terms",
    }


def _load_v20_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_path = package_root / V20_BASE_LINEAGE["definition"]["path"]
    bundle_path = package_root / _BASE_BUNDLE_TREE["path"]
    try:
        _v20.validate_current_coverage_ledger_v20(
            bundle_path, definition_path=definition_path
        )
    except _v20.CurrentCoverageV20Error as error:
        raise CurrentCoverageV21Error(
            f"accepted v20 base failed offline validation: {error}"
        ) from error
    definition_raw, definition = _pinned_json(
        package_root, V20_BASE_LINEAGE["definition"], "v21 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V20_BASE_LINEAGE["ledger"], "v21 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V20_BASE_LINEAGE["manifest"], "v21 base manifest"
    )
    if (
        definition.get("ledger_id") != V20_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V20_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V20_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V20_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V20_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V20_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV21Error("accepted v20 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v21 base bundle")
    return definition, ledger, manifest


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV21Error(f"{label} timestamp is invalid") from error


def _validate_excluded_discovery(package_root: Path) -> None:
    for artifact_id, spec in sorted(EXCLUDED_DISCOVERY_ARTIFACTS.items()):
        raw = _read_regular(
            package_root / str(spec["path"]), f"excluded discovery {artifact_id}"
        )
        if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
            raise CurrentCoverageV21Error(f"excluded discovery changed: {artifact_id}")
        document = _json_object(raw, f"excluded discovery {artifact_id}")
        if document.get("artifact_id") != artifact_id:
            raise CurrentCoverageV21Error(
                f"excluded discovery identity changed: {artifact_id}"
            )


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v21 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV21Error(f"v21 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v21 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v21 {label}")
    _validate_excluded_discovery(package_root)
    try:
        _master_v11.validate_construction_master_v11(
            package_root / _ACCEPTED_TREES["construction-master-v27"]["path"],
            definition_path=(
                package_root
                / "sources/construction-master-2026-07-21-public-open-v27.json"
            ),
            reproduce=False,
        )
        _map_v11.validate_construction_map_v11(
            package_root / _ACCEPTED_TREES["construction-map-v27"]["path"],
            master_directory=(
                package_root / _ACCEPTED_TREES["construction-master-v27"]["path"]
            ),
            master_definition_path=(
                package_root
                / "sources/construction-master-2026-07-21-public-open-v27.json"
            ),
            map_definition_path=(
                package_root
                / "sources/construction-map-2026-07-21-public-open-v27.json"
            ),
            reproduce=False,
        )
        _coverage_v3.validate_coverage_audit(
            package_root / _ACCEPTED_TREES["coverage-audit-v27"]["path"],
            definition_path=(
                package_root / "sources/coverage-audit-2026-07-21-public-open-v27.json"
            ),
        )
        _federation_v3.validate_federated_release_index(
            package_root / _ACCEPTED_TREES["federation-v28"]["path"]
        )
        _identity_v3.validate_exact_identity_decision_bundle(
            package_root / _ACCEPTED_TREES["exact-identity-decisions-v6"]["path"],
            definition_path=(
                package_root
                / "sources/exact-identity-decisions-2026-07-21-public-open-v6.json"
            ),
            verify_inputs=False,
            require_frozen=True,
        )
        _timeline_v3.validate_construction_timeline_bundle(
            package_root / _ACCEPTED_TREES["construction-timeline-v3"]["path"],
            definition_path=(
                package_root
                / "sources/construction-timeline-2026-07-21-public-open-v3.json"
            ),
            verify_inputs=True,
            require_frozen=True,
        )
    except Exception as error:
        raise CurrentCoverageV21Error(
            f"accepted v21 successor input failed offline validation: {error}"
        ) from error

    continuation = _json_object(
        _read_regular(
            package_root / _PINNED_FILES["unknown034 continuation manifest"][0],
            "v21 Unknown034 continuation manifest",
        ),
        "v21 Unknown034 continuation manifest",
    )
    batch = _json_object(
        _read_regular(
            package_root / _PINNED_FILES["unknown034 cumulative batch manifest"][0],
            "v21 Unknown034 cumulative batch manifest",
        ),
        "v21 Unknown034 cumulative batch manifest",
    )
    if (
        continuation.get("output", {}).get("batch_manifest")
        != {
            "bytes": _PINNED_FILES["unknown034 cumulative batch manifest"][1],
            "path": _PINNED_FILES["unknown034 cumulative batch manifest"][0],
            "sha256": _PINNED_FILES["unknown034 cumulative batch manifest"][2],
        }
        or continuation.get("output", {}).get("summary") != batch.get("summary")
        or continuation.get("scope", {}).get("mode") != "catalog_only"
        or continuation.get("scope", {}).get("imagery_assets_downloaded") is not False
        or continuation.get("scope", {}).get("change_analysis_executed") is not False
        or continuation.get("scope", {}).get("atlas_mutation") is not False
    ):
        raise CurrentCoverageV21Error("Unknown034 continuation binding changed")

    generated_at = _parse_timestamp(V21_GENERATED_AT, "v21")
    for label, (relative, field, expected) in sorted(_SOURCE_TIMESTAMPS.items()):
        document = _json_object(
            _read_regular(package_root / relative, f"v21 {label} timestamp source"),
            f"v21 {label} timestamp source",
        )
        if document.get(field) != expected:
            raise CurrentCoverageV21Error(f"v21 {label} timestamp changed")
        if _parse_timestamp(expected, f"v21 {label}") > generated_at:
            raise CurrentCoverageV21Error(f"v21 predates {label}")
    audit_manifest = _json_object(
        _read_regular(
            package_root / "audits/2026-07-21-public-open-coverage-v27/manifest.json",
            "v21 coverage audit manifest",
        ),
        "v21 coverage audit manifest",
    )
    timeline_manifest = _json_object(
        _read_regular(
            package_root
            / "construction_timelines/2026-07-21-public-open-v3/manifest.json",
            "v21 timeline manifest",
        ),
        "v21 timeline manifest",
    )
    if audit_manifest.get("as_of") != "2026-07-21":
        raise CurrentCoverageV21Error("v21 local audit as-of date changed")
    if timeline_manifest.get("as_of") != "2026-07-21":
        raise CurrentCoverageV21Error("v21 timeline as-of date changed")


_TIMELINE_GAP_IDS = frozenset(
    {
        "benchmark-parity-not-computed",
        "global-construction-coverage-partial",
        "site-resolution-partial",
        "type-power-energy-coverage-partial",
    }
)

_UPDATED_GAP_SUMMARIES = {
    "benchmark-parity-not-computed": (
        "No licensed, row-level external benchmark denominator is pinned; the 43 selected calibration labels and 443 source-scoped last-observed timelines provide neither recall nor SemiAnalysis-equivalent precision, feature, field, current-status, or quarterly parity."
    ),
    "global-construction-coverage-partial": (
        "The expanded official open seed, planning and permit review lanes, structural shortlist, footprint context, 443 last-observed timelines, and satellite review still do not establish a complete global construction census; the accepted Unknown034 catalog-only continuation is non-additive and promotes no source batch or site claim."
    ),
    "satellite-review-backlog": (
        "Unknown034 is the sole accepted cumulative unknown-priority catalog checkpoint: 4,397 completed, 303 no-scene, 2,036 pending, and zero failed. Its 22-completed and 3-no-scene continuation delta is non-additive; no imagery was downloaded, no change analysis ran, and candidate-level manual verification remains open."
    ),
    "site-resolution-partial": (
        "Resolution links remain advisory; England, Ireland, NSW, Netherlands, New Zealand, and France observations, 443 source-scoped lifecycle timelines, and selected imagery labels are not cross-source deduplicated, no merges are accepted, and unique physical sites remain null."
    ),
    "type-power-energy-coverage-partial": (
        "Type, operating model, typed capacity, power, annual energy, PUE, workload, and current status remain sparse and source-scoped; planned critical-IT values are not current load, generation and grid metrics stay distinct, last-observed timelines add no energy inference, NSW retains 10 untyped statements, and review lanes promote no ungrounded facility metrics."
    ),
}


def _v21_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV21Error("v20 parity gaps are invalid")
    mapping = {**ARTIFACT_REPLACEMENTS, **SATELLITE_REPLACEMENTS}
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV21Error("v20 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        affected = {
            mapping.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        }
        if gap["gap_id"] in _TIMELINE_GAP_IDS:
            affected.add(TIMELINE_ARTIFACT_ID)
        gap["affected_artifact_ids"] = sorted(affected)
        if gap["gap_id"] in _UPDATED_GAP_SUMMARIES:
            gap["summary"] = _UPDATED_GAP_SUMMARIES[gap["gap_id"]]
        result.append(gap)
    return result


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _require_digest(actual: str, expected: str, label: str) -> None:
    if expected and actual != expected:
        raise CurrentCoverageV21Error(f"v21 {label} digest changed")


def make_v21_definition(package_root: str | Path) -> bytes:
    """Create canonical v21 definition bytes from the pinned v20 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v20_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if len(base_entries) != 47 or not REMOVED_ARTIFACT_IDS <= set(base_entries):
        raise CurrentCoverageV21Error("v20 replacement source inventory changed")
    if set(base_entries) & NEW_ARTIFACT_IDS:
        raise CurrentCoverageV21Error("v20 unexpectedly contains a v21 artifact ID")
    removed = [
        base_entries[artifact_id] for artifact_id in sorted(REMOVED_ARTIFACT_IDS)
    ]
    replacements = _replacement_entries(base_entries)
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    base_entries[SATELLITE_ARTIFACT_ID] = _satellite_entry()
    base_entries[TIMELINE_ARTIFACT_ID] = _timeline_entry()
    if len(base_entries) != 47:
        raise CurrentCoverageV21Error("v21 definition must contain 47 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] not in NEW_ARTIFACT_IDS
    ]
    replacement_entries = [
        entry for entry in ordered if entry["artifact_id"] in REPLACEMENT_ARTIFACT_IDS
    ]
    added_entries = [
        entry for entry in ordered if entry["artifact_id"] in ADDED_ARTIFACT_IDS
    ]
    if len(unchanged) != 40 or len(replacement_entries) != 5 or len(added_entries) != 2:
        raise CurrentCoverageV21Error("v21 delta arithmetic changed")
    parity_gaps = _v21_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_40_SHA256, "inherited entries"
    )
    _require_digest(
        _component_digest(replacement_entries),
        REPLACEMENT_5_SHA256,
        "core replacement entries",
    )
    _require_digest(_component_digest(added_entries), ADDED_2_SHA256, "added entries")
    _require_digest(_component_digest(removed), REMOVED_7_SHA256, "removed entries")
    _require_digest(_component_digest(ordered), ALL_ENTRIES_SHA256, "all entries")
    _require_digest(
        _sha256(_canonical_line(parity_gaps)), PARITY_GAPS_SHA256, "parity gaps"
    )
    document = {
        "base_ledger": V20_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V21_GENERATED_AT,
        "ledger_id": V21_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": DEFINITION_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    rendered = raw.decode("utf-8")
    forbidden = (
        set(REMOVED_ARTIFACT_IDS)
        | set(EXCLUDED_DISCOVERY_ARTIFACTS)
        | set(EXCLUDED_CONCURRENT_ARTIFACT_MARKERS)
    )
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV21Error(
            "v21 definition contains superseded or excluded lineage"
        )
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V21_DEFINITION_PATH:
        raise CurrentCoverageV21Error("v21 definition publication path changed")
    raw = _read_regular(path, "v21 definition")
    document = _json_object(raw, "v21 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV21Error("v21 definition is not canonical JSON")
    if not V21_DEFINITION_SHA256 or _sha256(raw) != V21_DEFINITION_SHA256:
        raise CurrentCoverageV21Error("v21 definition content changed or is unpinned")
    if raw != make_v21_definition(package_root):
        raise CurrentCoverageV21Error(
            "v21 definition differs from pinned transformation"
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
        raise CurrentCoverageV21Error("v21 definition keys differ")
    if (
        document.get("ledger_id") != V21_LEDGER_ID
        or document.get("generated_at") != V21_GENERATED_AT
        or document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V20_BASE_LINEAGE
    ):
        raise CurrentCoverageV21Error("v21 identity, base, schema, or scope changed")
    if _parse_timestamp(V21_GENERATED_AT, "v21") > datetime.now(UTC):
        raise CurrentCoverageV21Error("v21 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 47:
        raise CurrentCoverageV21Error("v21 must contain exactly 47 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 47 or None in artifact_ids:
        raise CurrentCoverageV21Error("v21 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not NEW_ARTIFACT_IDS <= artifact_ids:
        raise CurrentCoverageV21Error("v21 delta inventory is invalid")
    return document, raw, package_root


def _entry_v4(
    package_root: Path,
    spec: Any,
    previous_id: str | None,
) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise CurrentCoverageV21Error("entry must be an object")
    artifact_kind = spec.get("artifact_kind")
    record_units = spec.get("record_units")
    if artifact_kind not in ARTIFACT_KINDS_V4:
        raise CurrentCoverageV21Error(
            f"{spec.get('artifact_id')} artifact_kind is invalid"
        )
    if (
        not isinstance(record_units, list)
        or not record_units
        or record_units != sorted(set(record_units))
        or any(unit not in RECORD_UNITS_V4 for unit in record_units)
    ):
        raise CurrentCoverageV21Error(
            f"{spec.get('artifact_id')} record_units must be sorted unique known units"
        )
    legacy_spec = deepcopy(dict(spec))
    if legacy_spec["artifact_kind"] == "construction_timeline":
        legacy_spec["artifact_kind"] = "source_scoped_release"
    legacy_spec["record_units"] = [
        "source_scoped_entity_row" if unit == "lifecycle_observation" else unit
        for unit in legacy_spec["record_units"]
    ]
    legacy_spec["record_units"] = sorted(set(legacy_spec["record_units"]))
    try:
        result = _legacy._entry(
            package_root,
            legacy_spec,
            previous_id,
            _legacy.DEFINITION_SCHEMA_VERSION_V3,
        )
    except _legacy.CurrentCoverageError as error:
        raise CurrentCoverageV21Error(str(error)) from error
    result["artifact_kind"] = artifact_kind
    result["record_units"] = list(record_units)
    return result


def _inventory_counts(
    artifacts: Sequence[Mapping[str, Any]], parity_gaps: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "artifacts": len(artifacts),
        "by_access_tier": {
            tier: sum(artifact["access_tier"] == tier for artifact in artifacts)
            for tier in sorted(_legacy.ACCESS_TIERS)
        },
        "by_evidence_scope": {
            scope: sum(artifact["evidence_scope"] == scope for artifact in artifacts)
            for scope in sorted(_legacy.EVIDENCE_SCOPES)
        },
        "by_publication_mode": {
            mode: sum(artifact["publication_mode"] == mode for artifact in artifacts)
            for mode in sorted(_legacy.PUBLICATION_MODES)
        },
        "by_record_unit": {
            unit: sum(unit in artifact["record_units"] for artifact in artifacts)
            for unit in sorted(RECORD_UNITS_V4)
        },
        "by_redistribution_status": {
            status: sum(
                artifact["redistribution_status"] == status for artifact in artifacts
            )
            for status in sorted(_legacy.REDISTRIBUTION_STATUSES)
        },
        "parity_gaps_by_status": {
            status: sum(gap["status"] == status for gap in parity_gaps)
            for status in sorted(_legacy.PARITY_GAP_STATUSES)
        },
        "public_open_review_only_artifacts": sum(
            artifact["access_tier"] == "public_open" and artifact["review_only"]
            for artifact in artifacts
        ),
    }


def build_current_coverage_ledger_v21(
    definition_path: str | Path,
) -> CurrentCoverageV21Bundle:
    """Reproduce the schema-v4 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, _base_ledger, _base_manifest = _load_v20_base(package_root)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    for spec in definition["entries"]:
        artifact = _entry_v4(package_root, spec, previous_id)
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _legacy.CurrentCoverageError as error:
        raise CurrentCoverageV21Error(str(error)) from error
    inventory_counts = _inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(_base_ledger["artifact_inventory_counts"])
    expected_inventory["by_evidence_scope"]["review_only"] -= 1
    expected_inventory["by_evidence_scope"]["source_scoped"] += 1
    expected_inventory["by_publication_mode"]["public_review_or_discovery"] -= 1
    expected_inventory["by_publication_mode"]["public_row_release"] += 1
    expected_inventory["by_record_unit"]["catalog_job"] -= 1
    expected_inventory["by_record_unit"]["lifecycle_observation"] = 1
    expected_inventory["public_open_review_only_artifacts"] -= 1
    if inventory_counts != expected_inventory:
        raise CurrentCoverageV21Error("v21 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V20_BASE_LINEAGE,
        "format": LEDGER_FORMAT_V4,
        "generated_at": V21_GENERATED_AT,
        "ledger_id": V21_LEDGER_ID,
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
        "base_ledger": V20_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V21_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT_V4,
        "generated_at": V21_GENERATED_AT,
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
        "ledger_id": V21_LEDGER_ID,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    return CurrentCoverageV21Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _lexical_absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


@contextmanager
def _exclusive_output_lock(destination: Path) -> Iterator[None]:
    try:
        with _v20._exclusive_output_lock(destination):
            yield
    except _v20.CurrentCoverageV20Error as error:
        raise CurrentCoverageV21Error(str(error).replace("v20", "v21")) from error


def _cleanup_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v20._cleanup_file_stage(stage, identity)
    except _v20.CurrentCoverageV20Error as error:
        raise CurrentCoverageV21Error(str(error).replace("v20", "v21")) from error


def _cleanup_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v20._cleanup_bundle_stage(stage, identity)
    except _v20.CurrentCoverageV20Error as error:
        raise CurrentCoverageV21Error(str(error).replace("v20", "v21")) from error


def _promote_noreplace(stage: Path, destination: Path) -> None:
    try:
        _v20._promote_noreplace(stage, destination)
    except _v20.CurrentCoverageV20Error as error:
        raise CurrentCoverageV21Error(str(error).replace("v20", "v21")) from error


def write_v21_definition(package_root: str | Path, output_path: str | Path) -> str:
    """Atomically create, but never replace, the canonical v21 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v21_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV21Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _v20._v19._v18._v17._v16._path_identity(stage)
            stage.chmod(0o644)
            _v20._v19._v18._v17._v16._fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _v20._v19._v18._v17._v16._fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV21Error(
                    "v21 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v21 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v21(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v21 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV21Error("v21 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v21(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV21Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _v20._v19._v18._v17._v16._path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _v20._v19._v18._v17._v16._fsync_regular(stage / filename)
            stage.chmod(0o555)
            _v20._v19._v18._v17._v16._fsync_directory(stage)
            validate_current_coverage_ledger_v21(stage, definition_path=definition_path)
            _promote_noreplace(stage, destination)
            _v20._v19._v18._v17._v16._fsync_directory(destination.parent)
            validate_current_coverage_ledger_v21(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v21 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v21(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = _lexical_absolute(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV21Error("v21 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV21Error("v21 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV21Error("v21 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v21 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v21 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v21 sidecar")
    ledger = _json_object(actual_ledger, "v21 ledger")
    manifest = _json_object(actual_manifest, "v21 manifest")
    if actual_ledger != _canonical_json(ledger):
        raise CurrentCoverageV21Error("v21 ledger is not canonical JSON")
    if actual_manifest != _canonical_json(manifest):
        raise CurrentCoverageV21Error("v21 manifest is not canonical JSON")
    if actual_sidecar != (
        f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CurrentCoverageV21Error("v21 manifest sidecar differs")
    expected = build_current_coverage_ledger_v21(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV21Error("v21 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV21Error("v21 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV21Error("v21 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_2_SHA256",
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_KINDS_V4",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT_V4",
    "CurrentCoverageV21Bundle",
    "CurrentCoverageV21Error",
    "DEFINITION_SCHEMA_VERSION_V4",
    "EXCLUDED_CONCURRENT_ARTIFACT_MARKERS",
    "EXCLUDED_DISCOVERY_ARTIFACTS",
    "LEDGER_FORMAT_V4",
    "LEDGER_SCHEMA_VERSION_V4",
    "NEW_ARTIFACT_IDS",
    "PARITY_GAPS_SHA256",
    "RECORD_UNITS_V4",
    "REMOVED_7_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_5_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "SATELLITE_ARTIFACT_ID",
    "SATELLITE_REPLACEMENTS",
    "TIMELINE_ARTIFACT_ID",
    "UNCHANGED_40_SHA256",
    "V20_BASE_LINEAGE",
    "V21_BUNDLE_PATH",
    "V21_DEFINITION_PATH",
    "V21_DEFINITION_SHA256",
    "V21_GENERATED_AT",
    "V21_LEDGER_ID",
    "build_current_coverage_ledger_v21",
    "make_v21_definition",
    "validate_current_coverage_ledger_v21",
    "write_current_coverage_ledger_v21",
    "write_v21_definition",
]
