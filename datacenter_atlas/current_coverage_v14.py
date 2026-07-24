"""Collision-isolated current-coverage ledger v14.

V14 is a strict successor to the frozen v13 ledger.  It updates the accepted
public core to construction master/map v17, official seed v44, federation v20,
and coverage audit v19.  It also records the historical seed-v43 satellite
queue, its catalog batch, and the offline v2 catalog reselection as explicitly
review-only, non-additive provenance.

The implementation deliberately lives outside ``current_coverage.py`` so the
accepted historical carriers and bundles remain byte-stable.
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
import shutil
import stat
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from . import current_coverage as _legacy


V14_LEDGER_ID = "current-coverage-2026-07-20-v14"
V14_GENERATED_AT = "2026-07-20T08:45:00Z"
V14_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v14.json"
V14_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v14"
V14_DEFINITION_SHA256 = (
    "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V13_BASE_LINEAGE = {
    "definition": {
        "bytes": 120_537,
        "path": "sources/current-coverage-2026-07-20-v13.json",
        "sha256": "7e23abc7be3c6a3e898c640960912a308297bf02aee22b86638a66b350d19cc5",
    },
    "ledger": {
        "bytes": 82_603,
        "path": (
            "current_coverage_ledgers/2026-07-20-v13/"
            "current-coverage-ledger.json"
        ),
        "sha256": "aabbc77b6fad657794b44e8eda6c833bccc694d863602ab8c7efaf79da49e0b7",
    },
    "ledger_id": "current-coverage-2026-07-20-v13",
    "manifest": {
        "bytes": 22_727,
        "path": "current_coverage_ledgers/2026-07-20-v13/manifest.json",
        "sha256": "3ab86c29de2d7a6054a0ec3c941644a639ef89cba7fdf27614ff9ea170f9f034",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v16": "construction-map-public-open-v17",
    "construction-master-public-open-v16": "construction-master-public-open-v17",
    "coverage-audit-public-open-v17": "coverage-audit-public-open-v19",
    "federation-public-open-v18": "federation-public-open-v20",
    "seed-epoch-official-v42": "seed-epoch-official-v44",
}
ADDED_SATELLITE_IDS = frozenset(
    {
        "satellite-catalog-open-seed-v43-active-001",
        "satellite-catalog-reselection-open-seed-v43-active-v2-001",
        "satellite-queue-open-seed-v43",
    }
)
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_SATELLITE_IDS

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v13",
    "sha256": "4baa5dce8714135637b81882e382f60754223bcbf09781a53c3ee9437ed4dc17",
}

# A tree hash contains every relative path, type, permission mode, byte count,
# and file digest.  These pins close each accepted input tree rather than merely
# trusting its manifest filename.
_ACCEPTED_TREES = {
    "construction-map-v17": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v17",
        "sha256": "915af875e9da3888cc0c2fc4dbd528990f253333904a5f302c9f112ceb6efbcc",
    },
    "construction-master-v17": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v17",
        "sha256": "341379b3353f24da035f106798a8eac9718c0f7d82bc757e24a92e9cc6f84c5e",
    },
    "coverage-audit-v19": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v19",
        "sha256": "9e4a3196e2bcaa791bb576cc1aa4c1ab2a1e844b3d16255972b6763b1e679364",
    },
    "federation-v20": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v20",
        "sha256": "c0a60e5c762aeae98e201482ab8e92f0c49a9d1cc361042ed7c064bd74b10dcb",
    },
    "official-seed-v44": {
        "directories": 1,
        "files": 13,
        "path": "releases/2026-07-20-open-seed-v44",
        "sha256": "8c42f28d6aef9c973f1dc37b995cbf3776e8bef11c7f1af0bdc5eeece37fbc35",
    },
    "satellite-catalog-reselection-v2": {
        "directories": 6,
        "files": 11,
        "path": (
            "satellite_catalog_reselection_runs/"
            "2026-07-20-open-seed-v43-active-v2-001"
        ),
        "sha256": "b9577bb392fcc0bb4726dbf3ed7347fab2017d2ec08a85e4e11b5d8a55b66ad5",
    },
    "satellite-catalog-v43": {
        "directories": 15,
        "files": 19,
        "path": "satellite_review_runs/2026-07-20-open-seed-v43-active-001",
        "sha256": "339cb9c97c9c86ba92abfef8c4eab60bb77423f5cefde4aba44dba5be06fcbae",
    },
    "satellite-queue-v43": {
        "directories": 1,
        "files": 3,
        "path": "satellite_review_queues/2026-07-20-open-seed-v43",
        "sha256": "948ce24401bdd20577aaae59cb108241db49519c856f961df3f683f1d3a79505",
    },
}

_PINNED_FILES = {
    "construction-map definition": (
        "sources/construction-map-2026-07-20-public-open-v17.json",
        2_440,
        "1e0c00892932e5e1077acbc018a98785f0b85b1b565d9adc6fe3126c62d3c806",
    ),
    "construction-map manifest": (
        "construction_maps/2026-07-20-public-open-v17/manifest.json",
        2_192,
        "5e57250b6765838ee9ae4e250b92a11e65b077307a2156c047c636752fe3e3c4",
    ),
    "construction-master definition": (
        "sources/construction-master-2026-07-20-public-open-v17.json",
        5_657,
        "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19",
    ),
    "construction-master manifest": (
        "construction_master/2026-07-20-public-open-v17/manifest.json",
        9_668,
        "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9",
    ),
    "coverage-audit definition": (
        "sources/coverage-audit-2026-07-20-public-open-v19.json",
        3_871,
        "c420307ec4b2e2188d023b5421194f9fe10eabeae4d24a5e0d16e19b5f0e5f76",
    ),
    "coverage-audit manifest": (
        "audits/2026-07-20-public-open-coverage-v19/manifest.json",
        2_240,
        "179c54831370c92cf5e58dec1e759190e896d554fb2d4929559c40c665be3db4",
    ),
    "federation definition": (
        "sources/federation-2026-07-20-public-open-v20.json",
        1_788,
        "5bd47924d1c19c30b77b1f76198a6924a461ff9d1a8e622a4216996335afe53d",
    ),
    "federation manifest": (
        "federated_indexes/2026-07-20-public-open-v20/manifest.json",
        986,
        "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78",
    ),
    "official-seed definition": (
        "sources/open-seed-2026-07-20-v44.json",
        56_914,
        "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312",
    ),
    "official-seed manifest": (
        "releases/2026-07-20-open-seed-v44/manifest.json",
        7_672,
        "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9",
    ),
}

_EXPECTED_INVENTORY_COUNTS = {
    "artifacts": 44,
    "by_access_tier": {"local_restricted": 6, "public_open": 38},
    "by_evidence_scope": {
        "metadata_only": 5,
        "mixed_source_scoped_and_review": 6,
        "review_only": 29,
        "source_scoped": 4,
    },
    "by_publication_mode": {
        "local_quarantined": 6,
        "public_index_or_audit": 4,
        "public_metadata_or_aggregate_only": 5,
        "public_review_or_discovery": 24,
        "public_row_release": 5,
    },
    "by_record_unit": {
        "advertised_source_record": 3,
        "aggregate_report_metric": 3,
        "air_permit_application_record": 1,
        "building_footprint_record": 3,
        "building_record": 2,
        "campus_project_record": 1,
        "candidate_record": 6,
        "capacity_observation": 5,
        "catalog_job": 8,
        "catalog_link": 6,
        "construction_master_row": 2,
        "construction_pipeline_record": 3,
        "coverage_gap": 2,
        "crosswalk_link": 3,
        "facility_record": 1,
        "issued_air_permit_record": 1,
        "parcel_record": 1,
        "planning_application_record": 5,
        "planning_observation_record": 5,
        "project_record": 3,
        "review_record": 14,
        "source_scoped_entity_row": 6,
    },
    "by_redistribution_status": {
        "eligible_with_upstream_terms": 33,
        "metadata_only_no_source_rows": 5,
        "quarantined_pending_rights": 6,
    },
    "parity_gaps_by_status": {
        "not_computed": 1,
        "partial_coverage": 3,
        "review_backlog": 1,
        "rights_blocked": 1,
    },
    "public_open_review_only_artifacts": 25,
}


class CurrentCoverageV14Error(_legacy.CurrentCoverageError):
    """Raised when the v14 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True, slots=True)
class CurrentCoverageV14Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV14Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV14Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV14Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path,
    spec: Mapping[str, Any],
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    if set(spec) != {"bytes", "path", "sha256"}:
        raise CurrentCoverageV14Error(f"{label} checkpoint schema changed")
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV14Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV14Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV14Error(f"{label} is not canonical JSON")
    return raw, document


def _tree_digest(root: Path, label: str) -> tuple[int, int, str]:
    if root.is_symlink() or not root.is_dir():
        raise CurrentCoverageV14Error(f"{label} must be a regular directory")
    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CurrentCoverageV14Error(f"{label} contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise CurrentCoverageV14Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
            directory_count += 1
        elif path.is_file():
            if mode != 0o444:
                raise CurrentCoverageV14Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode("utf-8")
            )
            file_count += 1
        else:
            raise CurrentCoverageV14Error(
                f"{label} contains unsupported entry: {relative}"
            )
    return file_count, directory_count, digest.hexdigest()


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV14Error(f"{label} tree escapes package root") from error
    files, directories, digest = _tree_digest(path, label)
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV14Error(f"{label} closed tree changed")


def _load_v13_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_raw, definition = _pinned_json(
        package_root, V13_BASE_LINEAGE["definition"], "v14 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V13_BASE_LINEAGE["ledger"], "v14 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V13_BASE_LINEAGE["manifest"], "v14 base manifest"
    )
    if (
        definition.get("ledger_id") != V13_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V13_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V13_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V13_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V13_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V13_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV14Error("accepted v13 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v14 base bundle")
    return definition, ledger, manifest


def _checkpoint(
    checkpoint_id: str,
    path: str,
    size: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bytes": size,
        "checkpoint_id": checkpoint_id,
        "path": path,
        "sha256": sha256,
    }
    if binding is not None:
        result["binding"] = {
            "checkpoint_id": binding[0],
            "json_pointer": binding[1],
        }
    return result


def _metric(
    label: str,
    checkpoint_id: str,
    json_pointer: str,
    value: Any,
    *,
    operation: str | None = None,
) -> dict[str, Any]:
    result = {
        "checkpoint_id": checkpoint_id,
        "json_pointer": json_pointer,
        "label": label,
        "value": value,
    }
    if operation is not None:
        result["operation"] = operation
    return result


def _entry_spec(
    *,
    artifact_id: str,
    artifact_kind: str,
    checkpoints: Sequence[dict[str, Any]],
    limitations: Sequence[str],
    metrics: Sequence[dict[str, Any]],
    record_units: Sequence[str],
    current_role: str = "authoritative_public_core",
    evidence_scope: str = "mixed_source_scoped_and_review",
    publication_mode: str = "public_row_release",
) -> dict[str, Any]:
    return {
        "access_tier": "public_open",
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "checkpoints": sorted(checkpoints, key=lambda row: row["checkpoint_id"]),
        "current_role": current_role,
        "evidence_scope": evidence_scope,
        "limitations": sorted(set(limitations)),
        "metrics": sorted(metrics, key=lambda row: row["label"]),
        "publication_mode": publication_mode,
        "record_units": sorted(set(record_units)),
        "redistribution_status": "eligible_with_upstream_terms",
    }


def _replacement_entries() -> dict[str, dict[str, Any]]:
    entries = [
        _entry_spec(
            artifact_id="construction-map-public-open-v17",
            artifact_kind="construction_map",
            checkpoints=[
                _checkpoint(
                    "coverage",
                    "construction_maps/2026-07-20-public-open-v17/coverage.json",
                    7_389,
                    "ff6552d63d31944497c9c669938cc5e973b5d26a14b19aff691ecd142de92a1a",
                    binding=("manifest", "/outputs/coverage.json"),
                ),
                _checkpoint(
                    "definition",
                    "sources/construction-map-2026-07-20-public-open-v17.json",
                    2_440,
                    "1e0c00892932e5e1077acbc018a98785f0b85b1b565d9adc6fe3126c62d3c806",
                ),
                _checkpoint(
                    "manifest",
                    "construction_maps/2026-07-20-public-open-v17/manifest.json",
                    2_192,
                    "5e57250b6765838ee9ae4e250b92a11e65b077307a2156c047c636752fe3e3c4",
                ),
            ],
            limitations=[
                "Map rows are a presentation derivative of construction-master v17 and must never be added to the master-row total.",
                "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
                "Two hundred thirty-six master observations lack coordinates, including 218 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
            ],
            metrics=[
                _metric("added_replacement_rows_unmapped", "coverage", "/projection/added_replacement_rows_unmapped", 97),
                _metric("default_visible_rows", "definition", "/expected_projection/default_visible_rows", 6_481),
                _metric("mapped_replacement_rows", "coverage", "/counts/mapped_replacement_rows", 82),
                _metric("mapped_rows_with_any_role", "coverage", "/counts/mapped_rows_with_any_role", 66),
                _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 201),
                _metric("mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280),
                _metric("mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494),
                _metric("mapped_total_rows", "coverage", "/counts/mapped_observation_rows", 108_975),
                _metric("mapped_unknown_country_rows", "coverage", "/mapped_counts/by_country/Unknown", 102_541),
                _metric("master_total_rows", "coverage", "/counts/master_observation_rows", 109_211),
                _metric("unique_physical_sites", "coverage", "/counts/unique_physical_site_count", None),
                _metric("unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 236),
            ],
            record_units=["construction_master_row"],
        ),
        _entry_spec(
            artifact_id="construction-master-public-open-v17",
            artifact_kind="construction_master",
            checkpoints=[
                _checkpoint(
                    "coverage",
                    "construction_master/2026-07-20-public-open-v17/coverage.json",
                    8_497,
                    "c1fbd7753e401bf7aa4c7a33b4ba1021c090afc076319b1263fd024c20617b49",
                    binding=("manifest", "/outputs/coverage.json"),
                ),
                _checkpoint(
                    "definition",
                    "sources/construction-master-2026-07-20-public-open-v17.json",
                    5_657,
                    "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19",
                    binding=("manifest", "/definition"),
                ),
                _checkpoint(
                    "manifest",
                    "construction_master/2026-07-20-public-open-v17/manifest.json",
                    9_668,
                    "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9",
                ),
            ],
            limitations=[
                "Historical lifecycle statuses are source-scoped observations and do not establish current construction after reported_status_date.",
                "Only 419 Tier-A source-supported observation rows enter construction arithmetic; the 109,211 total includes review and structural-discovery rows and is not a unique-site count.",
                "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
                "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
            ],
            metrics=[
                _metric("added_replacement_rows", "coverage", "/replacement_invariants/added_replacement_rows", 100),
                _metric("base_rows", "coverage", "/replacement_invariants/base_rows", 109_111),
                _metric("contract_marked_rows", "coverage", "/replacement_invariants/rows_with_contract_marker", 299),
                _metric("inherited_rows", "coverage", "/replacement_invariants/inherited_rows", 108_912),
                _metric("publication_contract_version", "coverage", "/replacement/publication_contract_version", 4),
                _metric("replacement_rows", "coverage", "/replacement_invariants/replacement_rows", 299),
                _metric("role_rows_with_any_role", "coverage", "/role_counts/rows_with_any_role", 102),
                _metric("role_rows_with_customers", "coverage", "/role_counts/with_core_role/customers", 1),
                _metric("role_rows_with_operator", "coverage", "/role_counts/with_core_role/operator", 35),
                _metric("role_rows_with_owner", "coverage", "/role_counts/with_core_role/owner", 47),
                _metric("role_rows_with_source_role_tags", "coverage", "/role_counts/rows_with_source_role_tags", 63),
                _metric("role_rows_with_tenants", "coverage", "/role_counts/with_core_role/tenants", 4),
                _metric("role_rows_with_users", "coverage", "/role_counts/with_core_role/users", 36),
                _metric("satellite_recovery_control_plane_bytes", "coverage", "/satellite_recovery_acceptance/control_plane_bytes", 15_313),
                _metric("satellite_recovery_control_plane_files", "coverage", "/satellite_recovery_acceptance/control_plane_files", 4),
                _metric("satellite_recovery_rows", "coverage", "/satellite_recovery_acceptance/rows_created", 0),
                _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 419),
                _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
                _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
                _metric("total_master_rows", "coverage", "/row_counts/total", 109_211),
                _metric("unchanged_replacement_rows", "coverage", "/replacement_invariants/unchanged_replacement_rows", 199),
                _metric("unique_physical_sites", "coverage", "/row_counts/unique_physical_site_count", None),
            ],
            record_units=["construction_master_row"],
        ),
        _entry_spec(
            artifact_id="coverage-audit-public-open-v19",
            artifact_kind="coverage_audit",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "audits/2026-07-20-public-open-coverage-v19/manifest.json",
                    2_240,
                    "179c54831370c92cf5e58dec1e759190e896d554fb2d4929559c40c665be3db4",
                )
            ],
            limitations=[
                "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
                "The 594 source and source-country groups and 3,123 open gaps are coverage-accounting units, not site counts.",
            ],
            metrics=[
                _metric("coverage_groups", "manifest", "/counts/coverage_groups", 594),
                _metric("non_review_source_scoped_rows", "manifest", "/counts/non_review_source_scoped_entity_records", 9_868),
                _metric("open_gaps", "manifest", "/counts/open_gaps", 3_123),
                _metric("review_only_source_scoped_rows", "manifest", "/counts/review_only_source_scoped_entity_records", 6_130),
                _metric("source_scoped_rows", "manifest", "/counts/source_scoped_entity_records", 15_998),
                _metric("unique_physical_sites", "manifest", "/counts/unique_physical_sites", None),
            ],
            record_units=["coverage_gap"],
            publication_mode="public_index_or_audit",
        ),
        _entry_spec(
            artifact_id="federation-public-open-v20",
            artifact_kind="federated_release_index",
            checkpoints=[
                _checkpoint(
                    "index",
                    "federated_indexes/2026-07-20-public-open-v20/federated-index.json",
                    22_362,
                    "8dfcbb82ac3ad8964ab6fb220da19b3fbe6720c3a65b0c34da624ca6829d53f4",
                    binding=("manifest", "/artifacts/federated-index.json"),
                ),
                _checkpoint(
                    "manifest",
                    "federated_indexes/2026-07-20-public-open-v20/manifest.json",
                    986,
                    "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78",
                ),
            ],
            limitations=[
                "The 15,998 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
                "The 6,549 construction-pipeline records include 6,130 review-only fuzzy rows and only 419 non-review observations; they are not all confirmed construction sites.",
            ],
            metrics=[
                _metric("capacity_observations", "index", "/counts/capacity_estimates", 1_235),
                _metric("construction_pipeline_records", "index", "/counts/construction_pipeline_records", 6_549),
                _metric("non_review_construction_pipeline_records", "index", "/counts/non_review_construction_pipeline_records", 419),
                _metric("non_review_source_scoped_rows", "index", "/counts/non_review_source_scoped_entity_records", 9_868),
                _metric("review_only_construction_pipeline_records", "index", "/counts/review_only_construction_pipeline_records", 6_130),
                _metric("review_only_source_scoped_rows", "index", "/counts/review_only_source_scoped_entity_records", 6_130),
                _metric("source_scoped_rows", "index", "/counts/source_scoped_entity_records", 15_998),
                _metric("unique_physical_sites", "index", "/counts/unique_physical_sites", None),
            ],
            record_units=["source_scoped_entity_row"],
            publication_mode="public_index_or_audit",
        ),
        _entry_spec(
            artifact_id="seed-epoch-official-v44",
            artifact_kind="source_scoped_release",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "releases/2026-07-20-open-seed-v44/manifest.json",
                    7_672,
                    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9",
                )
            ],
            limitations=[
                "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; absent fields are not inferred from satellite imagery.",
                "The 573 source-scoped entity rows comprise 312 campus observations and 261 project observations, not deduplicated physical sites.",
            ],
            metrics=[
                _metric("capacity_observations", "manifest", "/capacity_estimates", 449),
                _metric("construction_pipeline_records", "manifest", "/construction_pipeline_records", 299),
                _metric("construction_source_signals", "manifest", "/construction_source_signals", 221),
                _metric("evidence_records", "manifest", "/evidence_records", 327),
                _metric("resolution_candidates", "manifest", "/resolution_candidates", 4),
                _metric("source_scoped_entity_rows", "manifest", "/entities", 573),
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


def _satellite_entries() -> dict[str, dict[str, Any]]:
    review_arguments = {
        "current_role": "public_supporting_review_lane",
        "evidence_scope": "review_only",
        "publication_mode": "public_review_or_discovery",
    }
    entries = [
        _entry_spec(
            artifact_id="satellite-catalog-open-seed-v43-active-001",
            artifact_kind="satellite_catalog_batch",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "satellite_review_runs/2026-07-20-open-seed-v43-active-001/batch-manifest.json",
                    45_271,
                    "ac658626db624f87fdc77eb0e713985959656246d255b0b8eded2c13907d5d21",
                )
            ],
            limitations=[
                "Catalog availability is not visible-change, identity, lifecycle, operating-status, type, capacity, power, energy, or PUE evidence.",
                "This incomplete historical seed-v43 catalog batch is retained only as the source input to reselection v2; its counts are not additive to the v43 queue or current construction coverage.",
            ],
            metrics=[
                _metric("jobs_completed", "manifest", "/summary/jobs_completed", 6),
                _metric("jobs_failed", "manifest", "/summary/jobs_failed", 0),
                _metric("jobs_pending", "manifest", "/summary/jobs_pending", 70),
                _metric("jobs_selected", "manifest", "/summary/jobs_selected", 77),
                _metric("jobs_unavailable_no_scene", "manifest", "/summary/jobs_unavailable_no_scene", 1),
            ],
            record_units=["catalog_job", "catalog_link"],
            **review_arguments,
        ),
        _entry_spec(
            artifact_id="satellite-catalog-reselection-open-seed-v43-active-v2-001",
            artifact_kind="satellite_catalog_batch",
            checkpoints=[
                _checkpoint(
                    "grid_headers",
                    "satellite_catalog_reselection_runs/2026-07-20-open-seed-v43-active-v2-001/grid-headers.json",
                    17_713,
                    "9cc8e87c2b64b9262777a8973f05d2a7096525b3d933166ee21cc2ff5a5938f1",
                    binding=("manifest", "/grid_header_evidence"),
                ),
                _checkpoint(
                    "manifest",
                    "satellite_catalog_reselection_runs/2026-07-20-open-seed-v43-active-v2-001/batch-manifest.json",
                    8_247,
                    "5caba8afe58c21ae0e494fc8532fb5e25f0b9c26cc68dcc1b763732264ac6ec7",
                ),
                _checkpoint(
                    "queue_manifest",
                    "satellite_review_queues/2026-07-20-open-seed-v43/manifest.json",
                    10_891,
                    "ca0d03f03749f30001533c79b15e31af841f392cb60eb23c7319d7c7ffce7d97",
                    binding=("manifest", "/queue_bundle/manifest"),
                ),
                _checkpoint(
                    "source_catalog_manifest",
                    "satellite_review_runs/2026-07-20-open-seed-v43-active-001/batch-manifest.json",
                    45_271,
                    "ac658626db624f87fdc77eb0e713985959656246d255b0b8eded2c13907d5d21",
                    binding=("manifest", "/source_catalog_batch/manifest"),
                ),
                _checkpoint(
                    "unresolved",
                    "satellite_catalog_reselection_runs/2026-07-20-open-seed-v43-active-v2-001/unresolved-multitile-needed.json",
                    1_371,
                    "9139599fa4e4bb1d155debcdca24df3b40cdec7e0e071221a797f1e7be623bcd",
                    binding=("manifest", "/unresolved_assessment"),
                ),
            ],
            limitations=[
                "The offline v2 reselection covers exactly two explicit historical seed-v43 queue IDs and emits zero atlas rows; it is not a current construction census.",
                "The selected scene pairs establish catalog and grid compatibility only, not visible change, identity, lifecycle, operator, type, workload, capacity, power, energy, or PUE.",
                "The reselection is a non-additive successor view over its pinned v43 queue and catalog inputs; do not add its job counts to either input.",
            ],
            metrics=[
                _metric("atlas_rows_emitted", "manifest", "/summary/atlas_rows_emitted", 0),
                _metric("candidate_jobs_assessed", "manifest", "/summary/candidate_jobs_assessed", 2),
                _metric("change_jobs_executed", "manifest", "/summary/change_jobs_executed", 0),
                _metric("jobs_reselected", "manifest", "/summary/jobs_reselected", 2),
                _metric("jobs_unresolved_multitile_needed", "manifest", "/summary/jobs_unresolved_multitile_needed", 0),
                _metric("raw_provider_response_files_copied", "manifest", "/summary/raw_provider_response_files_copied", 4),
                _metric("source_catalog_manifest_files_copied", "manifest", "/summary/source_catalog_manifest_files_copied", 2),
                _metric("unique_aois_reselected", "manifest", "/summary/unique_aois_reselected", 2),
            ],
            record_units=["catalog_job", "catalog_link"],
            **review_arguments,
        ),
        _entry_spec(
            artifact_id="satellite-queue-open-seed-v43",
            artifact_kind="satellite_review_queue",
            checkpoints=[
                _checkpoint(
                    "manifest",
                    "satellite_review_queues/2026-07-20-open-seed-v43/manifest.json",
                    10_891,
                    "ca0d03f03749f30001533c79b15e31af841f392cb60eb23c7319d7c7ffce7d97",
                ),
                _checkpoint(
                    "release_manifest",
                    "releases/2026-07-20-open-seed-v43/manifest.json",
                    7_056,
                    "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537",
                    binding=("manifest", "/source/release_manifest"),
                ),
            ],
            limitations=[
                "Queue jobs are imagery-review plans for historical seed-v43 entities, not deduplicated sites, imagery findings, or current construction evidence.",
                "This queue is retained to bind the catalog-reselection lineage and is not additive to the newer seed-v44 queue or the broader global-open-v3 queue.",
            ],
            metrics=[
                _metric("entities_queued", "manifest", "/counts/entities_queued", 141),
                _metric("queue_jobs", "manifest", "/counts/queue_jobs", 141),
            ],
            record_units=["catalog_job"],
            **review_arguments,
        ),
    ]
    return {entry["artifact_id"]: entry for entry in entries}


def _new_entries() -> dict[str, dict[str, Any]]:
    result = _replacement_entries()
    result.update(_satellite_entries())
    return result


def _v14_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV14Error("v13 parity gaps are invalid")
    result: list[dict[str, Any]] = []
    satellite_gap_ids = {
        "global-construction-coverage-partial",
        "satellite-review-backlog",
    }
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV14Error("v13 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        affected = {
            ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        }
        if gap["gap_id"] in satellite_gap_ids:
            affected.update(ADDED_SATELLITE_IDS)
        gap["affected_artifact_ids"] = sorted(affected)
        result.append(gap)
    return result


def make_v14_definition(package_root: str | Path) -> bytes:
    """Create canonical v14 definition bytes from the pinned v13 baseline."""

    root = Path(package_root).resolve()
    base_definition, _base_ledger, _base_manifest = _load_v13_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if set(base_entries) & ADDED_SATELLITE_IDS:
        raise CurrentCoverageV14Error("v13 unexpectedly contains v14 satellite IDs")
    for artifact_id in REMOVED_ARTIFACT_IDS:
        if artifact_id not in base_entries:
            raise CurrentCoverageV14Error(f"v13 missing replacement source: {artifact_id}")
        del base_entries[artifact_id]
    base_entries.update(_new_entries())
    if len(base_entries) != 44:
        raise CurrentCoverageV14Error("v14 definition must contain exactly 44 entries")
    document = {
        "base_ledger": V13_BASE_LINEAGE,
        "entries": [base_entries[key] for key in sorted(base_entries)],
        "generated_at": V14_GENERATED_AT,
        "ledger_id": V14_LEDGER_ID,
        "parity_gaps": _v14_parity_gaps(base_definition["parity_gaps"]),
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    return _canonical_json(document)


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v14 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV14Error(f"v14 {label} changed")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v14 {label}")


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    expected_path = package_root / V14_DEFINITION_PATH
    if path != expected_path:
        raise CurrentCoverageV14Error("v14 definition publication path changed")
    raw = _read_regular(path, "v14 definition")
    document = _json_object(raw, "v14 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV14Error("v14 definition is not canonical JSON")
    if _sha256(raw) != V14_DEFINITION_SHA256:
        raise CurrentCoverageV14Error("v14 definition content changed")
    if set(document) != {
        "base_ledger",
        "entries",
        "generated_at",
        "ledger_id",
        "parity_gaps",
        "schema_version",
        "scope",
    }:
        raise CurrentCoverageV14Error("v14 definition keys changed")
    if (
        document.get("ledger_id") != V14_LEDGER_ID
        or document.get("generated_at") != V14_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V13_BASE_LINEAGE
    ):
        raise CurrentCoverageV14Error("v14 identity, base, schema, or scope changed")
    try:
        generated_at = datetime.fromisoformat(V14_GENERATED_AT.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV14Error("v14 generated_at is invalid") from error
    if generated_at > datetime.now(UTC):
        raise CurrentCoverageV14Error("v14 generated_at is in the future")

    base_definition, _base_ledger, _base_manifest = _load_v13_base(package_root)
    expected_raw = make_v14_definition(package_root)
    if raw != expected_raw:
        raise CurrentCoverageV14Error("v14 definition differs from pinned transformation")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 44:
        raise CurrentCoverageV14Error("v14 must contain exactly 44 entries")
    entry_map = {entry.get("artifact_id"): entry for entry in entries}
    if len(entry_map) != 44 or None in entry_map:
        raise CurrentCoverageV14Error("v14 entry inventory is invalid")
    base_map = {entry["artifact_id"]: entry for entry in base_definition["entries"]}
    inherited = set(base_map) - REMOVED_ARTIFACT_IDS
    if set(entry_map) != inherited | NEW_ARTIFACT_IDS:
        raise CurrentCoverageV14Error("v14 contains missing, extra, or stale entries")
    for artifact_id in sorted(inherited):
        if entry_map[artifact_id] != base_map[artifact_id]:
            raise CurrentCoverageV14Error(f"v14 inherited entry changed: {artifact_id}")
    for artifact_id, expected in sorted(_new_entries().items()):
        if entry_map[artifact_id] != expected:
            raise CurrentCoverageV14Error(f"v14 new entry changed: {artifact_id}")
    if document["parity_gaps"] != _v14_parity_gaps(base_definition["parity_gaps"]):
        raise CurrentCoverageV14Error("v14 parity gaps changed")
    _validate_accepted_inputs(package_root)
    return document, raw, package_root


def _inventory_counts(
    artifacts: Sequence[Mapping[str, Any]],
    parity_gaps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "artifacts": len(artifacts),
        "by_access_tier": {
            tier: sum(row["access_tier"] == tier for row in artifacts)
            for tier in sorted(_legacy.ACCESS_TIERS)
        },
        "by_evidence_scope": {
            scope: sum(row["evidence_scope"] == scope for row in artifacts)
            for scope in sorted(_legacy.EVIDENCE_SCOPES)
        },
        "public_open_review_only_artifacts": sum(
            row["access_tier"] == "public_open" and row["review_only"]
            for row in artifacts
        ),
        "by_publication_mode": {
            mode: sum(row["publication_mode"] == mode for row in artifacts)
            for mode in sorted(_legacy.PUBLICATION_MODES)
        },
        "by_record_unit": {
            unit: sum(unit in row["record_units"] for row in artifacts)
            for unit in sorted(_legacy.RECORD_UNITS)
        },
        "by_redistribution_status": {
            status_value: sum(
                row["redistribution_status"] == status_value for row in artifacts
            )
            for status_value in sorted(_legacy.REDISTRIBUTION_STATUSES)
        },
        "parity_gaps_by_status": {
            status_value: sum(
                gap["status"] == status_value for gap in parity_gaps
            )
            for status_value in sorted(_legacy.PARITY_GAP_STATUSES)
        },
    }
    return counts


def build_current_coverage_ledger_v14(
    definition_path: str | Path,
) -> CurrentCoverageV14Bundle:
    """Reproduce the v14 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
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
        raise CurrentCoverageV14Error(str(error)) from error
    inventory_counts = _inventory_counts(artifacts, parity_gaps)
    if inventory_counts != _EXPECTED_INVENTORY_COUNTS:
        raise CurrentCoverageV14Error("v14 artifact inventory arithmetic changed")

    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V13_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V14_GENERATED_AT,
        "ledger_id": V14_LEDGER_ID,
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
        "base_ledger": V13_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V14_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V14_GENERATED_AT,
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
        "ledger_id": V14_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV14Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


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
        raise CurrentCoverageV14Error(f"refusing active output lock: {lock}") from error
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


def write_v14_definition(
    package_root: str | Path,
    output_path: str | Path,
) -> str:
    """Atomically create, but never replace, the canonical v14 definition."""

    destination = Path(output_path).resolve()
    raw = make_v14_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV14Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise CurrentCoverageV14Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        finally:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass
    return _sha256(raw)


def write_current_coverage_ledger_v14(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v14 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV14Error("v14 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v14(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV14Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            if destination.exists() or destination.is_symlink():
                raise CurrentCoverageV14Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    if freeze:
        for filename in BUNDLE_FILES:
            (destination / filename).chmod(0o444)
        destination.chmod(0o555)
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v14(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV14Error("v14 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise CurrentCoverageV14Error("v14 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise CurrentCoverageV14Error("v14 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v14 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v14 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v14 sidecar")
    _json_object(actual_ledger, "v14 ledger")
    _json_object(actual_manifest, "v14 manifest")
    expected_sidecar = f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if actual_sidecar != expected_sidecar:
        raise CurrentCoverageV14Error("v14 manifest sidecar differs")
    expected = build_current_coverage_ledger_v14(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV14Error("v14 ledger differs from offline reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV14Error("v14 manifest differs from offline reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV14Error("v14 sidecar differs from offline reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_SATELLITE_IDS",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV14Bundle",
    "CurrentCoverageV14Error",
    "NEW_ARTIFACT_IDS",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_ARTIFACT_IDS",
    "V13_BASE_LINEAGE",
    "V14_BUNDLE_PATH",
    "V14_DEFINITION_PATH",
    "V14_DEFINITION_SHA256",
    "V14_GENERATED_AT",
    "V14_LEDGER_ID",
    "build_current_coverage_ledger_v14",
    "make_v14_definition",
    "validate_current_coverage_ledger_v14",
    "write_current_coverage_ledger_v14",
    "write_v14_definition",
]
