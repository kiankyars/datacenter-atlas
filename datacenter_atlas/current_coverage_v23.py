"""Fail-closed current-coverage ledger v23 successor.

V23 replaces exactly seven accepted public-core contracts from v22, adds the
accepted seed-v71 satellite queue, its bounded explicit catalog batch, and the
identity-blind analyst review of the eleven selected change jobs, and preserves
the other forty contracts byte-for-byte. Source-assessment wrappers remain
non-additive seed provenance. Raw machine-change runs and technical incidents
remain lineage rather than standalone schema-v4 coverage contracts.
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

from . import current_coverage_v22 as _v22


V23_LEDGER_ID = "current-coverage-2026-07-21-v23"
V23_GENERATED_AT = "2026-07-21T14:35:00Z"
V23_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v23.json"
V23_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v23"
V23_DEFINITION_SHA256: str | None = (
    "eca133b3f22e2ae58a3e90e42644cc1dad9d3849e2014a858529c270ccdf5687"
)
REPLACEMENT_7_SHA256: str | None = (
    "b8d432d15ea68eb42bb96dcfd74f775f8d4b8bbc0f898c2883d61c2665982636"
)
ADDED_3_SHA256: str | None = (
    "ff85fe539125d339c76761fc3e7d40b9cc03158668563ba4799bef833b151d6f"
)
ALL_ENTRIES_SHA256: str | None = (
    "d5aee68f2a2c773390b9084b779c4d4a4f365b07263adfff0aa4fe4757258696"
)

DEFINITION_SCHEMA_VERSION_V4 = _v22.DEFINITION_SCHEMA_VERSION_V4
LEDGER_SCHEMA_VERSION_V4 = _v22.LEDGER_SCHEMA_VERSION_V4
LEDGER_FORMAT_V4 = _v22.LEDGER_FORMAT_V4
BUNDLE_FORMAT_V4 = _v22.BUNDLE_FORMAT_V4
ARTIFACT_KINDS_V4 = _v22.ARTIFACT_KINDS_V4
RECORD_UNITS_V4 = _v22.RECORD_UNITS_V4
SCOPE_POLICY = _v22.SCOPE_POLICY
BUNDLE_FILES = _v22.BUNDLE_FILES
LEDGER_FILENAME = _v22.LEDGER_FILENAME
MANIFEST_FILENAME = _v22.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _v22.MANIFEST_HASH_FILENAME

V22_BASE_LINEAGE = {
    "definition": {
        "bytes": 147_739,
        "path": "sources/current-coverage-2026-07-21-v22.json",
        "sha256": "ee84ae4fd321ff4eb31e9d48359b18b8cb6d960d7ed4bf80a5d822e2386bd483",
    },
    "ledger": {
        "bytes": 100_662,
        "path": (
            "current_coverage_ledgers/2026-07-21-v22/"
            "current-coverage-ledger.json"
        ),
        "sha256": "f1cc7cab2be08611aed666507a38f5e8f5bffe6908ced9effaab2efa1ad38978",
    },
    "ledger_id": "current-coverage-2026-07-21-v22",
    "manifest": {
        "bytes": 27_663,
        "path": "current_coverage_ledgers/2026-07-21-v22/manifest.json",
        "sha256": "9ee42f8990e488be9bcbf3e47341824cdf9913fbf951c280710ae6990fd8e63f",
    },
}
V22_SIDECAR = {
    "bytes": 80,
    "path": "current_coverage_ledgers/2026-07-21-v22/manifest.sha256",
    "sha256": "1d22dcce5217f7a4a334b5580fc7b8ccf38373d75980a21ebe89e7e090a9f176",
}
V22_BUNDLE_TREE_SHA256 = (
    "56652ef22510a9ec96cb3913db5c69d7a4e47898a2bd161ca5e2a85297554803"
)

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v28": "construction-map-public-open-v29",
    "construction-master-public-open-v28": "construction-master-public-open-v29",
    "construction-timeline-public-open-v5": "construction-timeline-public-open-v6",
    "coverage-audit-public-open-v28": "coverage-audit-public-open-v29",
    "exact-identity-decisions-public-open-v8": (
        "exact-identity-decisions-public-open-v9"
    ),
    "federation-public-open-v31": "federation-public-open-v33",
    "seed-epoch-official-v71": "seed-epoch-official-v73",
}
ADDED_ARTIFACT_IDS = frozenset(
    {
        "satellite-catalog-open-seed-v71-active-explicit-final-v1",
        "satellite-change-review-open-seed-v71-active-explicit-11-review-v1",
        "satellite-queue-open-seed-v71",
    }
)
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS
UNCHANGED_40_SHA256 = (
    "6178822f9c84a39cabef04a370b852b70db3bc25906202f4734ed0dbe14a19d1"
)
REMOVED_7_SHA256 = (
    "5e0ea4d1b2ecda8d0727e505b76ea2f5a63a750956ea9ccc05f6b1f52881882d"
)
PARITY_GAPS_SHA256 = (
    "4924e50bc8bff0be416d3b0d04a3b906a0024e3e3b642678826ca6c2f08b3f69"
)

PENDING_DOWNSTREAM_REPLACEMENTS: dict[str, Mapping[str, Any] | None] = {}
PENDING_DOWNSTREAM_PIN_BLUEPRINT: dict[str, Mapping[str, Any]] = {}

# These accepted artifacts are provenance or incident inventory, not standalone
# schema-v4 coverage contracts. Their facts are either subsumed by v73 or have
# no honest artifact-kind/record-unit representation in the controlled
# vocabulary. Keeping the decision explicit prevents accidental additive reuse.
NON_LEDGER_ARTIFACT_DECISIONS: Mapping[str, Mapping[str, Any]] = {
    "site-coordinate-assessment-2026-07-21-v4": {
        "manifest": {
            "bytes": 1_792,
            "path": (
                "source_artifacts/site-coordinate-assessment-2026-07-21-v4/"
                "manifest.json"
            ),
            "sha256": (
                "8bcd9842af00890e4820e2b011a9fa799a1c4d5c98b0a77c4dc874c79b4c04b8"
            ),
        },
        "reason": "subsumed_nonadditive_seed_provenance",
    },
    "global-official-builds-six-candidate-2026-07-21-v1": {
        "manifest": {
            "bytes": 1_727,
            "path": (
                "source_artifacts/"
                "global-official-builds-six-candidate-2026-07-21-v1/"
                "manifest.json"
            ),
            "sha256": (
                "20b0788dba18402cf1b6bb8874ec6cd66f86000ff85f620c7e0167bf7e1894cd"
            ),
        },
        "reason": "subsumed_nonadditive_seed_provenance",
    },
    "federation-v32-partial-publication-incident-2026-07-21-v1": {
        "manifest": {
            "bytes": 1_122,
            "path": (
                "source_artifacts/"
                "federation-v32-partial-publication-incident-2026-07-21-v1/"
                "manifest.json"
            ),
            "sha256": (
                "4ef894097a41683a6d446e2c93e0a58127ceb1f4b7bf7b18e6cfce8eb9f51891"
            ),
        },
        "reason": "technical_incident_has_no_schema_v4_contract_kind",
    },
    "satellite-change-explicit-v1-disposition": {
        "manifest": {
            "bytes": 610,
            "path": (
                "satellite_change_run_dispositions/"
                "2026-07-21-open-seed-v71-active-explicit-001-v1/"
                "manifest.json"
            ),
            "sha256": (
                "81117523744d802d50ad08d65d4192c1673b0508b421a44b3e969b6e268a00cc"
            ),
        },
        "reason": "unreviewed_machine_change_has_no_schema_v4_contract_kind",
    },
}

_ACCEPTED_FILES = {
    "construction map v29 coverage": (
        "construction_maps/2026-07-21-public-open-v29/coverage.json",
        7_465,
        "7af745a8c3ec6d2cfd76047dd544febb79cef207c5b75d2be540644dde917398",
        0o444,
    ),
    "construction map v29 definition": (
        "sources/construction-map-2026-07-21-public-open-v29.json",
        2_442,
        "9668c1ee0eadfb755745407a2b140e414044a9c97dfeecaf95b131afbf8446bc",
        0o444,
    ),
    "construction map v29 index": (
        "construction_maps/2026-07-21-public-open-v29/construction-map-index.json.gz",
        6_681_116,
        "059c2b7a7f2cef562bc9548492ff363036f680829df0de8bf382a2e5368d11fc",
        0o444,
    ),
    "construction map v29 manifest": (
        "construction_maps/2026-07-21-public-open-v29/manifest.json",
        2_192,
        "5cfaeba6d854df6aabb4b4c500701d1a3d1d9f7c1e4d1481a986a2602374b889",
        0o444,
    ),
    "construction master v29 coverage": (
        "construction_master/2026-07-21-public-open-v29/coverage.json",
        8_550,
        "0f39569a5f0b17e1e90d2430704eb83f2653e2294c47c0cacacd9ef7b0f2d54d",
        0o444,
    ),
    "construction master v29 definition": (
        "sources/construction-master-2026-07-21-public-open-v29.json",
        5_659,
        "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d",
        0o444,
    ),
    "construction master v29 manifest": (
        "construction_master/2026-07-21-public-open-v29/manifest.json",
        9_720,
        "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c",
        0o444,
    ),
    "coverage v29 definition": (
        "sources/coverage-audit-2026-07-21-public-open-v29.json",
        5_920,
        "ed2ad9f176dedef97f1cf0d91e4894570adf226b89fa460f9edbc9233ed67078",
        0o444,
    ),
    "coverage v29 manifest": (
        "audits/2026-07-21-public-open-coverage-v29/manifest.json",
        3_379,
        "41df0bf668cba5e8ec8a2e484361e41614cdc2b58395bf204bcd8fac12714b68",
        0o444,
    ),
    "federation v33 definition": (
        "sources/federation-2026-07-21-public-open-v33.json",
        1_788,
        "6472c052092860af73da784b233261c6e8de6a7e9d853d215fa459d5347b4e89",
        0o444,
    ),
    "federation v33 index": (
        "federated_indexes/2026-07-21-public-open-v33/federated-index.json",
        31_626,
        "0d865517b715edf69ccfb8df19ba0ea63b50c8d51167e9c64ff12daf60c5df1a",
        0o444,
    ),
    "federation v33 manifest": (
        "federated_indexes/2026-07-21-public-open-v33/manifest.json",
        986,
        "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b",
        0o444,
    ),
    "identity v9 accounting": (
        "exact_identity_decisions/2026-07-21-public-open-v9/accounting.json",
        981,
        "715b37d6d60d5625b65c89a66219822cfb4af014d24177782440512921f753d5",
        0o444,
    ),
    "identity v9 definition": (
        "sources/exact-identity-decisions-2026-07-21-public-open-v9.json",
        1_735,
        "20b9a890b195029d64b29fb7d917956cca09e2062f5d91cc01f981e034aabcc1",
        0o444,
    ),
    "identity v9 manifest": (
        "exact_identity_decisions/2026-07-21-public-open-v9/manifest.json",
        11_439,
        "47b18c1eeb58eef7d1fa9d70489340e8d2651e428b9d945bc136ecc54c679e6c",
        0o444,
    ),
    "seed v73 definition": (
        "sources/open-seed-2026-07-21-v73.json",
        88_004,
        "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
        0o444,
    ),
    "seed v73 manifest": (
        "releases/2026-07-21-open-seed-v73/manifest.json",
        12_814,
        "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
        0o444,
    ),
    "timeline v6 coverage": (
        "construction_timelines/2026-07-21-public-open-v6/coverage.json",
        23_468,
        "edcde1a60597894f3b36de5055fa4e761d6f31bc0d1f5bca4a0be1ec3bde2104",
        0o444,
    ),
    "timeline v6 definition": (
        "sources/construction-timeline-2026-07-21-public-open-v6.json",
        3_001,
        "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa",
        0o444,
    ),
    "timeline v6 manifest": (
        "construction_timelines/2026-07-21-public-open-v6/manifest.json",
        3_957,
        "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543",
        0o444,
    ),
    "satellite queue v71 manifest": (
        "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
        17_073,
        "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
        0o444,
    ),
    "satellite queue v71 rows": (
        "satellite_review_queues/2026-07-21-open-seed-v71/satellite-review-queue.jsonl",
        522_456,
        "462a3d4b8f482fecb0ccd325d9aac393f69e02fe86ad9dbfcb3b5aa74c700000",
        0o444,
    ),
    "satellite catalog v71 finalized manifest": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "batch-manifest.json",
        64_864,
        "c930e7a0431540ead5fe54d8cc60808bc0e1e8a57ddea99acb01eacb94d25da9",
        0o444,
    ),
    "satellite catalog v71 finalized receipt": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "selection-receipt.json",
        9_921,
        "cab75bcfb893002baa65a04bd3e2b1a104a510cf820076f7fcddecb5a2c665d2",
        0o444,
    ),
    "satellite change review v71 analyst rows": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "analyst-reviews.jsonl",
        24_913,
        "951321125a123cb3be788dfb4d5b44bfddd309318bd740b45671d06c62ab2059",
        0o444,
    ),
    "satellite change review v71 blind decisions": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "blind-decisions.json",
        6_890,
        "6e6bc074400b13d47c23953c2224ab50e12b4b6f2b48a1377237275b3edde0eb",
        0o444,
    ),
    "satellite change review v71 definition": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "definition.json",
        4_158,
        "b2e6acbd705f4d0229222bfa0e6d17532e3866225315280c578933e00bbd3ff2",
        0o444,
    ),
    "satellite change review v71 manifest": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "manifest.json",
        4_203,
        "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12",
        0o444,
    ),
    "satellite change review v71 summary": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "summary.json",
        3_352,
        "ccdc4ae77e550073469c8b1672d961e7be8a7e26ca4c1d782926effd3e6afeef",
        0o444,
    ),
}

_ACCEPTED_TREES = {
    "construction map v29": (
        "construction_maps/2026-07-21-public-open-v29",
        "b551f672a6ce6e82815a0633cc5c7cbd45ce358b9d8f1db1bd8257c4c36fe4b8",
    ),
    "construction master v29": (
        "construction_master/2026-07-21-public-open-v29",
        "09a76700020e35b1daa95e00cbd6c6bdf90aede9d9f794f5a4c70a607541eff8",
    ),
    "coverage v29": (
        "audits/2026-07-21-public-open-coverage-v29",
        "c497902893f477001ec270c611febed97ef6c73ec9ffb35c8ec3080b1cef9ec7",
    ),
    "federation v33": (
        "federated_indexes/2026-07-21-public-open-v33",
        "0fa59ad26d24d6266df33613102828a42e231eb2f231872bc0a9146c9aa0c760",
    ),
    "identity v9": (
        "exact_identity_decisions/2026-07-21-public-open-v9",
        "a23703e6cf0469c2b81a0252d42c96cac95d64f1c772375c5529d3fb3b4e5a7a",
    ),
    "seed v73": (
        "releases/2026-07-21-open-seed-v73",
        "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394",
    ),
    "timeline v6": (
        "construction_timelines/2026-07-21-public-open-v6",
        "6f754dcaa6f9d0df7ded14a90da70b2eb7c14d75634ec7bd1c503d47ed060e8f",
    ),
    "satellite queue v71": (
        "satellite_review_queues/2026-07-21-open-seed-v71",
        "4927ecb00b2e3d47c992ac3747f2e82505fb8e7d56a9d181245c8a3666db1a2d",
    ),
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1",
        "f2abbd23a18ac4ded2e4afa9acbdfa30240fc3b0015d89a01cdb4805ce308a6a",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1",
        "2f671c8dee331e10f2b297145d6c7eb9efdf300f56592d32048ab075d7f9f2ad",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v29": (
        "construction_maps/2026-07-21-public-open-v29/manifest.json",
        "generated_at",
        "2026-07-21T13:47:30Z",
    ),
    "construction master v29": (
        "construction_master/2026-07-21-public-open-v29/manifest.json",
        "generated_at",
        "2026-07-21T13:43:00Z",
    ),
    "coverage v29": (
        "audits/2026-07-21-public-open-coverage-v29/manifest.json",
        "generated_at",
        "2026-07-21T13:52:30Z",
    ),
    "federation v33": (
        "federated_indexes/2026-07-21-public-open-v33/manifest.json",
        "generated_at",
        "2026-07-21T13:29:00Z",
    ),
    "identity v9": (
        "exact_identity_decisions/2026-07-21-public-open-v9/manifest.json",
        "recorded_at",
        "2026-07-21T13:34:50Z",
    ),
    "seed v73": (
        "releases/2026-07-21-open-seed-v73/manifest.json",
        "recorded_at",
        "2026-07-21T13:15:51Z",
    ),
    "timeline v6": (
        "construction_timelines/2026-07-21-public-open-v6/manifest.json",
        "generated_at",
        "2026-07-21T13:28:20Z",
    ),
    "satellite queue v71": (
        "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
        "generated_at",
        "2026-07-21T13:06:30Z",
    ),
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "batch-manifest.json",
        "updated_at",
        "2026-07-21T13:42:28Z",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "manifest.json",
        "generated_at",
        "2026-07-21T14:24:30.000000Z",
    ),
}

_ACCEPTED_ROOT_NOT_BEFORE = {
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1",
        "2026-07-21T14:05:15Z",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1",
        "2026-07-21T14:24:30Z",
    ),
}


class CurrentCoverageV23Error(_v22.CurrentCoverageV22Error):
    """Raised when the v23 preparation or publication contract fails closed."""


class PendingDownstreamPinsError(CurrentCoverageV23Error):
    """Raised while a downstream replacement or publication fuse is unresolved."""


@dataclass(frozen=True)
class CurrentCoverageV23Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedV23Publication:
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
        raise CurrentCoverageV23Error(f"{label} must be canonical UTC seconds")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV23Error(f"{label} is invalid") from error
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise CurrentCoverageV23Error(f"{label} must be canonical UTC seconds")
    return parsed.astimezone(UTC)


def _parse_pinned_source_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CurrentCoverageV23Error(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as error:
        raise CurrentCoverageV23Error(f"{label} is invalid") from error
    canonical_seconds = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    canonical_microseconds = parsed.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    if value not in {canonical_seconds, canonical_microseconds}:
        raise CurrentCoverageV23Error(f"{label} must be canonical UTC")
    return parsed


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV23Error(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV23Error(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise CurrentCoverageV23Error(f"{label} is not canonical JSON")
    return raw, document


def _inside(package_root: Path, relative: str, label: str) -> Path:
    candidate = package_root / relative
    resolved = candidate.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV23Error(f"{label} escapes package root") from error
    return candidate


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise CurrentCoverageV23Error(f"accepted tree is not a regular directory: {root}")
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CurrentCoverageV23Error(f"accepted tree contains symlink: {path}")
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
            raise CurrentCoverageV23Error(f"accepted tree entry is unsupported: {path}")
    return digest.hexdigest()


def _load_v22_base(package_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for label, spec in (
        ("definition", V22_BASE_LINEAGE["definition"]),
        ("ledger", V22_BASE_LINEAGE["ledger"]),
        ("manifest", V22_BASE_LINEAGE["manifest"]),
    ):
        path = _inside(package_root, str(spec["path"]), f"v22 {label}")
        raw, document = _read_json(path, f"v22 {label}")
        if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
            raise CurrentCoverageV23Error(f"accepted v22 {label} pin changed")
        documents[label] = document
    sidecar = _inside(
        package_root, str(V22_SIDECAR["path"]), "accepted v22 sidecar"
    )
    if sidecar.is_symlink() or not sidecar.is_file():
        raise CurrentCoverageV23Error("accepted v22 sidecar is not regular")
    sidecar_raw = sidecar.read_bytes()
    if (
        len(sidecar_raw) != V22_SIDECAR["bytes"]
        or _sha256(sidecar_raw) != V22_SIDECAR["sha256"]
    ):
        raise CurrentCoverageV23Error("accepted v22 sidecar pin changed")
    bundle = package_root / "current_coverage_ledgers/2026-07-21-v22"
    if _tree_digest(bundle) != V22_BUNDLE_TREE_SHA256:
        raise CurrentCoverageV23Error("accepted v22 bundle tree changed")
    if documents["definition"].get("ledger_id") != V22_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV23Error("accepted v22 definition identity changed")
    if documents["ledger"].get("ledger_id") != V22_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV23Error("accepted v22 ledger identity changed")
    return documents["definition"], documents["ledger"]


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v22._checkpoint(
        checkpoint_id, path, byte_count, sha256, binding=binding
    )


def _metric(
    label: str, checkpoint_id: str, pointer: str, value: Any
) -> dict[str, Any]:
    return _v22._metric(label, checkpoint_id, pointer, value)


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
        "construction-map-public-open-v28",
        "construction-map-public-open-v29",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-21-public-open-v29/coverage.json",
                7_465,
                "7af745a8c3ec6d2cfd76047dd544febb79cef207c5b75d2be540644dde917398",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-21-public-open-v29.json",
                2_442,
                "9668c1ee0eadfb755745407a2b140e414044a9c97dfeecaf95b131afbf8446bc",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-21-public-open-v29/manifest.json",
                2_192,
                "5cfaeba6d854df6aabb4b4c500701d1a3d1d9f7c1e4d1481a986a2602374b889",
            ),
        ],
        limitations=[
            "Map rows are a presentation derivative of construction-master v29 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Three hundred thirty-four master observations lack coordinates, including 316 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows_unmapped",
                "coverage",
                "/projection/added_replacement_rows_unmapped",
                205,
            ),
            _metric(
                "default_visible_rows",
                "definition",
                "/expected_projection/default_visible_rows",
                6_504,
            ),
            _metric(
                "mapped_replacement_rows",
                "coverage",
                "/counts/mapped_replacement_rows",
                105,
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
                224,
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
                108_998,
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
                109_332,
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
                334,
            ),
        ],
    )
    master = _replacement(
        base_entries,
        "construction-master-public-open-v28",
        "construction-master-public-open-v29",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_master/2026-07-21-public-open-v29/coverage.json",
                8_550,
                "0f39569a5f0b17e1e90d2430704eb83f2653e2294c47c0cacacd9ef7b0f2d54d",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-21-public-open-v29.json",
                5_659,
                "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-21-public-open-v29/manifest.json",
                9_720,
                "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c",
            ),
        ],
        limitations=[
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses, including 412 source-normalized under_construction rows, are source-scoped last-observed facts and do not establish current construction after reported_status_date.",
            "Only 540 Tier-A source-supported observation rows enter construction arithmetic; the 109,332 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows",
                "coverage",
                "/replacement_invariants/added_replacement_rows",
                221,
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
                420,
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
                420,
            ),
            _metric(
                "role_rows_with_any_role",
                "coverage",
                "/role_counts/rows_with_any_role",
                149,
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
                62,
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
                110,
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
                412,
            ),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 540),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric(
                "tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494
            ),
            _metric(
                "total_master_rows", "coverage", "/row_counts/total", 109_332
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
        "coverage-audit-public-open-v28",
        "coverage-audit-public-open-v29",
        checkpoints=[
            _checkpoint(
                "manifest",
                "audits/2026-07-21-public-open-coverage-v29/manifest.json",
                3_379,
                "41df0bf668cba5e8ec8a2e484361e41614cdc2b58395bf204bcd8fac12714b68",
            )
        ],
        limitations=[
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 847 source and source-country groups and 4,103 open gaps are coverage-accounting units, not site counts.",
            "The satellite methodology-support artifact is non-countable review support and creates no facility, lifecycle, identity, status, or capacity claim.",
        ],
        metrics=[
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 847),
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
                10_113,
            ),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 4_103),
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
                16_243,
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
        "federation-public-open-v31",
        "federation-public-open-v33",
        checkpoints=[
            _checkpoint(
                "index",
                "federated_indexes/2026-07-21-public-open-v33/federated-index.json",
                31_626,
                "0d865517b715edf69ccfb8df19ba0ea63b50c8d51167e9c64ff12daf60c5df1a",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-21-public-open-v33/manifest.json",
                986,
                "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b",
            ),
        ],
        limitations=[
            "Historical lifecycle observations are last-observed facts and do not establish current construction without later evidence.",
            "The 16,243 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,670 construction-pipeline records include 6,130 review-only fuzzy rows and only 540 non-review observations; they are not all confirmed construction sites.",
        ],
        metrics=[
            _metric(
                "capacity_observations",
                "index",
                "/counts/capacity_estimates",
                1_320,
            ),
            _metric(
                "construction_pipeline_records",
                "index",
                "/counts/construction_pipeline_records",
                6_670,
            ),
            _metric(
                "non_review_construction_pipeline_records",
                "index",
                "/counts/non_review_construction_pipeline_records",
                540,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "index",
                "/counts/non_review_source_scoped_entity_records",
                10_113,
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
                16_243,
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
        "exact-identity-decisions-public-open-v8",
        "exact-identity-decisions-public-open-v9",
        checkpoints=[
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-21-public-open-v9/accounting.json",
                981,
                "715b37d6d60d5625b65c89a66219822cfb4af014d24177782440512921f753d5",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-21-public-open-v9.json",
                1_735,
                "20b9a890b195029d64b29fb7d917956cca09e2062f5d91cc01f981e034aabcc1",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-21-public-open-v9/manifest.json",
                11_439,
                "47b18c1eeb58eef7d1fa9d70489340e8d2651e428b9d945bc136ecc54c679e6c",
            ),
        ],
        limitations=deepcopy(
            base_entries["exact-identity-decisions-public-open-v8"]["limitations"]
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
                2_396,
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
                8_381,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "accounting",
                "/non_review_source_scoped_entity_records",
                10_113,
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
                "raw_topology_links", "accounting", "/raw_topology_links", 2_801
            ),
            _metric(
                "release_candidate_references",
                "accounting",
                "/release_candidate_references",
                100_412,
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
                16_243,
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
                100_539,
            ),
        ],
    )
    seed = _replacement(
        base_entries,
        "seed-epoch-official-v71",
        "seed-epoch-official-v73",
        checkpoints=[
            _checkpoint(
                "manifest",
                "releases/2026-07-21-open-seed-v73/manifest.json",
                12_814,
                "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
            )
        ],
        limitations=[
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; last-observed status is not current status and absent fields are not inferred from satellite imagery.",
            "The 462 freshness rows are non-additive with timeline v6 and classify current status as unknown rather than asserting current construction.",
            "The 818 source-scoped entity rows comprise 431 campus observations and 387 project observations, not deduplicated physical sites.",
        ],
        metrics=[
            _metric("campus_rows", "manifest", "/entities_by_kind/campus", 431),
            _metric(
                "capacity_observations", "manifest", "/capacity_estimates", 534
            ),
            _metric(
                "construction_pipeline_records",
                "manifest",
                "/construction_pipeline_records",
                420,
            ),
            _metric(
                "construction_source_signals",
                "manifest",
                "/construction_source_signals",
                322,
            ),
            _metric(
                "current_status_inferred",
                "manifest",
                "/current_status_inferred",
                False,
            ),
            _metric("evidence_records", "manifest", "/evidence_records", 520),
            _metric(
                "lifecycle_freshness_records",
                "manifest",
                "/lifecycle_freshness_records",
                462,
            ),
            _metric(
                "lifecycle_status_semantics",
                "manifest",
                "/lifecycle_status_semantics",
                "last_observed",
            ),
            _metric("project_rows", "manifest", "/entities_by_kind/project", 387),
            _metric(
                "publication_contract_version",
                "manifest",
                "/publication_contract_version",
                4,
            ),
            _metric(
                "resolution_candidates", "manifest", "/resolution_candidates", 7
            ),
            _metric(
                "source_scoped_entity_rows", "manifest", "/entities", 818
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
        "construction-timeline-public-open-v5",
        "construction-timeline-public-open-v6",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_timelines/2026-07-21-public-open-v6/coverage.json",
                23_468,
                "edcde1a60597894f3b36de5055fa4e761d6f31bc0d1f5bca4a0be1ec3bde2104",
                binding=("manifest", "/files/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-timeline-2026-07-21-public-open-v6.json",
                3_001,
                "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_timelines/2026-07-21-public-open-v6/manifest.json",
                3_957,
                "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543",
            ),
        ],
        limitations=[
            "Dated raw observations and last-observed statuses do not establish current construction; all 462 timeline current-status classifications remain unknown and current_construction_claimed is false.",
            "No interpolation, forecast conversion, persistence assumption, quarterly parity, cross-source identity resolution, or satellite lifecycle promotion is applied.",
            "The 479 lifecycle observations across 462 source-scoped timelines and 207 source families are not cross-source-deduplicated unique physical sites.",
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
                462,
            ),
            _metric(
                "raw_lifecycle_observations",
                "coverage",
                "/counts/raw_lifecycle_observations",
                479,
            ),
            _metric(
                "source_families", "coverage", "/counts/source_families", 207
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


def _review_entry(
    *,
    artifact_id: str,
    artifact_kind: str,
    checkpoints: list[dict[str, Any]],
    limitations: list[str],
    metrics: list[dict[str, Any]],
    record_units: list[str],
) -> dict[str, Any]:
    return {
        "access_tier": "public_open",
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "checkpoints": checkpoints,
        "current_role": "public_supporting_review_lane",
        "evidence_scope": "review_only",
        "limitations": sorted(limitations),
        "metrics": metrics,
        "publication_mode": "public_review_or_discovery",
        "record_units": sorted(record_units),
        "redistribution_status": "eligible_with_upstream_terms",
    }


def _accepted_addition_entries() -> dict[str, dict[str, Any]]:
    catalog = _review_entry(
        artifact_id="satellite-catalog-open-seed-v71-active-explicit-final-v1",
        artifact_kind="satellite_catalog_batch",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v71-active-explicit-final-v1/"
                "batch-manifest.json",
                64_864,
                "c930e7a0431540ead5fe54d8cc60808bc0e1e8a57ddea99acb01eacb94d25da9",
            ),
            _checkpoint(
                "queue_manifest",
                "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
                17_073,
                "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
            ),
            _checkpoint(
                "selection_receipt",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v71-active-explicit-final-v1/"
                "selection-receipt.json",
                9_921,
                "cab75bcfb893002baa65a04bd3e2b1a104a510cf820076f7fcddecb5a2c665d2",
                binding=("manifest", "/selection_receipt"),
            ),
        ],
        limitations=[
            "Catalog availability and selected scene IDs are review controls, not visible-change, identity, lifecycle, operating-status, type, capacity, power, energy, PUE, workload, or unique-site evidence.",
            "The batch represents 98 active-priority queue jobs but executes only the 11 immutable receipt IDs; the other 87 remain pending and all counts are non-additive with the v71 queue.",
            "The finalized tree is a frozen byte-identical copy of the mutable execution checkpoint; no change analysis or Atlas mutation was performed by this catalog-only contract.",
        ],
        metrics=[
            _metric(
                "atlas_mutation",
                "manifest",
                "/scope/atlas_mutation",
                False,
            ),
            _metric(
                "change_analysis_executed",
                "manifest",
                "/scope/change_analysis_executed",
                False,
            ),
            _metric(
                "jobs_completed", "manifest", "/summary/jobs_completed", 11
            ),
            _metric(
                "jobs_failed", "manifest", "/summary/jobs_failed", 0
            ),
            _metric(
                "jobs_not_selected",
                "manifest",
                "/summary/jobs_not_selected",
                87,
            ),
            _metric(
                "jobs_pending", "manifest", "/summary/jobs_pending", 87
            ),
            _metric(
                "jobs_represented",
                "manifest",
                "/summary/jobs_represented",
                98,
            ),
            _metric(
                "jobs_selected_for_execution",
                "manifest",
                "/summary/jobs_selected_for_execution",
                11,
            ),
            _metric(
                "review_required", "manifest", "/scope/review_required", True
            ),
            _metric(
                "selected_jobs_unavailable_no_scene",
                "manifest",
                "/summary/selected_jobs_unavailable_no_scene",
                0,
            ),
            _metric(
                "unexpected_output_adoption",
                "manifest",
                "/scope/unexpected_output_adoption",
                False,
            ),
        ],
        record_units=["catalog_job", "catalog_link"],
    )
    queue = _review_entry(
        artifact_id="satellite-queue-open-seed-v71",
        artifact_kind="satellite_review_queue",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
                17_073,
                "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
            ),
            _checkpoint(
                "release_manifest",
                "releases/2026-07-21-open-seed-v71/manifest.json",
                12_577,
                "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
                binding=("manifest", "/source/release_manifest"),
            ),
        ],
        limitations=[
            "Queue jobs are review plans for source-scoped seed-v71 observations, not deduplicated sites, imagery findings, or current construction evidence.",
            "The active-construction priority tier is derived from last-observed source status and does not establish that any of its 98 queued observations remains under construction now.",
            "The queue is non-additive with seed v73 and the explicit catalog selection; 621 coordinate-null seed-v71 observations remain outside imagery execution.",
        ],
        metrics=[
            _metric(
                "active_construction_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/active_construction",
                98,
            ),
            _metric(
                "entities_queued", "manifest", "/counts/entities_queued", 189
            ),
            _metric(
                "network_requests_performed",
                "manifest",
                "/scope/network_requests_performed",
                False,
            ),
            _metric(
                "operational_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/operational",
                29,
            ),
            _metric(
                "proposed_pipeline_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/proposed_pipeline",
                5,
            ),
            _metric("queue_jobs", "manifest", "/counts/queue_jobs", 189),
            _metric(
                "skipped_missing_coordinates",
                "manifest",
                "/counts/skipped_missing_coordinates",
                621,
            ),
            _metric(
                "unknown_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/unknown",
                57,
            ),
        ],
        record_units=["catalog_job"],
    )
    analyst_review = _review_entry(
        artifact_id=(
            "satellite-change-review-open-seed-v71-active-explicit-11-review-v1"
        ),
        artifact_kind="analyst_imagery_review",
        checkpoints=[
            _checkpoint(
                "blind_decisions",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "blind-decisions.json",
                6_890,
                "6e6bc074400b13d47c23953c2224ab50e12b4b6f2b48a1377237275b3edde0eb",
                binding=("manifest", "/artifacts/blind-decisions.json"),
            ),
            _checkpoint(
                "definition",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "definition.json",
                4_158,
                "b2e6acbd705f4d0229222bfa0e6d17532e3866225315280c578933e00bbd3ff2",
                binding=("manifest", "/artifacts/definition.json"),
            ),
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "manifest.json",
                4_203,
                "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12",
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "summary.json",
                3_352,
                "ccdc4ae77e550073469c8b1672d961e7be8a7e26ca4c1d782926effd3e6afeef",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        limitations=[
            "The eleven identity-blind decisions retain seven image pairs for manual visible-change follow-up and reject four for site promotion; neither disposition establishes or negates construction, lifecycle, operating status, or any separately sourced fact.",
            "The four ambiguous decisions, one temporal-metadata correction, and two reciprocal visual-identity links remain review controls and do not create a unique-site count or cross-source identity resolution.",
            "The 44 inspected visuals and 66 hash-bound source artifacts are non-additive review records; imagery and change-mask metadata create no atlas mutation, automated promotion, data-centre type, capacity, power, energy, PUE, operator, or workload claim.",
        ],
        metrics=[
            _metric(
                "analyst_decisions", "manifest", "/summary/analyst_decisions", 11
            ),
            _metric("atlas_mutation", "manifest", "/guardrails/atlas_mutation", False),
            _metric(
                "automated_promotion_allowed",
                "manifest",
                "/guardrails/automated_promotion_allowed",
                False,
            ),
            _metric(
                "capacity_claim_created",
                "manifest",
                "/guardrails/capacity_claim_created",
                False,
            ),
            _metric(
                "construction_status_claim_created",
                "manifest",
                "/guardrails/construction_status_claim_created",
                False,
            ),
            _metric(
                "current_status_claim_created",
                "manifest",
                "/guardrails/current_status_claim_created",
                False,
            ),
            _metric(
                "data_centre_identity_claim_created",
                "manifest",
                "/guardrails/data_centre_identity_claim_created",
                False,
            ),
            _metric(
                "data_centre_type_claim_created",
                "manifest",
                "/guardrails/data_centre_type_claim_created",
                False,
            ),
            _metric(
                "energy_claim_created",
                "manifest",
                "/guardrails/energy_claim_created",
                False,
            ),
            _metric(
                "image_quality_partially_obscured",
                "manifest",
                "/summary/image_quality/partially_obscured",
                4,
            ),
            _metric(
                "image_quality_usable",
                "manifest",
                "/summary/image_quality/usable",
                7,
            ),
            _metric(
                "imagery_construction_truth_claim_created",
                "manifest",
                "/guardrails/imagery_construction_truth_claim_created",
                False,
            ),
            _metric(
                "it_capacity_claim_created",
                "manifest",
                "/guardrails/it_capacity_claim_created",
                False,
            ),
            _metric(
                "lifecycle_status_claim_created",
                "manifest",
                "/guardrails/lifecycle_status_claim_created",
                False,
            ),
            _metric(
                "operator_claim_created",
                "manifest",
                "/guardrails/operator_claim_created",
                False,
            ),
            _metric(
                "power_claim_created",
                "manifest",
                "/guardrails/power_claim_created",
                False,
            ),
            _metric(
                "promotion_rejected",
                "manifest",
                "/summary/promotion_dispositions/rejected_for_site_promotion",
                4,
            ),
            _metric(
                "promotion_retained_for_manual_followup",
                "manifest",
                "/summary/promotion_dispositions/retained_for_manual_followup",
                7,
            ),
            _metric(
                "pue_claim_created",
                "manifest",
                "/guardrails/pue_claim_created",
                False,
            ),
            _metric(
                "site_count_claim_created",
                "manifest",
                "/guardrails/site_count_claim_created",
                False,
            ),
            _metric(
                "source_artifacts_hash_bound",
                "manifest",
                "/summary/source_artifacts_hash_bound",
                66,
            ),
            _metric(
                "temporal_metadata_corrections",
                "manifest",
                "/summary/temporal_metadata_corrections",
                1,
            ),
            _metric(
                "unique_site_claim_created",
                "manifest",
                "/guardrails/unique_site_claim_created",
                False,
            ),
            _metric(
                "visible_change_ambiguous",
                "manifest",
                "/summary/visible_change/ambiguous",
                4,
            ),
            _metric(
                "visible_change_clear",
                "manifest",
                "/summary/visible_change/clear",
                7,
            ),
            _metric(
                "visual_artifacts_inspected",
                "manifest",
                "/summary/visual_artifacts_inspected",
                44,
            ),
            _metric(
                "visual_identity_links",
                "manifest",
                "/summary/visual_identity_links",
                2,
            ),
            _metric(
                "workload_claim_created",
                "manifest",
                "/guardrails/workload_claim_created",
                False,
            ),
        ],
        record_units=["aggregate_report_metric", "review_record"],
    )
    return {
        analyst_review["artifact_id"]: analyst_review,
        catalog["artifact_id"]: catalog,
        queue["artifact_id"]: queue,
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
            "v23 downstream pins remain unresolved: " + ", ".join(pending)
        )


def _validate_accepted_inputs(package_root: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(package_root).resolve()
    base_definition, _base_ledger = _load_v22_base(root)
    for label, (relative, byte_count, digest, mode) in _ACCEPTED_FILES.items():
        path = _inside(root, relative, f"accepted {label}")
        if path.is_symlink() or not path.is_file():
            raise CurrentCoverageV23Error(f"accepted {label} is not a regular file")
        raw = path.read_bytes()
        if (
            len(raw) != byte_count
            or _sha256(raw) != digest
            or stat.S_IMODE(path.stat().st_mode) != mode
        ):
            raise CurrentCoverageV23Error(f"accepted {label} pin or mode changed")
    for artifact_id, decision in NON_LEDGER_ARTIFACT_DECISIONS.items():
        checkpoint = decision["manifest"]
        path = _inside(
            root,
            str(checkpoint["path"]),
            f"non-ledger {artifact_id} manifest",
        )
        if path.is_symlink() or not path.is_file():
            raise CurrentCoverageV23Error(
                f"non-ledger {artifact_id} manifest is not regular"
            )
        raw = path.read_bytes()
        if (
            len(raw) != checkpoint["bytes"]
            or _sha256(raw) != checkpoint["sha256"]
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CurrentCoverageV23Error(
                f"non-ledger {artifact_id} manifest pin changed"
            )
    for label, (relative, digest) in _ACCEPTED_TREES.items():
        path = _inside(root, relative, f"accepted {label} tree")
        if _tree_digest(path) != digest:
            raise CurrentCoverageV23Error(f"accepted {label} tree changed")
        if stat.S_IMODE(path.stat().st_mode) != 0o555:
            raise CurrentCoverageV23Error(f"accepted {label} tree is not frozen")
    now = datetime.now(UTC)
    for label, (relative, field, expected) in _SOURCE_TIMESTAMPS.items():
        path = _inside(root, relative, f"accepted {label} timestamp")
        _, document = _read_json(path, f"accepted {label} timestamp")
        if document.get(field) != expected:
            raise CurrentCoverageV23Error(f"accepted {label} timestamp changed")
        if _parse_pinned_source_timestamp(expected, label) > now:
            raise CurrentCoverageV23Error(f"accepted {label} timestamp is future")
    for label, (relative, expected) in _ACCEPTED_ROOT_NOT_BEFORE.items():
        path = _inside(root, relative, f"accepted {label} root")
        target = _parse_timestamp(expected, f"accepted {label} publication")
        if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
            raise CurrentCoverageV23Error(
                f"accepted {label} root predates its publication time"
            )
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    accepted = _accepted_replacement_entries(base_entries)
    accepted.update(_accepted_addition_entries())
    if set(accepted) != NEW_ARTIFACT_IDS:
        raise CurrentCoverageV23Error("v23 accepted artifact inventory changed")
    previous_id: str | None = None
    for artifact_id in sorted(accepted):
        try:
            artifact = _v22._v21._entry_v4(
                root, accepted[artifact_id], previous_id
            )
        except _v22._v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV23Error(str(error)) from error
        previous_id = artifact["artifact_id"]
    return accepted


_UPDATED_GAP_SUMMARIES = {
    "benchmark-parity-not-computed": (
        "No licensed, row-level external benchmark denominator is pinned; the 43 selected calibration labels, 11 identity-blind follow-up dispositions, and 462 source-scoped last-observed timelines provide neither recall nor SemiAnalysis-equivalent precision, feature, field, current-status, or quarterly parity."
    ),
    "global-construction-coverage-partial": (
        "The expanded official open seed, planning and permit review lanes, structural shortlist, footprint context, 462 last-observed timelines, and satellite review still do not establish a complete global construction census; queue, catalog, and analyst-review controls are non-additive and promote no site or lifecycle claim."
    ),
    "satellite-review-backlog": (
        "Unknown034 remains the accepted cumulative unknown-priority catalog checkpoint with 4,397 completed, 303 no-scene, 2,036 pending, and zero failed. Separately, the v71 queue has 189 jobs; its explicit catalog represents 98 active-priority jobs, executes 11, and leaves 87 pending, while the 11 analyst dispositions promote no site or status claim. All counts are non-additive and manual verification remains open."
    ),
    "site-resolution-partial": (
        "Resolution links remain advisory; England, Ireland, NSW, Netherlands, New Zealand, and France observations, 462 source-scoped lifecycle timelines, and selected imagery labels are not cross-source deduplicated, no merges are accepted, and unique physical sites remain null."
    ),
}


def preview_parity_gaps(package_root: str | Path) -> list[dict[str, Any]]:
    base_definition, _ = _load_v22_base(Path(package_root).resolve())
    result: list[dict[str, Any]] = []
    for raw_gap in base_definition["parity_gaps"]:
        gap = deepcopy(raw_gap)
        gap["affected_artifact_ids"] = sorted(
            {
                ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in gap["affected_artifact_ids"]
            }
        )
        if gap["gap_id"] in {
            "global-construction-coverage-partial",
            "satellite-review-backlog",
        }:
            gap["affected_artifact_ids"] = sorted(
                {*gap["affected_artifact_ids"], *ADDED_ARTIFACT_IDS}
            )
        if gap["gap_id"] in _UPDATED_GAP_SUMMARIES:
            gap["summary"] = _UPDATED_GAP_SUMMARIES[gap["gap_id"]]
        result.append(gap)
    return result


def preview_v23_delta(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root).resolve()
    base_definition, _ = _load_v22_base(root)
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
    replacements = [
        accepted[artifact_id]
        for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
    ]
    additions = [
        accepted[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)
    ]
    if (
        len(unchanged) != 40
        or len(removed) != 7
        or len(replacements) != 7
        or len(additions) != 3
    ):
        raise CurrentCoverageV23Error("v23 prep delta arithmetic changed")
    if _component_digest(unchanged) != UNCHANGED_40_SHA256:
        raise CurrentCoverageV23Error("v23 unchanged-entry digest changed")
    if _component_digest(removed) != REMOVED_7_SHA256:
        raise CurrentCoverageV23Error("v23 removed-entry digest changed")
    if (
        REPLACEMENT_7_SHA256 is None
        or _component_digest(replacements) != REPLACEMENT_7_SHA256
    ):
        raise CurrentCoverageV23Error("v23 replacement-entry digest changed")
    if ADDED_3_SHA256 is None or _component_digest(additions) != ADDED_3_SHA256:
        raise CurrentCoverageV23Error("v23 added-entry digest changed")
    combined = {entry["artifact_id"]: entry for entry in unchanged}
    combined.update(accepted)
    ordered = [combined[artifact_id] for artifact_id in sorted(combined)]
    if ALL_ENTRIES_SHA256 is None or _component_digest(ordered) != ALL_ENTRIES_SHA256:
        raise CurrentCoverageV23Error("v23 all-entry digest changed")
    if _sha256(_canonical_line(preview_parity_gaps(root))) != PARITY_GAPS_SHA256:
        raise CurrentCoverageV23Error("v23 parity-gap digest changed")
    return {
        "accepted_added_ids": sorted(ADDED_ARTIFACT_IDS),
        "accepted_replacement_ids": sorted(REPLACEMENT_ARTIFACT_IDS),
        "base_entries": len(base_entries),
        "final_entries": 50,
        "pending_replacement_ids": list(pending_downstream_pins()),
        "parity_gaps_sha256": PARITY_GAPS_SHA256,
        "removed_7_sha256": REMOVED_7_SHA256,
        "replacement_7_sha256": REPLACEMENT_7_SHA256,
        "added_3_sha256": ADDED_3_SHA256,
        "unchanged_40_sha256": UNCHANGED_40_SHA256,
    }


def make_v23_definition(package_root: str | Path, *, generated_at: str) -> bytes:
    """Render v23 only after all seven replacements and final digests are sealed."""

    root = Path(package_root).resolve()
    base_definition, _ = _load_v22_base(root)
    accepted = _validate_accepted_inputs(root)
    _require_downstream_pins()
    if (
        REPLACEMENT_7_SHA256 is None
        or ADDED_3_SHA256 is None
        or ALL_ENTRIES_SHA256 is None
    ):
        raise PendingDownstreamPinsError("v23 replacement digest fuses are unresolved")
    generated = _parse_timestamp(generated_at, "v23 generated_at")
    if generated_at != V23_GENERATED_AT:
        raise CurrentCoverageV23Error("v23 generated_at changed")
    for label, (_relative, _field, expected) in _SOURCE_TIMESTAMPS.items():
        if _parse_pinned_source_timestamp(expected, label) > generated:
            raise CurrentCoverageV23Error(
                f"accepted {label} post-dates v23 generated_at"
            )
    new_entries = dict(accepted)
    new_entries.update(
        {
            artifact_id: deepcopy(dict(spec))
            for artifact_id, spec in PENDING_DOWNSTREAM_REPLACEMENTS.items()
            if spec is not None
        }
    )
    if set(new_entries) != NEW_ARTIFACT_IDS:
        raise CurrentCoverageV23Error("v23 new artifact inventory changed")
    base_entries = {
        entry["artifact_id"]: deepcopy(entry)
        for entry in base_definition["entries"]
    }
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(new_entries)
    ordered = [base_entries[artifact_id] for artifact_id in sorted(base_entries)]
    replacement_rows = [
        base_entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
    ]
    added_rows = [
        base_entries[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)
    ]
    if (
        len(ordered) != 50
        or _component_digest(replacement_rows) != REPLACEMENT_7_SHA256
        or _component_digest(added_rows) != ADDED_3_SHA256
        or _component_digest(ordered) != ALL_ENTRIES_SHA256
    ):
        raise CurrentCoverageV23Error("v23 sealed entry digest changed")
    document = {
        "base_ledger": V22_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": generated_at,
        "ledger_id": V23_LEDGER_ID,
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
        "federation-public-open-v32",
        "federated-index-2026-07-21-public-open-v32",
    }
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV23Error("v23 contains superseded or rejected lineage")
    return raw


def _validate_v23_definition(
    definition_path: str | Path,
    *,
    require_live: bool,
) -> tuple[dict[str, Any], bytes, Path, datetime]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path.parent != package_root / "sources":
        raise CurrentCoverageV23Error("v23 definition stage must be inside sources")
    raw, document = _read_json(path, "v23 definition")
    if stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise CurrentCoverageV23Error("v23 definition must be frozen 0444")
    if V23_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v23 definition digest fuse is unresolved")
    if _sha256(raw) != V23_DEFINITION_SHA256:
        raise CurrentCoverageV23Error("v23 definition content changed")
    generated_at = document.get("generated_at")
    if raw != make_v23_definition(package_root, generated_at=generated_at):
        raise CurrentCoverageV23Error(
            "v23 definition differs from its pinned transformation"
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
        raise CurrentCoverageV23Error("v23 definition keys differ")
    if (
        document.get("base_ledger") != V22_BASE_LINEAGE
        or document.get("ledger_id") != V23_LEDGER_ID
        or document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4
        or document.get("scope") != SCOPE_POLICY
    ):
        raise CurrentCoverageV23Error("v23 identity, base, schema, or scope changed")
    generated = _parse_timestamp(generated_at, "v23 generated_at")
    if require_live and generated > datetime.now(UTC):
        raise CurrentCoverageV23Error("v23 generated_at is not yet live")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 50:
        raise CurrentCoverageV23Error("v23 must contain exactly 50 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if (
        len(artifact_ids) != 50
        or None in artifact_ids
        or artifact_ids & REMOVED_ARTIFACT_IDS
        or not NEW_ARTIFACT_IDS <= artifact_ids
    ):
        raise CurrentCoverageV23Error("v23 entry inventory is invalid")
    return document, raw, package_root, generated


def build_current_coverage_ledger_v23(
    definition_path: str | Path,
) -> CurrentCoverageV23Bundle:
    """Reproduce all three v23 bundle files without publishing any path."""

    definition, definition_raw, package_root, _generated = _validate_v23_definition(
        definition_path, require_live=False
    )
    _base_definition, base_ledger = _load_v22_base(package_root)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    for spec in definition["entries"]:
        try:
            artifact = _v22._v21._entry_v4(package_root, spec, previous_id)
        except _v22._v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV23Error(str(error)) from error
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _v22._v21._legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _v22._v21._legacy.CurrentCoverageError as error:
        raise CurrentCoverageV23Error(str(error)) from error
    inventory_counts = _v22._v21._inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(base_ledger["artifact_inventory_counts"])
    expected_inventory["artifacts"] += 3
    expected_inventory["by_access_tier"]["public_open"] += 3
    expected_inventory["by_evidence_scope"]["review_only"] += 3
    expected_inventory["by_publication_mode"]["public_review_or_discovery"] += 3
    expected_inventory["by_record_unit"]["aggregate_report_metric"] += 1
    expected_inventory["by_record_unit"]["catalog_job"] += 2
    expected_inventory["by_record_unit"]["catalog_link"] += 1
    expected_inventory["by_record_unit"]["review_record"] += 1
    expected_inventory["by_redistribution_status"][
        "eligible_with_upstream_terms"
    ] += 3
    expected_inventory["public_open_review_only_artifacts"] += 3
    if inventory_counts != expected_inventory:
        raise CurrentCoverageV23Error("v23 artifact inventory arithmetic changed")
    generated_at = definition["generated_at"]
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V22_BASE_LINEAGE,
        "format": LEDGER_FORMAT_V4,
        "generated_at": generated_at,
        "ledger_id": V23_LEDGER_ID,
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
        "base_ledger": V22_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V23_DEFINITION_PATH,
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
        "ledger_id": V23_LEDGER_ID,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV23Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _validate_v23_bundle(
    output_path: str | Path,
    *,
    definition_path: str | Path,
    require_live: bool,
) -> dict[str, Any]:
    _require_downstream_pins()
    directory = Path(os.path.abspath(os.fspath(output_path)))
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV23Error("v23 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV23Error("v23 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV23Error("v23 bundle must be frozen 0555/0444")
    definition, _definition_raw, _root, generated = _validate_v23_definition(
        definition_path, require_live=require_live
    )
    expected = build_current_coverage_ledger_v23(definition_path)
    expected_files = {
        LEDGER_FILENAME: expected.ledger_bytes,
        MANIFEST_FILENAME: expected.manifest_bytes,
        MANIFEST_HASH_FILENAME: expected.manifest_hash_bytes,
    }
    for filename, expected_raw in expected_files.items():
        path = directory / filename
        if path.read_bytes() != expected_raw:
            raise CurrentCoverageV23Error(f"v23 {filename} differs")
    if require_live:
        _assert_final_root_ctimes(
            (Path(definition_path), directory), generated
        )
    if definition["generated_at"] != expected.manifest["generated_at"]:
        raise CurrentCoverageV23Error("v23 definition and bundle time differ")
    return dict(expected.manifest)


def _aware_utc(value: datetime | None, label: str) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise CurrentCoverageV23Error(f"{label} lacks timezone")
    return result.astimezone(UTC)


def _stage_paths(definition_stage: Path, bundle_stage: Path) -> tuple[Path, ...]:
    if definition_stage.is_symlink() or not definition_stage.is_file():
        raise CurrentCoverageV23Error("v23 definition stage must be a regular file")
    if bundle_stage.is_symlink() or not bundle_stage.is_dir():
        raise CurrentCoverageV23Error("v23 bundle stage must be a regular directory")
    descendants = sorted(
        bundle_stage.rglob("*"), key=lambda path: path.relative_to(bundle_stage).as_posix()
    )
    for path in descendants:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise CurrentCoverageV23Error(f"v23 stage is contaminated: {path}")
    return (definition_stage, bundle_stage, *descendants)


def _assert_stage_precedes_target(
    paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise CurrentCoverageV23Error("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target + 0.000_001:
            raise CurrentCoverageV23Error(
                f"v23 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctimes(
    final_paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in final_paths:
        if path.is_symlink() or not path.exists():
            raise CurrentCoverageV23Error(f"v23 final root is absent: {path}")
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target:
            raise CurrentCoverageV23Error(
                f"v23 final root rename predates generated_at: {path.name}"
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
    _raw, document = _read_json(definition_stage, "staged v23 definition")
    if document.get("ledger_id") != V23_LEDGER_ID:
        raise CurrentCoverageV23Error("staged v23 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV23Error("staged v23 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v23 generated_at")
    now = _aware_utc(wall_clock, "v23 staging wall clock")
    if now >= generated:
        raise CurrentCoverageV23Error(
            "v23 generated_at must remain future while private staging completes"
        )
    for final in (Path(final_definition), Path(final_bundle)):
        if final.exists() or final.is_symlink():
            raise CurrentCoverageV23Error("v23 final path exposed during staging")
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
    raw, document = _read_json(stage, "staged v23 definition")
    if document.get("ledger_id") != V23_LEDGER_ID:
        raise CurrentCoverageV23Error("staged v23 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV23Error("staged v23 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v23 generated_at")
    now = _aware_utc(wall_clock, "v23 publication wall clock")
    final_definition_path = Path(final_definition)
    final_bundle_path = Path(final_bundle)
    definition_exposed = (
        final_definition_path.exists() or final_definition_path.is_symlink()
    )
    bundle_exposed = final_bundle_path.exists() or final_bundle_path.is_symlink()
    if now < generated and definition_exposed:
        raise CurrentCoverageV23Error(
            "final v23 definition was exposed before generated_at"
        )
    if now < generated and bundle_exposed:
        raise CurrentCoverageV23Error(
            "final v23 bundle was exposed before generated_at"
        )
    if definition_exposed or bundle_exposed:
        raise CurrentCoverageV23Error("v23 final path collision")
    if now < generated:
        raise CurrentCoverageV23Error("v23 generated_at is not yet live")
    if V23_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v23 definition digest fuse is unresolved")
    if _sha256(raw) != V23_DEFINITION_SHA256:
        raise CurrentCoverageV23Error("staged v23 definition digest changed")
    if staged_bundle is not None:
        bundle_stage = Path(staged_bundle)
        _validate_v23_bundle(
            bundle_stage, definition_path=stage, require_live=False
        )
        paths = _stage_paths(stage, bundle_stage)
    else:
        paths = (stage,)
    _assert_stage_precedes_target(paths, generated)
    return generated


def preflight_v23_publication(package_root: str | Path) -> dict[str, Any]:
    """Validate accepted inputs and report the unresolved publication fuses."""

    root = Path(package_root).resolve()
    preview = preview_v23_delta(root)
    final_definition = root / V23_DEFINITION_PATH
    final_bundle = root / V23_BUNDLE_PATH
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV23Error("v23 final definition must remain absent")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV23Error("v23 final bundle must remain absent")
    _require_downstream_pins()
    if V23_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v23 definition digest fuse is unresolved")
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
        raise CurrentCoverageV23Error(f"v23 stage type changed: {path}")
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
        raise CurrentCoverageV23Error("refusing substituted v23 definition stage")
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
        raise CurrentCoverageV23Error("refusing substituted v23 bundle stage")
    entries = list(path.iterdir())
    if not {entry.name for entry in entries}.issubset(BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV23Error("refusing contaminated v23 bundle cleanup")
    if member_identities is not None:
        actual = {
            entry.name: (
                entry.stat(follow_symlinks=False).st_dev,
                entry.stat(follow_symlinks=False).st_ino,
            )
            for entry in entries
        }
        if actual != dict(member_identities):
            raise CurrentCoverageV23Error(
                "refusing identity-changed v23 bundle cleanup"
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
        with _v22._v21._exclusive_output_lock(final_definition):
            with _v22._v21._exclusive_output_lock(final_bundle):
                yield
    except _v22._v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV23Error(str(error).replace("v22", "v23")) from error


def _require_final_paths_absent(
    final_definition: Path, final_bundle: Path, label: str
) -> None:
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV23Error(f"{label} v23 definition path is occupied")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV23Error(f"{label} v23 bundle path is occupied")


def _prepare_v23_publication(
    package_root: Path,
    *,
    generated_at: str,
    wall_clock: datetime,
) -> _PreparedV23Publication:
    final_definition = package_root / V23_DEFINITION_PATH
    final_bundle = package_root / V23_BUNDLE_PATH
    raw = make_v23_definition(package_root, generated_at=generated_at)
    if V23_DEFINITION_SHA256 is None or _sha256(raw) != V23_DEFINITION_SHA256:
        raise CurrentCoverageV23Error("v23 staged definition digest changed")

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
        bundle = build_current_coverage_ledger_v23(definition_stage)
        staged_files = {
            LEDGER_FILENAME: bundle.ledger_bytes,
            MANIFEST_FILENAME: bundle.manifest_bytes,
            MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
        }
        for filename, content in staged_files.items():
            path = bundle_stage / filename
            _v22._v21._write_file(path, content)
            path.chmod(0o444)
            _fsync_regular(path)
        bundle_stage.chmod(0o555)
        _fsync_directory(bundle_stage)
        _validate_v23_bundle(
            bundle_stage, definition_path=definition_stage, require_live=False
        )
        generated = validate_private_staging_boundary(
            definition_stage,
            bundle_stage,
            final_definition,
            final_bundle,
            wall_clock=wall_clock,
        )
        return _PreparedV23Publication(
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
            primary_error.add_note(f"v23 stage cleanup failed: {cleanup_error}")
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
    prepared: _PreparedV23Publication, final_bundle: Path
) -> None:
    if not _path_has_identity(
        final_bundle, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV23Error(
            "refusing rollback of a substituted v23 final bundle"
        )
    if prepared.bundle_stage.exists() or prepared.bundle_stage.is_symlink():
        raise CurrentCoverageV23Error(
            "refusing rollback over an occupied v23 private bundle stage"
        )
    try:
        _v22._v21._promote_noreplace(final_bundle, prepared.bundle_stage)
    except _v22._v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV23Error(
            str(error).replace("v22", "v23")
        ) from error
    if final_bundle.exists() or final_bundle.is_symlink() or not _path_has_identity(
        prepared.bundle_stage, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV23Error(
            "v23 bundle rollback did not restore the owned private inode"
        )
    prepared.bundle_stage.chmod(0o555)
    _fsync_directory(prepared.bundle_stage)
    _fsync_directory(final_bundle.parent)


def _promote_staged_pair(
    prepared: _PreparedV23Publication,
    final_definition: Path,
    final_bundle: Path,
) -> None:
    if stat.S_IMODE(prepared.bundle_stage.stat().st_mode) != 0o555:
        raise CurrentCoverageV23Error(
            "v23 private bundle must be frozen before its promotion transition"
        )
    prepared.bundle_stage.chmod(0o755)
    _fsync_directory(prepared.bundle_stage)
    try:
        _v22._v21._promote_noreplace(prepared.bundle_stage, final_bundle)
    except _v22._v21.CurrentCoverageV21Error as error:
        if _path_has_identity(
            prepared.bundle_stage, prepared.bundle_identity, directory=True
        ):
            prepared.bundle_stage.chmod(0o555)
            _fsync_directory(prepared.bundle_stage)
        raise CurrentCoverageV23Error(
            str(error).replace("v22", "v23")
        ) from error
    if not _path_has_identity(final_bundle, prepared.bundle_identity, directory=True):
        raise CurrentCoverageV23Error("v23 final bundle identity changed on promotion")
    _fsync_directory(final_bundle.parent)
    try:
        _v22._v21._promote_noreplace(prepared.definition_stage, final_definition)
    except BaseException as definition_error:
        try:
            _rollback_owned_bundle_promotion(prepared, final_bundle)
        except Exception as rollback_error:
            definition_error.add_note(
                f"v23 owned-bundle rollback failed: {rollback_error}"
            )
        if isinstance(definition_error, _v22._v21.CurrentCoverageV21Error):
            raise CurrentCoverageV23Error(
                str(definition_error).replace("v22", "v23")
            ) from definition_error
        raise
    if not _path_has_identity(
        final_definition, prepared.definition_identity, directory=False
    ):
        raise CurrentCoverageV23Error(
            "v23 final definition identity changed on promotion"
        )
    final_bundle.chmod(0o555)
    _fsync_directory(final_bundle)
    _fsync_directory(final_definition.parent)


def publish_current_coverage_v23(
    package_root: str | Path,
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Stage both artifacts before target, then publish them without replacement."""

    root = Path(package_root).resolve()
    final_definition = root / V23_DEFINITION_PATH
    final_bundle = root / V23_BUNDLE_PATH
    target = _parse_timestamp(generated_at, "v23 generated_at")
    if _clock() >= target.timestamp():
        raise CurrentCoverageV23Error(
            "v23 generated_at must be future before private staging starts"
        )
    preflight_v23_publication(root)
    with _publication_locks(final_definition, final_bundle):
        _require_final_paths_absent(final_definition, final_bundle, "initial")
        prepared = _prepare_v23_publication(
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
                raise CurrentCoverageV23Error(
                    "v23 private stage changed while awaiting publication"
                )
            _require_final_paths_absent(final_definition, final_bundle, "late")
            _promote_staged_pair(
                prepared, final_definition, final_bundle
            )
            if stat.S_IMODE(final_definition.stat().st_mode) != 0o444:
                raise CurrentCoverageV23Error(
                    "v23 final definition must be frozen 0444"
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
                        raise CurrentCoverageV23Error(
                            "refusing cleanup of changed v23 private bundle"
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
                primary_error.add_note(f"v23 stage cleanup failed: {cleanup_error}")
            raise
    return validate_current_coverage_ledger_v23(
        final_bundle, definition_path=final_definition
    )


def write_v23_definition(
    package_root: str | Path, output_path: str | Path, *, generated_at: str
) -> str:
    """Refuse publication until all downstream and digest fuses are sealed."""

    preflight_v23_publication(package_root)
    raw = make_v23_definition(package_root, generated_at=generated_at)
    if _sha256(raw) != V23_DEFINITION_SHA256:
        raise CurrentCoverageV23Error("v23 definition digest changed")
    destination = Path(os.path.abspath(os.fspath(output_path)))
    if destination.exists() or destination.is_symlink():
        raise CurrentCoverageV23Error(f"refusing existing output: {destination}")
    raise CurrentCoverageV23Error(
        "v23 definition cannot publish alone; use the paired v23 publisher"
    )


def write_current_coverage_ledger_v23(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    if freeze is not True:
        raise CurrentCoverageV23Error("v23 publication requires freeze=True")
    definition = Path(definition_path)
    root = definition.parent.parent.resolve()
    preflight_v23_publication(root)
    if Path(output_path).resolve() != root / V23_BUNDLE_PATH:
        raise CurrentCoverageV23Error("v23 bundle publication path changed")
    raise CurrentCoverageV23Error(
        "v23 bundle cannot publish alone; use the paired v23 publisher"
    )


def validate_current_coverage_ledger_v23(
    output_path: str | Path, *, definition_path: str | Path
) -> dict[str, Any]:
    _require_downstream_pins()
    definition = Path(definition_path).resolve()
    root = definition.parent.parent.resolve()
    output = Path(output_path).resolve()
    if definition != root / V23_DEFINITION_PATH:
        raise CurrentCoverageV23Error("v23 definition publication path changed")
    if output != root / V23_BUNDLE_PATH:
        raise CurrentCoverageV23Error("v23 bundle publication path changed")
    return _validate_v23_bundle(
        output, definition_path=definition, require_live=True
    )


__all__ = [
    "ADDED_3_SHA256",
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_KINDS_V4",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT_V4",
    "CurrentCoverageV23Bundle",
    "CurrentCoverageV23Error",
    "DEFINITION_SCHEMA_VERSION_V4",
    "LEDGER_FORMAT_V4",
    "LEDGER_SCHEMA_VERSION_V4",
    "NEW_ARTIFACT_IDS",
    "NON_LEDGER_ARTIFACT_DECISIONS",
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
    "V22_BASE_LINEAGE",
    "V23_BUNDLE_PATH",
    "V23_DEFINITION_PATH",
    "V23_DEFINITION_SHA256",
    "V23_GENERATED_AT",
    "V23_LEDGER_ID",
    "build_current_coverage_ledger_v23",
    "make_v23_definition",
    "pending_downstream_pins",
    "preflight_v23_publication",
    "preview_parity_gaps",
    "preview_v23_delta",
    "publish_current_coverage_v23",
    "validate_current_coverage_ledger_v23",
    "validate_private_staging_boundary",
    "validate_prepublication_boundary",
    "write_current_coverage_ledger_v23",
    "write_v23_definition",
]
