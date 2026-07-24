"""Governed exact-identity v14 successor over live federation v38.

V14 replaces only the accepted open-seed-v92 source child with open-seed v97.
The 65 newly admitted source records remain 65 singleton exact components and
the 33 explicit project-to-campus declarations remain topology, not identity.
The reviewed Goodman and FIN04 source replacements regenerate source lineage
without changing stable keys or component membership.  Hanoi, Jakarta, and
Oran remain current-status unknown and are not made current by this layer.

The default entry point is a private, two-replay preflight.  Final publication
is reserved, atomic no-replace, descriptor-bound, rollback-capable, and
requires an explicit authorization flag.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import hashlib
import json
import os
import secrets
import stat
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import exact_identity_decisions as legacy
from . import exact_identity_decisions_carrier_v6 as carrier
from . import exact_identity_decisions_v13 as predecessor
from . import federated_release_v6 as federation
from . import (
    federation_v38,
    open_seed_v92,
    open_seed_v93,
    open_seed_v94,
    open_seed_v95,
    open_seed_v96,
    open_seed_v97,
)
from .open_seed_v56 import tree_digest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "2026-07-22-public-open-v14"
RECORDED_AT = "2026-07-24T22:30:00Z"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-22-public-open-v14.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-22-public-open-v14"
PUBLICATION_LOCK = ROOT / ".exact-identity-v14.lock"

PREDECESSOR_DEFINITION = predecessor.DEFINITION
PREDECESSOR_BUNDLE = predecessor.BUNDLE
PREDECESSOR_RECORDED_AT = predecessor.RECORDED_AT
PREDECESSOR_DEFINITION_PIN = predecessor.DEFINITION_PIN
PREDECESSOR_ACCOUNTING_PIN = predecessor.ARTIFACT_PINS["accounting.json"]
PREDECESSOR_MANIFEST_PIN = predecessor.ARTIFACT_PINS["manifest.json"]
PREDECESSOR_TREE_SHA256 = predecessor.BUNDLE_TREE_SHA256

FEDERATION_DEFINITION = federation_v38.DEFINITION
FEDERATION_BUNDLE = federation_v38.INDEX_DIR
FEDERATION_RECORDED_AT = "2026-07-24T20:45:00Z"
FEDERATION_DEFINITION_PIN = (
    1_784,
    "fc0f6985c403b1562f439c2abd31b244a6784f5ed7030edd349c6a8ba92a09fb",
)
FEDERATION_INDEX_PIN = (
    39_744,
    "cb45c67a4286cb8ab8da9b6cdb5ea3733886fe035236c7590de14749aad7d6f0",
)
FEDERATION_MANIFEST_PIN = (
    986,
    "4c8f79ca5a17d9dfb1c02a1f7ee01da62ece19d2c265854b82cb701c8012b453",
)
FEDERATION_SIDECAR_PIN = (
    80,
    "3688d1270615c2e1fc61eb7477db7adcb3d16193dc75ff212af0fac28a99be16",
)
FEDERATION_TREE_SHA256 = (
    "84b7329e7f62da8ebf3e868d8026d03b49b36a8d5290bb0004c34d4518f9a5d5"
)

V92_DEFINITION = open_seed_v92.DEFINITION
V92_RELEASE = open_seed_v92.RELEASE
V97_DEFINITION = open_seed_v97.DEFINITION
V97_RELEASE = open_seed_v97.RELEASE
V97_RECORDED_AT = federation_v38.V97_RECORDED_AT
V97_DEFINITION_PIN = federation_v38.V97_DEFINITION_PIN
V97_MANIFEST_PIN = federation_v38.V97_MANIFEST_PIN
V97_TREE_SHA256 = federation_v38.V97_TREE_SHA256

OLD_RELEASE_ID = predecessor.NEW_RELEASE_ID
NEW_RELEASE_ID = federation_v38.NEW_RELEASE_ID

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_517,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_616,
    "non_review_source_scoped_entity_records": 10_348,
    "raw_topology_links": 2_922,
    "release_candidate_references": 100_414,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_478,
    "unresolved_candidate_references": 100_541,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 33,
    "exact_component_reductions": 0,
    "exact_source_record_components": 65,
    "non_review_source_scoped_entity_records": 65,
    "raw_topology_links": 33,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 65,
    "unresolved_candidate_references": 0,
}
EXPECTED_KIND_COUNTS = {
    "raw_non_review_occurrences_by_kind": {
        "building": 2_355,
        "campus": 679,
        "facility": 6_747,
        "project": 567,
    },
    "exact_source_record_components_by_kind": {
        "building": 1_950,
        "campus": 679,
        "facility": 5_420,
        "project": 567,
    },
    "canonical_topology_links_by_type": {
        "facility_contains_building": 1_950,
        "project_targets": 567,
    },
}

RELEASE_MODULES = {
    "v93": open_seed_v93,
    "v94": open_seed_v94,
    "v95": open_seed_v95,
    "v96": open_seed_v96,
    "v97": open_seed_v97,
}
RELEASE_DELTAS = {
    name: (len(module.ADDED_ENTITY_KEYS), len(module.ADDED_PROJECT_KEYS))
    for name, module in RELEASE_MODULES.items()
}
EXPECTED_RELEASE_DELTAS = {
    "v93": (6, 3),
    "v94": (17, 9),
    "v95": (18, 9),
    "v96": (18, 9),
    "v97": (6, 3),
}
NEW_ENTITY_KEYS = frozenset(
    key for module in RELEASE_MODULES.values() for key in module.ADDED_ENTITY_KEYS
)
NEW_PROJECT_KEYS = frozenset(
    key for module in RELEASE_MODULES.values() for key in module.ADDED_PROJECT_KEYS
)
GOODMAN_KEYS = frozenset(open_seed_v94.GOODMAN_KEYS)
FIN04_KEYS = frozenset(open_seed_v96.FIN04_KEYS)
REPLACED_ENTITY_KEYS = GOODMAN_KEYS | FIN04_KEYS
STALE_CURRENT_UNKNOWN_KEYS = frozenset(
    open_seed_v96.EXPECTED_STALE_PROJECT_KEYS
)
SOURCE_NATIVE_COORDINATE_KEYS = frozenset(
    {
        "curated:northc-aalsmeer-data-center",
        "curated:northc-aalsmeer-data-center:phase-2-first-floor-expansion",
    }
)

SOURCE_REPLACEMENT_CONTRACT = {
    "curated:goodman-lax01-los-angeles-program-anchor": {
        "old_source_family": "goodman_group_investor_presentations",
        "new_source_family": "databank_press_releases",
        "old_snapshot_evidence_id": "e76fe169-8044-5df1-8943-837ec3c34e1b",
        "new_snapshot_evidence_id": "b244ccdf-e6bb-55a0-9048-be08e7fe57fd",
    },
    (
        "curated:goodman-lax01-los-angeles-program-anchor:"
        "first-site-current-development"
    ): {
        "old_source_family": "goodman_group_investor_presentations",
        "new_source_family": "databank_press_releases",
        "old_snapshot_evidence_id": "e76fe169-8044-5df1-8943-837ec3c34e1b",
        "new_snapshot_evidence_id": "b244ccdf-e6bb-55a0-9048-be08e7fe57fd",
    },
    "curated:atnorth-fin04-kouvola-campus": {
        "old_source_family": "atnorth_newsroom",
        "new_source_family": "yit_official_investor_news",
        "old_snapshot_evidence_id": "97ae0303-4e21-5324-a54e-48420a0fba5e",
        "new_snapshot_evidence_id": "a49b85ce-f91a-56b8-af06-3b663336bdf8",
    },
    "curated:atnorth-fin04-kouvola-campus:phase-1": {
        "old_source_family": "atnorth_newsroom",
        "new_source_family": "yit_official_investor_news",
        "old_snapshot_evidence_id": "97ae0303-4e21-5324-a54e-48420a0fba5e",
        "new_snapshot_evidence_id": "a49b85ce-f91a-56b8-af06-3b663336bdf8",
    },
}
SOURCE_REPLACEMENT_FIELD_ALLOWLIST = {
    "curated:goodman-lax01-los-angeles-program-anchor": frozenset(
        {
            "address",
            "snapshot_as_of",
            "snapshot_evidence_id",
            "source_publisher",
            "source_retrieved_at",
            "source_url",
            "tags_json",
        }
    ),
    (
        "curated:goodman-lax01-los-angeles-program-anchor:"
        "first-site-current-development"
    ): frozenset(
        {
            "address",
            "capacity_estimates_json",
            "snapshot_as_of",
            "snapshot_evidence_id",
            "source_publisher",
            "source_retrieved_at",
            "source_url",
            "tags_json",
        }
    ),
    "curated:atnorth-fin04-kouvola-campus": frozenset(
        {
            "snapshot_as_of",
            "snapshot_evidence_id",
            "source_publisher",
            "source_retrieved_at",
            "source_url",
        }
    ),
    "curated:atnorth-fin04-kouvola-campus:phase-1": frozenset(
        {
            "snapshot_as_of",
            "snapshot_evidence_id",
            "source_publisher",
            "source_retrieved_at",
            "source_url",
            "status_as_of",
            "status_evidence_id",
            "tags_json",
        }
    ),
}
LINEAGE_REPLACEMENT_CONTRACT = {
    "atnorth_newsroom": (4, 2),
    "cirion_pressroom": (2, 3),
    "edgeconnex_press_releases": (4, 6),
    "goodman_group_investor_presentations": (16, 14),
}
NEW_LINEAGE_FAMILIES = frozenset(
    {
        "algerian_radio_official_news",
        "beale_infrastructure_official_location",
        "beale_infrastructure_official_news",
        "bitzero_newsfile_releases",
        "bravida_official_press_release",
        "centra_official_linkedin_company_posts",
        "cirion_current_facility_pages",
        "cmc_corporation_annual_reports",
        "cmc_corporation_official_releases_archived",
        "ctrls_current_location_pages",
        "cyrusone_official_linkedin",
        "cyrusone_official_press_release",
        "damac_group_official_press_releases_archived",
        "databank_press_releases",
        "gulf_data_hub_official_location_pages",
        "hut8_sec_exhibits",
        "intersect_power_portfolio",
        "merlin_properties_official_news",
        "michigan_city_economic_development",
        "neutradc_official_news_archived",
        "nscale_press_releases",
        "nxdata3_project_pages",
        "pdok_locatieserver_bag",
        "pima_county_official_environmental_record",
        "sec_edgar_bitdeer_exhibit",
        "sec_edgar_iren_exhibits",
        "sentia_official_press_release",
        "serc_board_materials",
        "skygard_official_facility_page",
        "square_engineering_project_pages",
        "vietnam_government_portal_news",
        "yit_official_investor_news",
    }
)

REJECTED_LINEAGE_TOKENS = predecessor.REJECTED_LINEAGE_TOKENS
SUPERSEDED_LINEAGE_TOKENS = (
    *predecessor.SUPERSEDED_LINEAGE_TOKENS,
    b"2026-07-21-public-open-v37",
    b"epoch-official-open-seed-v92",
    b"2026-07-21-open-seed-v92",
    b"2026-07-21-public-open-v13",
)
PEERINGDB_FORBIDDEN = b"peeringdb"

DEFINITION_PIN: tuple[int, str] | None = (
    1_732,
    "2efe24eaff33a91d210f3139a66b9538fb1768e9d8695e1f9ddebddd6d1475f1",
)
ARTIFACT_PINS: dict[str, tuple[int, str]] = {
    "ATTRIBUTION.txt": (
        9_238,
        "fad33acea95263d4a5627ba8f95b865eedf14dea2248f60a2b4d65310224d694",
    ),
    "README.md": (
        629,
        "3d11f54e8686a23226d57254b99270f05bbfb6c09c8f0c6c58481827d4284617",
    ),
    "accounting.json": (
        981,
        "64ddd90c08aa13297ee88d62776de41177a90099fc2a21d3a26b4276609819bf",
    ),
    "component-members.csv": (
        3_744_672,
        "6f0c133c7710fe0a6d96fdad078d25c1cec0d858ef5f159abb890d518fb3ae25",
    ),
    "manifest.json": (
        11_440,
        "268b064077e82ab5b3d90459234770743838b22cc90a72021b96f788d4947ba4",
    ),
    "manifest.sha256": (
        80,
        "f292016246c741939c97102b11f32c51113033425eb60a6fcf11de4e5f5fb60e",
    ),
    "relationships.csv": (
        965_327,
        "e8bae6b1893e621066b4974390665ff322a5f625e9b11f98db6438c9adb08ef7",
    ),
    "source-lineage.csv": (
        50_601,
        "d9ebdeae525716bd47c65e14fa030d175d9e8c0fe29f8e94ad962557199fec66",
    ),
    "unresolved-candidate-references.csv": (
        38_421_580,
        "1f2c14b484f948b0f4bfbaf339b0527d5cd1d385dda41f8f66f63183ce7a0a1b",
    ),
}
BUNDLE_TREE_SHA256: str | None = (
    "1a4c733425316103ea50c24e83617a38bb339d927f45f13c470937356d20b0ac"
)
CODE_PINS = {
    "exact_identity_decisions.py": (
        76_330,
        "8c5d7fd14575d7f6afdb280144868534c9934753e96658498200a15833ccdfe1",
    ),
    "exact_identity_decisions_carrier_v5.py": (
        21_401,
        "6d99281d256d1fb33b256794c151a52bc9515a1b2398ca4b57b1434537b3698b",
    ),
    "exact_identity_decisions_carrier_v6.py": (
        14_091,
        "01152110b98defc2feacb1fa900e5a666b5b633a7fd809c19ffe0dc3f9c71d8e",
    ),
    "exact_identity_decisions_v13.py": (
        54_161,
        "c29ccc3cc4e21d05c504aea6d0283834e89b71dd5646e3310707e084f5055e7e",
    ),
    "federated_release_v3.py": (
        26_524,
        "e8504ca3bba1f201085579df20ec0cde4ebd700284e402f5104b656dd7c24528",
    ),
    "federated_release_v4.py": (
        17_669,
        "af10b118a5941b7d9b021bb7301d58082ac738160afc9a6dc1101213192f516a",
    ),
    "federated_release_v5.py": (
        13_330,
        "b2984555b053d0de64cac0e747fcec02e5ee133983ccf23a44f369e897b1f851",
    ),
    "federated_release_v6.py": (
        13_001,
        "6f420a96b8c24639d2ea748948d6bedaf02a0025255bdb285c601d8f2844371a",
    ),
    "federation_v38.py": (
        89_517,
        "de252de45f9544856e6c7ec78edb5cd04840492c02d054a63bcfd562f08fedf9",
    ),
    "global_snapshot.py": (
        25_282,
        "10eb78e03335b097ad4d43ecda97ef9f109e57217fee3117e6bc6fac630ecef0",
    ),
    "open_seed_v56.py": (
        25_343,
        "3349ba9ef81dfdbaba07e0c8b5b5e83642aed93442ca0aaf0dcdcc0b406a4f1c",
    ),
    "open_seed_v92.py": (
        69_392,
        "93a3ba71eac30f455a5d5258096b236e3078c4ec75400e141f6e6b1803c56b7a",
    ),
    "open_seed_v93.py": (
        73_366,
        "eea98c7da445c3ea7106af77b266a5deb013533a154bea837cccbb6a3ba5dfe2",
    ),
    "open_seed_v94.py": (
        97_187,
        "b5699e0e001a96255d4a38b9d199d77d837272e5a792f5584b9575fc31b378fb",
    ),
    "open_seed_v95.py": (
        80_379,
        "f10a6cf6e06e432bd0b660cbfcb3452603a60f2b9f8ad5cff55c67c62e3f923d",
    ),
    "open_seed_v96.py": (
        110_920,
        "d65711ef0a40216db8a811626369018df6f7216f0f54e49170663bcb9f50e9e1",
    ),
    "open_seed_v97.py": (
        88_620,
        "47ac8cacfebf6a9179be22db5368aae5066faf14e47e3bbd591208f331958466",
    ),
}

ACCOUNTING_FILENAME = carrier.ACCOUNTING_FILENAME
ATTRIBUTION_FILENAME = carrier.ATTRIBUTION_FILENAME
BUNDLE_FILES = carrier.BUNDLE_FILES
BUNDLE_FORMAT = carrier.BUNDLE_FORMAT
COMPONENTS_FILENAME = carrier.COMPONENTS_FILENAME
DEFINITION_FORMAT = carrier.DEFINITION_FORMAT
LINEAGE_FILENAME = carrier.LINEAGE_FILENAME
MANIFEST_FILENAME = carrier.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = carrier.MANIFEST_HASH_FILENAME
POLICY = carrier.POLICY
README_FILENAME = carrier.README_FILENAME
RELATIONSHIPS_FILENAME = carrier.RELATIONSHIPS_FILENAME
UNRESOLVED_FILENAME = carrier.UNRESOLVED_FILENAME
ExactIdentityDecisionError = carrier.ExactIdentityDecisionError

FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIRECTORY_MODE = 0o700
PROMOTION_CONTRACT = {
    "atomic_no_replace_required": True,
    "descriptor_bound_creation_required": True,
    "descriptor_bound_cleanup_required": True,
    "directory_descriptor_bound_rename_required": True,
    "existing_identical_checked_inside_lock": True,
    "identity_checked_before_and_after_promotion": True,
    "rollback_covers_final_validation_and_result_construction": True,
    "rollback_uses_atomic_no_replace": True,
    "stage_adoption_allowed": False,
    "replay_count": 2,
}

_canonical_json = predecessor._canonical_json
_wall_clock = predecessor._wall_clock
_parsed_timestamp = predecessor._parsed_timestamp
_regular_document = predecessor._regular_document
_path_timestamp_bounds = predecessor._path_timestamp_bounds
_final_root_ctime = predecessor._final_root_ctime

ParentBindings = Mapping[str, tuple[Path, tuple[int, int], int]]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_pin(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _target_timestamp(recorded_at: str | None) -> tuple[str, datetime]:
    value = recorded_at if recorded_at is not None else RECORDED_AT
    if value is None:
        raise ExactIdentityDecisionError(
            "identity v14 recorded_at is not frozen; pass --recorded-at for preflight"
        )
    target = _parsed_timestamp(value, "identity v14 recorded_at")
    if target <= _parsed_timestamp(
        FEDERATION_RECORDED_AT, "federation v38 generated_at"
    ):
        raise ExactIdentityDecisionError(
            "identity v14 recorded_at must follow live federation v38"
        )
    if RECORDED_AT is not None and value != RECORDED_AT:
        raise ExactIdentityDecisionError("identity v14 recorded_at is fixed")
    return value, target


def _definition_document(recorded_at: str) -> dict[str, Any]:
    predecessor_document, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v13 definition"
    )
    result = deepcopy(predecessor_document)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = recorded_at
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_PIN[1],
        "expected_manifest_sha256": FEDERATION_MANIFEST_PIN[1],
        "index_path": "../federated_indexes/2026-07-22-public-open-v38",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError("accepted identity v13 seed child changed")
    old_children[0].update(
        {
            "expected_manifest_sha256": V97_MANIFEST_PIN[1],
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-22-open-seed-v97",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _definition_object(
    document: Mapping[str, Any],
    raw: bytes,
    *,
    recorded_at: str,
    logical_path: Path = DEFINITION,
) -> legacy._Definition:
    expected = _definition_document(recorded_at)
    if document != expected or raw != _canonical_json(expected):
        raise ExactIdentityDecisionError(
            "identity v14 definition is not the exact v13 structural successor"
        )
    _assert_forbidden_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v14 child path must be relative")
        children.append(
            {**child, "release_path": (logical_path.parent / relative).resolve()}
        )
    return legacy._Definition(
        path=logical_path.resolve(),
        raw=raw,
        bundle_id=BUNDLE_ID,
        recorded_at=recorded_at,
        federation=dict(document["federation"]),
        children=tuple(sorted(children, key=lambda item: item["release_id"])),
        expected=dict(EXPECTED_COUNTS),
    )


def _assert_forbidden_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        if PEERINGDB_FORBIDDEN in raw.lower():
            raise ExactIdentityDecisionError(
                f"PeeringDB is forbidden from identity v14 {name}"
            )
        for token in (*REJECTED_LINEAGE_TOKENS, *SUPERSEDED_LINEAGE_TOKENS):
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"forbidden lineage token in identity v14 {name}: "
                    f"{token.decode('ascii')}"
                )


def _guard_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "predecessor_definition": _file_pin(PREDECESSOR_DEFINITION),
        "predecessor_accounting": _file_pin(
            PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME
        ),
        "predecessor_manifest": _file_pin(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
        "predecessor_tree": tree_digest(PREDECESSOR_BUNDLE),
        "federation_definition": _file_pin(FEDERATION_DEFINITION),
        "federation_index": _file_pin(
            FEDERATION_BUNDLE / federation.INDEX_FILENAME
        ),
        "federation_manifest": _file_pin(
            FEDERATION_BUNDLE / MANIFEST_FILENAME
        ),
        "federation_sidecar": _file_pin(
            FEDERATION_BUNDLE / MANIFEST_HASH_FILENAME
        ),
        "federation_tree": tree_digest(FEDERATION_BUNDLE),
        "v97_definition": _file_pin(V97_DEFINITION),
        "v97_manifest": _file_pin(V97_RELEASE / MANIFEST_FILENAME),
        "v97_tree": tree_digest(V97_RELEASE),
    }
    code_root = ROOT / "datacenter_atlas"
    state.update(
        {f"code:{name}": _file_pin(code_root / name) for name in CODE_PINS}
    )
    return state


def _reviewed_guard_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "predecessor_definition": PREDECESSOR_DEFINITION_PIN,
        "predecessor_accounting": PREDECESSOR_ACCOUNTING_PIN,
        "predecessor_manifest": PREDECESSOR_MANIFEST_PIN,
        "predecessor_tree": PREDECESSOR_TREE_SHA256,
        "federation_definition": FEDERATION_DEFINITION_PIN,
        "federation_index": FEDERATION_INDEX_PIN,
        "federation_manifest": FEDERATION_MANIFEST_PIN,
        "federation_sidecar": FEDERATION_SIDECAR_PIN,
        "federation_tree": FEDERATION_TREE_SHA256,
        "v97_definition": V97_DEFINITION_PIN,
        "v97_manifest": V97_MANIFEST_PIN,
        "v97_tree": V97_TREE_SHA256,
    }
    state.update({f"code:{name}": pin for name, pin in CODE_PINS.items()})
    return state


def _require_guard_state() -> dict[str, Any]:
    try:
        predecessor.validate_exact_identity_decision_bundle()
        federation_v38.validate_federation_v38()
        open_seed_v97.validate_open_seed_v97()
    except (
        OSError,
        predecessor.ExactIdentityDecisionError,
        federation_v38.FederationV38Error,
        open_seed_v97.OpenSeedV97Error,
    ) as error:
        raise ExactIdentityDecisionError(
            f"accepted identity-v14 input validation failed: {error}"
        ) from error
    actual = _guard_state()
    expected = _reviewed_guard_state()
    if actual != expected:
        differing = sorted(
            key for key in expected if actual.get(key) != expected.get(key)
        )
        raise ExactIdentityDecisionError(
            "accepted identity-v14 input pin drift: " + ", ".join(differing)
        )
    return actual


def _release_for_new_key() -> dict[str, str]:
    if RELEASE_DELTAS != EXPECTED_RELEASE_DELTAS:
        raise ExactIdentityDecisionError("v93-v97 governed release deltas differ")
    release_for: dict[str, str] = {}
    for name, module in RELEASE_MODULES.items():
        for key in module.ADDED_ENTITY_KEYS:
            if key in release_for:
                raise ExactIdentityDecisionError(
                    "v93-v97 admitted entity sets overlap"
                )
            release_for[key] = name
    if (
        set(release_for) != NEW_ENTITY_KEYS
        or len(NEW_ENTITY_KEYS) != 65
        or len(NEW_PROJECT_KEYS) != 33
        or set(SOURCE_REPLACEMENT_CONTRACT) != REPLACED_ENTITY_KEYS
        or GOODMAN_KEYS & FIN04_KEYS
    ):
        raise ExactIdentityDecisionError("identity v14 governed key inventory differs")
    return release_for


def _source_entity_inventory() -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    _release_for_new_key()
    previous_rows = {
        row["entity_id"]: row
        for row in _csv_rows(V92_RELEASE / "entities.csv")
    }
    current_rows = {
        row["entity_id"]: row
        for row in _csv_rows(V97_RELEASE / "entities.csv")
    }
    if (
        len(previous_rows) != 988
        or len(current_rows) != 1_053
        or set(previous_rows) - set(current_rows)
    ):
        raise ExactIdentityDecisionError(
            "v92-to-v97 source-record inventory is not append-only"
        )
    added_ids = set(current_rows) - set(previous_rows)
    if (
        len(added_ids) != 65
        or {current_rows[entity_id]["stable_key"] for entity_id in added_ids}
        != NEW_ENTITY_KEYS
    ):
        raise ExactIdentityDecisionError("v97 exact added-record inventory differs")

    changed: dict[str, frozenset[str]] = {}
    for entity_id in set(previous_rows) & set(current_rows):
        previous_row = previous_rows[entity_id]
        current_row = current_rows[entity_id]
        fields = frozenset(
            field
            for field in previous_row
            if previous_row[field] != current_row[field]
        )
        if fields:
            changed[current_row["stable_key"]] = fields
    if changed != SOURCE_REPLACEMENT_FIELD_ALLOWLIST:
        raise ExactIdentityDecisionError(
            "Goodman/FIN04 exact source-replacement field allowlist differs"
        )

    for key, contract in SOURCE_REPLACEMENT_CONTRACT.items():
        old = next(row for row in previous_rows.values() if row["stable_key"] == key)
        new = current_rows[old["entity_id"]]
        if (
            old["snapshot_evidence_id"]
            != contract["old_snapshot_evidence_id"]
            or new["snapshot_evidence_id"]
            != contract["new_snapshot_evidence_id"]
        ):
            raise ExactIdentityDecisionError(
                f"source replacement evidence differs: {key}"
            )

    geojson = json.loads((V97_RELEASE / "atlas.geojson").read_text())
    features_by_id = {feature["id"]: feature for feature in geojson["features"]}
    if len(features_by_id) != 1_053:
        raise ExactIdentityDecisionError("v97 feature inventory differs")
    added_features = {
        current_rows[entity_id]["stable_key"]: features_by_id[entity_id]
        for entity_id in added_ids
    }
    if set(added_features) != NEW_ENTITY_KEYS:
        raise ExactIdentityDecisionError("v97 added-feature inventory differs")
    observed_coordinate_keys = set()
    for key, feature in added_features.items():
        properties = feature["properties"]
        has_coordinates = (
            feature.get("geometry") is not None
            or properties.get("latitude") is not None
            or properties.get("longitude") is not None
        )
        if has_coordinates:
            observed_coordinate_keys.add(key)
        if (
            properties.get("stable_key") != key
            or properties.get("entity_kind") not in {"campus", "project"}
        ):
            raise ExactIdentityDecisionError(
                f"v97 added identity boundary differs: {key}"
            )
    if observed_coordinate_keys != SOURCE_NATIVE_COORDINATE_KEYS:
        raise ExactIdentityDecisionError(
            "v97 source-native coordinate allowlist differs"
        )

    targets: dict[str, str] = {}
    for key, feature in added_features.items():
        properties = feature["properties"]
        target_id = properties.get("target_entity_id")
        if key in NEW_PROJECT_KEYS:
            if (
                properties["entity_kind"] != "project"
                or not isinstance(target_id, str)
                or target_id not in features_by_id
                or features_by_id[target_id]["properties"]["entity_kind"] != "campus"
            ):
                raise ExactIdentityDecisionError(
                    f"v97 explicit project target differs: {key}"
                )
            targets[key] = features_by_id[target_id]["properties"]["stable_key"]
        elif properties["entity_kind"] != "campus" or target_id is not None:
            raise ExactIdentityDecisionError(f"v97 admitted entity kind differs: {key}")
    if len(targets) != 33:
        raise ExactIdentityDecisionError(
            "v97 explicit project-target inventory differs"
        )

    freshness = {
        row["stable_key"]: row
        for row in _csv_rows(V97_RELEASE / "lifecycle_freshness.csv")
    }
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(V97_RELEASE / "construction_pipeline.csv")
    }
    if not STALE_CURRENT_UNKNOWN_KEYS <= set(freshness):
        raise ExactIdentityDecisionError(
            "stale current-unknown lifecycle inventory differs"
        )
    for key in STALE_CURRENT_UNKNOWN_KEYS:
        row = next(item for item in current_rows.values() if item["stable_key"] == key)
        feature = features_by_id[row["entity_id"]]["properties"]
        if (
            row["status"]
            or row["status_as_of"]
            or row["status_evidence_id"]
            or feature.get("status") is not None
            or feature.get("status_as_of") is not None
            or feature.get("status_evidence_id") is not None
            or key in pipeline
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 inferred current status for stale project: {key}"
            )
    return previous_rows, current_rows, added_features, targets


def _component_inventory(
    bundle: Path,
) -> tuple[
    dict[str, str],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    previous_source, current_source, features, _targets = _source_entity_inventory()
    previous = _csv_rows(PREDECESSOR_BUNDLE / COMPONENTS_FILENAME)
    current = _csv_rows(bundle / COMPONENTS_FILENAME)
    previous_open = [row for row in previous if row["release_id"] == OLD_RELEASE_ID]
    current_open = [row for row in current if row["release_id"] == NEW_RELEASE_ID]
    if len(previous_open) != 988 or len(current_open) != 1_053:
        raise ExactIdentityDecisionError(
            "identity v14 replaced-record count differs"
        )
    previous_by_entity = {row["entity_id"]: row for row in previous_open}
    current_by_entity = {row["entity_id"]: row for row in current_open}
    added_ids = set(current_by_entity) - set(previous_by_entity)
    if (
        added_ids != {feature["id"] for feature in features.values()}
        or set(previous_by_entity) - set(current_by_entity)
    ):
        raise ExactIdentityDecisionError(
            "identity v14 exact new-record inventory differs"
        )

    unaffected_previous = [
        row for row in previous if row["release_id"] != OLD_RELEASE_ID
    ]
    unaffected_current = [
        row for row in current if row["release_id"] != NEW_RELEASE_ID
    ]
    if unaffected_current != unaffected_previous:
        raise ExactIdentityDecisionError(
            "identity v14 non-open component bytes or order changed"
        )

    dependent = {"component_id", "occurrence_id", "release_id"}
    ordered_inherited = [
        row["entity_id"] for row in current_open if row["entity_id"] not in added_ids
    ]
    if ordered_inherited != [row["entity_id"] for row in previous_open]:
        raise ExactIdentityDecisionError(
            "identity v14 inherited open-record order changed"
        )
    for entity_id, old in previous_by_entity.items():
        new = current_by_entity[entity_id]
        key = new["stable_key"]
        old_nondependent = {
            field: value for field, value in old.items() if field not in dependent
        }
        new_nondependent = {
            field: value for field, value in new.items() if field not in dependent
        }
        if key in SOURCE_REPLACEMENT_CONTRACT:
            contract = SOURCE_REPLACEMENT_CONTRACT[key]
            expected = {
                **old_nondependent,
                "source_family": contract["new_source_family"],
                "source_root": contract["new_source_family"],
                "snapshot_evidence_id": contract["new_snapshot_evidence_id"],
            }
            if (
                old["source_family"] != contract["old_source_family"]
                or old["source_root"] != contract["old_source_family"]
                or old["snapshot_evidence_id"]
                != contract["old_snapshot_evidence_id"]
                or new_nondependent != expected
            ):
                raise ExactIdentityDecisionError(
                    f"identity v14 source replacement changed identity: {key}"
                )
        elif new_nondependent != old_nondependent:
            raise ExactIdentityDecisionError(
                f"identity v14 inherited source-record decision changed: {key}"
            )
        expected_occurrence = f"{NEW_RELEASE_ID}:{entity_id}"
        if (
            new["occurrence_id"] != expected_occurrence
            or new["component_id"]
            != legacy._component_id(new["entity_kind"], [expected_occurrence])
            or new["component_member_count"] != "1"
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 inherited singleton differs: {key}"
            )
        source_key = current_source[entity_id]["stable_key"]
        if source_key != key or previous_source[entity_id]["stable_key"] != key:
            raise ExactIdentityDecisionError(
                f"identity v14 stable-key lineage differs: {key}"
            )

    component_for: dict[str, str] = {}
    for entity_id in added_ids:
        row = current_by_entity[entity_id]
        key = row["stable_key"]
        feature = features[key]
        expected_occurrence = f"{NEW_RELEASE_ID}:{entity_id}"
        if (
            row["entity_kind"] != feature["properties"]["entity_kind"]
            or row["snapshot_evidence_id"]
            != feature["properties"]["snapshot_evidence_id"]
            or row["source_family"] != feature["properties"]["source_family"]
            or row["occurrence_id"] != expected_occurrence
            or row["component_id"]
            != legacy._component_id(row["entity_kind"], [expected_occurrence])
            or row["component_member_count"] != "1"
            or row["identity_proof_parent_occurrence_id"]
            or row["identity_proof_token"]
            or row["typed_identity_tokens_json"] != "[]"
            or row["ambiguous_identity_tokens_json"] != "[]"
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 new singleton differs: {key}"
            )
        component_for[entity_id] = row["component_id"]
    if len(set(component_for.values())) != 65:
        raise ExactIdentityDecisionError("identity v14 merged a new source record")
    return component_for, previous, current


def _component_semantics(
    rows: list[dict[str, str]], *, normalize_open_release: bool
) -> dict[str, tuple[str, ...]]:
    members: dict[str, list[str]] = {}
    for row in rows:
        release_id = row["release_id"]
        if normalize_open_release and release_id in {OLD_RELEASE_ID, NEW_RELEASE_ID}:
            release_id = "<open-seed-successor>"
        members.setdefault(row["component_id"], []).append(
            f"{release_id}:{row['entity_id']}:{row['stable_key']}:{row['entity_kind']}"
        )
    return {
        component_id: tuple(sorted(values))
        for component_id, values in members.items()
    }


def _relationship_semantics(
    rows: list[dict[str, str]],
    components: Mapping[str, tuple[str, ...]],
) -> list[tuple[Any, ...]]:
    result = []
    for row in rows:
        releases = [
            "<open-seed-successor>"
            if release in {OLD_RELEASE_ID, NEW_RELEASE_ID}
            else release
            for release in json.loads(row["source_release_ids_json"])
        ]
        result.append(
            (
                row["relationship_type"],
                components[row["subject_component_id"]],
                row["subject_kind"],
                components[row["object_component_id"]],
                row["object_kind"],
                row["decision_basis"],
                row["typed_identity_tokens_json"],
                tuple(sorted(releases)),
                row["raw_relationship_count"],
            )
        )
    return sorted(result)


def _validate_relationship_delta(
    bundle: Path,
    new_components: Mapping[str, str],
    previous_components: list[dict[str, str]],
    current_components: list[dict[str, str]],
) -> None:
    _previous_source, _current_source, features, targets = _source_entity_inventory()
    previous_rows = _csv_rows(PREDECESSOR_BUNDLE / RELATIONSHIPS_FILENAME)
    current_rows = _csv_rows(bundle / RELATIONSHIPS_FILENAME)
    previous_semantics = _relationship_semantics(
        previous_rows,
        _component_semantics(previous_components, normalize_open_release=True),
    )
    current_component_semantics = _component_semantics(
        current_components, normalize_open_release=True
    )
    current_semantics = _relationship_semantics(
        current_rows, current_component_semantics
    )

    added_subjects = {
        current_component_semantics[new_components[features[key]["id"]]]
        for key in NEW_PROJECT_KEYS
    }
    added_semantics = [
        row for row in current_semantics if row[1] in added_subjects
    ]
    inherited_semantics = [
        row for row in current_semantics if row[1] not in added_subjects
    ]
    if inherited_semantics != previous_semantics or len(added_semantics) != 33:
        raise ExactIdentityDecisionError(
            "identity v14 inherited/new relationship semantics differ"
        )
    expected_pairs = {
        (
            new_components[features[project_key]["id"]],
            new_components[features[project_key]["properties"]["target_entity_id"]],
        )
        for project_key in targets
    }
    actual_pairs = {
        (row["subject_component_id"], row["object_component_id"])
        for row in current_rows
        if row["subject_component_id"] in {pair[0] for pair in expected_pairs}
    }
    if actual_pairs != expected_pairs:
        raise ExactIdentityDecisionError(
            "identity v14 explicit project-target edges differ"
        )
    for row in current_rows:
        if row["subject_component_id"] in {pair[0] for pair in expected_pairs} and (
            row["relationship_type"] != "project_targets"
            or row["decision_basis"] != "explicit_parent"
            or row["typed_identity_tokens_json"] != "[]"
            or row["source_release_ids_json"]
            != json.dumps([NEW_RELEASE_ID], separators=(",", ":"))
            or row["raw_relationship_count"] != "1"
        ):
            raise ExactIdentityDecisionError(
                "identity v14 new relationship proof differs"
            )


def _candidate_semantics(
    row: Mapping[str, str],
    component_rows: Mapping[str, str],
) -> tuple[Any, ...]:
    release = row["release_id"]
    if release in {OLD_RELEASE_ID, NEW_RELEASE_ID}:
        release = "<open-seed-successor>"

    def occurrence(value: str) -> str:
        if not value:
            return ""
        release_id, entity_id = value.split(":", 1)
        normalized_release = (
            "<open-seed-successor>"
            if release_id in {OLD_RELEASE_ID, NEW_RELEASE_ID}
            else release_id
        )
        stable_key = component_rows.get(f"{release_id}:{entity_id}", entity_id)
        return f"{normalized_release}:{stable_key}"

    return (
        row["origin"],
        release,
        occurrence(row["left_occurrence_id"]),
        occurrence(row["right_occurrence_id"]),
        row["relationship_suggestion"],
        row["disposition"],
        row["reason"],
        row["typed_identity_token"],
        row["source_artifact"],
        row["source_sha256"],
    )


def _validate_unresolved_delta(
    bundle: Path,
    previous_components: list[dict[str, str]],
    current_components: list[dict[str, str]],
) -> None:
    previous = _csv_rows(PREDECESSOR_BUNDLE / UNRESOLVED_FILENAME)
    current = _csv_rows(bundle / UNRESOLVED_FILENAME)
    previous_keys = {
        row["occurrence_id"]: row["stable_key"] for row in previous_components
    }
    current_keys = {
        row["occurrence_id"]: row["stable_key"] for row in current_components
    }
    previous_semantics = sorted(
        _candidate_semantics(row, previous_keys) for row in previous
    )
    current_semantics = sorted(
        _candidate_semantics(row, current_keys) for row in current
    )
    if current_semantics != previous_semantics:
        raise ExactIdentityDecisionError(
            "identity v14 unresolved-candidate semantics changed"
        )
    open_rows = [row for row in current if row["release_id"] == NEW_RELEASE_ID]
    if (
        len(open_rows) != 9
        or any(row["origin"] != "release_resolution_candidate" for row in open_rows)
        or (V92_RELEASE / "resolution_candidates.json").read_bytes()
        != (V97_RELEASE / "resolution_candidates.json").read_bytes()
    ):
        raise ExactIdentityDecisionError(
            "identity v14 release-candidate inventory differs"
        )


def _validate_lineage_delta(bundle: Path) -> None:
    previous = _csv_rows(PREDECESSOR_BUNDLE / LINEAGE_FILENAME)
    current = _csv_rows(bundle / LINEAGE_FILENAME)
    if (
        [row for row in previous if row["release_id"] != OLD_RELEASE_ID]
        != [row for row in current if row["release_id"] != NEW_RELEASE_ID]
    ):
        raise ExactIdentityDecisionError(
            "identity v14 non-open lineage bytes or order changed"
        )
    previous_open = {
        row["source_family"]: row
        for row in previous
        if row["release_id"] == OLD_RELEASE_ID
    }
    current_open = {
        row["source_family"]: row
        for row in current
        if row["release_id"] == NEW_RELEASE_ID
    }
    if (
        len(previous_open) != 312
        or len(current_open) != 344
        or set(current_open) - set(previous_open) != NEW_LINEAGE_FAMILIES
        or set(previous_open) - set(current_open)
    ):
        raise ExactIdentityDecisionError(
            "identity v14 lineage family inventory differs"
        )

    component_rows = [
        row
        for row in _csv_rows(bundle / COMPONENTS_FILENAME)
        if row["release_id"] == NEW_RELEASE_ID
    ]
    by_family: dict[str, list[dict[str, str]]] = {}
    for row in component_rows:
        by_family.setdefault(row["source_family"], []).append(row)
    for family, row in current_open.items():
        members = by_family.get(family, [])
        if (
            row["occurrence_count"] != str(len(members))
            or row["exact_component_count"]
            != str(len({member["component_id"] for member in members}))
            or {member["source_root"] for member in members} != {row["source_root"]}
            or not json.loads(row["publisher_roots_json"])
            or row["independence_claim_allowed"] != "False"
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 regenerated lineage differs: {family}"
            )
        if family in previous_open and family not in LINEAGE_REPLACEMENT_CONTRACT:
            old = previous_open[family]
            comparable_old = {**old, "release_id": NEW_RELEASE_ID}
            if row != comparable_old:
                raise ExactIdentityDecisionError(
                    f"identity v14 unrelated lineage changed: {family}"
                )
    for family, (old_count, new_count) in LINEAGE_REPLACEMENT_CONTRACT.items():
        if (
            int(previous_open[family]["occurrence_count"]) != old_count
            or int(current_open[family]["occurrence_count"]) != new_count
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 source-replacement lineage differs: {family}"
            )


def _validate_decision_delta(bundle: Path) -> None:
    new_components, previous_components, current_components = _component_inventory(
        bundle
    )
    _validate_relationship_delta(
        bundle,
        new_components,
        previous_components,
        current_components,
    )
    _validate_unresolved_delta(bundle, previous_components, current_components)
    _validate_lineage_delta(bundle)

    accounting = json.loads((bundle / ACCOUNTING_FILENAME).read_text())
    predecessor_accounting = json.loads(
        (PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME).read_text()
    )
    if any(
        accounting[key] - predecessor_accounting[key] != delta
        for key, delta in EXPECTED_DELTA.items()
    ):
        raise ExactIdentityDecisionError("identity v14 accounting delta differs")
    if any(accounting[key] != value for key, value in EXPECTED_KIND_COUNTS.items()):
        raise ExactIdentityDecisionError(
            "identity v14 conservative kind accounting differs"
        )
    if any(
        accounting[field] is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError(
            "identity v14 physical-site accounting must remain null"
        )


def _prepare_payloads(
    recorded_at: str,
) -> tuple[bytes, dict[str, bytes], dict[str, Any], legacy._Definition]:
    document = _definition_document(recorded_at)
    raw = _canonical_json(document)
    definition = _definition_object(
        document, raw, recorded_at=recorded_at, logical_path=DEFINITION
    )
    first_payloads, first_manifest = carrier._prepare_bundle(definition)
    second_payloads, second_manifest = carrier._prepare_bundle(definition)
    if first_payloads != second_payloads or first_manifest != second_manifest:
        raise ExactIdentityDecisionError(
            "identity v14 inputs changed or two offline reconstructions differ"
        )
    _assert_forbidden_lineage_absent({DEFINITION.name: raw, **first_payloads})
    if first_manifest["counts"] != {
        **json.loads(first_payloads[ACCOUNTING_FILENAME]),
    }:
        raise ExactIdentityDecisionError("identity v14 manifest accounting differs")
    return raw, first_payloads, first_manifest, definition


def _validate_bundle_container(
    bundle: Path, *, require_frozen: bool
) -> dict[str, Any]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError(
            "identity v14 bundle must be a regular directory"
        )
    entries = {entry.name: entry for entry in bundle.iterdir()}
    if set(entries) != set(BUNDLE_FILES):
        raise ExactIdentityDecisionError(
            "identity v14 bundle file inventory differs"
        )
    for name, entry in entries.items():
        if entry.is_symlink() or not entry.is_file():
            raise ExactIdentityDecisionError(
                f"identity v14 bundle member is not a regular file: {name}"
            )
        if (
            require_frozen
            and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 bundle member mode differs: {name}"
            )
    if (
        require_frozen
        and stat.S_IMODE(bundle.stat().st_mode) != FROZEN_DIRECTORY_MODE
    ):
        raise ExactIdentityDecisionError(
            "identity v14 bundle directory mode differs"
        )
    manifest_raw = entries[MANIFEST_FILENAME].read_bytes()
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise ExactIdentityDecisionError(
            "identity v14 manifest is not valid JSON"
        ) from error
    if not isinstance(manifest, dict) or manifest_raw != _canonical_json(manifest):
        raise ExactIdentityDecisionError(
            "identity v14 manifest is not canonical JSON"
        )
    sidecar = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if entries[MANIFEST_HASH_FILENAME].read_bytes() != sidecar:
        raise ExactIdentityDecisionError(
            "identity v14 manifest sidecar differs"
        )
    file_records = manifest.get("files")
    payload_names = set(BUNDLE_FILES) - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    if not isinstance(file_records, dict) or set(file_records) != payload_names:
        raise ExactIdentityDecisionError(
            "identity v14 manifest file inventory differs"
        )
    for name in payload_names:
        raw = entries[name].read_bytes()
        if file_records[name] != {"bytes": len(raw), "sha256": _sha256(raw)}:
            raise ExactIdentityDecisionError(
                f"identity v14 manifest file checkpoint differs: {name}"
            )
    return manifest


def _validate_payload_bundle(
    definition_raw: bytes,
    bundle: Path,
    *,
    recorded_at: str,
    require_frozen: bool,
    verify_inputs: bool,
) -> dict[str, Any]:
    document = json.loads(definition_raw)
    definition = _definition_object(
        document,
        definition_raw,
        recorded_at=recorded_at,
        logical_path=DEFINITION,
    )
    if _parsed_timestamp(
        recorded_at, "identity v14 recorded_at"
    ) > datetime.now(UTC):
        manifest = _validate_bundle_container(
            bundle, require_frozen=require_frozen
        )
    else:
        manifest = carrier.validate_exact_identity_decision_bundle(
            bundle, require_frozen=require_frozen
        )
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if verify_inputs:
        expected_payloads, expected_manifest = carrier._prepare_bundle(definition)
        replay_payloads, replay_manifest = carrier._prepare_bundle(definition)
        if (
            expected_payloads != replay_payloads
            or expected_manifest != replay_manifest
            or actual_payloads != expected_payloads
            or manifest != expected_manifest
        ):
            raise ExactIdentityDecisionError(
                "identity v14 bundle differs from two exact replays"
            )
    if (
        manifest.get("bundle_id") != BUNDLE_ID
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("counts") is None
        or any(
            manifest["counts"].get(key) != value
            for key, value in EXPECTED_COUNTS.items()
        )
        or manifest.get("scope") != POLICY
    ):
        raise ExactIdentityDecisionError("identity v14 manifest contract differs")
    _validate_decision_delta(bundle)
    _assert_forbidden_lineage_absent({DEFINITION.name: definition_raw, **actual_payloads})
    return manifest


def _component_name(name: str, *, label: str) -> str:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\0" in name
        or os.sep in name
    ):
        raise ExactIdentityDecisionError(f"invalid identity v14 {label}: {name!r}")
    return name


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    if path.is_symlink():
        raise ExactIdentityDecisionError(
            f"symlinked identity v14 publication member: {path}"
        )
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        kind = "directory" if directory else "file"
        raise ExactIdentityDecisionError(
            f"identity v14 member is not a {kind}: {path}"
        )
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, identity: tuple[int, int], *, directory: bool
) -> bool:
    try:
        return _identity(path, directory=directory) == identity
    except (FileNotFoundError, ExactIdentityDecisionError):
        return False


def _fstat_identity(
    descriptor: int,
    *,
    directory: bool,
    label: str,
    expected_mode: int | None = None,
) -> tuple[int, int]:
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise ExactIdentityDecisionError(
            f"identity v14 {label} descriptor is unavailable"
        ) from error
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        kind = "directory" if directory else "file"
        raise ExactIdentityDecisionError(
            f"identity v14 {label} is not an owned {kind}"
        )
    if expected_mode is not None and stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise ExactIdentityDecisionError(
            f"identity v14 {label} mode differs"
        )
    return metadata.st_dev, metadata.st_ino


def _parent_paths() -> dict[str, Path]:
    return {
        "definition": DEFINITION.parent,
        "bundle": BUNDLE.parent,
        "lock": PUBLICATION_LOCK.parent,
    }


def _assert_parent_descriptors(
    bindings: ParentBindings, *, label: str
) -> None:
    for name, (_path, expected, descriptor) in bindings.items():
        actual = _fstat_identity(
            descriptor,
            directory=True,
            label=f"{label} {name} parent",
        )
        if actual != expected:
            raise ExactIdentityDecisionError(
                f"identity v14 {label} {name} parent descriptor changed"
            )


def _assert_parent_bindings(bindings: ParentBindings, *, label: str) -> None:
    expected_paths = _parent_paths()
    if set(bindings) != set(expected_paths):
        raise ExactIdentityDecisionError(
            f"identity v14 {label} parent-binding schema differs"
        )
    for name, expected_path in expected_paths.items():
        path, identity, _descriptor = bindings[name]
        if path != expected_path or not _has_identity(
            path, identity, directory=True
        ):
            raise ExactIdentityDecisionError(
                f"identity v14 {label} {name} parent identity changed"
            )
    _assert_parent_descriptors(bindings, label=label)


@contextmanager
def _bound_output_parents() -> Iterator[dict[str, tuple[Path, tuple[int, int], int]]]:
    bindings: dict[str, tuple[Path, tuple[int, int], int]] = {}
    descriptors: list[int] = []
    try:
        for name, parent in _parent_paths().items():
            try:
                descriptor = os.open(
                    parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
            except OSError as error:
                raise ExactIdentityDecisionError(
                    f"identity v14 {name} parent cannot be opened: {parent}"
                ) from error
            descriptors.append(descriptor)
            identity = _fstat_identity(
                descriptor,
                directory=True,
                label=f"{name} parent binding",
            )
            if not _has_identity(parent, identity, directory=True):
                raise ExactIdentityDecisionError(
                    f"identity v14 {name} parent changed while binding"
                )
            bindings[name] = (parent, identity, descriptor)
        _assert_parent_bindings(bindings, label="parent binding")
        yield bindings
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _binding_for_parent(
    bindings: ParentBindings, parent: Path
) -> tuple[Path, tuple[int, int], int]:
    matches = [binding for binding in bindings.values() if binding[0] == parent]
    if len(matches) != 1:
        raise ExactIdentityDecisionError(
            f"identity v14 parent is not uniquely bound: {parent}"
        )
    return matches[0]


def _stat_at(
    binding: tuple[Path, tuple[int, int], int], name: str
) -> os.stat_result | None:
    _component_name(name, label="bound member")
    try:
        return os.stat(name, dir_fd=binding[2], follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ExactIdentityDecisionError(
            f"identity v14 bound member is unavailable: {name}"
        ) from error


def _bound_present(
    binding: tuple[Path, tuple[int, int], int], name: str
) -> bool:
    return _stat_at(binding, name) is not None


def _bound_identity(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    *,
    directory: bool,
) -> tuple[int, int]:
    metadata = _stat_at(binding, name)
    if metadata is None:
        raise ExactIdentityDecisionError(
            f"identity v14 bound member is absent: {name}"
        )
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        kind = "directory" if directory else "file"
        raise ExactIdentityDecisionError(
            f"identity v14 bound member is not a {kind}: {name}"
        )
    return metadata.st_dev, metadata.st_ino


def _has_bound_identity(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> bool:
    try:
        return _bound_identity(binding, name, directory=directory) == identity
    except ExactIdentityDecisionError:
        return False


def _random_stage_name(prefix: str, suffix: str = "") -> str:
    return _component_name(
        f".{prefix}.{secrets.token_hex(12)}{suffix}",
        label="private stage name",
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise ExactIdentityDecisionError("identity v14 short stage write")
        view = view[written:]
    os.fsync(descriptor)


def _discard_bound_file(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    identity: tuple[int, int],
) -> bool:
    if not _bound_present(binding, name):
        return False
    if not _has_bound_identity(
        binding, name, identity, directory=False
    ):
        raise ExactIdentityDecisionError(
            "refusing substituted bound identity v14 file cleanup"
        )
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=binding[2],
    )
    try:
        if _fstat_identity(
            descriptor, directory=False, label="file cleanup"
        ) != identity:
            raise ExactIdentityDecisionError(
                "refusing substituted open identity v14 file cleanup"
            )
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        if not _has_bound_identity(
            binding, name, identity, directory=False
        ):
            raise ExactIdentityDecisionError(
                "refusing late-substituted identity v14 file cleanup"
            )
        os.unlink(name, dir_fd=binding[2])
        os.fsync(binding[2])
    finally:
        os.close(descriptor)
    if _bound_present(binding, name):
        raise ExactIdentityDecisionError(
            "identity v14 bound file cleanup left residue"
        )
    return True


def _bound_bundle_identities(
    binding: tuple[Path, tuple[int, int], int], root_name: str
) -> dict[str, tuple[str, int, int]]:
    root_descriptor = os.open(
        root_name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=binding[2],
    )
    try:
        root = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root.st_mode):
            raise ExactIdentityDecisionError(
                "identity v14 bound bundle root is not a directory"
            )
        result = {".": ("directory", root.st_dev, root.st_ino)}
        for name in sorted(os.listdir(root_descriptor)):
            _component_name(name, label="bundle member")
            metadata = os.stat(
                name, dir_fd=root_descriptor, follow_symlinks=False
            )
            if not stat.S_ISREG(metadata.st_mode):
                raise ExactIdentityDecisionError(
                    f"identity v14 bundle has non-file member: {name}"
                )
            result[name] = ("file", metadata.st_dev, metadata.st_ino)
        return result
    finally:
        os.close(root_descriptor)


def _assert_bound_bundle_identities(
    binding: tuple[Path, tuple[int, int], int],
    root_name: str,
    expected: Mapping[str, tuple[str, int, int]],
) -> None:
    if _bound_bundle_identities(binding, root_name) != dict(expected):
        raise ExactIdentityDecisionError(
            "identity v14 recursive bound bundle identity changed"
        )


def _discard_bound_bundle(
    binding: tuple[Path, tuple[int, int], int],
    root_name: str,
    expected: Mapping[str, tuple[str, int, int]],
) -> bool:
    if not _bound_present(binding, root_name):
        return False
    _assert_bound_bundle_identities(binding, root_name, expected)
    root_descriptor = os.open(
        root_name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=binding[2],
    )
    try:
        root_identity = expected.get(".")
        root_actual = _fstat_identity(
            root_descriptor, directory=True, label="bundle cleanup root"
        )
        if root_identity != ("directory", *root_actual):
            raise ExactIdentityDecisionError(
                "refusing substituted bound identity v14 bundle cleanup"
            )
        expected_names = set(expected) - {"."}
        if set(os.listdir(root_descriptor)) != expected_names:
            raise ExactIdentityDecisionError(
                "refusing changed bound identity v14 bundle cleanup"
            )
        os.fchmod(root_descriptor, PRIVATE_DIRECTORY_MODE)
        for name in sorted(expected_names):
            expected_child = expected[name]
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_descriptor,
            )
            try:
                actual = _fstat_identity(
                    descriptor,
                    directory=False,
                    label=f"bundle cleanup member {name}",
                )
                if expected_child != ("file", *actual):
                    raise ExactIdentityDecisionError(
                        "refusing substituted bound identity v14 bundle member "
                        f"cleanup: {name}"
                    )
                os.fchmod(descriptor, PRIVATE_FILE_MODE)
                current = os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
                if expected_child != ("file", current.st_dev, current.st_ino):
                    raise ExactIdentityDecisionError(
                        "refusing late-substituted identity v14 bundle member "
                        f"cleanup: {name}"
                    )
                os.unlink(name, dir_fd=root_descriptor)
            finally:
                os.close(descriptor)
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    root_identity = expected["."]
    if not _has_bound_identity(
        binding,
        root_name,
        (root_identity[1], root_identity[2]),
        directory=True,
    ):
        raise ExactIdentityDecisionError(
            "refusing late-substituted identity v14 bundle cleanup"
        )
    os.rmdir(root_name, dir_fd=binding[2])
    os.fsync(binding[2])
    if _bound_present(binding, root_name):
        raise ExactIdentityDecisionError(
            "identity v14 bound bundle cleanup left residue"
        )
    return True


def _create_definition_stage(
    payload: bytes, *, parent_bindings: ParentBindings
) -> tuple[Path, tuple[int, int]]:
    _assert_parent_bindings(parent_bindings, label="before definition creation")
    binding = _binding_for_parent(parent_bindings, DEFINITION.parent)
    name = ""
    descriptor = -1
    identity: tuple[int, int] | None = None
    try:
        for _attempt in range(128):
            candidate = _random_stage_name(DEFINITION.name, ".stage")
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    PRIVATE_FILE_MODE,
                    dir_fd=binding[2],
                )
            except FileExistsError:
                continue
            name = candidate
            break
        if descriptor < 0:
            raise ExactIdentityDecisionError(
                "identity v14 could not reserve a definition stage"
            )
        identity = _fstat_identity(
            descriptor,
            directory=False,
            label="definition creation descriptor",
            expected_mode=PRIVATE_FILE_MODE,
        )
        _write_all(descriptor, payload)
        os.close(descriptor)
        descriptor = -1
        if not _has_bound_identity(
            binding, name, identity, directory=False
        ):
            raise ExactIdentityDecisionError(
                "identity v14 definition stage changed after descriptor creation"
            )
        os.fsync(binding[2])
        _assert_parent_bindings(parent_bindings, label="after definition creation")
        return binding[0] / name, identity
    except BaseException as error:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None and name:
            try:
                _discard_bound_file(binding, name, identity)
            except Exception as cleanup_error:  # noqa: BLE001
                error.add_note(
                    f"identity v14 definition creation cleanup failed: {cleanup_error}"
                )
        raise


def _create_bundle_stage(
    payloads: Mapping[str, bytes], *, parent_bindings: ParentBindings
) -> tuple[Path, dict[str, tuple[str, int, int]]]:
    _assert_parent_bindings(parent_bindings, label="before bundle creation")
    binding = _binding_for_parent(parent_bindings, BUNDLE.parent)
    name = ""
    root_descriptor = -1
    identities: dict[str, tuple[str, int, int]] = {}
    try:
        for _attempt in range(128):
            candidate = _random_stage_name(BUNDLE.name, ".stage")
            try:
                os.mkdir(
                    candidate,
                    PRIVATE_DIRECTORY_MODE,
                    dir_fd=binding[2],
                )
            except FileExistsError:
                continue
            name = candidate
            break
        if not name:
            raise ExactIdentityDecisionError(
                "identity v14 could not reserve a bundle stage"
            )
        root_descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=binding[2],
        )
        root_identity = _fstat_identity(
            root_descriptor,
            directory=True,
            label="bundle creation descriptor",
            expected_mode=PRIVATE_DIRECTORY_MODE,
        )
        identities["."] = ("directory", *root_identity)
        for filename, payload in sorted(payloads.items()):
            _component_name(filename, label="bundle filename")
            descriptor = os.open(
                filename,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                PRIVATE_FILE_MODE,
                dir_fd=root_descriptor,
            )
            try:
                file_identity = _fstat_identity(
                    descriptor,
                    directory=False,
                    label=f"bundle creation member {filename}",
                    expected_mode=PRIVATE_FILE_MODE,
                )
                identities[filename] = ("file", *file_identity)
                _write_all(descriptor, payload)
            finally:
                os.close(descriptor)
        os.fsync(root_descriptor)
        os.close(root_descriptor)
        root_descriptor = -1
        _assert_bound_bundle_identities(binding, name, identities)
        os.fsync(binding[2])
        _assert_parent_bindings(parent_bindings, label="after bundle creation")
        return binding[0] / name, identities
    except BaseException as error:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        if identities and name:
            try:
                _discard_bound_bundle(binding, name, identities)
            except Exception as cleanup_error:  # noqa: BLE001
                error.add_note(
                    f"identity v14 bundle creation cleanup failed: {cleanup_error}"
                )
        raise


def _freeze_stages(
    definition_stage: Path,
    definition_identity: tuple[int, int],
    bundle_stage: Path,
    bundle_identities: Mapping[str, tuple[str, int, int]],
    *,
    parent_bindings: ParentBindings,
) -> None:
    definition_binding = _binding_for_parent(
        parent_bindings, definition_stage.parent
    )
    definition_descriptor = os.open(
        definition_stage.name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=definition_binding[2],
    )
    try:
        if _fstat_identity(
            definition_descriptor, directory=False, label="definition freeze"
        ) != definition_identity:
            raise ExactIdentityDecisionError(
                "identity v14 definition changed before freeze"
            )
        os.fchmod(definition_descriptor, FROZEN_FILE_MODE)
        os.fsync(definition_descriptor)
    finally:
        os.close(definition_descriptor)

    bundle_binding = _binding_for_parent(parent_bindings, bundle_stage.parent)
    _assert_bound_bundle_identities(
        bundle_binding, bundle_stage.name, bundle_identities
    )
    root_descriptor = os.open(
        bundle_stage.name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=bundle_binding[2],
    )
    try:
        for name in sorted(set(bundle_identities) - {"."}):
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_descriptor,
            )
            try:
                expected = bundle_identities[name]
                actual = _fstat_identity(
                    descriptor, directory=False, label=f"bundle freeze {name}"
                )
                if expected != ("file", *actual):
                    raise ExactIdentityDecisionError(
                        f"identity v14 bundle member changed before freeze: {name}"
                    )
                os.fchmod(descriptor, FROZEN_FILE_MODE)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.fchmod(root_descriptor, FROZEN_DIRECTORY_MODE)
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    os.fsync(definition_binding[2])
    os.fsync(bundle_binding[2])
    _assert_bound_bundle_identities(
        bundle_binding, bundle_stage.name, bundle_identities
    )
    _assert_parent_bindings(parent_bindings, label="after stage freeze")


def _rename_noreplace_at(
    parent_descriptor: int, source_name: str, destination_name: str
) -> None:
    _component_name(source_name, label="rename source")
    _component_name(destination_name, label="rename destination")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        if function is None:  # pragma: no cover
            raise ExactIdentityDecisionError(
                "identity v14 bound atomic no-replace rename is unavailable"
            )
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            source,
            parent_descriptor,
            destination,
            0x00000004,
        )
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise ExactIdentityDecisionError(
                "identity v14 bound atomic no-replace rename is unavailable"
            )
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            source,
            parent_descriptor,
            destination,
            0x00000001,
        )
    else:  # pragma: no cover
        raise ExactIdentityDecisionError(
            "identity v14 bound atomic no-replace rename is unavailable"
        )
    if result == 0:
        os.fsync(parent_descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ExactIdentityDecisionError(
            "identity v14 late output collision; refusing overwrite: "
            f"{destination_name}"
        )
    raise ExactIdentityDecisionError(
        "identity v14 bound atomic no-replace rename failed: "
        f"{source_name} -> {destination_name}: {os.strerror(error_number)}"
    )


def _promote_noreplace(
    stage: Path,
    destination: Path,
    *,
    directory: bool,
    parent_bindings: ParentBindings,
) -> tuple[int, int]:
    _assert_parent_bindings(parent_bindings, label="before promotion")
    source_binding = _binding_for_parent(parent_bindings, stage.parent)
    destination_binding = _binding_for_parent(parent_bindings, destination.parent)
    if source_binding != destination_binding:
        raise ExactIdentityDecisionError(
            "identity v14 promotion crosses bound parents"
        )
    identity = _bound_identity(
        source_binding, stage.name, directory=directory
    )
    if _bound_present(destination_binding, destination.name):
        raise ExactIdentityDecisionError(
            f"identity v14 final path collision: {destination}"
        )
    _rename_noreplace_at(
        source_binding[2], stage.name, destination.name
    )
    if not _has_bound_identity(
        destination_binding,
        destination.name,
        identity,
        directory=directory,
    ):
        raise ExactIdentityDecisionError(
            "identity v14 promoted identity differs"
        )
    _assert_parent_bindings(parent_bindings, label="after promotion")
    return identity


def _rollback_noreplace(
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
    parent_bindings: ParentBindings,
) -> None:
    _assert_parent_descriptors(parent_bindings, label="before rollback")
    destination_binding = _binding_for_parent(
        parent_bindings, destination.parent
    )
    stage_binding = _binding_for_parent(parent_bindings, stage.parent)
    if destination_binding != stage_binding:
        raise ExactIdentityDecisionError(
            "identity v14 rollback crosses bound parents"
        )
    if not _has_bound_identity(
        destination_binding,
        destination.name,
        identity,
        directory=directory,
    ):
        raise ExactIdentityDecisionError(
            "identity v14 refuses identity-mismatched rollback"
        )
    if _bound_present(stage_binding, stage.name):
        raise ExactIdentityDecisionError(
            "identity v14 rollback stage is occupied"
        )
    _rename_noreplace_at(
        destination_binding[2], destination.name, stage.name
    )
    if not _has_bound_identity(
        stage_binding, stage.name, identity, directory=directory
    ):
        raise ExactIdentityDecisionError(
            "identity v14 rollback identity differs"
        )
    _assert_parent_descriptors(parent_bindings, label="after rollback")


def _private_promotion_roundtrip(
    definition_stage: Path,
    bundle_stage: Path,
    *,
    definition_identity: tuple[int, int],
    bundle_identities: Mapping[str, tuple[str, int, int]],
    parent_bindings: ParentBindings,
) -> None:
    pairs = (
        (bundle_stage, True, (bundle_identities["."][1], bundle_identities["."][2])),
        (definition_stage, False, definition_identity),
    )
    for stage, directory, identity in pairs:
        binding = _binding_for_parent(parent_bindings, stage.parent)
        destination_name = _random_stage_name(
            f"{stage.name}.roundtrip"
        )
        destination = stage.parent / destination_name
        moved = False
        try:
            _rename_noreplace_at(binding[2], stage.name, destination_name)
            moved = True
            if not _has_bound_identity(
                binding, destination_name, identity, directory=directory
            ):
                raise ExactIdentityDecisionError(
                    "identity v14 private promoted identity differs"
                )
            _rename_noreplace_at(binding[2], destination_name, stage.name)
            moved = False
            if not _has_bound_identity(
                binding, stage.name, identity, directory=directory
            ):
                raise ExactIdentityDecisionError(
                    "identity v14 private rollback identity differs"
                )
        except BaseException as error:
            if moved and _has_bound_identity(
                binding, destination.name, identity, directory=directory
            ):
                try:
                    _rename_noreplace_at(
                        binding[2], destination.name, stage.name
                    )
                except Exception as rollback_error:  # noqa: BLE001
                    error.add_note(
                        "identity v14 private roundtrip rollback failed: "
                        f"{rollback_error}"
                    )
            raise
    _assert_parent_bindings(parent_bindings, label="after private roundtrip")


def _path_members(definition: Path, bundle: Path) -> tuple[Path, ...]:
    return (definition, bundle, *sorted(bundle.rglob("*")))


def _validate_publication_times(
    definition: Path,
    bundle: Path,
    *,
    recorded_at: str,
    validation_wall_clock: datetime,
    require_live: bool,
) -> None:
    target = _parsed_timestamp(recorded_at, "identity v14 recorded_at")
    wall_clock = _wall_clock(validation_wall_clock)
    if require_live and target > wall_clock:
        raise ExactIdentityDecisionError(
            "identity v14 recorded_at exceeds validation wall clock"
        )
    for path in _path_members(definition, bundle):
        if path.is_symlink():
            raise ExactIdentityDecisionError(
                f"identity v14 temporal member is symlinked: {path}"
            )
        _path_timestamp_bounds(
            path, target, f"identity v14 artifact {path.name}"
        )
        if require_live:
            _final_root_ctime(
                path,
                target,
                wall_clock,
                f"identity v14 artifact {path.name}",
            )


def _refresh_publication_ctimes(
    definition_stage: Path,
    definition_identity: tuple[int, int],
    bundle_stage: Path,
    bundle_identities: Mapping[str, tuple[str, int, int]],
    *,
    recorded_at: str,
    parent_bindings: ParentBindings,
) -> None:
    target = _parsed_timestamp(recorded_at, "identity v14 recorded_at")
    if datetime.now(UTC) < target:
        raise ExactIdentityDecisionError(
            "identity v14 cannot refresh ctimes before recorded_at"
        )
    definition_binding = _binding_for_parent(
        parent_bindings, definition_stage.parent
    )
    descriptor = os.open(
        definition_stage.name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=definition_binding[2],
    )
    try:
        if _fstat_identity(
            descriptor, directory=False, label="definition ctime refresh"
        ) != definition_identity:
            raise ExactIdentityDecisionError(
                "identity v14 definition changed before ctime refresh"
            )
        os.fchmod(descriptor, 0o400)
        os.fchmod(descriptor, FROZEN_FILE_MODE)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    bundle_binding = _binding_for_parent(parent_bindings, bundle_stage.parent)
    _assert_bound_bundle_identities(
        bundle_binding, bundle_stage.name, bundle_identities
    )
    root_descriptor = os.open(
        bundle_stage.name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=bundle_binding[2],
    )
    try:
        os.fchmod(root_descriptor, 0o755)
        for name in sorted(set(bundle_identities) - {"."}):
            member = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_descriptor,
            )
            try:
                expected = bundle_identities[name]
                actual = _fstat_identity(
                    member,
                    directory=False,
                    label=f"bundle ctime refresh {name}",
                )
                if expected != ("file", *actual):
                    raise ExactIdentityDecisionError(
                        f"identity v14 bundle changed before ctime refresh: {name}"
                    )
                os.fchmod(member, 0o400)
                os.fchmod(member, FROZEN_FILE_MODE)
                os.fsync(member)
            finally:
                os.close(member)
        os.fchmod(root_descriptor, FROZEN_DIRECTORY_MODE)
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    os.fsync(definition_binding[2])
    os.fsync(bundle_binding[2])
    _assert_bound_bundle_identities(
        bundle_binding, bundle_stage.name, bundle_identities
    )
    _assert_parent_bindings(parent_bindings, label="after ctime refresh")


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def _candidate_pin_report(
    definition_raw: bytes,
    bundle: Path,
) -> tuple[tuple[int, str], dict[str, tuple[int, str]], str]:
    definition_pin = (len(definition_raw), _sha256(definition_raw))
    artifacts = {
        entry.name: _file_pin(entry)
        for entry in sorted(bundle.iterdir(), key=lambda item: item.name)
    }
    if set(artifacts) != set(BUNDLE_FILES):
        raise ExactIdentityDecisionError(
            "identity v14 candidate file inventory differs"
        )
    return definition_pin, artifacts, tree_digest(bundle)


def _require_candidate_pins(
    definition_pin: tuple[int, str],
    artifact_pins: Mapping[str, tuple[int, str]],
    bundle_tree: str,
) -> None:
    configured = (
        DEFINITION_PIN is not None,
        bool(ARTIFACT_PINS),
        BUNDLE_TREE_SHA256 is not None,
    )
    if any(configured) and not all(configured):
        raise ExactIdentityDecisionError(
            "identity v14 candidate pins are only partially configured"
        )
    if all(configured) and (
        definition_pin != DEFINITION_PIN
        or dict(artifact_pins) != ARTIFACT_PINS
        or bundle_tree != BUNDLE_TREE_SHA256
    ):
        raise ExactIdentityDecisionError("identity v14 candidate pins differ")


def _cleanup_stages(
    *,
    definition_stage: Path | None,
    definition_identity: tuple[int, int] | None,
    bundle_stage: Path | None,
    bundle_identities: Mapping[str, tuple[str, int, int]] | None,
    parent_bindings: ParentBindings,
    active_error: BaseException | None,
) -> None:
    errors: list[str] = []
    if definition_stage is not None and definition_identity is not None:
        binding = _binding_for_parent(
            parent_bindings, definition_stage.parent
        )
        try:
            _discard_bound_file(
                binding, definition_stage.name, definition_identity
            )
        except Exception as error:  # noqa: BLE001
            errors.append(f"definition stage cleanup failed: {error}")
    if bundle_stage is not None and bundle_identities is not None:
        binding = _binding_for_parent(parent_bindings, bundle_stage.parent)
        try:
            _discard_bound_bundle(
                binding, bundle_stage.name, bundle_identities
            )
        except Exception as error:  # noqa: BLE001
            errors.append(f"bundle stage cleanup failed: {error}")
    if errors:
        message = "identity v14 " + "; ".join(errors)
        if active_error is not None:
            active_error.add_note(message)
        else:
            raise ExactIdentityDecisionError(message)


@contextmanager
def _publication_lock(parent_bindings: ParentBindings) -> Iterator[None]:
    _assert_parent_bindings(parent_bindings, label="before lock acquisition")
    binding = _binding_for_parent(parent_bindings, PUBLICATION_LOCK.parent)
    descriptor = -1
    identity: tuple[int, int] | None = None
    try:
        try:
            descriptor = os.open(
                PUBLICATION_LOCK.name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                PRIVATE_FILE_MODE,
                dir_fd=binding[2],
            )
        except FileExistsError as error:
            raise ExactIdentityDecisionError(
                f"active identity-v14 publication lock exists: {PUBLICATION_LOCK}"
            ) from error
        identity = _fstat_identity(
            descriptor,
            directory=False,
            label="publication lock",
            expected_mode=PRIVATE_FILE_MODE,
        )
        _write_all(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        descriptor = -1
        if not _has_bound_identity(
            binding, PUBLICATION_LOCK.name, identity, directory=False
        ):
            raise ExactIdentityDecisionError(
                "identity v14 publication lock changed after creation"
            )
        _assert_parent_bindings(parent_bindings, label="after lock acquisition")
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            try:
                _discard_bound_file(
                    binding, PUBLICATION_LOCK.name, identity
                )
            except Exception as cleanup_error:
                active = sys.exception()
                if active is not None:
                    active.add_note(
                        "identity v14 publication lock cleanup failed: "
                        f"{cleanup_error}"
                    )
                else:
                    raise


def _final_presence(
    parent_bindings: ParentBindings,
) -> tuple[bool, bool]:
    definition_binding = _binding_for_parent(
        parent_bindings, DEFINITION.parent
    )
    bundle_binding = _binding_for_parent(parent_bindings, BUNDLE.parent)
    return (
        _bound_present(definition_binding, DEFINITION.name),
        _bound_present(bundle_binding, BUNDLE.name),
    )


def _require_finals_absent(
    parent_bindings: ParentBindings, *, label: str
) -> None:
    definition_present, bundle_present = _final_presence(parent_bindings)
    if definition_present or bundle_present:
        raise ExactIdentityDecisionError(
            f"identity v14 {label} final path already exists"
        )


def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    require_live: bool = True,
    validation_wall_clock: datetime | None = None,
    parent_bindings: ParentBindings | None = None,
) -> dict[str, Any]:
    """Validate v14 with exact lineage, inventory, and two offline replays."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v14 requires exactly two offline reconstructions"
        )
    if parent_bindings is None:
        with _bound_output_parents() as bindings:
            return validate_exact_identity_decision_bundle(
                path_value,
                definition_path=definition_path,
                require_frozen=require_frozen,
                replay_count=replay_count,
                require_live=require_live,
                validation_wall_clock=validation_wall_clock,
                parent_bindings=bindings,
            )
    _assert_parent_bindings(parent_bindings, label="validation entry")
    guard = _require_guard_state()
    definition = Path(definition_path)
    bundle = Path(path_value)
    if definition.is_symlink() or not definition.is_file():
        raise ExactIdentityDecisionError(
            "identity v14 definition must be an ordinary file"
        )
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError(
            "identity v14 bundle must be a regular directory"
        )
    raw = definition.read_bytes()
    document = json.loads(raw)
    recorded_at = document.get("recorded_at")
    if not isinstance(recorded_at, str):
        raise ExactIdentityDecisionError(
            "identity v14 definition recorded_at is invalid"
        )
    _target_timestamp(recorded_at)
    manifest = _validate_payload_bundle(
        raw,
        bundle,
        recorded_at=recorded_at,
        require_frozen=require_frozen,
        verify_inputs=True,
    )
    _validate_publication_times(
        definition,
        bundle,
        recorded_at=recorded_at,
        validation_wall_clock=(
            datetime.now(UTC)
            if validation_wall_clock is None
            else validation_wall_clock
        ),
        require_live=require_live,
    )
    if require_frozen and (
        stat.S_IMODE(definition.stat().st_mode) != FROZEN_FILE_MODE
        or stat.S_IMODE(bundle.stat().st_mode) != FROZEN_DIRECTORY_MODE
        or any(
            stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE
            for entry in bundle.iterdir()
        )
    ):
        raise ExactIdentityDecisionError(
            "identity v14 frozen modes differ"
        )
    definition_pin, artifact_pins, bundle_tree = _candidate_pin_report(
        raw, bundle
    )
    _require_candidate_pins(definition_pin, artifact_pins, bundle_tree)
    if _guard_state() != guard:
        raise ExactIdentityDecisionError(
            "identity v14 validation mutated accepted inputs"
        )
    _assert_parent_bindings(parent_bindings, label="validation completion")
    return manifest


def _existing_identical(
    recorded_at: str | None, parent_bindings: ParentBindings
) -> dict[str, Any]:
    definition_present, bundle_present = _final_presence(parent_bindings)
    if not (definition_present and bundle_present):
        raise ExactIdentityDecisionError(
            "identity v14 partial final-path collision"
        )
    manifest = validate_exact_identity_decision_bundle(
        parent_bindings=parent_bindings
    )
    actual_recorded_at = manifest["recorded_at"]
    if recorded_at is not None and recorded_at != actual_recorded_at:
        raise ExactIdentityDecisionError(
            "identity v14 existing final recorded_at differs"
        )
    definition_raw = DEFINITION.read_bytes()
    definition_pin, artifact_pins, bundle_tree = _candidate_pin_report(
        definition_raw, BUNDLE
    )
    return {
        "status": "existing-identical",
        "publication_authorized": True,
        "definition": str(DEFINITION),
        "definition_pin": definition_pin,
        "bundle": str(BUNDLE),
        "artifact_pins": artifact_pins,
        "bundle_tree_sha256": bundle_tree,
        "recorded_at": actual_recorded_at,
        "counts": manifest["counts"],
        "promotion_contract": PROMOTION_CONTRACT,
    }


def prepare_exact_identity_decisions_v14(
    recorded_at: str | None = None, *, replay_count: int = 2
) -> dict[str, Any]:
    """Run a publication-proof private preflight and leave no final paths."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v14 preflight requires exactly two offline replays"
        )
    timestamp, target = _target_timestamp(recorded_at)
    if target <= datetime.now(UTC):
        raise ExactIdentityDecisionError(
            "identity v14 preflight recorded_at must be future before staging"
        )
    with _bound_output_parents() as parent_bindings:
        definition_stage: Path | None = None
        definition_identity: tuple[int, int] | None = None
        bundle_stage: Path | None = None
        bundle_identities: dict[str, tuple[str, int, int]] | None = None
        with _publication_lock(parent_bindings):
            _require_finals_absent(parent_bindings, label="preflight")
            guard = _require_guard_state()
            try:
                definition_raw, payloads, expected_manifest, _definition = (
                    _prepare_payloads(timestamp)
                )
                definition_stage, definition_identity = _create_definition_stage(
                    definition_raw, parent_bindings=parent_bindings
                )
                bundle_stage, bundle_identities = _create_bundle_stage(
                    payloads, parent_bindings=parent_bindings
                )
                _freeze_stages(
                    definition_stage,
                    definition_identity,
                    bundle_stage,
                    bundle_identities,
                    parent_bindings=parent_bindings,
                )
                staged_manifest = _validate_payload_bundle(
                    definition_raw,
                    bundle_stage,
                    recorded_at=timestamp,
                    require_frozen=True,
                    verify_inputs=False,
                )
                if staged_manifest != expected_manifest:
                    raise ExactIdentityDecisionError(
                        "identity v14 staged manifest differs"
                    )
                _validate_publication_times(
                    definition_stage,
                    bundle_stage,
                    recorded_at=timestamp,
                    validation_wall_clock=target,
                    require_live=False,
                )
                _private_promotion_roundtrip(
                    definition_stage,
                    bundle_stage,
                    definition_identity=definition_identity,
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                )
                definition_pin, artifact_pins, bundle_tree = (
                    _candidate_pin_report(definition_raw, bundle_stage)
                )
                _require_candidate_pins(
                    definition_pin, artifact_pins, bundle_tree
                )
                if _guard_state() != guard:
                    raise ExactIdentityDecisionError(
                        "identity v14 preflight mutated accepted inputs"
                    )
                _assert_parent_bindings(
                    parent_bindings, label="preflight completion"
                )
                _require_finals_absent(
                    parent_bindings, label="preflight completion"
                )
                result = {
                    "status": "prepublication-validated",
                    "publication_authorized": False,
                    "definition": str(DEFINITION),
                    "definition_pin": definition_pin,
                    "bundle": str(BUNDLE),
                    "artifact_pins": artifact_pins,
                    "bundle_tree_sha256": bundle_tree,
                    "recorded_at": timestamp,
                    "counts": staged_manifest["counts"],
                    "promotion_contract": PROMOTION_CONTRACT,
                    "replay_count": 2,
                }
            finally:
                _cleanup_stages(
                    definition_stage=definition_stage,
                    definition_identity=definition_identity,
                    bundle_stage=bundle_stage,
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                    active_error=sys.exception(),
                )
            _require_finals_absent(
                parent_bindings, label="post-cleanup preflight"
            )
            return result


def _rollback_owned_final(
    error: BaseException,
    *,
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    directory: bool,
    parent_bindings: ParentBindings,
) -> bool:
    binding = _binding_for_parent(parent_bindings, destination.parent)
    if not _has_bound_identity(
        binding, destination.name, identity, directory=directory
    ):
        return False
    try:
        _rollback_noreplace(
            destination,
            stage,
            identity,
            directory=directory,
            parent_bindings=parent_bindings,
        )
    except Exception as rollback_error:  # noqa: BLE001
        error.add_note(
            f"identity v14 rollback failed for {destination}: {rollback_error}"
        )
        return True
    return False


def publish_exact_identity_decisions_v14(
    recorded_at: str | None = None,
    *,
    publication_authorized: bool = False,
    completion_callback: Any | None = None,
) -> dict[str, Any]:
    """Publish only after explicit authorization and every governed gate."""

    if not publication_authorized:
        raise ExactIdentityDecisionError(
            "identity v14 publication requires explicit authorization"
        )
    with _bound_output_parents() as parent_bindings:
        definition_stage: Path | None = None
        definition_identity: tuple[int, int] | None = None
        bundle_stage: Path | None = None
        bundle_identities: dict[str, tuple[str, int, int]] | None = None
        definition_published = False
        bundle_published = False
        bundle_identity: tuple[int, int] | None = None
        with _publication_lock(parent_bindings):
            definition_present, bundle_present = _final_presence(parent_bindings)
            if definition_present and bundle_present:
                result = _existing_identical(recorded_at, parent_bindings)
                if completion_callback is not None:
                    completion_callback(result)
                return result
            if definition_present or bundle_present:
                raise ExactIdentityDecisionError(
                    "identity v14 partial final-path collision"
                )
            timestamp, target = _target_timestamp(recorded_at)
            if target <= datetime.now(UTC):
                raise ExactIdentityDecisionError(
                    "identity v14 recorded_at must be future before staging"
                )
            guard = _require_guard_state()
            try:
                definition_raw, payloads, expected_manifest, _definition = (
                    _prepare_payloads(timestamp)
                )
                definition_stage, definition_identity = _create_definition_stage(
                    definition_raw, parent_bindings=parent_bindings
                )
                bundle_stage, bundle_identities = _create_bundle_stage(
                    payloads, parent_bindings=parent_bindings
                )
                _freeze_stages(
                    definition_stage,
                    definition_identity,
                    bundle_stage,
                    bundle_identities,
                    parent_bindings=parent_bindings,
                )
                staged_manifest = _validate_payload_bundle(
                    definition_raw,
                    bundle_stage,
                    recorded_at=timestamp,
                    require_frozen=True,
                    verify_inputs=False,
                )
                if staged_manifest != expected_manifest:
                    raise ExactIdentityDecisionError(
                        "identity v14 staged manifest differs"
                    )
                _private_promotion_roundtrip(
                    definition_stage,
                    bundle_stage,
                    definition_identity=definition_identity,
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                )
                definition_pin, artifact_pins, bundle_tree = (
                    _candidate_pin_report(definition_raw, bundle_stage)
                )
                _require_candidate_pins(
                    definition_pin, artifact_pins, bundle_tree
                )
                _validate_publication_times(
                    definition_stage,
                    bundle_stage,
                    recorded_at=timestamp,
                    validation_wall_clock=target,
                    require_live=False,
                )
                frozen_definition = definition_stage.read_bytes()
                frozen_tree = tree_digest(bundle_stage)
                _assert_parent_bindings(
                    parent_bindings, label="before publication wait"
                )
                _require_finals_absent(parent_bindings, label="pre-wait")
                _wait_until(target)
                _assert_parent_bindings(
                    parent_bindings, label="after publication wait"
                )
                _require_finals_absent(parent_bindings, label="late")
                definition_binding = _binding_for_parent(
                    parent_bindings, definition_stage.parent
                )
                bundle_binding = _binding_for_parent(
                    parent_bindings, bundle_stage.parent
                )
                if not _has_bound_identity(
                    definition_binding,
                    definition_stage.name,
                    definition_identity,
                    directory=False,
                ):
                    raise ExactIdentityDecisionError(
                        "identity v14 definition stage changed while waiting"
                    )
                _assert_bound_bundle_identities(
                    bundle_binding,
                    bundle_stage.name,
                    bundle_identities,
                )
                if (
                    definition_stage.read_bytes() != frozen_definition
                    or tree_digest(bundle_stage) != frozen_tree
                    or _guard_state() != guard
                ):
                    raise ExactIdentityDecisionError(
                        "identity v14 stage or inputs changed while waiting"
                    )
                _refresh_publication_ctimes(
                    definition_stage,
                    definition_identity,
                    bundle_stage,
                    bundle_identities,
                    recorded_at=timestamp,
                    parent_bindings=parent_bindings,
                )
                _validate_publication_times(
                    definition_stage,
                    bundle_stage,
                    recorded_at=timestamp,
                    validation_wall_clock=datetime.now(UTC),
                    require_live=True,
                )
                bundle_identity = (
                    bundle_identities["."][1],
                    bundle_identities["."][2],
                )
                try:
                    promoted_bundle = _promote_noreplace(
                        bundle_stage,
                        BUNDLE,
                        directory=True,
                        parent_bindings=parent_bindings,
                    )
                    bundle_published = True
                    if promoted_bundle != bundle_identity:
                        raise ExactIdentityDecisionError(
                            "identity v14 bundle promotion identity differs"
                        )
                    promoted_definition = _promote_noreplace(
                        definition_stage,
                        DEFINITION,
                        directory=False,
                        parent_bindings=parent_bindings,
                    )
                    definition_published = True
                    if promoted_definition != definition_identity:
                        raise ExactIdentityDecisionError(
                            "identity v14 definition promotion identity differs"
                        )
                except BaseException as error:
                    if definition_identity is not None:
                        definition_published = _rollback_owned_final(
                            error,
                            destination=DEFINITION,
                            stage=definition_stage,
                            identity=definition_identity,
                            directory=False,
                            parent_bindings=parent_bindings,
                        )
                    if bundle_identity is not None:
                        bundle_published = _rollback_owned_final(
                            error,
                            destination=BUNDLE,
                            stage=bundle_stage,
                            identity=bundle_identity,
                            directory=True,
                            parent_bindings=parent_bindings,
                        )
                    raise

                try:
                    manifest = validate_exact_identity_decision_bundle(
                        parent_bindings=parent_bindings
                    )
                    if _guard_state() != guard:
                        raise ExactIdentityDecisionError(
                            "identity v14 publication mutated accepted inputs"
                        )
                    _assert_parent_bindings(
                        parent_bindings, label="publication completion"
                    )
                    result = {
                        "status": "published",
                        "publication_authorized": True,
                        "definition": str(DEFINITION),
                        "definition_pin": definition_pin,
                        "bundle": str(BUNDLE),
                        "artifact_pins": artifact_pins,
                        "bundle_tree_sha256": bundle_tree,
                        "recorded_at": timestamp,
                        "counts": manifest["counts"],
                        "promotion_contract": PROMOTION_CONTRACT,
                    }
                    if completion_callback is not None:
                        completion_callback(result)
                except BaseException as error:
                    definition_published = _rollback_owned_final(
                        error,
                        destination=DEFINITION,
                        stage=definition_stage,
                        identity=definition_identity,
                        directory=False,
                        parent_bindings=parent_bindings,
                    )
                    bundle_published = _rollback_owned_final(
                        error,
                        destination=BUNDLE,
                        stage=bundle_stage,
                        identity=bundle_identity,
                        directory=True,
                        parent_bindings=parent_bindings,
                    )
                    raise
            finally:
                _cleanup_stages(
                    definition_stage=(
                        None if definition_published else definition_stage
                    ),
                    definition_identity=definition_identity,
                    bundle_stage=None if bundle_published else bundle_stage,
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                    active_error=sys.exception(),
                )
            return result


def write_exact_identity_decision_bundle(
    definition_path: str | Path = DEFINITION,
    output_directory: str | Path = BUNDLE,
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
    completion_callback: Any | None = None,
) -> dict[str, Any]:
    """Publish only the reserved v14 paths after explicit authorization."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ExactIdentityDecisionError(
            "identity v14 publication paths are reserved"
        )
    return publish_exact_identity_decisions_v14(
        recorded_at,
        publication_authorized=publication_authorized,
        completion_callback=completion_callback,
    )


build_exact_identity_decision_bundle = write_exact_identity_decision_bundle


def prepare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publication-proof private preflight for exact identity v14."
    )
    parser.add_argument("--recorded-at")
    parser.add_argument("--replay-count", type=int, default=2)
    return parser


def prepare_main(argv: Sequence[str] | None = None) -> int:
    arguments = prepare_parser().parse_args(argv)
    result = prepare_exact_identity_decisions_v14(
        arguments.recorded_at, replay_count=arguments.replay_count
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def publisher_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicitly authorized final publisher for exact identity v14."
    )
    parser.add_argument("--recorded-at")
    parser.add_argument("--publish-authorized", action="store_true")
    return parser


def publisher_main(
    argv: Sequence[str] | None = None, *, publication_authorized: bool = False
) -> int:
    parser = publisher_parser()
    arguments = parser.parse_args(argv)
    if not (publication_authorized or arguments.publish_authorized):
        parser.error("final publication requires --publish-authorized")

    def emit(result: Mapping[str, Any]) -> None:
        print(json.dumps(result, indent=2, sort_keys=True))

    publish_exact_identity_decisions_v14(
        arguments.recorded_at,
        publication_authorized=True,
        completion_callback=emit,
    )
    return 0


main = prepare_main


__all__ = [
    "ACCOUNTING_FILENAME",
    "ARTIFACT_PINS",
    "BUNDLE",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "BUNDLE_ID",
    "BUNDLE_TREE_SHA256",
    "COMPONENTS_FILENAME",
    "DEFINITION",
    "DEFINITION_FORMAT",
    "DEFINITION_PIN",
    "EXPECTED_COUNTS",
    "EXPECTED_DELTA",
    "FEDERATION_BUNDLE",
    "FEDERATION_DEFINITION",
    "FIN04_KEYS",
    "GOODMAN_KEYS",
    "LINEAGE_FILENAME",
    "NEW_ENTITY_KEYS",
    "NEW_PROJECT_KEYS",
    "POLICY",
    "PROMOTION_CONTRACT",
    "RECORDED_AT",
    "REJECTED_LINEAGE_TOKENS",
    "RELATIONSHIPS_FILENAME",
    "STALE_CURRENT_UNKNOWN_KEYS",
    "SUPERSEDED_LINEAGE_TOKENS",
    "UNRESOLVED_FILENAME",
    "ExactIdentityDecisionError",
    "build_exact_identity_decision_bundle",
    "prepare_exact_identity_decisions_v14",
    "publish_exact_identity_decisions_v14",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]


if __name__ == "__main__":
    raise SystemExit(prepare_main())
