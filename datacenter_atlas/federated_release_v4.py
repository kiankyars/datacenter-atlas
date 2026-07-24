"""Federation carrier accepting the explicit geometry non-inference guard.

The wire format remains the accepted federation-v2 format.  This module
isolates the one child-manifest extension introduced by open seed v85 and
later, while delegating every inherited validation rule to the frozen v3
carrier.
"""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from . import federated_release as legacy
from . import federated_release_v3 as base


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
GEOMETRY_NON_INFERENCE_FIELD = "geometry_only_representative_point_inferred"
GEOMETRY_MANIFEST_FIELDS = frozenset({GEOMETRY_NON_INFERENCE_FIELD})

FederatedIndexBundle = base.FederatedIndexBundle
FederatedReleaseError = base.FederatedReleaseError
_ChildDefinition = base._ChildDefinition
_promote_noreplace = base._promote_noreplace


def _geometry_contract(
    manifest: Mapping[str, Any], *, label: str
) -> dict[str, bool] | None:
    if GEOMETRY_NON_INFERENCE_FIELD not in manifest:
        return None
    if manifest.get("publication_contract_version") != 4:
        raise FederatedReleaseError(
            f"{label} geometry guard requires publication contract version 4"
        )
    if manifest.get(GEOMETRY_NON_INFERENCE_FIELD) is not False:
        raise FederatedReleaseError(
            f"{label} geometry-only representative point must not be inferred"
        )
    return {GEOMETRY_NON_INFERENCE_FIELD: False}


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
        | base.FRESHNESS_MANIFEST_FIELDS
        | GEOMETRY_MANIFEST_FIELDS
    )
    manifest_keys = set(manifest)
    if (
        not legacy.RELEASE_REQUIRED_MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(allowed)
    ):
        raise FederatedReleaseError("child release manifest schema is invalid")
    geometry = _geometry_contract(manifest, label="child release")
    if geometry is None:
        return base._inspect_child(definition)

    sanitized_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in GEOMETRY_MANIFEST_FIELDS
    }
    sanitized_raw = legacy._canonical_json(sanitized_manifest)
    with tempfile.TemporaryDirectory(
        prefix="federated-v4-child-", dir="/private/tmp"
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

    descriptor_manifest = descriptor["manifest"]
    descriptor_manifest["bytes"] = len(manifest_raw)
    descriptor_manifest["sha256"] = manifest_sha256
    descriptor_manifest.update(geometry)
    return descriptor


def build_federated_release_index(
    definition_path: str | Path,
) -> FederatedIndexBundle:
    """Build deterministic federation-v2 bytes from local frozen children."""

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


def _validate_descriptor(value: Any, position: int) -> dict[str, Any]:
    label = f"federated release descriptor {position}"
    if not isinstance(value, Mapping):
        raise FederatedReleaseError(f"{label} schema is invalid")
    manifest = value.get("manifest")
    if not isinstance(manifest, Mapping):
        raise FederatedReleaseError(f"{label} manifest schema is invalid")
    geometry = _geometry_contract(manifest, label=f"{label} manifest")
    allowed = (
        {
            "file",
            "bytes",
            "sha256",
            "format",
            "as_of",
            "recorded_at",
            "publication_contract_version",
        }
        | base.FRESHNESS_MANIFEST_FIELDS
        | GEOMETRY_MANIFEST_FIELDS
    )
    required = {"file", "bytes", "sha256", "format", "as_of", "recorded_at"}
    if not required.issubset(manifest) or not set(manifest).issubset(allowed):
        raise FederatedReleaseError(f"{label} manifest schema is invalid")
    sanitized = copy.deepcopy(value)
    sanitized_manifest = sanitized["manifest"]
    for field in GEOMETRY_MANIFEST_FIELDS:
        sanitized_manifest.pop(field, None)
    normalized = base._validate_descriptor(sanitized, position)
    if geometry is not None:
        normalized["manifest"].update(geometry)
    return normalized


def _shadow_v3_bundle(
    manifest: Mapping[str, Any], index: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    sanitized_index = copy.deepcopy(index)
    for descriptor in sanitized_index["releases"]:
        for field in GEOMETRY_MANIFEST_FIELDS:
            descriptor["manifest"].pop(field, None)
    sanitized_index_raw = legacy._canonical_json(sanitized_index)
    sanitized_manifest = copy.deepcopy(manifest)
    artifact = sanitized_manifest["artifacts"][INDEX_FILENAME]
    artifact["bytes"] = len(sanitized_index_raw)
    artifact["sha256"] = hashlib.sha256(sanitized_index_raw).hexdigest()
    return sanitized_manifest, sanitized_index


def validate_federated_release_index(
    directory_path: str | Path,
    *,
    child_release_paths: Mapping[str, str | Path] | None = None,
    require_frozen: bool = True,
) -> Mapping[str, Any]:
    """Validate federation bytes and optionally reconstruct every child."""

    directory = Path(directory_path)
    if directory.is_symlink() or not directory.is_dir():
        raise FederatedReleaseError(
            f"federated index must be a regular directory: {directory}"
        )
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != FEDERATED_BUNDLE_FILES or len(
        entries
    ) != len(FEDERATED_BUNDLE_FILES):
        raise FederatedReleaseError("federated index bundle file set is invalid")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise FederatedReleaseError(
                f"federated index entry must be a regular file: {entry.name}"
            )

    index_raw = (directory / INDEX_FILENAME).read_bytes()
    manifest_raw = (directory / MANIFEST_FILENAME).read_bytes()
    sidecar_raw = (directory / MANIFEST_HASH_FILENAME).read_bytes()
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise FederatedReleaseError("federated manifest sidecar does not match")
    manifest = legacy._json_object(manifest_raw, "federated bundle manifest")
    index = legacy._json_object(index_raw, "federated release index")
    if (
        manifest_raw != legacy._canonical_json(manifest)
        or index_raw != legacy._canonical_json(index)
    ):
        raise FederatedReleaseError("federated bundle JSON is not canonical")
    if (
        manifest.get("schema_version") != INDEX_SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or index.get("schema_version") != INDEX_SCHEMA_VERSION
        or index.get("format") != INDEX_FORMAT
    ):
        raise FederatedReleaseError("federated v2 bundle identity is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {INDEX_FILENAME}:
        raise FederatedReleaseError("federated artifact inventory is invalid")
    artifact = artifacts[INDEX_FILENAME]
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "format",
        "release_bundles",
        "bytes",
        "sha256",
    }:
        raise FederatedReleaseError("federated index checkpoint is invalid")
    if artifact.get("format") != INDEX_FORMAT:
        raise FederatedReleaseError("federated index artifact format is invalid")
    if (
        legacy._nonnegative_integer(artifact.get("bytes"), "federated index bytes")
        != len(index_raw)
        or legacy._sha256(artifact.get("sha256"), "federated index sha256")
        != hashlib.sha256(index_raw).hexdigest()
    ):
        raise FederatedReleaseError("federated index checkpoint does not match bytes")
    releases = index.get("releases")
    if not isinstance(releases, list):
        raise FederatedReleaseError("federated index releases must be an array")
    normalized = [
        _validate_descriptor(value, position)
        for position, value in enumerate(releases)
    ]
    if releases != normalized:
        raise FederatedReleaseError("federated release descriptors are not canonical")

    sanitized_manifest, sanitized_index = _shadow_v3_bundle(manifest, index)
    sanitized_index_raw = legacy._canonical_json(sanitized_index)
    sanitized_manifest_raw = legacy._canonical_json(sanitized_manifest)
    sanitized_sidecar = (
        f"{hashlib.sha256(sanitized_manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    with tempfile.TemporaryDirectory(
        prefix="federated-v4-index-", dir="/private/tmp"
    ) as temporary:
        shadow = Path(temporary) / "bundle"
        shadow.mkdir()
        (shadow / INDEX_FILENAME).write_bytes(sanitized_index_raw)
        (shadow / MANIFEST_FILENAME).write_bytes(sanitized_manifest_raw)
        (shadow / MANIFEST_HASH_FILENAME).write_bytes(sanitized_sidecar)
        validated = base.validate_federated_release_index(
            shadow, require_frozen=False
        )
    if validated != sanitized_index:
        raise FederatedReleaseError("federated v3 projection differs")

    if child_release_paths is not None:
        release_ids = [release["release_id"] for release in normalized]
        if set(child_release_paths) != set(release_ids):
            raise FederatedReleaseError(
                "child path mapping must exactly match federated release IDs"
            )
        for release in normalized:
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

    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise FederatedReleaseError("federated index root must have mode 0555")
        wrong_modes = [
            entry.name
            for entry in entries
            if stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise FederatedReleaseError(
                "federated index files must have mode 0444: "
                + ", ".join(sorted(wrong_modes))
            )
    return index


def _bundle_payloads(bundle: FederatedIndexBundle) -> dict[str, bytes]:
    return {
        INDEX_FILENAME: bundle.index_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


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
            base._discard_stage(stage)
    return first.index


__all__ = [
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
