"""Incident-preserving, chronology-correct current-coverage ledger v26.

V26 reconstructs the intended 53-entry successor directly from accepted v24
inputs. It does not accept v25 as a base: v25 is retained and pinned as a
rejected publication incident because its three final bundle members kept
private-stage ctimes that predated its declared publication timestamp.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
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

from . import current_coverage_v25 as _v25


ROOT = _v25.ROOT
V26_LEDGER_ID = "current-coverage-2026-07-21-v26"
V26_GENERATED_AT: str | None = "2026-07-22T02:10:00Z"
V26_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v26.json"
V26_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v26"
DEFINITION = ROOT / V26_DEFINITION_PATH
BUNDLE = ROOT / V26_BUNDLE_PATH
PUBLICATION_LOCK = ROOT / ".current-coverage-v26.lock"

LEDGER_FILENAME = _v25.LEDGER_FILENAME
MANIFEST_FILENAME = _v25.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _v25.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _v25.BUNDLE_FILES
DEFINITION_SCHEMA_VERSION_V4 = _v25.DEFINITION_SCHEMA_VERSION_V4
LEDGER_SCHEMA_VERSION_V4 = _v25.LEDGER_SCHEMA_VERSION_V4
LEDGER_FORMAT_V4 = _v25.LEDGER_FORMAT_V4
BUNDLE_FORMAT_V4 = _v25.BUNDLE_FORMAT_V4
SCOPE_POLICY = _v25.SCOPE_POLICY

REJECTED_V25_DEFINITION = {
    "bytes": 186_574,
    "path": "sources/current-coverage-2026-07-21-v25.json",
    "sha256": "40f85a544b3fd62e7fadbfd54dc52640ad04d91b04cbedcfeec09f82d5970e1c",
}
REJECTED_V25_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v25"
REJECTED_V25_MEMBERS: Mapping[str, tuple[int, str]] = {
    LEDGER_FILENAME: (
        121_407,
        "e040f735826d2f91c65fab0ea699aa40db6dedccf882c9e664d8389bf5584ae8",
    ),
    MANIFEST_FILENAME: (
        42_392,
        "2c167b54669a7166ee8dd18c4d2b3ae21d88963ac35bd455fc17bb540c69a297",
    ),
    MANIFEST_HASH_FILENAME: (
        80,
        "e898d2558d78cef151e759aea3440e219077cecbe75ced09ff5b5aa0f08e84ef",
    ),
}
REJECTED_V25_TREE_SHA256 = (
    "1de018b86667d144593baf1e52d1af207125aa0bc137395d20accbd8a5a928a7"
)
REJECTED_V25_GENERATED_AT = "2026-07-22T01:48:00Z"
REJECTED_V25_LEDGER_ID = "current-coverage-2026-07-21-v25"
REJECTED_V25_FAILED_MEMBERS = tuple(sorted(REJECTED_V25_MEMBERS))

INCIDENT_LINEAGE = {
    "accepted_as_base": False,
    "bundle": {
        "members": {
            name: {"bytes": size, "sha256": digest}
            for name, (size, digest) in sorted(REJECTED_V25_MEMBERS.items())
        },
        "path": REJECTED_V25_BUNDLE_PATH,
        "tree_sha256": REJECTED_V25_TREE_SHA256,
    },
    "chronology_contract": {
        "all_final_birth_and_mtime_lte_declared_generated_at": True,
        "all_final_ctime_gte_declared_generated_at": False,
        "failed_bundle_members": list(REJECTED_V25_FAILED_MEMBERS),
    },
    "declared_generated_at": REJECTED_V25_GENERATED_AT,
    "definition": REJECTED_V25_DEFINITION,
    "incident_kind": "final_bundle_member_ctime_predates_generated_at",
    "ledger_id": REJECTED_V25_LEDGER_ID,
    "status": "rejected_publication_incident",
}

V26_DEFINITION_SHA256: str | None = (
    "04ff833055238a20172a4fb340116198321c0b18df7ba8c8250b68f03f62780c"
)


class CurrentCoverageV26Error(RuntimeError):
    """Raised when v26 cannot prove its data or publication contracts."""


@dataclass(frozen=True)
class CurrentCoverageV26Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


def _canonical_json(value: object) -> bytes:
    return _v25._canonical_json(value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_utc(value: str, label: str) -> datetime:
    try:
        return _v25._parse_utc(value, label, seconds_only=True)
    except _v25.CurrentCoverageV25Error as error:
        raise CurrentCoverageV26Error(str(error)) from error


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV26Error(f"{label} is not a regular file")
    return path.read_bytes()


def _require_v25_incident() -> None:
    definition_path = ROOT / REJECTED_V25_DEFINITION["path"]
    definition_raw = _regular_bytes(definition_path, "rejected v25 definition")
    if (
        len(definition_raw) != REJECTED_V25_DEFINITION["bytes"]
        or _sha256(definition_raw) != REJECTED_V25_DEFINITION["sha256"]
        or stat.S_IMODE(definition_path.stat().st_mode) != 0o444
    ):
        raise CurrentCoverageV26Error("rejected v25 definition changed")
    definition = json.loads(definition_raw)
    if (
        definition.get("ledger_id") != REJECTED_V25_LEDGER_ID
        or definition.get("generated_at") != REJECTED_V25_GENERATED_AT
        or definition_raw != _canonical_json(definition)
    ):
        raise CurrentCoverageV26Error("rejected v25 identity changed")

    bundle = ROOT / REJECTED_V25_BUNDLE_PATH
    if bundle.is_symlink() or not bundle.is_dir():
        raise CurrentCoverageV26Error("rejected v25 bundle changed")
    members = list(bundle.iterdir())
    if {path.name for path in members} != set(REJECTED_V25_MEMBERS):
        raise CurrentCoverageV26Error("rejected v25 member set changed")
    if stat.S_IMODE(bundle.stat().st_mode) != 0o555:
        raise CurrentCoverageV26Error("rejected v25 bundle mode changed")
    for path in members:
        size, digest = REJECTED_V25_MEMBERS[path.name]
        raw = _regular_bytes(path, f"rejected v25 {path.name}")
        if (
            len(raw) != size
            or _sha256(raw) != digest
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CurrentCoverageV26Error(f"rejected v25 member changed: {path.name}")
    if _v25.tree_digest(bundle) != REJECTED_V25_TREE_SHA256:
        raise CurrentCoverageV26Error("rejected v25 tree changed")

    target = _parse_utc(REJECTED_V25_GENERATED_AT, "rejected v25 generated_at")
    target_seconds = target.timestamp()
    all_paths = (definition_path, bundle, *members)
    for path in all_paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target_seconds + 0.000_001:
            raise CurrentCoverageV26Error("rejected v25 chronology evidence changed")
    if definition_path.stat().st_ctime + 0.000_001 < target_seconds:
        raise CurrentCoverageV26Error("rejected v25 definition incident changed")
    if bundle.stat().st_ctime + 0.000_001 < target_seconds:
        raise CurrentCoverageV26Error("rejected v25 bundle-root incident changed")
    failed = tuple(
        sorted(
            path.name
            for path in members
            if path.stat().st_ctime + 0.000_001 < target_seconds
        )
    )
    if failed != REJECTED_V25_FAILED_MEMBERS:
        raise CurrentCoverageV26Error("rejected v25 failed-member set changed")


def _require_inputs() -> None:
    try:
        _v25._require_inputs()
    except _v25.CurrentCoverageV25Error as error:
        raise CurrentCoverageV26Error(str(error)) from error
    _require_v25_incident()


def _candidate_document(generated_at: str) -> dict[str, Any]:
    try:
        source = _v25.definition_document(_v25.V25_GENERATED_AT)
    except _v25.CurrentCoverageV25Error as error:
        raise CurrentCoverageV26Error(str(error)) from error
    return {
        "base_ledger": deepcopy(_v25.BASE_LINEAGE),
        "entries": deepcopy(source["entries"]),
        "generated_at": generated_at,
        "incident_lineage": deepcopy(INCIDENT_LINEAGE),
        "ledger_id": V26_LEDGER_ID,
        "parity_gaps": deepcopy(source["parity_gaps"]),
        "schema_version": DEFINITION_SCHEMA_VERSION_V4,
        "scope": deepcopy(SCOPE_POLICY),
    }


def definition_document(
    generated_at: str, *, require_fuses: bool = True
) -> dict[str, Any]:
    target = _parse_utc(generated_at, "v26 generated_at")
    if target <= _parse_utc(REJECTED_V25_GENERATED_AT, "rejected v25 generated_at"):
        raise CurrentCoverageV26Error("v26 must post-date the rejected v25 incident")
    _require_inputs()
    try:
        _v25._require_dependencies_before(target)
    except _v25.CurrentCoverageV25Error as error:
        raise CurrentCoverageV26Error(str(error)) from error
    preview = _v25.preview_v25_delta()
    try:
        _v25._require_component_fuses(preview)
    except _v25.CurrentCoverageV25Error as error:
        raise CurrentCoverageV26Error(str(error)) from error
    if require_fuses and (
        V26_GENERATED_AT is None or generated_at != V26_GENERATED_AT
    ):
        raise CurrentCoverageV26Error("v26 generated_at fuse changed")
    document = _candidate_document(generated_at)
    raw = _canonical_json(document)
    if any(token in raw for token in _v25.FORBIDDEN_FUTURE_TOKENS):
        raise CurrentCoverageV26Error("v26 contains future lineage")
    if require_fuses and (
        V26_DEFINITION_SHA256 is None
        or _sha256(raw) != V26_DEFINITION_SHA256
    ):
        raise CurrentCoverageV26Error("v26 definition digest fuse changed")
    return document


def _implementation_pins() -> dict[str, Any]:
    paths = {
        "cli": ROOT / "scripts/build_current_coverage_ledger_v26.py",
        "module": Path(__file__).resolve(),
        "root_shim": ROOT / "current_coverage_v26.py",
        "v21_schema_helper": Path(_v25._v21.__file__).resolve(),
        "v22_schema_helper": Path(_v25._v22.__file__).resolve(),
        "v24_accepted_predecessor": Path(_v25._v24.__file__).resolve(),
        "v25_rejected_publisher": Path(_v25.__file__).resolve(),
    }
    result = {}
    for label, path in sorted(paths.items()):
        raw = path.read_bytes()
        result[label] = {
            "bytes": len(raw),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    return result


def _validate_definition(
    path: Path, *, require_live: bool
) -> tuple[dict[str, Any], bytes, datetime]:
    raw = _regular_bytes(path, "v26 definition")
    document = json.loads(raw)
    if raw != _canonical_json(document):
        raise CurrentCoverageV26Error("v26 definition is not canonical")
    if stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise CurrentCoverageV26Error("v26 definition is not frozen 0444")
    generated_at = document.get("generated_at")
    generated = _parse_utc(generated_at, "v26 generated_at")
    if require_live and generated > datetime.now(UTC):
        raise CurrentCoverageV26Error("v26 generated_at exceeds wall clock")
    if document != definition_document(generated_at):
        raise CurrentCoverageV26Error("v26 definition changed")
    if V26_DEFINITION_SHA256 is None or _sha256(raw) != V26_DEFINITION_SHA256:
        raise CurrentCoverageV26Error("v26 definition checkpoint changed")
    return document, raw, generated


def build_current_coverage_ledger_v26(
    definition_path: str | Path,
) -> CurrentCoverageV26Bundle:
    definition, definition_raw, _generated = _validate_definition(
        Path(definition_path), require_live=False
    )
    _base_definition, base_ledger = _v25._load_base()
    artifacts = []
    previous_id: str | None = None
    for entry in definition["entries"]:
        try:
            artifact = _v25._v21._entry_v4(ROOT, entry, previous_id)
        except _v25._v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV26Error(str(error)) from error
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _v25._v21._legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _v25._v21._legacy.CurrentCoverageError as error:
        raise CurrentCoverageV26Error(str(error)) from error
    inventory = _v25._v21._inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(base_ledger["artifact_inventory_counts"])
    addition = next(
        entry
        for entry in definition["entries"]
        if entry["artifact_id"] == _v25.V83_REVIEW_ARTIFACT_ID
    )
    expected_inventory["artifacts"] += 1
    expected_inventory["by_access_tier"][addition["access_tier"]] += 1
    expected_inventory["by_evidence_scope"][addition["evidence_scope"]] += 1
    expected_inventory["by_publication_mode"][addition["publication_mode"]] += 1
    expected_inventory["by_redistribution_status"][
        addition["redistribution_status"]
    ] += 1
    for unit in addition["record_units"]:
        expected_inventory["by_record_unit"][unit] += 1
    expected_inventory["public_open_review_only_artifacts"] += 1
    if inventory != expected_inventory:
        raise CurrentCoverageV26Error("v26 inventory arithmetic changed")

    ledger = {
        "artifact_inventory_counts": inventory,
        "artifacts": artifacts,
        "base_ledger": deepcopy(_v25.BASE_LINEAGE),
        "format": LEDGER_FORMAT_V4,
        "generated_at": definition["generated_at"],
        "incident_lineage": deepcopy(INCIDENT_LINEAGE),
        "ledger_id": V26_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": deepcopy(SCOPE_POLICY),
    }
    ledger_bytes = _canonical_json(ledger)
    preview = _v25.preview_v25_delta()
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "base_bundle": {
            "manifest_sidecar": deepcopy(_v25.BASE_SIDECAR),
            "tree_sha256": _v25.BASE_TREE_SHA256,
        },
        "base_ledger": deepcopy(_v25.BASE_LINEAGE),
        "definition": {
            "bytes": len(definition_raw),
            "path": V26_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT_V4,
        "generated_at": definition["generated_at"],
        "implementation": _implementation_pins(),
        "incident_lineage": deepcopy(INCIDENT_LINEAGE),
        "input_checkpoints": {
            artifact["artifact_id"]: {
                checkpoint["checkpoint_id"]: {
                    "bytes": checkpoint["bytes"],
                    "path": checkpoint["path"],
                    "sha256": checkpoint["sha256"],
                }
                for checkpoint in artifact["checkpoints"]
            }
            for artifact in artifacts
        },
        "input_member_checkpoints": {
            _v25.V83_REVIEW_ARTIFACT_ID: {
                name: {"bytes": size, "sha256": digest}
                for name, (size, digest) in sorted(
                    _v25.V83_REVIEW_MEMBER_PINS.items()
                )
            }
        },
        "input_modes": {
            "bundle_directories": "0555",
            "bundle_files": "0444",
            "standalone_definitions": "0444",
        },
        "input_timestamps": {
            source: {
                "bundle": bundle,
                "field": ".".join(keys),
                "source_is_bundle_member": source_is_member,
                "value": value,
            }
            for source, keys, value, bundle, source_is_member in _v25.TIMESTAMP_PINS
        },
        "input_trees": {
            **dict(sorted(_v25.PINNED_TREES.items())),
            REJECTED_V25_BUNDLE_PATH: REJECTED_V25_TREE_SHA256,
        },
        "ledger_id": V26_LEDGER_ID,
        "publication_chronology": {
            "all_final_birth_and_mtime_lte_generated_at": True,
            "all_final_ctime_gte_generated_at": True,
            "final_paths": [
                V26_DEFINITION_PATH,
                V26_BUNDLE_PATH,
                *[
                    f"{V26_BUNDLE_PATH}/{name}"
                    for name in sorted(BUNDLE_FILES)
                ],
            ],
        },
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": deepcopy(SCOPE_POLICY),
        "successor_delta": preview,
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    return CurrentCoverageV26Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=sidecar,
        ledger=ledger,
        manifest=manifest,
    )


def _write_bundle(path: Path, bundle: CurrentCoverageV26Bundle) -> None:
    files = {
        LEDGER_FILENAME: bundle.ledger_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }
    for filename, raw in sorted(files.items()):
        with path.joinpath(filename).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _publication_paths(definition: Path, bundle: Path) -> tuple[Path, ...]:
    if definition.is_symlink() or not definition.is_file():
        raise CurrentCoverageV26Error("v26 definition path is invalid")
    if bundle.is_symlink() or not bundle.is_dir():
        raise CurrentCoverageV26Error("v26 bundle path is invalid")
    members = tuple(sorted(bundle.iterdir(), key=lambda path: path.name))
    if {path.name for path in members} != BUNDLE_FILES or any(
        path.is_symlink() or not path.is_file() for path in members
    ):
        raise CurrentCoverageV26Error("v26 bundle member set changed")
    return (definition, bundle, *members)


def _assert_chronology(
    paths: Sequence[Path], target: datetime, *, require_final_ctime: bool
) -> None:
    target_seconds = target.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise CurrentCoverageV26Error("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target_seconds + 0.000_001:
            raise CurrentCoverageV26Error(
                f"v26 path post-dates generated_at: {path.name}"
            )
        if (
            require_final_ctime
            and metadata.st_ctime + 0.000_001 < target_seconds
        ):
            raise CurrentCoverageV26Error(
                f"v26 final ctime predates generated_at: {path.name}"
            )


def _refresh_stage_ctimes(
    definition: Path, bundle: Path, target: datetime
) -> None:
    if datetime.now(UTC) < target:
        raise CurrentCoverageV26Error("v26 chronology refresh preceded generated_at")
    members = tuple(sorted(bundle.iterdir(), key=lambda path: path.name))
    for path in (definition, *members):
        path.chmod(0o644)
        path.chmod(0o444)
    bundle.chmod(0o755)
    bundle.chmod(0o555)
    paths = _publication_paths(definition, bundle)
    _assert_chronology(paths, target, require_final_ctime=True)


def _validate_bundle(
    bundle: Path, *, definition_path: Path, require_live: bool, rebuild: bool
) -> dict[str, Any]:
    paths = _publication_paths(definition_path, bundle)
    if stat.S_IMODE(bundle.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in paths
        if path != bundle
    ):
        raise CurrentCoverageV26Error("v26 bundle is not frozen 0555/0444")
    definition, _raw, generated = _validate_definition(
        definition_path, require_live=require_live
    )
    expected = build_current_coverage_ledger_v26(definition_path)
    expected_files = {
        LEDGER_FILENAME: expected.ledger_bytes,
        MANIFEST_FILENAME: expected.manifest_bytes,
        MANIFEST_HASH_FILENAME: expected.manifest_hash_bytes,
    }
    for filename, raw in expected_files.items():
        if bundle.joinpath(filename).read_bytes() != raw:
            raise CurrentCoverageV26Error(f"v26 artifact changed: {filename}")
    if definition.get("incident_lineage") != INCIDENT_LINEAGE:
        raise CurrentCoverageV26Error("v26 incident lineage changed")
    if expected.ledger.get("incident_lineage") != INCIDENT_LINEAGE:
        raise CurrentCoverageV26Error("v26 ledger incident lineage changed")
    ids = {artifact["artifact_id"] for artifact in expected.ledger["artifacts"]}
    if (
        len(ids) != 53
        or ids & _v25.REMOVED_ARTIFACT_IDS
        or not _v25.NEW_ARTIFACT_IDS <= ids
        or expected.ledger["scope"]["unique_physical_site_count"] is not None
    ):
        raise CurrentCoverageV26Error("v26 semantic inventory changed")
    if expected.manifest["implementation"] != _implementation_pins():
        raise CurrentCoverageV26Error("v26 implementation pins changed")
    if require_live:
        _assert_chronology(paths, generated, require_final_ctime=True)
    if rebuild and build_current_coverage_ledger_v26(definition_path) != expected:
        raise CurrentCoverageV26Error("v26 double reconstruction changed")
    return dict(expected.manifest)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 1_800:
        raise CurrentCoverageV26Error("v26 publication is over 30 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _now() -> datetime:
    return datetime.now(UTC)


def _discard_file(path: Path) -> None:
    if path.exists() and not path.is_symlink() and path.is_file():
        path.chmod(0o600)
        path.unlink()


def _discard_bundle(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for item in path.iterdir():
        if item.is_symlink() or not item.is_file() or item.name not in BUNDLE_FILES:
            raise CurrentCoverageV26Error("refusing contaminated v26 cleanup")
        item.chmod(0o600)
    shutil.rmtree(path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise CurrentCoverageV26Error("active v26 publication lock exists") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        PUBLICATION_LOCK.unlink(missing_ok=True)


def _require_unpublished() -> None:
    for path in (DEFINITION, BUNDLE):
        if path.exists() or path.is_symlink():
            raise CurrentCoverageV26Error(f"refusing replacement of v26: {path}")


def _rollback(definition_published: bool, bundle_published: bool) -> None:
    if definition_published and DEFINITION.exists():
        rollback = DEFINITION.parent / f".{DEFINITION.name}.rollback-{os.getpid()}"
        _v25.promote_noreplace(DEFINITION, rollback)
        _discard_file(rollback)
    if bundle_published and BUNDLE.exists():
        rollback = BUNDLE.parent / f".{BUNDLE.name}.rollback-{os.getpid()}"
        BUNDLE.chmod(0o755)
        _v25.promote_noreplace(BUNDLE, rollback)
        _discard_bundle(rollback)


def publish_current_coverage_ledger_v26(generated_at: str) -> dict[str, Any]:
    target = _parse_utc(generated_at, "v26 generated_at")
    if target <= _now():
        raise CurrentCoverageV26Error("v26 generated_at must be in the future")
    if V26_GENERATED_AT is None or generated_at != V26_GENERATED_AT:
        raise CurrentCoverageV26Error("v26 generated_at fuse changed")
    _require_inputs()
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CurrentCoverageV26Error(f"invalid v26 output parent: {parent}")
    with _publication_lock():
        _require_unpublished()
        descriptor, definition_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.stage-", dir=DEFINITION.parent
        )
        definition_stage = Path(definition_name)
        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.stage-", dir=BUNDLE.parent)
        )
        definition_published = False
        bundle_published = False
        try:
            raw = _canonical_json(definition_document(generated_at))
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            first = build_current_coverage_ledger_v26(definition_stage)
            second = build_current_coverage_ledger_v26(definition_stage)
            if first != second:
                raise CurrentCoverageV26Error("two offline v26 builds differ")
            _write_bundle(bundle_stage, first)
            for item in bundle_stage.iterdir():
                item.chmod(0o444)
            bundle_stage.chmod(0o555)
            _validate_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_live=False,
                rebuild=True,
            )
            paths = _publication_paths(definition_stage, bundle_stage)
            _assert_chronology(paths, target, require_final_ctime=False)
            _wait_until(target)
            _require_inputs()
            _require_unpublished()
            _refresh_stage_ctimes(definition_stage, bundle_stage, target)
            _validate_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_live=False,
                rebuild=True,
            )
            _v25.promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            _v25.promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            return validate_current_coverage_ledger_v26()
        except BaseException as error:
            try:
                _rollback(definition_published, bundle_published)
            except BaseException as rollback_error:
                error.add_note(f"v26 rollback failed: {rollback_error}")
            raise
        finally:
            if not bundle_published:
                _discard_bundle(bundle_stage)
            if not definition_published:
                _discard_file(definition_stage)


def validate_current_coverage_ledger_v26() -> dict[str, Any]:
    _require_inputs()
    return _validate_bundle(
        BUNDLE, definition_path=DEFINITION, require_live=True, rebuild=True
    )


__all__ = [
    "BUNDLE",
    "CurrentCoverageV26Error",
    "DEFINITION",
    "INCIDENT_LINEAGE",
    "V26_LEDGER_ID",
    "build_current_coverage_ledger_v26",
    "definition_document",
    "publish_current_coverage_ledger_v26",
    "validate_current_coverage_ledger_v26",
]
