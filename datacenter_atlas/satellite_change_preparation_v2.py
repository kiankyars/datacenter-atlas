"""Prepare the frozen v83 catalog for later single- or multi-tile runners.

This successor remains metadata-only.  It reads the frozen queue, catalog
manifest, and archived STAC JSON; it never opens an imagery asset, downloads
imagery, or executes change analysis.
"""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import errno
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from typing import Any, Mapping

from . import satellite_change_preparation_v1 as _v1
from .satellite_batch import BatchConfig, validate_satellite_batch
from .satellite_change import ALGORITHM_VERSION as SINGLE_TILE_ALGORITHM_VERSION
from .satellite_change_mosaic import (
    ALGORITHM_VERSION as MULTI_TILE_ALGORITHM_VERSION,
)
from .satellite_queue import validate_queue_bundle


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = Path(
    "sources/satellite-change-preparation-2026-07-21-open-seed-v83-active-v2.json"
)
OUTPUT_PATH = Path(
    "satellite_change_preparation/2026-07-21-open-seed-v83-active-v2"
)

DEFINITION_FORMAT = "datacenter-atlas-satellite-change-preparation-definition-v2"
RELEASE_FORMAT = "datacenter-atlas-satellite-change-preparation-v2"
SCHEMA_VERSION = 2
PREPARATION_ID = "2026-07-21-open-seed-v83-active-change-preparation-v2"
STATES = _v1.STATES
STATE_FILES = _v1.STATE_FILES
RELEASE_FILES = _v1.RELEASE_FILES
CLAIM_CONSTRAINTS = _v1.CLAIM_CONSTRAINTS
RUNTIME = _v1.RUNTIME

QUEUE_DIRECTORY = Path("satellite_review_queues/2026-07-21-open-seed-v83")
CATALOG_DIRECTORY = Path(
    "satellite_review_runs/2026-07-21-open-seed-v83-active-002"
)
CATALOG_LOCK = Path(
    "satellite_review_runs/2026-07-21-open-seed-v83-active-002.lock"
)

EXPECTED_QUEUE_TREE_SHA256 = (
    "2b9fc5a30525e2e815154d1635c49badf06c436e354ccb04a4898e6f42d22eee"
)
EXPECTED_CATALOG_TREE_SHA256 = (
    "7a26caebb28656c551837c1431bfd2a5a228889572d5df006a149badc8c91152"
)
EXPECTED_CATALOG_MANIFEST = {
    "bytes": 120_448,
    "mode": "0444",
    "path": (
        "satellite_review_runs/2026-07-21-open-seed-v83-active-002/"
        "batch-manifest.json"
    ),
    "sha256": "ec43aacf55bab8d8169e5cad4855b5e33614c2e65de0a5b82bf70c2c585adae8",
}
EXPECTED_CATALOG_LOCK = {
    "bytes": 0,
    "mode": "0600",
    "path": "satellite_review_runs/2026-07-21-open-seed-v83-active-002.lock",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
EXPECTED_PARTITION = {
    "active_jobs": 104,
    "distinct_aois": 100,
    "jobs_in_shared_aois": 8,
    "multi_tile_blocked": 7,
    "multi_tile_ready": 6,
    "partition_inventory_sha256": (
        "54f219388b7f80abb17cf0c53c4a5ca06b604333fde4234aa19a5cab33a5d74f"
    ),
    "shared_aoi_groups": 4,
    "single_tile_ready": 88,
    "terminal_no_scene": 3,
}

REVIEWED_QUEUE_IDS = frozenset(
    {
        "satq-02a713b5d0ec25375cffb0c3",
        "satq-0ffe3647dc32ee25ef77eab7",
        "satq-1610b5ac5506aac220b11453",
        "satq-1d4a91217eae3cffc49002cb",
        "satq-1f72804d5d56bb342d5e2e2c",
        "satq-3f234ace58ef90bcb7affc42",
        "satq-44d8e1c44fea11bc4dc51efd",
        "satq-511257788faac7f8fe916b55",
        "satq-54c6402eb93d14f1ea754e66",
        "satq-5ee998aa094cc5f057fec55d",
        "satq-5feb20b3df63076cce05ab3f",
        "satq-6d40fe3ecc9e39e712c0a2d0",
        "satq-78500568b1f6227789ae36f4",
        "satq-930a02278f48494c659e3e76",
        "satq-96fca962064e09f0dbafa93b",
        "satq-ac9d66dd45f3a868190ec4c1",
        "satq-b6f121dc644b91ad78eb479a",
        "satq-be2a4e34c6f53c7e4f96205c",
        "satq-c35caa31b2dbfa58da1de7b9",
        "satq-c5dd1e3c30725073cefca3e4",
        "satq-c92ac430b054e36342ee99ed",
        "satq-cef871428da247c3ecfadec6",
        "satq-d0a872a7aee9f9f54a8631ef",
        "satq-d2f2205b9b46de73b37998f3",
        "satq-db46dc300e93181cfe250029",
        "satq-ef22ae26b5cba60034c8567f",
        "satq-fb6b6f815dad079c059cf412",
    }
)
REVIEWED_QUEUE_IDS_SHA256 = (
    "c55aa3aa3b40b5e882b414b26a0a47dec3f297866d48248a08a6b8dc72e61c88"
)
NET_NEW_MULTI_TILE_BLOCKERS = {
    8: "satq-415d80a31d8798a2e2c06d17",
    17: "satq-e6e1ceab9c56fe15b25e03f4",
    31: "satq-3288e71f7387eee72714a756",
    62: "satq-1478784c38a09b1d3c588c3b",
    65: "satq-66d1dc2e7f8654ac10d7980c",
    78: "satq-6936ad65587f752edbc1ba41",
}
RETAINED_MULTI_TILE_BLOCKER = {21: "satq-d0a872a7aee9f9f54a8631ef"}

CATALOG_CONFIG = BatchConfig(
    priority_tiers=["active_construction"],
    user_agent=(
        "DataCenterAtlas/0.1 (open research satellite review queue; "
        "+https://github.com/kiankyars/semiconductors)"
    ),
    minimum_interval_seconds=1.1,
    timeout_seconds=60.0,
    catalog_retries=0,
    max_job_attempts=3,
    max_response_bytes=16_777_216,
)

# Keep the predecessor's fail-closed exception identity so every delegated
# metadata helper is covered by the v2 public exception contract.
SatelliteChangePreparationV2Error = _v1.SatelliteChangePreparationV1Error


def _review_coverage_context() -> dict[str, Any]:
    return {
        "active_jobs": 104,
        "context_only_not_preparation_input": True,
        "reviewed_jobs": 27,
        "reviewed_queue_ids_sha256": REVIEWED_QUEUE_IDS_SHA256,
        "unreviewed_jobs": 77,
        "unreviewed_no_scene_jobs": 3,
    }


def _assert_accepted_source_identity(sources: Mapping[str, Any]) -> None:
    if (
        sources["queue_bundle"]["closed_tree"]["inventory_sha256"]
        != EXPECTED_QUEUE_TREE_SHA256
    ):
        raise SatelliteChangePreparationV2Error("accepted queue tree differs")
    if (
        sources["catalog_batch"]["closed_tree"]["inventory_sha256"]
        != EXPECTED_CATALOG_TREE_SHA256
    ):
        raise SatelliteChangePreparationV2Error("accepted catalog tree differs")
    if sources["catalog_batch"]["batch_manifest"] != EXPECTED_CATALOG_MANIFEST:
        raise SatelliteChangePreparationV2Error("accepted catalog manifest differs")
    if sources["catalog_lock"] != EXPECTED_CATALOG_LOCK:
        raise SatelliteChangePreparationV2Error("accepted catalog lock differs")


def build_satellite_change_preparation_definition_v2(
    generated_at: str,
) -> dict[str, Any]:
    """Build the canonical definition document from current frozen inputs."""

    generated_at = _v1._rfc3339(generated_at, "definition generated_at")
    module = ROOT / "datacenter_atlas/satellite_change_preparation_v2.py"
    outer_shim = ROOT / "satellite_change_preparation_v2.py"
    cli = ROOT / "scripts/build_satellite_change_preparation_v2.py"
    queue = ROOT / QUEUE_DIRECTORY
    catalog = ROOT / CATALOG_DIRECTORY
    sources = {
        "catalog_batch": {
            "batch_manifest": _v1._path_pin(catalog / "batch-manifest.json"),
            "closed_tree": _v1._tree_inventory(catalog),
            "directory": CATALOG_DIRECTORY.as_posix(),
        },
        "catalog_lock": _v1._path_pin(ROOT / CATALOG_LOCK),
        "queue_bundle": {
            "closed_tree": _v1._tree_inventory(queue),
            "directory": QUEUE_DIRECTORY.as_posix(),
            "manifest": _v1._path_pin(queue / "manifest.json"),
            "manifest_sidecar": _v1._path_pin(queue / "manifest.sha256"),
            "queue": _v1._path_pin(queue / "satellite-review-queue.jsonl"),
        },
    }
    _assert_accepted_source_identity(sources)
    reviewed_digest = _v1._sha(
        _v1._canonical_json(sorted(REVIEWED_QUEUE_IDS))
    )
    if reviewed_digest != REVIEWED_QUEUE_IDS_SHA256:
        raise SatelliteChangePreparationV2Error("review coverage identity drift")
    return {
        "builder": {
            "cli": _v1._path_pin(cli),
            "module": _v1._path_pin(module),
            "outer_shim": _v1._path_pin(outer_shim),
        },
        "claim_constraints": CLAIM_CONSTRAINTS,
        "expected_partition": EXPECTED_PARTITION,
        "format": DEFINITION_FORMAT,
        "generated_at": generated_at,
        "preparation_id": PREPARATION_ID,
        "processors": {
            "multi_tile": {
                "algorithm_version": MULTI_TILE_ALGORITHM_VERSION,
                "cli": _v1._path_pin(ROOT / "scripts/sentinel_change_mosaic.py"),
                "minimum_component_area_m2": 5_000,
                "module": _v1._path_pin(
                    ROOT / "datacenter_atlas/satellite_change_mosaic.py"
                ),
            },
            "single_tile": {
                "algorithm_version": SINGLE_TILE_ALGORITHM_VERSION,
                "cli": _v1._path_pin(ROOT / "scripts/sentinel_change.py"),
                "minimum_component_area_m2": 5_000,
                "module": _v1._path_pin(
                    ROOT / "datacenter_atlas/satellite_change.py"
                ),
            },
        },
        "publication_contract": {
            "artifact_mode": "0444",
            "atomic_no_replace": True,
            "directory_mode": "0555",
            "publish_not_before": generated_at,
            "two_offline_replays_required": True,
        },
        "review_coverage_context": _review_coverage_context(),
        "runtime": RUNTIME,
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
    }


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes]:
    path = Path(definition_path)
    raw = _v1._read_regular(path, "v2 preparation definition")
    value = _v1._strict_json(raw, "v2 preparation definition")
    if not isinstance(value, dict) or raw != _v1._canonical_json(value):
        raise SatelliteChangePreparationV2Error(
            "v2 preparation definition is not canonical pretty JSON"
        )
    generated_at = value.get("generated_at")
    expected = build_satellite_change_preparation_definition_v2(generated_at)
    if value != expected:
        raise SatelliteChangePreparationV2Error("v2 preparation definition drift")
    return value, raw


def _validated_sources(
    definition: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    queue = ROOT / definition["sources"]["queue_bundle"]["directory"]
    catalog = ROOT / definition["sources"]["catalog_batch"]["directory"]
    if _v1._tree_inventory(queue) != definition["sources"]["queue_bundle"][
        "closed_tree"
    ]:
        raise SatelliteChangePreparationV2Error("queue closed-tree pin mismatch")
    if _v1._tree_inventory(catalog) != definition["sources"]["catalog_batch"][
        "closed_tree"
    ]:
        raise SatelliteChangePreparationV2Error("catalog closed-tree pin mismatch")
    for label in ("queue", "manifest", "manifest_sidecar"):
        _v1._validate_file_pin(
            definition["sources"]["queue_bundle"][label], f"queue {label}"
        )
    _v1._validate_file_pin(
        definition["sources"]["catalog_batch"]["batch_manifest"],
        "catalog batch manifest",
    )
    _v1._validate_file_pin(definition["sources"]["catalog_lock"], "catalog lock")
    queue_manifest = validate_queue_bundle(queue)
    batch_manifest = validate_satellite_batch(
        queue, catalog, config=CATALOG_CONFIG
    )
    active = queue_manifest["counts"]["queued_entities_by_priority_tier"].get(
        "active_construction"
    )
    if active != 104:
        raise SatelliteChangePreparationV2Error("queue active-job count drift")
    expected_summary = {
        "jobs_completed": 101,
        "jobs_failed": 0,
        "jobs_pending": 0,
        "jobs_selected": 104,
        "jobs_unavailable_no_scene": 3,
    }
    if (
        batch_manifest["state"] != "completed"
        or batch_manifest["summary"] != expected_summary
        or batch_manifest["configuration"] != {
            **CATALOG_CONFIG.as_dict(),
            "maximum_http_attempts_per_job": 2,
        }
    ):
        raise SatelliteChangePreparationV2Error("catalog terminal partition drift")
    return queue, catalog, queue_manifest, batch_manifest


def _annotate_rows(
    rows: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    all_queue_ids = {
        row["queue_id"] for state in STATES for row in rows[state]
    }
    if len(all_queue_ids) != 104 or not REVIEWED_QUEUE_IDS <= all_queue_ids:
        raise SatelliteChangePreparationV2Error("review coverage does not fit queue")
    no_scene = {row["queue_id"] for row in rows["terminal_no_scene"]}
    if no_scene & REVIEWED_QUEUE_IDS:
        raise SatelliteChangePreparationV2Error("no-scene review count drift")
    blocked = {
        row["queue_position"]: row["queue_id"]
        for row in rows["multi_tile_blocked"]
    }
    if blocked != {**NET_NEW_MULTI_TILE_BLOCKERS, **RETAINED_MULTI_TILE_BLOCKER}:
        raise SatelliteChangePreparationV2Error("multi-tile blocker identity drift")
    if set(NET_NEW_MULTI_TILE_BLOCKERS.values()) & REVIEWED_QUEUE_IDS:
        raise SatelliteChangePreparationV2Error("net-new blocker review drift")

    for state in STATES:
        for row in rows[state]:
            queue_id = row["queue_id"]
            ready = state in {"single_tile_ready", "multi_tile_ready"}
            runner = (
                "sentinel_change"
                if state == "single_tile_ready"
                else "sentinel_change_mosaic"
                if state == "multi_tile_ready"
                else None
            )
            row["analyst_review_coverage"] = {
                "context_only_not_preparation_input": True,
                "status": (
                    "reviewed"
                    if queue_id in REVIEWED_QUEUE_IDS
                    else "unreviewed"
                ),
            }
            row["future_runner_contract"] = {
                "execution_arguments_complete": ready,
                "metadata_only_preparation": True,
                "output_directory_placeholder": (
                    "{job_output_dir}" if ready else None
                ),
                "runner": runner,
            }
            row["schema_version"] = SCHEMA_VERSION
            if state == "multi_tile_blocked":
                row["blocker_generation"] = (
                    "net_new_v83"
                    if queue_id in NET_NEW_MULTI_TILE_BLOCKERS.values()
                    else "retained_predecessor"
                )
                row["net_new_v83_multi_tile_blocker"] = (
                    queue_id in NET_NEW_MULTI_TILE_BLOCKERS.values()
                )
    return rows


def _source_inventory(
    definition: Mapping[str, Any], queue: Path, catalog: Path
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for source_group, directory in (
        ("queue_bundle", queue),
        ("catalog_batch", catalog),
    ):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink():
                pin = _v1._path_pin(path)
                pin["source_group"] = source_group
                files[pin["path"]] = pin
    lock = _v1._validate_file_pin(
        definition["sources"]["catalog_lock"], "catalog lock"
    )
    lock_pin = _v1._path_pin(lock)
    lock_pin["source_group"] = "catalog_lock"
    files[lock_pin["path"]] = lock_pin
    for label, source_pin in definition["builder"].items():
        pin = dict(source_pin)
        pin["source_group"] = f"builder:{label}"
        files[pin["path"]] = pin
    for processor_name, processor in definition["processors"].items():
        for label in ("module", "cli"):
            pin = dict(processor[label])
            if pin["path"] not in files:
                pin["source_group"] = f"processor:{processor_name}:{label}"
                files[pin["path"]] = pin
    return {
        "files": [files[path] for path in sorted(files)],
        "schema_version": SCHEMA_VERSION,
        "source_file_count": len(files),
    }


def _readme(summary: Mapping[str, Any]) -> bytes:
    return f"""# V83 catalog-to-change preparation v2

This immutable metadata-only bundle partitions all {summary['active_jobs']} active-construction jobs from the frozen v83 catalog: {summary['single_tile_ready']} singleton-ready, {summary['multi_tile_ready']} mosaic-ready, {summary['multi_tile_blocked']} mosaic-blocked, and {summary['terminal_no_scene']} terminal no-scene.

The blocked set contains six net-new v83 metadata blockers at queue positions 8, 17, 31, 62, 65, and 78, plus one retained predecessor blocker at position 21. Those six are not the whole unreviewed population. Archived analyst-review rows cover 27/104 queue IDs; 77 remain unreviewed, including all three no-scene jobs. Review coverage is context only, not an input to the metadata partition.

Preparation reads archived STAC JSON and pinned Rasterio geometry metadata only. It performs no network request, imagery download, imagery open, raster change analysis, promotion, entity merge, site deduplication, or atlas mutation. Ready rows carry complete future-runner arguments; they are not identity, lifecycle, type, capacity, power, energy, PUE, workload, construction-truth, or site-count claims.
""".encode("utf-8")


def _payloads(
    definition_path: str | Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    definition, definition_raw = _validate_definition(definition_path)
    queue, catalog, _queue_manifest, batch_manifest = _validated_sources(definition)
    rows, relationships, partition = _v1._derive_rows(
        definition, queue, catalog, batch_manifest
    )
    rows = _annotate_rows(rows)
    source_inventory = _source_inventory(definition, queue, catalog)
    coverage = _review_coverage_context()
    summary = {
        **partition,
        "multi_tile_blocked_net_new_v83": 6,
        "multi_tile_blocked_retained": 1,
        "review_coverage": coverage,
    }
    payloads: dict[str, bytes] = {
        "ATTRIBUTION.txt": (
            "Catalog metadata: Element 84 Earth Search v1. Imagery references: "
            "Copernicus Sentinel-2 Level-2A. No imagery asset was fetched.\n"
        ).encode("utf-8"),
        "README.md": _readme(summary),
        "aoi-relationships.jsonl": _v1._canonical_jsonl(relationships),
        "source-inventory.json": _v1._canonical_json(source_inventory),
        "summary.json": _v1._canonical_json(
            {
                "claim_constraints": CLAIM_CONSTRAINTS,
                "preparation_id": PREPARATION_ID,
                "preparation_only": True,
                "runtime": definition["runtime"],
                "schema_version": SCHEMA_VERSION,
                **summary,
            }
        ),
    }
    for state, filename in STATE_FILES.items():
        payloads[filename] = _v1._canonical_jsonl(
            sorted(rows[state], key=lambda row: row["queue_position"])
        )
    artifacts = {
        filename: {"bytes": len(raw), "sha256": _v1._sha(raw)}
        for filename, raw in sorted(payloads.items())
    }
    definition_relative = (
        Path(definition_path).resolve().relative_to(ROOT).as_posix()
    )
    manifest = {
        "artifacts": artifacts,
        "builder": definition["builder"],
        "claim_constraints": CLAIM_CONSTRAINTS,
        "closed_inventory": {
            "manifest_hash_sidecar": "manifest.sha256",
            "release_files": sorted(RELEASE_FILES),
        },
        "definition": {
            "bytes": len(definition_raw),
            "path": definition_relative,
            "sha256": _v1._sha(definition_raw),
        },
        "format": RELEASE_FORMAT,
        "generated_at": definition["generated_at"],
        "preparation_id": PREPARATION_ID,
        "processors": definition["processors"],
        "publication_contract": definition["publication_contract"],
        "review_coverage_context": coverage,
        "runtime": definition["runtime"],
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "aoi_deduplication_applied": False,
            "entity_jobs_retained": 104,
            "imagery_downloads": 0,
            "imagery_opens": 0,
            "network_requests": 0,
            "preparation_only": True,
            "raster_analyses": 0,
        },
        "sources": definition["sources"],
        "summary": summary,
    }
    manifest_raw = _v1._canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_v1._sha(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return payloads, manifest


def validate_satellite_change_preparation_v2(
    output_directory: str | Path,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    output = Path(output_directory)
    if output.is_symlink() or not output.is_dir():
        raise SatelliteChangePreparationV2Error(
            f"preparation output is not a regular directory: {output}"
        )
    if {path.name for path in output.iterdir()} != RELEASE_FILES:
        raise SatelliteChangePreparationV2Error("preparation output inventory drift")
    expected, manifest = _payloads(definition_path)
    for filename in sorted(RELEASE_FILES):
        path = output / filename
        raw = _v1._read_regular(path, f"preparation artifact {filename}")
        if raw != expected[filename]:
            raise SatelliteChangePreparationV2Error(
                f"preparation artifact differs: {filename}"
            )
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise SatelliteChangePreparationV2Error(
                f"preparation artifact is not frozen: {filename}"
            )
    if stat.S_IMODE(output.stat().st_mode) != 0o555:
        raise SatelliteChangePreparationV2Error(
            "preparation directory is not frozen"
        )
    return manifest


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:  # pragma: no cover - publication platform guard
        raise SatelliteChangePreparationV2Error(
            "atomic no-replace publication is unavailable"
        )
    if result == 0:
        _fsync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SatelliteChangePreparationV2Error(
            f"late output collision; refusing overwrite: {destination}"
        )
    raise SatelliteChangePreparationV2Error(
        "atomic no-replace publication failed: " + os.strerror(error_number)
    )


def _thaw_and_remove(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    for child in path.iterdir():
        if not child.is_symlink():
            child.chmod(0o600 if child.is_file() else 0o700)
    path.chmod(0o700)
    shutil.rmtree(path)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def write_satellite_change_preparation_v2(
    output_directory: str | Path = ROOT / OUTPUT_PATH,
    *,
    definition_path: str | Path = ROOT / DEFINITION_PATH,
) -> dict[str, Any]:
    """Publish once after the future clock using atomic no-replace."""

    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise SatelliteChangePreparationV2Error(
            f"refusing to replace preparation output: {output}"
        )
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteChangePreparationV2Error(
            f"preparation output parent is not a regular directory: {parent}"
        )
    definition, definition_raw = _validate_definition(definition_path)
    publish_not_before = datetime.fromisoformat(
        definition["generated_at"].replace("Z", "+00:00")
    )
    if publish_not_before <= datetime.now(timezone.utc):
        raise SatelliteChangePreparationV2Error(
            "definition generated_at must be future at build start"
        )
    first_payloads, first_manifest = _payloads(definition_path)
    second_payloads, second_manifest = _payloads(definition_path)
    if first_payloads != second_payloads or first_manifest != second_manifest:
        raise SatelliteChangePreparationV2Error("offline replay differs")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    promoted = False
    identity: tuple[int, int] | None = None
    try:
        for filename, raw in sorted(first_payloads.items()):
            path = stage / filename
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(0o444)
        stage.chmod(0o555)
        validate_satellite_change_preparation_v2(
            stage, definition_path=definition_path
        )
        frozen_tree = _v1._tree_inventory(stage)
        frozen_members = _tree_bytes(stage)
        while datetime.now(timezone.utc) < publish_not_before:
            remaining = (
                publish_not_before - datetime.now(timezone.utc)
            ).total_seconds()
            time.sleep(min(max(remaining, 0.001), 0.25))
        if Path(definition_path).read_bytes() != definition_raw:
            raise SatelliteChangePreparationV2Error(
                "definition changed while staged"
            )
        if (
            _v1._tree_inventory(stage) != frozen_tree
            or _tree_bytes(stage) != frozen_members
        ):
            raise SatelliteChangePreparationV2Error("private stage changed while waiting")
        if output.exists() or output.is_symlink():
            raise SatelliteChangePreparationV2Error(
                f"preparation output appeared during publication: {output}"
            )
        # macOS renamex_np(RENAME_EXCL) rejects a 0555 source directory.
        # Member bytes stay immutable and are revalidated immediately after.
        status = stage.stat()
        identity = (status.st_dev, status.st_ino)
        stage.chmod(0o755)
        _promote_noreplace(stage, output)
        promoted = True
        output.chmod(0o555)
        return validate_satellite_change_preparation_v2(
            output, definition_path=definition_path
        )
    except BaseException:
        if promoted and output.exists() and not output.is_symlink() and identity:
            status = output.stat()
            if (status.st_dev, status.st_ino) == identity:
                rollback = parent / f".{output.name}.rollback-{os.getpid()}"
                if not rollback.exists() and not rollback.is_symlink():
                    output.chmod(0o755)
                    _promote_noreplace(output, rollback)
                    _thaw_and_remove(rollback)
        _thaw_and_remove(stage)
        raise


__all__ = [
    "CATALOG_CONFIG",
    "CLAIM_CONSTRAINTS",
    "DEFINITION_FORMAT",
    "DEFINITION_PATH",
    "NET_NEW_MULTI_TILE_BLOCKERS",
    "OUTPUT_PATH",
    "PREPARATION_ID",
    "RELEASE_FILES",
    "RELEASE_FORMAT",
    "REVIEWED_QUEUE_IDS",
    "RUNTIME",
    "SCHEMA_VERSION",
    "SatelliteChangePreparationV2Error",
    "build_satellite_change_preparation_definition_v2",
    "validate_satellite_change_preparation_v2",
    "write_satellite_change_preparation_v2",
]
