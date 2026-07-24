"""Fail-closed change runner for the audited v71 explicit catalog receipt.

The generic numerical change carrier remains byte-for-byte unchanged.  This
adapter loads that exact pinned source in an isolated module namespace, swaps
only its catalog validator for the exact explicit-v1 validator, and replaces
the job-publication rename with an atomic no-replace promotion.  Exactly the
eleven receipt-bound jobs are runnable, in receipt order.  All outputs remain
review-only visible-change proposals and cannot mutate Atlas facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import types
from typing import Any, Callable, Mapping

from .satellite_batch_explicit_v1 import (
    ExplicitBatchConfig,
    validate_explicit_satellite_batch_v1,
)


class ExplicitSatelliteChangeBatchV1Error(ValueError):
    """Raised when the pinned inputs, execution, or output contract drifts."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = (
    PACKAGE_ROOT / "satellite_review_queues/2026-07-21-open-seed-v71"
)
DEFAULT_CATALOG_RUN_PATH = (
    PACKAGE_ROOT
    / "satellite_review_runs/2026-07-21-open-seed-v71-active-explicit-001"
)
DEFAULT_OUTPUT_PATH = (
    PACKAGE_ROOT
    / "satellite_change_runs/2026-07-21-open-seed-v71-active-explicit-001"
)
GENERIC_CARRIER_PATH = PACKAGE_ROOT / "datacenter_atlas/satellite_change_batch.py"
CATALOG_VALIDATOR_PATH = (
    PACKAGE_ROOT / "datacenter_atlas/satellite_batch_explicit_v1.py"
)

GENERIC_CARRIER_SHA256 = (
    "01e8a6e27f2cca5fbcb95f95b2b6394419d0d95dd45c1210dc1549272b278ef3"
)
CATALOG_VALIDATOR_SHA256 = (
    "4d83adc758d904dac0024e797bad348353bbfc192cea1b9eccf3e43bea25b491"
)
QUEUE_MANIFEST_SHA256 = (
    "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000"
)
QUEUE_MANIFEST_SIDECAR_SHA256 = (
    "ca0314d3adacf71ca6957a65435e9f95e495e2973e3fef7b023fdab36f3f4aeb"
)
QUEUE_SHA256 = (
    "462a3d4b8f482fecb0ccd325d9aac393f69e02fe86ad9dbfcb3b5aa74c700000"
)
CATALOG_MANIFEST_SHA256 = (
    "c930e7a0431540ead5fe54d8cc60808bc0e1e8a57ddea99acb01eacb94d25da9"
)
SELECTION_RECEIPT_SHA256 = (
    "cab75bcfb893002baa65a04bd3e2b1a104a510cf820076f7fcddecb5a2c665d2"
)
SELECTION_RECEIPT_SIDECAR_SHA256 = (
    "529ce1834cccdce96605375dc4dc3674bffe92fccf1234462c9231f5000c8a49"
)
PIPELINE = "satellite_review_change_batch_explicit_v1"
SELECTED_QUEUE_IDS = (
    "satq-1f72804d5d56bb342d5e2e2c",
    "satq-be2a4e34c6f53c7e4f96205c",
    "satq-c35caa31b2dbfa58da1de7b9",
    "satq-6d40fe3ecc9e39e712c0a2d0",
    "satq-d2f2205b9b46de73b37998f3",
    "satq-db46dc300e93181cfe250029",
    "satq-c5dd1e3c30725073cefca3e4",
    "satq-3f234ace58ef90bcb7affc42",
    "satq-1d4a91217eae3cffc49002cb",
    "satq-5ee998aa094cc5f057fec55d",
    "satq-1610b5ac5506aac220b11453",
)
SELECTED_JOB_COUNT = len(SELECTED_QUEUE_IDS)
REPRESENTED_ACTIVE_JOB_COUNT = 98
UNSELECTED_PENDING_JOB_COUNT = 87
MAX_JOB_ATTEMPTS = 1
DEFAULT_TIMEOUT_SECONDS = 1_800.0
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1

PROCESSOR_FILES = (
    "datacenter_atlas/satellite_change_batch_explicit_v1.py",
    "satellite_change_batch_explicit_v1.py",
    "scripts/run_satellite_change_batch_explicit_v1.py",
    "datacenter_atlas/satellite_change_batch.py",
    "datacenter_atlas/satellite_batch_explicit_v1.py",
    "datacenter_atlas/satellite_batch.py",
    "datacenter_atlas/satellite_queue_v71.py",
    "datacenter_atlas/satellite_queue.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/models.py",
    "scripts/sentinel_change.py",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_file(path: Path, expected_sha256: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitSatelliteChangeBatchV1Error(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise ExplicitSatelliteChangeBatchV1Error(f"{label} changed")
    return raw


def _exact_directory(value: str | Path, expected: Path, label: str) -> Path:
    path = Path(os.path.abspath(os.fspath(value)))
    if path.is_symlink() or not path.is_dir():
        raise ExplicitSatelliteChangeBatchV1Error(
            f"{label} must be a regular non-symlink directory"
        )
    if path.resolve() != expected.resolve():
        raise ExplicitSatelliteChangeBatchV1Error(
            f"{label} must be the pinned {expected.resolve()}"
        )
    return path.resolve()


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExplicitSatelliteChangeBatchV1Error(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise ExplicitSatelliteChangeBatchV1Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitSatelliteChangeBatchV1Error(
            f"{label} is not valid JSON"
        ) from error


def validate_explicit_change_inputs(
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
) -> dict[str, Any]:
    """Offline-validate the exact queue, catalog run, and selection receipt."""

    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v71 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "explicit catalog run"
    )
    _exact_file(GENERIC_CARRIER_PATH, GENERIC_CARRIER_SHA256, "generic change carrier")
    _exact_file(
        CATALOG_VALIDATOR_PATH,
        CATALOG_VALIDATOR_SHA256,
        "explicit catalog validator",
    )
    _exact_file(queue / "manifest.json", QUEUE_MANIFEST_SHA256, "queue manifest")
    _exact_file(
        queue / "manifest.sha256",
        QUEUE_MANIFEST_SIDECAR_SHA256,
        "queue manifest sidecar",
    )
    _exact_file(
        queue / "satellite-review-queue.jsonl", QUEUE_SHA256, "queue JSONL"
    )
    manifest_raw = _exact_file(
        catalog / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "explicit catalog manifest",
    )
    receipt_raw = _exact_file(
        catalog / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "explicit selection receipt",
    )
    _exact_file(
        catalog / "selection-receipt.sha256",
        SELECTION_RECEIPT_SIDECAR_SHA256,
        "explicit selection receipt sidecar",
    )
    try:
        document = validate_explicit_satellite_batch_v1(
            queue, catalog, config=ExplicitBatchConfig()
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV1Error(
            f"explicit catalog run failed offline validation: {error}"
        ) from error
    if _strict_json(manifest_raw, "explicit catalog manifest") != document:
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit catalog validator did not return the pinned manifest"
        )
    receipt = _strict_json(receipt_raw, "explicit selection receipt")
    if not isinstance(receipt, Mapping):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit selection receipt must be an object"
        )
    selection = receipt.get("selection")
    policy = receipt.get("execution_policy")
    if (
        not isinstance(selection, Mapping)
        or tuple(selection.get("selected_queue_ids", ())) != SELECTED_QUEUE_IDS
        or selection.get("selected_jobs_count") != SELECTED_JOB_COUNT
        or selection.get("unselected_pending_jobs")
        != UNSELECTED_PENDING_JOB_COUNT
        or receipt.get("representation", {}).get("represented_jobs")
        != REPRESENTED_ACTIVE_JOB_COUNT
        or policy
        != {
            "catalog_retries": 0,
            "http_attempts_reserved_per_job": 2,
            "job_promotion": "atomic_no_replace",
            "lifetime_http_attempt_cap": 22,
            "max_job_attempts": 1,
            "unexpected_output_adoption": False,
        }
    ):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit selection receipt contract changed"
        )
    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping) or len(jobs) != REPRESENTED_ACTIVE_JOB_COUNT:
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit catalog represented inventory changed"
        )
    selected = [
        queue_id
        for queue_id, task in sorted(
            jobs.items(), key=lambda item: item[1]["queue_position"]
        )
        if task.get("selected_for_execution")
    ]
    if tuple(selected) != SELECTED_QUEUE_IDS:
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit catalog selected order changed"
        )
    for queue_id, task in jobs.items():
        if queue_id in SELECTED_QUEUE_IDS:
            if task.get("state") != "completed" or task.get("attempts") != 1:
                raise ExplicitSatelliteChangeBatchV1Error(
                    f"selected catalog task is not completed once: {queue_id}"
                )
        elif (
            task.get("selected_for_execution")
            or task.get("state") != "pending"
            or task.get("attempts") != 0
        ):
            raise ExplicitSatelliteChangeBatchV1Error(
                f"unselected catalog task became runnable: {queue_id}"
            )
    return document


def _explicit_catalog_lineage(
    index: int,
    root: Path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    if index != 0 or root.resolve() != DEFAULT_CATALOG_RUN_PATH.resolve():
        raise ExplicitSatelliteChangeBatchV1Error(
            "only the single pinned explicit catalog run is allowed"
        )
    raw = _exact_file(
        root / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "explicit catalog manifest",
    )
    if _strict_json(raw, "explicit catalog manifest") != document:
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit catalog manifest changed after validation"
        )
    receipt_raw = _exact_file(
        root / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "explicit selection receipt",
    )
    sidecar_raw = _exact_file(
        root / "selection-receipt.sha256",
        SELECTION_RECEIPT_SIDECAR_SHA256,
        "explicit selection receipt sidecar",
    )
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
        "selection_receipt_bytes": len(receipt_raw),
        "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
        "selection_receipt_sidecar_file": "selection-receipt.sha256",
        "selection_receipt_sidecar_bytes": len(sidecar_raw),
        "selection_receipt_sidecar_sha256": SELECTION_RECEIPT_SIDECAR_SHA256,
    }


def _atomic_promote_noreplace(stage: Path, destination: Path) -> None:
    """Atomically rename a directory only when the destination is absent."""

    if stage.is_symlink() or not stage.is_dir():
        raise ExplicitSatelliteChangeBatchV1Error(
            f"change stage is not a regular directory: {stage}"
        )
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover - platform contract
            raise ExplicitSatelliteChangeBatchV1Error(
                "atomic no-replace publication is unavailable"
            )
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover - platform contract
            raise ExplicitSatelliteChangeBatchV1Error(
                "atomic no-replace publication is unavailable"
            )
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:  # pragma: no cover - supported execution platforms are Darwin/Linux
        raise ExplicitSatelliteChangeBatchV1Error(
            "atomic no-replace publication is unavailable on this platform"
        )
    if result == 0:
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ExplicitSatelliteChangeBatchV1Error(
            f"late output collision; refusing overwrite: {destination}"
        )
    raise ExplicitSatelliteChangeBatchV1Error(
        "atomic no-replace publication failed: " + os.strerror(error_number)
    )


@lru_cache(maxsize=1)
def _derived_carrier() -> types.ModuleType:
    """Load the pinned generic carrier in an isolated, fail-closed namespace."""

    raw = _exact_file(
        GENERIC_CARRIER_PATH, GENERIC_CARRIER_SHA256, "generic change carrier"
    )
    source = raw.decode("utf-8")
    original = "                os.replace(stage, final)\n"
    replacement = "                _adapter_promote_noreplace(stage, final)\n"
    if source.count(original) != 1:
        raise ExplicitSatelliteChangeBatchV1Error(
            "generic carrier job-promotion site changed"
        )
    derived_source = source.replace(original, replacement)
    module_name = f"{__package__}._satellite_change_batch_explicit_v1_derived"
    module = types.ModuleType(module_name)
    module.__file__ = str(GENERIC_CARRIER_PATH)
    module.__package__ = __package__
    module.__doc__ = "Isolated exact-source derivative for explicit-v1 execution."
    sys.modules[module_name] = module
    try:
        exec(compile(derived_source, str(GENERIC_CARRIER_PATH), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise

    def explicit_validator(queue: Path, catalog: Path) -> Mapping[str, Any]:
        return validate_explicit_change_inputs(queue, catalog)

    def explicit_lineage(
        index: int, root: Path, document: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            return _explicit_catalog_lineage(index, root, document)
        except ExplicitSatelliteChangeBatchV1Error as error:
            raise module.SatelliteChangeBatchError(str(error)) from error

    def promote(stage: Path, destination: Path) -> None:
        try:
            _atomic_promote_noreplace(stage, destination)
        except ExplicitSatelliteChangeBatchV1Error as error:
            raise module.SatelliteChangeBatchError(str(error)) from error

    original_recovery = module._recover_interrupted_run

    def reject_uncheckpointed_publication(
        output: Path,
        document: dict[str, Any],
        inputs: Any,
        config: Any,
        recovered_at: str,
    ) -> None:
        running = [
            task for task in document["jobs"].values() if task["state"] == "running"
        ]
        if running:
            final, _stage = module._task_paths(output, running[0])
            if final.exists() or final.is_symlink():
                raise module.SatelliteChangeBatchError(
                    "unexpected uncheckpointed final output is never adopted"
                )
        original_recovery(output, document, inputs, config, recovered_at)

    module.validate_satellite_batch = explicit_validator
    module._catalog_lineage = explicit_lineage
    module._adapter_promote_noreplace = promote
    module._recover_interrupted_run = reject_uncheckpointed_publication
    module.PROCESSOR_FILES = PROCESSOR_FILES
    module.CHANGE_BATCH_PIPELINE = PIPELINE
    module.CHANGE_SCOPE = {
        **module.CHANGE_SCOPE,
        "automated_promotion_allowed": False,
        "catalog_manifest_sha256": CATALOG_MANIFEST_SHA256,
        "catalog_selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
        "job_promotion": "atomic_no_replace",
        "max_job_attempts": MAX_JOB_ATTEMPTS,
        "represented_active_catalog_jobs": REPRESENTED_ACTIVE_JOB_COUNT,
        "selected_catalog_jobs": SELECTED_JOB_COUNT,
        "selection_mode": "immutable_explicit_catalog_receipt",
        "unexpected_output_adoption": False,
        "unselected_catalog_jobs_pending": UNSELECTED_PENDING_JOB_COUNT,
        "unique_site_claim_created": False,
    }
    return module


@dataclass(frozen=True, slots=True)
class ExplicitChangeBatchConfig:
    """Runtime settings around the immutable one-attempt selection policy."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        for value, field, allow_zero in (
            (self.timeout_seconds, "timeout_seconds", False),
            (
                self.minimum_interval_seconds,
                "minimum_interval_seconds",
                True,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (float(value) < 0 if allow_zero else float(value) <= 0)
            ):
                qualifier = "non-negative" if allow_zero else "positive"
                raise ExplicitSatelliteChangeBatchV1Error(
                    f"{field} must be finite and {qualifier}"
                )
        if not all(
            value not in {float("inf"), float("-inf")} and value == value
            for value in (
                float(self.timeout_seconds),
                float(self.minimum_interval_seconds),
            )
        ):
            raise ExplicitSatelliteChangeBatchV1Error(
                "runtime settings must be finite"
            )
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        object.__setattr__(
            self,
            "minimum_interval_seconds",
            float(self.minimum_interval_seconds),
        )

    def carrier_config(self) -> Any:
        carrier = _derived_carrier()
        return carrier.ChangeBatchConfig(
            timeout_seconds=self.timeout_seconds,
            minimum_interval_seconds=self.minimum_interval_seconds,
            max_job_attempts=MAX_JOB_ATTEMPTS,
        )


def _output_path(value: str | Path) -> Path:
    output = Path(os.path.abspath(os.fspath(value)))
    if output == DEFAULT_QUEUE_PATH.resolve() or output == DEFAULT_CATALOG_RUN_PATH.resolve():
        raise ExplicitSatelliteChangeBatchV1Error(
            "change output must be separate from its frozen inputs"
        )
    return output


def _validate_adapter_contract(document: Mapping[str, Any]) -> None:
    selection = document.get("selection")
    if (
        document.get("pipeline") != PIPELINE
        or not isinstance(selection, Mapping)
        or tuple(selection.get("selected_queue_ids", ())) != SELECTED_QUEUE_IDS
        or tuple(selection.get("include_queue_ids", ())) != SELECTED_QUEUE_IDS
        or selection.get("exclude_queue_ids") != []
        or selection.get("selection_source") is not None
        or selection.get("counts")
        != {
            "catalog_completed_jobs": SELECTED_JOB_COUNT,
            "jobs_selected": SELECTED_JOB_COUNT,
            "catalog_completed_jobs_excluded": 0,
            "catalog_completed_jobs_not_in_inclusion": 0,
            "exclusion_ids_without_completed_catalog": 0,
        }
    ):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit change selection contract changed"
        )
    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping) or tuple(jobs) != SELECTED_QUEUE_IDS:
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit change runnable inventory changed"
        )
    if any(task.get("attempts", 0) > MAX_JOB_ATTEMPTS for task in jobs.values()):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit change task exceeded the one-attempt cap"
        )
    scope = document.get("scope")
    required_scope = {
        "atlas_mutation": False,
        "automated_promotion_allowed": False,
        "imagery_identity_inference": False,
        "imagery_lifecycle_inference": False,
        "imagery_operating_status_inference": False,
        "imagery_power_inference": False,
        "imagery_energy_inference": False,
        "imagery_operator_inference": False,
        "imagery_data_centre_type_inference": False,
        "imagery_it_capacity_inference": False,
        "imagery_pue_inference": False,
        "imagery_workload_inference": False,
        "review_required": True,
        "unexpected_output_adoption": False,
        "unique_site_claim_created": False,
    }
    if not isinstance(scope, Mapping) or any(
        scope.get(key) != value for key, value in required_scope.items()
    ):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit change no-inference scope changed"
        )
    catalogs = document.get("catalog_batches")
    if (
        not isinstance(catalogs, list)
        or len(catalogs) != 1
        or catalogs[0].get("manifest_sha256") != CATALOG_MANIFEST_SHA256
        or catalogs[0].get("selection_receipt_sha256")
        != SELECTION_RECEIPT_SHA256
        or catalogs[0].get("unselected_pending_jobs")
        != UNSELECTED_PENDING_JOB_COUNT
    ):
        raise ExplicitSatelliteChangeBatchV1Error(
            "explicit catalog lineage changed in the change checkpoint"
        )
    if any(run.get("jobs_recovered_after_publish") != 0 for run in document["runs"]):
        raise ExplicitSatelliteChangeBatchV1Error(
            "unexpected output adoption was recorded"
        )


def _is_terminal(document: Mapping[str, Any]) -> bool:
    summary = document["summary"]
    return summary["jobs_pending"] == 0 and summary["jobs_running"] == 0


def _freeze_tree(output: Path) -> None:
    for path in sorted(output.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            raise ExplicitSatelliteChangeBatchV1Error(
                f"refusing to freeze symlinked output: {path}"
            )
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)


def _validate_frozen_tree(output: Path) -> None:
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise ExplicitSatelliteChangeBatchV1Error(
            "terminal explicit change output root is not frozen"
        )
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ExplicitSatelliteChangeBatchV1Error(
                f"terminal explicit change output contains a symlink: {path}"
            )
        expected = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(path.stat().st_mode) != expected:
            raise ExplicitSatelliteChangeBatchV1Error(
                f"terminal explicit change output mode changed: {path}"
            )


def validate_explicit_satellite_change_batch_v1(
    output_directory: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
    config: ExplicitChangeBatchConfig | None = None,
) -> dict[str, Any]:
    """Offline-validate the exact inputs, checkpoint, and completed outputs."""

    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v71 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "explicit catalog run"
    )
    validate_explicit_change_inputs(queue, catalog)
    output = _output_path(output_directory)
    carrier = _derived_carrier()
    carrier_config = config.carrier_config() if config is not None else None
    try:
        document = carrier.validate_satellite_change_batch(
            queue,
            [catalog],
            output,
            config=carrier_config,
            include_queue_ids=SELECTED_QUEUE_IDS,
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV1Error(str(error)) from error
    _validate_adapter_contract(document)
    if _is_terminal(document):
        _validate_frozen_tree(output)
    return document


def execute_explicit_satellite_change_batch_v1(
    output_directory: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
    config: ExplicitChangeBatchConfig | None = None,
    max_jobs: int = SELECTED_JOB_COUNT,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Execute at most the receipt's eleven jobs, once each, then freeze."""

    if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or not 1 <= max_jobs <= 11:
        raise ExplicitSatelliteChangeBatchV1Error(
            "max_jobs must be an integer from 1 through 11"
        )
    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v71 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "explicit catalog run"
    )
    validate_explicit_change_inputs(queue, catalog)
    output = _output_path(output_directory)
    if output.exists() and stat.S_IMODE(output.stat().st_mode) == 0o555:
        return validate_explicit_satellite_change_batch_v1(
            output,
            queue_directory=queue,
            catalog_run_directory=catalog,
            config=config,
        )
    carrier = _derived_carrier()
    settings = config or ExplicitChangeBatchConfig()
    arguments: dict[str, Any] = {
        "config": settings.carrier_config(),
        "include_queue_ids": SELECTED_QUEUE_IDS,
        "max_jobs": max_jobs,
        "command_runner": command_runner,
        "sleep": sleep,
    }
    if timestamp is not None:
        arguments["timestamp"] = timestamp
    try:
        document = carrier.execute_satellite_change_batch(
            queue, [catalog], output, **arguments
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV1Error(str(error)) from error
    _validate_adapter_contract(document)
    if _is_terminal(document):
        _freeze_tree(output)
        return validate_explicit_satellite_change_batch_v1(
            output,
            queue_directory=queue,
            catalog_run_directory=catalog,
            config=settings,
        )
    return document


def output_tree_sha256(output_directory: str | Path = DEFAULT_OUTPUT_PATH) -> str:
    """Return a deterministic path-bound digest of every regular output file."""

    output = _output_path(output_directory)
    entries: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ExplicitSatelliteChangeBatchV1Error(
                f"output tree contains a symlink: {path}"
            )
        if path.is_file():
            raw = path.read_bytes()
            entries.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "bytes": len(raw),
                    "sha256": _sha256(raw),
                }
            )
    payload = (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    return _sha256(payload)


__all__ = [
    "CATALOG_MANIFEST_SHA256",
    "DEFAULT_CATALOG_RUN_PATH",
    "DEFAULT_MINIMUM_INTERVAL_SECONDS",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_QUEUE_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "ExplicitChangeBatchConfig",
    "ExplicitSatelliteChangeBatchV1Error",
    "GENERIC_CARRIER_SHA256",
    "MAX_JOB_ATTEMPTS",
    "PIPELINE",
    "REPRESENTED_ACTIVE_JOB_COUNT",
    "SELECTED_JOB_COUNT",
    "SELECTED_QUEUE_IDS",
    "SELECTION_RECEIPT_SHA256",
    "UNSELECTED_PENDING_JOB_COUNT",
    "execute_explicit_satellite_change_batch_v1",
    "output_tree_sha256",
    "validate_explicit_change_inputs",
    "validate_explicit_satellite_change_batch_v1",
]
