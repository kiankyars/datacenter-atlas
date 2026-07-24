"""Finalize and disposition the completed explicit-v1 satellite change run.

The original catalog checkpoint and change run are never mutated.  The
catalog checkpoint is copied byte-for-byte to a new immutable path and frozen.
An isolated validator then revalidates the frozen change run against that
copy.  The external disposition records the post-freeze mapping-order false
rejection without weakening the ordered receipt selection or any review-only
constraint.
"""

from __future__ import annotations

import ctypes
from datetime import UTC, datetime, timedelta
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import types
from typing import Any, Mapping

from .satellite_batch_explicit_v1 import (
    ExplicitBatchConfig,
    validate_explicit_satellite_batch_v1,
)
from . import satellite_change_batch_explicit_v1 as execution_adapter


class ExplicitV1DispositionError(ValueError):
    """Raised when finalization, validation, or publication fails closed."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = PACKAGE_ROOT / "satellite_review_queues/2026-07-21-open-seed-v71"
SOURCE_CATALOG_PATH = (
    PACKAGE_ROOT
    / "satellite_review_runs/2026-07-21-open-seed-v71-active-explicit-001"
)
FINALIZED_CATALOG_PATH = (
    PACKAGE_ROOT
    / "satellite_review_runs/2026-07-21-open-seed-v71-active-explicit-final-v1"
)
CHANGE_RUN_PATH = (
    PACKAGE_ROOT
    / "satellite_change_runs/2026-07-21-open-seed-v71-active-explicit-001"
)
DISPOSITION_PATH = (
    PACKAGE_ROOT
    / "satellite_change_run_dispositions/"
    "2026-07-21-open-seed-v71-active-explicit-001-v1"
)
GENERIC_CARRIER_PATH = PACKAGE_ROOT / "datacenter_atlas/satellite_change_batch.py"
EXECUTION_ADAPTER_PATH = (
    PACKAGE_ROOT / "datacenter_atlas/satellite_change_batch_explicit_v1.py"
)
ROOT_SHIM_PATH = PACKAGE_ROOT / "satellite_change_batch_explicit_v1.py"
EXECUTION_CLI_PATH = (
    PACKAGE_ROOT / "scripts/run_satellite_change_batch_explicit_v1.py"
)
DISPOSITION_MODULE_PATH = Path(__file__).resolve()
DISPOSITION_ROOT_SHIM_PATH = (
    PACKAGE_ROOT / "satellite_change_explicit_v1_disposition.py"
)
DISPOSITION_CLI_PATH = (
    PACKAGE_ROOT / "scripts/publish_satellite_change_explicit_v1_disposition.py"
)

QUEUE_MANIFEST_SHA256 = execution_adapter.QUEUE_MANIFEST_SHA256
QUEUE_SHA256 = execution_adapter.QUEUE_SHA256
CATALOG_MANIFEST_SHA256 = execution_adapter.CATALOG_MANIFEST_SHA256
SELECTION_RECEIPT_SHA256 = execution_adapter.SELECTION_RECEIPT_SHA256
GENERIC_CARRIER_SHA256 = execution_adapter.GENERIC_CARRIER_SHA256
SOURCE_CATALOG_TREE_SHA256 = (
    "9a3ad4cbd9c7b2442000fb29eb7ff1dd534bda40acf6fa81cdaef033ee53cb3f"
)
SOURCE_CATALOG_FILE_COUNT = 36
SOURCE_CATALOG_TOTAL_BYTES = 5_186_758
EXECUTION_ADAPTER_SHA256 = (
    "82fc7b814dc5cb26c1317d634ba0d0c95ae81e43ec05ff5f0e9d28f33128d372"
)
EXECUTION_ROOT_SHIM_SHA256 = (
    "bed22adeb04718ea5bff739da0929377f1705098fa7228f56a1c75951217d9bb"
)
EXECUTION_CLI_SHA256 = (
    "632c21800824c5512df427bec6c98f57db051c5b46e5243de453c9505ca4b2f6"
)
CHANGE_MANIFEST_SHA256 = (
    "2cf969b442a6b8b2f5a603fcb7db35d83e1380935b59a839bcf608e35c8fbbdb"
)
CHANGE_TREE_SHA256 = (
    "63fe7a3613e7edb8e924009a4e5bb1a592c5355910e6779a7dad325c16969a94"
)
CHANGE_FILE_COUNT = 67
SELECTED_QUEUE_IDS = execution_adapter.SELECTED_QUEUE_IDS
SELECTED_JOB_COUNT = len(SELECTED_QUEUE_IDS)
UNSELECTED_PENDING_JOB_COUNT = execution_adapter.UNSELECTED_PENDING_JOB_COUNT
REPRESENTED_ACTIVE_JOB_COUNT = execution_adapter.REPRESENTED_ACTIVE_JOB_COUNT
DISPOSITION_PIPELINE = "satellite_review_change_explicit_v1_disposition"
DISPOSITION_STATUS = "accepted_review_only_machine_change_batch"
INCIDENT_ID = "explicit-v1-post-freeze-job-mapping-order-false-rejection"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DISPOSITION_FILENAME = "disposition.json"
INCIDENT_FILENAME = "incident.json"
README_FILENAME = "README.md"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExplicitV1DispositionError(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise ExplicitV1DispositionError(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitV1DispositionError(f"{label} is not valid JSON") from error


def _timestamp(value: str, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value:
        raise ExplicitV1DispositionError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExplicitV1DispositionError(
            f"{label} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExplicitV1DispositionError(f"{label} must include a timezone")
    utc = parsed.astimezone(UTC)
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z"), utc


def suggested_publication_times() -> tuple[str, str]:
    """Return comfortably future catalog and disposition publication times."""

    now = datetime.now(UTC).replace(microsecond=0)
    catalog = now + timedelta(seconds=90)
    disposition = now + timedelta(seconds=180)
    return (
        catalog.isoformat().replace("+00:00", "Z"),
        disposition.isoformat().replace("+00:00", "Z"),
    )


def _exact_file(path: Path, expected: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV1DispositionError(f"{label} is not a regular file")
    raw = path.read_bytes()
    if _sha256(raw) != expected:
        raise ExplicitV1DispositionError(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def tree_sha256(root: Path) -> tuple[str, int, int]:
    """Return the same deterministic path-bound file-tree digest as the run."""

    if root.is_symlink() or not root.is_dir():
        raise ExplicitV1DispositionError(f"tree root is not a directory: {root}")
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ExplicitV1DispositionError(f"tree contains a symlink: {path}")
        if path.is_file():
            raw = path.read_bytes()
            total_bytes += len(raw)
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": len(raw),
                    "sha256": _sha256(raw),
                }
            )
        elif not path.is_dir():
            raise ExplicitV1DispositionError(
                f"tree contains a non-regular path: {path}"
            )
    payload = (
        json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return _sha256(payload), len(entries), total_bytes


def _validate_frozen_modes(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ExplicitV1DispositionError(f"frozen root is invalid: {root}")
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        raise ExplicitV1DispositionError(f"frozen root mode changed: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExplicitV1DispositionError(f"frozen tree contains symlink: {path}")
        expected = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(path.stat().st_mode) != expected:
            raise ExplicitV1DispositionError(f"frozen member mode changed: {path}")


def _validate_source_catalog(path: Path) -> dict[str, Any]:
    if path.resolve() != SOURCE_CATALOG_PATH.resolve():
        raise ExplicitV1DispositionError("source catalog checkpoint path changed")
    _exact_file(
        path / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "source catalog manifest",
    )
    _exact_file(
        path / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "source selection receipt",
    )
    try:
        document = validate_explicit_satellite_batch_v1(
            QUEUE_PATH, path, config=ExplicitBatchConfig()
        )
    except Exception as error:
        raise ExplicitV1DispositionError(
            f"source catalog checkpoint failed validation: {error}"
        ) from error
    if (
        document["state"] != "selection_complete"
        or document["summary"]["selected_jobs_completed"] != SELECTED_JOB_COUNT
        or document["summary"]["jobs_not_selected"]
        != UNSELECTED_PENDING_JOB_COUNT
        or document["summary"]["selected_jobs_failed"] != 0
        or document["summary"]["selected_jobs_unavailable_no_scene"] != 0
    ):
        raise ExplicitV1DispositionError("source catalog terminal accounting changed")
    return document


def validate_finalized_catalog(
    path: Path = FINALIZED_CATALOG_PATH,
    *,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    """Validate exact bytes, all terminal jobs, modes, and publication ctime."""

    _exact_file(
        path / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "finalized catalog manifest",
    )
    _exact_file(
        path / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "finalized selection receipt",
    )
    try:
        document = validate_explicit_satellite_batch_v1(
            QUEUE_PATH, path, config=ExplicitBatchConfig()
        )
    except Exception as error:
        raise ExplicitV1DispositionError(
            f"finalized catalog copy failed validation: {error}"
        ) from error
    _validate_frozen_modes(path)
    final_digest, final_files, final_bytes = tree_sha256(path)
    if (final_digest, final_files, final_bytes) != (
        SOURCE_CATALOG_TREE_SHA256,
        SOURCE_CATALOG_FILE_COUNT,
        SOURCE_CATALOG_TOTAL_BYTES,
    ):
        raise ExplicitV1DispositionError(
            "finalized catalog is not byte-identical to its source checkpoint"
        )
    if finalized_at is not None:
        normalized, parsed = _timestamp(finalized_at, "catalog finalized_at")
        if path.stat().st_ctime + 1e-6 < parsed.timestamp():
            raise ExplicitV1DispositionError(
                f"finalized catalog root ctime precedes {normalized}"
            )
    return document


def _catalog_lineage(
    index: int, root: Path, document: Mapping[str, Any]
) -> dict[str, Any]:
    if index != 0 or root.resolve() != FINALIZED_CATALOG_PATH.resolve():
        raise ExplicitV1DispositionError(
            "change disposition accepts only the frozen finalized catalog copy"
        )
    raw = _exact_file(
        root / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "finalized catalog manifest",
    )
    if _strict_json(raw, "finalized catalog manifest") != document:
        raise ExplicitV1DispositionError(
            "finalized catalog manifest changed after validation"
        )
    receipt = _exact_file(
        root / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "finalized selection receipt",
    )
    sidecar = root / "selection-receipt.sha256"
    sidecar_raw = sidecar.read_bytes()
    summary = document["summary"]
    return {
        "index": index,
        "schema_version": document["schema_version"],
        "pipeline": document["pipeline"],
        "state": document["state"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "manifest_file": "batch-manifest.json",
        "manifest_bytes": len(raw),
        "manifest_sha256": CATALOG_MANIFEST_SHA256,
        "queue_manifest_sha256": document["queue_bundle"]["manifest_sha256"],
        "jobs_represented": REPRESENTED_ACTIVE_JOB_COUNT,
        "jobs_selected": SELECTED_JOB_COUNT,
        "jobs_completed": summary["selected_jobs_completed"],
        "jobs_unavailable_no_scene": summary[
            "selected_jobs_unavailable_no_scene"
        ],
        "jobs_failed": summary["selected_jobs_failed"],
        "jobs_pending": UNSELECTED_PENDING_JOB_COUNT,
        "selected_jobs_pending": summary["selected_jobs_pending"],
        "unselected_pending_jobs": UNSELECTED_PENDING_JOB_COUNT,
        "selection_receipt_file": "selection-receipt.json",
        "selection_receipt_bytes": len(receipt),
        "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
        "selection_receipt_sidecar_file": "selection-receipt.sha256",
        "selection_receipt_sidecar_bytes": len(sidecar_raw),
        "selection_receipt_sidecar_sha256": _sha256(sidecar_raw),
    }


def _validation_carrier() -> types.ModuleType:
    raw = _exact_file(
        GENERIC_CARRIER_PATH, GENERIC_CARRIER_SHA256, "generic change carrier"
    )
    _exact_file(
        EXECUTION_ADAPTER_PATH,
        EXECUTION_ADAPTER_SHA256,
        "explicit change execution adapter",
    )
    _exact_file(
        ROOT_SHIM_PATH, EXECUTION_ROOT_SHIM_SHA256, "explicit change root shim"
    )
    _exact_file(
        EXECUTION_CLI_PATH, EXECUTION_CLI_SHA256, "explicit change CLI"
    )
    module_name = f"{__package__}._satellite_change_explicit_v1_validation_carrier"
    module = types.ModuleType(module_name)
    module.__file__ = str(GENERIC_CARRIER_PATH)
    module.__package__ = __package__
    sys.modules[module_name] = module
    try:
        exec(compile(raw, str(GENERIC_CARRIER_PATH), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise

    def validator(_queue: Path, catalog: Path) -> Mapping[str, Any]:
        return validate_finalized_catalog(catalog)

    def lineage(
        index: int, root: Path, document: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            return _catalog_lineage(index, root, document)
        except ExplicitV1DispositionError as error:
            raise module.SatelliteChangeBatchError(str(error)) from error

    module.validate_satellite_batch = validator
    module._catalog_lineage = lineage
    module.PROCESSOR_FILES = execution_adapter.PROCESSOR_FILES
    module.CHANGE_BATCH_PIPELINE = execution_adapter.PIPELINE
    module.CHANGE_SCOPE = dict(execution_adapter._derived_carrier().CHANGE_SCOPE)
    return module


def validate_frozen_change_run(
    finalized_catalog_path: Path = FINALIZED_CATALOG_PATH,
    change_run_path: Path = CHANGE_RUN_PATH,
) -> dict[str, Any]:
    """Validate the frozen run against the immutable catalog copy."""

    validate_finalized_catalog(finalized_catalog_path)
    _exact_file(
        change_run_path / "batch-manifest.json",
        CHANGE_MANIFEST_SHA256,
        "change-run manifest",
    )
    carrier = _validation_carrier()
    try:
        document = carrier.validate_satellite_change_batch(
            QUEUE_PATH,
            [finalized_catalog_path],
            change_run_path,
            config=carrier.ChangeBatchConfig(
                timeout_seconds=execution_adapter.DEFAULT_TIMEOUT_SECONDS,
                minimum_interval_seconds=(
                    execution_adapter.DEFAULT_MINIMUM_INTERVAL_SECONDS
                ),
                max_job_attempts=1,
            ),
            include_queue_ids=SELECTED_QUEUE_IDS,
        )
    except Exception as error:
        raise ExplicitV1DispositionError(
            f"frozen change run failed validation: {error}"
        ) from error
    selection = document["selection"]
    if tuple(selection["selected_queue_ids"]) != SELECTED_QUEUE_IDS:
        raise ExplicitV1DispositionError("ordered change selection changed")
    if set(document["jobs"]) != set(SELECTED_QUEUE_IDS):
        raise ExplicitV1DispositionError("unordered change job mapping changed")
    queue_order = tuple(
        sorted(document["jobs"], key=lambda key: document["jobs"][key]["queue_position"])
    )
    if queue_order != SELECTED_QUEUE_IDS:
        raise ExplicitV1DispositionError("change job queue order changed")
    if any(
        task["state"] != "completed"
        or task["attempts"] != 1
        or task["failures"]
        for task in document["jobs"].values()
    ):
        raise ExplicitV1DispositionError("change job terminal outcomes changed")
    if any(run["jobs_recovered_after_publish"] != 0 for run in document["runs"]):
        raise ExplicitV1DispositionError("change run adopted an unexpected output")
    if document["summary"] != {
        "catalog_completed_jobs": 11,
        "catalog_completed_jobs_excluded": 0,
        "catalog_completed_jobs_not_in_inclusion": 0,
        "exclusion_ids_without_completed_catalog": 0,
        "jobs_completed": 11,
        "jobs_exhausted": 0,
        "jobs_failed": 0,
        "jobs_pending": 0,
        "jobs_running": 0,
        "jobs_selected": 11,
    }:
        raise ExplicitV1DispositionError("change-run summary changed")
    _validate_frozen_modes(change_run_path)
    digest, files, _bytes = tree_sha256(change_run_path)
    if digest != CHANGE_TREE_SHA256 or files != CHANGE_FILE_COUNT:
        raise ExplicitV1DispositionError("change-run full tree changed")
    return document


def _copy_frozen_tree(source: Path, stage: Path) -> None:
    if stage.is_symlink() or (stage.exists() and not stage.is_dir()):
        raise ExplicitV1DispositionError(f"copy stage is invalid: {stage}")
    if stage.exists():
        if any(stage.iterdir()):
            raise ExplicitV1DispositionError(f"copy stage is not empty: {stage}")
        stage.chmod(0o700)
    else:
        stage.mkdir(mode=0o700)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ExplicitV1DispositionError(f"source contains a symlink: {path}")
        relative = path.relative_to(source)
        destination = stage / relative
        if path.is_dir():
            destination.mkdir(mode=0o700)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            raw = path.read_bytes()
            descriptor = os.open(
                destination,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(descriptor)
            destination.chmod(0o444)
        else:
            raise ExplicitV1DispositionError(
                f"source contains a non-regular path: {path}"
            )
    for path in sorted(
        (item for item in stage.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)
    # Darwin renamex_np(RENAME_EXCL) requires a writable source bundle root
    # when it is moved into its final name. Nested directories and all files
    # are already frozen; the published root is changed to 0555 immediately.
    stage.chmod(0o755)


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise ExplicitV1DispositionError("no-replace rename unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise ExplicitV1DispositionError("no-replace rename unavailable")
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
        raise ExplicitV1DispositionError("no-replace rename unavailable")
    if result == 0:
        destination.chmod(0o555)
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ExplicitV1DispositionError(
            f"late publication collision: {destination}"
        )
    raise ExplicitV1DispositionError(
        f"no-replace publication failed: {os.strerror(error_number)}"
    )


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


def _stage_precedes(stage: Path, target: datetime) -> None:
    cutoff = target.timestamp()
    for path in (stage, *stage.rglob("*")):
        status = path.stat()
        birth = getattr(status, "st_birthtime", status.st_mtime)
        if max(birth, status.st_mtime) > cutoff:
            raise ExplicitV1DispositionError(
                f"staged byte or directory is newer than publication time: {path}"
            )


def _discard_owned_stage(stage: Path, parent: Path, prefix: str) -> None:
    """Remove only an owned failed private stage after making it traversable."""

    if (
        not stage.exists()
        or stage.is_symlink()
        or stage.parent.resolve() != parent.resolve()
        or not stage.name.startswith(prefix)
    ):
        return
    for path in (stage, *stage.rglob("*")):
        if path.is_symlink():
            return
        try:
            path.chmod(0o700 if path.is_dir() else 0o600)
        except OSError:
            return
    shutil.rmtree(stage)


def publish_finalized_catalog(finalized_at: str) -> dict[str, Any]:
    """Copy, validate, freeze, and no-replace publish the catalog checkpoint."""

    normalized, target = _timestamp(finalized_at, "catalog finalized_at")
    if target.timestamp() <= time.time():
        raise ExplicitV1DispositionError("catalog finalized_at must be in the future")
    if FINALIZED_CATALOG_PATH.exists() or FINALIZED_CATALOG_PATH.is_symlink():
        raise ExplicitV1DispositionError("finalized catalog destination already exists")
    _validate_source_catalog(SOURCE_CATALOG_PATH)
    source_digest, source_files, source_bytes = tree_sha256(SOURCE_CATALOG_PATH)
    if (source_digest, source_files, source_bytes) != (
        SOURCE_CATALOG_TREE_SHA256,
        SOURCE_CATALOG_FILE_COUNT,
        SOURCE_CATALOG_TOTAL_BYTES,
    ):
        raise ExplicitV1DispositionError("source catalog tree changed")
    FINALIZED_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=".open-seed-v71-explicit-final-v1.",
            dir=FINALIZED_CATALOG_PATH.parent,
        )
    )
    try:
        _copy_frozen_tree(SOURCE_CATALOG_PATH, stage)
        try:
            validate_explicit_satellite_batch_v1(
                QUEUE_PATH, stage, config=ExplicitBatchConfig()
            )
        except Exception as error:
            raise ExplicitV1DispositionError(
                f"staged finalized catalog failed validation: {error}"
            ) from error
        stage_digest, stage_files, stage_bytes = tree_sha256(stage)
        if (stage_digest, stage_files, stage_bytes) != (
            source_digest,
            source_files,
            source_bytes,
        ):
            raise ExplicitV1DispositionError("staged catalog copy changed bytes")
        _stage_precedes(stage, target)
        _validate_source_catalog(SOURCE_CATALOG_PATH)
        _wait_until(target)
        _promote_noreplace(stage, FINALIZED_CATALOG_PATH)
    except BaseException:
        _discard_owned_stage(
            stage,
            FINALIZED_CATALOG_PATH.parent,
            ".open-seed-v71-explicit-final-v1.",
        )
        raise
    validate_finalized_catalog(FINALIZED_CATALOG_PATH, finalized_at=normalized)
    return {
        "finalized_at": normalized,
        "source_checkpoint": SOURCE_CATALOG_PATH.relative_to(PACKAGE_ROOT).as_posix(),
        "finalized_copy": FINALIZED_CATALOG_PATH.relative_to(PACKAGE_ROOT).as_posix(),
        "manifest_sha256": CATALOG_MANIFEST_SHA256,
        "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
        "tree_sha256": source_digest,
        "files": source_files,
        "bytes": source_bytes,
        "root_mode": "0555",
        "file_mode": "0444",
        "directory_mode": "0555",
    }


def _source_records() -> dict[str, Any]:
    return {
        "generic_change_carrier": {
            "path": GENERIC_CARRIER_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(GENERIC_CARRIER_PATH),
        },
        "execution_adapter": {
            "path": EXECUTION_ADAPTER_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(EXECUTION_ADAPTER_PATH),
        },
        "execution_root_shim": {
            "path": ROOT_SHIM_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(ROOT_SHIM_PATH),
        },
        "execution_cli": {
            "path": EXECUTION_CLI_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(EXECUTION_CLI_PATH),
        },
        "disposition_module": {
            "path": DISPOSITION_MODULE_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(DISPOSITION_MODULE_PATH),
        },
        "disposition_root_shim": {
            "path": DISPOSITION_ROOT_SHIM_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(DISPOSITION_ROOT_SHIM_PATH),
        },
        "disposition_cli": {
            "path": DISPOSITION_CLI_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            **_file_record(DISPOSITION_CLI_PATH),
        },
    }


def _disposition_documents(
    generated_at: str, catalog_finalized_at: str
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    change = validate_frozen_change_run()
    catalog_digest, catalog_files, catalog_bytes = tree_sha256(FINALIZED_CATALOG_PATH)
    change_digest, change_files, change_bytes = tree_sha256(CHANGE_RUN_PATH)
    incident = {
        "schema_version": 1,
        "incident_id": INCIDENT_ID,
        "classification": "post_freeze_adapter_validation_false_rejection",
        "trigger": (
            "The adapter compared tuple(document['jobs']) with receipt order after "
            "canonical JSON had sorted mapping keys."
        ),
        "correct_contract": {
            "job_mapping_semantics": "unordered_exact_key_set",
            "ordered_selection_field": "selection.selected_queue_ids",
            "ordered_selection_sha256": _sha256(
                ("\n".join(SELECTED_QUEUE_IDS) + "\n").encode("ascii")
            ),
        },
        "effect": {
            "pixel_jobs_completed_before_trigger": 11,
            "pixel_job_failures": 0,
            "pixel_job_retries": 0,
            "unexpected_output_adoptions": 0,
            "frozen_change_bytes_mutated": False,
            "original_catalog_checkpoint_mutated": False,
        },
        "resolution": (
            "An external exact-source validator uses the immutable ordered selection "
            "field and treats the jobs object as an unordered exact mapping."
        ),
    }
    disposition = {
        "schema_version": 1,
        "pipeline": DISPOSITION_PIPELINE,
        "generated_at": generated_at,
        "status": DISPOSITION_STATUS,
        "source_catalog_checkpoint": {
            "path": SOURCE_CATALOG_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "mutable_execution_checkpoint": True,
            "manifest_sha256": CATALOG_MANIFEST_SHA256,
            "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
            "tree_sha256_at_finalization": SOURCE_CATALOG_TREE_SHA256,
            "files": SOURCE_CATALOG_FILE_COUNT,
            "bytes": SOURCE_CATALOG_TOTAL_BYTES,
        },
        "finalized_catalog_copy": {
            "path": FINALIZED_CATALOG_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "finalized_at": catalog_finalized_at,
            "byte_identical_to_source_checkpoint": True,
            "manifest_sha256": CATALOG_MANIFEST_SHA256,
            "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
            "tree_sha256": catalog_digest,
            "files": catalog_files,
            "bytes": catalog_bytes,
            "root_mode": "0555",
            "file_mode": "0444",
            "directory_mode": "0555",
        },
        "change_run": {
            "path": CHANGE_RUN_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "manifest_sha256": CHANGE_MANIFEST_SHA256,
            "tree_sha256": change_digest,
            "files": change_files,
            "bytes": change_bytes,
            "state": change["state"],
            "summary": change["summary"],
            "selected_queue_ids": list(SELECTED_QUEUE_IDS),
            "jobs_mapping_exact_unordered": True,
            "jobs_completed_once": SELECTED_JOB_COUNT,
            "job_failures": 0,
            "job_retries": 0,
            "unexpected_output_adoptions": 0,
            "root_mode": "0555",
            "file_mode": "0444",
            "directory_mode": "0555",
        },
        "incident": {
            "incident_id": INCIDENT_ID,
            "file": INCIDENT_FILENAME,
        },
        "evidence_scope": {
            "artifact_kind": "unreviewed_visible_change_proposals",
            "analyst_decisions_created": False,
            "atlas_mutation": False,
            "automated_promotion_allowed": False,
            "identity_claim": False,
            "construction_status_claim": False,
            "lifecycle_claim": False,
            "operating_status_claim": False,
            "operator_claim": False,
            "data_centre_type_claim": False,
            "it_capacity_claim": False,
            "pue_claim": False,
            "workload_claim": False,
            "power_claim": False,
            "energy_claim": False,
            "unique_site_claim": False,
            "review_required": True,
        },
        "validator_sources": _source_records(),
    }
    readme = (
        "# Explicit v71 satellite-change disposition\n\n"
        "This release accepts one frozen 11-job machine change-proposal batch and "
        "records the adapter's post-freeze mapping-order false rejection. The "
        "ordered receipt selection remains exact; the jobs JSON object is validated "
        "as an unordered exact mapping.\n\n"
        "The original mutable catalog execution checkpoint was not changed. Its "
        "exact bytes were copied to a separately versioned immutable 0444/0555 "
        "catalog path before this disposition revalidated the frozen change run.\n\n"
        "No analyst decision or Atlas identity, construction status, lifecycle, "
        "operator, type, capacity, PUE, workload, power, or energy claim is created.\n"
    ).encode("utf-8")
    return disposition, incident, readme


def _write_exclusive(path: Path, raw: bytes, mode: int = 0o444) -> None:
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    path.chmod(mode)


def validate_disposition(
    path: Path = DISPOSITION_PATH,
    *,
    expected_generated_at: str | None = None,
    expected_catalog_finalized_at: str | None = None,
) -> dict[str, Any]:
    """Validate the published wrapper and all live bound artifacts offline."""

    _validate_frozen_modes(path)
    allowed = {
        README_FILENAME,
        DISPOSITION_FILENAME,
        INCIDENT_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    if {item.name for item in path.iterdir()} != allowed:
        raise ExplicitV1DispositionError("disposition file inventory changed")
    raw = (path / MANIFEST_FILENAME).read_bytes()
    manifest = _strict_json(raw, "disposition manifest")
    if raw != _canonical_json(manifest):
        raise ExplicitV1DispositionError("disposition manifest is not canonical")
    sidecar = (path / MANIFEST_HASH_FILENAME).read_bytes()
    if sidecar != f"{_sha256(raw)}  {MANIFEST_FILENAME}\n".encode("ascii"):
        raise ExplicitV1DispositionError("disposition manifest sidecar changed")
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema_version") != 1
        or manifest.get("pipeline") != DISPOSITION_PIPELINE
        or manifest.get("status") != DISPOSITION_STATUS
        or set(manifest.get("artifacts", {}))
        != {README_FILENAME, DISPOSITION_FILENAME, INCIDENT_FILENAME}
    ):
        raise ExplicitV1DispositionError("disposition manifest identity changed")
    generated_at, generated = _timestamp(
        manifest.get("generated_at"), "disposition generated_at"
    )
    if expected_generated_at is not None and generated_at != _timestamp(
        expected_generated_at, "expected disposition generated_at"
    )[0]:
        raise ExplicitV1DispositionError("disposition generated_at changed")
    if path.stat().st_ctime + 1e-6 < generated.timestamp():
        raise ExplicitV1DispositionError(
            "disposition root ctime precedes generated_at"
        )
    artifacts: dict[str, bytes] = {}
    for name, record in manifest["artifacts"].items():
        artifact_raw = (path / name).read_bytes()
        if record != {"bytes": len(artifact_raw), "sha256": _sha256(artifact_raw)}:
            raise ExplicitV1DispositionError(f"disposition artifact changed: {name}")
        artifacts[name] = artifact_raw
    disposition = _strict_json(artifacts[DISPOSITION_FILENAME], "disposition")
    incident = _strict_json(artifacts[INCIDENT_FILENAME], "incident")
    if incident.get("incident_id") != INCIDENT_ID:
        raise ExplicitV1DispositionError("incident identity changed")
    catalog_finalized_at = disposition["finalized_catalog_copy"]["finalized_at"]
    if expected_catalog_finalized_at is not None and catalog_finalized_at != _timestamp(
        expected_catalog_finalized_at, "expected catalog finalized_at"
    )[0]:
        raise ExplicitV1DispositionError("catalog finalized_at changed")
    validate_finalized_catalog(
        FINALIZED_CATALOG_PATH, finalized_at=catalog_finalized_at
    )
    validate_frozen_change_run()
    expected_disposition, expected_incident, expected_readme = _disposition_documents(
        generated_at, catalog_finalized_at
    )
    if (
        disposition != expected_disposition
        or incident != expected_incident
        or artifacts[README_FILENAME] != expected_readme
    ):
        raise ExplicitV1DispositionError("disposition content does not reproduce")
    return dict(manifest)


def publish_disposition(
    generated_at: str,
    catalog_finalized_at: str,
) -> dict[str, Any]:
    """Stage, freeze, and no-replace publish the external disposition."""

    normalized, target = _timestamp(generated_at, "disposition generated_at")
    catalog_time = _timestamp(catalog_finalized_at, "catalog finalized_at")[0]
    if target.timestamp() <= time.time():
        raise ExplicitV1DispositionError("disposition generated_at must be in the future")
    if DISPOSITION_PATH.exists() or DISPOSITION_PATH.is_symlink():
        raise ExplicitV1DispositionError("disposition destination already exists")
    validate_finalized_catalog(FINALIZED_CATALOG_PATH, finalized_at=catalog_time)
    disposition, incident, readme = _disposition_documents(normalized, catalog_time)
    payloads = {
        DISPOSITION_FILENAME: _canonical_json(disposition),
        INCIDENT_FILENAME: _canonical_json(incident),
        README_FILENAME: readme,
    }
    manifest = {
        "schema_version": 1,
        "pipeline": DISPOSITION_PIPELINE,
        "generated_at": normalized,
        "status": DISPOSITION_STATUS,
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(payloads.items())
        },
    }
    manifest_raw = _canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    DISPOSITION_PATH.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=".explicit-v1-disposition.", dir=DISPOSITION_PATH.parent
        )
    )
    try:
        for name, raw in payloads.items():
            _write_exclusive(stage / name, raw)
        stage.chmod(0o755)
        _stage_precedes(stage, target)
        validate_frozen_change_run()
        _wait_until(target)
        _promote_noreplace(stage, DISPOSITION_PATH)
    except BaseException:
        _discard_owned_stage(
            stage,
            DISPOSITION_PATH.parent,
            ".explicit-v1-disposition.",
        )
        raise
    return validate_disposition(
        DISPOSITION_PATH,
        expected_generated_at=normalized,
        expected_catalog_finalized_at=catalog_time,
    )


def publish_all(
    catalog_finalized_at: str,
    disposition_generated_at: str,
) -> dict[str, Any]:
    """Publish the immutable catalog copy, then its external disposition."""

    catalog = publish_finalized_catalog(catalog_finalized_at)
    disposition = publish_disposition(
        disposition_generated_at, catalog["finalized_at"]
    )
    disposition_raw = (DISPOSITION_PATH / MANIFEST_FILENAME).read_bytes()
    disposition_tree, disposition_files, disposition_bytes = tree_sha256(
        DISPOSITION_PATH
    )
    return {
        "catalog": catalog,
        "change_run": {
            "manifest_sha256": CHANGE_MANIFEST_SHA256,
            "tree_sha256": CHANGE_TREE_SHA256,
            "files": CHANGE_FILE_COUNT,
        },
        "disposition": {
            "generated_at": disposition["generated_at"],
            "manifest_sha256": _sha256(disposition_raw),
            "tree_sha256": disposition_tree,
            "files": disposition_files,
            "bytes": disposition_bytes,
            "status": disposition["status"],
        },
    }


__all__ = [
    "CATALOG_MANIFEST_SHA256",
    "CHANGE_MANIFEST_SHA256",
    "CHANGE_RUN_PATH",
    "CHANGE_TREE_SHA256",
    "DISPOSITION_PATH",
    "DISPOSITION_STATUS",
    "ExplicitV1DispositionError",
    "FINALIZED_CATALOG_PATH",
    "INCIDENT_ID",
    "SELECTION_RECEIPT_SHA256",
    "SOURCE_CATALOG_PATH",
    "publish_all",
    "publish_disposition",
    "publish_finalized_catalog",
    "suggested_publication_times",
    "tree_sha256",
    "validate_disposition",
    "validate_finalized_catalog",
    "validate_frozen_change_run",
]
