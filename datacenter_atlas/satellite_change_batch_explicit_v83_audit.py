"""Independent offline auditor and publisher for the frozen v83 change stage.

The execution adapter correctly enforced queue order during scheduling, but its
post-run presentation assertion compared canonical-JSON object key order with
queue order.  This auditor preserves and pins those executed processor bytes,
checks effective selection order separately, and treats job objects as a set.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from . import satellite_change_batch_explicit_v83 as execution


class ExplicitSatelliteChangeBatchV83AuditError(ValueError):
    """Raised when the frozen execution or publication contract drifts."""


EXECUTION_ADAPTER_SHA256 = (
    "430b323fb5c20956d5d9b3bde554955d308a3a7459a484fbe0d38f23bcec8942"
)
EXECUTION_SHIM_SHA256 = (
    "b3cb54ce167fac219c60e6e71238e3b92c0198d7d363e13be769a6c6d1d6d064"
)
EXECUTION_SCRIPT_SHA256 = (
    "d08793e43b5c444b74d62e2351565d9d016abd84e41e9b0cf4de67c1a14bd545"
)
STAGE_MANIFEST_SHA256 = (
    "aece77761174823eb4c2a2a58ea5aa85e191dbef28b490ed1de7b57cb12a4828"
)
STAGE_PHYSICAL_TREE_SHA256 = (
    "42b4f1cec01050bb56bf375e74e7c4430e70587bcd94814ee8ccbff43881146a"
)
PUBLICATION_NOT_BEFORE = "2026-07-21T18:37:00Z"


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ExplicitSatelliteChangeBatchV83AuditError(
            f"pinned processor is not a regular file: {path}"
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _processor_checkpoint() -> None:
    expected = {
        execution.PACKAGE_ROOT
        / "datacenter_atlas/satellite_change_batch_explicit_v83.py": (
            EXECUTION_ADAPTER_SHA256
        ),
        execution.PACKAGE_ROOT / "satellite_change_batch_explicit_v83.py": (
            EXECUTION_SHIM_SHA256
        ),
        execution.PACKAGE_ROOT
        / "scripts/run_satellite_change_batch_explicit_v83.py": (
            EXECUTION_SCRIPT_SHA256
        ),
    }
    for path, digest in expected.items():
        if _sha256(path) != digest:
            raise ExplicitSatelliteChangeBatchV83AuditError(
                f"executed processor bytes changed: {path}"
            )


def physical_tree_sha256(root: Path) -> str:
    """Hash paths, types, modes, sizes, and file bytes."""

    if root.is_symlink() or not root.is_dir():
        raise ExplicitSatelliteChangeBatchV83AuditError(
            f"tree root must be a regular directory: {root}"
        )
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        metadata = path.stat(follow_symlinks=False)
        mode = stat.S_IMODE(metadata.st_mode)
        if path.is_symlink():
            raise ExplicitSatelliteChangeBatchV83AuditError(
                f"tree contains symlink: {relative}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif stat.S_ISREG(metadata.st_mode):
            raw = path.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                f"{hashlib.sha256(raw).hexdigest()}\n".encode()
            )
        else:
            raise ExplicitSatelliteChangeBatchV83AuditError(
                f"tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def _tree_checkpoint(root: Path) -> None:
    manifest = root / "batch-manifest.json"
    if _sha256(manifest) != STAGE_MANIFEST_SHA256:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "frozen v83 stage manifest changed"
        )
    if physical_tree_sha256(root) != STAGE_PHYSICAL_TREE_SHA256:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "frozen v83 stage physical tree changed"
        )


def _corrected_contract(document: Mapping[str, Any]) -> None:
    selection = document.get("selection")
    if (
        document.get("pipeline") != execution.PIPELINE
        or not isinstance(selection, Mapping)
        or tuple(selection.get("selected_queue_ids", ()))
        != execution.SELECTED_QUEUE_IDS
        or tuple(selection.get("include_queue_ids", ()))
        != execution.SELECTED_QUEUE_IDS
        or tuple(selection.get("exclude_queue_ids", ()))
        != execution.EXCLUDED_QUEUE_IDS
        or selection.get("selection_source")
        != {
            "bytes": 229,
            "file": execution.EXCLUSION_PATH.name,
            "kind": "canonical_exclusion_file",
            "sha256": execution.EXCLUSION_SHA256,
        }
        or selection.get("counts")
        != {
            "catalog_completed_jobs": 3,
            "catalog_completed_jobs_excluded": 0,
            "catalog_completed_jobs_not_in_inclusion": 0,
            "exclusion_ids_without_completed_catalog": 1,
            "jobs_selected": 3,
        }
    ):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 effective selection or exclusion changed"
        )
    jobs = document.get("jobs")
    if (
        not isinstance(jobs, Mapping)
        or set(jobs) != set(execution.SELECTED_QUEUE_IDS)
        or len(jobs) != execution.SELECTED_JOB_COUNT
    ):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 runnable job set changed"
        )
    for queue_id in execution.SELECTED_QUEUE_IDS:
        task = jobs[queue_id]
        if (
            task.get("attempts") != 1
            or task.get("state") not in {"completed", "failed"}
            or task.get("priority", {}).get("tier") != "active_construction"
        ):
            raise ExplicitSatelliteChangeBatchV83AuditError(
                f"v83 terminal task contract changed: {queue_id}"
            )
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
    scope = document.get("scope")
    if (
        not isinstance(scope, Mapping)
        or any(scope.get(field) is not False for field in required_false)
        or scope.get("review_required") is not True
        or scope.get("catalog_unavailable_excluded_queue_ids")
        != list(execution.EXCLUDED_QUEUE_IDS)
    ):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 review-only scope changed"
        )
    catalogs = document.get("catalog_batches")
    if (
        not isinstance(catalogs, list)
        or len(catalogs) != 1
        or catalogs[0].get("manifest_sha256")
        != execution.CATALOG_MANIFEST_SHA256
        or catalogs[0].get("selection_receipt_sha256")
        != execution.SELECTION_RECEIPT_SHA256
        or catalogs[0].get("jobs_completed") != 3
        or catalogs[0].get("jobs_unavailable_no_scene") != 1
        or catalogs[0].get("unavailable_excluded_queue_ids")
        != list(execution.EXCLUDED_QUEUE_IDS)
    ):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 catalog lineage changed"
        )
    summary = document.get("summary")
    if (
        not isinstance(summary, Mapping)
        or summary.get("jobs_pending") != 0
        or summary.get("jobs_running") != 0
        or summary.get("jobs_selected") != 3
        or summary.get("exclusion_ids_without_completed_catalog") != 1
    ):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 terminal accounting changed"
        )
    if any(run.get("jobs_recovered_after_publish") != 0 for run in document["runs"]):
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "unexpected output adoption was recorded"
        )


def validate_explicit_satellite_change_batch_v83_audit(
    output_directory: str | Path = execution.DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Validate exact inputs, runtime, processor bytes, checkpoint, and assets."""

    execution._runtime_checkpoint()
    _processor_checkpoint()
    execution.validate_explicit_change_inputs_v83()
    output = Path(os.path.abspath(os.fspath(output_directory)))
    _tree_checkpoint(output)
    carrier = execution._derived_carrier()
    try:
        document = carrier.validate_satellite_change_batch(
            execution.DEFAULT_QUEUE_PATH,
            [execution.DEFAULT_CATALOG_RUN_PATH],
            output,
            config=execution.ExplicitChangeBatchV83Config().carrier_config(),
            include_queue_ids=execution.SELECTED_QUEUE_IDS,
            exclusion_file=execution.EXCLUSION_PATH,
        )
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV83AuditError(str(error)) from error
    _corrected_contract(document)
    execution._validate_frozen_tree(output)
    return document


def publish_explicit_satellite_change_batch_v83_audit() -> dict[str, Any]:
    """Atomically move the validated frozen stage to the absent final path."""

    stage = execution.DEFAULT_STAGE_PATH
    output = execution.DEFAULT_OUTPUT_PATH
    boundary = datetime.fromisoformat(PUBLICATION_NOT_BEFORE.replace("Z", "+00:00"))
    if datetime.now(UTC) < boundary:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            f"publication boundary has not arrived: {PUBLICATION_NOT_BEFORE}"
        )
    if output.exists() or output.is_symlink():
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 final change path already exists"
        )
    initial = stage.stat(follow_symlinks=False)
    identity = (initial.st_dev, initial.st_ino)
    for path in (stage, *stage.rglob("*")):
        if path.stat(follow_symlinks=False).st_mtime > boundary.timestamp():
            raise ExplicitSatelliteChangeBatchV83AuditError(
                f"stage entry is newer than publication boundary: {path}"
            )
    document = validate_explicit_satellite_change_batch_v83_audit(stage)
    current = stage.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino) != identity:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 stage identity changed during validation"
        )
    _tree_checkpoint(stage)
    if output.exists() or output.is_symlink():
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 final change path already exists"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        execution._atomic_promote_noreplace(stage, output)
    except Exception as error:
        raise ExplicitSatelliteChangeBatchV83AuditError(str(error)) from error
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "published v83 final root is not frozen"
        )
    published = output.stat(follow_symlinks=False)
    if (published.st_dev, published.st_ino) != identity:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "published v83 final has a different filesystem identity"
        )
    if published.st_ctime < boundary.timestamp():
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "published v83 final predates its declared boundary"
        )
    _tree_checkpoint(output)
    validated = validate_explicit_satellite_change_batch_v83_audit(output)
    if validated != document:
        raise ExplicitSatelliteChangeBatchV83AuditError(
            "v83 checkpoint changed during publication"
        )
    return validated


__all__ = [
    "EXECUTION_ADAPTER_SHA256",
    "EXECUTION_SCRIPT_SHA256",
    "EXECUTION_SHIM_SHA256",
    "ExplicitSatelliteChangeBatchV83AuditError",
    "PUBLICATION_NOT_BEFORE",
    "STAGE_MANIFEST_SHA256",
    "STAGE_PHYSICAL_TREE_SHA256",
    "publish_explicit_satellite_change_batch_v83_audit",
    "physical_tree_sha256",
    "validate_explicit_satellite_change_batch_v83_audit",
]
