"""Collision-isolated current-coverage ledger v20.

V20 is a strict successor of the accepted frozen v19 ledger. It replaces
exactly five superseded public-core entries with the accepted v26/v27 chain,
preserves the other forty-two entries byte-for-byte, and adds nothing. The
accepted construction-timeline v2 artifact is deliberately deferred because
adding it would expand the v19 ledger inventory rather than perform an exact
reference replacement. Historical lifecycle observations remain last-observed
facts, unique physical sites remain unknown, and imagery remains review-only.
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

from . import construction_map_v10 as _map_v10
from . import construction_master_v10 as _master_v10
from . import coverage_audit_v3 as _coverage_v3
from . import current_coverage as _legacy
from . import current_coverage_v19 as _v19
from . import exact_identity_decisions_v3 as _identity_v3
from . import federated_release_v3 as _federation_v3


V20_LEDGER_ID = "current-coverage-2026-07-20-v20"
V20_GENERATED_AT = "2026-07-21T05:55:00Z"
V20_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v20.json"
V20_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v20"
V20_DEFINITION_SHA256 = (
    "8a8aca77431ca21867f8f3317114b40cb41c642aacc9f333d7eb1f1a402410b3"
)

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V19_BASE_LINEAGE = {
    "definition": {
        "bytes": 142_460,
        "path": "sources/current-coverage-2026-07-20-v19.json",
        "sha256": "6ffd11fdeab77cb92c9c820c917f0a0e02f68c417907b70aec8059fbae9dee04",
    },
    "ledger": {
        "bytes": 98_188,
        "path": (
            "current_coverage_ledgers/2026-07-20-v19/"
            "current-coverage-ledger.json"
        ),
        "sha256": "143dacb68947f1d6483a47da1ebd294648a40d0ca2aab2deba078ec36fbd124a",
    },
    "ledger_id": "current-coverage-2026-07-20-v19",
    "manifest": {
        "bytes": 27_429,
        "path": "current_coverage_ledgers/2026-07-20-v19/manifest.json",
        "sha256": "bcfe53a5a23e3c8dbca40feb646cfff93abd24614a60382266dd830376074f42",
    },
}

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v24": "construction-map-public-open-v26",
    "construction-master-public-open-v24": "construction-master-public-open-v26",
    "coverage-audit-public-open-v24": "coverage-audit-public-open-v26",
    "exact-identity-decisions-public-open-v3": (
        "exact-identity-decisions-public-open-v5"
    ),
    "federation-public-open-v25": "federation-public-open-v27",
}
ADDED_ARTIFACT_IDS: frozenset[str] = frozenset()
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS

UNCHANGED_42_SHA256 = (
    "5d95751e60c4c7414e5d29a647234490fb701eaf44f76156e95bb54defee6804"
)
REPLACEMENT_5_SHA256 = (
    "4f5fffbdfdcc8db3664d97b93688507bee1c1ae97cc17a0101aa59512b9a9ac9"
)
ALL_ENTRIES_SHA256 = (
    "b0b1a944a4e5f5c852ee6ebc5ff5f81286aae81fd4bae41d2b0dcde41f20a5fe"
)
PARITY_GAPS_SHA256 = (
    "b093d029fcaa54390dabfac8e8346fe97db5bde4b329880cef6a59607ef2f6f4"
)

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v19",
    "sha256": "33d455ae9ce493dffdc11a5121cfc222800bc516dba37877434f7545b4365a3e",
}

_ACCEPTED_TREES = {
    "construction-map-v26": {
        "directories": 1,
        "files": 7,
        "path": "construction_maps/2026-07-20-public-open-v26",
        "sha256": "7f9a6e61f6d082286448d29c0d68fda37206c7a90a814f813909c049149350b2",
    },
    "construction-master-v26": {
        "directories": 1,
        "files": 7,
        "path": "construction_master/2026-07-20-public-open-v26",
        "sha256": "2c575c8e129c335694d29bac4000773980134a4ac6d253554438106742727079",
    },
    "coverage-audit-v26": {
        "directories": 1,
        "files": 6,
        "path": "audits/2026-07-20-public-open-coverage-v26",
        "sha256": "ed88ac54e1358233bb7270836d00aff6063ecf4b9fbfbdaf3e109fb968ea0fe8",
    },
    "exact-identity-decisions-v5": {
        "directories": 1,
        "files": 9,
        "path": "exact_identity_decisions/2026-07-20-public-open-v5",
        "sha256": "5fabf0ac8f28bc59c9969fb6a50240797ec0a440c2a534388aea9f0a2f9c64e6",
    },
    "federation-v27": {
        "directories": 1,
        "files": 3,
        "path": "federated_indexes/2026-07-20-public-open-v27",
        "sha256": "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671",
    },
}

_PINNED_FILES = {
    "v19 implementation": (
        "datacenter_atlas/current_coverage_v19.py",
        55_568,
        "ea6f08c025727d5702f20e6d7c195cd56881fd4fd2861f3f8ce75bb6d39bb378",
    ),
    "v19 compatibility wrapper": (
        "current_coverage_v19.py",
        150,
        "5d66572dc18aa43dd6ebe68c20d7316032059100b449916353c7f27c2bf91e8e",
    ),
    "v19 definition": (
        V19_BASE_LINEAGE["definition"]["path"],
        V19_BASE_LINEAGE["definition"]["bytes"],
        V19_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v19 ledger": (
        V19_BASE_LINEAGE["ledger"]["path"],
        V19_BASE_LINEAGE["ledger"]["bytes"],
        V19_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v19 manifest": (
        V19_BASE_LINEAGE["manifest"]["path"],
        V19_BASE_LINEAGE["manifest"]["bytes"],
        V19_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v19 sidecar": (
        "current_coverage_ledgers/2026-07-20-v19/manifest.sha256",
        80,
        "79ff81352c85ae188d5ecd2d9390e1f6a29905452ed60dbdc3bbeef05fcdc5c6",
    ),
    "construction map v26 definition": (
        "sources/construction-map-2026-07-20-public-open-v26.json",
        2_441,
        "3829254804d1377f7df74a92cd860db80d22e7b206ce4fd63214cbd1dd901d13",
    ),
    "construction map v26 coverage": (
        "construction_maps/2026-07-20-public-open-v26/coverage.json",
        7_462,
        "238abbbc23fffb5f132a472223a7a207e2bc375a402d62c926a2ee1fecf5d4fa",
    ),
    "construction map v26 manifest": (
        "construction_maps/2026-07-20-public-open-v26/manifest.json",
        2_192,
        "1f365a43ecc97d5ed19c9003bc517f962a69ee7d9c94e27943b2bd5052478de3",
    ),
    "construction master v26 definition": (
        "sources/construction-master-2026-07-20-public-open-v26.json",
        5_658,
        "ede029f2fa2ecb6371b311de6497e0eda2dc38d23752a8ec1efc2760b27dda45",
    ),
    "construction master v26 coverage": (
        "construction_master/2026-07-20-public-open-v26/coverage.json",
        8_548,
        "e3c1cb020a0261dee6f405dc5f865e33a53ae28b11faf9c00802b8ccf16bc838",
    ),
    "construction master v26 manifest": (
        "construction_master/2026-07-20-public-open-v26/manifest.json",
        9_720,
        "f5895210b32b0307dc1cc12791541024bdb9dc39532ff2ebff0f669d9442bb82",
    ),
    "coverage audit v26 definition": (
        "sources/coverage-audit-2026-07-20-public-open-v26.json",
        5_920,
        "7275d187e5d490be4a21a941f1d06189729f5357381957f51651d64c9ee0fddd",
    ),
    "coverage audit v26 manifest": (
        "audits/2026-07-20-public-open-coverage-v26/manifest.json",
        3_379,
        "181dd9c24f7445cade64e20708d01485d67d78c0124b6f88f2071d9b920de931",
    ),
    "exact identity v5 definition": (
        "sources/exact-identity-decisions-2026-07-20-public-open-v5.json",
        1_735,
        "c5a33ae467c2187157d5799a17d81f08c49d623926303641ebb21cd15f7192d7",
    ),
    "exact identity v5 accounting": (
        "exact_identity_decisions/2026-07-20-public-open-v5/accounting.json",
        981,
        "d26c6e1fbf3502ea68e2209e86355bc872826a60e351f884c69bb1b1516c42a5",
    ),
    "exact identity v5 manifest": (
        "exact_identity_decisions/2026-07-20-public-open-v5/manifest.json",
        11_438,
        "9bb5c1ef49fe1bf3904c2dca080ef5ab51de014935f1792a2bc99c0888bb68b5",
    ),
    "federation v27 definition": (
        "sources/federation-2026-07-20-public-open-v27.json",
        1_788,
        "4f0bbb0fcef771966f9d18cdcc28691b4adeb1b9b60d6f2af95fd4c6e592499e",
    ),
    "federation v27 index": (
        "federated_indexes/2026-07-20-public-open-v27/federated-index.json",
        27_784,
        "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8",
    ),
    "federation v27 manifest": (
        "federated_indexes/2026-07-20-public-open-v27/manifest.json",
        986,
        "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v26": (
        "construction_maps/2026-07-20-public-open-v26/manifest.json",
        "generated_at",
        "2026-07-21T05:05:01Z",
    ),
    "construction master v26": (
        "construction_master/2026-07-20-public-open-v26/manifest.json",
        "generated_at",
        "2026-07-21T05:05:00Z",
    ),
    "coverage audit v26": (
        "audits/2026-07-20-public-open-coverage-v26/manifest.json",
        "generated_at",
        "2026-07-21T05:35:00Z",
    ),
    "exact identity v5": (
        "exact_identity_decisions/2026-07-20-public-open-v5/manifest.json",
        "recorded_at",
        "2026-07-21T04:50:00Z",
    ),
    "federation v27": (
        "federated_indexes/2026-07-20-public-open-v27/manifest.json",
        "generated_at",
        "2026-07-21T04:45:00Z",
    ),
}


class CurrentCoverageV20Error(_legacy.CurrentCoverageError):
    """Raised when the v20 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True)
class CurrentCoverageV20Bundle:
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
        raise CurrentCoverageV20Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV20Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV20Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV20Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV20Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV20Error(f"{label} is not canonical JSON")
    return raw, document


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
        files, directories, digest = _v19._v14._tree_digest(path, label)
    except (ValueError, _v19._v14.CurrentCoverageV14Error) as error:
        raise CurrentCoverageV20Error(str(error)) from error
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV20Error(f"{label} closed tree changed")


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v19._v14._checkpoint(
        checkpoint_id, path, byte_count, sha256, binding=binding
    )


def _metric(label: str, checkpoint_id: str, pointer: str, value: Any) -> dict[str, Any]:
    return _v19._v14._metric(label, checkpoint_id, pointer, value)


def _replacement_checkpoints() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v26": [
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-20-public-open-v26/coverage.json",
                7_462,
                "238abbbc23fffb5f132a472223a7a207e2bc375a402d62c926a2ee1fecf5d4fa",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-20-public-open-v26.json",
                2_441,
                "3829254804d1377f7df74a92cd860db80d22e7b206ce4fd63214cbd1dd901d13",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-20-public-open-v26/manifest.json",
                2_192,
                "1f365a43ecc97d5ed19c9003bc517f962a69ee7d9c94e27943b2bd5052478de3",
            ),
        ],
        "construction-master-public-open-v26": [
            _checkpoint(
                "coverage",
                "construction_master/2026-07-20-public-open-v26/coverage.json",
                8_548,
                "e3c1cb020a0261dee6f405dc5f865e33a53ae28b11faf9c00802b8ccf16bc838",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-20-public-open-v26.json",
                5_658,
                "ede029f2fa2ecb6371b311de6497e0eda2dc38d23752a8ec1efc2760b27dda45",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-20-public-open-v26/manifest.json",
                9_720,
                "f5895210b32b0307dc1cc12791541024bdb9dc39532ff2ebff0f669d9442bb82",
            ),
        ],
        "coverage-audit-public-open-v26": [
            _checkpoint(
                "manifest",
                "audits/2026-07-20-public-open-coverage-v26/manifest.json",
                3_379,
                "181dd9c24f7445cade64e20708d01485d67d78c0124b6f88f2071d9b920de931",
            )
        ],
        "exact-identity-decisions-public-open-v5": [
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-20-public-open-v5/accounting.json",
                981,
                "d26c6e1fbf3502ea68e2209e86355bc872826a60e351f884c69bb1b1516c42a5",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-20-public-open-v5.json",
                1_735,
                "c5a33ae467c2187157d5799a17d81f08c49d623926303641ebb21cd15f7192d7",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-20-public-open-v5/manifest.json",
                11_438,
                "9bb5c1ef49fe1bf3904c2dca080ef5ab51de014935f1792a2bc99c0888bb68b5",
            ),
        ],
        "federation-public-open-v27": [
            _checkpoint(
                "index",
                "federated_indexes/2026-07-20-public-open-v27/federated-index.json",
                27_784,
                "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-20-public-open-v27/manifest.json",
                986,
                "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87",
            ),
        ],
    }


def _replacement_limitations() -> dict[str, list[str]]:
    return {
        "construction-map-public-open-v26": [
            "Map rows are a presentation derivative of construction-master v26 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Two hundred ninety-eight master observations lack coordinates, including 280 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        "construction-master-public-open-v26": [
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses are source-scoped last-observed facts and do not establish current construction after reported_status_date.",
            "Only 493 Tier-A source-supported observation rows enter construction arithmetic; the 109,285 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        "coverage-audit-public-open-v26": [
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 754 source and source-country groups and 3,736 open gaps are coverage-accounting units, not site counts.",
            "The satellite methodology-support artifact is non-countable review support and creates no facility, lifecycle, identity, status, or capacity claim.",
        ],
        "exact-identity-decisions-public-open-v5": [
            "Canonical topology links preserve explicit facility-contains-building and project-targets relationships and are non-additive; they are not unique physical-site counts.",
            "Exact same-kind source-record components collapse repeat occurrences only within their source-scoped keys and authorize neither cross-kind nor cross-source identity union.",
            "Review-only fuzzy references remain excluded from exact-component accounting; unresolved and ambiguous candidate references remain review work, while physical-site bounds and unique physical sites stay null.",
        ],
        "federation-public-open-v27": [
            "The 16,155 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,623 construction-pipeline records include 6,130 review-only fuzzy rows and only 493 non-review observations; they are not all confirmed construction sites.",
            "Historical lifecycle observations are last-observed facts and do not establish current construction without later evidence.",
        ],
    }


def _replacement_metrics() -> dict[str, list[dict[str, Any]]]:
    return {
        "construction-map-public-open-v26": [
            _metric("added_replacement_rows_unmapped", "coverage", "/projection/added_replacement_rows_unmapped", 167),
            _metric("default_visible_rows", "definition", "/expected_projection/default_visible_rows", 6_493),
            _metric("mapped_replacement_rows", "coverage", "/counts/mapped_replacement_rows", 94),
            _metric("mapped_rows_with_any_role", "coverage", "/counts/mapped_rows_with_any_role", 69),
            _metric("mapped_tier_a_rows", "coverage", "/mapped_counts/by_tier/A", 213),
            _metric("mapped_tier_b_rows", "coverage", "/mapped_counts/by_tier/B", 6_280),
            _metric("mapped_tier_c_rows", "coverage", "/mapped_counts/by_tier/C", 102_494),
            _metric("mapped_total_rows", "coverage", "/counts/mapped_observation_rows", 108_987),
            _metric("mapped_unknown_country_rows", "coverage", "/mapped_counts/by_country/Unknown", 102_541),
            _metric("master_total_rows", "coverage", "/counts/master_observation_rows", 109_285),
            _metric("unique_physical_sites", "coverage", "/counts/unique_physical_site_count", None),
            _metric("unmapped_rows", "coverage", "/counts/unmapped_observation_rows", 298),
        ],
        "construction-master-public-open-v26": [
            _metric("added_replacement_rows", "coverage", "/replacement_invariants/added_replacement_rows", 174),
            _metric("base_rows", "coverage", "/replacement_invariants/base_rows", 109_111),
            _metric("contract_marked_rows", "coverage", "/replacement_invariants/rows_with_contract_marker", 373),
            _metric("inherited_rows", "coverage", "/replacement_invariants/inherited_rows", 108_912),
            _metric("publication_contract_version", "coverage", "/replacement/publication_contract_version", 4),
            _metric("replacement_rows", "coverage", "/replacement_invariants/replacement_rows", 373),
            _metric("role_rows_with_any_role", "coverage", "/role_counts/rows_with_any_role", 129),
            _metric("role_rows_with_customers", "coverage", "/role_counts/with_core_role/customers", 2),
            _metric("role_rows_with_operator", "coverage", "/role_counts/with_core_role/operator", 51),
            _metric("role_rows_with_owner", "coverage", "/role_counts/with_core_role/owner", 47),
            _metric("role_rows_with_source_role_tags", "coverage", "/role_counts/rows_with_source_role_tags", 90),
            _metric("role_rows_with_tenants", "coverage", "/role_counts/with_core_role/tenants", 6),
            _metric("role_rows_with_users", "coverage", "/role_counts/with_core_role/users", 36),
            _metric("satellite_recovery_control_plane_bytes", "coverage", "/satellite_recovery_acceptance/control_plane_bytes", 15_313),
            _metric("satellite_recovery_control_plane_files", "coverage", "/satellite_recovery_acceptance/control_plane_files", 4),
            _metric("satellite_recovery_rows", "coverage", "/satellite_recovery_acceptance/rows_created", 0),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 493),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric("tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494),
            _metric("total_master_rows", "coverage", "/row_counts/total", 109_285),
            _metric("unchanged_replacement_rows", "coverage", "/replacement_invariants/unchanged_replacement_rows", 199),
            _metric("unique_physical_sites", "coverage", "/row_counts/unique_physical_site_count", None),
        ],
        "coverage-audit-public-open-v26": [
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 754),
            _metric("methodology_support_artifacts", "manifest", "/counts/methodology_support_artifacts", 1),
            _metric("methodology_support_jobs", "manifest", "/counts/methodology_support_jobs", 74),
            _metric("methodology_support_views", "manifest", "/counts/methodology_support_views", 71),
            _metric("non_review_source_scoped_rows", "manifest", "/counts/non_review_source_scoped_entity_records", 10_025),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 3_736),
            _metric("review_only_source_scoped_rows", "manifest", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "manifest", "/counts/source_scoped_entity_records", 16_155),
            _metric("unique_physical_sites", "manifest", "/counts/unique_physical_sites", None),
        ],
        "exact-identity-decisions-public-open-v5": [
            _metric("ambiguous_identity_candidate_references", "accounting", "/ambiguous_identity_candidate_references", 127),
            _metric("canonical_topology_links", "accounting", "/canonical_topology_links", 2_349),
            _metric("exact_component_reductions", "accounting", "/exact_component_reductions", 1_732),
            _metric("exact_source_record_components", "accounting", "/exact_source_record_components", 8_293),
            _metric("non_review_source_scoped_rows", "accounting", "/non_review_source_scoped_entity_records", 10_025),
            _metric("physical_site_lower_bound", "accounting", "/physical_site_lower_bound", None),
            _metric("physical_site_upper_bound", "accounting", "/physical_site_upper_bound", None),
            _metric("raw_topology_links", "accounting", "/raw_topology_links", 2_754),
            _metric("release_candidate_references", "accounting", "/release_candidate_references", 100_410),
            _metric("review_only_rows_in_public_accounting", "manifest", "/scope/review_only_rows_in_public_accounting", False),
            _metric("source_scoped_entity_rows", "accounting", "/source_scoped_entity_records", 16_155),
            _metric("unique_physical_sites", "accounting", "/unique_physical_sites", None),
            _metric("unresolved_candidate_references", "accounting", "/unresolved_candidate_references", 100_537),
        ],
        "federation-public-open-v27": [
            _metric("capacity_observations", "index", "/counts/capacity_estimates", 1_288),
            _metric("construction_pipeline_records", "index", "/counts/construction_pipeline_records", 6_623),
            _metric("non_review_construction_pipeline_records", "index", "/counts/non_review_construction_pipeline_records", 493),
            _metric("non_review_source_scoped_rows", "index", "/counts/non_review_source_scoped_entity_records", 10_025),
            _metric("review_only_construction_pipeline_records", "index", "/counts/review_only_construction_pipeline_records", 6_130),
            _metric("review_only_source_scoped_rows", "index", "/counts/review_only_source_scoped_entity_records", 6_130),
            _metric("source_scoped_rows", "index", "/counts/source_scoped_entity_records", 16_155),
            _metric("unique_physical_sites", "index", "/counts/unique_physical_sites", None),
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
        raise CurrentCoverageV20Error("v20 replacement specification changed")
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in ARTIFACT_REPLACEMENTS.items():
        entry = deepcopy(dict(base_entries[old_id]))
        entry["artifact_id"] = new_id
        entry["checkpoints"] = checkpoints[new_id]
        entry["limitations"] = sorted(limitations[new_id])
        entry["metrics"] = metrics[new_id]
        result[new_id] = entry
    return result


def _load_v19_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_path = package_root / V19_BASE_LINEAGE["definition"]["path"]
    bundle_path = package_root / _BASE_BUNDLE_TREE["path"]
    try:
        _v19.validate_current_coverage_ledger_v19(
            bundle_path, definition_path=definition_path
        )
    except _v19.CurrentCoverageV19Error as error:
        raise CurrentCoverageV20Error(
            f"accepted v19 base failed offline validation: {error}"
        ) from error
    definition_raw, definition = _pinned_json(
        package_root, V19_BASE_LINEAGE["definition"], "v20 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V19_BASE_LINEAGE["ledger"], "v20 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V19_BASE_LINEAGE["manifest"], "v20 base manifest"
    )
    if (
        definition.get("ledger_id") != V19_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V19_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V19_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V19_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V19_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V19_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV20Error("accepted v19 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v20 base bundle")
    return definition, ledger, manifest


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV20Error(f"{label} timestamp is invalid") from error


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v20 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV20Error(f"v20 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v20 base bundle")
    for label, spec in sorted(_ACCEPTED_TREES.items()):
        _validate_tree(package_root, spec, f"v20 {label}")
    try:
        _master_v10.validate_construction_master_v10(
            package_root / _ACCEPTED_TREES["construction-master-v26"]["path"],
            definition_path=(
                package_root
                / "sources/construction-master-2026-07-20-public-open-v26.json"
            ),
            reproduce=False,
        )
        _map_v10.validate_construction_map_v10(
            package_root / _ACCEPTED_TREES["construction-map-v26"]["path"],
            master_directory=(
                package_root
                / _ACCEPTED_TREES["construction-master-v26"]["path"]
            ),
            master_definition_path=(
                package_root
                / "sources/construction-master-2026-07-20-public-open-v26.json"
            ),
            map_definition_path=(
                package_root
                / "sources/construction-map-2026-07-20-public-open-v26.json"
            ),
            reproduce=False,
        )
        _coverage_v3.validate_coverage_audit(
            package_root / _ACCEPTED_TREES["coverage-audit-v26"]["path"],
            definition_path=(
                package_root
                / "sources/coverage-audit-2026-07-20-public-open-v26.json"
            ),
        )
        _federation_v3.validate_federated_release_index(
            package_root / _ACCEPTED_TREES["federation-v27"]["path"]
        )
        _identity_v3.validate_exact_identity_decision_bundle(
            package_root
            / _ACCEPTED_TREES["exact-identity-decisions-v5"]["path"],
            definition_path=(
                package_root
                / "sources/exact-identity-decisions-2026-07-20-public-open-v5.json"
            ),
            verify_inputs=False,
            require_frozen=True,
        )
    except Exception as error:
        raise CurrentCoverageV20Error(
            f"accepted v26/v27 successor input failed offline validation: {error}"
        ) from error
    generated_at = _parse_timestamp(V20_GENERATED_AT, "v20")
    for label, (relative, field, expected) in sorted(_SOURCE_TIMESTAMPS.items()):
        document = _json_object(
            _read_regular(package_root / relative, f"v20 {label} timestamp source"),
            f"v20 {label} timestamp source",
        )
        if document.get(field) != expected:
            raise CurrentCoverageV20Error(f"v20 {label} timestamp changed")
        if _parse_timestamp(expected, f"v20 {label}") > generated_at:
            raise CurrentCoverageV20Error(f"v20 predates {label}")
    audit_manifest = _json_object(
        _read_regular(
            package_root / "audits/2026-07-20-public-open-coverage-v26/manifest.json",
            "v20 coverage audit manifest",
        ),
        "v20 coverage audit manifest",
    )
    if audit_manifest.get("as_of") != "2026-07-20":
        raise CurrentCoverageV20Error("v20 local as-of date changed")


def _v20_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV20Error("v19 parity gaps are invalid")
    result: list[dict[str, Any]] = []
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV20Error("v19 parity gap is invalid")
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
        raise CurrentCoverageV20Error(f"v20 {label} digest changed")


def make_v20_definition(package_root: str | Path) -> bytes:
    """Create canonical v20 definition bytes from the pinned v19 baseline."""

    root = Path(package_root).resolve()
    _validate_accepted_inputs(root)
    base_definition, _base_ledger, _base_manifest = _load_v19_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if len(base_entries) != 47 or not REMOVED_ARTIFACT_IDS <= set(base_entries):
        raise CurrentCoverageV20Error("v19 replacement source inventory changed")
    if set(base_entries) & NEW_ARTIFACT_IDS:
        raise CurrentCoverageV20Error("v19 unexpectedly contains a v20 artifact ID")
    replacements = _replacement_entries(base_entries)
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(replacements)
    if len(base_entries) != 47:
        raise CurrentCoverageV20Error("v20 definition must contain 47 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] not in NEW_ARTIFACT_IDS
    ]
    replacement_entries = [
        entry
        for entry in ordered
        if entry["artifact_id"] in REPLACEMENT_ARTIFACT_IDS
    ]
    if len(unchanged) != 42 or len(replacement_entries) != 5:
        raise CurrentCoverageV20Error("v20 delta arithmetic changed")
    parity_gaps = _v20_parity_gaps(base_definition["parity_gaps"])
    _require_digest(
        _component_digest(unchanged), UNCHANGED_42_SHA256, "inherited entries"
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
        "base_ledger": V19_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V20_GENERATED_AT,
        "ledger_id": V20_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in REMOVED_ARTIFACT_IDS):
        raise CurrentCoverageV20Error("v20 definition contains superseded lineage")
    if "construction-timeline-public-open-v2" in rendered:
        raise CurrentCoverageV20Error("v20 must not expand into timeline inventory")
    return raw


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V20_DEFINITION_PATH:
        raise CurrentCoverageV20Error("v20 definition publication path changed")
    raw = _read_regular(path, "v20 definition")
    document = _json_object(raw, "v20 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV20Error("v20 definition is not canonical JSON")
    if not V20_DEFINITION_SHA256 or _sha256(raw) != V20_DEFINITION_SHA256:
        raise CurrentCoverageV20Error("v20 definition content changed or is unpinned")
    if raw != make_v20_definition(package_root):
        raise CurrentCoverageV20Error(
            "v20 definition differs from pinned transformation"
        )
    if (
        document.get("ledger_id") != V20_LEDGER_ID
        or document.get("generated_at") != V20_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V19_BASE_LINEAGE
    ):
        raise CurrentCoverageV20Error("v20 identity, base, schema, or scope changed")
    if _parse_timestamp(V20_GENERATED_AT, "v20") > datetime.now(UTC):
        raise CurrentCoverageV20Error("v20 timestamp is in the future")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 47:
        raise CurrentCoverageV20Error("v20 must contain exactly 47 entries")
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if len(artifact_ids) != 47 or None in artifact_ids:
        raise CurrentCoverageV20Error("v20 entry inventory is invalid")
    if artifact_ids & REMOVED_ARTIFACT_IDS or not NEW_ARTIFACT_IDS <= artifact_ids:
        raise CurrentCoverageV20Error("v20 delta inventory is invalid")
    return document, raw, package_root


def build_current_coverage_ledger_v20(
    definition_path: str | Path,
) -> CurrentCoverageV20Bundle:
    """Reproduce the v20 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    _base_definition, base_ledger, _base_manifest = _load_v19_base(package_root)
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
        raise CurrentCoverageV20Error(str(error)) from error
    inventory_counts = _v19._v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != base_ledger["artifact_inventory_counts"]:
        raise CurrentCoverageV20Error("v20 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V19_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V20_GENERATED_AT,
        "ledger_id": V20_LEDGER_ID,
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
        "base_ledger": V19_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V20_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V20_GENERATED_AT,
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
        "ledger_id": V20_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    return CurrentCoverageV20Bundle(
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
        with _v19._exclusive_output_lock(destination):
            yield
    except _v19.CurrentCoverageV19Error as error:
        raise CurrentCoverageV20Error(str(error).replace("v19", "v20")) from error


def _cleanup_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v19._cleanup_file_stage(stage, identity)
    except _v19.CurrentCoverageV19Error as error:
        raise CurrentCoverageV20Error(str(error).replace("v19", "v20")) from error


def _cleanup_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        _v19._cleanup_bundle_stage(stage, identity)
    except _v19.CurrentCoverageV19Error as error:
        raise CurrentCoverageV20Error(str(error).replace("v19", "v20")) from error


def _promote_noreplace(stage: Path, destination: Path) -> None:
    try:
        _v19._promote_noreplace(stage, destination)
    except _v19.CurrentCoverageV19Error as error:
        raise CurrentCoverageV20Error(str(error).replace("v19", "v20")) from error


def write_v20_definition(package_root: str | Path, output_path: str | Path) -> str:
    """Atomically create, but never replace, the canonical v20 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v20_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV20Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _v19._v18._v17._v16._path_identity(stage)
            stage.chmod(0o644)
            _v19._v18._v17._v16._fsync_regular(stage)
            _promote_noreplace(stage, destination)
            _v19._v18._v17._v16._fsync_directory(destination.parent)
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise CurrentCoverageV20Error(
                    "v20 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v20 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v20(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v20 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV20Error("v20 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v20(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV20Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _v19._v18._v17._v16._path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _v19._v18._v17._v16._fsync_regular(stage / filename)
            stage.chmod(0o555)
            _v19._v18._v17._v16._fsync_directory(stage)
            validate_current_coverage_ledger_v20(stage, definition_path=definition_path)
            _promote_noreplace(stage, destination)
            _v19._v18._v17._v16._fsync_directory(destination.parent)
            validate_current_coverage_ledger_v20(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v20 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v20(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = _lexical_absolute(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV20Error("v20 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV20Error("v20 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV20Error("v20 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v20 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v20 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v20 sidecar")
    ledger = _json_object(actual_ledger, "v20 ledger")
    manifest = _json_object(actual_manifest, "v20 manifest")
    if actual_ledger != _canonical_json(ledger):
        raise CurrentCoverageV20Error("v20 ledger is not canonical JSON")
    if actual_manifest != _canonical_json(manifest):
        raise CurrentCoverageV20Error("v20 manifest is not canonical JSON")
    if actual_sidecar != (
        f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise CurrentCoverageV20Error("v20 manifest sidecar differs")
    expected = build_current_coverage_ledger_v20(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV20Error("v20 ledger differs from reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV20Error("v20 manifest differs from reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV20Error("v20 sidecar differs from reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV20Bundle",
    "CurrentCoverageV20Error",
    "NEW_ARTIFACT_IDS",
    "PARITY_GAPS_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_5_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "UNCHANGED_42_SHA256",
    "V19_BASE_LINEAGE",
    "V20_BUNDLE_PATH",
    "V20_DEFINITION_PATH",
    "V20_DEFINITION_SHA256",
    "V20_GENERATED_AT",
    "V20_LEDGER_ID",
    "build_current_coverage_ledger_v20",
    "make_v20_definition",
    "validate_current_coverage_ledger_v20",
    "write_current_coverage_ledger_v20",
    "write_v20_definition",
]
