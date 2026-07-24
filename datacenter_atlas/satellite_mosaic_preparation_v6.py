"""Build and validate the publication-mechanics-v6 mosaic preparation release.

The scientific derivation remains pinned to the byte-preserved v2 definition.
V6 succeeds rejected v5 only for publication mechanics: every directory
descriptor is registered with a cleanup ledger immediately after ``os.open``
returns, including descriptors acquired before identity and target checks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from . import satellite_mosaic_preparation as v2
from . import satellite_mosaic_preparation_v4 as v4
from . import satellite_mosaic_preparation_v5 as v5


SatelliteMosaicPreparationError = v2.SatelliteMosaicPreparationError

DEFINITION_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-definition-v6"
RELEASE_FORMAT = "datacenter-atlas-satellite-mosaic-v3-preparation-v6"
SCHEMA_VERSION = 6
PUBLICATION_MECHANICS_VERSION = 6
BASE_DEFINITION_PATH = (
    "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v2.json"
)
REJECTED_PREDECESSOR_PATH = (
    "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v5.json"
)
BUILDER_PATHS = {
    "cli": "scripts/build_satellite_mosaic_preparation_v6.py",
    "legacy_scientific_module": "datacenter_atlas/satellite_mosaic_preparation.py",
    "module": "datacenter_atlas/satellite_mosaic_preparation_v6.py",
    "rejected_v3_module": "datacenter_atlas/satellite_mosaic_preparation_v3.py",
    "rejected_v4_module": "datacenter_atlas/satellite_mosaic_preparation_v4.py",
    "rejected_v5_module": "datacenter_atlas/satellite_mosaic_preparation_v5.py",
}
PUBLICATION_CONTRACT = {
    **v5.PUBLICATION_CONTRACT,
    "acquisition_and_cleanup_errors_aggregated": True,
    "descriptor_acquisition_cleanup_ledger": True,
    "requested_target_path_always_reported": True,
}
RELEASE_FILES = v2.RELEASE_FILES


class _DescriptorLedger:
    """Own descriptors from the instant an open operation returns."""

    def __init__(self) -> None:
        self._descriptors: list[tuple[str, int]] = []

    def open(
        self,
        label: str,
        path: Path | str,
        flags: int,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd is None:
            descriptor = os.open(path, flags)
        else:
            descriptor = os.open(path, flags, dir_fd=dir_fd)
        self._descriptors.append((label, descriptor))
        return descriptor

    def close_all(self) -> list[tuple[str, BaseException]]:
        descriptors = tuple(reversed(self._descriptors))
        self._descriptors.clear()
        return v5._close_descriptors(descriptors)


def _absolute_output(output_dir: Path) -> Path:
    return Path(os.path.abspath(os.fspath(output_dir.expanduser())))


def _acquire_bound_directory(
    path: Path,
    root: Path,
    label: str,
    ledger: _DescriptorLedger,
) -> tuple[Path, int, tuple[int, int]]:
    """Acquire a bound directory without hiding cleanup inside acquisition."""

    lexical = _absolute_output(path)
    v2._reject_symlink_components(lexical, root, label)
    try:
        before = os.lstat(lexical)
    except OSError as error:
        raise SatelliteMosaicPreparationError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(before.st_mode):
        raise SatelliteMosaicPreparationError(f"{label} is not a regular directory")
    try:
        descriptor = ledger.open(label, lexical, v2._DIRECTORY_OPEN_FLAGS)
    except OSError as error:
        raise SatelliteMosaicPreparationError(
            f"{label} cannot be opened safely"
        ) from error
    expected = v4._identity(before)
    v2._require_open_directory_identity(descriptor, expected, label)
    v2._require_directory_path_identity(lexical, expected, label)
    return lexical, descriptor, expected


def _acquire_output_parent(
    output: Path,
    root: Path,
    ledger: _DescriptorLedger,
) -> tuple[Path, int, tuple[int, int]]:
    v2._reject_symlink_components(output, root, "output")
    if output == root or output.name in {"", ".", ".."}:
        raise SatelliteMosaicPreparationError("output path is invalid")
    return _acquire_bound_directory(output.parent, root, "output parent", ledger)


def _read_definition(
    definition_path: Path, output_dir: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Path]]:
    root = v2._project_root(definition_path)
    definition_path = Path(os.path.abspath(os.fspath(definition_path.expanduser())))
    definition = v2._read_json(definition_path, "v6 definition", canonical=True)
    if v2._mode(definition_path) != "0444":
        raise SatelliteMosaicPreparationError("v6 definition mode must be 0444")
    if set(definition) != {
        "base_definition",
        "claim_constraints",
        "expected_partition",
        "format",
        "generated_at",
        "publication_contract",
        "rejected_predecessor",
        "release_id",
        "schema_version",
    }:
        raise SatelliteMosaicPreparationError("v6 definition schema drift")
    if (
        definition["format"] != DEFINITION_FORMAT
        or definition["schema_version"] != SCHEMA_VERSION
    ):
        raise SatelliteMosaicPreparationError("v6 definition format mismatch")
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

    predecessor_pin = definition["rejected_predecessor"]
    if not isinstance(predecessor_pin, dict) or set(predecessor_pin) != {
        "bytes",
        "mode",
        "path",
        "sha256",
    }:
        raise SatelliteMosaicPreparationError("rejected predecessor pin schema drift")
    if predecessor_pin["path"] != REJECTED_PREDECESSOR_PATH:
        raise SatelliteMosaicPreparationError("rejected predecessor path drift")
    predecessor_path = v2._inside(
        root, predecessor_pin["path"], "rejected predecessor"
    )
    v2._verify_pin(
        predecessor_path,
        {key: predecessor_pin[key] for key in ("bytes", "mode", "sha256")},
        "rejected predecessor",
    )

    base, base_root, directories = v2._source_state(base_path, output_dir)
    if base_root != root:
        raise SatelliteMosaicPreparationError("base definition project root drift")
    if base["claim_constraints"] != definition["claim_constraints"]:
        raise SatelliteMosaicPreparationError("base claim constraints drift")
    if base["expected_partition"] != definition["expected_partition"]:
        raise SatelliteMosaicPreparationError("base partition drift")

    if output_dir is not None:
        output = _absolute_output(output_dir)
        if v2._is_relative(output, definition_path) or v2._is_relative(
            definition_path, output
        ):
            raise SatelliteMosaicPreparationError("output overlaps v6 definition")

    effective = dict(base)
    effective["release_id"] = definition["release_id"]
    return definition, effective, root, directories


def _builder_pins(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, relative in sorted(BUILDER_PATHS.items()):
        path = v2._inside(root, relative, f"v6 builder {name}")
        if not path.is_file() or path.is_symlink():
            raise SatelliteMosaicPreparationError(f"v6 builder {name} is invalid")
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
        "Version 6 supersedes rejected versions 1 through 5 only for publication "
        "mechanics and remains a candidate pending a fresh independent audit. V5 "
        "registered writer and validator descriptors only after acquisition helpers "
        "completed, so identity or initial target-stat failures could escape the outer "
        "cleanup boundary. V6 registers every descriptor immediately after open. It "
        "attempts cleanup for every acquired descriptor, aggregates acquisition, "
        "recovery, and cleanup errors, and always reports the exact requested target "
        "plus every allocated staging or recovery path. V5's fail-closed ambiguous "
        "mkdir policy and all-descriptor final-close behavior are retained. Recovery "
        "remains nondestructive and never calls unlink or rmdir.\n\n"
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
        "rejected_predecessor": definition["rejected_predecessor"],
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


def _raise_ledger_failure(
    *,
    operation: str,
    target_path: Path,
    staging_path: Path | None,
    published_verified: bool,
    staging_absent_verified: bool,
    operation_errors: Sequence[tuple[str, BaseException]],
    close_errors: Sequence[tuple[str, BaseException]],
) -> None:
    details = [f"{operation} failed; no successful result was returned"]
    if published_verified:
        details.append(f"verified target path may remain: {target_path}")
    else:
        details.append(f"exact requested target path: {target_path}")
    if staging_path is None:
        details.append("staging path was not allocated")
    elif staging_absent_verified:
        details.append(f"allocated staging path verified absent: {staging_path}")
    else:
        details.append(f"allocated or possible staging path: {staging_path}")
    details.extend(
        f"{label}: {v4._error_text(error)}" for label, error in operation_errors
    )
    details.extend(
        f"{label} close failed: {v4._error_text(error)}"
        for label, error in close_errors
    )
    errors = [error for _, error in (*operation_errors, *close_errors)]
    cause = errors[0] if errors else None
    raised = SatelliteMosaicPreparationError(" | ".join(details))
    if cause is None:  # pragma: no cover - total control-flow assertion
        raise raised
    raise raised from cause


def validate_satellite_mosaic_preparation_v6(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    output = _absolute_output(output_dir)
    ledger = _DescriptorLedger()
    result: dict[str, Any] | None = None
    operation_errors: list[tuple[str, BaseException]] = []
    try:
        root = v2._project_root(definition_path)
        output, directory_fd, output_identity = _acquire_bound_directory(
            output, root, "output", ledger
        )
        actual = v2._read_bound_release_tree(directory_fd, output_identity)
        expected, manifest, _ = _payloads(definition_path, output)
        for name in RELEASE_FILES:
            if actual[name] != expected[name]:
                raise SatelliteMosaicPreparationError(
                    f"{name} differs from deterministic v6 reproduction"
                )
        parsed = v2._strict_json(actual["manifest.json"], "v6 release manifest")
        if not isinstance(parsed, dict) or actual["manifest.json"] != v2.canonical_json(
            parsed
        ):
            raise SatelliteMosaicPreparationError(
                "v6 release manifest is not canonical JSON"
            )
        if parsed != manifest:
            raise SatelliteMosaicPreparationError("v6 manifest semantic mismatch")
        v2._require_open_directory_identity(directory_fd, output_identity, "output")
        v2._require_directory_path_identity(output, output_identity, "output")
        result = manifest
    except BaseException as error:
        operation_errors.append(("primary validation failure", error))

    close_errors = ledger.close_all()
    if operation_errors or close_errors:
        _raise_ledger_failure(
            operation="validation",
            target_path=output,
            staging_path=None,
            published_verified=result is not None,
            staging_absent_verified=False,
            operation_errors=operation_errors,
            close_errors=close_errors,
        )
    if result is None:  # pragma: no cover - total control-flow assertion
        raise AssertionError("v6 validation produced no result")
    return result


def write_satellite_mosaic_preparation_v6(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    output = _absolute_output(output_dir)
    parent_path = output.parent
    parent_fd: int | None = None
    parent_identity: tuple[int, int] | None = None
    staging_name: str | None = None
    tree_fd: int | None = None
    tree_identity: tuple[int, int] | None = None
    result: dict[str, Any] | None = None
    published_verified = False
    staging_absent_verified = False
    operation_errors: list[tuple[str, BaseException]] = []
    ledger = _DescriptorLedger()

    try:
        root = v2._project_root(definition_path)
        parent_path, parent_fd, parent_identity = _acquire_output_parent(
            output, root, ledger
        )
        if v4._stat_at(parent_fd, output.name) is not None:
            raise SatelliteMosaicPreparationError("output already exists")

        payloads, manifest, _ = _payloads(definition_path, output)
        v2._require_open_directory_identity(parent_fd, parent_identity, "output parent")
        v2._require_directory_path_identity(
            parent_path, parent_identity, "output parent"
        )
        if v4._stat_at(parent_fd, output.name) is not None:
            raise SatelliteMosaicPreparationError("output appeared before staging")

        staging_name = f".{output.name}.staging-{secrets.token_hex(8)}"
        try:
            os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        except FileExistsError as error:
            raise SatelliteMosaicPreparationError(
                "ambiguous staging mkdir FileExistsError; collision identity cannot "
                "be proven and retry is forbidden"
            ) from error
        value = os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(value.st_mode):
            raise SatelliteMosaicPreparationError("created staging is not a directory")
        tree_identity = v4._identity(value)
        tree_fd = ledger.open(
            "staged tree descriptor",
            staging_name,
            v2._DIRECTORY_OPEN_FLAGS,
            dir_fd=parent_fd,
        )
        v2._require_open_directory_identity(tree_fd, tree_identity, "staging")
        v4._sync_parent(parent_fd, "staging creation parent fsync")

        v2._write_payloads(tree_fd, payloads)
        v2._freeze_staging(parent_fd, staging_name, tree_fd, tree_identity)
        v4._sync_parent(parent_fd, "frozen staging parent fsync")
        staging_path = parent_path / staging_name
        validated = validate_satellite_mosaic_preparation_v6(
            staging_path, definition_path=definition_path
        )
        if validated != manifest:
            raise SatelliteMosaicPreparationError(
                "frozen staging validation returned a differing v6 manifest"
            )
        v2._require_open_directory_identity(tree_fd, tree_identity, "staging")
        v2._require_directory_identity_at(
            parent_fd, staging_name, tree_identity, "staging"
        )
        v2._require_directory_path_identity(
            parent_path, parent_identity, "output parent"
        )
        if v4._stat_at(parent_fd, output.name) is not None:
            raise SatelliteMosaicPreparationError("output appeared before publication")
        v4._rename_noreplace(parent_fd, staging_name, output.name)
        v4._sync_parent(parent_fd, "publication parent fsync")

        v2._require_directory_identity_at(
            parent_fd, output.name, tree_identity, "published target"
        )
        if v4._stat_at(parent_fd, staging_name) is not None:
            raise SatelliteMosaicPreparationError(
                "staging name remains after publication rename"
            )
        staging_absent_verified = True
        final_bytes = v2._read_bound_release_tree(tree_fd, tree_identity)
        if final_bytes != payloads:
            raise SatelliteMosaicPreparationError(
                "published target bytes changed after parent fsync"
            )
        v2._require_open_directory_identity(
            tree_fd, tree_identity, "published target"
        )
        v2._require_directory_identity_at(
            parent_fd, output.name, tree_identity, "published target"
        )
        v2._require_directory_path_identity(
            parent_path, parent_identity, "output parent"
        )
        published_verified = True
        result = manifest
    except BaseException as primary_error:
        operation_errors.append(("primary publication failure", primary_error))
        if (
            parent_fd is not None
            and parent_identity is not None
            and (staging_name is not None or tree_identity is not None)
        ):
            try:
                v4._recover_publication_failure(
                    primary_error=primary_error,
                    parent_path=parent_path,
                    parent_fd=parent_fd,
                    parent_identity=parent_identity,
                    staging_name=staging_name,
                    target_name=output.name,
                    tree_identity=tree_identity,
                )
            except BaseException as recovery_error:
                operation_errors.append(("publication recovery failure", recovery_error))
            else:  # pragma: no cover - recovery is specified to raise
                operation_errors.append(
                    (
                        "publication recovery failure",
                        SatelliteMosaicPreparationError(
                            "publication recovery returned without reporting failure"
                        ),
                    )
                )

    close_errors = ledger.close_all()
    staging_path = parent_path / staging_name if staging_name is not None else None
    if operation_errors or close_errors:
        _raise_ledger_failure(
            operation="publication",
            target_path=output,
            staging_path=staging_path,
            published_verified=published_verified,
            staging_absent_verified=staging_absent_verified,
            operation_errors=operation_errors,
            close_errors=close_errors,
        )
    if result is None:  # pragma: no cover - total control-flow assertion
        raise AssertionError("v6 writer produced no result")
    return result
