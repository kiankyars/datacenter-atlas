"""Collision-isolated current-coverage ledger v16.

V16 is derived only from the accepted frozen v14 ledger.  It advances the
public core to official seed v47, federation v22, coverage audit v21, and
construction master/map v21.  It also adds the manually adjudicated v43
reselected change review as a review-only control artifact.  The review creates
no identity, lifecycle, type, capacity, power, energy, PUE, workload, area, or
unique-site claim and does not negate separately sourced construction facts.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import ctypes
from dataclasses import dataclass
from datetime import UTC, datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from . import current_coverage as _legacy
from . import current_coverage_v14 as _v14


V16_LEDGER_ID = "current-coverage-2026-07-20-v16"
V16_GENERATED_AT = "2026-07-20T16:20:00Z"
V16_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v16.json"
V16_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v16"
V16_DEFINITION_SHA256 = (
    "df337239c05f02ebd40847c22a214230ada51730f35444b6b13b8fc2e6e05137"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V14_BASE_LINEAGE = {
    "definition": {
        "bytes": 129_254,
        "path": "sources/current-coverage-2026-07-20-v14.json",
        "sha256": "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0",
    },
    "ledger": {
        "bytes": 89_210,
        "path": (
            "current_coverage_ledgers/2026-07-20-v14/"
            "current-coverage-ledger.json"
        ),
        "sha256": "ede89a5b75ca30dae4c96f3ae876e02abf53eff00497a8edc85fc9fcde69b2bd",
    },
    "ledger_id": "current-coverage-2026-07-20-v14",
    "manifest": {
        "bytes": 24_814,
        "path": "current_coverage_ledgers/2026-07-20-v14/manifest.json",
        "sha256": "5f318e610653a4579fb9d995133fd3ea388de5c7a2a3b66c2e250fced69d150c",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v17": "construction-map-public-open-v21",
    "construction-master-public-open-v17": "construction-master-public-open-v21",
    "coverage-audit-public-open-v19": "coverage-audit-public-open-v21",
    "federation-public-open-v20": "federation-public-open-v22",
    "seed-epoch-official-v44": "seed-epoch-official-v47",
}
ADDED_ARTIFACT_IDS = frozenset(
    {"satellite-change-review-open-seed-v43-active-reselected-v2-review-v1"}
)
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS

UNCHANGED_39_SHA256 = "be8fe4f0c7ba0c32530f3bb9017b7fda9f73d2c752bfec2ec5fd6846a2198a3b"
NEW_ENTRIES_SHA256 = "73aa2a63133056761ad8d837fbf56eaf5b774c6ec2a8f6207a0beefb184e620a"
ALL_ENTRIES_SHA256 = "415718d8798c5239ed1fd4fbe10bc348f16d01dca69e74765608c4ca62b408f3"
PARITY_GAPS_SHA256 = "58e3f193b7d4e1a03db30b010ac037107cf1ceaeda007078edcebf36519a62e9"

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v14",
    "sha256": "f59daffd971b54d9a462cc620d6d812dd1650b194675d6bcafa6d8559282ba50",
}

_ACCEPTED_TREES = {
    "coverage-audit-v21": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v21",
        "sha256": "7005f8ccf58d1ac204c81ae368fdc04a06da98c270711f7182afa1cddb8efcba",
    },
    "construction-map-v21": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v21",
        "sha256": "3640ec8f3cffb481a1781db16a91aec6b84d60974d1da3fdbdf044b724698497",
    },
    "construction-master-v21": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v21",
        "sha256": "17f033a2a8c14e6b1cbc20d8d3ca7913fe2748ae3658bef27aacc117626292b4",
    },
    "federation-v22": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v22",
        "sha256": "fa873f928e0163388d526d4499600b8bbfee8aaa247827c987e14d48be52967c",
    },
    "official-seed-v47": {
        "directories": 1,
        "files": 13,
        "path": "releases/2026-07-20-open-seed-v47",
        "sha256": "dc0bdcaa1905781ab5dd2642e4c44f86f80adf3ec340d09209ba6aee77e36a7e",
    },
    "satellite-change-review-v1": {
        "directories": 1,
        "files": 6,
        "path": (
            "satellite_change_reviews/"
            "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
        ),
        "sha256": "58c6d32e77f9956eeca39cee51261474cd0c812a802aafe570f35d9e33674843",
    },
    "satellite-change-run-v2": {
        "directories": 6,
        "files": 13,
        "path": (
            "satellite_change_runs/"
            "2026-07-20-open-seed-v43-active-reselected-v2-001"
        ),
        "sha256": "ce8d252c12a68d9908a0ef636843cf2acdcb5ee1a717c6d9a8f53b4670aa88d2",
    },
}

_PINNED_FILES = {
    "v14 implementation": (
        "datacenter_atlas/current_coverage_v14.py",
        52_478,
        "8ad89d1aa0e6dc4071f95d18134a01b4ef2685a51a27c8de697244bd6a9863d9",
    ),
    "v14 definition": (
        V14_BASE_LINEAGE["definition"]["path"],
        V14_BASE_LINEAGE["definition"]["bytes"],
        V14_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v14 ledger": (
        V14_BASE_LINEAGE["ledger"]["path"],
        V14_BASE_LINEAGE["ledger"]["bytes"],
        V14_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v14 manifest": (
        V14_BASE_LINEAGE["manifest"]["path"],
        V14_BASE_LINEAGE["manifest"]["bytes"],
        V14_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v14 sidecar": (
        "current_coverage_ledgers/2026-07-20-v14/manifest.sha256",
        80,
        "a9ad99f6a82b749ec69ef9f38a1b2f1c010848b0e7db33b878c232b64d4ce536",
    ),
    "official seed v47 definition": (
        "sources/open-seed-2026-07-20-v47.json",
        59_727,
        "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2",
    ),
    "official seed v47 manifest": (
        "releases/2026-07-20-open-seed-v47/manifest.json",
        8_024,
        "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1",
    ),
    "federation v22 definition": (
        "sources/federation-2026-07-20-public-open-v22.json",
        1_788,
        "87f8cf1b662431bcd3436ff89eaa8398b26d6cf42adfb1fdb9273d7fd06c37f6",
    ),
    "federation v22 index": (
        "federated_indexes/2026-07-20-public-open-v22/federated-index.json",
        22_981,
        "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c",
    ),
    "federation v22 manifest": (
        "federated_indexes/2026-07-20-public-open-v22/manifest.json",
        986,
        "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94",
    ),
    "coverage audit v21 definition": (
        "sources/coverage-audit-2026-07-20-public-open-v21.json",
        3_871,
        "f26fa3dda1ed3447941154635d252d68b6355f826a17a6a4c4efaa887257cd02",
    ),
    "coverage audit v21 manifest": (
        "audits/2026-07-20-public-open-coverage-v21/manifest.json",
        2_240,
        "b40981593dab96613f7a35dd5e4e07aeb7c4f7e4727f41802bec6b8af0f88393",
    ),
    "construction master v21 definition": (
        "sources/construction-master-2026-07-20-public-open-v21.json",
        5_657,
        "ca6258e96d72407d8aa24b94e3ac52c7c1f4d6b0c52e722b0f6d36bd2c16843a",
    ),
    "construction master v21 coverage": (
        "construction_master/2026-07-20-public-open-v21/coverage.json",
        8_523,
        "cc6288cd72eb2463a4f3bcf141eebbdfd7e56bad9c46334b5cefc54d0cae8013",
    ),
    "construction master v21 manifest": (
        "construction_master/2026-07-20-public-open-v21/manifest.json",
        9_694,
        "9af4215174275908f69f2f04302992be940277350e03924a1dda7fb089bab4f9",
    ),
    "construction map v21 definition": (
        "sources/construction-map-2026-07-20-public-open-v21.json",
        2_441,
        "72e99c9a1734375e02ed8a4e31a975cfaaa1c9518267466d514b39ba83df78b5",
    ),
    "construction map v21 coverage": (
        "construction_maps/2026-07-20-public-open-v21/coverage.json",
        7_390,
        "2543e3237acdd44b6c736ffc5142cdd8b2e345abe2e89f62d1d04db5f2f6566e",
    ),
    "construction map v21 manifest": (
        "construction_maps/2026-07-20-public-open-v21/manifest.json",
        2_192,
        "a2110233083bfef5271225e77a75d2132eedb9d848ee59671c20d26eabd26ba4",
    ),
    "satellite change review definition": (
        "definitions/satellite_change_reviews/"
        "2026-07-20-open-seed-v43-active-reselected-v2-review-v1.json",
        7_568,
        "7c84666520844b0e308f3d0fddb8223217648efe02c08ef134c19eb31a16a161",
    ),
    "satellite change review manifest": (
        "satellite_change_reviews/"
        "2026-07-20-open-seed-v43-active-reselected-v2-review-v1/manifest.json",
        13_297,
        "e06b780e6fc2ee85e969374ec97eb167a536953c5e8e9d9b5bb3feff14ab7623",
    ),
    "satellite change review summary": (
        "satellite_change_reviews/"
        "2026-07-20-open-seed-v43-active-reselected-v2-review-v1/summary.json",
        2_953,
        "d650dba66decbc80b4b4b57cc00b44a360f1d1b81cd2aa6f4936f09f74af6c04",
    ),
    "satellite change run manifest": (
        "satellite_change_runs/"
        "2026-07-20-open-seed-v43-active-reselected-v2-001/batch-manifest.json",
        23_729,
        "cfafe8788fa2f7bf4321947f01b1b95a7454569c73e286009a296adc93515112",
    ),
}


class CurrentCoverageV16Error(_legacy.CurrentCoverageError):
    """Raised when the v16 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True, slots=True)
class CurrentCoverageV16Bundle:
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
        raise CurrentCoverageV16Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV16Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV16Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV16Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV16Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV16Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v14._tree_digest(path, label)
    except (ValueError, _v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV16Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV16Error(f"{label} closed tree changed")


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v14._checkpoint(
        checkpoint_id, path, byte_count, sha256, binding=binding
    )


def _metric(
    label: str, checkpoint_id: str, pointer: str, value: Any
) -> dict[str, Any]:
    return _v14._metric(label, checkpoint_id, pointer, value)


def _entry_spec(**kwargs: Any) -> dict[str, Any]:
    return _v14._entry_spec(**kwargs)


def _replacement_entries() -> dict[str, dict[str, Any]]:
    entries = [
        _entry_spec(
            artifact_id="construction-map-public-open-v21",
            artifact_kind="construction_map",
            checkpoints=[
                _checkpoint(
                    "coverage",
                    "construction_maps/2026-07-20-public-open-v21/coverage.json",
                    7_390,
                    "2543e3237acdd44b6c736ffc5142cdd8b2e345abe2e89f62d1d04db5f2f6566e",
                    binding=("manifest", "/outputs/coverage.json"),
                ),
                _checkpoint(
                    "definition",
                    "sources/construction-map-2026-07-20-public-open-v21.json",
                    2_441,
                    "72e99c9a1734375e02ed8a4e31a975cfaaa1c9518267466d514b39ba83df78b5",
                ),
                _checkpoint(
                    "manifest",
                    "construction_maps/2026-07-20-public-open-v21/manifest.json",
                    2_192,
                    "a2110233083bfef5271225e77a75d2132eedb9d848ee59671c20d26eabd26ba4",
                ),
            ],
            limitations=[
                "Map rows are a presentation derivative of construction-master v21 and must never be added to the master-row total.",
                "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
                "Two hundred fifty master observations lack coordinates, including 232 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
            ],
            metrics=[
                _metric("added_replacement_rows_unmapped", "coverage", "/projection/added_replacement_rows_unmapped", 111),
                _metric("default_visible_rows", "definition", "/expected_projection/default_visible_rows", 6_481),
                _metric("mapped_replacement_rows", "coverage", "/counts/mapped_replacement_rows", 82),
                _metric("mapped_rows_with_any_role", "coverage", "/counts/mapped_rows_with_any_role", 66),
                _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 201),
                _metric("mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280),
                _metric("mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494),
                _metric("mapped_total_rows", "coverage", "/counts/mapped_observation_rows", 108_975),
                _metric("mapped_unknown_country_rows", "coverage", "/mapped_counts/by_country/Unknown", 102_541),
                _metric("master_total_rows", "coverage", "/counts/master_observation_rows", 109_225),
                _metric("unique_physical_sites", "coverage", "/counts/unique_physical_site_count", None),
                _metric("unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 250),
            ],
            record_units=["construction_master_row"],
        ),
        _entry_spec(
            artifact_id="construction-master-public-open-v21",
            artifact_kind="construction_master",
            checkpoints=[
                _checkpoint(
                    "coverage",
                    "construction_master/2026-07-20-public-open-v21/coverage.json",
                    8_523,
                    "cc6288cd72eb2463a4f3bcf141eebbdfd7e56bad9c46334b5cefc54d0cae8013",
                    binding=("manifest", "/outputs/coverage.json"),
                ),
                _checkpoint(
                    "definition",
                    "sources/construction-master-2026-07-20-public-open-v21.json",
                    5_657,
                    "ca6258e96d72407d8aa24b94e3ac52c7c1f4d6b0c52e722b0f6d36bd2c16843a",
                    binding=("manifest", "/definition"),
                ),
                _checkpoint(
                    "manifest",
                    "construction_master/2026-07-20-public-open-v21/manifest.json",
                    9_694,
                    "9af4215174275908f69f2f04302992be940277350e03924a1dda7fb089bab4f9",
                ),
            ],
            limitations=[
                "Historical lifecycle statuses are source-scoped observations and do not establish current construction after reported_status_date.",
                "Only 433 Tier-A source-supported observation rows enter construction arithmetic; the 109,225 total includes review and structural-discovery rows and is not a unique-site count.",
                "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
                "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
            ],
            metrics=[
                _metric("added_replacement_rows", "coverage", "/replacement_invariants/added_replacement_rows", 114),
                _metric("base_rows", "coverage", "/replacement_invariants/base_rows", 109_111),
                _metric("contract_marked_rows", "coverage", "/replacement_invariants/rows_with_contract_marker", 313),
                _metric("inherited_rows", "coverage", "/replacement_invariants/inherited_rows", 108_912),
                _metric("publication_contract_version", "coverage", "/replacement/publication_contract_version", 4),
                _metric("replacement_rows", "coverage", "/replacement_invariants/replacement_rows", 313),
                _metric("role_rows_with_any_role", "coverage", "/role_counts/rows_with_any_role", 108),
                _metric("role_rows_with_customers", "coverage", "/role_counts/with_core_role/customers", 1),
                _metric("role_rows_with_operator", "coverage", "/role_counts/with_core_role/operator", 40),
                _metric("role_rows_with_owner", "coverage", "/role_counts/with_core_role/owner", 47),
                _metric("role_rows_with_source_role_tags", "coverage", "/role_counts/rows_with_source_role_tags", 69),
                _metric("role_rows_with_tenants", "coverage", "/role_counts/with_core_role/tenants", 5),
                _metric("role_rows_with_users", "coverage", "/role_counts/with_core_role/users", 36),
                _metric("satellite_recovery_control_plane_bytes", "coverage", "/satellite_recovery_acceptance/control_plane_bytes", 15_313),
                _metric("satellite_recovery_control_plane_files", "coverage", "/satellite_recovery_acceptance/control_plane_files", 4),
                _metric("satellite_recovery_rows", "coverage", "/satellite_recovery_acceptance/rows_created", 0),
                _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 433),
                _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
                _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
                _metric("total_master_rows", "coverage", "/row_counts/total", 109_225),
                _metric("unchanged_replacement_rows", "coverage", "/replacement_invariants/unchanged_replacement_rows", 199),
                _metric("unique_physical_sites", "coverage", "/row_counts/unique_physical_site_count", None),
            ],
            record_units=["construction_master_row"],
        ),
        _entry_spec(
            artifact_id="coverage-audit-public-open-v21",
            artifact_kind="coverage_audit",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "audits/2026-07-20-public-open-coverage-v21/manifest.json",
                    2_240,
                    "b40981593dab96613f7a35dd5e4e07aeb7c4f7e4727f41802bec6b8af0f88393",
                )
            ],
            limitations=[
                "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
                "The 613 source and source-country groups and 3,193 open gaps are coverage-accounting units, not site counts.",
            ],
            metrics=[
                _metric("coverage_groups", "manifest", "/counts/coverage_groups", 613),
                _metric("non_review_source_scoped_rows", "manifest", "/counts/non_review_source_scoped_entity_records", 9_896),
                _metric("open_gaps", "manifest", "/counts/open_gaps", 3_193),
                _metric("review_only_source_scoped_rows", "manifest", "/counts/review_only_source_scoped_entity_records", 6_130),
                _metric("source_scoped_rows", "manifest", "/counts/source_scoped_entity_records", 16_026),
                _metric("unique_physical_sites", "manifest", "/counts/unique_physical_sites", None),
            ],
            record_units=["coverage_gap"],
            publication_mode="public_index_or_audit",
        ),
        _entry_spec(
            artifact_id="federation-public-open-v22",
            artifact_kind="federated_release_index",
            checkpoints=[
                _checkpoint(
                    "index",
                    "federated_indexes/2026-07-20-public-open-v22/federated-index.json",
                    22_981,
                    "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c",
                    binding=("manifest", "/artifacts/federated-index.json"),
                ),
                _checkpoint(
                    "manifest",
                    "federated_indexes/2026-07-20-public-open-v22/manifest.json",
                    986,
                    "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94",
                ),
            ],
            limitations=[
                "The 16,026 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
                "The 6,563 construction-pipeline records include 6,130 review-only fuzzy rows and only 433 non-review observations; they are not all confirmed construction sites.",
            ],
            metrics=[
                _metric("capacity_observations", "index", "/counts/capacity_estimates", 1_240),
                _metric("construction_pipeline_records", "index", "/counts/construction_pipeline_records", 6_563),
                _metric("non_review_construction_pipeline_records", "index", "/counts/non_review_construction_pipeline_records", 433),
                _metric("non_review_source_scoped_rows", "index", "/counts/non_review_source_scoped_entity_records", 9_896),
                _metric("review_only_construction_pipeline_records", "index", "/counts/review_only_construction_pipeline_records", 6_130),
                _metric("review_only_source_scoped_rows", "index", "/counts/review_only_source_scoped_entity_records", 6_130),
                _metric("source_scoped_rows", "index", "/counts/source_scoped_entity_records", 16_026),
                _metric("unique_physical_sites", "index", "/counts/unique_physical_sites", None),
            ],
            record_units=["source_scoped_entity_row"],
            publication_mode="public_index_or_audit",
        ),
        _entry_spec(
            artifact_id="seed-epoch-official-v47",
            artifact_kind="source_scoped_release",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "releases/2026-07-20-open-seed-v47/manifest.json",
                    8_024,
                    "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1",
                )
            ],
            limitations=[
                "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; absent fields are not inferred from satellite imagery.",
                "The 601 source-scoped entity rows comprise 326 campus observations and 275 project observations, not deduplicated physical sites.",
            ],
            metrics=[
                _metric("capacity_observations", "manifest", "/capacity_estimates", 454),
                _metric("construction_pipeline_records", "manifest", "/construction_pipeline_records", 313),
                _metric("construction_source_signals", "manifest", "/construction_source_signals", 228),
                _metric("evidence_records", "manifest", "/evidence_records", 337),
                _metric("resolution_candidates", "manifest", "/resolution_candidates", 4),
                _metric("source_scoped_entity_rows", "manifest", "/entities", 601),
            ],
            record_units=[
                "capacity_observation",
                "construction_pipeline_record",
                "source_scoped_entity_row",
            ],
            evidence_scope="source_scoped",
        ),
    ]
    return {entry["artifact_id"]: entry for entry in entries}


def _satellite_change_review_entry() -> dict[str, Any]:
    return _entry_spec(
        artifact_id=(
            "satellite-change-review-open-seed-v43-active-reselected-v2-review-v1"
        ),
        artifact_kind="analyst_imagery_review",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v43-active-reselected-v2-review-v1/"
                "manifest.json",
                13_297,
                "e06b780e6fc2ee85e969374ec97eb167a536953c5e8e9d9b5bb3feff14ab7623",
            ),
            _checkpoint(
                "source_run_manifest",
                "satellite_change_runs/"
                "2026-07-20-open-seed-v43-active-reselected-v2-001/"
                "batch-manifest.json",
                23_729,
                "cfafe8788fa2f7bf4321947f01b1b95a7454569c73e286009a296adc93515112",
                binding=("manifest", "/source_change_run/manifest"),
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-20-open-seed-v43-active-reselected-v2-review-v1/"
                "summary.json",
                2_953,
                "d650dba66decbc80b4b4b57cc00b44a360f1d1b81cd2aa6f4936f09f74af6c04",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        limitations=[
            "Both decisions reject imagery-only site promotion; they do not negate separately sourced construction facts.",
            "The change-mask areas are algorithm-derived metadata, not construction areas; no atlas mutation or automated promotion is allowed.",
            "The two selected analyst decisions and twelve hash-bound image or report artifacts are review records, not construction, identity, status, type, capacity, power, energy, PUE, workload, or unique-site evidence.",
        ],
        metrics=[
            _metric("atlas_mutation", "summary", "/scope/atlas_mutation", False),
            _metric("manual_review_completed", "summary", "/scope/manual_review_completed", True),
            _metric("review_decisions", "summary", "/counts/decisions", 2),
            _metric("site_promotion_rejections", "summary", "/counts/reject_for_site_promotion", 2),
            _metric("source_artifacts_hash_bound", "summary", "/counts/source_artifacts_hash_bound", 12),
            _metric("unique_site_claim_created", "summary", "/scope/unique_site_claim_created", False),
        ],
        record_units=["aggregate_report_metric", "review_record"],
        current_role="public_supporting_review_lane",
        evidence_scope="review_only",
        publication_mode="public_review_or_discovery",
    )


def _load_v14_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_raw, definition = _pinned_json(
        package_root, V14_BASE_LINEAGE["definition"], "v16 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V14_BASE_LINEAGE["ledger"], "v16 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V14_BASE_LINEAGE["manifest"], "v16 base manifest"
    )
    if (
        definition.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V14_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V14_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V14_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV16Error("accepted v14 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v16 base bundle")
    return definition, ledger, manifest


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v16 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV16Error(f"v16 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v16 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v16 {label}")


def _v16_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV16Error("v14 parity gaps are invalid")
    add_review_to = {
        "global-construction-coverage-partial",
        "satellite-review-backlog",
    }
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV16Error("v14 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        affected = {
            ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        }
        if gap["gap_id"] in add_review_to:
            affected.update(ADDED_ARTIFACT_IDS)
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
        raise CurrentCoverageV16Error(f"v16 {label} digest changed")


def make_v16_definition(package_root: str | Path) -> bytes:
    """Create canonical v16 definition bytes from the pinned v14 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v14_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry)
        for entry in base_definition["entries"]
    }
    if set(base_entries) & NEW_ARTIFACT_IDS:
        raise CurrentCoverageV16Error("v14 unexpectedly contains a v16 artifact ID")
    for artifact_id in REMOVED_ARTIFACT_IDS:
        if base_entries.pop(artifact_id, None) is None:
            raise CurrentCoverageV16Error(
                f"v14 missing replacement source: {artifact_id}"
            )
    replacement_entries = _replacement_entries()
    if set(replacement_entries) != REPLACEMENT_ARTIFACT_IDS:
        raise CurrentCoverageV16Error("v16 replacement entry inventory changed")
    base_entries.update(replacement_entries)
    satellite = _satellite_change_review_entry()
    base_entries[satellite["artifact_id"]] = satellite
    if len(base_entries) != 45:
        raise CurrentCoverageV16Error("v16 definition must contain 45 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] not in NEW_ARTIFACT_IDS
    ]
    new_entries = [
        entry for entry in ordered if entry["artifact_id"] in NEW_ARTIFACT_IDS
    ]
    if len(unchanged) != 39 or len(new_entries) != 6:
        raise CurrentCoverageV16Error("v16 delta arithmetic changed")
    parity_gaps = _v16_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_39_SHA256, "inherited entries"
    )
    _require_digest(_component_digest(new_entries), NEW_ENTRIES_SHA256, "new entries")
    _require_digest(_component_digest(ordered), ALL_ENTRIES_SHA256, "all entries")
    _require_digest(
        _sha256(_canonical_line(parity_gaps)), PARITY_GAPS_SHA256, "parity gaps"
    )
    document = {
        "base_ledger": V14_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V16_GENERATED_AT,
        "ledger_id": V16_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    forbidden = (
        "current-coverage-2026-07-20-v15",
        "open-seed-2026-07-20-v46",
        "open-seed-2026-07-20-v48",
        "seed-epoch-official-v46",
        "seed-epoch-official-v48",
    )
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV16Error("v16 definition contains rejected lineage")
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V16_DEFINITION_PATH:
        raise CurrentCoverageV16Error("v16 definition publication path changed")
    raw = _read_regular(path, "v16 definition")
    document = _json_object(raw, "v16 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV16Error("v16 definition is not canonical JSON")
    if not V16_DEFINITION_SHA256 or _sha256(raw) != V16_DEFINITION_SHA256:
        raise CurrentCoverageV16Error("v16 definition content changed or is unpinned")
    if raw != make_v16_definition(package_root):
        raise CurrentCoverageV16Error("v16 definition differs from pinned transformation")
    if (
        document.get("ledger_id") != V16_LEDGER_ID
        or document.get("generated_at") != V16_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V14_BASE_LINEAGE
    ):
        raise CurrentCoverageV16Error("v16 identity, base, schema, or scope changed")
    try:
        generated_at = datetime.fromisoformat(
            V16_GENERATED_AT.replace("Z", "+00:00")
        )
    except ValueError as error:  # pragma: no cover - static constant
        raise CurrentCoverageV16Error("v16 timestamp is invalid") from error
    if generated_at > datetime.now(UTC):
        raise CurrentCoverageV16Error("v16 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 45:
        raise CurrentCoverageV16Error("v16 must contain exactly 45 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 45 or None in artifact_ids:
        raise CurrentCoverageV16Error("v16 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not NEW_ARTIFACT_IDS <= artifact_ids:
        raise CurrentCoverageV16Error("v16 delta inventory is invalid")
    return document, raw, package_root


def _expected_inventory_counts(base_ledger: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base_ledger["artifact_inventory_counts"]))
    result["artifacts"] += 1
    result["by_access_tier"]["public_open"] += 1
    result["by_evidence_scope"]["review_only"] += 1
    result["by_publication_mode"]["public_review_or_discovery"] += 1
    result["by_record_unit"]["aggregate_report_metric"] += 1
    result["by_record_unit"]["review_record"] += 1
    result["by_redistribution_status"]["eligible_with_upstream_terms"] += 1
    result["public_open_review_only_artifacts"] += 1
    return result


def build_current_coverage_ledger_v16(
    definition_path: str | Path,
) -> CurrentCoverageV16Bundle:
    """Reproduce the v16 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, base_ledger, _base_manifest = _load_v14_base(package_root)
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
        raise CurrentCoverageV16Error(str(error)) from error
    inventory_counts = _v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != _expected_inventory_counts(base_ledger):
        raise CurrentCoverageV16Error("v16 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V14_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V16_GENERATED_AT,
        "ledger_id": V16_LEDGER_ID,
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
        "base_ledger": V14_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V16_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V16_GENERATED_AT,
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
        "ledger_id": V16_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV16Bundle(
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
        raise CurrentCoverageV16Error(f"refusing active output lock: {lock}") from error
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


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _cleanup_owned_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode) or (
        metadata.st_dev,
        metadata.st_ino,
    ) != identity:
        raise CurrentCoverageV16Error(
            "refusing cleanup of substituted v16 definition stage"
        )
    stage.unlink()


def _cleanup_owned_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(metadata.st_mode) or (
        metadata.st_dev,
        metadata.st_ino,
    ) != identity:
        raise CurrentCoverageV16Error(
            "refusing cleanup of substituted v16 bundle stage"
        )
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV16Error(
            "refusing cleanup of contaminated v16 bundle stage"
        )
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _promote_noreplace(stage: Path, destination: Path) -> None:
    """Atomically publish one sibling path without replacing a late arrival."""

    if stage.parent != destination.parent:
        raise CurrentCoverageV16Error("v16 stage and destination must be siblings")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise CurrentCoverageV16Error(
                "atomic no-clobber publication is unavailable"
            )
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise CurrentCoverageV16Error(
                "atomic no-clobber publication is unavailable"
            )
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:  # pragma: no cover
        raise CurrentCoverageV16Error(
            "atomic no-clobber publication is unavailable"
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise CurrentCoverageV16Error(
            f"refusing late output collision: {destination}"
        )
    raise CurrentCoverageV16Error(
        f"atomic no-clobber publication failed: {os.strerror(error_number)}"
    )


def write_v16_definition(
    package_root: str | Path, output_path: str | Path
) -> str:
    """Atomically create, but never replace, the canonical v16 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v16_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV16Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _path_identity(stage)
            stage.chmod(0o644)
            _fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV16Error(
                    "v16 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_owned_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v16 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v16(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v16 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV16Error("v16 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v16(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV16Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _fsync_regular(stage / filename)
            stage.chmod(0o555)
            _fsync_directory(stage)
            validate_current_coverage_ledger_v16(
                stage, definition_path=definition_path
            )
            _promote_noreplace(stage, destination)
            _fsync_directory(destination.parent)
            validate_current_coverage_ledger_v16(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_owned_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v16 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v16(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV16Error("v16 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise CurrentCoverageV16Error("v16 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise CurrentCoverageV16Error("v16 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v16 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v16 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v16 sidecar")
    _json_object(actual_ledger, "v16 ledger")
    _json_object(actual_manifest, "v16 manifest")
    expected_sidecar = f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if actual_sidecar != expected_sidecar:
        raise CurrentCoverageV16Error("v16 manifest sidecar differs")
    expected = build_current_coverage_ledger_v16(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV16Error("v16 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV16Error("v16 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV16Error("v16 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV16Bundle",
    "CurrentCoverageV16Error",
    "NEW_ENTRIES_SHA256",
    "NEW_ARTIFACT_IDS",
    "PARITY_GAPS_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_ARTIFACT_IDS",
    "UNCHANGED_39_SHA256",
    "V14_BASE_LINEAGE",
    "V16_BUNDLE_PATH",
    "V16_DEFINITION_PATH",
    "V16_DEFINITION_SHA256",
    "V16_GENERATED_AT",
    "V16_LEDGER_ID",
    "build_current_coverage_ledger_v16",
    "make_v16_definition",
    "validate_current_coverage_ledger_v16",
    "write_current_coverage_ledger_v16",
    "write_v16_definition",
]
