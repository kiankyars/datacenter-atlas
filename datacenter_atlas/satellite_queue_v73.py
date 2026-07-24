"""Strict, offline publisher for the accepted open-seed v73 satellite queue.

The generic queue builder remains unchanged.  This successor pins its exact
implementation and the accepted v73 release, rebuilds the queue twice while
the final path is absent, and publishes the frozen bundle with an atomic
no-replace rename only after ``generated_at`` becomes live.
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


class SatelliteQueueV73Error(ValueError):
    """Raised when the accepted input or publication boundary is violated."""


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
ATLAS = RELEASE / "atlas.geojson"
RELEASE_MANIFEST = RELEASE / carrier.MANIFEST_FILENAME
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v73"
PUBLICATION_LOCK = ROOT / ".satellite-review-queue-v73.lock"

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

CARRIER_SHA256 = "1d6f747e012ff2c34be747fe003f8fc28d715a03b60ff00fd848a9a4942e2bb2"
DEFINITION_BYTES = 88_004
DEFINITION_SHA256 = "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
ATLAS_BYTES = 2_885_700
ATLAS_SHA256 = "691585d470e7284f0185515d63f3c9b0507f528f039f3070804790927ee48672"
RELEASE_MANIFEST_BYTES = 12_814
RELEASE_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
RELEASE_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
QUEUE_BYTES = 531_111
QUEUE_SHA256 = "c734e68b5631ddc623f4624f6a5c81f89ad55a897983e96c8ab4c386ffd76c11"
PUBLISHED_GENERATED_AT = "2026-07-21T14:42:00Z"
PUBLISHED_MANIFEST_BYTES = 17_330
PUBLISHED_MANIFEST_SHA256 = (
    "bf6a6e94ad3cad3f3f0d67b54ca4821c0fa4db7a2c50711ef6500c1d4aba2af4"
)
PUBLISHED_MANIFEST_HASH_BYTES = 80
PUBLISHED_MANIFEST_HASH_SHA256 = (
    "46414d16bd800c4a9abb21a49f81acf6463dc9c50d872e4db8709910183bf8df"
)
PUBLISHED_TREE_SHA256 = (
    "03132cf6410970d3518cb5b9431beda4ce6256159ba1a5007cdae09594f988b9"
)
EXPECTED_COUNTS = {
    "features_examined": 818,
    "eligible_features_by_kind": {"campus": 431, "project": 387},
    "excluded_features_by_kind": {},
    "skipped_missing_coordinates": 626,
    "entities_queued": 192,
    "queue_jobs": 192,
    "entities_split_at_antimeridian": 0,
    "queued_entities_by_priority_tier": {
        "active_construction": 100,
        "operational": 29,
        "proposed_pipeline": 5,
        "unknown": 58,
    },
}
ACTIVE_ENTITY_COUNT = 100
ACTIVE_DISTINCT_AOI_COUNT = 96
ADDED_QUEUE_EXPECTATIONS = {
    "satq-415d80a31d8798a2e2c06d17": {
        "entity_id": "19f6a887-c4b1-57a7-9fee-2f11325a5b1d",
        "kind": "project",
        "priority_tier": "active_construction",
        "queue_position": 8,
    },
    "satq-e6e1ceab9c56fe15b25e03f4": {
        "entity_id": "cafab9a5-428c-5442-98d3-3784f9ecc7bb",
        "kind": "project",
        "priority_tier": "active_construction",
        "queue_position": 16,
    },
    "satq-6b4e4c670860247f4fc9f979": {
        "entity_id": "2d63fc14-9ccf-53aa-918f-65bbcd87d909",
        "kind": "campus",
        "priority_tier": "unknown",
        "queue_position": 113,
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
EXPECTED_AUDITED_POSITIONS = (1, 14, 21, 37, 39, 40, 44, 70, 98, 99, 100)
MAX_PUBLICATION_LEAD_SECONDS = 300


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise SatelliteQueueV73Error(f"{label} must be a regular file")
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteQueueV73Error(f"tree root must be a regular directory: {root}")
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
            raise SatelliteQueueV73Error(f"tree contains symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
        elif stat.S_ISREG(metadata.st_mode):
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode("utf-8")
            )
        else:
            raise SatelliteQueueV73Error(
                f"tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        canonical = carrier._timestamp(value, label)
        parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    except (TypeError, ValueError, carrier.QueueValidationError) as error:
        raise SatelliteQueueV73Error(str(error)) from error
    return parsed.astimezone(UTC)


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise SatelliteQueueV73Error("validation wall clock must include a timezone")
    return result.astimezone(UTC)


def _require_accepted_inputs() -> dict[str, Any]:
    carrier_path = Path(carrier.__file__ or "")
    actual = {
        "carrier": _checkpoint(carrier_path, "satellite queue carrier"),
        "definition": _checkpoint(DEFINITION, "accepted v73 definition"),
        "atlas": _checkpoint(ATLAS, "accepted v73 atlas"),
        "release_manifest": _checkpoint(
            RELEASE_MANIFEST, "accepted v73 release manifest"
        ),
        "release_tree_sha256": _tree_digest(RELEASE),
    }
    expected = {
        "carrier": {
            "bytes": carrier_path.stat().st_size,
            "sha256": CARRIER_SHA256,
        },
        "definition": {
            "bytes": DEFINITION_BYTES,
            "sha256": DEFINITION_SHA256,
        },
        "atlas": {"bytes": ATLAS_BYTES, "sha256": ATLAS_SHA256},
        "release_manifest": {
            "bytes": RELEASE_MANIFEST_BYTES,
            "sha256": RELEASE_MANIFEST_SHA256,
        },
        "release_tree_sha256": RELEASE_TREE_SHA256,
    }
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise SatelliteQueueV73Error(
            "accepted v73 queue input drift: " + ", ".join(differing)
        )
    try:
        release_manifest = json.loads(RELEASE_MANIFEST.read_bytes())
        definition = json.loads(DEFINITION.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV73Error("accepted v73 JSON input is invalid") from error
    if (
        release_manifest.get("recorded_at") != "2026-07-21T13:15:51Z"
        or release_manifest.get("files", {}).get("atlas.geojson")
        != {"bytes": ATLAS_BYTES, "sha256": ATLAS_SHA256}
        or definition.get("build", {}).get("recorded_at")
        != release_manifest.get("recorded_at")
    ):
        raise SatelliteQueueV73Error("accepted v73 release lineage changed")
    return actual


def _release_lineage(raw: bytes) -> Mapping[str, Any]:
    try:
        lineage = carrier._adjacent_release_manifest_lineage(ATLAS, raw)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV73Error(str(error)) from error
    if lineage is None:
        raise SatelliteQueueV73Error("accepted v73 release manifest lineage is absent")
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
        raise SatelliteQueueV73Error(str(error)) from error


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
            raise SatelliteQueueV73Error("v73 queue contains a non-object record")
        result.append(value)
    return result


def _validate_semantics(bundle: carrier.QueueBundle) -> None:
    if len(bundle.queue_bytes) != QUEUE_BYTES or _sha256(bundle.queue_bytes) != QUEUE_SHA256:
        raise SatelliteQueueV73Error("v73 queue JSONL differs from its accepted pin")
    counts = bundle.manifest.get("counts")
    if not isinstance(counts, Mapping) or any(
        counts.get(key) != value for key, value in EXPECTED_COUNTS.items()
    ):
        raise SatelliteQueueV73Error("v73 queue counts differ")
    records = _records(bundle.queue_bytes)
    active = [row for row in records if row["priority"]["tier"] == "active_construction"]
    distinct_aois = {
        tuple(row["location"]["aoi_bbox_wgs84"])
        for row in active
    }
    by_id = {row["queue_id"]: row for row in records}
    if (
        len(records) != EXPECTED_COUNTS["queue_jobs"]
        or len(active) != ACTIVE_ENTITY_COUNT
        or len(distinct_aois) != ACTIVE_DISTINCT_AOI_COUNT
        or tuple(by_id) == ()
        or any(queue_id not in by_id for queue_id in AUDITED_QUEUE_IDS)
        or tuple(by_id[queue_id]["queue_position"] for queue_id in AUDITED_QUEUE_IDS)
        != EXPECTED_AUDITED_POSITIONS
        or any(
            by_id[queue_id]["priority"]["tier"] != "active_construction"
            for queue_id in AUDITED_QUEUE_IDS
        )
        or {
            queue_id: {
                "entity_id": row["entity"]["id"],
                "kind": row["entity"]["kind"],
                "priority_tier": row["priority"]["tier"],
                "queue_position": row["queue_position"],
            }
            for queue_id, row in by_id.items()
            if queue_id in ADDED_QUEUE_EXPECTATIONS
        }
        != ADDED_QUEUE_EXPECTATIONS
        or any(
            row["review_constraints"].get(flag) is not False
            for row in records
            for flag in (
                "imagery_identity_claim",
                "imagery_lifecycle_claim",
                "imagery_operating_status_claim",
                "imagery_power_claim",
            )
        )
    ):
        raise SatelliteQueueV73Error("v73 active/AOI/addition/claim boundary differs")


def _write_stage(stage: Path, bundle: carrier.QueueBundle) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise SatelliteQueueV73Error("v73 private stage must be a regular directory")
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
        raise SatelliteQueueV73Error("v73 private stage changed type")
    entries = sorted(stage.iterdir(), key=lambda path: path.name)
    if {path.name for path in entries} != carrier.QUEUE_BUNDLE_FILES or any(
        path.is_symlink() or not path.is_file() for path in entries
    ):
        raise SatelliteQueueV73Error("v73 private stage file set changed")
    return (stage, *entries)


def _assert_stage_precedes_target(stage: Path, target: datetime) -> None:
    for path in _stage_paths(stage):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise SatelliteQueueV73Error(
                f"v73 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctime(path: Path, target: datetime) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SatelliteQueueV73Error("v73 final queue root is absent or invalid")
    if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target.timestamp():
        raise SatelliteQueueV73Error("v73 final queue rename predates generated_at")


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SatelliteQueueV73Error("v73 private stage must remain a directory")
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
        raise SatelliteQueueV73Error("refusing substituted v73 stage cleanup")
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(carrier.QUEUE_BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SatelliteQueueV73Error("refusing contaminated v73 stage cleanup")
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _require_absent(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise SatelliteQueueV73Error(f"{label} v73 queue path is occupied: {path}")


@contextmanager
def _publication_lock(path: Path) -> Iterator[None]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise SatelliteQueueV73Error(f"active v73 queue publication lock: {path}") from error
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


def validate_satellite_queue_v73(
    path: str | Path = QUEUE,
    *,
    require_live: bool = True,
    require_frozen: bool = True,
    require_final_root_ctime: bool | None = None,
    validation_wall_clock: datetime | None = None,
) -> Mapping[str, Any]:
    """Rebuild and verify an exact v73 queue bundle without network access."""

    _require_accepted_inputs()
    directory = Path(path)
    try:
        manifest = carrier.validate_queue_bundle(directory)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV73Error(str(error)) from error
    generated = _parse_timestamp(manifest.get("generated_at"), "v73 queue generated_at")
    if generated <= _parse_timestamp("2026-07-21T13:15:51Z", "v73 recorded_at"):
        raise SatelliteQueueV73Error("v73 queue must follow its accepted release")
    if require_live and generated > _wall_clock(validation_wall_clock):
        raise SatelliteQueueV73Error("v73 queue generated_at is not yet live")
    rebuilt = _bundle(manifest["generated_at"])
    _validate_semantics(rebuilt)
    for name, expected in _payloads(rebuilt).items():
        if (directory / name).read_bytes() != expected:
            raise SatelliteQueueV73Error(f"v73 queue artifact differs: {name}")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
            stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in directory.iterdir()
        ):
            raise SatelliteQueueV73Error("v73 queue must be frozen 0555/0444")
    if require_final_root_ctime is None:
        require_final_root_ctime = directory.resolve() == QUEUE.resolve()
    if directory.resolve() == QUEUE.resolve():
        final_checkpoints = {
            carrier.QUEUE_FILENAME: _checkpoint(
                directory / carrier.QUEUE_FILENAME, "published v73 queue"
            ),
            carrier.MANIFEST_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_FILENAME, "published v73 manifest"
            ),
            carrier.MANIFEST_HASH_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_HASH_FILENAME,
                "published v73 manifest sidecar",
            ),
        }
        expected_checkpoints = {
            carrier.QUEUE_FILENAME: {
                "bytes": QUEUE_BYTES,
                "sha256": QUEUE_SHA256,
            },
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
            raise SatelliteQueueV73Error("published v73 queue pins changed")
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
    target = _parse_timestamp(generated_at, "v73 queue generated_at")
    now = clock()
    if now >= target.timestamp():
        raise SatelliteQueueV73Error(
            "v73 queue generated_at must be future before private staging"
        )
    if target.timestamp() - now > MAX_PUBLICATION_LEAD_SECONDS:
        raise SatelliteQueueV73Error("v73 queue publication is over five minutes ahead")
    _require_accepted_inputs()
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteQueueV73Error("v73 queue output parent must be a regular directory")
    if lock.parent != parent.parent and lock.parent != ROOT:
        raise SatelliteQueueV73Error("v73 queue publication lock parent is invalid")

    with _publication_lock(lock):
        _require_absent(output, "initial")
        first = _bundle(generated_at)
        _require_absent(output, "between private builds")
        second = _bundle(generated_at)
        if _payloads(first) != _payloads(second) or first.manifest != second.manifest:
            raise SatelliteQueueV73Error("two private v73 queue builds differ")
        _validate_semantics(first)

        first_stage = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.stage-a-", dir=parent)
        )
        second_stage = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.stage-b-", dir=parent)
        )
        first_identity = _identity(first_stage)
        second_identity = _identity(second_stage)
        promoted = False
        try:
            _write_stage(first_stage, first)
            _write_stage(second_stage, second)
            validate_satellite_queue_v73(
                first_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            validate_satellite_queue_v73(
                second_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            first_tree = _tree_digest(first_stage)
            if first_tree != _tree_digest(second_stage):
                raise SatelliteQueueV73Error("two private v73 queue trees differ")
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
                raise SatelliteQueueV73Error("v73 queue generated_at is not yet live")
            _require_absent(output, "late")
            validate_satellite_queue_v73(
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
                raise SatelliteQueueV73Error(
                    "v73 private queue stage changed while awaiting publication"
                )
            first_stage.chmod(0o755)
            try:
                promote_noreplace(first_stage, output)
            except SystemExit as error:
                raise SatelliteQueueV73Error(str(error)) from error
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
                            f"v73 queue stage cleanup failed: {cleanup_error}"
                        )
            raise
    return validate_satellite_queue_v73(
        output,
        validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
        require_final_root_ctime=True,
    )


def publish_satellite_queue_v73(
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Publish the single reserved frozen v73 queue path."""

    if generated_at != PUBLISHED_GENERATED_AT:
        raise SatelliteQueueV73Error(
            "v73 publication timestamp differs from the accepted final pin"
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
    "ADDED_QUEUE_EXPECTATIONS",
    "ACTIVE_ENTITY_COUNT",
    "ATLAS",
    "ATLAS_SHA256",
    "AUDITED_QUEUE_IDS",
    "CONFIG",
    "DEFINITION",
    "EXPECTED_AUDITED_POSITIONS",
    "EXPECTED_COUNTS",
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
    "SatelliteQueueV73Error",
    "publish_satellite_queue_v73",
    "validate_satellite_queue_v73",
]
