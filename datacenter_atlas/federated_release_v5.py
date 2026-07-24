"""Federation carrier for append-only child-manifest lineage metadata.

The federated index wire format remains the accepted v2 format.  This carrier
accepts the four append-only audit fields first published by open seed v92,
validates them, and deliberately keeps them out of the compact child
descriptor.  The descriptor still pins the complete original manifest bytes
and hash, so no source information is weakened or rewritten.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from . import federated_release as legacy
from . import federated_release_v3 as carrier_v3
from . import federated_release_v4 as base


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
APPEND_ONLY_MANIFEST_FIELDS = frozenset(
    {
        "append_only_base_release",
        "base_rows_frozen",
        "internal_database_delta",
        "public_release_delta",
    }
)
INTERNAL_DELTA_FIELDS = frozenset(
    {"capacity_estimates", "entities", "evidence", "lifecycle_observations"}
)
PUBLIC_DELTA_FIELDS = frozenset(
    {
        "capacity_estimates",
        "construction_pipeline",
        "construction_source_signals",
        "entities",
        "evidence",
        "lifecycle_freshness",
    }
)

FederatedIndexBundle = base.FederatedIndexBundle
FederatedReleaseError = base.FederatedReleaseError
_ChildDefinition = base._ChildDefinition
_promote_noreplace = base._promote_noreplace


def _validated_delta(
    value: Any, *, fields: frozenset[str], label: str
) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FederatedReleaseError(f"{label} schema is invalid")
    return {
        field: legacy._nonnegative_integer(value[field], f"{label} {field}")
        for field in sorted(fields)
    }


def _append_only_contract(
    manifest: Mapping[str, Any], *, label: str
) -> dict[str, Any] | None:
    present = APPEND_ONLY_MANIFEST_FIELDS & set(manifest)
    if not present:
        return None
    if present != APPEND_ONLY_MANIFEST_FIELDS:
        raise FederatedReleaseError(
            f"{label} append-only lineage fields must be present together"
        )
    if manifest.get("publication_contract_version") != 4:
        raise FederatedReleaseError(
            f"{label} append-only lineage requires publication contract version 4"
        )
    base_release = legacy._required_text(
        manifest.get("append_only_base_release"),
        f"{label} append_only_base_release",
    )
    if manifest.get("base_rows_frozen") is not True:
        raise FederatedReleaseError(f"{label} base_rows_frozen must be true")
    internal = _validated_delta(
        manifest.get("internal_database_delta"),
        fields=INTERNAL_DELTA_FIELDS,
        label=f"{label} internal_database_delta",
    )
    public = _validated_delta(
        manifest.get("public_release_delta"),
        fields=PUBLIC_DELTA_FIELDS,
        label=f"{label} public_release_delta",
    )
    if internal["entities"] != public["entities"]:
        raise FederatedReleaseError(
            f"{label} append-only entity deltas must agree"
        )
    return {
        "append_only_base_release": base_release,
        "base_rows_frozen": True,
        "internal_database_delta": internal,
        "public_release_delta": public,
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
    allowed = (
        legacy.RELEASE_REQUIRED_MANIFEST_KEYS
        | legacy.RELEASE_OPTIONAL_MANIFEST_KEYS
        | carrier_v3.FRESHNESS_MANIFEST_FIELDS
        | base.GEOMETRY_MANIFEST_FIELDS
        | APPEND_ONLY_MANIFEST_FIELDS
    )
    manifest_keys = set(manifest)
    if (
        not legacy.RELEASE_REQUIRED_MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(allowed)
    ):
        raise FederatedReleaseError("child release manifest schema is invalid")
    append_only = _append_only_contract(manifest, label="child release")
    if append_only is None:
        return base._inspect_child(definition)

    sanitized_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in APPEND_ONLY_MANIFEST_FIELDS
    }
    sanitized_raw = legacy._canonical_json(sanitized_manifest)
    with tempfile.TemporaryDirectory(
        prefix="federated-v5-child-", dir="/private/tmp"
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
    """Build deterministic v2 federation bytes from local frozen children."""

    path = Path(definition_path)
    raw = legacy._regular_bytes(path, "federation definition")
    document = legacy._json_object(raw, "federation definition")
    if raw != legacy._canonical_json(document):
        raise FederatedReleaseError("federation definition is not canonical JSON")
    definition_raw, generated_at, definitions = legacy._definition(path)
    releases = [_inspect_child(definition) for definition in definitions]
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    latest_child = max(
        datetime.fromisoformat(
            release["manifest"]["recorded_at"].replace("Z", "+00:00")
        )
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
    """Validate bytes with v4, then reconstruct append-only children with v5."""

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


def _discard_stage(stage: Path) -> None:
    if not stage.exists():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        entry.chmod(0o600)
    shutil.rmtree(stage)


def write_federated_release_index(
    definition_path: str | Path, output_directory: str | Path
) -> Mapping[str, Any]:
    """Double-build, validate, freeze, and no-replace publish one index."""

    first = build_federated_release_index(definition_path)
    second = build_federated_release_index(definition_path)
    if first != second:
        raise FederatedReleaseError("two offline federation reconstructions differ")
    expected = _bundle_payloads(first)
    output = Path(output_directory)
    if output.is_symlink():
        raise FederatedReleaseError(f"federated output may not be a symlink: {output}")
    if output.exists():
        if not output.is_dir():
            raise FederatedReleaseError(
                f"federated output is not a directory: {output}"
            )
        validate_federated_release_index(output)
        differing = [
            name
            for name, raw in expected.items()
            if (output / name).read_bytes() != raw
        ]
        if differing:
            raise FederatedReleaseError(
                "existing federated index is valid but not byte-identical; "
                f"refusing to replace: {sorted(differing)}"
            )
        return first.index

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise FederatedReleaseError(
            f"federated output parent is not a regular directory: {parent}"
        )
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=parent))
    published = False
    try:
        for name, raw in expected.items():
            legacy._write_bytes(stage / name, raw)
        for entry in stage.iterdir():
            entry.chmod(FROZEN_FILE_MODE)
        stage.chmod(FROZEN_DIRECTORY_MODE)
        validate_federated_release_index(stage)
        _promote_noreplace(stage, output)
        published = True
        validate_federated_release_index(output)
    finally:
        if not published:
            _discard_stage(stage)
    return first.index


__all__ = [
    "APPEND_ONLY_MANIFEST_FIELDS",
    "BUNDLE_FORMAT",
    "FEDERATION_POLICY",
    "FederatedIndexBundle",
    "FederatedReleaseError",
    "GEOMETRY_NON_INFERENCE_FIELD",
    "INDEX_FILENAME",
    "INDEX_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "build_federated_release_index",
    "validate_federated_release_index",
    "write_federated_release_index",
]
