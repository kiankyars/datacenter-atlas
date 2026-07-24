"""Explicit, fail-closed execution adapter for eleven audited v71 jobs.

All 98 active-construction jobs remain represented in the checkpoint.  Only
the immutable eleven-ID receipt is executable; the other 87 jobs stay pending.
Each selected job has one catalog attempt, reserves exactly two HTTP POSTs,
and is promoted from a private transaction with an atomic no-replace rename.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

from . import satellite_batch as carrier
from .open_seed_v56 import promote_noreplace
from .satellite_queue import (
    MANIFEST_FILENAME as QUEUE_MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME as QUEUE_MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    REVIEW_CONSTRAINTS,
)
from .satellite_queue_v71 import (
    ACTIVE_DISTINCT_AOI_COUNT,
    ACTIVE_ENTITY_COUNT,
    AUDITED_QUEUE_IDS,
    EXPECTED_AUDITED_POSITIONS,
    PUBLISHED_GENERATED_AT,
    PUBLISHED_MANIFEST_HASH_SHA256,
    PUBLISHED_MANIFEST_SHA256,
    QUEUE as V71_QUEUE,
    QUEUE_SHA256,
    validate_satellite_queue_v71,
)


class ExplicitSatelliteBatchError(ValueError):
    """Raised when the explicit selection or checkpoint contract is violated."""


BATCH_MANIFEST_FILENAME = carrier.BATCH_MANIFEST_FILENAME
SELECTION_RECEIPT_FILENAME = "selection-receipt.json"
SELECTION_RECEIPT_HASH_FILENAME = "selection-receipt.sha256"
CONTROL_FILES = frozenset(
    {
        BATCH_MANIFEST_FILENAME,
        SELECTION_RECEIPT_FILENAME,
        SELECTION_RECEIPT_HASH_FILENAME,
    }
)
SCHEMA_VERSION = 1
PIPELINE = "satellite_review_catalog_batch_explicit_v1"
RECEIPT_ID = "open-seed-v71-active-explicit-audited-11-v1"
CARRIER_SHA256 = "b57497568a5268637828a30cc43c19f457c0e89d0428ee3ac08e9ea01b54fbba"
SELECTED_JOB_COUNT = 11
UNSELECTED_PENDING_JOB_COUNT = 87
HTTP_ATTEMPTS_PER_JOB = 2
LIFETIME_HTTP_ATTEMPT_CAP = 22
MAX_JOB_ATTEMPTS = 1
CATALOG_RETRIES = 0
DEFAULT_MAX_JOBS = SELECTED_JOB_COUNT
DEFAULT_MAX_HTTP_ATTEMPTS = LIFETIME_HTTP_ATTEMPT_CAP
SCOPE = {
    **carrier.BATCH_SCOPE,
    "selection_mode": "explicit_audited_queue_ids",
    "represented_priority_tier": "active_construction",
    "unselected_jobs_remain_pending": True,
    "unexpected_output_adoption": False,
    "job_promotion": "atomic_no_replace",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _timestamp(value: str, field: str) -> str:
    try:
        return carrier._timestamp(value, field)
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExplicitSatelliteBatchError(f"{field} must be a positive integer")
    return value


def _carrier_checkpoint() -> None:
    path = Path(carrier.__file__ or "")
    if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != CARRIER_SHA256:
        raise ExplicitSatelliteBatchError("pinned satellite batch carrier changed")


@dataclass(frozen=True, slots=True)
class ExplicitBatchConfig:
    """Runtime settings around the fixed zero-retry, one-attempt policy."""

    user_agent: str = carrier.DEFAULT_USER_AGENT
    minimum_interval_seconds: float = carrier.DEFAULT_MINIMUM_INTERVAL_SECONDS
    timeout_seconds: float = 60.0
    max_response_bytes: int = carrier.DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        try:
            base = carrier.BatchConfig(
                priority_tiers=("active_construction",),
                user_agent=self.user_agent,
                minimum_interval_seconds=self.minimum_interval_seconds,
                timeout_seconds=self.timeout_seconds,
                catalog_retries=CATALOG_RETRIES,
                max_job_attempts=MAX_JOB_ATTEMPTS,
                max_response_bytes=self.max_response_bytes,
            )
        except carrier.SatelliteBatchError as error:
            raise ExplicitSatelliteBatchError(str(error)) from error
        object.__setattr__(self, "user_agent", base.user_agent)
        object.__setattr__(
            self, "minimum_interval_seconds", base.minimum_interval_seconds
        )
        object.__setattr__(self, "timeout_seconds", base.timeout_seconds)
        object.__setattr__(self, "max_response_bytes", base.max_response_bytes)

    def base_config(self) -> carrier.BatchConfig:
        return carrier.BatchConfig(
            priority_tiers=("active_construction",),
            user_agent=self.user_agent,
            minimum_interval_seconds=self.minimum_interval_seconds,
            timeout_seconds=self.timeout_seconds,
            catalog_retries=CATALOG_RETRIES,
            max_job_attempts=MAX_JOB_ATTEMPTS,
            max_response_bytes=self.max_response_bytes,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "catalog_only",
            "represented_priority_tier": "active_construction",
            "user_agent": self.user_agent,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "catalog_retries": CATALOG_RETRIES,
            "max_job_attempts": MAX_JOB_ATTEMPTS,
            "max_response_bytes": self.max_response_bytes,
            "http_attempts_reserved_per_job": HTTP_ATTEMPTS_PER_JOB,
            "lifetime_http_attempt_cap": LIFETIME_HTTP_ATTEMPT_CAP,
        }


def _read_jobs(queue: Path) -> list[dict[str, Any]]:
    try:
        return carrier._read_jobs(queue)
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _queue_state(queue_directory: str | Path) -> tuple[
    Path,
    Mapping[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    _carrier_checkpoint()
    queue_input = Path(queue_directory)
    if queue_input.is_symlink() or not queue_input.is_dir():
        raise ExplicitSatelliteBatchError("v71 queue must be a regular directory")
    queue = queue_input.resolve()
    try:
        manifest = validate_satellite_queue_v71(
            queue, require_final_root_ctime=queue == V71_QUEUE.resolve()
        )
    except ValueError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error
    jobs = _read_jobs(queue)
    if any(job.get("review_constraints") != REVIEW_CONSTRAINTS for job in jobs):
        raise ExplicitSatelliteBatchError("v71 queue lost its review-only constraints")
    active = [job for job in jobs if job["priority"]["tier"] == "active_construction"]
    if len(active) != ACTIVE_ENTITY_COUNT:
        raise ExplicitSatelliteBatchError("v71 active job inventory changed")
    if (
        manifest["generated_at"] != PUBLISHED_GENERATED_AT
        or manifest["artifacts"][QUEUE_FILENAME]["sha256"] != QUEUE_SHA256
        or _sha256((queue / QUEUE_MANIFEST_FILENAME).read_bytes())
        != PUBLISHED_MANIFEST_SHA256
        or _sha256((queue / QUEUE_MANIFEST_HASH_FILENAME).read_bytes())
        != PUBLISHED_MANIFEST_HASH_SHA256
    ):
        raise ExplicitSatelliteBatchError("published v71 queue lineage changed")
    return queue, manifest, jobs, active


def _queue_lineage(queue: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return carrier._queue_lineage(queue, manifest)
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _receipt(
    queue: Path,
    manifest: Mapping[str, Any],
    active: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_id = {job["queue_id"]: job for job in active}
    represented_ids = [job["queue_id"] for job in active]
    if (
        len(by_id) != ACTIVE_ENTITY_COUNT
        or any(queue_id not in by_id for queue_id in AUDITED_QUEUE_IDS)
        or tuple(by_id[queue_id]["queue_position"] for queue_id in AUDITED_QUEUE_IDS)
        != EXPECTED_AUDITED_POSITIONS
        or list(AUDITED_QUEUE_IDS)
        != sorted(AUDITED_QUEUE_IDS, key=lambda queue_id: by_id[queue_id]["queue_position"])
    ):
        raise ExplicitSatelliteBatchError("explicit audited queue selection changed")
    selected_jobs = [
        {
            "selection_position": position,
            "queue_id": queue_id,
            "queue_position": by_id[queue_id]["queue_position"],
            "entity_id": by_id[queue_id]["entity"]["id"],
            "stable_key": by_id[queue_id]["entity"]["stable_key"],
            "aoi_bbox_wgs84": by_id[queue_id]["location"]["aoi_bbox_wgs84"],
        }
        for position, queue_id in enumerate(AUDITED_QUEUE_IDS, start=1)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": RECEIPT_ID,
        "pipeline": PIPELINE,
        "queue_bundle": _queue_lineage(queue, manifest),
        "representation": {
            "priority_tier": "active_construction",
            "represented_jobs": ACTIVE_ENTITY_COUNT,
            "distinct_aois": ACTIVE_DISTINCT_AOI_COUNT,
            "represented_queue_ids": represented_ids,
            "represented_queue_ids_sha256": _sha256(
                ("\n".join(represented_ids) + "\n").encode("ascii")
            ),
        },
        "selection": {
            "basis": "explicit_independent_audit_v1",
            "selected_jobs": selected_jobs,
            "selected_queue_ids": list(AUDITED_QUEUE_IDS),
            "selected_jobs_count": SELECTED_JOB_COUNT,
            "unselected_pending_jobs": UNSELECTED_PENDING_JOB_COUNT,
        },
        "execution_policy": {
            "catalog_retries": CATALOG_RETRIES,
            "max_job_attempts": MAX_JOB_ATTEMPTS,
            "http_attempts_reserved_per_job": HTTP_ATTEMPTS_PER_JOB,
            "lifetime_http_attempt_cap": LIFETIME_HTTP_ATTEMPT_CAP,
            "unexpected_output_adoption": False,
            "job_promotion": "atomic_no_replace",
        },
    }


def _receipt_payloads(receipt: Mapping[str, Any]) -> dict[str, bytes]:
    raw = _canonical_json(receipt)
    sidecar = f"{_sha256(raw)}  {SELECTION_RECEIPT_FILENAME}\n".encode("ascii")
    return {
        SELECTION_RECEIPT_FILENAME: raw,
        SELECTION_RECEIPT_HASH_FILENAME: sidecar,
    }


def _write_exclusive_file(path: Path, raw: bytes, mode: int) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ExplicitSatelliteBatchError(f"control-file collision: {path}") from error
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    path.chmod(mode)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_receipt(output: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    payloads = _receipt_payloads(receipt)
    for name in (SELECTION_RECEIPT_FILENAME, SELECTION_RECEIPT_HASH_FILENAME):
        _write_exclusive_file(output / name, payloads[name], 0o444)
    _fsync_directory(output)
    return {
        "file": SELECTION_RECEIPT_FILENAME,
        "bytes": len(payloads[SELECTION_RECEIPT_FILENAME]),
        "sha256": _sha256(payloads[SELECTION_RECEIPT_FILENAME]),
        "sidecar": SELECTION_RECEIPT_HASH_FILENAME,
        "sidecar_sha256": _sha256(payloads[SELECTION_RECEIPT_HASH_FILENAME]),
    }


def _validate_receipt(
    output: Path,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = _receipt_payloads(expected)
    for name, raw in payloads.items():
        path = output / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise ExplicitSatelliteBatchError(f"immutable selection receipt changed: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise ExplicitSatelliteBatchError(f"selection receipt is not frozen: {name}")
    return {
        "file": SELECTION_RECEIPT_FILENAME,
        "bytes": len(payloads[SELECTION_RECEIPT_FILENAME]),
        "sha256": _sha256(payloads[SELECTION_RECEIPT_FILENAME]),
        "sidecar": SELECTION_RECEIPT_HASH_FILENAME,
        "sidecar_sha256": _sha256(payloads[SELECTION_RECEIPT_HASH_FILENAME]),
    }


def _task_template(
    job: Mapping[str, Any], *, selection_position: int | None
) -> dict[str, Any]:
    return {
        "queue_position": job["queue_position"],
        "entity_id": job["entity"]["id"],
        "priority_rank": job["priority"]["rank"],
        "priority_tier": job["priority"]["tier"],
        "output_directory": job["catalog_job"]["output_directory"],
        "selected_for_execution": selection_position is not None,
        "selection_position": selection_position,
        "state": "pending",
        "attempts": 0,
        "failures": [],
        "completed_at": None,
        "catalog_retrieved_at": None,
        "selected_ids": None,
        "artifacts": None,
        "unavailability": None,
    }


def _summary(document: Mapping[str, Any]) -> dict[str, int]:
    tasks = document["jobs"]
    selected = [task for task in tasks.values() if task["selected_for_execution"]]
    states = ("completed", "failed", "pending", carrier.UNAVAILABLE_NO_SCENE)
    all_counts = {state: sum(task["state"] == state for task in tasks.values()) for state in states}
    selected_counts = {state: sum(task["state"] == state for task in selected) for state in states}
    return {
        "jobs_represented": len(tasks),
        "jobs_selected_for_execution": len(selected),
        "jobs_not_selected": len(tasks) - len(selected),
        "jobs_completed": all_counts["completed"],
        "jobs_failed": all_counts["failed"],
        "jobs_pending": all_counts["pending"],
        "jobs_unavailable_no_scene": all_counts[carrier.UNAVAILABLE_NO_SCENE],
        "selected_jobs_completed": selected_counts["completed"],
        "selected_jobs_failed": selected_counts["failed"],
        "selected_jobs_pending": selected_counts["pending"],
        "selected_jobs_unavailable_no_scene": selected_counts[
            carrier.UNAVAILABLE_NO_SCENE
        ],
    }


def _update_document(document: dict[str, Any], updated_at: str) -> None:
    document["updated_at"] = updated_at
    document["summary"] = _summary(document)
    selected_terminal = (
        document["summary"]["selected_jobs_completed"]
        + document["summary"]["selected_jobs_failed"]
        + document["summary"]["selected_jobs_unavailable_no_scene"]
    )
    document["state"] = (
        "selection_complete"
        if selected_terminal == SELECTED_JOB_COUNT
        else "selection_incomplete"
    )
    reserved = sum(task["attempts"] for task in document["jobs"].values()) * 2
    document["lifetime_budget"] = {
        "http_attempt_cap": LIFETIME_HTTP_ATTEMPT_CAP,
        "http_attempts_reserved": reserved,
        "http_attempts_remaining": LIFETIME_HTTP_ATTEMPT_CAP - reserved,
    }


def _manifest_raw(document: Mapping[str, Any]) -> bytes:
    return _canonical_json(document)


def _write_manifest(output: Path, document: dict[str, Any], updated_at: str) -> None:
    _update_document(document, updated_at)
    path = output / BATCH_MANIFEST_FILENAME
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ExplicitSatelliteBatchError("explicit batch manifest path is invalid")
    temporary = output / f".{BATCH_MANIFEST_FILENAME}.explicit-v1.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ExplicitSatelliteBatchError("stale explicit batch checkpoint exists")
    _write_exclusive_file(temporary, _manifest_raw(document), 0o600)
    os.replace(temporary, path)
    _fsync_directory(output)


def _new_document(
    *,
    lineage: Mapping[str, Any],
    receipt_checkpoint: Mapping[str, Any],
    config: ExplicitBatchConfig,
    active: Sequence[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    selection_positions = {
        queue_id: position
        for position, queue_id in enumerate(AUDITED_QUEUE_IDS, start=1)
    }
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "pipeline": PIPELINE,
        "state": "selection_incomplete",
        "created_at": created_at,
        "updated_at": created_at,
        "queue_bundle": dict(lineage),
        "selection_receipt": dict(receipt_checkpoint),
        "configuration": config.as_dict(),
        "scope": dict(SCOPE),
        "jobs": {
            job["queue_id"]: _task_template(
                job,
                selection_position=selection_positions.get(job["queue_id"]),
            )
            for job in active
        },
        "summary": {},
        "lifetime_budget": {},
        "last_run": None,
    }
    _update_document(document, created_at)
    return document


def _config_from_document(value: Any) -> ExplicitBatchConfig:
    if not isinstance(value, Mapping) or set(value) != set(
        ExplicitBatchConfig().as_dict()
    ):
        raise ExplicitSatelliteBatchError("explicit batch configuration schema changed")
    if (
        value.get("mode") != "catalog_only"
        or value.get("represented_priority_tier") != "active_construction"
        or value.get("catalog_retries") != CATALOG_RETRIES
        or value.get("max_job_attempts") != MAX_JOB_ATTEMPTS
        or value.get("http_attempts_reserved_per_job") != HTTP_ATTEMPTS_PER_JOB
        or value.get("lifetime_http_attempt_cap") != LIFETIME_HTTP_ATTEMPT_CAP
    ):
        raise ExplicitSatelliteBatchError("fixed explicit execution policy changed")
    try:
        config = ExplicitBatchConfig(
            user_agent=value.get("user_agent"),
            minimum_interval_seconds=value.get("minimum_interval_seconds"),
            timeout_seconds=value.get("timeout_seconds"),
            max_response_bytes=value.get("max_response_bytes"),
        )
    except ExplicitSatelliteBatchError:
        raise
    if config.as_dict() != dict(value):
        raise ExplicitSatelliteBatchError("explicit batch configuration is not canonical")
    return config


def _expected_jobs(
    active: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, int]]:
    selected_positions = {
        queue_id: position
        for position, queue_id in enumerate(AUDITED_QUEUE_IDS, start=1)
    }
    return (
        {job["queue_id"]: job for job in active},
        selected_positions,
    )


def _validate_failure(
    failure: Any, *, queue_id: str, attempts: int
) -> int:
    if not isinstance(failure, Mapping) or set(failure) != {"attempt", "at", "error"}:
        raise ExplicitSatelliteBatchError(f"{queue_id} failure schema changed")
    attempt = _positive_integer(failure.get("attempt"), f"{queue_id} failure attempt")
    if attempt > attempts:
        raise ExplicitSatelliteBatchError(f"{queue_id} failure exceeds attempts")
    _timestamp(failure.get("at"), f"{queue_id} failure timestamp")
    if not isinstance(failure.get("error"), str) or not failure["error"]:
        raise ExplicitSatelliteBatchError(f"{queue_id} failure error is invalid")
    return attempt


def _validate_document(
    document: Any,
    *,
    lineage: Mapping[str, Any],
    receipt_checkpoint: Mapping[str, Any],
    config: ExplicitBatchConfig,
    active: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "pipeline",
        "state",
        "created_at",
        "updated_at",
        "queue_bundle",
        "selection_receipt",
        "configuration",
        "scope",
        "jobs",
        "summary",
        "lifetime_budget",
        "last_run",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ExplicitSatelliteBatchError("explicit batch manifest schema changed")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("pipeline") != PIPELINE
        or document.get("queue_bundle") != dict(lineage)
        or document.get("selection_receipt") != dict(receipt_checkpoint)
        or document.get("configuration") != config.as_dict()
        or document.get("scope") != SCOPE
    ):
        raise ExplicitSatelliteBatchError("explicit batch identity or lineage changed")
    _timestamp(document.get("created_at"), "explicit batch created_at")
    _timestamp(document.get("updated_at"), "explicit batch updated_at")
    expected_jobs, selected_positions = _expected_jobs(active)
    tasks = document.get("jobs")
    if not isinstance(tasks, dict) or set(tasks) != set(expected_jobs):
        raise ExplicitSatelliteBatchError("explicit batch represented job inventory changed")
    task_keys = set(_task_template(active[0], selection_position=None))
    for queue_id, task in tasks.items():
        if not isinstance(task, dict) or set(task) != task_keys:
            raise ExplicitSatelliteBatchError(f"task schema changed: {queue_id}")
        expected = _task_template(
            expected_jobs[queue_id], selection_position=selected_positions.get(queue_id)
        )
        immutable = {
            "queue_position",
            "entity_id",
            "priority_rank",
            "priority_tier",
            "output_directory",
            "selected_for_execution",
            "selection_position",
        }
        if any(task.get(field) != expected[field] for field in immutable):
            raise ExplicitSatelliteBatchError(f"task identity changed: {queue_id}")
        state = task.get("state")
        if state not in {
            "pending",
            "failed",
            "completed",
            carrier.UNAVAILABLE_NO_SCENE,
        }:
            raise ExplicitSatelliteBatchError(f"task state is invalid: {queue_id}")
        attempts = task.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 1:
            raise ExplicitSatelliteBatchError(f"task attempts are invalid: {queue_id}")
        failures = task.get("failures")
        if not isinstance(failures, list) or len(failures) > attempts:
            raise ExplicitSatelliteBatchError(f"task failures are invalid: {queue_id}")
        failure_attempts = [
            _validate_failure(failure, queue_id=queue_id, attempts=attempts)
            for failure in failures
        ]
        if failure_attempts != sorted(set(failure_attempts)):
            raise ExplicitSatelliteBatchError(f"task failures are unordered: {queue_id}")
        if not task["selected_for_execution"] and (
            attempts != 0 or state != "pending" or failures
        ):
            raise ExplicitSatelliteBatchError(
                f"unselected task left pending-zero state: {queue_id}"
            )
        if state == "completed":
            if attempts != 1:
                raise ExplicitSatelliteBatchError(f"completed task attempts differ: {queue_id}")
            _timestamp(task.get("completed_at"), f"{queue_id} completed_at")
            _timestamp(
                task.get("catalog_retrieved_at"), f"{queue_id} catalog_retrieved_at"
            )
            if not isinstance(task.get("selected_ids"), dict) or not isinstance(
                task.get("artifacts"), dict
            ):
                raise ExplicitSatelliteBatchError(f"completed task provenance absent: {queue_id}")
            if task.get("unavailability") is not None:
                raise ExplicitSatelliteBatchError(f"completed task unavailable: {queue_id}")
        elif any(
            task.get(field) is not None
            for field in (
                "completed_at",
                "catalog_retrieved_at",
                "selected_ids",
                "artifacts",
            )
        ):
            raise ExplicitSatelliteBatchError(f"non-completed task has provenance: {queue_id}")
        if state == "failed" and failure_attempts != [1]:
            raise ExplicitSatelliteBatchError(f"failed task lacks final failure: {queue_id}")
        if state == carrier.UNAVAILABLE_NO_SCENE:
            if failure_attempts != [1]:
                raise ExplicitSatelliteBatchError(
                    f"unavailable task lacks final failure: {queue_id}"
                )
            try:
                expected_unavailable = carrier._no_scene_unavailability(
                    failures[-1]["error"], expected_jobs[queue_id], failures[-1]["at"]
                )
            except carrier.SatelliteBatchError as error:
                raise ExplicitSatelliteBatchError(str(error)) from error
            if task.get("unavailability") != expected_unavailable:
                raise ExplicitSatelliteBatchError(
                    f"unavailable outcome changed: {queue_id}"
                )
        elif task.get("unavailability") is not None:
            raise ExplicitSatelliteBatchError(f"unexpected unavailability: {queue_id}")
    expected_summary = _summary(document)
    if document.get("summary") != expected_summary:
        raise ExplicitSatelliteBatchError("explicit batch summary changed")
    selected_terminal = (
        expected_summary["selected_jobs_completed"]
        + expected_summary["selected_jobs_failed"]
        + expected_summary["selected_jobs_unavailable_no_scene"]
    )
    expected_state = (
        "selection_complete"
        if selected_terminal == SELECTED_JOB_COUNT
        else "selection_incomplete"
    )
    if document.get("state") != expected_state:
        raise ExplicitSatelliteBatchError("explicit selection state changed")
    reserved = sum(task["attempts"] for task in tasks.values()) * HTTP_ATTEMPTS_PER_JOB
    expected_lifetime = {
        "http_attempt_cap": LIFETIME_HTTP_ATTEMPT_CAP,
        "http_attempts_reserved": reserved,
        "http_attempts_remaining": LIFETIME_HTTP_ATTEMPT_CAP - reserved,
    }
    if reserved > LIFETIME_HTTP_ATTEMPT_CAP or document.get("lifetime_budget") != expected_lifetime:
        raise ExplicitSatelliteBatchError("explicit lifetime HTTP budget changed")
    _validate_last_run(document.get("last_run"), reserved=reserved)
    return document


def _validate_last_run(value: Any, *, reserved: int) -> None:
    if value is None:
        return
    keys = {
        "started_at",
        "finished_at",
        "max_jobs",
        "max_http_attempts",
        "job_attempts",
        "http_attempts_reserved",
        "lifetime_http_attempts_reserved",
        "jobs_completed",
        "jobs_failed",
        "jobs_unavailable_no_scene",
        "budget_exhausted",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ExplicitSatelliteBatchError("explicit last_run schema changed")
    _timestamp(value.get("started_at"), "explicit last_run started_at")
    if value.get("finished_at") is not None:
        _timestamp(value.get("finished_at"), "explicit last_run finished_at")
    for field in (
        "max_jobs",
        "max_http_attempts",
        "job_attempts",
        "http_attempts_reserved",
        "lifetime_http_attempts_reserved",
        "jobs_completed",
        "jobs_failed",
        "jobs_unavailable_no_scene",
    ):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise ExplicitSatelliteBatchError(f"explicit last_run {field} is invalid")
    if (
        value["max_jobs"] <= 0
        or value["max_http_attempts"] <= 0
        or value["job_attempts"] > value["max_jobs"]
        or value["http_attempts_reserved"] > value["max_http_attempts"]
        or value["http_attempts_reserved"]
        != value["job_attempts"] * HTTP_ATTEMPTS_PER_JOB
        or value["lifetime_http_attempts_reserved"] != reserved
        or value["lifetime_http_attempts_reserved"] > LIFETIME_HTTP_ATTEMPT_CAP
        or not isinstance(value.get("budget_exhausted"), bool)
    ):
        raise ExplicitSatelliteBatchError("explicit last_run budget changed")
    if value["finished_at"] is not None and (
        value["jobs_completed"]
        + value["jobs_failed"]
        + value["jobs_unavailable_no_scene"]
        != value["job_attempts"]
    ):
        raise ExplicitSatelliteBatchError("explicit last_run outcomes do not reconcile")


def _safe_directory(output: Path, relative: str) -> Path:
    try:
        return carrier._safe_directory(output, relative)
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _validate_directory_chain(output: Path, directory: Path) -> None:
    output_resolved = output.resolve()
    try:
        relative = directory.relative_to(output)
    except ValueError as error:
        raise ExplicitSatelliteBatchError("catalog parent escapes explicit output") from error
    current = output
    if output.is_symlink() or not output.is_dir():
        raise ExplicitSatelliteBatchError("explicit output root changed type")
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ExplicitSatelliteBatchError(
                f"catalog parent is not a regular directory: {current}"
            )
        resolved = current.resolve()
        if resolved != output_resolved and output_resolved not in resolved.parents:
            raise ExplicitSatelliteBatchError("catalog parent escapes explicit output")


def _catalog_result(
    job: Mapping[str, Any], directory: Path, config: ExplicitBatchConfig
) -> dict[str, Any]:
    try:
        return carrier._catalog_result(
            job, directory, max_response_bytes=config.max_response_bytes
        )
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _terminal_artifacts(
    document: Mapping[str, Any],
    *,
    jobs: Mapping[str, Mapping[str, Any]],
    output: Path,
    config: ExplicitBatchConfig,
) -> None:
    allowed: set[Path] = {
        output / BATCH_MANIFEST_FILENAME,
        output / SELECTION_RECEIPT_FILENAME,
        output / SELECTION_RECEIPT_HASH_FILENAME,
    }
    for queue_id, task in document["jobs"].items():
        final = _safe_directory(output, task["output_directory"])
        transaction_pattern = f".{final.name}.explicit-v1-stage-*"
        if final.parent.exists():
            _validate_directory_chain(output, final.parent)
            if any(final.parent.glob(transaction_pattern)):
                raise ExplicitSatelliteBatchError(
                    f"unexpected private transaction exists for {queue_id}"
                )
        if task["state"] == "completed":
            result = _catalog_result(jobs[queue_id], final, config)
            if (
                task["artifacts"] != result["artifacts"]
                or task["selected_ids"] != result["selected_ids"]
                or task["catalog_retrieved_at"] != result["retrieved_at"]
            ):
                raise ExplicitSatelliteBatchError(
                    f"completed catalog output changed for {queue_id}"
                )
            for path in (final, *final.parents):
                if path == output:
                    break
                allowed.add(path)
            allowed.update(final.iterdir())
        elif final.exists() or final.is_symlink():
            raise ExplicitSatelliteBatchError(
                f"unexpected catalog output; adoption prohibited for {queue_id}"
            )
    for path in output.rglob("*"):
        if path not in allowed:
            raise ExplicitSatelliteBatchError(f"unexpected explicit batch artifact: {path}")


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitSatelliteBatchError("explicit batch manifest is not a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExplicitSatelliteBatchError("explicit batch manifest is invalid JSON") from error
    if not isinstance(document, dict) or raw != _manifest_raw(document):
        raise ExplicitSatelliteBatchError("explicit batch manifest is not canonical JSON")
    return document


def validate_explicit_satellite_batch_v1(
    queue_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ExplicitBatchConfig | None = None,
) -> dict[str, Any]:
    """Validate the receipt, all 98 tasks, budget, and terminal outputs offline."""

    queue, manifest, _jobs, active = _queue_state(queue_directory)
    receipt = _receipt(queue, manifest, active)
    output_input = Path(output_directory)
    if output_input.is_symlink() or not output_input.is_dir():
        raise ExplicitSatelliteBatchError("explicit batch output is not a regular directory")
    output = output_input.resolve()
    receipt_checkpoint = _validate_receipt(output, receipt)
    document = _read_manifest(output / BATCH_MANIFEST_FILENAME)
    saved_config = _config_from_document(document.get("configuration"))
    if config is not None and config != saved_config:
        raise ExplicitSatelliteBatchError("saved explicit configuration differs")
    jobs_by_id = {job["queue_id"]: job for job in active}
    result = _validate_document(
        document,
        lineage=_queue_lineage(queue, manifest),
        receipt_checkpoint=receipt_checkpoint,
        config=saved_config,
        active=active,
    )
    _terminal_artifacts(
        result,
        jobs=jobs_by_id,
        output=output,
        config=saved_config,
    )
    return result


def _ensure_output(output_directory: str | Path, queue: Path) -> Path:
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output == queue or queue in output.parents:
        raise ExplicitSatelliteBatchError("explicit output must be separate from queue")
    if output.is_symlink():
        raise ExplicitSatelliteBatchError("explicit output may not be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ExplicitSatelliteBatchError("explicit output is not a regular directory")
    return output.resolve()


def _initialize_or_resume(
    output: Path,
    *,
    queue: Path,
    manifest: Mapping[str, Any],
    active: Sequence[Mapping[str, Any]],
    config: ExplicitBatchConfig,
    now: str,
) -> dict[str, Any]:
    receipt = _receipt(queue, manifest, active)
    checkpoint = output / BATCH_MANIFEST_FILENAME
    if checkpoint.exists() or checkpoint.is_symlink():
        receipt_checkpoint = _validate_receipt(output, receipt)
        document = _read_manifest(checkpoint)
        return _validate_document(
            document,
            lineage=_queue_lineage(queue, manifest),
            receipt_checkpoint=receipt_checkpoint,
            config=config,
            active=active,
        )
    if any(output.iterdir()):
        raise ExplicitSatelliteBatchError(
            "explicit output contains artifacts without a checkpoint"
        )
    receipt_checkpoint = _write_receipt(output, receipt)
    document = _new_document(
        lineage=_queue_lineage(queue, manifest),
        receipt_checkpoint=receipt_checkpoint,
        config=config,
        active=active,
        created_at=now,
    )
    _write_manifest(output, document, now)
    return document


def _transaction(output: Path, final: Path) -> tuple[Path, tuple[int, int]]:
    final.parent.mkdir(parents=True, exist_ok=True)
    _validate_directory_chain(output, final.parent)
    if final.exists() or final.is_symlink():
        raise ExplicitSatelliteBatchError(f"catalog final path collision: {final}")
    transaction = Path(
        tempfile.mkdtemp(
            prefix=f".{final.name}.explicit-v1-stage-", dir=final.parent
        )
    )
    metadata = transaction.stat(follow_symlinks=False)
    return transaction, (metadata.st_dev, metadata.st_ino)


def _discard_transaction(
    transaction: Path, identity: tuple[int, int]
) -> None:
    try:
        metadata = transaction.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise ExplicitSatelliteBatchError("refusing substituted job transaction cleanup")
    paths = sorted(transaction.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    if any(path.is_symlink() for path in paths):
        raise ExplicitSatelliteBatchError("refusing symlink-contaminated job cleanup")
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            path.chmod(0o600)
            path.unlink()
        elif stat.S_ISDIR(metadata.st_mode):
            path.chmod(0o700)
            path.rmdir()
        else:
            raise ExplicitSatelliteBatchError("refusing non-regular job cleanup")
    transaction.chmod(0o700)
    transaction.rmdir()


def _prune_empty_parents(path: Path, output: Path) -> None:
    current = path
    while current != output:
        if current.is_symlink() or not current.is_dir():
            raise ExplicitSatelliteBatchError("catalog parent changed during cleanup")
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _command(
    job: Mapping[str, Any],
    *,
    stage: Path,
    config: ExplicitBatchConfig,
) -> list[str]:
    try:
        return carrier._command(
            job,
            stage=stage,
            config=config.base_config(),
            package_root=Path(carrier.__file__).resolve().parents[1],
        )
    except carrier.SatelliteBatchError as error:
        raise ExplicitSatelliteBatchError(str(error)) from error


def _completed_task(
    task: dict[str, Any], result: Mapping[str, Any], completed_at: str
) -> None:
    task.update(
        {
            "state": "completed",
            "completed_at": completed_at,
            "catalog_retrieved_at": result["retrieved_at"],
            "selected_ids": result["selected_ids"],
            "artifacts": result["artifacts"],
            "unavailability": None,
        }
    )


def execute_explicit_satellite_batch_v1(
    queue_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ExplicitBatchConfig = ExplicitBatchConfig(),
    max_jobs: int = DEFAULT_MAX_JOBS,
    max_http_attempts: int = DEFAULT_MAX_HTTP_ATTEMPTS,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = carrier._utc_now,
) -> dict[str, Any]:
    """Attempt only the immutable eleven-ID selection under a lifetime cap."""

    if not isinstance(config, ExplicitBatchConfig):
        raise ExplicitSatelliteBatchError("config must be ExplicitBatchConfig")
    max_jobs = _positive_integer(max_jobs, "max_jobs")
    max_http_attempts = _positive_integer(max_http_attempts, "max_http_attempts")
    if max_jobs > SELECTED_JOB_COUNT:
        raise ExplicitSatelliteBatchError("max_jobs exceeds the eleven-job selection")
    if max_http_attempts > LIFETIME_HTTP_ATTEMPT_CAP:
        raise ExplicitSatelliteBatchError("max_http_attempts exceeds lifetime cap 22")

    queue, queue_manifest, _all_jobs, active = _queue_state(queue_directory)
    jobs_by_id = {job["queue_id"]: job for job in active}
    output = _ensure_output(output_directory, queue)
    now = _timestamp(timestamp(), "explicit batch run started_at")
    document = _initialize_or_resume(
        output,
        queue=queue,
        manifest=queue_manifest,
        active=active,
        config=config,
        now=now,
    )

    # Validate every extant terminal output and reject all unbound artifacts
    # before a command is eligible to run.
    _terminal_artifacts(
        document,
        jobs=jobs_by_id,
        output=output,
        config=config,
    )
    for queue_id in AUDITED_QUEUE_IDS:
        task = document["jobs"][queue_id]
        if task["state"] == "pending" and task["attempts"] == 1:
            task["state"] = "failed"
            task["failures"].append(
                {
                    "attempt": 1,
                    "at": now,
                    "error": "interrupted before the explicit attempt was checkpointed",
                }
            )
            _write_manifest(output, document, now)

    lifetime_reserved = sum(
        task["attempts"] for task in document["jobs"].values()
    ) * HTTP_ATTEMPTS_PER_JOB
    run = {
        "started_at": now,
        "finished_at": None,
        "max_jobs": max_jobs,
        "max_http_attempts": max_http_attempts,
        "job_attempts": 0,
        "http_attempts_reserved": 0,
        "lifetime_http_attempts_reserved": lifetime_reserved,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "jobs_unavailable_no_scene": 0,
        "budget_exhausted": False,
    }
    document["last_run"] = run
    _write_manifest(output, document, now)
    invoked = False

    for queue_id in AUDITED_QUEUE_IDS:
        task = document["jobs"][queue_id]
        if task["state"] != "pending" or task["attempts"] >= MAX_JOB_ATTEMPTS:
            continue
        if (
            run["job_attempts"] >= max_jobs
            or run["http_attempts_reserved"] + HTTP_ATTEMPTS_PER_JOB
            > max_http_attempts
            or run["lifetime_http_attempts_reserved"] + HTTP_ATTEMPTS_PER_JOB
            > LIFETIME_HTTP_ATTEMPT_CAP
        ):
            run["budget_exhausted"] = True
            break
        if invoked:
            sleep(config.minimum_interval_seconds)
        invoked = True
        job = jobs_by_id[queue_id]
        final = _safe_directory(output, task["output_directory"])
        if final.exists() or final.is_symlink():
            raise ExplicitSatelliteBatchError(
                f"unexpected catalog output; adoption prohibited for {queue_id}"
            )
        transaction, transaction_identity = _transaction(output, final)
        stage = transaction / "catalog"
        task["attempts"] = 1
        run["job_attempts"] += 1
        run["http_attempts_reserved"] += HTTP_ATTEMPTS_PER_JOB
        run["lifetime_http_attempts_reserved"] += HTTP_ATTEMPTS_PER_JOB
        attempt_at = _timestamp(timestamp(), f"{queue_id} attempt timestamp")
        _write_manifest(output, document, attempt_at)
        command = _command(job, stage=stage, config=config)
        failure: str | None = None
        no_scene_stderr = ""
        promoted = False
        try:
            completed = command_runner(
                command,
                cwd=Path(carrier.__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                stderr = completed.stderr if isinstance(completed.stderr, str) else ""
                stdout = completed.stdout if isinstance(completed.stdout, str) else ""
                no_scene_stderr = stderr
                detail = (stderr or stdout).strip()
                failure = f"catalog command exited {completed.returncode}"
                if detail:
                    failure += ": " + detail[-2_000:]
            else:
                result = _catalog_result(job, stage, config)
                if final.exists() or final.is_symlink():
                    raise ExplicitSatelliteBatchError(
                        f"late catalog final collision for {queue_id}"
                    )
                try:
                    promote_noreplace(stage, final)
                except SystemExit as error:
                    raise ExplicitSatelliteBatchError(str(error)) from error
                promoted = True
                transaction.rmdir()
                completion_at = _timestamp(
                    timestamp(), f"{queue_id} completion timestamp"
                )
                _completed_task(task, result, completion_at)
                run["jobs_completed"] += 1
        except ExplicitSatelliteBatchError:
            raise
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
        finally:
            if not promoted:
                try:
                    _discard_transaction(transaction, transaction_identity)
                    _prune_empty_parents(final.parent, output)
                except Exception as cleanup_error:
                    if failure is None:
                        raise
                    failure += f"; cleanup failed closed: {cleanup_error}"
        if failure is not None:
            failure_at = _timestamp(timestamp(), f"{queue_id} failure timestamp")
            task["failures"].append(
                {"attempt": 1, "at": failure_at, "error": failure}
            )
            try:
                unavailable = carrier._no_scene_unavailability(
                    no_scene_stderr, job, failure_at
                )
            except carrier.SatelliteBatchError as error:
                raise ExplicitSatelliteBatchError(str(error)) from error
            if unavailable is None:
                task["state"] = "failed"
                task["unavailability"] = None
                run["jobs_failed"] += 1
            else:
                task["state"] = carrier.UNAVAILABLE_NO_SCENE
                task["unavailability"] = unavailable
                run["jobs_unavailable_no_scene"] += 1
        checkpoint_at = _timestamp(timestamp(), f"{queue_id} checkpoint timestamp")
        _write_manifest(output, document, checkpoint_at)

    finished_at = _timestamp(timestamp(), "explicit batch run finished_at")
    run["finished_at"] = finished_at
    _write_manifest(output, document, finished_at)
    return validate_explicit_satellite_batch_v1(
        queue, output, config=config
    )


__all__ = [
    "BATCH_MANIFEST_FILENAME",
    "CATALOG_RETRIES",
    "DEFAULT_MAX_HTTP_ATTEMPTS",
    "DEFAULT_MAX_JOBS",
    "ExplicitBatchConfig",
    "ExplicitSatelliteBatchError",
    "HTTP_ATTEMPTS_PER_JOB",
    "LIFETIME_HTTP_ATTEMPT_CAP",
    "MAX_JOB_ATTEMPTS",
    "PIPELINE",
    "RECEIPT_ID",
    "SCHEMA_VERSION",
    "SELECTED_JOB_COUNT",
    "SELECTION_RECEIPT_FILENAME",
    "SELECTION_RECEIPT_HASH_FILENAME",
    "SCOPE",
    "UNSELECTED_PENDING_JOB_COUNT",
    "execute_explicit_satellite_batch_v1",
    "validate_explicit_satellite_batch_v1",
]
