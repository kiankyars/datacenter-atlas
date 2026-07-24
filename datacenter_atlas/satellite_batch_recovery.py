"""Fail-closed recovery of a bounded satellite catalog tranche.

This module reconciles selected terminal catalog results from an interrupted
batch onto an immutable, previously validated base batch.  It never performs a
network request and never turns catalog availability into an identity,
lifecycle, operating-status, workload, or power claim.

The recovered artifact is a sealed wrapper rather than a resumable live-run
directory.  ``batch/`` remains a normal satellite batch that validates with
``validate_satellite_batch``; the wrapper records why and how it was recovered.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .satellite_batch import (
    BATCH_MANIFEST_FILENAME,
    BATCH_SCOPE,
    BATCH_SCHEMA_VERSION,
    CATALOG_FILES,
    DEFAULT_MAX_RESPONSE_BYTES,
    PRIOR_BATCH_SCHEMA_VERSION,
    UNAVAILABLE_NO_SCENE,
    BatchConfig,
    SatelliteBatchError,
    _catalog_result,
    _config_from_manifest,
    _migrate_prior_checkpoint,
    _read_jobs,
    _queue_lineage,
    _safe_directory,
    _summary,
    _timestamp,
    _update_document,
    _validate_checkpoint,
    validate_satellite_batch,
)
from .satellite_queue import REVIEW_CONSTRAINTS, validate_queue_bundle


RECOVERY_FORMAT = "datacenter-atlas-satellite-batch-recovery-v3"
RECOVERY_SCHEMA_VERSION = 3
RECOVERY_MANIFEST_FILENAME = "recovery-manifest.json"
RECOVERY_MANIFEST_HASH_FILENAME = "manifest.sha256"
RECOVERY_INVENTORY_FILENAME = "inventory.jsonl"
SOURCE_MANIFEST_SNAPSHOT_FILENAME = "source-evidence-manifest-snapshot.json"
SELECTED_QUEUE_JOBS_FILENAME = "selected-queue-jobs.jsonl"
RECOVERED_BATCH_DIRECTORY = "batch"
RUN_HISTORY_LIMITATION = (
    "the source schema retains only last_run; it does not identify which process "
    "or run produced the selected terminal task records"
)
TERMINAL_TASK_TIME_BASIS = (
    "timestamps copied from selected terminal task records; process and run "
    "causality are not inferred"
)
RECOVERY_METHOD = (
    "offline schema-v2 base audit and migration followed by exact selected "
    "terminal-task and three-file catalog copying"
)
RECOVERY_ROOT_FILES = frozenset(
    {
        RECOVERY_MANIFEST_FILENAME,
        RECOVERY_MANIFEST_HASH_FILENAME,
        RECOVERY_INVENTORY_FILENAME,
        SOURCE_MANIFEST_SNAPSHOT_FILENAME,
        SELECTED_QUEUE_JOBS_FILENAME,
    }
)
RECOVERY_SCOPE = {
    "mode": "offline_recovery_reconciliation",
    "network_requests_performed": False,
    "source_batch_promoted": False,
    "source_evidence_accepted_for_release": False,
    "atlas_mutation": False,
    "change_analysis_executed": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_power_inference": False,
    "review_required": True,
}


class SatelliteBatchRecoveryError(ValueError):
    """Raised when a recovery input or sealed output fails validation."""


def _integer(value: Any, field: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise SatelliteBatchRecoveryError(f"{field} must be a {qualifier} integer")
    return value


def _checkpoint_observation(value: Any) -> dict[str, Any]:
    expected_keys = {
        "manifest_sha256",
        "manifest_bytes",
        "updated_at",
        "summary",
        "last_run",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise SatelliteBatchRecoveryError(
            "incident must include the exact observed unfinished checkpoint"
        )
    digest = value["manifest_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation has an invalid SHA-256"
        )
    manifest_bytes = _integer(
        value["manifest_bytes"],
        "interrupted checkpoint observation manifest_bytes",
        positive=True,
    )
    updated_at = _timestamp(
        value["updated_at"], "interrupted checkpoint observation updated_at"
    )
    if updated_at != value["updated_at"]:
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation updated_at is not canonical UTC"
        )

    summary = value["summary"]
    summary_keys = {
        "jobs_selected",
        "jobs_completed",
        "jobs_failed",
        "jobs_pending",
        "jobs_unavailable_no_scene",
    }
    if not isinstance(summary, Mapping) or set(summary) != summary_keys:
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation summary has an invalid schema"
        )
    normalized_summary = {
        key: _integer(summary[key], f"interrupted checkpoint summary {key}")
        for key in sorted(summary_keys)
    }
    if normalized_summary["jobs_selected"] != sum(
        normalized_summary[key]
        for key in (
            "jobs_completed",
            "jobs_failed",
            "jobs_pending",
            "jobs_unavailable_no_scene",
        )
    ):
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation summary does not reconcile"
        )

    last_run = value["last_run"]
    run_keys = {
        "started_at",
        "finished_at",
        "max_jobs",
        "max_http_attempts",
        "job_attempts",
        "http_attempts_reserved",
        "jobs_completed",
        "jobs_failed",
        "jobs_unavailable_no_scene",
        "budget_exhausted",
    }
    if not isinstance(last_run, Mapping) or set(last_run) != run_keys:
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation last_run has an invalid schema"
        )
    started_at = _timestamp(
        last_run["started_at"], "interrupted checkpoint last_run started_at"
    )
    if started_at != last_run["started_at"] or last_run["finished_at"] is not None:
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation must retain a canonical unfinished run"
        )
    normalized_run = {
        "started_at": started_at,
        "finished_at": None,
        "max_jobs": _integer(
            last_run["max_jobs"], "interrupted checkpoint last_run max_jobs", positive=True
        ),
        "max_http_attempts": _integer(
            last_run["max_http_attempts"],
            "interrupted checkpoint last_run max_http_attempts",
            positive=True,
        ),
        "job_attempts": _integer(
            last_run["job_attempts"], "interrupted checkpoint last_run job_attempts"
        ),
        "http_attempts_reserved": _integer(
            last_run["http_attempts_reserved"],
            "interrupted checkpoint last_run http_attempts_reserved",
        ),
        "jobs_completed": _integer(
            last_run["jobs_completed"],
            "interrupted checkpoint last_run jobs_completed",
        ),
        "jobs_failed": _integer(
            last_run["jobs_failed"], "interrupted checkpoint last_run jobs_failed"
        ),
        "jobs_unavailable_no_scene": _integer(
            last_run["jobs_unavailable_no_scene"],
            "interrupted checkpoint last_run jobs_unavailable_no_scene",
        ),
        "budget_exhausted": last_run["budget_exhausted"],
    }
    if not isinstance(normalized_run["budget_exhausted"], bool):
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint last_run budget_exhausted must be boolean"
        )
    if (
        normalized_run["job_attempts"] > normalized_run["max_jobs"]
        or normalized_run["http_attempts_reserved"]
        > normalized_run["max_http_attempts"]
        or normalized_run["jobs_completed"]
        + normalized_run["jobs_failed"]
        + normalized_run["jobs_unavailable_no_scene"]
        > normalized_run["job_attempts"]
    ):
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation last_run does not reconcile"
        )
    if started_at > updated_at:
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation predates its run start"
        )
    return {
        "manifest_sha256": digest,
        "manifest_bytes": manifest_bytes,
        "updated_at": updated_at,
        "summary": normalized_summary,
        "last_run": normalized_run,
    }


@dataclass(frozen=True, slots=True)
class RecoveryIncident:
    """Operator-observed interruption context retained as provenance only."""

    observed_writer_pids: Sequence[int]
    launchd_service_observations: Sequence[Mapping[str, str]]
    reported_guard_pid: int | None = None
    interrupted_checkpoint_observation: Mapping[str, Any] | None = None
    handling: str = (
        "operator-supplied handling note; recovery did not verify process, service, "
        "or guard state and treated the interrupted source as read-only evidence"
    )

    def as_dict(self) -> dict[str, Any]:
        if not isinstance(self.handling, str) or not self.handling.strip():
            raise SatelliteBatchRecoveryError("incident handling must be non-empty")
        pids = list(self.observed_writer_pids)
        if not pids or any(
            isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 for pid in pids
        ):
            raise SatelliteBatchRecoveryError(
                "observed writer PIDs must be a non-empty sequence of positive integers"
            )
        if len(set(pids)) != len(pids):
            raise SatelliteBatchRecoveryError("observed writer PIDs must be unique")
        services = list(self.launchd_service_observations)
        normalized_services: list[dict[str, str]] = []
        for observation in services:
            if (
                not isinstance(observation, Mapping)
                or set(observation) != {"label", "status"}
                or not isinstance(observation["label"], str)
                or not observation["label"].strip()
                or not isinstance(observation["status"], str)
                or not observation["status"].strip()
            ):
                raise SatelliteBatchRecoveryError(
                    "launchd service observation has an invalid schema"
                )
            normalized_services.append(
                {
                    "label": observation["label"].strip(),
                    "status": observation["status"].strip(),
                }
            )
        if not normalized_services or len(
            {row["label"] for row in normalized_services}
        ) != len(normalized_services):
            raise SatelliteBatchRecoveryError(
                "launchd service observations must be non-empty and label-unique"
            )
        guard = self.reported_guard_pid
        if guard is not None and (
            isinstance(guard, bool) or not isinstance(guard, int) or guard <= 0
        ):
            raise SatelliteBatchRecoveryError(
                "reported guard PID must be a positive integer when provided"
            )
        observation = _checkpoint_observation(
            self.interrupted_checkpoint_observation
        )
        return {
            "kind": "operator_reported_interruption_context",
            "observed_writer_pids": pids,
            "launchd_service_observations": normalized_services,
            "observation_verification": "operator_supplied_unverified",
            "process_state_verified_by_recovery": False,
            "guard_lock_verified_by_recovery": False,
            "causal_linkage_claimed": False,
            "reported_guard_pid_at_task_dispatch": guard,
            "handling": self.handling.strip(),
            "interrupted_checkpoint_observation": observation,
        }


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_json_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _checkpoint(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _regular_tree(root: Path, label: str) -> tuple[list[Path], list[Path]]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteBatchRecoveryError(f"{label} is not a regular directory")
    files: list[Path] = []
    directories: list[Path] = [root]
    for parent, directory_names, file_names in os.walk(root, followlinks=False):
        parent_path = Path(parent)
        for name in sorted(directory_names):
            path = parent_path / name
            if path.is_symlink() or not path.is_dir():
                raise SatelliteBatchRecoveryError(
                    f"{label} contains a symlink or irregular directory: {path}"
                )
            directories.append(path)
        for name in sorted(file_names):
            path = parent_path / name
            if path.is_symlink() or not path.is_file():
                raise SatelliteBatchRecoveryError(
                    f"{label} contains a symlink or irregular file: {path}"
                )
            files.append(path)
    return sorted(files), sorted(directories)


def _inventory(root: Path, label: str) -> tuple[list[dict[str, Any]], bytes, set[str]]:
    files, directories = _regular_tree(root, label)
    rows: list[dict[str, Any]] = []
    for path in files:
        raw = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(raw),
                "sha256": _sha256(raw),
            }
        )
    rows.sort(key=lambda row: row["path"])
    canonical = b"".join(
        (
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n"
        ).encode("utf-8")
        for row in rows
    )
    directory_set = {
        "." if path == root else path.relative_to(root).as_posix()
        for path in directories
    }
    return rows, canonical, directory_set


def _tree_metadata(root: Path, label: str) -> list[dict[str, Any]]:
    files, directories = _regular_tree(root, label)
    rows: list[dict[str, Any]] = []
    for path in sorted(directories):
        metadata = path.stat(follow_symlinks=False)
        rows.append(
            {
                "path": "." if path == root else path.relative_to(root).as_posix(),
                "kind": "directory",
                "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "mtime_ns": metadata.st_mtime_ns,
            }
        )
    for path in files:
        before = path.stat(follow_symlinks=False)
        raw = path.read_bytes()
        after = path.stat(follow_symlinks=False)
        identity = (
            before.st_dev,
            before.st_ino,
            stat.S_IMODE(before.st_mode),
            before.st_size,
            before.st_mtime_ns,
        )
        if identity != (
            after.st_dev,
            after.st_ino,
            stat.S_IMODE(after.st_mode),
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SatelliteBatchRecoveryError(
                f"{label} file changed while metadata was captured: {path}"
            )
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "kind": "file",
                "mode": f"{stat.S_IMODE(after.st_mode):04o}",
                "device": after.st_dev,
                "inode": after.st_ino,
                "mtime_ns": after.st_mtime_ns,
                "bytes": len(raw),
                "sha256": _sha256(raw),
            }
        )
    return sorted(rows, key=lambda row: (str(row["path"]), str(row["kind"])))


def _assert_tree_unchanged(
    root: Path, expected: Sequence[Mapping[str, Any]], label: str
) -> None:
    if _tree_metadata(root, label) != list(expected):
        raise SatelliteBatchRecoveryError(
            f"{label} path, content, or mode metadata changed during recovery"
        )


def _assert_no_symlink_components(path: Path) -> None:
    if not path.is_absolute():
        raise SatelliteBatchRecoveryError(
            "recovery output parent must be an absolute path"
        )
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise SatelliteBatchRecoveryError(
                "recovery output parent must already exist"
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise SatelliteBatchRecoveryError(
                f"recovery output parent contains a symlink component: {current}"
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise SatelliteBatchRecoveryError(
                f"recovery output parent contains a non-directory component: {current}"
            )


def _output_paths(
    output_directory: str | Path, input_roots: Sequence[Path]
) -> tuple[Path, Path, Path, tuple[int, int]]:
    requested = Path(os.path.abspath(os.fspath(output_directory)))
    if requested.exists() or requested.is_symlink():
        raise SatelliteBatchRecoveryError("recovery output already exists")
    if not requested.name or requested.name in {".", ".."}:
        raise SatelliteBatchRecoveryError("recovery output name is invalid")
    _assert_no_symlink_components(requested.parent)
    try:
        parent = requested.parent.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise SatelliteBatchRecoveryError(
            "recovery output parent must already exist"
        ) from error
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteBatchRecoveryError(
            "recovery output parent is not a regular directory"
        )
    output = parent / requested.name
    stage = parent / f".{requested.name}.recovery-staging"
    if output.exists() or output.is_symlink():
        raise SatelliteBatchRecoveryError("recovery output already exists")
    if stage.exists() or stage.is_symlink():
        raise SatelliteBatchRecoveryError("recovery staging output already exists")
    roots = tuple(input_roots)
    if len(set((*roots, output, stage))) != len(roots) + 2:
        raise SatelliteBatchRecoveryError("recovery inputs and outputs must be distinct")
    for candidate in (output, stage):
        if any(
            candidate == root
            or root in candidate.parents
            or candidate in root.parents
            for root in roots
        ):
            raise SatelliteBatchRecoveryError(
                "recovery output must be outside every input"
            )
    parent_stat = parent.stat(follow_symlinks=False)
    return output, stage, parent, (parent_stat.st_dev, parent_stat.st_ino)


def _assert_directory_identity(path: Path, identity: tuple[int, int]) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SatelliteBatchRecoveryError("recovery output parent identity changed")
    metadata = path.stat(follow_symlinks=False)
    if (metadata.st_dev, metadata.st_ino) != identity:
        raise SatelliteBatchRecoveryError("recovery output parent identity changed")


def _promote_directory_exclusive(stage: Path, output: Path) -> None:
    """Atomically rename a directory without replacing a concurrently created target."""
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    destination = os.fsencode(output)
    if sys.platform == "darwin":
        rename_exclusive = getattr(library, "renamex_np", None)
        if rename_exclusive is None:
            raise SatelliteBatchRecoveryError(
                "atomic exclusive directory promotion is unavailable"
            )
        rename_exclusive.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        result = rename_exclusive(source, destination, 0x00000004)
    elif sys.platform.startswith("linux"):
        rename_exclusive = getattr(library, "renameat2", None)
        if rename_exclusive is None:
            raise SatelliteBatchRecoveryError(
                "atomic exclusive directory promotion is unavailable"
            )
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        result = rename_exclusive(-100, source, -100, destination, 0x00000001)
    else:
        raise SatelliteBatchRecoveryError(
            "atomic exclusive directory promotion is unavailable"
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SatelliteBatchRecoveryError(
            "recovery output appeared before exclusive promotion"
        )
    raise SatelliteBatchRecoveryError(
        f"exclusive recovery promotion failed: {os.strerror(error_number)}"
    )


def _inventory_summary(rows: Sequence[Mapping[str, Any]], canonical: bytes) -> dict[str, Any]:
    return {
        "files": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "canonicalization": "UTF-8 path NUL decimal-bytes NUL lowercase-SHA-256 newline",
        "sha256": _sha256(canonical),
    }


def _assert_frozen(root: Path, label: str) -> None:
    files, directories = _regular_tree(root, label)
    for path in files:
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise SatelliteBatchRecoveryError(f"{label} file is not mode 0444: {path}")
    for path in directories:
        if stat.S_IMODE(path.stat().st_mode) != 0o555:
            raise SatelliteBatchRecoveryError(
                f"{label} directory is not mode 0555: {path}"
            )


def _freeze(root: Path) -> None:
    files, directories = _regular_tree(root, "recovery staging tree")
    for path in files:
        path.chmod(0o444)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555)


def _load_canonical_manifest(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteBatchRecoveryError(f"{label} is not a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SatelliteBatchRecoveryError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise SatelliteBatchRecoveryError(f"{label} is not canonical JSON")
    return document, raw


def _queue_context(queue: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    try:
        queue_manifest = validate_queue_bundle(queue)
    except Exception as error:
        raise SatelliteBatchRecoveryError(f"queue validation failed: {error}") from error
    jobs = _read_jobs(queue)
    if any(job.get("review_constraints") != REVIEW_CONSTRAINTS for job in jobs):
        raise SatelliteBatchRecoveryError("queue job lost its review-only constraints")
    return queue_manifest, jobs, _queue_lineage(queue, queue_manifest)


def _validated_snapshot(
    raw: bytes,
    *,
    lineage: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], BatchConfig, dict[str, Mapping[str, Any]]]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SatelliteBatchRecoveryError(
            "source evidence manifest snapshot is not valid JSON"
        ) from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise SatelliteBatchRecoveryError(
            "source evidence manifest snapshot is not canonical JSON"
        )
    schema_version = document.get("schema_version")
    try:
        config = _config_from_manifest(
            document.get("configuration"), schema_version=schema_version
        )
    except SatelliteBatchError as error:
        raise SatelliteBatchRecoveryError(
            f"source evidence configuration is invalid: {error}"
        ) from error
    selected_jobs = {
        job["queue_id"]: job
        for job in jobs
        if job["priority"]["tier"] in config.priority_tiers
    }
    try:
        _validate_checkpoint(
            document,
            lineage=lineage,
            config=config,
            selected_jobs=selected_jobs,
        )
    except SatelliteBatchError as error:
        raise SatelliteBatchRecoveryError(
            f"source evidence checkpoint is structurally invalid: {error}"
        ) from error
    return document, config, selected_jobs


def _event_timestamp(task: Mapping[str, Any]) -> str | None:
    if task.get("state") == "completed":
        value = task.get("completed_at")
    elif task.get("state") in {"failed", UNAVAILABLE_NO_SCENE}:
        failures = task.get("failures")
        value = failures[-1].get("at") if isinstance(failures, list) and failures else None
    else:
        return None
    return _timestamp(value, "terminal task event timestamp") if value is not None else None


def _selected_tranche(
    *,
    jobs: Sequence[Mapping[str, Any]],
    base: Mapping[str, Any],
    source: Mapping[str, Any],
    source_directory: Path,
    source_config: BatchConfig,
    position_start: int,
    position_end: int,
) -> tuple[
    list[Mapping[str, Any]],
    list[str],
    dict[str, dict[str, Any]],
    str,
    str,
    int,
    dict[str, Any] | None,
]:
    if (
        isinstance(position_start, bool)
        or not isinstance(position_start, int)
        or isinstance(position_end, bool)
        or not isinstance(position_end, int)
        or position_start <= 0
        or position_end < position_start
    ):
        raise SatelliteBatchRecoveryError("recovery queue-position interval is invalid")
    selected_queue_jobs = [
        job
        for job in jobs
        if position_start <= job["queue_position"] <= position_end
    ]
    expected_count = position_end - position_start + 1
    if len(selected_queue_jobs) != expected_count or [
        job["queue_position"] for job in selected_queue_jobs
    ] != list(range(position_start, position_end + 1)):
        raise SatelliteBatchRecoveryError(
            "recovery interval is not a closed contiguous queue-position tranche"
        )
    queue_ids = [str(job["queue_id"]) for job in selected_queue_jobs]
    if len(set(queue_ids)) != expected_count:
        raise SatelliteBatchRecoveryError("recovery tranche queue IDs are not unique")
    if any(queue_id not in base["jobs"] or queue_id not in source["jobs"] for queue_id in queue_ids):
        raise SatelliteBatchRecoveryError(
            "recovery tranche is not selected by both base and source batches"
        )
    tiers = {job["priority"]["tier"] for job in selected_queue_jobs}
    if len(tiers) != 1 or not tiers.issubset(set(source_config.priority_tiers)):
        raise SatelliteBatchRecoveryError(
            "recovery tranche is not one source-selected priority tier"
        )

    selected_tasks: dict[str, dict[str, Any]] = {}
    event_times: list[str] = []
    largest_response = 0
    for job in selected_queue_jobs:
        queue_id = str(job["queue_id"])
        base_task = base["jobs"][queue_id]
        source_task = source["jobs"][queue_id]
        if base_task.get("state") != "pending" or base_task.get("attempts") != 0:
            raise SatelliteBatchRecoveryError(
                f"base task was not pristine pending at recovery boundary: {queue_id}"
            )
        base_final = _safe_directory(source_directory, base_task["output_directory"])
        # The path is relative to source_directory only to obtain its canonical shape;
        # source output existence is checked below from source_task.
        del base_final
        if source_task.get("state") != "completed":
            raise SatelliteBatchRecoveryError(
                f"recovery tranche task is not a completed catalog result: {queue_id}"
            )
        if (
            source_task.get("attempts") != 1
            or source_task.get("failures") != []
            or source_task.get("unavailability") is not None
        ):
            raise SatelliteBatchRecoveryError(
                f"recovery tranche task is not a clean first-attempt completion: {queue_id}"
            )
        final = _safe_directory(source_directory, source_task["output_directory"])
        try:
            result = _catalog_result(
                job,
                final,
                max_response_bytes=source_config.max_response_bytes,
            )
        except SatelliteBatchError as error:
            raise SatelliteBatchRecoveryError(
                f"selected source catalog is invalid for {queue_id}: {error}"
            ) from error
        if (
            source_task.get("artifacts") != result["artifacts"]
            or source_task.get("selected_ids") != result["selected_ids"]
            or source_task.get("catalog_retrieved_at") != result["retrieved_at"]
        ):
            raise SatelliteBatchRecoveryError(
                f"selected source task does not checkpoint its catalog: {queue_id}"
            )
        event = _event_timestamp(source_task)
        if event is None:
            raise SatelliteBatchRecoveryError(
                f"selected source task lacks a terminal timestamp: {queue_id}"
            )
        event_times.append(event)
        for name in ("baseline-response.json", "current-response.json"):
            largest_response = max(
                largest_response, int(result["artifacts"][name]["bytes"])
            )
        selected_tasks[queue_id] = json.loads(json.dumps(source_task))

    if event_times != sorted(event_times):
        raise SatelliteBatchRecoveryError(
            "selected task timestamps do not follow queue order"
        )
    first_event, last_event = event_times[0], event_times[-1]
    outside_terminals: list[tuple[str, int, str, str]] = []
    for queue_id, source_task in source["jobs"].items():
        if queue_id in queue_ids or source_task == base["jobs"][queue_id]:
            continue
        position = int(source_task["queue_position"])
        if position < position_start:
            raise SatelliteBatchRecoveryError(
                "source evidence changed a task before the requested recovery tranche"
            )
        event = _event_timestamp(source_task)
        if event is not None:
            outside_terminals.append(
                (event, position, queue_id, str(source_task["state"]))
            )
    earliest_outside = min(outside_terminals) if outside_terminals else None
    if earliest_outside is not None and earliest_outside[0] <= last_event:
        raise SatelliteBatchRecoveryError(
            "later source additions are not temporally distinguishable from the tranche"
        )
    return (
        selected_queue_jobs,
        queue_ids,
        selected_tasks,
        first_event,
        last_event,
        largest_response,
        (
            {
                "at": earliest_outside[0],
                "queue_position": earliest_outside[1],
                "queue_id": earliest_outside[2],
                "state": earliest_outside[3],
            }
            if earliest_outside is not None
            else None
        ),
    )


def _batch_expected_inventory(
    *,
    base_rows: Sequence[Mapping[str, Any]],
    batch_manifest_raw: bytes,
    selected_tasks: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    expected = {
        str(row["path"]): {"bytes": int(row["bytes"]), "sha256": str(row["sha256"])}
        for row in base_rows
        if row["path"] != BATCH_MANIFEST_FILENAME
    }
    expected[BATCH_MANIFEST_FILENAME] = _checkpoint(batch_manifest_raw)
    for task in selected_tasks.values():
        directory = str(task["output_directory"])
        for filename, checkpoint in task["artifacts"].items():
            expected[f"{directory}/{filename}"] = {
                "bytes": int(checkpoint["bytes"]),
                "sha256": str(checkpoint["sha256"]),
            }
    return expected


def _write_inventory(path: Path, rows: Sequence[Mapping[str, Any]]) -> bytes:
    raw = b"".join(_canonical_json_line(dict(row)) for row in rows)
    path.write_bytes(raw)
    return raw


def _copy_catalog(source: Path, destination: Path) -> None:
    files, directories = _regular_tree(source, "selected source catalog")
    if {path.name for path in files} != CATALOG_FILES or len(directories) != 1:
        raise SatelliteBatchRecoveryError(
            "selected source catalog does not have the exact three-file contract"
        )
    destination.parent.mkdir(parents=True, exist_ok=False)
    destination.mkdir()
    for path in files:
        shutil.copy2(path, destination / path.name)


def recover_satellite_batch(
    queue_directory: str | Path,
    base_directory: str | Path,
    source_evidence_directory: str | Path,
    output_directory: str | Path,
    *,
    artifact_id: str,
    base_artifact_id: str,
    source_evidence_artifact_id: str,
    position_start: int,
    position_end: int,
    recovered_at: str,
    incident: RecoveryIncident,
    source_manifest_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a sealed recovery artifact without reading the network.

    The source evidence is opened read-only.  The immutable base and every
    selected catalog are validated before any bytes are promoted to the output.
    """
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise SatelliteBatchRecoveryError("artifact_id must be non-empty")
    if not isinstance(base_artifact_id, str) or not base_artifact_id.strip():
        raise SatelliteBatchRecoveryError("base_artifact_id must be non-empty")
    if (
        not isinstance(source_evidence_artifact_id, str)
        or not source_evidence_artifact_id.strip()
    ):
        raise SatelliteBatchRecoveryError(
            "source_evidence_artifact_id must be non-empty"
        )
    recovered_at = _timestamp(recovered_at, "recovered_at")
    incident_document = incident.as_dict()
    if (
        incident_document["interrupted_checkpoint_observation"]["updated_at"]
        > recovered_at
    ):
        raise SatelliteBatchRecoveryError(
            "interrupted checkpoint observation follows recovered_at"
        )
    if not isinstance(source_manifest_pin, Mapping) or set(source_manifest_pin) != {
        "bytes",
        "sha256",
        "mtime_ns",
    }:
        raise SatelliteBatchRecoveryError("source manifest pin has an invalid schema")
    if (
        isinstance(source_manifest_pin["bytes"], bool)
        or not isinstance(source_manifest_pin["bytes"], int)
        or source_manifest_pin["bytes"] <= 0
        or not isinstance(source_manifest_pin["sha256"], str)
        or len(source_manifest_pin["sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in source_manifest_pin["sha256"]
        )
        or isinstance(source_manifest_pin["mtime_ns"], bool)
        or not isinstance(source_manifest_pin["mtime_ns"], int)
        or source_manifest_pin["mtime_ns"] <= 0
    ):
        raise SatelliteBatchRecoveryError("source manifest pin has invalid values")
    queue = Path(queue_directory).resolve()
    base = Path(base_directory).resolve()
    source = Path(source_evidence_directory).resolve()
    output, stage, output_parent, output_parent_identity = _output_paths(
        output_directory, (queue, base, source)
    )
    if artifact_id != output.name:
        raise SatelliteBatchRecoveryError(
            "artifact_id must equal the canonical recovery output directory name"
        )
    if base_artifact_id != base.name:
        raise SatelliteBatchRecoveryError(
            "base_artifact_id must equal the canonical base directory name"
        )
    if source_evidence_artifact_id != source.name:
        raise SatelliteBatchRecoveryError(
            "source_evidence_artifact_id must equal the canonical source directory name"
        )

    queue_manifest, jobs, lineage = _queue_context(queue)
    try:
        base_document = validate_satellite_batch(queue, base)
    except SatelliteBatchError as error:
        raise SatelliteBatchRecoveryError(f"base batch validation failed: {error}") from error
    if base_document.get("schema_version") != PRIOR_BATCH_SCHEMA_VERSION:
        raise SatelliteBatchRecoveryError(
            "recovery base must be the immutable schema-v2 checkpoint"
        )
    _assert_frozen(base, "recovery base")
    base_rows_before, base_inventory_before, base_directories = _inventory(
        base, "recovery base"
    )
    base_manifest_raw = (base / BATCH_MANIFEST_FILENAME).read_bytes()

    source_manifest_path = source / BATCH_MANIFEST_FILENAME
    if source_manifest_path.is_symlink() or not source_manifest_path.is_file():
        raise SatelliteBatchRecoveryError("source evidence manifest is not a regular file")
    source_stat = source_manifest_path.stat()
    source_snapshot_raw = source_manifest_path.read_bytes()
    if dict(source_manifest_pin) != {
        **_checkpoint(source_snapshot_raw),
        "mtime_ns": source_stat.st_mtime_ns,
    }:
        raise SatelliteBatchRecoveryError(
            "source evidence manifest does not match the post-guard pin"
        )
    source_document, source_config, source_selected_jobs = _validated_snapshot(
        source_snapshot_raw,
        lineage=lineage,
        jobs=jobs,
    )
    if source_document.get("schema_version") != BATCH_SCHEMA_VERSION:
        raise SatelliteBatchRecoveryError("source evidence is not a schema-v3 batch")
    if source_document.get("scope") != BATCH_SCOPE:
        raise SatelliteBatchRecoveryError("source evidence lost review-only scope")
    if source_document.get("state") != "incomplete":
        raise SatelliteBatchRecoveryError(
            "source evidence is not an unfinished overall batch"
        )
    migration = source_document.get("response_limit_migration")
    if (
        not isinstance(migration, dict)
        or migration.get("source_schema_version") != PRIOR_BATCH_SCHEMA_VERSION
        or migration.get("max_response_bytes") != DEFAULT_MAX_RESPONSE_BYTES
        or migration.get("historical_acquisition_bounded") is not False
    ):
        raise SatelliteBatchRecoveryError(
            "source evidence lacks the expected honest schema-v2 response-cap migration"
        )
    if source_document["queue_bundle"] != base_document["queue_bundle"]:
        raise SatelliteBatchRecoveryError("base and source queue lineage differ")
    if set(source_document["jobs"]) != set(base_document["jobs"]):
        raise SatelliteBatchRecoveryError("base and source task inventories differ")

    (
        selected_queue_jobs,
        queue_ids,
        selected_tasks,
        first_event,
        last_event,
        largest_response,
        earliest_outside,
    ) = _selected_tranche(
        jobs=jobs,
        base=base_document,
        source=source_document,
        source_directory=source,
        source_config=source_config,
        position_start=position_start,
        position_end=position_end,
    )
    if recovered_at < last_event:
        raise SatelliteBatchRecoveryError(
            "recovered_at precedes a selected terminal catalog result"
        )

    source_metadata_before = _tree_metadata(source, "source evidence")
    stage_identity: tuple[int, int] | None = None
    try:
        _assert_directory_identity(output_parent, output_parent_identity)
        stage.mkdir(parents=False)
        stage_stat = stage.stat(follow_symlinks=False)
        stage_identity = (stage_stat.st_dev, stage_stat.st_ino)
        batch_stage = stage / RECOVERED_BATCH_DIRECTORY
        shutil.copytree(base, batch_stage, copy_function=shutil.copy2)
        batch_stage.chmod(0o755)
        (batch_stage / "jobs").chmod(0o755)
        (batch_stage / BATCH_MANIFEST_FILENAME).chmod(0o644)

        base_config = BatchConfig(
            priority_tiers=base_document["configuration"]["priority_tiers"],
            user_agent=base_document["configuration"]["user_agent"],
            minimum_interval_seconds=base_document["configuration"][
                "minimum_interval_seconds"
            ],
            timeout_seconds=base_document["configuration"]["timeout_seconds"],
            catalog_retries=base_document["configuration"]["catalog_retries"],
            max_job_attempts=base_document["configuration"]["max_job_attempts"],
            max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES,
        )
        base_selected_jobs = {
            job["queue_id"]: job
            for job in jobs
            if job["priority"]["tier"] in base_config.priority_tiers
        }
        migrated = _migrate_prior_checkpoint(
            base_document,
            lineage=lineage,
            config=base_config,
            selected_jobs=base_selected_jobs,
            output=batch_stage,
            migrated_at=recovered_at,
        )
        migrated["last_run"] = None
        for job in selected_queue_jobs:
            queue_id = str(job["queue_id"])
            task = selected_tasks[queue_id]
            source_catalog = _safe_directory(source, task["output_directory"])
            destination_catalog = _safe_directory(batch_stage, task["output_directory"])
            _copy_catalog(source_catalog, destination_catalog)
            migrated["jobs"][queue_id] = json.loads(json.dumps(task))
        _update_document(migrated, recovered_at)
        try:
            _validate_checkpoint(
                migrated,
                lineage=lineage,
                config=base_config,
                selected_jobs=base_selected_jobs,
            )
        except SatelliteBatchError as error:
            raise SatelliteBatchRecoveryError(
                f"reconciled batch checkpoint is invalid: {error}"
            ) from error
        reconciled_manifest_raw = _canonical_json(migrated)
        (batch_stage / BATCH_MANIFEST_FILENAME).write_bytes(reconciled_manifest_raw)

        # Re-read only selected source records and bytes.  Other interrupted-source
        # state may have existed, but can neither enter nor invalidate this tranche.
        source_manifest_after = source_manifest_path.read_bytes()
        source_stat_after = source_manifest_path.stat()
        if (
            source_manifest_after != source_snapshot_raw
            or source_stat_after.st_mtime_ns != source_stat.st_mtime_ns
        ):
            raise SatelliteBatchRecoveryError(
                "source evidence manifest changed after the post-guard pin"
            )
        after_document, _, _ = _validated_snapshot(
            source_manifest_after,
            lineage=lineage,
            jobs=jobs,
        )
        for queue_id in queue_ids:
            if after_document["jobs"][queue_id] != source_document["jobs"][queue_id]:
                raise SatelliteBatchRecoveryError(
                    f"selected source task changed during recovery: {queue_id}"
                )
            task = selected_tasks[queue_id]
            source_catalog = _safe_directory(source, task["output_directory"])
            try:
                result = _catalog_result(
                    source_selected_jobs[queue_id],
                    source_catalog,
                    max_response_bytes=source_config.max_response_bytes,
                )
            except SatelliteBatchError as error:
                raise SatelliteBatchRecoveryError(
                    f"selected source catalog changed during recovery: {queue_id}: {error}"
                ) from error
            if result["artifacts"] != task["artifacts"]:
                raise SatelliteBatchRecoveryError(
                    f"selected source catalog changed during recovery: {queue_id}"
                )

        selected_queue_raw = b"".join(
            _canonical_json_line(dict(job)) for job in selected_queue_jobs
        )
        (stage / SELECTED_QUEUE_JOBS_FILENAME).write_bytes(selected_queue_raw)
        (stage / SOURCE_MANIFEST_SNAPSHOT_FILENAME).write_bytes(source_snapshot_raw)

        try:
            output_batch_document = validate_satellite_batch(queue, batch_stage)
        except SatelliteBatchError as error:
            raise SatelliteBatchRecoveryError(
                f"reconciled batch validation failed: {error}"
            ) from error
        if output_batch_document["last_run"] is not None:
            raise SatelliteBatchRecoveryError("reconciled batch claims a live last_run")
        if output_batch_document["summary"] != {
            **base_document["summary"],
            "jobs_completed": base_document["summary"]["jobs_completed"]
            + len(queue_ids),
            "jobs_pending": base_document["summary"]["jobs_pending"] - len(queue_ids),
        }:
            raise SatelliteBatchRecoveryError("reconciled batch delta is not exact")

        batch_rows, batch_inventory_raw, batch_directories = _inventory(
            batch_stage, "reconciled batch"
        )
        actual_batch = {
            str(row["path"]): {
                "bytes": int(row["bytes"]),
                "sha256": str(row["sha256"]),
            }
            for row in batch_rows
        }
        expected_batch = _batch_expected_inventory(
            base_rows=base_rows_before,
            batch_manifest_raw=reconciled_manifest_raw,
            selected_tasks=selected_tasks,
        )
        if actual_batch != expected_batch:
            raise SatelliteBatchRecoveryError(
                "reconciled batch file inventory contains a missing, changed, or leaked file"
            )
        expected_directories = set(base_directories)
        for task in selected_tasks.values():
            output_directory = Path(str(task["output_directory"]))
            expected_directories.add(output_directory.parent.as_posix())
            expected_directories.add(output_directory.as_posix())
        if batch_directories != expected_directories:
            raise SatelliteBatchRecoveryError(
                "reconciled batch directory inventory contains a missing or leaked directory"
            )

        payload_rows: list[dict[str, Any]] = []
        for row in batch_rows:
            payload_rows.append({**row, "path": f"{RECOVERED_BATCH_DIRECTORY}/{row['path']}"})
        for name in (SOURCE_MANIFEST_SNAPSHOT_FILENAME, SELECTED_QUEUE_JOBS_FILENAME):
            raw = (stage / name).read_bytes()
            payload_rows.append({"path": name, **_checkpoint(raw)})
        payload_rows.sort(key=lambda row: row["path"])
        inventory_file_raw = _write_inventory(
            stage / RECOVERY_INVENTORY_FILENAME, payload_rows
        )
        payload_canonical = b"".join(
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8")
            for row in payload_rows
        )
        source_changed_outside = sum(
            source_document["jobs"][queue_id] != base_document["jobs"][queue_id]
            for queue_id in source_document["jobs"]
            if queue_id not in set(queue_ids)
        )
        recovery_manifest = {
            "format": RECOVERY_FORMAT,
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "artifact_id": artifact_id.strip(),
            "state": "sealed_recovered_from_interrupted_evidence",
            "recovered_at": recovered_at,
            "scope": dict(RECOVERY_SCOPE),
            "queue_bundle": dict(lineage),
            "base": {
                "artifact_id": base_artifact_id.strip(),
                "batch_manifest": _checkpoint(base_manifest_raw),
                "schema_version": PRIOR_BATCH_SCHEMA_VERSION,
                "summary": dict(base_document["summary"]),
                "inventory": _inventory_summary(
                    base_rows_before, base_inventory_before
                ),
                "preserved_read_only": True,
            },
            "source_evidence": {
                "artifact_id": source_evidence_artifact_id.strip(),
                "source_directory_name": source.name,
                "status": "unaccepted_provenance_contaminated_not_promoted",
                "manifest_snapshot_file": SOURCE_MANIFEST_SNAPSHOT_FILENAME,
                "manifest_snapshot": _checkpoint(source_snapshot_raw),
                "snapshot_updated_at": source_document["updated_at"],
                "snapshot_summary": dict(source_document["summary"]),
                "snapshot_last_run": source_document["last_run"],
                "snapshot_last_run_finished": (
                    source_document["last_run"] is not None
                    and source_document["last_run"].get("finished_at") is not None
                ),
                "post_guard_manifest_pin": dict(source_manifest_pin),
                "response_limit_migration": migration,
                "run_history_limitation": RUN_HISTORY_LIMITATION,
                "terminal_task_time_basis": TERMINAL_TASK_TIME_BASIS,
                "incident": incident_document,
            },
            "selection": {
                "rule": "closed inclusive queue-position interval",
                "queue_position_start": position_start,
                "queue_position_end": position_end,
                "jobs": len(queue_ids),
                "priority_tier": selected_queue_jobs[0]["priority"]["tier"],
                "queue_ids": queue_ids,
                "selected_queue_jobs_file": SELECTED_QUEUE_JOBS_FILENAME,
                "selected_queue_jobs": _checkpoint(selected_queue_raw),
                "first_terminal_task_at": first_event,
                "last_terminal_task_at": last_event,
                "earliest_outside_delta_terminal": earliest_outside,
                "selected_terminals_strictly_predate_outside_delta": (
                    earliest_outside is None or last_event < earliest_outside["at"]
                ),
                "clean_first_attempt_completed": len(queue_ids),
                "unavailable_no_scene": 0,
                "largest_response_bytes": largest_response,
                "max_response_bytes": source_config.max_response_bytes,
            },
            "reconciliation": {
                "method": RECOVERY_METHOD,
                "live_catalog_requests": 0,
                "batch_last_run": None,
                "selected_task_delta": len(queue_ids),
                "selected_catalog_files_copied": len(queue_ids) * len(CATALOG_FILES),
                "source_changes_outside_selection_observed": source_changed_outside,
                "source_changes_outside_selection_copied": 0,
                "later_job_leakage": 0,
                "base_common_files_byte_preserved": True,
                "base_source_directory_mutated": False,
                "interrupted_source_directory_mutated": False,
                "selected_source_bytes_revalidated_after_copy": True,
            },
            "output": {
                "batch_directory": RECOVERED_BATCH_DIRECTORY,
                "batch_manifest": _checkpoint(reconciled_manifest_raw),
                "batch_schema_version": BATCH_SCHEMA_VERSION,
                "batch_summary": dict(output_batch_document["summary"]),
                "batch_inventory": _inventory_summary(
                    batch_rows, batch_inventory_raw
                ),
                "payload_inventory_file": RECOVERY_INVENTORY_FILENAME,
                "payload_inventory_file_checkpoint": _checkpoint(inventory_file_raw),
                "payload_inventory": _inventory_summary(
                    payload_rows, payload_canonical
                ),
                "files_mode": "0444",
                "directories_mode": "0555",
            },
        }
        manifest_raw = _canonical_json(recovery_manifest)
        (stage / RECOVERY_MANIFEST_FILENAME).write_bytes(manifest_raw)
        (stage / RECOVERY_MANIFEST_HASH_FILENAME).write_text(
            f"{_sha256(manifest_raw)}  {RECOVERY_MANIFEST_FILENAME}\n",
            encoding="ascii",
        )

        base_rows_after, base_inventory_after, _ = _inventory(base, "recovery base")
        if (
            base_inventory_after != base_inventory_before
            or base_rows_after != base_rows_before
            or (base / BATCH_MANIFEST_FILENAME).read_bytes() != base_manifest_raw
        ):
            raise SatelliteBatchRecoveryError("immutable base changed during recovery")
        _freeze(stage)
        _assert_frozen(stage, "recovery staging artifact")
        _assert_tree_unchanged(
            source, source_metadata_before, "source evidence"
        )
        _assert_directory_identity(output_parent, output_parent_identity)
        result = validate_recovered_satellite_batch(
            queue,
            base,
            stage,
            source_evidence_directory=source,
            _expected_artifact_id=output.name,
        )
        _assert_tree_unchanged(
            source, source_metadata_before, "source evidence"
        )
        _assert_directory_identity(output_parent, output_parent_identity)
        if output.exists() or output.is_symlink():
            raise SatelliteBatchRecoveryError(
                "recovery output appeared before exclusive promotion"
            )
        _promote_directory_exclusive(stage, output)
        return result
    except Exception as error:
        # Never alter either input.  A failed private stage has no evidentiary value.
        cleanup_error: SatelliteBatchRecoveryError | None = None
        try:
            _assert_directory_identity(output_parent, output_parent_identity)
        except SatelliteBatchRecoveryError as identity_error:
            cleanup_error = identity_error
        if cleanup_error is None and stage.exists() and not stage.is_symlink():
            current_stage = stage.stat(follow_symlinks=False)
            if stage_identity != (current_stage.st_dev, current_stage.st_ino):
                cleanup_error = SatelliteBatchRecoveryError(
                    "recovery staging identity changed; refusing cleanup"
                )
        if cleanup_error is None and stage.exists() and not stage.is_symlink():
            for parent, directory_names, file_names in os.walk(stage, topdown=False):
                for name in file_names:
                    (Path(parent) / name).chmod(0o600)
                for name in directory_names:
                    (Path(parent) / name).chmod(0o700)
            stage.chmod(0o700)
            shutil.rmtree(stage)
        try:
            _assert_tree_unchanged(
                source, source_metadata_before, "source evidence"
            )
        except SatelliteBatchRecoveryError as source_error:
            raise source_error from error
        if cleanup_error is not None:
            raise cleanup_error from error
        raise


def _parse_inventory(raw: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SatelliteBatchRecoveryError(
                f"recovery inventory line {line_number} is invalid JSON"
            ) from error
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "bytes", "sha256"}
            or not isinstance(row["path"], str)
            or not row["path"]
            or isinstance(row["bytes"], bool)
            or not isinstance(row["bytes"], int)
            or row["bytes"] < 0
            or not isinstance(row["sha256"], str)
            or len(row["sha256"]) != 64
        ):
            raise SatelliteBatchRecoveryError(
                f"recovery inventory line {line_number} has an invalid schema"
            )
        if _canonical_json_line(row).rstrip(b"\n") != line:
            raise SatelliteBatchRecoveryError(
                f"recovery inventory line {line_number} is not canonical"
            )
        rows.append(row)
    if [row["path"] for row in rows] != sorted({row["path"] for row in rows}):
        raise SatelliteBatchRecoveryError(
            "recovery inventory paths are duplicated or unordered"
        )
    return rows


def validate_recovered_satellite_batch(
    queue_directory: str | Path,
    base_directory: str | Path,
    output_directory: str | Path,
    *,
    source_evidence_directory: str | Path | None = None,
    _expected_artifact_id: str | None = None,
) -> dict[str, Any]:
    """Validate a sealed recovery artifact and reproduce its exact delta offline."""
    queue = Path(queue_directory).resolve()
    base = Path(base_directory).resolve()
    output = Path(output_directory)
    _assert_frozen(output, "recovered satellite artifact")
    expected_artifact_id = output.resolve().name
    if _expected_artifact_id is not None:
        if (
            not isinstance(_expected_artifact_id, str)
            or not _expected_artifact_id
            or _expected_artifact_id != _expected_artifact_id.strip()
            or output.resolve().name
            != f".{_expected_artifact_id}.recovery-staging"
        ):
            raise SatelliteBatchRecoveryError(
                "staging recovery artifact_id override is invalid"
            )
        expected_artifact_id = _expected_artifact_id
    root_files, root_directories = _regular_tree(output, "recovered satellite artifact")
    immediate_files = {path.name for path in root_files if path.parent == output}
    immediate_directories = {
        path.name for path in root_directories if path.parent == output
    }
    if immediate_files != RECOVERY_ROOT_FILES or immediate_directories != {
        RECOVERED_BATCH_DIRECTORY
    }:
        raise SatelliteBatchRecoveryError("recovery root file set changed")

    manifest, manifest_raw = _load_canonical_manifest(
        output / RECOVERY_MANIFEST_FILENAME, "recovery manifest"
    )
    expected_sidecar = (
        f"{_sha256(manifest_raw)}  {RECOVERY_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if (output / RECOVERY_MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise SatelliteBatchRecoveryError("recovery manifest sidecar changed")
    expected_top_keys = {
        "format",
        "schema_version",
        "artifact_id",
        "state",
        "recovered_at",
        "scope",
        "queue_bundle",
        "base",
        "source_evidence",
        "selection",
        "reconciliation",
        "output",
    }
    if set(manifest) != expected_top_keys:
        raise SatelliteBatchRecoveryError("recovery manifest schema changed")
    if (
        manifest.get("format") != RECOVERY_FORMAT
        or manifest.get("schema_version") != RECOVERY_SCHEMA_VERSION
        or manifest.get("state") != "sealed_recovered_from_interrupted_evidence"
        or manifest.get("scope") != RECOVERY_SCOPE
    ):
        raise SatelliteBatchRecoveryError("recovery manifest identity or scope changed")
    if (
        not isinstance(manifest.get("artifact_id"), str)
        or not manifest["artifact_id"].strip()
        or manifest["artifact_id"] != manifest["artifact_id"].strip()
        or manifest["artifact_id"] != expected_artifact_id
    ):
        raise SatelliteBatchRecoveryError("recovery artifact_id is invalid")
    recovered_at = _timestamp(
        manifest.get("recovered_at"), "recovery manifest recovered_at"
    )
    if recovered_at != manifest["recovered_at"]:
        raise SatelliteBatchRecoveryError("recovery recovered_at is not canonical UTC")

    queue_manifest, jobs, lineage = _queue_context(queue)
    del queue_manifest
    if manifest["queue_bundle"] != lineage:
        raise SatelliteBatchRecoveryError("recovery queue lineage changed")
    try:
        base_document = validate_satellite_batch(queue, base)
    except SatelliteBatchError as error:
        raise SatelliteBatchRecoveryError(f"base batch validation failed: {error}") from error
    if base_document.get("schema_version") != PRIOR_BATCH_SCHEMA_VERSION:
        raise SatelliteBatchRecoveryError("recovery base schema changed")
    _assert_frozen(base, "recovery base")
    base_rows, base_inventory_raw, base_directories = _inventory(base, "recovery base")
    base_manifest_raw = (base / BATCH_MANIFEST_FILENAME).read_bytes()
    base_record = manifest["base"]
    if (
        not isinstance(base_record, dict)
        or not isinstance(base_record.get("artifact_id"), str)
        or not base_record["artifact_id"].strip()
        or base_record["artifact_id"] != base_record["artifact_id"].strip()
        or base_record["artifact_id"] != base.name
    ):
        raise SatelliteBatchRecoveryError("recovery base artifact_id is invalid")
    if base_record != {
        "artifact_id": base_record["artifact_id"],
        "batch_manifest": _checkpoint(base_manifest_raw),
        "schema_version": PRIOR_BATCH_SCHEMA_VERSION,
        "summary": dict(base_document["summary"]),
        "inventory": _inventory_summary(base_rows, base_inventory_raw),
        "preserved_read_only": True,
    }:
        raise SatelliteBatchRecoveryError("recovery base provenance changed")

    source_snapshot_raw = (output / SOURCE_MANIFEST_SNAPSHOT_FILENAME).read_bytes()
    source_document, source_config, source_selected_jobs = _validated_snapshot(
        source_snapshot_raw,
        lineage=lineage,
        jobs=jobs,
    )
    if (
        source_document.get("schema_version") != BATCH_SCHEMA_VERSION
        or source_document.get("scope") != BATCH_SCOPE
        or source_document.get("state") != "incomplete"
    ):
        raise SatelliteBatchRecoveryError(
            "recovery source snapshot schema, scope, or state changed"
        )
    migration = source_document.get("response_limit_migration")
    if (
        not isinstance(migration, dict)
        or migration.get("source_schema_version") != PRIOR_BATCH_SCHEMA_VERSION
        or migration.get("max_response_bytes") != DEFAULT_MAX_RESPONSE_BYTES
        or migration.get("historical_acquisition_bounded") is not False
    ):
        raise SatelliteBatchRecoveryError(
            "recovery source response-limit migration changed"
        )
    source_evidence = manifest["source_evidence"]
    if not isinstance(source_evidence, dict):
        raise SatelliteBatchRecoveryError("recovery source evidence schema changed")
    source_artifact_id = source_evidence.get("artifact_id")
    source_directory_name = source_evidence.get("source_directory_name")
    if (
        not isinstance(source_artifact_id, str)
        or not source_artifact_id.strip()
        or source_artifact_id != source_artifact_id.strip()
        or not isinstance(source_directory_name, str)
        or not source_directory_name
        or source_directory_name != source_directory_name.strip()
        or source_directory_name in {".", ".."}
        or Path(source_directory_name).name != source_directory_name
        or source_artifact_id != source_directory_name
    ):
        raise SatelliteBatchRecoveryError(
            "recovery source evidence artifact_id is invalid"
        )
    snapshot_last_run_finished = (
        source_document.get("last_run") is not None
        and source_document["last_run"].get("finished_at") is not None
    )
    post_guard_pin = source_evidence.get("post_guard_manifest_pin")
    if (
        not isinstance(post_guard_pin, dict)
        or set(post_guard_pin) != {"bytes", "sha256", "mtime_ns"}
        or post_guard_pin.get("bytes") != len(source_snapshot_raw)
        or post_guard_pin.get("sha256") != _sha256(source_snapshot_raw)
        or isinstance(post_guard_pin.get("mtime_ns"), bool)
        or not isinstance(post_guard_pin.get("mtime_ns"), int)
        or post_guard_pin["mtime_ns"] <= 0
    ):
        raise SatelliteBatchRecoveryError("recovery post-guard manifest pin changed")
    incident = source_evidence.get("incident")
    if not isinstance(incident, dict):
        raise SatelliteBatchRecoveryError("recovery incident provenance changed")
    try:
        normalized_incident = RecoveryIncident(
            observed_writer_pids=incident.get("observed_writer_pids"),
            launchd_service_observations=incident.get(
                "launchd_service_observations"
            ),
            reported_guard_pid=incident.get("reported_guard_pid_at_task_dispatch"),
            handling=incident.get("handling"),
            interrupted_checkpoint_observation=incident.get(
                "interrupted_checkpoint_observation"
            ),
        ).as_dict()
    except (TypeError, SatelliteBatchRecoveryError) as error:
        raise SatelliteBatchRecoveryError(
            f"recovery incident provenance changed: {error}"
        ) from error
    if (
        normalized_incident["interrupted_checkpoint_observation"]["updated_at"]
        > recovered_at
    ):
        raise SatelliteBatchRecoveryError(
            "recovery incident checkpoint follows recovered_at"
        )
    expected_source_evidence = {
        "artifact_id": source_artifact_id,
        "source_directory_name": source_directory_name,
        "status": "unaccepted_provenance_contaminated_not_promoted",
        "manifest_snapshot_file": SOURCE_MANIFEST_SNAPSHOT_FILENAME,
        "manifest_snapshot": _checkpoint(source_snapshot_raw),
        "snapshot_updated_at": source_document["updated_at"],
        "snapshot_summary": dict(source_document["summary"]),
        "snapshot_last_run": source_document["last_run"],
        "snapshot_last_run_finished": snapshot_last_run_finished,
        "post_guard_manifest_pin": post_guard_pin,
        "response_limit_migration": migration,
        "run_history_limitation": RUN_HISTORY_LIMITATION,
        "terminal_task_time_basis": TERMINAL_TASK_TIME_BASIS,
        "incident": normalized_incident,
    }
    if source_evidence != expected_source_evidence:
        raise SatelliteBatchRecoveryError(
            "recovery source interruption provenance changed"
        )
    if source_evidence_directory is not None:
        current_source_directory = Path(source_evidence_directory).resolve()
        if current_source_directory.name != source_directory_name:
            raise SatelliteBatchRecoveryError(
                "external source directory name no longer matches provenance"
            )
        current_source_manifest = current_source_directory / BATCH_MANIFEST_FILENAME
        current_raw = current_source_manifest.read_bytes()
        current_stat = current_source_manifest.stat()
        if post_guard_pin != {
            **_checkpoint(current_raw),
            "mtime_ns": current_stat.st_mtime_ns,
        }:
            raise SatelliteBatchRecoveryError(
                "external source no longer matches the post-guard manifest pin"
            )

    selection = manifest["selection"]
    if not isinstance(selection, dict):
        raise SatelliteBatchRecoveryError("recovery selection schema changed")
    start = selection.get("queue_position_start")
    end = selection.get("queue_position_end")
    (
        selected_queue_jobs,
        queue_ids,
        selected_tasks,
        first_event,
        last_event,
        largest_response,
        earliest_outside,
    ) = _selected_tranche(
        jobs=jobs,
        base=base_document,
        source=source_document,
        source_directory=(
            Path(source_evidence_directory).resolve()
            if source_evidence_directory is not None
            else output / RECOVERED_BATCH_DIRECTORY
        ),
        source_config=source_config,
        position_start=start,
        position_end=end,
    )
    if recovered_at < last_event:
        raise SatelliteBatchRecoveryError(
            "recovery recovered_at precedes selected terminal evidence"
        )
    # When no external source is supplied, validate selected catalogs from the
    # self-contained recovered batch against the signed source task snapshot.
    if source_evidence_directory is None:
        for job in selected_queue_jobs:
            queue_id = str(job["queue_id"])
            task = selected_tasks[queue_id]
            result = _catalog_result(
                job,
                _safe_directory(
                    output / RECOVERED_BATCH_DIRECTORY, task["output_directory"]
                ),
                max_response_bytes=source_config.max_response_bytes,
            )
            if result["artifacts"] != task["artifacts"]:
                raise SatelliteBatchRecoveryError(
                    f"recovered selected catalog differs from snapshot: {queue_id}"
                )
    selected_queue_raw = b"".join(
        _canonical_json_line(dict(job)) for job in selected_queue_jobs
    )
    if (output / SELECTED_QUEUE_JOBS_FILENAME).read_bytes() != selected_queue_raw:
        raise SatelliteBatchRecoveryError("selected queue-job snapshot changed")
    expected_selection = {
        "rule": "closed inclusive queue-position interval",
        "queue_position_start": start,
        "queue_position_end": end,
        "jobs": len(queue_ids),
        "priority_tier": selected_queue_jobs[0]["priority"]["tier"],
        "queue_ids": queue_ids,
        "selected_queue_jobs_file": SELECTED_QUEUE_JOBS_FILENAME,
        "selected_queue_jobs": _checkpoint(selected_queue_raw),
        "first_terminal_task_at": first_event,
        "last_terminal_task_at": last_event,
        "earliest_outside_delta_terminal": earliest_outside,
        "selected_terminals_strictly_predate_outside_delta": (
            earliest_outside is None or last_event < earliest_outside["at"]
        ),
        "clean_first_attempt_completed": len(queue_ids),
        "unavailable_no_scene": 0,
        "largest_response_bytes": largest_response,
        "max_response_bytes": source_config.max_response_bytes,
    }
    if selection != expected_selection:
        raise SatelliteBatchRecoveryError("recovery selection provenance changed")

    batch = output / RECOVERED_BATCH_DIRECTORY
    try:
        batch_document = validate_satellite_batch(queue, batch)
    except SatelliteBatchError as error:
        raise SatelliteBatchRecoveryError(f"recovered batch is invalid: {error}") from error
    if batch_document.get("schema_version") != BATCH_SCHEMA_VERSION:
        raise SatelliteBatchRecoveryError("recovered batch schema changed")
    if batch_document.get("last_run") is not None:
        raise SatelliteBatchRecoveryError("recovered batch claims a live last_run")
    recovered_migration = batch_document.get("response_limit_migration")
    if (
        batch_document.get("updated_at") != recovered_at
        or not isinstance(recovered_migration, dict)
        or recovered_migration.get("migrated_at") != recovered_at
        or recovered_migration.get("enforced_for_subsequent_attempts_at_or_after")
        != recovered_at
    ):
        raise SatelliteBatchRecoveryError(
            "recovery recovered_at is not bound to the reconciled batch"
        )
    for queue_id, task in batch_document["jobs"].items():
        expected = selected_tasks[queue_id] if queue_id in selected_tasks else base_document["jobs"][queue_id]
        if task != expected:
            raise SatelliteBatchRecoveryError(
                f"recovered batch task delta leaked outside selection: {queue_id}"
            )
    expected_summary = dict(base_document["summary"])
    expected_summary["jobs_completed"] += len(queue_ids)
    expected_summary["jobs_pending"] -= len(queue_ids)
    if batch_document["summary"] != expected_summary:
        raise SatelliteBatchRecoveryError("recovered batch summary delta changed")

    batch_rows, batch_inventory_raw, batch_directories = _inventory(
        batch, "recovered batch"
    )
    batch_manifest_raw = (batch / BATCH_MANIFEST_FILENAME).read_bytes()
    expected_files = _batch_expected_inventory(
        base_rows=base_rows,
        batch_manifest_raw=batch_manifest_raw,
        selected_tasks=selected_tasks,
    )
    actual_files = {
        str(row["path"]): {
            "bytes": int(row["bytes"]),
            "sha256": str(row["sha256"]),
        }
        for row in batch_rows
    }
    if actual_files != expected_files:
        raise SatelliteBatchRecoveryError(
            "recovered batch contains a missing, changed, or later-job file"
        )
    expected_directories = set(base_directories)
    for task in selected_tasks.values():
        output_directory = Path(str(task["output_directory"]))
        expected_directories.add(output_directory.parent.as_posix())
        expected_directories.add(output_directory.as_posix())
    if batch_directories != expected_directories:
        raise SatelliteBatchRecoveryError(
            "recovered batch contains a missing or later-job directory"
        )

    payload_rows: list[dict[str, Any]] = [
        {**row, "path": f"{RECOVERED_BATCH_DIRECTORY}/{row['path']}"}
        for row in batch_rows
    ]
    for name in (SOURCE_MANIFEST_SNAPSHOT_FILENAME, SELECTED_QUEUE_JOBS_FILENAME):
        raw = (output / name).read_bytes()
        payload_rows.append({"path": name, **_checkpoint(raw)})
    payload_rows.sort(key=lambda row: row["path"])
    inventory_raw = (output / RECOVERY_INVENTORY_FILENAME).read_bytes()
    if _parse_inventory(inventory_raw) != payload_rows:
        raise SatelliteBatchRecoveryError("recovery payload inventory changed")
    payload_canonical = b"".join(
        f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8")
        for row in payload_rows
    )
    output_record = manifest["output"]
    if output_record != {
        "batch_directory": RECOVERED_BATCH_DIRECTORY,
        "batch_manifest": _checkpoint(batch_manifest_raw),
        "batch_schema_version": BATCH_SCHEMA_VERSION,
        "batch_summary": dict(batch_document["summary"]),
        "batch_inventory": _inventory_summary(batch_rows, batch_inventory_raw),
        "payload_inventory_file": RECOVERY_INVENTORY_FILENAME,
        "payload_inventory_file_checkpoint": _checkpoint(inventory_raw),
        "payload_inventory": _inventory_summary(payload_rows, payload_canonical),
        "files_mode": "0444",
        "directories_mode": "0555",
    }:
        raise SatelliteBatchRecoveryError("recovery output inventory changed")
    source_changed_outside = sum(
        source_document["jobs"][queue_id] != base_document["jobs"][queue_id]
        for queue_id in source_document["jobs"]
        if queue_id not in set(queue_ids)
    )
    expected_reconciliation = {
        "method": RECOVERY_METHOD,
        "live_catalog_requests": 0,
        "batch_last_run": None,
        "selected_task_delta": len(queue_ids),
        "selected_catalog_files_copied": len(queue_ids) * len(CATALOG_FILES),
        "source_changes_outside_selection_observed": source_changed_outside,
        "source_changes_outside_selection_copied": 0,
        "later_job_leakage": 0,
        "base_common_files_byte_preserved": True,
        "base_source_directory_mutated": False,
        "interrupted_source_directory_mutated": False,
        "selected_source_bytes_revalidated_after_copy": True,
    }
    if manifest["reconciliation"] != expected_reconciliation:
        raise SatelliteBatchRecoveryError("recovery reconciliation contract changed")
    return manifest
