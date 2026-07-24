"""Federation carrier for governed open-seed successor manifests.

The federated v2 wire format is unchanged.  This carrier accepts the governed
successor metadata first published after open seed v92, validates it as a
closed contract, and then constructs the compact child descriptor through the
v5 carrier.  The descriptor continues to pin the complete original manifest
bytes and SHA-256; no governed field is rewritten in source lineage.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from . import federated_release as legacy
from . import federated_release_v3 as freshness
from . import federated_release_v4 as wire
from . import federated_release_v5 as base

INDEX_FILENAME = base.INDEX_FILENAME
MANIFEST_FILENAME = base.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = base.MANIFEST_HASH_FILENAME
FEDERATED_BUNDLE_FILES = base.FEDERATED_BUNDLE_FILES
INDEX_SCHEMA_VERSION = base.INDEX_SCHEMA_VERSION
INDEX_FORMAT = base.INDEX_FORMAT
BUNDLE_FORMAT = base.BUNDLE_FORMAT
FEDERATION_POLICY = base.FEDERATION_POLICY
FROZEN_FILE_MODE = base.FROZEN_FILE_MODE
FROZEN_DIRECTORY_MODE = base.FROZEN_DIRECTORY_MODE
GEOMETRY_NON_INFERENCE_FIELD = base.GEOMETRY_NON_INFERENCE_FIELD
GEOMETRY_MANIFEST_FIELDS = base.GEOMETRY_MANIFEST_FIELDS
APPEND_ONLY_MANIFEST_FIELDS = base.APPEND_ONLY_MANIFEST_FIELDS

GOVERNED_MANIFEST_FIELDS = frozenset(
    {
        "claim_boundary",
        "coordinate_boundary",
        "curated_source_input_appends",
        "curated_source_input_delta",
        "curated_source_input_replacements",
        "governed_base_row_replacements",
        "governed_successor_base_release",
        "public_source_input_rows_delta",
        "stale_status_suppression",
        "unaffected_base_rows_frozen",
    }
)
GOVERNED_INTERNAL_DELTA_FIELDS = frozenset(
    {
        "campuses",
        "capacity_estimates",
        "entities",
        "entity_snapshots",
        "evidence",
        "lifecycle_observations",
        "operating_model_observations",
        "projects",
        "workload_observations",
    }
)
GOVERNED_PUBLIC_DELTA_FIELDS = frozenset(
    {
        "capacity_estimates",
        "construction_pipeline",
        "construction_source_signals",
        "entities",
        "evidence",
        "lifecycle_freshness",
        "source_input_rows",
    }
)

FederatedIndexBundle = base.FederatedIndexBundle
FederatedReleaseError = base.FederatedReleaseError
_ChildDefinition = base._ChildDefinition
_promote_noreplace = base._promote_noreplace


def _closed_nonnegative_delta(
    value: Any, *, fields: frozenset[str], label: str
) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FederatedReleaseError(f"{label} schema is invalid")
    return {
        field: legacy._nonnegative_integer(value[field], f"{label} {field}")
        for field in sorted(fields)
    }


def _governed_contract(manifest: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    present = GOVERNED_MANIFEST_FIELDS & set(manifest)
    if present != GOVERNED_MANIFEST_FIELDS:
        raise FederatedReleaseError(
            f"{label} governed successor fields must be present together"
        )
    if manifest.get("publication_contract_version") != 4:
        raise FederatedReleaseError(
            f"{label} governed successor requires publication contract version 4"
        )
    internal = _closed_nonnegative_delta(
        manifest.get("internal_database_delta"),
        fields=GOVERNED_INTERNAL_DELTA_FIELDS,
        label=f"{label} internal_database_delta",
    )
    public = _closed_nonnegative_delta(
        manifest.get("public_release_delta"),
        fields=GOVERNED_PUBLIC_DELTA_FIELDS,
        label=f"{label} public_release_delta",
    )
    appends = legacy._nonnegative_integer(
        manifest.get("curated_source_input_appends"),
        f"{label} curated_source_input_appends",
    )
    replacements = legacy._nonnegative_integer(
        manifest.get("curated_source_input_replacements"),
        f"{label} curated_source_input_replacements",
    )
    delta = legacy._nonnegative_integer(
        manifest.get("curated_source_input_delta"),
        f"{label} curated_source_input_delta",
    )
    source_rows = legacy._nonnegative_integer(
        manifest.get("public_source_input_rows_delta"),
        f"{label} public_source_input_rows_delta",
    )
    base_release = legacy._required_text(
        manifest.get("append_only_base_release"),
        f"{label} append_only_base_release",
    )
    governed_base = legacy._required_text(
        manifest.get("governed_successor_base_release"),
        f"{label} governed_successor_base_release",
    )
    mappings = {
        name: manifest.get(name)
        for name in (
            "claim_boundary",
            "coordinate_boundary",
            "governed_base_row_replacements",
            "stale_status_suppression",
        )
    }
    if (
        manifest.get("base_rows_frozen") is not True
        or manifest.get("unaffected_base_rows_frozen") is not True
        or any(not isinstance(value, Mapping) for value in mappings.values())
        or internal["campuses"] + internal["projects"] != internal["entities"]
        or internal["entity_snapshots"] != internal["entities"]
        or public["entities"] != internal["entities"]
        or source_rows != public["source_input_rows"]
        or delta != appends - replacements
        or governed_base != base_release
    ):
        raise FederatedReleaseError(f"{label} governed successor contract differs")
    return {
        "internal": internal,
        "public": public,
        "base_release": base_release,
        "mappings": mappings,
    }


def _inspect_child(definition: _ChildDefinition) -> dict[str, Any]:
    release = definition.release_path
    if release.is_symlink() or not release.is_dir():
        raise FederatedReleaseError(
            f"child release must be a regular directory: {release}"
        )
    manifest_path = release / MANIFEST_FILENAME
    manifest_raw = legacy._regular_bytes(manifest_path, "child release manifest")
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha256 != definition.expected_manifest_sha256:
        raise FederatedReleaseError(
            f"child {definition.release_id} manifest SHA-256 does not match definition"
        )
    manifest = legacy._json_object(manifest_raw, "child release manifest")
    if manifest_raw != legacy._canonical_json(manifest):
        raise FederatedReleaseError("child release manifest is not canonical JSON")
    governed_present = GOVERNED_MANIFEST_FIELDS & set(manifest)
    if not governed_present:
        return base._inspect_child(definition)
    allowed = (
        legacy.RELEASE_REQUIRED_MANIFEST_KEYS
        | legacy.RELEASE_OPTIONAL_MANIFEST_KEYS
        | freshness.FRESHNESS_MANIFEST_FIELDS
        | wire.GEOMETRY_MANIFEST_FIELDS
        | APPEND_ONLY_MANIFEST_FIELDS
        | GOVERNED_MANIFEST_FIELDS
    )
    if not legacy.RELEASE_REQUIRED_MANIFEST_KEYS.issubset(manifest) or not set(
        manifest
    ).issubset(allowed):
        raise FederatedReleaseError("child release manifest schema is invalid")
    contract = _governed_contract(manifest, label="child release")
    sanitized = {
        key: value
        for key, value in manifest.items()
        if key not in GOVERNED_MANIFEST_FIELDS
    }
    sanitized["internal_database_delta"] = {
        field: contract["internal"][field] for field in base.INTERNAL_DELTA_FIELDS
    }
    sanitized["public_release_delta"] = {
        field: contract["public"][field] for field in base.PUBLIC_DELTA_FIELDS
    }
    sanitized_raw = legacy._canonical_json(sanitized)
    with tempfile.TemporaryDirectory(
        prefix="federated-v6-child-", dir="/private/tmp"
    ) as temporary:
        shadow = Path(temporary) / release.name
        shadow.mkdir()
        for entry in release.iterdir():
            if entry.name != MANIFEST_FILENAME:
                shutil.copy2(entry, shadow / entry.name)
        (shadow / MANIFEST_FILENAME).write_bytes(sanitized_raw)
        sanitized_definition = _ChildDefinition(
            release_id=definition.release_id,
            release_path=shadow,
            reference=definition.reference,
            expected_manifest_sha256=hashlib.sha256(sanitized_raw).hexdigest(),
            license_expression=definition.license_expression,
            rights_notice=definition.rights_notice,
        )
        descriptor = base._inspect_child(sanitized_definition)
    descriptor["manifest"]["bytes"] = len(manifest_raw)
    descriptor["manifest"]["sha256"] = manifest_sha256
    return descriptor


def build_federated_release_index(
    definition_path: str | Path,
) -> FederatedIndexBundle:
    path = Path(definition_path)
    raw = legacy._regular_bytes(path, "federation definition")
    document = legacy._json_object(raw, "federation definition")
    if raw != legacy._canonical_json(document):
        raise FederatedReleaseError("federation definition is not canonical JSON")
    definition_raw, generated_at, definitions = legacy._definition(path)
    releases = [_inspect_child(definition) for definition in definitions]
    generated = datetime.fromisoformat(generated_at)
    latest_child = max(
        datetime.fromisoformat(release["manifest"]["recorded_at"])
        for release in releases
    )
    if generated <= latest_child:
        raise FederatedReleaseError(
            "federation generated_at must follow every child recorded_at"
        )
    totals = legacy._aggregate_counts(releases, include_scope_splits=True)
    index = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "format": INDEX_FORMAT,
        "generated_at": generated_at,
        "policy": dict(FEDERATION_POLICY),
        "counts": totals,
        "releases": releases,
    }
    index_bytes = legacy._canonical_json(index)
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "generated_at": generated_at,
        "scope": dict(FEDERATION_POLICY),
        "definition": {
            "file": path.name,
            "bytes": len(definition_raw),
            "sha256": hashlib.sha256(definition_raw).hexdigest(),
        },
        "artifacts": {
            INDEX_FILENAME: {
                "format": INDEX_FORMAT,
                "release_bundles": len(releases),
                "bytes": len(index_bytes),
                "sha256": hashlib.sha256(index_bytes).hexdigest(),
            }
        },
    }
    manifest_bytes = legacy._canonical_json(manifest)
    manifest_hash_bytes = (
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return FederatedIndexBundle(
        index_bytes=index_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        index=index,
        manifest=manifest,
    )


def validate_federated_release_index(
    directory_path: str | Path,
    *,
    child_release_paths: Mapping[str, str | Path] | None = None,
    require_frozen: bool = True,
) -> Mapping[str, Any]:
    index = base.validate_federated_release_index(
        directory_path, require_frozen=require_frozen
    )
    if child_release_paths is not None:
        release_ids = [release["release_id"] for release in index["releases"]]
        if set(child_release_paths) != set(release_ids):
            raise FederatedReleaseError(
                "child path mapping must exactly match federated release IDs"
            )
        for release in index["releases"]:
            release_id = release["release_id"]
            definition = _ChildDefinition(
                release_id=release_id,
                release_path=Path(child_release_paths[release_id]),
                reference=release["reference"],
                expected_manifest_sha256=release["manifest"]["sha256"],
                license_expression=release["rights"]["license_expression"],
                rights_notice=release["rights"]["rights_notice"],
            )
            if _inspect_child(definition) != release:
                raise FederatedReleaseError(
                    f"federated child descriptor drifted: {release_id}"
                )
    return index


def _bundle_payloads(bundle: FederatedIndexBundle) -> dict[str, bytes]:
    return {
        INDEX_FILENAME: bundle.index_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


__all__ = [
    "BUNDLE_FORMAT",
    "FEDERATION_POLICY",
    "GEOMETRY_NON_INFERENCE_FIELD",
    "GOVERNED_MANIFEST_FIELDS",
    "INDEX_FILENAME",
    "INDEX_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "FederatedIndexBundle",
    "FederatedReleaseError",
    "build_federated_release_index",
    "validate_federated_release_index",
]
