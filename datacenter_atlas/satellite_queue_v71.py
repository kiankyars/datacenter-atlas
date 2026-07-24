"""Strict, offline publisher for the accepted open-seed v71 satellite queue.

The generic queue builder remains unchanged.  This successor pins its exact
implementation and the accepted v71 release, rebuilds the queue twice while
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


class SatelliteQueueV71Error(ValueError):
    """Raised when the accepted input or publication boundary is violated."""


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
ATLAS = RELEASE / "atlas.geojson"
RELEASE_MANIFEST = RELEASE / carrier.MANIFEST_FILENAME
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v71"
PUBLICATION_LOCK = ROOT / ".satellite-review-queue-v71.lock"

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
DEFINITION_BYTES = 86_839
DEFINITION_SHA256 = "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
ATLAS_BYTES = 2_858_831
ATLAS_SHA256 = "7eaf66f3f7a760901dd2ad75d3c7e07c90d4bdfea5120e35ea9f6f7225c31a8d"
RELEASE_MANIFEST_BYTES = 12_577
RELEASE_MANIFEST_SHA256 = (
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
)
RELEASE_TREE_SHA256 = (
    "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"
)
QUEUE_BYTES = 522_456
QUEUE_SHA256 = "462a3d4b8f482fecb0ccd325d9aac393f69e02fe86ad9dbfcb3b5aa74c700000"
PUBLISHED_GENERATED_AT = "2026-07-21T13:06:30Z"
PUBLISHED_MANIFEST_BYTES = 17_073
PUBLISHED_MANIFEST_SHA256 = (
    "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000"
)
PUBLISHED_MANIFEST_HASH_BYTES = 80
PUBLISHED_MANIFEST_HASH_SHA256 = (
    "ca0314d3adacf71ca6957a65435e9f95e495e2973e3fef7b023fdab36f3f4aeb"
)
PUBLISHED_TREE_SHA256 = (
    "4927ecb00b2e3d47c992ac3747f2e82505fb8e7d56a9d181245c8a3666db1a2d"
)
EXPECTED_COUNTS = {
    "features_examined": 810,
    "eligible_features_by_kind": {"campus": 427, "project": 383},
    "excluded_features_by_kind": {},
    "skipped_missing_coordinates": 621,
    "entities_queued": 189,
    "queue_jobs": 189,
    "entities_split_at_antimeridian": 0,
    "queued_entities_by_priority_tier": {
        "active_construction": 98,
        "operational": 29,
        "proposed_pipeline": 5,
        "unknown": 57,
    },
}
ACTIVE_ENTITY_COUNT = 98
ACTIVE_DISTINCT_AOI_COUNT = 94
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
EXPECTED_AUDITED_POSITIONS = (1, 13, 19, 35, 37, 38, 42, 68, 96, 97, 98)
MAX_PUBLICATION_LEAD_SECONDS = 300


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise SatelliteQueueV71Error(f"{label} must be a regular file")
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteQueueV71Error(f"tree root must be a regular directory: {root}")
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
            raise SatelliteQueueV71Error(f"tree contains symlink: {relative}")
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
            raise SatelliteQueueV71Error(
                f"tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        canonical = carrier._timestamp(value, label)
        parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    except (TypeError, ValueError, carrier.QueueValidationError) as error:
        raise SatelliteQueueV71Error(str(error)) from error
    return parsed.astimezone(UTC)


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise SatelliteQueueV71Error("validation wall clock must include a timezone")
    return result.astimezone(UTC)


def _require_accepted_inputs() -> dict[str, Any]:
    carrier_path = Path(carrier.__file__ or "")
    actual = {
        "carrier": _checkpoint(carrier_path, "satellite queue carrier"),
        "definition": _checkpoint(DEFINITION, "accepted v71 definition"),
        "atlas": _checkpoint(ATLAS, "accepted v71 atlas"),
        "release_manifest": _checkpoint(
            RELEASE_MANIFEST, "accepted v71 release manifest"
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
        raise SatelliteQueueV71Error(
            "accepted v71 queue input drift: " + ", ".join(differing)
        )
    try:
        release_manifest = json.loads(RELEASE_MANIFEST.read_bytes())
        definition = json.loads(DEFINITION.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV71Error("accepted v71 JSON input is invalid") from error
    if (
        release_manifest.get("recorded_at") != "2026-07-21T10:17:38Z"
        or release_manifest.get("files", {}).get("atlas.geojson")
        != {"bytes": ATLAS_BYTES, "sha256": ATLAS_SHA256}
        or definition.get("build", {}).get("recorded_at")
        != release_manifest.get("recorded_at")
    ):
        raise SatelliteQueueV71Error("accepted v71 release lineage changed")
    return actual


def _release_lineage(raw: bytes) -> Mapping[str, Any]:
    try:
        lineage = carrier._adjacent_release_manifest_lineage(ATLAS, raw)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV71Error(str(error)) from error
    if lineage is None:
        raise SatelliteQueueV71Error("accepted v71 release manifest lineage is absent")
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
        raise SatelliteQueueV71Error(str(error)) from error


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
            raise SatelliteQueueV71Error("v71 queue contains a non-object record")
        result.append(value)
    return result


def _validate_semantics(bundle: carrier.QueueBundle) -> None:
    if len(bundle.queue_bytes) != QUEUE_BYTES or _sha256(bundle.queue_bytes) != QUEUE_SHA256:
        raise SatelliteQueueV71Error("v71 queue JSONL differs from its accepted pin")
    counts = bundle.manifest.get("counts")
    if not isinstance(counts, Mapping) or any(
        counts.get(key) != value for key, value in EXPECTED_COUNTS.items()
    ):
        raise SatelliteQueueV71Error("v71 queue counts differ")
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
    ):
        raise SatelliteQueueV71Error("v71 active/AOI/audited selection boundary differs")


def _write_stage(stage: Path, bundle: carrier.QueueBundle) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise SatelliteQueueV71Error("v71 private stage must be a regular directory")
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
        raise SatelliteQueueV71Error("v71 private stage changed type")
    entries = sorted(stage.iterdir(), key=lambda path: path.name)
    if {path.name for path in entries} != carrier.QUEUE_BUNDLE_FILES or any(
        path.is_symlink() or not path.is_file() for path in entries
    ):
        raise SatelliteQueueV71Error("v71 private stage file set changed")
    return (stage, *entries)


def _assert_stage_precedes_target(stage: Path, target: datetime) -> None:
    for path in _stage_paths(stage):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise SatelliteQueueV71Error(
                f"v71 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctime(path: Path, target: datetime) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SatelliteQueueV71Error("v71 final queue root is absent or invalid")
    if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target.timestamp():
        raise SatelliteQueueV71Error("v71 final queue rename predates generated_at")


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SatelliteQueueV71Error("v71 private stage must remain a directory")
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
        raise SatelliteQueueV71Error("refusing substituted v71 stage cleanup")
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(carrier.QUEUE_BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SatelliteQueueV71Error("refusing contaminated v71 stage cleanup")
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _require_absent(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise SatelliteQueueV71Error(f"{label} v71 queue path is occupied: {path}")


@contextmanager
def _publication_lock(path: Path) -> Iterator[None]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise SatelliteQueueV71Error(f"active v71 queue publication lock: {path}") from error
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


def validate_satellite_queue_v71(
    path: str | Path = QUEUE,
    *,
    require_live: bool = True,
    require_frozen: bool = True,
    require_final_root_ctime: bool | None = None,
    validation_wall_clock: datetime | None = None,
) -> Mapping[str, Any]:
    """Rebuild and verify an exact v71 queue bundle without network access."""

    _require_accepted_inputs()
    directory = Path(path)
    try:
        manifest = carrier.validate_queue_bundle(directory)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV71Error(str(error)) from error
    generated = _parse_timestamp(manifest.get("generated_at"), "v71 queue generated_at")
    if generated <= _parse_timestamp("2026-07-21T10:17:38Z", "v71 recorded_at"):
        raise SatelliteQueueV71Error("v71 queue must follow its accepted release")
    if require_live and generated > _wall_clock(validation_wall_clock):
        raise SatelliteQueueV71Error("v71 queue generated_at is not yet live")
    rebuilt = _bundle(manifest["generated_at"])
    _validate_semantics(rebuilt)
    for name, expected in _payloads(rebuilt).items():
        if (directory / name).read_bytes() != expected:
            raise SatelliteQueueV71Error(f"v71 queue artifact differs: {name}")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
            stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in directory.iterdir()
        ):
            raise SatelliteQueueV71Error("v71 queue must be frozen 0555/0444")
    if require_final_root_ctime is None:
        require_final_root_ctime = directory.resolve() == QUEUE.resolve()
    if directory.resolve() == QUEUE.resolve():
        final_checkpoints = {
            carrier.QUEUE_FILENAME: _checkpoint(
                directory / carrier.QUEUE_FILENAME, "published v71 queue"
            ),
            carrier.MANIFEST_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_FILENAME, "published v71 manifest"
            ),
            carrier.MANIFEST_HASH_FILENAME: _checkpoint(
                directory / carrier.MANIFEST_HASH_FILENAME,
                "published v71 manifest sidecar",
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
            raise SatelliteQueueV71Error("published v71 queue pins changed")
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
    target = _parse_timestamp(generated_at, "v71 queue generated_at")
    now = clock()
    if now >= target.timestamp():
        raise SatelliteQueueV71Error(
            "v71 queue generated_at must be future before private staging"
        )
    if target.timestamp() - now > MAX_PUBLICATION_LEAD_SECONDS:
        raise SatelliteQueueV71Error("v71 queue publication is over five minutes ahead")
    _require_accepted_inputs()
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteQueueV71Error("v71 queue output parent must be a regular directory")
    if lock.parent != parent.parent and lock.parent != ROOT:
        raise SatelliteQueueV71Error("v71 queue publication lock parent is invalid")

    with _publication_lock(lock):
        _require_absent(output, "initial")
        first = _bundle(generated_at)
        _require_absent(output, "between private builds")
        second = _bundle(generated_at)
        if _payloads(first) != _payloads(second) or first.manifest != second.manifest:
            raise SatelliteQueueV71Error("two private v71 queue builds differ")
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
            validate_satellite_queue_v71(
                first_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            validate_satellite_queue_v71(
                second_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            first_tree = _tree_digest(first_stage)
            if first_tree != _tree_digest(second_stage):
                raise SatelliteQueueV71Error("two private v71 queue trees differ")
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
                raise SatelliteQueueV71Error("v71 queue generated_at is not yet live")
            _require_absent(output, "late")
            validate_satellite_queue_v71(
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
                raise SatelliteQueueV71Error(
                    "v71 private queue stage changed while awaiting publication"
                )
            first_stage.chmod(0o755)
            try:
                promote_noreplace(first_stage, output)
            except SystemExit as error:
                raise SatelliteQueueV71Error(str(error)) from error
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
                            f"v71 queue stage cleanup failed: {cleanup_error}"
                        )
            raise
    return validate_satellite_queue_v71(
        output,
        validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
        require_final_root_ctime=True,
    )


def publish_satellite_queue_v71(
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Publish the single reserved frozen v71 queue path."""

    if generated_at != PUBLISHED_GENERATED_AT:
        raise SatelliteQueueV71Error(
            "v71 publication timestamp differs from the accepted final pin"
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
    "SatelliteQueueV71Error",
    "publish_satellite_queue_v71",
    "validate_satellite_queue_v71",
]
