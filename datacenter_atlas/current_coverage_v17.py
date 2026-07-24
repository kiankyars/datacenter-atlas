"""Collision-isolated current-coverage ledger v17.

V17 derives only from the accepted frozen v16 ledger. It replaces exactly the
five public-core entries advanced by the accepted v49 chain and preserves the
other forty entries, including the manually adjudicated satellite-change
review, byte-for-byte at the canonical-entry level.
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
from . import current_coverage_v16 as _v16


V17_LEDGER_ID = "current-coverage-2026-07-20-v17"
V17_GENERATED_AT = "2026-07-20T17:29:30Z"
V17_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v17.json"
V17_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v17"
V17_DEFINITION_SHA256 = (
    "6ddeea2d789d8dbbf09df12fc4739e67d1f5ee04b6a99c98a27366f9a965ad0f"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V16_BASE_LINEAGE = {
    "definition": {
        "bytes": 132_723,
        "path": "sources/current-coverage-2026-07-20-v16.json",
        "sha256": "df337239c05f02ebd40847c22a214230ada51730f35444b6b13b8fc2e6e05137",
    },
    "ledger": {
        "bytes": 91_839,
        "path": (
            "current_coverage_ledgers/2026-07-20-v16/"
            "current-coverage-ledger.json"
        ),
        "sha256": "1e9368fd910653edc116070710e08d49033110c6c448fcc715e9d3fbde603d95",
    },
    "ledger_id": "current-coverage-2026-07-20-v16",
    "manifest": {
        "bytes": 25_659,
        "path": "current_coverage_ledgers/2026-07-20-v16/manifest.json",
        "sha256": "3745f27ef5cf631dccd1ac0c894ea59d1e31751825ad05acf0d2243e9b971dad",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v21": "construction-map-public-open-v22",
    "construction-master-public-open-v21": "construction-master-public-open-v22",
    "coverage-audit-public-open-v21": "coverage-audit-public-open-v22",
    "federation-public-open-v22": "federation-public-open-v23",
    "seed-epoch-official-v47": "seed-epoch-official-v49",
}
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())

UNCHANGED_40_SHA256 = "c534ed692c49ab001fd49c5ec9d861254945dc27d0975bbcb4a024ac8e706044"
REPLACEMENT_5_SHA256 = "691dcad8c11b79a4f7dd58b25f80d75b7647301276103314852ecb9603f58e7b"
ALL_ENTRIES_SHA256 = "8506fe1e8ddde68f5c8b69e5e8e71ae2dcc0844f09f6cfd5aaae92cb5d1406f7"
PARITY_GAPS_SHA256 = "8a14f9fea78febef81083cdee51a6945026e33c91bfd04df7208495722d8c8d5"

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v16",
    "sha256": "d570c1ef8f0e9ce51e5508e99830798067675a7aa232a9fc95668186aeb7be1b",
}

_ACCEPTED_TREES = {
    "coverage-audit-v22": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v22",
        "sha256": "2e13adaa6a9b3758a13473c430f74fd6ab2571c9c5098370e61382cd46f4b190",
    },
    "construction-map-v22": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v22",
        "sha256": "26f4219ff77913d61dde2844cb2f042439e49f8eb5aa1516d45cfe0f4780cfaf",
    },
    "construction-master-v22": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v22",
        "sha256": "430ebfd9b36fad867ef0edb94fbc80fbca12b7deb70044e0a8fe516cfbb9cf2a",
    },
    "federation-v23": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v23",
        "sha256": "582c5e33482bfad18f6e2aadda16ef198fa01cdf87f68d24aa32a3603218f68e",
    },
    "official-seed-v49": {
        "directories": 1,
        "files": 13,
        "path": "releases/2026-07-20-open-seed-v49",
        "sha256": "77309cad997d57635c7a88de10746ff194d456d19b360574cf46223cb2841395",
    },
}

_PINNED_FILES = {
    "v16 implementation": (
        "datacenter_atlas/current_coverage_v16.py",
        50_693,
        "e5d385c5caf6dfa56a45b10a8150d46360413e99abdb594b86d5f370f6a35b90",
    ),
    "v16 compatibility wrapper": (
        "current_coverage_v16.py",
        150,
        "88e3a89c14174436f2ae6ef80aad2dae500a165e99d7a95ba130c41101f7952a",
    ),
    "v16 definition": (
        V16_BASE_LINEAGE["definition"]["path"],
        V16_BASE_LINEAGE["definition"]["bytes"],
        V16_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v16 ledger": (
        V16_BASE_LINEAGE["ledger"]["path"],
        V16_BASE_LINEAGE["ledger"]["bytes"],
        V16_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v16 manifest": (
        V16_BASE_LINEAGE["manifest"]["path"],
        V16_BASE_LINEAGE["manifest"]["bytes"],
        V16_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v16 sidecar": (
        "current_coverage_ledgers/2026-07-20-v16/manifest.sha256",
        80,
        "92989e32ccbd8a40b633d4aeb7728ef152ca0898de16567967fa936427af4f38",
    ),
    "official seed v49 definition": (
        "sources/open-seed-2026-07-20-v49.json",
        62_617,
        "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c",
    ),
    "official seed v49 manifest": (
        "releases/2026-07-20-open-seed-v49/manifest.json",
        8_364,
        "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489",
    ),
    "federation v23 definition": (
        "sources/federation-2026-07-20-public-open-v23.json",
        1_788,
        "056d36d13712e613b51d28e59ea542b82fc720e093afb142af289ae30d1b0411",
    ),
    "federation v23 index": (
        "federated_indexes/2026-07-20-public-open-v23/federated-index.json",
        23_453,
        "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2",
    ),
    "federation v23 manifest": (
        "federated_indexes/2026-07-20-public-open-v23/manifest.json",
        986,
        "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be",
    ),
    "coverage audit v22 definition": (
        "sources/coverage-audit-2026-07-20-public-open-v22.json",
        3_871,
        "0961741293f4ea682536498bb705a687a2b328037cc3de1577ae8803ed2d7d65",
    ),
    "coverage audit v22 manifest": (
        "audits/2026-07-20-public-open-coverage-v22/manifest.json",
        2_240,
        "e30e622393099b3bcca2c0965258664ff261133913d677cd06579c622df56307",
    ),
    "construction master v22 implementation": (
        "datacenter_atlas/construction_master_v6.py",
        3_037,
        "260389903e4bd0b4877251076f6913eb3e5ae197efc1def4e1d0ce1d836558bd",
    ),
    "construction master v22 definition": (
        "sources/construction-master-2026-07-20-public-open-v22.json",
        5_657,
        "6a66eb3698d15c428d6196e46f1f1ceca468bb5180b372c33632d6506684fca7",
    ),
    "construction master v22 coverage": (
        "construction_master/2026-07-20-public-open-v22/coverage.json",
        8_523,
        "3c7ebaf3ae82292bbd489c573e3393b552bf1855df3d586c72dfca3eed4b38b1",
    ),
    "construction master v22 manifest": (
        "construction_master/2026-07-20-public-open-v22/manifest.json",
        9_694,
        "a7e96c666b440b53a6fdf8c1f295f2da0a587294abb56d51380bb85a8ac80731",
    ),
    "construction map v22 implementation": (
        "datacenter_atlas/construction_map_v6.py",
        2_260,
        "941bf89f4913f2cfc40859abb16a735f286c3323fc8e8d3811e14d728b96f6df",
    ),
    "construction map v22 definition": (
        "sources/construction-map-2026-07-20-public-open-v22.json",
        2_441,
        "e9da20d5e60351f9dded7becd79927c297af40490b3b0583ba11256c350299e8",
    ),
    "construction map v22 coverage": (
        "construction_maps/2026-07-20-public-open-v22/coverage.json",
        7_390,
        "8e9a52561aeba7593824af413c8e546fb657ba22816a31b21286e1d7921d2721",
    ),
    "construction map v22 manifest": (
        "construction_maps/2026-07-20-public-open-v22/manifest.json",
        2_192,
        "d0621f88437a7dc1934abe84138ecd8732868f8ecc2a4f02d836d0751746cf85",
    ),
}

_SOURCE_TIMESTAMPS = {
    "official seed v49": (
        "releases/2026-07-20-open-seed-v49/manifest.json",
        "recorded_at",
        "2026-07-20T16:45:00Z",
    ),
    "federation v23": (
        "federated_indexes/2026-07-20-public-open-v23/federated-index.json",
        "generated_at",
        "2026-07-20T16:49:00Z",
    ),
    "coverage audit v22": (
        "audits/2026-07-20-public-open-coverage-v22/manifest.json",
        "generated_at",
        "2026-07-20T16:50:00Z",
    ),
    "construction master v22": (
        "construction_master/2026-07-20-public-open-v22/manifest.json",
        "generated_at",
        "2026-07-20T16:52:30Z",
    ),
    "construction map v22": (
        "construction_maps/2026-07-20-public-open-v22/manifest.json",
        "generated_at",
        "2026-07-20T16:52:31Z",
    ),
}


class CurrentCoverageV17Error(_legacy.CurrentCoverageError):
    """Raised when the v17 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True)
class CurrentCoverageV17Bundle:
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
        raise CurrentCoverageV17Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV17Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV17Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV17Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV17Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV17Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v14._tree_digest(path, label)
    except (ValueError, _v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV17Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV17Error(f"{label} closed tree changed")


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


def _replacement_checkpoints() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v22": [
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-20-public-open-v22/coverage.json",
                7_390,
                "8e9a52561aeba7593824af413c8e546fb657ba22816a31b21286e1d7921d2721",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-20-public-open-v22.json",
                2_441,
                "e9da20d5e60351f9dded7becd79927c297af40490b3b0583ba11256c350299e8",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-20-public-open-v22/manifest.json",
                2_192,
                "d0621f88437a7dc1934abe84138ecd8732868f8ecc2a4f02d836d0751746cf85",
            ),
        ],
        "construction-master-public-open-v22": [
            _checkpoint(
                "coverage",
                "construction_master/2026-07-20-public-open-v22/coverage.json",
                8_523,
                "3c7ebaf3ae82292bbd489c573e3393b552bf1855df3d586c72dfca3eed4b38b1",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-20-public-open-v22.json",
                5_657,
                "6a66eb3698d15c428d6196e46f1f1ceca468bb5180b372c33632d6506684fca7",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-20-public-open-v22/manifest.json",
                9_694,
                "a7e96c666b440b53a6fdf8c1f295f2da0a587294abb56d51380bb85a8ac80731",
            ),
        ],
        "coverage-audit-public-open-v22": [
            _checkpoint(
                "manifest",
                "audits/2026-07-20-public-open-coverage-v22/manifest.json",
                2_240,
                "e30e622393099b3bcca2c0965258664ff261133913d677cd06579c622df56307",
            )
        ],
        "federation-public-open-v23": [
            _checkpoint(
                "index",
                "federated_indexes/2026-07-20-public-open-v23/federated-index.json",
                23_453,
                "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-20-public-open-v23/manifest.json",
                986,
                "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be",
            ),
        ],
        "seed-epoch-official-v49": [
            _checkpoint(
                "manifest",
                "releases/2026-07-20-open-seed-v49/manifest.json",
                8_364,
                "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489",
            )
        ],
    }


def _replacement_limitations() -> dict[str, list[str]]:
    return {
        "construction-map-public-open-v22": [
            "Map rows are a presentation derivative of construction-master v22 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Two hundred sixty-four master observations lack coordinates, including 246 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        "construction-master-public-open-v22": [
            "Historical lifecycle statuses are source-scoped observations and do not establish current construction after reported_status_date.",
            "Only 447 Tier-A source-supported observation rows enter construction arithmetic; the 109,239 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        "coverage-audit-public-open-v22": [
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 633 source and source-country groups and 3,293 open gaps are coverage-accounting units, not site counts.",
        ],
        "federation-public-open-v23": [
            "The 16,054 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,577 construction-pipeline records include 6,130 review-only fuzzy rows and only 447 non-review observations; they are not all confirmed construction sites.",
        ],
        "seed-epoch-official-v49": [
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; absent fields are not inferred from satellite imagery.",
            "The 629 source-scoped entity rows comprise 340 campus observations and 289 project observations, not deduplicated physical sites.",
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
        ],
    }


def _replacement_metrics() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v22": [
            _metric("added_replacement_rows_unmapped", "coverage", "/projection/added_replacement_rows_unmapped", 125),
            _metric("default_visible_rows", "definition", "/expected_projection/default_visible_rows", 6_481),
            _metric("mapped_replacement_rows", "coverage", "/counts/mapped_replacement_rows", 82),
            _metric("mapped_rows_with_any_role", "coverage", "/counts/mapped_rows_with_any_role", 66),
            _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 201),
            _metric("mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280),
            _metric("mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494),
            _metric("mapped_total_rows", "coverage", "/counts/mapped_observation_rows", 108_975),
            _metric("mapped_unknown_country_rows", "coverage", "/mapped_counts/by_country/Unknown", 102_541),
            _metric("master_total_rows", "coverage", "/counts/master_observation_rows", 109_239),
            _metric("unique_physical_sites", "coverage", "/counts/unique_physical_site_count", None),
            _metric("unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 264),
        ],
        "construction-master-public-open-v22": [
            _metric("added_replacement_rows", "coverage", "/replacement_invariants/added_replacement_rows", 128),
            _metric("base_rows", "coverage", "/replacement_invariants/base_rows", 109_111),
            _metric("contract_marked_rows", "coverage", "/replacement_invariants/rows_with_contract_marker", 327),
            _metric("inherited_rows", "coverage", "/replacement_invariants/inherited_rows", 108_912),
            _metric("publication_contract_version", "coverage", "/replacement/publication_contract_version", 4),
            _metric("replacement_rows", "coverage", "/replacement_invariants/replacement_rows", 327),
            _metric("role_rows_with_any_role", "coverage", "/role_counts/rows_with_any_role", 114),
            _metric("role_rows_with_customers", "coverage", "/role_counts/with_core_role/customers", 1),
            _metric("role_rows_with_operator", "coverage", "/role_counts/with_core_role/operator", 45),
            _metric("role_rows_with_owner", "coverage", "/role_counts/with_core_role/owner", 47),
            _metric("role_rows_with_source_role_tags", "coverage", "/role_counts/rows_with_source_role_tags", 75),
            _metric("role_rows_with_tenants", "coverage", "/role_counts/with_core_role/tenants", 5),
            _metric("role_rows_with_users", "coverage", "/role_counts/with_core_role/users", 36),
            _metric("satellite_recovery_control_plane_bytes", "coverage", "/satellite_recovery_acceptance/control_plane_bytes", 15_313),
            _metric("satellite_recovery_control_plane_files", "coverage", "/satellite_recovery_acceptance/control_plane_files", 4),
            _metric("satellite_recovery_rows", "coverage", "/satellite_recovery_acceptance/rows_created", 0),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 447),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
            _metric("total_master_rows", "coverage", "/row_counts/total", 109_239),
            _metric("unchanged_replacement_rows", "coverage", "/replacement_invariants/unchanged_replacement_rows", 199),
            _metric("unique_physical_sites", "coverage", "/row_counts/unique_physical_site_count", None),
        ],
        "coverage-audit-public-open-v22": [
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 633),
            _metric("non_review_source_scoped_rows", "manifest", "/counts/non_review_source_scoped_entity_records", 9_924),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 3_293),
            _metric("review_only_source_scoped_rows", "manifest", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "manifest", "/counts/source_scoped_entity_records", 16_054),
            _metric("unique_physical_sites", "manifest", "/counts/unique_physical_sites", None),
        ],
        "federation-public-open-v23": [
            _metric("capacity_observations", "index", "/counts/capacity_estimates", 1_253),
            _metric("construction_pipeline_records", "index", "/counts/construction_pipeline_records", 6_577),
            _metric("non_review_construction_pipeline_records", "index", "/counts/non_review_construction_pipeline_records", 447),
            _metric("non_review_source_scoped_rows", "index", "/counts/non_review_source_scoped_entity_records", 9_924),
            _metric("review_only_construction_pipeline_records", "index", "/counts/review_only_construction_pipeline_records", 6_130),
            _metric("review_only_source_scoped_rows", "index", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "index", "/counts/source_scoped_entity_records", 16_054),
            _metric("unique_physical_sites", "index", "/counts/unique_physical_sites", None),
        ],
        "seed-epoch-official-v49": [
            _metric("capacity_observations", "manifest", "/capacity_estimates", 467),
            _metric("construction_pipeline_records", "manifest", "/construction_pipeline_records", 327),
            _metric("construction_source_signals", "manifest", "/construction_source_signals", 235),
            _metric("evidence_records", "manifest", "/evidence_records", 352),
            _metric("resolution_candidates", "manifest", "/resolution_candidates", 4),
            _metric("source_scoped_entity_rows", "manifest", "/entities", 629),
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
        raise CurrentCoverageV17Error("v17 replacement specification changed")
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in ARTIFACT_REPLACEMENTS.items():
        entry = deepcopy(dict(base_entries[old_id]))
        entry["artifact_id"] = new_id
        entry["checkpoints"] = checkpoints[new_id]
        entry["limitations"] = sorted(limitations[new_id])
        entry["metrics"] = metrics[new_id]
        result[new_id] = entry
    return result


def _load_v16_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_path = package_root / V16_BASE_LINEAGE["definition"]["path"]
    bundle_path = package_root / _BASE_BUNDLE_TREE["path"]
    try:
        _v16.validate_current_coverage_ledger_v16(
            bundle_path, definition_path=definition_path
        )
    except _v16.CurrentCoverageV16Error as error:
        raise CurrentCoverageV17Error(
            f"accepted v16 base failed offline validation: {error}"
        ) from error
    definition_raw, definition = _pinned_json(
        package_root, V16_BASE_LINEAGE["definition"], "v17 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V16_BASE_LINEAGE["ledger"], "v17 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V16_BASE_LINEAGE["manifest"], "v17 base manifest"
    )
    if (
        definition.get("ledger_id") != V16_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V16_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V16_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V16_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V16_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V16_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV17Error("accepted v16 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v17 base bundle")
    return definition, ledger, manifest


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV17Error(f"{label} timestamp is invalid") from error


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v17 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV17Error(f"v17 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v17 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v17 {label}")
    generated_at = _parse_timestamp(V17_GENERATED_AT, "v17")
    for label, (relative, field, expected) in sorted(_SOURCE_TIMESTAMPS.items()):
        raw = _read_regular(package_root / relative, f"v17 {label} timestamp source")
        document = _json_object(raw, f"v17 {label} timestamp source")
        if document.get(field) != expected:
            raise CurrentCoverageV17Error(f"v17 {label} timestamp changed")
        if _parse_timestamp(expected, f"v17 {label}") > generated_at:
            raise CurrentCoverageV17Error(f"v17 predates {label}")


def _v17_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV17Error("v16 parity gaps are invalid")
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV17Error("v16 parity gap is invalid")
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
        raise CurrentCoverageV17Error(f"v17 {label} digest changed")


def make_v17_definition(package_root: str | Path) -> bytes:
    """Create canonical v17 definition bytes from the pinned v16 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v16_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry)
        for entry in base_definition["entries"]
    }
    if len(base_entries) != 45 or not REMOVED_ARTIFACT_IDS <= set(base_entries):
        raise CurrentCoverageV17Error("v16 replacement source inventory changed")
    if set(base_entries) & REPLACEMENT_ARTIFACT_IDS:
        raise CurrentCoverageV17Error("v16 unexpectedly contains a v17 artifact ID")
    replacements = _replacement_entries(base_entries)
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    if len(base_entries) != 45:
        raise CurrentCoverageV17Error("v17 definition must contain 45 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry
        for entry in ordered
        if entry["artifact_id"] not in REPLACEMENT_ARTIFACT_IDS
    ]
    replacement_entries = [
        entry
        for entry in ordered
        if entry["artifact_id"] in REPLACEMENT_ARTIFACT_IDS
    ]
    if len(unchanged) != 40 or len(replacement_entries) != 5:
        raise CurrentCoverageV17Error("v17 delta arithmetic changed")
    parity_gaps = _v17_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_40_SHA256, "inherited entries"
    )
    _require_digest(
        _component_digest(replacement_entries),
        REPLACEMENT_5_SHA256,
        "replacement entries",
    )
    _require_digest(_component_digest(ordered), ALL_ENTRIES_SHA256, "all entries")
    _require_digest(
        _sha256(_canonical_line(parity_gaps)), PARITY_GAPS_SHA256, "parity gaps"
    )
    document = {
        "base_ledger": V16_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V17_GENERATED_AT,
        "ledger_id": V17_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    forbidden = (
        "current-coverage-2026-07-20-v15",
        "open-seed-2026-07-20-v45",
        "open-seed-2026-07-20-v46",
        "open-seed-2026-07-20-v48",
        "seed-epoch-official-v45",
        "seed-epoch-official-v46",
        "seed-epoch-official-v48",
        "construction-master-public-open-v20",
        "construction-map-public-open-v20",
        "federation-public-open-v21",
    )
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV17Error("v17 definition contains rejected lineage")
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V17_DEFINITION_PATH:
        raise CurrentCoverageV17Error("v17 definition publication path changed")
    raw = _read_regular(path, "v17 definition")
    document = _json_object(raw, "v17 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV17Error("v17 definition is not canonical JSON")
    if not V17_DEFINITION_SHA256 or _sha256(raw) != V17_DEFINITION_SHA256:
        raise CurrentCoverageV17Error("v17 definition content changed or is unpinned")
    if raw != make_v17_definition(package_root):
        raise CurrentCoverageV17Error("v17 definition differs from pinned transformation")
    if (
        document.get("ledger_id") != V17_LEDGER_ID
        or document.get("generated_at") != V17_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V16_BASE_LINEAGE
    ):
        raise CurrentCoverageV17Error("v17 identity, base, schema, or scope changed")
    generated_at = _parse_timestamp(V17_GENERATED_AT, "v17")
    if generated_at > datetime.now(UTC):
        raise CurrentCoverageV17Error("v17 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 45:
        raise CurrentCoverageV17Error("v17 must contain exactly 45 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 45 or None in artifact_ids:
        raise CurrentCoverageV17Error("v17 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not (
        REPLACEMENT_ARTIFACT_IDS <= artifact_ids
    ):
        raise CurrentCoverageV17Error("v17 delta inventory is invalid")
    return document, raw, package_root


def build_current_coverage_ledger_v17(
    definition_path: str | Path,
) -> CurrentCoverageV17Bundle:
    """Reproduce the v17 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, base_ledger, _base_manifest = _load_v16_base(package_root)
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
        raise CurrentCoverageV17Error(str(error)) from error
    inventory_counts = _v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != base_ledger["artifact_inventory_counts"]:
        raise CurrentCoverageV17Error("v17 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V16_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V17_GENERATED_AT,
        "ledger_id": V17_LEDGER_ID,
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
        "base_ledger": V16_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V17_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V17_GENERATED_AT,
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
        "ledger_id": V17_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV17Bundle(
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
        raise CurrentCoverageV17Error(f"refusing active output lock: {lock}") from error
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
        _v16._cleanup_owned_file_stage(stage, identity)
    except _v16.CurrentCoverageV16Error as error:
        raise CurrentCoverageV17Error(str(error).replace("v16", "v17")) from error


def _cleanup_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v16._cleanup_owned_bundle_stage(stage, identity)
    except _v16.CurrentCoverageV16Error as error:
        raise CurrentCoverageV17Error(str(error).replace("v16", "v17")) from error


def _promote_noreplace(stage: Path, destination: Path) -> None:
    try:
        _v16._promote_noreplace(stage, destination)
    except _v16.CurrentCoverageV16Error as error:
        raise CurrentCoverageV17Error(str(error).replace("v16", "v17")) from error


def write_v17_definition(
    package_root: str | Path, output_path: str | Path
) -> str:
    """Atomically create, but never replace, the canonical v17 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v17_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV17Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _v16._path_identity(stage)
            stage.chmod(0o644)
            _v16._fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _v16._fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV17Error(
                    "v17 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v17 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v17(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v17 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV17Error("v17 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v17(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV17Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _v16._path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _v16._fsync_regular(stage / filename)
            stage.chmod(0o555)
            _v16._fsync_directory(stage)
            validate_current_coverage_ledger_v17(
                stage, definition_path=definition_path
            )
            _promote_noreplace(stage, destination)
            _v16._fsync_directory(destination.parent)
            validate_current_coverage_ledger_v17(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v17 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v17(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = _lexical_absolute(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV17Error("v17 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV17Error("v17 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV17Error("v17 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v17 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v17 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v17 sidecar")
    _json_object(actual_ledger, "v17 ledger")
    manifest = _json_object(actual_manifest, "v17 manifest")
    if actual_ledger != _canonical_json(_json_object(actual_ledger, "v17 ledger")):
        raise CurrentCoverageV17Error("v17 ledger is not canonical JSON")
    if actual_manifest != _canonical_json(manifest):
        raise CurrentCoverageV17Error("v17 manifest is not canonical JSON")
    if actual_sidecar != (
        f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CurrentCoverageV17Error("v17 manifest sidecar differs")
    expected = build_current_coverage_ledger_v17(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV17Error("v17 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV17Error("v17 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV17Error("v17 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV17Bundle",
    "CurrentCoverageV17Error",
    "PARITY_GAPS_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_5_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "UNCHANGED_40_SHA256",
    "V16_BASE_LINEAGE",
    "V17_BUNDLE_PATH",
    "V17_DEFINITION_PATH",
    "V17_DEFINITION_SHA256",
    "V17_GENERATED_AT",
    "V17_LEDGER_ID",
    "build_current_coverage_ledger_v17",
    "make_v17_definition",
    "validate_current_coverage_ledger_v17",
    "write_current_coverage_ledger_v17",
    "write_v17_definition",
]
