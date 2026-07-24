"""Resumable, fail-closed execution of satellite catalog review jobs.

The executor consumes a verified satellite-review queue and invokes the
existing ``scripts/catalog_satellite.py`` command sequentially.  Its outputs
remain review-only catalog evidence: this module never writes to the atlas or
promotes imagery to an identity, lifecycle, operating-status, or power claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .satellite_catalog import (
    OUTPUT_LABELS,
    SCOPE_NOTE,
    CatalogQuery,
    Provider,
    build_pair_manifest,
    manifest_json,
)
from .satellite_queue import (
    MANIFEST_FILENAME as QUEUE_MANIFEST_FILENAME,
    PRIORITY_POLICY,
    QUEUE_FILENAME,
    REVIEW_CONSTRAINTS,
    validate_queue_bundle,
)


BATCH_MANIFEST_FILENAME = "batch-manifest.json"
BATCH_SCHEMA_VERSION = 3
PRIOR_BATCH_SCHEMA_VERSION = 2
LEGACY_BATCH_SCHEMA_VERSION = 1
BATCH_PIPELINE = "satellite_review_catalog_batch"
DEFAULT_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research satellite review queue; "
    "+https://github.com/kiankyars/semiconductors)"
)
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
CATALOG_FILES = frozenset(
    {"baseline-response.json", "current-response.json", "manifest.json"}
)
BATCH_SCOPE = {
    "mode": "catalog_only",
    "atlas_mutation": False,
    "change_analysis_executed": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_power_inference": False,
    "review_required": True,
}
UNAVAILABLE_NO_SCENE = "unavailable_no_scene"
_NO_SCENE_ERROR = re.compile(
    r"datacenter_atlas\.satellite_catalog\.CatalogValidationError: "
    r"(?P<reason>no scene falls within the "
    r"(?P<window>baseline|current) temporal window)"
)


class SatelliteBatchError(ValueError):
    """Raised when a queue, checkpoint, command, or output fails validation."""


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SatelliteBatchError(f"{field} must be a non-empty RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteBatchError(f"{field} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteBatchError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SatelliteBatchError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SatelliteBatchError(f"{field} must be a non-negative integer")
    return value


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SatelliteBatchError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise SatelliteBatchError(f"{field} must be finite and positive")
    return result


def _number_argument(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _user_agent(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SatelliteBatchError("user_agent must be non-empty text")
    result = value.strip()
    if len(result) > 512 or any(character in result for character in "\r\n"):
        raise SatelliteBatchError(
            "user_agent must be at most 512 characters with no line breaks"
        )
    return result


_TIER_RANK = {str(item["tier"]): int(item["rank"]) for item in PRIORITY_POLICY}


@dataclass(frozen=True, slots=True)
class BatchConfig:
    """Pinned execution settings; per-run budgets are intentionally separate."""

    priority_tiers: Sequence[str] | None = None
    user_agent: str = DEFAULT_USER_AGENT
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS
    timeout_seconds: float = 60.0
    catalog_retries: int = 0
    max_job_attempts: int = 3
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        if self.priority_tiers is None:
            tiers = tuple(sorted(_TIER_RANK, key=_TIER_RANK.__getitem__))
        elif isinstance(self.priority_tiers, (str, bytes)):
            raise SatelliteBatchError("priority_tiers must be a sequence of tier names")
        else:
            tiers = tuple(self.priority_tiers)
        if not tiers:
            raise SatelliteBatchError("priority_tiers must select at least one tier")
        if any(not isinstance(tier, str) for tier in tiers):
            raise SatelliteBatchError("priority_tiers must contain only tier names")
        if len(set(tiers)) != len(tiers) or any(tier not in _TIER_RANK for tier in tiers):
            allowed = ", ".join(sorted(_TIER_RANK, key=_TIER_RANK.__getitem__))
            raise SatelliteBatchError(
                f"priority_tiers must be unique values from: {allowed}"
            )
        tiers = tuple(sorted(tiers, key=_TIER_RANK.__getitem__))
        interval = _positive_number(
            self.minimum_interval_seconds, "minimum_interval_seconds"
        )
        timeout = _positive_number(self.timeout_seconds, "timeout_seconds")
        if (
            isinstance(self.catalog_retries, bool)
            or not isinstance(self.catalog_retries, int)
            or not 0 <= self.catalog_retries <= 10
        ):
            raise SatelliteBatchError("catalog_retries must be an integer from 0 to 10")
        attempts = _positive_integer(self.max_job_attempts, "max_job_attempts")
        max_response_bytes = _positive_integer(
            self.max_response_bytes, "max_response_bytes"
        )
        object.__setattr__(self, "priority_tiers", tiers)
        object.__setattr__(self, "user_agent", _user_agent(self.user_agent))
        object.__setattr__(self, "minimum_interval_seconds", interval)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "max_job_attempts", attempts)
        object.__setattr__(self, "max_response_bytes", max_response_bytes)

    @property
    def maximum_http_attempts_per_job(self) -> int:
        return 2 * (self.catalog_retries + 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "catalog_only",
            "priority_tiers": list(self.priority_tiers),
            "user_agent": self.user_agent,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "catalog_retries": self.catalog_retries,
            "max_job_attempts": self.max_job_attempts,
            "max_response_bytes": self.max_response_bytes,
            "maximum_http_attempts_per_job": self.maximum_http_attempts_per_job,
        }


def _configuration_for_schema(
    config: BatchConfig, schema_version: int
) -> dict[str, Any]:
    configuration = config.as_dict()
    if schema_version in {
        LEGACY_BATCH_SCHEMA_VERSION,
        PRIOR_BATCH_SCHEMA_VERSION,
    }:
        configuration.pop("max_response_bytes")
    elif schema_version != BATCH_SCHEMA_VERSION:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    return configuration


def _validate_response_limit_migration(
    value: Any, config: BatchConfig
) -> None:
    if value is None:
        return
    expected_keys = {
        "source_schema_version",
        "migrated_at",
        "max_response_bytes",
        "enforced_for_subsequent_attempts_at_or_after",
        "historical_acquisition_bounded",
        "historical_terminal_jobs_validated",
        "historical_completed_jobs",
        "historical_response_files",
        "largest_historical_response_bytes",
        "historical_response_files_validated_within_cap",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise SatelliteBatchError("batch response-limit migration record is invalid")
    if value.get("source_schema_version") not in {
        LEGACY_BATCH_SCHEMA_VERSION,
        PRIOR_BATCH_SCHEMA_VERSION,
    }:
        raise SatelliteBatchError(
            "batch response-limit migration source schema is invalid"
        )
    migrated_at = _timestamp(
        value.get("migrated_at"), "batch response-limit migration migrated_at"
    )
    enforced_at = _timestamp(
        value.get("enforced_for_subsequent_attempts_at_or_after"),
        "batch response-limit migration enforcement timestamp",
    )
    if migrated_at != enforced_at:
        raise SatelliteBatchError(
            "batch response-limit migration timestamps do not match"
        )
    if value.get("max_response_bytes") != config.max_response_bytes:
        raise SatelliteBatchError(
            "batch response-limit migration cap does not match configuration"
        )
    if value.get("historical_acquisition_bounded") is not False:
        raise SatelliteBatchError(
            "batch response-limit migration must not claim bounded historical acquisition"
        )
    terminal_jobs = _nonnegative_integer(
        value.get("historical_terminal_jobs_validated"),
        "batch response-limit migration historical terminal jobs",
    )
    completed_jobs = _nonnegative_integer(
        value.get("historical_completed_jobs"),
        "batch response-limit migration historical completed jobs",
    )
    response_files = _nonnegative_integer(
        value.get("historical_response_files"),
        "batch response-limit migration historical response files",
    )
    largest = _nonnegative_integer(
        value.get("largest_historical_response_bytes"),
        "batch response-limit migration largest historical response",
    )
    if terminal_jobs < completed_jobs or response_files != completed_jobs * 2:
        raise SatelliteBatchError(
            "batch response-limit migration historical counts do not reconcile"
        )
    if (response_files == 0 and largest != 0) or (
        response_files > 0 and largest == 0
    ):
        raise SatelliteBatchError(
            "batch response-limit migration largest response is inconsistent"
        )
    if largest > config.max_response_bytes:
        raise SatelliteBatchError(
            "batch response-limit migration historical response exceeds cap"
        )
    if value.get("historical_response_files_validated_within_cap") is not True:
        raise SatelliteBatchError(
            "batch response-limit migration lacks historical size validation"
        )


def _read_jobs(queue_directory: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        (queue_directory / QUEUE_FILENAME).read_bytes().splitlines(), start=1
    ):
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise SatelliteBatchError(
                f"validated queue line {line_number} is no longer valid JSON"
            ) from error
        if not isinstance(value, dict):
            raise SatelliteBatchError(f"validated queue line {line_number} is not an object")
        jobs.append(value)
    return jobs


def _queue_lineage(queue_directory: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    manifest_raw = (queue_directory / QUEUE_MANIFEST_FILENAME).read_bytes()
    queue_artifact = manifest["artifacts"][QUEUE_FILENAME]
    return {
        "pipeline": manifest["pipeline"],
        "generated_at": manifest["generated_at"],
        "manifest_bytes": len(manifest_raw),
        "manifest_sha256": _sha256(manifest_raw),
        "queue_file": QUEUE_FILENAME,
        "queue_bytes": queue_artifact["bytes"],
        "queue_sha256": queue_artifact["sha256"],
        "queue_jobs": queue_artifact["records"],
    }


def _task_template(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "queue_position": job["queue_position"],
        "entity_id": job["entity"]["id"],
        "priority_rank": job["priority"]["rank"],
        "priority_tier": job["priority"]["tier"],
        "output_directory": job["catalog_job"]["output_directory"],
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
    counts = {
        state: sum(task.get("state") == state for task in tasks.values())
        for state in ("completed", "failed", "pending", UNAVAILABLE_NO_SCENE)
    }
    return {
        "jobs_selected": len(tasks),
        "jobs_completed": counts["completed"],
        "jobs_failed": counts["failed"],
        "jobs_pending": counts["pending"],
        "jobs_unavailable_no_scene": counts[UNAVAILABLE_NO_SCENE],
    }


def _update_document(document: dict[str, Any], updated_at: str) -> None:
    document["updated_at"] = updated_at
    document["summary"] = _summary(document)
    document["state"] = (
        "completed"
        if (
            document["summary"]["jobs_completed"]
            + document["summary"]["jobs_unavailable_no_scene"]
            == document["summary"]["jobs_selected"]
        )
        else "incomplete"
    )


def _manifest_raw(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _write_manifest(output: Path, document: dict[str, Any], updated_at: str) -> None:
    _update_document(document, updated_at)
    path = output / BATCH_MANIFEST_FILENAME
    if path.is_symlink():
        raise SatelliteBatchError("batch manifest may not be a symlink")
    temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteBatchError("stale batch manifest checkpoint exists")
    with temporary.open("wb") as destination:
        destination.write(_manifest_raw(document))
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def _new_document(
    *,
    lineage: Mapping[str, Any],
    config: BatchConfig,
    jobs: Sequence[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    selected = [job for job in jobs if job["priority"]["tier"] in config.priority_tiers]
    return {
        "schema_version": BATCH_SCHEMA_VERSION,
        "pipeline": BATCH_PIPELINE,
        "state": "incomplete",
        "created_at": created_at,
        "updated_at": created_at,
        "queue_bundle": dict(lineage),
        "configuration": config.as_dict(),
        "response_limit_migration": None,
        "scope": dict(BATCH_SCOPE),
        "jobs": {job["queue_id"]: _task_template(job) for job in selected},
        "summary": {
            "jobs_selected": len(selected),
            "jobs_completed": 0,
            "jobs_failed": 0,
            "jobs_pending": len(selected),
            "jobs_unavailable_no_scene": 0,
        },
        "last_run": None,
    }


def _validate_checkpoint(
    document: Any,
    *,
    lineage: Mapping[str, Any],
    config: BatchConfig,
    selected_jobs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise SatelliteBatchError("batch manifest must be a JSON object")
    schema_version = document.get("schema_version")
    if schema_version not in {
        PRIOR_BATCH_SCHEMA_VERSION,
        BATCH_SCHEMA_VERSION,
    }:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    expected_keys = {
        "schema_version",
        "pipeline",
        "state",
        "created_at",
        "updated_at",
        "queue_bundle",
        "configuration",
        "scope",
        "jobs",
        "summary",
        "last_run",
    }
    if schema_version == BATCH_SCHEMA_VERSION:
        expected_keys.add("response_limit_migration")
    if set(document) != expected_keys:
        raise SatelliteBatchError("batch manifest has unexpected fields")
    if document.get("pipeline") != BATCH_PIPELINE:
        raise SatelliteBatchError("batch manifest has an unexpected pipeline")
    if document.get("queue_bundle") != dict(lineage):
        raise SatelliteBatchError("batch manifest queue lineage does not match")
    if document.get("configuration") != _configuration_for_schema(
        config, schema_version
    ):
        raise SatelliteBatchError("batch manifest configuration does not match")
    if schema_version == BATCH_SCHEMA_VERSION:
        _validate_response_limit_migration(
            document.get("response_limit_migration"), config
        )
    if document.get("scope") != BATCH_SCOPE:
        raise SatelliteBatchError("batch manifest review-only scope does not match")
    _timestamp(document.get("created_at"), "batch manifest created_at")
    _timestamp(document.get("updated_at"), "batch manifest updated_at")
    tasks = document.get("jobs")
    if not isinstance(tasks, dict) or set(tasks) != set(selected_jobs):
        raise SatelliteBatchError("batch manifest task inventory does not match selection")
    expected_task_keys = set(_task_template(next(iter(selected_jobs.values())))) if tasks else set()
    for queue_id, task in tasks.items():
        if not isinstance(task, dict) or set(task) != expected_task_keys:
            raise SatelliteBatchError(f"batch task {queue_id} has unexpected fields")
        expected = _task_template(selected_jobs[queue_id])
        for key in (
            "queue_position",
            "entity_id",
            "priority_rank",
            "priority_tier",
            "output_directory",
        ):
            if task.get(key) != expected[key]:
                raise SatelliteBatchError(f"batch task {queue_id} changed {key}")
        if task.get("state") not in {
            "pending",
            "failed",
            "completed",
            UNAVAILABLE_NO_SCENE,
        }:
            raise SatelliteBatchError(f"batch task {queue_id} has an invalid state")
        attempts = _nonnegative_integer(task.get("attempts"), f"{queue_id} attempts")
        if attempts > config.max_job_attempts:
            raise SatelliteBatchError(f"batch task {queue_id} exceeded its attempt cap")
        failures = task.get("failures")
        if not isinstance(failures, list) or len(failures) > attempts:
            raise SatelliteBatchError(f"batch task {queue_id} failures are invalid")
        failure_attempts: list[int] = []
        for failure in failures:
            if not isinstance(failure, dict) or set(failure) != {"attempt", "at", "error"}:
                raise SatelliteBatchError(f"batch task {queue_id} failure is invalid")
            failure_attempt = _positive_integer(
                failure.get("attempt"), f"{queue_id} failure attempt"
            )
            if not 1 <= failure_attempt <= attempts:
                raise SatelliteBatchError(f"batch task {queue_id} failure attempt is invalid")
            failure_attempts.append(failure_attempt)
            _timestamp(failure.get("at"), f"{queue_id} failure timestamp")
            if not isinstance(failure.get("error"), str) or not failure["error"]:
                raise SatelliteBatchError(f"batch task {queue_id} failure error is invalid")
        if failure_attempts != sorted(set(failure_attempts)):
            raise SatelliteBatchError(f"batch task {queue_id} failures are not unique and ordered")
        if task["state"] == "completed":
            if attempts == 0:
                raise SatelliteBatchError(f"completed task {queue_id} has no attempt")
            _timestamp(task.get("completed_at"), f"{queue_id} completed_at")
            _timestamp(task.get("catalog_retrieved_at"), f"{queue_id} catalog_retrieved_at")
            if not isinstance(task.get("selected_ids"), dict) or not isinstance(
                task.get("artifacts"), dict
            ):
                raise SatelliteBatchError(f"completed task {queue_id} lacks output provenance")
            if task.get("unavailability") is not None:
                raise SatelliteBatchError(
                    f"completed task {queue_id} claims an unavailable outcome"
                )
        elif any(
            task.get(field) is not None
            for field in ("completed_at", "catalog_retrieved_at", "selected_ids", "artifacts")
        ):
            raise SatelliteBatchError(f"incomplete task {queue_id} claims output provenance")
        if task["state"] == "failed" and (
            not failure_attempts or failure_attempts[-1] != attempts
        ):
            raise SatelliteBatchError(f"failed task {queue_id} lacks its final failure")
        if task["state"] == UNAVAILABLE_NO_SCENE:
            if not failure_attempts or failure_attempts[-1] != attempts:
                raise SatelliteBatchError(
                    f"unavailable task {queue_id} lacks its final catalog outcome"
                )
            expected_unavailability = _no_scene_unavailability(
                failures[-1]["error"],
                selected_jobs[queue_id],
                failures[-1]["at"],
            )
            if task.get("unavailability") != expected_unavailability:
                raise SatelliteBatchError(
                    f"unavailable task {queue_id} outcome does not match its raw failure"
                )
        elif task.get("unavailability") is not None:
            raise SatelliteBatchError(
                f"batch task {queue_id} has unexpected unavailability metadata"
            )
    if document.get("summary") != _summary(document):
        raise SatelliteBatchError("batch manifest summary does not match task states")
    expected_state = (
        "completed"
        if (
            document["summary"]["jobs_completed"]
            + document["summary"]["jobs_unavailable_no_scene"]
            == document["summary"]["jobs_selected"]
        )
        else "incomplete"
    )
    if document.get("state") != expected_state:
        raise SatelliteBatchError("batch manifest state does not match task states")
    last_run = document.get("last_run")
    if last_run is not None:
        expected_run_keys = {
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
        if not isinstance(last_run, dict) or set(last_run) != expected_run_keys:
            raise SatelliteBatchError("batch manifest last_run is invalid")
        _timestamp(last_run.get("started_at"), "batch last_run started_at")
        if last_run.get("finished_at") is not None:
            _timestamp(last_run["finished_at"], "batch last_run finished_at")
        for field in (
            "job_attempts",
            "http_attempts_reserved",
            "jobs_completed",
            "jobs_failed",
            "jobs_unavailable_no_scene",
        ):
            _nonnegative_integer(last_run.get(field), f"batch last_run {field}")
        for field in ("max_jobs", "max_http_attempts"):
            _positive_integer(last_run.get(field), f"batch last_run {field}")
        if not isinstance(last_run.get("budget_exhausted"), bool):
            raise SatelliteBatchError("batch last_run budget_exhausted must be boolean")
        if last_run["job_attempts"] > last_run["max_jobs"]:
            raise SatelliteBatchError("batch last_run exceeded its job cap")
        if last_run["http_attempts_reserved"] > last_run["max_http_attempts"]:
            raise SatelliteBatchError("batch last_run exceeded its HTTP-attempt cap")
        if last_run["http_attempts_reserved"] != (
            last_run["job_attempts"] * config.maximum_http_attempts_per_job
        ):
            raise SatelliteBatchError("batch last_run HTTP reservation is inconsistent")
        if last_run["finished_at"] is not None and (
            last_run["jobs_completed"]
            + last_run["jobs_failed"]
            + last_run["jobs_unavailable_no_scene"]
            != last_run["job_attempts"]
        ):
            raise SatelliteBatchError("finished batch last_run counts do not reconcile")
    return document


def _no_scene_unavailability(
    error_text: str,
    job: Mapping[str, Any],
    recorded_at: str,
) -> dict[str, Any] | None:
    """Return a terminal outcome only for the catalog's exact typed no-scene error."""
    if not isinstance(error_text, str):
        return None
    lines = [line.strip() for line in error_text.splitlines() if line.strip()]
    if not lines:
        return None
    match = _NO_SCENE_ERROR.fullmatch(lines[-1])
    if match is None:
        return None
    arguments = _arguments(job)
    window = match.group("window")
    prefix = f"--{window}-"
    try:
        temporal_window_days = int(arguments["--temporal-window-days"])
        query_window = {
            "provider": arguments["--provider"],
            "bbox": arguments["--bbox"],
            "start_date": arguments[f"{prefix}start"],
            "end_date": arguments[f"{prefix}end"],
            "target_date": arguments[f"{prefix}target"],
            "temporal_window_days": temporal_window_days,
        }
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "outcome": UNAVAILABLE_NO_SCENE,
        "catalog_error_type": (
            "datacenter_atlas.satellite_catalog.CatalogValidationError"
        ),
        "raw_reason": match.group("reason"),
        "window": window,
        "query_window": query_window,
        "recorded_at": _timestamp(recorded_at, "no-scene outcome recorded_at"),
    }


def _migrate_legacy_checkpoint(
    document: Mapping[str, Any],
    *,
    lineage: Mapping[str, Any],
    config: BatchConfig,
    selected_jobs: Mapping[str, Mapping[str, Any]],
    output: Path,
    migrated_at: str,
) -> dict[str, Any]:
    """Strictly validate and upgrade a schema-v1 checkpoint without rerunning jobs."""
    if document.get("schema_version") != LEGACY_BATCH_SCHEMA_VERSION:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    if config.max_response_bytes != DEFAULT_MAX_RESPONSE_BYTES:
        raise SatelliteBatchError(
            "schema-v1 checkpoints can migrate only with the default response cap"
        )
    upgraded = json.loads(json.dumps(document))
    tasks = upgraded.get("jobs")
    if not isinstance(tasks, dict) or set(tasks) != set(selected_jobs):
        raise SatelliteBatchError(
            "legacy batch manifest task inventory does not match selection"
        )
    legacy_task_keys = (
        set(_task_template(next(iter(selected_jobs.values())))) - {"unavailability"}
        if tasks
        else set()
    )
    for queue_id, task in tasks.items():
        if not isinstance(task, dict) or set(task) != legacy_task_keys:
            raise SatelliteBatchError(
                f"legacy batch task {queue_id} has unexpected fields"
            )
        task["unavailability"] = None

    summary = upgraded.get("summary")
    legacy_summary_keys = {
        "jobs_selected",
        "jobs_completed",
        "jobs_failed",
        "jobs_pending",
    }
    if not isinstance(summary, dict) or set(summary) != legacy_summary_keys:
        raise SatelliteBatchError("legacy batch manifest summary is invalid")
    summary["jobs_unavailable_no_scene"] = 0

    last_run = upgraded.get("last_run")
    if last_run is not None:
        legacy_run_keys = {
            "started_at",
            "finished_at",
            "max_jobs",
            "max_http_attempts",
            "job_attempts",
            "http_attempts_reserved",
            "jobs_completed",
            "jobs_failed",
            "budget_exhausted",
        }
        if not isinstance(last_run, dict) or set(last_run) != legacy_run_keys:
            raise SatelliteBatchError("legacy batch manifest last_run is invalid")
        last_run["jobs_unavailable_no_scene"] = 0

    upgraded["schema_version"] = PRIOR_BATCH_SCHEMA_VERSION
    _validate_checkpoint(
        upgraded,
        lineage=lineage,
        config=config,
        selected_jobs=selected_jobs,
    )

    migrated_in_last_run = 0
    run_start: datetime | None = None
    run_finish: datetime | None = None
    if last_run is not None:
        run_start = datetime.fromisoformat(
            _timestamp(
                last_run["started_at"], "legacy batch last_run started_at"
            ).replace("Z", "+00:00")
        )
        if last_run["finished_at"] is not None:
            run_finish = datetime.fromisoformat(
                _timestamp(
                    last_run["finished_at"], "legacy batch last_run finished_at"
                ).replace("Z", "+00:00")
            )

    for queue_id, task in tasks.items():
        if task["state"] != "failed" or not task["failures"]:
            continue
        failure = task["failures"][-1]
        outcome = _no_scene_unavailability(
            failure["error"], selected_jobs[queue_id], failure["at"]
        )
        if outcome is None:
            continue
        task["state"] = UNAVAILABLE_NO_SCENE
        task["unavailability"] = outcome
        if run_start is not None:
            failure_at = datetime.fromisoformat(
                _timestamp(failure["at"], f"{queue_id} failure timestamp").replace(
                    "Z", "+00:00"
                )
            )
            if failure_at >= run_start and (
                run_finish is None or failure_at <= run_finish
            ):
                migrated_in_last_run += 1

    if last_run is not None:
        if migrated_in_last_run > last_run["jobs_failed"]:
            raise SatelliteBatchError(
                "legacy batch no-scene outcomes exceed last_run failures"
            )
        last_run["jobs_failed"] -= migrated_in_last_run
        last_run["jobs_unavailable_no_scene"] = migrated_in_last_run
    _update_document(upgraded, migrated_at)
    _validate_checkpoint(
        upgraded,
        lineage=lineage,
        config=config,
        selected_jobs=selected_jobs,
    )
    audit = _validate_terminal_artifacts(
        upgraded,
        selected_jobs=selected_jobs,
        output=output,
        config=config,
    )
    upgraded["schema_version"] = BATCH_SCHEMA_VERSION
    upgraded["configuration"] = config.as_dict()
    upgraded["response_limit_migration"] = _response_limit_migration_record(
        source_schema_version=LEGACY_BATCH_SCHEMA_VERSION,
        migrated_at=migrated_at,
        config=config,
        audit=audit,
    )
    return _validate_checkpoint(
        upgraded,
        lineage=lineage,
        config=config,
        selected_jobs=selected_jobs,
    )


def _migrate_prior_checkpoint(
    document: Mapping[str, Any],
    *,
    lineage: Mapping[str, Any],
    config: BatchConfig,
    selected_jobs: Mapping[str, Mapping[str, Any]],
    output: Path,
    migrated_at: str,
) -> dict[str, Any]:
    """Strictly audit and upgrade schema v2 before any request can be made."""
    if document.get("schema_version") != PRIOR_BATCH_SCHEMA_VERSION:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    if config.max_response_bytes != DEFAULT_MAX_RESPONSE_BYTES:
        raise SatelliteBatchError(
            "schema-v2 checkpoints can migrate only with the default response cap"
        )
    _validate_checkpoint(
        document,
        lineage=lineage,
        config=config,
        selected_jobs=selected_jobs,
    )
    audit = _validate_terminal_artifacts(
        document,
        selected_jobs=selected_jobs,
        output=output,
        config=config,
    )
    upgraded = json.loads(json.dumps(document))
    upgraded["schema_version"] = BATCH_SCHEMA_VERSION
    upgraded["configuration"] = config.as_dict()
    upgraded["response_limit_migration"] = _response_limit_migration_record(
        source_schema_version=PRIOR_BATCH_SCHEMA_VERSION,
        migrated_at=migrated_at,
        config=config,
        audit=audit,
    )
    _update_document(upgraded, migrated_at)
    return _validate_checkpoint(
        upgraded,
        lineage=lineage,
        config=config,
        selected_jobs=selected_jobs,
    )


def _arguments(job: Mapping[str, Any]) -> dict[str, str]:
    raw = job["catalog_job"]["arguments"]
    if not isinstance(raw, list) or len(raw) % 2:
        raise SatelliteBatchError("catalog arguments must be flag/value pairs")
    parsed: dict[str, str] = {}
    for index in range(0, len(raw), 2):
        flag, value = raw[index : index + 2]
        if not isinstance(flag, str) or not flag.startswith("--") or not isinstance(
            value, str
        ):
            raise SatelliteBatchError("catalog arguments contain an invalid pair")
        if flag in parsed:
            raise SatelliteBatchError(f"catalog argument repeats {flag}")
        parsed[flag] = value
    return parsed


def _catalog_result(
    job: Mapping[str, Any],
    directory: Path,
    *,
    max_response_bytes: int,
) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteBatchError(f"catalog output is not a regular directory: {directory}")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SatelliteBatchError("catalog output contains a non-regular file")
    if {entry.name for entry in entries} != CATALOG_FILES:
        raise SatelliteBatchError("catalog output file set does not match its contract")
    for name in ("baseline-response.json", "current-response.json"):
        size = (directory / name).stat().st_size
        if size > max_response_bytes:
            raise SatelliteBatchError(
                f"catalog response {name} is {size} bytes, exceeding the "
                f"{max_response_bytes}-byte cap"
            )
    manifest_path = directory / "manifest.json"
    manifest_raw = manifest_path.read_bytes()
    try:
        document = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise SatelliteBatchError("catalog manifest is not valid JSON") from error
    if not isinstance(document, dict) or manifest_json(document).encode("utf-8") != manifest_raw:
        raise SatelliteBatchError("catalog manifest is not canonical JSON")
    arguments = _arguments(job)
    required = {
        "--provider",
        "--bbox",
        "--baseline-start",
        "--baseline-end",
        "--baseline-target",
        "--current-start",
        "--current-end",
        "--current-target",
        "--max-cloud-cover",
        "--limit",
        "--temporal-window-days",
        "--output-dir",
    }
    if set(arguments) != required:
        raise SatelliteBatchError("catalog job arguments do not match their contract")
    try:
        bbox = tuple(float(value) for value in arguments["--bbox"].split(","))
        baseline_query = CatalogQuery(
            bbox,
            arguments["--baseline-start"],
            arguments["--baseline-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        current_query = CatalogQuery(
            bbox,
            arguments["--current-start"],
            arguments["--current-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        rebuilt = build_pair_manifest(
            Provider(arguments["--provider"]),
            baseline_query,
            (directory / "baseline-response.json").read_bytes(),
            current_query,
            (directory / "current-response.json").read_bytes(),
            baseline_date=arguments["--baseline-target"],
            current_date=arguments["--current-target"],
            retrieved_at=document.get("retrieved_at"),
            temporal_window_days=int(arguments["--temporal-window-days"]),
        )
    except (TypeError, ValueError) as error:
        raise SatelliteBatchError(
            f"catalog output does not match its queue job: {error}"
        ) from error
    if rebuilt != document:
        raise SatelliteBatchError("catalog manifest does not reproduce from exact responses")
    if document.get("output_labels") != list(OUTPUT_LABELS) or document.get(
        "scope_note"
    ) != SCOPE_NOTE:
        raise SatelliteBatchError("catalog output lost its review-only labels or scope")
    selected_ids = document.get("selected_ids")
    if (
        not isinstance(selected_ids, dict)
        or set(selected_ids) != {"baseline", "current"}
        or any(not isinstance(value, str) or not value for value in selected_ids.values())
    ):
        raise SatelliteBatchError("catalog manifest selected IDs are invalid")
    artifacts = {
        name: _file_record(directory / name) for name in sorted(CATALOG_FILES)
    }
    if any(
        artifacts[name]["bytes"] > max_response_bytes
        for name in ("baseline-response.json", "current-response.json")
    ):
        raise SatelliteBatchError("catalog response changed while validating its byte cap")
    return {
        "artifacts": artifacts,
        "selected_ids": dict(selected_ids),
        "retrieved_at": _timestamp(document["retrieved_at"], "catalog retrieved_at"),
    }


def _safe_directory(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise SatelliteBatchError("catalog output directory must be a safe relative path")
    path = root.joinpath(candidate)
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise SatelliteBatchError("catalog output directory escapes batch output")
    return path


def _stage_directory(final: Path) -> Path:
    return final.with_name(f".{final.name}.staging")


def _validate_terminal_artifacts(
    document: Mapping[str, Any],
    *,
    selected_jobs: Mapping[str, Mapping[str, Any]],
    output: Path,
    config: BatchConfig,
) -> dict[str, int]:
    """Validate every saved terminal result and summarize historical responses."""
    completed_jobs = 0
    terminal_jobs = 0
    response_files = 0
    largest_response = 0
    for queue_id, task in document["jobs"].items():
        job = selected_jobs[queue_id]
        final = _safe_directory(output, task["output_directory"])
        stage = _stage_directory(final)
        if task["state"] == "completed":
            terminal_jobs += 1
            completed_jobs += 1
            try:
                result = _catalog_result(
                    job,
                    final,
                    max_response_bytes=config.max_response_bytes,
                )
            except SatelliteBatchError as error:
                raise SatelliteBatchError(
                    f"completed catalog output is invalid for {queue_id}: {error}"
                ) from error
            if (
                task["artifacts"] != result["artifacts"]
                or task["selected_ids"] != result["selected_ids"]
                or task["catalog_retrieved_at"] != result["retrieved_at"]
            ):
                raise SatelliteBatchError(
                    f"completed catalog output changed for {queue_id}"
                )
            sizes = [
                result["artifacts"][name]["bytes"]
                for name in ("baseline-response.json", "current-response.json")
            ]
            response_files += len(sizes)
            largest_response = max(largest_response, *sizes)
        elif task["state"] == UNAVAILABLE_NO_SCENE:
            terminal_jobs += 1
            if final.exists() or final.is_symlink() or stage.exists() or stage.is_symlink():
                raise SatelliteBatchError(
                    f"unavailable catalog outcome has unexpected output for {queue_id}"
                )
    return {
        "historical_terminal_jobs_validated": terminal_jobs,
        "historical_completed_jobs": completed_jobs,
        "historical_response_files": response_files,
        "largest_historical_response_bytes": largest_response,
    }


def _response_limit_migration_record(
    *,
    source_schema_version: int,
    migrated_at: str,
    config: BatchConfig,
    audit: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "source_schema_version": source_schema_version,
        "migrated_at": migrated_at,
        "max_response_bytes": config.max_response_bytes,
        "enforced_for_subsequent_attempts_at_or_after": migrated_at,
        "historical_acquisition_bounded": False,
        **dict(audit),
        "historical_response_files_validated_within_cap": True,
    }


def _clear_stale_stage(stage: Path) -> None:
    if stage.is_symlink():
        raise SatelliteBatchError(f"catalog staging path may not be a symlink: {stage}")
    if stage.exists():
        if not stage.is_dir():
            raise SatelliteBatchError(f"catalog staging path is not a directory: {stage}")
        shutil.rmtree(stage)


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
        }
    )


def _command(
    job: Mapping[str, Any],
    *,
    stage: Path,
    config: BatchConfig,
    package_root: Path,
) -> list[str]:
    script = package_root / job["catalog_job"]["script"]
    if script.is_symlink() or not script.is_file():
        raise SatelliteBatchError(f"catalog script is not a regular file: {script}")
    arguments = list(job["catalog_job"]["arguments"])
    try:
        output_index = arguments.index("--output-dir") + 1
    except ValueError as error:
        raise SatelliteBatchError("catalog job lacks --output-dir") from error
    arguments[output_index] = str(stage.resolve(strict=False))
    try:
        bbox_index = arguments.index("--bbox")
        bbox_value = arguments[bbox_index + 1]
    except (ValueError, IndexError) as error:
        raise SatelliteBatchError("catalog job lacks --bbox") from error
    arguments[bbox_index : bbox_index + 2] = [f"--bbox={bbox_value}"]
    arguments.extend(
        [
            "--timeout",
            _number_argument(config.timeout_seconds),
            "--retries",
            str(config.catalog_retries),
            "--user-agent",
            config.user_agent,
            "--minimum-interval-seconds",
            _number_argument(config.minimum_interval_seconds),
            "--max-response-bytes",
            str(config.max_response_bytes),
        ]
    )
    return [sys.executable, str(script), *arguments]


def _config_from_manifest(value: Any, *, schema_version: int) -> BatchConfig:
    expected_keys = {
        "mode",
        "priority_tiers",
        "user_agent",
        "minimum_interval_seconds",
        "timeout_seconds",
        "catalog_retries",
        "max_job_attempts",
        "maximum_http_attempts_per_job",
    }
    if schema_version == BATCH_SCHEMA_VERSION:
        expected_keys.add("max_response_bytes")
    elif schema_version != PRIOR_BATCH_SCHEMA_VERSION:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise SatelliteBatchError("batch configuration schema is invalid")
    if value.get("mode") != "catalog_only":
        raise SatelliteBatchError("batch configuration mode is invalid")
    config = BatchConfig(
        priority_tiers=value.get("priority_tiers"),
        user_agent=value.get("user_agent"),
        minimum_interval_seconds=value.get("minimum_interval_seconds"),
        timeout_seconds=value.get("timeout_seconds"),
        catalog_retries=value.get("catalog_retries"),
        max_job_attempts=value.get("max_job_attempts"),
        max_response_bytes=(
            value.get("max_response_bytes")
            if schema_version == BATCH_SCHEMA_VERSION
            else DEFAULT_MAX_RESPONSE_BYTES
        ),
    )
    if value != _configuration_for_schema(config, schema_version):
        raise SatelliteBatchError("batch configuration is not canonical")
    return config


def validate_satellite_batch(
    queue_directory: str | Path,
    output_directory: str | Path,
    *,
    config: BatchConfig | None = None,
) -> dict[str, Any]:
    """Validate a saved catalog batch and all terminal output artifacts offline."""
    queue_input = Path(queue_directory)
    if queue_input.is_symlink() or not queue_input.is_dir():
        raise SatelliteBatchError(
            f"queue bundle is not a regular directory: {queue_input}"
        )
    queue = queue_input.resolve()
    queue_manifest = validate_queue_bundle(queue)
    jobs = _read_jobs(queue)
    if any(job.get("review_constraints") != REVIEW_CONSTRAINTS for job in jobs):
        raise SatelliteBatchError("queue job lost its review-only constraints")

    output_input = Path(output_directory)
    if output_input.is_symlink() or not output_input.is_dir():
        raise SatelliteBatchError(
            f"batch output is not a regular directory: {output_input}"
        )
    output = output_input.resolve()
    checkpoint = output / BATCH_MANIFEST_FILENAME
    if checkpoint.is_symlink() or not checkpoint.is_file():
        raise SatelliteBatchError("batch manifest is not a regular file")
    raw = checkpoint.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SatelliteBatchError("batch manifest is not valid JSON") from error
    if not isinstance(document, dict) or raw != _manifest_raw(document):
        raise SatelliteBatchError("batch manifest is not canonical JSON")
    schema_version = document.get("schema_version")
    if schema_version not in {
        PRIOR_BATCH_SCHEMA_VERSION,
        BATCH_SCHEMA_VERSION,
    }:
        raise SatelliteBatchError("batch manifest has an unexpected schema version")
    saved_config = _config_from_manifest(
        document.get("configuration"), schema_version=schema_version
    )
    if config is not None:
        if not isinstance(config, BatchConfig):
            raise SatelliteBatchError("config must be a BatchConfig")
        if saved_config != config:
            raise SatelliteBatchError("saved batch configuration differs from expected")
    config = saved_config
    selected_jobs = {
        job["queue_id"]: job
        for job in jobs
        if job["priority"]["tier"] in config.priority_tiers
    }
    document = _validate_checkpoint(
        document,
        lineage=_queue_lineage(queue, queue_manifest),
        config=config,
        selected_jobs=selected_jobs,
    )
    _validate_terminal_artifacts(
        document,
        selected_jobs=selected_jobs,
        output=output,
        config=config,
    )
    for queue_id, task in document["jobs"].items():
        final = _safe_directory(output, task["output_directory"])
        stage = _stage_directory(final)
        if task["state"] not in {"completed", UNAVAILABLE_NO_SCENE} and (
            final.exists()
            or final.is_symlink()
            or stage.exists()
            or stage.is_symlink()
        ):
            raise SatelliteBatchError(
                f"non-completed task has unexpected catalog output for {queue_id}"
            )
    return document


def execute_satellite_queue(
    queue_directory: str | Path,
    output_directory: str | Path,
    *,
    config: BatchConfig = BatchConfig(),
    max_jobs: int = 25,
    max_http_attempts: int = 50,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Execute a bounded catalog-only batch and return its checkpoint manifest.

    ``max_http_attempts`` is enforced conservatively by reserving the command's
    worst-case two-window retry budget before each job.  Actual HTTP attempts
    therefore cannot exceed the cap, including failed subprocesses.
    """
    if not isinstance(config, BatchConfig):
        raise SatelliteBatchError("config must be a BatchConfig")
    max_jobs = _positive_integer(max_jobs, "max_jobs")
    max_http_attempts = _positive_integer(
        max_http_attempts, "max_http_attempts"
    )
    queue_input = Path(queue_directory)
    if queue_input.is_symlink() or not queue_input.is_dir():
        raise SatelliteBatchError(
            f"queue bundle is not a regular directory: {queue_input}"
        )
    queue = queue_input.resolve()
    queue_manifest = validate_queue_bundle(queue)
    jobs = _read_jobs(queue)
    if any(job.get("review_constraints") != REVIEW_CONSTRAINTS for job in jobs):
        raise SatelliteBatchError("queue job lost its review-only constraints")
    lineage = _queue_lineage(queue, queue_manifest)
    selected_jobs = {
        job["queue_id"]: job
        for job in jobs
        if job["priority"]["tier"] in config.priority_tiers
    }
    ordered_queue_ids = [
        job["queue_id"]
        for job in jobs
        if job["priority"]["tier"] in config.priority_tiers
    ]

    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output == queue or queue in output.parents:
        raise SatelliteBatchError("batch output must be separate from the queue bundle")
    if output.is_symlink():
        raise SatelliteBatchError("batch output may not be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir():
        raise SatelliteBatchError("batch output is not a directory")
    checkpoint_path = output / BATCH_MANIFEST_FILENAME
    checkpoint_temporary = output / f".{BATCH_MANIFEST_FILENAME}.tmp"
    if checkpoint_temporary.is_symlink():
        raise SatelliteBatchError("batch checkpoint temporary may not be a symlink")
    if checkpoint_temporary.exists():
        if not checkpoint_temporary.is_file():
            raise SatelliteBatchError("batch checkpoint temporary is not a regular file")
        checkpoint_temporary.unlink()
    now = _timestamp(timestamp(), "batch run started_at")
    if checkpoint_path.exists():
        if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
            raise SatelliteBatchError("batch manifest is not a regular file")
        checkpoint_raw = checkpoint_path.read_bytes()
        try:
            document = json.loads(checkpoint_raw)
        except json.JSONDecodeError as error:
            raise SatelliteBatchError("batch manifest is not valid JSON") from error
        if not isinstance(document, dict) or checkpoint_raw != _manifest_raw(document):
            raise SatelliteBatchError("batch manifest is not canonical JSON")
        if document.get("schema_version") == LEGACY_BATCH_SCHEMA_VERSION:
            document = _migrate_legacy_checkpoint(
                document,
                lineage=lineage,
                config=config,
                selected_jobs=selected_jobs,
                output=output,
                migrated_at=now,
            )
            _write_manifest(output, document, now)
        elif document.get("schema_version") == PRIOR_BATCH_SCHEMA_VERSION:
            document = _migrate_prior_checkpoint(
                document,
                lineage=lineage,
                config=config,
                selected_jobs=selected_jobs,
                output=output,
                migrated_at=now,
            )
            _write_manifest(output, document, now)
        else:
            document = _validate_checkpoint(
                document,
                lineage=lineage,
                config=config,
                selected_jobs=selected_jobs,
            )
    else:
        if any(output.iterdir()):
            raise SatelliteBatchError(
                "batch output contains files without a checkpoint manifest"
            )
        document = _new_document(
            lineage=lineage,
            config=config,
            jobs=jobs,
            created_at=now,
        )
        _write_manifest(output, document, now)

    for queue_id in ordered_queue_ids:
        task = document["jobs"][queue_id]
        job = selected_jobs[queue_id]
        final = _safe_directory(output, task["output_directory"])
        if task["state"] == "completed":
            try:
                result = _catalog_result(
                    job,
                    final,
                    max_response_bytes=config.max_response_bytes,
                )
            except SatelliteBatchError as error:
                raise SatelliteBatchError(
                    f"completed catalog output is invalid for {queue_id}: {error}"
                ) from error
            if (
                task["artifacts"] != result["artifacts"]
                or task["selected_ids"] != result["selected_ids"]
                or task["catalog_retrieved_at"] != result["retrieved_at"]
            ):
                raise SatelliteBatchError(
                    f"completed catalog output changed for {queue_id}"
                )
        elif task["state"] == UNAVAILABLE_NO_SCENE:
            stage = _stage_directory(final)
            if (
                final.exists()
                or final.is_symlink()
                or stage.exists()
                or stage.is_symlink()
            ):
                raise SatelliteBatchError(
                    f"unavailable catalog outcome has unexpected output for {queue_id}"
                )
        elif final.exists() or final.is_symlink():
            if task["attempts"] == 0:
                raise SatelliteBatchError(
                    f"unexpected catalog output exists before {queue_id} ran"
                )
            result = _catalog_result(
                job,
                final,
                max_response_bytes=config.max_response_bytes,
            )
            _completed_task(task, result, now)
            _write_manifest(output, document, now)
        elif task["state"] == "pending" and task["attempts"] > 0:
            task["state"] = "failed"
            task["failures"].append(
                {
                    "attempt": task["attempts"],
                    "at": now,
                    "error": "interrupted before the catalog attempt was checkpointed",
                }
            )
            _write_manifest(output, document, now)

    run = {
        "started_at": now,
        "finished_at": None,
        "max_jobs": max_jobs,
        "max_http_attempts": max_http_attempts,
        "job_attempts": 0,
        "http_attempts_reserved": 0,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "jobs_unavailable_no_scene": 0,
        "budget_exhausted": False,
    }
    document["last_run"] = run
    _write_manifest(output, document, now)
    invoked = False
    package_root = Path(__file__).resolve().parents[1]

    for queue_id in ordered_queue_ids:
        task = document["jobs"][queue_id]
        if task["state"] in {"completed", UNAVAILABLE_NO_SCENE} or task[
            "attempts"
        ] >= config.max_job_attempts:
            continue
        reservation = config.maximum_http_attempts_per_job
        if run["job_attempts"] >= max_jobs or (
            run["http_attempts_reserved"] + reservation > max_http_attempts
        ):
            run["budget_exhausted"] = True
            break
        if invoked:
            sleep(config.minimum_interval_seconds)
        invoked = True
        job = selected_jobs[queue_id]
        final = _safe_directory(output, task["output_directory"])
        stage = _stage_directory(final)
        if final.exists() or final.is_symlink():
            raise SatelliteBatchError(f"refusing to overwrite catalog output: {final}")
        _clear_stale_stage(stage)
        stage.parent.mkdir(parents=True, exist_ok=True)
        if stage.parent.is_symlink():
            raise SatelliteBatchError("catalog output parent may not be a symlink")

        task["attempts"] += 1
        task["state"] = "pending"
        run["job_attempts"] += 1
        run["http_attempts_reserved"] += reservation
        attempt_time = _timestamp(timestamp(), f"{queue_id} attempt timestamp")
        _write_manifest(output, document, attempt_time)
        command = _command(job, stage=stage, config=config, package_root=package_root)
        failure: str | None = None
        no_scene_error: str | None = None
        try:
            completed = command_runner(
                command,
                cwd=package_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                stderr = completed.stderr if isinstance(completed.stderr, str) else ""
                stdout = completed.stdout if isinstance(completed.stdout, str) else ""
                detail = (stderr or stdout).strip()
                failure = f"catalog command exited {completed.returncode}"
                if detail:
                    failure += ": " + detail[-2_000:]
                no_scene_error = stderr
            else:
                result = _catalog_result(
                    job,
                    stage,
                    max_response_bytes=config.max_response_bytes,
                )
                stage.replace(final)
                completion_time = _timestamp(
                    timestamp(), f"{queue_id} completion timestamp"
                )
                _completed_task(task, result, completion_time)
                run["jobs_completed"] += 1
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
        if failure is not None:
            failure_time = _timestamp(timestamp(), f"{queue_id} failure timestamp")
            task["failures"].append(
                {"attempt": task["attempts"], "at": failure_time, "error": failure}
            )
            unavailable = _no_scene_unavailability(
                no_scene_error or "", job, failure_time
            )
            if unavailable is None:
                task["state"] = "failed"
                task["unavailability"] = None
                run["jobs_failed"] += 1
            else:
                task["state"] = UNAVAILABLE_NO_SCENE
                task["unavailability"] = unavailable
                run["jobs_unavailable_no_scene"] += 1
            _clear_stale_stage(stage)
        _write_manifest(
            output,
            document,
            _timestamp(timestamp(), f"{queue_id} checkpoint timestamp"),
        )

    finished_at = _timestamp(timestamp(), "batch run finished_at")
    run["finished_at"] = finished_at
    _write_manifest(output, document, finished_at)
    return document
