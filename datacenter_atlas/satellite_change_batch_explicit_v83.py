"""Strict visible-change runner for the accepted v83 catalog tranche.

The adapter pins the queue, four-attempt catalog receipt, catalog payloads,
processor source, and numerical runtime.  Only the three catalog-complete
project jobs are executable.  The unavailable Jashore job remains explicitly
excluded and accounted for.  Outputs are review-only visible-change proposals.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as distribution_version
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import time
import types
from typing import Any, Callable, Mapping

from .satellite_batch_explicit_v83 import (
    ExplicitV83BatchConfig,
    validate_explicit_satellite_batch_v83,
)
from .satellite_change_batch_explicit_v1 import (
    _atomic_promote_noreplace,
    _freeze_tree,
    _validate_frozen_tree,
)


class ExplicitSatelliteChangeBatchV83Error(ValueError):
    """Raised when a pinned input, runtime, checkpoint, or output drifts."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = PACKAGE_ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
DEFAULT_CATALOG_RUN_PATH = (
    PACKAGE_ROOT
    / "satellite_review_runs/2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1"
)
DEFAULT_STAGE_PATH = (
    PACKAGE_ROOT
    / "satellite_change_runs/2026-07-21-open-seed-v83-active-explicit-new-projects-001"
)
DEFAULT_OUTPUT_PATH = (
    PACKAGE_ROOT
    / "satellite_change_runs/2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1"
)
EXCLUSION_PATH = (
    PACKAGE_ROOT
    / "satellite_change_selections/2026-07-21-open-seed-v83-jashore-unavailable-v1.json"
)
GENERIC_CARRIER_PATH = PACKAGE_ROOT / "datacenter_atlas/satellite_change_batch.py"
CATALOG_VALIDATOR_PATH = (
    PACKAGE_ROOT / "datacenter_atlas/satellite_batch_explicit_v83.py"
)
V1_HELPER_PATH = (
    PACKAGE_ROOT / "datacenter_atlas/satellite_change_batch_explicit_v1.py"
)

GENERIC_CARRIER_SHA256 = (
    "01e8a6e27f2cca5fbcb95f95b2b6394419d0d95dd45c1210dc1549272b278ef3"
)
CATALOG_VALIDATOR_SHA256 = (
    "a7fdc30eccad02657612d9c01fd9739a432da74454be890f77825e4111605e83"
)
V1_HELPER_SHA256 = (
    "82fc7b814dc5cb26c1317d634ba0d0c95ae81e43ec05ff5f0e9d28f33128d372"
)
QUEUE_MANIFEST_SHA256 = (
    "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd"
)
QUEUE_MANIFEST_SIDECAR_SHA256 = (
    "9554a659b8b51925377bc31e99fa29a6fda92a5aa4675c48164d3de28e583288"
)
QUEUE_SHA256 = (
    "8792ee2d80ed9b44d3ef67d3511b29ca0f9160b8ebd641e7f54cf4f5db4e4251"
)
CATALOG_MANIFEST_SHA256 = (
    "d8c99c8cd5f82f8474c4f7f0ab0ef5b002555583d083b6664ed5ae600b477a48"
)
SELECTION_RECEIPT_SHA256 = (
    "ea98a8ceb3d3b457e84e1ae0db06ed28c12e39437c649c50f8c495dc3041fc45"
)
SELECTION_RECEIPT_SIDECAR_SHA256 = (
    "4009e5e33a6228fced49da22bab1c88723725f0caf46b3f00bf74ffcad583ba8"
)
EXCLUSION_SHA256 = (
    "d0b793134165e081b22a1c0d147072c821ea7ef2879744ec7334cc9348d09135"
)

PIPELINE = "satellite_review_change_batch_explicit_v83_v1"
CATALOG_SELECTED_QUEUE_IDS = (
    "satq-3149584b9d40a3049b84371e",
    "satq-c92ac430b054e36342ee99ed",
    "satq-44d8e1c44fea11bc4dc51efd",
    "satq-930a02278f48494c659e3e76",
)
SELECTED_QUEUE_IDS = (
    "satq-c92ac430b054e36342ee99ed",
    "satq-44d8e1c44fea11bc4dc51efd",
    "satq-930a02278f48494c659e3e76",
)
EXCLUDED_QUEUE_IDS = ("satq-3149584b9d40a3049b84371e",)
SELECTED_JOB_COUNT = len(SELECTED_QUEUE_IDS)
REPRESENTED_ACTIVE_JOB_COUNT = 104
CATALOG_SELECTED_JOB_COUNT = 4
CATALOG_UNAVAILABLE_JOB_COUNT = 1
UNSELECTED_PENDING_JOB_COUNT = 100
MAX_JOB_ATTEMPTS = 1
DEFAULT_TIMEOUT_SECONDS = 1_800.0
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.1

PINNED_RUNTIME = {
    "python_implementation": "CPython",
    "python_version": "3.12.13",
    "packages": {
        "numpy": "2.5.1",
        "Pillow": "12.3.0",
        "rasterio": "1.5.0",
    },
}

PROCESSOR_FILES = (
    "datacenter_atlas/satellite_change_batch_explicit_v83.py",
    "satellite_change_batch_explicit_v83.py",
    "scripts/run_satellite_change_batch_explicit_v83.py",
    "datacenter_atlas/satellite_change_batch.py",
    "datacenter_atlas/satellite_batch_explicit_v83.py",
    "satellite_batch_explicit_v83.py",
    "datacenter_atlas/satellite_change_batch_explicit_v1.py",
    "datacenter_atlas/satellite_batch.py",
    "datacenter_atlas/satellite_queue_v83.py",
    "satellite_queue_v83.py",
    "datacenter_atlas/satellite_queue.py",
    "datacenter_atlas/satellite_change.py",
    "datacenter_atlas/satellite_catalog.py",
    "datacenter_atlas/models.py",
    "scripts/sentinel_change.py",
    "satellite_change_selections/2026-07-21-open-seed-v83-jashore-unavailable-v1.json",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_file(path: Path, expected_sha256: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise ExplicitSatelliteChangeBatchV83Error(f"{label} changed")
    return raw


def _exact_directory(value: str | Path, expected: Path, label: str) -> Path:
    path = Path(os.path.abspath(os.fspath(value)))
    if path.is_symlink() or not path.is_dir():
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} must be a regular non-symlink directory"
        )
    if path.resolve() != expected.resolve():
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} must be the pinned {expected.resolve()}"
        )
    return path.resolve()


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} is not UTF-8"
        ) from error

    def reject_constant(value: str) -> None:
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitSatelliteChangeBatchV83Error(
            f"{label} is not valid JSON"
        ) from error


def _runtime_checkpoint() -> None:
    if (
        platform.python_implementation() != PINNED_RUNTIME["python_implementation"]
        or platform.python_version() != PINNED_RUNTIME["python_version"]
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "machine change requires the pinned CPython 3.12.13 runtime"
        )
    for distribution, expected in PINNED_RUNTIME["packages"].items():
        try:
            actual = distribution_version(distribution)
        except PackageNotFoundError as error:
            raise ExplicitSatelliteChangeBatchV83Error(
                f"required pinned package is absent: {distribution}"
            ) from error
        if actual != expected:
            raise ExplicitSatelliteChangeBatchV83Error(
                f"pinned package changed: {distribution} {actual} != {expected}"
            )


def validate_explicit_change_inputs_v83(
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
) -> dict[str, Any]:
    """Offline-validate the exact queue, catalog receipt, and exclusion."""

    _runtime_checkpoint()
    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v83 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "v83 catalog run"
    )
    _exact_file(GENERIC_CARRIER_PATH, GENERIC_CARRIER_SHA256, "generic carrier")
    _exact_file(
        CATALOG_VALIDATOR_PATH,
        CATALOG_VALIDATOR_SHA256,
        "v83 catalog validator",
    )
    _exact_file(V1_HELPER_PATH, V1_HELPER_SHA256, "no-replace helper")
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
        "v83 catalog manifest",
    )
    receipt_raw = _exact_file(
        catalog / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "v83 selection receipt",
    )
    _exact_file(
        catalog / "selection-receipt.sha256",
        SELECTION_RECEIPT_SIDECAR_SHA256,
        "v83 selection receipt sidecar",
    )
    exclusion_raw = _exact_file(
        EXCLUSION_PATH, EXCLUSION_SHA256, "Jashore exclusion receipt"
    )
    try:
        document = validate_explicit_satellite_batch_v83(
            queue, catalog, config=ExplicitV83BatchConfig()
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV83Error(
            f"v83 catalog run failed offline validation: {error}"
        ) from error
    if _strict_json(manifest_raw, "v83 catalog manifest") != document:
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 catalog validator returned a different manifest"
        )
    receipt = _strict_json(receipt_raw, "v83 selection receipt")
    selection = receipt.get("selection") if isinstance(receipt, Mapping) else None
    if (
        not isinstance(selection, Mapping)
        or tuple(selection.get("selected_queue_ids", ()))
        != CATALOG_SELECTED_QUEUE_IDS
        or selection.get("selected_jobs_count") != CATALOG_SELECTED_JOB_COUNT
        or selection.get("unselected_pending_jobs")
        != UNSELECTED_PENDING_JOB_COUNT
        or receipt.get("representation", {}).get("represented_jobs")
        != REPRESENTED_ACTIVE_JOB_COUNT
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 catalog selection receipt changed"
        )
    summary = document.get("summary")
    expected_summary = {
        "jobs_completed": 3,
        "jobs_failed": 0,
        "jobs_not_selected": 100,
        "jobs_pending": 100,
        "jobs_represented": 104,
        "jobs_selected_for_execution": 4,
        "jobs_unavailable_no_scene": 1,
        "selected_jobs_completed": 3,
        "selected_jobs_failed": 0,
        "selected_jobs_pending": 0,
        "selected_jobs_unavailable_no_scene": 1,
    }
    if summary != expected_summary:
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 catalog terminal accounting changed"
        )
    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping) or len(jobs) != REPRESENTED_ACTIVE_JOB_COUNT:
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 catalog represented inventory changed"
        )
    for queue_id in SELECTED_QUEUE_IDS:
        task = jobs.get(queue_id)
        if (
            not isinstance(task, Mapping)
            or task.get("state") != "completed"
            or task.get("attempts") != 1
            or not isinstance(task.get("selected_ids"), Mapping)
            or not isinstance(task.get("artifacts"), Mapping)
        ):
            raise ExplicitSatelliteChangeBatchV83Error(
                f"change-eligible catalog job changed: {queue_id}"
            )
    unavailable = jobs.get(EXCLUDED_QUEUE_IDS[0])
    if (
        not isinstance(unavailable, Mapping)
        or unavailable.get("state") != "unavailable_no_scene"
        or unavailable.get("attempts") != 1
        or unavailable.get("selected_ids") is not None
        or unavailable.get("artifacts") is not None
        or unavailable.get("unavailability", {}).get("outcome")
        != "unavailable_no_scene"
        or unavailable.get("unavailability", {}).get("window") != "baseline"
        or unavailable.get("unavailability", {}).get("raw_reason")
        != "no scene falls within the baseline temporal window"
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "Jashore unavailability accounting changed"
        )
    exclusion = _strict_json(exclusion_raw, "Jashore exclusion receipt")
    if exclusion != {
        "purpose": "satellite_change_batch_exclusions",
        "queue_ids": list(EXCLUDED_QUEUE_IDS),
        "queue_manifest_sha256": QUEUE_MANIFEST_SHA256,
        "schema_version": 1,
    }:
        raise ExplicitSatelliteChangeBatchV83Error(
            "Jashore exclusion receipt changed"
        )
    return document


def _catalog_lineage(
    index: int,
    root: Path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    if index != 0 or root.resolve() != DEFAULT_CATALOG_RUN_PATH.resolve():
        raise ExplicitSatelliteChangeBatchV83Error(
            "only the single pinned v83 catalog run is allowed"
        )
    raw = _exact_file(
        root / "batch-manifest.json",
        CATALOG_MANIFEST_SHA256,
        "v83 catalog manifest",
    )
    if _strict_json(raw, "v83 catalog manifest") != document:
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 catalog manifest changed after validation"
        )
    receipt_raw = _exact_file(
        root / "selection-receipt.json",
        SELECTION_RECEIPT_SHA256,
        "v83 selection receipt",
    )
    sidecar_raw = _exact_file(
        root / "selection-receipt.sha256",
        SELECTION_RECEIPT_SIDECAR_SHA256,
        "v83 selection receipt sidecar",
    )
    return {
        "index": 0,
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
        "jobs_selected": CATALOG_SELECTED_JOB_COUNT,
        "jobs_completed": SELECTED_JOB_COUNT,
        "jobs_unavailable_no_scene": CATALOG_UNAVAILABLE_JOB_COUNT,
        "jobs_failed": 0,
        "jobs_pending": UNSELECTED_PENDING_JOB_COUNT,
        "selected_jobs_pending": 0,
        "unselected_pending_jobs": UNSELECTED_PENDING_JOB_COUNT,
        "unavailable_excluded_queue_ids": list(EXCLUDED_QUEUE_IDS),
        "selection_receipt_file": "selection-receipt.json",
        "selection_receipt_bytes": len(receipt_raw),
        "selection_receipt_sha256": SELECTION_RECEIPT_SHA256,
        "selection_receipt_sidecar_file": "selection-receipt.sha256",
        "selection_receipt_sidecar_bytes": len(sidecar_raw),
        "selection_receipt_sidecar_sha256": SELECTION_RECEIPT_SIDECAR_SHA256,
    }


@lru_cache(maxsize=1)
def _derived_carrier() -> types.ModuleType:
    """Load the exact generic carrier with only strict adapter hooks changed."""

    raw = _exact_file(
        GENERIC_CARRIER_PATH, GENERIC_CARRIER_SHA256, "generic change carrier"
    )
    source = raw.decode("utf-8")
    original = "                os.replace(stage, final)\n"
    replacement = "                _adapter_promote_noreplace(stage, final)\n"
    if source.count(original) != 1:
        raise ExplicitSatelliteChangeBatchV83Error(
            "generic carrier job-promotion site changed"
        )
    derived_source = source.replace(original, replacement)
    module_name = f"{__package__}._satellite_change_batch_explicit_v83_derived"
    module = types.ModuleType(module_name)
    module.__file__ = str(GENERIC_CARRIER_PATH)
    module.__package__ = __package__
    module.__doc__ = "Exact-source derivative for explicit v83 execution."
    sys.modules[module_name] = module
    try:
        exec(compile(derived_source, str(GENERIC_CARRIER_PATH), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise

    def explicit_validator(queue: Path, catalog: Path) -> Mapping[str, Any]:
        return validate_explicit_change_inputs_v83(queue, catalog)

    def explicit_lineage(
        index: int, root: Path, document: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            return _catalog_lineage(index, root, document)
        except ExplicitSatelliteChangeBatchV83Error as error:
            raise module.SatelliteChangeBatchError(str(error)) from error

    def promote(stage: Path, destination: Path) -> None:
        try:
            _atomic_promote_noreplace(stage, destination)
        except Exception as error:
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
        "catalog_unavailable_excluded_queue_ids": list(EXCLUDED_QUEUE_IDS),
        "catalog_unavailable_job_count": CATALOG_UNAVAILABLE_JOB_COUNT,
        "job_promotion": "atomic_no_replace",
        "max_job_attempts": MAX_JOB_ATTEMPTS,
        "represented_active_catalog_jobs": REPRESENTED_ACTIVE_JOB_COUNT,
        "selected_catalog_jobs": CATALOG_SELECTED_JOB_COUNT,
        "change_executable_catalog_jobs": SELECTED_JOB_COUNT,
        "selection_mode": "explicit_completed_inclusion_plus_unavailable_exclusion",
        "selection_exclusion_sha256": EXCLUSION_SHA256,
        "unexpected_output_adoption": False,
        "unique_site_claim_created": False,
    }
    return module


@dataclass(frozen=True, slots=True)
class ExplicitChangeBatchV83Config:
    """Runtime settings around the fixed three-job, one-attempt policy."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        for value, field, allow_zero in (
            (self.timeout_seconds, "timeout_seconds", False),
            (self.minimum_interval_seconds, "minimum_interval_seconds", True),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (float(value) < 0 if allow_zero else float(value) <= 0)
                or float(value) in {float("inf"), float("-inf")}
                or float(value) != float(value)
            ):
                qualifier = "non-negative" if allow_zero else "positive"
                raise ExplicitSatelliteChangeBatchV83Error(
                    f"{field} must be finite and {qualifier}"
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
    if output in {DEFAULT_QUEUE_PATH.resolve(), DEFAULT_CATALOG_RUN_PATH.resolve()}:
        raise ExplicitSatelliteChangeBatchV83Error(
            "change output must be separate from frozen inputs"
        )
    return output


def _validate_adapter_contract(document: Mapping[str, Any]) -> None:
    selection = document.get("selection")
    expected_counts = {
        "catalog_completed_jobs": 3,
        "jobs_selected": 3,
        "catalog_completed_jobs_excluded": 0,
        "catalog_completed_jobs_not_in_inclusion": 0,
        "exclusion_ids_without_completed_catalog": 1,
    }
    if (
        document.get("pipeline") != PIPELINE
        or not isinstance(selection, Mapping)
        or tuple(selection.get("selected_queue_ids", ())) != SELECTED_QUEUE_IDS
        or tuple(selection.get("include_queue_ids", ())) != SELECTED_QUEUE_IDS
        or tuple(selection.get("exclude_queue_ids", ())) != EXCLUDED_QUEUE_IDS
        or selection.get("selection_source")
        != {
            "kind": "canonical_exclusion_file",
            "file": EXCLUSION_PATH.name,
            "bytes": 229,
            "sha256": EXCLUSION_SHA256,
        }
        or selection.get("counts") != expected_counts
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "explicit v83 change selection contract changed"
        )
    jobs = document.get("jobs")
    if not isinstance(jobs, Mapping) or tuple(jobs) != SELECTED_QUEUE_IDS:
        raise ExplicitSatelliteChangeBatchV83Error(
            "explicit v83 change runnable inventory changed"
        )
    if any(task.get("attempts", 0) > MAX_JOB_ATTEMPTS for task in jobs.values()):
        raise ExplicitSatelliteChangeBatchV83Error(
            "explicit v83 change task exceeded the one-attempt cap"
        )
    scope = document.get("scope")
    required_false = (
        "atlas_mutation",
        "automated_promotion_allowed",
        "imagery_identity_inference",
        "imagery_lifecycle_inference",
        "imagery_operating_status_inference",
        "imagery_power_inference",
        "imagery_energy_inference",
        "imagery_operator_inference",
        "imagery_data_centre_type_inference",
        "imagery_it_capacity_inference",
        "imagery_pue_inference",
        "imagery_workload_inference",
        "unexpected_output_adoption",
        "unique_site_claim_created",
    )
    if (
        not isinstance(scope, Mapping)
        or any(scope.get(field) is not False for field in required_false)
        or scope.get("review_required") is not True
        or scope.get("catalog_unavailable_excluded_queue_ids")
        != list(EXCLUDED_QUEUE_IDS)
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "explicit v83 change no-inference scope changed"
        )
    catalogs = document.get("catalog_batches")
    if (
        not isinstance(catalogs, list)
        or len(catalogs) != 1
        or catalogs[0].get("manifest_sha256") != CATALOG_MANIFEST_SHA256
        or catalogs[0].get("selection_receipt_sha256")
        != SELECTION_RECEIPT_SHA256
        or catalogs[0].get("jobs_completed") != SELECTED_JOB_COUNT
        or catalogs[0].get("jobs_unavailable_no_scene")
        != CATALOG_UNAVAILABLE_JOB_COUNT
        or catalogs[0].get("unavailable_excluded_queue_ids")
        != list(EXCLUDED_QUEUE_IDS)
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "explicit v83 catalog lineage changed in the change checkpoint"
        )
    if any(run.get("jobs_recovered_after_publish") != 0 for run in document["runs"]):
        raise ExplicitSatelliteChangeBatchV83Error(
            "unexpected output adoption was recorded"
        )


def _is_terminal(document: Mapping[str, Any]) -> bool:
    summary = document["summary"]
    return summary["jobs_pending"] == 0 and summary["jobs_running"] == 0


def validate_explicit_satellite_change_batch_v83(
    output_directory: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
    config: ExplicitChangeBatchV83Config | None = None,
) -> dict[str, Any]:
    """Offline-validate the exact inputs, checkpoint, and output bytes."""

    _runtime_checkpoint()
    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v83 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "v83 catalog run"
    )
    validate_explicit_change_inputs_v83(queue, catalog)
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
            exclusion_file=EXCLUSION_PATH,
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV83Error(str(error)) from error
    _validate_adapter_contract(document)
    if _is_terminal(document):
        _validate_frozen_tree(output)
    return document


def execute_explicit_satellite_change_batch_v83(
    output_directory: str | Path = DEFAULT_STAGE_PATH,
    *,
    queue_directory: str | Path = DEFAULT_QUEUE_PATH,
    catalog_run_directory: str | Path = DEFAULT_CATALOG_RUN_PATH,
    config: ExplicitChangeBatchV83Config | None = None,
    max_jobs: int = SELECTED_JOB_COUNT,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    timestamp: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Run at most the exact three completed catalog jobs, once each."""

    _runtime_checkpoint()
    if (
        isinstance(max_jobs, bool)
        or not isinstance(max_jobs, int)
        or not 1 <= max_jobs <= SELECTED_JOB_COUNT
    ):
        raise ExplicitSatelliteChangeBatchV83Error(
            "max_jobs must be an integer from 1 through 3"
        )
    queue = _exact_directory(queue_directory, DEFAULT_QUEUE_PATH, "v83 queue")
    catalog = _exact_directory(
        catalog_run_directory, DEFAULT_CATALOG_RUN_PATH, "v83 catalog run"
    )
    validate_explicit_change_inputs_v83(queue, catalog)
    output = _output_path(output_directory)
    if output.exists() and stat.S_IMODE(output.stat().st_mode) == 0o555:
        return validate_explicit_satellite_change_batch_v83(
            output,
            queue_directory=queue,
            catalog_run_directory=catalog,
            config=config,
        )
    carrier = _derived_carrier()
    settings = config or ExplicitChangeBatchV83Config()
    arguments: dict[str, Any] = {
        "config": settings.carrier_config(),
        "include_queue_ids": SELECTED_QUEUE_IDS,
        "exclusion_file": EXCLUSION_PATH,
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
        raise ExplicitSatelliteChangeBatchV83Error(str(error)) from error
    _validate_adapter_contract(document)
    if _is_terminal(document):
        _freeze_tree(output)
        return validate_explicit_satellite_change_batch_v83(
            output,
            queue_directory=queue,
            catalog_run_directory=catalog,
            config=settings,
        )
    return document


def publish_explicit_satellite_change_batch_v83(
    stage_directory: str | Path = DEFAULT_STAGE_PATH,
    output_directory: str | Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Atomically publish a terminal frozen stage without replacement."""

    stage = _output_path(stage_directory)
    output = _output_path(output_directory)
    if stage.resolve() != DEFAULT_STAGE_PATH.resolve():
        raise ExplicitSatelliteChangeBatchV83Error(
            "only the pinned v83 change stage may be published"
        )
    if output.resolve(strict=False) != DEFAULT_OUTPUT_PATH.resolve(strict=False):
        raise ExplicitSatelliteChangeBatchV83Error(
            "only the pinned v83 final path may be published"
        )
    document = validate_explicit_satellite_change_batch_v83(stage)
    if not _is_terminal(document):
        raise ExplicitSatelliteChangeBatchV83Error(
            "non-terminal change stage cannot be published"
        )
    if output.exists() or output.is_symlink():
        raise ExplicitSatelliteChangeBatchV83Error(
            "v83 final change output already exists"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_promote_noreplace(stage, output)
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV83Error(str(error)) from error
    return validate_explicit_satellite_change_batch_v83(output)


def output_tree_sha256(output_directory: str | Path = DEFAULT_OUTPUT_PATH) -> str:
    """Return the deterministic path-bound digest of all regular files."""

    output = _output_path(output_directory)
    entries: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ExplicitSatelliteChangeBatchV83Error(
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
    payload = (
        json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return _sha256(payload)


__all__ = [
    "CATALOG_MANIFEST_SHA256",
    "CATALOG_UNAVAILABLE_JOB_COUNT",
    "DEFAULT_CATALOG_RUN_PATH",
    "DEFAULT_MINIMUM_INTERVAL_SECONDS",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_QUEUE_PATH",
    "DEFAULT_STAGE_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "EXCLUDED_QUEUE_IDS",
    "ExplicitChangeBatchV83Config",
    "ExplicitSatelliteChangeBatchV83Error",
    "MAX_JOB_ATTEMPTS",
    "PINNED_RUNTIME",
    "PIPELINE",
    "REPRESENTED_ACTIVE_JOB_COUNT",
    "SELECTED_JOB_COUNT",
    "SELECTED_QUEUE_IDS",
    "SELECTION_RECEIPT_SHA256",
    "UNSELECTED_PENDING_JOB_COUNT",
    "execute_explicit_satellite_change_batch_v83",
    "output_tree_sha256",
    "publish_explicit_satellite_change_batch_v83",
    "validate_explicit_change_inputs_v83",
    "validate_explicit_satellite_change_batch_v83",
]
