"""Collision-isolated current-coverage ledger v19.

V19 is a strict successor of the accepted frozen v18 ledger. It replaces
exactly seven entries with the accepted v56 public chain, preserves the other
forty entries byte-for-byte, and adds nothing. The v3 imagery review is a
review-only wrapper around its queue, catalog, runtime retry, and explicitly
excluded technical incident; those raw runs are not separate ledger entries.
Unseeded Google Bermuda Hundred, Aligned IAD-06, and NEXTDC successors are
outside this ledger.
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

from . import construction_map_v8 as _map_v8
from . import construction_master_v8 as _master_v8
from . import coverage_audit as _coverage
from . import current_coverage as _legacy
from . import current_coverage_v14 as _v14
from . import current_coverage_v18 as _v18
from . import exact_identity_decisions as _identity
from . import federated_release as _federation
from . import open_seed_v56 as _seed_v56
from . import satellite_change_review_v3 as _review_v3


V19_LEDGER_ID = "current-coverage-2026-07-20-v19"
V19_GENERATED_AT = "2026-07-20T23:25:00Z"
V19_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v19.json"
V19_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v19"
V19_DEFINITION_SHA256 = (
    "6ffd11fdeab77cb92c9c820c917f0a0e02f68c417907b70aec8059fbae9dee04"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V18_BASE_LINEAGE = {
    "definition": {
        "bytes": 142_381,
        "path": "sources/current-coverage-2026-07-20-v18.json",
        "sha256": "d8e151cb9b9f38349c5a462a31d91ec70776d5bd25d0228becffb8f0d7546e8c",
    },
    "ledger": {
        "bytes": 98_109,
        "path": (
            "current_coverage_ledgers/2026-07-20-v18/"
            "current-coverage-ledger.json"
        ),
        "sha256": "a1c1e6f680db43c7b571bb94846315f756c918b58e2eea31853ef2e6c1740f01",
    },
    "ledger_id": "current-coverage-2026-07-20-v18",
    "manifest": {
        "bytes": 27_414,
        "path": "current_coverage_ledgers/2026-07-20-v18/manifest.json",
        "sha256": "a3fdc74b36ce33f6959c436ecb34f6171614a0e96d8a4f9a8140db9f33a5d2f4",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v23": "construction-map-public-open-v24",
    "construction-master-public-open-v23": "construction-master-public-open-v24",
    "coverage-audit-public-open-v23": "coverage-audit-public-open-v24",
    "exact-identity-decisions-public-open-v2": (
        "exact-identity-decisions-public-open-v3"
    ),
    "federation-public-open-v24": "federation-public-open-v25",
    "satellite-change-review-open-seed-v55-active-review-v1": (
        "satellite-change-review-open-seed-v56-active-review-v1"
    ),
    "seed-epoch-official-v55": "seed-epoch-official-v56",
}
ADDED_ARTIFACT_IDS: frozenset[str] = frozenset()
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS

UNCHANGED_40_SHA256 = "c534ed692c49ab001fd49c5ec9d861254945dc27d0975bbcb4a024ac8e706044"
REPLACEMENT_7_SHA256 = (
    "8077afea00866f88acc838cfd5c8266c7c146ed784240410258a2463b16af7b7"
)
ALL_ENTRIES_SHA256 = "2351b4cf3f499ad22b7c17bc12d029ae6d9f67133b380790e76d0adfb65f6bf6"
PARITY_GAPS_SHA256 = "16092f411665ca38ee80fe1665ddbb7f8e0473e3f3727bba99edc3920b115cc5"

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v18",
    "sha256": "2e02522427363c2c4bc02cd0d19aa81e6d7fe87e647e06d3b0a7ab6e7e14d420",
}

_ACCEPTED_TREES = {
    "construction-map-v24": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v24",
        "sha256": "a1f38b01ae1058aea9c502cb9b2d58881e8613d6e01a777af8fd5579f81dd8f4",
    },
    "construction-master-v24": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v24",
        "sha256": "ee8d3994db5576363ae8bf3c58a990769702781e26d29f97f6775dda8bf95e40",
    },
    "coverage-audit-v24": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v24",
        "sha256": "3828ae78a4b9c29927a4f770fbcc4d36fa10cbada8d9cdde578d447d98e03d37",
    },
    "exact-identity-decisions-v3": {
        "directories": 1,
        "files": 9,
        "path": "exact_identity_decisions/2026-07-20-public-open-v3",
        "sha256": "5ce6d5a2dcd24d612b434124e7d67347e6dabb1a59e198285b1fd2ec51d63ff7",
    },
    "federation-v25": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v25",
        "sha256": "962a7d0733b363935f6640bc36d0930573e1c04ba91679dc7cdbef8cada83e57",
    },
    "official-seed-v56": {
        "directories": 1,
        "files": 13,
        "path": "releases/2026-07-20-open-seed-v56",
        "sha256": "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2",
    },
    "satellite-change-review-v3": {
        "directories": 1,
        "files": 6,
        "path": "satellite_change_reviews/2026-07-20-open-seed-v56-active-review-v1",
        "sha256": "b38079438e238da999a6afa52bb835ac70b57c0c8706082281e58a68d87e5fe4",
    },
}

_PINNED_FILES = {
    "v18 implementation": (
        "datacenter_atlas/current_coverage_v18.py",
        62_454,
        "82c2e03a19dbb3253a44e80cdd6279a6c73f20037f3d22ca004330897a974ace",
    ),
    "v18 compatibility wrapper": (
        "current_coverage_v18.py",
        150,
        "b516ac0a032f163c27c0f258cefbe18309b05903389ee1a8654acbc7f1f1de5e",
    ),
    "v18 definition": (
        V18_BASE_LINEAGE["definition"]["path"],
        V18_BASE_LINEAGE["definition"]["bytes"],
        V18_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v18 ledger": (
        V18_BASE_LINEAGE["ledger"]["path"],
        V18_BASE_LINEAGE["ledger"]["bytes"],
        V18_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v18 manifest": (
        V18_BASE_LINEAGE["manifest"]["path"],
        V18_BASE_LINEAGE["manifest"]["bytes"],
        V18_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v18 sidecar": (
        "current_coverage_ledgers/2026-07-20-v18/manifest.sha256",
        80,
        "c127cf61d6f889162ca0a11ae12beb950be5fdd00d2a7daf13257bbd74baef96",
    ),
    "construction map v24 definition": (
        "sources/construction-map-2026-07-20-public-open-v24.json",
        2_441,
        "59bf6d020cb308b7d2ad1148f39c6794fc7df5697a0f19a0149448e56e1b99cd",
    ),
    "construction map v24 coverage": (
        "construction_maps/2026-07-20-public-open-v24/coverage.json",
        7_435,
        "6528124968bcecbdc62ad3213f5128842d2614fa43fb1bde4c4d43d53833d7b4",
    ),
    "construction map v24 manifest": (
        "construction_maps/2026-07-20-public-open-v24/manifest.json",
        2_192,
        "2b2c2298a550c07a507c7083326f6e062c884a81f6e32da553d1f35c0a7b314b",
    ),
    "construction master v24 definition": (
        "sources/construction-master-2026-07-20-public-open-v24.json",
        5_657,
        "5472a417b58547027e039df6b72bd8d4ee84bcfb186424781422f04e1c9736c0",
    ),
    "construction master v24 coverage": (
        "construction_master/2026-07-20-public-open-v24/coverage.json",
        8_548,
        "d3343af6363a491d8f2f7059ce90778e0e304b1e180aca3c44dd8192950f8811",
    ),
    "construction master v24 manifest": (
        "construction_master/2026-07-20-public-open-v24/manifest.json",
        9_719,
        "61f8c11ce3c782d63d02539b58ebfc2dd4f3e1c9f0957fe5ccda2bc5a5216705",
    ),
    "coverage audit v24 definition": (
        "sources/coverage-audit-2026-07-20-public-open-v24.json",
        3_871,
        "4f236d3bb9b39a546c592f2de2f9e5f771b5c913ea3703d5742c4b99772ed937",
    ),
    "coverage audit v24 manifest": (
        "audits/2026-07-20-public-open-coverage-v24/manifest.json",
        2_240,
        "7fa0fd899ba268bef8d3105fc542e29c150728e0640484c9553d83d4eca392a2",
    ),
    "federation v25 definition": (
        "sources/federation-2026-07-20-public-open-v25.json",
        1_788,
        "2b60e26e211e584d60f6743beef1a3ed7f06714297cd36896cd2f60a0067e829",
    ),
    "federation v25 index": (
        "federated_indexes/2026-07-20-public-open-v25/federated-index.json",
        24_828,
        "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db",
    ),
    "federation v25 manifest": (
        "federated_indexes/2026-07-20-public-open-v25/manifest.json",
        986,
        "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f",
    ),
    "official seed v56 definition": (
        "sources/open-seed-2026-07-20-v56.json",
        67_918,
        "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c",
    ),
    "official seed v56 manifest": (
        "releases/2026-07-20-open-seed-v56/manifest.json",
        9_274,
        "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd",
    ),
    "exact identity v3 definition": (
        "sources/exact-identity-decisions-2026-07-20-public-open-v3.json",
        1_734,
        "f78c91794e3d7e5b6873c702cca07216e25881a49d9cbab9468b8ce406d672eb",
    ),
    "exact identity v3 accounting": (
        "exact_identity_decisions/2026-07-20-public-open-v3/accounting.json",
        980,
        "51bc2f380da7a7f8251ac0e23d0c659c895666bdc3f00b87c2c6ef032b1ea280",
    ),
    "exact identity v3 manifest": (
        "exact_identity_decisions/2026-07-20-public-open-v3/manifest.json",
        11_274,
        "0eb02f73e24831df42235d5b732d09349fff77f725192a2b5221f45d43f1fcdd",
    ),
    "satellite review v3 definition": (
        "definitions/satellite_change_reviews/"
        "2026-07-20-open-seed-v56-active-review-v1.json",
        23_421,
        "c35728fab6b3fa909586d89cb605d978653d9353196a5e7cc56796985e0e4e6c",
    ),
    "satellite review v3 manifest": (
        "satellite_change_reviews/2026-07-20-open-seed-v56-active-review-v1/"
        "manifest.json",
        17_652,
        "269fe8133138d82680b0fa9498f24ee3a886a3e32c58ab4013276d719868dba9",
    ),
    "satellite review v3 summary": (
        "satellite_change_reviews/2026-07-20-open-seed-v56-active-review-v1/"
        "summary.json",
        13_379,
        "e0414cdac8c0a3ad9d8e7d44462df6a3da6517448ad5d231a351555758cc1097",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v24": (
        "construction_maps/2026-07-20-public-open-v24/manifest.json",
        "generated_at",
        "2026-07-20T23:05:01Z",
    ),
    "construction master v24": (
        "construction_master/2026-07-20-public-open-v24/manifest.json",
        "generated_at",
        "2026-07-20T23:05:00Z",
    ),
    "coverage audit v24": (
        "audits/2026-07-20-public-open-coverage-v24/manifest.json",
        "generated_at",
        "2026-07-20T22:55:00Z",
    ),
    "exact identity v3": (
        "exact_identity_decisions/2026-07-20-public-open-v3/manifest.json",
        "recorded_at",
        "2026-07-20T22:55:00Z",
    ),
    "federation v25": (
        "federated_indexes/2026-07-20-public-open-v25/manifest.json",
        "generated_at",
        "2026-07-20T22:54:00Z",
    ),
    "official seed v56": (
        "releases/2026-07-20-open-seed-v56/manifest.json",
        "recorded_at",
        "2026-07-20T22:34:00Z",
    ),
    "satellite change review v3": (
        "satellite_change_reviews/2026-07-20-open-seed-v56-active-review-v1/"
        "manifest.json",
        "generated_at",
        "2026-07-20T23:12:00Z",
    ),
}


class CurrentCoverageV19Error(_legacy.CurrentCoverageError):
    """Raised when the v19 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True)
class CurrentCoverageV19Bundle:
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
        raise CurrentCoverageV19Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV19Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV19Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV19Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV19Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV19Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v14._tree_digest(path, label)
    except (ValueError, _v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV19Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV19Error(f"{label} closed tree changed")


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v14._checkpoint(checkpoint_id, path, byte_count, sha256, binding=binding)


def _metric(label: str, checkpoint_id: str, pointer: str, value: Any) -> dict[str, Any]:
    return _v14._metric(label, checkpoint_id, pointer, value)


def _replacement_checkpoints() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v24": [
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-20-public-open-v24/coverage.json",
                7_435,
                "6528124968bcecbdc62ad3213f5128842d2614fa43fb1bde4c4d43d53833d7b4",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-20-public-open-v24.json",
                2_441,
                "59bf6d020cb308b7d2ad1148f39c6794fc7df5697a0f19a0149448e56e1b99cd",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-20-public-open-v24/manifest.json",
                2_192,
                "2b2c2298a550c07a507c7083326f6e062c884a81f6e32da553d1f35c0a7b314b",
            ),
        ],
        "construction-master-public-open-v24": [
            _checkpoint(
                "coverage",
                "construction_master/2026-07-20-public-open-v24/coverage.json",
                8_548,
                "d3343af6363a491d8f2f7059ce90778e0e304b1e180aca3c44dd8192950f8811",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-20-public-open-v24.json",
                5_657,
                "5472a417b58547027e039df6b72bd8d4ee84bcfb186424781422f04e1c9736c0",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-20-public-open-v24/manifest.json",
                9_719,
                "61f8c11ce3c782d63d02539b58ebfc2dd4f3e1c9f0957fe5ccda2bc5a5216705",
            ),
        ],
        "coverage-audit-public-open-v24": [
            _checkpoint(
                "manifest",
                "audits/2026-07-20-public-open-coverage-v24/manifest.json",
                2_240,
                "7fa0fd899ba268bef8d3105fc542e29c150728e0640484c9553d83d4eca392a2",
            )
        ],
        "exact-identity-decisions-public-open-v3": [
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-20-public-open-v3/accounting.json",
                980,
                "51bc2f380da7a7f8251ac0e23d0c659c895666bdc3f00b87c2c6ef032b1ea280",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-20-public-open-v3.json",
                1_734,
                "f78c91794e3d7e5b6873c702cca07216e25881a49d9cbab9468b8ce406d672eb",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-20-public-open-v3/manifest.json",
                11_274,
                "0eb02f73e24831df42235d5b732d09349fff77f725192a2b5221f45d43f1fcdd",
            ),
        ],
        "federation-public-open-v25": [
            _checkpoint(
                "index",
                "federated_indexes/2026-07-20-public-open-v25/federated-index.json",
                24_828,
                "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-20-public-open-v25/manifest.json",
                986,
                "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f",
            ),
        ],
        "satellite-change-review-open-seed-v56-active-review-v1": [
            _checkpoint(
                "definition",
                "definitions/satellite_change_reviews/"
                "2026-07-20-open-seed-v56-active-review-v1.json",
                23_421,
                "c35728fab6b3fa909586d89cb605d978653d9353196a5e7cc56796985e0e4e6c",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v56-active-review-v1/manifest.json",
                17_652,
                "269fe8133138d82680b0fa9498f24ee3a886a3e32c58ab4013276d719868dba9",
            ),
            _checkpoint(
                "source_run_manifest",
                "satellite_change_runs/"
                "2026-07-20-open-seed-v56-active-runtime-retry-001/"
                "batch-manifest.json",
                42_990,
                "f94fb3298b352dc579ae5d07020e442889424e782ee04dbbe6f306826270c5f8",
                binding=("manifest", "/source_change_run/manifest"),
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v56-active-review-v1/summary.json",
                13_379,
                "e0414cdac8c0a3ad9d8e7d44462df6a3da6517448ad5d231a351555758cc1097",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        "seed-epoch-official-v56": [
            _checkpoint(
                "manifest",
                "releases/2026-07-20-open-seed-v56/manifest.json",
                9_274,
                "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd",
            )
        ],
    }


def _replacement_limitations() -> dict[str, list[str]]:
    return {
        "construction-map-public-open-v24": [
            "Map rows are a presentation derivative of construction-master v24 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Two hundred eighty master observations lack coordinates, including 262 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        "construction-master-public-open-v24": [
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses are source-scoped observations and do not establish current construction after reported_status_date.",
            "Only 468 Tier-A source-supported observation rows enter construction arithmetic; the 109,260 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        "coverage-audit-public-open-v24": [
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 679 source and source-country groups and 3,452 open gaps are coverage-accounting units, not site counts.",
        ],
        "exact-identity-decisions-public-open-v3": [
            "Canonical topology links preserve explicit facility-contains-building and project-targets relationships and are non-additive; they are not unique physical-site counts.",
            "Exact same-kind source-record components collapse repeat occurrences only within their source-scoped keys and authorize neither cross-kind nor cross-source identity union.",
            "Review-only fuzzy references remain excluded from exact-component accounting; unresolved and ambiguous candidate references remain review work, while physical-site bounds and unique physical sites stay null.",
        ],
        "federation-public-open-v25": [
            "The 16,092 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,598 construction-pipeline records include 6,130 review-only fuzzy rows and only 468 non-review observations; they are not all confirmed construction sites.",
        ],
        "satellite-change-review-open-seed-v56-active-review-v1": [
            "Six analyst decisions and thirty-six hash-bound source artifacts are review records, not construction, identity, lifecycle, status, type, capacity, power, energy, PUE, workload, area, or unique-site evidence.",
            "Three outputs are retained only for site-aligned visible-change follow-up and three are rejected for site promotion; neither disposition negates separately sourced facts.",
            "One failed AOI requires a future multi-tile mosaic and remains a metadata-only technical blocker; the separate no-raster incident is excluded technical lineage and not a model result.",
        ],
        "seed-epoch-official-v56": [
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; absent fields are not inferred from satellite imagery.",
            "The 667 source-scoped entity rows comprise 359 campus observations and 308 project observations, not deduplicated physical sites.",
        ],
    }


def _replacement_metrics() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v24": [
            _metric("added_replacement_rows_unmapped", "coverage", "/projection/added_replacement_rows_unmapped", 144),
            _metric("default_visible_rows", "definition", "/expected_projection/default_visible_rows", 6_486),
            _metric("mapped_replacement_rows", "coverage", "/counts/mapped_replacement_rows", 87),
            _metric("mapped_rows_with_any_role", "coverage", "/counts/mapped_rows_with_any_role", 68),
            _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 206),
            _metric("mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280),
            _metric("mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494),
            _metric("mapped_total_rows", "coverage", "/counts/mapped_observation_rows", 108_980),
            _metric("mapped_unknown_country_rows", "coverage", "/mapped_counts/by_country/Unknown", 102_541),
            _metric("master_total_rows", "coverage", "/counts/master_observation_rows", 109_260),
            _metric("unique_physical_sites", "coverage", "/counts/unique_physical_site_count", None),
            _metric("unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 280),
        ],
        "construction-master-public-open-v24": [
            _metric("added_replacement_rows", "coverage", "/replacement_invariants/added_replacement_rows", 149),
            _metric("base_rows", "coverage", "/replacement_invariants/base_rows", 109_111),
            _metric("contract_marked_rows", "coverage", "/replacement_invariants/rows_with_contract_marker", 348),
            _metric("inherited_rows", "coverage", "/replacement_invariants/inherited_rows", 108_912),
            _metric("publication_contract_version", "coverage", "/replacement/publication_contract_version", 4),
            _metric("replacement_rows", "coverage", "/replacement_invariants/replacement_rows", 348),
            _metric("role_rows_with_any_role", "coverage", "/role_counts/rows_with_any_role", 126),
            _metric("role_rows_with_customers", "coverage", "/role_counts/with_core_role/customers", 2),
            _metric("role_rows_with_operator", "coverage", "/role_counts/with_core_role/operator", 49),
            _metric("role_rows_with_owner", "coverage", "/role_counts/with_core_role/owner", 47),
            _metric("role_rows_with_source_role_tags", "coverage", "/role_counts/rows_with_source_role_tags", 87),
            _metric("role_rows_with_tenants", "coverage", "/role_counts/with_core_role/tenants", 6),
            _metric("role_rows_with_users", "coverage", "/role_counts/with_core_role/users", 36),
            _metric("satellite_recovery_control_plane_bytes", "coverage", "/satellite_recovery_acceptance/control_plane_bytes", 15_313),
            _metric("satellite_recovery_control_plane_files", "coverage", "/satellite_recovery_acceptance/control_plane_files", 4),
            _metric("satellite_recovery_rows", "coverage", "/satellite_recovery_acceptance/rows_created", 0),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 468),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
            _metric("total_master_rows", "coverage", "/row_counts/total", 109_260),
            _metric("unchanged_replacement_rows", "coverage", "/replacement_invariants/unchanged_replacement_rows", 199),
            _metric("unique_physical_sites", "coverage", "/row_counts/unique_physical_site_count", None),
        ],
        "coverage-audit-public-open-v24": [
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 679),
            _metric("non_review_source_scoped_rows", "manifest", "/counts/non_review_source_scoped_entity_records", 9_962),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 3_452),
            _metric("review_only_source_scoped_rows", "manifest", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "manifest", "/counts/source_scoped_entity_records", 16_092),
            _metric("unique_physical_sites", "manifest", "/counts/unique_physical_sites", None),
        ],
        "exact-identity-decisions-public-open-v3": [
            _metric("ambiguous_identity_candidate_references", "accounting", "/ambiguous_identity_candidate_references", 127),
            _metric("canonical_topology_links", "accounting", "/canonical_topology_links", 2_317),
            _metric("exact_component_reductions", "accounting", "/exact_component_reductions", 1_732),
            _metric("exact_source_record_components", "accounting", "/exact_source_record_components", 8_230),
            _metric("non_review_source_scoped_rows", "accounting", "/non_review_source_scoped_entity_records", 9_962),
            _metric("physical_site_lower_bound", "accounting", "/physical_site_lower_bound", None),
            _metric("physical_site_upper_bound", "accounting", "/physical_site_upper_bound", None),
            _metric("raw_topology_links", "accounting", "/raw_topology_links", 2_722),
            _metric("release_candidate_references", "accounting", "/release_candidate_references", 100_409),
            _metric("review_only_rows_in_public_accounting", "manifest", "/scope/review_only_rows_in_public_accounting", False),
            _metric("source_scoped_entity_rows", "accounting", "/source_scoped_entity_records", 16_092),
            _metric("unique_physical_sites", "accounting", "/unique_physical_sites", None),
            _metric("unresolved_candidate_references", "accounting", "/unresolved_candidate_references", 100_536),
        ],
        "federation-public-open-v25": [
            _metric("capacity_observations", "index", "/counts/capacity_estimates", 1_270),
            _metric("construction_pipeline_records", "index", "/counts/construction_pipeline_records", 6_598),
            _metric("non_review_construction_pipeline_records", "index", "/counts/non_review_construction_pipeline_records", 468),
            _metric("non_review_source_scoped_rows", "index", "/counts/non_review_source_scoped_entity_records", 9_962),
            _metric("review_only_construction_pipeline_records", "index", "/counts/review_only_construction_pipeline_records", 6_130),
            _metric("review_only_source_scoped_rows", "index", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "index", "/counts/source_scoped_entity_records", 16_092),
            _metric("unique_physical_sites", "index", "/counts/unique_physical_sites", None),
        ],
        "satellite-change-review-open-seed-v56-active-review-v1": [
            _metric("atlas_mutation", "summary", "/scope/atlas_mutation", False),
            _metric("capacity_claim_created", "summary", "/scope/capacity_claim_created", False),
            _metric("manual_review_completed", "summary", "/scope/manual_review_completed", True),
            _metric("review_decisions", "summary", "/counts/decisions", 6),
            _metric("site_aligned_follow_up_retained", "summary", "/counts/retain_for_site_aligned_visible_change_follow_up", 3),
            _metric("site_count_claim_created", "summary", "/scope/site_count_claim_created", False),
            _metric("site_promotion_rejections", "summary", "/counts/reject_for_site_promotion", 3),
            _metric("source_artifacts_hash_bound", "summary", "/counts/source_artifacts_hash_bound", 36),
            _metric("technical_multitile_failures", "summary", "/counts/technical_multitile_failures", 1),
            _metric("unique_site_claim_created", "summary", "/scope/unique_site_claim_created", False),
        ],
        "seed-epoch-official-v56": [
            _metric("capacity_observations", "manifest", "/capacity_estimates", 484),
            _metric("construction_pipeline_records", "manifest", "/construction_pipeline_records", 348),
            _metric("construction_source_signals", "manifest", "/construction_source_signals", 254),
            _metric("evidence_records", "manifest", "/evidence_records", 388),
            _metric("resolution_candidates", "manifest", "/resolution_candidates", 4),
            _metric("source_scoped_entity_rows", "manifest", "/entities", 667),
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
        raise CurrentCoverageV19Error("v19 replacement specification changed")
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in ARTIFACT_REPLACEMENTS.items():
        entry = deepcopy(dict(base_entries[old_id]))
        entry["artifact_id"] = new_id
        entry["checkpoints"] = checkpoints[new_id]
        entry["limitations"] = sorted(limitations[new_id])
        entry["metrics"] = metrics[new_id]
        result[new_id] = entry
    return result


def _load_v18_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_path = package_root / V18_BASE_LINEAGE["definition"]["path"]
    bundle_path = package_root / _BASE_BUNDLE_TREE["path"]
    try:
        _v18.validate_current_coverage_ledger_v18(
            bundle_path, definition_path=definition_path
        )
    except _v18.CurrentCoverageV18Error as error:
        raise CurrentCoverageV19Error(
            f"accepted v18 base failed offline validation: {error}"
        ) from error
    definition_raw, definition = _pinned_json(
        package_root, V18_BASE_LINEAGE["definition"], "v19 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V18_BASE_LINEAGE["ledger"], "v19 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V18_BASE_LINEAGE["manifest"], "v19 base manifest"
    )
    if (
        definition.get("ledger_id") != V18_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V18_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V18_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V18_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V18_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V18_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV19Error("accepted v18 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v19 base bundle")
    return definition, ledger, manifest


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV19Error(f"{label} timestamp is invalid") from error


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v19 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV19Error(f"v19 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v19 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v19 {label}")
    try:
        _master_v8.validate_construction_master_v8(
            package_root / _ACCEPTED_TREES["construction-master-v24"]["path"],
            definition_path=(
                package_root
                / "sources/construction-master-2026-07-20-public-open-v24.json"
            ),
            reproduce=False,
        )
        _map_v8.validate_construction_map_v8(
            package_root / _ACCEPTED_TREES["construction-map-v24"]["path"],
            master_directory=(
                package_root
                / _ACCEPTED_TREES["construction-master-v24"]["path"]
            ),
            master_definition_path=(
                package_root
                / "sources/construction-master-2026-07-20-public-open-v24.json"
            ),
            map_definition_path=(
                package_root
                / "sources/construction-map-2026-07-20-public-open-v24.json"
            ),
            reproduce=False,
        )
        _coverage.validate_coverage_audit(
            package_root / _ACCEPTED_TREES["coverage-audit-v24"]["path"],
            definition_path=(
                package_root
                / "sources/coverage-audit-2026-07-20-public-open-v24.json"
            ),
        )
        _federation.validate_federated_release_index(
            package_root / _ACCEPTED_TREES["federation-v25"]["path"]
        )
        _seed_v56.validate_open_seed_release(
            package_root / "sources/open-seed-2026-07-20-v56.json",
            package_root / _ACCEPTED_TREES["official-seed-v56"]["path"],
            require_frozen=True,
        )
        _identity.validate_exact_identity_decision_bundle(
            package_root
            / _ACCEPTED_TREES["exact-identity-decisions-v3"]["path"],
            definition_path=(
                package_root
                / "sources/exact-identity-decisions-2026-07-20-public-open-v3.json"
            ),
            verify_inputs=False,
            require_frozen=True,
        )
        _review_v3.validate_satellite_change_review_v3(
            package_root / _ACCEPTED_TREES["satellite-change-review-v3"]["path"],
            definition_path=(
                package_root
                / "definitions/satellite_change_reviews/"
                "2026-07-20-open-seed-v56-active-review-v1.json"
            ),
        )
    except Exception as error:
        raise CurrentCoverageV19Error(
            f"accepted v56 successor input failed offline validation: {error}"
        ) from error
    generated_at = _parse_timestamp(V19_GENERATED_AT, "v19")
    for label, (relative, field, expected) in sorted(_SOURCE_TIMESTAMPS.items()):
        document = _json_object(
            _read_regular(package_root / relative, f"v19 {label} timestamp source"),
            f"v19 {label} timestamp source",
        )
        if document.get(field) != expected:
            raise CurrentCoverageV19Error(f"v19 {label} timestamp changed")
        if _parse_timestamp(expected, f"v19 {label}") > generated_at:
            raise CurrentCoverageV19Error(f"v19 predates {label}")


def _v19_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV19Error("v18 parity gaps are invalid")
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV19Error("v18 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        gap["affected_artifact_ids"] = sorted(
            ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        )
        result.append(gap)
    return result


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _require_digest(actual: str, expected: str, label: str) -> None:
    if expected and actual != expected:
        raise CurrentCoverageV19Error(f"v19 {label} digest changed")


def make_v19_definition(package_root: str | Path) -> bytes:
    """Create canonical v19 definition bytes from the pinned v18 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v18_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if len(base_entries) != 47 or not REMOVED_ARTIFACT_IDS <= set(base_entries):
        raise CurrentCoverageV19Error("v18 replacement source inventory changed")
    if set(base_entries) & NEW_ARTIFACT_IDS:
        raise CurrentCoverageV19Error("v18 unexpectedly contains a v19 artifact ID")
    replacements = _replacement_entries(base_entries)
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    if len(base_entries) != 47:
        raise CurrentCoverageV19Error("v19 definition must contain 47 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] not in NEW_ARTIFACT_IDS
    ]
    replacement_entries = [
        entry for entry in ordered if entry["artifact_id"] in REPLACEMENT_ARTIFACT_IDS
    ]
    if len(unchanged) != 40 or len(replacement_entries) != 7:
        raise CurrentCoverageV19Error("v19 delta arithmetic changed")
    parity_gaps = _v19_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_40_SHA256, "inherited entries"
    )
    _require_digest(
        _component_digest(replacement_entries),
        REPLACEMENT_7_SHA256,
        "replacement entries",
    )
    _require_digest(_component_digest(ordered), ALL_ENTRIES_SHA256, "all entries")
    _require_digest(
        _sha256(_canonical_line(parity_gaps)), PARITY_GAPS_SHA256, "parity gaps"
    )
    document = {
        "base_ledger": V18_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V19_GENERATED_AT,
        "ledger_id": V19_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    rendered = raw.decode("utf-8")
    forbidden = (
        *REMOVED_ARTIFACT_IDS,
        "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json",
        "curated-official-2026-07-20-aligned-iad06-frederick-topout.json",
    )
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV19Error("v19 definition contains superseded lineage")
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V19_DEFINITION_PATH:
        raise CurrentCoverageV19Error("v19 definition publication path changed")
    raw = _read_regular(path, "v19 definition")
    document = _json_object(raw, "v19 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV19Error("v19 definition is not canonical JSON")
    if not V19_DEFINITION_SHA256 or _sha256(raw) != V19_DEFINITION_SHA256:
        raise CurrentCoverageV19Error("v19 definition content changed or is unpinned")
    if raw != make_v19_definition(package_root):
        raise CurrentCoverageV19Error(
            "v19 definition differs from pinned transformation"
        )
    if (
        document.get("ledger_id") != V19_LEDGER_ID
        or document.get("generated_at") != V19_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V18_BASE_LINEAGE
    ):
        raise CurrentCoverageV19Error("v19 identity, base, schema, or scope changed")
    if _parse_timestamp(V19_GENERATED_AT, "v19") > datetime.now(UTC):
        raise CurrentCoverageV19Error("v19 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 47:
        raise CurrentCoverageV19Error("v19 must contain exactly 47 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 47 or None in artifact_ids:
        raise CurrentCoverageV19Error("v19 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not NEW_ARTIFACT_IDS <= artifact_ids:
        raise CurrentCoverageV19Error("v19 delta inventory is invalid")
    return document, raw, package_root


def build_current_coverage_ledger_v19(
    definition_path: str | Path,
) -> CurrentCoverageV19Bundle:
    """Reproduce the v19 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, base_ledger, _base_manifest = _load_v18_base(package_root)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    try:
        for spec in definition["entries"]:
            artifact = _legacy._entry(
                package_root,
                spec,
                previous_id,
                _legacy.DEFINITION_SCHEMA_VERSION_V3,
            )
            artifacts.append(artifact)
            previous_id = artifact["artifact_id"]
        parity_gaps = _legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _legacy.CurrentCoverageError as error:
        raise CurrentCoverageV19Error(str(error)) from error
    inventory_counts = _v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != base_ledger["artifact_inventory_counts"]:
        raise CurrentCoverageV19Error("v19 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V18_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V19_GENERATED_AT,
        "ledger_id": V19_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
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
        "base_ledger": V18_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V19_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V19_GENERATED_AT,
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
        "ledger_id": V19_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    return CurrentCoverageV19Bundle(
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
        with _v18._exclusive_output_lock(destination):
            yield
    except _v18.CurrentCoverageV18Error as error:
        raise CurrentCoverageV19Error(str(error).replace("v18", "v19")) from error


def _cleanup_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v18._cleanup_file_stage(stage, identity)
    except _v18.CurrentCoverageV18Error as error:
        raise CurrentCoverageV19Error(str(error).replace("v18", "v19")) from error


def _cleanup_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v18._cleanup_bundle_stage(stage, identity)
    except _v18.CurrentCoverageV18Error as error:
        raise CurrentCoverageV19Error(str(error).replace("v18", "v19")) from error


def _promote_noreplace(stage: Path, destination: Path) -> None:
    try:
        _v18._promote_noreplace(stage, destination)
    except _v18.CurrentCoverageV18Error as error:
        raise CurrentCoverageV19Error(str(error).replace("v18", "v19")) from error


def write_v19_definition(package_root: str | Path, output_path: str | Path) -> str:
    """Atomically create, but never replace, the canonical v19 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v19_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV19Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _v18._v17._v16._path_identity(stage)
            stage.chmod(0o644)
            _v18._v17._v16._fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _v18._v17._v16._fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV19Error(
                    "v19 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v19 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v19(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v19 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV19Error("v19 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v19(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV19Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _v18._v17._v16._path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _v18._v17._v16._fsync_regular(stage / filename)
            stage.chmod(0o555)
            _v18._v17._v16._fsync_directory(stage)
            validate_current_coverage_ledger_v19(stage, definition_path=definition_path)
            _promote_noreplace(stage, destination)
            _v18._v17._v16._fsync_directory(destination.parent)
            validate_current_coverage_ledger_v19(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v19 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v19(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = _lexical_absolute(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV19Error("v19 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV19Error("v19 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV19Error("v19 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v19 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v19 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v19 sidecar")
    ledger = _json_object(actual_ledger, "v19 ledger")
    manifest = _json_object(actual_manifest, "v19 manifest")
    if actual_ledger != _canonical_json(ledger):
        raise CurrentCoverageV19Error("v19 ledger is not canonical JSON")
    if actual_manifest != _canonical_json(manifest):
        raise CurrentCoverageV19Error("v19 manifest is not canonical JSON")
    if actual_sidecar != (
        f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CurrentCoverageV19Error("v19 manifest sidecar differs")
    expected = build_current_coverage_ledger_v19(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV19Error("v19 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV19Error("v19 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV19Error("v19 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV19Bundle",
    "CurrentCoverageV19Error",
    "NEW_ARTIFACT_IDS",
    "PARITY_GAPS_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_7_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "UNCHANGED_40_SHA256",
    "V18_BASE_LINEAGE",
    "V19_BUNDLE_PATH",
    "V19_DEFINITION_PATH",
    "V19_DEFINITION_SHA256",
    "V19_GENERATED_AT",
    "V19_LEDGER_ID",
    "build_current_coverage_ledger_v19",
    "make_v19_definition",
    "validate_current_coverage_ledger_v19",
    "write_current_coverage_ledger_v19",
    "write_v19_definition",
]
