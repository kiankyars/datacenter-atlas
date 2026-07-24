"""Atomic change execution over a frozen coverage-aware catalog reselection.

This side-by-side runner deliberately does not make the legacy catalog-batch
validator reinterpret derived selections as raw provider output.  It validates
the original catalog batch and the immutable reselection release, adapts only
the release's completed jobs to the frozen change-runner contract, and reuses
the unchanged v2 numerical processor.  Outputs remain visible-change proposals
for analyst review and are never atlas facts or infrastructure inferences.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Mapping

from . import satellite_change_batch as legacy
from .satellite_catalog_reselection import (
    HEADER_EVIDENCE_FILENAME,
    JOB_MANIFEST_FILENAME,
    RESELECTION_MANIFEST_FILENAME,
    SOURCE_MANIFEST_FILENAME,
    SUPPORTED_QUEUE_IDS,
    UNRESOLVED_FILENAME,
    release_catalog_tasks,
    validate_catalog_reselection,
)
from .satellite_queue import QUEUE_FILENAME, validate_queue_bundle


RESELECTED_CHANGE_BATCH_SCHEMA_VERSION = 1
RESELECTED_CHANGE_BATCH_PIPELINE = "satellite_review_reselected_change_batch"
RESELECTION_ADAPTER_VERSION = 1
RESELECTION_ADAPTER_FILES = (
    "datacenter_atlas/satellite_reselected_change_batch.py",
    "datacenter_atlas/satellite_catalog_reselection.py",
    "scripts/run_satellite_reselected_change_batch.py",
    "scripts/build_satellite_catalog_reselection.py",
)

CHANGE_BATCH_MANIFEST_FILENAME = legacy.CHANGE_BATCH_MANIFEST_FILENAME
DEFAULT_TIMEOUT_SECONDS = legacy.DEFAULT_TIMEOUT_SECONDS
DEFAULT_MINIMUM_INTERVAL_SECONDS = legacy.DEFAULT_MINIMUM_INTERVAL_SECONDS
ChangeBatchConfig = legacy.ChangeBatchConfig


class SatelliteReselectedChangeBatchError(legacy.SatelliteChangeBatchError):
    """Raised when reselection lineage or side-by-side execution is invalid."""


@dataclass(frozen=True, slots=True)
class _Inputs:
    legacy: legacy._Inputs
    source_catalog: Path
    release: Path
    release_document: Mapping[str, Any]
    release_manifest_record: Mapping[str, Any]
    expected_release_files: Mapping[Path, Mapping[str, Any]]
    expected_release_directories: frozenset[Path]


def _release_lineage(
    release: Path,
    document: Mapping[str, Any],
    queue_lineage: Mapping[str, Any],
) -> dict[str, Any]:
    path = legacy._regular_file(
        release,
        RESELECTION_MANIFEST_FILENAME,
        "reselection release manifest",
    )
    raw = path.read_bytes()
    if legacy._decode_json(raw, "reselection release manifest") != document:
        raise SatelliteReselectedChangeBatchError(
            "reselection release manifest changed after offline validation"
        )
    return {
        "index": 0,
        "schema_version": document["schema_version"],
        "pipeline": document["pipeline"],
        "state": document["state"],
        "generated_at": document["generated_at"],
        "manifest_file": RESELECTION_MANIFEST_FILENAME,
        "manifest_bytes": len(raw),
        "manifest_sha256": legacy._sha256(raw),
        "queue_manifest_sha256": queue_lineage["manifest_sha256"],
        "source_catalog_manifest_sha256": document["source_catalog_batch"][
            "manifest"
        ]["sha256"],
        "jobs_reselected": document["summary"]["jobs_reselected"],
        "jobs_unresolved_multitile_needed": document["summary"][
            "jobs_unresolved_multitile_needed"
        ],
        "change_jobs_executed_in_release_build": document["summary"][
            "change_jobs_executed"
        ],
    }


def _release_tree_contract(
    release: Path,
    document: Mapping[str, Any],
) -> tuple[dict[Path, Mapping[str, Any]], frozenset[Path]]:
    manifest = release / RESELECTION_MANIFEST_FILENAME
    expected_files: dict[Path, Mapping[str, Any]] = {
        manifest: legacy._file_record(manifest),
        release / HEADER_EVIDENCE_FILENAME: {
            "bytes": document["grid_header_evidence"]["bytes"],
            "sha256": document["grid_header_evidence"]["sha256"],
        },
        release / UNRESOLVED_FILENAME: {
            "bytes": document["unresolved_assessment"]["bytes"],
            "sha256": document["unresolved_assessment"]["sha256"],
        },
    }
    expected_directories = {release}
    for queue_id in SUPPORTED_QUEUE_IDS:
        job = document["jobs"][queue_id]
        directory = legacy._safe_child(
            release,
            job["output_directory"],
            f"{queue_id} reselection output directory",
        )
        current = directory
        while current != release:
            expected_directories.add(current)
            current = current.parent
        artifacts = job["artifacts"]
        if set(artifacts) != {
            "baseline-response.json",
            "current-response.json",
            SOURCE_MANIFEST_FILENAME,
            JOB_MANIFEST_FILENAME,
        }:
            raise SatelliteReselectedChangeBatchError(
                f"reselection artifact inventory changed for {queue_id}"
            )
        for name, record in artifacts.items():
            expected_files[directory / name] = {
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
    return expected_files, frozenset(expected_directories)


def _verify_reselection_tree(inputs: _Inputs) -> None:
    """Fast byte and closed-tree guard used around every numerical job."""

    release = inputs.release
    if release.is_symlink() or not release.is_dir():
        raise SatelliteReselectedChangeBatchError(
            "reselection release is not a regular directory"
        )
    actual_files: set[Path] = set()
    actual_directories: set[Path] = {release}
    for path in release.rglob("*"):
        if path.is_symlink():
            raise SatelliteReselectedChangeBatchError(
                f"reselection release contains a symlink: {path}"
            )
        if path.is_dir():
            actual_directories.add(path)
        elif path.is_file():
            actual_files.add(path)
        else:
            raise SatelliteReselectedChangeBatchError(
                f"reselection release contains a non-regular path: {path}"
            )
    expected_files = set(inputs.expected_release_files)
    if actual_files != expected_files:
        missing = sorted(str(path) for path in expected_files - actual_files)
        extra = sorted(str(path) for path in actual_files - expected_files)
        raise SatelliteReselectedChangeBatchError(
            f"reselection release file inventory changed; missing={missing}, extra={extra}"
        )
    if actual_directories != set(inputs.expected_release_directories):
        raise SatelliteReselectedChangeBatchError(
            "reselection release directory inventory changed"
        )
    for path, expected in inputs.expected_release_files.items():
        if legacy._file_record(path) != dict(expected):
            raise SatelliteReselectedChangeBatchError(
                f"reselection release artifact changed: {path}"
            )
    source_manifest = legacy._regular_file(
        inputs.source_catalog,
        RESELECTION_MANIFEST_FILENAME,
        "original source catalog manifest",
    )
    if legacy._file_record(source_manifest) != dict(
        inputs.release_document["source_catalog_batch"]["manifest"]
    ):
        raise SatelliteReselectedChangeBatchError(
            "original source catalog manifest changed"
        )


def _validated_inputs(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
) -> _Inputs:
    try:
        release_document = validate_catalog_reselection(
            queue_directory,
            source_catalog_batch_directory,
            reselection_release_directory,
        )
    except Exception as error:
        raise SatelliteReselectedChangeBatchError(
            f"reselection release failed offline validation: {error}"
        ) from error

    queue = legacy._absolute_directory(
        queue_directory, "queue bundle", must_exist=True
    )
    source = legacy._absolute_directory(
        source_catalog_batch_directory,
        "original source catalog batch",
        must_exist=True,
    )
    release = legacy._absolute_directory(
        reselection_release_directory,
        "reselection release",
        must_exist=True,
    )
    queue_manifest = validate_queue_bundle(queue)
    if queue_manifest["configuration"]["provider"] != "earth-search-v1":
        raise SatelliteReselectedChangeBatchError(
            "reselected change processor supports only earth-search-v1 queues"
        )
    queue_jobs = tuple(legacy._read_queue_jobs(queue, queue_manifest))
    queue_by_id = {job["queue_id"]: job for job in queue_jobs}
    if len(queue_by_id) != len(queue_jobs):
        raise SatelliteReselectedChangeBatchError(
            "validated queue contains duplicate queue IDs"
        )
    queue_lineage = legacy._queue_lineage(queue, queue_manifest)
    tasks = release_catalog_tasks(release_document)
    if set(tasks) != set(SUPPORTED_QUEUE_IDS):
        raise SatelliteReselectedChangeBatchError(
            "reselection adapter task inventory changed"
        )
    lineage = _release_lineage(release, release_document, queue_lineage)
    adapted = legacy._Inputs(
        queue=queue,
        queue_manifest=queue_manifest,
        queue_jobs=queue_jobs,
        queue_by_id=queue_by_id,
        queue_lineage=queue_lineage,
        catalog_roots=(release,),
        catalog_documents=(release_document,),
        catalog_lineages=(lineage,),
        completed_sources={
            queue_id: (0, tasks[queue_id]) for queue_id in SUPPORTED_QUEUE_IDS
        },
    )
    expected_files, expected_directories = _release_tree_contract(
        release, release_document
    )
    inputs = _Inputs(
        legacy=adapted,
        source_catalog=source,
        release=release,
        release_document=release_document,
        release_manifest_record=expected_files[
            release / RESELECTION_MANIFEST_FILENAME
        ],
        expected_release_files=expected_files,
        expected_release_directories=expected_directories,
    )
    _verify_reselection_tree(inputs)
    return inputs


def _processor_lineage(package_root: Path) -> dict[str, Any]:
    processor = json.loads(json.dumps(legacy._processor_lineage(package_root)))
    for relative in RESELECTION_ADAPTER_FILES:
        path = legacy._regular_file(package_root, relative, f"processor {relative}")
        processor["files"][relative] = legacy._file_record(path)
    processor["reselection_adapter"] = {
        "schema_version": RESELECTED_CHANGE_BATCH_SCHEMA_VERSION,
        "pipeline": RESELECTED_CHANGE_BATCH_PIPELINE,
        "adapter_version": RESELECTION_ADAPTER_VERSION,
        "numerical_processor_reused_unchanged": True,
    }
    return processor


def _selection(inputs: _Inputs) -> dict[str, Any]:
    return legacy._build_selection(
        inputs.legacy,
        include_queue_ids=list(SUPPORTED_QUEUE_IDS),
        exclusion_file=None,
    )


def _expected_tasks(
    inputs: _Inputs, selection: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    tasks = legacy._expected_tasks(inputs.legacy, selection)
    release_document = inputs.release_document
    for queue_id in selection["selected_queue_ids"]:
        release_job = release_document["jobs"][queue_id]
        artifacts = release_job["artifacts"]
        tasks[queue_id]["catalog_reselection"] = {
            "schema_version": release_document["schema_version"],
            "pipeline": release_document["pipeline"],
            "release_manifest": {
                "file": RESELECTION_MANIFEST_FILENAME,
                **dict(inputs.release_manifest_record),
            },
            "job_manifest": {
                "file": (
                    f"{release_job['output_directory']}/{JOB_MANIFEST_FILENAME}"
                ),
                **dict(artifacts[JOB_MANIFEST_FILENAME]),
            },
            "source_catalog_manifest": dict(
                release_document["source_catalog_batch"]["manifest"]
            ),
            "source_catalog_task_sha256": release_job[
                "source_catalog_task_sha256"
            ],
            "original_selected_ids": dict(release_job["original_selected_ids"]),
            "selected_ids": dict(release_job["selected_ids"]),
            "selected_feature_sha256": dict(
                release_job["selected_feature_sha256"]
            ),
            "grid_header_evidence": dict(
                release_document["grid_header_evidence"]
            ),
            "raw_provider_response_bytes_copied_exactly": True,
            "all_required_asset_header_windows_within_grid": True,
        }
    return tasks


def _saved_context(
    document: Mapping[str, Any], inputs: _Inputs
) -> tuple[ChangeBatchConfig, dict[str, Any], dict[str, dict[str, Any]]]:
    config = legacy._config_from_document(document.get("configuration"))
    selection = legacy._validate_selection(
        document.get("selection"), inputs.legacy
    )
    if selection != _selection(inputs):
        raise SatelliteReselectedChangeBatchError(
            "saved selection differs from the complete reselection inventory"
        )
    return config, selection, _expected_tasks(inputs, selection)


def _validate_checkpoint(
    document: Any,
    *,
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: ChangeBatchConfig,
    selection: Mapping[str, Any],
    expected_tasks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise SatelliteReselectedChangeBatchError(
            "reselected change-batch manifest must be an object"
        )
    if document.get("schema_version") != RESELECTED_CHANGE_BATCH_SCHEMA_VERSION or (
        document.get("pipeline") != RESELECTED_CHANGE_BATCH_PIPELINE
    ):
        raise SatelliteReselectedChangeBatchError(
            "reselected change-batch manifest identity is invalid"
        )
    proxy = json.loads(json.dumps(document))
    proxy["schema_version"] = legacy.CHANGE_BATCH_SCHEMA_VERSION
    proxy["pipeline"] = legacy.CHANGE_BATCH_PIPELINE
    legacy._validate_checkpoint(
        proxy,
        inputs=inputs.legacy,
        processor=processor,
        config=config,
        selection=selection,
        expected_tasks=expected_tasks,
    )
    return document


def _new_document(
    *,
    inputs: _Inputs,
    processor: Mapping[str, Any],
    config: ChangeBatchConfig,
    selection: Mapping[str, Any],
    expected_tasks: Mapping[str, Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    document = legacy._new_document(
        inputs=inputs.legacy,
        processor=processor,
        config=config,
        selection=selection,
        expected_tasks=expected_tasks,
        created_at=created_at,
    )
    document["schema_version"] = RESELECTED_CHANGE_BATCH_SCHEMA_VERSION
    document["pipeline"] = RESELECTED_CHANGE_BATCH_PIPELINE
    return document


def _separate_output(output: Path, inputs: _Inputs) -> None:
    legacy._separate_output(output, inputs.legacy)
    output_resolved = output.resolve(strict=False)
    source_resolved = inputs.source_catalog.resolve()
    if (
        output_resolved == source_resolved
        or source_resolved in output_resolved.parents
        or output_resolved in source_resolved.parents
    ):
        raise SatelliteReselectedChangeBatchError(
            "change-batch output must be separate from the original source catalog batch"
        )


def validate_reselected_change_inputs(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
) -> dict[str, Any]:
    """Validate all inputs and task bindings without creating or running output."""

    inputs = _validated_inputs(
        queue_directory,
        source_catalog_batch_directory,
        reselection_release_directory,
    )
    package_root = Path(__file__).resolve().parents[1]
    processor = _processor_lineage(package_root)
    selection = _selection(inputs)
    tasks = _expected_tasks(inputs, selection)
    legacy._verify_input_manifest_bytes(inputs.legacy)
    _verify_reselection_tree(inputs)
    return {
        "schema_version": RESELECTED_CHANGE_BATCH_SCHEMA_VERSION,
        "pipeline": "satellite_review_reselected_change_input_validation",
        "change_analysis_executed": False,
        "reselection_release": {
            "manifest_file": RESELECTION_MANIFEST_FILENAME,
            **dict(inputs.release_manifest_record),
            "pipeline": inputs.release_document["pipeline"],
            "generated_at": inputs.release_document["generated_at"],
        },
        "selection": selection,
        "processor": processor,
        "summary": {
            "jobs_validated": len(tasks),
            "jobs_unresolved_multitile_needed": inputs.release_document["summary"][
                "jobs_unresolved_multitile_needed"
            ],
            "change_jobs_executed": 0,
        },
        "scope": dict(legacy.CHANGE_SCOPE),
    }


def validate_satellite_reselected_change_batch(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
) -> dict[str, Any]:
    """Validate a closed side-by-side output under a shared directory lock."""

    inputs = _validated_inputs(
        queue_directory,
        source_catalog_batch_directory,
        reselection_release_directory,
    )
    output = legacy._absolute_directory(
        output_directory, "reselected change-batch output", must_exist=True
    )
    _separate_output(output, inputs)
    with legacy._directory_lock(output, exclusive=False):
        return _validate_satellite_reselected_change_batch_locked(
            queue_directory,
            source_catalog_batch_directory,
            reselection_release_directory,
            output_directory,
            config=config,
        )


def _validate_satellite_reselected_change_batch_locked(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
) -> dict[str, Any]:
    inputs = _validated_inputs(
        queue_directory,
        source_catalog_batch_directory,
        reselection_release_directory,
    )
    package_root = Path(__file__).resolve().parents[1]
    processor = _processor_lineage(package_root)
    output = legacy._absolute_directory(
        output_directory, "reselected change-batch output", must_exist=True
    )
    _separate_output(output, inputs)
    temporary = output / f".{CHANGE_BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise SatelliteReselectedChangeBatchError(
            "reselected change-batch output contains an unfinished checkpoint temporary"
        )
    document = legacy._load_checkpoint(output / CHANGE_BATCH_MANIFEST_FILENAME)
    saved_config, selection, expected_tasks = _saved_context(document, inputs)
    if config is not None:
        if not isinstance(config, ChangeBatchConfig) or config != saved_config:
            raise SatelliteReselectedChangeBatchError(
                "saved change-batch configuration differs from expected"
            )
    _validate_checkpoint(
        document,
        inputs=inputs,
        processor=processor,
        config=saved_config,
        selection=selection,
        expected_tasks=expected_tasks,
    )
    legacy._verify_input_manifest_bytes(inputs.legacy)
    _verify_reselection_tree(inputs)
    legacy._validate_output_tree(output, document, inputs.legacy)
    return document


def execute_satellite_reselected_change_batch(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    max_jobs: int = 1,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = legacy._utc_now,
) -> dict[str, Any]:
    """Execute one bounded invocation over all fifteen supported reselected jobs."""

    legacy._positive_integer(max_jobs, "max_jobs")
    if config is not None and not isinstance(config, ChangeBatchConfig):
        raise SatelliteReselectedChangeBatchError(
            "config must be a ChangeBatchConfig"
        )
    inputs = _validated_inputs(
        queue_directory,
        source_catalog_batch_directory,
        reselection_release_directory,
    )
    output = legacy._absolute_directory(
        output_directory, "reselected change-batch output", must_exist=False
    )
    _separate_output(output, inputs)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteReselectedChangeBatchError(
            "reselected change-batch output is not a regular directory"
        )
    with legacy._directory_lock(output, exclusive=True):
        return _execute_satellite_reselected_change_batch_locked(
            queue_directory,
            source_catalog_batch_directory,
            reselection_release_directory,
            output_directory,
            config=config,
            max_jobs=max_jobs,
            command_runner=command_runner,
            sleep=sleep,
            timestamp=timestamp,
        )


def _execute_satellite_reselected_change_batch_locked(
    queue_directory: str | Path,
    source_catalog_batch_directory: str | Path,
    reselection_release_directory: str | Path,
    output_directory: str | Path,
    *,
    config: ChangeBatchConfig | None = None,
    max_jobs: int = 1,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] = legacy._utc_now,
) -> dict[str, Any]:
    max_jobs = legacy._positive_integer(max_jobs, "max_jobs")
    if config is not None and not isinstance(config, ChangeBatchConfig):
        raise SatelliteReselectedChangeBatchError(
            "config must be a ChangeBatchConfig"
        )
    inputs = _validated_inputs(
        queue_directory,
        source_catalog_batch_directory,
        reselection_release_directory,
    )
    package_root = Path(__file__).resolve().parents[1]
    processor = _processor_lineage(package_root)
    output = legacy._absolute_directory(
        output_directory, "reselected change-batch output", must_exist=False
    )
    _separate_output(output, inputs)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteReselectedChangeBatchError(
            "reselected change-batch output is not a regular directory"
        )
    checkpoint = output / CHANGE_BATCH_MANIFEST_FILENAME
    temporary = output / f".{CHANGE_BATCH_MANIFEST_FILENAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_symlink() or not temporary.is_file():
            raise SatelliteReselectedChangeBatchError(
                "reselected change-batch checkpoint temporary is not a regular file"
            )
        temporary.unlink()

    started_at = legacy._timestamp(
        timestamp(), "reselected change-batch invocation started_at"
    )
    if checkpoint.exists() or checkpoint.is_symlink():
        document = legacy._load_checkpoint(checkpoint)
        saved_config, selection, expected_tasks = _saved_context(document, inputs)
        if config is not None and config != saved_config:
            raise SatelliteReselectedChangeBatchError(
                "saved change-batch configuration differs from requested configuration"
            )
        config = saved_config
        _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
        )
        legacy._validate_output_tree(output, document, inputs.legacy)
        _verify_reselection_tree(inputs)
        legacy._recover_interrupted_run(
            output, document, inputs.legacy, config, started_at
        )
        _validate_checkpoint(
            document,
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
        )
        legacy._validate_output_tree(output, document, inputs.legacy)
    else:
        if any(output.iterdir()):
            raise SatelliteReselectedChangeBatchError(
                "reselected change-batch output contains files without a checkpoint"
            )
        config = config or ChangeBatchConfig()
        selection = _selection(inputs)
        expected_tasks = _expected_tasks(inputs, selection)
        document = _new_document(
            inputs=inputs,
            processor=processor,
            config=config,
            selection=selection,
            expected_tasks=expected_tasks,
            created_at=started_at,
        )
        legacy._write_checkpoint(output, document, config, started_at)

    run = {
        "run_number": len(document["runs"]) + 1,
        "state": "running",
        "started_at": started_at,
        "finished_at": None,
        "interruption_recorded_at": None,
        "max_jobs": max_jobs,
        "job_attempts": 0,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "jobs_recovered_after_publish": 0,
        "jobs_interrupted": 0,
        "budget_exhausted": False,
    }
    document["runs"].append(run)
    legacy._write_checkpoint(output, document, config, started_at)

    invoked = False
    for queue_id in selection["selected_queue_ids"]:
        task = document["jobs"][queue_id]
        if task["state"] == "completed" or task["attempts"] >= config.max_job_attempts:
            continue
        if run["job_attempts"] >= max_jobs:
            run["budget_exhausted"] = True
            break
        if invoked and config.minimum_interval_seconds:
            sleep(config.minimum_interval_seconds)
        invoked = True
        legacy._verify_input_manifest_bytes(inputs.legacy)
        _verify_reselection_tree(inputs)
        if _processor_lineage(package_root) != document["processor"]:
            raise SatelliteReselectedChangeBatchError(
                "change processor or reselection adapter changed during execution"
            )
        final, stage = legacy._task_paths(output, task)
        if final.exists() or final.is_symlink():
            raise SatelliteReselectedChangeBatchError(
                f"refusing to overwrite change output for {queue_id}: {final}"
            )
        legacy._clear_stage(stage)
        legacy._prepare_parent(output, final)

        attempt_at = legacy._timestamp(timestamp(), f"{queue_id} attempt timestamp")
        task["attempts"] += 1
        task["state"] = "running"
        task["last_attempt_started_at"] = attempt_at
        run["job_attempts"] += 1
        legacy._write_checkpoint(output, document, config, attempt_at)
        failure_kind: str | None = None
        failure_detail: str | None = None
        try:
            command = legacy._command(
                task,
                catalog_root=legacy._catalog_root(inputs.legacy, task),
                stage=stage,
                package_root=package_root,
            )
            completed = command_runner(
                command,
                cwd=package_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
            )
            legacy._verify_input_manifest_bytes(inputs.legacy)
            _verify_reselection_tree(inputs)
            if completed.returncode != 0:
                stderr = completed.stderr if isinstance(completed.stderr, str) else ""
                stdout = completed.stdout if isinstance(completed.stdout, str) else ""
                detail = (stderr or stdout).strip()
                failure_kind = "command_exit"
                failure_detail = f"change command exited {completed.returncode}"
                if detail:
                    failure_detail += ": " + detail[-2_000:]
            else:
                result = legacy._change_result(
                    task, stage, legacy._catalog_root(inputs.legacy, task)
                )
                legacy._fsync_tree(stage)
                if legacy._change_result(
                    task, stage, legacy._catalog_root(inputs.legacy, task)
                ) != result:
                    raise SatelliteReselectedChangeBatchError(
                        "validated change output changed before atomic publication"
                    )
                legacy._verify_input_manifest_bytes(inputs.legacy)
                _verify_reselection_tree(inputs)
                if _processor_lineage(package_root) != document["processor"]:
                    raise SatelliteReselectedChangeBatchError(
                        "processor or reselection adapter changed during the job"
                    )
                os.replace(stage, final)
                parent_fd = os.open(final.parent, os.O_RDONLY)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                completed_at = legacy._timestamp(
                    timestamp(), f"{queue_id} completion timestamp"
                )
                legacy._complete_task(task, result, completed_at)
                run["jobs_completed"] += 1
        except subprocess.TimeoutExpired as error:
            failure_kind = "timeout"
            failure_detail = (
                f"change command exceeded {config.timeout_seconds:g} seconds: {error}"
            )
        except legacy.SatelliteChangeBatchError as error:
            failure_kind = "output_validation"
            failure_detail = f"{type(error).__name__}: {error}"
        except Exception as error:
            failure_kind = "execution_error"
            failure_detail = f"{type(error).__name__}: {error}"
        if failure_kind is not None:
            failed_at = legacy._timestamp(
                timestamp(), f"{queue_id} failure timestamp"
            )
            legacy._record_failure(
                task,
                at=failed_at,
                kind=failure_kind,
                error=failure_detail or failure_kind,
            )
            run["jobs_failed"] += 1
            legacy._clear_stage(stage)
        checkpoint_at = legacy._timestamp(
            timestamp(), f"{queue_id} checkpoint timestamp"
        )
        legacy._write_checkpoint(output, document, config, checkpoint_at)

    legacy._verify_input_manifest_bytes(inputs.legacy)
    _verify_reselection_tree(inputs)
    finished_at = legacy._timestamp(
        timestamp(), "reselected change-batch invocation finished_at"
    )
    run["state"] = "completed"
    run["finished_at"] = finished_at
    legacy._write_checkpoint(output, document, config, finished_at)
    _validate_checkpoint(
        document,
        inputs=inputs,
        processor=processor,
        config=config,
        selection=selection,
        expected_tasks=expected_tasks,
    )
    legacy._validate_output_tree(output, document, inputs.legacy)
    return document
