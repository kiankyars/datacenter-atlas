"""Strict public-coverage v29 successor over accepted coverage v28.

The wire schema remains coverage-audit v2. V29 replaces only the accepted
open-seed-v71 and federation-v31 coverage inputs with open-seed-v73 and
federation-v33. Identity v9, timeline v6, master v29, and map v29 are
acceptance gates; they are not added as coverage rows or provenance.

The audit remains a source-scoped observation audit. It does not merge child
rows, promote review leads, infer current construction, count unique physical
sites, or claim comparability with SemiAnalysis's public >5,000-facility
statement.
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
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v28.json"
BASE_BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v28"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v29.json"
BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v29"

V73_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v33.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v33"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v9.json"
)
IDENTITY_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v9"
TIMELINE_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v6.json"
)
TIMELINE_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v6"
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v29.json"
)
MASTER_BUNDLE = ROOT / "construction_master/2026-07-21-public-open-v29"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-21-public-open-v29.json"
MAP_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v29"
PUBLICATION_LOCK = ROOT / ".coverage-audit-v29.lock"

AUDIT_ID = "public-open-coverage-v29"
OLD_RELEASE_ID = "epoch-official-open-seed-v71"
NEW_RELEASE_ID = "epoch-official-open-seed-v73"

BASE_DEFINITION_SHA256 = (
    "5fb9f2d544f3411014271461fee8b821d7677a5c6db6ebad70586545e706cff0"
)
BASE_TREE_SHA256 = (
    "5d2f271b5dcd6eee6d2f53f1347370fafad7ff6d32effe0defe5e6516acc2207"
)
V73_DEFINITION_SHA256 = (
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
)
V73_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
V73_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
FEDERATION_DEFINITION_SHA256 = (
    "6472c052092860af73da784b233261c6e8de6a7e9d853d215fa459d5347b4e89"
)
FEDERATION_INDEX_SHA256 = (
    "0d865517b715edf69ccfb8df19ba0ea63b50c8d51167e9c64ff12daf60c5df1a"
)
FEDERATION_MANIFEST_SHA256 = (
    "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b"
)
FEDERATION_TREE_SHA256 = (
    "0fa59ad26d24d6266df33613102828a42e231eb2f231872bc0a9146c9aa0c760"
)
IDENTITY_DEFINITION_SHA256 = (
    "20b9a890b195029d64b29fb7d917956cca09e2062f5d91cc01f981e034aabcc1"
)
IDENTITY_MANIFEST_SHA256 = (
    "47b18c1eeb58eef7d1fa9d70489340e8d2651e428b9d945bc136ecc54c679e6c"
)
IDENTITY_TREE_SHA256 = (
    "a23703e6cf0469c2b81a0252d42c96cac95d64f1c772375c5529d3fb3b4e5a7a"
)
TIMELINE_DEFINITION_SHA256 = (
    "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa"
)
TIMELINE_MANIFEST_SHA256 = (
    "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543"
)
TIMELINE_TREE_SHA256 = (
    "6f754dcaa6f9d0df7ded14a90da70b2eb7c14d75634ec7bd1c503d47ed060e8f"
)
MASTER_DEFINITION_SHA256 = (
    "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d"
)
MASTER_MANIFEST_SHA256 = (
    "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c"
)
MASTER_TREE_SHA256 = (
    "09a76700020e35b1daa95e00cbd6c6bdf90aede9d9f794f5a4c70a607541eff8"
)

# Installed only after map-v29 finals independently passed their validator.
MAP_DEFINITION_SHA256 = (
    "9668c1ee0eadfb755745407a2b140e414044a9c97dfeecaf95b131afbf8446bc"
)
MAP_MANIFEST_SHA256 = (
    "5cfaeba6d854df6aabb4b4c500701d1a3d1d9f7c1e4d1481a986a2602374b889"
)
MAP_TREE_SHA256 = (
    "b551f672a6ce6e82815a0633cc5c7cbd45ce358b9d8f1db1bd8257c4c36fe4b8"
)

REJECTED_LINEAGE_TOKENS = (
    b"open-seed-2026-07-21-v68",
    b"epoch-official-open-seed-v68",
    b"federation-2026-07-21-public-open-v29",
    b"federation-2026-07-21-public-open-v30",
    b"federation-2026-07-21-public-open-v32",
    b"federated_indexes/2026-07-21-public-open-v29",
    b"federated_indexes/2026-07-21-public-open-v30",
    b"federated_indexes/2026-07-21-public-open-v32",
    b"exact-identity-decisions-2026-07-21-public-open-v7",
    b"construction-timeline-2026-07-21-public-open-v4",
)


class CoverageAuditV29Error(RuntimeError):
    """Raised when the bounded v29 transition cannot be proved."""


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
        raise CoverageAuditV29Error(f"{label} is not a regular file: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise CoverageAuditV29Error(
            f"{label} checkpoint changed: expected {expected}, got {actual}"
        )


def _require_tree(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CoverageAuditV29Error(f"{label} is not a directory: {path}")
    actual = tree_digest(path)
    if actual != expected:
        raise CoverageAuditV29Error(
            f"{label} tree changed: expected {expected}, got {actual}"
        )


def _require_map_configuration() -> None:
    for label, value in (
        ("map v29 definition", MAP_DEFINITION_SHA256),
        ("map v29 manifest", MAP_MANIFEST_SHA256),
        ("map v29 tree", MAP_TREE_SHA256),
    ):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise CoverageAuditV29Error(f"{label} pin is not configured")


def _require_inputs() -> None:
    _require_checkpoint(BASE_DEFINITION, BASE_DEFINITION_SHA256, "coverage v28 definition")
    _require_tree(BASE_BUNDLE, BASE_TREE_SHA256, "accepted coverage v28")
    _require_checkpoint(V73_DEFINITION, V73_DEFINITION_SHA256, "open-seed v73 definition")
    _require_checkpoint(
        V73_RELEASE / "manifest.json", V73_MANIFEST_SHA256, "open-seed v73 manifest"
    )
    _require_tree(V73_RELEASE, V73_TREE_SHA256, "accepted open-seed v73")

    _require_checkpoint(
        FEDERATION_DEFINITION,
        FEDERATION_DEFINITION_SHA256,
        "federation v33 definition",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "federated-index.json",
        FEDERATION_INDEX_SHA256,
        "federation v33 index",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "manifest.json",
        FEDERATION_MANIFEST_SHA256,
        "federation v33 manifest",
    )
    _require_tree(FEDERATION_BUNDLE, FEDERATION_TREE_SHA256, "accepted federation v33")

    _require_checkpoint(
        IDENTITY_DEFINITION,
        IDENTITY_DEFINITION_SHA256,
        "identity v9 definition",
    )
    _require_checkpoint(
        IDENTITY_BUNDLE / "manifest.json",
        IDENTITY_MANIFEST_SHA256,
        "identity v9 manifest",
    )
    _require_tree(IDENTITY_BUNDLE, IDENTITY_TREE_SHA256, "accepted identity v9")

    _require_checkpoint(
        TIMELINE_DEFINITION,
        TIMELINE_DEFINITION_SHA256,
        "timeline v6 definition",
    )
    _require_checkpoint(
        TIMELINE_BUNDLE / "manifest.json",
        TIMELINE_MANIFEST_SHA256,
        "timeline v6 manifest",
    )
    _require_tree(TIMELINE_BUNDLE, TIMELINE_TREE_SHA256, "accepted timeline v6")

    _require_checkpoint(
        MASTER_DEFINITION,
        MASTER_DEFINITION_SHA256,
        "construction master v29 definition",
    )
    _require_checkpoint(
        MASTER_BUNDLE / "manifest.json",
        MASTER_MANIFEST_SHA256,
        "construction master v29 manifest",
    )
    _require_tree(MASTER_BUNDLE, MASTER_TREE_SHA256, "accepted construction master v29")

    _require_map_configuration()
    _require_checkpoint(
        MAP_DEFINITION, MAP_DEFINITION_SHA256, "construction map v29 definition"
    )
    _require_checkpoint(
        MAP_BUNDLE / "manifest.json",
        MAP_MANIFEST_SHA256,
        "construction map v29 manifest",
    )
    _require_tree(MAP_BUNDLE, MAP_TREE_SHA256, "accepted construction map v29")


def definition_document(generated_at: str) -> dict[str, Any]:
    """Return the exact accepted-v28 to v29 definition transform."""

    _parse_utc(generated_at, label="coverage v29 generated_at")
    raw = BASE_DEFINITION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_DEFINITION_SHA256:
        raise CoverageAuditV29Error("accepted coverage v28 definition changed")
    document = json.loads(raw)
    result = deepcopy(document)
    result["audit_id"] = AUDIT_ID
    result["generated_at"] = generated_at

    matches = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise CoverageAuditV29Error("v28 open-seed child boundary changed")
    matches[0].update(
        {
            "expected_manifest_sha256": V73_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v73",
        }
    )
    result["federated_index"] = {
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "path": "../federated_indexes/2026-07-21-public-open-v33",
    }

    replacements = 0
    for references in result["methodology_evidence_classification"].values():
        for reference in references:
            if reference["release_id"] == OLD_RELEASE_ID:
                reference["release_id"] = NEW_RELEASE_ID
                replacements += 1
    if replacements != 12:
        raise CoverageAuditV29Error(
            "v28 methodology-reference boundary changed: "
            f"expected 12, got {replacements}"
        )

    benchmark = result.get("public_benchmark", {})
    claims = benchmark.get("claims", [])
    facility_claim = [claim for claim in claims if claim.get("claim_id") == "facility_scope_count"]
    if len(facility_claim) != 1 or "more than 5,000 facilities" not in facility_claim[0].get(
        "paraphrase", ""
    ):
        raise CoverageAuditV29Error("SemiAnalysis public count boundary changed")

    serialized = _canonical_json(result)
    for token in REJECTED_LINEAGE_TOKENS:
        if token in serialized:
            raise CoverageAuditV29Error(
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
    for name, raw in payloads.items():
        for token in REJECTED_LINEAGE_TOKENS:
            if token in raw:
                raise CoverageAuditV29Error(
                    "rejected lineage token present in "
                    f"{name}: {token.decode('ascii')}"
                )
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
            raise CoverageAuditV29Error("filesystem birth time is unavailable")
        timestamps.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(timestamps)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise CoverageAuditV29Error("coverage v29 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _discard_bundle_stage(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for entry in path.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditV29Error("refusing contaminated coverage stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise CoverageAuditV29Error(
            f"active coverage-v29 publication lock exists: {PUBLICATION_LOCK}"
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
            raise CoverageAuditV29Error(f"refusing replacement of coverage v29: {path}")


def publish_coverage_audit_v29(generated_at: str) -> Mapping[str, Any]:
    """Build privately and no-replace publish the bounded v29 successor."""

    target = _parse_utc(generated_at, label="coverage v29 generated_at")
    _require_inputs()
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CoverageAuditV29Error(f"invalid output parent: {parent}")
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
                raise CoverageAuditV29Error("two offline v29 reconstructions differ")
            _write_bundle_stage(bundle_stage, first)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o755)
            bundle_stage.chmod(0o555)
            definition_stage.chmod(0o444)
            legacy.validate_coverage_audit(bundle_stage)
            if _latest_stage_time(definition_stage, bundle_stage) > target.timestamp() + 0.000_001:
                raise CoverageAuditV29Error(
                    "coverage v29 staging exceeded generated_at; refusing publication"
                )
            _wait_until(target)
            _require_unpublished()
            # Darwin RENAME_EXCL rejects a read-only source directory. Payload
            # members remain 0444 while the root is briefly 0755 for promotion.
            bundle_stage.chmod(0o755)
            promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            BUNDLE.chmod(0o555)
            promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            for final in (BUNDLE, DEFINITION):
                if final.stat().st_ctime + 0.000_001 < target.timestamp():
                    raise CoverageAuditV29Error(
                        f"coverage v29 final rename predates generated_at: {final.name}"
                    )
            return legacy.validate_coverage_audit(BUNDLE, definition_path=DEFINITION)
        finally:
            if not bundle_published:
                _discard_bundle_stage(bundle_stage)
            if not definition_published and definition_stage.exists():
                definition_stage.chmod(0o600)
                definition_stage.unlink()


def validate_coverage_audit_v29() -> Mapping[str, Any]:
    """Validate frozen v29 against every accepted dependency gate."""

    _require_inputs()
    document = json.loads(DEFINITION.read_bytes())
    generated = _parse_utc(document["generated_at"], label="coverage v29 generated_at")
    if generated > datetime.now(timezone.utc):
        raise CoverageAuditV29Error("coverage v29 generated_at exceeds wall clock")
    if document != definition_document(document["generated_at"]):
        raise CoverageAuditV29Error("coverage v29 definition is not the bounded successor")
    for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
        metadata = path.stat()
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise CoverageAuditV29Error(
                f"coverage v29 artifact post-dates generated_at: {path}"
            )
    for root in (DEFINITION, BUNDLE):
        if root.stat().st_ctime + 0.000_001 < generated.timestamp():
            raise CoverageAuditV29Error(
                f"coverage v29 final rename predates generated_at: {root}"
            )
    audit = legacy.validate_coverage_audit(BUNDLE, definition_path=DEFINITION)
    if audit["scope"]["current_status_inferred"] is not False:
        raise CoverageAuditV29Error("coverage v29 inferred current status")
    if audit["totals"]["unique_physical_sites"] is not None:
        raise CoverageAuditV29Error("coverage v29 claimed a unique-site total")
    if audit["scope"]["review_only_rows_separately_counted"] is not True:
        raise CoverageAuditV29Error("coverage v29 merged review-only rows")
    return audit


__all__ = [
    "AUDIT_ID",
    "BUNDLE",
    "CoverageAuditV29Error",
    "DEFINITION",
    "definition_document",
    "publish_coverage_audit_v29",
    "validate_coverage_audit_v29",
]
