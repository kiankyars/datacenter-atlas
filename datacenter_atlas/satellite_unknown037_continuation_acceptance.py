"""Accept one sealed Unknown037 catalog-only satellite continuation.

Unknown037 is an APFS copy-on-write continuation of accepted Unknown036.  Its
only payload changes are the batch manifest, 24 catalog-result triples, and
one explicit ``unavailable_no_scene`` checkpoint.  Acceptance is offline: this
module performs no network request, downloads no imagery, runs no computer
vision, and creates no identity, lifecycle, type, capacity, power, energy,
operator, map, coverage, construction-master, completeness, or parity claim.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from . import satellite_batch as batch
from . import satellite_batch_recovery as recovery


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-18-global-open-v3"
SOURCE = ROOT / "satellite_review_runs/2026-07-22-global-open-v3-unknown-036"
DESTINATION = ROOT / "satellite_review_runs/2026-07-22-global-open-v3-unknown-037"
DESTINATION_LOCK = DESTINATION.with_name(f"{DESTINATION.name}.lock")
SOURCE_ACCEPTANCE = (
    ROOT / "satellite_review_continuations/"
    "2026-07-22-global-open-v3-unknown-036-continued-25"
)

ARTIFACT_ID = "2026-07-22-global-open-v3-unknown-037-continued-25"
OUTPUT = ROOT / "satellite_review_continuations" / ARTIFACT_ID
ACCEPTED_AT = "2026-07-22T06:17:00Z"

MANIFEST_FILENAME = "continuation-manifest.json"
SIDECAR_FILENAME = "manifest.sha256"
SOURCE_INVENTORY_FILENAME = "source-tree.inventory"
DESTINATION_INVENTORY_FILENAME = "destination-tree.inventory"
DELTA_FILENAME = "clone-delta.json"
CONTENT_FILENAMES = (
    SOURCE_INVENTORY_FILENAME,
    DESTINATION_INVENTORY_FILENAME,
    DELTA_FILENAME,
)
CLOSED_FILENAMES = frozenset((*CONTENT_FILENAMES, MANIFEST_FILENAME, SIDECAR_FILENAME))

SOURCE_BATCH_PIN = (
    6_519_285,
    "12c5231a1770b269acce3aa5edf37ca0b950caa119ed5d361bbec5c0fd9b26c8",
)
DESTINATION_BATCH_PIN = (
    6_535_665,
    "8243bab467d4b9d661315b22b8cd54fc19de3de2afadf686ff0c1e1d63dd665e",
)
SOURCE_ACCEPTANCE_MANIFEST_PIN = (
    10_023,
    "fed0d7d0176af0eda611f7c1a403b827e85db892eac00114eae35451ee2a1088",
)
SOURCE_ACCEPTANCE_SIDECAR_PIN = (
    93,
    "6460bd11f146a71ab89446bfaf131dd1e900ca98c52bb79f0bafea05f65d3b28",
)
QUEUE_MANIFEST_PIN = (
    28_269,
    "58c39d64510f37fda8eaf6912ed36001845f276239dcaeec0ea24ba4a6a2836c",
)
QUEUE_FILE_PIN = (
    18_238_365,
    "6889779b817d7822e02745261699c9e2eac8860f5c1d617662882770798764be",
)
RUNNER_PINS: Mapping[str, tuple[int, str]] = {
    "datacenter_atlas/satellite_catalog.py": (
        28_132,
        "16a22c0e20e973a23e153f0611366d284c9db198cf4533268df9ac8a3e040087",
    ),
    "scripts/catalog_satellite.py": (
        9_646,
        "6aaef442995f1f9c5f1b77f1f9ae6969f2f6a6795d47d26c6ac3fa255f2e1833",
    ),
    "scripts/run_satellite_review_queue.py": (
        7_338,
        "626c271fca3cb6d724494688a3c7149bf217936c784d37000a0a13366743be23",
    ),
    "datacenter_atlas/satellite_batch.py": (
        59_984,
        "b57497568a5268637828a30cc43c19f457c0e89d0428ee3ac08e9ea01b54fbba",
    ),
}

SOURCE_INVENTORY = {
    "bytes": 3_132_875_874,
    "canonicalization": ("UTF-8 path NUL decimal-bytes NUL lowercase-SHA-256 newline"),
    "directories": 9_233,
    "files": 13_584,
    "sha256": "6f51009a26f4c1e175236d201efbee6f89fae41eaff5abe74ad762f86cd445ba",
}
DESTINATION_INVENTORY = {
    "bytes": 3_146_051_663,
    "canonicalization": ("UTF-8 path NUL decimal-bytes NUL lowercase-SHA-256 newline"),
    "directories": 9_282,
    "files": 13_656,
    "sha256": "63407d0870f97fe8a1397efff07392da7bbbb737c836eb4fcae463c0b7b7ac1a",
}

SOURCE_SUMMARY = {
    "jobs_completed": 4_446,
    "jobs_failed": 0,
    "jobs_pending": 1_986,
    "jobs_selected": 6_736,
    "jobs_unavailable_no_scene": 304,
}
DESTINATION_SUMMARY = {
    "jobs_completed": 4_470,
    "jobs_failed": 0,
    "jobs_pending": 1_961,
    "jobs_selected": 6_736,
    "jobs_unavailable_no_scene": 305,
}
EXPECTED_RUN = {
    "budget_exhausted": True,
    "finished_at": "2026-07-22T06:04:41Z",
    "http_attempts_reserved": 50,
    "job_attempts": 25,
    "jobs_completed": 24,
    "jobs_failed": 0,
    "jobs_unavailable_no_scene": 1,
    "max_http_attempts": 50,
    "max_jobs": 25,
    "started_at": "2026-07-22T06:02:54Z",
}
EXPECTED_CONFIGURATION = {
    "catalog_retries": 0,
    "max_job_attempts": 3,
    "max_response_bytes": 16_777_216,
    "maximum_http_attempts_per_job": 2,
    "minimum_interval_seconds": 1.1,
    "mode": "catalog_only",
    "priority_tiers": ["unknown"],
    "timeout_seconds": 60.0,
    "user_agent": (
        "DataCenterAtlas/0.1 (open research satellite review queue; "
        "+https://github.com/kiankyars/semiconductors)"
    ),
}

POSITION_START = 4_845
POSITION_END = 4_869
NEXT_PENDING_POSITION = 4_870
NEXT_PENDING_QUEUE_ID = "satq-feda771e469369c01497086b"
SOURCE_NEXT_PENDING_QUEUE_ID = "satq-e5631eb90d392d5c6074b2cf"
NO_SCENE_POSITION = 4_846
NO_SCENE_QUEUE_ID = "satq-b59eb808ed34c15f3df70044"
EXPECTED_UNAVAILABILITY = {
    "catalog_error_type": ("datacenter_atlas.satellite_catalog.CatalogValidationError"),
    "outcome": "unavailable_no_scene",
    "query_window": {
        "bbox": "8.309072,49.9728932,8.3650252,50.008866",
        "end_date": "2024-07-30",
        "provider": "earth-search-v1",
        "start_date": "2024-05-01",
        "target_date": "2024-06-15",
        "temporal_window_days": 45,
    },
    "raw_reason": "no scene falls within the baseline temporal window",
    "recorded_at": "2026-07-22T06:03:38Z",
    "window": "baseline",
}
EXPECTED_DELTA = {
    "directories_added": 49,
    "files_added": 72,
    "jobs_completed": 24,
    "jobs_failed": 0,
    "jobs_pending": -25,
    "jobs_selected": 0,
    "jobs_unavailable_no_scene": 1,
    "logical_bytes_added": 13_175_789,
    "preexisting_non_manifest_files_byte_identical": 13_583,
}

SCOPE = {
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "change_analysis_executed": False,
    "construction_master_integration": False,
    "current_coverage_integration": False,
    "global_completeness_claimed": False,
    "imagery_assets_downloaded": False,
    "imagery_computer_vision_executed": False,
    "imagery_construction_status_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_power_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "map_integration": False,
    "mode": "catalog_only",
    "network_access_during_acceptance": False,
    "network_access_during_validation": False,
    "review_required": True,
    "semianalysis_parity_claimed": False,
    "unique_site_claim_created": False,
}

BUILDER_FILES = (
    "datacenter_atlas/satellite_unknown037_continuation_acceptance.py",
    "scripts/accept_satellite_unknown037_continuation.py",
)


class Unknown037ContinuationAcceptanceError(RuntimeError):
    """Raised when a pinned input, clone delta, or wrapper differs."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _path_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise Unknown037ContinuationAcceptanceError(
            f"input is not an ordinary file: {path}"
        )
    return {"path": path.relative_to(ROOT).as_posix(), **_file_record(path)}


def _assert_pin(path: Path, pin: tuple[int, str], label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise Unknown037ContinuationAcceptanceError(f"{label} is not an ordinary file")
    raw = path.read_bytes()
    if (len(raw), _sha256(raw)) != pin:
        raise Unknown037ContinuationAcceptanceError(f"{label} pin changed")
    return raw


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Unknown037ContinuationAcceptanceError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise Unknown037ContinuationAcceptanceError(f"{label} is not an object")
    return value


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Unknown037ContinuationAcceptanceError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unknown037ContinuationAcceptanceError(
            f"{label} is not a timestamp"
        ) from error
    if parsed.microsecond:
        raise Unknown037ContinuationAcceptanceError(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _filesystem_time(value: float) -> str:
    return (
        datetime.fromtimestamp(value, UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _frozen(root: Path, label: str) -> None:
    files, directories = recovery._regular_tree(root, label)
    if not files or not directories:
        raise Unknown037ContinuationAcceptanceError(f"{label} is empty")
    for path in files:
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise Unknown037ContinuationAcceptanceError(
                f"{label} file is not mode 0444: {path}"
            )
    for path in directories:
        if stat.S_IMODE(path.stat().st_mode) != 0o555:
            raise Unknown037ContinuationAcceptanceError(
                f"{label} directory is not mode 0555: {path}"
            )


def _inventory_summary(
    rows: list[dict[str, Any]], raw: bytes, directories: set[str]
) -> dict[str, Any]:
    return {
        **recovery._inventory_summary(rows, raw),
        "directories": len(directories),
    }


def _terminal_bytes(tasks: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(
                task,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        for task in tasks
    )


def _root_chronology(path: Path) -> dict[str, Any]:
    metadata = path.stat(follow_symlinks=False)
    return {
        "birthtime": _filesystem_time(metadata.st_birthtime),
        "ctime": _filesystem_time(metadata.st_ctime),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mtime": _filesystem_time(metadata.st_mtime),
    }


def _validate_static_inputs() -> dict[str, dict[str, Any]]:
    pins: dict[str, dict[str, Any]] = {}
    fixed = {
        "queue_manifest": (QUEUE / "manifest.json", QUEUE_MANIFEST_PIN),
        "queue": (QUEUE / "satellite-review-queue.jsonl", QUEUE_FILE_PIN),
        "source_acceptance_manifest": (
            SOURCE_ACCEPTANCE / MANIFEST_FILENAME,
            SOURCE_ACCEPTANCE_MANIFEST_PIN,
        ),
        "source_acceptance_sidecar": (
            SOURCE_ACCEPTANCE / SIDECAR_FILENAME,
            SOURCE_ACCEPTANCE_SIDECAR_PIN,
        ),
        "source_batch_manifest": (
            SOURCE / batch.BATCH_MANIFEST_FILENAME,
            SOURCE_BATCH_PIN,
        ),
        "destination_batch_manifest": (
            DESTINATION / batch.BATCH_MANIFEST_FILENAME,
            DESTINATION_BATCH_PIN,
        ),
    }
    for name, (path, pin) in fixed.items():
        _assert_pin(path, pin, name)
        pins[name] = _path_record(path)
    for relative, pin in RUNNER_PINS.items():
        path = ROOT / relative
        _assert_pin(path, pin, relative)
        pins[relative] = _path_record(path)
    return pins


def _validate_source_acceptance() -> dict[str, Any]:
    _frozen(SOURCE_ACCEPTANCE, "Unknown036 acceptance wrapper")
    raw = _assert_pin(
        SOURCE_ACCEPTANCE / MANIFEST_FILENAME,
        SOURCE_ACCEPTANCE_MANIFEST_PIN,
        "Unknown036 acceptance manifest",
    )
    manifest = _json_object(raw, "Unknown036 acceptance manifest")
    if raw != _canonical_json(manifest):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown036 acceptance manifest is not canonical"
        )
    if (
        manifest.get("artifact_id")
        != "2026-07-22-global-open-v3-unknown-036-continued-25"
        or manifest.get("format")
        != "datacenter-atlas-satellite-catalog-continuation-acceptance-v1"
        or manifest.get("output", {}).get("batch_manifest")
        != _path_record(SOURCE / batch.BATCH_MANIFEST_FILENAME)
        or manifest.get("output", {}).get("inventory") != SOURCE_INVENTORY
        or manifest.get("output", {}).get("summary") != SOURCE_SUMMARY
        or manifest.get("output", {}).get("next_pending")
        != {
            "queue_id": SOURCE_NEXT_PENDING_QUEUE_ID,
            "queue_position": POSITION_START,
        }
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown036 acceptance semantics changed"
        )
    sidecar = _assert_pin(
        SOURCE_ACCEPTANCE / SIDECAR_FILENAME,
        SOURCE_ACCEPTANCE_SIDECAR_PIN,
        "Unknown036 acceptance sidecar",
    )
    if sidecar != (
        f"{SOURCE_ACCEPTANCE_MANIFEST_PIN[1]}  {MANIFEST_FILENAME}\n"
    ).encode("ascii"):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown036 acceptance sidecar changed"
        )
    return manifest


def _validate_lock() -> dict[str, Any]:
    if (
        DESTINATION_LOCK.is_symlink()
        or not DESTINATION_LOCK.is_file()
        or DESTINATION_LOCK.stat().st_size != 0
        or stat.S_IMODE(DESTINATION_LOCK.stat().st_mode) != 0o600
        or DESTINATION in DESTINATION_LOCK.parents
    ):
        raise Unknown037ContinuationAcceptanceError("Unknown037 canonical lock changed")
    metadata = DESTINATION_LOCK.stat(follow_symlinks=False)
    return {
        "birthtime": _filesystem_time(metadata.st_birthtime),
        "bytes": 0,
        "ctime": _filesystem_time(metadata.st_ctime),
        "excluded_from_accepted_tree": True,
        "mode": "0600",
        "mtime": _filesystem_time(metadata.st_mtime),
        "outside_destination_tree": True,
        "path": DESTINATION_LOCK.relative_to(ROOT).as_posix(),
        "single_writer": True,
    }


def _audit() -> dict[str, Any]:
    """Recompute the complete offline clone delta and all governed semantics."""

    accepted = _timestamp(ACCEPTED_AT, "accepted_at")
    static_pins = _validate_static_inputs()
    source_acceptance = _validate_source_acceptance()
    lock = _validate_lock()
    _frozen(SOURCE, "accepted Unknown036 source")
    _frozen(DESTINATION, "accepted Unknown037 destination")

    source_document = batch.validate_satellite_batch(QUEUE, SOURCE)
    destination_document = batch.validate_satellite_batch(QUEUE, DESTINATION)
    if (
        source_document.get("state") != "incomplete"
        or source_document.get("summary") != SOURCE_SUMMARY
        or destination_document.get("state") != "incomplete"
        or destination_document.get("summary") != DESTINATION_SUMMARY
        or destination_document.get("configuration") != EXPECTED_CONFIGURATION
        or destination_document.get("last_run") != EXPECTED_RUN
        or destination_document.get("scope") != batch.BATCH_SCOPE
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 batch semantics changed"
        )

    source_rows, source_raw, source_directories = recovery._inventory(
        SOURCE, "accepted Unknown036 source"
    )
    destination_rows, destination_raw, destination_directories = recovery._inventory(
        DESTINATION, "accepted Unknown037 destination"
    )
    source_inventory = _inventory_summary(source_rows, source_raw, source_directories)
    destination_inventory = _inventory_summary(
        destination_rows, destination_raw, destination_directories
    )
    if source_inventory != SOURCE_INVENTORY:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown036 complete canonical inventory changed"
        )
    if destination_inventory != DESTINATION_INVENTORY:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 complete canonical inventory changed"
        )

    source_files = {row["path"]: row for row in source_rows}
    destination_files = {row["path"]: row for row in destination_rows}
    if not set(source_files).issubset(destination_files):
        raise Unknown037ContinuationAcceptanceError("Unknown037 removed a source file")
    changed_non_manifest = [
        relative
        for relative, record in source_files.items()
        if relative != batch.BATCH_MANIFEST_FILENAME
        and destination_files[relative] != record
    ]
    if changed_non_manifest:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 changed inherited non-manifest bytes"
        )

    selected = sorted(
        (
            (queue_id, task)
            for queue_id, task in destination_document["jobs"].items()
            if POSITION_START <= task["queue_position"] <= POSITION_END
        ),
        key=lambda item: item[1]["queue_position"],
    )
    if [task["queue_position"] for _queue_id, task in selected] != list(
        range(POSITION_START, POSITION_END + 1)
    ):
        raise Unknown037ContinuationAcceptanceError("Unknown037 task interval changed")
    state_counts = Counter(task["state"] for _queue_id, task in selected)
    if state_counts != Counter({"completed": 24, batch.UNAVAILABLE_NO_SCENE: 1}):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 bounded task outcomes changed"
        )
    no_scene = [
        (queue_id, task)
        for queue_id, task in selected
        if task["state"] == batch.UNAVAILABLE_NO_SCENE
    ]
    if (
        len(no_scene) != 1
        or no_scene[0][0] != NO_SCENE_QUEUE_ID
        or no_scene[0][1]["queue_position"] != NO_SCENE_POSITION
        or no_scene[0][1]["attempts"] != 1
        or no_scene[0][1]["selected_ids"] is not None
        or no_scene[0][1]["artifacts"] is not None
        or no_scene[0][1]["unavailability"] != EXPECTED_UNAVAILABILITY
        or len(no_scene[0][1]["failures"]) != 1
        or "no scene falls within the baseline temporal window"
        not in no_scene[0][1]["failures"][0]["error"]
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 no-scene checkpoint changed"
        )
    completed = [
        (queue_id, task) for queue_id, task in selected if task["state"] == "completed"
    ]
    if any(
        task["attempts"] != 1
        or task["failures"]
        or task["unavailability"] is not None
        or task["selected_ids"] is None
        or set(task["artifacts"]) != set(batch.CATALOG_FILES)
        for _queue_id, task in completed
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 completed task semantics changed"
        )
    for queue_id, source_task in source_document["jobs"].items():
        position = source_task["queue_position"]
        if not POSITION_START <= position <= POSITION_END:
            if destination_document["jobs"][queue_id] != source_task:
                raise Unknown037ContinuationAcceptanceError(
                    "Unknown037 changed an out-of-range task"
                )

    expected_new_files = {
        f"jobs/{queue_id}/catalog/{name}"
        for queue_id, _task in completed
        for name in batch.CATALOG_FILES
    }
    expected_new_directories = {f"jobs/{queue_id}" for queue_id, _task in selected} | {
        f"jobs/{queue_id}/catalog" for queue_id, _task in completed
    }
    actual_new_files = set(destination_files) - set(source_files)
    actual_new_directories = destination_directories - source_directories
    if (
        actual_new_files != expected_new_files
        or actual_new_directories != expected_new_directories
        or source_directories - destination_directories
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 exact catalog-only clone delta changed"
        )

    next_pending = min(
        (
            (task["queue_position"], queue_id)
            for queue_id, task in destination_document["jobs"].items()
            if task["state"] == "pending"
        )
    )
    if next_pending != (NEXT_PENDING_POSITION, NEXT_PENDING_QUEUE_ID):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 next-pending position changed"
        )

    source_manifest = source_files[batch.BATCH_MANIFEST_FILENAME]
    destination_manifest = destination_files[batch.BATCH_MANIFEST_FILENAME]
    added_file_rows = [destination_files[path] for path in sorted(actual_new_files)]
    delta_summary = {
        "directories_added": len(actual_new_directories),
        "files_added": len(actual_new_files),
        "jobs_completed": (
            DESTINATION_SUMMARY["jobs_completed"] - SOURCE_SUMMARY["jobs_completed"]
        ),
        "jobs_failed": (
            DESTINATION_SUMMARY["jobs_failed"] - SOURCE_SUMMARY["jobs_failed"]
        ),
        "jobs_pending": (
            DESTINATION_SUMMARY["jobs_pending"] - SOURCE_SUMMARY["jobs_pending"]
        ),
        "jobs_selected": (
            DESTINATION_SUMMARY["jobs_selected"] - SOURCE_SUMMARY["jobs_selected"]
        ),
        "jobs_unavailable_no_scene": (
            DESTINATION_SUMMARY["jobs_unavailable_no_scene"]
            - SOURCE_SUMMARY["jobs_unavailable_no_scene"]
        ),
        "logical_bytes_added": (
            destination_inventory["bytes"] - source_inventory["bytes"]
        ),
        "preexisting_non_manifest_files_byte_identical": len(source_files) - 1,
    }
    if delta_summary != EXPECTED_DELTA:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 delta arithmetic changed"
        )
    delta = {
        "destination": DESTINATION.relative_to(ROOT).as_posix(),
        "directories_added": sorted(actual_new_directories),
        "directories_added_count": len(actual_new_directories),
        "directories_removed": [],
        "files_added": added_file_rows,
        "files_added_count": len(added_file_rows),
        "format": "datacenter-atlas-satellite-catalog-clone-delta-v1",
        "position_end": POSITION_END,
        "position_start": POSITION_START,
        "preexisting_files": {
            "batch_manifest": {
                "changed": True,
                "destination": {
                    "bytes": destination_manifest["bytes"],
                    "sha256": destination_manifest["sha256"],
                },
                "path": batch.BATCH_MANIFEST_FILENAME,
                "source": {
                    "bytes": source_manifest["bytes"],
                    "sha256": source_manifest["sha256"],
                },
            },
            "non_manifest_byte_identical": len(source_files) - 1,
            "non_manifest_changed": [],
            "removed": [],
        },
        "queue_tasks": [
            {
                "attempts": task["attempts"],
                "output_directory": task["output_directory"],
                "queue_id": queue_id,
                "queue_position": task["queue_position"],
                "state": task["state"],
            }
            for queue_id, task in selected
        ],
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "summary": delta_summary,
    }

    source_chronology = _root_chronology(SOURCE)
    destination_chronology = _root_chronology(DESTINATION)
    started = _timestamp(EXPECTED_RUN["started_at"], "started_at")
    finished = _timestamp(EXPECTED_RUN["finished_at"], "finished_at")
    lock_birth = datetime.fromisoformat(lock["birthtime"].replace("Z", "+00:00"))
    lock_birth_whole_second = lock_birth.replace(microsecond=0)
    destination_birth = datetime.fromisoformat(
        destination_chronology["birthtime"].replace("Z", "+00:00")
    )
    destination_freeze = datetime.fromisoformat(
        destination_chronology["ctime"].replace("Z", "+00:00")
    )
    if not (
        destination_birth < lock_birth
        and lock_birth_whole_second
        <= started
        < finished
        < destination_freeze
        < accepted
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance chronology changed"
        )
    if source_chronology["device"] != destination_chronology["device"]:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 source and destination are no longer on one device"
        )

    return {
        "delta": delta,
        "delta_summary": delta_summary,
        "destination_chronology": destination_chronology,
        "destination_inventory": destination_inventory,
        "destination_inventory_raw": destination_raw,
        "lock": lock,
        "next_pending": next_pending,
        "selected": selected,
        "source_acceptance": source_acceptance,
        "source_chronology": source_chronology,
        "source_inventory": source_inventory,
        "source_inventory_raw": source_raw,
        "static_pins": static_pins,
        "terminal_raw": _terminal_bytes([task for _queue_id, task in selected]),
    }


def _artifact_record(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def build_unknown037_continuation_acceptance() -> dict[str, bytes]:
    """Build the exact wrapper bytes after a complete offline audit."""

    audit = _audit()
    files = {
        SOURCE_INVENTORY_FILENAME: audit["source_inventory_raw"],
        DESTINATION_INVENTORY_FILENAME: audit["destination_inventory_raw"],
        DELTA_FILENAME: _canonical_json(audit["delta"]),
    }
    artifacts = {name: _artifact_record(raw) for name, raw in sorted(files.items())}
    manifest = {
        "accepted_at": ACCEPTED_AT,
        "artifact_id": ARTIFACT_ID,
        "artifacts": artifacts,
        "builder": {
            "clone_delta_recomputed": True,
            "complete_inventory_recomputed": True,
            "files": {
                relative: _path_record(ROOT / relative) for relative in BUILDER_FILES
            },
            "network_access": False,
        },
        "clone": {
            "destination_path": DESTINATION.relative_to(ROOT).as_posix(),
            "destination_root_chronology": audit["destination_chronology"],
            "filesystem": "APFS",
            "filesystem_observation": "local mount table before acceptance",
            "method": "cp -cR copy-on-write clone",
            "source_and_destination_same_device": True,
            "source_path": SOURCE.relative_to(ROOT).as_posix(),
            "source_root_chronology": audit["source_chronology"],
        },
        "execution": {
            "bounds": {
                "catalog_retries": 0,
                "max_http_attempts": 50,
                "max_job_attempts": 3,
                "max_jobs": 25,
            },
            "configuration": EXPECTED_CONFIGURATION,
            "http_outcomes": {
                "actual_status_codes_persisted": False,
                "catalog_pair_selection_completed": 24,
                "http_attempts_reserved": 50,
                "no_scene_outcomes_persisted": 1,
                "provider_http_success_count_claimed": False,
                "provider_or_transport_failures_recorded": 0,
            },
            "position_end": POSITION_END,
            "position_start": POSITION_START,
            "run": EXPECTED_RUN,
            "run_start_clock_precision": {
                "batch_manifest": "whole-second UTC",
                "lock_filesystem": "microsecond UTC",
                "ordering_check": (
                    "lock birth whole-second <= recorded run start; runner pin "
                    "holds the lock around queue execution"
                ),
            },
            "runner": {
                relative: audit["static_pins"][relative] for relative in RUNNER_PINS
            },
            "terminal_tasks": {
                "bytes": len(audit["terminal_raw"]),
                "canonicalization": (
                    "queue-position order; compact sorted-key UTF-8 JSON plus "
                    "newline for each exact batch task object"
                ),
                "jobs": len(audit["selected"]),
                "sha256": _sha256(audit["terminal_raw"]),
            },
        },
        "format": "datacenter-atlas-satellite-catalog-continuation-acceptance-v1",
        "output": {
            "batch_manifest": audit["static_pins"]["destination_batch_manifest"],
            "delta": audit["delta_summary"],
            "delta_artifact": {
                "path": DELTA_FILENAME,
                **artifacts[DELTA_FILENAME],
            },
            "directories_mode": "0555",
            "files_mode": "0444",
            "inventory": audit["destination_inventory"],
            "inventory_artifact": {
                "path": DESTINATION_INVENTORY_FILENAME,
                **artifacts[DESTINATION_INVENTORY_FILENAME],
            },
            "lock": audit["lock"],
            "next_pending": {
                "queue_id": audit["next_pending"][1],
                "queue_position": audit["next_pending"][0],
            },
            "post_freeze_validation": {
                "performed_offline": True,
                "state": "incomplete",
            },
            "summary": DESTINATION_SUMMARY,
        },
        "publication_contract": {
            "declared_at": ACCEPTED_AT,
            "final_tree_ctime_not_before_declared": True,
            "no_replace_promotion": True,
            "stage_birthtime_and_mtime_not_after_declared": True,
        },
        "queue_bundle": {
            "manifest": audit["static_pins"]["queue_manifest"],
            "queue": audit["static_pins"]["queue"],
            "queue_jobs": 6_830,
            "selected_unknown_jobs": 6_736,
        },
        "schema_version": 1,
        "scope": SCOPE,
        "source_continuation": {
            "acceptance_manifest": audit["static_pins"]["source_acceptance_manifest"],
            "acceptance_sidecar": audit["static_pins"]["source_acceptance_sidecar"],
            "artifact_id": audit["source_acceptance"]["artifact_id"],
            "batch_manifest": audit["static_pins"]["source_batch_manifest"],
            "directories_mode": "0555",
            "files_mode": "0444",
            "inventory": audit["source_inventory"],
            "inventory_artifact": {
                "path": SOURCE_INVENTORY_FILENAME,
                **artifacts[SOURCE_INVENTORY_FILENAME],
            },
            "preserved_read_only": True,
            "validated_offline_before_acceptance": True,
        },
        "wrapper_closed_file_set": sorted(CLOSED_FILENAMES),
    }
    files[MANIFEST_FILENAME] = _canonical_json(manifest)
    files[SIDECAR_FILENAME] = (
        f"{_sha256(files[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return files


def _closed_tree(directory: Path, expected: Mapping[str, bytes]) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance wrapper is not a regular directory"
        )
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(expected) or set(entries) != CLOSED_FILENAMES:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance wrapper closed set changed"
        )
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance wrapper directory is not mode 0555"
        )
    for name, raw in expected.items():
        path = entries[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            or path.read_bytes() != raw
        ):
            raise Unknown037ContinuationAcceptanceError(
                f"Unknown037 acceptance wrapper member changed: {name}"
            )


def _publication_paths(root: Path) -> list[Path]:
    files, directories = recovery._regular_tree(root, "Unknown037 wrapper")
    return [*files, *directories]


def _assert_predeclared_stage(root: Path) -> None:
    declared = _timestamp(ACCEPTED_AT, "accepted_at").timestamp()
    for path in _publication_paths(root):
        metadata = path.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", None)
        if birthtime is None or birthtime > declared or metadata.st_mtime > declared:
            raise Unknown037ContinuationAcceptanceError(
                f"Unknown037 stage chronology is too late: {path}"
            )


def _refresh_final_ctimes(root: Path) -> None:
    files, directories = recovery._regular_tree(root, "Unknown037 wrapper")
    for path in files:
        path.chmod(0o400)
        path.chmod(0o444)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o500)
        path.chmod(0o555)


def _validate_publication_chronology(root: Path) -> None:
    declared = _timestamp(ACCEPTED_AT, "accepted_at").timestamp()
    for path in _publication_paths(root):
        metadata = path.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", None)
        if (
            birthtime is None
            or birthtime > declared
            or metadata.st_mtime > declared
            or metadata.st_ctime < declared
        ):
            raise Unknown037ContinuationAcceptanceError(
                f"Unknown037 final publication chronology changed: {path}"
            )


def validate_unknown037_continuation_acceptance(
    directory: Path = OUTPUT,
) -> dict[str, Any]:
    """Recompute every input, inventory, delta, wrapper byte, and clock."""

    supplied = Path(os.path.abspath(os.fspath(directory)))
    if supplied != OUTPUT:
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance wrapper path changed"
        )
    expected = build_unknown037_continuation_acceptance()
    _closed_tree(supplied, expected)
    _validate_publication_chronology(supplied)
    manifest_raw = expected[MANIFEST_FILENAME]
    manifest = _json_object(manifest_raw, "Unknown037 acceptance manifest")
    if manifest_raw != _canonical_json(manifest):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance manifest is not canonical"
        )
    if expected[SIDECAR_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii"):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance sidecar changed"
        )
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("scope") != SCOPE
        or manifest.get("output", {}).get("summary") != DESTINATION_SUMMARY
        or manifest.get("output", {}).get("delta") != EXPECTED_DELTA
        or manifest.get("output", {}).get("next_pending")
        != {
            "queue_id": NEXT_PENDING_QUEUE_ID,
            "queue_position": NEXT_PENDING_POSITION,
        }
    ):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance manifest semantics changed"
        )
    return manifest


def _discard_stage(stage: Path) -> None:
    if stage.is_symlink() or not stage.exists():
        return
    files, directories = recovery._regular_tree(stage, "owned acceptance stage")
    for path in files:
        path.chmod(0o600)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o700)
    shutil.rmtree(stage)


def write_unknown037_continuation_acceptance() -> dict[str, Any]:
    """Write the frozen wrapper with future-clock and no-replace guards."""

    if OUTPUT.exists() or OUTPUT.is_symlink():
        return validate_unknown037_continuation_acceptance(OUTPUT)
    parent = OUTPUT.parent
    if parent.is_symlink() or not parent.is_dir():
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 acceptance output parent is unsafe"
        )
    parent_metadata = parent.stat(follow_symlinks=False)
    parent_identity = (parent_metadata.st_dev, parent_metadata.st_ino)
    expected = build_unknown037_continuation_acceptance()
    if datetime.now(UTC) >= _timestamp(ACCEPTED_AT, "accepted_at"):
        raise Unknown037ContinuationAcceptanceError(
            "Unknown037 stage would postdate the declared acceptance time"
        )
    stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=parent))
    stage_identity = (
        stage.stat(follow_symlinks=False).st_dev,
        stage.stat(follow_symlinks=False).st_ino,
    )
    try:
        for name, raw in expected.items():
            path = stage / name
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(0o444)
        stage.chmod(0o555)
        _closed_tree(stage, expected)
        _assert_predeclared_stage(stage)
        while datetime.now(UTC) < _timestamp(ACCEPTED_AT, "accepted_at"):
            time.sleep(
                min(
                    1.0,
                    max(
                        0.01,
                        (
                            _timestamp(ACCEPTED_AT, "accepted_at") - datetime.now(UTC)
                        ).total_seconds(),
                    ),
                )
            )
        if OUTPUT.exists() or OUTPUT.is_symlink():
            raise Unknown037ContinuationAcceptanceError(
                "Unknown037 acceptance output appeared before promotion"
            )
        current_parent = parent.stat(follow_symlinks=False)
        current_stage = stage.stat(follow_symlinks=False)
        if (current_parent.st_dev, current_parent.st_ino) != parent_identity:
            raise Unknown037ContinuationAcceptanceError(
                "Unknown037 acceptance parent identity changed"
            )
        if (current_stage.st_dev, current_stage.st_ino) != stage_identity:
            raise Unknown037ContinuationAcceptanceError(
                "Unknown037 acceptance stage identity changed"
            )
        recovery._promote_directory_exclusive(stage, OUTPUT)
        if stage.exists() or stage.is_symlink():
            raise Unknown037ContinuationAcceptanceError(
                "Unknown037 acceptance stage remains after promotion"
            )
        _refresh_final_ctimes(OUTPUT)
        return validate_unknown037_continuation_acceptance(OUTPUT)
    except BaseException:
        if stage.exists() or stage.is_symlink():
            _discard_stage(stage)
        raise


def main() -> int:
    manifest = write_unknown037_continuation_acceptance()
    manifest_raw = (OUTPUT / MANIFEST_FILENAME).read_bytes()
    print(
        json.dumps(
            {
                "accepted_at": manifest["accepted_at"],
                "artifact_id": manifest["artifact_id"],
                "delta": manifest["output"]["delta"],
                "destination_inventory": manifest["output"]["inventory"],
                "manifest_bytes": len(manifest_raw),
                "manifest_sha256": _sha256(manifest_raw),
                "next_pending": manifest["output"]["next_pending"],
                "source_inventory": manifest["source_continuation"]["inventory"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
