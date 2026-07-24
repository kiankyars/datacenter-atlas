"""Collision-isolated current-coverage ledger v18.

V18 derives only from the accepted frozen v17 ledger. It replaces exactly five
public-core entries with the accepted v55 downstream chain, adds the
authoritative source-scoped exact-identity decision index and the review-only
v55 satellite-change analyst review, and preserves the other forty canonical
entries byte-for-byte. No PAIX, PentaPoint, or future v56 artifact is consumed.
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

from . import current_coverage as _legacy
from . import current_coverage_v14 as _v14
from . import current_coverage_v17 as _v17
from . import exact_identity_decisions as _identity
from . import satellite_change_review_v2 as _review_v2


V18_LEDGER_ID = "current-coverage-2026-07-20-v18"
V18_GENERATED_AT = "2026-07-20T22:35:00Z"
V18_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v18.json"
V18_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v18"
V18_DEFINITION_SHA256 = (
    "d8e151cb9b9f38349c5a462a31d91ec70776d5bd25d0228becffb8f0d7546e8c"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V17_BASE_LINEAGE = {
    "definition": {
        "bytes": 133_016,
        "path": "sources/current-coverage-2026-07-20-v17.json",
        "sha256": "6ddeea2d789d8dbbf09df12fc4739e67d1f5ee04b6a99c98a27366f9a965ad0f",
    },
    "ledger": {
        "bytes": 92_132,
        "path": (
            "current_coverage_ledgers/2026-07-20-v17/current-coverage-ledger.json"
        ),
        "sha256": "d87e0cc5869e5887c5336449cd98859075065cb56bfe620499c8d4e64e863fa6",
    },
    "ledger_id": "current-coverage-2026-07-20-v17",
    "manifest": {
        "bytes": 25_659,
        "path": "current_coverage_ledgers/2026-07-20-v17/manifest.json",
        "sha256": "f782fd93681c0a66527f033f304554d288128f0209db7437ef8fd28c1cebe1e2",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v22": "construction-map-public-open-v23",
    "construction-master-public-open-v22": "construction-master-public-open-v23",
    "coverage-audit-public-open-v22": "coverage-audit-public-open-v23",
    "federation-public-open-v23": "federation-public-open-v24",
    "seed-epoch-official-v49": "seed-epoch-official-v55",
}
ADDED_ARTIFACT_IDS = frozenset(
    {
        "exact-identity-decisions-public-open-v2",
        "satellite-change-review-open-seed-v55-active-review-v1",
    }
)
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS

UNCHANGED_40_SHA256 = "c534ed692c49ab001fd49c5ec9d861254945dc27d0975bbcb4a024ac8e706044"
REPLACEMENT_5_SHA256 = (
    "ef1d560a1705980b6da2ea0aac14754e6b0b15540ff4e4af438fa467dcefb295"
)
ADDITION_2_SHA256 = "755c616f9c2a264c395893fad0ca02c144c7736642260b2fd02390b5900c59b5"
ALL_ENTRIES_SHA256 = "e6cd27cb694456fc540843c89c35053aaecf45fcacdf527ef4c9892bed647510"
PARITY_GAPS_SHA256 = "350a13a28e535b3e3f3b0bd12b7eb3add3a08d1ec36f8ad42aba57ff94267e04"

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v17",
    "sha256": "7bcd3bc45f4e9329cfd6ac852737a497b76855be1f4f2c17265933ccb6de7e37",
}

_ACCEPTED_TREES = {
    "construction-map-v23": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v23",
        "sha256": "377677b9d7d5e750af8b4312086f1320ab09258baa4a92f44208193ccc3ad326",
    },
    "construction-master-v23": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v23",
        "sha256": "37100ba7e612e81b7aecc8516224a75d67f70af41ac3b9991b18912238a0f077",
    },
    "coverage-audit-v23": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v23",
        "sha256": "6df5bd35b44e8efc5d230246ae36c5f3093876cedf64198f362f2613aeeddb8f",
    },
    "exact-identity-decisions-v2": {
        "directories": 1,
        "files": 9,
        "path": "exact_identity_decisions/2026-07-20-public-open-v2",
        "sha256": "11b6b59a9e98c73289d1a5e9311be8b2470dc08c16dd806bfd777d6919ff426e",
    },
    "federation-v24": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v24",
        "sha256": "7ee18187b63f6f68e39d04b808cb0de294eddb2837b79bb0ac7259685029e4f3",
    },
    "official-seed-v55": {
        "directories": 1,
        "files": 13,
        "path": "releases/2026-07-20-open-seed-v55",
        "sha256": "44610a81fab0375255da9824975746ce301591a2b94e099f43f551eb7eb157b4",
    },
    "satellite-change-review-v2": {
        "directories": 1,
        "files": 6,
        "path": ("satellite_change_reviews/2026-07-20-open-seed-v55-active-review-v1"),
        "sha256": "baf1172ab85658ea80f34fdafc68868e2f8fc112ab5fc06e219015b6361c4a59",
    },
}

_PINNED_FILES = {
    "v17 implementation": (
        "datacenter_atlas/current_coverage_v17.py",
        44_652,
        "f5933e7a77b1ec437a09ff71b806baf2ce5996a037c4ace25dc01f2c77516770",
    ),
    "v17 compatibility wrapper": (
        "current_coverage_v17.py",
        150,
        "1cba63622aa9cd23b6b1fb534e61ade356dac8bc1c0df0482f1cc7f9c0fa29ba",
    ),
    "v17 definition": (
        V17_BASE_LINEAGE["definition"]["path"],
        V17_BASE_LINEAGE["definition"]["bytes"],
        V17_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v17 ledger": (
        V17_BASE_LINEAGE["ledger"]["path"],
        V17_BASE_LINEAGE["ledger"]["bytes"],
        V17_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v17 manifest": (
        V17_BASE_LINEAGE["manifest"]["path"],
        V17_BASE_LINEAGE["manifest"]["bytes"],
        V17_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v17 sidecar": (
        "current_coverage_ledgers/2026-07-20-v17/manifest.sha256",
        80,
        "21d1d134176a55fdbb844294ff6508f6023a563c348345ef3e5fe115893f0ce7",
    ),
    "official seed v55 definition": (
        "sources/open-seed-2026-07-20-v55.json",
        67_472,
        "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba",
    ),
    "official seed v55 manifest": (
        "releases/2026-07-20-open-seed-v55/manifest.json",
        9_210,
        "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
    ),
    "federation v24 definition": (
        "sources/federation-2026-07-20-public-open-v24.json",
        1_788,
        "98dc26e06948ff3334a8c3e21fc7b31616cf177362217459f04cd5a9d221e6a0",
    ),
    "federation v24 index": (
        "federated_indexes/2026-07-20-public-open-v24/federated-index.json",
        24_660,
        "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d",
    ),
    "federation v24 manifest": (
        "federated_indexes/2026-07-20-public-open-v24/manifest.json",
        986,
        "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1",
    ),
    "coverage audit v23 definition": (
        "sources/coverage-audit-2026-07-20-public-open-v23.json",
        3_871,
        "3c35a36e02aefbcb169dee6a0dd8b7fe5480983767f0766fd3e7f0c942699436",
    ),
    "coverage audit v23 manifest": (
        "audits/2026-07-20-public-open-coverage-v23/manifest.json",
        2_240,
        "7d282d3d725a3882475bf69f581a6b70f1505ccc135ecc7027b01cd7269e3e23",
    ),
    "construction master v23 implementation": (
        "datacenter_atlas/construction_master_v7.py",
        3_509,
        "80fb676a3f30b92a105a656b206b837360705a3ad2534a663bc53a5488e42f02",
    ),
    "construction master v23 definition": (
        "sources/construction-master-2026-07-20-public-open-v23.json",
        5_657,
        "6a72a8c44808ad6d276fed6141b15ee91e5708b5ff95f91aaf0c011e0c69d438",
    ),
    "construction master v23 coverage": (
        "construction_master/2026-07-20-public-open-v23/coverage.json",
        8_523,
        "a8b1313c5bd017dde45f8f7ed81355a0a0bc9dad065a6ec3543587f22fa0cd7c",
    ),
    "construction master v23 manifest": (
        "construction_master/2026-07-20-public-open-v23/manifest.json",
        9_694,
        "987580aec591763c01a48ba146dfa935db59097ae189479e6a43386b4a1e8384",
    ),
    "construction map v23 implementation": (
        "datacenter_atlas/construction_map_v7.py",
        2_749,
        "053995421f2e581ba49ea5bf89fd539afce527b718c643ea8e1074204a7586be",
    ),
    "construction map v23 definition": (
        "sources/construction-map-2026-07-20-public-open-v23.json",
        2_441,
        "6022402312649301dc921981bc89bb63801b456f9bbcb7915bb9dc475cbdcf79",
    ),
    "construction map v23 coverage": (
        "construction_maps/2026-07-20-public-open-v23/coverage.json",
        7_390,
        "f644082c91dbf7339092bf347652cb7a0335f50e8a3cb55a5d31fd3d6e2db3b9",
    ),
    "construction map v23 manifest": (
        "construction_maps/2026-07-20-public-open-v23/manifest.json",
        2_192,
        "aa394a0e1d231d1ec3c7f28731933c3844d27f7262119027fa9ce87db9602648",
    ),
    "exact identity implementation": (
        "datacenter_atlas/exact_identity_decisions.py",
        76_330,
        "8c5d7fd14575d7f6afdb280144868534c9934753e96658498200a15833ccdfe1",
    ),
    "exact identity v2 definition": (
        "sources/exact-identity-decisions-2026-07-20-public-open-v2.json",
        1_734,
        "65ffef9681c982b2149591706542c6b8277eedc22de63b2ffd2253ec94332a03",
    ),
    "exact identity v2 accounting": (
        "exact_identity_decisions/2026-07-20-public-open-v2/accounting.json",
        980,
        "e01dc4f0381d3ff4449fe8d5acbce6bb85584f2e164bdcf660efa96da19e0e6e",
    ),
    "exact identity v2 manifest": (
        "exact_identity_decisions/2026-07-20-public-open-v2/manifest.json",
        11_274,
        "43724ed405b77ae64505a05a708e514bbdcf9c13044c3255908563eddb5e7d5c",
    ),
    "satellite change review v2 implementation": (
        "datacenter_atlas/satellite_change_review_v2.py",
        56_596,
        "b1643a4d44976ef63985197d1a57b6343125a224cf96c74f676f40a06c671548",
    ),
    "satellite change review v2 definition": (
        "definitions/satellite_change_reviews/"
        "2026-07-20-open-seed-v55-active-review-v1.json",
        18_540,
        "5dbe5e35da8af84a84e62717355c0d5b3c0cc228a2206f6dedb20b41eab83cc3",
    ),
    "satellite change review v2 manifest": (
        "satellite_change_reviews/"
        "2026-07-20-open-seed-v55-active-review-v1/manifest.json",
        18_667,
        "19e025f4435c413ce9d9af1176bd54996ab474fab216277a7b5a5165980a170a",
    ),
    "satellite change review v2 summary": (
        "satellite_change_reviews/"
        "2026-07-20-open-seed-v55-active-review-v1/summary.json",
        8_533,
        "631e16ca6ca6ee5b57dd0d1fd20b0cef492093a7394d05022d48e87a64edea7a",
    ),
    "satellite change source manifest": (
        "satellite_change_runs/2026-07-20-open-seed-v55-active-001/batch-manifest.json",
        41_744,
        "99e58d7bcc09ca850c9add4bfc15635b9808d11eabce8c3782a35a4256ec3a8a",
    ),
}

_SOURCE_TIMESTAMPS = {
    "official seed v55": (
        "releases/2026-07-20-open-seed-v55/manifest.json",
        "recorded_at",
        "2026-07-20T20:05:00Z",
    ),
    "federation v24": (
        "federated_indexes/2026-07-20-public-open-v24/federated-index.json",
        "generated_at",
        "2026-07-20T20:06:00Z",
    ),
    "coverage audit v23": (
        "audits/2026-07-20-public-open-coverage-v23/manifest.json",
        "generated_at",
        "2026-07-20T20:07:00Z",
    ),
    "exact identity v2": (
        "exact_identity_decisions/2026-07-20-public-open-v2/manifest.json",
        "recorded_at",
        "2026-07-20T20:08:00Z",
    ),
    "construction master v23": (
        "construction_master/2026-07-20-public-open-v23/manifest.json",
        "generated_at",
        "2026-07-20T20:20:00Z",
    ),
    "construction map v23": (
        "construction_maps/2026-07-20-public-open-v23/manifest.json",
        "generated_at",
        "2026-07-20T20:20:01Z",
    ),
    "satellite change review v2": (
        "satellite_change_reviews/"
        "2026-07-20-open-seed-v55-active-review-v1/manifest.json",
        "generated_at",
        "2026-07-20T22:12:00Z",
    ),
}


class CurrentCoverageV18Error(_legacy.CurrentCoverageError):
    """Raised when the v18 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True)
class CurrentCoverageV18Bundle:
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
        raise CurrentCoverageV18Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV18Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV18Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV18Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV18Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV18Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v14._tree_digest(path, label)
    except (ValueError, _v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV18Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV18Error(f"{label} closed tree changed")


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


def _entry_spec(**kwargs: Any) -> dict[str, Any]:
    return _v14._entry_spec(**kwargs)


def _replacement_checkpoints() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v23": [
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-20-public-open-v23/coverage.json",
                7_390,
                "f644082c91dbf7339092bf347652cb7a0335f50e8a3cb55a5d31fd3d6e2db3b9",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-20-public-open-v23.json",
                2_441,
                "6022402312649301dc921981bc89bb63801b456f9bbcb7915bb9dc475cbdcf79",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-20-public-open-v23/manifest.json",
                2_192,
                "aa394a0e1d231d1ec3c7f28731933c3844d27f7262119027fa9ce87db9602648",
            ),
        ],
        "construction-master-public-open-v23": [
            _checkpoint(
                "coverage",
                "construction_master/2026-07-20-public-open-v23/coverage.json",
                8_523,
                "a8b1313c5bd017dde45f8f7ed81355a0a0bc9dad065a6ec3543587f22fa0cd7c",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-20-public-open-v23.json",
                5_657,
                "6a72a8c44808ad6d276fed6141b15ee91e5708b5ff95f91aaf0c011e0c69d438",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-20-public-open-v23/manifest.json",
                9_694,
                "987580aec591763c01a48ba146dfa935db59097ae189479e6a43386b4a1e8384",
            ),
        ],
        "coverage-audit-public-open-v23": [
            _checkpoint(
                "manifest",
                "audits/2026-07-20-public-open-coverage-v23/manifest.json",
                2_240,
                "7d282d3d725a3882475bf69f581a6b70f1505ccc135ecc7027b01cd7269e3e23",
            )
        ],
        "federation-public-open-v24": [
            _checkpoint(
                "index",
                "federated_indexes/2026-07-20-public-open-v24/federated-index.json",
                24_660,
                "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-20-public-open-v24/manifest.json",
                986,
                "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1",
            ),
        ],
        "seed-epoch-official-v55": [
            _checkpoint(
                "manifest",
                "releases/2026-07-20-open-seed-v55/manifest.json",
                9_210,
                "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
            )
        ],
    }


def _replacement_limitations() -> dict[str, list[str]]:
    return {
        "construction-map-public-open-v23": [
            "Map rows are a presentation derivative of construction-master v23 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Two hundred eighty master observations lack coordinates, including 262 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        "construction-master-public-open-v23": [
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses are source-scoped observations and do not establish current construction after reported_status_date.",
            "Only 466 Tier-A source-supported observation rows enter construction arithmetic; the 109,258 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        "coverage-audit-public-open-v23": [
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 675 source and source-country groups and 3,435 open gaps are coverage-accounting units, not site counts.",
        ],
        "federation-public-open-v24": [
            "The 16,088 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,596 construction-pipeline records include 6,130 review-only fuzzy rows and only 466 non-review observations; they are not all confirmed construction sites.",
        ],
        "seed-epoch-official-v55": [
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; absent fields are not inferred from satellite imagery.",
            "The 663 source-scoped entity rows comprise 357 campus observations and 306 project observations, not deduplicated physical sites.",
        ],
    }


def _replacement_metrics() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v23": [
            _metric(
                "added_replacement_rows_unmapped",
                "coverage",
                "/projection/added_replacement_rows_unmapped",
                144,
            ),
            _metric(
                "default_visible_rows",
                "definition",
                "/expected_projection/default_visible_rows",
                6_484,
            ),
            _metric(
                "mapped_replacement_rows",
                "coverage",
                "/counts/mapped_replacement_rows",
                85,
            ),
            _metric(
                "mapped_rows_with_any_role",
                "coverage",
                "/counts/mapped_rows_with_any_role",
                66,
            ),
            _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 204),
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
                108_978,
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
                109_258,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/counts/unique_physical_site_count",
                None,
            ),
            _metric(
                "unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 280
            ),
        ],
        "construction-master-public-open-v23": [
            _metric(
                "added_replacement_rows",
                "coverage",
                "/replacement_invariants/added_replacement_rows",
                147,
            ),
            _metric(
                "base_rows", "coverage", "/replacement_invariants/base_rows", 109_111
            ),
            _metric(
                "contract_marked_rows",
                "coverage",
                "/replacement_invariants/rows_with_contract_marker",
                346,
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
                346,
            ),
            _metric(
                "role_rows_with_any_role",
                "coverage",
                "/role_counts/rows_with_any_role",
                124,
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
                48,
            ),
            _metric(
                "role_rows_with_owner",
                "coverage",
                "/role_counts/with_core_role/owner",
                47,
            ),
            _metric(
                "role_rows_with_source_role_tags",
                "coverage",
                "/role_counts/rows_with_source_role_tags",
                85,
            ),
            _metric(
                "role_rows_with_tenants",
                "coverage",
                "/role_counts/with_core_role/tenants",
                6,
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
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 466),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
            _metric("total_master_rows", "coverage", "/row_counts/total", 109_258),
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
        "coverage-audit-public-open-v23": [
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 675),
            _metric(
                "non_review_source_scoped_rows",
                "manifest",
                "/counts/non_review_source_scoped_entity_records",
                9_958,
            ),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 3_435),
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
                16_088,
            ),
            _metric(
                "unique_physical_sites",
                "manifest",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
        "federation-public-open-v24": [
            _metric(
                "capacity_observations", "index", "/counts/capacity_estimates", 1_268
            ),
            _metric(
                "construction_pipeline_records",
                "index",
                "/counts/construction_pipeline_records",
                6_596,
            ),
            _metric(
                "non_review_construction_pipeline_records",
                "index",
                "/counts/non_review_construction_pipeline_records",
                466,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "index",
                "/counts/non_review_source_scoped_entity_records",
                9_958,
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
                16_088,
            ),
            _metric(
                "unique_physical_sites", "index", "/counts/unique_physical_sites", None
            ),
        ],
        "seed-epoch-official-v55": [
            _metric("capacity_observations", "manifest", "/capacity_estimates", 482),
            _metric(
                "construction_pipeline_records",
                "manifest",
                "/construction_pipeline_records",
                346,
            ),
            _metric(
                "construction_source_signals",
                "manifest",
                "/construction_source_signals",
                252,
            ),
            _metric("evidence_records", "manifest", "/evidence_records", 383),
            _metric("resolution_candidates", "manifest", "/resolution_candidates", 4),
            _metric("source_scoped_entity_rows", "manifest", "/entities", 663),
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
        raise CurrentCoverageV18Error("v18 replacement specification changed")
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in ARTIFACT_REPLACEMENTS.items():
        entry = deepcopy(dict(base_entries[old_id]))
        entry["artifact_id"] = new_id
        entry["checkpoints"] = checkpoints[new_id]
        entry["limitations"] = sorted(limitations[new_id])
        entry["metrics"] = metrics[new_id]
        result[new_id] = entry
    return result


def _exact_identity_entry() -> dict[str, Any]:
    return _entry_spec(
        artifact_id="exact-identity-decisions-public-open-v2",
        artifact_kind="cross_release_resolution",
        checkpoints=[
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-20-public-open-v2/accounting.json",
                980,
                "e01dc4f0381d3ff4449fe8d5acbce6bb85584f2e164bdcf660efa96da19e0e6e",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-20-public-open-v2.json",
                1_734,
                "65ffef9681c982b2149591706542c6b8277eedc22de63b2ffd2253ec94332a03",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-20-public-open-v2/manifest.json",
                11_274,
                "43724ed405b77ae64505a05a708e514bbdcf9c13044c3255908563eddb5e7d5c",
            ),
        ],
        limitations=[
            "Canonical topology links preserve explicit facility-contains-building and project-targets relationships and are non-additive; they are not unique physical-site counts.",
            "Exact same-kind source-record components collapse repeat occurrences only within their source-scoped keys and authorize neither cross-kind nor cross-source identity union.",
            "Review-only fuzzy references remain excluded from exact-component accounting; unresolved and ambiguous candidate references remain review work, while physical-site bounds and unique physical sites stay null.",
        ],
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
                2_315,
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
                8_226,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "accounting",
                "/non_review_source_scoped_entity_records",
                9_958,
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
            _metric("raw_topology_links", "accounting", "/raw_topology_links", 2_720),
            _metric(
                "release_candidate_references",
                "accounting",
                "/release_candidate_references",
                100_409,
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
                16_088,
            ),
            _metric(
                "unique_physical_sites", "accounting", "/unique_physical_sites", None
            ),
            _metric(
                "unresolved_candidate_references",
                "accounting",
                "/unresolved_candidate_references",
                100_536,
            ),
        ],
        record_units=["crosswalk_link"],
        current_role="authoritative_public_core",
        evidence_scope="source_scoped",
        publication_mode="public_index_or_audit",
    )


def _satellite_review_entry() -> dict[str, Any]:
    return _entry_spec(
        artifact_id="satellite-change-review-open-seed-v55-active-review-v1",
        artifact_kind="analyst_imagery_review",
        checkpoints=[
            _checkpoint(
                "definition",
                "definitions/satellite_change_reviews/"
                "2026-07-20-open-seed-v55-active-review-v1.json",
                18_540,
                "5dbe5e35da8af84a84e62717355c0d5b3c0cc228a2206f6dedb20b41eab83cc3",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v55-active-review-v1/manifest.json",
                18_667,
                "19e025f4435c413ce9d9af1176bd54996ab474fab216277a7b5a5165980a170a",
            ),
            _checkpoint(
                "source_run_manifest",
                "satellite_change_runs/2026-07-20-open-seed-v55-active-001/"
                "batch-manifest.json",
                41_744,
                "99e58d7bcc09ca850c9add4bfc15635b9808d11eabce8c3782a35a4256ec3a8a",
                binding=("manifest", "/source_change_run/manifest"),
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v55-active-review-v1/summary.json",
                8_533,
                "631e16ca6ca6ee5b57dd0d1fd20b0cef492093a7394d05022d48e87a64edea7a",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        limitations=[
            "Five analyst decisions and thirty hash-bound source artifacts are review records, not construction, identity, lifecycle, status, type, capacity, power, energy, PUE, workload, area, or unique-site evidence.",
            "Three outputs are retained only for site-aligned visible-change follow-up and two are rejected for site promotion; neither disposition negates separately sourced facts.",
            "Two failed AOIs require future multi-tile mosaics and remain metadata-only technical blockers rather than analyst decisions.",
        ],
        metrics=[
            _metric("atlas_mutation", "summary", "/scope/atlas_mutation", False),
            _metric(
                "capacity_claim_created",
                "summary",
                "/scope/capacity_claim_created",
                False,
            ),
            _metric(
                "manual_review_completed",
                "summary",
                "/scope/manual_review_completed",
                True,
            ),
            _metric("review_decisions", "summary", "/counts/decisions", 5),
            _metric(
                "site_count_claim_created",
                "summary",
                "/scope/site_count_claim_created",
                False,
            ),
            _metric(
                "site_promotion_rejections",
                "summary",
                "/counts/reject_for_site_promotion",
                2,
            ),
            _metric(
                "site_aligned_follow_up_retained",
                "summary",
                "/counts/retain_for_site_aligned_visible_change_follow_up",
                3,
            ),
            _metric(
                "source_artifacts_hash_bound",
                "summary",
                "/counts/source_artifacts_hash_bound",
                30,
            ),
            _metric(
                "technical_multitile_failures",
                "summary",
                "/counts/technical_multitile_failures",
                2,
            ),
            _metric(
                "unique_site_claim_created",
                "summary",
                "/scope/unique_site_claim_created",
                False,
            ),
        ],
        record_units=["aggregate_report_metric", "review_record"],
        current_role="public_supporting_review_lane",
        evidence_scope="review_only",
        publication_mode="public_review_or_discovery",
    )


def _addition_entries() -> dict[str, dict[str, Any]]:
    entries = [_exact_identity_entry(), _satellite_review_entry()]
    return {entry["artifact_id"]: entry for entry in entries}


def _load_v17_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_path = package_root / V17_BASE_LINEAGE["definition"]["path"]
    bundle_path = package_root / _BASE_BUNDLE_TREE["path"]
    try:
        _v17.validate_current_coverage_ledger_v17(
            bundle_path, definition_path=definition_path
        )
    except _v17.CurrentCoverageV17Error as error:
        raise CurrentCoverageV18Error(
            f"accepted v17 base failed offline validation: {error}"
        ) from error
    definition_raw, definition = _pinned_json(
        package_root, V17_BASE_LINEAGE["definition"], "v18 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V17_BASE_LINEAGE["ledger"], "v18 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V17_BASE_LINEAGE["manifest"], "v18 base manifest"
    )
    if (
        definition.get("ledger_id") != V17_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V17_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V17_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V17_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V17_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V17_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV18Error("accepted v17 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v18 base bundle")
    return definition, ledger, manifest


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV18Error(f"{label} timestamp is invalid") from error


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v18 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV18Error(f"v18 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v18 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v18 {label}")
    try:
        _identity.validate_exact_identity_decision_bundle(
            package_root / _ACCEPTED_TREES["exact-identity-decisions-v2"]["path"],
            definition_path=(
                package_root
                / "sources/exact-identity-decisions-2026-07-20-public-open-v2.json"
            ),
            verify_inputs=False,
            require_frozen=True,
        )
    except _identity.ExactIdentityDecisionError as error:
        raise CurrentCoverageV18Error(
            f"accepted exact-identity v2 failed validation: {error}"
        ) from error
    try:
        _review_v2.validate_satellite_change_review_v2(
            package_root / _ACCEPTED_TREES["satellite-change-review-v2"]["path"],
            definition_path=(
                package_root / "definitions/satellite_change_reviews/"
                "2026-07-20-open-seed-v55-active-review-v1.json"
            ),
        )
    except _review_v2.SatelliteChangeReviewV2Error as error:
        raise CurrentCoverageV18Error(
            f"accepted satellite review v2 failed validation: {error}"
        ) from error
    generated_at = _parse_timestamp(V18_GENERATED_AT, "v18")
    for label, (relative, field, expected) in sorted(_SOURCE_TIMESTAMPS.items()):
        document = _json_object(
            _read_regular(package_root / relative, f"v18 {label} timestamp source"),
            f"v18 {label} timestamp source",
        )
        if document.get(field) != expected:
            raise CurrentCoverageV18Error(f"v18 {label} timestamp changed")
        if _parse_timestamp(expected, f"v18 {label}") > generated_at:
            raise CurrentCoverageV18Error(f"v18 predates {label}")


def _v18_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV18Error("v17 parity gaps are invalid")
    additions_by_gap = {
        "global-construction-coverage-partial": {
            "satellite-change-review-open-seed-v55-active-review-v1"
        },
        "satellite-review-backlog": {
            "satellite-change-review-open-seed-v55-active-review-v1"
        },
        "site-resolution-partial": {"exact-identity-decisions-public-open-v2"},
    }
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV18Error("v17 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        affected = {
            ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        }
        affected.update(additions_by_gap.get(gap["gap_id"], set()))
        gap["affected_artifact_ids"] = sorted(affected)
        result.append(gap)
    return result


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _require_digest(actual: str, expected: str, label: str) -> None:
    if expected and actual != expected:
        raise CurrentCoverageV18Error(f"v18 {label} digest changed")


def make_v18_definition(package_root: str | Path) -> bytes:
    """Create canonical v18 definition bytes from the pinned v17 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v17_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if len(base_entries) != 45 or not REMOVED_ARTIFACT_IDS <= set(base_entries):
        raise CurrentCoverageV18Error("v17 replacement source inventory changed")
    if set(base_entries) & NEW_ARTIFACT_IDS:
        raise CurrentCoverageV18Error("v17 unexpectedly contains a v18 artifact ID")
    replacements = _replacement_entries(base_entries)
    additions = _addition_entries()
    if set(additions) != ADDED_ARTIFACT_IDS:
        raise CurrentCoverageV18Error("v18 addition inventory changed")
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    base_entries.update(additions)
    if len(base_entries) != 47:
        raise CurrentCoverageV18Error("v18 definition must contain 47 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] not in NEW_ARTIFACT_IDS
    ]
    replacement_entries = [
        entry for entry in ordered if entry["artifact_id"] in REPLACEMENT_ARTIFACT_IDS
    ]
    addition_entries = [
        entry for entry in ordered if entry["artifact_id"] in ADDED_ARTIFACT_IDS
    ]
    if not (
        len(unchanged) == 40
        and len(replacement_entries) == 5
        and len(addition_entries) == 2
    ):
        raise CurrentCoverageV18Error("v18 delta arithmetic changed")
    parity_gaps = _v18_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_40_SHA256, "inherited entries"
    )
    _require_digest(
        _component_digest(replacement_entries),
        REPLACEMENT_5_SHA256,
        "replacement entries",
    )
    _require_digest(
        _component_digest(addition_entries), ADDITION_2_SHA256, "addition entries"
    )
    _require_digest(_component_digest(ordered), ALL_ENTRIES_SHA256, "all entries")
    _require_digest(
        _sha256(_canonical_line(parity_gaps)), PARITY_GAPS_SHA256, "parity gaps"
    )
    document = {
        "base_ledger": V17_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V18_GENERATED_AT,
        "ledger_id": V18_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    forbidden = (
        "paix",
        "pentapoint",
        "open-seed-2026-07-20-v56",
        "seed-epoch-official-v56",
        "construction-map-public-open-v22",
        "construction-master-public-open-v22",
        "coverage-audit-public-open-v22",
        "federation-public-open-v23",
        "seed-epoch-official-v49",
    )
    rendered = raw.decode("utf-8").lower()
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV18Error("v18 definition contains rejected lineage")
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V18_DEFINITION_PATH:
        raise CurrentCoverageV18Error("v18 definition publication path changed")
    raw = _read_regular(path, "v18 definition")
    document = _json_object(raw, "v18 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV18Error("v18 definition is not canonical JSON")
    if not V18_DEFINITION_SHA256 or _sha256(raw) != V18_DEFINITION_SHA256:
        raise CurrentCoverageV18Error("v18 definition content changed or is unpinned")
    if raw != make_v18_definition(package_root):
        raise CurrentCoverageV18Error(
            "v18 definition differs from pinned transformation"
        )
    if (
        document.get("ledger_id") != V18_LEDGER_ID
        or document.get("generated_at") != V18_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V17_BASE_LINEAGE
    ):
        raise CurrentCoverageV18Error("v18 identity, base, schema, or scope changed")
    if _parse_timestamp(V18_GENERATED_AT, "v18") > datetime.now(UTC):
        raise CurrentCoverageV18Error("v18 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 47:
        raise CurrentCoverageV18Error("v18 must contain exactly 47 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 47 or None in artifact_ids:
        raise CurrentCoverageV18Error("v18 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not NEW_ARTIFACT_IDS <= artifact_ids:
        raise CurrentCoverageV18Error("v18 delta inventory is invalid")
    return document, raw, package_root


def _expected_inventory_counts(base_ledger: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base_ledger["artifact_inventory_counts"]))
    result["artifacts"] += 2
    result["by_access_tier"]["public_open"] += 2
    result["by_evidence_scope"]["source_scoped"] += 1
    result["by_evidence_scope"]["review_only"] += 1
    result["by_publication_mode"]["public_index_or_audit"] += 1
    result["by_publication_mode"]["public_review_or_discovery"] += 1
    result["by_record_unit"]["crosswalk_link"] += 1
    result["by_record_unit"]["aggregate_report_metric"] += 1
    result["by_record_unit"]["review_record"] += 1
    result["by_redistribution_status"]["eligible_with_upstream_terms"] += 2
    result["public_open_review_only_artifacts"] += 1
    return result


def build_current_coverage_ledger_v18(
    definition_path: str | Path,
) -> CurrentCoverageV18Bundle:
    """Reproduce the v18 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, base_ledger, _base_manifest = _load_v17_base(package_root)
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
        raise CurrentCoverageV18Error(str(error)) from error
    inventory_counts = _v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != _expected_inventory_counts(base_ledger):
        raise CurrentCoverageV18Error("v18 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V17_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V18_GENERATED_AT,
        "ledger_id": V18_LEDGER_ID,
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
        "base_ledger": V17_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V18_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V18_GENERATED_AT,
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
        "ledger_id": V18_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    return CurrentCoverageV18Bundle(
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CurrentCoverageV18Error(f"refusing active output lock: {lock}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _cleanup_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v17._cleanup_file_stage(stage, identity)
    except _v17.CurrentCoverageV17Error as error:
        raise CurrentCoverageV18Error(str(error).replace("v17", "v18")) from error


def _cleanup_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v17._cleanup_bundle_stage(stage, identity)
    except _v17.CurrentCoverageV17Error as error:
        raise CurrentCoverageV18Error(str(error).replace("v17", "v18")) from error


def _promote_noreplace(stage: Path, destination: Path) -> None:
    try:
        _v17._promote_noreplace(stage, destination)
    except _v17.CurrentCoverageV17Error as error:
        raise CurrentCoverageV18Error(str(error).replace("v17", "v18")) from error


def write_v18_definition(package_root: str | Path, output_path: str | Path) -> str:
    """Atomically create, but never replace, the canonical v18 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v18_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV18Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _v17._v16._path_identity(stage)
            stage.chmod(0o644)
            _v17._v16._fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _v17._v16._fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV18Error(
                    "v18 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v18 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v18(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v18 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV18Error("v18 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v18(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV18Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _v17._v16._path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _v17._v16._fsync_regular(stage / filename)
            stage.chmod(0o555)
            _v17._v16._fsync_directory(stage)
            validate_current_coverage_ledger_v18(stage, definition_path=definition_path)
            _promote_noreplace(stage, destination)
            _v17._v16._fsync_directory(destination.parent)
            validate_current_coverage_ledger_v18(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v18 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v18(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = _lexical_absolute(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV18Error("v18 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV18Error("v18 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV18Error("v18 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v18 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v18 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v18 sidecar")
    ledger = _json_object(actual_ledger, "v18 ledger")
    manifest = _json_object(actual_manifest, "v18 manifest")
    if actual_ledger != _canonical_json(ledger):
        raise CurrentCoverageV18Error("v18 ledger is not canonical JSON")
    if actual_manifest != _canonical_json(manifest):
        raise CurrentCoverageV18Error("v18 manifest is not canonical JSON")
    if actual_sidecar != (
        f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CurrentCoverageV18Error("v18 manifest sidecar differs")
    expected = build_current_coverage_ledger_v18(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV18Error("v18 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV18Error("v18 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV18Error("v18 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_ARTIFACT_IDS",
    "ADDITION_2_SHA256",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV18Bundle",
    "CurrentCoverageV18Error",
    "NEW_ARTIFACT_IDS",
    "PARITY_GAPS_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_5_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "UNCHANGED_40_SHA256",
    "V17_BASE_LINEAGE",
    "V18_BUNDLE_PATH",
    "V18_DEFINITION_PATH",
    "V18_DEFINITION_SHA256",
    "V18_GENERATED_AT",
    "V18_LEDGER_ID",
    "build_current_coverage_ledger_v18",
    "make_v18_definition",
    "validate_current_coverage_ledger_v18",
    "write_current_coverage_ledger_v18",
    "write_v18_definition",
]
