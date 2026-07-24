"""Publish the chronology-correct v2 Google Haskell/Maize/Pyramid artifact.

The three curated source files published alongside v1 are valid, immutable
inputs and are reused byte-for-byte. The v1 artifact directory is retained as
a rejected incident because all seven of its child-file ctimes predated its
declared recorded_at. V2 publishes no source file and performs no integration.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import google_official_haskell_maize_pyramid_current_build_gap_20260722 as v1


ROOT = v1.ROOT
SOURCES_ROOT = v1.SOURCES_ROOT
ARTIFACT_ROOT = v1.ARTIFACT_ROOT
ARTIFACT_ID = (
    "google-official-haskell-maize-pyramid-current-build-gap-2026-07-22-v2"
)
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
RECORDED_AT = "2026-07-22T02:35:00Z"
PUBLICATION_LOCK = ROOT / ".google-haskell-maize-pyramid-current-build-v2.lock"

SOURCE_FILENAMES = v1.SOURCE_FILENAMES
CONTENT_FILES = v1.CONTENT_FILES
CLOSED_FILES = v1.CLOSED_FILES

SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    "curated-official-2026-07-22-google-haskell-quantum-linked-current-build.json": (
        8_973,
        "72fe2080d815d6c42f518804119d622b6673aabdd874cbb077978bc5f1fa3a22",
    ),
    "curated-official-2026-07-22-google-michigan-city-project-maize-site-works.json": (
        8_734,
        "8a4badebd8271e0360e5e1977f4abd88e1cc4c4bda4ebe9497b5944cad80c24f",
    ),
    "curated-official-2026-07-22-google-west-memphis-project-pyramid-current-build.json": (
        6_985,
        "55db0349fd90cc348f512f1409e92671892f06e288cd82a8dce2e4cf5530f692",
    ),
}
SOURCE_CTIME_NS: Mapping[str, int] = {
    "curated-official-2026-07-22-google-haskell-quantum-linked-current-build.json": 1_784_685_692_010_133_613,
    "curated-official-2026-07-22-google-michigan-city-project-maize-site-works.json": 1_784_685_692_010_325_282,
    "curated-official-2026-07-22-google-west-memphis-project-pyramid-current-build.json": 1_784_685_692_010_455_283,
}

REJECTED_V1_ID = v1.ARTIFACT_ID
REJECTED_V1_PATH = f"source_artifacts/{REJECTED_V1_ID}"
REJECTED_V1_RECORDED_AT = "2026-07-22T02:01:32Z"
REJECTED_V1_PHYSICAL_TREE_SHA256 = (
    "3613881b11187faae76682dc09e1fc2d1185c0c60a2d053ff9328fc4d0220d87"
)
REJECTED_V1_LOGICAL_TREE_SHA256 = (
    "db1e1411deb788191fb658f9fa135ef79aaf8c6d6798db517689838f60180588"
)
REJECTED_V1_ROOT_CTIME_NS = 1_784_685_692_010_618_369
REJECTED_V1_MEMBER_PINS: Mapping[str, tuple[int, str, int]] = {
    "README.md": (
        1_931,
        "9d1ecbbd0c9303a9fb3089c1d17c9a6e46a8bd6c4fec87f29dafb9f94fe91258",
        1_784_685_647_966_924_238,
    ),
    "candidate-assessment.json": (
        6_264,
        "beace8901d54f7d0fa5710874bb35a3f1f35875369fdd27b4a5f5837025314d3",
        1_784_685_647_967_037_864,
    ),
    "manifest.json": (
        1_837,
        "b05989194bc280d050eb5011ae9951b4dfad94427fd5771924db7b118c554820",
        1_784_685_647_967_591_662,
    ),
    "manifest.sha256": (
        80,
        "744d85b5aa526428d78907717db230989fecb15457e7b41ca2c29dec16157aca",
        1_784_685_647_967_709_497,
    ),
    "retrieval-inventory.json": (
        17_651,
        "aa8d23101829feb666587f9707a99b5d53099e969ca68cbd0a4b7fd8e171f54e",
        1_784_685_647_967_137_574,
    ),
    "rights-and-disposition.json": (
        1_156,
        "94cf2c9345d51edbee2a0719b446ffaf1cf73f7036778f2c9924d92179a89994",
        1_784_685_647_967_232_825,
    ),
    "source-snapshot.json": (
        6_028,
        "c39e37c396303474f41debe4141322a0fbf1201b597548cd148d9005ed049a44",
        1_784_685_647_967_333_034,
    ),
}

INCIDENT_LINEAGE = {
    "accepted_as_base": False,
    "artifact_id": REJECTED_V1_ID,
    "artifact_path": REJECTED_V1_PATH,
    "declared_recorded_at": REJECTED_V1_RECORDED_AT,
    "failed_members": {
        name: {
            "bytes": size,
            "ctime_ns": ctime_ns,
            "path": f"{REJECTED_V1_PATH}/{name}",
            "sha256": digest,
        }
        for name, (size, digest, ctime_ns) in sorted(
            REJECTED_V1_MEMBER_PINS.items()
        )
    },
    "logical_tree_sha256": REJECTED_V1_LOGICAL_TREE_SHA256,
    "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
    "reason": (
        "All seven final artifact child files retained private-stage ctimes "
        "that predated the declared recorded_at."
    ),
    "root_ctime_ns": REJECTED_V1_ROOT_CTIME_NS,
    "status": "rejected_publication_incident",
}


class GoogleCurrentBuildGapV2Error(RuntimeError):
    """Raised when the v2 input, semantic, or publication contract differs."""


@dataclass(frozen=True)
class ArtifactBundle:
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]


def _canonical(value: object) -> bytes:
    return v1._canonical(value)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str) -> datetime:
    try:
        parsed = v1._instant(value)
    except Exception as error:
        raise GoogleCurrentBuildGapV2Error(str(error)) from error
    if value != parsed.isoformat(timespec="seconds").replace("+00:00", "Z"):
        raise GoogleCurrentBuildGapV2Error("timestamp is not canonical second UTC")
    return parsed


def _now() -> datetime:
    return datetime.now(UTC)


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GoogleCurrentBuildGapV2Error(f"{label} is not a regular file")
    return path.read_bytes()


def _require_v1_incident() -> None:
    path = ROOT / REJECTED_V1_PATH
    if path.is_symlink() or not path.is_dir():
        raise GoogleCurrentBuildGapV2Error("rejected v1 artifact is absent")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise GoogleCurrentBuildGapV2Error("rejected v1 root mode changed")
    root_metadata = path.stat(follow_symlinks=False)
    if root_metadata.st_ctime_ns != REJECTED_V1_ROOT_CTIME_NS:
        raise GoogleCurrentBuildGapV2Error("rejected v1 root ctime changed")
    entries = list(path.iterdir())
    if {entry.name for entry in entries} != set(REJECTED_V1_MEMBER_PINS):
        raise GoogleCurrentBuildGapV2Error("rejected v1 member set changed")
    target = _instant(REJECTED_V1_RECORDED_AT).timestamp()
    for entry in entries:
        size, digest, ctime_ns = REJECTED_V1_MEMBER_PINS[entry.name]
        raw = _regular_bytes(entry, f"rejected v1 {entry.name}")
        metadata = entry.stat(follow_symlinks=False)
        if (
            len(raw) != size
            or _sha256_bytes(raw) != digest
            or metadata.st_ctime_ns != ctime_ns
            or stat.S_IMODE(metadata.st_mode) != 0o444
        ):
            raise GoogleCurrentBuildGapV2Error(
                f"rejected v1 member changed: {entry.name}"
            )
        if metadata.st_ctime + 0.000_001 >= target:
            raise GoogleCurrentBuildGapV2Error(
                f"rejected v1 chronology evidence changed: {entry.name}"
            )
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target + 0.000_001:
            raise GoogleCurrentBuildGapV2Error(
                f"rejected v1 staged time evidence changed: {entry.name}"
            )
    if root_metadata.st_ctime + 0.000_001 < target:
        raise GoogleCurrentBuildGapV2Error("rejected v1 root chronology changed")
    if v1.tree_digest(path) != REJECTED_V1_PHYSICAL_TREE_SHA256:
        raise GoogleCurrentBuildGapV2Error("rejected v1 physical tree changed")
    manifest = json.loads((path / "manifest.json").read_bytes())
    if (
        manifest.get("artifact_id") != REJECTED_V1_ID
        or manifest.get("recorded_at") != REJECTED_V1_RECORDED_AT
        or manifest.get("tree_sha256") != REJECTED_V1_LOGICAL_TREE_SHA256
    ):
        raise GoogleCurrentBuildGapV2Error("rejected v1 manifest changed")


def _require_sources() -> dict[str, dict[str, Any]]:
    if set(SOURCE_PINS) != set(SOURCE_FILENAMES):
        raise GoogleCurrentBuildGapV2Error("v2 source pin inventory changed")
    documents: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILENAMES:
        path = SOURCES_ROOT / name
        raw = _regular_bytes(path, f"accepted source {name}")
        size, digest = SOURCE_PINS[name]
        if (
            len(raw) != size
            or _sha256_bytes(raw) != digest
            or path.stat(follow_symlinks=False).st_ctime_ns != SOURCE_CTIME_NS[name]
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise GoogleCurrentBuildGapV2Error(f"accepted source changed: {name}")
        document = json.loads(raw)
        if raw != _canonical(document):
            raise GoogleCurrentBuildGapV2Error(f"accepted source is not canonical: {name}")
        documents[name] = document
    expected = v1.expected_source_documents()
    if documents != expected:
        raise GoogleCurrentBuildGapV2Error("accepted source semantics changed")
    return documents


def _source_reuse() -> dict[str, Any]:
    return {
        "exact_reused_source_count": 3,
        "new_source_files_created": False,
        "records": [
            {
                "bytes": SOURCE_PINS[name][0],
                "ctime_ns": SOURCE_CTIME_NS[name],
                "path": f"sources/{name}",
                "sha256": SOURCE_PINS[name][1],
            }
            for name in SOURCE_FILENAMES
        ],
    }


def _implementation_pins() -> dict[str, Any]:
    paths = {
        "cli": ROOT / "scripts/build_google_official_haskell_maize_pyramid_current_build_gap_v2_20260722.py",
        "module": Path(__file__).resolve(),
        "root_shim": ROOT / "google_official_haskell_maize_pyramid_current_build_gap_v2_20260722.py",
        "v1_rejected_publisher": Path(v1.__file__).resolve(),
    }
    return {
        label: {
            "bytes": path.stat().st_size,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(path),
        }
        for label, path in sorted(paths.items())
    }


def _content_payloads(recorded_at: str) -> dict[str, bytes]:
    if recorded_at != RECORDED_AT:
        raise GoogleCurrentBuildGapV2Error("v2 recorded_at fuse changed")
    documents = _require_sources()
    base = v1._artifact_documents(recorded_at, documents)
    result: dict[str, bytes] = {}
    for name in CONTENT_FILES:
        if name == "README.md":
            text = base[name].decode("utf-8").rstrip()
            text += (
                "\n\n## Publication incident lineage\n\n"
                f"The `{REJECTED_V1_ID}` artifact is retained but rejected: all "
                "seven child files had final ctimes before its declared recorded_at. "
                "This v2 artifact reuses the three already-frozen curated source "
                "files byte-for-byte, creates no source definition, and performs no "
                "open-seed or release integration.\n"
            )
            result[name] = text.encode("utf-8")
            continue
        document = json.loads(base[name])
        document["artifact_id"] = ARTIFACT_ID
        document["incident_lineage"] = INCIDENT_LINEAGE
        if name == "candidate-assessment.json":
            document["format"] = "datacenter-atlas-official-current-build-assessment-v2"
        result[name] = _canonical(document)
    return result


def build_bundle(recorded_at: str = RECORDED_AT) -> ArtifactBundle:
    _require_v1_incident()
    payloads = _content_payloads(recorded_at)
    rows = [
        {
            "bytes": len(payloads[name]),
            "path": name,
            "sha256": _sha256_bytes(payloads[name]),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "candidate_assessments": 6,
        "closed_file_set": sorted(CLOSED_FILES),
        "controlled_capture_count": 14,
        "curated_source_records": 3,
        "failed_http_body_captures": 3,
        "files": rows,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "implementation": _implementation_pins(),
        "incident_lineage": INCIDENT_LINEAGE,
        "open_seed_successor_created": False,
        "publication_chronology": {
            "all_final_birth_and_mtime_lte_recorded_at": True,
            "all_final_ctime_gte_recorded_at": True,
            "final_paths": [
                f"source_artifacts/{ARTIFACT_ID}",
                *[
                    f"source_artifacts/{ARTIFACT_ID}/{name}"
                    for name in sorted(CLOSED_FILES)
                ],
            ],
        },
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_source_publication": True,
        "raw_capture_redistributed": False,
        "recorded_at": recorded_at,
        "regional_completeness_claimed": False,
        "release_integration": "none",
        "review_only_candidates": 3,
        "seed_eligible_candidates": 3,
        "seed_eligible_source_records": 3,
        "source_reuse": _source_reuse(),
        "successful_http_200_body_captures": 11,
        "tree_sha256": v1._file_tree(rows),
    }
    manifest_raw = _canonical(manifest)
    files = {
        **payloads,
        "manifest.json": manifest_raw,
        "manifest.sha256": (
            f"{_sha256_bytes(manifest_raw)}  manifest.json\n".encode("ascii")
        ),
    }
    return ArtifactBundle(files=files, manifest=manifest)


def _artifact_paths(path: Path) -> tuple[Path, ...]:
    if path.is_symlink() or not path.is_dir():
        raise GoogleCurrentBuildGapV2Error("v2 artifact is not a regular directory")
    members = tuple(sorted(path.iterdir(), key=lambda item: item.name))
    if {member.name for member in members} != CLOSED_FILES or any(
        member.is_symlink() or not member.is_file() for member in members
    ):
        raise GoogleCurrentBuildGapV2Error("v2 closed file set changed")
    return (path, *members)


def _assert_chronology(
    paths: Sequence[Path], target: datetime, *, require_final_ctime: bool
) -> None:
    target_epoch = target.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise GoogleCurrentBuildGapV2Error("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target_epoch + 0.000_001:
            raise GoogleCurrentBuildGapV2Error(
                f"v2 path post-dates recorded_at: {path.name}"
            )
        if require_final_ctime and metadata.st_ctime + 0.000_001 < target_epoch:
            raise GoogleCurrentBuildGapV2Error(
                f"v2 final ctime predates recorded_at: {path.name}"
            )


def _refresh_stage_ctimes(stage: Path, target: datetime) -> None:
    if _now() < target:
        raise GoogleCurrentBuildGapV2Error("v2 ctime refresh preceded recorded_at")
    stage.chmod(0o500)
    for member in sorted(stage.iterdir(), key=lambda item: item.name):
        member.chmod(0o400)
        member.chmod(0o444)
        v1._fsync_regular(member)
    stage.chmod(0o555)
    v1._fsync_directory(stage)
    _assert_chronology(_artifact_paths(stage), target, require_final_ctime=True)


def _semantic_contract(bundle: ArtifactBundle) -> None:
    snapshot = json.loads(bundle.files["source-snapshot.json"])
    totals = snapshot["totals"]
    expected = {
        "source_records": 3,
        "distinct_entities_in_source_records": 6,
        "unique_evidence_records": 8,
        "lifecycle_observations": 3,
        "capacity_estimates": 0,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "voltage_metadata_records": 0,
    }
    if any(totals.get(key) != value for key, value in expected.items()):
        raise GoogleCurrentBuildGapV2Error("v2 semantic totals changed")
    documents = _require_sources()
    lifecycle = {
        (
            document["project"]["stable_key"],
            document["lifecycle"][0]["value"],
            document["lifecycle"][0]["as_of_date"],
        )
        for document in documents.values()
    }
    if lifecycle != {
        (
            "curated:google-haskell-county-quantum-linked-data-center-campus:current-development",
            "under_construction",
            "2025-11-30",
        ),
        (
            "curated:google-michigan-city-project-maize-data-center:2025-site-works",
            "site_preparation",
            "2025-09-24",
        ),
        (
            "curated:google-west-memphis-project-pyramid-data-center-campus:current-development",
            "under_construction",
            "2025-10-02",
        ),
    }:
        raise GoogleCurrentBuildGapV2Error("v2 lifecycle contract changed")
    assessment = json.loads(bundle.files["candidate-assessment.json"])
    review_ids = [row["candidate_id"] for row in assessment["candidates"][3:]]
    if review_ids != [
        "google-new-florence-project-spade",
        "google-pine-island-project-skyway",
        "google-hermantown-potential-campus",
    ]:
        raise GoogleCurrentBuildGapV2Error("v2 review-only contract changed")
    serialized = b"\n".join(
        _canonical(document) for document in documents.values()
    ).decode("utf-8").casefold()
    if any(token in serialized for token in ("500/230", "voltage_kv", '"latitude"', '"longitude"')):
        raise GoogleCurrentBuildGapV2Error("v2 promoted omitted USACE facts")


def _source_paths() -> dict[str, Path]:
    return {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _require_v1_incident()
    _require_sources()
    paths = _artifact_paths(path)
    if stat.S_IMODE(path.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(member.stat().st_mode) != 0o444 for member in paths[1:]
    ):
        raise GoogleCurrentBuildGapV2Error("v2 artifact is not frozen 0555/0444")
    first = build_bundle(RECORDED_AT)
    second = build_bundle(RECORDED_AT)
    if first != second:
        raise GoogleCurrentBuildGapV2Error("v2 deterministic double-build changed")
    if {name: (path / name).read_bytes() for name in CLOSED_FILES} != first.files:
        raise GoogleCurrentBuildGapV2Error("v2 artifact bytes changed")
    _semantic_contract(first)
    source_rows = v1._validate_sources(_source_paths())
    if len(source_rows) != 3 or sum(row["evidence_records"] for row in source_rows) != 8:
        raise GoogleCurrentBuildGapV2Error("v2 reused-source validation changed")
    replay = [v1._offline_import(_source_paths(), RECORDED_AT) for _ in range(2)]
    if replay[0] != replay[1]:
        raise GoogleCurrentBuildGapV2Error("v2 offline replay changed")
    target = _instant(RECORDED_AT)
    now = wall_clock or _now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise GoogleCurrentBuildGapV2Error("wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise GoogleCurrentBuildGapV2Error("v2 recorded_at is not live")
        _assert_chronology(paths, target, require_final_ctime=True)
    return dict(first.manifest)


def _write_stage(stage: Path, bundle: ArtifactBundle) -> None:
    for name in sorted(CLOSED_FILES):
        target = stage / name
        with target.open("xb") as stream:
            stream.write(bundle.files[name])
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(0o444)
    stage.chmod(0o555)
    v1._fsync_directory(stage)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 1_800:
        raise GoogleCurrentBuildGapV2Error("v2 publication is over 30 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    entries = list(stage.iterdir())
    if {entry.name for entry in entries} != CLOSED_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise GoogleCurrentBuildGapV2Error("refusing contaminated v2 cleanup")
    for entry in entries:
        entry.chmod(0o600)
    shutil.rmtree(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise GoogleCurrentBuildGapV2Error("active v2 publication lock exists") from error
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise GoogleCurrentBuildGapV2Error(
                    "refusing substituted v2 lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def _require_absent() -> None:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise GoogleCurrentBuildGapV2Error("refusing replacement of v2 artifact")


def publish_artifact(recorded_at: str = RECORDED_AT) -> dict[str, Any]:
    target = _instant(recorded_at)
    if recorded_at != RECORDED_AT:
        raise GoogleCurrentBuildGapV2Error("v2 recorded_at fuse changed")
    if _now() >= target:
        raise GoogleCurrentBuildGapV2Error("v2 recorded_at must be future")
    _require_v1_incident()
    _require_sources()
    if ARTIFACT_ROOT.is_symlink() or not ARTIFACT_ROOT.is_dir():
        raise GoogleCurrentBuildGapV2Error("v2 artifact parent is invalid")
    with _publication_lock():
        _require_absent()
        stage = Path(
            tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
        )
        published = False
        try:
            first = build_bundle(recorded_at)
            second = build_bundle(recorded_at)
            if first != second:
                raise GoogleCurrentBuildGapV2Error(
                    "v2 deterministic prepublication build changed"
                )
            _write_stage(stage, first)
            validate_artifact(
                stage,
                require_live=False,
                wall_clock=_now(),
            )
            _assert_chronology(
                _artifact_paths(stage), target, require_final_ctime=False
            )
            if _now() >= target:
                raise GoogleCurrentBuildGapV2Error(
                    "v2 private staging did not finish before recorded_at"
                )
            _wait_until(target)
            _require_v1_incident()
            _require_sources()
            _require_absent()
            _refresh_stage_ctimes(stage, target)
            validate_artifact(
                stage,
                require_live=False,
                wall_clock=_now(),
            )
            v1._promote_noreplace(stage, ARTIFACT)
            published = True
            return validate_artifact()
        except BaseException as error:
            if published and ARTIFACT.exists():
                try:
                    v1._promote_noreplace(ARTIFACT, stage)
                    published = False
                except BaseException as rollback_error:
                    error.add_note(f"v2 rollback failed: {rollback_error}")
            raise
        finally:
            if not published:
                _discard_stage(stage)


__all__ = [
    "ARTIFACT",
    "ARTIFACT_ID",
    "INCIDENT_LINEAGE",
    "RECORDED_AT",
    "SOURCE_PINS",
    "build_bundle",
    "publish_artifact",
    "validate_artifact",
]
