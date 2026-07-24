"""Exact-identity v3 carrier over a publication-v4 federation.

The legacy and accepted v2 identity implementations remain byte-pinned. This
successor keeps every identity, topology, and review policy unchanged while
validating the versioned federation-v3 carrier and each hash-pinned child.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from . import exact_identity_decisions as legacy
from . import federated_release_v3 as federation_v3
from .global_snapshot import GlobalSnapshotError, validate_release_files


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
        index = federation_v3.validate_federated_release_index(
            directory,
            child_release_paths=child_paths,
        )
    except (federation_v3.FederatedReleaseError, OSError) as error:
        raise ExactIdentityDecisionError(
            f"federated v3 index validation failed: {error}"
        ) from error
    manifest_checkpoint = legacy._checkpoint(directory / MANIFEST_FILENAME)
    index_checkpoint = legacy._checkpoint(
        directory / federation_v3.INDEX_FILENAME
    )
    if (
        manifest_checkpoint["sha256"]
        != definition.federation["expected_manifest_sha256"]
        or index_checkpoint["sha256"]
        != definition.federation["expected_index_sha256"]
    ):
        raise ExactIdentityDecisionError("federated v3 index hash drifted")
    if (
        index.get("schema_version") != federation_v3.INDEX_SCHEMA_VERSION
        or index.get("format") != federation_v3.INDEX_FORMAT
    ):
        raise ExactIdentityDecisionError("federated v3 index format is unsupported")
    generated_at = legacy._timestamp(
        index.get("generated_at"), "federated v3 generated_at"
    )
    if datetime.fromisoformat(generated_at.replace("Z", "+00:00")) >= (
        datetime.fromisoformat(definition.recorded_at.replace("Z", "+00:00"))
    ):
        raise ExactIdentityDecisionError(
            "decision recorded_at must follow the federated v3 index"
        )
    return dict(index), {
        "directory_name": directory.name,
        "manifest": manifest_checkpoint,
        "federated_index": index_checkpoint,
    }


def _inspect_children(
    definition: legacy._Definition, index: Mapping[str, Any]
) -> list[legacy._Child]:
    descriptors = index.get("releases")
    if not isinstance(descriptors, list):
        raise ExactIdentityDecisionError(
            "federated v3 release descriptors are invalid"
        )
    by_id = {
        str(item.get("release_id")): item
        for item in descriptors
        if isinstance(item, Mapping)
    }
    definition_ids = {str(item["release_id"]) for item in definition.children}
    if set(by_id) != definition_ids or len(by_id) != len(descriptors):
        raise ExactIdentityDecisionError(
            "decision children do not exactly match the federation"
        )

    children: list[legacy._Child] = []
    for value in definition.children:
        release_id = str(value["release_id"])
        directory = Path(value["release_path"])
        try:
            manifest = validate_release_files(directory)
        except (GlobalSnapshotError, OSError) as error:
            raise ExactIdentityDecisionError(
                f"child release validation failed for {release_id}: {error}"
            ) from error
        manifest_checkpoint = legacy._checkpoint(directory / MANIFEST_FILENAME)
        if manifest_checkpoint["sha256"] != value["expected_manifest_sha256"]:
            raise ExactIdentityDecisionError(
                f"child manifest hash drifted: {release_id}"
            )

        descriptor = by_id[release_id]
        descriptor_manifest = descriptor.get("manifest")
        if (
            not isinstance(descriptor_manifest, Mapping)
            or descriptor_manifest.get("sha256")
            != manifest_checkpoint["sha256"]
            or descriptor.get("files") != manifest.get("files")
        ):
            raise ExactIdentityDecisionError(
                f"child hashes do not match federation descriptor: {release_id}"
            )

        publication_version = manifest.get("publication_contract_version")
        descriptor_version = descriptor_manifest.get(
            "publication_contract_version"
        )
        if descriptor_version != publication_version:
            raise ExactIdentityDecisionError(
                f"child publication contract does not reconcile: {release_id}"
            )
        try:
            freshness = federation_v3._freshness_contract(
                manifest,
                label=f"{release_id} child manifest",
            )
            descriptor_freshness = federation_v3._freshness_contract(
                descriptor_manifest,
                label=f"{release_id} federation descriptor",
            )
        except federation_v3.FederatedReleaseError as error:
            raise ExactIdentityDecisionError(
                f"child lifecycle descriptor is invalid: {release_id}: {error}"
            ) from error
        if descriptor_freshness != freshness:
            raise ExactIdentityDecisionError(
                f"child lifecycle descriptor does not reconcile: {release_id}"
            )
        if freshness is not None:
            try:
                federation_v3._validate_freshness_csv(
                    directory,
                    expected_records=freshness["lifecycle_freshness_records"],
                    entity_records=int(manifest["entities"]),
                )
            except (federation_v3.FederatedReleaseError, OSError) as error:
                raise ExactIdentityDecisionError(
                    f"child lifecycle rows are invalid: {release_id}: {error}"
                ) from error

        scope = descriptor.get("scope")
        review_only = manifest.get("review_only", False)
        if (
            not isinstance(scope, Mapping)
            or not isinstance(review_only, bool)
            or scope.get("review_only") is not review_only
            or value["expected_review_only"] is not review_only
        ):
            raise ExactIdentityDecisionError(
                f"child review scope does not reconcile: {release_id}"
            )
        child_recorded_at = legacy._timestamp(
            manifest.get("recorded_at"), f"{release_id} recorded_at"
        )
        if child_recorded_at >= definition.recorded_at:
            raise ExactIdentityDecisionError(
                f"decision recorded_at must follow child release: {release_id}"
            )
        children.append(
            legacy._Child(
                release_id=release_id,
                directory=directory,
                manifest=manifest,
                manifest_checkpoint=manifest_checkpoint,
                review_only=review_only,
                disposition=(
                    "excluded_review_only" if review_only else "processed"
                ),
                federation_descriptor=descriptor,
            )
        )
    return sorted(children, key=lambda item: item.release_id)


def _prepare_bundle(
    definition: legacy._Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    index, federation_record = _federation_input(definition)
    children = _inspect_children(definition, index)
    processed = [child for child in children if not child.review_only]
    occurrences = [
        occurrence
        for child in processed
        for occurrence in legacy._load_occurrences(child)
    ]
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
        raise ExactIdentityDecisionError(
            "physical-site accounting must remain null"
        )

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
    """Validate a closed bundle and optionally replay all v3-bound inputs."""

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


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    legacy._thaw_tree(stage)
    shutil.rmtree(stage)


def write_exact_identity_decision_bundle(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Double-rebuild, freeze, and atomically publish one v3-bound bundle."""

    definition = legacy._load_definition(definition_path)
    payloads, manifest = _prepare_bundle(definition)
    rechecked_payloads, rechecked_manifest = _prepare_bundle(definition)
    if rechecked_payloads != payloads or rechecked_manifest != manifest:
        raise ExactIdentityDecisionError(
            "decision inputs changed or two offline reconstructions differ"
        )
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.is_symlink():
        raise ExactIdentityDecisionError("decision output may not be a symlink")
    if output.exists():
        validated = validate_exact_identity_decision_bundle(
            output,
            definition_path=definition.path,
            verify_inputs=True,
        )
        if any(
            (output / name).read_bytes() != raw
            for name, raw in payloads.items()
        ):
            raise ExactIdentityDecisionError(
                "existing decision bundle is valid but not byte-identical"
            )
        return validated

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir() or not output.name:
        raise ExactIdentityDecisionError("decision output parent is invalid")
    stage = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent)
    )
    published = False
    try:
        for name, raw in payloads.items():
            legacy._write_bytes(stage / name, raw)
        validate_exact_identity_decision_bundle(stage, require_frozen=False)
        legacy._freeze_tree(stage)
        validate_exact_identity_decision_bundle(stage)
        try:
            federation_v3._promote_noreplace(stage, output)
        except federation_v3.FederatedReleaseError as error:
            raise ExactIdentityDecisionError(str(error)) from error
        published = True
        return validate_exact_identity_decision_bundle(
            output,
            definition_path=definition.path,
            verify_inputs=True,
        )
    finally:
        if not published:
            _discard_stage(stage)


build_exact_identity_decision_bundle = write_exact_identity_decision_bundle


__all__ = [
    "ACCOUNTING_FILENAME",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COMPONENTS_FILENAME",
    "DEFINITION_FORMAT",
    "ExactIdentityDecisionError",
    "LINEAGE_FILENAME",
    "POLICY",
    "RELATIONSHIPS_FILENAME",
    "UNRESOLVED_FILENAME",
    "build_exact_identity_decision_bundle",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]
