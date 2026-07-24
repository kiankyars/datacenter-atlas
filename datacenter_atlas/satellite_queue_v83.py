"""Strict offline publisher for the accepted open-seed v83 satellite queue.

The generic queue carrier remains byte-pinned and unchanged. This successor
uses only coordinates, identities, and last-observed lifecycle values already
present in the accepted v83 atlas. It performs no catalog request, imagery
analysis, entity merge, coordinate inference, lifecycle inference, or capacity
inference.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping

from . import satellite_queue as carrier
from .open_seed_v56 import promote_noreplace


class SatelliteQueueV83Error(ValueError):
    """Raised when an accepted input or publication boundary is violated."""


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
ATLAS = RELEASE / "atlas.geojson"
RELEASE_MANIFEST = RELEASE / carrier.MANIFEST_FILENAME
PREDECESSOR_QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v73"
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
PUBLICATION_LOCK = ROOT / ".satellite-review-queue-v83.lock"

BASELINE_TARGET = "2024-07-15"
CURRENT_TARGET = "2026-07-15"
CONFIG = carrier.QueueConfig(
    baseline_target=BASELINE_TARGET,
    current_target=CURRENT_TARGET,
    provider="earth-search-v1",
    query_window_days=45,
    max_cloud_cover=20,
    catalog_limit=100,
    aoi_half_side_km=2,
    minimum_component_area_m2=5_000,
)

V83_RECORDED_AT = "2026-07-21T17:38:10Z"
CARRIER_BYTES = 68_511
CARRIER_SHA256 = "1d6f747e012ff2c34be747fe003f8fc28d715a03b60ff00fd848a9a4942e2bb2"
DEFINITION_BYTES = 98_808
DEFINITION_SHA256 = "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7"
ATLAS_BYTES = 3_154_971
ATLAS_SHA256 = "79f8b647629f0898ce9ae43ebf82216f4c4e838adbaac2d4b112a3e8217bbdb8"
RELEASE_MANIFEST_BYTES = 14_812
RELEASE_MANIFEST_SHA256 = (
    "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5"
)
RELEASE_TREE_SHA256 = (
    "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"
)
PREDECESSOR_QUEUE_BYTES = 531_111
PREDECESSOR_QUEUE_SHA256 = (
    "c734e68b5631ddc623f4624f6a5c81f89ad55a897983e96c8ab4c386ffd76c11"
)
PREDECESSOR_TREE_SHA256 = (
    "03132cf6410970d3518cb5b9431beda4ce6256159ba1a5007cdae09594f988b9"
)
QUEUE_BYTES = 553_692
QUEUE_SHA256 = "8792ee2d80ed9b44d3ef67d3511b29ca0f9160b8ebd641e7f54cf4f5db4e4251"

# These final-bundle pins are set before the one allowed publication. The
# queue JSONL does not depend on generated_at; the manifest and sidecar do.
PUBLISHED_GENERATED_AT = "2026-07-21T18:05:10Z"
PUBLISHED_MANIFEST_BYTES = 19_851
PUBLISHED_MANIFEST_SHA256 = (
    "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd"
)
PUBLISHED_MANIFEST_HASH_BYTES = 80
PUBLISHED_MANIFEST_HASH_SHA256 = (
    "9554a659b8b51925377bc31e99fa29a6fda92a5aa4675c48164d3de28e583288"
)
PUBLISHED_TREE_SHA256 = (
    "2b9fc5a30525e2e815154d1635c49badf06c436e354ccb04a4898e6f42d22eee"
)

EXPECTED_COUNTS = {
    "features_examined": 905,
    "eligible_features_by_kind": {"campus": 474, "project": 431},
    "excluded_features_by_kind": {},
    "skipped_missing_coordinates": 705,
    "entities_queued": 200,
    "queue_jobs": 200,
    "entities_split_at_antimeridian": 0,
    "queued_entities_by_priority_tier": {
        "active_construction": 104,
        "operational": 29,
        "proposed_pipeline": 5,
        "unknown": 62,
    },
    "queued_entities_by_status_freshness": {
        "age_days_0_30": 88,
        "age_days_181_365": 10,
        "age_days_31_90": 19,
        "age_days_366_plus": 4,
        "age_days_91_180": 17,
        "missing": 62,
    },
}
ACTIVE_ENTITY_COUNT = 104
ACTIVE_DISTINCT_AOI_COUNT = 100
ALL_DISTINCT_AOI_COUNT = 139
COORDINATE_METHOD_COUNTS = {"properties.latitude_longitude": 200}
PREDECESSOR_RETAINED_COUNT = 192
INHERITED_POSITION_CHANGE_COUNT = 179
INHERITED_UNCHANGED_POSITION_COUNT = 13
INHERITED_SEMANTIC_CHANGE_COUNT = 0
ADDED_PRIORITY_COUNTS = {"active_construction": 4, "unknown": 4}
ADDED_STATUS_COUNTS = {"under_construction": 4, "unknown": 4}

ADDED_QUEUE_EXPECTATIONS = {
    "satq-3149584b9d40a3049b84371e": {
        "entity_id": "5c6e55e6-1029-5edf-9975-8695c3009b9d",
        "kind": "project",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 14,
        "center_wgs84": {"latitude": 23.1562752, "longitude": 89.2224683},
    },
    "satq-c92ac430b054e36342ee99ed": {
        "entity_id": "d6270e7f-0c83-5d00-8481-6cb753f4b16c",
        "kind": "project",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 25,
        "center_wgs84": {"latitude": -14.075622, "longitude": -75.734798},
    },
    "satq-44d8e1c44fea11bc4dc51efd": {
        "entity_id": "e997ad94-2a62-5c44-90f9-fa27edf77dc2",
        "kind": "project",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 50,
        "center_wgs84": {"latitude": 56.9356302, "longitude": 22.0132503},
    },
    "satq-930a02278f48494c659e3e76": {
        "entity_id": "44130f9f-95af-5f19-9fcf-47aabd3a5c8b",
        "kind": "project",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 102,
        "center_wgs84": {"latitude": 51.2067694, "longitude": 71.4577083},
    },
    "satq-5fa6487ff51fad93294d4bef": {
        "entity_id": "2663ab75-e78a-53cc-80d3-1822e28a0661",
        "kind": "campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 116,
        "center_wgs84": {"latitude": 56.9356302, "longitude": 22.0132503},
    },
    "satq-0051cfe7526fb3b0e67e5c45": {
        "entity_id": "880e258c-1029-5e88-b345-08ee13dacebf",
        "kind": "campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 138,
        "center_wgs84": {"latitude": 23.1562752, "longitude": 89.2224683},
    },
    "satq-8832134a28399085fa57f02f": {
        "entity_id": "baf2b1c7-7af3-5b3e-9c10-4d4dbb364d9b",
        "kind": "campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 157,
        "center_wgs84": {"latitude": -14.075622, "longitude": -75.734798},
    },
    "satq-c5c9a9066a8a6a4ebe0dfa90": {
        "entity_id": "f36d3171-1f21-516a-9ef3-f8a6e4c0471c",
        "kind": "campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 167,
        "center_wgs84": {"latitude": 51.2067694, "longitude": 71.4577083},
    },
}

AUDITED_QUEUE_IDS = (
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
EXPECTED_AUDITED_POSITIONS = (1, 15, 22, 39, 41, 42, 46, 73, 101, 103, 104)
MAX_PUBLICATION_LEAD_SECONDS = 300


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path, label: str, *, mode: int | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise SatelliteQueueV83Error(f"{label} must be a regular file")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise SatelliteQueueV83Error(f"{label} mode differs")
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteQueueV83Error(f"tree root must be a regular directory: {root}")
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
            raise SatelliteQueueV83Error(f"tree contains symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif stat.S_ISREG(metadata.st_mode):
            raw = path.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n".encode()
            )
        else:
            raise SatelliteQueueV83Error(
                f"tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        canonical = carrier._timestamp(value, label)
        parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    except (TypeError, ValueError, carrier.QueueValidationError) as error:
        raise SatelliteQueueV83Error(str(error)) from error
    return parsed.astimezone(UTC)


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise SatelliteQueueV83Error("validation wall clock must include a timezone")
    return result.astimezone(UTC)


def _require_accepted_inputs() -> dict[str, Any]:
    carrier_path = Path(carrier.__file__ or "")
    predecessor_path = PREDECESSOR_QUEUE / carrier.QUEUE_FILENAME
    actual = {
        "carrier": _checkpoint(carrier_path, "satellite queue carrier"),
        "definition": _checkpoint(DEFINITION, "accepted v83 definition", mode=0o444),
        "atlas": _checkpoint(ATLAS, "accepted v83 atlas", mode=0o444),
        "release_manifest": _checkpoint(
            RELEASE_MANIFEST, "accepted v83 release manifest", mode=0o444
        ),
        "release_tree_sha256": _tree_digest(RELEASE),
        "predecessor_queue": _checkpoint(
            predecessor_path, "accepted v73 queue", mode=0o444
        ),
        "predecessor_tree_sha256": _tree_digest(PREDECESSOR_QUEUE),
    }
    expected = {
        "carrier": {"bytes": CARRIER_BYTES, "sha256": CARRIER_SHA256},
        "definition": {"bytes": DEFINITION_BYTES, "sha256": DEFINITION_SHA256},
        "atlas": {"bytes": ATLAS_BYTES, "sha256": ATLAS_SHA256},
        "release_manifest": {
            "bytes": RELEASE_MANIFEST_BYTES,
            "sha256": RELEASE_MANIFEST_SHA256,
        },
        "release_tree_sha256": RELEASE_TREE_SHA256,
        "predecessor_queue": {
            "bytes": PREDECESSOR_QUEUE_BYTES,
            "sha256": PREDECESSOR_QUEUE_SHA256,
        },
        "predecessor_tree_sha256": PREDECESSOR_TREE_SHA256,
    }
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise SatelliteQueueV83Error(
            "accepted v83 queue input drift: " + ", ".join(differing)
        )
    try:
        release_manifest = json.loads(RELEASE_MANIFEST.read_bytes())
        definition = json.loads(DEFINITION.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV83Error("accepted v83 JSON input is invalid") from error
    if (
        release_manifest.get("recorded_at") != V83_RECORDED_AT
        or release_manifest.get("files", {}).get("atlas.geojson")
        != {"bytes": ATLAS_BYTES, "sha256": ATLAS_SHA256}
        or definition.get("release_id") != "2026-07-21-open-seed-v83"
        or definition.get("build", {}).get("recorded_at") != V83_RECORDED_AT
    ):
        raise SatelliteQueueV83Error("accepted v83 release lineage changed")
    return actual


def _release_lineage(raw: bytes) -> Mapping[str, Any]:
    try:
        lineage = carrier._adjacent_release_manifest_lineage(ATLAS, raw)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV83Error(str(error)) from error
    if lineage is None:
        raise SatelliteQueueV83Error("accepted v83 release lineage is absent")
    return lineage


def _bundle(generated_at: str) -> carrier.QueueBundle:
    raw = ATLAS.read_bytes()
    try:
        return carrier.build_queue_bundle(
            raw,
            source_name=ATLAS.name,
            generated_at=generated_at,
            config=CONFIG,
            release_manifest_lineage=_release_lineage(raw),
        )
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV83Error(str(error)) from error


def _payloads(bundle: carrier.QueueBundle) -> dict[str, bytes]:
    return {
        carrier.QUEUE_FILENAME: bundle.queue_bytes,
        carrier.MANIFEST_FILENAME: bundle.manifest_bytes,
        carrier.MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


def _records(raw: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in raw.splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SatelliteQueueV83Error("v83 queue contains a non-object record")
        result.append(value)
    return result


def _atlas_features() -> dict[str, Mapping[str, Any]]:
    try:
        document = json.loads(ATLAS.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV83Error("accepted v83 atlas is invalid JSON") from error
    features = document.get("features")
    if not isinstance(features, list):
        raise SatelliteQueueV83Error("accepted v83 atlas features are absent")
    result: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping) or not isinstance(
            feature.get("properties"), Mapping
        ):
            raise SatelliteQueueV83Error("accepted v83 atlas feature is invalid")
        properties = feature["properties"]
        entity_id = properties.get("entity_id")
        if not isinstance(entity_id, str) or entity_id in result:
            raise SatelliteQueueV83Error("accepted v83 atlas identity inventory differs")
        result[entity_id] = properties
    return result


def _validate_non_inference(
    bundle: carrier.QueueBundle, records: list[dict[str, Any]]
) -> None:
    expected_scope = {
        "purpose": "bounded imagery review planning for existing atlas entities",
        "network_requests_performed": False,
        "imagery_identity_inference": False,
        "imagery_lifecycle_inference": False,
        "imagery_power_inference": False,
        "automatic_entity_merge": False,
    }
    if bundle.manifest.get("scope") != expected_scope:
        raise SatelliteQueueV83Error("v83 queue inference scope differs")
    features = _atlas_features()
    coordinate_methods: dict[str, int] = {}
    forbidden_entity_keys = {
        "capacity_estimates",
        "operating_model",
        "workload_observations",
        "workloads",
    }
    for row in records:
        if row.get("review_constraints") != carrier.REVIEW_CONSTRAINTS:
            raise SatelliteQueueV83Error("v83 queue review constraints differ")
        entity = row["entity"]
        properties = features.get(entity["id"])
        if properties is None:
            raise SatelliteQueueV83Error("v83 queue inferred an entity identity")
        if forbidden_entity_keys & set(entity):
            raise SatelliteQueueV83Error("v83 queue imported a capacity or model claim")
        if (
            entity["kind"] != properties.get("entity_kind")
            or entity["name"]
            != (properties.get("name") or properties.get("stable_key") or entity["id"])
            or entity["target_entity_id"] != properties.get("target_entity_id")
            or entity["status_evidence_id"] != properties.get("status_evidence_id")
            or entity["status_as_of"] != properties.get("status_as_of")
        ):
            raise SatelliteQueueV83Error("v83 queue inferred identity or lifecycle data")
        expected_status = properties.get("status") or "unknown"
        if row["priority"]["lifecycle_status"] != expected_status:
            raise SatelliteQueueV83Error("v83 queue inferred a lifecycle status")
        center = row["location"]["center_wgs84"]
        method = center["method"]
        coordinate_methods[method] = coordinate_methods.get(method, 0) + 1
        if (
            method != "properties.latitude_longitude"
            or center["latitude"] != round(float(properties["latitude"]), 7)
            or center["longitude"] != round(float(properties["longitude"]), 7)
        ):
            raise SatelliteQueueV83Error("v83 queue inferred a coordinate")
    if coordinate_methods != COORDINATE_METHOD_COUNTS:
        raise SatelliteQueueV83Error("v83 coordinate-method inventory differs")


def _delta_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    center = row["location"]["center_wgs84"]
    return {
        "entity_id": row["entity"]["id"],
        "kind": row["entity"]["kind"],
        "priority_tier": row["priority"]["tier"],
        "lifecycle_status": row["priority"]["lifecycle_status"],
        "queue_position": row["queue_position"],
        "center_wgs84": {
            "latitude": center["latitude"],
            "longitude": center["longitude"],
        },
    }


def _validate_delta(records: list[dict[str, Any]]) -> None:
    predecessor = _records(
        (PREDECESSOR_QUEUE / carrier.QUEUE_FILENAME).read_bytes()
    )
    predecessor_by_id = {row["queue_id"]: row for row in predecessor}
    successor_by_id = {row["queue_id"]: row for row in records}
    added = set(successor_by_id) - set(predecessor_by_id)
    removed = set(predecessor_by_id) - set(successor_by_id)
    position_changes = 0
    semantic_changes = 0
    for queue_id in set(predecessor_by_id) & set(successor_by_id):
        before = dict(predecessor_by_id[queue_id])
        after = dict(successor_by_id[queue_id])
        if before.pop("queue_position") != after.pop("queue_position"):
            position_changes += 1
        if before != after:
            semantic_changes += 1
    if (
        len(predecessor) != PREDECESSOR_RETAINED_COUNT
        or removed
        or added != set(ADDED_QUEUE_EXPECTATIONS)
        or {
            queue_id: _delta_projection(successor_by_id[queue_id])
            for queue_id in added
        }
        != ADDED_QUEUE_EXPECTATIONS
        or position_changes != INHERITED_POSITION_CHANGE_COUNT
        or PREDECESSOR_RETAINED_COUNT - position_changes
        != INHERITED_UNCHANGED_POSITION_COUNT
        or semantic_changes != INHERITED_SEMANTIC_CHANGE_COUNT
    ):
        raise SatelliteQueueV83Error("v83-to-v73 queue delta differs")


def _validate_semantics(bundle: carrier.QueueBundle) -> None:
    if len(bundle.queue_bytes) != QUEUE_BYTES or _sha256(bundle.queue_bytes) != QUEUE_SHA256:
        raise SatelliteQueueV83Error("v83 queue JSONL differs from its accepted pin")
    counts = bundle.manifest.get("counts")
    if not isinstance(counts, Mapping) or any(
        counts.get(key) != value for key, value in EXPECTED_COUNTS.items()
    ):
        raise SatelliteQueueV83Error("v83 queue counts differ")
    records = _records(bundle.queue_bytes)
    active = [row for row in records if row["priority"]["tier"] == "active_construction"]
    all_aois = {tuple(row["location"]["aoi_bbox_wgs84"]) for row in records}
    active_aois = {
        tuple(row["location"]["aoi_bbox_wgs84"]) for row in active
    }
    by_id = {row["queue_id"]: row for row in records}
    added_rows = [by_id[queue_id] for queue_id in ADDED_QUEUE_EXPECTATIONS]
    priority_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for row in added_rows:
        tier = row["priority"]["tier"]
        status_value = row["priority"]["lifecycle_status"]
        priority_counts[tier] = priority_counts.get(tier, 0) + 1
        status_counts[status_value] = status_counts.get(status_value, 0) + 1
    if (
        len(records) != EXPECTED_COUNTS["queue_jobs"]
        or len(active) != ACTIVE_ENTITY_COUNT
        or len(active_aois) != ACTIVE_DISTINCT_AOI_COUNT
        or len(all_aois) != ALL_DISTINCT_AOI_COUNT
        or any(queue_id not in by_id for queue_id in AUDITED_QUEUE_IDS)
        or tuple(by_id[queue_id]["queue_position"] for queue_id in AUDITED_QUEUE_IDS)
        != EXPECTED_AUDITED_POSITIONS
        or priority_counts != ADDED_PRIORITY_COUNTS
        or status_counts != ADDED_STATUS_COUNTS
    ):
        raise SatelliteQueueV83Error("v83 priority, AOI, or audited-order boundary differs")
    _validate_non_inference(bundle, records)
    _validate_delta(records)


def _write_stage(stage: Path, bundle: carrier.QueueBundle) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise SatelliteQueueV83Error("v83 private stage must be a regular directory")
    for name, raw in _payloads(bundle).items():
        path = stage / name
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        path.chmod(0o444)
    stage.chmod(0o555)
    carrier._fsync_directory(stage)


def _stage_paths(stage: Path) -> tuple[Path, ...]:
    if stage.is_symlink() or not stage.is_dir():
        raise SatelliteQueueV83Error("v83 private stage changed type")
    entries = sorted(stage.iterdir(), key=lambda path: path.name)
    if {path.name for path in entries} != carrier.QUEUE_BUNDLE_FILES or any(
        path.is_symlink() or not path.is_file() for path in entries
    ):
        raise SatelliteQueueV83Error("v83 private stage file set changed")
    return (stage, *entries)


def _assert_stage_precedes_target(stage: Path, target: datetime) -> None:
    for path in _stage_paths(stage):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise SatelliteQueueV83Error(
                f"v83 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctime(path: Path, target: datetime) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SatelliteQueueV83Error("v83 final queue root is absent or invalid")
    if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target.timestamp():
        raise SatelliteQueueV83Error("v83 final queue rename predates generated_at")


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SatelliteQueueV83Error("v83 private stage must remain a directory")
    return metadata.st_dev, metadata.st_ino


def _discard_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise SatelliteQueueV83Error("refusing substituted v83 stage cleanup")
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(carrier.QUEUE_BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SatelliteQueueV83Error("refusing contaminated v83 stage cleanup")
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _require_absent(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise SatelliteQueueV83Error(f"{label} v83 queue path is occupied: {path}")


@contextmanager
def _publication_lock(path: Path) -> Iterator[None]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise SatelliteQueueV83Error(
            f"active v83 queue publication lock: {path}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def validate_satellite_queue_v83(
    path: str | Path = QUEUE,
    *,
    require_live: bool = True,
    require_frozen: bool = True,
    require_final_root_ctime: bool | None = None,
    validation_wall_clock: datetime | None = None,
) -> Mapping[str, Any]:
    """Rebuild and verify an exact v83 queue bundle without network access."""

    _require_accepted_inputs()
    directory = Path(path)
    try:
        manifest = carrier.validate_queue_bundle(directory)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV83Error(str(error)) from error
    generated = _parse_timestamp(manifest.get("generated_at"), "v83 queue generated_at")
    if generated <= _parse_timestamp(V83_RECORDED_AT, "v83 recorded_at"):
        raise SatelliteQueueV83Error("v83 queue must follow its accepted release")
    if require_live and generated > _wall_clock(validation_wall_clock):
        raise SatelliteQueueV83Error("v83 queue generated_at is not yet live")
    rebuilt = _bundle(manifest["generated_at"])
    _validate_semantics(rebuilt)
    for name, expected in _payloads(rebuilt).items():
        if (directory / name).read_bytes() != expected:
            raise SatelliteQueueV83Error(f"v83 queue artifact differs: {name}")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
            stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in directory.iterdir()
        ):
            raise SatelliteQueueV83Error("v83 queue must be frozen 0555/0444")
    if require_final_root_ctime is None:
        require_final_root_ctime = directory.resolve() == QUEUE.resolve()
    if directory.resolve() == QUEUE.resolve():
        final_checkpoints = {
            carrier.QUEUE_FILENAME: _checkpoint(
                directory / carrier.QUEUE_FILENAME, "published v83 queue"
            ),
            carrier.MANIFEST_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_FILENAME, "published v83 manifest"
            ),
            carrier.MANIFEST_HASH_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_HASH_FILENAME,
                "published v83 manifest sidecar",
            ),
        }
        expected_checkpoints = {
            carrier.QUEUE_FILENAME: {"bytes": QUEUE_BYTES, "sha256": QUEUE_SHA256},
            carrier.MANIFEST_FILENAME: {
                "bytes": PUBLISHED_MANIFEST_BYTES,
                "sha256": PUBLISHED_MANIFEST_SHA256,
            },
            carrier.MANIFEST_HASH_FILENAME: {
                "bytes": PUBLISHED_MANIFEST_HASH_BYTES,
                "sha256": PUBLISHED_MANIFEST_HASH_SHA256,
            },
        }
        if (
            manifest["generated_at"] != PUBLISHED_GENERATED_AT
            or final_checkpoints != expected_checkpoints
            or _tree_digest(directory) != PUBLISHED_TREE_SHA256
        ):
            raise SatelliteQueueV83Error("published v83 queue pins changed")
    if require_final_root_ctime:
        _assert_final_root_ctime(directory, generated)
    return manifest


def _wait_until(
    target: float,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    while True:
        remaining = target - clock()
        if remaining <= 0:
            return
        sleeper(min(remaining, 0.25))


def _publish_to(
    output: Path,
    lock: Path,
    *,
    generated_at: str,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> Mapping[str, Any]:
    target = _parse_timestamp(generated_at, "v83 queue generated_at")
    now = clock()
    if now >= target.timestamp():
        raise SatelliteQueueV83Error(
            "v83 queue generated_at must be future before private staging"
        )
    if target.timestamp() - now > MAX_PUBLICATION_LEAD_SECONDS:
        raise SatelliteQueueV83Error("v83 queue publication is over five minutes ahead")
    _require_accepted_inputs()
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteQueueV83Error("v83 queue output parent must be a regular directory")
    if lock.parent != parent.parent and lock.parent != ROOT:
        raise SatelliteQueueV83Error("v83 queue publication lock parent is invalid")

    with _publication_lock(lock):
        _require_absent(output, "initial")
        first = _bundle(generated_at)
        _require_absent(output, "between private builds")
        second = _bundle(generated_at)
        if _payloads(first) != _payloads(second) or first.manifest != second.manifest:
            raise SatelliteQueueV83Error("two private v83 queue builds differ")
        _validate_semantics(first)

        first_stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-a-", dir=parent))
        second_stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-b-", dir=parent))
        first_identity = _identity(first_stage)
        second_identity = _identity(second_stage)
        promoted = False
        try:
            _write_stage(first_stage, first)
            _write_stage(second_stage, second)
            validate_satellite_queue_v83(
                first_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            validate_satellite_queue_v83(
                second_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            first_tree = _tree_digest(first_stage)
            if first_tree != _tree_digest(second_stage):
                raise SatelliteQueueV83Error("two private v83 queue trees differ")
            first_payload_checkpoint = {
                name: _checkpoint(first_stage / name, f"staged {name}")
                for name in carrier.QUEUE_BUNDLE_FILES
            }
            _assert_stage_precedes_target(first_stage, target)
            _assert_stage_precedes_target(second_stage, target)
            _require_absent(output, "pre-wait")
            _discard_stage(second_stage, second_identity)
            _wait_until(target.timestamp(), clock=clock, sleeper=sleeper)
            if clock() < target.timestamp():
                raise SatelliteQueueV83Error("v83 queue generated_at is not yet live")
            _require_absent(output, "late")
            validate_satellite_queue_v83(
                first_stage,
                require_live=True,
                require_final_root_ctime=False,
                validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
            )
            if (
                _tree_digest(first_stage) != first_tree
                or {
                    name: _checkpoint(first_stage / name, f"staged {name}")
                    for name in carrier.QUEUE_BUNDLE_FILES
                }
                != first_payload_checkpoint
            ):
                raise SatelliteQueueV83Error(
                    "v83 private queue stage changed while awaiting publication"
                )
            first_stage.chmod(0o755)
            try:
                promote_noreplace(first_stage, output)
            except SystemExit as error:
                raise SatelliteQueueV83Error(str(error)) from error
            promoted = True
            output.chmod(0o555)
            carrier._fsync_directory(parent)
            _assert_final_root_ctime(output, target)
        except BaseException as primary_error:
            if not promoted and not output.exists() and not output.is_symlink():
                for stage, identity in (
                    (first_stage, first_identity),
                    (second_stage, second_identity),
                ):
                    try:
                        _discard_stage(stage, identity)
                    except Exception as cleanup_error:
                        primary_error.add_note(
                            f"v83 queue stage cleanup failed: {cleanup_error}"
                        )
            raise
    return validate_satellite_queue_v83(
        output,
        validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
        require_final_root_ctime=True,
    )


def publish_satellite_queue_v83(
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Publish the single reserved frozen v83 queue path."""

    if generated_at != PUBLISHED_GENERATED_AT:
        raise SatelliteQueueV83Error(
            "v83 publication timestamp differs from the accepted final pin"
        )
    return _publish_to(
        QUEUE,
        PUBLICATION_LOCK,
        generated_at=generated_at,
        clock=_clock,
        sleeper=_sleep,
    )


__all__ = [
    "ACTIVE_DISTINCT_AOI_COUNT",
    "ACTIVE_ENTITY_COUNT",
    "ADDED_PRIORITY_COUNTS",
    "ADDED_QUEUE_EXPECTATIONS",
    "ADDED_STATUS_COUNTS",
    "ALL_DISTINCT_AOI_COUNT",
    "ATLAS",
    "ATLAS_SHA256",
    "AUDITED_QUEUE_IDS",
    "CONFIG",
    "COORDINATE_METHOD_COUNTS",
    "DEFINITION",
    "EXPECTED_AUDITED_POSITIONS",
    "EXPECTED_COUNTS",
    "INHERITED_POSITION_CHANGE_COUNT",
    "INHERITED_SEMANTIC_CHANGE_COUNT",
    "INHERITED_UNCHANGED_POSITION_COUNT",
    "PREDECESSOR_QUEUE",
    "PREDECESSOR_RETAINED_COUNT",
    "PUBLISHED_GENERATED_AT",
    "PUBLISHED_MANIFEST_HASH_SHA256",
    "PUBLISHED_MANIFEST_SHA256",
    "PUBLISHED_TREE_SHA256",
    "QUEUE",
    "QUEUE_BYTES",
    "QUEUE_SHA256",
    "RELEASE",
    "RELEASE_MANIFEST_SHA256",
    "RELEASE_TREE_SHA256",
    "SatelliteQueueV83Error",
    "publish_satellite_queue_v83",
    "validate_satellite_queue_v83",
]
