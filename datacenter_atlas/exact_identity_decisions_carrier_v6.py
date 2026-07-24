"""Governed exact-identity carrier for the live federation-v6 projection.

The identity wire format and conservative component policy remain unchanged.
This carrier differs from v5 only at two reviewed boundaries:

* the federation validator is upgraded to ``federated_release_v6`` so the
  accepted open-seed-v97 stale-status contract is validated; and
* the five known cross-root stable-key collisions are suppressed only on the
  nine explicitly witnessed v97 successor occurrences.

Any release-inventory, token, witness, or occurrence-count drift fails closed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from . import exact_identity_decisions as legacy
from . import exact_identity_decisions_carrier_v5 as carrier_v5
from . import federated_release_v6 as federation_v6

ACCOUNTING_FILENAME = legacy.ACCOUNTING_FILENAME
ATTRIBUTION_FILENAME = legacy.ATTRIBUTION_FILENAME
BUNDLE_FILES = legacy.BUNDLE_FILES
BUNDLE_FORMAT = legacy.BUNDLE_FORMAT
COMPONENTS_FILENAME = legacy.COMPONENTS_FILENAME
DEFINITION_FORMAT = legacy.DEFINITION_FORMAT
LINEAGE_FILENAME = legacy.LINEAGE_FILENAME
MANIFEST_FILENAME = legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = legacy.MANIFEST_HASH_FILENAME
POLICY = legacy.POLICY
README_FILENAME = legacy.README_FILENAME
RELATIONSHIPS_FILENAME = legacy.RELATIONSHIPS_FILENAME
UNRESOLVED_FILENAME = legacy.UNRESOLVED_FILENAME

ExactIdentityDecisionError = legacy.ExactIdentityDecisionError

SUCCESSOR_RELEASE_ID = "2026-07-22-open-seed-v97"
GLOBAL_RELEASE_ID = "global-open-v3"
REVIEW_RELEASE_ID = "osm-fuzzy-review-v2"
EXPECTED_RELEASE_IDS = frozenset(
    {SUCCESSOR_RELEASE_ID, GLOBAL_RELEASE_ID, REVIEW_RELEASE_ID}
)
CROSS_ROOT_SINGLETON_TOKENS = carrier_v5.CROSS_ROOT_SINGLETON_TOKENS
EXPECTED_SUCCESSOR_OCCURRENCES = 9


def _preserve_cross_root_singletons(
    occurrences: list[legacy._Occurrence],
) -> list[legacy._Occurrence]:
    """Suppress only the v97-side token in five reviewed cross-root collisions."""

    by_token: dict[str, list[legacy._Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        for identity in occurrence.identities:
            if not identity.ambiguous:
                by_token[identity.token].append(occurrence)
    collisions = {
        token: members
        for token, members in by_token.items()
        if len(members) > 1 and len({item.source_root for item in members}) > 1
    }
    if set(collisions) != CROSS_ROOT_SINGLETON_TOKENS:
        raise ExactIdentityDecisionError(
            "federation-v6 cross-root singleton collision inventory differs"
        )

    for token, members in collisions.items():
        if {item.release_id for item in members} != {
            SUCCESSOR_RELEASE_ID,
            GLOBAL_RELEASE_ID,
        }:
            raise ExactIdentityDecisionError(
                f"federation-v6 cross-root singleton witness differs: {token}"
            )
        expected_basis = (
            "wikidata_stable_key"
            if token.startswith("wikidata:")
            else "osm_stable_key"
        )
        successors = [
            item for item in members if item.release_id == SUCCESSOR_RELEASE_ID
        ]
        if not successors or any(
            len(
                [
                    identity
                    for identity in successor.identities
                    if identity.token == token
                    and identity.basis == expected_basis
                    and not identity.ambiguous
                ]
            )
            != 1
            for successor in successors
        ):
            raise ExactIdentityDecisionError(
                f"federation-v6 suppression basis differs: {token}"
            )

    suppressed_occurrences = {
        occurrence.occurrence_id
        for occurrence in occurrences
        if occurrence.release_id == SUCCESSOR_RELEASE_ID
        and any(
            identity.token in CROSS_ROOT_SINGLETON_TOKENS
            for identity in occurrence.identities
        )
    }
    if len(suppressed_occurrences) != EXPECTED_SUCCESSOR_OCCURRENCES:
        raise ExactIdentityDecisionError(
            "federation-v6 cross-root successor occurrence inventory differs"
        )

    return [
        (
            replace(
                occurrence,
                identities=tuple(
                    identity
                    for identity in occurrence.identities
                    if identity.token not in CROSS_ROOT_SINGLETON_TOKENS
                ),
            )
            if occurrence.occurrence_id in suppressed_occurrences
            else occurrence
        )
        for occurrence in occurrences
    ]


def _federation_input(
    definition: legacy._Definition,
) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = legacy._resolve(
        definition.path,
        definition.federation["index_path"],
        "federation index_path",
    )
    child_paths = {
        str(child["release_id"]): Path(child["release_path"])
        for child in definition.children
    }
    try:
        index = federation_v6.validate_federated_release_index(
            directory,
            child_release_paths=child_paths,
        )
    except (federation_v6.FederatedReleaseError, OSError) as error:
        raise ExactIdentityDecisionError(
            f"federated v6 index validation failed: {error}"
        ) from error
    manifest_checkpoint = legacy._checkpoint(directory / MANIFEST_FILENAME)
    index_checkpoint = legacy._checkpoint(
        directory / federation_v6.INDEX_FILENAME
    )
    if (
        manifest_checkpoint["sha256"]
        != definition.federation["expected_manifest_sha256"]
        or index_checkpoint["sha256"]
        != definition.federation["expected_index_sha256"]
    ):
        raise ExactIdentityDecisionError("federated v6 index hash drifted")
    if (
        index.get("schema_version") != federation_v6.INDEX_SCHEMA_VERSION
        or index.get("format") != federation_v6.INDEX_FORMAT
    ):
        raise ExactIdentityDecisionError("federated v6 index format is unsupported")
    generated_at = legacy._timestamp(
        index.get("generated_at"), "federated v6 generated_at"
    )
    if datetime.fromisoformat(generated_at) >= datetime.fromisoformat(
        definition.recorded_at
    ):
        raise ExactIdentityDecisionError(
            "decision recorded_at must follow the federated v6 index"
        )
    return dict(index), {
        "directory_name": directory.name,
        "manifest": manifest_checkpoint,
        "federated_index": index_checkpoint,
    }


def _inspect_children(
    definition: legacy._Definition, index: dict[str, Any]
) -> list[legacy._Child]:
    """Validate children and the v97-only governed release inventory."""

    children = carrier_v5._inspect_children(definition, index)
    release_ids = {child.release_id for child in children}
    if release_ids != EXPECTED_RELEASE_IDS:
        raise ExactIdentityDecisionError(
            "federation-v6 exact-identity release inventory differs"
        )
    successor = [
        child for child in children if child.release_id == SUCCESSOR_RELEASE_ID
    ]
    review = [child for child in children if child.release_id == REVIEW_RELEASE_ID]
    if (
        len(successor) != 1
        or successor[0].review_only
        or len(review) != 1
        or not review[0].review_only
    ):
        raise ExactIdentityDecisionError(
            "federation-v6 successor/review disposition differs"
        )
    return children


def _prepare_bundle(
    definition: legacy._Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    index, federation_record = _federation_input(definition)
    children = _inspect_children(definition, index)
    processed = [child for child in children if not child.review_only]
    occurrences = _preserve_cross_root_singletons(
        [
            occurrence
            for child in processed
            for occurrence in legacy._load_occurrences(child)
        ]
    )
    occurrence_map = {item.occurrence_id: item for item in occurrences}
    if len(occurrence_map) != len(occurrences):
        raise ExactIdentityDecisionError("occurrence IDs collide across children")
    raw_relationships = [
        relationship
        for child in processed
        for relationship in legacy._raw_relationships(
            child,
            [
                occurrence
                for occurrence in occurrences
                if occurrence.release_id == child.release_id
            ],
        )
    ]
    (
        component_rows,
        component_for,
        ambiguous_candidates,
        component_tokens,
    ) = legacy._build_components(occurrences)
    relationships = legacy._build_relationships(
        occurrences,
        component_for,
        raw_relationships,
        component_tokens,
    )
    release_candidates = [
        candidate
        for child in processed
        for candidate in legacy._load_release_candidates(child, occurrence_map)
    ]
    by_child = {child.release_id: child for child in children}
    legacy._fill_ambiguous_source_hashes(ambiguous_candidates, by_child)
    unresolved = sorted(
        [*release_candidates, *ambiguous_candidates],
        key=lambda item: item["candidate_reference_id"],
    )
    if len(unresolved) != len(
        {item["candidate_reference_id"] for item in unresolved}
    ):
        raise ExactIdentityDecisionError("unresolved candidate references collide")
    lineage = legacy._build_lineage(occurrences, component_for)
    accounting = legacy._accounting(
        children,
        occurrences,
        component_rows,
        relationships,
        raw_relationships,
        unresolved,
    )

    compared = {key: accounting[key] for key in definition.expected}
    expected = dict(definition.expected)
    if compared != expected:
        raise ExactIdentityDecisionError(
            f"decision counts diverged: expected {expected}, found {compared}"
        )
    if any(
        accounting[field] is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError("physical-site accounting must remain null")

    payloads = {
        COMPONENTS_FILENAME: legacy._csv_bytes(
            legacy.COMPONENT_FIELDS, component_rows
        ),
        RELATIONSHIPS_FILENAME: legacy._csv_bytes(
            legacy.RELATIONSHIP_FIELDS, relationships
        ),
        UNRESOLVED_FILENAME: legacy._csv_bytes(
            legacy.UNRESOLVED_FIELDS, unresolved
        ),
        LINEAGE_FILENAME: legacy._csv_bytes(legacy.LINEAGE_FIELDS, lineage),
        ACCOUNTING_FILENAME: legacy._canonical_json(accounting),
        README_FILENAME: legacy._readme(accounting),
        ATTRIBUTION_FILENAME: legacy._attribution(children),
    }
    manifest = {
        "schema_version": legacy.SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "bundle_id": definition.bundle_id,
        "recorded_at": definition.recorded_at,
        "scope": POLICY,
        "definition": {
            "file": definition.path.name,
            "bytes": len(definition.raw),
            "sha256": legacy._sha256_bytes(definition.raw),
        },
        "federation_input": federation_record,
        "input_children": [
            legacy._input_child_record(child) for child in children
        ],
        "counts": accounting,
        "files": {
            name: {"bytes": len(raw), "sha256": legacy._sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
    }
    manifest_raw = legacy._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{legacy._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def validate_exact_identity_decision_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate a closed identity bundle and optionally replay v97 inputs."""

    manifest = legacy.validate_exact_identity_decision_bundle(
        path_value,
        require_frozen=require_frozen,
    )
    if definition_path is not None:
        definition = legacy._load_definition(definition_path)
        expected_definition = {
            "file": definition.path.name,
            "bytes": len(definition.raw),
            "sha256": legacy._sha256_bytes(definition.raw),
        }
        if manifest.get("definition") != expected_definition:
            raise ExactIdentityDecisionError("definition checkpoint differs")
        if verify_inputs:
            expected_payloads, expected_manifest = _prepare_bundle(definition)
            directory = Path(path_value)
            actual_payloads = {
                item.name: item.read_bytes() for item in directory.iterdir()
            }
            if (
                actual_payloads != expected_payloads
                or manifest != expected_manifest
            ):
                raise ExactIdentityDecisionError(
                    "exact-input rebuild differs from decision bundle"
                )
    elif verify_inputs:
        raise ExactIdentityDecisionError(
            "verify_inputs requires the original definition"
        )
    return manifest


__all__ = [
    "ACCOUNTING_FILENAME",
    "ATTRIBUTION_FILENAME",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COMPONENTS_FILENAME",
    "CROSS_ROOT_SINGLETON_TOKENS",
    "DEFINITION_FORMAT",
    "EXPECTED_RELEASE_IDS",
    "EXPECTED_SUCCESSOR_OCCURRENCES",
    "LINEAGE_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "POLICY",
    "README_FILENAME",
    "RELATIONSHIPS_FILENAME",
    "SUCCESSOR_RELEASE_ID",
    "UNRESOLVED_FILENAME",
    "ExactIdentityDecisionError",
    "validate_exact_identity_decision_bundle",
]
