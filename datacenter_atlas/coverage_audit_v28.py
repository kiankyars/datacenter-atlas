"""Hardened v28 coverage-audit successor over accepted v27.

The wire schema remains coverage-audit v2. V28 replaces only the accepted
open-seed-v67/federation-v28 inputs with open-seed-v71/federation-v31. It does
not merge children, infer current construction, promote review rows, or claim
unique physical-site counts.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import coverage_audit as base
from . import coverage_audit_v3 as legacy
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v27.json"
BASE_BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v27"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v28.json"
BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v28"
V71_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v31.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v31"
PUBLICATION_LOCK = ROOT / ".coverage-audit-v28.lock"

AUDIT_ID = "public-open-coverage-v28"
OLD_RELEASE_ID = "epoch-official-open-seed-v67"
NEW_RELEASE_ID = "epoch-official-open-seed-v71"

BASE_DEFINITION_SHA256 = (
    "0224660dd28426c51eb5a76d1264e46b7da629f42d9de2648296b0b0f7b6e9ec"
)
BASE_TREE_SHA256 = (
    "a2f945f421e22776633c0dc5960301d429ef629882e7361204cd35912ab764e1"
)
V71_DEFINITION_SHA256 = (
    "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
)
V71_MANIFEST_SHA256 = (
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
)
V71_TREE_SHA256 = (
    "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"
)
FEDERATION_DEFINITION_SHA256 = (
    "83a878ee72563e6572a53cf09236c0af469e629bc04482401d6891b54d108ee1"
)
FEDERATION_INDEX_SHA256 = (
    "02907b58973b74461a6117bc4373ea6ac06e5026b4fdf632e43fdaa05043e576"
)
FEDERATION_MANIFEST_SHA256 = (
    "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101"
)
FEDERATION_TREE_SHA256 = (
    "978b1a574071f0128538aafee4503436fd0ae95284a60e236b0ee9065834f55c"
)

REJECTED_LINEAGE_TOKENS = (
    b"open-seed-2026-07-21-v68",
    b"epoch-official-open-seed-v68",
    b"2026-07-21-public-open-v29",
    b"2026-07-21-public-open-v30",
)


class CoverageAuditV4Error(RuntimeError):
    """Raised when the bounded v28 transition cannot be proved."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return base._canonical_json(value)


def _parse_utc(value: str, *, label: str) -> datetime:
    canonical, _ = base._canonical_timestamp(value, label)
    parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _require_checkpoint(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise CoverageAuditV4Error(f"{label} is not a regular file: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise CoverageAuditV4Error(
            f"{label} checkpoint changed: expected {expected}, got {actual}"
        )


def _require_inputs() -> None:
    _require_checkpoint(BASE_DEFINITION, BASE_DEFINITION_SHA256, "v27 definition")
    _require_checkpoint(V71_DEFINITION, V71_DEFINITION_SHA256, "v71 definition")
    _require_checkpoint(
        V71_RELEASE / "manifest.json", V71_MANIFEST_SHA256, "v71 manifest"
    )
    _require_checkpoint(
        FEDERATION_DEFINITION,
        FEDERATION_DEFINITION_SHA256,
        "federation v31 definition",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "federated-index.json",
        FEDERATION_INDEX_SHA256,
        "federation v31 index",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "manifest.json",
        FEDERATION_MANIFEST_SHA256,
        "federation v31 manifest",
    )
    if tree_digest(BASE_BUNDLE) != BASE_TREE_SHA256:
        raise CoverageAuditV4Error("accepted coverage v27 tree changed")
    if tree_digest(V71_RELEASE) != V71_TREE_SHA256:
        raise CoverageAuditV4Error("accepted open-seed v71 tree changed")
    if tree_digest(FEDERATION_BUNDLE) != FEDERATION_TREE_SHA256:
        raise CoverageAuditV4Error("accepted federation v31 tree changed")


def definition_document(generated_at: str) -> dict[str, Any]:
    """Return the exact v27-to-v28 definition transform."""

    _parse_utc(generated_at, label="coverage v28 generated_at")
    raw = BASE_DEFINITION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_DEFINITION_SHA256:
        raise CoverageAuditV4Error("accepted coverage v27 definition changed")
    document = json.loads(raw)
    result = deepcopy(document)
    result["audit_id"] = AUDIT_ID
    result["generated_at"] = generated_at

    matches = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise CoverageAuditV4Error("v27 open-seed child boundary changed")
    matches[0].update(
        {
            "expected_manifest_sha256": V71_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v71",
        }
    )
    result["federated_index"] = {
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "path": "../federated_indexes/2026-07-21-public-open-v31",
    }
    replacements = 0
    for references in result["methodology_evidence_classification"].values():
        for reference in references:
            if reference["release_id"] == OLD_RELEASE_ID:
                reference["release_id"] = NEW_RELEASE_ID
                replacements += 1
    if replacements != 12:
        raise CoverageAuditV4Error(
            f"v27 methodology-reference boundary changed: expected 12, got {replacements}"
        )
    serialized = _canonical_json(result)
    for token in REJECTED_LINEAGE_TOKENS:
        if token in serialized:
            raise CoverageAuditV4Error(
                f"rejected lineage token present: {token.decode('ascii')}"
            )
    return result


def _patched_payloads(definition_path: Path) -> Mapping[str, bytes]:
    built = legacy.build_coverage_audit(definition_path)
    payloads = dict(built.payloads)
    manifest = json.loads(payloads[legacy.MANIFEST_FILENAME])
    manifest["definition"]["file"] = DEFINITION.name
    manifest_raw = _canonical_json(manifest)
    payloads[legacy.MANIFEST_FILENAME] = manifest_raw
    payloads[legacy.MANIFEST_HASH_FILENAME] = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {legacy.MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads


def _write_definition_stage(path: Path, raw: bytes) -> None:
    with path.open("r+b") as stream:
        stream.truncate(0)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_bundle_stage(path: Path, payloads: Mapping[str, bytes]) -> None:
    for name, raw in sorted(payloads.items()):
        target = path / name
        with target.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _latest_stage_time(definition_stage: Path, bundle_stage: Path) -> float:
    timestamps: list[float] = []
    for path in (definition_stage, bundle_stage, *bundle_stage.iterdir()):
        metadata = path.stat()
        if not hasattr(metadata, "st_birthtime"):
            raise CoverageAuditV4Error("filesystem birth time is unavailable")
        timestamps.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(timestamps)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise CoverageAuditV4Error("coverage v28 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _discard_bundle_stage(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for entry in path.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditV4Error("refusing contaminated coverage stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CoverageAuditV4Error(
            f"active coverage-v28 publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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
            raise CoverageAuditV4Error(f"refusing replacement of coverage v28: {path}")


def publish_coverage_audit_v28(generated_at: str) -> Mapping[str, Any]:
    """Build privately and no-replace publish the bounded v28 successor."""

    target = _parse_utc(generated_at, label="coverage v28 generated_at")
    _require_inputs()
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CoverageAuditV4Error(f"invalid output parent: {parent}")
    with _publication_lock():
        _require_unpublished()
        descriptor, definition_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.stage-", dir=DEFINITION.parent
        )
        os.close(descriptor)
        definition_stage = Path(definition_name)
        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.stage-", dir=BUNDLE.parent)
        )
        definition_published = False
        bundle_published = False
        try:
            definition_raw = _canonical_json(definition_document(generated_at))
            _write_definition_stage(definition_stage, definition_raw)
            first = _patched_payloads(definition_stage)
            second = _patched_payloads(definition_stage)
            if first != second:
                raise CoverageAuditV4Error("two offline v28 reconstructions differ")
            _write_bundle_stage(bundle_stage, first)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            definition_stage.chmod(0o444)
            legacy.validate_coverage_audit(bundle_stage)
            if _latest_stage_time(definition_stage, bundle_stage) > target.timestamp() + 0.000_001:
                raise CoverageAuditV4Error(
                    "coverage v28 staging exceeded generated_at; refusing publication"
                )
            _wait_until(target)
            _require_unpublished()
            promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            return legacy.validate_coverage_audit(
                BUNDLE, definition_path=DEFINITION
            )
        finally:
            if not bundle_published:
                _discard_bundle_stage(bundle_stage)
            if not definition_published and definition_stage.exists():
                definition_stage.chmod(0o600)
                definition_stage.unlink()


def validate_coverage_audit_v28() -> Mapping[str, Any]:
    """Validate the frozen v28 bundle against all accepted children."""

    _require_inputs()
    document = json.loads(DEFINITION.read_bytes())
    generated = _parse_utc(document["generated_at"], label="coverage v28 generated_at")
    if generated > datetime.now(timezone.utc):
        raise CoverageAuditV4Error("coverage v28 generated_at exceeds wall clock")
    if document != definition_document(document["generated_at"]):
        raise CoverageAuditV4Error("coverage v28 definition is not the bounded successor")
    for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
        metadata = path.stat()
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise CoverageAuditV4Error(
                f"coverage v28 artifact post-dates generated_at: {path}"
            )
    return legacy.validate_coverage_audit(BUNDLE, definition_path=DEFINITION)


__all__ = [
    "AUDIT_ID",
    "BUNDLE",
    "CoverageAuditV4Error",
    "DEFINITION",
    "definition_document",
    "publish_coverage_audit_v28",
    "validate_coverage_audit_v28",
]
