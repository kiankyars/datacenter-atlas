"""Build and validate the publication-mechanics-v3 mosaic preparation release.

The scientific derivation remains pinned to the byte-preserved v2 definition.
This successor changes only publication metadata and failure recovery.  Recovery
uses atomic no-clobber renames and deliberately performs no unlink or rmdir:
portable POSIX offers no inode-conditional delete, so a pathname check followed
by deletion would retain a substitution race.
"""

from __future__ import annotations

from collections.abc import Mapping
import errno
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from . import satellite_mosaic_preparation as v2


SatelliteMosaicPreparationError = v2.SatelliteMosaicPreparationError

DEFINITION_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-definition-v3"
RELEASE_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-v3"
SCHEMA_VERSION = 3
PUBLICATION_MECHANICS_VERSION = 3
BASE_DEFINITION_PATH = (
    "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v2.json"
)
BUILDER_PATHS = {
    "cli": "scripts/build_satellite_mosaic_preparation_v3.py",
    "legacy_scientific_module": "datacenter_atlas/satellite_mosaic_preparation.py",
    "module": "datacenter_atlas/satellite_mosaic_preparation_v3.py",
}
PUBLICATION_CONTRACT = {
    "all_namespace_mutations_parent_fsynced": True,
    "atomic_no_clobber_rename": True,
    "destructive_failure_cleanup": False,
    "existing_regular_parent_required": True,
    "failure_recovery_policy": "atomic_quarantine_without_recursive_deletion",
    "frozen_file_inode_fsync_after_chmod": True,
    "frozen_staging_validation_before_rename": True,
    "lexical_symlink_rejection_before_resolution": True,
    "never_false_success": True,
    "parent_directory_fd_binding": True,
    "path_identity_binding": "st_dev_and_st_ino",
    "recovery_probe_errors_are_reported": True,
    "rollback_and_recovery_errors_are_reported": True,
    "substituted_nodes_are_never_deleted": True,
}
RELEASE_FILES = v2.RELEASE_FILES


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _identity_text(value: tuple[int, int]) -> str:
    return f"dev={value[0]},ino={value[1]}"


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _stat_at(parent_fd: int, name: str) -> os.stat_result | None:
    """Return one descriptor-relative entry stat; propagate every non-ENOENT error."""

    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _sync_parent(parent_fd: int, phase: str) -> None:
    try:
        os.fsync(parent_fd)
    except OSError as error:
        raise OSError(error.errno, f"{phase}: {error.strerror}") from error


def _rename_noreplace(parent_fd: int, source_name: str, target_name: str) -> None:
    v2._rename_noreplace(parent_fd, source_name, target_name)


def _read_definition(
    definition_path: Path, output_dir: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Path]]:
    root = v2._project_root(definition_path)
    definition_path = Path(os.path.abspath(os.fspath(definition_path.expanduser())))
    definition = v2._read_json(definition_path, "v3 definition", canonical=True)
    if v2._mode(definition_path) != "0444":
        raise SatelliteMosaicPreparationError("v3 definition mode must be 0444")
    if set(definition) != {
        "base_definition",
        "claim_constraints",
        "expected_partition",
        "format",
        "generated_at",
        "publication_contract",
        "release_id",
        "schema_version",
    }:
        raise SatelliteMosaicPreparationError("v3 definition schema drift")
    if (
        definition["format"] != DEFINITION_FORMAT
        or definition["schema_version"] != SCHEMA_VERSION
    ):
        raise SatelliteMosaicPreparationError("v3 definition format mismatch")
    if definition["claim_constraints"] != v2.CLAIM_CONSTRAINTS:
        raise SatelliteMosaicPreparationError("claim constraints drift")
    if definition["publication_contract"] != PUBLICATION_CONTRACT:
        raise SatelliteMosaicPreparationError("publication contract drift")
    if definition["expected_partition"] != {
        "blocked": 1,
        "blocked_queue_id": v2.BLOCKED_QUEUE_ID,
        "metadata_ready": 6,
        "total": 7,
    }:
        raise SatelliteMosaicPreparationError("expected partition drift")

    base_pin = definition["base_definition"]
    if not isinstance(base_pin, dict) or set(base_pin) != {
        "bytes",
        "mode",
        "path",
        "sha256",
    }:
        raise SatelliteMosaicPreparationError("base definition pin schema drift")
    if base_pin["path"] != BASE_DEFINITION_PATH:
        raise SatelliteMosaicPreparationError("base definition path drift")
    base_path = v2._inside(root, base_pin["path"], "base definition")
    v2._verify_pin(
        base_path,
        {key: base_pin[key] for key in ("bytes", "mode", "sha256")},
        "base definition",
    )
    base, base_root, directories = v2._source_state(base_path, output_dir)
    if base_root != root:
        raise SatelliteMosaicPreparationError("base definition project root drift")
    if base["claim_constraints"] != definition["claim_constraints"]:
        raise SatelliteMosaicPreparationError("base claim constraints drift")
    if base["expected_partition"] != definition["expected_partition"]:
        raise SatelliteMosaicPreparationError("base partition drift")

    if output_dir is not None:
        output = Path(os.path.abspath(os.fspath(output_dir.expanduser())))
        if v2._is_relative(output, definition_path) or v2._is_relative(
            definition_path, output
        ):
            raise SatelliteMosaicPreparationError("output overlaps v3 definition")

    effective = dict(base)
    effective["release_id"] = definition["release_id"]
    return definition, effective, root, directories


def _builder_pins(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, relative in sorted(BUILDER_PATHS.items()):
        path = v2._inside(root, relative, f"v3 builder {name}")
        if not path.is_file() or path.is_symlink():
            raise SatelliteMosaicPreparationError(f"v3 builder {name} is invalid")
        result[name] = {"path": relative, **v2._pin(path)}
    return result


def _readme(definition: Mapping[str, Any]) -> bytes:
    return (
        "# Sentinel mosaic-v3 blocked-row preparation\n\n"
        "This immutable, metadata-only release binds the same seven algorithm-v2 "
        "calibration rows as the byte-preserved v2 scientific definition. Six rows "
        "have explicit primary and companion item IDs and canonical STAC item hashes "
        "for both epochs. The MRS5 row remains blocked because its archived current "
        "response has no same-acquisition 31TFJ companion.\n\n"
        "No network request, imagery download, imagery read, or mosaic execution was "
        "performed. `mosaic-specs.jsonl` is a preparation interface, not an execution "
        "release or a calibration result. Satellite metadata and future visible-change "
        "output establish no data-centre identity, construction lifecycle, type, "
        "operator, capacity, power, energy, PUE, workload, or SemiAnalysis parity.\n\n"
        "Version 3 supersedes rejected versions 1 and 2 only for publication mechanics. "
        "Failure recovery uses descriptor-relative probes and atomic no-clobber renames. "
        "It never calls unlink or rmdir: a writer-owned failed tree is left under a "
        "reported recovery-quarantine name, while a substituted node is preserved. "
        "Every successful namespace mutation is followed by a parent-directory fsync, "
        "and probe, rollback, recovery, and sync errors are appended to the primary "
        "failure instead of masking it or returning false success.\n\n"
        f"Release ID: `{definition['release_id']}`.\n"
    ).encode("utf-8")


def _payloads(
    definition_path: Path, output_dir: Path | None = None
) -> tuple[dict[str, bytes], dict[str, Any], Path]:
    definition, effective, root, directories = _read_definition(
        definition_path, output_dir
    )
    ready, blocked, summary = v2._derive_payload_rows(effective, directories)
    summary.update(
        {
            "publication_mechanics_version": PUBLICATION_MECHANICS_VERSION,
            "release_id": definition["release_id"],
            "schema_version": SCHEMA_VERSION,
        }
    )
    inventory = v2._source_inventory(effective)
    summary["source_file_pins"] = inventory["source_file_count"]
    payloads = {
        "ATTRIBUTION.txt": v2._attribution(),
        "README.md": _readme(definition),
        "blocked.jsonl": v2.canonical_jsonl(blocked),
        "mosaic-specs.jsonl": v2.canonical_jsonl(ready),
        "source-inventory.json": v2.canonical_json(inventory),
        "summary.json": v2.canonical_json(summary),
    }
    manifest = {
        "base_definition": definition["base_definition"],
        "builder": _builder_pins(root),
        "definition": {
            "path": definition_path.resolve(strict=True).relative_to(root).as_posix(),
            **v2._pin(definition_path),
        },
        "format": RELEASE_FORMAT,
        "outputs": {
            name: {"bytes": len(raw), "mode": "0444", "sha256": v2._sha(raw)}
            for name, raw in sorted(payloads.items())
        },
        "processor": effective["processor"],
        "publication_contract": definition["publication_contract"],
        "release_id": definition["release_id"],
        "schema_version": SCHEMA_VERSION,
        "sources": effective["sources"],
        "summary": summary,
    }
    payloads["manifest.json"] = v2.canonical_json(manifest)
    payloads["manifest.sha256"] = (
        f"{v2._sha(payloads['manifest.json'])}  manifest.json\n".encode("ascii")
    )
    return payloads, manifest, root


def _probe_at(
    parent_fd: int,
    name: str,
    label: str,
    errors: list[str],
) -> tuple[bool, os.stat_result | None]:
    """Probe an entry without allowing lookup errors to escape recovery."""

    try:
        return True, _stat_at(parent_fd, name)
    except BaseException as error:
        errors.append(f"{label} probe failed: {_error_text(error)}")
        return False, None


def _sync_after_mutation(parent_fd: int, phase: str, errors: list[str]) -> bool:
    try:
        _sync_parent(parent_fd, phase)
        return True
    except BaseException as error:
        errors.append(f"{phase} failed: {_error_text(error)}")
        return False


def _restore_unexpected_move(
    *,
    parent_fd: int,
    moved_name: str,
    original_name: str,
    errors: list[str],
    label: str,
) -> None:
    original_known, original = _probe_at(
        parent_fd, original_name, f"{label} original", errors
    )
    moved_known, moved = _probe_at(parent_fd, moved_name, f"{label} moved", errors)
    if not original_known or not moved_known:
        errors.append(f"{label} restoration refused because entry state is unknown")
        return
    if moved is None:
        errors.append(f"{label} moved entry disappeared before restoration")
        return
    if original is not None:
        errors.append(
            f"{label} unrelated moved entry preserved at {moved_name}; "
            f"original name {original_name} is occupied"
        )
        return
    try:
        _rename_noreplace(parent_fd, moved_name, original_name)
    except BaseException as error:
        errors.append(f"{label} restoration rename failed: {_error_text(error)}")
        return
    _sync_after_mutation(parent_fd, f"{label} restoration parent fsync", errors)
    errors.append(f"{label} unrelated moved entry was restored without deletion")


def _move_owned_entry(
    *,
    parent_fd: int,
    source_name: str,
    destination_name: str,
    expected_identity: tuple[int, int],
    errors: list[str],
    label: str,
) -> bool:
    """Nondestructively move one name, then prove what the atomic rename moved."""

    try:
        _rename_noreplace(parent_fd, source_name, destination_name)
    except BaseException as error:
        errors.append(f"{label} rename failed: {_error_text(error)}")
        return False
    _sync_after_mutation(parent_fd, f"{label} parent fsync", errors)
    known, moved = _probe_at(parent_fd, destination_name, f"{label} destination", errors)
    if known and moved is not None and _identity(moved) == expected_identity:
        return True
    if known and moved is not None:
        errors.append(
            f"{label} moved a substituted entry {_identity_text(_identity(moved))}; "
            "it will be restored or preserved, never deleted"
        )
    else:
        errors.append(f"{label} destination identity could not be proven")
    _restore_unexpected_move(
        parent_fd=parent_fd,
        moved_name=destination_name,
        original_name=source_name,
        errors=errors,
        label=label,
    )
    return False


def _recover_publication_failure(
    *,
    primary_error: BaseException,
    parent_path: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staging_name: str | None,
    target_name: str,
    tree_identity: tuple[int, int] | None,
) -> None:
    """Report the primary failure and nondestructively quarantine an owned tree.

    There is intentionally no recursive cleanup here.  A directory descriptor
    proves which tree the writer created, but POSIX unlinkat/rmdir still select
    their victim by a mutable name.  Atomic no-clobber rename is non-destructive;
    its result is verified and an unexpectedly moved substitute is restored or
    left intact.
    """

    errors = [f"primary failure: {_error_text(primary_error)}"]
    if staging_name is not None:
        # Covers a failure between mkdirat and the normal creation fsync.  This
        # is harmlessly redundant when creation was already synced.
        _sync_after_mutation(
            parent_fd, "staging creation recovery parent fsync", errors
        )
    parent_safe = True
    try:
        v2._require_open_directory_identity(parent_fd, parent_identity, "output parent")
    except BaseException as error:
        parent_safe = False
        errors.append(f"parent descriptor identity check failed: {_error_text(error)}")
    try:
        v2._require_directory_path_identity(parent_path, parent_identity, "output parent")
    except BaseException as error:
        parent_safe = False
        errors.append(f"parent path identity check failed: {_error_text(error)}")

    names = [name for name in (staging_name, target_name) if name]
    states: dict[str, tuple[bool, os.stat_result | None]] = {
        name: _probe_at(parent_fd, name, f"recovery {name}", errors)
        for name in names
    }
    if tree_identity is None:
        errors.append("writer-created tree identity is unavailable; no recovery mutation attempted")
    elif not parent_safe or any(not known for known, _ in states.values()):
        errors.append("recovery mutation refused because identity state is not fully known")
    else:
        owned_names = [
            name
            for name, (_, value) in states.items()
            if value is not None and _identity(value) == tree_identity
        ]
        if len(owned_names) > 1:
            errors.append("writer-created tree appears at multiple names; recovery refused")
        elif not owned_names:
            errors.append("writer-created tree is no longer bound to staging or target")
        else:
            owned_name = owned_names[0]
            # Prefer a rollback into the private staging namespace after a
            # post-publication failure.  The move itself cannot overwrite.
            if owned_name == target_name and staging_name is not None:
                staging_known, staging_value = states[staging_name]
                if staging_known and staging_value is None:
                    if _move_owned_entry(
                        parent_fd=parent_fd,
                        source_name=target_name,
                        destination_name=staging_name,
                        expected_identity=tree_identity,
                        errors=errors,
                        label="rollback",
                    ):
                        owned_name = staging_name
                else:
                    errors.append("rollback destination is occupied; rollback not attempted")

            known, current = _probe_at(
                parent_fd, owned_name, "pre-quarantine owned entry", errors
            )
            if not known or current is None or _identity(current) != tree_identity:
                errors.append("owned entry changed before quarantine; no deletion attempted")
            else:
                try:
                    token = secrets.token_hex(12)
                except BaseException as error:
                    errors.append(f"recovery quarantine name generation failed: {_error_text(error)}")
                else:
                    quarantine = f".{target_name}.recovery-{token}"
                    quarantine_known, quarantine_value = _probe_at(
                        parent_fd, quarantine, "recovery quarantine", errors
                    )
                    if not quarantine_known or quarantine_value is not None:
                        errors.append("recovery quarantine destination is unavailable")
                    elif _move_owned_entry(
                        parent_fd=parent_fd,
                        source_name=owned_name,
                        destination_name=quarantine,
                        expected_identity=tree_identity,
                        errors=errors,
                        label="recovery quarantine",
                    ):
                        errors.append(
                            f"writer-created tree preserved without deletion at {quarantine}"
                        )

    for name in names:
        known, value = _probe_at(parent_fd, name, f"final recovery {name}", errors)
        if known and value is not None:
            ownership = (
                "writer-created" if tree_identity is not None and _identity(value) == tree_identity
                else "substituted"
            )
            errors.append(
                f"final {name} entry preserved ({ownership}, "
                f"{_identity_text(_identity(value))})"
            )
    try:
        v2._require_directory_path_identity(parent_path, parent_identity, "output parent")
    except BaseException as error:
        errors.append(f"final parent identity check failed: {_error_text(error)}")
    raise SatelliteMosaicPreparationError(
        "publication failed | " + " | ".join(errors)
    ) from primary_error


def validate_satellite_mosaic_preparation_v3(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = v2._project_root(definition_path)
    output, directory_fd, output_identity = v2._open_bound_directory(
        output_dir, root, "output"
    )
    try:
        actual = v2._read_bound_release_tree(directory_fd, output_identity)
        expected, manifest, _ = _payloads(definition_path, output)
        for name in RELEASE_FILES:
            if actual[name] != expected[name]:
                raise SatelliteMosaicPreparationError(
                    f"{name} differs from deterministic v3 reproduction"
                )
        parsed = v2._strict_json(actual["manifest.json"], "v3 release manifest")
        if not isinstance(parsed, dict) or actual["manifest.json"] != v2.canonical_json(parsed):
            raise SatelliteMosaicPreparationError("v3 release manifest is not canonical JSON")
        if parsed != manifest:
            raise SatelliteMosaicPreparationError("v3 manifest semantic mismatch")
        v2._require_open_directory_identity(directory_fd, output_identity, "output")
        v2._require_directory_path_identity(output, output_identity, "output")
        return manifest
    finally:
        os.close(directory_fd)


def write_satellite_mosaic_preparation_v3(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = v2._project_root(definition_path)
    output, parent_path, parent_fd, parent_identity = v2._open_output_parent(
        output_dir, root
    )
    staging_name: str | None = None
    tree_fd: int | None = None
    tree_identity: tuple[int, int] | None = None
    try:
        try:
            payloads, manifest, _ = _payloads(definition_path, output)
            v2._require_open_directory_identity(parent_fd, parent_identity, "output parent")
            v2._require_directory_path_identity(parent_path, parent_identity, "output parent")
            if _stat_at(parent_fd, output.name) is not None:
                raise SatelliteMosaicPreparationError("output appeared before staging")

            for _ in range(100):
                candidate = f".{output.name}.staging-{secrets.token_hex(8)}"
                try:
                    os.mkdir(candidate, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    continue
                staging_name = candidate
                value = os.stat(candidate, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISDIR(value.st_mode):
                    raise SatelliteMosaicPreparationError("created staging is not a directory")
                tree_identity = _identity(value)
                tree_fd = os.open(candidate, v2._DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
                v2._require_open_directory_identity(tree_fd, tree_identity, "staging")
                _sync_parent(parent_fd, "staging creation parent fsync")
                break
            else:
                raise SatelliteMosaicPreparationError(
                    "could not allocate a unique staging name"
                )

            v2._write_payloads(tree_fd, payloads)
            v2._freeze_staging(parent_fd, staging_name, tree_fd, tree_identity)
            _sync_parent(parent_fd, "frozen staging parent fsync")
            staging_path = parent_path / staging_name
            validated = validate_satellite_mosaic_preparation_v3(
                staging_path, definition_path=definition_path
            )
            if validated != manifest:
                raise SatelliteMosaicPreparationError(
                    "frozen staging validation returned a differing v3 manifest"
                )
            v2._require_open_directory_identity(tree_fd, tree_identity, "staging")
            v2._require_directory_identity_at(parent_fd, staging_name, tree_identity, "staging")
            v2._require_directory_path_identity(parent_path, parent_identity, "output parent")
            if _stat_at(parent_fd, output.name) is not None:
                raise SatelliteMosaicPreparationError("output appeared before publication")
            _rename_noreplace(parent_fd, staging_name, output.name)
            _sync_parent(parent_fd, "publication parent fsync")

            # Re-prove the published pathname, the held directory descriptor,
            # and every frozen byte after the durability boundary.
            v2._require_directory_identity_at(parent_fd, output.name, tree_identity, "published target")
            if _stat_at(parent_fd, staging_name) is not None:
                raise SatelliteMosaicPreparationError("staging name remains after publication rename")
            final_bytes = v2._read_bound_release_tree(tree_fd, tree_identity)
            if final_bytes != payloads:
                raise SatelliteMosaicPreparationError("published target bytes changed after parent fsync")
            v2._require_open_directory_identity(tree_fd, tree_identity, "published target")
            v2._require_directory_identity_at(parent_fd, output.name, tree_identity, "published target")
            v2._require_directory_path_identity(parent_path, parent_identity, "output parent")
            return manifest
        except BaseException as primary_error:
            _recover_publication_failure(
                primary_error=primary_error,
                parent_path=parent_path,
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                staging_name=staging_name,
                target_name=output.name,
                tree_identity=tree_identity,
            )
            raise AssertionError("unreachable")
    finally:
        if tree_fd is not None:
            os.close(tree_fd)
        os.close(parent_fd)
