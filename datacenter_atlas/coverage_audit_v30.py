"""Strict public-coverage v30 successor over accepted coverage v29.

The wire schema remains coverage-audit v2. V30 replaces only the accepted
open-seed-v73 and federation-v33 coverage inputs with open-seed-v83 and
federation-v34. Identity v10, timeline v7, master v30, and map v30 are strict
acceptance gates; they are not added as coverage rows or provenance.

The audit remains source scoped. It does not merge child rows, promote review
leads, infer current construction, count unique physical sites, or claim
comparability with SemiAnalysis's public facility statement.
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
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import coverage_audit as base
from . import coverage_audit_v3 as legacy
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v29.json"
BASE_BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v29"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v30.json"
BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v30"

V83_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
V83_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v34.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v34"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v10.json"
)
IDENTITY_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v10"
TIMELINE_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v7.json"
)
TIMELINE_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v7"
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v30.json"
)
MASTER_BUNDLE = ROOT / "construction_master/2026-07-21-public-open-v30"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-21-public-open-v30.json"
MAP_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v30"
PUBLICATION_LOCK = ROOT / ".coverage-audit-v30.lock"

AUDIT_ID = "public-open-coverage-v30"
OLD_RELEASE_ID = "epoch-official-open-seed-v73"
NEW_RELEASE_ID = "epoch-official-open-seed-v83"

BASE_DEFINITION_SHA256 = (
    "ed2ad9f176dedef97f1cf0d91e4894570adf226b89fa460f9edbc9233ed67078"
)
BASE_TREE_SHA256 = (
    "c497902893f477001ec270c611febed97ef6c73ec9ffb35c8ec3080b1cef9ec7"
)
V83_DEFINITION_SHA256 = (
    "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7"
)
V83_MANIFEST_SHA256 = (
    "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5"
)
V83_TREE_SHA256 = (
    "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"
)
FEDERATION_DEFINITION_SHA256 = (
    "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82"
)
FEDERATION_INDEX_SHA256 = (
    "6389e18f6a1085e0a2cba577e412406187ea89d017e921aba6e7fb3edede60ba"
)
FEDERATION_MANIFEST_SHA256 = (
    "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503"
)
FEDERATION_TREE_SHA256 = (
    "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2"
)
IDENTITY_DEFINITION_SHA256 = (
    "b68c6cd6f84405844b518dcf1aa421f86202c7d2f86c1325905333e5f281d78b"
)
IDENTITY_MANIFEST_SHA256 = (
    "5806448df1316aa56e4ba82a63961f5dd0b6337ee455de29929c369288a940fe"
)
IDENTITY_TREE_SHA256 = (
    "22363d1472487077386510c51ee373b15b2c1ee9f6343d80267f98ca4cd4a5fa"
)
TIMELINE_DEFINITION_SHA256 = (
    "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1"
)
TIMELINE_MANIFEST_SHA256 = (
    "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265"
)
TIMELINE_TREE_SHA256 = (
    "b7dd059de068366d12da84970ca750fc3a2872f59069b5563ac47c5e05ce568c"
)
MASTER_DEFINITION_SHA256 = (
    "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63"
)
MASTER_MANIFEST_SHA256 = (
    "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f"
)
MASTER_TREE_SHA256 = (
    "32d3370e3604434886d305c2a0b129458bfbe1c4e823760f0ccc3a16a3519e30"
)

# Installed after map-v30 finals independently passed their validator.
MAP_DEFINITION_SHA256 = (
    "47f2322edd2983bc8ed881edf8e0071d806df304cf773be2e215bcc1806d0847"
)
MAP_MANIFEST_SHA256 = (
    "73108a00068912f83233114fc2ab7ae79087e610d54226762512fe3cc8ef4360"
)
MAP_INDEX_SHA256 = (
    "dc5fcccf70fbd7232062134831bfdd68172013ae5d53a35ee5de8ac1fffaa718"
)
MAP_TREE_SHA256 = (
    "67bc3870ddc2c34308ab0de5defe19ece9d9cea85f6f1ac5c1d4082b18714149"
)

REJECTED_LINEAGE_TOKENS = (
    b"epoch-official-open-seed-v73",
    b"open-seed-2026-07-21-v73",
    b"federation-2026-07-21-public-open-v33",
    b"federated_indexes/2026-07-21-public-open-v33",
    b"exact-identity-decisions-2026-07-21-public-open-v9",
    b"construction-timeline-2026-07-21-public-open-v6",
    b"construction-master-2026-07-21-public-open-v29",
    b"construction-map-2026-07-21-public-open-v29",
    b"public-open-coverage-v29",
)


class CoverageAuditV30Error(RuntimeError):
    """Raised when the bounded v30 transition cannot be proved."""


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
        raise CoverageAuditV30Error(f"{label} is not a regular file: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise CoverageAuditV30Error(
            f"{label} checkpoint changed: expected {expected}, got {actual}"
        )


def _require_tree(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CoverageAuditV30Error(f"{label} is not a directory: {path}")
    actual = tree_digest(path)
    if actual != expected:
        raise CoverageAuditV30Error(
            f"{label} tree changed: expected {expected}, got {actual}"
        )


def _definition_timestamp(path: Path, keys: Sequence[str], label: str) -> datetime:
    value: Any = json.loads(path.read_bytes())
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise CoverageAuditV30Error(f"{label} timestamp field is absent")
        value = value[key]
    if not isinstance(value, str):
        raise CoverageAuditV30Error(f"{label} timestamp is not a string")
    return _parse_utc(value, label=f"{label} timestamp")


def _require_frozen_dependency(
    definition: Path,
    bundle: Path,
    timestamp_keys: Sequence[str],
    label: str,
) -> datetime:
    timestamp = _definition_timestamp(definition, timestamp_keys, label)
    paths = (definition, bundle, *bundle.rglob("*"))
    for path in paths:
        if path.is_symlink():
            raise CoverageAuditV30Error(f"{label} contains a symlink: {path}")
        metadata = path.stat()
        expected_mode = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise CoverageAuditV30Error(f"{label} is not frozen: {path}")
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > timestamp.timestamp() + 0.000_001:
            raise CoverageAuditV30Error(f"{label} post-dates its timestamp: {path}")
    for root in (definition, bundle):
        if root.stat().st_ctime + 0.000_001 < timestamp.timestamp():
            raise CoverageAuditV30Error(f"{label} final rename predates its timestamp")
    return timestamp


def _require_map_configuration() -> None:
    for label, value in (
        ("map v30 definition", MAP_DEFINITION_SHA256),
        ("map v30 manifest", MAP_MANIFEST_SHA256),
        ("map v30 index", MAP_INDEX_SHA256),
        ("map v30 tree", MAP_TREE_SHA256),
    ):
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise CoverageAuditV30Error(f"{label} pin is not configured")


def _dependency_times() -> tuple[tuple[str, datetime], ...]:
    return (
        (
            "accepted coverage v29",
            _require_frozen_dependency(
                BASE_DEFINITION, BASE_BUNDLE, ("generated_at",), "coverage v29"
            ),
        ),
        (
            "accepted open-seed v83",
            _require_frozen_dependency(
                V83_DEFINITION,
                V83_RELEASE,
                ("build", "recorded_at"),
                "open-seed v83",
            ),
        ),
        (
            "accepted federation v34",
            _require_frozen_dependency(
                FEDERATION_DEFINITION,
                FEDERATION_BUNDLE,
                ("generated_at",),
                "federation v34",
            ),
        ),
        (
            "accepted identity v10",
            _require_frozen_dependency(
                IDENTITY_DEFINITION,
                IDENTITY_BUNDLE,
                ("recorded_at",),
                "identity v10",
            ),
        ),
        (
            "accepted timeline v7",
            _require_frozen_dependency(
                TIMELINE_DEFINITION,
                TIMELINE_BUNDLE,
                ("generated_at",),
                "timeline v7",
            ),
        ),
        (
            "accepted master v30",
            _require_frozen_dependency(
                MASTER_DEFINITION,
                MASTER_BUNDLE,
                ("generated_at",),
                "master v30",
            ),
        ),
        (
            "accepted map v30",
            _require_frozen_dependency(
                MAP_DEFINITION, MAP_BUNDLE, ("generated_at",), "map v30"
            ),
        ),
    )


def _require_inputs() -> None:
    _require_checkpoint(BASE_DEFINITION, BASE_DEFINITION_SHA256, "coverage v29 definition")
    _require_tree(BASE_BUNDLE, BASE_TREE_SHA256, "accepted coverage v29")
    _require_checkpoint(V83_DEFINITION, V83_DEFINITION_SHA256, "open-seed v83 definition")
    _require_checkpoint(
        V83_RELEASE / "manifest.json", V83_MANIFEST_SHA256, "open-seed v83 manifest"
    )
    _require_tree(V83_RELEASE, V83_TREE_SHA256, "accepted open-seed v83")
    _require_checkpoint(
        FEDERATION_DEFINITION,
        FEDERATION_DEFINITION_SHA256,
        "federation v34 definition",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "federated-index.json",
        FEDERATION_INDEX_SHA256,
        "federation v34 index",
    )
    _require_checkpoint(
        FEDERATION_BUNDLE / "manifest.json",
        FEDERATION_MANIFEST_SHA256,
        "federation v34 manifest",
    )
    _require_tree(FEDERATION_BUNDLE, FEDERATION_TREE_SHA256, "accepted federation v34")
    _require_checkpoint(
        IDENTITY_DEFINITION, IDENTITY_DEFINITION_SHA256, "identity v10 definition"
    )
    _require_checkpoint(
        IDENTITY_BUNDLE / "manifest.json",
        IDENTITY_MANIFEST_SHA256,
        "identity v10 manifest",
    )
    _require_tree(IDENTITY_BUNDLE, IDENTITY_TREE_SHA256, "accepted identity v10")
    _require_checkpoint(
        TIMELINE_DEFINITION, TIMELINE_DEFINITION_SHA256, "timeline v7 definition"
    )
    _require_checkpoint(
        TIMELINE_BUNDLE / "manifest.json",
        TIMELINE_MANIFEST_SHA256,
        "timeline v7 manifest",
    )
    _require_tree(TIMELINE_BUNDLE, TIMELINE_TREE_SHA256, "accepted timeline v7")
    _require_checkpoint(
        MASTER_DEFINITION, MASTER_DEFINITION_SHA256, "construction master v30 definition"
    )
    _require_checkpoint(
        MASTER_BUNDLE / "manifest.json",
        MASTER_MANIFEST_SHA256,
        "construction master v30 manifest",
    )
    _require_tree(MASTER_BUNDLE, MASTER_TREE_SHA256, "accepted construction master v30")
    _require_map_configuration()
    _require_checkpoint(MAP_DEFINITION, MAP_DEFINITION_SHA256, "construction map v30 definition")
    _require_checkpoint(
        MAP_BUNDLE / "manifest.json", MAP_MANIFEST_SHA256, "construction map v30 manifest"
    )
    _require_checkpoint(
        MAP_BUNDLE / "construction-map-index.json.gz",
        MAP_INDEX_SHA256,
        "construction map v30 index",
    )
    _require_tree(MAP_BUNDLE, MAP_TREE_SHA256, "accepted construction map v30")
    _dependency_times()


def _require_dependencies_before(target: datetime) -> None:
    for label, timestamp in _dependency_times():
        if timestamp >= target:
            raise CoverageAuditV30Error(
                f"{label} is not temporally prior to coverage v30 generated_at"
            )


def definition_document(generated_at: str) -> dict[str, Any]:
    """Return the exact accepted-v29 to v30 definition transform."""

    _parse_utc(generated_at, label="coverage v30 generated_at")
    raw = BASE_DEFINITION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_DEFINITION_SHA256:
        raise CoverageAuditV30Error("accepted coverage v29 definition changed")
    result = deepcopy(json.loads(raw))
    result["audit_id"] = AUDIT_ID
    result["generated_at"] = generated_at

    matches = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise CoverageAuditV30Error("v29 open-seed child boundary changed")
    matches[0].update(
        {
            "expected_manifest_sha256": V83_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v83",
        }
    )
    result["federated_index"] = {
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "path": "../federated_indexes/2026-07-21-public-open-v34",
    }

    replacements = 0
    for references in result["methodology_evidence_classification"].values():
        for reference in references:
            if reference["release_id"] == OLD_RELEASE_ID:
                reference["release_id"] = NEW_RELEASE_ID
                replacements += 1
    if replacements != 12:
        raise CoverageAuditV30Error(
            "v29 methodology-reference boundary changed: "
            f"expected 12, got {replacements}"
        )

    claims = result.get("public_benchmark", {}).get("claims", [])
    facility_claim = [
        claim for claim in claims if claim.get("claim_id") == "facility_scope_count"
    ]
    if len(facility_claim) != 1 or "more than 5,000 facilities" not in facility_claim[
        0
    ].get("paraphrase", ""):
        raise CoverageAuditV30Error("SemiAnalysis public count boundary changed")

    serialized = _canonical_json(result)
    for token in REJECTED_LINEAGE_TOKENS:
        if token in serialized:
            raise CoverageAuditV30Error(
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
                raise CoverageAuditV30Error(
                    f"rejected lineage token present in {name}: {token.decode('ascii')}"
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
            raise CoverageAuditV30Error("filesystem birth time is unavailable")
        timestamps.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(timestamps)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise CoverageAuditV30Error("coverage v30 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _discard_bundle_stage(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for entry in path.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditV30Error("refusing contaminated coverage stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise CoverageAuditV30Error(
            f"active coverage-v30 publication lock exists: {PUBLICATION_LOCK}"
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
            raise CoverageAuditV30Error(f"refusing replacement of coverage v30: {path}")


def publish_coverage_audit_v30(generated_at: str) -> Mapping[str, Any]:
    """Build privately and no-replace publish the bounded v30 successor."""

    target = _parse_utc(generated_at, label="coverage v30 generated_at")
    _require_inputs()
    _require_dependencies_before(target)
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CoverageAuditV30Error(f"invalid output parent: {parent}")
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
                raise CoverageAuditV30Error("two offline v30 reconstructions differ")
            _write_bundle_stage(bundle_stage, first)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            definition_stage.chmod(0o444)
            legacy.validate_coverage_audit(bundle_stage)
            if (
                _latest_stage_time(definition_stage, bundle_stage)
                > target.timestamp() + 0.000_001
            ):
                raise CoverageAuditV30Error(
                    "coverage v30 staging exceeded generated_at; refusing publication"
                )
            _wait_until(target)
            _require_unpublished()
            bundle_stage.chmod(0o755)
            promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            BUNDLE.chmod(0o555)
            promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            for final in (BUNDLE, DEFINITION):
                if final.stat().st_ctime + 0.000_001 < target.timestamp():
                    raise CoverageAuditV30Error(
                        f"coverage v30 final rename predates generated_at: {final.name}"
                    )
            return legacy.validate_coverage_audit(BUNDLE, definition_path=DEFINITION)
        finally:
            if not bundle_published:
                _discard_bundle_stage(bundle_stage)
            if not definition_published and definition_stage.exists():
                definition_stage.chmod(0o600)
                definition_stage.unlink()


def validate_coverage_audit_v30() -> Mapping[str, Any]:
    """Validate frozen v30 against every accepted dependency gate."""

    _require_inputs()
    document = json.loads(DEFINITION.read_bytes())
    generated = _parse_utc(document["generated_at"], label="coverage v30 generated_at")
    if generated > datetime.now(timezone.utc):
        raise CoverageAuditV30Error("coverage v30 generated_at exceeds wall clock")
    _require_dependencies_before(generated)
    if document != definition_document(document["generated_at"]):
        raise CoverageAuditV30Error("coverage v30 definition is not the bounded successor")
    for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
        metadata = path.stat()
        expected_mode = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise CoverageAuditV30Error(f"coverage v30 artifact is not frozen: {path}")
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise CoverageAuditV30Error(
                f"coverage v30 artifact post-dates generated_at: {path}"
            )
    for root in (DEFINITION, BUNDLE):
        if root.stat().st_ctime + 0.000_001 < generated.timestamp():
            raise CoverageAuditV30Error(
                f"coverage v30 final rename predates generated_at: {root}"
            )
    audit = legacy.validate_coverage_audit(BUNDLE, definition_path=DEFINITION)
    if audit["scope"]["children_merged"] is not False:
        raise CoverageAuditV30Error("coverage v30 merged child rows")
    if audit["scope"]["current_status_inferred"] is not False:
        raise CoverageAuditV30Error("coverage v30 inferred current status")
    if audit["totals"]["unique_physical_sites"] is not None:
        raise CoverageAuditV30Error("coverage v30 claimed a unique-site total")
    if audit["scope"]["review_only_rows_separately_counted"] is not True:
        raise CoverageAuditV30Error("coverage v30 merged review-only rows")
    if audit["semianalysis_public_comparison"]["overall_parity"]["status"] != "pending":
        raise CoverageAuditV30Error("coverage v30 claimed SemiAnalysis parity")
    return audit


__all__ = [
    "AUDIT_ID",
    "BUNDLE",
    "CoverageAuditV30Error",
    "DEFINITION",
    "definition_document",
    "publish_coverage_audit_v30",
    "validate_coverage_audit_v30",
]
