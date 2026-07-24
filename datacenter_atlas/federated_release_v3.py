"""Versioned federation v3 carrier with publication-v4 freshness semantics.

This strict successor preserves the accepted v2 wire format and closed legacy
validation primitives while isolating new publications from the frozen v2
implementation.
"""

from __future__ import annotations

import copy
import csv
import ctypes
from datetime import datetime
import errno
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any, Mapping

from . import federated_release as legacy


INDEX_FILENAME = legacy.INDEX_FILENAME
MANIFEST_FILENAME = legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = legacy.MANIFEST_HASH_FILENAME
FEDERATED_BUNDLE_FILES = legacy.FEDERATED_BUNDLE_FILES
DEFINITION_SCHEMA_VERSION = legacy.DEFINITION_SCHEMA_VERSION
INDEX_SCHEMA_VERSION = 2
INDEX_FORMAT = "datacenter-atlas-federated-release-index-v2"
BUNDLE_FORMAT = "datacenter-atlas-federated-index-bundle-v2"
CHILD_RELEASE_FORMAT = legacy.CHILD_RELEASE_FORMAT
FEDERATION_POLICY = legacy.FEDERATION_POLICY
REQUIRED_CHILD_FILES = legacy.REQUIRED_CHILD_FILES
FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555
MAX_SUPPORTED_PUBLICATION_CONTRACT_VERSION = 4
FRESHNESS_FILENAME = "lifecycle_freshness.csv"
FRESHNESS_MANIFEST_FIELDS = frozenset(
    {
        "current_status_inferred",
        "lifecycle_freshness_records",
        "lifecycle_status_semantics",
    }
)

FederatedIndexBundle = legacy.FederatedIndexBundle
FederatedReleaseError = legacy.FederatedReleaseError
_ChildDefinition = legacy._ChildDefinition


def _publication_contract_version(manifest: Mapping[str, Any], label: str) -> int | None:
    value = manifest.get("publication_contract_version")
    if value is None:
        return None
    version = legacy._positive_integer(value, f"{label} publication_contract_version")
    if version > MAX_SUPPORTED_PUBLICATION_CONTRACT_VERSION:
        raise FederatedReleaseError(
            f"{label} publication contract version is unsupported: {version}"
        )
    return version


def _freshness_contract(
    manifest: Mapping[str, Any], *, label: str
) -> dict[str, Any] | None:
    version = _publication_contract_version(manifest, label)
    present = FRESHNESS_MANIFEST_FIELDS & set(manifest)
    if version != 4:
        if present:
            raise FederatedReleaseError(
                f"{label} freshness fields require publication contract version 4"
            )
        return None
    if present != FRESHNESS_MANIFEST_FIELDS:
        raise FederatedReleaseError(
            f"{label} publication-v4 freshness fields must be present together"
        )
    if manifest.get("current_status_inferred") is not False:
        raise FederatedReleaseError(
            f"{label} current_status_inferred must be false"
        )
    records = legacy._nonnegative_integer(
        manifest.get("lifecycle_freshness_records"),
        f"{label} lifecycle_freshness_records",
    )
    if manifest.get("lifecycle_status_semantics") != "last_observed":
        raise FederatedReleaseError(
            f"{label} lifecycle_status_semantics must be last_observed"
        )
    return {
        "current_status_inferred": False,
        "lifecycle_freshness_records": records,
        "lifecycle_status_semantics": "last_observed",
    }


def _child_manifest(
    definition: _ChildDefinition,
) -> tuple[bytes, dict[str, Any], dict[str, dict[str, Any]], dict[str, Any] | None]:
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
    manifest_keys = set(manifest)
    allowed = (
        legacy.RELEASE_REQUIRED_MANIFEST_KEYS
        | legacy.RELEASE_OPTIONAL_MANIFEST_KEYS
        | FRESHNESS_MANIFEST_FIELDS
    )
    if (
        not legacy.RELEASE_REQUIRED_MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(allowed)
    ):
        raise FederatedReleaseError("child release manifest schema is invalid")
    if manifest.get("format") != CHILD_RELEASE_FORMAT:
        raise FederatedReleaseError("child release format is unsupported")
    freshness = _freshness_contract(manifest, label="child release")

    files_value = manifest.get("files")
    if not isinstance(files_value, Mapping) or not files_value:
        raise FederatedReleaseError("child release files inventory is invalid")
    files: dict[str, dict[str, Any]] = {}
    for filename, value in files_value.items():
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename == MANIFEST_FILENAME
        ):
            raise FederatedReleaseError("child release contains an unsafe filename")
        files[filename] = legacy._checkpoint(value, f"child file {filename}")
    if not REQUIRED_CHILD_FILES.issubset(files):
        missing = sorted(REQUIRED_CHILD_FILES - set(files))
        raise FederatedReleaseError(
            f"child release is missing required provenance files: {missing}"
        )
    if freshness is not None and FRESHNESS_FILENAME not in files:
        raise FederatedReleaseError(
            "publication-v4 child must publish lifecycle_freshness.csv"
        )

    entries = list(release.iterdir())
    expected_names = set(files) | {MANIFEST_FILENAME}
    if {entry.name for entry in entries} != expected_names or len(entries) != len(
        expected_names
    ):
        raise FederatedReleaseError("child release file set differs from its manifest")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise FederatedReleaseError(
                f"child release entry must be a regular file: {entry.name}"
            )
        if entry.name == MANIFEST_FILENAME:
            continue
        raw = entry.read_bytes()
        checkpoint = files[entry.name]
        if (
            len(raw) != checkpoint["bytes"]
            or hashlib.sha256(raw).hexdigest() != checkpoint["sha256"]
        ):
            raise FederatedReleaseError(
                f"child release file hash mismatch: {entry.name}"
            )
    return manifest_raw, manifest, files, freshness


def _validate_freshness_csv(
    release: Path, *, expected_records: int, entity_records: int
) -> None:
    required_fields = {
        "stable_key",
        "status_semantics",
        "current_status_classification",
        "current_construction_claim",
    }
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(legacy.MAX_CHILD_CSV_FIELD_SIZE)
        with (release / FRESHNESS_FILENAME).open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not required_fields.issubset(
                reader.fieldnames
            ):
                raise FederatedReleaseError(
                    "child lifecycle_freshness.csv schema is invalid"
                )
            stable_keys: set[str] = set()
            records = 0
            for row in reader:
                stable_key = legacy._required_text(
                    row.get("stable_key"), "child lifecycle freshness stable_key"
                )
                if stable_key in stable_keys:
                    raise FederatedReleaseError(
                        "child lifecycle_freshness.csv repeats a stable_key"
                    )
                stable_keys.add(stable_key)
                if (
                    row.get("status_semantics") != "last_observed"
                    or row.get("current_status_classification") != "unknown"
                    or row.get("current_construction_claim") != "false"
                ):
                    raise FederatedReleaseError(
                        "child lifecycle freshness row implies current status"
                    )
                records += 1
    except (UnicodeDecodeError, csv.Error) as error:
        raise FederatedReleaseError(
            "child lifecycle_freshness.csv must be valid UTF-8 CSV"
        ) from error
    finally:
        csv.field_size_limit(previous_limit)
    if records != expected_records:
        raise FederatedReleaseError(
            "child lifecycle freshness count does not match manifest"
        )
    if records > entity_records:
        raise FederatedReleaseError(
            "child lifecycle freshness count exceeds child entities"
        )


def _inspect_child(definition: _ChildDefinition) -> dict[str, Any]:
    manifest_raw, manifest, _, freshness = _child_manifest(definition)
    if freshness is None:
        return legacy._inspect_child(definition)

    entity_records = legacy._nonnegative_integer(
        manifest.get("entities"), "child release entities"
    )
    _validate_freshness_csv(
        definition.release_path,
        expected_records=freshness["lifecycle_freshness_records"],
        entity_records=entity_records,
    )
    sanitized_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in FRESHNESS_MANIFEST_FIELDS
    }
    sanitized_raw = legacy._canonical_json(sanitized_manifest)
    with tempfile.TemporaryDirectory(
        prefix="federated-v3-child-", dir="/private/tmp"
    ) as temporary:
        shadow = Path(temporary) / definition.release_path.name
        shadow.mkdir()
        for entry in definition.release_path.iterdir():
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
        descriptor = legacy._inspect_child(sanitized_definition)

    descriptor_manifest = descriptor["manifest"]
    descriptor_manifest["bytes"] = len(manifest_raw)
    descriptor_manifest["sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    descriptor_manifest.update(freshness)
    return descriptor


def build_federated_release_index(
    definition_path: str | Path,
) -> FederatedIndexBundle:
    """Build a deterministic v2 federation bundle entirely from local children."""

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
    child_manifest = value.get("manifest")
    if not isinstance(child_manifest, Mapping):
        raise FederatedReleaseError(f"{label} manifest schema is invalid")
    base_keys = {
        "file",
        "bytes",
        "sha256",
        "format",
        "as_of",
        "recorded_at",
    }
    manifest_keys = set(child_manifest)
    allowed_keys = (
        base_keys | {"publication_contract_version"} | FRESHNESS_MANIFEST_FIELDS
    )
    if not base_keys.issubset(manifest_keys) or not manifest_keys.issubset(
        allowed_keys
    ):
        raise FederatedReleaseError(f"{label} manifest schema is invalid")
    freshness = _freshness_contract(child_manifest, label=f"{label} manifest")
    sanitized = dict(value)
    sanitized_manifest = {
        key: item
        for key, item in child_manifest.items()
        if key not in FRESHNESS_MANIFEST_FIELDS
    }
    sanitized["manifest"] = sanitized_manifest
    normalized = legacy._validate_descriptor(sanitized, position)
    if freshness is not None:
        if (
            freshness["lifecycle_freshness_records"]
            > normalized["counts"]["source_scoped_entity_records"]
        ):
            raise FederatedReleaseError(
                f"{label} lifecycle freshness count exceeds child entities"
            )
        normalized["manifest"].update(freshness)
    return normalized


def _shadow_legacy_bundle(
    manifest: Mapping[str, Any], index: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    sanitized_index = copy.deepcopy(index)
    sanitized_index["schema_version"] = legacy.INDEX_SCHEMA_VERSION
    sanitized_index["format"] = legacy.INDEX_FORMAT
    for descriptor in sanitized_index["releases"]:
        for field in FRESHNESS_MANIFEST_FIELDS:
            descriptor["manifest"].pop(field, None)
    sanitized_index_raw = legacy._canonical_json(sanitized_index)

    sanitized_manifest = copy.deepcopy(manifest)
    sanitized_manifest["schema_version"] = legacy.INDEX_SCHEMA_VERSION
    sanitized_manifest["format"] = legacy.BUNDLE_FORMAT
    artifact = sanitized_manifest["artifacts"][INDEX_FILENAME]
    artifact["format"] = legacy.INDEX_FORMAT
    artifact["bytes"] = len(sanitized_index_raw)
    artifact["sha256"] = hashlib.sha256(sanitized_index_raw).hexdigest()
    return sanitized_manifest, sanitized_index


def validate_federated_release_index(
    directory_path: str | Path,
    *,
    child_release_paths: Mapping[str, str | Path] | None = None,
    require_frozen: bool = True,
) -> Mapping[str, Any]:
    """Validate v2 bytes and optionally reconstruct every child descriptor."""

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
    if manifest_raw != legacy._canonical_json(manifest) or index_raw != legacy._canonical_json(
        index
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

    releases_value = index.get("releases")
    if not isinstance(releases_value, list):
        raise FederatedReleaseError("federated index releases must be an array")
    normalized_releases = [
        _validate_descriptor(value, position)
        for position, value in enumerate(releases_value)
    ]
    if releases_value != normalized_releases:
        raise FederatedReleaseError("federated release descriptors are not canonical")

    sanitized_manifest, sanitized_index = _shadow_legacy_bundle(manifest, index)
    sanitized_index_raw = legacy._canonical_json(sanitized_index)
    sanitized_manifest_raw = legacy._canonical_json(sanitized_manifest)
    sanitized_sidecar = (
        f"{hashlib.sha256(sanitized_manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    with tempfile.TemporaryDirectory(
        prefix="federated-v3-index-", dir="/private/tmp"
    ) as temporary:
        shadow = Path(temporary) / "bundle"
        shadow.mkdir()
        (shadow / INDEX_FILENAME).write_bytes(sanitized_index_raw)
        (shadow / MANIFEST_FILENAME).write_bytes(sanitized_manifest_raw)
        (shadow / MANIFEST_HASH_FILENAME).write_bytes(sanitized_sidecar)
        legacy_validated = legacy.validate_federated_release_index(shadow)
    if legacy_validated != sanitized_index:
        raise FederatedReleaseError("federated v2 legacy projection differs")

    if child_release_paths is not None:
        release_ids = [release["release_id"] for release in normalized_releases]
        if set(child_release_paths) != set(release_ids):
            raise FederatedReleaseError(
                "child path mapping must exactly match federated release IDs"
            )
        for release in normalized_releases:
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


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise FederatedReleaseError("atomic no-clobber publication is unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise FederatedReleaseError("atomic no-clobber publication is unavailable")
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
        raise FederatedReleaseError("atomic no-clobber publication is unavailable")
    if result == 0:
        legacy._fsync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FederatedReleaseError(
            f"late output collision; refusing overwrite: {destination}"
        )
    raise FederatedReleaseError(
        f"atomic no-clobber publication failed: {os.strerror(error_number)}"
    )


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        entry.chmod(0o600)
    shutil.rmtree(stage)


def write_federated_release_index(
    definition_path: str | Path, output_directory: str | Path
) -> Mapping[str, Any]:
    """Double-build, validate, freeze, and atomically publish one v2 index."""

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
    if not output.name:
        raise FederatedReleaseError("federated output must have a directory basename")
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
    "BUNDLE_FORMAT",
    "FEDERATION_POLICY",
    "FRESHNESS_MANIFEST_FIELDS",
    "FederatedIndexBundle",
    "FederatedReleaseError",
    "INDEX_FILENAME",
    "INDEX_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "build_federated_release_index",
    "validate_federated_release_index",
    "write_federated_release_index",
]
